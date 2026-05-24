#!/usr/bin/env bash
# Regenerates Python gRPC bindings from taskgrid.proto.
# Run from the repo root: bash proto/compile_proto.sh
#
# Requires: pip install grpcio-tools
set -e

PROTO_DIR="proto"
OUT_DIR="proto"

python -m grpc_tools.protoc \
  --proto_path="$PROTO_DIR" \
  --python_out="$OUT_DIR" \
  --grpc_python_out="$OUT_DIR" \
  "$PROTO_DIR/taskgrid.proto"

echo "Generated: proto/taskgrid_pb2.py and proto/taskgrid_pb2_grpc.py"
