import unittest
from types import SimpleNamespace
from unittest.mock import patch

from api.services import security_run_runtime


class FakeAgent:
    async def arun(self, *_args, **_kwargs):
        yield {"event": "RunContent", "content": "dict chunk"}
        yield {"event": "Other", "content": "ignored"}
        yield SimpleNamespace(event="RunContent", content="object chunk")
        yield SimpleNamespace(event="RunContent", content="")


class SecurityRunRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_stream_agent_content_filters_run_content_events(self):
        chunks = [
            chunk
            async for chunk in security_run_runtime._stream_agent_content(
                FakeAgent(),
                "hello",
                session_id="session-1",
                user_id="u1",
            )
        ]

        self.assertEqual(chunks, ["dict chunk", "object chunk"])

    async def test_provider_block_detector_matches_openai_status_error_text(self):
        self.assertTrue(
            security_run_runtime._is_provider_block_error(
                RuntimeError("Your request was blocked.")
            )
        )
        self.assertFalse(security_run_runtime._is_provider_block_error(RuntimeError("db down")))

    async def test_mcp_url_includes_runtime_token(self):
        env = {
            "MCP_SERVER_URL": "http://127.0.0.1:8000/mcp/?transport=stream",
            "MCP_TOKEN": "secret token",
        }

        with patch.object(security_run_runtime.os, "environ", env):
            self.assertEqual(
                security_run_runtime._build_mcp_url(),
                "http://127.0.0.1:8000/mcp/?transport=stream&token=secret+token",
            )


if __name__ == "__main__":
    unittest.main()
