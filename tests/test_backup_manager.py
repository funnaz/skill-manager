import backup_manager


def test_list_and_restore_backup(tmp_path, monkeypatch):
    backup_root = tmp_path / "backups"
    backup = backup_root / "demo-skill-20260702-120000"
    backup.mkdir(parents=True)
    (backup / "SKILL.md").write_text("---\nname: demo-skill\ndescription: Old\n---\n", encoding="utf-8")

    target = tmp_path / "skills" / "demo-skill"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text("---\nname: demo-skill\ndescription: New\n---\n", encoding="utf-8")

    monkeypatch.setattr(backup_manager, "BACKUP_ROOT", backup_root)

    backups = backup_manager.list_backups()
    result = backup_manager.restore_backup(backups[0]["id"], str(target))

    assert backups[0]["name"] == "demo-skill"
    assert result["ok"] is True
    assert "description: Old" in (target / "SKILL.md").read_text(encoding="utf-8")
    assert result["safety_backup"]
