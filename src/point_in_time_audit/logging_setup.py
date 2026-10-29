"""Structured logging: key=value pairs on stderr, machine-greppable.

The CLI's stdout is the report and its exit code is the verdict, so logging
stays out of both. One configuration function, used by the CLI and every
experiment, so a reviewer reading CI output sees one format everywhere.
"""

from __future__ import annotations

import logging
import sys


class KeyValueFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = f"level={record.levelname.lower()} logger={record.name} msg={record.getMessage()!r}"
        extras = getattr(record, "fields", None)
        if extras:
            pairs = " ".join(f"{k}={v}" for k, v in sorted(extras.items()))
            return f"{base} {pairs}"
        return base


def configure(level: int = logging.INFO) -> logging.Logger:
    root = logging.getLogger("pit_audit")
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(KeyValueFormatter())
        root.addHandler(handler)
    root.setLevel(level)
    return root


def log_fields(logger: logging.Logger, msg: str, **fields) -> None:
    logger.info(msg, extra={"fields": fields})
