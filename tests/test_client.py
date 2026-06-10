import pytest

from uscis_case_monitor.core import client


@pytest.mark.parametrize(
    "status,content_type,expected",
    [
        (200, "application/json; charset=utf-8", False),
        (200, "text/html; charset=utf-8", True),
        (401, "application/json", True),
        (403, "application/json", True),
        (302, "text/html", True),
    ],
)
def test_looks_like_login(status, content_type, expected):
    assert client.looks_like_login(status, content_type) is expected
