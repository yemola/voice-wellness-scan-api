"""
analysis/logger.py
------------------
Centralised logging configuration for the Voice Wellness FastAPI backend.

Usage
-----
    from analysis.logger import get_logger
    log = get_logger(__name__)
    log.debug("message")

Environment
-----------
Set  DEBUG=True  (or 1 / yes / on)  to enable debug output.
Omit or set to any other value to suppress debug logs.
"""

import logging
import os
import sys

# ── Read the DEBUG flag from the environment ────────────────────────────────
_raw = os.environ.get("DEBUG", "false").strip().lower()
DEBUG_ENABLED: bool = _raw in ("1", "true", "yes", "on")

# ── One-time setup (idempotent — safe to import multiple times) ──────────────
_HANDLER_INSTALLED = False


def _setup() -> None:
    global _HANDLER_INSTALLED
    if _HANDLER_INSTALLED:
        return

    level = logging.DEBUG if DEBUG_ENABLED else logging.WARNING

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    root = logging.getLogger("voice_api")
    root.setLevel(level)
    # Avoid duplicate handlers if uvicorn reloads the module
    root.handlers.clear()
    root.addHandler(handler)
    root.propagate = False

    _HANDLER_INSTALLED = True


_setup()


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the 'voice_api' namespace."""
    return logging.getLogger(f"voice_api.{name}")
