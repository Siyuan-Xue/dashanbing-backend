from copy import deepcopy

import pytest


def fixture():
    return {
        "clips": [
            {"clip_id": "b:0", "student_id": "b", "action_type": "layup", "release_ms": 10000},
            {"clip_id": "b:1", "student_id": "b", "action_type": "layup", "release_ms": 20000},
        ],
        "shot_outcomes": [
            {"clip_id": "a:1", "student_id": "a", "action_type": "layup", "anchor_timestamp_ms": 11600, "made": True},
            {"clip_id": "a:3", "student_id": "a", "action_type": "layup", "anchor_timestamp_ms": 21600, "made": False},
        ],
        "shot_stats": {"attempts": 2, "makes": 1, "misses": 1},
    }


def test_repair_uses_unique_time_evidence_and_preserves_scoring():
    from scripts.repair_v3_presets import repair_report
    original = fixture()
    repaired, audit = repair_report(original, 0)
    assert original == fixture()
    assert [o["clip_id"] for o in repaired["shot_outcomes"]] == ["b:0", "b:1"]
    assert [o["student_id"] for o in repaired["shot_outcomes"]] == ["b", "b"]
    assert repaired["shot_stats"] == original["shot_stats"]
    assert repaired["clips"] == original["clips"]
    for before, after in zip(original["shot_outcomes"], repaired["shot_outcomes"]):
        assert {k: v for k, v in before.items() if k not in {"clip_id", "student_id"}} == {
            k: v for k, v in after.items() if k not in {"clip_id", "student_id"}}
    assert len(audit) == 2
    assert repair_report(repaired, 0)[0] == repaired


@pytest.mark.parametrize("case", ["ambiguous", "missing", "duplicate", "clock"])
def test_repair_refuses_to_guess_or_drop_outcomes(case):
    from scripts.repair_v3_presets import repair_report
    data = fixture()
    if case == "ambiguous": data["clips"][1]["release_ms"] = 10500
    if case == "missing": data["shot_outcomes"].pop()
    if case == "duplicate": data["shot_outcomes"][1] = deepcopy(data["shot_outcomes"][0])
    if case == "clock": data["shot_outcomes"][0]["anchor_timestamp_ms"] += 60000
    with pytest.raises(ValueError): repair_report(data, 0)


def test_repair_uses_camera_sync_before_associating():
    from scripts.repair_v3_presets import repair_report
    data = fixture()
    for o in data["shot_outcomes"]: o["anchor_timestamp_ms"] += 60000
    assert [o["clip_id"] for o in repair_report(data, 60000)[0]["shot_outcomes"]] == ["b:0", "b:1"]
