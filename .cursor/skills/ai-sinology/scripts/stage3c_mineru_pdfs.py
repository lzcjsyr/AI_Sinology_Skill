#!/usr/bin/env python3
r"""
阶段 3C 前置：将 `outputs/<project>/_stage3b/papers/` 下 PDF 经 MinerU API 转为 Markdown，
写入 `outputs/<project>/_stage3c/papers_md/`。

实现与仓库根目录的 `test_mineru_v4_batch.py` 一致（v4 批量上传 + 轮询 + zip 内 full.md），
默认 `model_version=vlm`。默认与 `stage3b_sources.py` 相同：**省略 `--env-file` 时**先读仓库根目录 `.env`，再读 **技能目录** `ai-sinology/.env`（同名键以后者为准），最后当前 shell 环境覆盖。键名 `MINERU_API_TOKEN` 或 `MINERU_TOKEN`。指定 `--env-file` 时只加载该单一文件。`.env` 已被 Git 忽略，勿提交。

依赖：系统可用 `curl`（用于 PUT 预签名 URL）。

可选环境变量（可写在 `.env` 或当前 shell）：
- `MINERU_MODEL_VERSION`：`pipeline` 或 `vlm`（默认 `vlm`）
- `MINERU_POLL_TIMEOUT_SEC`：单文件轮询超时秒数（默认 `600`）
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

from stage3_common import resolve_stage3_env

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
    matches = sorted(extract_root.rglob("full.md"), key=lambda p: len(p.parts))
    return matches[0] if matches else None


def _save_markdown_from_zip(zip_url: str, out_md: Path) -> bool:
    out_md.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        zpath = t / "mineru_result.zip"
        exdir = t / "extracted"
        print(f"    下载结果包 -> {zpath.name}")
        _download_file(zip_url, zpath)
        exdir.mkdir()
        with zipfile.ZipFile(zpath, "r") as zf:
            zf.extractall(exdir)
        full_md = _find_mineru_full_md(exdir)
        if full_md is None or not full_md.is_file():
            print("解压后未找到 full.md", file=sys.stderr)
            return False
        shutil.copy2(full_md, out_md)
    print(f"    已写入: {out_md}")
    return True


def _convert_one_pdf(
    *,
    token: str,
    pdf: Path,
    out_md: Path,
    model: str,
    poll_timeout_sec: float,
    data_id_override: str | None,
) -> bool:
    data_id = (data_id_override or "").strip() or f"local-{model}-{uuid.uuid4().hex[:12]}"
    auth = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "*/*",
    }
    body = {
        "files": [{"name": pdf.name, "data_id": data_id}],
        "model_version": model,
    }
    url_batch = f"{BASE}/api/v4/file-urls/batch"
    code, raw = _req("POST", url_batch, headers=auth, data=json.dumps(body).encode())
    if code != 200:
        print(f"POST file-urls/batch HTTP {code}: {raw[:500]!r}", file=sys.stderr)
        return False
    try:
        payload = json.loads(raw.decode())
    except json.JSONDecodeError:
        print(raw[:500], file=sys.stderr)
        return False
    if payload.get("code") != 0:
        print(
            f"申请上传链接失败: code={payload.get('code')} msg={payload.get('msg')}",
            file=sys.stderr,
        )
        return False

    batch_id = payload["data"]["batch_id"]
    put_url = payload["data"]["file_urls"][0]
    code = _put_presigned_local_file(put_url, pdf)
    print(f"    PUT 上传 -> HTTP {code}")
    if code not in (200, 201):
        return False

    poll_url = f"{BASE}/api/v4/extract-results/batch/{batch_id}"
    deadline = time.time() + poll_timeout_sec
    while time.time() < deadline:
        time.sleep(4)
        code, raw = _req("GET", poll_url, headers=auth, data=None)
        try:
            out = json.loads(raw.decode())
        except json.JSONDecodeError:
            print(raw[:500], file=sys.stderr)
            return False
        if out.get("code") == 0 and out.get("data", {}).get("extract_result"):
            er = out["data"]["extract_result"]
            if isinstance(er, list) and er:
                state = er[0].get("state")
                err = er[0].get("err_msg", "")
                if state == "done":
                    zip_url = er[0].get("full_zip_url")
                    if not zip_url:
                        print("无 full_zip_url", file=sys.stderr)
                        return False
                    return _save_markdown_from_zip(zip_url, out_md)
                if state == "failed":
                    print(f"解析失败: {err}", file=sys.stderr)
                    return False
    print(f"轮询超时（{poll_timeout_sec:.0f}s）: {pdf.name}", file=sys.stderr)
    return False


def _papers_pdf_paths(papers_dir: Path) -> list[Path]:
    if not papers_dir.is_dir():
        return []
    return sorted(papers_dir.rglob("*.pdf"))


def _target_md_path(papers_dir: Path, papers_md_dir: Path, pdf: Path) -> Path:
    rel = pdf.relative_to(papers_dir)
    return papers_md_dir / rel.parent / f"{rel.stem}_mineru.md"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="3C 前置：从 _stage3b/papers 读取 PDF，写入 _stage3c/papers_md（MinerU Markdown，默认 vlm）。"
    )
    p.add_argument("project", help="项目名（outputs/<project>/）。")
    p.add_argument(
        "--outputs",
        default="outputs",
        help="项目根目录，默认 ./outputs。",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="仅列出待转换/已存在的对应关系，不调用 API。",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="即使目标 .md 已存在也重新转换。",
    )
    p.add_argument(
        "--env-file",
        default=None,
        help="指定单一环境文件；省略时合并仓库根目录 .env 与技能目录 ai-sinology/.env（后者覆盖同名键）。",
    )
    return p


def main() -> int:
    args = build_parser().parse_args()
    env = resolve_stage3_env(args.env_file)

    outputs_root = Path(args.outputs).expanduser().resolve()
    project_root = outputs_root / args.project
    papers_dir = project_root / "_stage3b" / "papers"
    papers_md_dir = project_root / "_stage3c" / "papers_md"

    token = (env.get("MINERU_API_TOKEN") or env.get("MINERU_TOKEN") or "").strip()
    if not args.dry_run and not token:
        print(
            "请在仓库根目录 .env 或 .cursor/skills/ai-sinology/.env 中设置 MINERU_API_TOKEN 或 MINERU_TOKEN（或传入 --env-file 指定单一文件）。",
            file=sys.stderr,
        )
        return 2

    model = (env.get("MINERU_MODEL_VERSION") or "vlm").strip().lower()
    if model not in ("pipeline", "vlm"):
        print("MINERU_MODEL_VERSION 须为 pipeline 或 vlm", file=sys.stderr)
        return 2
    poll_timeout = float(env.get("MINERU_POLL_TIMEOUT_SEC") or "600")
    data_id_override = (env.get("MINERU_DATA_ID") or "").strip() or None

    pdfs = _papers_pdf_paths(papers_dir)
    if not pdfs:
        print(f"未找到 PDF：{papers_dir}")
        return 0

    papers_md_dir.mkdir(parents=True, exist_ok=True)

    todo: list[tuple[Path, Path]] = []
    for pdf in pdfs:
        out_md = _target_md_path(papers_dir, papers_md_dir, pdf)
        if args.force or not out_md.is_file():
            todo.append((pdf, out_md))
        elif out_md.stat().st_size == 0:
            todo.append((pdf, out_md))

    print(f"model_version={model} papers={len(pdfs)} need_convert={len(todo)}")
    if args.dry_run:
        for pdf in pdfs:
            out_md = _target_md_path(papers_dir, papers_md_dir, pdf)
            status = "missing" if not out_md.is_file() else "ok"
            print(f"  [{status}] {pdf.relative_to(papers_dir)} -> {out_md.relative_to(papers_md_dir)}")
        return 0

    failed = 0
    for pdf, out_md in todo:
        print(f"\n--> {pdf.relative_to(papers_dir)}")
        if not _convert_one_pdf(
            token=token,
            pdf=pdf,
            out_md=out_md,
            model=model,
            poll_timeout_sec=poll_timeout,
            data_id_override=data_id_override,
        ):
            failed += 1

    if failed:
        print(f"\n完成，失败 {failed} 个。", file=sys.stderr)
        return 1
    print("\n全部完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
