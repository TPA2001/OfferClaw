# -*- mode: python ; coding: utf-8 -*-
"""OfferCabin PyInstaller 打包配置（onedir 模式）

产物：dist/OfferCabin/OfferCabin.exe + _internal/（含前端、chromium、依赖）
分发：把整个 dist/OfferCabin/ 文件夹打成 zip 给用户，解压后双击 OfferCabin.exe 即用

构建：在 backend/ 目录执行
    python -m PyInstaller offercabin.spec --clean --noconfirm
"""
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# spec 文件位于 backend/，SPECPATH = backend/，项目根 = SPECPATH.parent
PROJ_ROOT = Path(SPECPATH).parent
WEB_DIR = PROJ_ROOT / 'frontend' / 'web'

# playwright 浏览器二进制目录（%LOCALAPPDATA%\ms-playwright）
MS_PW = Path(os.environ.get('LOCALAPPDATA', '')) / 'ms-playwright'

datas = []
binaries = []

# 1) 前端静态文件 → _MEIPASS/frontend/web（供 main.py 的 StaticFiles 挂载）
if WEB_DIR.exists():
    datas.append((str(WEB_DIR), 'frontend/web'))
else:
    print(f'[警告] 前端目录不存在：{WEB_DIR}')

# 2) playwright Python 包（含 driver/node）数据 + 二进制 + 隐式 import
pw_datas, pw_bins, pw_hidden = collect_all('playwright')
datas += pw_datas
binaries += pw_bins

# 3) chromium 浏览器二进制 → _MEIPASS/ms-playwright/<name>
#    只打包 1223 版本（最新），跳过旧版 1124 省体积
#    run.py 已设 PLAYWRIGHT_BROWSERS_PATH=_MEIPASS/ms-playwright
if MS_PW.exists():
    for name in ['chromium-1223', 'chromium_headless_shell-1223', '.links', 'winldd-1007']:
        sub = MS_PW / name
        if sub.exists():
            datas.append((str(sub), f'ms-playwright/{name}'))
else:
    print(f'[警告] ms-playwright 不存在：{MS_PW}（Boss 登录/搜索功能将不可用）')

# 4) hiddenimports：uvicorn 子模块（已知 PyInstaller 追踪不全）+ 关键动态 import
hiddenimports = [
    # uvicorn 完整子模块树
    'uvicorn', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.asyncio',
    'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
    'uvicorn.protocols.http.h11_impl', 'uvicorn.protocols.http.httptools_impl',
    'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
    'uvicorn.protocols.websockets.wsproto_impl', 'uvicorn.protocols.websockets.websockets_impl',
    'uvicorn.lifespan', 'uvicorn.lifespan.on', 'uvicorn.lifespan.off',
    # FastAPI form 解析依赖
    'email', 'email.mime', 'multipart',
    # sqlalchemy 方言
    'sqlalchemy.dialects.sqlite',
    # 项目内可能被动态引用的子模块（保险起见显式列）
    'app.api.automation', 'app.api.license', 'app.api.profile', 'app.api.applications',
    'app.api.journal', 'app.api.settings', 'app.api.agent',
    'app.services.smart_fill', 'app.services.auto_filler', 'app.services.boss_search',
    'app.services.resume_service', 'app.services.playwright_runtime',
    'app.automation.form_extractor', 'app.automation.field_matcher',
    'app.models.profile', 'app.models.application',
    'app.core.license', 'app.core.migrations', 'app.core.paths',
    'app.core.database', 'app.core.llm', 'app.core.config_store',
] + pw_hidden

a = Analysis(
    ['run.py'],
    pathex=[str(Path(SPECPATH))],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tests', 'pytest', 'scripts', 'issue_license'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# onedir 模式：exe 只含脚本入口，依赖放 _internal/，启动快
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='OfferCabin',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX 压缩易触发杀软误报
    console=True,  # 保留控制台窗口便于看启动日志；正式发布可改 False
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 如有图标：icon=str(PROJ_ROOT / 'assets' / 'oc.ico')
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='OfferCabin',
)
