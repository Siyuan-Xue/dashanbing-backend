from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.services.results import ProductResult, build_product_result


@dataclass(frozen=True)
class PresetDefinition:
    id: str
    title: str
    description: str
    group_number: int
    expected_minutes: float

    @property
    def group_id(self) -> str:
        return f"group_{self.group_number:02d}"


PRESETS: tuple[PresetDefinition, ...] = (
    PresetDefinition("quick-demo", "快速演示", "4 次跳投", 4, 9.4),
    PresetDefinition("mixed-actions", "混合动作", "三威胁与跳投", 3, 26.7),
    PresetDefinition("verified-outcome", "命中验证", "带投篮结果真值的罚篮样例", 5, 30.9),
    PresetDefinition("layup-demo", "上篮演示", "6 次上篮", 6, 14.3),
)

MEDIA_FILES = {
    "cam_01": "cam_01_annotated.mp4",
    "cam_02": "cam_02_annotated.mp4",
    "cam_03": "cam_03_annotated.mp4",
    "cam_04": "cam_04_ball.mp4",
    "phases": "phases.mp4",
}


class PresetCatalog:
    def __init__(self, sample_root: Path):
        self.sample_root = sample_root.resolve()
        self._presets = {preset.id: preset for preset in PRESETS}

    def _preset(self, preset_id: str) -> PresetDefinition:
        try:
            return self._presets[preset_id]
        except KeyError as exc:
            raise KeyError(preset_id) from exc

    def _group_root(self, preset: PresetDefinition) -> Path:
        return self.sample_root / "outputs" / "v3" / preset.group_id

    def group_root(self, preset_id: str) -> Path:
        return self._group_root(self._preset(preset_id))

    @staticmethod
    def _read_json(path: Path) -> dict:
        with path.open(encoding="utf-8") as source:
            return json.load(source)

    def list(self) -> list[dict]:
        return [
            {
                "id": preset.id,
                "title": preset.title,
                "description": preset.description,
                "expected_minutes": preset.expected_minutes,
            }
            for preset in PRESETS
        ]

    def _manifest_warnings(self, preset: PresetDefinition, summary: dict) -> list[str]:
        manifest_path = self.sample_root / "outputs" / "v3" / "manifest.json"
        if not manifest_path.is_file():
            return []
        manifest = self._read_json(manifest_path)
        group = next(
            (item for item in manifest.get("groups", []) if item.get("group_id") == preset.group_id),
            None,
        )
        if group is None:
            return ["根 manifest.json 缺少该分组，已使用最终分组结果。"]
        if (
            group.get("clip_count") != summary.get("clip_count")
            or group.get("action_type_hist") != summary.get("action_type_hist")
        ):
            return ["根 manifest.json 与最终分组结果不一致，已忽略过期 manifest。"]
        return []

    def result(self, preset_id: str) -> ProductResult:
        preset = self._preset(preset_id)
        group_root = self._group_root(preset)
        report = self._read_json(group_root / "report.json")
        summary = self._read_json(group_root / "summary.json")
        warnings = self._manifest_warnings(preset, summary)
        report_count = len(report.get("clips") or [])
        if summary.get("clip_count") != report_count:
            warnings.append("summary.json 与最终 report.json 动作数量不一致，已以 report.json 为准。")
        evaluation_path = group_root / "eval_vs_gt.json"
        if evaluation_path.is_file():
            evaluation = self._read_json(evaluation_path)
            if evaluation.get("n_pred") is not None and evaluation.get("n_pred") != report_count:
                warnings.append("eval_vs_gt.json 与最终 report.json 动作数量不一致，请复核样例导入。")
        missing_media = [
            filename
            for filename in MEDIA_FILES.values()
            if not (group_root / "viz" / filename).is_file()
        ]
        if missing_media:
            raise FileNotFoundError("Preset review media is incomplete")
        media = {
            kind: f"/api/v1/presets/{preset.id}/media/{kind}"
            for kind, filename in MEDIA_FILES.items()
        }
        return build_product_result(
            report=report,
            summary=summary,
            media=media,
            extra_warnings=warnings,
        )

    def media_path(self, preset_id: str, kind: str) -> Path:
        preset = self._preset(preset_id)
        try:
            filename = MEDIA_FILES[kind]
        except KeyError as exc:
            raise KeyError(kind) from exc
        path = self._group_root(preset) / "viz" / filename
        if not path.is_file():
            raise KeyError(kind)
        return path

    def rerun_manifest(self, preset_id: str) -> dict[str, str]:
        preset = self._preset(preset_id)
        inputs = self.sample_root / "test_data_v3"
        group = preset.group_number
        manifest = {
            "enrollment_video": str(inputs / "0-2.mkv"),
            "cam_01": str(inputs / f"{group}-1.mkv"),
            "cam_02": str(inputs / f"{group}-2.mkv"),
            "cam_03": str(inputs / f"{group}-3.mkv"),
            "cam_04": str(inputs / f"{group}-4.mkv"),
            "sync": str(inputs / "sync" / f"group_{group:02d}.json"),
        }
        if not all(Path(path).is_file() for path in manifest.values()):
            raise FileNotFoundError("Preset rerun inputs are incomplete")
        return manifest
