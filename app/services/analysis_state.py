from enum import Enum


class AnalysisStatus(str, Enum):
    draft = "draft"
    uploading = "uploading"
    queued = "queued"
    running = "running"
    registering = "registering"
    perception = "perception"
    ball_tracking = "ball_tracking"
    synchronizing = "synchronizing"
    action_recognition = "action_recognition"
    outcome_detection = "outcome_detection"
    exporting = "exporting"
    visualizing = "visualizing"
    cancel_requested = "cancel_requested"
    completed = "completed"
    failed = "failed"
    canceled = "canceled"
    interrupted = "interrupted"
    expired = "expired"


ACTIVE_STATUSES = {
    AnalysisStatus.running,
    AnalysisStatus.registering,
    AnalysisStatus.perception,
    AnalysisStatus.ball_tracking,
    AnalysisStatus.synchronizing,
    AnalysisStatus.action_recognition,
    AnalysisStatus.outcome_detection,
    AnalysisStatus.exporting,
    AnalysisStatus.visualizing,
}
TERMINAL_STATUSES = {
    AnalysisStatus.completed,
    AnalysisStatus.failed,
    AnalysisStatus.canceled,
    AnalysisStatus.interrupted,
    AnalysisStatus.expired,
}

_NEXT_STAGE = {
    AnalysisStatus.draft: {
        AnalysisStatus.uploading,
        AnalysisStatus.queued,
        AnalysisStatus.canceled,
        AnalysisStatus.expired,
    },
    AnalysisStatus.uploading: {
        AnalysisStatus.draft,
        AnalysisStatus.canceled,
        AnalysisStatus.expired,
    },
    AnalysisStatus.queued: {AnalysisStatus.running, AnalysisStatus.registering, AnalysisStatus.canceled},
    AnalysisStatus.running: {AnalysisStatus.registering, AnalysisStatus.interrupted},
    AnalysisStatus.registering: {AnalysisStatus.perception},
    AnalysisStatus.perception: {AnalysisStatus.ball_tracking},
    AnalysisStatus.ball_tracking: {AnalysisStatus.synchronizing},
    AnalysisStatus.synchronizing: {AnalysisStatus.action_recognition},
    AnalysisStatus.action_recognition: {AnalysisStatus.outcome_detection},
    AnalysisStatus.outcome_detection: {AnalysisStatus.exporting},
    AnalysisStatus.exporting: {AnalysisStatus.visualizing},
    AnalysisStatus.visualizing: {AnalysisStatus.completed},
    AnalysisStatus.cancel_requested: {AnalysisStatus.canceled, AnalysisStatus.failed},
    AnalysisStatus.failed: {AnalysisStatus.queued},
    AnalysisStatus.canceled: {AnalysisStatus.queued},
    AnalysisStatus.interrupted: {AnalysisStatus.queued},
}


def transition_status(current: AnalysisStatus | str, target: AnalysisStatus | str) -> AnalysisStatus:
    current_status = AnalysisStatus(current)
    target_status = AnalysisStatus(target)
    allowed = set(_NEXT_STAGE.get(current_status, set()))
    if current_status in ACTIVE_STATUSES:
        allowed.update(
            {
                AnalysisStatus.cancel_requested,
                AnalysisStatus.failed,
                AnalysisStatus.canceled,
                AnalysisStatus.interrupted,
            }
        )
    if target_status not in allowed:
        raise ValueError(f"Invalid analysis transition: {current_status} -> {target_status}")
    return target_status
