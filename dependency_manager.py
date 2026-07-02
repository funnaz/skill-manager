"""Install missing dependencies detected from skill metadata."""

from __future__ import annotations

import subprocess
import sys
from typing import Any

from audit_log import append_audit
from scanner import scan_all


def missing_dependencies(name: str | None = None) -> dict[str, Any]:
    rows = []
    for skill in scan_all().get("skills", []):
        if name and name not in {skill.get("name"), skill.get("folder_name")}:
            continue
        deps = skill.get("dependencies") or {}
        if deps.get("missing_python") or deps.get("missing_env"):
            rows.append(
                {
                    "name": skill.get("name"),
                    "folder_name": skill.get("folder_name"),
                    "missing_python": deps.get("missing_python") or [],
                    "missing_env": deps.get("missing_env") or [],
                }
            )
    return {"ok": True, "items": rows}


def install_missing_python(name: str, yes: bool = False) -> dict[str, Any]:
    info = missing_dependencies(name)
    packages = sorted({pkg for item in info["items"] for pkg in item.get("missing_python", [])})
    if not packages:
        return {"ok": True, "action": "install_deps", "name": name, "installed": []}
    if not yes:
        return {
            "ok": False,
            "action": "install_deps",
            "requires_confirmation": True,
            "packages": packages,
            "hint": "Run again with --yes to install with pip.",
        }
    subprocess.run([sys.executable, "-m", "pip", "install", *packages], check=True)
    append_audit("install_dependencies", name=name, packages=packages)
    return {"ok": True, "action": "install_deps", "name": name, "installed": packages}
