import asyncio
import json
import logging
import traceback
from dataclasses import asdict

import httpx
import pytest

from app.services import glm


MESSAGES = [{"role": "user", "content": "Return a JSON report."}]
USAGE = {"prompt_tokens": 8, "completion_tokens": 12, "total_tokens": 20}
SECRET = "private-key-or-upstream-reasoning"


def completion(content='{"summary":"ok"}', finish_reason="stop", **extra):
    return {
        "id": "provider-id",
        "model": "glm-5.3",
        "choices": [{"index": 0, "finish_reason": finish_reason, "message": {
            "role": "assistant", "content": content, "reasoning_content": SECRET,
        }}],
        "usage": dict(USAGE),
        **extra,
    }


def chunk(content=None, finish_reason=None, **extra):
    return {"choices": [{"index": 0, "delta": {"content": content},
                         "finish_reason": finish_reason}], **extra}


def sse(*events):
    return "".join("data: " + (event if isinstance(event, str) else json.dumps(event, ensure_ascii=False))
                   + "\r\n\r\n" for event in events).encode()


class FragmentedStream(httpx.AsyncByteStream):
    def __init__(self, body, *, fragment_size=1, error=None):
        self.body = body
        self.fragment_size = fragment_size
        self.error = error
        self.closed = False

    async def __aiter__(self):
        for offset in range(0, len(self.body), self.fragment_size):
            yield self.body[offset:offset + self.fragment_size]
        if self.error is not None:
            raise self.error

    async def aclose(self):
        self.closed = True


async def invoke(client, mode):
    if mode == "json":
        return await client.complete_json(MESSAGES, "request-1")
    return [event async for event in client.stream(MESSAGES, "request-1")]


def test_complete_json_sends_official_parameters_and_returns_only_data_usage(caplog):
    caplog.set_level(logging.DEBUG)
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=completion(usage={
            **USAGE, "prompt_tokens_details": {"cached_tokens": 3},
            "completion_tokens_details": {"reasoning_tokens": 5, "reasoning_content": SECRET},
            "reasoning_content": SECRET,
        }))

    async def run():
        async with glm.GlmClient(api_key=SECRET, transport=httpx.MockTransport(handle)) as client:
            result = await client.complete_json(MESSAGES, "request-1")
        assert isinstance(result, glm.GlmJsonResult)
        assert result.data == {"summary": "ok"}
        assert result.usage == {
            **USAGE, "prompt_tokens_details": {"cached_tokens": 3},
            "completion_tokens_details": {"reasoning_tokens": 5},
        }
        assert SECRET not in repr(asdict(result))

    asyncio.run(run())
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert str(request.url) == "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    assert request.headers["authorization"] == f"Bearer {SECRET}"
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.content) == {
        "model": "glm-5.3", "messages": MESSAGES, "request_id": "request-1",
        "thinking": {"type": "enabled"}, "reasoning_effort": "max",
        "temperature": 1.0, "max_tokens": 65536, "stream": False,
        "response_format": {"type": "json_object"},
    }
    assert all(0 < value < float("inf") for value in request.extensions["timeout"].values())
    assert SECRET not in caplog.text


def test_configured_client_overrides_injected_defaults_without_owning_client():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=completion())

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle), timeout=None,
                                    auth=("wrong-user", "wrong-password")) as injected:
            async with glm.GlmClient("key", base_url="https://glm.example/v4/", model="glm-5.3",
                                     reasoning_effort="low", max_tokens=4096, timeout=2.5,
                                     client=injected) as client:
                await client.complete_json(MESSAGES, "custom-id")
            await client.aclose()
            assert not injected.is_closed

    asyncio.run(run())
    request = requests[0]
    assert str(request.url) == "https://glm.example/v4/chat/completions"
    assert request.headers["authorization"] == "Bearer key"
    assert request.extensions["timeout"] == dict.fromkeys(["connect", "read", "write", "pool"], 2.5)
    assert json.loads(request.content)["reasoning_effort"] == "low"
    assert json.loads(request.content)["max_tokens"] == 4096
    assert json.loads(request.content)["request_id"] == "custom-id"


@pytest.mark.parametrize("mode", ["json", "stream"])
@pytest.mark.parametrize("temperature", [0, 0.0, 0.01, 0.29, 0.75, 1, 1.0])
def test_configured_temperature_is_sent_for_reports_and_streams(mode, temperature):
    requests = []

    def handle(request):
        requests.append(request)
        if mode == "json":
            return httpx.Response(200, json=completion())
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              content=sse(chunk("ok", "stop", usage=USAGE), "[DONE]"))

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as injected:
            client = glm.GlmClient("key", temperature=temperature, client=injected)
            await invoke(client, mode)
            await client.aclose()
            assert not injected.is_closed

    asyncio.run(run())
    assert len(requests) == 1
    payload = json.loads(requests[0].content)
    assert payload["temperature"] == temperature
    assert payload["thinking"] == {"type": "enabled"}
    assert payload["reasoning_effort"] == "max"


