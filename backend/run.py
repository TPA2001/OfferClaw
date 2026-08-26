"""
OfferClaw 后端启动脚本

Windows 环境下，uvicorn --reload 模式会强制使用 SelectorEventLoop，
但 Playwright 需要 ProactorEventLoop 来启动 node 子进程。
本脚本在不使用 --reload 的情况下启动 uvicorn，确保事件循环正确。

用法：
    python run.py            # 默认启动（无热重载，Playwright 正常）
    python run.py --reload   # 热重载模式（Playwright 可能异常，仅用于纯 API 开发）

注意：需要修改后端代码时，请手动 Ctrl+C 重启本脚本。
"""
import sys
import asyncio
import os
from pathlib import Path

# 打包模式：playwright 浏览器路径指向 exe 内的 ms-playwright（spec 打包的 chromium）
if getattr(sys, "frozen", False):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(Path(sys._MEIPASS) / "ms-playwright")

# Windows 上必须使用 ProactorEventLoop，否则 Playwright 无法创建子进程
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    # monkeypatch uvicorn 的 loop 安装器，防止它覆盖回 SelectorEventLoop
    try:
        import uvicorn.loops.asyncio as _oc_loop
        _oc_loop.asyncio_setup = lambda use_subprocess=False: None
    except ImportError:
        pass

if __name__ == "__main__":
    # 免费分发：默认开启 OFFERCLAW_DEV=1（开放模式），授权门控全部放行，无需激活码。
    # 源码与打包(exe)一致生效；如需关闭，显式设置 OFFERCLAW_DEV=0 或 OFFERCLAW_LICENSE_GATE=1。
    if "OFFERCLAW_DEV" not in os.environ:
        os.environ["OFFERCLAW_DEV"] = "1"

    import uvicorn

    use_reload = "--reload" in sys.argv
    if use_reload:
        print("[警告] --reload 模式下 uvicorn 子进程可能使用 SelectorEventLoop，"
              "Playwright（Boss 登录/搜索）可能无法正常工作。", file=sys.stderr)

    # 打包模式启动后自动打开浏览器到应用首页（开发模式不自动开，避免干扰）
    if getattr(sys, "frozen", False):
        import threading
        import webbrowser
        import time
        def _open_browser():
            time.sleep(1.5)  # 等服务起来
            webbrowser.open("http://localhost:8000/")
        threading.Thread(target=_open_browser, daemon=True).start()

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
