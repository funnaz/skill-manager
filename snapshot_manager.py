"""Export and compare portable environment snapshots."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from scanner import scan_all


def export_snapshot(output_path: str | None = None) -> dict[str, Any]:
    data = scan_all()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = Path(output_path or f"skill-snapshot-{stamp}.json").resolve()
    snapshot = {
        "format": "skill-manager-snapshot",
        "version": 1,
        "scanned_at": data["scanned_at"],
        "home": data["home"],
        "skills": [
            {
                "name": skill["name"],
                "folder_name": skill["folder_name"],
                "category": skill["category"],
                "source_url": skill.get("source_url"),
                "health": skill.get("health"),
                "triggers": skill.get("triggers"),
            }
            for skill in data["skills"]
        ],
    }
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "action": "snapshot", "path": str(path), "skills": len(snapshot["skills"])}


def diff_snapshot(snapshot_path: str) -> dict[str, Any]:
    current = scan_all()
    old = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    old_names = {skill["folder_name"]: skill for skill in old.get("skills", [])}
    current_names = {skill["folder_name"]: skill for skill in current.get("skills", [])}
    missing_here = sorted(set(old_names) - set(current_names))
    added_here = sorted(set(current_names) - set(old_names))
    common = sorted(set(old_names) & set(current_names))
    source_changed = [
        name for name in common
        if (old_names[name].get("source_url") or "") != (current_names[name].get("source_url") or "")
    ]
    return {
        "ok": True,
        "action": "diff_snapshot",
        "snapshot": snapshot_path,
        "missing_here": missing_here,
        "added_here": added_here,
        "source_changed": source_changed,
    }
