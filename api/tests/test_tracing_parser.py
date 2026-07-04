from __future__ import annotations
from api.services.tracing_service import parse_span_display


def test_parse_span_display_extracts_agentos_input_output_metadata() -> None:
    span = {
        "name": "OpenAIChat.ainvoke_stream",
        "attributes": {
            "input.value": '{"messages":[{"role":"user","content":"latest news?"}]}',
            "output.value": '{"content":"Here are the latest stories."}',
            "gen_ai.request.model": "gpt-5.2",
            "gen_ai.usage.prompt_tokens": 31,
            "gen_ai.usage.completion_tokens": 42,
        },
        "events": [
            {"name": "exception", "attributes": {"exception.message": "tool timeout"}}
        ],
    }
    parsed = parse_span_display(span)
    assert parsed["input"]["format"] == "json"
    assert "latest news?" in parsed["input"]["text"]
    assert parsed["output"]["format"] == "json"
    assert "latest stories" in parsed["output"]["text"]
    assert parsed["metadata"]["model"] == "gpt-5.2"
    assert parsed["metadata"]["tokens"]["prompt"] == 31
    assert parsed["events"][0]["message"] == "tool timeout"
