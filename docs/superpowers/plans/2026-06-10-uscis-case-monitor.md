# USCIS Case Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a macOS CLI that checks a single USCIS case via the authenticated case-service API, persists a logged-in browser session, and reports whether the case changed since the last run.

**Architecture:** A `core/` layer holds pure logic (config/secrets, JSON state, change diffing) plus the side-effecting browser pieces (Playwright login + session, authenticated fetch) and an orchestrator. A thin Typer `cli.py` exposes `init` and `check`. Pure logic is unit-tested against JSON fixtures; the live login/fetch is validated manually in the final task.

**Tech Stack:** Python 3.11+, Typer (CLI), Playwright (session + authenticated fetch), pyotp (TOTP), keyring (macOS Keychain), platformdirs (app data dir), pytest.

---

## File Structure

```
uscis_case_monitor/
  __init__.py
  cli.py                 # Typer app: init, check
  core/
    __init__.py
    config.py            # app dir paths + Keychain secret storage
    state.py             # config.json / state.json / last_response.json
    diff.py              # pure: parse payload, compute changes
    auth.py              # TOTP helper + Playwright login & session save
    client.py            # authenticated case fetch + expiry detection
    monitor.py           # orchestration: run_init, run_check
pyproject.toml
README.md
tests/
  __init__.py
  fixtures/
    case_base.json       # provided sample payload
    case_new_event.json  # base + one extra event, newer updatedAt
  test_config.py
  test_state.py
  test_diff.py
  test_auth.py
  test_client.py
  test_monitor.py
  test_cli.py
```

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `uscis_case_monitor/__init__.py`
- Create: `uscis_case_monitor/core/__init__.py`
- Create: `tests/__init__.py`
- Test: `tests/test_smoke.py`

- [ ] **Step 1: Write the failing test**

`tests/test_smoke.py`:
```python
def test_package_imports():
    import uscis_case_monitor
    assert uscis_case_monitor.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'uscis_case_monitor'`

- [ ] **Step 3: Create the package and config**

`pyproject.toml`:
```toml
[project]
name = "uscis-case-monitor"
version = "0.1.0"
description = "Check a USCIS case status via the authenticated case-service API."
requires-python = ">=3.11"
dependencies = [
    "typer>=0.12",
    "pyotp>=2.9",
    "keyring>=25",
    "platformdirs>=4",
    "playwright>=1.44",
]

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.scripts]
uscis-case-monitor = "uscis_case_monitor.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["uscis_case_monitor"]
```

`uscis_case_monitor/__init__.py`:
```python
__version__ = "0.1.0"
```

`uscis_case_monitor/core/__init__.py`:
```python
```

`tests/__init__.py`:
```python
```

- [ ] **Step 4: Install in editable mode with dev deps**

