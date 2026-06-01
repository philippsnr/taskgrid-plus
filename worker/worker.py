import os
import signal
import sys
import threading
import time
import uuid
from concurrent import futures
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "proto"))

import grpc

import taskgrid_pb2
import taskgrid_pb2_grpc
from common.logger import get_logger


def _now_ms() -> int:
    """Get current time in milliseconds since epoch."""
    return int(time.time() * 1000)


def _response_header(message_type: str) -> taskgrid_pb2.MessageHeader:
    """Create a standardized message header for responses."""
    return taskgrid_pb2.MessageHeader(
        message_type=message_type,
        request_id=str(uuid.uuid4()),
        timestamp=_now_ms(),
        sender="worker",
    )


class Worker:
    """Base class for all task-type workers.
    
    Concrete workers extend this class and implement process_task() to handle
    task-type-specific logic. The Worker manages:
    - Registration with the Namensdienst at startup (with retry)
    - Periodic heartbeat to keep registration alive
    - gRPC ProcessTask endpoint for receiving tasks from Dispatcher
    - Task processing in background threads (non-blocking)
    - Result return to Dispatcher
    - Graceful shutdown with SIGTERM handling
    """

    # ── Configuration (from environment) ──────────────────────────────────────

    def __init__(
        self,
        worker_id: Optional[str] = None,
        worker_type: Optional[str] = None,
        address: Optional[str] = None,
        port: Optional[int] = None,
        nameservice_address: Optional[str] = None,
        nameservice_port: Optional[int] = None,
        dispatcher_address: Optional[str] = None,
        dispatcher_port: Optional[int] = None,
        heartbeat_interval_sec: Optional[int] = None,
        capacity: int = 10,
    ) -> None:
        """Initialize Worker with configuration from environment variables or parameters.

        Environment variables:
        - WORKER_ID: unique identifier for this worker (required)
        - WORKER_TYPE: task type handled by this worker (required)
        - WORKER_ADDRESS: address where this worker's gRPC server listens (default: 0.0.0.0)
        - WORKER_PORT: port where this worker's gRPC server listens (default: 50052)
        - NAMESERVICE_ADDRESS: address of Namensdienst (default: localhost)
        - NAMESERVICE_PORT: port of Namensdienst (default: 50051)
        - DISPATCHER_ADDRESS: address of Dispatcher for returning results (default: localhost)
        - DISPATCHER_PORT: port of Dispatcher for returning results (default: 50051)
        - HEARTBEAT_INTERVAL_SEC: interval between heartbeats (default: 10)
        - WORKER_CAPACITY: max concurrent tasks (default: 10)

        Args:
            worker_id: Override WORKER_ID env var
            worker_type: Override WORKER_TYPE env var
            address: Override WORKER_ADDRESS env var
            port: Override WORKER_PORT env var
            nameservice_address: Override NAMESERVICE_ADDRESS env var
            nameservice_port: Override NAMESERVICE_PORT env var
            dispatcher_address: Override DISPATCHER_ADDRESS env var
            dispatcher_port: Override DISPATCHER_PORT env var
            heartbeat_interval_sec: Override HEARTBEAT_INTERVAL_SEC env var
            capacity: Max concurrent tasks
        """
        # Read from environment or use provided values
        self._worker_id = worker_id or os.environ.get("WORKER_ID")
        self._worker_type = worker_type or os.environ.get("WORKER_TYPE")
        self._address = address or os.environ.get("WORKER_ADDRESS", "0.0.0.0")
        self._port = port or int(os.environ.get("WORKER_PORT", "50052"))
        self._nameservice_address = nameservice_address or os.environ.get("NAMESERVICE_ADDRESS", "localhost")
        self._nameservice_port = nameservice_port or int(os.environ.get("NAMESERVICE_PORT", "50051"))
        self._dispatcher_address = dispatcher_address or os.environ.get("DISPATCHER_ADDRESS", "localhost")
        self._dispatcher_port = dispatcher_port or int(os.environ.get("DISPATCHER_PORT", "50051"))
        self._heartbeat_interval_sec = heartbeat_interval_sec or int(os.environ.get("HEARTBEAT_INTERVAL_SEC", "10"))
        self._capacity = capacity

        # Initialize logger before any logging
        logger_name = self._worker_id or "worker-unnamed"
        self._logger = get_logger(logger_name)

        # Validate required configuration
        if not self._worker_id:
            raise ValueError("WORKER_ID environment variable is required")
        if not self._worker_type:
            raise ValueError("WORKER_TYPE environment variable is required")

        # State management
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._current_load = 0  # Number of tasks currently processing
        self._task_threads: dict[int, threading.Thread] = {}  # task_id -> processing thread

        # gRPC server (not yet started)
        self._server: Optional[grpc.Server] = None

        # Nameservice connection (lazy, established during registration)
        self._nameservice_stub: Optional[taskgrid_pb2_grpc.NameServiceStub] = None
        self._nameservice_channel: Optional[grpc.Channel] = None

        # Dispatcher connection (lazy, established on first result return)
        self._dispatcher_stub: Optional[taskgrid_pb2_grpc.DispatcherServiceStub] = None
        self._dispatcher_channel: Optional[grpc.Channel] = None

    # ── Startup ───────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the worker: register with Namensdienst, start heartbeat, start gRPC server."""
        self._logger.info(
            event="WORKER_STARTING",
            worker_id=self._worker_id,
            type=self._worker_type,
            address=self._address,
            port=self._port,
        )

        # Register with Namensdienst (with retry)
        self._register_with_nameservice()

        # Start heartbeat thread
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True, name="heartbeat"
        )
        self._heartbeat_thread.start()
        self._logger.debug(event="HEARTBEAT_STARTED", interval_sec=self._heartbeat_interval_sec)

        # Start gRPC server
        self._start_grpc_server()
        self._logger.info(event="WORKER_READY", address=self._address, port=self._port)

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

        # Block until stop is called or signal received
        self._stop_event.wait()

    def _start_grpc_server(self) -> None:
        """Start the gRPC server."""
        servicer = _WorkerServicer(self)
        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        taskgrid_pb2_grpc.add_WorkerServiceServicer_to_server(servicer, self._server)
        self._server.add_insecure_port(f"{self._address}:{self._port}")
        self._server.start()
        self._logger.debug(event="GRPC_SERVER_STARTED")

    # ── Nameservice Registration ──────────────────────────────────────────────

    def _get_nameservice_stub(self) -> taskgrid_pb2_grpc.NameServiceStub:
        """Get or create a gRPC stub for the Namensdienst."""
        if self._nameservice_stub is None:
            self._nameservice_channel = grpc.insecure_channel(
                f"{self._nameservice_address}:{self._nameservice_port}"
            )
            self._nameservice_stub = taskgrid_pb2_grpc.NameServiceStub(self._nameservice_channel)
        return self._nameservice_stub

    def _register_with_nameservice(self) -> None:
        """Register worker with Namensdienst with exponential backoff retry."""
        max_retries = 10
        retry_delay_sec = 1

        for attempt in range(max_retries):
            try:
                stub = self._get_nameservice_stub()
                request = taskgrid_pb2.RegisterWorkerRequest(
                    header=_response_header("REGISTER_WORKER"),
                    worker_id=self._worker_id,
                    type=self._worker_type,
                    address=self._address,
                    port=self._port,
                    capacity=self._capacity,
                )
                response = stub.RegisterWorker(request, timeout=5)

                if response.success:
                    self._logger.info(event="REGISTERED", attempt=attempt + 1)
                    return
                else:
                    self._logger.warning(
                        event="REGISTRATION_FAILED",
                        attempt=attempt + 1,
                        message=response.message,
                    )
            except Exception as e:
                self._logger.warning(
                    event="REGISTRATION_ERROR",
                    attempt=attempt + 1,
                    error=str(e),
                )

            # Exponential backoff (1s, 2s, 4s, ..., capped at 30s)
            if attempt < max_retries - 1:
                delay = min(retry_delay_sec * (2 ** attempt), 30)
                self._logger.debug(
                    event="REGISTRATION_RETRY",
                    attempt=attempt + 1,
                    retry_delay_sec=delay,
                )
                time.sleep(delay)

        raise RuntimeError(
            f"Failed to register with Namensdienst after {max_retries} attempts"
        )

    # ── Heartbeat ─────────────────────────────────────────────────────────────

    def _heartbeat_loop(self) -> None:
        """Periodically send heartbeat to Namensdienst."""
        while not self._stop_event.wait(timeout=self._heartbeat_interval_sec):
            self._send_heartbeat()

    def _send_heartbeat(self) -> None:
        """Send a heartbeat to the Namensdienst."""
        try:
            with self._lock:
                current_load = self._current_load

            stub = self._get_nameservice_stub()
            request = taskgrid_pb2.HeartbeatRequest(
                header=_response_header("HEARTBEAT"),
                worker_id=self._worker_id,
                timestamp=_now_ms(),
                current_load=current_load,
            )
            response = stub.Heartbeat(request, timeout=5)

            if not response.success:
                self._logger.warning(
                    event="HEARTBEAT_FAILED",
                    message=response.message,
                )
                # Nameservice doesn't recognise us (e.g., restarted and lost state) — re-register
                self._reregister_once()
        except Exception as e:
            self._logger.warning(
                event="HEARTBEAT_ERROR",
                error=str(e),
            )

    def _reregister_once(self) -> None:
        """Single re-registration attempt used when the nameservice has forgotten this worker."""
        try:
            stub = self._get_nameservice_stub()
            request = taskgrid_pb2.RegisterWorkerRequest(
                header=_response_header("REGISTER_WORKER"),
                worker_id=self._worker_id,
                type=self._worker_type,
                address=self._address,
                port=self._port,
                capacity=self._capacity,
            )
            response = stub.RegisterWorker(request, timeout=5)
            if response.success:
                self._logger.info(event="RE_REGISTERED")
            else:
                self._logger.warning(event="RE_REGISTRATION_FAILED", message=response.message)
        except Exception as e:
            self._logger.warning(event="RE_REGISTRATION_ERROR", error=str(e))

    # ── Task Processing ──────────────────────────────────────────────────────

    def process_task(self, task: taskgrid_pb2.Task, request_id: str) -> tuple[bool, str]:
        """Process a task. Override this method in concrete worker implementations.
        
        Args:
            task: The task to process
            request_id: Correlation ID for logging
            
        Returns:
            (success: bool, result: str)
            - If success=True, result is the task result payload
            - If success=False, result is the error message
        """
        raise NotImplementedError(
            "Concrete worker must implement process_task(task, request_id)"
        )

    def _process_task_background(self, task: taskgrid_pb2.Task, request_id: str) -> None:
        """Process task in background and send result to Dispatcher."""
        try:
            self._logger.info(
                request_id=request_id,
                task_id=task.id,
                status="PROCESSING",
                type=task.type,
            )

            # Call concrete implementation
            success, result = self.process_task(task, request_id)

            # Send result to Dispatcher
            self._send_result(task.id, result, success, request_id)

            if success:
                self._logger.info(
                    request_id=request_id,
                    task_id=task.id,
                    status="COMPLETED",
                )
            else:
                self._logger.error(
                    request_id=request_id,
                    task_id=task.id,
                    status="FAILED",
                    error=result,
                )
        except Exception as e:
            error_msg = f"Task processing exception: {str(e)}"
            self._logger.error(
                request_id=request_id,
                task_id=task.id,
                status="FAILED",
                error=error_msg,
            )
            self._send_result(task.id, error_msg, False, request_id)
        finally:
            # Update load
            with self._lock:
                self._current_load -= 1
                # Clean up thread reference
                self._task_threads.pop(task.id, None)

    def _send_result(
        self,
        task_id: int,
        result: str,
        success: bool,
        request_id: str,
    ) -> None:
        """Send result back to Dispatcher."""
        try:
            with self._lock:
                if self._dispatcher_stub is None:
                    self._dispatcher_channel = grpc.insecure_channel(
                        f"{self._dispatcher_address}:{self._dispatcher_port}"
                    )
                    self._dispatcher_stub = taskgrid_pb2_grpc.DispatcherServiceStub(
                        self._dispatcher_channel
                    )
                stub = self._dispatcher_stub

            request = taskgrid_pb2.ReturnResultRequest(
                header=_response_header("RETURN_RESULT"),
                task_id=task_id,
                result=result,
                worker_id=self._worker_id,
                success=success,
                error_message="" if success else result,
            )
            response = stub.ReturnResult(request, timeout=10)

            if not response.success:
                self._logger.warning(
                    request_id=request_id,
                    task_id=task_id,
                    event="RESULT_RETURN_FAILED",
                    message=response.message,
                )
        except Exception as e:
            self._logger.error(
                request_id=request_id,
                task_id=task_id,
                event="RESULT_RETURN_ERROR",
                error=str(e),
            )

    # ── Shutdown ──────────────────────────────────────────────────────────────

    def _handle_shutdown(self, sig, frame):
        """Handle SIGTERM/SIGINT for graceful shutdown."""
        self._logger.info(event="SHUTDOWN_REQUESTED", signal=sig)

        # Deregister from Namensdienst
        self._deregister_from_nameservice()

        # Stop accepting new tasks
        self._stop_event.set()

        # Wait for current tasks to complete (with timeout)
        self._wait_for_tasks_completion(timeout_sec=30)

        # Shutdown gRPC server
        if self._server:
            self._logger.debug(event="SHUTTING_DOWN_GRPC_SERVER")
            self._server.stop(grace=5).wait()

        # Close channels
        if self._nameservice_channel:
            self._nameservice_channel.close()
        if self._dispatcher_channel:
            self._dispatcher_channel.close()

        self._logger.info(event="WORKER_STOPPED")
        sys.exit(0)

    def _deregister_from_nameservice(self) -> None:
        """Deregister worker from Namensdienst."""
        try:
            stub = self._get_nameservice_stub()
            request = taskgrid_pb2.DeregisterWorkerRequest(
                header=_response_header("DEREGISTER_WORKER"),
                worker_id=self._worker_id,
            )
            response = stub.DeregisterWorker(request, timeout=5)

            if response.success:
                self._logger.info(event="DEREGISTERED")
            else:
                self._logger.warning(
                    event="DEREGISTRATION_FAILED",
                    message=response.message,
                )
        except Exception as e:
            self._logger.error(
                event="DEREGISTRATION_ERROR",
                error=str(e),
            )

    def _wait_for_tasks_completion(self, timeout_sec: int = 30) -> None:
        """Wait for all current task processing threads to complete."""
        start_time = time.time()
        while time.time() - start_time < timeout_sec:
            with self._lock:
                if self._current_load == 0:
                    self._logger.info(event="ALL_TASKS_COMPLETED")
                    return

            time.sleep(0.5)

        with self._lock:
            if self._current_load > 0:
                self._logger.warning(
                    event="TIMEOUT_WAITING_FOR_TASKS",
                    remaining_tasks=self._current_load,
                )

    # ── Health and status ─────────────────────────────────────────────────────

    def get_load(self) -> int:
        """Return current number of tasks being processed."""
        with self._lock:
            return self._current_load

    def is_ready(self) -> bool:
        """Return True if worker is accepting tasks."""
        with self._lock:
            return (
                self._current_load < self._capacity
                and not self._stop_event.is_set()
            )


