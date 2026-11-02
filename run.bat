@echo off
setlocal
cd /d "%~dp0"

rem Run from source (needs Python 3.8+ with tkinter).
rem Prefer the packaged exe if present - it needs no Python at all.

if exist "%~dp0dist\PCIe_TLP_Header_Parser.exe" (
    echo [INFO] Found packaged exe, launching it ...
    start "" "%~dp0dist\PCIe_TLP_Header_Parser.exe"
    goto :eof
)

set "PY=py -3"
where py >nul 2>nul
if errorlevel 1 set "PY=python"

%PY% -c "import tkinter" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python has no tkinter. Run dist\PCIe_TLP_Header_Parser.exe instead.
    pause
    exit /b 1
)

%PY% "%~dp0main.py"
if errorlevel 1 pause
endlocal
