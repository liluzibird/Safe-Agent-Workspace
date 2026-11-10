"""Append-only JSONL audit logging for agent activity."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any


def _shorten(value: Any, limit: int = 4000) -> Any:
    """Keep audit records useful without allowing huge model output entries."""

    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "...[truncated]"
    return value


class AuditLogger:
    """Write one structured JSON record for each important agent event."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("safe_workspace_agent")

    def event(self, event: str, **details: Any) -> None:
        """Append an event and mirror failures to the standard logger."""

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **{key: _shorten(value) for key, value in details.items()},
        }
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            self.logger.error("Could not write audit record: %s", exc)


def configure_logging(log_path: str | Path) -> None:
    """Configure a small human-readable operational log."""

    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
