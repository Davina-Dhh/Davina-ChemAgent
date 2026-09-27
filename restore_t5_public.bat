@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo  电脑重启后：一键恢复 ReactionT5 公网
echo ========================================
echo.

REM 固定令牌文件（与 Cloud Secrets 里 REACTIONT5_API_TOKEN 一致）
if "%REACTIONT5_API_TOKEN%"=="" (
  if exist ".reactiont5_token" (
    set /p REACTIONT5_API_TOKEN=<".reactiont5_token"
  ) else (
    echo [首次] 正在生成 .reactiont5_token …
    powershell -NoProfile -Command "[guid]::NewGuid().ToString('N').Substring(0,24)" > ".reactiont5_token"
    set /p REACTIONT5_API_TOKEN=<".reactiont5_token"
    echo 已写入 .reactiont5_token=%REACTIONT5_API_TOKEN%
    echo 请把同一串写入 Streamlit Cloud Secrets 的 REACTIONT5_API_TOKEN
    echo.
  )
)

set ENABLE_REACTIONT5=1

echo [1/3] 启动本机推理服务 http://127.0.0.1:8765
start "ChemAgent-ReactionT5" cmd /k "cd /d "%~dp0" && set ENABLE_REACTIONT5=1 && set REACTIONT5_API_TOKEN=%REACTIONT5_API_TOKEN% && .venv\Scripts\python.exe -m uvicorn reactiont5_server:app --host 0.0.0.0 --port 8765"

echo 等待服务就绪…
timeout /t 8 /nobreak >nul
curl -s http://127.0.0.1:8765/health
echo.
echo.

where cloudflared >nul 2>&1
if %ERRORLEVEL%==0 (
  echo [2/3] 检测到 cloudflared，正在开隧道窗口…
  start "ChemAgent-Tunnel" cmd /k "cloudflared tunnel --url http://127.0.0.1:8765"
  echo.
  echo [3/3] 请看「ChemAgent-Tunnel」窗口里的 https://xxxx.trycloudflare.com
  echo       复制后打开 Streamlit Cloud → App settings → Secrets，更新:
  echo         REACTIONT5_API_URL = "https://刚才复制的地址"
  echo         REACTIONT5_API_TOKEN = "%REACTIONT5_API_TOKEN%"
  echo       保存后 Cloud 会自动用这台电脑；连不上才回退大模型。
) else (
  echo [2/3] 未安装 cloudflared。请任选:
  echo   A^) 安装: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/
  echo       然后另开终端: cloudflared tunnel --url http://127.0.0.1:8765
  echo   B^) 或用 ngrok: ngrok http 8765
  echo.
  echo [3/3] 把隧道给出的 https://... 写入 Cloud Secrets 的 REACTIONT5_API_URL
  echo       Token 使用: %REACTIONT5_API_TOKEN%
)

echo.
echo 注意: 免费 quick tunnel 每次重启 URL 都会变，必须改 Secrets。
echo       服务窗口和隧道窗口都不要关；电脑休眠也会断。
echo.
pause
