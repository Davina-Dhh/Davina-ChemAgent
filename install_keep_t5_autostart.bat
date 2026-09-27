@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LINK=%STARTUP%\ChemAgent-KeepT5Online.bat"

(
echo @echo off
echo cd /d "%~dp0"
echo start "" "%~dp0keep_t5_online.bat"
) > "%LINK%"

echo 已加入开机启动:
echo   %LINK%
echo.
echo 以后电脑开机登录后会自动跑 keep_t5_online（服务+隧道+发布地址）。
echo Cloud 刷新页面即可调用；一般不用改 Secrets。
echo.
echo 取消自启: 删除上面那个 bat 即可。
echo.
pause
