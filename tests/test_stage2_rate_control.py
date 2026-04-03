from __future__ import annotations

import io
import json
import unittest
from unittest.mock import Mock
from unittest.mock import patch
from urllib.error import HTTPError

from runtime.stage2.api_config import RateControllerRegistry, estimate_request_tokens
from runtime.stage2.runner import OpenAICompatClient


class Stage2RateControlTests(unittest.TestCase):
    def test_estimate_request_tokens_counts_prompt_and_completion_budget(self) -> None:
        estimated = estimate_request_tokens(
            messages=[
                {"role": "system", "content": "你是助手。"},
                {"role": "user", "content": "请判断这段文本是否与冬雷有关。"},
            ],
            max_tokens=1200,
        )

        self.assertGreaterEqual(estimated, 1200)

    def test_registry_reuses_controller_for_same_slot_signature(self) -> None:
        registry = RateControllerRegistry()
        payload = {
            "provider": "volcengine",
            "model": "deepseek-v3-2-251201",
            "api_keys": ("key-a", "key-b"),
            "rpm": 120,
            "tpm": 120000,
        }

        left = registry.get(payload)
        right = registry.get(dict(payload))

        self.assertIs(left, right)

    def test_multi_key_acquire_balances_between_keys(self) -> None:
        registry = RateControllerRegistry()
        controller = registry.get(
            {
                "provider": "volcengine",
                "model": "deepseek-v3-2-251201",
                "api_keys": ("key-a", "key-b"),
                "rpm": 120,
                "tpm": 120000,
            }
        )

        first = controller.acquire(estimated_tokens=500)
        second = controller.acquire(estimated_tokens=500)

        self.assertEqual({first.api_key, second.api_key}, {"key-a", "key-b"})

    def test_effective_worker_limit_shrinks_under_tpm_budget(self) -> None:
        registry = RateControllerRegistry()
        controller = registry.get(
            {
                "provider": "volcengine",
                "model": "deepseek-v3-2-251201",
                "api_keys": ("key-a", "key-b"),
                "rpm": 600,
                "tpm": 6000,
            }
        )

        workers = controller.effective_worker_limit(requested_workers=16, estimated_tokens=1000)

        self.assertEqual(workers, 2)

    def test_openai_client_retries_on_http_429(self) -> None:
        client = OpenAICompatClient(
            model="test-model",
            base_url="https://example.com/v1",
            api_keys=("test-key",),
            slot="llm1",
            rate_controller=None,
        )
        payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({"ok": True}, ensure_ascii=False),
                    }
                }
            ],
            "usage": {"total_tokens": 123},
        }
        response = Mock()
        response.read.return_value = json.dumps(payload).encode("utf-8")
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        rate_limited = HTTPError(
            url="https://example.com/v1/chat/completions",
            code=429,
            msg="Too Many Requests",
            hdrs={"Retry-After": "0"},
            fp=io.BytesIO(b'{"error":"rate limited"}'),
        )

        with (
            patch("runtime.stage2.runner.urlopen", side_effect=[rate_limited, response]) as mocked_urlopen,
            patch("runtime.stage2.runner.time.sleep") as mocked_sleep,
        ):
            result = client._request(
                payload={"model": "test-model", "messages": [{"role": "user", "content": "hi"}]},
                estimated_tokens=100,
            )

        self.assertTrue(result["choices"])
        self.assertEqual(mocked_urlopen.call_count, 2)
        mocked_sleep.assert_called_once_with(0.0)


if __name__ == "__main__":
    unittest.main()
