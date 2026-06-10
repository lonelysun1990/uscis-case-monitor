import pyotp

from uscis_case_monitor.core import auth


def test_current_totp_matches_pyotp():
    seed = "JBSWY3DPEHPK3PXP"
    code = auth.current_totp(seed)
    assert len(code) == 6
    assert code.isdigit()
    assert pyotp.TOTP(seed).verify(code)
