"""
Playwright 运行时基础设施（CDP 模式）

核心策略（参考网上最佳实践）：
1. 用 subprocess 启动真实系统 Chrome（非 Playwright Chromium）
   - 加 --remote-debugging-port 开启调试端口
   - 加 --user-data-dir 持久化登录态（cookie/localStorage 跨会话保留）
2. Playwright 用 connect_over_cdp 连接已启动的 Chrome
3. 因为是真实用户启动的 Chrome，无任何自动化痕迹，Boss 无法识别

为什么不用 launch_persistent_context？
- Boss 直聘能识别 Playwright Chromium（即使加 --disable-blink-features）
- 返回 HTTP 200 但 JS 清空页面到 about:blank（白屏）
- 系统 Chrome（channel="chrome"）仍会被识别（launch_persistent_context 模式下）
- 唯一可靠方案：subprocess 启动真实 Chrome + CDP 连接

环境要求：
- 系统已安装 Google Chrome（或 Chromium / Edge）
- Windows 默认路径：C:\Program Files\Google\Chrome\Application\chrome.exe
"""

import os
import sys
import asyncio
import subprocess
import logging
import socket
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger("offerclaw.playwright")


# ============================================================================
# 配置
# ============================================================================

# userDataDir 根目录（保存各站点的登录态）
USER_DATA_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "browser_profiles"
USER_DATA_ROOT.mkdir(parents=True, exist_ok=True)

# 默认 CDP 调试端口（可被占用时自动递增）
DEFAULT_CDP_PORT = 9222

# Chrome 可执行文件候选路径（按优先级）
CHROME_CANDIDATES = [
    # Windows
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Users\{user}\AppData\Local\Google\Chrome\Application\chrome.exe",
    # Edge（兼容）
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    # macOS
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    # Linux
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
]


def find_chrome_path() -> Optional[str]:
    """查找系统 Chrome 可执行文件路径"""
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    for candidate in CHROME_CANDIDATES:
        path = candidate.replace("{user}", user)
        if os.path.exists(path):
            logger.info(f"找到 Chrome: {path}")
            return path
    return None


def get_user_data_dir(site: str, user_id: str = "default") -> Path:
    """获取指定站点 + 用户的 userDataDir 路径"""
    safe_user = "".join(c if c.isalnum() or c in "-_" else "_" for c in user_id)
    p = USER_DATA_ROOT / site / safe_user
    p.mkdir(parents=True, exist_ok=True)
    return p


# ============================================================================
# 端口管理
# ============================================================================

def find_free_port(start: int = DEFAULT_CDP_PORT, max_tries: int = 20) -> int:
    """从 start 开始找一个空闲端口"""
    for port in range(start, start + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"在 {start}-{start+max_tries} 范围内找不到空闲端口")


