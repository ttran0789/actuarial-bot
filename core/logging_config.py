"""Centralized logging for the actuarial bot."""

import logging
import os
from datetime import datetime


def setup_logging(log_dir: str = None, level: str = "INFO") -> logging.Logger:
    """Configure logging to both file and console.

    Log files are stored in log_dir (default: ~/Documents/actuarial-bot-logs/)
    with one file per day.
    """
    if log_dir is None:
        log_dir = os.path.join(os.path.expanduser("~"), "Documents", "actuarial-bot-logs")
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, f"actbot_{datetime.now():%Y-%m-%d}.log")

    logger = logging.getLogger("actuarial_bot")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Don't add handlers if they already exist (re-import safety)
    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler — all levels
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Console handler — INFO and above
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger
