"""
Worker main entry point.

This is a minimal example that starts a base Worker.
Concrete task-type workers extend this with their own main.py
that subclasses Worker and implements process_task().

Environment variables:
- WORKER_ID: unique identifier (required)
- WORKER_TYPE: task type handled by this worker (required)
- WORKER_ADDRESS: listen address (default: 0.0.0.0)
- WORKER_PORT: listen port (default: 50052)
- NAMESERVICE_ADDRESS: Namensdienst address (default: localhost)
- NAMESERVICE_PORT: Namensdienst port (default: 50051)
- HEARTBEAT_INTERVAL_SEC: heartbeat interval in seconds (default: 10)
- WORKER_CAPACITY: max concurrent tasks (default: 10)
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from worker.worker import Worker
from common.logger import get_logger

logger = get_logger("worker-main")


class ExampleWorker(Worker):
    """Example concrete worker implementation for demonstration."""

    def process_task(self, task, request_id: str) -> tuple[bool, str]:
        """Simple example: echo the task payload.
        
        Concrete workers override this to implement task-type-specific logic.
        """
        try:
            # For demonstration, just echo the payload
            result = f"Echo: {task.payload}"
            return True, result
        except Exception as e:
            return False, f"Error processing task: {str(e)}"


def serve() -> None:
    """Start the worker."""
    try:
        # Create and start worker
        worker = ExampleWorker()
        worker.start()
    except KeyboardInterrupt:
        logger.info(event="INTERRUPTED")
        sys.exit(0)
    except Exception as e:
        logger.error(event="STARTUP_FAILED", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    serve()
