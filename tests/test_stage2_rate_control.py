from __future__ import annotations

import unittest

from runtime.stage2.rate_control import RateControllerRegistry, estimate_request_tokens


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


if __name__ == "__main__":
    unittest.main()
