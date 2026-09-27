"""把本机 ReactionT5 公网地址写进 static/t5_endpoint.json 并推送到 GitHub。

Cloud 固定读发现链接即可，重启后不用改 Secrets。
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENDPOINT = ROOT / "static" / "t5_endpoint.json"

# Streamlit Cloud / 代码里默认用的发现地址（固定，只配一次）
DEFAULT_DISCOVERY = (
    "https://raw.githubusercontent.com/Davina-Dhh/Davina-ChemAgent/"
    "main/static/t5_endpoint.json"
)


def publish(url: str, *, push: bool = True) -> Path:
    url = (url or "").strip().rstrip("/")
    if not url.startswith("http"):
        raise SystemExit(f"无效 URL: {url}")

    ENDPOINT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "url": url,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": "auto-published by keep_t5_online / publish_t5_endpoint.py",
    }
    ENDPOINT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[OK] 已写入 {ENDPOINT}")
    print(f"     url = {url}")

    if not push:
        return ENDPOINT

    def _run(cmd: list[str]) -> None:
        print("+", " ".join(cmd))
        subprocess.run(cmd, cwd=str(ROOT), check=False)

    _run(["git", "add", "static/t5_endpoint.json"])
    _run(
        [
            "git",
            "commit",
            "-m",
            f"chore: update ReactionT5 public endpoint ({url})",
        ]
    )
    r = subprocess.run(
        ["git", "push", "origin", "HEAD"],
        cwd=str(ROOT),
        check=False,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print(r.stdout or "")
        print(r.stderr or "")
        print("[WARN] git push 失败：请检查网络/登录。文件已更新，可手动 push。")
        print(f"发现链接（固定）: {DEFAULT_DISCOVERY}")
        raise SystemExit(1)
    print("[OK] 已推送到 GitHub。Cloud 刷新后即可用，无需改 Secrets。")
    print(f"发现链接: {DEFAULT_DISCOVERY}")
    return ENDPOINT


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python publish_t5_endpoint.py https://xxxx.trycloudflare.com")
        raise SystemExit(2)
    publish(sys.argv[1], push="--no-push" not in sys.argv)
