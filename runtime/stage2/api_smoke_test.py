"""对阶段二各模型槽位执行最小化 API 连通性自检。"""

from __future__ import annotations

import argparse
import json

from .api_config import STAGE2_MODELS, merged_env, slot_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="对阶段二模型槽位做最小 API 连通性测试。")
    parser.add_argument("--slot", choices=sorted(STAGE2_MODELS.keys()), default="llm1", help="测试哪个模型槽位。")
    parser.add_argument("--env-file", help="可选 .env 文件路径。默认读取当前目录下的 .env。")
    parser.add_argument("--json", action="store_true", help="输出 JSON。")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = slot_payload(args.slot, env_values=merged_env(args.env_file or ".env"))
    if not payload["api_key"] and not payload["api_keys"]:
        raise SystemExit(
            f"{args.slot} 缺少 API key，请检查 {payload['api_key_env']} 或 {payload['api_keys_env']}。"
        )

    try:
        from litellm import completion
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"未安装 litellm: {exc}") from exc

    response = completion(
        model=payload["model"],
        messages=[
            {"role": "system", "content": "你是一个严格遵守格式的助手。"},
            {"role": "user", "content": "请只返回一个极短 JSON：{\"ok\":true}"},
        ],
        temperature=0.0,
        custom_llm_provider="openai",
        api_key=payload["api_key"],
        api_base=payload["base_url"],
        timeout=60,
        num_retries=2,
        max_tokens=32,
        response_format={"type": "json_object"},
    )

    if hasattr(response, "model_dump"):
        data = response.model_dump()
    elif hasattr(response, "dict"):
        data = response.dict()
    else:
        data = dict(response)

    result = {
        "slot": args.slot,
        "provider": payload["provider"],
        "model": payload["model"],
        "content": (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""),
        "usage": data.get("usage"),
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"slot: {result['slot']}")
        print(f"provider: {result['provider']}")
        print(f"model: {result['model']}")
        print(f"content: {result['content']}")
        print(f"usage: {result['usage']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
