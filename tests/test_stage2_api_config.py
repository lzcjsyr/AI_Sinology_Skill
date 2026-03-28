from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.stage2.api_config import resolve_provider_keys, slot_payload, slot_worker_limit


class Stage2ApiConfigTests(unittest.TestCase):
    def test_resolve_provider_keys_merges_pool_and_primary_key(self) -> None:
        primary, pool = resolve_provider_keys(
            "volcengine",
            env_values={
                "VOLCENGINE_API_KEY": "legacy-key",
                "VOLCENGINE_API_KEYS": "key-a,key-b,key-a",
            },
        )

        self.assertEqual(primary, "key-a")
        self.assertEqual(pool, ("key-a", "key-b", "legacy-key"))

    def test_slot_payload_reads_dotenv_when_env_values_not_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("VOLCENGINE_API_KEY=dotenv-key\n", encoding="utf-8")

            payload = slot_payload("llm1", dotenv_path=env_file)

        self.assertEqual(payload["provider"], "volcengine")
        self.assertEqual(payload["api_key"], "dotenv-key")
        self.assertEqual(payload["api_keys"], ("dotenv-key",))

    def test_resolve_provider_keys_respects_explicit_empty_env_values(self) -> None:
        with patch.dict("os.environ", {"VOLCENGINE_API_KEY": "from-os"}, clear=False):
            primary, pool = resolve_provider_keys("volcengine", env_values={})

        self.assertEqual(primary, "")
        self.assertEqual(pool, ())

    def test_slot_payload_exposes_configured_max_concurrency(self) -> None:
        payload = slot_payload("llm3", env_values={"VOLCENGINE_API_KEY": "test-key"})

        self.assertEqual(payload["max_concurrency"], 2)
        self.assertEqual(slot_worker_limit("llm1"), 4)


if __name__ == "__main__":
    unittest.main()
