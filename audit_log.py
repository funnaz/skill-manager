"""Append-only local audit log for Skill Manager operations."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from scanner import HOME

AUDIT_PATH = HOME / ".skill-manager" / "audit.log"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def append_audit(action: str, **payload: Any) -> dict[str, Any]:
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    event = {"ts": _now_iso(), "action": action, **payload}
    with AUDIT_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def read_audit(limit: int = 100) -> list[dict[str, Any]]:
    if not AUDIT_PATH.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in AUDIT_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            events.append(item)
    return events[-limit:]
