"""Dependency, conflict, and health analysis for SKILL.md files."""

from __future__ import annotations

import importlib.util
import os
import re
from typing import Any


PYTHON_PACKAGE_ALIASES = {
    "pyyaml": "yaml",
    "python-docx": "docx",
    "fpdf2": "fpdf",
    "pillow": "PIL",
}


def _as_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, dict):
        return [str(key).strip() for key in value if str(key).strip()]
    return [part.strip() for part in re.split(r"[,;\n]", str(value)) if part.strip()]


def _normalize_pkg(name: str) -> str:
    cleaned = re.split(r"[<>=!~\[]", name.strip(), maxsplit=1)[0].strip()
    return cleaned


def _extract_inline_dependencies(text: str) -> tuple[list[str], list[str], list[str]]:
    python: set[str] = set()
    node: set[str] = set()
    env: set[str] = set()
    for match in re.finditer(r"pip(?:3)?\s+install\s+([^\n`]+)", text, re.I):
        for part in match.group(1).split():
            if part.startswith("-") or part in {"install", "python", "-m"}:
                continue
            python.add(_normalize_pkg(part))
    for match in re.finditer(r"npm\s+install\s+(?:-g\s+)?([^\n`]+)", text, re.I):
        for part in match.group(1).split():
            if part.startswith("-"):
                continue
            node.add(part.strip())
    for match in re.finditer(r"\b([A-Z][A-Z0-9_]{3,})\b", text):
        token = match.group(1)
        if token.endswith(("_KEY", "_TOKEN", "_SECRET", "_URL", "_ID")):
            env.add(token)
    return sorted(python), sorted(node), sorted(env)


def _extract_triggers(meta: dict[str, Any], body: str) -> list[str]:
    triggers = set(_as_list(meta.get("triggers") or meta.get("commands") or meta.get("command")))
    desc = str(meta.get("description") or "")
    for text in (desc, body[:3000]):
        for match in re.finditer(r"(/[a-zA-Z0-9][a-zA-Z0-9_-]+)", text):
            triggers.add(match.group(1).lower())
        for match in re.finditer(r"触发(?:方式)?[：:]\s*([^\n]+)", text):
            for part in re.split(r"[、,，\s]+", match.group(1)):
                if part.strip():
                    triggers.add(part.strip().lower())
    return sorted(triggers)


def analyze_skill_quality(meta: dict[str, Any], body: str, skill: dict[str, Any] | None = None) -> dict[str, Any]:
    text = f"{meta}\n{body}"
    inline_py, inline_node, inline_env = _extract_inline_dependencies(text)
    python_packages = sorted(set(_as_list(meta.get("requirements") or meta.get("python") or meta.get("python_packages")) + inline_py))
    node_packages = sorted(set(_as_list(meta.get("node") or meta.get("node_packages") or meta.get("npm")) + inline_node))
    env_vars = sorted(set(_as_list(meta.get("env_vars") or meta.get("environment") or meta.get("env")) + inline_env))
    triggers = _extract_triggers(meta, body)

    missing_python = []
    for package in python_packages:
        module = PYTHON_PACKAGE_ALIASES.get(package.lower(), package.replace("-", "_"))
        if importlib.util.find_spec(module) is None:
            missing_python.append(package)
    missing_env = [name for name in env_vars if not os.environ.get(name)]

    score = 100
    issues: list[str] = []
    if not str(meta.get("description") or "").strip():
        score -= 18
        issues.append("缺少 description")
    if not triggers:
        score -= 12
        issues.append("缺少明确 triggers/命令")
    if "example" not in body.lower() and "示例" not in body:
        score -= 8
        issues.append("缺少示例")
    if missing_python:
        score -= min(24, 8 * len(missing_python))
        issues.append(f"缺少 Python 依赖：{', '.join(missing_python)}")
    if missing_env:
        score -= min(18, 6 * len(missing_env))
        issues.append(f"缺少环境变量：{', '.join(missing_env)}")
    if skill and skill.get("has_update"):
        score -= 10
        issues.append("有可用更新")
    if skill and not skill.get("agent_labels"):
        score -= 8
        issues.append("未挂载到任何 Agent")

    score = max(0, min(100, score))
    return {
        "score": score,
        "grade": "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 50 else "D",
        "issues": issues,
        "dependencies": {
            "python": python_packages,
            "node": node_packages,
            "env_vars": env_vars,
            "missing_python": missing_python,
            "missing_env": missing_env,
        },
        "triggers": triggers,
    }


def build_conflicts(skills: list[dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
    index: dict[str, list[dict[str, str]]] = {}
    for skill in skills:
        for trigger in skill.get("triggers", []):
            index.setdefault(trigger, []).append(
                {
                    "name": str(skill.get("name") or ""),
                    "folder_name": str(skill.get("folder_name") or ""),
                    "path": str(skill.get("resolved_path") or ""),
                }
            )
    return {key: value for key, value in index.items() if len(value) > 1}


def annotate_conflicts(skills: list[dict[str, Any]], conflicts: dict[str, list[dict[str, str]]]) -> None:
    conflict_by_folder: dict[str, list[str]] = {}
    for trigger, items in conflicts.items():
        for item in items:
            conflict_by_folder.setdefault(item["folder_name"], []).append(trigger)
    for skill in skills:
        triggers = sorted(set(conflict_by_folder.get(skill.get("folder_name"), [])))
        skill["conflicts"] = triggers
        if triggers:
            skill["health"]["score"] = max(0, int(skill["health"]["score"]) - min(18, len(triggers) * 6))
            skill["health"]["grade"] = (
                "A" if skill["health"]["score"] >= 85 else
                "B" if skill["health"]["score"] >= 70 else
                "C" if skill["health"]["score"] >= 50 else
                "D"
            )
            skill["health"]["issues"].append(f"触发词冲突：{', '.join(triggers[:5])}")
