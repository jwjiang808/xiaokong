"""Configure Loguru for first-party and standard-library logs."""

from __future__ import annotations

import inspect
import logging
import sys

from loguru import logger

_configured = False


class _InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame = inspect.currentframe()
        depth = 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1
        logger.patch(lambda log: log.update(name=record.name)).opt(
            depth=depth, exception=record.exc_info
        ).log(level, record.getMessage())


def setup_logging() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        colorize=sys.stderr.isatty(),
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <7}</level> | "
            "<cyan>{name}</cyan> | "
            "<level>{message}</level>"
        ),
    )
    logging.basicConfig(
        handlers=[_InterceptHandler()],
        level=logging.INFO,
        force=True,
    )
