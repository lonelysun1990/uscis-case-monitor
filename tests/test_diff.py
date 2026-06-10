import json
from pathlib import Path

import pytest

from uscis_case_monitor.core import diff

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def base():
    return _load("case_base.json")


@pytest.fixture
def new_event():
    return _load("case_new_event.json")


def test_get_updated_at(base):
    assert diff.get_updated_at(base) == "2026-04-28T01:49:16.139Z"


def test_first_run_not_changed(base):
    report = diff.summarize(base, None)
    assert report.changed is False
    assert report.new_events == []
    assert report.new_notices == []
    assert report.receipt_number == "IOE0934311580"
    assert report.form_type == "I-485"
    assert report.updated_at_timestamp == "2026-04-28T01:49:16.139Z"


def test_identical_payload_not_changed(base):
    report = diff.summarize(base, base)
    assert report.changed is False
    assert report.new_events == []
    assert report.new_notices == []


def test_change_detected_with_new_event_and_notice(base, new_event):
    report = diff.summarize(new_event, base)
    assert report.changed is True
    assert report.updated_at_timestamp == "2026-05-15T10:00:00.000Z"
    assert [e["eventId"] for e in report.new_events] == [
        "aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb"
    ]
    assert [n["letterId"] for n in report.new_notices] == ["500000001"]
