from __future__ import annotations

import unittest

from runtime.stage3.baidu_scholar_smoke_test import build_result, build_url, resolve_api_key


class BaiduScholarSmokeTestTests(unittest.TestCase):
    def test_resolve_api_key_prefers_primary_env_name(self) -> None:
        env_name, api_key = resolve_api_key(
            {
                "QIANFAN_API_KEY": "primary-key",
                "BAIDU_QIANFAN_API_KEY": "fallback-key",
            }
        )

        self.assertEqual(env_name, "QIANFAN_API_KEY")
        self.assertEqual(api_key, "primary-key")

    def test_build_url_encodes_query_and_optional_flags(self) -> None:
        url = build_url("汉代 灾异", page_num=2, enable_abstract=True)

        self.assertIn("wd=%E6%B1%89%E4%BB%A3+%E7%81%BE%E5%BC%82", url)
        self.assertIn("pageNum=2", url)
        self.assertIn("enable_abstract=true", url)

    def test_build_result_extracts_first_item_summary(self) -> None:
        result = build_result(
            {
                "code": "0",
                "message": "Success",
                "requestId": "req-1",
                "hasMore": True,
                "data": [
                    {
                        "title": "测试论文",
                        "publishYear": 2024,
                        "url": "https://x.example/paper",
                    }
                ],
            },
            "汉代 灾异",
            "QIANFAN_API_KEY",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["resultCount"], 1)
        self.assertEqual(result["firstResult"]["title"], "测试论文")


if __name__ == "__main__":
    unittest.main()