@pytest.mark.parametrize("temperature", [
    None, "0.5", True, False, -0.01, 1.01, 2, 10 ** 400,
    float("nan"), float("inf"), float("-inf"), 0.001, 0.555,
])
def test_temperature_rejects_non_numeric_non_finite_or_undocumented_values(temperature):
    with pytest.raises(ValueError, match="temperature"):
        glm.GlmClient("key", temperature=temperature)


@pytest.mark.parametrize("content", [' {"ok": true} ', '```json\n{"ok": true}\n```',
                                    '```\n{"ok": true}\n```'])
def test_complete_json_accepts_object_or_one_complete_outer_fence(content):
    async def run():
        async with glm.GlmClient("key", transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=completion(content)))) as client:
            assert (await client.complete_json(MESSAGES, "request-1")).data == {"ok": True}
    asyncio.run(run())


@pytest.mark.parametrize("content", [
    '{"ok":', '{"ok": true} trailing', 'prefix {"ok": true}',
    '```json\n{"ok": true}', '```json\n{"ok": true}\n``` trailing',
    '[1, 2]', 'null', '"text"', '', None, [{"type": "text", "text": "{}"}],
    '{"n": NaN}', '{"n": Infinity}', '{"n": 1e9999}', '{"ok": 1, "ok": 2}',
])
def test_complete_json_rejects_malformed_or_non_object_json(content, caplog):
    async def run():
        async with glm.GlmClient(SECRET, transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=completion(content)))) as client:
            with pytest.raises(glm.GlmError) as caught:
                await client.complete_json(MESSAGES, "request-1")
        assert caught.value.code == "invalid_response"
        assert not caught.value.retryable
        assert SECRET not in "".join(traceback.format_exception(caught.value))
    asyncio.run(run())
    assert SECRET not in caplog.text


@pytest.mark.parametrize("finish_reason", ["length", None, "tool_calls", "sensitive", "network_error"])
def test_complete_json_rejects_incomplete_finish_even_with_valid_json(finish_reason):
    async def run():
        async with glm.GlmClient("key", transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=completion(finish_reason=finish_reason)))) as client:
            with pytest.raises(glm.GlmError) as caught:
                await client.complete_json(MESSAGES, "request-1")
        assert caught.value.code == "incomplete_response"
    asyncio.run(run())


@pytest.mark.parametrize("payload", [{}, [], {"choices": []}, {"choices": [None]},
    {"choices": [{"finish_reason": "stop", "message": None}]},
    completion(usage={"prompt_tokens": "8"}), completion(usage={"total_tokens": -1}),
    completion(usage={"total_tokens": True}), {"error": {"message": SECRET}},
])
def test_complete_json_rejects_invalid_envelopes_with_safe_error(payload):
    async def run():
        async with glm.GlmClient("key", transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload))) as client:
            with pytest.raises(glm.GlmError) as caught:
                await client.complete_json(MESSAGES, "request-1")
        assert SECRET not in "".join(traceback.format_exception(caught.value))
    asyncio.run(run())


@pytest.mark.parametrize("mode", ["json", "stream"])
@pytest.mark.parametrize("status,retryable", [(429, True), (500, True), (502, True),
                                             (503, True), (400, False), (401, False), (403, False)])
def test_http_errors_are_sanitized_classified_and_never_retried(mode, status, retryable, caplog):
    caplog.set_level(logging.DEBUG)
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(status, text=SECRET)

    async def run():
        async with glm.GlmClient(SECRET, transport=httpx.MockTransport(handle)) as client:
            with pytest.raises(glm.GlmError) as caught:
                await invoke(client, mode)
        error = caught.value
        assert error.retryable is retryable
        assert error.status_code == status
        assert error.code == ("rate_limited" if status == 429 else "upstream_error")
        assert SECRET not in repr(error)
        assert SECRET not in "".join(traceback.format_exception(error))
        assert not hasattr(error, "response")

    asyncio.run(run())
    assert len(requests) == 1
    assert SECRET not in caplog.text


@pytest.mark.parametrize("mode", ["json", "stream"])
@pytest.mark.parametrize("error_type,code", [(httpx.ReadTimeout, "timeout"),
    (httpx.ConnectTimeout, "timeout"), (httpx.PoolTimeout, "timeout"),
    (httpx.ConnectError, "transport_error"), (httpx.RemoteProtocolError, "transport_error")])
