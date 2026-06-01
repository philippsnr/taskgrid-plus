import sys
import os
import time
import threading
import uuid
from collections import deque
from dataclasses import dataclass, field, replace
from typing import Dict, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "proto"))

import grpc
import taskgrid_pb2
import taskgrid_pb2_grpc
from common.logger import get_logger

logger = get_logger("dispatcher")

_NAMESERVICE_RETRY_DELAY_SEC = 5  # backoff when nameservice is temporarily unavailable


# ── Data structures ────────────────────────────────────────────────────────


@dataclass
class TaskRecord:
    id: int
    type: str
    payload: str
    status: taskgrid_pb2.TaskStatus
    timestamp_created: int  # unix epoch ms
    timestamp_dispatched: int = 0
    timestamp_completed: int = 0
    result: str = ""
    error_message: str = ""
    retry_count: int = 0
    assigned_worker: str = ""
    last_failed_worker: str = ""


class TaskQueue:
    """Thread-safe in-memory FIFO task queue."""

    def __init__(self) -> None:
        self._queue: deque = deque()
        self._lock = threading.Lock()

    def enqueue(self, task_id: int) -> None:
        with self._lock:
            self._queue.append(task_id)

    def dequeue(self) -> Optional[int]:
        with self._lock:
            if self._queue:
                return self._queue.popleft()
            return None

    def size(self) -> int:
        with self._lock:
            return len(self._queue)


