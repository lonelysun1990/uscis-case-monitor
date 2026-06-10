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
def init(
    show_browser: bool = typer.Option(
        False,
        "--show-browser",
        help="Show the login browser window (for troubleshooting).",
    ),
) -> None:
    """First-time setup: store credentials, log in, and save a baseline."""
    username = typer.prompt("USCIS email")
    password = typer.prompt("USCIS password", hide_input=True)
    totp_seed = typer.prompt("Authenticator app OTP key (seed)", hide_input=True)
    receipt_number = typer.prompt("Case receipt number")
    try:
        report = monitor.run_init(
            username, password, totp_seed, receipt_number, headed=show_browser
        )
    except Exception as exc:  # noqa: BLE001 - top-level CLI boundary
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)
    typer.echo("Setup complete. Baseline saved.")
    _print_human(report)


@app.command()
def check(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output."),
) -> None:
    """Check the case and report whether it changed since the last run."""
    try:
        report = monitor.run_check()
    except Exception as exc:  # noqa: BLE001 - top-level CLI boundary
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)
    if json_output:
        _print_json(report)
    else:
        _print_human(report)
    raise typer.Exit(code=10 if report.changed else 0)
