import pytest

from uscis_case_monitor.core import client, monitor


@pytest.fixture
def payload():
    return {"data": {"receiptNumber": "IOE0934311580", "formType": "I-485",
                      "formName": "Adjust Status", "updatedAtTimestamp": "2026-05-15T10:00:00.000Z",
                      "events": [], "notices": []}}


def test_run_check_happy_path(monkeypatch, payload):
    saved = {}
    monkeypatch.setattr(monitor.state, "load_config", lambda: {"receiptNumber": "IOE0934311580"})
    monkeypatch.setattr(monitor.client, "fetch_case", lambda r: payload)
    monkeypatch.setattr(monitor.state, "load_last_response", lambda: None)
    monkeypatch.setattr(monitor.state, "save_state", lambda *a: saved.update(state=a))
    monkeypatch.setattr(monitor.state, "save_last_response", lambda p: saved.update(resp=p))

    report = monitor.run_check()
    assert report.changed is False
    assert report.updated_at_timestamp == "2026-05-15T10:00:00.000Z"
    assert saved["resp"] == payload


def test_run_check_relogins_once_on_expiry(monkeypatch, payload):
    calls = {"fetch": 0, "login": 0}

    def fake_fetch(receipt):
        calls["fetch"] += 1
        if calls["fetch"] == 1:
            raise client.SessionExpired("expired")
        return payload

    monkeypatch.setattr(monitor.state, "load_config", lambda: {"receiptNumber": "IOE0934311580"})
    monkeypatch.setattr(monitor.client, "fetch_case", fake_fetch)
    monkeypatch.setattr(monitor.config, "load_secrets",
                        lambda: {"username": "u", "password": "p", "totp_seed": "s"})
    monkeypatch.setattr(monitor.auth, "login_and_save_session",
                        lambda u, p, s, headed: calls.update(login=calls["login"] + 1))
    monkeypatch.setattr(monitor.state, "load_last_response", lambda: None)
    monkeypatch.setattr(monitor.state, "save_state", lambda *a: None)
    monkeypatch.setattr(monitor.state, "save_last_response", lambda p: None)

    report = monitor.run_check()
    assert calls["fetch"] == 2
    assert calls["login"] == 1
    assert report.updated_at_timestamp == "2026-05-15T10:00:00.000Z"


def test_run_check_raises_when_unconfigured(monkeypatch):
    monkeypatch.setattr(monitor.state, "load_config", lambda: None)
    with pytest.raises(RuntimeError, match="init"):
        monitor.run_check()
