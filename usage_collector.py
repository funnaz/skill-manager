"""Collect and aggregate skill usage from Grok, Claude Code, and Codex."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HOME = Path.home()
DATA_DIR = HOME / ".skill-manager"
EVENTS_PATH = DATA_DIR / "usage-events.jsonl"
STATE_PATH = DATA_DIR / "usage-scan-state.json"

SKILL_PATH_RE = re.compile(
    r"[\\/]+(?:skills|bundled[\\/]+skills)[\\/]([^\\/]+)[\\/]+SKILL\.md",
    re.I,
)
SKILL_TITLE_RE = re.compile(r"Skill\s+([a-z0-9][a-z0-9-]*)", re.I)
CODEX_HOME_RE = re.compile(r"CODEX_HOME\s*=\s*['\"]([^'\"]+)['\"]", re.I)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def skill_name_from_path(path: str) -> str:
    normalized = str(path or "").replace("\\", "/")
    match = SKILL_PATH_RE.search(normalized)
    if match:
        return match.group(1).lower()
    parent = Path(path).parent.name if path else ""
    return parent.lower() if parent else ""


def _event_id(event: dict[str, Any]) -> str:
    raw = "|".join(
        [
            str(event.get("agent", "")),
            str(event.get("skill", "")),
            str(event.get("event", "")),
            str(event.get("ts", "")),
            str(event.get("source", "")),
            str(event.get("session_id", "")),
            str(event.get("path", "")),
            str(event.get("line_key", "")),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def append_event(event: dict[str, Any]) -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    skill = str(event.get("skill") or "").strip().lower().lstrip("/")
    if not skill:
        raise ValueError("skill is required")
    normalized = {
        "ts": event.get("ts") or _now_iso(),
        "agent": event.get("agent") or "unknown",
        "skill": skill,
        "event": event.get("event") or "auto",
        "source": event.get("source") or "manual",
        "session_id": event.get("session_id") or "",
        "path": event.get("path") or "",
        "line_key": event.get("line_key") or "",
    }
    normalized["id"] = _event_id(normalized)
    with EVENTS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(normalized, ensure_ascii=False) + "\n")
    return normalized


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"files": {}, "last_collect_at": None}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"files": {}, "last_collect_at": None}
    except (json.JSONDecodeError, OSError):
        return {"files": {}, "last_collect_at": None}


def _save_state(state: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_existing_ids() -> set[str]:
    ids: set[str] = set()
    if not EVENTS_PATH.exists():
        return ids
    for line in EVENTS_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            if isinstance(item, dict) and item.get("id"):
                ids.add(str(item["id"]))
        except json.JSONDecodeError:
            continue
    return ids


def _append_many(events: list[dict[str, Any]], existing_ids: set[str]) -> int:
    added = 0
    for event in events:
        event_id = _event_id(event)
        if event_id in existing_ids:
            continue
        event["id"] = event_id
        with EVENTS_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        existing_ids.add(event_id)
        added += 1
    return added


def _parse_ts(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value > 1_000_000_000_000:
            value = value / 1000
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        return text
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return text


def resolve_codex_home() -> Path | None:
    env_home = os.environ.get("CODEX_HOME")
    if env_home:
        candidate = Path(env_home)
        if candidate.exists():
            return candidate

    candidates = [HOME / ".codex", Path("D:/Codex"), Path("D:\\Codex")]
    for base in candidates:
        config = base / "config.toml"
        if config.exists():
            try:
                text = config.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                text = ""
            match = CODEX_HOME_RE.search(text)
            if match:
                resolved = Path(match.group(1))
                if resolved.exists():
                    return resolved
            if (base / "sessions").exists() or (base / "archived_sessions").exists():
                return base
    return None


def _iter_scan_files(state: dict[str, Any], pattern: str, roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        if root.is_file():
            files.append(root)
            continue
        files.extend(sorted(root.rglob(pattern)))
    return files


def _scan_file_incremental(
    file_path: Path,
    state: dict[str, Any],
    parser,
    agent: str,
    source: str,
) -> list[dict[str, Any]]:
    key = str(file_path)
    prev = state.get("files", {}).get(key, {})
    offset = int(prev.get("offset", 0))
    try:
        size = file_path.stat().st_size
    except OSError:
        return []
    if size < offset:
        offset = 0

    events: list[dict[str, Any]] = []
    try:
        with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
            handle.seek(offset)
            for line_no, line in enumerate(handle, start=1):
                line_key = f"{key}:{offset + line_no}"
                for item in parser(line, file_path, line_key):
                    item["agent"] = agent
                    item["source"] = source
                    events.append(item)
            new_offset = handle.tell()
    except OSError:
        return []

    state.setdefault("files", {})[key] = {"offset": new_offset, "size": size}
    return events


def _parse_grok_line(line: str, file_path: Path, line_key: str) -> list[dict[str, Any]]:
    if "Skill " not in line and "SKILL.md" not in line:
        return []
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return []

    update = payload.get("params", {}).get("update", {})
    if update.get("sessionUpdate") != "tool_call_update":
        return []

    title = str(update.get("title") or "")
    match = SKILL_TITLE_RE.search(title)
    skill = match.group(1).lower() if match else ""
    path = ""
    for loc in update.get("locations") or []:
        candidate = str(loc.get("path") or "")
        if candidate.lower().endswith("skill.md"):
            path = candidate
            if not skill:
                skill = skill_name_from_path(candidate)
            break

    if not skill:
        return []

    ts = _parse_ts(payload.get("timestamp"))
    session_id = str(payload.get("params", {}).get("sessionId") or "")
    return [
        {
            "ts": ts or _now_iso(),
            "skill": skill,
            "event": "read",
            "session_id": session_id,
            "path": path,
            "line_key": line_key,
        }
    ]


def _parse_codex_line(line: str, file_path: Path, line_key: str) -> list[dict[str, Any]]:
    if "function_call" not in line or "SKILL.md" not in line:
        return []
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return []

    item = payload.get("payload") or {}
    if item.get("type") != "function_call":
        return []

    ts = _parse_ts(payload.get("timestamp"))
    session_id = file_path.stem
    events: list[dict[str, Any]] = []
    seen: set[str] = set()

    args_raw = item.get("arguments") or ""
    try:
        args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
    except json.JSONDecodeError:
        args = {}
    command = str((args or {}).get("command") or "")
    if "skill.md" not in command.lower():
        return []

    for match in SKILL_PATH_RE.finditer(command):
        skill = match.group(1).lower()
        if not skill or skill in seen:
            continue
        seen.add(skill)
        events.append(
            {
                "ts": ts or _now_iso(),
                "skill": skill,
                "event": "read",
                "session_id": session_id,
                "path": match.group(0),
                "line_key": f"{line_key}:{skill}",
            }
        )

    return events


def _parse_claude_line(line: str, file_path: Path, line_key: str) -> list[dict[str, Any]]:
    if "skill" not in line.lower():
        return []
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return []

    events: list[dict[str, Any]] = []
    ts = _parse_ts(payload.get("timestamp"))
    session_id = file_path.parent.name

    def add(skill: str, path: str = "", event: str = "read") -> None:
        if not skill:
            return
        events.append(
            {
                "ts": ts or _now_iso(),
                "skill": skill.lower(),
                "event": event,
                "session_id": session_id,
                "path": path,
                "line_key": f"{line_key}:{skill}:{event}",
            }
        )

    message = payload.get("message") if isinstance(payload.get("message"), dict) else payload
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") == "Read":
                input_data = block.get("input") or {}
                path = str(input_data.get("file_path") or "")
                if path.lower().endswith("skill.md"):
                    add(skill_name_from_path(path), path, "read")
            text = str(block.get("text") or "")
            if text.startswith("/"):
                add(text.strip().split()[0].lstrip("/"), event="slash")

    tool_name = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") or {}
    if tool_name == "Read" and isinstance(tool_input, dict):
        path = str(tool_input.get("file_path") or "")
        if path.lower().endswith("skill.md"):
            add(skill_name_from_path(path), path, "read")

    command = str(payload.get("command") or payload.get("command_name") or "")
    if command:
        add(command.lstrip("/"), event="slash")

    return events


def collect_grok(state: dict[str, Any]) -> list[dict[str, Any]]:
    roots = [HOME / ".grok" / "sessions"]
    files = _iter_scan_files(state, "updates.jsonl", roots)
    events: list[dict[str, Any]] = []
    for file_path in files:
        events.extend(_scan_file_incremental(file_path, state, _parse_grok_line, "grok", "updates.jsonl"))
    return events


def collect_codex(state: dict[str, Any]) -> list[dict[str, Any]]:
    codex_home = resolve_codex_home()
    if not codex_home:
        return []
    roots = [
        codex_home / "sessions",
        codex_home / "archived_sessions",
    ]
    files = _iter_scan_files(state, "*.jsonl", roots)
    events: list[dict[str, Any]] = []
    for file_path in files:
        if file_path.name == "session_index.jsonl":
            continue
        events.extend(_scan_file_incremental(file_path, state, _parse_codex_line, "codex", "rollout"))
    return events


def collect_claude(state: dict[str, Any]) -> list[dict[str, Any]]:
    roots = [HOME / ".claude" / "projects"]
    files = _iter_scan_files(state, "*.jsonl", roots)
    events: list[dict[str, Any]] = []
    for file_path in files:
        events.extend(_scan_file_incremental(file_path, state, _parse_claude_line, "claude", "transcript"))
    return events


def collect_all() -> dict[str, Any]:
    state = _load_state()
    existing_ids = _load_existing_ids()
    grok_events = collect_grok(state)
    claude_events = collect_claude(state)
    codex_events = collect_codex(state)
    all_events = grok_events + claude_events + codex_events
    added = _append_many(all_events, existing_ids)
    state["last_collect_at"] = _now_iso()
    _save_state(state)
    return {
        "ok": True,
        "added": added,
        "scanned": {
            "grok": len(grok_events),
            "claude": len(claude_events),
            "codex": len(codex_events),
        },
        "last_collect_at": state["last_collect_at"],
        "codex_home": str(resolve_codex_home() or ""),
    }


def load_events() -> list[dict[str, Any]]:
    if not EVENTS_PATH.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in EVENTS_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                events.append(item)
        except json.JSONDecodeError:
            continue
    return events


def aggregate_stats(events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    events = events if events is not None else load_events()
    by_skill: dict[str, dict[str, Any]] = {}
    by_agent: dict[str, int] = defaultdict(int)
    by_day: dict[str, int] = defaultdict(int)
    by_event: dict[str, int] = defaultdict(int)

    for event in events:
        skill = str(event.get("skill") or "").lower()
        agent = str(event.get("agent") or "unknown")
        ts = str(event.get("ts") or "")
        if not skill:
            continue
        day = ts[:10] if len(ts) >= 10 else "unknown"
        by_day[day] += 1
        by_agent[agent] += 1
        by_event[str(event.get("event") or "auto")] += 1

        bucket = by_skill.setdefault(
            skill,
            {
                "skill": skill,
                "count": 0,
                "first_at": ts,
                "last_at": ts,
                "agents": defaultdict(int),
                "events": defaultdict(int),
            },
        )
        bucket["count"] += 1
        if ts and (not bucket["first_at"] or ts < bucket["first_at"]):
            bucket["first_at"] = ts
        if ts and (not bucket["last_at"] or ts > bucket["last_at"]):
            bucket["last_at"] = ts
        bucket["agents"][agent] += 1
        bucket["events"][str(event.get("event") or "auto")] += 1

    skills = []
    for item in by_skill.values():
        skills.append(
            {
                "skill": item["skill"],
                "count": item["count"],
                "first_at": item["first_at"],
                "last_at": item["last_at"],
                "agents": dict(item["agents"]),
                "events": dict(item["events"]),
            }
        )
    skills.sort(key=lambda row: (-row["count"], row["skill"]))

    return {
        "total_events": len(events),
        "unique_skills": len(skills),
        "by_agent": dict(sorted(by_agent.items(), key=lambda item: (-item[1], item[0]))),
        "by_day": dict(sorted(by_day.items())),
        "by_event": dict(by_event),
        "skills": skills,
        "top": skills[:20],
        "cold": [row for row in reversed(skills[-20:])] if skills else [],
        "note": "基于本机可观测事件统计，包含 Grok 会话日志、Codex rollout、Claude 转录与 hooks 记录。自动注入的 skill 可能漏计。",
    }


def build_usage_report() -> dict[str, Any]:
    collect_result = collect_all()
    stats = aggregate_stats()
    from hook_installer import hook_status

    return {
        "collect": collect_result,
        "stats": stats,
        "hooks": hook_status(),
        "events_path": str(EVENTS_PATH),
    }