Run: `python -m pip install -e ".[dev]"`
Expected: installs successfully; `uscis-case-monitor` script registered.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uscis_case_monitor tests
git commit -m "chore: scaffold package and tooling"
```

---

### Task 2: config.py — app dir paths + Keychain secrets

**Files:**
- Create: `uscis_case_monitor/core/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'uscis_case_monitor.core.config'`

- [ ] **Step 3: Write the implementation**

`uscis_case_monitor/core/config.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add uscis_case_monitor/core/config.py tests/test_config.py
git commit -m "feat: app-dir paths and Keychain secret storage"
```

---

### Task 3: state.py — JSON config/state/response files

**Files:**
- Create: `uscis_case_monitor/core/state.py`
- Test: `tests/test_state.py`

- [ ] **Step 1: Write the failing test**

`tests/test_state.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_state.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'uscis_case_monitor.core.state'`

- [ ] **Step 3: Write the implementation**

`uscis_case_monitor/core/state.py`:
```python
"""Read/write config and run state as JSON files."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from uscis_case_monitor.core import config


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2))
    os.chmod(path, 0o600)


def _read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def save_config(receipt_number: str) -> None:
    _write_json(config.config_path(), {"receiptNumber": receipt_number})


def load_config() -> dict | None:
    return _read_json(config.config_path())


def save_state(receipt_number: str, updated_at_timestamp: str, last_checked_at: str) -> None:
    _write_json(
        config.state_path(),
        {
            "receiptNumber": receipt_number,
            "lastUpdatedAtTimestamp": updated_at_timestamp,
            "lastCheckedAt": last_checked_at,
        },
    )


def load_state() -> dict | None:
    return _read_json(config.state_path())


def save_last_response(payload: dict) -> None:
    _write_json(config.last_response_path(), payload)


def load_last_response() -> dict | None:
    return _read_json(config.last_response_path())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_state.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add uscis_case_monitor/core/state.py tests/test_state.py
git commit -m "feat: JSON config/state/response persistence"
```

---

### Task 4: diff.py — parse payload and compute changes

**Files:**
- Create: `tests/fixtures/case_base.json`
- Create: `tests/fixtures/case_new_event.json`
- Create: `uscis_case_monitor/core/diff.py`
- Test: `tests/test_diff.py`

- [ ] **Step 1: Create the fixtures**

`tests/fixtures/case_base.json` (the provided sample payload):
```json
{"data":{"receiptNumber":"IOE0934311580","submissionDate":"2025-10-21","submissionTimestamp":"2025-10-21T00:00:00.000Z","formType":"I-485","formName":"Application to Register Permanent Residence or Adjust Status","updatedAt":"2026-04-28","updatedAtTimestamp":"2026-04-28T01:49:16.139Z","cmsFailure":false,"closed":false,"ackedByAdjudicatorAndCms":true,"applicantName":"JIN, ZHAOYANG","representativeName":"CROWLEY, NOEL CHASE","nonElisPaperFiled":false,"noticeMailingPrefIndicator":false,"docMailingPrefIndicator":false,"elisBeneficiaryAddendum":{},"areAllGroupStatusesComplete":false,"areAllGroupMembersAuthorizedForTravel":true,"isPremiumProcessed":false,"actionRequired":false,"elisChannelType":"Lockbox","concurrentCases":[],"documents":[],"evidenceRequests":[],"notices":[{"receiptNumber":"IOE0934311580","letterId":"411592235","generationDate":"2025-11-05T04:23:09.877Z","appointmentDateTime":"2025-11-07T13:00:00.000Z","actionType":"Appointment Scheduled"}],"events":[{"receiptNumber":"IOE0934311580","eventId":"072cebdf-cb38-468e-8433-65ca82a2da04","eventCode":"FTA0","createdAt":"2025-11-07","createdAtTimestamp":"2025-11-07T16:57:33.012Z","updatedAt":"2025-11-07","updatedAtTimestamp":"2025-11-07T16:57:33.012Z","eventDateTime":"2025-11-07","eventTimestamp":"2025-11-07T16:57:31.048Z"},{"receiptNumber":"IOE0934311580","eventId":"1652e5a0-6500-4a19-a3c4-a8fde601d315","eventCode":"FTA0","createdAt":"2025-11-07","createdAtTimestamp":"2025-11-07T16:57:32.725Z","updatedAt":"2025-11-07","updatedAtTimestamp":"2025-11-07T16:57:32.725Z","eventDateTime":"2025-11-07","eventTimestamp":"2025-11-07T16:57:31.067Z"},{"receiptNumber":"IOE0934311580","eventId":"f011725a-06bd-4e97-8015-a81f40133aaa","eventCode":"IAF","createdAt":"2025-10-24","createdAtTimestamp":"2025-10-24T13:15:36.545Z","updatedAt":"2025-10-24","updatedAtTimestamp":"2025-10-24T13:15:36.545Z","eventDateTime":"2025-10-21","eventTimestamp":"2025-10-21T00:00:00.000Z"}],"addendums":[]}}
```

`tests/fixtures/case_new_event.json` (newer `updatedAtTimestamp`, one extra event with a new `eventId`, and one extra notice with a new `letterId`):
```json
{"data":{"receiptNumber":"IOE0934311580","submissionDate":"2025-10-21","submissionTimestamp":"2025-10-21T00:00:00.000Z","formType":"I-485","formName":"Application to Register Permanent Residence or Adjust Status","updatedAt":"2026-05-15","updatedAtTimestamp":"2026-05-15T10:00:00.000Z","cmsFailure":false,"closed":false,"ackedByAdjudicatorAndCms":true,"applicantName":"JIN, ZHAOYANG","representativeName":"CROWLEY, NOEL CHASE","nonElisPaperFiled":false,"noticeMailingPrefIndicator":false,"docMailingPrefIndicator":false,"elisBeneficiaryAddendum":{},"areAllGroupStatusesComplete":false,"areAllGroupMembersAuthorizedForTravel":true,"isPremiumProcessed":false,"actionRequired":false,"elisChannelType":"Lockbox","concurrentCases":[],"documents":[],"evidenceRequests":[],"notices":[{"receiptNumber":"IOE0934311580","letterId":"411592235","generationDate":"2025-11-05T04:23:09.877Z","appointmentDateTime":"2025-11-07T13:00:00.000Z","actionType":"Appointment Scheduled"},{"receiptNumber":"IOE0934311580","letterId":"500000001","generationDate":"2026-05-15T09:00:00.000Z","actionType":"Card Was Mailed"}],"events":[{"receiptNumber":"IOE0934311580","eventId":"072cebdf-cb38-468e-8433-65ca82a2da04","eventCode":"FTA0","createdAt":"2025-11-07","createdAtTimestamp":"2025-11-07T16:57:33.012Z","updatedAt":"2025-11-07","updatedAtTimestamp":"2025-11-07T16:57:33.012Z","eventDateTime":"2025-11-07","eventTimestamp":"2025-11-07T16:57:31.048Z"},{"receiptNumber":"IOE0934311580","eventId":"1652e5a0-6500-4a19-a3c4-a8fde601d315","eventCode":"FTA0","createdAt":"2025-11-07","createdAtTimestamp":"2025-11-07T16:57:32.725Z","updatedAt":"2025-11-07","updatedAtTimestamp":"2025-11-07T16:57:32.725Z","eventDateTime":"2025-11-07","eventTimestamp":"2025-11-07T16:57:31.067Z"},{"receiptNumber":"IOE0934311580","eventId":"f011725a-06bd-4e97-8015-a81f40133aaa","eventCode":"IAF","createdAt":"2025-10-24","createdAtTimestamp":"2025-10-24T13:15:36.545Z","updatedAt":"2025-10-24","updatedAtTimestamp":"2025-10-24T13:15:36.545Z","eventDateTime":"2025-10-21","eventTimestamp":"2025-10-21T00:00:00.000Z"},{"receiptNumber":"IOE0934311580","eventId":"aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb","eventCode":"CRD0","createdAt":"2026-05-15","createdAtTimestamp":"2026-05-15T10:00:00.000Z","updatedAt":"2026-05-15","updatedAtTimestamp":"2026-05-15T10:00:00.000Z","eventDateTime":"2026-05-15","eventTimestamp":"2026-05-15T10:00:00.000Z"}],"addendums":[]}}
```

- [ ] **Step 2: Write the failing test**

`tests/test_diff.py`:
```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_diff.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'uscis_case_monitor.core.diff'`

- [ ] **Step 4: Write the implementation**

`uscis_case_monitor/core/diff.py`:
```python
"""Pure logic to parse case payloads and compute changes between runs."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChangeReport:
    receipt_number: str
    form_type: str
    form_name: str
    updated_at_timestamp: str
    changed: bool
    new_events: list[dict] = field(default_factory=list)
    new_notices: list[dict] = field(default_factory=list)


