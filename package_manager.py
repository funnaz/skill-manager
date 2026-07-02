"""Import and export portable .skillpkg archives."""

from __future__ import annotations

import json
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from audit_log import append_audit
from manager import install_skill
from scanner import scan_all


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _find_skill(name: str) -> dict[str, Any]:
    for skill in scan_all().get("skills", []):
        if skill.get("folder_name") == name or skill.get("name") == name:
            return skill
    raise FileNotFoundError(f"Skill not found: {name}")


def export_skillpkg(names: list[str], output_path: str | None = None) -> dict[str, Any]:
    if not names:
        raise ValueError("At least one skill name is required")
    skills = [_find_skill(name.strip()) for name in names if name.strip()]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = Path(output_path or f"skills-{stamp}.skillpkg").resolve()
    metadata = {
        "format": "skillpkg",
        "version": 1,
        "created_at": _now_iso(),
        "skills": [
            {
                "name": skill["name"],
                "folder_name": skill["folder_name"],
                "category": skill["category"],
                "source": skill.get("source"),
                "source_type": skill.get("source_type"),
            }
            for skill in skills
        ],
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("skillpkg.json", json.dumps(metadata, ensure_ascii=False, indent=2))
        for skill in skills:
            root = Path(skill["resolved_path"])
            prefix = f"skills/{skill['folder_name']}"
            for file_path in sorted(root.rglob("*")):
                if file_path.is_file():
                    archive.write(file_path, f"{prefix}/{file_path.relative_to(root).as_posix()}")
    append_audit("export_skillpkg", names=[skill["folder_name"] for skill in skills], path=str(path))
    return {"ok": True, "action": "export_skillpkg", "path": str(path), "count": len(skills)}


def import_skillpkg(package_path: str, scope: str = "agents", overwrite: bool = False) -> dict[str, Any]:
    path = Path(package_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    imported: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="skillpkg-") as tmp:
        tmp_root = Path(tmp)
        with zipfile.ZipFile(path) as archive:
            archive.extractall(tmp_root)
        skills_root = tmp_root / "skills"
        if not skills_root.exists():
            raise ValueError("Invalid .skillpkg: missing skills directory")
        for skill_dir in sorted(child for child in skills_root.iterdir() if child.is_dir()):
            if not (skill_dir / "SKILL.md").exists():
                continue
            if overwrite:
                result = install_skill(skill_dir.name, scope=scope, source_path=str(skill_dir), overwrite=True)
            else:
                result = install_skill(skill_dir.name, scope=scope, source_path=str(skill_dir))
            imported.append(result)
    append_audit("import_skillpkg", package=str(path), scope=scope, count=len(imported))
    return {"ok": True, "action": "import_skillpkg", "scope": scope, "count": len(imported), "imported": imported}


def unpack_skillpkg(package_path: str, output_dir: str) -> dict[str, Any]:
    path = Path(package_path).expanduser().resolve()
    dest = Path(output_dir).expanduser().resolve()
    if dest.exists():
        raise FileExistsError(dest)
    dest.mkdir(parents=True)
    with zipfile.ZipFile(path) as archive:
        archive.extractall(dest)
    return {"ok": True, "action": "unpack_skillpkg", "path": str(path), "output_dir": str(dest)}
