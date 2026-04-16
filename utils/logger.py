"""
GoldX Bot — Centralized logging via loguru.
"""

import sys
import os
from loguru import logger

from config import LOG_LEVEL, LOG_FILE


def setup_logger() -> None:
    """Configure loguru for console + rotating file output."""
    log_dir = os.path.dirname(LOG_FILE)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    logger.remove()  # Remove default handler

    # Console — colored, human-readable
    logger.add(
        sys.stdout,
        level=LOG_LEVEL,
        colorize=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{line}</cyan> — <level>{message}</level>",
    )

    # File — rotation every day, keep 7 days
    logger.add(
        LOG_FILE,
        level=LOG_LEVEL,
        rotation="00:00",
        retention="7 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} — {message}",
    )

    logger.info("Logger initialized — level={}", LOG_LEVEL)


# Auto-setup on import
setup_logger()

__all__ = ["logger"]
