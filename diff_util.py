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
BUNDLED_PREFIXES = ("references/", "scripts/", "agents/")


def is_bundled_path(rel: str) -> bool:
    return any(rel.startswith(prefix) for prefix in BUNDLED_PREFIXES)


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
    if rel.startswith("references/") or rel.startswith("scripts/") or rel.startswith("agents/"):
        return "official_asset"
    return "custom"


def filter_diff_for_classification(diff: dict[str, Any], *, md_only: bool = False) -> dict[str, Any]:
    """Remove bundled ancillary paths so they never affect update classification."""
    filtered = dict(diff)
    filtered["added_locally"] = [
        path for path in diff.get("added_locally", [])
        if not is_bundled_path(path) and (not md_only or path == "SKILL.md")
    ]
    filtered["missing_locally"] = [
        path for path in diff.get("missing_locally", [])
        if not is_bundled_path(path) and (not md_only or path == "SKILL.md")
    ]
    filtered["modified"] = [
        item for item in diff.get("modified", [])
        if not is_bundled_path(item.get("path", "")) and (not md_only or item.get("path") == "SKILL.md")
    ]
    filtered["has_local_changes"] = bool(filtered["added_locally"] or filtered["modified"])
    filtered["has_remote_changes"] = bool(filtered["missing_locally"] or filtered["modified"])
    filtered["summary"] = _summarize_diff(
        filtered["added_locally"],
        filtered["missing_locally"],
        filtered["modified"],
    )
    return filtered


def analyze_change_nature(
    diff: dict[str, Any],
    *,
    md_only: bool = False,
    locked_hash: str | None = None,
    local_folder_hash: str | None = None,
) -> dict[str, Any]:
    """Distinguish real user edits from outdated install drift."""
    diff = filter_diff_for_classification(diff, md_only=md_only)
    added = list(diff.get("added_locally", []))
    modified = list(diff.get("modified", []))

    custom_added = [path for path in added if _classify_change(path) == "custom"]
    custom_modified = [item for item in modified if _classify_change(item.get("path", "")) == "custom"]
    skill_md_modified = [item for item in modified if item.get("path") == "SKILL.md"]
    official_asset_modified = [
        item for item in modified
        if _classify_change(item.get("path", "")) == "official_asset"
    ]

    user_edited = bool(custom_added or custom_modified)
    if not user_edited and locked_hash and local_folder_hash:
        user_edited = bool(official_asset_modified) and local_folder_hash != locked_hash

    has_remote_changes = bool(diff.get("missing_locally") or modified)
    has_real_local_changes = bool(custom_added or custom_modified or (user_edited and skill_md_modified))

    if user_edited and has_remote_changes:
        change_type = "user_and_official"
        change_label = "你改过，官方也有更新"
    elif user_edited:
        change_type = "user_only"
        change_label = "仅本地功能改动"
    elif has_remote_changes:
        change_type = "official_outdated"
        change_label = "安装版本落后（非用户改动）"
    else:
        change_type = "none"
        change_label = "无实质差异"

    real_local_files = custom_added + [item["path"] for item in custom_modified]
    if user_edited:
        real_local_files += [item["path"] for item in skill_md_modified]

    return {
        "change_type": change_type,
        "change_label": change_label,
        "user_edited": user_edited,
        "has_real_local_changes": has_real_local_changes,
        "has_remote_changes": has_remote_changes,
        "real_local_files": sorted(set(real_local_files)),
        "skill_md_changed": bool(skill_md_modified),
        "official_asset_changed": bool(official_asset_modified),
        "notes": _build_change_notes(
            skill_md_modified=skill_md_modified,
            user_edited=user_edited,
            has_remote_changes=has_remote_changes,
        ),
    }


def _build_change_notes(
    *,
    skill_md_modified: list[dict[str, Any]],
    user_edited: bool,
    has_remote_changes: bool,
) -> list[str]:
    notes: list[str] = []
    if skill_md_modified and not user_edited and has_remote_changes:
        notes.append("仅 SKILL.md 与官方不同，更像是安装版本落后，而不是你改了功能。")
    if not user_edited and has_remote_changes:
        notes.append("建议直接「覆盖升级」或「整合更新」，通常不会丢失你的定制。")
    return notes


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


def merge_folders(
    local_dir: Path,
    remote_dir: Path,
    *,
    md_only: bool = False,
    overwrite_skill_md: bool = False,
) -> dict[str, Any]:
    diff = diff_folders(local_dir, remote_dir)
    if md_only:
        diff = filter_diff_for_classification(diff, md_only=True)

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
        if rel == "SKILL.md" and overwrite_skill_md:
            content = remote_path.read_text(encoding="utf-8")
            strategy = "overwrite_skill_md"
        else:
            content, strategy = _choose_merged_file(rel, local_path, remote_path)
        local_path.write_text(content, encoding="utf-8")
        actions.append({"path": rel, "action": strategy})
        if strategy in {"merged_skill_md", "overwrite_skill_md"}:
            conflicts.append(rel)

    return {
        "ok": True,
        "backup_path": str(backup_dir),
        "diff": diff,
        "actions": actions,
        "merged_files": [item["path"] for item in diff["modified"]],
        "conflicts_resolved": conflicts,
    }