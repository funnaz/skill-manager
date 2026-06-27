"""Detect and apply skill updates from remote sources."""

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

import yaml

from constants import GITHUB_CLONE_URL
from manager import LOCK_PATH, _load_lock, _update_lock_install, install_skill
from scanner import HOME, _read_frontmatter, scan_all

USER_AGENT = "skill-manager/2.2"


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
        return {"version": None, "skill_md_hash": None}
    text = skill_md.read_text(encoding="utf-8")
    meta, _ = _read_frontmatter(text)
    return {
        "version": version_label(str(meta.get("version") or "")),
        "skill_md_hash": hashlib.sha1(text.encode("utf-8")).hexdigest(),
        "folder_hash": compute_folder_hash(folder),
    }


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


def _check_github_skill(
    skill: dict[str, Any],
    lock: dict[str, Any],
    repo_cache: dict[str, Path],
    temp_dirs: list[Path],
) -> dict[str, Any]:
    git_url = lock.get("sourceUrl") or skill.get("source_url")
    if not git_url:
        return {"status": "unknown", "reason": "缺少 GitHub 地址"}

    repo_dir = _clone_github_repo(git_url, repo_cache)
    if not repo_dir:
        return {"status": "error", "reason": "无法拉取 GitHub 仓库"}

    remote_dir = _github_skill_dir(repo_dir, lock.get("skillPath"), skill["folder_name"])
    if not remote_dir:
        return {"status": "error", "reason": "仓库中未找到对应 skill 目录"}

    local_dir = Path(skill["resolved_path"])
    local_info = _local_skill_info(local_dir)
    remote_info = _local_skill_info(remote_dir)
    locked_hash = lock.get("skillFolderHash") or ""

    version_status = _compare_versions(local_info["version"], remote_info["version"])
    local_hash = local_info["folder_hash"]
    remote_hash = remote_info["folder_hash"]
    status = _resolve_update_status(
        version_status=version_status,
        local_hash=local_hash,
        remote_hash=remote_hash,
        locked_hash=locked_hash or None,
    )

    return {
        "status": status,
        "source_type": "github",
        "remote_url": git_url,
        "local_version": local_info["version"],
        "remote_version": remote_info["version"],
        "local_hash": local_hash,
        "remote_hash": remote_hash,
        "locked_hash": locked_hash or None,
    }


def _well_known_folder_url(source_url: str) -> str | None:
    if not source_url.endswith("/SKILL.md"):
        return None
    return source_url[: -len("/SKILL.md")] + "/"


def _check_well_known_skill(skill: dict[str, Any], lock: dict[str, Any]) -> dict[str, Any]:
    source_url = lock.get("sourceUrl") or skill.get("source_url")
    if not source_url:
        return {"status": "unknown", "reason": "缺少远程地址"}

    local_dir = Path(skill["resolved_path"])
    local_info = _local_skill_info(local_dir)

    try:
        remote_text = _fetch_text(source_url)
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"status": "error", "reason": f"拉取远程 SKILL.md 失败: {exc}"}

    remote_meta, _ = _read_frontmatter(remote_text)
    remote_version = version_label(str(remote_meta.get("version") or ""))
    remote_skill_hash = hashlib.sha1(remote_text.encode("utf-8")).hexdigest()
    version_status = _compare_versions(local_info["version"], remote_version)
    status = _resolve_update_status(
        version_status=version_status,
        local_hash=local_info["skill_md_hash"],
        remote_hash=remote_skill_hash,
        locked_hash=lock.get("skillFolderHash") or None,
        md_only=True,
    )

    return {
        "status": status,
        "source_type": "well-known",
        "remote_url": source_url,
        "local_version": local_info["version"],
        "remote_version": remote_version,
        "local_hash": local_info["skill_md_hash"],
        "remote_hash": remote_skill_hash,
        "detail": "基于远程 SKILL.md 的 version 与内容哈希判断",
    }


