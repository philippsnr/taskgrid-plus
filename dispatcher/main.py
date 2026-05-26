#!/usr/bin/env python3
"""
Dispatcher service entry point.

The Dispatcher receives tasks from Clients (via PostTask), maintains a task queue,
and forwards tasks to Workers via the background dispatcher loop.

Environment variables:
- DISPATCHER_PORT: gRPC server port (default: 50051)
- LOG_LEVEL: logging level (DEBUG, INFO, WARNING, ERROR; default: INFO)
- LOG_DIR: directory for log files (optional)
"""

import sys
import os
import signal
import threading

# Adjust path to import from repo root
repo_root = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, repo_root)
sys.path.insert(0, os.path.join(repo_root, "proto"))

import grpc
from concurrent import futures
import taskgrid_pb2
import taskgrid_pb2_grpc

# Now import from the modules
from dispatcher.dispatcher import Dispatcher
from common.logger import get_logger

logger = get_logger("dispatcher")


class DispatcherServicer(taskgrid_pb2_grpc.DispatcherServiceServicer):
    """gRPC servicer for the Dispatcher."""

    def __init__(self, dispatcher: Dispatcher) -> None:
        self.dispatcher = dispatcher

    def PostTask(self, request: taskgrid_pb2.PostTaskRequest, context) -> taskgrid_pb2.PostTaskResponse:
        """Handle PostTask RPC."""
        return self.dispatcher.post_task(request)

    def GetResult(self, request: taskgrid_pb2.GetResultRequest, context) -> taskgrid_pb2.GetResultResponse:
        """Handle GetResult RPC (not yet implemented)."""
        return taskgrid_pb2.GetResultResponse(
            header=taskgrid_pb2.MessageHeader(
                message_type="GetResultResponse",
                request_id=request.header.request_id,
                timestamp=int(self.dispatcher._get_current_timestamp_ms()),
                sender="dispatcher",
            ),
            success=False,
            task_id=request.task_id,
            status=taskgrid_pb2.TASK_STATUS_UNSPECIFIED,
            message="GetResult not yet implemented",
        )

    def ReturnResult(self, request: taskgrid_pb2.ReturnResultRequest, context) -> taskgrid_pb2.ReturnResultResponse:
        """Handle ReturnResult RPC (not yet implemented)."""
        return taskgrid_pb2.ReturnResultResponse(
            header=taskgrid_pb2.MessageHeader(
                message_type="ReturnResultResponse",
                request_id=request.header.request_id,
                timestamp=int(self.dispatcher._get_current_timestamp_ms()),
                sender="dispatcher",
            ),
            success=False,
            message="ReturnResult not yet implemented",
        )

    def GetDispatcherStatus(self, request: taskgrid_pb2.GetStatusRequest, context) -> taskgrid_pb2.GetStatusResponse:
        """Handle GetDispatcherStatus RPC."""
        task_store = self.dispatcher._task_store.all()
        tasks_queued_count = self.dispatcher._task_queue.size()

        return taskgrid_pb2.GetStatusResponse(
            header=taskgrid_pb2.MessageHeader(
                message_type="GetStatusResponse",
                request_id=request.header.request_id,
                timestamp=int(self.dispatcher._get_current_timestamp_ms()),
                sender="dispatcher",
            ),
            workers_registered=0,  # Not yet tracked
            workers_active=0,  # Not yet tracked
            supported_task_types=[],  # Will be populated later
            tasks_queued=tasks_queued_count,
            tasks_running=0,  # Not yet tracked
            tasks_completed=sum(1 for t in task_store.values() if t.status == taskgrid_pb2.COMPLETED),
            tasks_failed=sum(1 for t in task_store.values() if t.status == taskgrid_pb2.FAILED),
            avg_processing_time_ms=0.0,  # Not yet calculated
            total_timeouts=sum(1 for t in task_store.values() if t.status == taskgrid_pb2.TIMEOUT),
            total_retries=sum(1 for t in task_store.values() if t.retry_count > 0),
        )


def serve() -> None:
    """Start the Dispatcher gRPC server."""
    port = int(os.environ.get("DISPATCHER_PORT", 50051))

    # Create dispatcher instance
    dispatcher = Dispatcher()

    # Create gRPC server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    taskgrid_pb2_grpc.add_DispatcherServiceServicer_to_server(
        DispatcherServicer(dispatcher), server
    )
    server.add_insecure_port(f"[::]:{port}")

    logger.info(event="DISPATCHER_STARTING", port=port)

    # Start server in a thread so we can handle signals
    server_thread = threading.Thread(target=server.start, daemon=True)
    server_thread.start()

    logger.info(event="DISPATCHER_READY", port=port)

    # Handle graceful shutdown on SIGTERM
    def signal_handler(signum, frame):
        logger.info(event="DISPATCHER_SHUTTING_DOWN", signal=signum)
        # Give ongoing RPCs a grace period to finish
        server.stop(grace=5)
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Keep the server running
    try:
        while True:
            threading.Event().wait(timeout=86400)  # Sleep in chunks to handle signals
    except KeyboardInterrupt:
        logger.info(event="DISPATCHER_INTERRUPTED")
        server.stop(grace=5)


if __name__ == "__main__":
    serve()
