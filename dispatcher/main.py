#!/usr/bin/env python3
"""
Dispatcher service entry point.

Environment variables:
- DISPATCHER_PORT:  gRPC server port (default: 50051)
- NAMESERVICE_ADDR: address of the Namensdienst (default: nameservice:50052)
- LOG_LEVEL:        logging level (DEBUG, INFO, WARNING, ERROR; default: INFO)
- LOG_DIR:          directory for log files (optional)
"""

import sys
import os
import signal
import threading

repo_root = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, repo_root)
sys.path.insert(0, os.path.join(repo_root, "proto"))

import grpc
from concurrent import futures
import taskgrid_pb2
import taskgrid_pb2_grpc

from dispatcher.dispatcher import Dispatcher
from common.logger import get_logger

logger = get_logger("dispatcher")


class DispatcherServicer(taskgrid_pb2_grpc.DispatcherServiceServicer):

    def __init__(self, dispatcher: Dispatcher) -> None:
        self.dispatcher = dispatcher

    def PostTask(self, request: taskgrid_pb2.PostTaskRequest, context) -> taskgrid_pb2.PostTaskResponse:
        return self.dispatcher.post_task(request)

    def GetResult(self, request: taskgrid_pb2.GetResultRequest, context) -> taskgrid_pb2.GetResultResponse:
        return self.dispatcher.get_result(request)

    def ReturnResult(self, request: taskgrid_pb2.ReturnResultRequest, context) -> taskgrid_pb2.ReturnResultResponse:
        return self.dispatcher.return_result(request)

    def GetDispatcherStatus(self, request: taskgrid_pb2.GetStatusRequest, context) -> taskgrid_pb2.GetStatusResponse:
        task_store = self.dispatcher._task_store.all()
        tasks_running = sum(
            1 for t in task_store.values()
            if t.status in (taskgrid_pb2.DISPATCHED, taskgrid_pb2.PROCESSING)
        )
        return taskgrid_pb2.GetStatusResponse(
            header=self.dispatcher._make_header("GetStatusResponse", request.header.request_id),
            workers_registered=0,
            workers_active=0,
            supported_task_types=[],
            tasks_queued=self.dispatcher._task_queue.size(),
            tasks_running=tasks_running,
            tasks_completed=sum(1 for t in task_store.values() if t.status == taskgrid_pb2.COMPLETED),
            tasks_failed=sum(1 for t in task_store.values() if t.status == taskgrid_pb2.FAILED),
            avg_processing_time_ms=0.0,
            total_timeouts=sum(1 for t in task_store.values() if t.status == taskgrid_pb2.TIMEOUT),
            total_retries=sum(1 for t in task_store.values() if t.retry_count > 0),
        )


def serve() -> None:
    port = int(os.environ.get("DISPATCHER_PORT", 50051))
    nameservice_addr = os.environ.get("NAMESERVICE_ADDR", "nameservice:50052")
    task_timeout_sec = int(os.environ.get("TASK_TIMEOUT_SEC", 60))
    max_retries = int(os.environ.get("MAX_RETRIES", 3))

    dispatcher = Dispatcher()

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    taskgrid_pb2_grpc.add_DispatcherServiceServicer_to_server(
        DispatcherServicer(dispatcher), server
    )
    server.add_insecure_port(f"[::]:{port}")

    logger.info(event="DISPATCHER_STARTING", port=port, nameservice_addr=nameservice_addr)
    server.start()

    dispatcher.start_dispatch_loop(nameservice_addr, task_timeout_sec=task_timeout_sec, max_retries=max_retries)

    logger.info(event="DISPATCHER_READY", port=port)

    def signal_handler(signum, frame):
        logger.info(event="DISPATCHER_SHUTTING_DOWN", signal=signum)
        server.stop(grace=5)
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        while True:
            threading.Event().wait(timeout=86400)
    except KeyboardInterrupt:
        logger.info(event="DISPATCHER_INTERRUPTED")
        server.stop(grace=5)


if __name__ == "__main__":
    serve()
