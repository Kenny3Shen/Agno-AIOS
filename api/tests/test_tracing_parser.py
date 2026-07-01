from __future__ import annotations

import unittest

from api.services.tracing_service import parse_span_display


class TraceSpanParserContractTest(unittest.TestCase):
    def test_parse_span_display_extracts_agentos_input_output_metadata(self) -> None:
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
                {
                    "name": "exception",
                    "attributes": {"exception.message": "tool timeout"},
                }
            ],
        }

        parsed = parse_span_display(span)

        self.assertEqual(parsed["input"]["format"], "json")
        self.assertIn("latest news?", parsed["input"]["text"])
        self.assertEqual(parsed["output"]["format"], "json")
        self.assertIn("latest stories", parsed["output"]["text"])
        self.assertEqual(parsed["metadata"]["model"], "gpt-5.2")
        self.assertEqual(parsed["metadata"]["tokens"]["prompt"], 31)
        self.assertEqual(parsed["events"][0]["message"], "tool timeout")


if __name__ == "__main__":
    unittest.main()
