"""Built-in lightweight templates for creating new skills."""

from __future__ import annotations

from typing import Any

from manager import create_skill

TEMPLATES: dict[str, dict[str, str]] = {
    "code-review": {
        "name": "code-review",
        "title": "Code Review Skill",
        "description": "Review code changes for bugs, regressions, missing tests, and maintainability risks.",
        "body": """# Code Review Skill

## When To Use

Use when the user asks for a code review, PR review, or risk assessment of code changes.

## Workflow

1. Inspect the changed files.
2. Prioritize bugs, regressions, and missing tests.
3. Report findings first with file and line references.
4. Keep summary brief.

## Output

Findings first, then open questions, then a short summary.
""",
    },
    "doc-generator": {
        "name": "doc-generator",
        "title": "Documentation Generator Skill",
        "description": "Create concise user-facing or developer-facing documentation from source notes or code.",
        "body": """# Documentation Generator Skill

## When To Use

Use when the user wants README sections, usage docs, API docs, release notes, or internal guides.

## Workflow

1. Identify the audience.
2. Extract exact behavior from source material.
3. Write task-oriented documentation.
4. Include commands and file paths when useful.
""",
    },
    "workflow-automation": {
        "name": "workflow-automation",
        "title": "Workflow Automation Skill",
        "description": "Turn repeated local workflows into clear step-by-step automation instructions.",
        "body": """# Workflow Automation Skill

## When To Use

Use when the user repeats a manual workflow and wants a reusable agent procedure.

## Workflow

1. Capture trigger conditions.
2. List required inputs and tools.
3. Define exact steps and verification.
4. Add failure handling and rollback notes.
""",
    },
}


def list_templates() -> list[dict[str, str]]:
    return [{"id": key, **value} for key, value in sorted(TEMPLATES.items())]


def create_from_template(template_id: str, name: str | None = None, scope: str = "agents") -> dict[str, Any]:
    template = TEMPLATES.get(template_id)
    if not template:
        raise FileNotFoundError(f"Template not found: {template_id}")
    return create_skill(
        name=name or template["name"],
        description=template["description"],
        scope=scope,
        body=template["body"],
    )
