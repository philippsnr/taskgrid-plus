import os
import sys
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "proto"))

import grpc
import taskgrid_pb2
import taskgrid_pb2_grpc
from common.logger import get_logger

logger = get_logger("client")


class Client:
    def __init__(self) -> None:
        host = os.environ.get("DISPATCHER_HOST", "localhost")
        port = os.environ.get("DISPATCHER_PORT", "50051")
        self._address = f"{host}:{port}"

    def _make_header(self, message_type: str, request_id: str) -> taskgrid_pb2.MessageHeader:
        return taskgrid_pb2.MessageHeader(
            message_type=message_type,
            request_id=request_id,
            timestamp=int(time.time() * 1000),
            sender="client",
        )

    def send_task(self, task_type: str, payload: str) -> None:
        request_id = str(uuid.uuid4())
        logger.info(request_id=request_id, event="TASK_SENT", type=task_type)
        try:
            with grpc.insecure_channel(self._address) as channel:
                stub = taskgrid_pb2_grpc.DispatcherServiceStub(channel)
                response = stub.PostTask(taskgrid_pb2.PostTaskRequest(
                    header=self._make_header("POST_TASK", request_id),
                    type=task_type,
                    payload=payload,
                ))
        except grpc.RpcError as e:
            print(f"Connection error ({e.code().name}): could not reach dispatcher at {self._address}")
            logger.error(request_id=request_id, event="CONNECTION_ERROR", code=e.code().name, error=e.details())
            return

        if response.success:
            print(f"Task accepted, ID = {response.task_id}")
            logger.info(request_id=request_id, task_id=response.task_id, event="TASK_ACCEPTED")
        else:
            print(f"Error: {response.message}")
            logger.error(request_id=request_id, event="TASK_REJECTED", error=response.message)

    def request_result(self, task_id: int) -> None:
        request_id = str(uuid.uuid4())
        logger.debug(request_id=request_id, task_id=task_id, event="RESULT_REQUESTED")
        try:
            with grpc.insecure_channel(self._address) as channel:
                stub = taskgrid_pb2_grpc.DispatcherServiceStub(channel)
                response = stub.GetResult(taskgrid_pb2.GetResultRequest(
                    header=self._make_header("GET_RESULT", request_id),
                    task_id=task_id,
                ))
        except grpc.RpcError as e:
            print(f"Connection error ({e.code().name}): could not reach dispatcher at {self._address}")
            logger.error(request_id=request_id, task_id=task_id, event="CONNECTION_ERROR", code=e.code().name, error=e.details())
            return

        status_name = taskgrid_pb2.TaskStatus.Name(response.status)
        logger.info(request_id=request_id, task_id=task_id, event="RESULT_RECEIVED", status=status_name)

        if not response.success:
            print(f"Error: {response.message}")
        elif response.status == taskgrid_pb2.COMPLETED:
            print(f"Task {task_id}: {status_name}")
            print(f"Result: {response.result}")
        elif response.status == taskgrid_pb2.FAILED:
            print(f"Task {task_id}: {status_name}")
            print(f"Error: {response.message}")
        else:
            print(f"Task {task_id}: {status_name} (result not yet available)")
