@echo off
chcp 65001 >nul
rem Hermes Phone Remote - 启动手机可访问的 dashboard（幂等：已在跑就只提示）
rem 凭据不写在本脚本里；账号密码查看命令见下方 echo。
set "HV=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts"
set "PORT=9119"

echo [1/3] 检查 dashboard 是否已在运行...
curl -s -m 3 -o nul http://127.0.0.1:%PORT%/api/status && (echo     已在运行。& goto :addr)

echo [2/3] 启动 dashboard（隐藏窗口）...
start "" /min "%HV%\hermes.exe" dashboard --host 0.0.0.0 --port %PORT% --no-open --skip-build
timeout /t 4 >nul

:addr
echo [3/3] 手机访问地址：
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /c:"IPv4"') do echo     http://%%i:%PORT%/
echo.
echo 登录账号/用户名请查看:  hermes config get dashboard.basic_auth
echo 首次要用手机浏览器登录一次（勾选记住），之后扫码即可继续对话。
echo 提示：手机需与电脑连同一个 Wi-Fi；若打不开，检查防火墙是否放行 %PORT%。
pause
