"""Detect, diff, merge and apply skill updates from remote sources."""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from audit_log import append_audit
from constants import GITHUB_CLONE_URL
from diff_util import analyze_change_nature, diff_folders, filter_diff_for_classification, merge_folders
from manager import LOCK_FILE_MUTEX, _load_lock, _update_lock_install, install_skill
from scanner import _read_frontmatter, scan_all

USER_AGENT = "skill-manager/2.3"
MAX_BATCH_UPGRADE_WORKERS = 8


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_version(value: str | None) -> tuple[int, ...]:
    if not value:
        return ()
    parts = re.findall(r"\d+", str(value))
    return tuple(int(part) for part in parts)


def version_label(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def compute_folder_hash(folder: Path) -> str:
    digest = hashlib.sha1()
    for file_path in sorted(folder.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(folder).as_posix().encode("utf-8")
        digest.update(rel)
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _fetch_text(url: str, timeout: int = 20) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def _local_skill_info(folder: Path) -> dict[str, Any]:
    skill_md = folder / "SKILL.md"
    if not skill_md.exists():
        return {"version": None, "skill_md_hash": None, "folder_hash": compute_folder_hash(folder)}
    text = skill_md.read_text(encoding="utf-8")
    meta, _ = _read_frontmatter(text)
    return {
        "version": version_label(str(meta.get("version") or "")),
        "skill_md_hash": hashlib.sha1(text.encode("utf-8")).hexdigest(),
        "folder_hash": compute_folder_hash(folder),
    }


def _compare_versions(local: str | None, remote: str | None) -> str | None:
    if not remote:
        return None
    if not local:
        return "update_available"
    if parse_version(remote) > parse_version(local):
        return "update_available"
    if parse_version(remote) < parse_version(local):
        return "local_ahead"
    return "same_version"


def _resolve_update_status(
    version_status: str | None,
    local_hash: str,
    remote_hash: str,
    locked_hash: str | None,
    md_only: bool = False,
) -> str:
    if local_hash == remote_hash:
        return "up_to_date"
    if version_status == "update_available":
        return "update_available"
    if version_status == "local_ahead":
        return "local_ahead"
    if locked_hash:
        if remote_hash != locked_hash and local_hash == locked_hash:
            return "update_available"
        if local_hash != locked_hash and remote_hash == locked_hash:
            return "local_modified"
        if local_hash != locked_hash and remote_hash != locked_hash:
            return "content_diff"
    if md_only and local_hash != remote_hash:
        return "update_available"
    return "content_diff"


def _clone_github_repo(git_url: str, cache: dict[str, Path]) -> Path | None:
    if git_url in cache:
        return cache[git_url]
    temp_root = Path(tempfile.mkdtemp(prefix="skill-manager-update-"))
    repo_dir = temp_root / "repo"
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", git_url, str(repo_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
        cache[git_url] = repo_dir
        return repo_dir
    except subprocess.CalledProcessError:
        shutil.rmtree(temp_root, ignore_errors=True)
        return None


def _github_skill_dir(repo_dir: Path, skill_path: str | None, folder_name: str) -> Path | None:
    if skill_path:
        candidate = repo_dir / Path(skill_path).parent
        if (candidate / "SKILL.md").exists():
            return candidate
    direct = repo_dir / folder_name
    if (direct / "SKILL.md").exists():
        return direct
    matches = sorted(repo_dir.rglob("SKILL.md"))
    for match in matches:
        if match.parent.name == folder_name:
            return match.parent
    return matches[0].parent if len(matches) == 1 else None


def _prepare_lock(skill: dict[str, Any], lock: dict[str, Any]) -> dict[str, Any]:
    folder_name = skill["folder_name"]
    if folder_name == "skill-manager" or lock.get("sourceUrl") == GITHUB_CLONE_URL:
        return {
            **lock,
            "sourceType": "github",
            "sourceUrl": GITHUB_CLONE_URL,
            "skillPath": "SKILL.md",
        }
    return lock


def fetch_remote_skill_dir(skill: dict[str, Any], lock: dict[str, Any], repo_cache: dict[str, Path] | None = None) -> tuple[Path | None, dict[str, Any]]:
    lock = _prepare_lock(skill, lock)
    source_type = (lock.get("sourceType") or "").lower()
    cache = repo_cache if repo_cache is not None else {}

    if source_type == "github":
        git_url = lock.get("sourceUrl") or skill.get("source_url")
        if not git_url:
            return None, {"error": "缺少 GitHub 地址"}
        repo_dir = _clone_github_repo(git_url, cache)
        if not repo_dir:
            return None, {"error": "无法拉取 GitHub 仓库"}
        remote_dir = _github_skill_dir(repo_dir, lock.get("skillPath"), skill["folder_name"])
        if not remote_dir:
            return None, {"error": "仓库中未找到 skill 目录"}
        return remote_dir, {"source_type": "github", "remote_url": git_url}

    source_url = lock.get("sourceUrl") or skill.get("source_url")
    if not source_url:
        return None, {"error": "缺少远程地址"}

    temp_root = Path(tempfile.mkdtemp(prefix="skill-manager-wellknown-"))
    remote_dir = temp_root / "remote"
    remote_dir.mkdir(parents=True)
    try:
        remote_text = _fetch_text(source_url)
    except (urllib.error.URLError, TimeoutError) as exc:
        shutil.rmtree(temp_root, ignore_errors=True)
        return None, {"error": f"拉取远程 SKILL.md 失败: {exc}"}
    (remote_dir / "SKILL.md").write_text(remote_text, encoding="utf-8")
    return remote_dir, {"source_type": "well-known", "remote_url": source_url, "temp_root": str(temp_root)}


def _classify_result(info: dict[str, Any]) -> dict[str, Any]:
    nature = info.get("change_nature") or {}
    official_update = bool(info.get("official_update"))
    user_edited = bool(nature.get("user_edited"))
    has_remote = bool(nature.get("has_remote_changes"))
    has_real_local = bool(nature.get("has_real_local_changes"))
    needs_merge = user_edited and has_remote and info.get("status") not in {"up_to_date", "local_ahead"}
    change_type = nature.get("change_type", "none")

    group = "up_to_date"
    if info.get("status") in {"error", "unknown", "not_checkable"}:
        group = info.get("status", "unknown")
    elif official_update and needs_merge:
        group = "official_with_local_changes"
    elif official_update:
        group = "official_update"
    elif needs_merge:
        group = "merge_needed"
    elif change_type == "user_only":
        group = "local_modified"
    elif change_type == "official_outdated" or has_remote:
        group = "remote_update"
    elif info.get("status") in {"update_available", "content_diff"}:
        group = "remote_update"

    return {
        "official_update": official_update,
        "has_local_changes": has_real_local,
        "has_remote_changes": has_remote,
        "user_edited": user_edited,
        "needs_merge": needs_merge,
        "group": group,
        "change_type": change_type,
        "change_label": nature.get("change_label"),
    }


def _build_check_result(
    skill: dict[str, Any],
    lock: dict[str, Any],
    repo_cache: dict[str, Path],
) -> dict[str, Any]:
    local_dir = Path(skill["resolved_path"])
    local_info = _local_skill_info(local_dir)
    remote_dir, remote_meta = fetch_remote_skill_dir(skill, lock, repo_cache)

    if remote_dir is None:
        return {
            "status": "error",
            "reason": remote_meta.get("error", "无法获取远程版本"),
            "local_version": local_info["version"],
        }

    remote_info = _local_skill_info(remote_dir)
    locked_hash = lock.get("skillFolderHash") or ""
    version_status = _compare_versions(local_info["version"], remote_info["version"])
    md_only = remote_meta.get("source_type") == "well-known"
    compare_local = local_info["skill_md_hash"] if md_only else local_info["folder_hash"]
    compare_remote = remote_info["skill_md_hash"] if md_only else remote_info["folder_hash"]

    status = _resolve_update_status(
        version_status=version_status,
        local_hash=compare_local,
        remote_hash=compare_remote,
        locked_hash=locked_hash or None,
        md_only=md_only,
    )

    diff = diff_folders(local_dir, remote_dir)
    diff = filter_diff_for_classification(diff, md_only=md_only)

    nature = analyze_change_nature(
        diff,
        md_only=md_only,
        locked_hash=locked_hash or None,
        local_folder_hash=local_info["folder_hash"],
    )
    diff["has_local_changes"] = nature["has_real_local_changes"]
    diff["has_remote_changes"] = nature["has_remote_changes"]

    official_update = version_status == "update_available" and bool(remote_info["version"])

    result = {
        "status": status,
        "source_type": remote_meta.get("source_type"),
        "remote_url": remote_meta.get("remote_url"),
        "local_version": local_info["version"],
        "remote_version": remote_info["version"],
        "local_hash": compare_local,
        "remote_hash": compare_remote,
        "locked_hash": locked_hash or None,
        "official_update": official_update,
        "diff": diff,
        "change_nature": nature,
        "local_changes": {
            "added_files": diff.get("added_locally", []),
            "modified_files": [item["path"] for item in diff.get("modified", [])],
            "real_files": nature.get("real_local_files", []),
            "summary": nature.get("change_label") or diff.get("summary"),
            "notes": nature.get("notes", []),
            "user_edited": nature.get("user_edited", False),
        },
    }
    result.update(_classify_result(result))
    return result


def _check_single_skill(skill: dict[str, Any], lock_map: dict[str, Any], repo_cache: dict[str, Path]) -> dict[str, Any]:
    if skill["category"] in {"grok-bundled", "package", "marketplace"}:
        return {"status": "not_checkable", "reason": "该类型 skill 由运行时自身管理更新", "group": "not_checkable"}

    lock = _prepare_lock(skill, lock_map.get(skill["folder_name"], {}))
    source_type = (lock.get("sourceType") or skill.get("source_type") or "").lower()

    if source_type in {"local", "manual"} and not lock.get("sourceUrl"):
        return {"status": "unknown", "reason": "本地 skill，无远程源", "group": "unknown"}

    if source_type == "github" or (lock.get("sourceUrl") and ("github.com" in lock["sourceUrl"] or lock["sourceUrl"].endswith(".git"))):
        return _build_check_result(skill, lock, repo_cache)

    if source_type == "well-known" or lock.get("sourceUrl"):
        return _build_check_result(skill, lock, repo_cache)

    return {"status": "unknown", "reason": "无法识别更新源", "group": "unknown"}


def _build_summary(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = {
        "official_updates": [],
        "remote_updates": [],
        "local_modified": [],
        "merge_needed": [],
        "official_with_local_changes": [],
    }

    for name, info in results.items():
        if info.get("status") in {"not_checkable", "unknown", "error", "up_to_date"}:
            continue
        group = info.get("group")
        item = {
            "name": name,
            "local_version": info.get("local_version"),
            "remote_version": info.get("remote_version"),
            "local_changes": info.get("local_changes"),
            "change_label": info.get("change_label"),
            "change_type": info.get("change_type"),
            "user_edited": info.get("user_edited"),
            "diff": info.get("diff"),
            "status": info.get("status"),
            "needs_merge": info.get("needs_merge"),
        }
        if group in buckets:
            buckets[group].append(item)
        elif info.get("official_update"):
            buckets["official_updates"].append(item)
        elif info.get("needs_merge"):
            buckets["merge_needed"].append(item)
        elif info.get("has_local_changes"):
            buckets["local_modified"].append(item)
        elif info.get("has_remote_changes"):
            buckets["remote_updates"].append(item)

    return {
        "official_updates_count": len(buckets["official_updates"]) + len(buckets["official_with_local_changes"]),
        "remote_updates_count": len(buckets["remote_updates"]),
        "local_modified_count": len(buckets["local_modified"]),
        "merge_needed_count": len(buckets["merge_needed"]) + len(buckets["official_with_local_changes"]),
        **buckets,
    }


def check_updates(names: list[str] | None = None, max_workers: int = 8) -> dict[str, Any]:
    data = scan_all()
    lock_map = _load_lock().get("skills", {})
    skills = data["skills"]

    if names:
        wanted = {name.strip() for name in names}
        skills = [skill for skill in skills if skill["folder_name"] in wanted or skill["name"] in wanted]

    checkable = [skill for skill in skills if skill["category"] not in {"grok-bundled", "package", "marketplace"}]
    repo_cache: dict[str, Path] = {}
    results: dict[str, dict[str, Any]] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_check_single_skill, skill, lock_map, repo_cache): skill for skill in checkable}
        for future in as_completed(futures):
            skill = futures[future]
            try:
                results[skill["folder_name"]] = future.result()
            except Exception as exc:  # noqa: BLE001
                results[skill["folder_name"]] = {"status": "error", "reason": str(exc), "group": "error"}

    for skill in skills:
        if skill["folder_name"] not in results:
            results[skill["folder_name"]] = {"status": "not_checkable", "reason": "未纳入远程检查", "group": "not_checkable"}

    summary = _build_summary(results)
    updates_available = [
        name
        for name, info in results.items()
        if info.get("group") in {"official_update", "official_with_local_changes", "remote_update", "merge_needed"}
        or info.get("status") in {"update_available", "content_diff"}
    ]

    return {
        "checked_at": _now_iso(),
        "total_checked": len(checkable),
        "updates_available_count": len(updates_available),
        "updates_available": updates_available,
        "summary": summary,
        "results": results,
    }


def merge_skill_integrated(name: str, *, overwrite_skill_md: bool = False) -> dict[str, Any]:
    data = scan_all()
    skill = next((item for item in data["skills"] if item["folder_name"] == name or item["name"] == name), None)
    if not skill:
        raise FileNotFoundError(f"未找到 Skill: {name}")

    lock_map = _load_lock().get("skills", {})
    lock = _prepare_lock(skill, lock_map.get(skill["folder_name"], {}))
    local_dir = Path(skill["resolved_path"])
    remote_dir, remote_meta = fetch_remote_skill_dir(skill, lock)

    if remote_dir is None:
        raise ValueError(remote_meta.get("error", "无法获取远程版本"))

    md_only = remote_meta.get("source_type") == "well-known"
    merge_result = merge_folders(
        local_dir,
        remote_dir,
        md_only=md_only,
        overwrite_skill_md=overwrite_skill_md,
    )

    if lock.get("sourceType") == "github" or remote_meta.get("source_type") == "github":
        new_hash = compute_folder_hash(local_dir)
        with LOCK_FILE_MUTEX:
            lock_data = _load_lock()
            entry = lock_data.setdefault("skills", {}).setdefault(skill["folder_name"], {})
            entry["skillFolderHash"] = new_hash
            entry["updatedAt"] = _now_iso()
            from manager import _save_lock

            _save_lock(lock_data)

    final = {
        "ok": True,
        "action": "merge",
        "name": skill["folder_name"],
        "local_version": skill.get("local_version"),
        "remote_version": None,
        "backup_path": merge_result["backup_path"],
        "diff": merge_result["diff"],
        "actions": merge_result["actions"],
        "merged_files": merge_result["merged_files"],
    }
    append_audit("merge", name=skill["folder_name"], backup_path=merge_result["backup_path"])
    return final


def upgrade_skill(name: str, scope: str | None = None, *, overwrite: bool = True) -> dict[str, Any]:
    data = scan_all()
    skill = next((item for item in data["skills"] if item["folder_name"] == name or item["name"] == name), None)
    if not skill:
        raise FileNotFoundError(f"未找到 Skill: {name}")

    lock_map = _load_lock().get("skills", {})
    lock = lock_map.get(skill["folder_name"], {})
    git_url = lock.get("sourceUrl")
    source_type = (lock.get("sourceType") or skill.get("source_type") or "").lower()

    if skill["folder_name"] == "skill-manager":
        git_url = GITHUB_CLONE_URL
        source_type = "github"

    target_scope = scope or ("agents" if skill["category"] == "agents-shared" else "grok")

    if source_type == "github" or (git_url and ("github.com" in git_url or git_url.endswith(".git"))):
        result = install_skill(
            name=skill["folder_name"],
            scope=target_scope,
            git_url=git_url or GITHUB_CLONE_URL,
            skill_subpath=str(Path(lock["skillPath"]).parent.as_posix()) if lock.get("skillPath") else None,
            overwrite=True,
            allow_reserved_name=skill["folder_name"] == "skill-manager",
        )
    else:
        return merge_skill_integrated(name, overwrite_skill_md=overwrite)

    if target_scope in {"agents", "project-agents"}:
        _update_lock_install(skill["folder_name"], git_url or "github", "github", git_url)

    final = {"ok": True, "action": "upgrade", "name": skill["folder_name"], "scope": target_scope, "install": result}
    append_audit("upgrade", name=skill["folder_name"], scope=target_scope)
    return final


def batch_upgrade_skills(names: list[str] | None = None, max_workers: int = 4) -> dict[str, Any]:
    skipped: list[dict[str, Any]] = []
    if names:
        targets = []
        seen = set()
        for name in names:
            cleaned = name.strip()
            if cleaned and cleaned not in seen:
                targets.append(cleaned)
                seen.add(cleaned)
    else:
        updates = check_updates(max_workers=max_workers)
        summary = updates.get("summary") or {}
        safe_items = list(summary.get("official_updates") or []) + list(summary.get("remote_updates") or [])
        targets = [item["name"] for item in safe_items if item.get("name")]
        merge_items = list(summary.get("merge_needed") or []) + list(summary.get("official_with_local_changes") or [])
        skipped = [
            {
                "ok": False,
                "name": item.get("name"),
                "skipped": True,
                "reason": "需要整合更新，批量升级不会自动覆盖本地改动",
            }
            for item in merge_items
            if item.get("name")
        ]

    if not targets:
        return {"ok": True, "action": "batch_upgrade", "workers": max_workers, "results": skipped}

    workers = max(1, min(max_workers, len(targets), MAX_BATCH_UPGRADE_WORKERS))
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(upgrade_skill, name): name for name in targets}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001
                results.append({"ok": False, "name": name, "error": str(exc)})

    results.extend(skipped)
    results.sort(key=lambda item: str(item.get("name") or item.get("install", {}).get("name") or ""))
    return {
        "ok": all(item.get("ok") or item.get("skipped") for item in results),
        "action": "batch_upgrade",
        "workers": workers,
        "results": results,
    }


