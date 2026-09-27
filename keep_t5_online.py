"""一键：本机 ReactionT5 服务 + cloudflared 隧道 + 自动发布发现链接。

用法（电脑开机后跑一次即可）:
  .\\.venv\\Scripts\\python.exe keep_t5_online.py

Cloud 固定读发现链接（jsDelivr / GitHub），一般不必再改 Secrets 里的 URL。
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOKEN_FILE = ROOT / ".reactiont5_token"
LOG_FILE = Path(os.environ.get("TEMP", str(ROOT))) / "chemagent_cloudflared.log"
URL_RE = re.compile(
    r"https://[a-z0-9-]+\.trycloudflare\.com|https://[a-zA-Z0-9.-]+\.ngrok-free\.app|https://[a-zA-Z0-9.-]+\.ngrok\.io",
    re.I,
)
LOCAL_PORT = 8765
LOCAL_HEALTH = f"http://127.0.0.1:{LOCAL_PORT}/health"


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


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.5):
            return True
    except OSError:
        return False


def _health_ok() -> bool:
    try:
        with urllib.request.urlopen(LOCAL_HEALTH, timeout=3) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


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


def _find_cloudflared() -> str:
    which = subprocess.run(
        ["where" if sys.platform == "win32" else "which", "cloudflared"],
        capture_output=True,
        text=True,
    )
    if which.returncode == 0:
        line = (which.stdout or "").splitlines()
        if line:
            return line[0].strip()
    candidates = [
        Path(r"C:\Program Files (x86)\cloudflared\cloudflared.exe"),
        Path(r"C:\Program Files\cloudflared\cloudflared.exe"),
    ]
    for p in candidates:
        if p.is_file():
            return str(p)
    raise FileNotFoundError("cloudflared")


def _start_server(py: Path, env: dict) -> None:
    if _health_ok():
        print(f"[1/4] 本机推理服务已在 :{LOCAL_PORT} 运行")
        return
    if _port_open(LOCAL_PORT) and not _health_ok():
        print(f"[警告] :{LOCAL_PORT} 被占用但 /health 不通，将尝试直接启动（若失败请关掉旧窗口）")

    print(f"[1/4] 启动本机推理服务 :{LOCAL_PORT} …")
    _popen_new_console(
        [
            str(py),
            "-m",
            "uvicorn",
            "reactiont5_server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(LOCAL_PORT),
        ],
        env,
    )
    deadline = time.time() + 120
    while time.time() < deadline:
        if _health_ok():
            print("[OK] /health 已就绪")
            return
        time.sleep(1.5)
    raise TimeoutError(
        f"本机服务启动超时：请查看名为 ChemAgent / uvicorn 的黑窗口，"
        f"确认 http://127.0.0.1:{LOCAL_PORT}/health 可访问"
    )


def _start_tunnel(cloudflared: str, env: dict) -> subprocess.Popen:
    try:
        LOG_FILE.write_text("", encoding="utf-8")
    except Exception:
        pass

    print(f"[2/4] 启动 cloudflared 隧道（日志 {LOG_FILE}）…")
    # 新版 cloudflared 把 URL 打在 stderr；用 Python 同时捕获 stdout/stderr，避免 cmd 重定向丢日志
    logf = open(LOG_FILE, "w", encoding="utf-8", errors="replace")
    creation = 0
    if sys.platform == "win32":
        # 独立进程组，脚本退出后隧道仍可继续；不弹新控制台以免丢句柄
        creation = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    return subprocess.Popen(
        [
            cloudflared,
            "tunnel",
            "--protocol",
            "http2",
            "--url",
            f"http://127.0.0.1:{LOCAL_PORT}",
        ],
        cwd=str(ROOT),
        env=env,
        stdout=logf,
        stderr=subprocess.STDOUT,
        creationflags=creation,
    )


def _wait_url(timeout_sec: float = 120.0) -> str:
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
        time.sleep(1.0)
    raise TimeoutError(f"超时未在日志中找到公网 URL，请查看 {LOG_FILE}")


def main() -> None:
    token = _ensure_token()
    env = os.environ.copy()
    env["ENABLE_REACTIONT5"] = "1"
    env["REACTIONT5_API_TOKEN"] = token

    py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.is_file():
        py = Path(sys.executable)

    try:
        cloudflared = _find_cloudflared()
        subprocess.run(
            [cloudflared, "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception as exc:  # noqa: BLE001
        print("[错误] 未找到 cloudflared，请先安装后重试。")
        print("  winget install --id Cloudflare.cloudflared -e")
        raise SystemExit(1) from exc

    _start_server(py, env)

    tunnel_proc = _start_tunnel(cloudflared, env)
    print("[3/4] 等待公网地址…")
    try:
        url = _wait_url(120)
    except TimeoutError:
        if tunnel_proc.poll() is not None:
            print(f"[错误] cloudflared 已退出，代码 {tunnel_proc.returncode}")
        raise
    print(f"[OK] 隧道地址: {url}")

    # 冒烟：公网 /health
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=20) as resp:
            print(f"[OK] 公网 /health = {resp.status}")
    except Exception as exc:  # noqa: BLE001
        print(f"[警告] 公网 /health 暂未通（可能还在预热）: {exc}")

    print("[4/4] 发布到 GitHub 发现链接…")
    pub = ROOT / "publish_t5_endpoint.py"
    r = subprocess.run([str(py), str(pub), url], cwd=str(ROOT))
    if r.returncode != 0:
        raise SystemExit(r.returncode)

    print()
    print("完成。保持本窗口不要关（隧道挂在此进程下）；电脑别休眠。")
    print("Cloud 刷新页面即可直接调用，一般不用再改 Secrets 里的 URL。")
    print("下次开机：再运行一次 keep_t5_online.bat 即可。")
    print()
    print("按 Ctrl+C 可停止隧道（推理服务黑窗口需另关）。")
    try:
        tunnel_proc.wait()
    except KeyboardInterrupt:
        print("\n正在停止隧道…")
        tunnel_proc.terminate()


if __name__ == "__main__":
    main()