class _WorkerServicer(taskgrid_pb2_grpc.WorkerServiceServicer):
    """gRPC servicer for the WorkerService."""

    def __init__(self, worker: Worker) -> None:
        self._worker = worker

    def ProcessTask(
        self,
        request: taskgrid_pb2.ProcessTaskRequest,
        context: grpc.ServicerContext,
    ) -> taskgrid_pb2.ProcessTaskResponse:
        """Handle ProcessTask RPC from Dispatcher."""
        request_id = request.header.request_id
        task = request.task

        thread = threading.Thread(
            target=self._worker._process_task_background,
            args=(task, request_id),
            daemon=True,
            name=f"task-{task.id}",
        )

        # Check capacity and register atomically to prevent TOCTOU overshoot
        with self._worker._lock:
            if (self._worker._current_load >= self._worker._capacity
                    or self._worker._stop_event.is_set()):
                self._worker._logger.warning(
                    request_id=request_id,
                    task_id=task.id,
                    event="REJECTED_NOT_READY",
                    current_load=self._worker._current_load,
                    capacity=self._worker._capacity,
                )
                return taskgrid_pb2.ProcessTaskResponse(
                    header=_response_header("PROCESS_TASK_RESPONSE"),
                    accepted=False,
                    message="Worker at capacity or shutting down",
                )
            self._worker._current_load += 1
            self._worker._task_threads[task.id] = thread

        self._worker._logger.info(
            request_id=request_id,
            task_id=task.id,
            status="RECEIVED",
            type=task.type,
        )

        try:
            thread.start()
        except RuntimeError as e:
            with self._worker._lock:
                self._worker._current_load -= 1
                self._worker._task_threads.pop(task.id, None)
            return taskgrid_pb2.ProcessTaskResponse(
                header=_response_header("PROCESS_TASK_RESPONSE"),
                accepted=False,
                message=f"Failed to start task thread: {e}",
            )

        return taskgrid_pb2.ProcessTaskResponse(
            header=_response_header("PROCESS_TASK_RESPONSE"),
            accepted=True,
            message="Task accepted",
        )
