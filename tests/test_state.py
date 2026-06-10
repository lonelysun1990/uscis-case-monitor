import os
import stat

import pytest

from uscis_case_monitor.core import config, state


@pytest.fixture
def tmp_app_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "user_data_dir", lambda app_name: str(tmp_path / app_name))
    return tmp_path


def test_config_round_trip(tmp_app_dir):
    assert state.load_config() is None
    state.save_config("IOE0934311580")
    assert state.load_config() == {"receiptNumber": "IOE0934311580"}


def test_state_round_trip(tmp_app_dir):
    assert state.load_state() is None
    state.save_state("IOE0934311580", "2026-04-28T01:49:16.139Z", "2026-06-10T00:00:00+00:00")
    assert state.load_state() == {
        "receiptNumber": "IOE0934311580",
        "lastUpdatedAtTimestamp": "2026-04-28T01:49:16.139Z",
        "lastCheckedAt": "2026-06-10T00:00:00+00:00",
    }


def test_last_response_round_trip(tmp_app_dir):
    assert state.load_last_response() is None
    payload = {"data": {"receiptNumber": "IOE0934311580"}}
    state.save_last_response(payload)
    assert state.load_last_response() == payload


def test_files_written_with_0600(tmp_app_dir):
    state.save_config("IOE0934311580")
    mode = stat.S_IMODE(os.stat(config.config_path()).st_mode)
    assert mode == 0o600
