"""Unit tests for llm_bridge/server.py helpers."""
from llm_bridge import server


def test_parse_bearer_token():
    assert server._parse_bearer_token("Bearer abc123") == "abc123"
    assert server._parse_bearer_token("bearer token") == "token"
    assert server._parse_bearer_token("Token abc") is None
    assert server._parse_bearer_token("") is None


def test_is_authorized():
    assert server._is_authorized("Bearer secret", "secret") is True
    assert server._is_authorized("Bearer wrong", "secret") is False
    assert server._is_authorized(None, "secret") is False


def test_build_upstream_url():
    assert (
        server._build_upstream_url("http://127.0.0.1:1234", "/v1/models")
        == "http://127.0.0.1:1234/v1/models"
    )
    assert (
        server._build_upstream_url("http://127.0.0.1:1234/", "/v1/chat/completions?x=1")
        == "http://127.0.0.1:1234/v1/chat/completions?x=1"
    )
