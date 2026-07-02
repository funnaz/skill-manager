"""Skill Manager local dashboard."""

from __future__ import annotations

import asyncio
import os
import secrets
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from audit_log import read_audit
from backup_manager import list_backups, restore_backup
from config_io import disable_skill, enable_skill
from constants import GITHUB_URL
from dependency_manager import install_missing_python, missing_dependencies
from maintenance_manager import auto_cleanup, cleanup_plan
from manager import batch_delete, create_skill, delete_skill, fork_skill, install_skill, search_skills, set_skill_source
from package_manager import export_skillpkg, import_skillpkg
from skill_parser import parse_skill_md
from report import build_export_bytes, build_html_report, export_report
from scanner import read_skill_content, scan_all
from snapshot_manager import diff_snapshot, export_snapshot
from template_manager import create_from_template, list_templates
from trash_manager import list_trash, purge_trash, restore_from_trash
from updater import batch_upgrade_skills, check_updates, merge_skill_integrated, merge_updates_into_scan, upgrade_skill
from path_picker import pick_folder
from user_settings import load_settings, save_settings
from usage_collector import aggregate_stats, build_usage_report, collect_all
from hook_installer import hook_status, install_all_hooks

APP = FastAPI(title="Skill Manager", version="2.4.0")
STATIC_DIR = Path(__file__).parent / "static"
if not (STATIC_DIR / "index.html").exists():
    STATIC_DIR = Path(sys.prefix) / "static"
PORT = 5520
SERVER_TOKEN = os.environ.get("SKILL_MANAGER_TOKEN") or secrets.token_urlsafe(32)


@APP.middleware("http")
async def require_local_api_token(request: Request, call_next: Any) -> Any:
    if request.url.path.startswith("/api/") and request.url.path != "/api/session":
        token = request.headers.get("X-Skill-Manager-Token", "")
        if not secrets.compare_digest(token, SERVER_TOKEN):
            return JSONResponse({"detail": "Missing or invalid local API token"}, status_code=403)
    return await call_next(request)


class CreateSkillRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    scope: str = Field(default_factory=lambda: load_settings()["default_scope"])
    body: str | None = None
    skill_md: str | None = None


class ParseSkillMdRequest(BaseModel):
    content: str


class SettingsRequest(BaseModel):
    default_scope: str


class InstallSkillRequest(BaseModel):
    name: str | None = None
    scope: str = Field(default_factory=lambda: load_settings()["default_scope"])
    source_path: str | None = None
    git_url: str | None = None
    skill_subpath: str | None = None
    description: str | None = None


class DeleteSkillRequest(BaseModel):
    name: str | None = None
    resolved_path: str | None = None
    force: bool = False
    dry_run: bool = False


class BatchDeleteRequest(BaseModel):
    names: list[str] | None = None
    resolved_paths: list[str] | None = None
    force: bool = False
    dry_run: bool = False


class ToggleSkillRequest(BaseModel):
    name: str


class BatchToggleSkillRequest(BaseModel):
    names: list[str]


class UpgradeSkillRequest(BaseModel):
    name: str
    scope: str | None = None


class BatchUpgradeRequest(BaseModel):
    names: list[str] | None = None
    max_workers: int = 4


class PackageExportRequest(BaseModel):
    names: list[str]
    output_path: str | None = None


class PackageImportRequest(BaseModel):
    package_path: str
    scope: str = Field(default_factory=lambda: load_settings()["default_scope"])
    overwrite: bool = False


class ForkSkillRequest(BaseModel):
    source: str
    name: str
    scope: str = Field(default_factory=lambda: load_settings()["default_scope"])
    description: str | None = None


class TemplateCreateRequest(BaseModel):
    template: str
    name: str | None = None
    scope: str = Field(default_factory=lambda: load_settings()["default_scope"])


class InstallDepsRequest(BaseModel):
    name: str
    yes: bool = False


class SetSourceRequest(BaseModel):
    name: str
    url: str
    type: str = "github"
    skill_path: str | None = None


class SnapshotDiffRequest(BaseModel):
    snapshot_path: str


class AutoCleanupRequest(BaseModel):
    names: list[str] | None = None
    yes: bool = False
    refresh: bool = False


class RestoreBackupRequest(BaseModel):
    backup_id: str
    target_path: str | None = None


@APP.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@APP.get("/api/session")
async def api_session() -> dict[str, Any]:
    return {
        "ok": True,
        "token": SERVER_TOKEN,
        "version": APP.version,
        "token_required": True,
    }


