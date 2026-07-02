# Skill Manager

Local-first dashboard and CLI for managing Agent Skills across Grok Build, Claude Code, OpenAI Codex, Cursor, and shared `~/.agents/skills` directories.

Skill Manager helps you see what skills are installed, where they are mounted, which ones are used, which ones can be updated, and which ones are safe to disable, back up, restore, or remove.

GitHub: https://github.com/funnaz/skill-manager  
License: MIT

## Highlights

- Web dashboard on `http://127.0.0.1:5520`
- Local API token protection for `/api/*`
- Scan Grok, Claude Code, OpenAI Codex, Cursor, and shared skills
- Create skills from Markdown
- Install skills from local folders or GitHub repositories
- Check updates from GitHub and well-known remote skill sources
- Direct upgrade for clean skills
- Integrated merge for locally modified skills
- Threaded batch upgrade with safe skipping for merge-needed skills
- Backup and restore for risky operations
- Trash-based delete and restore
- Disable and enable skills
- Trigger conflict detection
- Dependency detection and optional install
- Health scoring for `SKILL.md`
- Local usage statistics from observable local Agent logs
- Operation audit log
- `.skillpkg` import/export
- Snapshot, diff, templates, fork, fuzzy search, and cleanup planning
- Export reports as Word, Markdown, PDF, CSV, HTML, or read-only web report

## Supported Agents

| Agent | Default paths |
| --- | --- |
| Grok Build | `~/.grok/skills`, bundled skills, marketplace cache |
| Shared Agents | `~/.agents/skills` |
| Claude Code | `~/.claude/skills` |
| OpenAI Codex | `~/.codex/skills` |
| Cursor | `~/.cursor/skills` |

## Quick Start

### Run from source

```bash
git clone https://github.com/funnaz/skill-manager.git
cd skill-manager
python -m pip install -r requirements.txt
python cli.py serve --port 5520
```

Open:

```text
http://127.0.0.1:5520
```

### Install as a command

```bash
python -m pip install -e .
skill-manager serve --port 5520
```

### Install as an Agent Skill

```bash
python cli.py install --git "https://github.com/funnaz/skill-manager.git" --scope agents
```

Valid scopes:

```text
agents, grok, claude, codex, cursor
```

Windows helper:

```powershell
.\scripts\install.ps1 -Scope agents
```

macOS/Linux helper:

```bash
./scripts/install.sh agents
```

## Web Dashboard

The dashboard is designed for normal daily use:

1. Click **重新扫描** to refresh local skills.
2. Use the left filters to narrow by Agent or category.
3. Select a skill to inspect metadata, health, conflicts, dependencies, and raw `SKILL.md`.
4. Use **检查更新** before upgrading.
5. Use **整合更新** for locally modified skills.
6. Use **备份恢复** or **回收站** if you need to undo a risky operation.