def test_transport_errors_are_safe_and_retryable(mode, error_type, code):
    def handle(request):
        raise error_type(SECRET, request=request)

    async def run():
        async with glm.GlmClient(SECRET, transport=httpx.MockTransport(handle)) as client:
            with pytest.raises(glm.GlmError) as caught:
                await invoke(client, mode)
        assert caught.value.code == code
        assert caught.value.retryable
        assert SECRET not in "".join(traceback.format_exception(caught.value))
    asyncio.run(run())


@pytest.mark.parametrize("separate_usage", [False, True])
def test_stream_handles_fragmented_sse_excludes_reasoning_and_emits_final_usage(separate_usage, caplog):
    caplog.set_level(logging.DEBUG)
    requests = []
    events = [
        {"choices": [{"index": 0, "delta": {"role": "assistant", "reasoning_content": SECRET},
                       "finish_reason": None}]},
        chunk("正式"), chunk(" answer"),
        chunk("", "stop", **({} if separate_usage else {"usage": USAGE})),
    ]
    if separate_usage:
        events.append({"choices": [], "usage": USAGE})
    body = b": heartbeat\r\n\r\nevent: message\r\nid: ignored\r\n" + sse(*events, "[DONE]")
    upstream = FragmentedStream(body)

    def handle(request):
        requests.append(request)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=upstream)

    async def run():
        async with glm.GlmClient(SECRET, transport=httpx.MockTransport(handle)) as client:
            result = await invoke(client, "stream")
        assert [asdict(event) for event in result] == [
            {"type": "text", "text": "正式"},
            {"type": "text", "text": " answer"},
            {"type": "usage", "usage": USAGE},
        ]
        assert isinstance(result[0], glm.GlmTextDelta)
        assert isinstance(result[-1], glm.GlmUsage)
        assert SECRET not in repr(result)

    asyncio.run(run())
    payload = json.loads(requests[0].content)
    assert payload == {
        "model": "glm-5.3", "messages": MESSAGES, "request_id": "request-1",
        "thinking": {"type": "enabled"}, "reasoning_effort": "max",
        "temperature": 1.0, "max_tokens": 65536, "stream": True,
    }
    assert upstream.closed
    assert SECRET not in caplog.text


def test_stream_supports_multiline_data_and_does_not_invent_missing_usage():
    body = b'data: {"choices": [\ndata: {"index":0,"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'

    async def run():
        async with glm.GlmClient("key", transport=httpx.MockTransport(lambda request:
            httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body))) as client:
            result = await invoke(client, "stream")
        assert [asdict(event) for event in result] == [
            {"type": "text", "text": "ok"}, {"type": "usage", "usage": {}},
        ]
    asyncio.run(run())


@pytest.mark.parametrize("body", [
    sse(chunk("partial")), sse(chunk("partial"), "[DONE]"),
    sse(chunk("partial", "length", usage=USAGE), "[DONE]"),
    sse(chunk("partial", "stop", usage=USAGE)),
    sse(chunk("partial")) + b'data: {"choices":',
    sse(chunk("partial", "network_error"), "[DONE]"),
])
def test_stream_rejects_incomplete_finish_without_final_usage(body):
    seen = []

    async def run():
        async with glm.GlmClient("key", transport=httpx.MockTransport(lambda request:
            httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body))) as client:
            with pytest.raises(glm.GlmError) as caught:
                async for event in client.stream(MESSAGES, "request-1"):
                    seen.append(event)
        assert caught.value.code == "incomplete_response"
        assert not any(event.type == "usage" for event in seen)
    asyncio.run(run())


@pytest.mark.parametrize("body", [sse("not-json"), sse({"choices": [None]}),
    sse(chunk([{"text": "wrong"}])), sse({"error": {"message": SECRET}}),
    sse(chunk(None, "stop"), "[DONE]"),
    sse(chunk("ok", "stop"), chunk("unexpected"), "[DONE]"),
])
def test_stream_rejects_malformed_events(body):
    async def run():
        async with glm.GlmClient(SECRET, transport=httpx.MockTransport(lambda request:
            httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body))) as client:
            with pytest.raises(glm.GlmError) as caught:
                await invoke(client, "stream")
        assert SECRET not in "".join(traceback.format_exception(caught.value))
    asyncio.run(run())


def test_stream_read_timeout_after_partial_text_closes_response_without_usage():
    upstream = FragmentedStream(sse(chunk("partial")), error=httpx.ReadTimeout(SECRET))
    seen = []

    async def run():
        async with glm.GlmClient("key", transport=httpx.MockTransport(lambda request:
            httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=upstream))) as client:
            with pytest.raises(glm.GlmError) as caught:
                async for event in client.stream(MESSAGES, "request-1"):
                    seen.append(event)
        assert caught.value.code == "timeout"
        assert caught.value.retryable
        assert [asdict(event) for event in seen] == [{"type": "text", "text": "partial"}]
    asyncio.run(run())
    assert upstream.closed


