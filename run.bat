@echo off
setlocal

:: Get the absolute path of the project directory
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

:: Start FastAPI Backend inside the venv in a separate window
start cmd /k "call venv\Scripts\activate && python main.py"

:: Wait 3 seconds for FastAPI to boot up properly
timeout /t 3 /nobreak > nul

:: Start Ngrok with the Static Domain
echo Starting Ngrok Static Tunnel...
ngrok http --domain=reveler-species-operable.ngrok-free.dev 8000

endlocal