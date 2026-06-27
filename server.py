"""Skill Manager local dashboard."""

from __future__ import annotations

import subprocess
import webbrowser
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from config_io import disable_skill, enable_skill
from constants import GITHUB_URL
from manager import batch_delete, create_skill, delete_skill, install_skill
from report import build_markdown_report, export_report
from scanner import read_skill_content, scan_all

APP = FastAPI(title="Skill Manager", version="2.1.0")
STATIC_DIR = Path(__file__).parent / "static"
PORT = 5520


class CreateSkillRequest(BaseModel):
    name: str
    description: str
    scope: str = "grok"
    body: str | None = None


class InstallSkillRequest(BaseModel):
    name: str | None = None
    scope: str = "grok"
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


@APP.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@APP.get("/api/scan")
async def api_scan() -> dict[str, Any]:
    return scan_all()


@APP.get("/api/skill")
async def api_skill(path: str) -> dict[str, Any]:
    try:
        return read_skill_content(path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@APP.post("/api/skills/create")
async def api_create(payload: CreateSkillRequest) -> dict[str, Any]:
    try:
        return create_skill(payload.name, payload.description, payload.scope, payload.body)
    except (ValueError, FileExistsError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@APP.get("/api/export")
async def api_export(fmt: str = "json") -> Any:
    try:
        if fmt == "markdown":
            return PlainTextResponse(build_markdown_report(), media_type="text/markdown; charset=utf-8")
        return export_report("json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@APP.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "port": PORT, "version": "2.1.0", "github": GITHUB_URL}


def main(open_browser: bool = True) -> None:
    url = f"http://127.0.0.1:{PORT}"
    print(f"Skill Manager running at {url}")
    print(f"GitHub: {GITHUB_URL}")
    if open_browser:
        webbrowser.open(url)
    uvicorn.run(APP, host="127.0.0.1", port=PORT, log_level="info")


if __name__ == "__main__":
    main()