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
