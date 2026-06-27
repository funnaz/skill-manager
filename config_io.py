"""Read and write Grok config.toml skill settings."""

from __future__ import annotations

import re
from pathlib import Path

from scanner import HOME

CONFIG_PATH = HOME / ".grok" / "config.toml"


def _read_lines() -> list[str]:
    if not CONFIG_PATH.exists():
        return []
    return CONFIG_PATH.read_text(encoding="utf-8").splitlines()


def load_disabled_skills() -> list[str]:
    disabled: list[str] = []
    in_skills = False
    for raw in _read_lines():
        line = raw.strip()
        if line == "[skills]":
            in_skills = True
            continue
        if line.startswith("[") and line.endswith("]"):
            in_skills = False
            continue
        if in_skills and line.startswith("disabled"):
            match = re.search(r"\[(.*)\]", line)
            if match:
                items = re.findall(r'"([^"]+)"|\'([^\']+)\'|([^,\]\s]+)', match.group(1))
                for groups in items:
                    value = next((g for g in groups if g), None)
                    if value:
                        disabled.append(value.strip())
    return disabled


def _write_disabled(disabled: list[str]) -> None:
    lines = _read_lines()
    in_skills = False
    skills_idx = -1
    disabled_idx = -1

    for i, raw in enumerate(lines):
        stripped = raw.strip()
        if stripped == "[skills]":
            in_skills = True
            skills_idx = i
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_skills = False
            continue
        if in_skills and stripped.startswith("disabled"):
            disabled_idx = i

    disabled_line = "disabled = [" + ", ".join(f'"{name}"' for name in sorted(set(disabled))) + "]"

    if skills_idx == -1:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(["[skills]", disabled_line])
    elif disabled_idx == -1:
        lines.insert(skills_idx + 1, disabled_line)
    else:
        lines[disabled_idx] = disabled_line

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def disable_skill(name: str) -> dict:
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("skill 名称不能为空")
    disabled = load_disabled_skills()
    if cleaned not in disabled:
        disabled.append(cleaned)
    _write_disabled(disabled)
    return {"ok": True, "action": "disable", "name": cleaned, "disabled": sorted(set(disabled))}


def enable_skill(name: str) -> dict:
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("skill 名称不能为空")
    disabled = [item for item in load_disabled_skills() if item != cleaned]
    _write_disabled(disabled)
    return {"ok": True, "action": "enable", "name": cleaned, "disabled": disabled}