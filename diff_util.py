"""Folder diff and merge helpers for skills."""

from __future__ import annotations

import hashlib
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from scanner import _read_frontmatter

BACKUP_ROOT = Path.home() / ".skill-manager" / "backups"
IGNORE_NAMES = {"__pycache__", ".git", ".DS_Store"}


def _file_digest(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def _list_files(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    if not root.exists():
        return files
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in IGNORE_NAMES for part in path.parts):
            continue
        files[path.relative_to(root).as_posix()] = path
    return files


def _line_count(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8").splitlines())
    except OSError:
        return 0


def diff_folders(local_dir: Path, remote_dir: Path | None) -> dict[str, Any]:
    if remote_dir is None or not remote_dir.exists():
        return {
            "available": False,
            "added_locally": [],
            "missing_locally": [],
            "modified": [],
            "unchanged_count": 0,
            "has_local_changes": False,
            "has_remote_changes": False,
            "summary": "无法获取远程目录进行比对",
        }

    local_files = _list_files(local_dir)
    remote_files = _list_files(remote_dir)

    added_locally = sorted(set(local_files) - set(remote_files))
    missing_locally = sorted(set(remote_files) - set(local_files))
    modified: list[dict[str, Any]] = []
    unchanged = 0

    for rel in sorted(set(local_files) & set(remote_files)):
        local_path = local_files[rel]
        remote_path = remote_files[rel]
        if _file_digest(local_path) == _file_digest(remote_path):
            unchanged += 1
            continue
        modified.append(
            {
                "path": rel,
                "local_lines": _line_count(local_path),
                "remote_lines": _line_count(remote_path),
                "kind": _classify_change(rel),
            }
        )

    return {
        "available": True,
        "added_locally": added_locally,
        "missing_locally": missing_locally,
        "modified": modified,
        "unchanged_count": unchanged,
        "has_local_changes": bool(added_locally or modified),
        "has_remote_changes": bool(missing_locally or modified),
        "summary": _summarize_diff(added_locally, missing_locally, modified),
    }


def _classify_change(rel: str) -> str:
    if rel == "SKILL.md":
        return "skill_md"
    if rel.startswith("references/") or rel.startswith("scripts/"):
        return "official_asset"
    return "custom"


def _summarize_diff(added: list[str], missing: list[str], modified: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    if added:
        parts.append(f"本地新增 {len(added)} 个文件")
    if missing:
        parts.append(f"官方新增 {len(missing)} 个文件")
    if modified:
        parts.append(f"双方修改 {len(modified)} 个文件")
    return "；".join(parts) if parts else "无文件差异"


def _dump_frontmatter(meta: dict[str, Any]) -> str:
    body = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{body}\n---\n\n"


def merge_skill_md(local_text: str, remote_text: str) -> str:
    local_meta, local_body = _read_frontmatter(local_text)
    remote_meta, remote_body = _read_frontmatter(remote_text)
    local_body = local_body.strip()
    remote_body = remote_body.strip()

    if local_body == remote_body:
        return _dump_frontmatter(remote_meta) + remote_body + ("\n" if remote_body else "")

    merged = _dump_frontmatter(remote_meta) + remote_body
    if local_body:
        merged += (
            "\n\n---\n\n"
            "## 本地保留内容\n\n"
            "> 以下内容来自你本地的定制，已在整合更新时保留。\n\n"
            f"{local_body}\n"
        )
    return merged


def _choose_merged_file(rel: str, local_path: Path, remote_path: Path) -> tuple[str, str]:
    kind = _classify_change(rel)
    if kind == "skill_md":
        text = merge_skill_md(
            local_path.read_text(encoding="utf-8"),
            remote_path.read_text(encoding="utf-8"),
        )
        return text, "merged_skill_md"
    if kind == "official_asset":
        return remote_path.read_text(encoding="utf-8"), "prefer_remote"
    return local_path.read_text(encoding="utf-8"), "prefer_local"


def merge_folders(local_dir: Path, remote_dir: Path) -> dict[str, Any]:
    diff = diff_folders(local_dir, remote_dir)
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = BACKUP_ROOT / f"{local_dir.name}-{stamp}"
    shutil.copytree(local_dir, backup_dir)

    actions: list[dict[str, str]] = []
    conflicts: list[str] = []

    for rel in diff["missing_locally"]:
        target = local_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(remote_dir / rel, target)
        actions.append({"path": rel, "action": "added_from_remote"})

    for rel in diff["added_locally"]:
        actions.append({"path": rel, "action": "kept_local_only"})

    for item in diff["modified"]:
        rel = item["path"]
        local_path = local_dir / rel
        remote_path = remote_dir / rel
        content, strategy = _choose_merged_file(rel, local_path, remote_path)
        local_path.write_text(content, encoding="utf-8")
        actions.append({"path": rel, "action": strategy})
        if strategy == "merged_skill_md":
            conflicts.append(rel)

    return {
        "ok": True,
        "backup_path": str(backup_dir),
        "diff": diff,
        "actions": actions,
        "merged_files": [item["path"] for item in diff["modified"]],
        "conflicts_resolved": conflicts,
    }