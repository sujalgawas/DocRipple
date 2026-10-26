@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    python run.py
    exit /b %ERRORLEVEL%
)

where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    py run.py
    exit /b %ERRORLEVEL%
)

echo [DocRipple] Python not found in PATH. Starting services in separate command windows...
start "DocRipple Backend (Agent + FastAPI)" cmd /k "cd /d docsync-agent && if exist .venv\Scripts\activate.bat (call .venv\Scripts\activate.bat) && uvicorn src.main:app --reload --port 8000"
start "DocRipple Frontend (React/Vite)" cmd /k "cd /d frontend && npm run dev"
