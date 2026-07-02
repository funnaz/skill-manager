import trash_manager


def test_move_and_restore_trash(tmp_path, monkeypatch):
    trash_root = tmp_path / "trash"
    monkeypatch.setattr(trash_manager, "TRASH_ROOT", trash_root)
    monkeypatch.setattr(trash_manager, "TRASH_INDEX", trash_root / "index.json")

    target = tmp_path / "skills" / "demo"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text("---\nname: demo\n---\n", encoding="utf-8")

    item = trash_manager.move_to_trash(target, "demo")
    assert not target.exists()
    assert trash_manager.list_trash()[0]["id"] == item["id"]

    result = trash_manager.restore_from_trash(item["id"])
    assert result["ok"] is True
    assert (target / "SKILL.md").exists()
