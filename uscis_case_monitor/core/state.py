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
