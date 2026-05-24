import logging
import os
import sys


class _StructuredFormatter(logging.Formatter):
    def __init__(self, component: str):
        super().__init__()
        self._prefix = f"[{component}]"

    def format(self, record: logging.LogRecord) -> str:
        return f"{self._prefix} {record.getMessage()}"


class ComponentLogger:
    """Emits structured log lines: [component] key=val key=val ...

    Log level is controlled by the LOG_LEVEL environment variable
    (DEBUG, INFO, WARNING, ERROR). Defaults to INFO.

    If LOG_DIR is set, logs are also written to LOG_DIR/<component>.log
    so they can be persisted via a Docker volume mount.
    """

    def __init__(self, component: str):
        level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)

        self._logger = logging.getLogger(f"taskgrid.{component}")
        if not self._logger.handlers:
            stdout_handler = logging.StreamHandler(sys.stdout)
            stdout_handler.setFormatter(_StructuredFormatter(component))
            self._logger.addHandler(stdout_handler)

            log_dir = os.environ.get("LOG_DIR", "")
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
                file_handler = logging.FileHandler(
                    os.path.join(log_dir, f"{component}.log"), encoding="utf-8"
                )
                file_handler.setFormatter(_StructuredFormatter(component))
                self._logger.addHandler(file_handler)

            self._logger.propagate = False
        self._logger.setLevel(level)

    @staticmethod
    def _fmt(**fields: object) -> str:
        return " ".join(f"{k}={v}" for k, v in fields.items())

    def debug(self, **fields: object) -> None:
        self._logger.debug(self._fmt(**fields))

    def info(self, **fields: object) -> None:
        self._logger.info(self._fmt(**fields))

    def warning(self, **fields: object) -> None:
        self._logger.warning(self._fmt(**fields))

    def error(self, **fields: object) -> None:
        self._logger.error(self._fmt(**fields))


def get_logger(component: str) -> ComponentLogger:
    """Return a ComponentLogger for the named component.

    Typical usage:
        logger = get_logger("dispatcher")
        logger.info(request_id="abc123", task_id=42, status="QUEUED", type="sum")
        # → [dispatcher] request_id=abc123 task_id=42 status=QUEUED type=sum
    """
    return ComponentLogger(component)
