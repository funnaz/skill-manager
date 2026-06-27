"""Export scan reports."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from constants import GITHUB_URL
from scanner import scan_all


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = "\n".join("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join([head, sep, body])


def build_markdown_report(data: dict[str, Any] | None = None) -> str:
    data = data or scan_all()
    lines = [
        "# Skill Manager Report",
        "",
        f"- Generated: {data['scanned_at']}",
        f"- Home: `{data['home']}`",
        f"- Project: {GITHUB_URL}",
        "",
        "## Summary",
        "",
        f"- Total skills: **{data['totals']['skills']}**",
        f"- Configured agents: **{data['totals']['agents_configured']}**",
        f"- Shared skills: **{data['totals']['shared_skills']}**",
        f"- Disabled: **{data['totals']['disabled']}**",
        "",
        "## Agents",
        "",
        _markdown_table(
            ["Agent", "Installed", "Configured", "Roots"],
            [
                [
                    agent["label"],
                    str(agent["installed"]),
                    "yes" if agent["configured"] else "no",
                    "<br>".join(agent["roots"]) or "-",
                ]
                for agent in data["agents"]
            ],
        ),
        "",
        "## Skills",
        "",
        _markdown_table(
            ["Name", "Category", "Agents", "Deletable", "Path"],
            [
                [
                    skill["name"],
                    skill["category"],
                    ", ".join(skill["agent_labels"]) or "-",
                    "yes" if skill["deletable"] else "no",
                    skill["resolved_path"],
                ]
                for skill in data["skills"]
            ],
        ),
        "",
    ]
    return "\n".join(lines)


def export_report(
    fmt: str = "json",
    output_path: str | None = None,
) -> dict[str, Any]:
    data = scan_all()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    if fmt == "markdown":
        content = build_markdown_report(data)
        suffix = ".md"
    elif fmt == "json":
        content = json.dumps(data, ensure_ascii=False, indent=2)
        suffix = ".json"
    else:
        raise ValueError("format 仅支持 json 或 markdown")

    if output_path:
        path = Path(output_path)
    else:
        path = Path.cwd() / f"skill-report-{timestamp}{suffix}"

    path.write_text(content + ("\n" if fmt == "markdown" else ""), encoding="utf-8")
    return {"ok": True, "format": fmt, "path": str(path.resolve()), "skills": data["totals"]["skills"]}