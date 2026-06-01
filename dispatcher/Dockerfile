FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir grpcio

COPY proto/taskgrid_pb2.py proto/taskgrid_pb2_grpc.py proto/
COPY common/ common/
COPY dispatcher/ dispatcher/

EXPOSE 50051

CMD ["python", "dispatcher/main.py"]
