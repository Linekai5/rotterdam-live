"""Structured logging configuration using Loguru."""
import sys
import logging
from loguru import logger
from app.config import settings


class InterceptHandler(logging.Handler):
    """Intercept standard logging messages and route them to Loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame.f_back and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging() -> None:
    """Initialize structured logging."""
    logger.remove()

    if settings.ENVIRONMENT == "production":
        # Structured JSON format in production
        logger.add(
            sys.stdout,
            level=settings.LOG_LEVEL,
            serialize=True,
            backtrace=False,
            diagnose=False,
        )
    else:
        # Readable colored console format in development
        logger.add(
            sys.stdout,
            level=settings.LOG_LEVEL,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            colorize=True,
        )

    # Intercept standard library logging (e.g. uvicorn, sqlalchemy, fastapi)
    logging.root.handlers = [InterceptHandler()]
    logging.root.setLevel(settings.LOG_LEVEL)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logging_logger = logging.getLogger(logger_name)
        logging_logger.handlers = [InterceptHandler()]
        logging_logger.propagate = False
