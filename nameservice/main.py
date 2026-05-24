import os
import signal
import sys
from concurrent import futures

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "proto"))

import grpc

import taskgrid_pb2_grpc
from nameservice.nameservice import NameServiceServicer
from common.logger import get_logger

PORT = int(os.environ.get("NAMESERVICE_PORT", "50051"))
HEARTBEAT_TIMEOUT_SEC = int(os.environ.get("HEARTBEAT_TIMEOUT_SEC", "30"))
OFFLINE_TIMEOUT_SEC = int(os.environ.get("OFFLINE_TIMEOUT_SEC", "90"))

logger = get_logger("nameservice")


def serve() -> None:
    servicer = NameServiceServicer(
        heartbeat_timeout_sec=HEARTBEAT_TIMEOUT_SEC,
        offline_timeout_sec=OFFLINE_TIMEOUT_SEC,
    )
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    taskgrid_pb2_grpc.add_NameServiceServicer_to_server(servicer, server)
    server.add_insecure_port(f"[::]:{PORT}")
    server.start()
    logger.info(event="STARTED", port=PORT)

    def _handle_shutdown(sig, frame):
        logger.info(event="STOPPING", signal=sig)
        servicer.stop()
        server.stop(grace=5).wait()

    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
