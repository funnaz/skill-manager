"""Scan local SKILL.md files and map them to agent runtimes."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

HOME = Path.home()

PACKAGE_MARKERS = (
    "node_modules",
    "site-packages",
    "npm-cache",
    "runtimes/cua_node",
)

CUSTOM_SCAN_ROOTS = (
    HOME / "Documents",
    HOME / ".bb-browser",
)

AGENT_PROFILES: dict[str, dict[str, Any]] = {
    "grok": {
        "label": "Grok Build",
        "short": "Grok",
        "color": "#111827",
        "scan_roots": [
            HOME / ".grok" / "skills",
            HOME / ".grok" / "bundled" / "skills",
            HOME / ".agents" / "skills",
        ],
        "extra_globs": [HOME / ".grok" / "marketplace-cache"],
    },
    "cursor": {
        "label": "Cursor",
        "short": "Cursor",
        "color": "#5B21B6",
        "scan_roots": [HOME / ".cursor" / "skills"],
    },
    "codex": {
        "label": "OpenAI Codex",
        "short": "Codex",
        "color": "#10A37F",
        "scan_roots": [HOME / ".codex" / "skills", HOME / ".agents" / "skills"],
    },
}

CATEGORY_LABELS = {
    "grok-user": "Grok 用户",
    "grok-bundled": "Grok 内置",
    "agents-shared": "共享 Agents",
    "cursor-native": "Cursor 原生",
    "codex-native": "Codex 原生",
    "marketplace": "Marketplace",
    "custom": "用户自定义",
    "package": "依赖包内置",
}


@dataclass
class SkillRecord:
    id: str
    name: str
    folder_name: str
    description: str
    path: str
    resolved_path: str
    category: str
    agents: list[str] = field(default_factory=list)
    agent_labels: list[str] = field(default_factory=list)
    is_junction: bool = False
    junction_target: str | None = None
    source: str | None = None
    source_type: str | None = None
    source_url: str | None = None
    installed_at: str | None = None
    updated_at: str | None = None
    disabled: bool = False
    body_preview: str = ""
    line_count: int = 0
    modified_at: str | None = None
    deletable: bool = True
    delete_reason: str = ""


def _is_package_path(path: Path) -> bool:
    normalized = str(path).replace("\\", "/").lower()
    return any(marker in normalized for marker in PACKAGE_MARKERS)


def _read_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.DOTALL)
    if not match:
        return {}, text
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    body = text[match.end() :]
    return meta if isinstance(meta, dict) else {}, body


def _first_heading_or_line(body: str, fallback: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
        if stripped:
            return stripped[:160]
    return fallback


def _load_skill_lock() -> dict[str, Any]:
    lock_path = HOME / ".agents" / ".skill-lock.json"
    if not lock_path.exists():
        return {}
    try:
        return json.loads(lock_path.read_text(encoding="utf-8")).get("skills", {})
    except (json.JSONDecodeError, OSError):
        return {}


def _load_disabled_skills() -> set[str]:
    from config_io import load_disabled_skills

    return set(load_disabled_skills())


def _junction_info(path: Path) -> tuple[bool, str | None]:
    if os.name != "nt":
        return False, None
    try:
        import stat

        if not path.is_dir():
            return False, None
        if path.lstat().st_mode & stat.S_IFLNK:
            target = os.readlink(path)
            return True, target
    except OSError:
        return False, None
    return False, None


def _category_for_path(path: Path, resolved: Path, is_junction: bool, in_marketplace: bool) -> str:
    normalized = str(resolved).replace("\\", "/")
    if _is_package_path(path):
        return "package"
    if in_marketplace:
        return "marketplace"
    if "/.grok/bundled/skills/" in normalized:
        return "grok-bundled"
    if "/.grok/skills/" in normalized:
        return "grok-user"
    if "/.agents/skills/" in normalized:
        return "agents-shared"
    if "/.cursor/skills/" in normalized:
        return "cursor-native"
    if "/.codex/skills/" in normalized:
        return "codex-native"
    return "custom"


def _iter_skill_files(root: Path, recursive: bool = True) -> list[Path]:
    if not root.exists():
        return []
    if root.is_file() and root.name == "SKILL.md":
        return [root]
    if not root.is_dir():
        return []
    if recursive:
        return sorted(root.rglob("SKILL.md"))
    skill = root / "SKILL.md"
    return [skill] if skill.exists() else []


def _resolve_real(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


def scan_all() -> dict[str, Any]:
    disabled = _load_disabled_skills()
    lock_data = _load_skill_lock()

    discovered: dict[str, dict[str, Any]] = {}
    agent_hits: dict[str, set[str]] = {key: set() for key in AGENT_PROFILES}

    def register_hit(skill_key: str, agent_key: str) -> None:
        agent_hits[agent_key].add(skill_key)

    def ingest(skill_file: Path, agent_key: str | None, in_marketplace: bool = False) -> None:
        if _is_package_path(skill_file):
            return
        resolved = _resolve_real(skill_file)
        skill_key = str(resolved).lower()

        parent = skill_file.parent
        is_junction, junction_target = _junction_info(parent)
        category = _category_for_path(skill_file, resolved, is_junction, in_marketplace)

        if skill_key not in discovered:
            try:
                text = resolved.read_text(encoding="utf-8")
            except OSError:
                return
            meta, body = _read_frontmatter(text)
            folder_name = parent.name
            name = str(meta.get("name") or folder_name)
            description = str(meta.get("description") or meta.get("metadata", {}).get("short-description", ""))
            description = " ".join(description.split())
            if not description:
                description = _first_heading_or_line(body, folder_name)

            lock = lock_data.get(folder_name) or lock_data.get(name) or {}
            stat = resolved.stat()
            discovered[skill_key] = {
                "id": folder_name,
                "name": name,
                "folder_name": folder_name,
                "description": description,
                "path": str(skill_file.parent),
                "resolved_path": str(resolved.parent),
                "category": category,
                "agents": set(),
                "is_junction": is_junction,
                "junction_target": junction_target,
                "source": lock.get("source"),
                "source_type": lock.get("sourceType"),
                "source_url": lock.get("sourceUrl"),
                "installed_at": lock.get("installedAt"),
                "updated_at": lock.get("updatedAt"),
                "disabled": name in disabled or folder_name in disabled,
                "body_preview": body.strip()[:500],
                "line_count": len(text.splitlines()),
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                "deletable": True,
                "delete_reason": "",
            }

        if agent_key:
            discovered[skill_key]["agents"].add(agent_key)
            register_hit(skill_key, agent_key)

    for agent_key, profile in AGENT_PROFILES.items():
        for root in profile["scan_roots"]:
            for child in sorted(root.iterdir()) if root.exists() and root.is_dir() else []:
                skill = child / "SKILL.md"
                if skill.exists():
                    ingest(skill, agent_key)
            for skill_file in _iter_skill_files(root):
                ingest(skill_file, agent_key)

        for extra in profile.get("extra_globs", []):
            if extra.exists():
                for skill_file in _iter_skill_files(extra):
                    ingest(skill_file, agent_key, in_marketplace=True)

    for root in CUSTOM_SCAN_ROOTS:
        if not root.exists():
            continue
        for skill_file in _iter_skill_files(root):
            if _is_package_path(skill_file):
                continue
            normalized = str(skill_file).replace("\\", "/")
            if any(
                part in normalized
                for part in (
                    "/.grok/",
                    "/.agents/",
                    "/.cursor/",
                    "/.codex/",
                )
            ):
                continue
            ingest(skill_file, None)

    from manager import can_delete

    skills: list[SkillRecord] = []
    for item in discovered.values():
        agents = sorted(item["agents"])
        item["agents"] = agents
        item["agent_labels"] = [AGENT_PROFILES[a]["label"] for a in agents if a in AGENT_PROFILES]
        allowed, reason = can_delete(item)
        item["deletable"] = allowed
        item["delete_reason"] = reason
        skills.append(SkillRecord(**item))

    skills.sort(key=lambda s: (s.category, s.name.lower()))

    agent_summary = []
    for agent_key, profile in AGENT_PROFILES.items():
        roots = [str(p) for p in profile["scan_roots"] if p.exists()]
        agent_summary.append(
            {
                "id": agent_key,
                "label": profile["label"],
                "short": profile["short"],
                "color": profile["color"],
                "installed": len(agent_hits[agent_key]),
                "roots": roots,
                "roots_exist": [str(p) for p in profile["scan_roots"]],
                "configured": any(p.exists() for p in profile["scan_roots"]),
            }
        )

    categories: dict[str, int] = {}
    for skill in skills:
        categories[skill.category] = categories.get(skill.category, 0) + 1

    only_on = {
        agent["id"]: sorted(
            s.name
            for s in skills
            if agent["id"] in s.agents and len(s.agents) == 1
        )
        for agent in agent_summary
    }

    shared = sorted(s.name for s in skills if len(s.agents) > 1)

    from constants import GITHUB_CLONE_URL, GITHUB_URL

    return {
        "scanned_at": datetime.now().isoformat(timespec="seconds"),
        "home": str(HOME),
        "project": {
            "name": "skill-manager",
            "github_url": GITHUB_URL,
            "clone_url": GITHUB_CLONE_URL,
        },
        "totals": {
            "skills": len(skills),
            "agents_configured": sum(1 for a in agent_summary if a["configured"]),
            "shared_skills": len(shared),
            "disabled": sum(1 for s in skills if s.disabled),
        },
        "agents": agent_summary,
        "categories": [
            {"id": key, "label": CATEGORY_LABELS.get(key, key), "count": count}
            for key, count in sorted(categories.items(), key=lambda x: -x[1])
        ],
        "only_on": only_on,
        "shared": shared,
        "skills": [asdict(s) for s in skills],
    }


def read_skill_content(resolved_folder: str) -> dict[str, Any]:
    skill_md = Path(resolved_folder) / "SKILL.md"
    if not skill_md.exists():
        raise FileNotFoundError(skill_md)
    text = skill_md.read_text(encoding="utf-8")
    meta, body = _read_frontmatter(text)
    return {
        "path": str(skill_md),
        "meta": meta,
        "body": body,
        "raw": text,
    }