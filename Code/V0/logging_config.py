"""Structured JSON logging configuration for Forbidden Scribe."""

import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


class JsonFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Args:
            record: The log record to format.

        Returns:
            JSON-formatted log string.
        """
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data)


def setup_logging(
    log_path: str = "logs/forbidden_scribe.log",
    level: int = logging.DEBUG,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
) -> logging.Logger:
    """Configure structured JSON logging with rotation.

    Args:
        log_path: Path to the log file.
        level: Logging level (default DEBUG).
        max_bytes: Maximum log file size before rotation (default 10MB).
        backup_count: Number of backup files to keep (default 5).

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger("forbidden_scribe")
    logger.setLevel(level)

    # Avoid adding duplicate handlers
    if logger.handlers:
        return logger

    # Ensure log directory exists
    log_dir = Path(log_path).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    # Create rotating file handler
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(JsonFormatter())
    logger.addHandler(file_handler)

    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Get a logger instance.

    Args:
        name: Optional name for child logger. If None, returns root logger.

    Returns:
        Logger instance.
    """
    base_logger = logging.getLogger("forbidden_scribe")
    if name:
        return base_logger.getChild(name)
    return base_logger
