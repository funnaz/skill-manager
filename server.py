"""Skill Manager local dashboard."""

from __future__ import annotations

import subprocess
import webbrowser
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from manager import create_skill, delete_skill, install_skill
from scanner import read_skill_content, scan_all

APP = FastAPI(title="Skill Manager", version="2.0.0")
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


@APP.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "port": PORT, "version": "2.0.0"}


def main(open_browser: bool = True) -> None:
    url = f"http://127.0.0.1:{PORT}"
    print(f"Skill Manager running at {url}")
    if open_browser:
        webbrowser.open(url)
    uvicorn.run(APP, host="127.0.0.1", port=PORT, log_level="info")


if __name__ == "__main__":
    main()