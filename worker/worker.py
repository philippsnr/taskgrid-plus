import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common.logger import get_logger

# Worker ID is set per container: WORKER_ID=worker-sum-1
WORKER_ID = os.environ.get("WORKER_ID", "worker-unknown")
logger = get_logger(WORKER_ID)


class Worker:
    def __init__(self, worker_id: str = WORKER_ID):
        self._worker_id = worker_id

    # ── Task lifecycle ────────────────────────────────────────────────────────

    def on_task_received(self, request_id: str, task_id: int) -> None:
        logger.info(request_id=request_id, task_id=task_id, status="RECEIVED")

    def on_processing_started(self, request_id: str, task_id: int) -> None:
        logger.info(request_id=request_id, task_id=task_id, status="PROCESSING")

    def on_result_sent(self, request_id: str, task_id: int) -> None:
        logger.info(request_id=request_id, task_id=task_id, status="RESULT_SENT")

    def on_error(self, request_id: str, task_id: int, error: str) -> None:
        logger.error(request_id=request_id, task_id=task_id, status="ERROR", error=error)
