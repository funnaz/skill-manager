"""Install, create, and delete local agent skills."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from audit_log import append_audit
from scanner import HOME, _read_frontmatter, read_skill_content, scan_all
from skill_parser import parse_skill_md, slugify_skill_name
from trash_manager import move_to_trash

SKILL_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}[a-z0-9]$|^[a-z]{1,2}$")
PROTECTED_CATEGORIES = {"grok-bundled", "marketplace", "package"}
PROTECTED_NAMES = {"skill-manager"}

SCOPES: dict[str, Path] = {
    "grok": HOME / ".grok" / "skills",
    "agents": HOME / ".agents" / "skills",
    "claude": HOME / ".claude" / "skills",
    "codex": HOME / ".codex" / "skills",
    "cursor": HOME / ".cursor" / "skills",
    "project-grok": Path.cwd() / ".grok" / "skills",
    "project-agents": Path.cwd() / ".agents" / "skills",
}

BRIDGE_ROOTS = (
    HOME / ".claude" / "skills",
    HOME / ".cursor" / "skills",
)

LOCK_PATH = HOME / ".agents" / ".skill-lock.json"
LOCK_FILE_MUTEX = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_skill_name(name: str, *, allow_reserved: bool = False) -> str:
    cleaned = name.strip().lower()
    if not SKILL_NAME_RE.match(cleaned):
        raise ValueError(
            "Skill 名称只能用小写字母、数字和连字符，长度 1-64，且不能以连字符开头或结尾。"
        )
    if cleaned in PROTECTED_NAMES and not allow_reserved:
        raise ValueError(f"名称 `{cleaned}` 为保留名称，请换一个。")
    return cleaned


def _skill_template(name: str, description: str, body: str | None = None) -> str:
    desc = description.strip() or f"Custom skill: {name}"
    content = body.strip() if body else f"# {name}\n\n在此编写 Skill 指令。\n"
    return (
        "---\n"
        f"name: {name}\n"
        f"description: {desc}\n"
        "---\n\n"
        f"{content}\n"
    )


def _load_lock() -> dict[str, Any]:
    if not LOCK_PATH.exists():
        return {"version": 3, "skills": {}, "dismissed": {}}
    try:
        return json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 3, "skills": {}, "dismissed": {}}


def _save_lock(data: dict[str, Any]) -> None:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _update_lock_install(name: str, source: str, source_type: str, source_url: str | None = None) -> None:
    with LOCK_FILE_MUTEX:
        lock = _load_lock()
        skills = lock.setdefault("skills", {})
        now = _now_iso()
        entry = skills.get(name, {})
        entry.update(
            {
                "source": source,
                "sourceType": source_type,
                "installedAt": entry.get("installedAt") or now,
                "updatedAt": now,
            }
        )
        if source_url:
            entry["sourceUrl"] = source_url
        skills[name] = entry
        _save_lock(lock)


def set_skill_source(name: str, source_url: str, source_type: str = "github", skill_path: str | None = None) -> dict[str, Any]:
    skill = find_skill_by_name(name)
    if not skill:
        raise FileNotFoundError(f"未找到 Skill: {name}")
    if source_type not in {"github", "well-known"}:
        raise ValueError("source_type 仅支持 github 或 well-known")
    with LOCK_FILE_MUTEX:
        lock = _load_lock()
        entry = lock.setdefault("skills", {}).setdefault(skill["folder_name"], {})
        entry["source"] = source_url
        entry["sourceType"] = source_type
        entry["sourceUrl"] = source_url
        entry["updatedAt"] = _now_iso()
        if skill_path:
            entry["skillPath"] = skill_path
        _save_lock(lock)
    append_audit("set_source", name=skill["folder_name"], source_url=source_url, source_type=source_type, skill_path=skill_path)
    return {"ok": True, "action": "set_source", "name": skill["folder_name"], "source_url": source_url, "source_type": source_type}


def _update_lock_delete(name: str) -> None:
    with LOCK_FILE_MUTEX:
        lock = _load_lock()
        skills = lock.get("skills", {})
        if name in skills:
            del skills[name]
            _save_lock(lock)


def _find_junctions(target_dir: Path) -> list[Path]:
    resolved = str(target_dir.resolve()).lower()
    hits: list[Path] = []
    for root in BRIDGE_ROOTS:
        if not root.exists():
            continue
        for child in root.iterdir():
            try:
                if child.is_symlink() or (hasattr(child, "is_junction") and _is_windows_junction(child)):
                    if str(child.resolve()).lower() == resolved:
                        hits.append(child)
            except OSError:
                continue
    return hits


def _is_windows_junction(path: Path) -> bool:
    import os
    import stat

    if os.name != "nt":
        return False
    try:
        return path.is_dir() and bool(path.lstat().st_mode & stat.S_IFLNK)
    except OSError:
        return False


def _remove_bridge_links(target_dir: Path) -> list[str]:
    removed: list[str] = []
    for link in _find_junctions(target_dir):
        if link.is_symlink():
            link.unlink()
        else:
            link.rmdir()
        removed.append(str(link))
    return removed


def _copy_skill_dir(src: Path, dest: Path) -> None:
    if dest.exists():
        raise FileExistsError(f"目标目录已存在: {dest}")
    shutil.copytree(src, dest)


def _resolve_scope(scope: str) -> Path:
    if scope not in SCOPES:
        raise ValueError(f"未知 scope: {scope}，可选: {', '.join(SCOPES)}")
    return SCOPES[scope]


def find_skill_by_name(name: str) -> dict[str, Any] | None:
    data = scan_all()
    for skill in data["skills"]:
        if skill["folder_name"] == name or skill["name"] == name:
            return skill
    return None


def search_skills(query: str, limit: int = 10) -> list[dict[str, Any]]:
    q = query.strip().lower()
    if not q:
        return []
    scored: list[tuple[int, dict[str, Any]]] = []
    for skill in scan_all().get("skills", []):
        haystack = " ".join(
            str(skill.get(key) or "")
            for key in ("name", "folder_name", "description", "category", "resolved_path")
        ).lower()
        score = 0
        if skill.get("folder_name") == q or skill.get("name") == q:
            score += 100
        if q in haystack:
            score += 30
        for token in q.split():
            if token in haystack:
                score += 10
        if score:
            scored.append((score, skill))
    scored.sort(key=lambda item: (-item[0], item[1].get("name", "")))
    return [skill for _, skill in scored[:limit]]


def fork_skill(source_name: str, new_name: str, scope: str = "agents", description: str | None = None) -> dict[str, Any]:
    source = find_skill_by_name(source_name)
    if not source:
        matches = search_skills(source_name, limit=1)
        source = matches[0] if matches else None
    if not source:
        raise FileNotFoundError(f"未找到 Skill: {source_name}")
    result = install_skill(
        name=validate_skill_name(new_name),
        scope=scope,
        source_path=source["resolved_path"],
        description=description,
    )
    append_audit("fork", source=source["folder_name"], name=result["name"], scope=scope, path=result["path"])
    return {"ok": True, "action": "fork", "source": source["folder_name"], "result": result}


def can_delete(skill: dict[str, Any]) -> tuple[bool, str]:
    if skill["category"] in PROTECTED_CATEGORIES:
        return False, f"受保护分类 `{skill['category']}` 不可删除"
    if skill["folder_name"] in PROTECTED_NAMES or skill["name"] in PROTECTED_NAMES:
        return False, "skill-manager 自身不可删除"
    if skill["category"] == "grok-bundled":
        return False, "Grok 内置 Skill 不可删除"
    return True, ""


def _resolve_skill_name_from_input(raw: str | None, fallback: str) -> str:
    cleaned = (raw or "").strip()
    if cleaned:
        slug = slugify_skill_name(cleaned)
        if slug:
            try:
                return validate_skill_name(slug)
            except ValueError:
                pass
    return validate_skill_name(fallback)


def create_skill(
    name: str | None = None,
    description: str | None = None,
    scope: str = "agents",
    body: str | None = None,
    skill_md: str | None = None,
) -> dict[str, Any]:
    if skill_md:
        parsed = parse_skill_md(skill_md)
        skill_name = _resolve_skill_name_from_input(name, parsed["name"])
        final_desc = (description or parsed["description"]).strip()
        content = parsed["skill_md"]
        meta, body_text = _read_frontmatter(content)
        meta["name"] = skill_name
        meta["description"] = final_desc
        content = _render_skill_md(meta, body_text)
        analysis = {
            "name_source": parsed["name_source"],
            "description_source": parsed["description_source"],
            "analysis_notes": parsed["analysis_notes"],
            "triggers": parsed["triggers"],
        }
    else:
        if not name or not description:
            raise ValueError("未提供 Markdown 时，name 和 description 必填")
        skill_name = validate_skill_name(name)
        final_desc = description.strip()
        content = _skill_template(skill_name, final_desc, body)
        analysis = None

    dest_root = _resolve_scope(scope)
    dest = dest_root / skill_name
    dest_root.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise FileExistsError(f"Skill 已存在: {dest}")

    dest.mkdir(parents=True)
    (dest / "SKILL.md").write_text(content, encoding="utf-8")

    if scope in {"agents", "project-agents"}:
        _update_lock_install(skill_name, "local", "manual")
    append_audit("create", name=skill_name, scope=scope, path=str(dest))

    result = {
        "ok": True,
        "action": "create",
        "name": skill_name,
        "description": final_desc,
        "scope": scope,
        "path": str(dest),
    }
    if analysis:
        result["analysis"] = analysis
    return result


def _render_skill_md(meta: dict[str, Any], body: str) -> str:
    body_yaml = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    body_text = body.strip()
    rendered = f"---\n{body_yaml}\n---\n\n"
    if body_text:
        rendered += f"{body_text}\n"
    return rendered


def install_skill(
    name: str | None,
    scope: str = "agents",
    source_path: str | None = None,
    git_url: str | None = None,
    skill_subpath: str | None = None,
    description: str | None = None,
    overwrite: bool = False,
    allow_reserved_name: bool = False,
) -> dict[str, Any]:
    dest_root = _resolve_scope(scope)
    dest_root.mkdir(parents=True, exist_ok=True)

    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    try:
        if git_url:
            temp_dir = tempfile.TemporaryDirectory(prefix="skill-manager-")
            clone_root = Path(temp_dir.name)
            subprocess.run(
                ["git", "clone", "--depth", "1", git_url, str(clone_root / "repo")],
                check=True,
                capture_output=True,
                text=True,
            )
            src_root = clone_root / "repo"
            if skill_subpath:
                src = src_root / skill_subpath
            else:
                src = _detect_skill_dir(src_root)
        elif source_path:
            src = Path(source_path).expanduser().resolve()
            if src.is_file() and src.name == "SKILL.md":
                src = src.parent
        else:
            raise ValueError("必须提供 source_path 或 git_url")

        if not src.exists() or not (src / "SKILL.md").exists():
            raise FileNotFoundError(f"未找到有效 Skill 目录（需要 SKILL.md）: {src}")

        meta = read_skill_content(str(src))["meta"]
        skill_name = validate_skill_name(name or str(meta.get("name") or src.name), allow_reserved=allow_reserved_name)
        dest = dest_root / skill_name
        if dest.exists():
            if not overwrite:
                raise FileExistsError(f"Skill 已存在: {dest}")
            shutil.rmtree(dest)

        _copy_skill_dir(src, dest)

        if description:
            text = (dest / "SKILL.md").read_text(encoding="utf-8")
            if text.startswith("---"):
                match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.DOTALL)
                if match:
                    payload = yaml.safe_load(match.group(1)) or {}
                    payload["description"] = description.strip()
                    new_front = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False).strip()
                    body = text[match.end():]
                    (dest / "SKILL.md").write_text(f"---\n{new_front}\n---\n{body}", encoding="utf-8")

        source_type = "github" if git_url else "local"
        source_label = git_url or str(src)
        if scope in {"agents", "project-agents"}:
            _update_lock_install(skill_name, source_label, source_type, git_url)
        append_audit("install", name=skill_name, scope=scope, path=str(dest), source=source_label)

        return {
            "ok": True,
            "action": "install",
            "name": skill_name,
            "scope": scope,
            "path": str(dest),
            "source": source_label,
        }
    finally:
        if temp_dir:
            temp_dir.cleanup()


def _detect_skill_dir(repo_root: Path) -> Path:
    direct = repo_root / "SKILL.md"
    if direct.exists():
        return repo_root
    matches = sorted(repo_root.rglob("SKILL.md"))
    if not matches:
        raise FileNotFoundError(f"仓库中未找到 SKILL.md: {repo_root}")
    if len(matches) == 1:
        return matches[0].parent
    for match in matches:
        if match.parent.name == repo_root.name:
            return match.parent
    return matches[0].parent


def delete_skill(
    name: str | None = None,
    resolved_path: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    skill = None
    if resolved_path:
        folder = Path(resolved_path).resolve()
        data = scan_all()
        for item in data["skills"]:
            if Path(item["resolved_path"]).resolve() == folder:
                skill = item
                break
        if not skill:
            raise FileNotFoundError(f"未在扫描结果中找到: {resolved_path}")
    elif name:
        skill = find_skill_by_name(name)
        if not skill:
            raise FileNotFoundError(f"未找到 Skill: {name}")
    else:
        raise ValueError("必须提供 name 或 resolved_path")

    allowed, reason = can_delete(skill)
    if not allowed and not force:
        raise PermissionError(reason)

    target = Path(skill["resolved_path"]).resolve()
    if not target.exists():
        raise FileNotFoundError(f"目录不存在: {target}")

    if dry_run:
        return {
            "ok": True,
            "action": "delete",
            "dry_run": True,
            "name": skill["name"],
            "folder_name": skill["folder_name"],
            "path": str(target),
            "would_remove_bridges": [str(path) for path in _find_junctions(target)],
        }

    removed_bridges = _remove_bridge_links(target)
    trash_item = None
    if force:
        shutil.rmtree(target)
    else:
        trash_item = move_to_trash(target, skill["folder_name"])

    if skill["category"] == "agents-shared" or str(target).replace("\\", "/").endswith("/.agents/skills/" + skill["folder_name"]):
        _update_lock_delete(skill["folder_name"])
    append_audit(
        "delete",
        name=skill["folder_name"],
        path=str(target),
        force=force,
        trash_id=trash_item["id"] if trash_item else None,
    )

    return {
        "ok": True,
        "action": "delete",
        "dry_run": False,
        "name": skill["name"],
        "folder_name": skill["folder_name"],
        "path": str(target),
        "removed_bridges": removed_bridges,
        "trash": trash_item,
    }


def batch_delete(
    names: list[str] | None = None,
    resolved_paths: list[str] | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    targets: list[dict[str, Any]] = []
    if names:
        for name in names:
            skill = find_skill_by_name(name)
            if not skill:
                raise FileNotFoundError(f"未找到 Skill: {name}")
            targets.append(skill)
    if resolved_paths:
        data = scan_all()
        for path in resolved_paths:
            folder = Path(path).resolve()
            skill = next(
                (item for item in data["skills"] if Path(item["resolved_path"]).resolve() == folder),
                None,
            )
            if not skill:
                raise FileNotFoundError(f"未在扫描结果中找到: {path}")
            targets.append(skill)

    if not targets:
        raise ValueError("必须提供 names 或 resolved_paths")

    seen: set[str] = set()
    deleted: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []

    for skill in targets:
        key = skill["resolved_path"].lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            deleted.append(
                delete_skill(resolved_path=skill["resolved_path"], force=force, dry_run=dry_run)
            )
        except Exception as exc:  # noqa: BLE001
            failed.append({"name": skill["name"], "error": str(exc)})

    return {
        "ok": not failed,
        "action": "batch_delete",
        "dry_run": dry_run,
        "deleted_count": len(deleted),
        "failed_count": len(failed),
        "deleted": deleted,
        "failed": failed,
    }
