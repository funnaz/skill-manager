"""Skill Manager local dashboard."""

from __future__ import annotations

import asyncio
import subprocess
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from config_io import disable_skill, enable_skill
from constants import GITHUB_URL
from manager import batch_delete, create_skill, delete_skill, install_skill
from skill_parser import parse_skill_md
from report import build_export_bytes, export_report
from scanner import read_skill_content, scan_all
from updater import check_updates, merge_skill_integrated, merge_updates_into_scan, upgrade_skill
from path_picker import pick_folder
from user_settings import load_settings, save_settings

APP = FastAPI(title="Skill Manager", version="2.3.0")
STATIC_DIR = Path(__file__).parent / "static"
PORT = 5520


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


class BatchDeleteRequest(BaseModel):
    names: list[str] | None = None
    resolved_paths: list[str] | None = None
    force: bool = False


class ToggleSkillRequest(BaseModel):
    name: str


class UpgradeSkillRequest(BaseModel):
    name: str
    scope: str | None = None


@APP.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


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
        return delete_skill(name=payload.name, resolved_path=payload.resolved_path, force=payload.force)
    except (ValueError, FileNotFoundError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@APP.post("/api/skills/batch-delete")
async def api_batch_delete(payload: BatchDeleteRequest) -> dict[str, Any]:
    try:
        return batch_delete(names=payload.names, resolved_paths=payload.resolved_paths, force=payload.force)
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


@APP.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "port": PORT, "version": "2.3.0", "github": GITHUB_URL}


def main(open_browser: bool = True) -> None:
    url = f"http://127.0.0.1:{PORT}"
    print(f"Skill Manager running at {url}")
    print(f"GitHub: {GITHUB_URL}")
    if open_browser:
        webbrowser.open(url)
    uvicorn.run(APP, host="127.0.0.1", port=PORT, log_level="info")


if __name__ == "__main__":
    main()