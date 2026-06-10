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
