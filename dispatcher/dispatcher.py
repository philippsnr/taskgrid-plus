import sys
import os
import time
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "proto"))

import grpc
import taskgrid_pb2
import taskgrid_pb2_grpc
from common.logger import get_logger

logger = get_logger("dispatcher")


# ── Data structures ────────────────────────────────────────────────────────


@dataclass
class TaskRecord:
    """In-memory representation of a task."""
    id: int
    type: str
    payload: str
    status: taskgrid_pb2.TaskStatus
    timestamp_created: int  # unix epoch ms
    timestamp_dispatched: int = 0
    timestamp_completed: int = 0
    result: str = ""
    retry_count: int = 0
    assigned_worker: str = ""


class TaskQueue:
    """Thread-safe in-memory task queue."""

    def __init__(self) -> None:
        self._queue: deque = deque()
        self._lock = threading.Lock()

    def enqueue(self, task_id: int) -> None:
        """Enqueue a task ID in FIFO order."""
        with self._lock:
            self._queue.append(task_id)

    def dequeue(self) -> Optional[int]:
        """Dequeue a task ID, or None if queue is empty."""
        with self._lock:
            if self._queue:
                return self._queue.popleft()
            return None

    def size(self) -> int:
        """Return current queue size."""
        with self._lock:
            return len(self._queue)


class TaskStore:
    """Thread-safe persistent task storage (in-memory dict)."""

    def __init__(self) -> None:
        self._tasks: Dict[int, TaskRecord] = {}
        self._lock = threading.Lock()

    def put(self, task: TaskRecord) -> None:
        """Store a task record."""
        with self._lock:
            self._tasks[task.id] = task

    def get(self, task_id: int) -> Optional[TaskRecord]:
        """Retrieve a task record by ID."""
        with self._lock:
            return self._tasks.get(task_id)

    def all(self) -> Dict[int, TaskRecord]:
        """Return a copy of all task records."""
        with self._lock:
            return dict(self._tasks)


class Dispatcher:
    """Main Dispatcher service implementation."""

    def __init__(self) -> None:
        self._task_queue = TaskQueue()
        self._task_store = TaskStore()
        self._next_task_id = 1
        self._id_lock = threading.Lock()

    def _allocate_task_id(self) -> int:
        """Allocate a unique, monotonically increasing task ID."""
        with self._id_lock:
            task_id = self._next_task_id
            self._next_task_id += 1
            return task_id

    def _get_current_timestamp_ms(self) -> int:
        """Return current time in milliseconds since epoch."""
        return int(time.time() * 1000)

    # ── Task state transitions ────────────────────────────────────────────────

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

    def on_task_timeout(self, request_id: str, task_id: int) -> None:
        logger.warning(request_id=request_id, task_id=task_id, status="TIMEOUT")

    def on_task_retrying(self, request_id: str, task_id: int, retry_count: int) -> None:
        logger.warning(request_id=request_id, task_id=task_id, status="RETRYING", retry_count=retry_count)

    # ── Dispatch decisions ────────────────────────────────────────────────────

    def on_worker_selected(self, request_id: str, task_id: int, worker_id: str, strategy: str) -> None:
        logger.debug(request_id=request_id, task_id=task_id, event="WORKER_SELECTED", worker=worker_id, strategy=strategy)

    def on_no_worker_available(self, request_id: str, task_id: int, task_type: str) -> None:
        logger.warning(request_id=request_id, task_id=task_id, event="NO_WORKER", type=task_type)

    # ── Result handling ───────────────────────────────────────────────────────

    def on_result_received(self, request_id: str, task_id: int, worker_id: str, success: bool) -> None:
        logger.info(request_id=request_id, task_id=task_id, event="RESULT_RECEIVED", worker=worker_id, success=success)

    # ── gRPC service implementation ────────────────────────────────────────────

    def post_task(
        self, request: taskgrid_pb2.PostTaskRequest
    ) -> taskgrid_pb2.PostTaskResponse:
        """Handle PostTask RPC: receive task, assign ID, and queue it."""
        request_id = request.header.request_id
        task_type = request.type
        payload = request.payload

        # Validate input
        if not task_type or not task_type.strip():
            error_msg = "type is required and cannot be empty"
            logger.error(request_id=request_id, event="VALIDATION_ERROR", error=error_msg)
            return taskgrid_pb2.PostTaskResponse(
                header=taskgrid_pb2.MessageHeader(
                    message_type="PostTaskResponse",
                    request_id=request_id,
                    timestamp=self._get_current_timestamp_ms(),
                    sender="dispatcher",
                ),
                success=False,
                task_id=0,
                message=error_msg,
            )

        if not payload or not payload.strip():
            error_msg = "payload is required and cannot be empty"
            logger.error(request_id=request_id, event="VALIDATION_ERROR", error=error_msg)
            return taskgrid_pb2.PostTaskResponse(
                header=taskgrid_pb2.MessageHeader(
                    message_type="PostTaskResponse",
                    request_id=request_id,
                    timestamp=self._get_current_timestamp_ms(),
                    sender="dispatcher",
                ),
                success=False,
                task_id=0,
                message=error_msg,
            )

        # Allocate unique task ID
        task_id = self._allocate_task_id()

        # Log CREATED state
        self.on_task_received(request_id, task_id, task_type)

        # Create task record and transition to QUEUED
        now_ms = self._get_current_timestamp_ms()
        task_record = TaskRecord(
            id=task_id,
            type=task_type,
            payload=payload,
            status=taskgrid_pb2.QUEUED,
            timestamp_created=now_ms,
        )
        self._task_store.put(task_record)

        # Log QUEUED state
        self.on_task_queued(request_id, task_id, task_type)

        # Enqueue task for dispatcher loop to pick up
        self._task_queue.enqueue(task_id)

        # Return success response
        return taskgrid_pb2.PostTaskResponse(
            header=taskgrid_pb2.MessageHeader(
                message_type="PostTaskResponse",
                request_id=request_id,
                timestamp=now_ms,
                sender="dispatcher",
            ),
            success=True,
            task_id=task_id,
            message="Task queued successfully",
        )
