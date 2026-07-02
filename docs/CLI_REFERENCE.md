# CLI Reference

Use `python cli.py <command>` from the repository root, or `skill-manager <command>` after installing the package.

## Dashboard

```bash
python cli.py serve --host 127.0.0.1 --port 5520
```

## Scan

```bash
python cli.py scan
```

## Create

```bash
python cli.py create --name my-skill --description "What it does" --scope agents
python cli.py create --from-md ./SKILL.md --scope agents
```

## Install

```bash
python cli.py install --from-path "C:/path/to/skill" --scope agents
python cli.py install --git "https://github.com/user/repo.git" --subpath "skills/my-skill" --scope agents
```

Scopes:

```text
agents, grok, claude, codex, cursor
```

## Disable and Enable

```bash
python cli.py disable --name my-skill
python cli.py enable --name my-skill
python cli.py batch-disable --names "a,b,c"
python cli.py batch-enable --names "a,b,c"
```

## Delete and Trash

```bash
python cli.py delete --name old-skill --dry-run
python cli.py delete --name old-skill
python cli.py delete --name old-skill --force
python cli.py trash
python cli.py trash-restore --trash-id old-skill-20260702-120000
python cli.py trash-purge --trash-id old-skill-20260702-120000
python cli.py trash-purge
```

## Update

```bash
python cli.py check-updates
python cli.py check-updates --names "a,b"
python cli.py upgrade --name a
python cli.py merge --name a
python cli.py batch-upgrade --workers 4
python cli.py set-source --name a --url "https://github.com/user/repo.git" --type github
```

Batch upgrade skips merge-needed skills.

## Backups

```bash
python cli.py backups
python cli.py restore --backup-id "skill-20260702-120000"
python cli.py restore --backup-id "skill-20260702-120000" --target-path "C:/Users/me/.agents/skills/skill"
```

## Reports

```bash
python cli.py export --format markdown --lang zh --output skill-report.md
python cli.py export --format docx --lang en --output skill-report.docx
python cli.py export --format pdf --lang zh --output skill-report.pdf
python cli.py export --format csv --output skill-report.csv
python cli.py export --format html --output skill-report.html
```

## Packages

```bash
python cli.py export-pkg --names "a,b" --output skills.skillpkg
python cli.py import-pkg --package skills.skillpkg --scope agents
```

## Search, Fork, Templates

```bash
python cli.py search "excel"
python cli.py fork --source xlsx --name xlsx-custom --scope agents
python cli.py templates
python cli.py from-template --template code-review --name my-code-review --scope agents
```

## Dependencies

```bash
python cli.py deps
python cli.py deps --name my-skill
python cli.py install-deps --name my-skill --yes
```

## Usage Statistics

```bash
python cli.py usage-collect
python cli.py usage-stats --refresh
python cli.py usage-hooks-install
```

## Audit, Snapshot, Cleanup

```bash
python cli.py audit --limit 100
python cli.py snapshot --output current.json
python cli.py diff-snapshot --snapshot other-machine.json
python cli.py cleanup-plan --refresh
python cli.py auto-cleanup --names "a,b" --yes
python cli.py auto-cleanup --yes
```
