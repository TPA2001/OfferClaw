@echo off
REM OfferClaw 一键打包脚本
REM 产物：dist/OfferClaw/OfferClaw.exe + dist/OfferClaw-v1.1.0.zip
REM 用法：双击或 cmd 中执行 build_release.bat

setlocal
cd /d "%~dp0"

set VERSION=1.1.0
set OUT_DIR=dist\OfferClaw
set ZIP_PATH=dist\OfferClaw-v%VERSION%.zip

echo ============================================================
echo  OfferClaw v%VERSION% 打包
echo ============================================================
echo.

REM 1) 清理旧产物（PyInstaller --clean 会清 build/，但 dist/OfferClaw 需手动清）
if exist "%OUT_DIR%" (
    echo [1/3] 清理旧 dist\OfferClaw ...
    rmdir /s /q "%OUT_DIR%"
)
if exist "%ZIP_PATH%" del /q "%ZIP_PATH%"

REM 2) 调用 PyInstaller（用 spec 文件，--clean 清缓存，--noconfirm 覆盖）
echo [2/3] 调用 PyInstaller 打包 ...
python -m PyInstaller offerclaw.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo [错误] PyInstaller 打包失败，请查看上方日志
    pause
    exit /b 1
)

REM 3) 校验产物并压缩成 zip
if not exist "%OUT_DIR%\OfferClaw.exe" (
    echo [错误] 未找到 %OUT_DIR%\OfferClaw.exe
    pause
    exit /b 1
)

echo.
echo [3/3] 压缩成 zip ...
powershell -NoProfile -Command "Compress-Archive -Path 'dist\OfferClaw\*' -DestinationPath '%ZIP_PATH%' -Force"
if errorlevel 1 (
    echo [错误] 压缩失败
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  打包完成
echo ============================================================
echo  exe  目录: %~dp0%OUT_DIR%
echo  分发包  : %~dp0%ZIP_PATH%
echo.
echo  分发方式: 把 zip 发给用户，解压后双击 OfferClaw.exe 即可
echo ============================================================
pause
endlocal
