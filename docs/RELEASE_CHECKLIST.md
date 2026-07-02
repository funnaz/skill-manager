# Release Checklist

Use this before publishing a new GitHub release.

## Documentation

- `README.md` describes the current dashboard and CLI.
- `docs/USER_GUIDE.md` covers normal web usage.
- `docs/CLI_REFERENCE.md` covers command examples.
- `CHANGELOG.md` has a new version entry.
- `SECURITY.md` lists all local data locations.

## Local Data

Do not commit:

- `.venv/`
- `.pytest_cache/`
- `.ruff_cache/`
- `__pycache__/`
- `skill_manager.egg-info/`
- local reports such as `.docx`, `.pdf`, `.csv`, `.html`
- local backups, trash, or usage event files

## Checks

```bash
python -m pytest
python -m ruff check .
python -m compileall .
```

## Publish

```bash
git status -sb
git checkout -b codex/<description>
git add <intended files>
git commit -m "<description>"
git push -u origin codex/<description>
```

Open a draft pull request first unless the release is trivial.
