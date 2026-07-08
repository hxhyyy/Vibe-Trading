"""Rotate API keys on rate-limit / quota errors (ported from TradingAgents-CN)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from typing import Any, Callable

logger = logging.getLogger(__name__)


def split_api_keys(api_key: str | None) -> list[str]:
    """Parse multiple API keys separated by ``|``, ``,``, ``;``, or newlines."""
    if not api_key:
        return []
    raw = str(api_key).replace("\r", "\n")
    for sep in (";", ",", "\n"):
        raw = raw.replace(sep, "|")
    keys = [k.strip() for k in raw.split("|") if k.strip()]
    deduped: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if key not in seen:
            seen.add(key)
            deduped.append(key)
    return deduped


def is_failover_error(exc: Exception) -> bool:
    """Return True when switching to the next API key may help."""
    status = getattr(exc, "status_code", None)
    if status in (403, 429):
        return True
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "403",
            "429",
            "too many requests",
            "rate limit",
            "resource exhausted",
            "quota exceeded",
            "forbidden",
        )
    )


def _mask_api_key(api_key: str) -> str:
    if len(api_key) > 12:
        return f"{api_key[:8]}...{api_key[-4:]}"
    return "***"


class ApiKeyFailoverLLM:
    """Retry LLM calls with the next configured API key on failover errors."""

    def __init__(
        self,
        llm_factory: Callable[[str], Any],
        api_keys: list[str],
        provider: str,
        model: str,
    ) -> None:
        if len(api_keys) < 2:
            raise ValueError("ApiKeyFailoverLLM requires at least two API keys")
        self._llm_factory = llm_factory
        self._api_keys = api_keys
        self._provider = provider
        self._model = model
        self._index = 0
        self._llm = self._llm_factory(self._api_keys[self._index])

    @property
    def active_api_key(self) -> str:
        return self._api_keys[self._index]

    def _rotate_key(self) -> None:
        self._index = (self._index + 1) % len(self._api_keys)
        self._llm = self._llm_factory(self._api_keys[self._index])
        logger.warning(
            "API key failover: %s/%s switched to %s",
            self._provider,
            self._model,
            _mask_api_key(self._api_keys[self._index]),
        )

    def _should_failover(self, exc: Exception, attempt: int) -> bool:
        return is_failover_error(exc) and attempt < len(self._api_keys) - 1

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        last_error: Exception | None = None
        for attempt in range(len(self._api_keys)):
            try:
                return self._llm.invoke(input, config=config, **kwargs)
            except Exception as exc:
                last_error = exc
                if self._should_failover(exc, attempt):
                    self._rotate_key()
                    continue
                raise
        raise last_error or RuntimeError("LLM invoke failed after API key failover")

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        last_error: Exception | None = None
        for attempt in range(len(self._api_keys)):
            try:
                return await self._llm.ainvoke(input, config=config, **kwargs)
            except Exception as exc:
                last_error = exc
                if self._should_failover(exc, attempt):
                    self._rotate_key()
                    continue
                raise
        raise last_error or RuntimeError("LLM ainvoke failed after API key failover")

    def stream(self, input: Any, config: Any = None, **kwargs: Any) -> Iterator[Any]:
        last_error: Exception | None = None
        for attempt in range(len(self._api_keys)):
            try:
                yield from self._llm.stream(input, config=config, **kwargs)
                return
            except Exception as exc:
                last_error = exc
                if self._should_failover(exc, attempt):
                    self._rotate_key()
                    continue
                raise
        raise last_error or RuntimeError("LLM stream failed after API key failover")

    async def astream(self, input: Any, config: Any = None, **kwargs: Any) -> AsyncIterator[Any]:
        last_error: Exception | None = None
        for attempt in range(len(self._api_keys)):
            try:
                async for chunk in self._llm.astream(input, config=config, **kwargs):
                    yield chunk
                return
            except Exception as exc:
                last_error = exc
                if self._should_failover(exc, attempt):
                    self._rotate_key()
                    continue
                raise
        raise last_error or RuntimeError("LLM astream failed after API key failover")

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        parent = self

        class _BoundToolInvoker:
            def invoke(self, input: Any, config: Any = None, **invoke_kwargs: Any) -> Any:
                last_error: Exception | None = None
                for attempt in range(len(parent._api_keys)):
                    try:
                        bound = parent._llm.bind_tools(tools, **kwargs)
                        return bound.invoke(input, config=config, **invoke_kwargs)
                    except Exception as exc:
                        last_error = exc
                        if parent._should_failover(exc, attempt):
                            parent._rotate_key()
                            continue
                        raise
                raise last_error or RuntimeError("Tool invoke failed after API key failover")

            async def ainvoke(self, input: Any, config: Any = None, **invoke_kwargs: Any) -> Any:
                last_error: Exception | None = None
                for attempt in range(len(parent._api_keys)):
                    try:
                        bound = parent._llm.bind_tools(tools, **kwargs)
                        return await bound.ainvoke(input, config=config, **invoke_kwargs)
                    except Exception as exc:
                        last_error = exc
                        if parent._should_failover(exc, attempt):
                            parent._rotate_key()
                            continue
                        raise
                raise last_error or RuntimeError("Tool ainvoke failed after API key failover")

            def stream(self, input: Any, config: Any = None, **invoke_kwargs: Any) -> Iterator[Any]:
                last_error: Exception | None = None
                for attempt in range(len(parent._api_keys)):
                    try:
                        bound = parent._llm.bind_tools(tools, **kwargs)
                        yield from bound.stream(input, config=config, **invoke_kwargs)
                        return
                    except Exception as exc:
                        last_error = exc
                        if parent._should_failover(exc, attempt):
                            parent._rotate_key()
                            continue
                        raise
                raise last_error or RuntimeError("Tool stream failed after API key failover")

        return _BoundToolInvoker()

    def __getattr__(self, item: str) -> Any:
        return getattr(self._llm, item)
