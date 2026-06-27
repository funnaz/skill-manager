"""Command-line entry for skill-manager."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from config_io import disable_skill, enable_skill
from constants import GITHUB_INSTALL_CMD, GITHUB_URL
from manager import batch_delete, create_skill, delete_skill, install_skill
from report import export_report
from scanner import scan_all
from updater import check_updates, merge_skill_integrated, merge_updates_into_scan, upgrade_skill


def cmd_scan(_: argparse.Namespace) -> int:
    print(json.dumps(scan_all(), ensure_ascii=False, indent=2))
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    skill_md = None
    if args.from_md:
        skill_md = Path(args.from_md).read_text(encoding="utf-8")
    result = create_skill(args.name, args.description, args.scope, args.body, skill_md)
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
    if args.batch:
        names = [part.strip() for part in args.batch.split(",") if part.strip()]
        result = batch_delete(names=names, force=args.force)
    else:
        result = delete_skill(name=args.name, resolved_path=args.path, force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_disable(args: argparse.Namespace) -> int:
    result = disable_skill(args.name)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_enable(args: argparse.Namespace) -> int:
    result = enable_skill(args.name)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    result = export_report(args.format, args.output, lang=args.lang)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_check_updates(args: argparse.Namespace) -> int:
    updates = check_updates(args.names.split(",") if args.names else None)
    if args.merge:
        payload = merge_updates_into_scan(scan_all(), updates)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(updates, ensure_ascii=False, indent=2))
    return 0


def cmd_upgrade(args: argparse.Namespace) -> int:
    result = upgrade_skill(args.name, args.scope)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_merge(args: argparse.Namespace) -> int:
    result = merge_skill_integrated(args.name)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from server import APP

    uvicorn.run(APP, host=args.host, port=args.port, log_level="info")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Skill Manager CLI ({GITHUB_URL})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scan_p = sub.add_parser("scan", help="扫描本机 skills")
    scan_p.set_defaults(func=cmd_scan)

    create_p = sub.add_parser("create", help="创建新 skill")
    create_p.add_argument("--name")
    create_p.add_argument("--description")
    create_p.add_argument("--scope", default="agents", choices=["agents", "codex", "cursor", "grok", "project-agents", "project-grok"])
    create_p.add_argument("--body")
    create_p.add_argument("--from-md", dest="from_md", help="从 Markdown 文件导入并自动解析名称与描述")
    create_p.set_defaults(func=cmd_create)

    install_p = sub.add_parser("install", help="安装 skill")
    install_p.add_argument("--name")
    install_p.add_argument("--scope", default="agents", choices=["agents", "codex", "cursor", "grok", "project-agents", "project-grok"])
    install_p.add_argument("--from-path", dest="from_path")
    install_p.add_argument("--git")
    install_p.add_argument("--subpath")
    install_p.add_argument("--description")
    install_p.set_defaults(func=cmd_install)

    delete_p = sub.add_parser("delete", help="删除 skill")
    delete_p.add_argument("--name")
    delete_p.add_argument("--path")
    delete_p.add_argument("--batch", help="逗号分隔的多个 skill 名称")
    delete_p.add_argument("--force", action="store_true")
    delete_p.set_defaults(func=cmd_delete)

    disable_p = sub.add_parser("disable", help="在 Grok 中禁用 skill")
    disable_p.add_argument("--name", required=True)
    disable_p.set_defaults(func=cmd_disable)

    enable_p = sub.add_parser("enable", help="在 Grok 中启用 skill")
    enable_p.add_argument("--name", required=True)
    enable_p.set_defaults(func=cmd_enable)

    export_p = sub.add_parser("export", help="导出扫描报告")
    export_p.add_argument("--format", default="md", choices=["json", "markdown", "md", "docx", "pdf"])
    export_p.add_argument("--lang", default="zh", choices=["zh", "en"])
    export_p.add_argument("--output")
    export_p.set_defaults(func=cmd_export)

    updates_p = sub.add_parser("check-updates", help="检测 skill 新版本")
    updates_p.add_argument("--names", help="逗号分隔，仅检查指定 skill")
    updates_p.add_argument("--merge", action="store_true", help="合并到 scan 结果输出")
    updates_p.set_defaults(func=cmd_check_updates)

    upgrade_p = sub.add_parser("upgrade", help="升级 skill 到远程最新版")
    upgrade_p.add_argument("--name", required=True)
    upgrade_p.add_argument("--scope")
    upgrade_p.set_defaults(func=cmd_upgrade)

    merge_p = sub.add_parser("merge", help="整合官方最新版本与本地改动")
    merge_p.add_argument("--name", required=True)
    merge_p.set_defaults(func=cmd_merge)

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
        print(json.dumps({"ok": False, "error": str(exc), "github": GITHUB_URL}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())