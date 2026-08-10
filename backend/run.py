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
    import uvicorn

    use_reload = "--reload" in sys.argv
    if use_reload:
        print("[警告] --reload 模式下 uvicorn 子进程可能使用 SelectorEventLoop，"
              "Playwright（Boss 登录/搜索）可能无法正常工作。", file=sys.stderr)

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=use_reload,
    )
