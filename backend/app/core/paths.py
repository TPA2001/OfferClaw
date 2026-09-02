"""路径解析 - 统一处理 Docker/打包模式与开发模式的目录定位

Docker 模式：
- 静态目录 = OFFERCABIN_STATIC_DIR 环境变量（如 /app/frontend/web）

打包模式（frozen）：
- 应用目录 = sys.executable 所在目录（exe 旁边）
- 数据目录 = 应用目录 / "data"（可写：SQLite、license 缓存、迁移备份）
- 静态目录 = sys._MEIPASS / "frontend" / "web"（只读：打包进来的前端文件）

开发模式：
- 应用目录 = backend/
- 数据目录 = backend/data
- 静态目录 = 项目根 / frontend / web
"""
import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    """是否处于 PyInstaller 打包模式"""
    return getattr(sys, "frozen", False)


def app_dir() -> Path:
    """应用运行目录（exe 所在 或 backend/）"""
    if is_frozen():
        # 打包后：exe 旁边放可写数据，与 CWD 无关，快捷方式/命令行启动都稳定
        return Path(sys.executable).parent
    # 开发模式：本文件 backend/app/core/paths.py → 向上两级到 backend/
    return Path(__file__).resolve().parent.parent.parent


def data_dir() -> Path:
    """可写数据目录（SQLite、迁移备份）"""
    d = app_dir() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def static_dir() -> Path:
    """前端静态文件目录（只读）"""
    # Docker/自定义部署：优先使用环境变量指定
    env_dir = os.getenv("OFFERCABIN_STATIC_DIR", "").strip()
    if env_dir:
        return Path(env_dir)
    if is_frozen():
        # spec 里 datas: ('frontend/web', 'frontend/web') → _MEIPASS/frontend/web
        return Path(sys._MEIPASS) / "frontend" / "web"
    return app_dir().parent / "frontend" / "web"


def admin_static_dir() -> Path:
    """管理后台前端静态文件目录（只读，与主站隔离）"""
    # Docker/自定义部署：优先使用环境变量指定
    env_dir = os.getenv("OFFERCABIN_ADMIN_STATIC_DIR", "").strip()
    if env_dir:
        return Path(env_dir)
    if is_frozen():
        # spec 里 datas: ('frontend/admin', 'frontend/admin') → _MEIPASS/frontend/admin
        return Path(sys._MEIPASS) / "frontend" / "admin"
    return app_dir().parent / "frontend" / "admin"


def web_styles_dir() -> Path:
    """主站样式目录（管理后台通过 /__styles 复用，保持设计系统一致）"""
    return static_dir() / "styles"