def merge_updates_into_scan(scan_data: dict[str, Any], update_data: dict[str, Any]) -> dict[str, Any]:
    merged = dict(scan_data)
    skills = []
    for skill in scan_data["skills"]:
        item = dict(skill)
        info = update_data["results"].get(skill["folder_name"], {})
        item["update_status"] = info.get("status", "unknown")
        item["update_reason"] = info.get("reason")
        item["local_version"] = info.get("local_version") or item.get("local_version")
        item["remote_version"] = info.get("remote_version")
        item["update_group"] = info.get("group")
        item["official_update"] = info.get("official_update", False)
        item["needs_merge"] = info.get("needs_merge", False)
        item["local_changes"] = info.get("local_changes")
        item["diff"] = info.get("diff")
        item["has_update"] = info.get("group") in {
            "official_update",
            "official_with_local_changes",
            "remote_update",
            "merge_needed",
        } or info.get("status") in {"update_available", "content_diff"}
        item["has_local_changes"] = info.get("has_local_changes", False)
        item["user_edited"] = info.get("user_edited", False)
        item["change_type"] = info.get("change_type")
        item["change_label"] = info.get("change_label")
        skills.append(item)
    merged["skills"] = skills
    merged["updates"] = {
        "checked_at": update_data["checked_at"],
        "updates_available_count": update_data["updates_available_count"],
        "updates_available": update_data["updates_available"],
        "summary": update_data.get("summary", {}),
    }
    return merged
