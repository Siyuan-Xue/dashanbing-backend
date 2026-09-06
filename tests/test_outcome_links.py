from copy import deepcopy

import pytest

from app.services.results import build_product_result
from app.services.analyst_facts import build_analyst_facts


def report():
    return {
        "clips": [{"clip_id": "a:1", "student_id": "a", "action_type": "layup",
                   "start_ms": 20000, "end_ms": 22300, "release_ms": 21600}],
        "shot_outcomes": [{"clip_id": "a:1", "student_id": "a", "action_type": "layup",
                           "anchor_timestamp_ms": 23000, "made": True,
                           "metadata": {"source": "clip_segment_aligned", "clock_offset_ms": 0}}],
        "shot_stats": {"attempts": 1, "makes": 1, "misses": 0, "undetermined": 0},
    }


@pytest.mark.parametrize("change", [
    {"student_id": "b"}, {"action_type": "jump_shot"},
    {"anchor_timestamp_ms": 12366}, {"anchor_timestamp_ms": 65000},
])
def test_reused_id_with_incompatible_evidence_is_unlinked_in_both_views(change):
    data = report()
    data["shot_outcomes"][0].update(change)
    result = build_product_result(report=data, summary={}, media={})
    facts = build_analyst_facts(data, {})
    assert result.events[0].result is None
    assert facts.evidence[0].result == "undetermined"
    assert result.shots.unlinked_outcomes == facts.metrics.shots.unlinked_outcomes == 1
    assert result.shots.makes == facts.metrics.shots.makes == 1


def test_valid_delayed_ball_evidence_and_clock_offset_remain_linked():
    data = report()
    data["shot_outcomes"][0]["anchor_timestamp_ms"] += 60000
    data["shot_outcomes"][0]["metadata"]["clock_offset_ms"] = 60000
    assert build_product_result(report=data, summary={}, media={}).events[0].result == "make"
    assert build_analyst_facts(data, {}).evidence[0].result == "make"


def test_duplicate_final_ids_cannot_silently_choose_another_clip():
    data = report()
    data["clips"].append(deepcopy(data["clips"][0]))
    assert build_product_result(report=data, summary={}, media={}).shots.unlinked_outcomes == 1
    assert build_analyst_facts(data, {}).metrics.shots.unlinked_outcomes == 1


def test_conflicting_outcomes_are_undetermined_in_both_views():
    data = report()
    data["shot_outcomes"].append({**data["shot_outcomes"][0], "made": False})
    assert build_product_result(report=data, summary={}, media={}).events[0].result == "undetermined"
    assert build_analyst_facts(data, {}).evidence[0].result == "undetermined"
