#!/usr/bin/env python3
r"""
MinerU「精准解析 API」本地文件测试（与文档 https://mineru.net/apiManage/docs 一致）。

文档里与「文件从哪来」相关的几种方式（均为异步：提交后轮询）：

1) 单文件 + 仅远程 URL —— POST /api/v4/extract/task
   - 请求体里是 JSON，字段 `url` 指向**已可在公网下载**的文件；**不支持**在该接口里 multipart 直传本地文件。
   - Header：`Authorization: Bearer <官网申请的 API Token>`。

2) 本地文件批量 —— POST /api/v4/file-urls/batch（本脚本采用）
   - 先带 Token 申请：返回 `batch_id` 与每条 `file_urls`（预签名上传地址，文档写有效期约 24 小时）。
   - 对每个本地文件用 **HTTP PUT** 将**原始字节**传到对应 URL；文档写明上传时**无须**设置 Content-Type。
   - 上传完成后**无需**再调「创建任务」接口，服务端会自动扫描并提交解析。
   - 轮询：GET /api/v4/extract-results/batch/{batch_id}，直到 `state` 为 done/failed。

3) 多文件远程 URL 批量 —— POST /api/v4/extract/task/batch
   - 每个文件一个公网 `url`，再 GET 批量结果接口（同文档）。

默认与技能脚本一致：**仓库根目录 `.env`** 与 **`.cursor/skills/ai-sinology/.env`** 分层合并（同名键以后者为准），再由当前 shell 覆盖。键名 `MINERU_API_TOKEN` 或 `MINERU_TOKEN`。可将密钥只放在技能目录 `.env` 中。
`MINERU_MODEL_VERSION`：`pipeline` 或 `vlm`（默认 `vlm`）。
`MINERU_OUTPUT_MD`：解析完成后写入的 Markdown 路径（默认：仓库根目录 `<stem>_mineru.md`）。
`MINERU_DATA_ID`：可选，不传则每次自动生成，减少服务端缓存命中。
"""

from __future__ import annotations

import json
import uuid
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_PDF = ROOT / "我的合同.pdf"

_SCRIPTS = ROOT / ".cursor/skills/ai-sinology/scripts"
if _SCRIPTS.is_dir():
    sys.path.insert(0, str(_SCRIPTS))
from stage3_common import resolve_stage3_env  # noqa: E402

BASE = "https://mineru.net"


def _req(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    data: bytes | None = None,
) -> tuple[int, bytes]:
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            return resp.getcode(), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _put_presigned_local_file(presigned_url: str, file_path: Path) -> int:
    """上传到 OSS 预签名 URL。urllib 对 PUT 易触发 Broken pipe，与文档示例一致改用 curl。"""
    proc = subprocess.run(
        [
            "curl",
            "-sS",
            "-o",
            "/dev/null",
            "-w",
            "%{http_code}",
            "-X",
            "PUT",
            "-T",
            str(file_path),
            presigned_url,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        return 0
    try:
        return int(proc.stdout.strip())
    except ValueError:
        return 0


def _download_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=300) as resp:
        dest.write_bytes(resp.read())


def _find_mineru_full_md(extract_root: Path) -> Path | None:
    """MinerU zip 内通常为某子目录下的 full.md。"""
    matches = sorted(extract_root.rglob("full.md"), key=lambda p: len(p.parts))
    return matches[0] if matches else None


def _save_only_markdown(zip_url: str, pdf: Path, env: dict[str, str]) -> Path | None:
    """下载 zip → 解压 → 仅保留 full.md 到目标路径，删除临时 zip 与解压目录。"""
    out = Path(
        env.get("MINERU_OUTPUT_MD") or str(ROOT / f"{pdf.stem}_mineru.md")
    ).resolve()

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        zpath = t / "mineru_result.zip"
        exdir = t / "extracted"
        print(f"[3] 下载结果包 -> {zpath.name}")
        _download_file(zip_url, zpath)
        exdir.mkdir()
        with zipfile.ZipFile(zpath, "r") as zf:
            zf.extractall(exdir)
        full_md = _find_mineru_full_md(exdir)
        if full_md is None or not full_md.is_file():
            print("解压后未找到 full.md", file=sys.stderr)
            return None
        shutil.copy2(full_md, out)
    print(f"[4] 已仅保留 Markdown: {out}")
    return out


def main() -> int:
    env = resolve_stage3_env(None)
    token = (env.get("MINERU_API_TOKEN") or env.get("MINERU_TOKEN") or "").strip()
    if not token:
        print(
            "请在仓库根目录 .env 或 .cursor/skills/ai-sinology/.env 中设置 MINERU_API_TOKEN 或 MINERU_TOKEN。",
            file=sys.stderr,
        )
        return 2

    pdf = Path(env.get("MINERU_TEST_PDF") or str(DEFAULT_PDF)).resolve()

    if not pdf.is_file():
        print(f"找不到 PDF：{pdf}", file=sys.stderr)
        return 2

    model = (env.get("MINERU_MODEL_VERSION") or "vlm").strip().lower()
    if model not in ("pipeline", "vlm"):
        print("MINERU_MODEL_VERSION 须为 pipeline 或 vlm", file=sys.stderr)
        return 2
    data_id = env.get("MINERU_DATA_ID") or f"local-{model}-{uuid.uuid4().hex[:12]}"

    auth = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "*/*"}
    body = {
        "files": [{"name": pdf.name, "data_id": data_id}],
        "model_version": model,
    }
    print(f"model_version={model} data_id={data_id}")
    url_batch = f"{BASE}/api/v4/file-urls/batch"
    code, raw = _req("POST", url_batch, headers=auth, data=json.dumps(body).encode())
    print(f"[1] POST file-urls/batch -> HTTP {code}")
    try:
        payload = json.loads(raw.decode())
    except json.JSONDecodeError:
        print(raw[:500], file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2)[:2000])
    if code != 200 or payload.get("code") != 0:
        print(
            f"申请上传链接失败：HTTP {code}，业务 code={payload.get('code')} msg={payload.get('msg')}",
            file=sys.stderr,
        )
        return 1

    batch_id = payload["data"]["batch_id"]
    put_url = payload["data"]["file_urls"][0]

    code = _put_presigned_local_file(put_url, pdf)
    print(f"[2] PUT 上传文件（curl）-> HTTP {code}")
    if code not in (200, 201):
        return 1

    poll_url = f"{BASE}/api/v4/extract-results/batch/{batch_id}"
    deadline = time.time() + 300
    while time.time() < deadline:
        time.sleep(4)
        code, raw = _req("GET", poll_url, headers=auth, data=None)
        try:
            out = json.loads(raw.decode())
        except json.JSONDecodeError:
            print(raw[:500])
            return 1
        if out.get("code") == 0 and out.get("data", {}).get("extract_result"):
            er = out["data"]["extract_result"]
            if isinstance(er, list) and er:
                state = er[0].get("state")
                err = er[0].get("err_msg", "")
                print(f"[poll] state={state} err={err!r}")
                if state == "done":
                    print("成功:", json.dumps(out, ensure_ascii=False, indent=2)[:3000])
                    zip_url = er[0].get("full_zip_url")
                    if zip_url:
                        print("\n结果包 URL:", zip_url)
                        md_path = _save_only_markdown(zip_url, pdf, env)
                        if md_path is None:
                            return 1
                    return 0
                if state == "failed":
                    print("解析失败:", err, file=sys.stderr)
                    return 1
        else:
            print("[poll]", json.dumps(out, ensure_ascii=False)[:800])

    print("轮询超时（5 分钟）", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
