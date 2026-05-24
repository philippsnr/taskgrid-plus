import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common.logger import get_logger

logger = get_logger("dispatcher")


class Dispatcher:
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
