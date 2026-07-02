"""Install usage-tracking hooks for Claude Code (and optional Codex notify)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

HOME = Path.home()
PROJECT_ROOT = Path(__file__).resolve().parent
LOG_SCRIPT = PROJECT_ROOT / "scripts" / "log_usage.py"
CLAUDE_SETTINGS = HOME / ".claude" / "settings.json"
MARKER = "skill-manager-usage"


def _python_command() -> str:
    return sys.executable


def _hook_entry(agent: str, event: str) -> dict[str, Any]:
    return {
        "type": "command",
        "command": _python_command(),
        "args": [str(LOG_SCRIPT), agent, event, "--stdin"],
        "_skill_manager": MARKER,
    }


def _merge_hooks(existing: dict[str, Any] | None, agent: str) -> dict[str, Any]:
    hooks = dict(existing or {})
    expansion = hooks.setdefault("UserPromptExpansion", [])
    post_read = hooks.setdefault("PostToolUse", [])

    def has_marker(group: list[dict[str, Any]]) -> bool:
        for item in group:
            for handler in item.get("hooks", []):
                if handler.get("_skill_manager") == MARKER:
                    return True
        return False

    if not has_marker(expansion):
        expansion.append({"hooks": [_hook_entry(agent, "slash")]})

    read_group = None
    for item in post_read:
        if item.get("matcher") == "Read":
            read_group = item
            break
    if read_group is None:
        read_group = {"matcher": "Read", "hooks": []}
        post_read.append(read_group)

    handlers = read_group.setdefault("hooks", [])
    if not any(handler.get("_skill_manager") == MARKER for handler in handlers):
        handlers.append(_hook_entry(agent, "read"))

    return hooks


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def install_claude_hooks() -> dict[str, Any]:
    settings = _load_json(CLAUDE_SETTINGS)
    settings["hooks"] = _merge_hooks(settings.get("hooks"), "claude")
    _save_json(CLAUDE_SETTINGS, settings)
    return {
        "ok": True,
        "agent": "claude",
        "settings_path": str(CLAUDE_SETTINGS),
        "log_script": str(LOG_SCRIPT),
    }


def install_codex_notify() -> dict[str, Any]:
    """Best-effort: document-only for Codex since rollout parsing is primary."""
    from usage_collector import resolve_codex_home

    codex_home = resolve_codex_home()
    return {
        "ok": True,
        "agent": "codex",
        "mode": "rollout-scan",
        "codex_home": str(codex_home or ""),
        "note": "Codex 暂无稳定的 skill hook；Skill 管家通过解析 CODEX_HOME 下的 rollout 会话统计 skill 读取。",
    }


def install_all_hooks() -> dict[str, Any]:
    return {
        "claude": install_claude_hooks(),
        "codex": install_codex_notify(),
    }


def hook_status() -> dict[str, Any]:
    settings = _load_json(CLAUDE_SETTINGS)
    hooks = settings.get("hooks") or {}
    claude_installed = False
    for event_name in ("UserPromptExpansion", "PostToolUse"):
        for group in hooks.get(event_name, []):
            for handler in group.get("hooks", []):
                if handler.get("_skill_manager") == MARKER:
                    claude_installed = True
    from usage_collector import resolve_codex_home

    return {
        "claude": {
            "installed": claude_installed,
            "settings_path": str(CLAUDE_SETTINGS),
            "settings_exists": CLAUDE_SETTINGS.exists(),
        },
        "codex": {
            "installed": bool(resolve_codex_home()),
            "mode": "rollout-scan",
            "codex_home": str(resolve_codex_home() or ""),
        },
        "grok": {
            "installed": (HOME / ".grok" / "sessions").exists(),
            "mode": "updates.jsonl",
        },
        "log_script": str(LOG_SCRIPT),
        "log_script_exists": LOG_SCRIPT.exists(),
    }
