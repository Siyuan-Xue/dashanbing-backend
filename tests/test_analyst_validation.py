import pytest

from app.services.analyst import validate_report

FACTS = {'subjects':[{'id':'player_1'},{'id':'player_2'}], 'evidence':[{'id':'event-1','subject_id':'player_1'}]}


def test_report_rejects_evidence_owned_by_other_player():
    with pytest.raises(ValueError, match='different player'):
        validate_report({'summary':'本次训练', 'players':[{'subject_id':'player_2','text':'这球值得重看','evidence_ids':['event-1']}]},FACTS,{})


def test_report_cannot_invent_historical_comparison():
    with pytest.raises(ValueError, match='comparison'):
        validate_report({'summary':'本次训练','comparison':{'text':'比上次更好','evidence_ids':[]}},FACTS,{})


def test_report_rejects_unprovided_evidence_and_internal_identity():
    with pytest.raises(ValueError, match='Unknown evidence'):
        validate_report({'summary':'本次训练','highlights':[{'text':'这球值得重看','evidence_ids':['event-404']}]},FACTS,{})
    with pytest.raises(ValueError, match='Private identifier'):
        validate_report({'summary':'stu_03 表现稳定'},FACTS,{})


def test_report_accepts_real_evidence_and_training_suggestion():
    report=validate_report({'summary':'这球值得重看','highlights':[{'text':'回看出手','evidence_ids':['event-1']}],'suggestions':['下次保持出手后的跟随动作']},FACTS,{})
    assert report.highlights[0].evidence_ids == ['event-1']
