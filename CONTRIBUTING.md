# Contributing

Thanks for improving Skill Manager.

## Development Setup

```bash
git clone https://github.com/funnaz/skill-manager.git
cd skill-manager
python -m venv .venv
.\.venv\Scripts\Activate.ps1  # Windows
python -m pip install -e ".[dev]"
```

On macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Checks

Run these before opening a pull request:

```bash
python -m pytest
python -m ruff check .
python -m compileall .
```

## Pull Request Guidelines

- Keep changes focused on one behavior or workflow.
- Add or update tests for scanner, manager, updater, report, and parser changes.
- Do not commit local user data from `~/.skill-manager`, `~/.agents`, `.grok`, `.codex`, `.claude`, or `.cursor`.
- For destructive operations such as delete, upgrade, merge, and restore, include a dry-run or backup story.
- Update `README.md` and `CHANGELOG.md` when behavior changes.

## Local Testing Notes

Tests should use temporary directories and monkeypatch module-level paths. Do not read or modify the contributor's real
Agent skill directories in tests.
