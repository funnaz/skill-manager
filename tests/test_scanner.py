import scanner


def test_scan_all_maps_shared_skill_to_multiple_agents(tmp_path, monkeypatch):
    shared = tmp_path / ".agents" / "skills" / "demo-skill"
    shared.mkdir(parents=True)
    (shared / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Demo skill\n---\n\n# Demo\n",
        encoding="utf-8",
    )

    profiles = {
        "grok": {
            "label": "Grok Build",
            "short": "Grok",
            "color": "#000",
            "scan_roots": [shared.parent],
            "extra_globs": [],
        },
        "codex": {
            "label": "OpenAI Codex",
            "short": "Codex",
            "color": "#000",
            "scan_roots": [shared.parent],
            "extra_globs": [],
        },
    }
    monkeypatch.setattr(scanner, "AGENT_PROFILES", profiles)
    monkeypatch.setattr(scanner, "CUSTOM_SCAN_ROOTS", ())
    monkeypatch.setattr(scanner, "_load_disabled_skills", lambda: set())
    monkeypatch.setattr(scanner, "_load_skill_lock", lambda: {})

    data = scanner.scan_all()

    assert data["totals"]["skills"] == 1
    assert data["totals"]["shared_skills"] == 1
    assert data["skills"][0]["agents"] == ["codex", "grok"]
