import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common.logger import get_logger

logger = get_logger("client")


class Client:
    # ── Outbound requests ─────────────────────────────────────────────────────

    def on_task_sent(self, request_id: str, task_type: str) -> None:
        logger.info(request_id=request_id, event="TASK_SENT", type=task_type)

    def on_task_accepted(self, request_id: str, task_id: int) -> None:
        logger.info(request_id=request_id, task_id=task_id, event="TASK_ACCEPTED")

    # ── Result polling ────────────────────────────────────────────────────────

    def on_result_requested(self, request_id: str, task_id: int) -> None:
        logger.debug(request_id=request_id, task_id=task_id, event="RESULT_REQUESTED")

    def on_result_received(self, request_id: str, task_id: int, status: str) -> None:
        logger.info(request_id=request_id, task_id=task_id, event="RESULT_RECEIVED", status=status)

    # ── Errors ────────────────────────────────────────────────────────────────

    def on_error(self, request_id: str, task_id: int, error: str) -> None:
        logger.error(request_id=request_id, task_id=task_id, event="ERROR", error=error)
