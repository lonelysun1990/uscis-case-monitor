import os
import stat

import pytest

from uscis_case_monitor.core import config


@pytest.fixture
def tmp_app_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "user_data_dir", lambda app_name: str(tmp_path / app_name))
    return tmp_path


class FakeKeyring:
    def __init__(self):
        self.store = {}

    def set_password(self, service, key, value):
        self.store[(service, key)] = value

    def get_password(self, service, key):
        return self.store.get((service, key))


@pytest.fixture
def fake_keyring(monkeypatch):
    fk = FakeKeyring()
    monkeypatch.setattr(config, "keyring", fk)
    return fk


def test_app_dir_created_with_0700(tmp_app_dir):
    path = config.app_dir()
    assert path.exists()
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o700


def test_path_helpers_live_under_app_dir(tmp_app_dir):
    assert config.session_path().parent == config.app_dir()
    assert config.session_path().name == "storage_state.json"
    assert config.state_path().name == "state.json"
    assert config.last_response_path().name == "last_response.json"
    assert config.config_path().name == "config.json"


def test_secrets_round_trip(tmp_app_dir, fake_keyring):
    config.save_secrets("user@example.com", "pw", "SEED123")
    secrets = config.load_secrets()
    assert secrets == {
        "username": "user@example.com",
        "password": "pw",
        "totp_seed": "SEED123",
    }


def test_load_secrets_raises_when_missing(tmp_app_dir, fake_keyring):
    with pytest.raises(RuntimeError, match="Run `uscis-case-monitor init`"):
        config.load_secrets()
