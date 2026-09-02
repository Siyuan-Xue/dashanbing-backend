"""Validate imported v3 reports, evaluations, outcome truth, and review media."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.presets import MEDIA_FILES, PresetCatalog  # noqa: E402


SAMPLE_ROOT = ROOT / "local-assets" / "sample-bundle" / "data"
THRESHOLDS = {
    "mixed-actions": (0.963, 1.0),
    "quick-demo": (1.0, 1.0),
    "verified-outcome": (0.944, 1.0),
    "layup-demo": (1.0, 1.0),
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    catalog = PresetCatalog(SAMPLE_ROOT)
    for preset in catalog.list():
        preset_id = preset["id"]
        group = catalog.group_root(preset_id)
        report = load(group / "report.json")
        evaluation = load(group / "eval_vs_gt.json")
        product = catalog.result(preset_id)
        serialized = product.model_dump_json()
        assert "stu_" not in serialized and "student_id" not in serialized
        supported_total = sum(product.action_counts.model_dump().values())
        assert supported_total + product.unsupported_event_count == len(report.get("clips") or [])
        precision, recall = THRESHOLDS[preset_id]
        assert float(evaluation["precision"]) >= precision
        assert float(evaluation["recall"]) >= recall
        for kind, filename in MEDIA_FILES.items():
            assert catalog.media_path(preset_id, kind) == group / "viz" / filename
        print(
            f"{preset_id}: clips={supported_total}, shots={product.shots.attempts}, "
            f"precision={evaluation['precision']}, recall={evaluation['recall']}"
        )
    group5 = load(catalog.group_root("verified-outcome") / "eval_vs_gt.json")
    assert group5["n_outcome_gt"] == 17
    assert group5["n_outcome_ok"] == 17
    assert group5["pass_outcome"] is True
    print("verified-outcome: outcome truth 17/17")


if __name__ == "__main__":
    main()
