#!/usr/bin/env python3
"""
Simple test client for the Dispatcher.
Tests the PostTask RPC endpoint.
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "proto"))

import grpc
import taskgrid_pb2
import taskgrid_pb2_grpc


def test_post_task():
    """Test PostTask RPC."""
    print("Connecting to dispatcher on localhost:50051...")
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = taskgrid_pb2_grpc.DispatcherServiceStub(channel)

        # Test 1: Send a valid task
        print("\nTest 1: Sending valid task...")
        request = taskgrid_pb2.PostTaskRequest(
            header=taskgrid_pb2.MessageHeader(
                message_type="PostTaskRequest",
                request_id="test-req-001",
                timestamp=int(time.time() * 1000),
                sender="test-client",
            ),
            type="sum",
            payload="[1, 2, 3, 4, 5]",
        )
        response = stub.PostTask(request)
        print(f"Response: success={response.success}, task_id={response.task_id}, message={response.message}")
        assert response.success, "PostTask should succeed"
        task_id_1 = response.task_id

        # Test 2: Send another task
        print("\nTest 2: Sending another task...")
        request = taskgrid_pb2.PostTaskRequest(
            header=taskgrid_pb2.MessageHeader(
                message_type="PostTaskRequest",
                request_id="test-req-002",
                timestamp=int(time.time() * 1000),
                sender="test-client",
            ),
            type="multiply",
            payload="[2, 3]",
        )
        response = stub.PostTask(request)
        print(f"Response: success={response.success}, task_id={response.task_id}, message={response.message}")
        assert response.success, "PostTask should succeed"
        task_id_2 = response.task_id

        # Verify task IDs are monotonic
        print(f"\nTask IDs are monotonic: {task_id_1} < {task_id_2} = {task_id_1 < task_id_2}")
        assert task_id_1 < task_id_2, "Task IDs should be monotonically increasing"

        # Test 3: Send invalid task (empty type)
        print("\nTest 3: Sending invalid task (empty type)...")
        request = taskgrid_pb2.PostTaskRequest(
            header=taskgrid_pb2.MessageHeader(
                message_type="PostTaskRequest",
                request_id="test-req-003",
                timestamp=int(time.time() * 1000),
                sender="test-client",
            ),
            type="",
            payload="[1, 2]",
        )
        response = stub.PostTask(request)
        print(f"Response: success={response.success}, message={response.message}")
        assert not response.success, "PostTask with empty type should fail"

        print("\n✓ All tests passed!")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] != "--run":
        print("Usage: python3 test_dispatcher_client.py --run")
        print("\nNote: Run the dispatcher server first with:")
        print("  cd /home/bim/Documents/GitHub/taskgrid-plus")
        print("  python3 -m dispatcher.main")
        sys.exit(0)

    try:
        test_post_task()
    except grpc.RpcError as e:
        print(f"✗ gRPC error: {e.code()}: {e.details()}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)