def _data(payload: dict) -> dict:
    return payload.get("data", {})


def get_updated_at(payload: dict) -> str:
    return _data(payload).get("updatedAtTimestamp", "")


def new_events(current: dict, previous: dict | None) -> list[dict]:
    cur = _data(current).get("events", [])
    if previous is None:
        return list(cur)
    prev_ids = {e.get("eventId") for e in _data(previous).get("events", [])}
    return [e for e in cur if e.get("eventId") not in prev_ids]


def new_notices(current: dict, previous: dict | None) -> list[dict]:
    cur = _data(current).get("notices", [])
    if previous is None:
        return list(cur)
    prev_ids = {n.get("letterId") for n in _data(previous).get("notices", [])}
    return [n for n in cur if n.get("letterId") not in prev_ids]


def summarize(current: dict, previous: dict | None) -> ChangeReport:
    """Build a ChangeReport. A first run (previous is None) is reported as
    unchanged so the caller can save a baseline without a false alert."""
    data = _data(current)
    cur_updated = get_updated_at(current)
    changed = previous is not None and cur_updated != get_updated_at(previous)
    return ChangeReport(
        receipt_number=data.get("receiptNumber", ""),
        form_type=data.get("formType", ""),
        form_name=data.get("formName", ""),
        updated_at_timestamp=cur_updated,
        changed=changed,
        new_events=new_events(current, previous) if changed else [],
        new_notices=new_notices(current, previous) if changed else [],
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_diff.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add uscis_case_monitor/core/diff.py tests/test_diff.py tests/fixtures
git commit -m "feat: case payload parsing and change diffing"
```

---

### Task 5: auth.py — TOTP helper + Playwright login

**Files:**
- Create: `uscis_case_monitor/core/auth.py`
- Test: `tests/test_auth.py`

> **Note:** Only the pure `current_totp` helper is unit-tested here. `login_and_save_session` drives the live USCIS login; its selectors are best-effort from the documented login flow and are calibrated against the real site in Task 10.

- [ ] **Step 1: Write the failing test**

`tests/test_auth.py`:
```python
import pyotp

from uscis_case_monitor.core import auth


def test_current_totp_matches_pyotp():
    seed = "JBSWY3DPEHPK3PXP"
    code = auth.current_totp(seed)
    assert len(code) == 6
    assert code.isdigit()
    assert pyotp.TOTP(seed).verify(code)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'uscis_case_monitor.core.auth'`

- [ ] **Step 3: Write the implementation**

`uscis_case_monitor/core/auth.py`:
```python
"""TOTP generation and Playwright-based login/session persistence."""
from __future__ import annotations

import subprocess
import sys

import pyotp

from uscis_case_monitor.core import config

SIGN_IN_URL = "https://my.uscis.gov/sign-in"
LOGGED_IN_URL_GLOB = "**/account/**"


def current_totp(seed: str) -> str:
    """Return the current 6-digit TOTP code for the given seed."""
    return pyotp.TOTP(seed).now()


def ensure_browser_installed() -> None:
    """Install the Chromium browser Playwright needs (idempotent)."""
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=True,
    )