def _check_single_skill(
    skill: dict[str, Any],
    lock_map: dict[str, Any],
    repo_cache: dict[str, Path],
) -> dict[str, Any]:
    folder_name = skill["folder_name"]
    lock = lock_map.get(folder_name, {})
    source_type = (lock.get("sourceType") or skill.get("source_type") or "").lower()

    if skill["category"] in {"grok-bundled", "package", "marketplace"}:
        return {
            "status": "not_checkable",
            "reason": "该类型 skill 由运行时自身管理更新",
        }

    if folder_name == "skill-manager" or lock.get("sourceUrl") == GITHUB_CLONE_URL:
        source_type = "github"
        lock = {
            **lock,
            "sourceType": "github",
            "sourceUrl": GITHUB_CLONE_URL,
            "skillPath": "SKILL.md",
        }

    if source_type == "github":
        return _check_github_skill(skill, lock, repo_cache, [])
    if source_type == "well-known":
        return _check_well_known_skill(skill, lock)
    if source_type in {"local", "manual", ""}:
        return {"status": "unknown", "reason": "本地 skill，无远程源"}

    if lock.get("sourceUrl"):
        if "github.com" in lock["sourceUrl"] or lock["sourceUrl"].endswith(".git"):
            lock["sourceType"] = "github"
            return _check_github_skill(skill, lock, repo_cache, [])
        return _check_well_known_skill(skill, lock)

    return {"status": "unknown", "reason": "无法识别更新源"}


def check_updates(
    names: list[str] | None = None,
    max_workers: int = 8,
) -> dict[str, Any]:
    data = scan_all()
    lock_map = _load_lock().get("skills", {})
    skills = data["skills"]

    if names:
        wanted = {name.strip() for name in names}
        skills = [skill for skill in skills if skill["folder_name"] in wanted or skill["name"] in wanted]

    checkable = [
        skill
        for skill in skills
        if skill["category"] not in {"grok-bundled", "package", "marketplace"}
    ]

    repo_cache: dict[str, Path] = {}
    results: dict[str, dict[str, Any]] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_check_single_skill, skill, lock_map, repo_cache): skill
            for skill in checkable
        }
        for future in as_completed(futures):
            skill = futures[future]
            try:
                results[skill["folder_name"]] = future.result()
            except Exception as exc:  # noqa: BLE001
                results[skill["folder_name"]] = {"status": "error", "reason": str(exc)}

    for skill in skills:
        if skill["folder_name"] not in results:
            results[skill["folder_name"]] = {
                "status": "not_checkable",
                "reason": "未纳入远程检查",
            }

    updates_available = [
        name
        for name, info in results.items()
        if info.get("status") in {"update_available", "content_diff"}
    ]

    return {
        "checked_at": _now_iso(),
        "total_checked": len(checkable),
        "updates_available_count": len(updates_available),
        "updates_available": updates_available,
        "results": results,
    }


def upgrade_skill(name: str, scope: str | None = None) -> dict[str, Any]:
    data = scan_all()
    skill = next(
        (item for item in data["skills"] if item["folder_name"] == name or item["name"] == name),
        None,
    )
    if not skill:
        raise FileNotFoundError(f"未找到 Skill: {name}")

    lock_map = _load_lock().get("skills", {})
    lock = lock_map.get(skill["folder_name"], {})
    source_type = (lock.get("sourceType") or skill.get("source_type") or "").lower()
    git_url = lock.get("sourceUrl")
    source_url = lock.get("sourceUrl") or skill.get("source_url")

    if skill["folder_name"] == "skill-manager":
        git_url = GITHUB_CLONE_URL
        source_type = "github"

    target_scope = scope or (
        "agents" if skill["category"] == "agents-shared" else "grok"
    )

    if source_type == "github" or (git_url and (".git" in git_url or "github.com" in git_url)):
        result = install_skill(
            name=skill["folder_name"],
            scope=target_scope,
            git_url=git_url or GITHUB_CLONE_URL,
            skill_subpath=str(Path(lock["skillPath"]).parent.as_posix()) if lock.get("skillPath") else None,
            overwrite=True,
        )
    elif source_url:
        raise NotImplementedError(
            "well-known skill 暂不支持一键升级，请使用对应安装器或重新 install。"
        )
    else:
        raise ValueError(f"Skill `{name}` 没有可升级的远程源")

    if target_scope in {"agents", "project-agents"}:
        _update_lock_install(skill["folder_name"], git_url or source_url or "github", "github", git_url)

    return {
        "ok": True,
        "action": "upgrade",
        "name": skill["folder_name"],
        "scope": target_scope,
        "install": result,
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
        item["has_update"] = info.get("status") in {"update_available", "content_diff"}
        skills.append(item)
    merged["skills"] = skills
    merged["updates"] = {
        "checked_at": update_data["checked_at"],
        "updates_available_count": update_data["updates_available_count"],
        "updates_available": update_data["updates_available"],
    }
    return merged