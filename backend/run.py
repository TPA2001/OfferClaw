"""
OfferClaw 后端启动脚本

简化版：无 Playwright/Boss 依赖，直接启动 uvicorn。
Docker 环境使用 `uvicorn app.main:app` 启动，本脚本用于本地开发。

用法：
    python run.py            # 默认启动（0.0.0.0:8000）
    python run.py --reload   # 热重载模式（仅纯 API 开发）
"""
import sys
import asyncio
import os

if __name__ == "__main__":
    import uvicorn

    use_reload = "--reload" in sys.argv

    if getattr(sys, "frozen", False):
        # 打包模式：直接传 app 对象，绕过 uvicorn 字符串动态 import（frozen 下不可靠）
        try:
            from app.main import app as _app_obj
        except Exception as e:
            import traceback
            print(f"[启动失败] 导入 app.main 失败: {e}", file=sys.stderr)
            traceback.print_exc()
            input("按回车退出...")
            sys.exit(1)
        uvicorn.run(_app_obj, host="0.0.0.0", port=8000)
    else:
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=8000,
            reload=use_reload,
        )