See the full user guide: [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

## Common CLI Commands

```bash
# Scan local skills
python cli.py scan

# Start dashboard
python cli.py serve --host 127.0.0.1 --port 5520

# Create a skill
python cli.py create --name my-skill --description "What it does and when to trigger" --scope agents
python cli.py create --from-md ./draft.md --scope agents

# Install a skill
python cli.py install --from-path "C:/path/to/skill" --scope agents
python cli.py install --git "https://github.com/user/repo.git" --subpath "skills/my-skill" --scope agents

# Delete safely through trash
python cli.py delete --name old-skill --dry-run
python cli.py delete --name old-skill
python cli.py trash
python cli.py trash-restore --trash-id old-skill-20260702-120000

# Update and merge
python cli.py check-updates
python cli.py check-updates --names "dbs,lark-doc"
python cli.py upgrade --name dbs
python cli.py batch-upgrade --workers 4
python cli.py merge --name lark-doc
python cli.py set-source --name my-skill --url "https://github.com/user/repo.git" --type github

# Backups
python cli.py backups
python cli.py restore --backup-id "lark-doc-20260702-123000"

# Dependencies, conflicts, and health
python cli.py deps
python cli.py deps --name my-skill
python cli.py install-deps --name my-skill --yes

# Usage statistics
python cli.py usage-collect
python cli.py usage-stats --refresh
python cli.py usage-hooks-install

# Reports
python cli.py export --format markdown --lang zh --output skill-report.md
python cli.py export --format docx --lang en --output skill-report.docx
python cli.py export --format csv --output skill-report.csv
python cli.py export --format html --output skill-report.html

# Skill packages
python cli.py export-pkg --names "skill-a,skill-b" --output skills.skillpkg
python cli.py import-pkg --package skills.skillpkg --scope agents

# Search, fork, templates
python cli.py search "excel"
python cli.py fork --source xlsx --name xlsx-custom --scope agents
python cli.py templates
python cli.py from-template --template code-review --name my-code-review

# Audit, snapshots, cleanup
python cli.py audit --limit 50
python cli.py snapshot --output office-pc.json
python cli.py diff-snapshot --snapshot office-pc.json
python cli.py cleanup-plan --refresh
python cli.py auto-cleanup --yes
```

## Upgrade Behavior

Update results are grouped by risk:

| Status | Meaning | Recommended action |
| --- | --- | --- |
| Official update | Remote version changed and local copy is clean | Direct upgrade |
| Local changes only | You changed local files; remote has no newer version | Keep or inspect |
| Merge recommended | Remote changed and local files were modified | Use integrated merge |

Batch upgrade is threaded. It upgrades clean direct-upgrade candidates and skips merge-needed skills so local customizations are not overwritten. If batch upgrade reports `0` successes, usually every pending item needs manual merge rather than direct upgrade.

## Safety Model

Skill Manager is intentionally conservative:

- The web app binds to `127.0.0.1` by default.
- API requests require a local session token.
- Delete uses trash by default.
- Merge, restore, and other overwrite-like operations create backups first.
- Protected bundled and marketplace skills are not deleted.
- Usage statistics stay local.

Customize the local API token:

```bash
SKILL_MANAGER_TOKEN=your-random-token python cli.py serve
```

Do not expose the dashboard directly to the public internet. If you bind to `0.0.0.0`, put it behind your own authentication and network controls.

## Local Data and Privacy

Skill Manager does not require an account and does not upload local skill data. It stores local state in:

| Path | Purpose |
| --- | --- |
| `~/.agents/.skill-lock.json` | Install source, update source, hashes, timestamps |
| `~/.skill-manager/settings.json` | Dashboard and install preferences |
| `~/.skill-manager/backups/` | Backups before risky operations |
| `~/.skill-manager/trash/` | Trash for deleted skills |
| `~/.skill-manager/audit.log` | Operation log |
| `~/.skill-manager/usage-events.jsonl` | Local usage events |
| `~/.skill-manager/usage-scan-state.json` | Incremental usage scan state |

Clear usage statistics:

```bash
rm ~/.skill-manager/usage-events.jsonl ~/.skill-manager/usage-scan-state.json
```

Windows PowerShell:

```powershell
Remove-Item "$env:USERPROFILE\.skill-manager\usage-events.jsonl","$env:USERPROFILE\.skill-manager\usage-scan-state.json" -ErrorAction SilentlyContinue
```

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
python -m compileall .
```

Useful docs:

- [docs/USER_GUIDE.md](docs/USER_GUIDE.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [SECURITY.md](SECURITY.md)
- [CHANGELOG.md](CHANGELOG.md)

## Project Structure

```text
skill-manager/
  cli.py
  server.py
  scanner.py
  manager.py
  updater.py
  diff_util.py
  backup_manager.py
  trash_manager.py
  usage_collector.py
  usage_insights.py
  report.py
  static/index.html
  scripts/install.ps1
  scripts/install.sh
  docs/USER_GUIDE.md
```
