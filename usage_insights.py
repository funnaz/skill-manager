"""Turn local usage events into report-ready buckets and maintenance advice."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from usage_collector import aggregate_stats, collect_all, load_events

PROTECTED_CATEGORIES = {"grok-bundled", "marketplace", "package"}
STALE_DAYS = 30
DORMANT_DAYS = 14


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        if text.endswith("Z"):
            return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
        return datetime.fromisoformat(text).astimezone(timezone.utc)
    except ValueError:
        return None


def _skill_keys(skill: dict[str, Any]) -> set[str]:
    keys = {
        str(skill.get("name") or "").lower(),
        str(skill.get("folder_name") or "").lower(),
        str(skill.get("id") or "").lower(),
    }
    return {key for key in keys if key}


def _count_in_window(events: list[dict[str, Any]], skill_key: str, days: int, now: datetime) -> int:
    cutoff = now - timedelta(days=days)
    total = 0
    for event in events:
        if str(event.get("skill") or "").lower() != skill_key:
            continue
        ts = _parse_ts(str(event.get("ts") or ""))
        if ts and ts >= cutoff:
            total += 1
    return total


def _merge_usage_for_skill(skill: dict[str, Any], events: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    keys = _skill_keys(skill)
    matched_events = [event for event in events if str(event.get("skill") or "").lower() in keys]
    usage_key = ""
    if matched_events:
        usage_key = str(matched_events[0].get("skill") or "").lower()

    count_total = len(matched_events)
    count_7d = sum(1 for event in matched_events if (_parse_ts(str(event.get("ts") or "")) or datetime.min.replace(tzinfo=timezone.utc)) >= now - timedelta(days=7))
    count_14d = sum(1 for event in matched_events if (_parse_ts(str(event.get("ts") or "")) or datetime.min.replace(tzinfo=timezone.utc)) >= now - timedelta(days=14))

    first_at = ""
    last_at = ""
    agents: dict[str, int] = {}
    for event in matched_events:
        ts = str(event.get("ts") or "")
        if ts and (not first_at or ts < first_at):
            first_at = ts
        if ts and (not last_at or ts > last_at):
            last_at = ts
        agent = str(event.get("agent") or "unknown")
        agents[agent] = agents.get(agent, 0) + 1

    last_dt = _parse_ts(last_at)
    days_since_last = (now - last_dt).days if last_dt else None

    return {
        "usage_key": usage_key,
        "count_total": count_total,
        "count_7d": count_7d,
        "count_14d": count_14d,
        "first_at": first_at,
        "last_at": last_at,
        "days_since_last": days_since_last,
        "agents": agents,
    }


def _recommendation(skill: dict[str, Any], usage: dict[str, Any], lang: str) -> str | None:
    category = skill.get("category") or ""
    deletable = bool(skill.get("deletable"))
    has_update = bool(skill.get("has_update"))
    count_total = usage["count_total"]
    count_7d = usage["count_7d"]
    count_14d = usage["count_14d"]
    days_since = usage["days_since_last"]

    if category in PROTECTED_CATEGORIES:
        if has_update and lang == "zh":
            return "官方有更新，建议整合升级（受保护，勿删除）"
        if has_update:
            return "Update available; merge upgrade recommended (protected, do not delete)"
        return None

    if has_update:
        return "有官方更新，优先整合升级" if lang == "zh" else "Official update available; merge upgrade first"

    if count_total == 0:
        if deletable:
            return "从未记录使用，建议评估后删除" if lang == "zh" else "No recorded usage; consider deleting"
        return "从未记录使用，但受保护或不宜删除" if lang == "zh" else "No recorded usage; protected or keep"

    if 1 <= count_total <= 3 and (days_since is None or days_since >= DORMANT_DAYS):
        if deletable:
            return "仅用过 1-3 次且已久未用，建议删除" if lang == "zh" else "Used only 1-3 times and dormant; consider deleting"
        return "使用很少，建议观察或禁用" if lang == "zh" else "Low usage; observe or disable"

    if count_total > 0 and days_since is not None and days_since >= STALE_DAYS:
        if deletable:
            return f"已 {days_since} 天未用，旧 skill，建议归档或删除" if lang == "zh" else f"Unused for {days_since} days; archive or delete"
        return f"已 {days_since} 天未用，建议检查是否仍需要" if lang == "zh" else f"Unused for {days_since} days; review necessity"

    if count_7d >= 5:
        return "近 7 天高频使用，建议保留并纳入核心清单" if lang == "zh" else "High activity in 7 days; keep as core skill"

    if count_14d > 0:
        return "近 2 周仍在使用，建议保留" if lang == "zh" else "Active within 14 days; keep"

    return "使用偏低，暂可保留观察" if lang == "zh" else "Low activity; keep for now"


def _primary_bucket(usage: dict[str, Any]) -> str:
    count_total = usage["count_total"]
    count_7d = usage["count_7d"]
    count_14d = usage["count_14d"]
    days_since = usage["days_since_last"]

    if count_total == 0:
        return "never_recorded"
    if count_7d >= 4:
        return "hot_7d"
    if count_7d > 0:
        return "active_7d"
    if count_14d > 0:
        return "active_14d"
    if 1 <= count_total <= 3:
        return "light_use"
    if days_since is not None and days_since >= STALE_DAYS:
        return "stale"
    if days_since is not None and days_since >= DORMANT_DAYS:
        return "dormant"
    return "other"


def build_usage_insights(scan_data: dict[str, Any], refresh: bool = True, lang: str = "zh") -> dict[str, Any]:
    collect_info = collect_all() if refresh else {"last_collect_at": None, "added": 0}
    events = load_events()
    stats = aggregate_stats(events)
    now = datetime.now(timezone.utc)

    rows: list[dict[str, Any]] = []
    for skill in scan_data.get("skills", []):
        usage = _merge_usage_for_skill(skill, events, now)
        bucket = _primary_bucket(usage)
        recommendation = _recommendation(skill, usage, lang)
        rows.append(
            {
                "name": skill.get("name") or skill.get("folder_name"),
                "folder_name": skill.get("folder_name"),
                "category": skill.get("category"),
                "deletable": skill.get("deletable"),
                "has_update": skill.get("has_update"),
                "path": skill.get("resolved_path"),
                "bucket": bucket,
                "count_7d": usage["count_7d"],
                "count_14d": usage["count_14d"],
                "count_total": usage["count_total"],
                "last_at": usage["last_at"],
                "first_at": usage["first_at"],
                "days_since_last": usage["days_since_last"],
                "agents": usage["agents"],
                "recommendation": recommendation,
            }
        )

    buckets: dict[str, list[dict[str, Any]]] = {
        "hot_7d": [],
        "active_7d": [],
        "active_14d": [],
        "light_use": [],
        "dormant": [],
        "stale": [],
        "never_recorded": [],
        "other": [],
    }
    for row in rows:
        buckets[row["bucket"]].append(row)

    for key in buckets:
        buckets[key].sort(key=lambda item: (-item["count_7d"], -item["count_total"], item["name"] or ""))

    delete_candidates = [
        row for row in rows
        if row.get("recommendation") and ("删除" in row["recommendation"] or "delete" in row["recommendation"].lower())
        and row.get("deletable")
    ]
    update_candidates = [row for row in rows if row.get("has_update")]
    keep_core = [row for row in rows if row["bucket"] in {"hot_7d", "active_7d"}]

    labels = _bucket_labels(lang)
    summary = {
        "total_installed": len(rows),
        "with_usage": sum(1 for row in rows if row["count_total"] > 0),
        "never_recorded": len(buckets["never_recorded"]),
        "hot_7d": len(buckets["hot_7d"]),
        "active_7d": len(buckets["active_7d"]),
        "active_14d": len(buckets["active_14d"]),
        "light_use": len(buckets["light_use"]),
        "dormant": len(buckets["dormant"]),
        "stale": len(buckets["stale"]),
        "delete_candidates": len(delete_candidates),
        "update_candidates": len(update_candidates),
    }

    return {
        "collect": collect_info,
        "stats": stats,
        "summary": summary,
        "buckets": buckets,
        "bucket_labels": labels,
        "rows": rows,
        "delete_candidates": delete_candidates,
        "update_candidates": update_candidates,
        "keep_core": keep_core,
        "note": stats.get("note"),
    }


def _bucket_labels(lang: str) -> dict[str, str]:
    if lang == "zh":
        return {
            "hot_7d": "近 7 天高频（≥4 次）",
            "active_7d": "近 7 天有使用（1-3 次）",
            "active_14d": "近 2 周有使用（7 天内未用）",
            "light_use": "仅用过 1-3 次",
            "dormant": "14-29 天未用",
            "stale": "30 天及以上未用（旧 skill）",
            "never_recorded": "从未记录使用",
            "other": "其他",
        }
    return {
        "hot_7d": "High frequency in 7 days (≥4)",
        "active_7d": "Used in 7 days (1-3 times)",
        "active_14d": "Used in 14 days (not in last 7)",
        "light_use": "Only used 1-3 times total",
        "dormant": "Dormant 14-29 days",
        "stale": "Stale 30+ days",
        "never_recorded": "Never recorded",
        "other": "Other",
    }


def build_usage_analysis_sections(lang: str, scan_data: dict[str, Any], insights: dict[str, Any]) -> list[dict[str, Any]]:
    summary = insights["summary"]
    labels = insights["bucket_labels"]
    note = insights.get("note") or ""

    def row_line(row: dict[str, Any]) -> str:
        agents = " · ".join(f"{k}:{v}" for k, v in (row.get("agents") or {}).items()) or "-"
        last = (row.get("last_at") or "-")[:10]
        if lang == "zh":
            return (
                f"- **{row['name']}**：7天 {row['count_7d']} 次 / 14天 {row['count_14d']} 次 / 累计 {row['count_total']} 次；"
                f"最近 {last}；平台 {agents}"
            )
        return (
            f"- **{row['name']}**: 7d {row['count_7d']} / 14d {row['count_14d']} / total {row['count_total']}; "
            f"last {last}; agents {agents}"
        )

    if lang == "zh":
        intro = [
            f"本机共 **{summary['total_installed']}** 个已安装 Skill，其中 **{summary['with_usage']}** 个有使用记录，"
            f"**{summary['never_recorded']}** 个从未记录使用。",
            note,
            f"近 7 天高频 **{summary['hot_7d']}** 个，近 7 天有使用 **{summary['active_7d']}** 个，"
            f"近 2 周有使用 **{summary['active_14d']}** 个，仅用过 1-3 次 **{summary['light_use']}** 个。",
        ]
        sections = [{"title": "使用记录解读", "paragraphs": intro}]
    else:
        intro = [
            f"**{summary['total_installed']}** installed skills; **{summary['with_usage']}** have usage records; "
            f"**{summary['never_recorded']}** never recorded.",
            note,
            f"High-frequency (7d): **{summary['hot_7d']}**; active in 7d: **{summary['active_7d']}**; "
            f"active in 14d: **{summary['active_14d']}**; light use (1-3 total): **{summary['light_use']}**.",
        ]
        sections = [{"title": "Usage Insights", "paragraphs": intro}]

    bucket_order = ["hot_7d", "active_7d", "active_14d", "light_use", "dormant", "stale", "never_recorded"]
    for key in bucket_order:
        items = insights["buckets"].get(key) or []
        if not items:
            continue
        title = labels[key]
        if lang == "zh":
            title = f"分类：{title}（{len(items)} 个）"
        else:
            title = f"Bucket: {title} ({len(items)})"
        sections.append({"title": title, "paragraphs": [row_line(row) for row in items[:25]]})
        if len(items) > 25:
            extra = f"…另有 {len(items) - 25} 个未列出" if lang == "zh" else f"…and {len(items) - 25} more"
            sections[-1]["paragraphs"].append(extra)

    action_lines: list[str] = []
    if lang == "zh":
        action_lines.append(f"**建议优先更新（{len(insights['update_candidates'])} 个）**")
        for row in insights["update_candidates"][:15]:
            action_lines.append(f"- {row['name']}：{row.get('recommendation') or '有官方更新'}")
        if not insights["update_candidates"]:
            action_lines.append("- 当前无待更新 skill。")

        action_lines.append(f"**建议评估删除（{len(insights['delete_candidates'])} 个）**")
        for row in insights["delete_candidates"][:15]:
            action_lines.append(f"- {row['name']}（{row['category']}）：{row.get('recommendation')}")
        if not insights["delete_candidates"]:
            action_lines.append("- 暂无明确可删项；请结合业务再判断。")

        action_lines.append(f"**建议保留为核心（{len(insights['keep_core'])} 个）**")
        for row in insights["keep_core"][:10]:
            action_lines.append(f"- {row['name']}：7天 {row['count_7d']} 次")
        if not insights["keep_core"]:
            action_lines.append("- 近 7 天暂无高频 skill。")
    else:
        action_lines.append(f"**Update first ({len(insights['update_candidates'])})**")
        for row in insights["update_candidates"][:15]:
            action_lines.append(f"- {row['name']}: {row.get('recommendation') or 'update available'}")
        if not insights["update_candidates"]:
            action_lines.append("- No pending updates.")

        action_lines.append(f"**Review for deletion ({len(insights['delete_candidates'])})**")
        for row in insights["delete_candidates"][:15]:
            action_lines.append(f"- {row['name']} ({row['category']}): {row.get('recommendation')}")
        if not insights["delete_candidates"]:
            action_lines.append("- No clear delete candidates.")

        action_lines.append(f"**Keep as core ({len(insights['keep_core'])})**")
        for row in insights["keep_core"][:10]:
            action_lines.append(f"- {row['name']}: {row['count_7d']} in 7d")
        if not insights["keep_core"]:
            action_lines.append("- No high-frequency skills in the last 7 days.")

    sections.append(
        {
            "title": "使用驱动的维护建议" if lang == "zh" else "Usage-driven Maintenance",
            "paragraphs": action_lines,
        }
    )
    return sections


def usage_table_rows(lang: str, insights: dict[str, Any]) -> list[list[str]]:
    if lang == "zh":
        headers = ["名称", "7天", "14天", "累计", "最近使用", "分类", "建议"]
    else:
        headers = ["Name", "7d", "14d", "Total", "Last Used", "Bucket", "Advice"]

    rows: list[list[str]] = []
    for row in sorted(insights["rows"], key=lambda item: (-item["count_7d"], -item["count_total"], item["name"] or "")):
        bucket_label = insights["bucket_labels"].get(row["bucket"], row["bucket"])
        rows.append(
            [
                str(row.get("name") or ""),
                str(row.get("count_7d") or 0),
                str(row.get("count_14d") or 0),
                str(row.get("count_total") or 0),
                (row.get("last_at") or "-")[:10],
                bucket_label,
                str(row.get("recommendation") or "-"),
            ]
        )
    return headers, rows