@pytest.mark.parametrize("timeout", [None, 0, -1, float("inf"), float("nan"), True])
def test_timeout_must_be_positive_and_finite(timeout):
    with pytest.raises(ValueError):
        glm.GlmClient("key", timeout=timeout)


@pytest.mark.parametrize("messages", [[], [{"role": "tool", "content": "x"}],
    [{"role": "user", "content": [{"type": "image_url", "image_url": "secret"}]}],
    [{"role": "user", "content": None}],
])
def test_only_text_messages_are_allowed_without_sending_request(messages):
    requests = []

    async def run():
        async with glm.GlmClient("key", transport=httpx.MockTransport(
            lambda request: requests.append(request))) as client:
            with pytest.raises(ValueError):
                await client.complete_json(messages, "request-1")
    asyncio.run(run())
    assert not requests


def test_outbound_messages_drop_reasoning_metadata():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=completion())

    async def run():
        async with glm.GlmClient("key", transport=httpx.MockTransport(handle)) as client:
            await client.complete_json([
                {"role": "assistant", "content": "answer", "reasoning_content": SECRET},
                *MESSAGES,
            ], "request-1")
    asyncio.run(run())
    assert SECRET.encode() not in requests[0].content


class ClosingTransport(httpx.MockTransport):
    def __init__(self, handler):
        super().__init__(handler)
        self.close_count = 0

    async def aclose(self):
        self.close_count += 1
        await super().aclose()


@pytest.mark.parametrize("mode", ["json", "stream"])
@pytest.mark.parametrize("outcome", ["success", "http_error", "timeout", "malformed"])
def test_owned_client_closes_after_each_call_without_context_manager(mode, outcome):
    def handle(request):
        if outcome == "http_error":
            return httpx.Response(429, text=SECRET)
        if outcome == "timeout":
            raise httpx.ReadTimeout(SECRET, request=request)
        if mode == "json":
            return httpx.Response(200, json=completion("bad-json" if outcome == "malformed" else "{}"))
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              content=sse("bad-json") if outcome == "malformed" else
                              sse(chunk("ok", "stop", usage=USAGE), "[DONE]"))

    transport = ClosingTransport(handle)

    async def run():
        client = glm.GlmClient("key", transport=transport)
        for expected_closes in (1, 2):
            if outcome == "success":
                await invoke(client, mode)
            else:
                with pytest.raises(glm.GlmError):
                    await invoke(client, mode)
            assert transport.close_count == expected_closes
    asyncio.run(run())


@pytest.mark.parametrize("mode", ["json", "stream"])
def test_injected_client_stays_open_after_request_and_provider_close(mode):
    def handle(request):
        if mode == "json":
            return httpx.Response(200, json=completion())
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              content=sse(chunk("ok", "stop", usage=USAGE), "[DONE]"))

    transport = ClosingTransport(handle)

    async def run():
        async with httpx.AsyncClient(transport=transport) as injected:
            provider = glm.GlmClient("key", timeout=2, client=injected)
            if mode == "json":
                result = await provider.complete_json(MESSAGES, request_id="parent-job")
                assert result.data == {"summary": "ok"}
                assert result.usage == USAGE
            else:
                events = [event async for event in provider.stream(MESSAGES, request_id="parent-job")]
                assert events[0].type == "text"
                assert events[-1].usage == USAGE
            await provider.aclose()
            assert not injected.is_closed
            assert transport.close_count == 0
        assert transport.close_count == 1
    asyncio.run(run())


def test_closing_stream_early_closes_owned_client_and_response():
    upstream = FragmentedStream(sse(chunk("partial")))
    transport = ClosingTransport(lambda request: httpx.Response(
        200, headers={"content-type": "text/event-stream"}, stream=upstream))

    async def run():
        provider = glm.GlmClient("key", transport=transport)
        iterator = provider.stream(MESSAGES, request_id="parent-job")
        assert (await anext(iterator)).text == "partial"
        await iterator.aclose()
        assert upstream.closed
        assert transport.close_count == 1
    asyncio.run(run())


@pytest.mark.parametrize("mode", ["json", "stream"])
def test_cancellation_closes_owned_client_and_propagates(mode):
    def handle(request):
        raise asyncio.CancelledError

    transport = ClosingTransport(handle)

    async def run():
        provider = glm.GlmClient("key", transport=transport)
        with pytest.raises(asyncio.CancelledError):
            await invoke(provider, mode)
        assert transport.close_count == 1
    asyncio.run(run())
