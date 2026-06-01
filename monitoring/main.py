#!/usr/bin/env python3
"""
Monitoring CLI for TaskGrid+.

Queries the Dispatcher (and optionally the Namensdienst directly) via gRPC
and prints a formatted status table to stdout.

Environment variables:
  DISPATCHER_ADDR    host:port of the Dispatcher  (default: localhost:50051)
  NAMESERVICE_ADDR   host:port of the Namensdienst (default: localhost:50052)
  WATCH_INTERVAL_SEC refresh interval in seconds; 0 = run once and exit (default: 0)
"""

import os
import sys
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "proto"))

import grpc
import taskgrid_pb2
import taskgrid_pb2_grpc

from monitoring.monitoring import Monitoring

monitoring = Monitoring()

_DISPATCHER_ADDR = os.environ.get("DISPATCHER_ADDR", "localhost:50051")
_NAMESERVICE_ADDR = os.environ.get("NAMESERVICE_ADDR", "localhost:50052")
_WATCH_INTERVAL_SEC = int(os.environ.get("WATCH_INTERVAL_SEC", "0"))


def _make_header(message_type: str) -> taskgrid_pb2.MessageHeader:
    return taskgrid_pb2.MessageHeader(
        message_type=message_type,
        request_id=str(uuid.uuid4()),
        timestamp=int(time.time() * 1000),
        sender="monitoring",
    )


def _fetch_dispatcher_status(stub: taskgrid_pb2_grpc.DispatcherServiceStub) -> taskgrid_pb2.GetStatusResponse:
    return stub.GetDispatcherStatus(
        taskgrid_pb2.GetStatusRequest(header=_make_header("GetStatusRequest")),
        timeout=5,
    )


def _fetch_nameservice_status(stub: taskgrid_pb2_grpc.NameServiceStub) -> taskgrid_pb2.GetStatusResponse:
    return stub.GetNameServiceStatus(
        taskgrid_pb2.GetStatusRequest(header=_make_header("GetStatusRequest")),
        timeout=5,
    )


def _print_status(ds: taskgrid_pb2.GetStatusResponse, ns: taskgrid_pb2.GetStatusResponse | None) -> None:
    worker_registered = ns.workers_registered if ns else ds.workers_registered
    worker_active = ns.workers_active if ns else ds.workers_active
    task_types = ", ".join(ns.supported_task_types if ns else ds.supported_task_types) or "-"

    width = 44
    sep = "+" + "-" * (width - 2) + "+"

    def row(label: str, value) -> str:
        label_str = f"  {label}"
        value_str = str(value)
        pad = width - 2 - len(label_str) - len(value_str)
        if pad < 1:
            pad = 1
        return f"|{label_str}{' ' * pad}{value_str}|"

    now = time.strftime("%Y-%m-%d %H:%M:%S")
    title = f"TaskGrid+ Status  {now}"
    title_pad = width - 4 - len(title)
    if title_pad < 0:
        title_pad = 0
    print(sep)
    print(f"|  {title}{' ' * title_pad}|")
    print(sep)
    print(row("Workers registered", worker_registered))
    print(row("Workers active", worker_active))
    print(row("Supported task types", task_types))
    print(sep)
    print(row("Tasks queued", ds.tasks_queued))
    print(row("Tasks running", ds.tasks_running))
    print(row("Tasks completed", ds.tasks_completed))
    print(row("Tasks failed", ds.tasks_failed))
    print(sep)
    print(row("Avg processing time (ms)", f"{ds.avg_processing_time_ms:.1f}"))
    print(row("Total timeouts", ds.total_timeouts))
    print(row("Total retries", ds.total_retries))
    print(sep)


def query_once() -> None:
    request_id = str(uuid.uuid4())
    ds_status = None
    ns_status = None

    with grpc.insecure_channel(_DISPATCHER_ADDR) as ds_channel:
        ds_stub = taskgrid_pb2_grpc.DispatcherServiceStub(ds_channel)
        try:
            ds_status = _fetch_dispatcher_status(ds_stub)
            monitoring.on_dispatcher_status_queried(request_id)
            monitoring.on_status_response_received(
                request_id, "dispatcher", ds_status.workers_active, ds_status.tasks_queued
            )
        except grpc.RpcError as e:
            print(f"ERROR: cannot reach dispatcher at {_DISPATCHER_ADDR}: {e.details()}", file=sys.stderr)

    with grpc.insecure_channel(_NAMESERVICE_ADDR) as ns_channel:
        ns_stub = taskgrid_pb2_grpc.NameServiceStub(ns_channel)
        try:
            ns_status = _fetch_nameservice_status(ns_stub)
            monitoring.on_nameservice_status_queried(request_id)
            monitoring.on_status_response_received(
                request_id, "nameservice", ns_status.workers_active, 0
            )
        except grpc.RpcError:
            pass  # nameservice unavailable — fall back to dispatcher's worker data

    if ds_status is None:
        sys.exit(1)

    _print_status(ds_status, ns_status)


def main() -> None:
    if _WATCH_INTERVAL_SEC > 0:
        while True:
            try:
                query_once()
            except Exception as e:
                print(f"ERROR: {e}", file=sys.stderr)
            time.sleep(_WATCH_INTERVAL_SEC)
    else:
        query_once()


if __name__ == "__main__":
    main()
