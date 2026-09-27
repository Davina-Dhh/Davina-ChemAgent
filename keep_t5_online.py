"""一键：本机 ReactionT5 服务 + cloudflared 隧道 + 自动发布发现链接。

用法（电脑开机后跑一次即可）:
  .\\.venv\\Scripts\\python.exe keep_t5_online.py

Cloud 固定读:
  https://raw.githubusercontent.com/Davina-Dhh/Davina-ChemAgent/main/static/t5_endpoint.json
一般不必再改 Secrets 里的 URL。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOKEN_FILE = ROOT / ".reactiont5_token"
LOG_FILE = Path(os.environ.get("TEMP", str(ROOT))) / "chemagent_cloudflared.log"
URL_RE = re.compile(
    r"https://[a-z0-9-]+\.trycloudflare\.com|https://[a-zA-Z0-9.-]+\.ngrok-free\.app|https://[a-zA-Z0-9.-]+\.ngrok\.io",
    re.I,
)


def _ensure_token() -> str:
    env = (os.getenv("REACTIONT5_API_TOKEN") or "").strip()
    if env:
        return env
    if TOKEN_FILE.is_file():
        tok = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if tok:
            return tok
    import secrets

    tok = secrets.token_hex(12)
    TOKEN_FILE.write_text(tok + "\n", encoding="utf-8")
    print(f"[首次] 已生成 {TOKEN_FILE.name} = {tok}")
    print("请把同一串写入 Streamlit Cloud Secrets → REACTIONT5_API_TOKEN（只需一次）")
    return tok


def _popen_new_console(args: list[str], env: dict) -> subprocess.Popen:
    creation = 0
    if sys.platform == "win32":
        creation = subprocess.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]
    return subprocess.Popen(
        args,
        cwd=str(ROOT),
        env=env,
        creationflags=creation,
    )


def _wait_url(timeout_sec: float = 90.0) -> str:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if LOG_FILE.is_file():
            try:
                text = LOG_FILE.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                text = ""
            m = URL_RE.search(text)
            if m:
                return m.group(0).rstrip("/")
        time.sleep(1.5)
    raise TimeoutError(f"超时未在日志中找到公网 URL，请查看 {LOG_FILE}")


def main() -> None:
    token = _ensure_token()
    env = os.environ.copy()
    env["ENABLE_REACTIONT5"] = "1"
    env["REACTIONT5_API_TOKEN"] = token

    py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.is_file():
        py = Path(sys.executable)

    print("[1/4] 启动本机推理服务 :8765 …")
    _popen_new_console(
        [
            str(py),
            "-m",
            "uvicorn",
            "reactiont5_server:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8765",
        ],
        env,
    )
    time.sleep(5)

    cloudflared = "cloudflared"
    try:
        subprocess.run(
            [cloudflared, "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception as exc:  # noqa: BLE001
        print("[错误] 未找到 cloudflared，请先安装后重试。")
        print("  https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/")
        raise SystemExit(1) from exc

    if LOG_FILE.is_file():
        try:
            LOG_FILE.unlink()
        except Exception:
            pass

    print(f"[2/4] 启动 cloudflared 隧道（日志 {LOG_FILE}）…")
    # 用 cmd 重定向，避免管道缓冲问题
    if sys.platform == "win32":
        cmd = (
            f'cloudflared tunnel --url http://127.0.0.1:8765 > "{LOG_FILE}" 2>&1'
        )
        _popen_new_console(["cmd", "/k", cmd], env)
    else:
        with open(LOG_FILE, "w", encoding="utf-8") as logf:
            subprocess.Popen(
                [cloudflared, "tunnel", "--url", "http://127.0.0.1:8765"],
                cwd=str(ROOT),
                env=env,
                stdout=logf,
                stderr=subprocess.STDOUT,
            )

    print("[3/4] 等待公网地址…")
    url = _wait_url(100)
    print(f"[OK] 隧道地址: {url}")

    print("[4/4] 发布到 GitHub 发现链接…")
    pub = ROOT / "publish_t5_endpoint.py"
    r = subprocess.run([str(py), str(pub), url], cwd=str(ROOT))
    if r.returncode != 0:
        raise SystemExit(r.returncode)

    print()
    print("完成。保持两个黑色窗口不要关；电脑别休眠。")
    print("Cloud 刷新页面即可直接调用，一般不用再改 Secrets 里的 URL。")
    print("下次开机：再运行一次本脚本即可。")


if __name__ == "__main__":
    main()
