import os
import sys
import threading
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "proto"))

import grpc

import taskgrid_pb2
import taskgrid_pb2_grpc
from common.logger import get_logger

logger = get_logger("nameservice")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _response_header(message_type: str) -> taskgrid_pb2.MessageHeader:
    return taskgrid_pb2.MessageHeader(
        message_type=message_type,
        request_id=str(uuid.uuid4()),
        timestamp=_now_ms(),
        sender="nameservice",
    )


_HEARTBEAT_TIMEOUT_SEC_DEFAULT = 30
_OFFLINE_TIMEOUT_SEC_DEFAULT = 90


class NameServiceServicer(taskgrid_pb2_grpc.NameServiceServicer):
    """gRPC servicer for the NameService (Namensdienst).

    Registry data model: worker_id → Worker (supports multiple workers per type).
    All public methods are thread-safe via a single RLock.
    Background thread demotes workers to UNHEALTHY/OFFLINE when heartbeats stop.
    """

    def __init__(
        self,
        heartbeat_timeout_sec: int = _HEARTBEAT_TIMEOUT_SEC_DEFAULT,
        offline_timeout_sec: int = _OFFLINE_TIMEOUT_SEC_DEFAULT,
    ) -> None:
        self._lock = threading.RLock()
        self._registry: dict[str, taskgrid_pb2.Worker] = {}
        self._heartbeat_timeout_ms = heartbeat_timeout_sec * 1000
        self._offline_timeout_ms = offline_timeout_sec * 1000
        self._stop_event = threading.Event()
        self._health_thread = threading.Thread(
            target=self._health_check_loop, daemon=True, name="health-checker"
        )
        self._health_thread.start()
        logger.info(
            event="HEALTH_CHECKER_STARTED",
            heartbeat_timeout_sec=heartbeat_timeout_sec,
            offline_timeout_sec=offline_timeout_sec,
        )

    def stop(self) -> None:
        self._stop_event.set()
        self._health_thread.join(timeout=5)

    # ── Background health checker ─────────────────────────────────────────────

    def _health_check_loop(self) -> None:
        while not self._stop_event.wait(timeout=1.0):
            self._check_worker_health()

    def _check_worker_health(self) -> None:
        now = _now_ms()
        with self._lock:
            for worker_id, worker in list(self._registry.items()):
                if worker.status == taskgrid_pb2.DRAINING:
                    continue
                elapsed = now - worker.last_heartbeat
                if elapsed > self._offline_timeout_ms:
                    new_status = taskgrid_pb2.OFFLINE
                elif elapsed > self._heartbeat_timeout_ms:
                    new_status = taskgrid_pb2.UNHEALTHY
                else:
                    continue
                if new_status == worker.status:
                    continue
                self._registry[worker_id] = taskgrid_pb2.Worker(
                    worker_id=worker.worker_id,
                    type=worker.type,
                    address=worker.address,
                    port=worker.port,
                    status=new_status,
                    last_heartbeat=worker.last_heartbeat,
                    current_load=worker.current_load,
                )
                event = "WORKER_OFFLINE" if new_status == taskgrid_pb2.OFFLINE else "WORKER_UNHEALTHY"
                logger.warning(event=event, worker_id=worker_id, elapsed_ms=elapsed)

    # ── gRPC endpoints ────────────────────────────────────────────────────────

    def RegisterWorker(self, request, context):
        request_id = request.header.request_id
        is_update: bool
        with self._lock:
            is_update = request.worker_id in self._registry
            self._registry[request.worker_id] = taskgrid_pb2.Worker(
                worker_id=request.worker_id,
                type=request.type,
                address=request.address,
                port=request.port,
                status=taskgrid_pb2.ACTIVE,
                last_heartbeat=_now_ms(),
                current_load=0,
            )
        event = "RE_REGISTERED" if is_update else "REGISTERED"
        logger.info(
            request_id=request_id,
            event=event,
            worker_id=request.worker_id,
            type=request.type,
            address=request.address,
            port=request.port,
        )
        return taskgrid_pb2.RegisterWorkerResponse(
            header=_response_header("REGISTER_WORKER_RESPONSE"),
            success=True,
            message="",
        )

    def Heartbeat(self, request, context):
        worker_id = request.worker_id
        with self._lock:
            worker = self._registry.get(worker_id)
            if worker is None:
                logger.warning(event="HEARTBEAT_UNKNOWN", worker_id=worker_id)
                return taskgrid_pb2.HeartbeatResponse(
                    header=_response_header("HEARTBEAT_RESPONSE"),
                    success=False,
                    message=f"unknown worker: {worker_id}",
                )
            recovered = worker.status == taskgrid_pb2.UNHEALTHY
            new_status = taskgrid_pb2.ACTIVE if recovered else worker.status
            self._registry[worker_id] = taskgrid_pb2.Worker(
                worker_id=worker.worker_id,
                type=worker.type,
                address=worker.address,
                port=worker.port,
                status=new_status,
                last_heartbeat=_now_ms(),
                current_load=request.current_load,
            )
        if recovered:
            logger.info(event="WORKER_RECOVERED", worker_id=worker_id)
        logger.debug(event="HEARTBEAT", worker_id=worker_id, current_load=request.current_load)
        return taskgrid_pb2.HeartbeatResponse(
            header=_response_header("HEARTBEAT_RESPONSE"),
            success=True,
            message="",
        )

    def LookupWorker(self, request, context):
        request_id = request.header.request_id
        worker_type = request.type
        with self._lock:
            matches = [
                w
                for w in self._registry.values()
                if w.type == worker_type and w.status == taskgrid_pb2.ACTIVE
            ]
        logger.debug(
            request_id=request_id, event="LOOKUP", type=worker_type, matches=len(matches)
        )
        return taskgrid_pb2.LookupWorkerResponse(
            header=_response_header("LOOKUP_WORKER_RESPONSE"),
            success=True,
            workers=matches,
            message="",
        )

    def DeregisterWorker(self, request, context):
        request_id = request.header.request_id
        worker_id = request.worker_id
        with self._lock:
            removed = self._registry.pop(worker_id, None)
        if removed is None:
            logger.warning(
                request_id=request_id, event="DEREGISTER_UNKNOWN", worker_id=worker_id
            )
            return taskgrid_pb2.DeregisterWorkerResponse(
                header=_response_header("DEREGISTER_WORKER_RESPONSE"),
                success=False,
                message=f"unknown worker: {worker_id}",
            )
        logger.info(request_id=request_id, event="DEREGISTERED", worker_id=worker_id)
        return taskgrid_pb2.DeregisterWorkerResponse(
            header=_response_header("DEREGISTER_WORKER_RESPONSE"),
            success=True,
            message="",
        )

    def GetNameServiceStatus(self, request, context):
        with self._lock:
            workers = list(self._registry.values())
        active = [w for w in workers if w.status == taskgrid_pb2.ACTIVE]
        types = sorted({w.type for w in active})
        return taskgrid_pb2.GetStatusResponse(
            header=_response_header("GET_STATUS_RESPONSE"),
            workers_registered=len(workers),
            workers_active=len(active),
            supported_task_types=types,
        )
