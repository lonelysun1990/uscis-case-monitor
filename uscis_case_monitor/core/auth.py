"""TOTP generation and Playwright-based login/session persistence."""
from __future__ import annotations

import subprocess
import sys

import pyotp

from uscis_case_monitor.core import config

SIGN_IN_URL = "https://myaccount.uscis.gov/sign-in"
# The case-service API is hosted here; we visit it after login so the saved
# session also carries this host's cookies (login happens on myaccount.uscis.gov).
ACCOUNT_URL = "https://my.uscis.gov/account/applicant"

# USCIS serves an error page to the bare headless Chromium UA, so present a
# normal desktop Chrome UA for both headed and headless (silent re-login) runs.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
)


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
    """Log into the USCIS online account and persist the session to the app dir.

    Selectors are calibrated against the live myaccount.uscis.gov sign-in flow:
    email + password, then an authentication-app verification code. The
    "Remember this browser" box is ticked so future runs are less likely to be
    challenged for 2FA again. If login does not reach the account page a
    TimeoutError is raised and the caller should re-run `init` in headed mode.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        try:
            context = browser.new_context(user_agent=USER_AGENT, locale="en-US")
            page = context.new_page()
            # Do NOT wait for networkidle: the USCIS SPA holds background
            # connections open, so networkidle never fires and goto times out.
            page.goto(SIGN_IN_URL, wait_until="domcontentloaded", timeout=60000)

            # Type with real keystrokes (NOT .fill): this React form only marks
            # fields valid/touched on per-keystroke events, so .fill() leaves the
            # Sign In button a no-op.
            page.locator("#email-address").wait_for(state="visible", timeout=30000)
            page.locator("#email-address").click()
            page.locator("#email-address").press_sequentially(username, delay=20)
            page.locator("#password").click()
            page.locator("#password").press_sequentially(password, delay=20)
            page.locator("#password").press("Tab")  # blur to trigger validation

            # Submit, retrying to absorb the React hydration race: an early click
            # is a no-op until the button's handler is wired up. Stop as soon as
            # the 2FA code field appears.
            code_field = page.locator("#secure-verification-code")
            for _ in range(5):
                # The button click alone is unreliable on this form; submitting
                # with Enter from the password field is what actually advances.
                try:
                    page.locator("#sign-in-btn").click(timeout=3000)
                except Exception:  # noqa: BLE001 - button not yet interactive
                    pass
                try:
                    page.locator("#password").press("Enter")
                except Exception:  # noqa: BLE001 - field may have detached
                    pass
                try:
                    code_field.wait_for(state="visible", timeout=6000)
                    break
                except Exception:  # noqa: BLE001 - not advanced yet, retry
                    continue
            else:
                raise TimeoutError(
                    "Sign-in did not reach the 2FA code page (check credentials)."
                )

            # 2FA page: type the authenticator code and remember this browser.
            code_field.click()
            code_field.press_sequentially(current_totp(totp_seed), delay=20)
            remember = page.locator("#remember-me-checkbox")
            if remember.count() and not remember.is_checked():
                remember.check()
            try:
                page.locator("#2fa-submit-btn").click(timeout=3000)
            except Exception:  # noqa: BLE001 - fall back to Enter
                pass
            try:
                code_field.press("Enter")
            except Exception:  # noqa: BLE001 - field may have detached
                pass

            # Logged in once we've left the sign-in / 2FA pages.
            page.wait_for_url(
                lambda url: "/sign-in" not in url and "/auth" not in url,
                timeout=45000,
            )
            # Establish the my.uscis.gov session (case API host) before snapshot.
            try:
                page.goto(ACCOUNT_URL, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(2500)
            except Exception:  # noqa: BLE001 - best effort; snapshot regardless
                pass
            context.storage_state(path=str(config.session_path()))
        finally:
            browser.close()