@APP.get("/api/scan")
async def api_scan(check_updates_flag: bool = False) -> dict[str, Any]:
    data = scan_all()
    data["settings"] = load_settings()
    if check_updates_flag:
        return merge_updates_into_scan(data, check_updates())
    return data


@APP.get("/api/settings")
async def api_get_settings() -> dict[str, Any]:
    return load_settings()


@APP.post("/api/settings")
async def api_save_settings(payload: SettingsRequest) -> dict[str, Any]:
    try:
        return save_settings({"default_scope": payload.default_scope})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@APP.get("/api/updates")
async def api_updates() -> dict[str, Any]:
    return check_updates()


@APP.post("/api/skills/upgrade")
async def api_upgrade(payload: UpgradeSkillRequest) -> dict[str, Any]:
    try:
        return upgrade_skill(payload.name, payload.scope)
    except (ValueError, FileNotFoundError, NotImplementedError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@APP.post("/api/skills/batch-upgrade")
async def api_batch_upgrade(payload: BatchUpgradeRequest) -> dict[str, Any]:
    return batch_upgrade_skills(payload.names, max_workers=payload.max_workers)


@APP.post("/api/skills/merge")
async def api_merge(payload: UpgradeSkillRequest) -> dict[str, Any]:
    try:
        return merge_skill_integrated(payload.name)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@APP.get("/api/skill")
async def api_skill(path: str) -> dict[str, Any]:
    try:
        return read_skill_content(path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@APP.post("/api/skills/parse-md")
async def api_parse_md(payload: ParseSkillMdRequest) -> dict[str, Any]:
    try:
        return parse_skill_md(payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@APP.post("/api/skills/create")
async def api_create(payload: CreateSkillRequest) -> dict[str, Any]:
    try:
        return create_skill(
            payload.name,
            payload.description,
            payload.scope,
            payload.body,
            payload.skill_md,
        )
    except (ValueError, FileExistsError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@APP.post("/api/pick-folder")
async def api_pick_folder() -> dict[str, Any]:
    try:
        path = await asyncio.to_thread(pick_folder)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"无法打开文件夹选择器：{exc}") from exc
    return {"path": path}


@APP.post("/api/skills/install")
async def api_install(payload: InstallSkillRequest) -> dict[str, Any]:
    try:
        return install_skill(
            name=payload.name,
            scope=payload.scope,
            source_path=payload.source_path,
            git_url=payload.git_url,
            skill_subpath=payload.skill_subpath,
            description=payload.description,
        )
    except (ValueError, FileExistsError, FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@APP.post("/api/skills/delete")
async def api_delete(payload: DeleteSkillRequest) -> dict[str, Any]:
    try:
        return delete_skill(
            name=payload.name,
            resolved_path=payload.resolved_path,
            force=payload.force,
            dry_run=payload.dry_run,
        )
    except (ValueError, FileNotFoundError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@APP.post("/api/skills/batch-delete")
async def api_batch_delete(payload: BatchDeleteRequest) -> dict[str, Any]:
    try:
        return batch_delete(
            names=payload.names,
            resolved_paths=payload.resolved_paths,
            force=payload.force,
            dry_run=payload.dry_run,
        )
    except (ValueError, FileNotFoundError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@APP.post("/api/skills/disable")
async def api_disable(payload: ToggleSkillRequest) -> dict[str, Any]:
    try:
        return disable_skill(payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@APP.post("/api/skills/enable")
async def api_enable(payload: ToggleSkillRequest) -> dict[str, Any]:
    try:
        return enable_skill(payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@APP.post("/api/skills/batch-disable")
async def api_batch_disable(payload: BatchToggleSkillRequest) -> dict[str, Any]:
    return {"ok": True, "results": [disable_skill(name) for name in payload.names]}


@APP.post("/api/skills/batch-enable")
async def api_batch_enable(payload: BatchToggleSkillRequest) -> dict[str, Any]:
    return {"ok": True, "results": [enable_skill(name) for name in payload.names]}


def _attachment_disposition(filename: str) -> str:
    safe = filename.encode("ascii", "ignore").decode() or "skill-report.bin"
    if safe == filename:
        return f'attachment; filename="{filename}"'
    return f"attachment; filename=\"{safe}\"; filename*=UTF-8''{quote(filename)}"


@APP.get("/api/export")
async def api_export(fmt: str = "md", lang: str = "zh") -> Any:
    try:
        if fmt == "json":
            return export_report("json")
        content, media_type, filename = build_export_bytes(fmt, lang)
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": _attachment_disposition(filename)},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@APP.get("/share")
async def share_html() -> Response:
    return Response(content=build_html_report(lang="zh"), media_type="text/html; charset=utf-8")


@APP.get("/api/usage/stats")
async def api_usage_stats(refresh: bool = False) -> dict[str, Any]:
    if refresh:
        collect_all()
    return {
        "ok": True,
        "stats": aggregate_stats(),
        "hooks": hook_status(),
    }


@APP.post("/api/usage/collect")
async def api_usage_collect() -> dict[str, Any]:
    return build_usage_report()


@APP.post("/api/usage/hooks/install")
async def api_usage_hooks_install() -> dict[str, Any]:
    return install_all_hooks()


@APP.get("/api/usage/hooks/status")
async def api_usage_hooks_status() -> dict[str, Any]:
    return {"ok": True, "hooks": hook_status()}


@APP.get("/api/backups")
async def api_backups() -> dict[str, Any]:
    return {"ok": True, "backups": list_backups()}


@APP.post("/api/backups/restore")
async def api_restore_backup(payload: RestoreBackupRequest) -> dict[str, Any]:
    try:
        return restore_backup(payload.backup_id, payload.target_path)
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@APP.get("/api/audit")
async def api_audit(limit: int = 100) -> dict[str, Any]:
    return {"ok": True, "events": read_audit(limit)}


@APP.get("/api/trash")
async def api_trash() -> dict[str, Any]:
    return {"ok": True, "items": list_trash()}


@APP.post("/api/trash/restore")
async def api_trash_restore(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return restore_from_trash(str(payload.get("trash_id") or ""), payload.get("target_path"))
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@APP.post("/api/trash/purge")
async def api_trash_purge(payload: dict[str, Any]) -> dict[str, Any]:
    return purge_trash(payload.get("trash_id"))


@APP.post("/api/packages/export")
async def api_export_package(payload: PackageExportRequest) -> dict[str, Any]:
    try:
        return export_skillpkg(payload.names, payload.output_path)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@APP.post("/api/packages/import")
async def api_import_package(payload: PackageImportRequest) -> dict[str, Any]:
    try:
        return import_skillpkg(payload.package_path, payload.scope, payload.overwrite)
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@APP.get("/api/search")
async def api_search(q: str, limit: int = 10) -> dict[str, Any]:
    return {"ok": True, "matches": search_skills(q, limit)}


@APP.post("/api/skills/fork")
async def api_fork(payload: ForkSkillRequest) -> dict[str, Any]:
    try:
        return fork_skill(payload.source, payload.name, payload.scope, payload.description)
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@APP.get("/api/templates")
async def api_templates() -> dict[str, Any]:
    return {"ok": True, "templates": list_templates()}


@APP.post("/api/templates/create")
async def api_template_create(payload: TemplateCreateRequest) -> dict[str, Any]:
    try:
        return create_from_template(payload.template, payload.name, payload.scope)
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@APP.get("/api/deps")
async def api_deps(name: str | None = None) -> dict[str, Any]:
    return missing_dependencies(name)


@APP.post("/api/deps/install")
async def api_install_deps(payload: InstallDepsRequest) -> dict[str, Any]:
    try:
        return install_missing_python(payload.name, payload.yes)
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@APP.post("/api/skills/source")
async def api_set_source(payload: SetSourceRequest) -> dict[str, Any]:
    try:
        return set_skill_source(payload.name, payload.url, payload.type, payload.skill_path)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@APP.post("/api/snapshot")
async def api_snapshot(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    return export_snapshot(payload.get("output_path"))


@APP.post("/api/snapshot/diff")
async def api_diff_snapshot(payload: SnapshotDiffRequest) -> dict[str, Any]:
    try:
        return diff_snapshot(payload.snapshot_path)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@APP.get("/api/cleanup-plan")
async def api_cleanup_plan(refresh: bool = False) -> dict[str, Any]:
    return cleanup_plan(refresh)


@APP.post("/api/auto-cleanup")
async def api_auto_cleanup(payload: AutoCleanupRequest) -> dict[str, Any]:
    return auto_cleanup(payload.names, payload.yes, payload.refresh)


@APP.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "port": PORT, "version": "2.4.0", "github": GITHUB_URL, "token_required": True}


def main(open_browser: bool = True, host: str = "127.0.0.1", port: int = PORT) -> None:
    url = f"http://{host}:{port}"
    print(f"Skill Manager running at {url}")
    print(f"GitHub: {GITHUB_URL}")
    print("Local API token enabled. Open the dashboard from this server URL.")
    if open_browser:
        webbrowser.open(url)
    uvicorn.run(APP, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
