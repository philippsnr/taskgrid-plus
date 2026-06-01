#!/bin/sh
export WORKER_ID="${WORKER_ID:-$(hostname)}"
export WORKER_ADDRESS="${WORKER_ADDRESS:-$(hostname)}"
exec python worker/main.py
