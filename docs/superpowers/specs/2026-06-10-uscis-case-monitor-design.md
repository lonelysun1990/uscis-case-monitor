# USCIS Case Monitor — Design

**Date:** 2026-06-10
**Status:** Draft for review

## Overview

A local, installable Python CLI that checks a single USCIS case's status via the
authenticated case-service API and reports whether anything has changed since the
last check. Each installation belongs to one user and tracks one case, using that
user's own credentials. The tool is distributable so non-technical users (e.g. a
spouse) can install it on their own Mac and monitor their own case.

The case-service endpoint
(`https://my.uscis.gov/account/case-service/api/cases/<RECEIPT>`) is **not** a
public API — it is authorized by the session cookies set when logging in at
`https://my.uscis.gov/account/applicant`. The tool's central job is to obtain and
maintain a valid logged-in session, then read the JSON and diff it.

## Goals

- One command (`check`) returns current case status and whether it changed since last run.
- First-time setup collects credentials + TOTP seed + receipt number interactively.
- Daily use requires no interaction while the session is valid; re-login is silent (option A).
- Installable by any macOS user via a documented, simple process.

## Non-Goals (v1 — YAGNI)

- Multiple cases per installation (single receipt number only).
- Scheduling / cron / launchd (user triggers manually; documented as an optional add-on).
- Desktop / Slack / email notifications.
- Windows or Linux support (macOS only — see Limitations).

## Limitations (must be stated in the README)

1. **macOS only.** Tested and supported on macOS only. (`keyring` and Playwright are
   cross-platform, but we neither test nor document other OSes in v1.)
2. **Single case per installation.** One receipt number per user/machine.
3. **Authenticator-app (TOTP) 2FA required.** The user's USCIS account must use the
   "authentication app" 2-step verification method, and the user must have the TOTP
   secret (OTP Key) saved from setup. SMS / email / push 2FA are not supported.
4. **Government account / your own data.** Intended only for checking your own case.
   Credentials and TOTP seed are stored locally (see Secrets). Treat the machine as
   trusted.
5. **Login-flow fragility.** The browser login automation depends on USCIS's current
   login page structure; a site redesign may require updating selectors.
6. **Session expiry.** USCIS may invalidate the session at any time; the tool
   re-authenticates automatically, but an unexpected change (e.g. CAPTCHA) may require
   re-running setup in headed mode.

## Architecture

Layered so core logic is reusable (future MCP server / scheduled job) and independently
testable.

```
uscis_case_monitor/
  core/
    auth.py       # Playwright login + TOTP, session persistence, silent re-login
    client.py     # fetch case JSON from the API using the live session
    state.py      # read/write config + last-seen timestamp + cached payload
    diff.py       # compare current vs last updatedAtTimestamp; summarize changes
    config.py     # paths (platformdirs), keyring access
  cli.py          # Typer wrapper: `init`, `check`
  __init__.py
pyproject.toml    # packaging + console-script entry point
README.md         # limitations, install, first-time setup
tests/
  fixtures/       # saved case JSON payloads
  test_diff.py
  test_state.py
```

`core/` has no CLI dependency. `cli.py` is a thin shell over it.

## Data Flow (`check`)

1. Load session (`storage_state.json`) and config (receipt number).
2. `client` performs an authenticated GET on `…/cases/<RECEIPT>` using the saved
   session context (cookies travel with the request).
3. If the response is a login redirect / 401 / non-JSON login page → `auth` silently
   re-logs-in using credentials + TOTP seed from Keychain, saves a fresh
   `storage_state.json`, and retries the GET **once**.
4. Parse JSON. Compare `data.updatedAtTimestamp` against the stored last value.
5. Report (see Output). Persist new timestamp, `lastCheckedAt`, and the full payload.

## Secrets & State (option A — fully unattended)

- **Keychain (via `keyring`):** `username`, `password`, `totp_seed`.
- **App data dir (via `platformdirs`, perms `0700`; files `0600`):**
  - `storage_state.json` — Playwright session (cookies + local storage; sensitive).
  - `state.json` — `{ receiptNumber, lastUpdatedAtTimestamp, lastCheckedAt }`.
  - `last_response.json` — full payload from previous run, for diffing event/notice detail.

Option A explicitly accepts that anything able to read the user's Keychain could
authenticate into their USCIS account. Documented in the README.

## CLI Commands

- **`uscis-case-monitor init`**
  - Prompts: username, password, TOTP seed, receipt number.
  - Runs `playwright install chromium` if the browser isn't present.
  - Performs a first **headed** login (so the user can see/intervene), auto-filling the
    TOTP code via `pyotp`; on success saves session + secrets + config.
  - Confirms by fetching the case once and printing current status.

- **`uscis-case-monitor check`** (default command)
  - The everyday command. Loads session, fetches case, diffs, reports. Silent re-login
    on expiry. Updates state.
  - Flags: `--json` (structured output for scripts/agents).

## Output & Exit Codes

- **No change:** one human-readable line (form type, current status, `updatedAt`),
  exit code `0`.
- **Change detected:** highlights new `updatedAtTimestamp`, plus any **new events /
  notices** vs the cached payload (e.g. a new `Appointment Scheduled` notice or new
  `eventCode`). Exit code `10`.
- **Error:** message to stderr, non-zero exit (not `0`/`10`).
- `--json`: emits `{ changed: bool, receiptNumber, updatedAtTimestamp, status, newEvents, newNotices }`.

## Error Handling

- Session expired / unauthorized → auto re-login, one retry, then fail with a clear message.
- Login failure (bad creds, unexpected page, CAPTCHA) → stop; instruct user to re-run
  `init` in headed mode.
- Network / 5xx → fail cleanly; leave stored state untouched.

## Distribution & Install

- **Packaging:** `pyproject.toml` with a `uscis-case-monitor` console-script entry point.
- **Install:** GitHub repo, installed via `pipx install git+https://github.com/<user>/uscis-case-monitor`
  (pipx gives an isolated environment — clean for non-developers).
- **Browser:** `playwright install chromium` handled by `init` (or documented as a one-time step).
- **README must contain:** the Limitations section above, the install steps, and a
  first-time-setup walkthrough (how to find/save the USCIS TOTP OTP Key, running `init`,
  then daily `check`).

## Testing

- **Unit-tested without the live site:** `diff.py` and `state.py` against saved JSON
  fixtures (the provided sample payload is fixture #1; variants cover "no change",
  "new event", "new notice").
- **Manual validation:** `auth.py` / `client.py` live-login path verified against the
  real site during implementation (the one part not unit-testable without real
  credentials). Selector tuning expected here.

## Open Implementation Risks

- USCIS login DOM/redirect specifics are unknown until driven live; selectors will need
  tuning with real credentials.
- Possible CAPTCHA or device-trust prompts on login that defeat full automation; the
  fallback is headed `init`.
- Session cookie lifetime is unknown; the auto-relogin path must be robust to it.
