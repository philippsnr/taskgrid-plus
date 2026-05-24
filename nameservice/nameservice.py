import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common.logger import get_logger

logger = get_logger("nameservice")


class NameService:
    # ── Worker registration ───────────────────────────────────────────────────

    def on_worker_registered(self, request_id: str, worker_id: str, worker_type: str, address: str, port: int) -> None:
        logger.info(request_id=request_id, event="REGISTERED", worker_id=worker_id, type=worker_type, address=address, port=port)

    def on_worker_deregistered(self, request_id: str, worker_id: str) -> None:
        logger.info(request_id=request_id, event="DEREGISTERED", worker_id=worker_id)

    # ── Heartbeat ─────────────────────────────────────────────────────────────

    def on_heartbeat_received(self, worker_id: str, current_load: int) -> None:
        logger.debug(event="HEARTBEAT", worker_id=worker_id, current_load=current_load)

    # ── State changes ─────────────────────────────────────────────────────────

    def on_worker_state_changed(self, worker_id: str, old_state: str, new_state: str) -> None:
        logger.warning(event="STATE_CHANGE", worker_id=worker_id, old_state=old_state, new_state=new_state)

    # ── Lookup ────────────────────────────────────────────────────────────────

    def on_lookup(self, request_id: str, worker_type: str, matches: int) -> None:
        logger.debug(request_id=request_id, event="LOOKUP", type=worker_type, matches=matches)
