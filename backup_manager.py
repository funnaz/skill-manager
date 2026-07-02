"""List and restore Skill Manager backups."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from audit_log import append_audit
from diff_util import BACKUP_ROOT
from scanner import scan_all


def _resolve_backup(backup_id: str) -> Path:
    name = Path(backup_id).name
    if not name or name in {".", ".."}:
        raise ValueError("Invalid backup id")
    backup = (BACKUP_ROOT / name).resolve()
    root = BACKUP_ROOT.resolve()
    if root not in backup.parents:
        raise ValueError("Backup must be under the Skill Manager backup directory")
    if not backup.exists() or not backup.is_dir() or not (backup / "SKILL.md").exists():
        raise FileNotFoundError(f"Backup not found or invalid: {name}")
    return backup


def _skill_name_from_backup(backup: Path) -> str:
    parts = backup.name.rsplit("-", 2)
    return parts[0] if len(parts) == 3 else backup.name


def list_backups() -> list[dict[str, Any]]:
    if not BACKUP_ROOT.exists():
        return []
    backups: list[dict[str, Any]] = []
    for child in sorted(BACKUP_ROOT.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not child.is_dir() or not (child / "SKILL.md").exists():
            continue
        stat = child.stat()
        backups.append(
            {
                "id": child.name,
                "name": _skill_name_from_backup(child),
                "path": str(child),
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            }
        )
    return backups


def _find_restore_target(skill_name: str) -> Path | None:
    for skill in scan_all().get("skills", []):
        if skill.get("folder_name") == skill_name or skill.get("name") == skill_name:
            return Path(skill["resolved_path"]).resolve()
    return None


def restore_backup(backup_id: str, target_path: str | None = None) -> dict[str, Any]:
    backup = _resolve_backup(backup_id)
    target = Path(target_path).expanduser().resolve() if target_path else _find_restore_target(_skill_name_from_backup(backup))
    if target is None:
        raise FileNotFoundError("No current skill target found. Pass target_path explicitly.")
    if target.exists() and not (target / "SKILL.md").exists():
        raise FileExistsError(f"Target exists but is not a skill directory: {target}")

    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    safety_backup = None
    if target.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safety_backup = BACKUP_ROOT / f"{target.name}-before-restore-{stamp}"
        shutil.copytree(target, safety_backup)
        shutil.rmtree(target)

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(backup, target)
    result = {
        "ok": True,
        "action": "restore",
        "backup_id": backup.name,
        "restored_to": str(target),
        "safety_backup": str(safety_backup) if safety_backup else None,
    }
    append_audit("restore_backup", backup_id=backup.name, restored_to=str(target), safety_backup=str(safety_backup) if safety_backup else None)
    return result
