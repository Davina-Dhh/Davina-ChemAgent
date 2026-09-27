@echo off
cd /d "%~dp0"
set ENABLE_REACTIONT5=1
if "%REACTIONT5_API_TOKEN%"=="" (
  echo [提示] 未设置 REACTIONT5_API_TOKEN。公网隧道时建议先:
  echo   set REACTIONT5_API_TOKEN=换成一串随机密码
)
echo ReactionT5 API: http://127.0.0.1:8765/health
echo 公网暴露示例: cloudflared tunnel --url http://127.0.0.1:8765
".venv\Scripts\python.exe" -m uvicorn reactiont5_server:app --host 0.0.0.0 --port 8765
pause
