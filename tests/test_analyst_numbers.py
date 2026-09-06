from copy import deepcopy

import pytest

from app.analyst_reports import MessagePublic, ReportPublic
from app.services.analyst import system_prompt, validate_report
from app.services.analyst_numbers import format_analyst_numbers


@pytest.mark.parametrize(('text', 'expected'), [
    ('命中率 66.6666667%，差值 12.345 个百分点', '命中率 66.67%，差值 12.35 个百分点'),
    ('角度 120.100000°，时长6.23456s，置信度0.987654', '角度 120.1°，时长6.23s，置信度0.99'),
    ('4 次，2.5 秒，12.34%，5.0000 次', '4 次，2.5 秒，12.34%，5 次'),
    ('1.005, -1.005, -0.004, +2.999', '1.01, -1.01, 0, +3'),
    ('1,234.5678 ms; 9999999999999999999999999999.995', '1,234.57 ms; 10000000000000000000000000000'),
    ('[event-1.2345] player_1.2345 glm-5.3333 1.2345.6 https://x.test/1.2345 `0.12345` 1.2345e-10', '[event-1.2345] player_1.2345 glm-5.3333 1.2345.6 https://x.test/1.2345 `0.12345` 1.2345e-10'),
])
def test_numbers_round_for_prose_without_changing_identifiers(text, expected):
    assert format_analyst_numbers(text) == expected
    assert format_analyst_numbers(expected) == expected


def test_report_rounds_all_narrative_fields_without_modifying_facts_or_ids():
    facts = {'subjects': [{'id': 'player_1.2345'}], 'evidence': [{'id': 'event-1.2345', 'subject_id': 'player_1.2345', 'time_ms': 6234.56789}]}
    before = deepcopy(facts)
    body = {'summary': '命中率66.666667%', 'highlights': [{'text': '6.23456s', 'evidence_ids': ['event-1.2345']}],
            'players': [{'subject_id': 'player_1.2345', 'text': '角度120.5555°', 'evidence_ids': ['event-1.2345']}],
            'comparison': {'text': '增加16.666667个百分点', 'evidence_ids': []}, 'suggestions': ['回看6.23456秒']}
    report = validate_report(body, facts, {'comparison': {'id': 'old'}})
    assert report.summary == '命中率66.67%'
    assert report.highlights[0].text == '6.23s'
    assert report.players[0].text == '角度120.56°'
    assert report.comparison.text == '增加16.67个百分点'
    assert report.suggestions == ['回看6.23秒']
    assert report.players[0].subject_id == 'player_1.2345'
    assert report.highlights[0].evidence_ids == ['event-1.2345']
    assert facts == before
    assert body['summary'] == '命中率66.666667%'
    # Existing stored reports use the same public read path without regeneration.
    public = ReportPublic.model_validate({**body, 'id': 'r1', 'model': 'glm-5.3', 'style': 'coach', 'locale': 'zh', 'created_at': '2026-09-06T01:00:00Z'})
    assert public.summary == report.summary


@pytest.mark.parametrize('status', ['running', 'completed'])
def test_chat_formats_assistant_snapshots_but_keeps_user_input_exact(status):
    message = {'id': 'm1', 'role': 'assistant', 'content': '命中率33.33333% [event-1.2345]', 'status': status, 'citations': ['event-1.2345']}
    assert MessagePublic.model_validate(message).content == '命中率33.33% [event-1.2345]'
    assert MessagePublic.model_validate({**message, 'role': 'user'}).content == message['content']


@pytest.mark.parametrize('report', [True, False])
def test_prompt_limits_display_precision_after_percentage_conversion(report):
    prompt = system_prompt({'locale': 'zh', 'style': 'coach'}, report=report)
    assert '最多保留两位小数' in prompt
    assert '先换算成百分比' in prompt
