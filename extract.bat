@echo off
REM ============================================================================
REM Service Photo POC — Gemini extraction runner
REM ============================================================================
REM Calls Gemini once per image in input_images/ and drops one JSON per image
REM into inbound/. Reads the API key from .env at the repo root.
REM
REM Defaults to gemini-2.5-flash. To use a different model, edit GEMINI_MODEL
REM in .env (or pass --model on the command line, but then run via terminal).
REM ============================================================================

cd /d %~dp0

echo Running Gemini extraction over input_images\ ...
echo.

backend\.venv\Scripts\python.exe scripts\run_gemini_extraction.py

echo.
echo Done. Open the Inbound screen at http://localhost:5173/#/inbound to review.
echo (Run dev.bat first if your servers aren't up.)
echo.
pause
