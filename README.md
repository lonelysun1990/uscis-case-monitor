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
pipx install git+https://github.com/lonelysun1990/uscis-case-monitor
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
- Case receipt number (e.g. `IOE09343115XX`)

The login runs in the background (no visible browser). On success, your
credentials are stored in Keychain, the session is saved, and a baseline of your
current case status is recorded. If you want to watch the login (e.g. to
troubleshoot), run `uscis-case-monitor init --show-browser`.

## Daily use

```bash
uscis-case-monitor check
```

- If nothing changed, it prints the current status and exits with code `0`.
- If the case changed, it prints what's new (events / notices) and exits with
  code `10`.
- Add `--json` for machine-readable output.

The session is reused between runs; when it expires the tool re-logs-in
automatically in the background. If an unexpected login prompt (e.g. a CAPTCHA)
blocks automatic login, re-run `uscis-case-monitor init --show-browser` to watch
and complete it.

## Updating

When a new version of the tool is released, reinstall it from GitHub:

```bash
pipx uninstall uscis-case-monitor
pipx install git+https://github.com/lonelysun1990/uscis-case-monitor
```

(Or in a single step: `pipx install --force git+https://github.com/lonelysun1990/uscis-case-monitor`.)

Your saved login and case settings are **kept** — they live in the macOS
Keychain and app data, not in the tool itself — so you do **not** need to run
`init` again. Just keep using `uscis-case-monitor check`. After updating you may
see a one-time macOS prompt to allow Keychain access; click **Always Allow**.

If you *do* re-run `init` after updating and hit a `Can't store password on
keychain` error, clear the old entries first, then run `init` again:

```bash
for a in username password totp_seed; do security delete-generic-password -a "$a" -s uscis-case-monitor >/dev/null 2>&1; done
uscis-case-monitor init
```

## Optional: run it automatically

You can schedule `uscis-case-monitor check` with `launchd` or `cron`. This is
not required — the tool is designed to be run on demand.
