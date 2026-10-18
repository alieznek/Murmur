@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul

pushd "%~dp0"
if errorlevel 1 exit /b 1
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

for %%P in ("%~dp0.venv\Scripts\python.exe") do (
    if exist "%%~fP" (
        "%%~fP" -c "import PySide6.QtWidgets, rapidocr, onnxruntime, numpy, httpx, keyring.backends.Windows, ctranslate2, sentencepiece, minisbd, screen_translator.app" >nul 2>&1
        if not errorlevel 1 (
            set "TRANSLATOR_PYTHON=%%~fP"
            goto ready
        )
    )
)

echo [ERROR] No project Python environment with all required dependencies was found.
echo Run these commands from the project folder, then try again:
echo   python -m venv .venv
echo   .venv\Scripts\python.exe -m pip install -r requirements.lock
echo   .venv\Scripts\python.exe -m pip install -e . --no-deps --no-build-isolation
echo   .venv\Scripts\python.exe scripts\prepare_models.py
goto failed

:ready
for %%P in ("%TRANSLATOR_PYTHON%") do set "TRANSLATOR_PYTHONW=%%~dpPpythonw.exe"
if not exist "%TRANSLATOR_PYTHONW%" (
    echo [ERROR] pythonw.exe is missing. Please recreate the Python environment.
    goto failed
)
if /I "%~1"=="--check" (
    echo Using Python: "%TRANSLATOR_PYTHON%"
    popd
    exit /b 0
)

start "" "%TRANSLATOR_PYTHONW%" -m screen_translator.app
if errorlevel 1 (
    echo [ERROR] Could not start Screen Translator.
    goto failed
)
popd
exit /b 0

:failed
if /I not "%~1"=="--check" pause
popd
exit /b 1
