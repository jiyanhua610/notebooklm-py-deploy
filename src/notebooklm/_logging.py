"""Logging configuration for notebooklm-py."""

import logging
import os


def configure_logging() -> None:
    """Configure logging based on environment variables.

    Environment Variables:
        NOTEBOOKLM_LOG_LEVEL: Set to DEBUG, INFO, WARNING (default), or ERROR
        NOTEBOOKLM_DEBUG_RPC: Legacy - set to "1" to enable DEBUG level

    Safe to call multiple times (idempotent - won't add duplicate handlers).
    """
    # Check if already configured (including parent handlers)
    logger = logging.getLogger("notebooklm")
    if logger.hasHandlers():
        return  # Already configured

    # Determine log level
    level_name = os.environ.get("NOTEBOOKLM_LOG_LEVEL", "WARNING").upper()

    # Legacy support: DEBUG_RPC=1 overrides to DEBUG level
    if os.environ.get("NOTEBOOKLM_DEBUG_RPC", "").lower() in ("1", "true", "yes"):
        level_name = "DEBUG"

    level = getattr(logging, level_name, logging.WARNING)

    # Configure the notebooklm logger hierarchy
    logger.setLevel(level)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    logger.addHandler(console_handler)

    # File handler (fixed to service.log in the current directory)
    log_file = os.environ.get("NOTEBOOKLM_LOG_FILE", "service.log")
    try:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(file_handler)
    except Exception as e:
        # If we can't write to the file (e.g. permission issues), log to console and move on
        print(f"Warning: Could not set up file logging to {log_file}: {e}")
