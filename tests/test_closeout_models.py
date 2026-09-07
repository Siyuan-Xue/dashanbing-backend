import pytest
from pydantic import ValidationError

from app.models import TaskCreate, TaskUpdate, User, UserPublic, UsageQuota


def test_new_accounts_default_to_business_role_and_revocable_sessions():
    user = User(username="player", hashed_password="not-a-real-secret")
    assert user.role == "user"
    assert user.session_version == 0
    assert UserPublic(id=1, username="player", email=None, is_active=True).role == "user"


def test_drafts_accept_registration_metadata_without_requiring_completed_inputs():
    draft = TaskCreate(title="Training", enrollment_mode="lineup", expected_persons=4)
    assert draft.enrollment_mode == "lineup"
    assert draft.expected_persons == 4
    assert TaskCreate(title="Training").expected_persons is None
    update = TaskUpdate(title="Training", mode="quick", expected_persons=2)
    assert update.expected_persons == 2


@pytest.mark.parametrize("count", [0, 7])
def test_api_rejects_registration_counts_outside_supported_range(count):
    with pytest.raises(ValidationError):
        TaskCreate(title="Training", expected_persons=count)


def test_api_rejects_unknown_registration_method():
    with pytest.raises(ValidationError):
        TaskCreate(title="Training", enrollment_mode="automatic")


def test_usage_can_describe_an_explicit_zero_quota():
    assert UsageQuota(used=0, limit=0).limit == 0
