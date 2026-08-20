import asyncio

from app.services.orchestrator import response_pipeline as pipeline_module
from app.services.orchestrator.response_pipeline import ResponsePipeline


def test_length_limit_continues_inside_one_response(monkeypatch):
    calls = 0

    async def fake_stream_text(*, trace=None, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            trace["finish_reason"] = "length"
            yield "<html>partial"
        else:
            trace["finish_reason"] = "stop"
            yield " complete</html>"

    monkeypatch.setattr(pipeline_module, "stream_text", fake_stream_text)
    trace = {}
    async def run():
        return [chunk async for chunk in ResponsePipeline().stream(
            "Create a responsive dental clinic landing page using HTML and CSS",
            {"merged_contributions": {"selected_agents": ["Bolt"]}},
            trace=trace,
        )]
    chunks = asyncio.run(run())

    assert "".join(chunks) == "<html>partial complete</html>"
    assert trace["continuation_count"] == 1
    assert trace["finish_reason"] == "stop"


def test_multiple_length_limits_are_bounded(monkeypatch):
    calls = 0

    async def fake_stream_text(*, trace=None, **kwargs):
        nonlocal calls
        calls += 1
        trace["finish_reason"] = "stop" if calls == 3 else "length"
        yield f"segment-{calls}"

    monkeypatch.setattr(pipeline_module, "stream_text", fake_stream_text)
    trace = {}
    async def run():
        return [chunk async for chunk in ResponsePipeline().stream(
            "Build a complete HTML CSS JavaScript landing page",
            {"merged_contributions": {"selected_agents": ["Bolt"]}},
            trace=trace,
        )]
    chunks = asyncio.run(run())

    assert "".join(chunks) == "segment-1segment-2segment-3"
    assert trace["continuation_count"] == 2
    assert calls == 3


def test_ordinary_chat_does_not_continue(monkeypatch):
    async def fake_stream_text(*, trace=None, **kwargs):
        trace["finish_reason"] = "length"
        yield "short answer"

    monkeypatch.setattr(pipeline_module, "stream_text", fake_stream_text)
    trace = {}
    async def run():
        return [chunk async for chunk in ResponsePipeline().stream(
            "Explain recursion simply.", {}, trace=trace
        )]
    chunks = asyncio.run(run())

    assert chunks == ["short answer"]
    assert "continuation_count" not in trace
