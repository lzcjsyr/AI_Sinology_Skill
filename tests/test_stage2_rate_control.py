from __future__ import annotations

import json
import unittest
from unittest.mock import Mock
from unittest.mock import patch

import litellm

import runtime.stage2.runner as runner_module
from runtime.stage2.runner import LiteLLMClient, Stage2RunnerError


def _mock_response(payload: dict) -> Mock:
    response = Mock()
    response.model_dump.return_value = payload
    return response


class Stage2LiteLLMClientTests(unittest.TestCase):
    def test_client_rotates_api_keys_round_robin(self) -> None:
        client = LiteLLMClient(
            model="test-model",
            base_url="https://example.com/v1/chat/completions",
            api_keys=("key-a", "key-b"),
            slot="llm1",
        )
        payload = {
            "choices": [{"message": {"content": json.dumps({"ok": True}, ensure_ascii=False)}}],
            "usage": {"total_tokens": 12},
        }
        seen_keys: list[str] = []
        seen_bases: list[str] = []

        def fake_completion(**kwargs):  # noqa: ANN003
            seen_keys.append(kwargs["api_key"])
            seen_bases.append(kwargs["base_url"])
            return _mock_response(payload)

        with patch("runtime.stage2.runner.completion", side_effect=fake_completion):
            client.chat_json(messages=[{"role": "user", "content": "hi"}], max_tokens=32)
            client.chat_json(messages=[{"role": "user", "content": "hi"}], max_tokens=32)

        self.assertEqual(seen_keys, ["key-a", "key-b"])
        self.assertEqual(seen_bases, ["https://example.com/v1", "https://example.com/v1"])

    def test_client_retries_without_response_format_after_bad_request(self) -> None:
        client = LiteLLMClient(
            model="test-model",
            base_url="https://example.com/v1",
            api_keys=("test-key",),
            slot="llm1",
        )
        payload = {
            "choices": [{"message": {"content": json.dumps({"ok": True}, ensure_ascii=False)}}],
            "usage": {"total_tokens": 12},
        }
        bad_request = litellm.BadRequestError("bad", model="test-model", llm_provider="openai")

        with patch(
            "runtime.stage2.runner.completion",
            side_effect=[bad_request, _mock_response(payload)],
        ) as mocked_completion:
            result, usage = client.chat_json(messages=[{"role": "user", "content": "hi"}], max_tokens=32)

        self.assertEqual(result, {"ok": True})
        self.assertEqual(usage["total_tokens"], 12)
        self.assertEqual(mocked_completion.call_count, 2)
        self.assertIn("response_format", mocked_completion.call_args_list[0].kwargs)
        self.assertNotIn("response_format", mocked_completion.call_args_list[1].kwargs)

    def test_client_surfaces_network_error_as_stage2_runner_error(self) -> None:
        client = LiteLLMClient(
            model="test-model",
            base_url="https://example.com/v1",
            api_keys=("test-key",),
            slot="llm1",
        )

        with patch(
            "runtime.stage2.runner.completion",
            side_effect=litellm.APIConnectionError("Tunnel connection failed: 503", model="test-model", llm_provider="openai"),
        ):
            with self.assertRaises(Stage2RunnerError) as ctx:
                client.chat_json(messages=[{"role": "user", "content": "hi"}], max_tokens=32)

        self.assertIn("llm1 网络错误", str(ctx.exception))

    def test_client_reports_missing_litellm_dependency_clearly(self) -> None:
        client = LiteLLMClient(
            model="test-model",
            base_url="https://example.com/v1",
            api_keys=("test-key",),
            slot="llm1",
        )

        with (
            patch.object(runner_module, "completion", None),
            patch.object(runner_module, "_LITELLM_IMPORT_ERROR", ModuleNotFoundError("No module named 'litellm'")),
        ):
            with self.assertRaises(Stage2RunnerError) as ctx:
                client.chat_json(messages=[{"role": "user", "content": "hi"}], max_tokens=32)

        self.assertIn("未安装 litellm", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
