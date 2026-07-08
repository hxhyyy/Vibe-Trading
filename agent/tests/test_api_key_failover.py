"""Tests for API key failover rotation."""

from __future__ import annotations

import pytest

from src.providers.api_key_failover import ApiKeyFailoverLLM, is_failover_error, split_api_keys


class _FakeLLM:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def invoke(self, input, config=None, **kwargs):
        if self.api_key == "bad":
            raise RuntimeError("HTTP 429 Too Many Requests")
        return f"ok:{self.api_key}"


def test_split_api_keys_supports_multiple_separators() -> None:
    keys = split_api_keys("k1|k2\nk3,k4;k5")
    assert keys == ["k1", "k2", "k3", "k4", "k5"]


def test_split_api_keys_deduplicates() -> None:
    assert split_api_keys("k1|k1|k2") == ["k1", "k2"]


@pytest.mark.parametrize(
    "message",
    [
        "HTTP 429 Too Many Requests",
        "Error 403: forbidden",
        "rate limit exceeded",
        "resource exhausted",
    ],
)
def test_is_failover_error(message: str) -> None:
    assert is_failover_error(RuntimeError(message)) is True


def test_is_failover_error_rejects_generic_failure() -> None:
    assert is_failover_error(RuntimeError("invalid api key")) is False


def test_api_key_failover_rotates_on_429() -> None:
    used_keys: list[str] = []

    def factory(api_key: str) -> _FakeLLM:
        used_keys.append(api_key)
        return _FakeLLM(api_key)

    llm = ApiKeyFailoverLLM(
        factory,
        ["bad", "good"],
        provider="openai",
        model="test-model",
    )

    assert llm.invoke("hello") == "ok:good"
    assert used_keys == ["bad", "good"]
