"""Command-line entry for skill-manager."""

from __future__ import annotations

import argparse
import json
import sys

from manager import create_skill, delete_skill, install_skill
from scanner import scan_all


def cmd_scan(_: argparse.Namespace) -> int:
    print(json.dumps(scan_all(), ensure_ascii=False, indent=2))
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    result = create_skill(args.name, args.description, args.scope, args.body)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    result = install_skill(
        name=args.name,
        scope=args.scope,
        source_path=args.from_path,
        git_url=args.git,
        skill_subpath=args.subpath,
        description=args.description,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    result = delete_skill(name=args.name, resolved_path=args.path, force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from server import APP

    uvicorn.run(APP, host=args.host, port=args.port, log_level="info")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Skill Manager CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    scan_p = sub.add_parser("scan", help="扫描本机 skills")
    scan_p.set_defaults(func=cmd_scan)

    create_p = sub.add_parser("create", help="创建新 skill")
    create_p.add_argument("--name", required=True)
    create_p.add_argument("--description", required=True)
    create_p.add_argument("--scope", default="grok", choices=["grok", "agents", "codex", "cursor", "project-grok", "project-agents"])
    create_p.add_argument("--body")
    create_p.set_defaults(func=cmd_create)

    install_p = sub.add_parser("install", help="安装 skill")
    install_p.add_argument("--name")
    install_p.add_argument("--scope", default="grok", choices=["grok", "agents", "codex", "cursor", "project-grok", "project-agents"])
    install_p.add_argument("--from-path", dest="from_path")
    install_p.add_argument("--git")
    install_p.add_argument("--subpath")
    install_p.add_argument("--description")
    install_p.set_defaults(func=cmd_install)

    delete_p = sub.add_parser("delete", help="删除 skill")
    delete_p.add_argument("--name")
    delete_p.add_argument("--path")
    delete_p.add_argument("--force", action="store_true")
    delete_p.set_defaults(func=cmd_delete)

    serve_p = sub.add_parser("serve", help="启动 Web 面板")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=5520)
    serve_p.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())