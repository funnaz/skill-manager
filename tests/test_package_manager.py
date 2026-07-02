import zipfile

import package_manager


def test_export_skillpkg_writes_metadata_and_files(tmp_path, monkeypatch):
    skill_dir = tmp_path / "demo"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: demo\n---\n# Demo\n", encoding="utf-8")
    monkeypatch.setattr(
        package_manager,
        "scan_all",
        lambda: {
            "skills": [
                {
                    "name": "demo",
                    "folder_name": "demo",
                    "category": "custom",
                    "resolved_path": str(skill_dir),
                    "source": None,
                    "source_type": None,
                }
            ]
        },
    )
    monkeypatch.setattr(package_manager, "append_audit", lambda *args, **kwargs: {})

    output = tmp_path / "demo.skillpkg"
    result = package_manager.export_skillpkg(["demo"], str(output))

    assert result["ok"] is True
    with zipfile.ZipFile(output) as archive:
        assert "skillpkg.json" in archive.namelist()
        assert "skills/demo/SKILL.md" in archive.namelist()