class TaskStore:
    """Thread-safe in-memory task storage."""

    def __init__(self) -> None:
        self._tasks: Dict[int, TaskRecord] = {}
        self._lock = threading.Lock()

    def put(self, task: TaskRecord) -> None:
        with self._lock:
            self._tasks[task.id] = task

    def get(self, task_id: int) -> Optional[TaskRecord]:
        with self._lock:
            return self._tasks.get(task_id)

    def update(self, task_id: int, **kwargs) -> Optional[TaskRecord]:
        """Atomically update fields of a stored task and return the updated record."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            updated = replace(task, **kwargs)
            self._tasks[task_id] = updated
            return updated

    def all(self) -> Dict[int, TaskRecord]:
        with self._lock:
            return dict(self._tasks)


class Dispatcher:

    def __init__(self) -> None:
        self._task_queue = TaskQueue()
        self._task_store = TaskStore()
        self._next_task_id = 1
        self._id_lock = threading.Lock()
        # worker_id → grpc.Channel (cached, reused across dispatches)
        self._worker_channels: Dict[str, grpc.Channel] = {}
        self._worker_channels_lock = threading.Lock()
        # shared nameservice stub (lazy-init, thread-safe via lock)
        self._nameservice_addr: Optional[str] = None
        self._nameservice_channel: Optional[grpc.Channel] = None
        self._nameservice_stub: Optional[taskgrid_pb2_grpc.NameServiceStub] = None
        self._nameservice_lock = threading.Lock()

    def _allocate_task_id(self) -> int:
        with self._id_lock:
            task_id = self._next_task_id
            self._next_task_id += 1
            return task_id

    def _get_current_timestamp_ms(self) -> int:
        return int(time.time() * 1000)

    def _make_header(self, message_type: str, request_id: str) -> taskgrid_pb2.MessageHeader:
        return taskgrid_pb2.MessageHeader(
            message_type=message_type,
            request_id=request_id,
            timestamp=self._get_current_timestamp_ms(),
            sender="dispatcher",
        )

    # ── Task state transition logging ─────────────────────────────────────────

    def on_task_received(self, request_id: str, task_id: int, task_type: str) -> None:
        logger.info(request_id=request_id, task_id=task_id, status="CREATED", type=task_type)

    def on_task_queued(self, request_id: str, task_id: int, task_type: str) -> None:
        logger.info(request_id=request_id, task_id=task_id, status="QUEUED", type=task_type)

    def on_task_dispatched(self, request_id: str, task_id: int, worker_id: str) -> None:
        logger.info(request_id=request_id, task_id=task_id, status="DISPATCHED", worker=worker_id)

    def on_task_completed(self, request_id: str, task_id: int, duration_ms: int) -> None:
        logger.info(request_id=request_id, task_id=task_id, status="COMPLETED", duration_ms=duration_ms)

    def on_task_failed(self, request_id: str, task_id: int, error: str) -> None:
        logger.error(request_id=request_id, task_id=task_id, status="FAILED", error=error)

    def on_task_timeout(self, request_id: str, task_id: int, worker: str, elapsed_ms: int) -> None:
        logger.warning(request_id=request_id, task_id=task_id, status="TIMEOUT", worker=worker, elapsed_ms=elapsed_ms)

    def on_task_retrying(self, request_id: str, task_id: int, retry_count: int) -> None:
        logger.warning(request_id=request_id, task_id=task_id, status="RETRYING", retry_count=retry_count)

    def on_worker_selected(self, request_id: str, task_id: int, worker_id: str, strategy: str) -> None:
        logger.debug(request_id=request_id, task_id=task_id, event="WORKER_SELECTED", worker=worker_id, strategy=strategy)

    def on_unknown_task_type(self, request_id: str, task_type: str) -> None:
        logger.error(request_id=request_id, event="UNKNOWN_TASK_TYPE", type=task_type)

    def on_no_worker_available(self, request_id: str, task_id: int, task_type: str) -> None:
        logger.warning(request_id=request_id, task_id=task_id, event="NO_WORKER", type=task_type)

    def on_result_received(self, request_id: str, task_id: int, worker_id: str, success: bool) -> None:
        logger.info(request_id=request_id, task_id=task_id, event="RESULT_RECEIVED", worker=worker_id, success=success)

    # ── Nameservice stub ──────────────────────────────────────────────────────

    def _get_nameservice_stub(self) -> Optional[taskgrid_pb2_grpc.NameServiceStub]:
        with self._nameservice_lock:
            if self._nameservice_stub is None:
                if self._nameservice_addr is None:
                    return None
                self._nameservice_channel = grpc.insecure_channel(self._nameservice_addr)
                self._nameservice_stub = taskgrid_pb2_grpc.NameServiceStub(self._nameservice_channel)
            return self._nameservice_stub

    # ── gRPC: PostTask ────────────────────────────────────────────────────────

    def post_task(self, request: taskgrid_pb2.PostTaskRequest) -> taskgrid_pb2.PostTaskResponse:
        request_id = request.header.request_id
        task_type = request.type
        payload = request.payload

        if not task_type or not task_type.strip():
            error_msg = "type is required and cannot be empty"
            logger.error(request_id=request_id, event="VALIDATION_ERROR", error=error_msg)
            return taskgrid_pb2.PostTaskResponse(
                header=self._make_header("PostTaskResponse", request_id),
                success=False,
                task_id=0,
                message=error_msg,
            )

        if not payload or not payload.strip():
            error_msg = "payload is required and cannot be empty"
            logger.error(request_id=request_id, event="VALIDATION_ERROR", error=error_msg)
            return taskgrid_pb2.PostTaskResponse(
                header=self._make_header("PostTaskResponse", request_id),
                success=False,
                task_id=0,
                message=error_msg,
            )

        stub = self._get_nameservice_stub()
        if stub is not None:
            try:
                lookup = stub.LookupWorker(
                    taskgrid_pb2.LookupWorkerRequest(
                        header=self._make_header("LookupWorkerRequest", request_id),
                        type=task_type,
                    ),
                    timeout=5,
                )
                if not lookup.workers:
                    error_msg = f"no worker registered for task type '{task_type}'"
                    self.on_unknown_task_type(request_id, task_type)
                    return taskgrid_pb2.PostTaskResponse(
                        header=self._make_header("PostTaskResponse", request_id),
                        success=False,
                        task_id=0,
                        message=error_msg,
                    )
            except grpc.RpcError as e:
                logger.warning(request_id=request_id, event="NAMESERVICE_UNAVAILABLE_ON_POST", error=str(e.details()))

        task_id = self._allocate_task_id()
        self.on_task_received(request_id, task_id, task_type)

        now_ms = self._get_current_timestamp_ms()
        task_record = TaskRecord(
            id=task_id,
            type=task_type,
            payload=payload,
            status=taskgrid_pb2.QUEUED,
            timestamp_created=now_ms,
        )
        self._task_store.put(task_record)
        self.on_task_queued(request_id, task_id, task_type)
        self._task_queue.enqueue(task_id)

        return taskgrid_pb2.PostTaskResponse(
            header=self._make_header("PostTaskResponse", request_id),
            success=True,
            task_id=task_id,
            message="Task queued successfully",
        )

    # ── gRPC: GetResult ───────────────────────────────────────────────────────

    def get_result(self, request: taskgrid_pb2.GetResultRequest) -> taskgrid_pb2.GetResultResponse:
        request_id = request.header.request_id
        task_id = request.task_id
        task = self._task_store.get(task_id)

        if task is None:
            return taskgrid_pb2.GetResultResponse(
                header=self._make_header("GetResultResponse", request_id),
                success=False,
                task_id=task_id,
                status=taskgrid_pb2.TASK_STATUS_UNSPECIFIED,
                message=f"task {task_id} not found",
            )

        terminal_error = task.status in (taskgrid_pb2.FAILED, taskgrid_pb2.TIMEOUT)
        return taskgrid_pb2.GetResultResponse(
            header=self._make_header("GetResultResponse", request_id),
            success=True,
            task_id=task_id,
            result=task.result,
            status=task.status,
            message=task.error_message if terminal_error else "",
        )

    # ── gRPC: ReturnResult (Worker → Dispatcher) ──────────────────────────────

    def return_result(self, request: taskgrid_pb2.ReturnResultRequest) -> taskgrid_pb2.ReturnResultResponse:
        request_id = request.header.request_id
        task_id = request.task_id
        worker_id = request.worker_id

        task = self._task_store.get(task_id)
        if task is None:
            logger.error(request_id=request_id, event="RESULT_UNKNOWN_TASK", task_id=task_id, worker=worker_id)
            return taskgrid_pb2.ReturnResultResponse(
                header=self._make_header("ReturnResultResponse", request_id),
                success=False,
                message=f"task {task_id} not found",
            )

        if task.status not in (taskgrid_pb2.DISPATCHED, taskgrid_pb2.PROCESSING):
            if task.status == taskgrid_pb2.COMPLETED:
                logger.warning(request_id=request_id, event="RESULT_DUPLICATE", task_id=task_id, worker=worker_id)
            else:
                logger.warning(request_id=request_id, event="RESULT_STALE_STATE", task_id=task_id, worker=worker_id, status=task.status)
            return taskgrid_pb2.ReturnResultResponse(
                header=self._make_header("ReturnResultResponse", request_id),
                success=False,
                message=f"task {task_id} is not in an active state",
            )

        if task.assigned_worker and worker_id != task.assigned_worker:
            logger.warning(
                request_id=request_id,
                event="RESULT_WRONG_WORKER",
                task_id=task_id,
                worker=worker_id,
                assigned=task.assigned_worker,
            )
            return taskgrid_pb2.ReturnResultResponse(
                header=self._make_header("ReturnResultResponse", request_id),
                success=False,
                message=f"task {task_id} is assigned to a different worker",
            )

        now_ms = self._get_current_timestamp_ms()
        if request.success:
            self._task_store.update(
                task_id,
                status=taskgrid_pb2.COMPLETED,
                result=request.result,
                timestamp_completed=now_ms,
            )
            duration_ms = now_ms - task.timestamp_dispatched
            self.on_task_completed(request_id, task_id, duration_ms)
        else:
            self._task_store.update(
                task_id,
                status=taskgrid_pb2.FAILED,
                timestamp_completed=now_ms,
                error_message=request.error_message,
            )
            self.on_task_failed(request_id, task_id, request.error_message)

        self.on_result_received(request_id, task_id, worker_id, request.success)

        return taskgrid_pb2.ReturnResultResponse(
            header=self._make_header("ReturnResultResponse", request_id),
            success=True,
            message="",
        )

    # ── Background dispatch loop ──────────────────────────────────────────────

    def start_dispatch_loop(self, nameservice_addr: str, task_timeout_sec: int = 60, max_retries: int = 3) -> None:
        """Start background threads for dispatch and per-task timeout checking."""
        with self._nameservice_lock:
            self._nameservice_addr = nameservice_addr
        self._task_timeout_ms = task_timeout_sec * 1000
        self._max_retries = max_retries

        threading.Thread(
            target=self._dispatch_loop,
            args=(nameservice_addr,),
            daemon=True,
            name="dispatch-loop",
        ).start()

        threading.Thread(
            target=self._timeout_loop,
            daemon=True,
            name="timeout-checker",
        ).start()

        logger.info(event="DISPATCH_LOOP_STARTED", nameservice_addr=nameservice_addr, task_timeout_sec=task_timeout_sec)

    def _timeout_loop(self) -> None:
        while True:
            time.sleep(5)
            try:
                now_ms = self._get_current_timestamp_ms()
                for task in self._task_store.all().values():
                    if task.status not in (taskgrid_pb2.DISPATCHED, taskgrid_pb2.PROCESSING):
                        continue
                    if task.timestamp_dispatched == 0:
                        continue
                    elapsed_ms = now_ms - task.timestamp_dispatched
                    if elapsed_ms <= self._task_timeout_ms:
                        continue
                    request_id = str(uuid.uuid4())
                    timed_out_worker = task.assigned_worker
                    self._task_store.update(task.id, status=taskgrid_pb2.TIMEOUT)
                    self.on_task_timeout(request_id, task.id, timed_out_worker, elapsed_ms)
                    if task.retry_count < self._max_retries:
                        new_count = task.retry_count + 1
                        self._task_store.update(
                            task.id,
                            status=taskgrid_pb2.RETRYING,
                            last_failed_worker=timed_out_worker,
                            assigned_worker="",
                            timestamp_dispatched=0,
                            retry_count=new_count,
                        )
                        self.on_task_retrying(request_id, task.id, new_count)
                        self._task_store.update(task.id, status=taskgrid_pb2.QUEUED)
                        self._task_queue.enqueue(task.id)
                    else:
                        self._task_store.update(
                            task.id,
                            status=taskgrid_pb2.FAILED,
                            timestamp_completed=now_ms,
                            error_message="task timed out after maximum retries",
                        )
                        self.on_task_failed(request_id, task.id, "task timed out after maximum retries")
            except Exception as e:
                logger.error(event="TIMEOUT_LOOP_ERROR", error=str(e))

    def _dispatch_loop(self, nameservice_addr: str) -> None:
        while True:
            task_id = self._task_queue.dequeue()
            if task_id is None:
                time.sleep(0.1)
                continue

            task = self._task_store.get(task_id)
            if task is None:
                continue

            nameservice_stub = self._get_nameservice_stub()
            if nameservice_stub is None:
                self._task_queue.enqueue(task_id)
                time.sleep(1.0)
                continue

            request_id = str(uuid.uuid4())
            worker, nameservice_failed = self._select_worker(nameservice_stub, request_id, task_id, task.type, exclude_worker=task.last_failed_worker)
            if worker is None:
                if nameservice_failed:
                    # Nameservice temporarily unavailable — keep task queued and back off
                    self._task_queue.enqueue(task_id)
                    time.sleep(_NAMESERVICE_RETRY_DELAY_SEC)
                elif task.retry_count > 0:
                    # Retry after timeout: no alternative worker available → FAILED
                    now_ms = self._get_current_timestamp_ms()
                    self._task_store.update(
                        task_id,
                        status=taskgrid_pb2.FAILED,
                        timestamp_completed=now_ms,
                        error_message="no alternative worker available for retry",
                    )
                    self.on_task_failed(request_id, task_id, "no alternative worker available for retry")
                else:
                    # First dispatch attempt; re-queue and back off briefly before retrying
                    self._task_queue.enqueue(task_id)
                    time.sleep(1.0)
                continue

            self._dispatch_to_worker(request_id, task, worker)

    def _select_worker(
        self,
        nameservice_stub: taskgrid_pb2_grpc.NameServiceStub,
        request_id: str,
        task_id: int,
        task_type: str,
        exclude_worker: str = "",
    ) -> tuple[Optional[taskgrid_pb2.Worker], bool]:
        """Returns (worker, nameservice_unavailable).

        nameservice_unavailable=True means the RPC call itself failed (transient outage).
        nameservice_unavailable=False means the call succeeded but no suitable worker exists.
        """
        try:
            response = nameservice_stub.LookupWorker(
                taskgrid_pb2.LookupWorkerRequest(
                    header=self._make_header("LookupWorkerRequest", request_id),
                    type=task_type,
                )
            )
        except grpc.RpcError as e:
            logger.warning(request_id=request_id, task_id=task_id, event="NAMESERVICE_UNAVAILABLE", error=str(e.details()))
            return None, True

        # Safety filter: keep only ACTIVE workers (NameService should already filter,
        # but this guards against stale registrations slipping through).
        active_workers = [w for w in response.workers if w.status == taskgrid_pb2.ACTIVE]
        if not active_workers:
            # Edge case: all known workers are UNHEALTHY or OFFLINE — do not dispatch.
            self.on_no_worker_available(request_id, task_id, task_type)
            return None, False

        # Selection strategy: Least Load
        # Among the active candidates we pick the worker reporting the lowest
        # current_load.  This spreads work across heterogeneous workers without
        # requiring coordinated state between dispatcher instances.
        #
        # On retry: exclude the worker that caused the previous timeout so the
        # task is handed to a different node when possible.  If only one worker
        # exists, we fall back to using it anyway.
        preferred = [w for w in active_workers if w.worker_id != exclude_worker]
        candidates = preferred if preferred else active_workers
        selected = min(candidates, key=lambda w: w.current_load)
        self.on_worker_selected(request_id, task_id, selected.worker_id, "least_loaded")
        return selected, False

    def _get_or_create_worker_channel(self, worker: taskgrid_pb2.Worker) -> grpc.Channel:
        addr = f"{worker.address}:{worker.port}"
        with self._worker_channels_lock:
            if addr not in self._worker_channels:
                self._worker_channels[addr] = grpc.insecure_channel(addr)
            return self._worker_channels[addr]

    def _dispatch_to_worker(
        self,
        request_id: str,
        task: TaskRecord,
        worker: taskgrid_pb2.Worker,
    ) -> None:
        now_ms = self._get_current_timestamp_ms()
        self._task_store.update(
            task.id,
            status=taskgrid_pb2.DISPATCHED,
            assigned_worker=worker.worker_id,
            timestamp_dispatched=now_ms,
        )
        self.on_task_dispatched(request_id, task.id, worker.worker_id)

        proto_task = taskgrid_pb2.Task(
            id=task.id,
            type=task.type,
            payload=task.payload,
            status=taskgrid_pb2.DISPATCHED,
            timestamp_created=task.timestamp_created,
            timestamp_dispatched=now_ms,
            retry_count=task.retry_count,
            assigned_worker=worker.worker_id,
        )

        try:
            channel = self._get_or_create_worker_channel(worker)
            stub = taskgrid_pb2_grpc.WorkerServiceStub(channel)
            response = stub.ProcessTask(
                taskgrid_pb2.ProcessTaskRequest(
                    header=self._make_header("ProcessTaskRequest", request_id),
                    task=proto_task,
                )
            )
            if response.accepted:
                self._task_store.update(task.id, status=taskgrid_pb2.PROCESSING)
                logger.info(request_id=request_id, task_id=task.id, status="PROCESSING", worker=worker.worker_id)
            else:
                logger.warning(
                    request_id=request_id,
                    task_id=task.id,
                    event="WORKER_REJECTED",
                    worker=worker.worker_id,
                    message=response.message,
                )
                # Re-queue if worker rejected
                self._task_store.update(task.id, status=taskgrid_pb2.QUEUED, assigned_worker="", timestamp_dispatched=0)
                self._task_queue.enqueue(task.id)
        except grpc.RpcError as e:
            logger.error(
                request_id=request_id,
                task_id=task.id,
                event="WORKER_UNREACHABLE",
                worker=worker.worker_id,
                error=str(e.details()),
            )
            # Re-queue on connection failure
            self._task_store.update(task.id, status=taskgrid_pb2.QUEUED, assigned_worker="", timestamp_dispatched=0)
            self._task_queue.enqueue(task.id)
