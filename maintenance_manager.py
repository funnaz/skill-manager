"""Usage-driven cleanup plans and guarded execution."""

from __future__ import annotations

from typing import Any

from audit_log import append_audit
from manager import delete_skill
from scanner import scan_all
from usage_insights import build_usage_insights


def cleanup_plan(refresh: bool = False) -> dict[str, Any]:
    data = scan_all()
    insights = build_usage_insights(data, refresh=refresh, lang="zh")
    candidates = [
        row for row in insights.get("delete_candidates", [])
        if row.get("deletable") and row.get("folder_name")
    ]
    return {
        "ok": True,
        "action": "cleanup_plan",
        "count": len(candidates),
        "candidates": candidates,
        "note": "执行清理会移入回收站，不会永久删除。使用统计可能漏计，请先人工确认。",
    }


def auto_cleanup(names: list[str] | None = None, yes: bool = False, refresh: bool = False) -> dict[str, Any]:
    plan = cleanup_plan(refresh=refresh)
    candidate_names = [row["folder_name"] for row in plan["candidates"]]
    targets = names or candidate_names
    if not yes:
        return {
            "ok": False,
            "requires_confirmation": True,
            "action": "auto_cleanup",
            "targets": targets,
            "hint": "Run again with --yes to move these skills to trash.",
        }
    results = []
    for name in targets:
        if name not in candidate_names and names is None:
            continue
        try:
            results.append(delete_skill(name=name))
        except Exception as exc:  # noqa: BLE001
            results.append({"ok": False, "name": name, "error": str(exc)})
    append_audit("auto_cleanup", targets=targets, count=len(results))
    return {"ok": all(item.get("ok") for item in results), "action": "auto_cleanup", "results": results}
