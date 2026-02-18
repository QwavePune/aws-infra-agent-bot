"""Structured workflow execution logging with file rotation."""

import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from typing import Any, Dict


def setup_workflow_logger(app_root: str, channel: str) -> logging.Logger:
    """Create a dedicated JSONL workflow logger with timed rotation."""
    log_dir = os.path.join(app_root, "logs", "workflow_execution_log")
    os.makedirs(log_dir, exist_ok=True)

    logger_name = f"workflow.{channel}"
    logger = logging.getLogger(logger_name)
    if logger.handlers:
        return logger

    log_file = os.path.join(log_dir, f"workflow_execution_log_{channel}.jsonl")
    handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))

    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)
    return logger


def workflow_event(logger: logging.Logger, event_type: str, **payload: Any) -> None:
    """Write one workflow execution event as JSON to log file."""
    record: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
    }
    record.update(payload)
    logger.info(json.dumps(record, default=str))
