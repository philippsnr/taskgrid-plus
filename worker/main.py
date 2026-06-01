"""
Worker main entry point.

Implements a generic TaskWorker that dispatches to handlers based on task type.

Environment variables:
- WORKER_ID: unique identifier (required)
- WORKER_TYPE: task type handled by this worker (required, one of: reverse, sum, hash, upper, wait)
- WORKER_ADDRESS: listen address (default: 0.0.0.0)
- WORKER_PORT: listen port (default: 50052)
- NAMESERVICE_ADDRESS: Namensdienst address (default: localhost)
- NAMESERVICE_PORT: Namensdienst port (default: 50051)
- DISPATCHER_ADDRESS: Dispatcher address for returning results (default: localhost)
- DISPATCHER_PORT: Dispatcher port for returning results (default: 50051)
- HEARTBEAT_INTERVAL_SEC: heartbeat interval in seconds (default: 10)
- WORKER_CAPACITY: max concurrent tasks (default: 10)

Task types supported:
- reverse: reverse the input string
- sum: sum a comma-separated list of numbers
- hash: compute SHA-256 hash
- upper: convert string to uppercase
- wait: sleep for N seconds and return confirmation
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "proto"))

import taskgrid_pb2
from worker.worker import Worker
from worker.handlers import handle_task, SUPPORTED_TYPES, get_handler
from common.logger import get_logger

logger = get_logger("worker-main")


class TaskWorker(Worker):
    """Generic task worker that dispatches to registered handlers.
    
    Handlers are registered in worker/handlers.py in the HANDLERS dict.
    The WORKER_TYPE env var determines which handler this worker uses.
    """

    def process_task(self, task: taskgrid_pb2.Task, request_id: str) -> tuple[bool, str]:
        """Process a task by dispatching to the appropriate handler."""
        if task.type != self._worker_type:
            return False, f"Task type mismatch: expected {self._worker_type}, got {task.type}"
        try:
            return handle_task(task.type, task.payload)
        except Exception as e:
            return False, f"Task processing failed: {str(e)}"


def serve() -> None:
    """Start the task worker."""
    try:
        # Validate that WORKER_TYPE is supported
        worker_type = os.environ.get("WORKER_TYPE")
        if worker_type not in SUPPORTED_TYPES:
            raise ValueError(
                f"WORKER_TYPE '{worker_type}' not supported. "
                f"Supported types: {', '.join(SUPPORTED_TYPES)}"
            )
        
        # Log supported handler
        handler = get_handler(worker_type)
        logger.info(event="HANDLER_LOADED", type=worker_type, handler=handler.__name__)
        
        # Create and start worker
        worker = TaskWorker()
        logger.info(
            event="WORKER_STARTING",
            worker_type=worker._worker_type,
        )
        worker.start()
    except KeyboardInterrupt:
        logger.info(event="INTERRUPTED")
        sys.exit(0)
    except Exception as e:
        logger.error(event="STARTUP_FAILED", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    serve()
