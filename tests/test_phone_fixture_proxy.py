import pytest

from scripts.serve_closeout_phone import allowed_cookie, private_bind


def test_proxy_only_accepts_exact_fixture_session():
    tokens = {"synthetic-test-session"}
    assert allowed_cookie("access_token=synthetic-test-session", tokens)
    assert not allowed_cookie("access_token=synthetic-test-session-extra", tokens)
    assert not allowed_cookie("access_token=other", tokens)
    assert not allowed_cookie("", tokens)


@pytest.mark.parametrize("value", ["0.0.0.0", "127.0.0.1", "example.com", "8.8.8.8", "100.64.0.1", "192.0.2.1"])
def test_proxy_refuses_non_private_interface(value):
    with pytest.raises(ValueError):
        private_bind(value)


def test_proxy_accepts_explicit_private_interface():
    assert private_bind("10.129.156.78") == "10.129.156.78"
