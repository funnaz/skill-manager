from pathlib import Path

import manager


def test_create_skill_writes_skill_md_and_lock(tmp_path, monkeypatch):
    agents_root = tmp_path / ".agents" / "skills"
    lock_path = tmp_path / ".agents" / ".skill-lock.json"
    monkeypatch.setitem(manager.SCOPES, "agents", agents_root)
    monkeypatch.setattr(manager, "LOCK_PATH", lock_path)

    result = manager.create_skill("demo-skill", "Demo description", "agents")

    assert result["ok"] is True
    assert (agents_root / "demo-skill" / "SKILL.md").exists()
    assert "demo-skill" in lock_path.read_text(encoding="utf-8")


def test_delete_skill_dry_run_does_not_remove_directory(tmp_path, monkeypatch):
    skill_dir = tmp_path / "skills" / "demo-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: demo-skill\ndescription: Demo\n---\n", encoding="utf-8")
    monkeypatch.setattr(manager, "_find_junctions", lambda target: [])
    monkeypatch.setattr(
        manager,
        "scan_all",
        lambda: {
            "skills": [
                {
                    "name": "demo-skill",
                    "folder_name": "demo-skill",
                    "category": "agents-shared",
                    "resolved_path": str(skill_dir),
                }
            ]
        },
    )

    result = manager.delete_skill(name="demo-skill", dry_run=True)

    assert result["dry_run"] is True
    assert Path(result["path"]).exists()
    assert (skill_dir / "SKILL.md").exists()
