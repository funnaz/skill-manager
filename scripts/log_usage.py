"""Append skill usage events for Claude/Codex hooks and manual logging."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from usage_collector import append_event, skill_name_from_path  # noqa: E402

SKILL_TITLE_RE = re.compile(r"^Skill\s+([a-z0-9][a-z0-9-]*)$", re.I)
SLASH_RE = re.compile(r"(?:^|\s)/([a-z][a-z0-9-]*)", re.I)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_stdin_json() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {"raw": raw}


def _event_from_hook(agent: str, event_type: str, payload: dict) -> dict | None:
    skill = ""
    path = ""
    session_id = str(payload.get("session_id") or payload.get("sessionId") or "")
    hook_event = str(payload.get("hook_event_name") or payload.get("hookEventName") or "")

    if hook_event == "UserPromptExpansion" or event_type == "slash":
        skill = str(
            payload.get("command")
            or payload.get("command_name")
            or payload.get("commandName")
            or ""
        ).strip().lstrip("/")
        if not skill:
            prompt = str(payload.get("prompt") or payload.get("expanded_prompt") or "")
            match = SLASH_RE.search(prompt)
            if match:
                skill = match.group(1)
    elif hook_event in {"PostToolUse", "PreToolUse"} or event_type == "read":
        tool_input = payload.get("tool_input") or payload.get("toolInput") or {}
        if isinstance(tool_input, dict):
            path = str(tool_input.get("file_path") or tool_input.get("path") or "")
        if not path:
            path = str(payload.get("file_path") or payload.get("path") or "")
        if path.lower().endswith("skill.md"):
            skill = skill_name_from_path(path)
    else:
        prompt = str(payload.get("prompt") or payload.get("user_prompt") or "")
        match = SLASH_RE.search(prompt)
        if match:
            skill = match.group(1)
            event_type = "slash"

    if not skill:
        return None

    return {
        "ts": _now_iso(),
        "agent": agent,
        "skill": skill,
        "event": event_type,
        "source": "hook",
        "session_id": session_id,
        "path": path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Log a skill usage event")
    parser.add_argument("agent", choices=["claude", "codex", "grok", "cursor"])
    parser.add_argument("event", choices=["read", "slash", "auto", "hook"])
    parser.add_argument("--skill", help="Skill name")
    parser.add_argument("--path", default="", help="SKILL.md path if known")
    parser.add_argument("--session", default="", help="Session id")
    parser.add_argument("--stdin", action="store_true", help="Read Claude/Codex hook JSON from stdin")
    args = parser.parse_args(argv)

    if args.stdin:
        payload = _read_stdin_json()
        event = _event_from_hook(args.agent, args.event, payload)
        if not event:
            return 0
        append_event(event)
        return 0

    skill = (args.skill or "").strip().lstrip("/")
    if not skill and args.path:
        skill = skill_name_from_path(args.path)
    if not skill:
        print("skill name required", file=sys.stderr)
        return 1

    append_event(
        {
            "ts": _now_iso(),
            "agent": args.agent,
            "skill": skill,
            "event": args.event,
            "source": "manual",
            "session_id": args.session,
            "path": args.path,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())