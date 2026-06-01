# Docker Build Guide

## Overview

Each TaskGrid+ component has its own Dockerfile. All images use `python:3.12-slim` and are configured exclusively via environment variables — no addresses or worker types are hardcoded.

The pre-generated proto bindings (`proto/taskgrid_pb2.py`, `proto/taskgrid_pb2_grpc.py`) are copied into each image at build time. No `protoc` installation is required inside the containers.

## Building all images

```bash
docker compose build
```

## Running the full stack

```bash
docker compose up
```

This starts: nameservice, dispatcher, all five worker types (sum, reverse, hash, upper, wait), and the monitoring dashboard.

## Environment variables

### nameservice

| Variable | Default | Description |
|---|---|---|
| `NAMESERVICE_PORT` | `50051` | gRPC listen port |
| `HEARTBEAT_TIMEOUT_SEC` | `30` | Seconds before a worker is marked UNHEALTHY |
| `OFFLINE_TIMEOUT_SEC` | `90` | Seconds before a worker is marked OFFLINE |

### dispatcher

| Variable | Default | Description |
|---|---|---|
| `DISPATCHER_PORT` | `50051` | gRPC listen port |
| `NAMESERVICE_ADDR` | `nameservice:50052` | Namensdienst address |
| `TASK_TIMEOUT_SEC` | `60` | Task timeout before retry |
| `MAX_RETRIES` | `3` | Max dispatch retries per task |
| `LOG_LEVEL` | `INFO` | Log verbosity (DEBUG/INFO/WARNING/ERROR) |

### worker

| Variable | Default | Description |
|---|---|---|
| `WORKER_ID` | *(required)* | Unique worker identifier |
| `WORKER_TYPE` | *(required)* | Task type: `sum`, `reverse`, `hash`, `upper`, `wait` |
| `WORKER_ADDRESS` | `0.0.0.0` | Address registered with the Namensdienst (set to the service hostname in Docker) |
| `WORKER_PORT` | `50052` | gRPC listen port |
| `NAMESERVICE_ADDRESS` | `localhost` | Namensdienst host |
| `NAMESERVICE_PORT` | `50051` | Namensdienst port |
| `DISPATCHER_ADDRESS` | `localhost` | Dispatcher host (for result return) |
| `DISPATCHER_PORT` | `50051` | Dispatcher port |
| `WORKER_CAPACITY` | `10` | Max concurrent tasks |

### monitoring

| Variable | Default | Description |
|---|---|---|
| `DISPATCHER_ADDR` | `localhost:50051` | Dispatcher address |
| `NAMESERVICE_ADDR` | `localhost:50052` | Namensdienst address |
| `WATCH_INTERVAL_SEC` | `0` | Refresh interval in seconds; `0` = run once |

### client

| Variable | Default | Description |
|---|---|---|
| `DISPATCHER_HOST` | `localhost` | Dispatcher host |
| `DISPATCHER_PORT` | `50051` | Dispatcher port |

## Sending a task via client container

```bash
docker compose run --rm client send sum "1,2,3,4"
docker compose run --rm client result 1
```

The `client` service is in the `tools` profile and does not start with `docker compose up`. Use `docker compose run` to invoke it on demand.

## Running the monitoring dashboard standalone

```bash
docker compose run --rm monitoring
```

## Adding more workers of a given type

To run multiple workers of the same type, add additional service entries in `docker-compose.yml` with unique `WORKER_ID` and `WORKER_ADDRESS` values:

```yaml
worker-sum-2:
  build:
    context: .
    dockerfile: worker/Dockerfile
  environment:
    - WORKER_ID=worker-sum-2
    - WORKER_TYPE=sum
    - WORKER_ADDRESS=worker-sum-2
    - WORKER_PORT=50053
    - NAMESERVICE_ADDRESS=nameservice
    - NAMESERVICE_PORT=50052
    - DISPATCHER_ADDRESS=dispatcher
    - DISPATCHER_PORT=50051
  depends_on:
    - nameservice
    - dispatcher
```

Each worker must have a unique `WORKER_ID` and its `WORKER_ADDRESS` must match the Docker Compose service name so the dispatcher can route tasks to it.
