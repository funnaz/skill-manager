"""Command-line entry for skill-manager."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from audit_log import read_audit
from backup_manager import list_backups, restore_backup
from config_io import disable_skill, enable_skill
from constants import GITHUB_URL
from dependency_manager import install_missing_python, missing_dependencies
from maintenance_manager import auto_cleanup, cleanup_plan
from manager import batch_delete, create_skill, delete_skill, fork_skill, install_skill, search_skills, set_skill_source
from package_manager import export_skillpkg, import_skillpkg
from report import export_report
from scanner import scan_all
from snapshot_manager import diff_snapshot, export_snapshot
from template_manager import create_from_template, list_templates
from trash_manager import list_trash, purge_trash, restore_from_trash
from updater import batch_upgrade_skills, check_updates, merge_skill_integrated, merge_updates_into_scan, upgrade_skill
from user_settings import load_settings


def cmd_scan(_: argparse.Namespace) -> int:
    print(json.dumps(scan_all(), ensure_ascii=False, indent=2))
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    skill_md = None
    if args.from_md:
        skill_md = Path(args.from_md).read_text(encoding="utf-8")
    scope = args.scope or load_settings()["default_scope"]
    result = create_skill(args.name, args.description, scope, args.body, skill_md)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    scope = args.scope or load_settings()["default_scope"]
    result = install_skill(
        name=args.name,
        scope=scope,
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
        result = batch_delete(names=names, force=args.force, dry_run=args.dry_run)
    else:
        result = delete_skill(name=args.name, resolved_path=args.path, force=args.force, dry_run=args.dry_run)
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


def cmd_batch_disable(args: argparse.Namespace) -> int:
    names = [part.strip() for part in args.names.split(",") if part.strip()]
    result = [disable_skill(name) for name in names]
    print(json.dumps({"ok": True, "action": "batch_disable", "results": result}, ensure_ascii=False, indent=2))
    return 0


def cmd_batch_enable(args: argparse.Namespace) -> int:
    names = [part.strip() for part in args.names.split(",") if part.strip()]
    result = [enable_skill(name) for name in names]
    print(json.dumps({"ok": True, "action": "batch_enable", "results": result}, ensure_ascii=False, indent=2))
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


def cmd_batch_upgrade(args: argparse.Namespace) -> int:
    names = [part.strip() for part in args.names.split(",") if part.strip()] if args.names else None
    print(json.dumps(batch_upgrade_skills(names, max_workers=args.workers), ensure_ascii=False, indent=2))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from server import main as serve_main

    serve_main(open_browser=not args.no_browser, host=args.host, port=args.port)
    return 0


def cmd_backups(_: argparse.Namespace) -> int:
    print(json.dumps({"ok": True, "backups": list_backups()}, ensure_ascii=False, indent=2))
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    result = restore_backup(args.backup_id, args.target_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    print(json.dumps({"ok": True, "events": read_audit(args.limit)}, ensure_ascii=False, indent=2))
    return 0


def cmd_trash(args: argparse.Namespace) -> int:
    print(json.dumps({"ok": True, "items": list_trash()}, ensure_ascii=False, indent=2))
    return 0


def cmd_trash_restore(args: argparse.Namespace) -> int:
    print(json.dumps(restore_from_trash(args.trash_id, args.target_path), ensure_ascii=False, indent=2))
    return 0


def cmd_trash_purge(args: argparse.Namespace) -> int:
    print(json.dumps(purge_trash(args.trash_id), ensure_ascii=False, indent=2))
    return 0


def cmd_export_pkg(args: argparse.Namespace) -> int:
    names = [part.strip() for part in args.names.split(",") if part.strip()]
    print(json.dumps(export_skillpkg(names, args.output), ensure_ascii=False, indent=2))
    return 0


def cmd_import_pkg(args: argparse.Namespace) -> int:
    print(json.dumps(import_skillpkg(args.package, args.scope, args.overwrite), ensure_ascii=False, indent=2))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    print(json.dumps({"ok": True, "matches": search_skills(args.query, args.limit)}, ensure_ascii=False, indent=2))
    return 0


def cmd_fork(args: argparse.Namespace) -> int:
    result = fork_skill(args.source, args.name, args.scope, args.description)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_templates(_: argparse.Namespace) -> int:
    print(json.dumps({"ok": True, "templates": list_templates()}, ensure_ascii=False, indent=2))
    return 0


def cmd_from_template(args: argparse.Namespace) -> int:
    print(json.dumps(create_from_template(args.template, args.name, args.scope), ensure_ascii=False, indent=2))
    return 0


def cmd_deps(args: argparse.Namespace) -> int:
    print(json.dumps(missing_dependencies(args.name), ensure_ascii=False, indent=2))
    return 0


def cmd_install_deps(args: argparse.Namespace) -> int:
    print(json.dumps(install_missing_python(args.name, args.yes), ensure_ascii=False, indent=2))
    return 0


def cmd_set_source(args: argparse.Namespace) -> int:
    print(json.dumps(set_skill_source(args.name, args.url, args.type, args.skill_path), ensure_ascii=False, indent=2))
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    print(json.dumps(export_snapshot(args.output), ensure_ascii=False, indent=2))
    return 0


def cmd_diff_snapshot(args: argparse.Namespace) -> int:
    print(json.dumps(diff_snapshot(args.snapshot), ensure_ascii=False, indent=2))
    return 0


def cmd_cleanup_plan(args: argparse.Namespace) -> int:
    print(json.dumps(cleanup_plan(args.refresh), ensure_ascii=False, indent=2))
    return 0


def cmd_auto_cleanup(args: argparse.Namespace) -> int:
    names = [part.strip() for part in args.names.split(",") if part.strip()] if args.names else None
    print(json.dumps(auto_cleanup(names, args.yes, args.refresh), ensure_ascii=False, indent=2))
    return 0


def cmd_interactive() -> int:
    print("Skill Manager")
    print("1. Scan")
    print("2. Open dashboard")
    print("3. Check updates")
    print("4. View backups")
    print("5. View trash")
    choice = input("Choose: ").strip()
    if choice == "1":
        return cmd_scan(argparse.Namespace())
    if choice == "2":
        return cmd_serve(argparse.Namespace(host="127.0.0.1", port=5520, no_browser=False))
    if choice == "3":
        return cmd_check_updates(argparse.Namespace(names=None, merge=False))
    if choice == "4":
        return cmd_backups(argparse.Namespace())
    if choice == "5":
        return cmd_trash(argparse.Namespace())
    print("Unknown choice")
    return 1


def cmd_usage_collect(_: argparse.Namespace) -> int:
    from usage_collector import build_usage_report

    print(json.dumps(build_usage_report(), ensure_ascii=False, indent=2))
    return 0


def cmd_usage_stats(args: argparse.Namespace) -> int:
    from usage_collector import aggregate_stats, collect_all

    if args.refresh:
        collect_all()
    print(json.dumps(aggregate_stats(), ensure_ascii=False, indent=2))
    return 0


def cmd_usage_hooks_install(_: argparse.Namespace) -> int:
    from hook_installer import install_all_hooks

    print(json.dumps(install_all_hooks(), ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Skill Manager CLI ({GITHUB_URL})",
    )
    sub = parser.add_subparsers(dest="command", required=False)

    scan_p = sub.add_parser("scan", help="扫描本机 skills")
    scan_p.set_defaults(func=cmd_scan)

    create_p = sub.add_parser("create", help="创建新 skill")
    create_p.add_argument("--name")
    create_p.add_argument("--description")
    create_p.add_argument("--scope", default=None, choices=["agents", "claude", "codex", "cursor", "grok", "project-agents", "project-grok"])
    create_p.add_argument("--body")
    create_p.add_argument("--from-md", dest="from_md", help="从 Markdown 文件导入并自动解析名称与描述")
    create_p.set_defaults(func=cmd_create)

    install_p = sub.add_parser("install", help="安装 skill")
    install_p.add_argument("--name")
    install_p.add_argument("--scope", default=None, choices=["agents", "claude", "codex", "cursor", "grok", "project-agents", "project-grok"])
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
    delete_p.add_argument("--dry-run", action="store_true", help="只显示将删除的路径，不实际删除")
    delete_p.set_defaults(func=cmd_delete)

    disable_p = sub.add_parser("disable", help="在 Grok 中禁用 skill")
    disable_p.add_argument("--name", required=True)
    disable_p.set_defaults(func=cmd_disable)

    enable_p = sub.add_parser("enable", help="在 Grok 中启用 skill")
    enable_p.add_argument("--name", required=True)
    enable_p.set_defaults(func=cmd_enable)

    batch_disable_p = sub.add_parser("batch-disable", help="批量禁用 Grok skills")
    batch_disable_p.add_argument("--names", required=True)
    batch_disable_p.set_defaults(func=cmd_batch_disable)

    batch_enable_p = sub.add_parser("batch-enable", help="批量启用 Grok skills")
    batch_enable_p.add_argument("--names", required=True)
    batch_enable_p.set_defaults(func=cmd_batch_enable)

    export_p = sub.add_parser("export", help="导出扫描报告")
    export_p.add_argument("--format", default="md", choices=["json", "markdown", "md", "docx", "pdf", "csv", "html"])
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

    batch_upgrade_p = sub.add_parser("batch-upgrade", help="批量升级可更新 skills")
    batch_upgrade_p.add_argument("--names", help="逗号分隔；留空则升级所有检测到的可更新项")
    batch_upgrade_p.add_argument("--workers", type=int, default=4, help="并发升级线程数，默认 4")
    batch_upgrade_p.set_defaults(func=cmd_batch_upgrade)

    merge_p = sub.add_parser("merge", help="整合官方最新版本与本地改动")
    merge_p.add_argument("--name", required=True)
    merge_p.set_defaults(func=cmd_merge)

    backups_p = sub.add_parser("backups", help="查看可恢复备份")
    backups_p.set_defaults(func=cmd_backups)

    restore_p = sub.add_parser("restore", help="从备份恢复 skill")
    restore_p.add_argument("--backup-id", required=True)
    restore_p.add_argument("--target-path", help="恢复到指定 skill 目录；默认按备份名称匹配当前 skill")
    restore_p.set_defaults(func=cmd_restore)

    audit_p = sub.add_parser("audit", help="查看操作日志")
    audit_p.add_argument("--limit", type=int, default=100)
    audit_p.set_defaults(func=cmd_audit)

    trash_p = sub.add_parser("trash", help="查看回收站")
    trash_p.set_defaults(func=cmd_trash)

    trash_restore_p = sub.add_parser("trash-restore", help="从回收站恢复")
    trash_restore_p.add_argument("--trash-id", required=True)
    trash_restore_p.add_argument("--target-path")
    trash_restore_p.set_defaults(func=cmd_trash_restore)

    trash_purge_p = sub.add_parser("trash-purge", help="清空或永久删除回收站项目")
    trash_purge_p.add_argument("--trash-id")
    trash_purge_p.set_defaults(func=cmd_trash_purge)

    export_pkg_p = sub.add_parser("export-pkg", help="导出 .skillpkg")
    export_pkg_p.add_argument("--names", required=True)
    export_pkg_p.add_argument("--output")
    export_pkg_p.set_defaults(func=cmd_export_pkg)

    import_pkg_p = sub.add_parser("import-pkg", help="导入 .skillpkg")
    import_pkg_p.add_argument("--package", required=True)
    import_pkg_p.add_argument("--scope", default="agents")
    import_pkg_p.add_argument("--overwrite", action="store_true")
    import_pkg_p.set_defaults(func=cmd_import_pkg)

    search_p = sub.add_parser("search", help="模糊搜索 skill")
    search_p.add_argument("query")
    search_p.add_argument("--limit", type=int, default=10)
    search_p.set_defaults(func=cmd_search)

    fork_p = sub.add_parser("fork", help="复制已有 skill 并改名")
    fork_p.add_argument("--source", required=True)
    fork_p.add_argument("--name", required=True)
    fork_p.add_argument("--scope", default="agents")
    fork_p.add_argument("--description")
    fork_p.set_defaults(func=cmd_fork)

    templates_p = sub.add_parser("templates", help="查看内置模板")
    templates_p.set_defaults(func=cmd_templates)

    from_template_p = sub.add_parser("from-template", help="从模板创建 skill")
    from_template_p.add_argument("--template", required=True)
    from_template_p.add_argument("--name")
    from_template_p.add_argument("--scope", default="agents")
    from_template_p.set_defaults(func=cmd_from_template)

    deps_p = sub.add_parser("deps", help="查看缺失依赖")
    deps_p.add_argument("--name")
    deps_p.set_defaults(func=cmd_deps)

    install_deps_p = sub.add_parser("install-deps", help="安装指定 skill 的缺失 Python 依赖")
    install_deps_p.add_argument("--name", required=True)
    install_deps_p.add_argument("--yes", action="store_true")
    install_deps_p.set_defaults(func=cmd_install_deps)

    set_source_p = sub.add_parser("set-source", help="为 skill 设置自定义远程更新源")
    set_source_p.add_argument("--name", required=True)
    set_source_p.add_argument("--url", required=True)
    set_source_p.add_argument("--type", choices=["github", "well-known"], default="github")
    set_source_p.add_argument("--skill-path")
    set_source_p.set_defaults(func=cmd_set_source)

    snapshot_p = sub.add_parser("snapshot", help="导出本机 Skill 环境快照")
    snapshot_p.add_argument("--output")
    snapshot_p.set_defaults(func=cmd_snapshot)

    diff_snapshot_p = sub.add_parser("diff-snapshot", help="对比另一台机器导出的快照")
    diff_snapshot_p.add_argument("--snapshot", required=True)
    diff_snapshot_p.set_defaults(func=cmd_diff_snapshot)

    cleanup_plan_p = sub.add_parser("cleanup-plan", help="生成智能清理计划")
    cleanup_plan_p.add_argument("--refresh", action="store_true")
    cleanup_plan_p.set_defaults(func=cmd_cleanup_plan)

    auto_cleanup_p = sub.add_parser("auto-cleanup", help="按清理计划移入回收站")
    auto_cleanup_p.add_argument("--names")
    auto_cleanup_p.add_argument("--refresh", action="store_true")
    auto_cleanup_p.add_argument("--yes", action="store_true")
    auto_cleanup_p.set_defaults(func=cmd_auto_cleanup)

    serve_p = sub.add_parser("serve", help="启动 Web 面板")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=5520)
    serve_p.add_argument("--no-browser", action="store_true", help="启动服务但不自动打开浏览器")
    serve_p.set_defaults(func=cmd_serve)

    usage_collect_p = sub.add_parser("usage-collect", help="采集本机 skill 使用事件")
    usage_collect_p.set_defaults(func=cmd_usage_collect)

    usage_stats_p = sub.add_parser("usage-stats", help="查看 skill 使用统计")
    usage_stats_p.add_argument("--refresh", action="store_true", help="采集后再统计")
    usage_stats_p.set_defaults(func=cmd_usage_stats)

    usage_hooks_p = sub.add_parser("usage-hooks-install", help="安装 Claude/Codex 使用统计 hooks")
    usage_hooks_p.set_defaults(func=cmd_usage_hooks_install)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        return cmd_interactive()
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc), "github": GITHUB_URL}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
