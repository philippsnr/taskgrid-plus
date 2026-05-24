import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common.logger import get_logger

logger = get_logger("monitoring")


class Monitoring:
    # ── Status queries ────────────────────────────────────────────────────────

    def on_dispatcher_status_queried(self, request_id: str) -> None:
        logger.info(request_id=request_id, event="STATUS_QUERY", target="dispatcher")

    def on_nameservice_status_queried(self, request_id: str) -> None:
        logger.info(request_id=request_id, event="STATUS_QUERY", target="nameservice")

    def on_status_response_received(self, request_id: str, target: str, workers_active: int, tasks_queued: int) -> None:
        logger.info(
            request_id=request_id,
            event="STATUS_RESPONSE",
            target=target,
            workers_active=workers_active,
            tasks_queued=tasks_queued,
        )
