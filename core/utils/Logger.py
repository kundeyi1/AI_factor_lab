"""Logging helpers for Quant.

Library modules should call ``get_logger(__name__)`` or import the compatibility
``logger`` object. Neither path configures handlers or creates log files during
import. Application entry points should call ``configure_logging()`` explicitly
when console/file logging is desired.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path


DEFAULT_LOGGER_NAME = "QuantCore"
_HANDLER_MARK = "_quant_logging_handler"


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger without configuring handlers or touching the filesystem."""
    return logging.getLogger(name or DEFAULT_LOGGER_NAME)


def _has_quant_handler(logger: logging.Logger, handler_kind: str) -> bool:
    return any(getattr(handler, _HANDLER_MARK, None) == handler_kind for handler in logger.handlers)


def configure_logging(
    *,
    level: int = logging.DEBUG,
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
    log_dir: str | Path | None = None,
    logger_name: str | None = None,
    enable_console: bool = True,
    enable_file: bool = True,
) -> logging.Logger:
    """Configure logging explicitly for an application entry point.

    By default this configures the root logger so module loggers created with
    ``logging.getLogger(__name__)`` propagate to the same handlers.
    """
    target_logger = logging.getLogger(logger_name) if logger_name else logging.getLogger()
    target_logger.setLevel(level)

    if enable_console and not _has_quant_handler(target_logger, "console"):
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(console_level)
        console_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - [%(levelname)s] - %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        setattr(console_handler, _HANDLER_MARK, "console")
        target_logger.addHandler(console_handler)

    if enable_file and not _has_quant_handler(target_logger, "file"):
        resolved_log_dir = Path(log_dir) if log_dir is not None else Path(__file__).resolve().parents[1] / "logs"
        try:
            resolved_log_dir.mkdir(parents=True, exist_ok=True)
            log_filename = f"quant_log_{datetime.now().strftime('%Y%m%d')}.log"
            file_handler = logging.FileHandler(resolved_log_dir / log_filename, encoding="utf-8")
            file_handler.setLevel(file_level)
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
                )
            )
            setattr(file_handler, _HANDLER_MARK, "file")
            target_logger.addHandler(file_handler)
        except Exception as exc:
            logging.getLogger(__name__).warning("Could not create log file in %s: %s", resolved_log_dir, exc)

    return target_logger


def setup_logger(*args, **kwargs) -> logging.Logger:
    """Backward-compatible alias for explicit logging configuration."""
    return configure_logging(*args, **kwargs)


# Compatibility export. Importing this logger has no side effects.
logger = get_logger(DEFAULT_LOGGER_NAME)


if __name__ == "__main__":
    configure_logging()
    test_logger = get_logger(__name__)
    test_logger.info("Logger test: Standard Info")
    test_logger.debug("Logger test: Debug Message (File Only)")
    test_logger.error("Logger test: Error Message")
