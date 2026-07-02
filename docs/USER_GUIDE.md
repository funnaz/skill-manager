# Skill Manager User Guide

Default dashboard URL:

```text
http://127.0.0.1:5520
```

This guide explains the dashboard in normal user terms. You can use Skill Manager without touching code.

## 1. Open the Dashboard

Start the app:

```bash
python cli.py serve --port 5520
```

Then open:

```text
http://127.0.0.1:5520
```

The first screen contains:

| Area | What it does |
| --- | --- |
| Top actions | Scan, usage stats, update, batch upgrade, export, backup, trash, audit, create, install |
| Stats cards | Total skills, updatable skills, shared skills, disabled skills |
| Left filters | Filter by Agent or category |
| Skill list | Click a skill to inspect it |
| Detail panel | Metadata, health check, conflicts, dependencies, and raw `SKILL.md` |

## 2. Daily Workflow

Use this routine when you want to understand or clean your local skills:

1. Click **重新扫描**.
2. Click **刷新使用统计**.
3. Review total, shared, disabled, and updatable counts.
4. Filter by Agent or category.
5. Open suspicious or low-quality skills.
6. Disable skills you are unsure about.
7. Delete only when you are confident, and use trash recovery if needed.
8. Export a report after major cleanup.

## 3. Inspect a Skill

Click any skill in the middle list. The detail panel shows:

| Field | Meaning |
| --- | --- |
| Folder | Local folder name |
| Category | Shared, user custom, bundled, marketplace, and similar categories |
| Path | Real local path |
| Source | Known install source or update source |
| Local version | Version in local `SKILL.md` |
| Remote version | Version found from the update source |
| Update status | Whether it is checked, clean, modified, or updatable |
| Deletable | Whether Skill Manager considers it safe to delete |

## 4. Health Check

The health panel is a practical quality check for `SKILL.md`.

| Item | Meaning |
| --- | --- |
| Score | A rough completeness score from 0 to 100 |
| Triggers | Words or phrases likely to activate the skill |
| Conflicts | Trigger overlap with other skills |
| Missing dependencies | Python packages detected but not installed |
| Issues | Specific warnings to inspect |

Common fixes:

| Problem | Fix |
| --- | --- |
| Missing examples | Add one to three real usage examples to `SKILL.md` |
| Trigger conflicts | Make trigger phrases more specific |
| Missing dependencies | Confirm they are needed, then install dependencies |
| Low score but still useful | Keep it and improve later |

## 5. Usage Statistics

Click **刷新使用统计** to summarize locally observable Agent activity.

Skill Manager can read local Grok, Codex, and Claude logs where available. It records normalized local events under `~/.skill-manager/usage-events.jsonl`.

Use this panel to answer:

1. Which skills are frequently used?
2. Which skills have not been used recently?
3. Which Agent uses which skills?
4. Which cleanup candidates are low-risk?

If the dashboard shows that hooks are not installed, click **安装统计 Hooks**. Statistics improve after future Agent sessions.

## 6. Create a Skill

Click **新建 Skill**.

Recommended steps:

1. Paste a full `SKILL.md`, or drag in a Markdown file.
2. Click **分析内容**.
3. Review the parsed name and description.
4. Choose an install location.
5. Click **创建**.
6. Click **重新扫描**.

Naming tips:

| Good | Avoid |
| --- | --- |
| `wechat-public-account-coach` | `我的公众号工具` |
| `xhs-title-generator` | `标题` |
| `lark-doc-helper` | `飞书` |

Prefer lowercase English words joined with hyphens. This works better across GitHub, command lines, and Agent hosts.

## 7. Install a Skill

Click **安装 Skill**.

You can install from:

| Source | Use when |
| --- | --- |
| Local folder | You already downloaded a skill folder |
| GitHub repository | You have a repository URL containing `SKILL.md` |

Prefer installing to **Shared Agents** if you want Codex, Claude Code, Grok Build, and other tools to share one copy.

## 8. Check Updates

Click **检查更新**. This only checks remote sources; it does not modify local files.

Update results are grouped by risk:

| Group | Meaning | Action |
| --- | --- | --- |
| Official version update | Remote is newer and local copy is clean | Direct upgrade |
| Local changes only | Local files changed, remote is not newer | Inspect or keep |
| Merge recommended | Remote changed and local files also changed | Integrated merge |

## 9. Direct Upgrade, Merge, and Batch Upgrade

### Direct Upgrade

Use direct upgrade for clean official updates. Skill Manager creates a backup first.

### Integrated Merge

Use merge when you customized a skill locally and the remote version also changed. Merge tries to preserve local customizations while bringing in remote updates.

### Batch Upgrade

Batch upgrade is threaded. It processes clean direct-upgrade candidates in parallel.

Batch upgrade skips merge-needed skills on purpose. If it reports `0` successes, it usually means there are no safe direct-upgrade candidates. Open the update report and handle merge-needed skills one by one.

## 10. Disable, Delete, and Trash

If you are unsure, disable first. Deleting is for skills that are clearly duplicated, migrated, or unused.

| Situation | Recommended action |
| --- | --- |
| Might need it later | Disable |
| Duplicate or migrated | Delete to trash |
| Deleted by mistake | Restore from trash |
| Definitely no longer needed | Purge trash later |

Normal delete moves the skill to `~/.skill-manager/trash/`. Hard delete requires explicit force from the CLI.

## 11. Backup and Restore

Risky operations create backups under `~/.skill-manager/backups/`.

Use **备份恢复** when:

1. An upgrade behaves worse than before.
2. A merge lost a local customization.
3. You manually edited `SKILL.md` and want to roll back.

Restore creates another backup of the current copy before overwriting it.

## 12. Operation Log

Click **操作日志** to inspect create, install, delete, restore, merge, upgrade, and similar events.

Use the log when you need to know what changed recently.

## 13. Export Reports

Click **导出报告** and choose a format:

| Format | Best for |
| --- | --- |
| Word `.docx` | Sharing with teammates |
| Markdown `.md` | Knowledge base or GitHub |
| PDF `.pdf` | Read-only review |
| CSV `.csv` | Spreadsheet analysis |
| HTML `.html` | Browser report |

**只读分享** opens a local read-only HTML report. It is useful for quick review on your own machine. Do not treat it as a public website.

## 14. Privacy

Skill Manager is local-first:

- It does not require an account.
- It does not upload your skills.
- Usage statistics are stored locally.
- Remote network calls happen only when you install or check updates from remote sources.

Do not expose the dashboard to the public internet without your own authentication and network controls.

## 15. Troubleshooting

### The dashboard does not open

Confirm the server is running and the URL is:

```text
http://127.0.0.1:5520
```

### Batch upgrade says 0 successes

Open the update report. If items need merge, batch upgrade skipped them intentionally.

### A skill appears under multiple Agents

That is normal for shared skills under `~/.agents/skills`.

### Delete did not remove a skill permanently

Normal delete uses trash. Open **回收站** or use the CLI to purge later.

### Update checking is slow

Skill Manager may need to clone or fetch remote repositories and compare content hashes. Network speed and repository size affect runtime.

## 16. Short Routine

```text
Rescan -> Refresh usage -> Check updates -> Upgrade clean items -> Merge customized items -> Disable uncertain items -> Delete only when confident
```
