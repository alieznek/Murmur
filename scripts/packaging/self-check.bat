@echo off
setlocal
chcp 65001 >nul
set "REPORT_DIR=%TEMP%\Murmur-diagnostics"
if not exist "%REPORT_DIR%" mkdir "%REPORT_DIR%"
set "REPORT=%REPORT_DIR%\offline-self-check.json"
echo 正在检查程序、OCR 和中英离线翻译，请稍候……
echo 自检使用合成内容，不读取个人密钥或聊天记录。
"%~dp0Murmur.exe" --self-check "%REPORT%"
if errorlevel 1 (
    echo 自检未通过，请将报告发送给提供安装包的人。
    echo 报告位置：%REPORT%
    pause
    exit /b 1
)
echo 自检通过。
echo 报告位置：%REPORT%
pause
exit /b 0
