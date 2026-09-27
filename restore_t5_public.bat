@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo  电脑重启后：恢复 ReactionT5 公网接入
echo ========================================
echo.
echo 步骤 1/2：启动本机 ReactionT5 服务（8765）
echo 步骤 2/2：另开窗口跑隧道，再把新 URL 写入 Cloud Secrets
echo.

if "%REACTIONT5_API_TOKEN%"=="" (
  if exist ".reactiont5_token" (
    set /p REACTIONT5_API_TOKEN=<".reactiont5_token"
  ) else (
    echo 请先设置令牌（只需一次）:
    echo   echo 你的随机密码> .reactiont5_token
    echo   set REACTIONT5_API_TOKEN=你的随机密码
    echo.
  )
)

set ENABLE_REACTIONT5=1
start "ChemAgent-ReactionT5" cmd /k "cd /d "%~dp0" && set ENABLE_REACTIONT5=1 && set REACTIONT5_API_TOKEN=%REACTIONT5_API_TOKEN% && .venv\Scripts\python.exe -m uvicorn reactiont5_server:app --host 0.0.0.0 --port 8765"

timeout /t 3 /nobreak >nul
echo [OK] 已尝试启动服务。健康检查:
curl -s http://127.0.0.1:8765/health
echo.
echo.
echo -------- 公网隧道（二选一，另开窗口）--------
echo   cloudflared tunnel --url http://127.0.0.1:8765
echo   ngrok http 8765
echo.
echo 复制隧道给出的 https://... 地址，到 Streamlit Cloud → Secrets 更新:
echo   REACTIONT5_API_URL = "https://新地址"
echo   REACTIONT5_API_TOKEN = "与本机一致"
echo.
echo 注意：免费 quick tunnel 每次重启 URL 会变，必须改 Secrets。
echo 若要用固定域名，请配置 Cloudflare Named Tunnel。
echo.
pause
