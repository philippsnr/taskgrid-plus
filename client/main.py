#!/usr/bin/env python3
"""
Client entry point.

Usage:
  python client/main.py send <type> <payload>
  python client/main.py result <task_id>

Environment variables:
  DISPATCHER_HOST  Dispatcher host (default: localhost)
  DISPATCHER_PORT  Dispatcher port (default: 50051)
"""

import sys
import os

repo_root = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, repo_root)
sys.path.insert(0, os.path.join(repo_root, "proto"))

from client.client import Client


def _print_usage() -> None:
    print("Usage:")
    print("  python client/main.py send <type> <payload>")
    print("  python client/main.py result <task_id>")
    print()
    print("Environment variables:")
    print("  DISPATCHER_HOST  Dispatcher host (default: localhost)")
    print("  DISPATCHER_PORT  Dispatcher port (default: 50051)")


def main() -> None:
    if len(sys.argv) < 2:
        _print_usage()
        sys.exit(1)

    command = sys.argv[1]
    client = Client()

    if command == "send":
        if len(sys.argv) < 4:
            print("Usage: client/main.py send <type> <payload>")
            sys.exit(1)
        client.send_task(sys.argv[2], sys.argv[3])

    elif command == "result":
        if len(sys.argv) < 3:
            print("Usage: client/main.py result <task_id>")
            sys.exit(1)
        try:
            task_id = int(sys.argv[2])
        except ValueError:
            print(f"Error: task_id must be an integer, got '{sys.argv[2]}'")
            sys.exit(1)
        client.request_result(task_id)

    else:
        print(f"Unknown command: '{command}'")
        _print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
