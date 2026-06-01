FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir grpcio

COPY proto/taskgrid_pb2.py proto/taskgrid_pb2_grpc.py proto/
COPY common/ common/
COPY worker/ worker/

RUN chmod +x /app/worker/docker-entrypoint.sh

EXPOSE 50053

ENTRYPOINT ["/app/worker/docker-entrypoint.sh"]
