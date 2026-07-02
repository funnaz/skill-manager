from health_analyzer import analyze_skill_quality, build_conflicts


def test_health_analyzer_detects_missing_env_and_triggers(monkeypatch):
    monkeypatch.delenv("DEMO_API_KEY", raising=False)
    meta = {"name": "demo", "description": "Trigger: /demo", "env_vars": ["DEMO_API_KEY"]}
    body = "# Demo\n\nUse /demo for testing."

    result = analyze_skill_quality(meta, body)

    assert "/demo" in result["triggers"]
    assert "DEMO_API_KEY" in result["dependencies"]["missing_env"]
    assert result["score"] < 100


def test_build_conflicts_groups_same_trigger():
    conflicts = build_conflicts(
        [
            {"name": "a", "folder_name": "a", "resolved_path": "a", "triggers": ["/same"]},
            {"name": "b", "folder_name": "b", "resolved_path": "b", "triggers": ["/same"]},
        ]
    )

    assert "/same" in conflicts
    assert len(conflicts["/same"]) == 2
