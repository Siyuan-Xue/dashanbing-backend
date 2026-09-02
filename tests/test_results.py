from app.services.results import build_product_result


def test_product_result_exposes_only_supported_aggregate_events():
    """Catches leaking identities or silently treating unsupported actions as supported."""
    report = {
        "clips": [
            {
                "clip_id": "stu_00:1",
                "student_id": "stu_00",
                "participant_ids": ["stu_00"],
                "action_type": "jump_shot",
                "start_ms": 1_000,
                "end_ms": 2_000,
                "release_ms": 1_700,
            },
            {
                "clip_id": "stu_01:1",
                "student_id": "stu_01",
                "participant_ids": ["stu_01", "stu_02"],
                "action_type": "pass",
                "start_ms": 2_500,
                "end_ms": 3_000,
                "release_ms": None,
            },
            {
                "clip_id": "stu_03:1",
                "student_id": "stu_03",
                "participant_ids": ["stu_03"],
                "action_type": "unknown",
                "start_ms": 4_000,
                "end_ms": 4_500,
                "release_ms": None,
            },
        ],
        "shot_outcomes": [
            {"clip_id": "stu_00:1", "made": True},
            {"clip_id": "obsolete:9", "made": False},
        ],
        "shot_stats": {
            "attempts": 2,
            "makes": 1,
            "misses": 1,
            "undetermined": 0,
        },
    }
    summary = {"student_ids": ["stu_00", "stu_01", "stu_02", "stu_03"]}

    result = build_product_result(report=report, summary=summary, media={"phases": "/media/phases"})

    assert result.model_dump(mode="json") == {
        "registered_participant_count": 4,
        "action_counts": {
            "triple_threat": 0,
            "free_throw": 0,
            "jump_shot": 1,
            "layup": 0,
        },
        "unsupported_event_count": 2,
        "shots": {
            "attempts": 2,
            "makes": 1,
            "misses": 1,
            "undetermined": 0,
            "make_rate": 0.5,
            "unlinked_outcomes": 1,
        },
        "events": [
            {
                "event_index": 1,
                "action_type": "jump_shot",
                "start_ms": 1000.0,
                "end_ms": 2000.0,
                "time_ms": 1700.0,
                "result": "make",
            }
        ],
        "media": {"phases": "/media/phases"},
        "warnings": [
            "2 个事件属于当前版本未支持的动作类型。",
            "1 个投篮结果无法可靠关联到最终动作片段。",
        ],
        "disclaimer": "AI 识别结果，仅供训练复盘。",
    }
    serialized = result.model_dump_json()
    assert "stu_" not in serialized
    assert "student_id" not in serialized


def test_product_result_uses_null_make_rate_when_no_attempts():
    """Catches rendering a misleading 0% shooting rate when there were no attempts."""
    result = build_product_result(
        report={
            "clips": [],
            "shot_outcomes": [],
            "shot_stats": {"attempts": 0, "makes": 0, "misses": 0, "undetermined": 0},
        },
        summary={"student_ids": []},
        media={},
    )

    assert result.shots.make_rate is None
    assert result.events == []


def test_product_result_keeps_shot_totals_independent_from_action_count():
    """Catches forcing shot attempts to equal the number of supported action clips."""
    result = build_product_result(
        report={
            "clips": [
                {
                    "clip_id": "clip-1",
                    "action_type": "layup",
                    "start_ms": 100,
                    "end_ms": 200,
                    "release_ms": 180,
                }
            ],
            "shot_outcomes": [
                {"clip_id": "old-1", "made": True},
                {"clip_id": "old-2", "made": False},
            ],
            "shot_stats": {"attempts": 2, "makes": 1, "misses": 1, "undetermined": 0},
        },
        summary={"student_ids": ["stu_00"]},
        media={},
    )

    assert result.action_counts.layup == 1
    assert result.shots.attempts == 2
    assert result.shots.unlinked_outcomes == 2
