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


def test_check_handles_error_cleanly(monkeypatch):
    def boom():
        raise RuntimeError("Not configured. Run `uscis-case-monitor init`.")
    monkeypatch.setattr(cli.monitor, "run_check", boom)
    result = runner.invoke(cli.app, ["check"])
    assert result.exit_code == 1
    assert "Not configured" in result.output
    assert "Traceback" not in result.output
