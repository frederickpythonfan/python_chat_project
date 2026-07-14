"""
Standard logging configuration for a Python application.

Usage:
    from logging_config import setup_logging
    setup_logging()

    import logging
    logger = logging.getLogger(__name__)
    logger.info("app started")
"""

import logging
import logging.config
import os
from pathlib import Path

LOG_DIR = Path(os.environ.get("LOG_DIR", "logs"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
APP_NAME = os.environ.get("APP_NAME", "app")

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,

    "formatters": {
        "standard": {
            "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "detailed": {
            "format": (
                "%(asctime)s | %(levelname)-8s | %(name)s | "
                "%(filename)s:%(lineno)d | %(funcName)s() | %(message)s"
            ),
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },

    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": LOG_LEVEL,
            "formatter": "standard",
            "stream": "ext://sys.stdout",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "DEBUG",
            "formatter": "detailed",
            "filename": str(LOG_DIR / f"{APP_NAME}.log"),
            "maxBytes": 10 * 1024 * 1024,  # 10 MB
            "backupCount": 5,
            "encoding": "utf-8",
        },
        "error_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "ERROR",
            "formatter": "detailed",
            "filename": str(LOG_DIR / f"{APP_NAME}.error.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "encoding": "utf-8",
        },
    },

    "root": {
        "level": "DEBUG",
        "handlers": ["console", "file", "error_file"],
    },

    "loggers": {
        # quiet down noisy third-party libraries individually, e.g.:
        # "urllib3": {"level": "WARNING", "propagate": True},
        # "asyncio": {"level": "WARNING", "propagate": True},
    },
}


def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.config.dictConfig(LOGGING_CONFIG)
    logging.getLogger(__name__).debug("Logging configured (level=%s)", LOG_LEVEL)


if __name__ == "__main__":
    setup_logging()
    log = logging.getLogger(__name__)
    log.debug("debug message")
    log.info("info message")
    log.warning("warning message")
    log.error("error message")
    try:
        1 / 0
    except ZeroDivisionError:
        log.exception("caught an exception")