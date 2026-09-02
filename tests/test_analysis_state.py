import pytest

from app.services.analysis_state import AnalysisStatus, transition_status


def test_analysis_status_allows_supported_queue_lifecycle():
    assert transition_status(AnalysisStatus.queued, AnalysisStatus.registering) == AnalysisStatus.registering
    assert transition_status(AnalysisStatus.registering, AnalysisStatus.perception) == AnalysisStatus.perception
    assert transition_status(AnalysisStatus.perception, AnalysisStatus.ball_tracking) == AnalysisStatus.ball_tracking
    assert transition_status(AnalysisStatus.visualizing, AnalysisStatus.completed) == AnalysisStatus.completed


def test_analysis_status_rejects_invalid_and_terminal_transitions():
    with pytest.raises(ValueError):
        transition_status(AnalysisStatus.queued, AnalysisStatus.completed)
    with pytest.raises(ValueError):
        transition_status(AnalysisStatus.completed, AnalysisStatus.queued)


def test_interrupted_and_failed_jobs_can_be_retried():
    assert transition_status(AnalysisStatus.running, AnalysisStatus.interrupted) == AnalysisStatus.interrupted
    assert transition_status(AnalysisStatus.interrupted, AnalysisStatus.queued) == AnalysisStatus.queued
    assert transition_status(AnalysisStatus.failed, AnalysisStatus.queued) == AnalysisStatus.queued
