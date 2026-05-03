@echo off
REM ============================================================================
REM Service Photo POC — dev environment launcher
REM ============================================================================
REM Opens TWO new windows, one for each server:
REM   - Backend  (FastAPI + uvicorn) at http://localhost:8000
REM   - Frontend (Vite + React)      at http://localhost:5173
REM Then opens the Inbound screen in your default browser.
REM
REM Press Ctrl+C in either server window to stop that server.
REM Close this window when you're done — it's safe to close anytime.
REM ============================================================================

echo Starting Service Photo dev environment...
echo.

REM %~dp0 = directory this .bat lives in (with trailing backslash). This makes
REM the script work whether you double-click it or run it from another cwd.

start "Service Photo - Backend" cmd /k "cd /d %~dp0backend && call .venv\Scripts\activate.bat && uvicorn service_photo.main:app --reload"

start "Service Photo - Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

REM Give Vite ~4s to print its "ready" line before opening the browser. Vite
REM usually boots in well under 1s; uvicorn's first request will block briefly
REM if the backend hasn't finished starting, but it'll catch up.
timeout /t 4 /nobreak > nul
start "" "http://localhost:5173/#/inbound"

echo.
echo   Backend:  http://localhost:8000   (docs at /docs)
echo   Frontend: http://localhost:5173/#/inbound  (opening in browser)
echo.
echo Each server runs in its own window. Press Ctrl+C there to stop it.
echo This launcher window can be closed at any time.
echo.
pause
