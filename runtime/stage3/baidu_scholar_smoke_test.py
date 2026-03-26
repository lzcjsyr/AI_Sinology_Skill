"""百度学术检索 API 最小连通性测试。"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .api_config import merged_env


BAIDU_SCHOLAR_URL = "https://qianfan.baidubce.com/v2/tools/baidu_scholar/search"
BAIDU_SCHOLAR_API_KEY_ENV_NAMES = ("QIANFAN_API_KEY", "BAIDU_QIANFAN_API_KEY")


def resolve_api_key(env_values: dict[str, str]) -> tuple[str, str]:
    for env_name in BAIDU_SCHOLAR_API_KEY_ENV_NAMES:
        value = env_values.get(env_name, "").strip()
        if value:
            return env_name, value
    return BAIDU_SCHOLAR_API_KEY_ENV_NAMES[0], ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="测试百度学术检索 API 是否可联通。")
    parser.add_argument("--query", default="汉代 灾异", help="检索关键词，对应接口参数 wd。")
    parser.add_argument("--page-num", type=int, default=0, help="页码，从 0 开始。")
    parser.add_argument(
        "--enable-abstract",
        action="store_true",
        help="是否开启智能摘要，对应接口参数 enable_abstract=true。",
    )
    parser.add_argument("--env-file", help="可选 .env 文件路径。默认读取当前目录下的 .env。")
    parser.add_argument("--json", action="store_true", help="输出 JSON。")
    return parser


def build_url(query: str, *, page_num: int, enable_abstract: bool) -> str:
    params = {
        "wd": query,
        "pageNum": page_num,
    }
    if enable_abstract:
        params["enable_abstract"] = "true"
    return f"{BAIDU_SCHOLAR_URL}?{urllib.parse.urlencode(params)}"


def build_result(payload: dict[str, object], query: str, env_name: str) -> dict[str, object]:
    data = payload.get("data")
    items = data if isinstance(data, list) else []
    first = items[0] if items and isinstance(items[0], dict) else {}
    return {
        "ok": str(payload.get("code", "")) == "0",
        "query": query,
        "api_key_env": env_name,
        "code": payload.get("code"),
        "message": payload.get("message"),
        "requestId": payload.get("requestId"),
        "hasMore": payload.get("hasMore"),
        "resultCount": len(items),
        "firstResult": {
            "title": first.get("title"),
            "publishYear": first.get("publishYear"),
            "url": first.get("url"),
        },
    }


def emit(result: dict[str, object], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(f"ok: {result['ok']}")
    print(f"query: {result['query']}")
    print(f"api_key_env: {result['api_key_env']}")
    print(f"code: {result['code']}")
    print(f"message: {result['message']}")
    print(f"requestId: {result['requestId']}")
    print(f"hasMore: {result['hasMore']}")
    print(f"resultCount: {result['resultCount']}")
    first = result["firstResult"]
    if isinstance(first, dict):
        print(f"firstResult.title: {first.get('title')}")
        print(f"firstResult.publishYear: {first.get('publishYear')}")
        print(f"firstResult.url: {first.get('url')}")


def main() -> int:
    args = build_parser().parse_args()
    env = merged_env(args.env_file or ".env")
    env_name, api_key = resolve_api_key(env)
    if not api_key:
        raise SystemExit(
            f"缺少百度学术 API key，请检查环境变量 {env_name} 或 BAIDU_QIANFAN_API_KEY。"
        )

    url = build_url(args.query, page_num=args.page_num, enable_abstract=args.enable_abstract)
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Appbuilder-Request-Id": str(uuid.uuid4()),
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(body, file=sys.stderr)
        raise SystemExit(f"百度学术 API 请求失败: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"百度学术 API 网络错误: {exc}") from exc

    result = build_result(payload, args.query, env_name)
    emit(result, args.json)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
