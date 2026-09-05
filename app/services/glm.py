"""Text-only GLM transport; queueing, retries and persistence belong to callers.

Only formal ``content`` leaves this module. Provider reasoning and response bodies
are never logged or included in errors. Streaming deltas are provisional until a
``GlmUsage`` event confirms a normal finish and the provider's [DONE] marker.
"""

from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import json
import math
import re
from typing import Any, Literal

import httpx


DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
Usage = dict[str, Any]


@dataclass(frozen=True)
class GlmJsonResult:
    data: dict[str, Any]
    usage: Usage


@dataclass(frozen=True)
class GlmTextDelta:
    text: str
    type: Literal["text"] = field(default="text", init=False)


@dataclass(frozen=True)
class GlmUsage:
    """Final usage; an empty dict means the provider did not supply usage."""

    usage: Usage
    type: Literal["usage"] = field(default="usage", init=False)


class GlmError(Exception):
    """Safe to surface or log; contains no upstream request or response object."""

    def __init__(self, code: str, *, retryable: bool, status_code: int | None = None, retry_after_seconds: float | None = None):
        super().__init__("GLM request failed.")
        self.code = code
        self.retryable = retryable
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


def _invalid_response() -> GlmError:
    return GlmError("invalid_response", retryable=False)


def _http_error(status: int, retry_after: str | None = None) -> GlmError:
    delay = None
    if retry_after:
        try:
            number = float(retry_after)
            if math.isfinite(number):
                delay = min(3600, max(0, number))
        except ValueError:
            from email.utils import parsedate_to_datetime
            from datetime import datetime, timezone
            try:
                date = parsedate_to_datetime(retry_after)
                delay = min(3600, max(0, (date - datetime.now(timezone.utc)).total_seconds()))
            except (ValueError, TypeError, OverflowError):
                pass
    return GlmError(
        "rate_limited" if status == 429 else "upstream_error",
        retryable=status == 429 or 500 <= status < 600,
        status_code=status,
        retry_after_seconds=delay,
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite JSON number")
    return number


def _reject_constant(value: str) -> None:
    raise ValueError("Invalid JSON constant")


def _json_object(value: str | bytes) -> dict[str, Any]:
    try:
        result = json.loads(
            value, object_pairs_hook=_unique_object,
            parse_float=_finite_float, parse_constant=_reject_constant,
        )
    except (ValueError, TypeError, RecursionError):
        raise _invalid_response() from None
    if not isinstance(result, dict):
        raise _invalid_response()
    return result


def _usage(value: Any) -> Usage:
    """Allowlist token counters, never copy arbitrary upstream metadata."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise _invalid_response()

    def counters(source: dict, names: tuple[str, ...]) -> dict[str, int]:
        result = {}
        for name in names:
            if name in source:
                count = source[name]
                if type(count) is not int or count < 0:
                    raise _invalid_response()
                result[name] = count
        return result

    result: Usage = counters(value, ("prompt_tokens", "completion_tokens", "total_tokens"))
    for name, keys in (
        ("prompt_tokens_details", ("cached_tokens",)),
        ("completion_tokens_details", ("reasoning_tokens",)),
    ):
        details = value.get(name)
        if details is not None:
            if not isinstance(details, dict):
                raise _invalid_response()
            result[name] = counters(details, keys)
    return result


def _check_envelope(payload: dict[str, Any]) -> None:
    if "error" in payload:
        error = payload["error"]
        status = error.get("code") if isinstance(error, dict) else None
        if type(status) is int and 400 <= status < 600:
            raise _http_error(status)
        raise GlmError("upstream_error", retryable=False)


def _choice(choices: Any) -> dict[str, Any]:
    if not isinstance(choices, list) or len(choices) != 1:
        raise _invalid_response()
    choice = choices[0]
    if not isinstance(choice, dict) or choice.get("index", 0) != 0:
        raise _invalid_response()
    return choice


def _check_finish(reason: Any) -> None:
    if reason != "stop":
        raise GlmError("incomplete_response", retryable=reason in (None, "network_error"))


async def _sse_data(response: httpx.Response) -> AsyncIterator[str]:
    """Frame SSE events across arbitrary byte/UTF-8/line boundaries."""
    data: list[str] = []
    async for line in response.aiter_lines():
        if line == "":
            if data:
                yield "\n".join(data)
                data.clear()
        elif line.startswith("data:"):
            value = line[5:]
            data.append(value[1:] if value.startswith(" ") else value)
        elif line == "data":
            data.append("")
    # EOF does not dispatch a partial frame. The caller requires [DONE].


class GlmClient:
    """Async HTTP transport with a finite timeout for each I/O operation.

    ``base_url`` is the API root (ending in /v4 by default). ``timeout`` is
    positive, finite seconds, applied to connect/read/write/pool even for an
    injected client. Owned HTTP clients are created per request and always
    closed when it ends, including errors and cancellation. ``aclose()`` also
    closes any active owned clients. An injected ``client`` remains caller-owned.
    Do not pass both injection options. No request is retried internally.
    ``temperature`` follows BigModel's [0, 1] range with at most two decimals.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = "glm-5.3",
        reasoning_effort: str = "max",
        max_tokens: int = 65536,
        timeout: float = 120.0,
        *,
        temperature: float = 1.0,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        if not isinstance(api_key, str) or not api_key.strip() or any(c in api_key for c in "\r\n"):
            raise ValueError("A valid GLM API key is required")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("A GLM model is required")
        if reasoning_effort not in ("low", "high", "max"):
            raise ValueError("Invalid GLM reasoning effort")
        if type(max_tokens) is not int or max_tokens <= 0:
            raise ValueError("GLM max_tokens must be a positive integer")
        if (type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0):
            raise ValueError("GLM timeout must be positive and finite")
        if (type(temperature) not in (int, float) or not 0 <= temperature <= 1
                or not math.isfinite(temperature) or round(temperature, 2) != temperature):
            raise ValueError("GLM temperature must be finite, between 0 and 1, with at most two decimals")
        if client is not None and transport is not None:
            raise ValueError("Supply either a GLM client or transport")
        try:
            root = httpx.URL(base_url)
        except (TypeError, ValueError, httpx.InvalidURL):
            raise ValueError("Invalid GLM base URL") from None
        if (root.scheme not in ("http", "https") or not root.host
                or root.userinfo or root.query or root.fragment):
            raise ValueError("Invalid GLM base URL")
        self._url = str(root).rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._max_tokens = max_tokens
        self._temperature = float(temperature)
        self._timeout = httpx.Timeout(timeout)
        self._client = client
        self._transport = transport
        self._active_clients: set[httpx.AsyncClient] = set()

    async def __aenter__(self) -> "GlmClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        for client in tuple(self._active_clients):
            await client.aclose()

    def _payload(
        self, messages: Sequence[Mapping[str, str]], request_id: str, *, stream: bool,
    ) -> dict[str, Any]:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("A GLM request ID is required")
        if not isinstance(messages, Sequence) or not messages:
            raise ValueError("GLM requires text messages")
        clean_messages = []
        for message in messages:
            if (not isinstance(message, Mapping)
                    or message.get("role") not in ("system", "user", "assistant")
                    or not isinstance(message.get("content"), str)):
                raise ValueError("GLM requires text messages")
            clean_messages.append({"role": message["role"], "content": message["content"]})
        payload = {
            "model": self._model,
            "messages": clean_messages,
            "request_id": request_id,
            "thinking": {"type": "enabled"},
            "reasoning_effort": self._reasoning_effort,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "stream": stream,
        }
        if not stream:
            payload["response_format"] = {"type": "json_object"}
        return payload

    @asynccontextmanager
    async def _response(self, payload: dict[str, Any]) -> AsyncIterator[httpx.Response]:
        client = self._client
        owned = client is None
        if owned:
            client = httpx.AsyncClient(transport=self._transport)
            self._active_clients.add(client)
        try:
            async with client.stream(
                "POST", self._url, json=payload,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Accept": "text/event-stream" if payload["stream"] else "application/json",
                },
                timeout=self._timeout, follow_redirects=False, auth=None,
            ) as response:
                if not 200 <= response.status_code < 300:
                    # Do not read, log or attach an error body.
                    raise _http_error(response.status_code, response.headers.get("Retry-After"))
                yield response
        except httpx.TimeoutException:
            raise GlmError("timeout", retryable=True) from None
        except httpx.RequestError:
            raise GlmError("transport_error", retryable=True) from None
        finally:
            if owned:
                try:
                    await client.aclose()
                finally:
                    self._active_clients.discard(client)

    async def complete_json(
        self, messages: Sequence[Mapping[str, str]], request_id: str,
    ) -> GlmJsonResult:
        """Parse one JSON object, optionally wrapped in one complete JSON fence.

        Prose, malformed JSON, duplicate keys, non-finite numbers and any finish
        other than ``stop`` fail. No repair or inferred report is attempted.
        """
        async with self._response(self._payload(messages, request_id, stream=False)) as response:
            payload = _json_object(await response.aread())
        _check_envelope(payload)
        choice = _choice(payload.get("choices"))
        _check_finish(choice.get("finish_reason"))
        message = choice.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise _invalid_response()
        content = message["content"].strip()
        fence = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n```", content, flags=re.DOTALL)
        if fence:
            content = fence.group(1)
        return GlmJsonResult(data=_json_object(content), usage=_usage(payload.get("usage")))

    async def stream(
        self, messages: Sequence[Mapping[str, str]], request_id: str,
    ) -> AsyncIterator[GlmTextDelta | GlmUsage]:
        """Yield formal text, then usage after a complete SSE response.

        Reasoning-only deltas are discarded. A raised error invalidates earlier
        text; consumers should explicitly close the iterator if they stop early.
        """
        usage: Usage = {}
        stopped = False
        done = False
        has_text = False
        async with self._response(self._payload(messages, request_id, stream=True)) as response:
            if response.headers.get("content-type", "").split(";", 1)[0].strip() != "text/event-stream":
                raise _invalid_response()
            async for data in _sse_data(response):
                if data == "[DONE]":
                    done = True
                    break
                payload = _json_object(data)
                _check_envelope(payload)
                if payload.get("usage") is not None:
                    usage = _usage(payload["usage"])
                choices = payload.get("choices")
                if choices == [] and payload.get("usage") is not None:
                    continue
                choice = _choice(choices)
                if stopped:
                    raise _invalid_response()
                reason = choice.get("finish_reason")
                if reason is not None:
                    _check_finish(reason)
                    stopped = True
                delta = choice.get("delta")
                if not isinstance(delta, dict):
                    raise _invalid_response()
                content = delta.get("content")
                if content is not None and not isinstance(content, str):
                    raise _invalid_response()
                if content:
                    has_text = True
                    yield GlmTextDelta(text=content)
        if not done or not stopped:
            raise GlmError("incomplete_response", retryable=True)
        if not has_text:
            raise _invalid_response()
        yield GlmUsage(usage=usage)
