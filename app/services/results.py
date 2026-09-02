from typing import Literal

from pydantic import BaseModel, Field


ProductActionType = Literal["triple_threat", "free_throw", "jump_shot", "layup"]
SUPPORTED_ACTIONS: tuple[ProductActionType, ...] = (
    "triple_threat",
    "free_throw",
    "jump_shot",
    "layup",
)


class ProductActionCounts(BaseModel):
    triple_threat: int = 0
    free_throw: int = 0
    jump_shot: int = 0
    layup: int = 0


class ProductShotSummary(BaseModel):
    attempts: int = 0
    makes: int = 0
    misses: int = 0
    undetermined: int = 0
    make_rate: float | None = None
    unlinked_outcomes: int = 0


class ProductActionEvent(BaseModel):
    event_index: int
    action_type: ProductActionType
    start_ms: float
    end_ms: float
    time_ms: float
    result: Literal["make", "miss", "undetermined"] | None = None


class ProductResult(BaseModel):
    registered_participant_count: int
    action_counts: ProductActionCounts
    unsupported_event_count: int
    shots: ProductShotSummary
    events: list[ProductActionEvent]
    media: dict[str, str]
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str = "AI 识别结果，仅供训练复盘。"


def _outcome_label(made: object) -> Literal["make", "miss", "undetermined"]:
    if made is True:
        return "make"
    if made is False:
        return "miss"
    return "undetermined"


def build_product_result(
    *,
    report: dict,
    summary: dict,
    media: dict[str, str],
    extra_warnings: list[str] | tuple[str, ...] = (),
) -> ProductResult:
    """Convert research output into a deliberately anonymous product result."""
    clips = report.get("clips") or []
    outcomes = report.get("shot_outcomes") or []
    stats = report.get("shot_stats") or {}

    counts = {action: 0 for action in SUPPORTED_ACTIONS}
    unsupported_event_count = 0
    final_clip_ids = {clip.get("clip_id") for clip in clips if clip.get("clip_id")}
    outcome_by_clip = {
        outcome.get("clip_id"): outcome
        for outcome in outcomes
        if outcome.get("clip_id") in final_clip_ids
    }
    events: list[ProductActionEvent] = []

    for clip in clips:
        action = clip.get("action_type")
        if action not in SUPPORTED_ACTIONS:
            unsupported_event_count += 1
            continue
        counts[action] += 1
        outcome = outcome_by_clip.get(clip.get("clip_id"))
        release_ms = clip.get("release_ms")
        events.append(
            ProductActionEvent(
                event_index=len(events) + 1,
                action_type=action,
                start_ms=float(clip.get("start_ms", 0)),
                end_ms=float(clip.get("end_ms", 0)),
                time_ms=float(release_ms if release_ms is not None else clip.get("start_ms", 0)),
                result=_outcome_label(outcome.get("made")) if outcome is not None else None,
            )
        )

    attempts = int(stats.get("attempts", 0))
    makes = int(stats.get("makes", 0))
    unlinked_outcomes = sum(
        1 for outcome in outcomes if outcome.get("clip_id") not in final_clip_ids
    )
    warnings = list(extra_warnings)
    if unsupported_event_count:
        warnings.append(f"{unsupported_event_count} 个事件属于当前版本未支持的动作类型。")
    if unlinked_outcomes:
        warnings.append(f"{unlinked_outcomes} 个投篮结果无法可靠关联到最终动作片段。")

    return ProductResult(
        registered_participant_count=len(summary.get("student_ids") or []),
        action_counts=ProductActionCounts(**counts),
        unsupported_event_count=unsupported_event_count,
        shots=ProductShotSummary(
            attempts=attempts,
            makes=makes,
            misses=int(stats.get("misses", 0)),
            undetermined=int(stats.get("undetermined", 0)),
            make_rate=makes / attempts if attempts else None,
            unlinked_outcomes=unlinked_outcomes,
        ),
        events=events,
        media=media,
        warnings=warnings,
    )
