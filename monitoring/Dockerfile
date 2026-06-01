FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir grpcio protobuf

COPY proto/taskgrid_pb2.py proto/taskgrid_pb2_grpc.py proto/
COPY common/ common/
COPY monitoring/ monitoring/

CMD ["python", "monitoring/main.py"]