def login_and_save_session(
    username: str, password: str, totp_seed: str, headed: bool
) -> None:
    """Log into my.uscis.gov and persist the session to the app dir.

    Selectors below follow USCIS's documented login flow (email + password,
    then an authentication-app verification code). They are calibrated against
    the live site in the plan's final task; if login does not reach the
    account page, a TimeoutError is raised and the caller should re-run `init`
    in headed mode.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        context = browser.new_context()
        page = context.new_page()
        page.goto(SIGN_IN_URL)

        page.get_by_label("Email").fill(username)
        page.get_by_label("Password").fill(password)
        page.get_by_role("button", name="Sign in").click()

        page.get_by_label("Secure verification code").fill(current_totp(totp_seed))
        page.get_by_role("button", name="Submit").click()

        page.wait_for_url(LOGGED_IN_URL_GLOB, timeout=30000)
        context.storage_state(path=str(config.session_path()))
        browser.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_auth.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add uscis_case_monitor/core/auth.py tests/test_auth.py
git commit -m "feat: TOTP helper and Playwright login/session"
```

---

### Task 6: client.py — authenticated fetch + expiry detection

**Files:**
- Create: `uscis_case_monitor/core/client.py`
- Test: `tests/test_client.py`

> **Note:** The `fetch_case` browser round-trip is exercised in Task 10. Here we unit-test the pure `looks_like_login` detector.

- [ ] **Step 1: Write the failing test**

`tests/test_client.py`:
```python
import pytest

from uscis_case_monitor.core import client


@pytest.mark.parametrize(
    "status,content_type,expected",
    [
        (200, "application/json; charset=utf-8", False),
        (200, "text/html; charset=utf-8", True),
        (401, "application/json", True),
        (403, "application/json", True),
        (302, "text/html", True),
    ],
)
def test_looks_like_login(status, content_type, expected):
    assert client.looks_like_login(status, content_type) is expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'uscis_case_monitor.core.client'`

- [ ] **Step 3: Write the implementation**

`uscis_case_monitor/core/client.py`:
```python
"""Authenticated fetch of a USCIS case payload using the saved session."""
from __future__ import annotations

from uscis_case_monitor.core import config

API_BASE = "https://my.uscis.gov/account/case-service/api/cases/"


class SessionExpired(Exception):
    """Raised when the saved session can no longer reach the case API."""


def looks_like_login(status: int, content_type: str) -> bool:
    """True if a response indicates we are not authenticated (redirect to
    login, auth error, or an HTML page instead of JSON)."""
    if status >= 300:
        return True
    return "application/json" not in content_type.lower()


def fetch_case(receipt_number: str) -> dict:
    """Fetch and return the case JSON. Raises SessionExpired if the saved
    session is missing or no longer valid."""
    from playwright.sync_api import sync_playwright

    session = config.session_path()
    if not session.exists():
        raise SessionExpired("No saved session.")

    url = API_BASE + receipt_number
    with sync_playwright() as p:
        request = p.request.new_context(storage_state=str(session))
        try:
            resp = request.get(url)
            content_type = resp.headers.get("content-type", "")
            if looks_like_login(resp.status, content_type):
                raise SessionExpired(f"Session invalid (status {resp.status}).")
            return resp.json()
        finally:
            request.dispose()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_client.py -v`
Expected: PASS (5 parametrized cases)

- [ ] **Step 5: Commit**

```bash
git add uscis_case_monitor/core/client.py tests/test_client.py
git commit -m "feat: authenticated case fetch with expiry detection"
```

---

### Task 7: monitor.py — orchestration (init + check with auto re-login)

**Files:**
- Create: `uscis_case_monitor/core/monitor.py`
- Test: `tests/test_monitor.py`

- [ ] **Step 1: Write the failing test**

`tests/test_monitor.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_monitor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'uscis_case_monitor.core.monitor'`

- [ ] **Step 3: Write the implementation**

`uscis_case_monitor/core/monitor.py`:
```python
"""Orchestration for init and check flows."""
from __future__ import annotations

from datetime import datetime, timezone

from uscis_case_monitor.core import auth, client, config, diff, state


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_check() -> diff.ChangeReport:
    cfg = state.load_config()
    if not cfg:
        raise RuntimeError("Not configured. Run `uscis-case-monitor init`.")
    receipt = cfg["receiptNumber"]

    try:
        payload = client.fetch_case(receipt)
    except client.SessionExpired:
        secrets = config.load_secrets()
        auth.login_and_save_session(
            secrets["username"], secrets["password"], secrets["totp_seed"], headed=False
        )
        payload = client.fetch_case(receipt)

    previous = state.load_last_response()
    report = diff.summarize(payload, previous)
    state.save_state(receipt, report.updated_at_timestamp, _now_iso())
    state.save_last_response(payload)
    return report


def run_init(
    username: str, password: str, totp_seed: str, receipt_number: str
) -> diff.ChangeReport:
    auth.ensure_browser_installed()
    config.save_secrets(username, password, totp_seed)
    auth.login_and_save_session(username, password, totp_seed, headed=True)
    state.save_config(receipt_number)

    payload = client.fetch_case(receipt_number)
    report = diff.summarize(payload, None)
    state.save_state(receipt_number, report.updated_at_timestamp, _now_iso())
    state.save_last_response(payload)
    return report
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_monitor.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add uscis_case_monitor/core/monitor.py tests/test_monitor.py
git commit -m "feat: init/check orchestration with auto re-login"
```

---

### Task 8: cli.py — Typer commands

**Files:**
- Create: `uscis_case_monitor/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
from typer.testing import CliRunner

from uscis_case_monitor import cli
from uscis_case_monitor.core import diff

runner = CliRunner()


def _report(changed):
    return diff.ChangeReport(
        receipt_number="IOE0934311580",
        form_type="I-485",
        form_name="Adjust Status",
        updated_at_timestamp="2026-05-15T10:00:00.000Z",
        changed=changed,
        new_events=[{"eventCode": "CRD0"}] if changed else [],
        new_notices=[{"actionType": "Card Was Mailed"}] if changed else [],
    )


def test_check_no_change_exit_0(monkeypatch):
    monkeypatch.setattr(cli.monitor, "run_check", lambda: _report(False))
    result = runner.invoke(cli.app, ["check"])
    assert result.exit_code == 0
    assert "No change" in result.stdout


def test_check_change_exit_10(monkeypatch):
    monkeypatch.setattr(cli.monitor, "run_check", lambda: _report(True))
    result = runner.invoke(cli.app, ["check"])
    assert result.exit_code == 10
    assert "Update detected" in result.stdout
    assert "Card Was Mailed" in result.stdout


def test_check_json_output(monkeypatch):
    monkeypatch.setattr(cli.monitor, "run_check", lambda: _report(True))
    result = runner.invoke(cli.app, ["check", "--json"])
    assert result.exit_code == 10
    assert '"changed": true' in result.stdout
    assert '"receiptNumber": "IOE0934311580"' in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'uscis_case_monitor.cli'`

- [ ] **Step 3: Write the implementation**

`uscis_case_monitor/cli.py`:
```python
"""Command-line interface for uscis-case-monitor."""
from __future__ import annotations

import json

import typer

from uscis_case_monitor.core import diff, monitor

app = typer.Typer(add_completion=False, help="Check a USCIS case status.")


def _print_human(report: diff.ChangeReport) -> None:
    header = f"{report.form_type} ({report.receipt_number}) — {report.form_name}"
    typer.echo(header)
    typer.echo(f"Last updated: {report.updated_at_timestamp}")
    if not report.changed:
        typer.echo("No change since last check.")
        return
    typer.echo("Update detected since last check:")
    for notice in report.new_notices:
        typer.echo(f"  • Notice: {notice.get('actionType', 'unknown')}")
    for event in report.new_events:
        typer.echo(f"  • Event: {event.get('eventCode', 'unknown')}")


def _print_json(report: diff.ChangeReport) -> None:
    typer.echo(
        json.dumps(
            {
                "changed": report.changed,
                "receiptNumber": report.receipt_number,
                "formType": report.form_type,
                "updatedAtTimestamp": report.updated_at_timestamp,
                "newEvents": report.new_events,
                "newNotices": report.new_notices,
            },
            indent=2,
        )
    )


@app.command()
def init() -> None:
    """First-time setup: store credentials, log in, and save a baseline."""
    username = typer.prompt("USCIS email")
    password = typer.prompt("USCIS password", hide_input=True)
    totp_seed = typer.prompt("Authenticator app OTP key (seed)", hide_input=True)
    receipt_number = typer.prompt("Case receipt number")
    report = monitor.run_init(username, password, totp_seed, receipt_number)
    typer.echo("Setup complete. Baseline saved.")
    _print_human(report)


@app.command()
def check(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output."),
) -> None:
    """Check the case and report whether it changed since the last run."""
    report = monitor.run_check()
    if json_output:
        _print_json(report)
    else:
        _print_human(report)
    raise typer.Exit(code=10 if report.changed else 0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -v`
Expected: PASS (all tests across Tasks 1-8)

- [ ] **Step 6: Commit**

```bash
git add uscis_case_monitor/cli.py tests/test_cli.py
git commit -m "feat: Typer CLI with init and check commands"
```

---

### Task 9: README — limitations, install, first-time setup

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write the README**

`README.md`:
```markdown
# USCIS Case Monitor

A small macOS command-line tool that checks a single USCIS case via your
authenticated USCIS online account and tells you whether anything changed
since the last time you ran it.

## Limitations

- **macOS only.** Tested and supported on macOS.
- **One case per installation.** Each install tracks a single receipt number.
- **Authenticator-app (TOTP) 2FA required.** Your USCIS account must use the
  "authentication app" two-step verification method, and you must have the
  **OTP key** (the long setup seed). SMS, email, and push 2FA are not supported.
- **Your own account only.** Your USCIS username, password, and TOTP seed are
  stored in your macOS Keychain so the tool can re-log-in unattended. Anyone who
  can read your Keychain could sign in to your USCIS account — only install on a
  machine you trust.
- The login automation depends on the current USCIS sign-in page; a USCIS site
  change may require an update to the tool.

## Requirements

- macOS
- Python 3.11+
- [pipx](https://pipx.pypa.io/) (recommended)

## Install

```bash
pipx install git+https://github.com/<your-username>/uscis-case-monitor
```

Then install the browser the tool drives (one time):

```bash
uscis-case-monitor --help   # confirms the command is on your PATH
```

(The first `init` run also installs the browser automatically.)

## Getting your OTP key (TOTP seed)

The tool needs the *seed* behind your authenticator app — not the rotating
6-digit code and not the 10-digit backup code.

1. Sign in at https://my.uscis.gov and open your profile / account settings.
2. Go to **two-step verification** and choose **Authentication App**.
3. USCIS shows a QR code **and** an **OTP key** text string. Copy that string —
   that is your seed.
4. Re-scan the new QR code with your phone's authenticator app so your phone and
   this tool stay in sync.

## First-time setup

```bash
uscis-case-monitor init
```

You will be prompted for:

- USCIS email
- USCIS password
- Authenticator app OTP key (the seed from the step above)
- Case receipt number (e.g. `IOE0934311580`)

A browser window opens so you can watch the login complete. On success, your
credentials are stored in Keychain, the session is saved, and a baseline of your
current case status is recorded.

## Daily use

```bash
uscis-case-monitor check
```

- If nothing changed, it prints the current status and exits with code `0`.
- If the case changed, it prints what's new (events / notices) and exits with
  code `10`.
- Add `--json` for machine-readable output.

The session is reused between runs; when it expires the tool re-logs-in
automatically. If an unexpected login prompt (e.g. a CAPTCHA) blocks automatic
login, re-run `uscis-case-monitor init`.

## Optional: run it automatically

You can schedule `uscis-case-monitor check` with `launchd` or `cron`. This is
not required — the tool is designed to be run on demand.
```

- [ ] **Step 2: Verify the command name in the README matches the entry point**

Run: `grep -n "uscis-case-monitor" README.md pyproject.toml`
Expected: the console-script name in `pyproject.toml` (`uscis-case-monitor`) matches the commands shown in the README.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README with limitations, install, and setup guide"
```

---

### Task 10: Live calibration & end-to-end verification (manual)

**Files:**
- Modify (if needed): `uscis_case_monitor/core/auth.py` (login selectors)

> This task requires the user's real USCIS credentials, OTP key, and receipt
> number. It cannot be unit-tested. Run it interactively with the user present.

- [ ] **Step 1: Run first-time setup against the live site**

Run: `uscis-case-monitor init`
Enter real email, password, OTP key, and receipt number when prompted.
Expected: a Chromium window opens and completes login automatically; the command
prints "Setup complete" and the current case status.

- [ ] **Step 2: If login fails, calibrate the selectors**

If the browser stalls or `wait_for_url` times out, inspect the live sign-in and
verification pages and adjust the locators in `auth.py:login_and_save_session`
(`get_by_label("Email")`, `get_by_label("Password")`,
`get_by_role("button", name="Sign in")`, `get_by_label("Secure verification code")`,
`get_by_role("button", name="Submit")`, and `LOGGED_IN_URL_GLOB`) to match the
actual labels/roles/URL. Re-run `uscis-case-monitor init` until it succeeds.

- [ ] **Step 3: Verify the everyday check (no change)**

Run: `uscis-case-monitor check`
Expected: prints "No change since last check." and exits `0`
(verify with `echo $?`).

- [ ] **Step 4: Verify change detection**

Edit the saved baseline to simulate a prior, different state: open the
`last_response.json` in the app data dir (path: run
`python -c "from uscis_case_monitor.core import config; print(config.last_response_path())"`),
change its `data.updatedAtTimestamp` to an older value, and remove one entry from
`data.events`. Save.
Run: `uscis-case-monitor check`
Expected: prints "Update detected", lists the re-appeared event, exits `10`
(verify with `echo $?`). Run once more; expected: back to "No change", exit `0`.

- [ ] **Step 5: Verify auto re-login**

Delete the session file (path: run
`python -c "from uscis_case_monitor.core import config; print(config.session_path())"`).
Run: `uscis-case-monitor check`
Expected: the tool re-logs-in headlessly and still returns the case status.

- [ ] **Step 6: Verify JSON output**

Run: `uscis-case-monitor check --json`
Expected: valid JSON containing `"changed"`, `"receiptNumber"`, and
`"updatedAtTimestamp"`.

- [ ] **Step 7: Commit any selector fixes**

```bash
git add uscis_case_monitor/core/auth.py
git commit -m "fix: calibrate USCIS login selectors against live site"
```

---

## Self-Review

**Spec coverage:**
- macOS-only, single-case, TOTP-only, option-A secret storage → Limitations in README (Task 9), Keychain storage (Task 2), config (Task 3). ✓
- Authenticated fetch via persisted session → client.py (Task 6), auth.py (Task 5). ✓
- Auto silent re-login with one retry → monitor.run_check (Task 7). ✓
- Diff on `updatedAtTimestamp` + new events/notices → diff.py (Task 4). ✓
- `init` / `check` commands, `--json`, exit codes 0/10 → cli.py (Task 8). ✓
- Distribution via pipx + Playwright browser install → README + monitor.run_init (Tasks 9, 7). ✓
- Unit tests for pure logic; manual live validation → Tasks 2-8 + Task 10. ✓
- `.gitignore` blocks secrets/session/state → already committed (53cd435). ✓

**Placeholder scan:** No TBD/TODO. The auth/client live-flow uncertainty is handled by real best-effort code plus an explicit calibration task (Task 10), not placeholders.

**Type consistency:** `ChangeReport` fields (`receipt_number`, `form_type`, `form_name`, `updated_at_timestamp`, `changed`, `new_events`, `new_notices`) used identically in diff.py, monitor.py, and cli.py. `SessionExpired` raised in client.py and caught in monitor.py. `config.load_secrets()` returns the same `{username,password,totp_seed}` dict consumed by monitor and auth. Consistent. ✓
