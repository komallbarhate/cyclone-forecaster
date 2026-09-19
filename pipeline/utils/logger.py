"""
Structured logging utilities for the CycloneShield pipeline.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path


LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Return a named logger configured with console output.

    Parameters
    ----------
    name : str
        Logger name (typically ``__name__`` of the calling module).
    level : int
        Logging level (default INFO).

    Returns
    -------
    logging.Logger
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        # Avoid charmap encode issues on Windows consoles
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


def setup_file_logger(name: str, log_path: Path, level: int = logging.INFO) -> logging.Logger:
    """
    Return a logger that writes to both console and a file.

    Parameters
    ----------
    name : str
        Logger name.
    log_path : Path
        Path to the log file (will be created/appended).
    level : int
        Logging level.

    Returns
    -------
    logging.Logger
    """
    logger = get_logger(name, level)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    logger.addHandler(file_handler)
    return logger
