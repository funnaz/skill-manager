# Security Policy

Skill Manager is a local-first tool. It scans and modifies files under local Agent skill directories such as
`~/.agents/skills`, `~/.grok/skills`, `~/.codex/skills`, `~/.claude/skills`, and `~/.cursor/skills`.

## Local Web Dashboard

The dashboard binds to `127.0.0.1` by default. API requests under `/api/*` require an in-memory local token returned to
the same-origin dashboard by `/api/session`.

You can provide your own token:

```bash
SKILL_MANAGER_TOKEN=your-random-token skill-manager serve
```

Do not expose the dashboard on a public network unless you understand the risk. If you intentionally bind to
`0.0.0.0`, put it behind your own authentication and network controls.

## Local Data

Skill Manager stores local state under:

- `~/.agents/.skill-lock.json`
- `~/.skill-manager/settings.json`
- `~/.skill-manager/backups/`
- `~/.skill-manager/trash/`
- `~/.skill-manager/audit.log`
- `~/.skill-manager/usage-events.jsonl`
- `~/.skill-manager/usage-scan-state.json`

No cloud service is contacted except when you explicitly install or check updates from remote sources such as GitHub or
well-known skill URLs.

## Usage Statistics

Usage statistics are local and opt-in from the dashboard or CLI. Collection reads local Grok, Codex, and Claude session
logs and stores normalized events locally. It records skill name, agent name, event time, event type, session id, source
file, and path snippets that identify `SKILL.md` reads. It does not upload these events.

To remove collected events:

```bash
rm ~/.skill-manager/usage-events.jsonl ~/.skill-manager/usage-scan-state.json
```

## Reporting Issues

Please report security issues privately to the repository owner before opening a public issue. Include:

- operating system and Python version
- command or dashboard action used
- affected file paths, with sensitive names redacted
- expected and actual behavior
