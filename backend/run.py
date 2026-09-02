"""
OfferCabin 后端启动脚本（单进程双 app 双端口）

默认：asyncio.gather 同时拉起
  - 主应用  app.main:app      0.0.0.0:8000      （公开站点）
  - 管理后台 app.admin_main:app  admin_host:admin_port（默认 127.0.0.1:8001）

两个 app 共享同一进程与 DB 引擎单例，管理后台跑在独立端口上、与公开应用隔离。

用法：
    python run.py                 # 双 app 双端口（默认）
    python run.py --reload        # 仅主 app 热重载（开发 API）
    python run.py --admin-only    # 仅管理后台（排查/开发管理端）
    python run.py --port 9000     # 覆盖主端口
    python run.py --host 0.0.0.0 # 覆盖主主机
"""
import sys
import asyncio
import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("offercabin.run")


def _parse_arg(name: str, default: str | None = None) -> str | None:
    """解析 --name value 形式参数"""
    flag = f"--{name}"
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def _build_server(app_ref: str, host: str, port: int, reload: bool = False):
    """构造 uvicorn Server（字符串 import 路径）"""
    import uvicorn
    config = uvicorn.Config(app_ref, host=host, port=port, reload=reload, log_config=None)
    return uvicorn.Server(config)


def _build_server_obj(app_obj, host: str, port: int):
    """构造 uvicorn Server（直接传 app 对象，frozen 模式用）"""
    import uvicorn
    config = uvicorn.Config(app_obj, host=host, port=port, log_config=None)
    return uvicorn.Server(config)


async def _serve_dual(main_app_obj, main_host: str, main_port: int,
                      admin_app_obj, admin_host: str, admin_port: int):
    """同时跑主 app 与管理后台 app（admin_app_obj 可为 None 表示跳过）"""
    servers = [_build_server_obj(main_app_obj, main_host, main_port)]
    logger.info(f"主应用启动于 http://{main_host}:{main_port}")
    if admin_app_obj is not None:
        servers.append(_build_server_obj(admin_app_obj, admin_host, admin_port))
        logger.info(f"管理后台启动于 http://{admin_host}:{admin_port}")
    else:
        logger.warning("管理后台未启动（配置未通过启动守卫），仅运行主应用")
    await asyncio.gather(*[s.serve() for s in servers])


if __name__ == "__main__":
    import uvicorn

    use_reload = "--reload" in sys.argv
    admin_only = "--admin-only" in sys.argv

    # 主端口/主机覆盖（默认 0.0.0.0:8000）
    main_host = _parse_arg("host", "0.0.0.0")
    main_port = int(_parse_arg("port", "8000"))

    # 管理端口/主机走 settings（默认 127.0.0.1:8001）
    from app.core.config import settings

    frozen = getattr(sys, "frozen", False)

    # ---- --reload 模式：仅主 app 热重载（管理后台不重载）----
    if use_reload:
        logger.info("热重载模式：仅主应用（app.main:app），管理后台不启动")
        uvicorn.run("app.main:app", host=main_host, port=main_port, reload=True)
        sys.exit(0)

    # ---- --admin-only 模式：仅管理后台 ----
    if admin_only:
        logger.info("仅管理后台模式（app.admin_main:app）")
        if frozen:
            try:
                from app.admin_main import app as _admin_obj
            except Exception as e:
                import traceback
                print(f"[启动失败] 导入 app.admin_main 失败: {e}", file=sys.stderr)
                traceback.print_exc()
                input("按回车退出...")
                sys.exit(1)
            uvicorn.run(_admin_obj, host=settings.admin_host, port=settings.admin_port)
        else:
            uvicorn.run(
                "app.admin_main:app",
                host=settings.admin_host,
                port=settings.admin_port,
            )
        sys.exit(0)

    # ---- 默认：双 app 双端口 ----
    # 预导入两个 app 对象：管理后台的启动硬守卫在此触发，
    # 失败时降级为仅主应用（绝不带着不安全配置运行管理后台）。
    try:
        from app.main import app as _main_obj
    except Exception as e:
        import traceback
        print(f"[启动失败] 导入 app.main 失败: {e}", file=sys.stderr)
        traceback.print_exc()
        input("按回车退出...")
        sys.exit(1)

    _admin_obj = None
    try:
        from app.admin_main import app as _admin_obj  # noqa: F811
    except RuntimeError as e:
        logger.warning(f"管理后台未启动（启动守卫拒绝）：{e}")
        logger.warning("如需管理后台：设置 AUTH_MODE=jwt 且 SECRET_KEY 为强随机值后重启")
        _admin_obj = None
    except Exception as e:
        logger.warning(f"管理后台导入异常，跳过：{e}")
        _admin_obj = None

    try:
        asyncio.run(_serve_dual(
            _main_obj, main_host, main_port,
            _admin_obj, settings.admin_host, settings.admin_port,
        ))
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在退出...")
    except OSError as e:
        # 端口被占用（Win Errno 10048 / Linux 98）：给出可读提示而非堆栈
        win_in_use = getattr(e, "winerror", None) == 10048 or "10048" in str(e)
        logger.error(
            f"端口被占用，无法启动（{e}）。"
            f"通常是上一个 OfferCabin 进程未退出。"
        )
        logger.error(
            f"排查：netstat -ano | findstr :{main_port}  /  findstr :{settings.admin_port}"
        )
        logger.error(
            "解决：用 `taskkill /F /PID <占用进程PID>` 杀掉残留进程，"
            "或换端口：python run.py --port 8002"
        )
        if not win_in_use:
            raise
