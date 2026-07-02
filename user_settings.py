"""Persist per-user Skill Manager preferences."""

from __future__ import annotations

import json
from typing import Any

from scanner import HOME

SETTINGS_PATH = HOME / ".skill-manager" / "settings.json"
DEFAULT_SCOPE = "agents"
UI_SCOPES = ("agents", "claude", "codex", "cursor", "grok")


def _default_settings() -> dict[str, Any]:
    return {"default_scope": DEFAULT_SCOPE}


def load_settings() -> dict[str, Any]:
    if not SETTINGS_PATH.exists():
        return _default_settings()
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _default_settings()
    scope = str(data.get("default_scope") or DEFAULT_SCOPE)
    if scope not in UI_SCOPES:
        scope = DEFAULT_SCOPE
    return {"default_scope": scope}


def save_settings(payload: dict[str, Any]) -> dict[str, Any]:
    current = load_settings()
    scope = str(payload.get("default_scope") or current["default_scope"]).strip()
    if scope not in UI_SCOPES:
        raise ValueError(f"default_scope 仅支持: {', '.join(UI_SCOPES)}")
    current["default_scope"] = scope
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return current
