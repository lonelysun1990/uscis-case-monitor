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