def is_port_in_use(port: int) -> bool:
    """检查端口是否被占用（CDP 端口是否已开启）"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


# ============================================================================
# Chrome 进程管理
# ============================================================================

# 已启动的 Chrome 进程映射：{(site, user_id): (port, subprocess.Popen)}
_running_chromes: Dict[Tuple[str, str], Tuple[int, subprocess.Popen]] = {}


def start_chrome(
    site: str,
    user_id: str = "default",
    headless: bool = False,
    extra_args: Optional[list] = None,
    initial_url: Optional[str] = None,
) -> Tuple[int, subprocess.Popen]:
    """
    启动真实系统 Chrome（带远程调试端口）

    Args:
        site: 站点标识（决定 userDataDir）
        user_id: 用户 ID
        headless: 是否无头（反爬场景建议 headful，让用户能手动通过滑块）
        extra_args: 额外启动参数
        initial_url: Chrome 启动时直接打开的 URL（不通过 CDP 导航，避免被反爬检测）

    Returns:
        (port, process): CDP 端口号 + subprocess.Popen 对象

    Raises:
        RuntimeError: Chrome 未安装或启动失败
    """
    key = (site, user_id)
    if key in _running_chromes:
        port, proc = _running_chromes[key]
        if proc.poll() is None and is_port_in_use(port):
            # 检查已运行 Chrome 的 headless 状态是否与请求一致
            cmdline = " ".join(proc.args) if hasattr(proc, "args") and proc.args else ""
            is_running_headless = "--headless" in cmdline
            if is_running_headless == headless:
                logger.info(f"Chrome 已在运行 (site={site}, port={port}, headless={is_running_headless})")
                return port, proc
            else:
                # headless 模式不同，先停止旧的再启动新的
                logger.info(
                    f"已运行 Chrome headless={is_running_headless}，"
                    f"请求 headless={headless}，先停止旧 Chrome 再启动新的"
                )
                stop_chrome(site, user_id)
        else:
            # 进程已退出，清理
            del _running_chromes[key]

    chrome_path = find_chrome_path()
    if not chrome_path:
        raise RuntimeError(
            "未找到系统 Chrome。请安装 Google Chrome：https://www.google.com/chrome/\n"
            "或 Microsoft Edge（Windows 默认已安装）"
        )

    port = find_free_port()
    user_data_dir = str(get_user_data_dir(site, user_id))

    args = [
        chrome_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-popup-blocking",
        # 注意：不加 --disable-blink-features=AutomationControlled
        # 因为是真实 Chrome 启动，本身就没有 webdriver 标记
    ]
    if headless:
        args.append("--headless=new")
    if extra_args:
        args.extend(extra_args)
    # 初始 URL 放在最后（Chrome 会自动打开这个 URL，不通过 CDP 导航）
    if initial_url:
        args.append(initial_url)

    logger.info(f"启动 Chrome: {chrome_path}")
    logger.info(f"  port={port}, user_data_dir={user_data_dir}, headless={headless}")

    # 启动进程（不阻塞）
    if sys.platform == "win32":
        # Windows：用 CREATE_NEW_PROCESS_GROUP 避免被父进程终止
        proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    else:
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 等待 CDP 端口就绪
    for _ in range(30):
        if is_port_in_use(port):
            logger.info(f"Chrome CDP 端口就绪: {port}")
            break
        time.sleep(0.5)
    else:
        logger.warning(f"Chrome 启动后 CDP 端口 {port} 未就绪，但继续尝试连接")

    _running_chromes[key] = (port, proc)
    return port, proc


def stop_chrome(site: str, user_id: str = "default"):
    """停止已启动的 Chrome 进程"""
    key = (site, user_id)
    if key not in _running_chromes:
        return
    port, proc = _running_chromes.pop(key)
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        logger.info(f"已停止 Chrome (site={site}, port={port})")
    except Exception as e:
        logger.warning(f"停止 Chrome 异常: {e}")


def stop_all_chromes():
    """停止所有已启动的 Chrome 进程"""
    for key in list(_running_chromes.keys()):
        stop_chrome(*key)


# ============================================================================
# CDP 连接（核心）
# ============================================================================

async def connect_to_chrome(
    site: str,
    user_id: str = "default",
    headless: bool = False,
    auto_start: bool = True,
) -> Tuple[Any, Any, int]:
    """
    启动（或复用）真实 Chrome 并通过 CDP 连接

    用法：
        async with async_playwright() as pw:
            browser, context, port = await connect_to_chrome("boss", user_id, pw)
            page = await context.new_page()
            ...
            await browser.close()  # 仅断开 CDP 连接，Chrome 进程保持运行

    Args:
        site: 站点标识
        user_id: 用户 ID
        headless: 是否无头
        auto_start: True=Chrome 未运行时自动启动；False=仅连接已运行的 Chrome
        pw: playwright 实例（由调用方传入）

    Returns:
        (browser, context, port)：CDP 连接的 Browser、默认 Context、CDP 端口
    """
    from playwright.async_api import async_playwright

    # 启动或复用 Chrome
    key = (site, user_id)
    if key in _running_chromes:
        port, proc = _running_chromes[key]
        if proc.poll() is not None or not is_port_in_use(port):
            logger.info(f"Chrome 已退出，重新启动")
            del _running_chromes[key]
            if auto_start:
                port, proc = start_chrome(site, user_id, headless)
            else:
                raise RuntimeError(f"Chrome 未运行 (site={site})")
    else:
        if auto_start:
            port, proc = start_chrome(site, user_id, headless)
        else:
            raise RuntimeError(f"Chrome 未运行 (site={site})，请先调用 open_login_page")

    # CDP 连接
    logger.info(f"CDP 连接: http://127.0.0.1:{port}")
    browser = await async_playwright().start()
    try:
        cdp_browser = await browser.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    except Exception as e:
        await browser.stop()
        raise RuntimeError(f"CDP 连接失败（端口 {port}）: {e}")

    # 获取默认 context（Chrome 启动时已有一个）
    if len(cdp_browser.contexts) > 0:
        context = cdp_browser.contexts[0]
    else:
        context = await cdp_browser.new_context()

    return cdp_browser, context, port


# ============================================================================
# 高层 API：打开登录页（headful，让用户手动登录）
# ============================================================================

async def open_login_page(
    site: str,
    user_id: str,
    login_url: str,
    headless: bool = False,
) -> Dict[str, Any]:
    """
    以 headful 模式打开真实 Chrome 登录页（让用户手动登录，登录态自动保存到 userDataDir）

    核心策略（实测验证）：
    - 通过命令行参数让 Chrome 启动时直接打开 login_url（不通过 CDP page.goto）
    - Chrome 自己加载页面，行为与用户手动打开完全一致，Boss 无法检测
    - 完全不使用 CDP 连接（CDP 连接会导致 Boss 页面关闭/白屏）
    - 只监听 Chrome 进程退出，等待用户手动登录后关闭浏览器

    流程：
    1. subprocess 启动真实 Chrome（带 --remote-debugging-port + --user-data-dir + login_url）
    2. Chrome 自动打开 login_url，用户看到登录页
    3. 用户手动完成登录（滑块/短信验证码），登录态保存到 userDataDir
    4. 用户关闭浏览器，函数返回

    注意：此函数会阻塞直到用户关闭浏览器窗口，或最长 10 分钟超时。

    Returns:
        dict: { "success": bool, "loaded": bool, "message": str }
    """
    logger.info(f"打开 {site} 登录页 (user={user_id}, headless={headless})")

    try:
        # 1. 启动真实 Chrome（headful），并通过命令行参数直接打开登录页
        #    关键：不通过 CDP 的 page.goto 导航，避免 Boss 检测到 CDP 控制后白屏
        #    Chrome 启动时自己加载登录页，行为与用户手动打开完全一致
        port, proc = start_chrome(site, user_id, headless=headless, initial_url=login_url)

        # 2. 等待几秒确认 Chrome 启动成功
        await asyncio.sleep(3)
        if proc.poll() is not None:
            return {"success": False, "loaded": False, "message": "Chrome 启动后立即退出，请检查 Chrome 安装"}

        logger.info(f"Chrome 已启动 (PID={proc.pid})，登录页应已打开，等待用户手动登录...")

        # 3. 监听 Chrome 进程退出，等待用户关闭浏览器（最长 10 分钟）
        close_event = asyncio.Event()

        async def watch_process():
            """监视 Chrome 进程，退出时触发 close_event"""
            while proc.poll() is None:
                await asyncio.sleep(1)
            close_event.set()

        asyncio.create_task(watch_process())

        try:
            await asyncio.wait_for(close_event.wait(), timeout=600)
            logger.info("Chrome 浏览器已关闭（用户完成登录操作）")
        except asyncio.TimeoutError:
            logger.warning("等待用户登录超时（10 分钟），自动结束")
            # 超时后不主动 kill Chrome，让用户继续操作

        # 4. 清理进程跟踪
        key = (site, user_id)
        if key in _running_chromes:
            del _running_chromes[key]

        return {
            "success": True,
            "loaded": True,
            "message": "登录完成，登录态已保存到本地。现在可以回到 OfferClaw 进行岗位搜索。",
        }
    except Exception as e:
        logger.error(f"打开登录页失败: {e}", exc_info=True)
        return {"success": False, "loaded": False, "message": str(e)}


# ============================================================================
# 高层 API：检查登录态（headless）
# ============================================================================

async def check_login_status(
    site: str,
    user_id: str,
    login_check_url: str,
    logged_in_indicator: str,
    login_url: str,
) -> Dict[str, Any]:
    """
    检查指定站点的登录态（headless，通过 Cookie 判断，不导航避免触发反爬）

    策略（参考 boss-cli）：
    - 启动 headless Chrome（复用 userDataDir）
    - CDP 连接，但不导航，只读取已存在的 cookie
    - 检查必需 cookie 是否齐全（判断登录态）
    - 对 Boss 站点，额外调用 wapi 验证 cookie 是否有效

    Args:
        site: 站点标识
        user_id: 用户 ID
        login_check_url: 用于探测登录态的 URL（保留参数，兼容旧调用）
        logged_in_indicator: CSS 选择器（保留参数，兼容旧调用）
        login_url: 登录页 URL

    Returns:
        dict: { "logged_in": bool, "login_url": str, "site": str, "message": str, "screenshot": Optional[str] }
    """
    from playwright.async_api import async_playwright

    logger.info(f"检查 {site} 登录态 (user={user_id})")

    try:
        # 启动 headless Chrome
        port, proc = start_chrome(site, user_id, headless=True)

        async with async_playwright() as pw:
            try:
                browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            except Exception as e:
                return {
                    "logged_in": False,
                    "login_url": login_url,
                    "site": site,
                    "message": f"CDP 连接失败: {e}",
                    "screenshot": None,
                }

            try:
                # 获取默认 context
                if len(browser.contexts) > 0:
                    context = browser.contexts[0]
                else:
                    context = await browser.new_context()

                # 关键：不导航，直接读取已存在的 cookie
                # （导航会触发 Boss 反爬，但读取 cookie 不会）
                cookies_list = await context.cookies("https://www.zhipin.com")
                cookies: Dict[str, str] = {}
                for c in cookies_list:
                    name = c.get("name", "")
                    value = c.get("value", "")
                    if name and value:
                        cookies[name] = value

                # 检查必需 cookie
                required_cookies = {"__zp_stoken__", "wt2", "wbg", "zp_at"}
                has_required = bool(required_cookies & set(cookies.keys()))
                cookie_count = len(cookies)

                logger.info(
                    f"登录态检查: 提取到 {cookie_count} 个 cookie，"
                    f"必需 cookie 完整: {has_required}"
                )

                return {
                    "logged_in": has_required,
                    "login_url": login_url,
                    "site": site,
                    "message": "已登录" if has_required else "未登录，请先点击「登录 Boss」完成登录",
                    "screenshot": None,
                    "cookie_count": cookie_count,
                }
            finally:
                try:
                    await browser.close()
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"登录态检查失败: {e}")
        return {
            "logged_in": False,
            "login_url": login_url,
            "site": site,
            "message": f"检查失败: {e}",
            "screenshot": None,
        }
    finally:
        # headless 检查完即关闭 Chrome（释放资源）
        key = (site, user_id)
        if key in _running_chromes:
            port, proc = _running_chromes[key]
            if proc.poll() is None:
                cmdline = " ".join(proc.args) if hasattr(proc, "args") else ""
                if "--headless" in cmdline:
                    stop_chrome(site, user_id)


# ============================================================================
# 高层 API：执行页面操作（用于 Boss 搜索 / 自动填表）
# ============================================================================

async def run_in_chrome(
    site: str,
    user_id: str,
    url: str,
    action: callable,
    headless: bool = True,
    timeout: int = 60,
) -> Any:
    """
    在真实 Chrome 中打开 URL 并执行操作

    Args:
        site: 站点标识
        user_id: 用户 ID
        url: 要打开的 URL
        action: 异步函数 async def action(page) -> Any
        headless: 是否无头
        timeout: 总超时（秒）

    Returns:
        action 函数的返回值
    """
    from playwright.async_api import async_playwright

    port, proc = start_chrome(site, user_id, headless=headless)

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        try:
            if len(browser.contexts) > 0:
                context = browser.contexts[0]
            else:
                context = await browser.new_context()

            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)
                return await action(page)
            finally:
                await page.close()
        finally:
            try:
                await browser.close()
            except Exception:
                pass


# ============================================================================
# 人类化操作辅助函数（反爬用）
# ============================================================================

async def human_delay(min_sec: float = 0.5, max_sec: float = 1.5):
    """人类化随机延迟（反爬：避免请求过于规律）"""
    import random
    delay = random.uniform(min_sec, max_sec)
    await asyncio.sleep(delay)


async def human_scroll(page, steps: int = 3, min_step: int = 200, max_step: int = 600):
    """
    人类化分步滚动（触发懒加载 + 反爬）

    Args:
        page: Playwright Page 对象
        steps: 滚动步数
        min_step: 每步最小像素
        max_step: 每步最大像素
    """
    import random
    for _ in range(steps):
        delta = random.randint(min_step, max_step)
        try:
            await page.mouse.wheel(0, delta)
        except Exception:
            try:
                await page.evaluate(f"window.scrollBy(0, {delta})")
            except Exception:
                pass
        await asyncio.sleep(random.uniform(0.3, 0.8))


# ============================================================================
# Boss 直聘专用配置
# ============================================================================

BOSS_LOGIN_URL = "https://www.zhipin.com/web/user/?ka=header-login"
BOSS_LOGIN_CHECK_URL = "https://www.zhipin.com/web/geek/recommend?ka=header-user"
BOSS_LOGGED_IN_INDICATOR = ".user-info, .header-user, [class*='user-name'], .btn-sign-up"


async def check_boss_login(user_id: str = "default") -> Dict[str, Any]:
    """检查 Boss 直聘登录态"""
    return await check_login_status(
        site="boss",
        user_id=user_id,
        login_check_url=BOSS_LOGIN_CHECK_URL,
        logged_in_indicator=BOSS_LOGGED_IN_INDICATOR,
        login_url=BOSS_LOGIN_URL,
    )


async def open_boss_login(user_id: str = "default") -> Dict[str, Any]:
    """打开 Boss 直聘登录页（headful 真实 Chrome）"""
    return await open_login_page(
        site="boss",
        user_id=user_id,
        login_url=BOSS_LOGIN_URL,
        headless=False,
    )
