"""Paths and secret storage for uscis-case-monitor."""
from __future__ import annotations

import os
from pathlib import Path

import keyring
from platformdirs import user_data_dir

APP_NAME = "uscis-case-monitor"
KEYRING_SERVICE = "uscis-case-monitor"

_USERNAME_KEY = "username"
_PASSWORD_KEY = "password"
_TOTP_SEED_KEY = "totp_seed"


def app_dir() -> Path:
    """Return the per-user app data directory, creating it with 0700 perms."""
    path = Path(user_data_dir(APP_NAME))
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def session_path() -> Path:
    return app_dir() / "storage_state.json"


def state_path() -> Path:
    return app_dir() / "state.json"


def last_response_path() -> Path:
    return app_dir() / "last_response.json"


def config_path() -> Path:
    return app_dir() / "config.json"


def save_secrets(username: str, password: str, totp_seed: str) -> None:
    keyring.set_password(KEYRING_SERVICE, _USERNAME_KEY, username)
    keyring.set_password(KEYRING_SERVICE, _PASSWORD_KEY, password)
    keyring.set_password(KEYRING_SERVICE, _TOTP_SEED_KEY, totp_seed)


def load_secrets() -> dict[str, str]:
    """Return saved secrets. Raises RuntimeError if not yet configured."""
    username = keyring.get_password(KEYRING_SERVICE, _USERNAME_KEY)
    password = keyring.get_password(KEYRING_SERVICE, _PASSWORD_KEY)
    totp_seed = keyring.get_password(KEYRING_SERVICE, _TOTP_SEED_KEY)
    if not (username and password and totp_seed):
        raise RuntimeError("Secrets not configured. Run `uscis-case-monitor init`.")
    return {"username": username, "password": password, "totp_seed": totp_seed}
