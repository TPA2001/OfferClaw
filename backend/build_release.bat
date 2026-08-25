@echo off
chcp 65001 >nul 2>&1
REM ============================================================
REM OfferClaw build script (desktop app + browser extension)
REM Output: dist/OfferClaw/
REM   |-- OfferClaw.exe + _internal/        desktop app (PyInstaller onedir)
REM   |-- offerclaw-extension/              Chrome MV3 extension
REM   `-- quick-start.txt                   usage guide (CN, UTF-8)
REM Zips:   dist/OfferClaw-v<VER>-full.zip   (app + extension bundle)
REM         dist/OfferClaw-extension-v<EXT_VER>.zip (extension only)
REM Usage:  double-click or run in cmd
REM ============================================================

setlocal
cd /d "%~dp0"

set VERSION=1.2.0
set EXT_VER=0.0.3
set PROJ_ROOT=%~dp0..
set OUT_DIR=dist\OfferClaw
set EXT_SRC=%PROJ_ROOT%\offerclaw-extension
set EXT_DST=%OUT_DIR%\offerclaw-extension
set ZIP_FULL=dist\OfferClaw-v%VERSION%-full.zip
set ZIP_EXT=dist\OfferClaw-extension-v%EXT_VER%.zip
set GUIDE_SRC=quick-start.txt
set GUIDE_DST=%OUT_DIR%\quick-start.txt

echo ============================================================
echo  OfferClaw v%VERSION% build (app + extension)
echo ============================================================
echo.

REM 1) Clean old artifacts (PyInstaller --clean clears build/, dist\OfferClaw needs manual clean)
if exist "%OUT_DIR%" (
    echo [1/5] Cleaning old dist\OfferClaw ...
    rmdir /s /q "%OUT_DIR%"
)
if exist "%ZIP_FULL%" del /q "%ZIP_FULL%"
if exist "%ZIP_EXT%" del /q "%ZIP_EXT%"

REM 2) Run PyInstaller (spec file, --clean clears cache, --noconfirm overwrites)
echo [2/5] Running PyInstaller for desktop app ...
python -m PyInstaller offerclaw.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller build failed, check logs above
    pause
    exit /b 1
)

REM 3) Verify desktop app artifact
if not exist "%OUT_DIR%\OfferClaw.exe" (
    echo [ERROR] Not found: %OUT_DIR%\OfferClaw.exe
    pause
    exit /b 1
)

REM 4) Copy browser extension into output dir
echo.
echo [3/5] Copying browser extension ...
if not exist "%EXT_SRC%\manifest.json" (
    echo [ERROR] Extension manifest.json not found: %EXT_SRC%
    pause
    exit /b 1
)
xcopy "%EXT_SRC%" "%EXT_DST%\" /e /i /y /q >nul
if errorlevel 1 (
    echo [ERROR] Failed to copy extension
    pause
    exit /b 1
)

REM 5) Copy quick-start guide
echo.
echo [4/5] Copying quick-start guide ...
if not exist "%GUIDE_SRC%" (
    echo [ERROR] Guide file not found: %GUIDE_SRC%
    pause
    exit /b 1
)
copy /y "%GUIDE_SRC%" "%GUIDE_DST%" >nul
if errorlevel 1 (
    echo [ERROR] Failed to copy guide
    pause
    exit /b 1
)

REM 6) Zip: full bundle (app+extension) + extension-only
echo.
echo [5/5] Zipping distribution packages ...

REM Full bundle (user extracts and runs OfferClaw.exe)
powershell -NoProfile -Command "Compress-Archive -Path 'dist\OfferClaw\*' -DestinationPath '%ZIP_FULL%' -Force"
if errorlevel 1 (
    echo [ERROR] Failed to zip full bundle
    pause
    exit /b 1
)

REM Extension-only zip (for users who only need to update extension)
powershell -NoProfile -Command "Compress-Archive -Path '%EXT_DST%\*' -DestinationPath '%ZIP_EXT%' -Force"
if errorlevel 1 (
    echo [WARN] Extension-only zip failed, full bundle still OK
)

echo.
echo ============================================================
echo  Build complete
echo ============================================================
echo  Full bundle : %ZIP_FULL%
echo  Extension   : %ZIP_EXT%
echo  App folder  : %OUT_DIR%
echo.
echo  Distribution:
echo    - Send OfferClaw-v%VERSION%-full.zip to users (extract, run OfferClaw.exe)
echo    - offerclaw-extension-v%EXT_VER%.zip for extension-only updates
echo ============================================================
pause
endlocal
