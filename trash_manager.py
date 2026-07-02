"""Recycle-bin style deletion for local skills."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scanner import HOME

TRASH_ROOT = HOME / ".skill-manager" / "trash"
TRASH_INDEX = TRASH_ROOT / "index.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_index() -> dict[str, Any]:
    if not TRASH_INDEX.exists():
        return {"items": []}
    try:
        data = json.loads(TRASH_INDEX.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"items": []}
    except (json.JSONDecodeError, OSError):
        return {"items": []}


def _save_index(data: dict[str, Any]) -> None:
    TRASH_ROOT.mkdir(parents=True, exist_ok=True)
    TRASH_INDEX.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def move_to_trash(target: Path, name: str) -> dict[str, Any]:
    TRASH_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    trash_id = f"{name}-{stamp}"
    dest = TRASH_ROOT / trash_id
    counter = 1
    while dest.exists():
        counter += 1
        dest = TRASH_ROOT / f"{trash_id}-{counter}"
    shutil.move(str(target), str(dest))
    item = {
        "id": dest.name,
        "name": name,
        "original_path": str(target),
        "trash_path": str(dest),
        "deleted_at": _now_iso(),
    }
    data = _load_index()
    data.setdefault("items", []).append(item)
    _save_index(data)
    return item


def list_trash() -> list[dict[str, Any]]:
    items = _load_index().get("items", [])
    live = [item for item in items if Path(str(item.get("trash_path", ""))).exists()]
    live.sort(key=lambda item: str(item.get("deleted_at", "")), reverse=True)
    return live


def restore_from_trash(trash_id: str, target_path: str | None = None) -> dict[str, Any]:
    data = _load_index()
    item = next((row for row in data.get("items", []) if row.get("id") == trash_id), None)
    if not item:
        raise FileNotFoundError(f"Trash item not found: {trash_id}")
    source = Path(item["trash_path"])
    if not source.exists():
        raise FileNotFoundError(f"Trash path missing: {source}")
    target = Path(target_path or item["original_path"]).expanduser().resolve()
    if target.exists():
        raise FileExistsError(f"Restore target already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    item["restored_at"] = _now_iso()
    item["restored_to"] = str(target)
    _save_index(data)
    return {"ok": True, "action": "trash_restore", "id": trash_id, "restored_to": str(target)}


def purge_trash(trash_id: str | None = None) -> dict[str, Any]:
    data = _load_index()
    removed = 0
    kept = []
    for item in data.get("items", []):
        if trash_id and item.get("id") != trash_id:
            kept.append(item)
            continue
        path = Path(str(item.get("trash_path", "")))
        if path.exists():
            shutil.rmtree(path)
            removed += 1
    data["items"] = kept if trash_id else []
    _save_index(data)
    return {"ok": True, "action": "trash_purge", "removed": removed}
