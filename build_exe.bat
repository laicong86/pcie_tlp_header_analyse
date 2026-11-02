@echo off
setlocal
cd /d "%~dp0"

rem ===========================================================
rem  PCIe TLP Header Parser - build script
rem  Usage:
rem      build_exe.bat        build single-file exe  -> dist\
rem      build_exe.bat dir    build folder version   -> dist\<name>\
rem ===========================================================

set "APPNAME=PCIe_TLP_Header_Parser"
set "MODE=%~1"
set "ONEFILE=--onefile"
set "OUTDESC=single-file"

if /i "%MODE%"=="dir" (
    set "ONEFILE=--onedir"
    set "OUTDESC=folder"
)

rem ---- pick a Python that has tkinter ----
set "PY=py -3"
where py >nul 2>nul
if errorlevel 1 set "PY=python"

%PY% -c "import tkinter" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] The selected Python has no tkinter. Install full Python 3.8+ first.
    exit /b 1
)

%PY% -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo [INFO] PyInstaller not found, installing...
    %PY% -m pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] Failed to install PyInstaller.
        exit /b 1
    )
)

if not exist "assets\app.ico" (
    %PY% tools\make_icon.py
)

echo.
echo [1/2] Cleaning old output ...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [2/2] Building %OUTDESC% ...
%PY% -m PyInstaller --noconfirm --clean %ONEFILE% --windowed ^
  --name "%APPNAME%" ^
  --icon "%~dp0assets\app.ico" ^
  --add-data "%~dp0assets\app.ico;assets" ^
  --version-file "%~dp0packaging\version_info.txt" ^
  --exclude-module tkinter.test ^
  --exclude-module unittest ^
  --exclude-module pydoc ^
  --exclude-module doctest ^
  --exclude-module lib2to3 ^
  --exclude-module sqlite3 ^
  --exclude-module distutils ^
  --exclude-module setuptools ^
  --exclude-module pip ^
  --noupx ^
  --distpath "%~dp0dist" ^
  --workpath "%~dp0build" ^
  --specpath "%~dp0build" ^
  "%~dp0main.py"

if errorlevel 1 (
    echo.
    echo [FAILED] Build aborted, see messages above.
    exit /b 1
)

echo.
echo [OK] Output:
if /i "%MODE%"=="dir" (
    echo      %~dp0dist\%APPNAME%\%APPNAME%.exe
) else (
    echo      %~dp0dist\%APPNAME%.exe
)
echo.
endlocal
