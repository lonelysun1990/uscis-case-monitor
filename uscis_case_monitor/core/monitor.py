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
