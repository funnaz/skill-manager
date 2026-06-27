"""Parse pasted Markdown and infer skill name, description, and triggers."""

from __future__ import annotations

import hashlib
import re
from typing import Any

import yaml

from scanner import _first_heading_or_line, _read_frontmatter

SECTION_HINTS = (
    "何时使用",
    "什么时候用",
    "使用场景",
    "触发方式",
    "触发",
    "功能",
    "概述",
    "简介",
    "说明",
    "when to use",
    "when use",
    "triggers",
    "trigger",
    "overview",
    "description",
    "usage",
)
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,62}[a-z0-9]$|^[a-z]{1,2}$")
IDENT_PATTERN = re.compile(r"\b([a-z][a-z0-9-]{2,})\b")
NAME_STOPWORDS = {
    "skill", "skills", "true", "false", "null", "http", "https", "github",
    "docx", "md", "pdf", "yaml", "json", "html", "css", "api", "cli",
}


def _dump_frontmatter(meta: dict[str, Any]) -> str:
    body = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{body}\n---\n\n"


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s-]", " ", text.lower())
    cleaned = re.sub(r"[\s_]+", "-", cleaned.strip())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    if not cleaned:
        return ""
    if not NAME_PATTERN.match(cleaned):
        cleaned = re.sub(r"[^a-z0-9-]", "", cleaned)
        cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    if cleaned and cleaned[0].isdigit():
        cleaned = f"skill-{cleaned}"
    if len(cleaned) > 64:
        cleaned = cleaned[:64].rstrip("-")
    return cleaned


def _extract_section(body: str, hints: tuple[str, ...]) -> str:
    lines = body.splitlines()
    capture: list[str] = []
    active = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            title = stripped.lstrip("#").strip().lower()
            if level <= 2 and any(hint in title for hint in hints):
                active = True
                capture = []
                continue
            if active and level <= 2:
                break
        if active and stripped:
            capture.append(stripped.lstrip("-* ").strip())
        if active and len(" ".join(capture)) > 280:
            break
    text = " ".join(capture)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:320]


def _first_paragraph(body: str) -> str:
    chunks: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            if chunks:
                break
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith(("-", "*", "|", "```")):
            continue
        chunks.append(stripped)
    text = " ".join(chunks)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:280]


def _collect_triggers(body: str) -> list[str]:
    triggers: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith(("-", "*")):
            continue
        item = stripped.lstrip("-* ").strip()
        if 6 <= len(item) <= 120:
            triggers.append(item)
        if len(triggers) >= 4:
            break
    return triggers


def _infer_name(title: str, body: str, meta_name: str | None) -> tuple[str, str]:
    if meta_name:
        slug = _slugify(meta_name)
        if slug and NAME_PATTERN.match(slug):
            return slug, "frontmatter"

    title_slug = _slugify(title)
    if title_slug and NAME_PATTERN.match(title_slug):
        return title_slug, "title"

    for pattern in (
        r"name:\s*['\"]?([a-z][a-z0-9-]{1,62}[a-z0-9])",
        r"/skills/([a-z][a-z0-9-]{1,62}[a-z0-9])",
        r"`([a-z][a-z0-9-]{2,})`",
    ):
        match = re.search(pattern, body, re.IGNORECASE)
        if match:
            slug = _slugify(match.group(1))
            if slug and NAME_PATTERN.match(slug):
                return slug, "content"

    candidates: dict[str, int] = {}
    for token in IDENT_PATTERN.findall(f"{title}\n{body[:2000]}"):
        if token in NAME_STOPWORDS or len(token) < 5:
            continue
        candidates[token] = candidates.get(token, 0) + 1
    if candidates:
        best = sorted(candidates.items(), key=lambda item: (-item[1], -len(item[0])))[0][0]
        if NAME_PATTERN.match(best):
            return best, "keywords"

    if title and not re.search(r"[A-Za-z]", title):
        digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:6]
        return f"skill-{digest}", "title-hash"

    digest = hashlib.sha1(f"{title}{body[:200]}".encode("utf-8")).hexdigest()[:6]
    return f"skill-{digest}", "generated"


def _infer_description(
    body: str,
    title: str,
    meta_desc: str | None,
    short_desc: str | None,
) -> tuple[str, str]:
    if meta_desc:
        text = " ".join(str(meta_desc).split())
        if text:
            return text[:320], "frontmatter"

    if short_desc:
        text = " ".join(str(short_desc).split())
        if text:
            return text[:320], "short-description"

    section = _extract_section(body, SECTION_HINTS)
    if section:
        return section, "section"

    paragraph = _first_paragraph(body)
    if paragraph:
        return paragraph, "paragraph"

    triggers = _collect_triggers(body)
    if triggers:
        joined = "；".join(triggers[:3])
        return f"{title}：{joined}"[:320], "triggers"

    return f"Custom skill: {title}"[:320], "fallback"


def _build_analysis_notes(
    *,
    name_source: str,
    desc_source: str,
    triggers: list[str],
    has_frontmatter: bool,
) -> list[str]:
    notes: list[str] = []
    if has_frontmatter:
        notes.append("检测到 YAML frontmatter，已读取其中的 name / description。")
    notes.append(f"名称来源：{name_source}；描述来源：{desc_source}。")
    if triggers:
        notes.append(f"识别到 {len(triggers)} 条使用场景/触发说明。")
    return notes


def slugify_skill_name(text: str) -> str:
    return _slugify(text)


def parse_skill_md(content: str) -> dict[str, Any]:
    text = content.strip()
    if not text:
        raise ValueError("Markdown 内容不能为空")

    meta, body = _read_frontmatter(text)
    has_frontmatter = bool(meta)
    title = _first_heading_or_line(body, "未命名 Skill")
    if str(meta.get("name") or "").strip():
        title = str(meta.get("name")).strip()

    meta_name = str(meta.get("name") or "").strip() or None
    meta_desc = str(meta.get("description") or "").strip() or None
    short_desc = ""
    metadata = meta.get("metadata")
    if isinstance(metadata, dict):
        short_desc = str(metadata.get("short-description") or "").strip()

    name, name_source = _infer_name(title, body, meta_name)
    description, desc_source = _infer_description(body, title, meta_desc, short_desc or None)
    triggers = _collect_triggers(body)

    final_meta = dict(meta)
    final_meta["name"] = name
    final_meta["description"] = description
    if short_desc and "metadata" not in final_meta:
        final_meta["metadata"] = {"short-description": short_desc[:160]}
    skill_md = _dump_frontmatter(final_meta) + body.strip() + ("\n" if body.strip() else "")

    return {
        "name": name,
        "description": description,
        "title": title,
        "skill_md": skill_md,
        "has_frontmatter": has_frontmatter,
        "name_source": name_source,
        "description_source": desc_source,
        "triggers": triggers,
        "analysis_notes": _build_analysis_notes(
            name_source=name_source,
            desc_source=desc_source,
            triggers=triggers,
            has_frontmatter=has_frontmatter,
        ),
    }