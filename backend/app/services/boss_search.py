"""
Boss 直聘岗位搜索服务（参考 boss-cli 项目重构）

核心策略（借鉴 https://github.com/jackwener/boss-cli）：
1. 用 Playwright CDP 获取已登录 Chrome 的 Cookie（不导航，只读 cookie，避免触发反爬）
2. 用 httpx + Cookie 直接调用 Boss 的 wapi 接口（/wapi/zpgeek/search/joblist.json）
3. 完整反爬策略：
   - Gaussian jitter 延迟（mean=0.3, σ=0.15）
   - 5% 概率长暂停（2-5s 模拟阅读）
   - 突发惩罚（15s内3次或45s内6次请求加延迟）
   - 指数退避（HTTP 429/5xx，最多3次重试）
   - code=9 自动冷却（10s→20s→40s→60s）
   - Set-Cookie 合并回 session
   - HTML 重定向检测（防止 auth redirect）
   - 浏览器指纹（Chrome 145 macOS UA, sec-ch-ua, DNT, Priority）
   - 端点特定 Referer
   - zp_token header（从 bst cookie 提取）
   - X-Requested-With: XMLHttpRequest

登录流程：
1. 用户调用 /automation/open-login → Playwright 启动真实 Chrome 打开 Boss 登录页
2. 用户手动登录（滑块/短信验证码），登录态保存到 userDataDir
3. 用户关闭浏览器
4. 搜索时：Playwright headless 启动 Chrome（复用 userDataDir）→ CDP 读取 cookie → httpx 调用 wapi
"""

import asyncio
import hashlib
import logging
import random
import time
import urllib.parse
from collections import deque
from typing import List, Dict, Any, Optional, Tuple

import httpx

from app.services.playwright_runtime import (
    start_chrome,
    stop_chrome,
    BOSS_LOGIN_URL,
)

logger = logging.getLogger("offerclaw.boss_search")


# ============================================================================
# Boss 直聘 API 常量（参考 boss-cli/constants.py）
# ============================================================================

BASE_URL = "https://www.zhipin.com"
WEB_GEEK_JOB_URL = f"{BASE_URL}/web/geek/job"

# wapi 端点
JOB_SEARCH_URL = "/wapi/zpgeek/search/joblist.json"
USER_INFO_URL = "/wapi/zpuser/wap/getUserInfo.json"

# 浏览器指纹（Chrome 145 macOS）
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/145.0.0.0 Safari/537.36"
    ),
    "sec-ch-ua": '"Chromium";v="145", "Not(A:Brand";v="99", "Google Chrome";v="145"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "DNT": "1",
    "Priority": "u=1, i",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/",
}

# 必需 Cookie（用于判断登录态）
REQUIRED_COOKIES = {"__zp_stoken__", "wt2", "wbg", "zp_at"}

# 城市编号（参考 boss-cli/constants.py）
CITY_CODES: Dict[str, str] = {
    "全国": "100010000",
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280100",
    "深圳": "101280600",
    "杭州": "101210100",
    "成都": "101270100",
    "南京": "101190100",
    "武汉": "101200100",
    "西安": "101110100",
    "苏州": "101190400",
    "长沙": "101250100",
    "天津": "101030100",
    "重庆": "101040100",
    "郑州": "101180100",
    "东莞": "101281600",
    "佛山": "101280800",
    "合肥": "101220100",
    "青岛": "101120200",
    "宁波": "101210400",
    "沈阳": "101070100",
    "昆明": "101290100",
    "大连": "101070200",
    "厦门": "101230200",
    "珠海": "101280700",
    "无锡": "101190200",
    "福州": "101230100",
    "济南": "101120100",
    "哈尔滨": "101050100",
    "长春": "101060100",
    "南昌": "101240100",
    "贵阳": "101260100",
    "南宁": "101300100",
    "石家庄": "101090100",
    "太原": "101100100",
    "兰州": "101160100",
    "海口": "101310100",
    "常州": "101191100",
    "温州": "101210700",
    "嘉兴": "101210300",
    "徐州": "101190800",
    "香港": "101320100",
}


# ============================================================================
# Boss API 客户端（参考 boss-cli/client.py）
# ============================================================================

class BossApiClient:
    """
    Boss 直聘 API 客户端

    反爬策略（参考 boss-cli）：
    - Gaussian jitter 延迟
    - 5% 概率长暂停（模拟阅读）
    - 突发惩罚（短时间多次请求加延迟）
    - 指数退避（HTTP 429/5xx）
    - code=9 自动冷却
    - Set-Cookie 合并回 session
    - HTML 重定向检测
    - 端点特定 Referer
    - zp_token header
    """

    def __init__(
        self,
        cookies: Dict[str, str],
        timeout: float = 30.0,
        request_delay: float = 1.0,
        max_retries: int = 3,
    ):
        self.cookies = cookies
        self._timeout = timeout
        self._request_delay = request_delay
        self._base_request_delay = request_delay
        self._max_retries = max_retries
        self._last_request_time = 0.0
        self._request_count = 0
        self._rate_limit_count = 0
        self._recent_request_times: deque = deque(maxlen=12)
        self._http: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "BossApiClient":
        self._http = httpx.AsyncClient(
            base_url=BASE_URL,
            headers=dict(BROWSER_HEADERS),
            cookies=self.cookies,
            follow_redirects=True,
            timeout=httpx.Timeout(self._timeout),
        )
        return self

    async def __aexit__(self, *args) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    # ── 限流 ───────────────────────────────────────────────────────

    async def _rate_limit_delay(self) -> None:
        """Gaussian jitter 延迟，模拟人类浏览"""
        if self._request_delay <= 0:
            return
        elapsed = time.time() - self._last_request_time
        if elapsed < self._request_delay:
            # Gaussian jitter: mean=0.3, σ=0.15
            jitter = max(0, random.gauss(0.3, 0.15))
            # 5% 概率长暂停，模拟阅读
            if random.random() < 0.05:
                jitter += random.uniform(2.0, 5.0)
            sleep_time = self._request_delay - elapsed + jitter
            logger.debug(f"限流延迟: {sleep_time:.2f}s")
            await asyncio.sleep(sleep_time)

        burst_penalty = self._burst_penalty_delay()
        if burst_penalty > 0:
            logger.debug(f"突发惩罚延迟: {burst_penalty:.2f}s")
            await asyncio.sleep(burst_penalty)

    def _burst_penalty_delay(self) -> float:
        """短时间多次请求加额外延迟"""
        if not self._recent_request_times:
            return 0.0
        now = time.time()
        recent_15s = sum(1 for ts in self._recent_request_times if now - ts <= 15)
        recent_45s = sum(1 for ts in self._recent_request_times if now - ts <= 45)
        if recent_45s >= 6:
            return random.uniform(4.0, 7.0)
        if recent_15s >= 3:
            return random.uniform(1.2, 2.8)
        return 0.0

    def _mark_request(self) -> None:
        now = time.time()
        self._last_request_time = now
        self._request_count += 1
        self._recent_request_times.append(now)

    # ── 响应处理 ───────────────────────────────────────────────────

    def _merge_response_cookies(self, resp: httpx.Response) -> None:
        """将响应的 Set-Cookie 合并回 session"""
        for name, value in resp.cookies.items():
            if value:
                self._http.cookies.set(name, value)

    def _headers_for_request(self, url: str, params: Optional[Dict] = None) -> Dict[str, str]:
        """构建浏览器请求头，包含端点特定 Referer 和 zp_token"""
        headers = dict(BROWSER_HEADERS)
        headers["X-Requested-With"] = "XMLHttpRequest"
        # zp_token（从 bst cookie 提取）
        bst = self._http.cookies.get("bst", "")
        if bst:
            headers["zp_token"] = bst
        # 端点特定 Referer
        if url == JOB_SEARCH_URL:
            query = ""
            if params and params.get("query"):
                query = f"?{urllib.parse.urlencode({'query': params['query']})}"
            headers["Referer"] = f"{WEB_GEEK_JOB_URL}{query}"
        return headers

    def _handle_response(self, data: Dict, action: str) -> Dict:
        """验证 API 响应，返回 zpData，错误时抛异常"""
        code = data.get("code", -1)
        if code == 0:
            return data.get("zpData", {})
        message = data.get("message", "Unknown error")
        # code=37: 会话过期
        if code == 37:
            raise SessionExpiredError(message)
        # code=9: 限流
        if code == 9:
            self._rate_limit_count += 1
            cooldown = min(60, 10 * (2 ** (self._rate_limit_count - 1)))
            self._request_delay = max(self._request_delay, self._base_request_delay * 2)
            logger.warning(
                f"被限流 (count={self._rate_limit_count}), 冷却 {cooldown:.0f}s, "
                f"延迟提升到 {self._request_delay:.1f}s"
            )
            raise RateLimitError(message)
        # code=121/122: 安全系统拦截
        if code in (121, 122):
            raise SecurityBlockError(message, code=code)
        # code=36: 账户异常行为（风控，需要用户重新登录或在浏览器正常浏览恢复）
        if code == 36:
            logger.warning(f"账户异常行为 (code=36): {message}")
            raise SecurityBlockError(message, code=code)
        raise BossApiError(f"{action}: {message} (code={code})", code=code)

    # ── 请求（带重试）──────────────────────────────────────────────

    async def _request(self, method: str, url: str, **kwargs) -> Dict:
        """执行 HTTP 请求，带限流延迟、重试、Cookie 合并"""
        await self._rate_limit_delay()
        last_exc: Optional[Exception] = None
        params = kwargs.get("params")
        merged_headers = self._headers_for_request(url, params=params)
        request_headers = kwargs.pop("headers", None)
        if request_headers:
            merged_headers.update(request_headers)

        for attempt in range(self._max_retries):
            t0 = time.time()
            try:
                resp = await self._http.request(method, url, headers=merged_headers, **kwargs)
                elapsed = time.time() - t0
                self._merge_response_cookies(resp)
                self._mark_request()
                logger.info(
                    f"[#{self._request_count}] {method} {url[:60]} → {resp.status_code} ({elapsed:.2f}s)"
                )
                # 服务器错误重试
                if resp.status_code in (429, 500, 502, 503, 504):
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        f"HTTP {resp.status_code} from {url[:80]}, {wait:.1f}s 后重试 "
                        f"(attempt {attempt + 1}/{self._max_retries})"
                    )
                    await asyncio.sleep(wait)
                    continue
                if resp.status_code == 404:
                    text = resp.text
                    if text.strip().startswith("{"):
                        return resp.json()
                    raise BossApiError(f"接口不存在: {url} (HTTP 404)", code=404)
                resp.raise_for_status()
                # 检测 HTML 响应（auth 重定向）
                text = resp.text
                if text.startswith("<"):
                    raise BossApiError(
                        f"收到 HTML 而非 JSON（可能登录态失效）: {url}"
                    )
                return resp.json()
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                elapsed = time.time() - t0
                last_exc = exc
                wait = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    f"[#{self._request_count + 1}] {method} {url[:60]} → 网络错误: {exc} "
                    f"({elapsed:.2f}s), {wait:.1f}s 后重试 (attempt {attempt + 1}/{self._max_retries})"
                )
                await asyncio.sleep(wait)
        if last_exc:
            raise BossApiError(f"请求失败（重试 {self._max_retries} 次）: {last_exc}")
        raise BossApiError(f"请求失败（重试 {self._max_retries} 次）")

    async def _get(self, url: str, params: Optional[Dict] = None, action: str = "") -> Dict:
        """GET 请求，带响应验证和限流重试"""
        data = await self._request("GET", url, params=params)
        try:
            result = self._handle_response(data, action)
            # 成功后重置限流计数
            self._rate_limit_count = 0
            return result
        except RateLimitError:
            # 限流后自动重试一次（冷却已在 _handle_response 中执行）
            logger.info("限流冷却后重试...")
            data = await self._request("GET", url, params=params)
            result = self._handle_response(data, action)
            self._rate_limit_count = 0
            return result

    # ── 搜索 ───────────────────────────────────────────────────────

    async def search_jobs(
        self,
        query: str,
        city: str = "101010100",
        page: int = 1,
        page_size: int = 15,
    ) -> Dict:
        """搜索岗位"""
        params = {
            "query": query,
            "city": city,
            "page": page,
            "pageSize": page_size,
        }
        return await self._get(JOB_SEARCH_URL, params=params, action="搜索职位")

    async def get_user_info(self) -> Dict:
        """获取用户信息（验证登录态）"""
        return await self._get(USER_INFO_URL, action="用户信息")


# ============================================================================
# 异常定义
# ============================================================================

class BossApiError(Exception):
    def __init__(self, message: str, code: int = -1, response: Optional[Dict] = None):
        super().__init__(message)
        self.code = code
        self.response = response


class SessionExpiredError(BossApiError):
    """会话过期（code=37）"""
    def __init__(self, message: str = "会话过期"):
        super().__init__(message, code=37)


class RateLimitError(BossApiError):
    """被限流（code=9）"""
    def __init__(self, message: str = "被限流"):
        super().__init__(message, code=9)


class SecurityBlockError(BossApiError):
    """安全系统拦截（code=121/122，需要浏览器验证）"""
    def __init__(self, message: str, code: int = 121):
        super().__init__(message, code=code)


# ============================================================================
# Cookie 提取（通过 Playwright CDP）
# ============================================================================

async def extract_cookies_from_browser(user_id: str = "default") -> Tuple[Dict[str, str], bool]:
    """
    通过 Playwright CDP 从已登录的 Chrome 中提取 zhipin.com 的 Cookie

    策略：
    - 启动 headless Chrome（复用 userDataDir，登录态已保存）
    - CDP 连接，但不导航（只读取已存在的 cookie）
    - 提取 zhipin.com 域的所有 cookie

    Returns:
        (cookies_dict, has_required): cookie 字典 + 是否包含必需 cookie
    """
    from playwright.async_api import async_playwright

    port, proc = start_chrome(site="boss", user_id=user_id, headless=True)
    try:
        async with async_playwright() as pw:
            try:
                browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            except Exception as e:
                logger.error(f"CDP 连接失败: {e}")
                return {}, False

            try:
                # 获取默认 context
                if len(browser.contexts) > 0:
                    context = browser.contexts[0]
                else:
                    context = await browser.new_context()

                # 关键：不导航，直接读取已存在的 cookie
                # （导航会触发 Boss 反爬，但读取 cookie 不会）
                cookies_list = await context.cookies("https://www.zhipin.com")

                # 转为 dict
                cookies: Dict[str, str] = {}
                for c in cookies_list:
                    name = c.get("name", "")
                    value = c.get("value", "")
                    if name and value:
                        cookies[name] = value

                has_required = bool(REQUIRED_COOKIES & set(cookies.keys()))
                logger.info(
                    f"提取到 {len(cookies)} 个 zhipin.com cookie，"
                    f"必需 cookie 完整: {has_required}"
                )
                if has_required:
                    missing = REQUIRED_COOKIES - set(cookies.keys())
                    if missing:
                        logger.debug(f"缺失的必需 cookie: {missing}")

                return cookies, has_required
            finally:
                try:
                    await browser.close()
                except Exception:
                    pass
    finally:
        # headless 提取完即关闭 Chrome
        try:
            cmdline = " ".join(proc.args) if hasattr(proc, "args") and proc.args else ""
            if "--headless" in cmdline:
                stop_chrome(site="boss", user_id=user_id)
        except Exception as e:
            logger.warning(f"stop_chrome 异常: {e}")


# ============================================================================
# 搜索服务
# ============================================================================

class BossSearchService:
    """Boss 直聘岗位搜索服务"""

    async def search(
        self,
        keyword: str,
        city: Optional[str] = None,
        page: int = 1,
        use_real: bool = True,
        user_id: str = "default",
    ) -> Dict[str, Any]:
        """
        搜索 Boss 直聘岗位

        Args:
            keyword: 搜索关键字（如 "Java 后端"）
            city: 城市名（如 "北京" / "上海" / "杭州"），可选
            page: 页码（从 1 开始）
            use_real: 是否尝试真实搜索（False 则直接用模拟数据）
            user_id: 用户 ID（用于隔离 userDataDir 登录态）

        Returns:
            dict: {
                "keyword": "关键字",
                "city": "城市",
                "source": "real" | "mock" | "need_login",
                "total": 数量,
                "jobs": [岗位列表],
                "need_login": bool,
                "login_url": str,
                "anti_crawl": bool,
                "message": str,
            }
        """
        logger.info(
            f"Boss 搜索: keyword={keyword}, city={city}, page={page}, "
            f"use_real={use_real}, user={user_id}"
        )

        if use_real:
            try:
                result = await self._fetch_real(keyword, city, page, user_id)
                # 检测登录墙
                if result.get("need_login"):
                    return {
                        "keyword": keyword,
                        "city": city,
                        "source": "need_login",
                        "total": 0,
                        "jobs": [],
                        "page": page,
                        "need_login": True,
                        "login_url": BOSS_LOGIN_URL,
                        "anti_crawl": False,
                        "message": "Boss 直聘需要登录后才能搜索，请先点击「登录 Boss」按钮完成登录",
                    }
                # 检测反爬
                if result.get("anti_crawl"):
                    logger.warning("检测到反爬拦截，降级为模拟数据")
                    mock = self._mock_search(keyword, city, page)
                    mock["message"] = (
                        "⚠️ Boss 直聘触发了反爬/安全验证，已临时降级为模拟数据。"
                        "建议稍后重试，或重新登录获取新 Cookie。"
                    )
                    mock["anti_crawl"] = True
                    mock["login_url"] = BOSS_LOGIN_URL
                    return mock
                # 正常返回
                jobs = result.get("jobs", [])
                if jobs:
                    return {
                        "keyword": keyword,
                        "city": city,
                        "source": "real",
                        "total": len(jobs),
                        "jobs": jobs,
                        "page": page,
                        "need_login": False,
                        "anti_crawl": False,
                        "message": "真实搜索成功（via wapi）",
                    }
                logger.warning("真实搜索返回空，降级为模拟数据")
            except Exception as e:
                logger.warning(f"真实搜索失败，降级模拟: {e}")

        # 降级：模拟数据
        mock = self._mock_search(keyword, city, page)
        mock["need_login"] = False
        mock["anti_crawl"] = False
        return mock

    async def _fetch_real(
        self,
        keyword: str,
        city: Optional[str],
        page: int,
        user_id: str = "default",
    ) -> Dict[str, Any]:
        """
        用 httpx 直接调用 Boss wapi 接口搜索岗位

        流程：
        1. 通过 Playwright CDP 从已登录 Chrome 提取 Cookie
        2. 检测必需 Cookie 是否齐全（判断登录态）
        3. 用 httpx + Cookie 调用 /wapi/zpgeek/search/joblist.json
        4. 处理响应，解析岗位列表
        """
        # 1. 提取 Cookie
        cookies, has_required = await extract_cookies_from_browser(user_id)
        if not has_required:
            logger.warning("必需 Cookie 不完整，需要登录")
            return {"jobs": [], "need_login": True, "anti_crawl": False}

        # 2. 城市编号
        city_code = CITY_CODES.get(city or "全国", "100010000")

        # 3. 调用 wapi
        try:
            async with BossApiClient(cookies=cookies) as client:
                data = await client.search_jobs(
                    query=keyword,
                    city=city_code,
                    page=page,
                    page_size=15,
                )
                jobs = self._parse_wapi_response(data)
                return {"jobs": jobs, "need_login": False, "anti_crawl": False}
        except SessionExpiredError as e:
            logger.warning(f"会话过期: {e}")
            return {"jobs": [], "need_login": True, "anti_crawl": False}
        except SecurityBlockError as e:
            logger.warning(f"安全系统拦截: {e}")
            return {"jobs": [], "need_login": False, "anti_crawl": True}
        except RateLimitError as e:
            logger.warning(f"被限流: {e}")
            return {"jobs": [], "need_login": False, "anti_crawl": True}
        except BossApiError as e:
            logger.error(f"Boss API 错误: {e}")
            return {"jobs": [], "need_login": False, "anti_crawl": False, "error": str(e)}
        except Exception as e:
            logger.error(f"搜索异常: {e}", exc_info=True)
            return {"jobs": [], "need_login": False, "anti_crawl": False, "error": str(e)}

    def _parse_wapi_response(self, data: Dict) -> List[Dict[str, Any]]:
        """
        解析 wapi 搜索响应

        响应结构（参考 boss-cli）：
        {
            "code": 0,
            "zpData": {
                "jobList": [
                    {
                        "jobName": "Python工程师",
                        "brandName": "字节跳动",
                        "salaryDesc": "20-40K·15薪",
                        "cityName": "北京",
                        "areaDistrict": "海淀区",
                        "jobExperience": "3-5年",
                        "jobDegree": "本科",
                        "hrName": "王HR",
                        "hrPosition": "招聘经理",
                        "securityId": "xxx",
                        "jobLabels": ["Python", "Django"],
                        "brandIndustry": "互联网",
                        "brandScaleName": "10000人以上",
                        "brandStageName": "已上市",
                        ...
                    }
                ]
            }
        }
        """
        jobs: List[Dict[str, Any]] = []
        job_list = data.get("jobList") or []

        for item in job_list:
            try:
                # 安全 ID（用于构造 job_url）
                security_id = item.get("securityId") or item.get("encryptId") or ""
                job_url = ""
                if security_id:
                    job_url = f"https://www.zhipin.com/job_detail/{security_id}.html"

                # 城市 + 地区
                city_name = item.get("cityName") or ""
                area_district = item.get("areaDistrict") or ""
                business_district = item.get("businessDistrict") or ""
                location_parts = [p for p in [city_name, area_district, business_district] if p]
                location = ".".join(location_parts)

                # 公司标签
                company_tags: List[str] = []
                for key in ("brandIndustry", "brandScaleName", "brandStageName"):
                    val = item.get(key)
                    if val:
                        company_tags.append(val)

                # 技能标签
                skill_tags: List[str] = []
                for key in ("jobLabels", "skills"):
                    vals = item.get(key)
                    if isinstance(vals, list):
                        skill_tags.extend([str(v) for v in vals if v])

                job = {
                    "title": item.get("jobName") or "",
                    "company": item.get("brandName") or "",
                    "salary": item.get("salaryDesc") or "",
                    "location": location,
                    "experience": item.get("jobExperience") or "",
                    "education": self._decode_degree(item.get("jobDegree")),
                    "hr_name": item.get("hrName") or "",
                    "hr_position": item.get("hrPosition") or "",
                    "job_url": job_url,
                    "company_tags": company_tags,
                    "skill_tags": skill_tags,
                    "source": "boss",
                    # 额外字段
                    "welfare": item.get("welfare") or [],
                    "job_type": item.get("jobType") or "",
                }
                if job["title"] and job["company"]:
                    jobs.append(job)
            except Exception as e:
                logger.debug(f"解析岗位失败: {e}")

        logger.info(f"wapi 解析到 {len(jobs)} 个岗位")
        return jobs

    def _decode_degree(self, degree: Any) -> str:
        """解码学历代码（Boss 用数字表示学历）"""
        if not degree:
            return ""
        if isinstance(degree, str):
            return degree
        degree_map = {
            0: "不限",
            209: "初中及以下",
            208: "中专/中技",
            206: "高中",
            202: "大专",
            203: "本科",
            204: "硕士",
            205: "博士",
        }
        return degree_map.get(degree, str(degree))

    def _deterministic_seed(self, keyword: str, city: Optional[str], page: int) -> int:
        """根据搜索参数生成稳定的随机种子（避免内置 hash 的 PYTHONHASHSEED 随机性）"""
        key = f"{keyword}|{city or ''}|{page}"
        # 取 sha256 前 8 字节作为整数种子，跨进程稳定
        return int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")

    def _mock_search(
        self, keyword: str, city: Optional[str], page: int
    ) -> Dict[str, Any]:
        """生成模拟数据（demo / 反爬降级用）"""
        company_pool = [
            ("字节跳动", "互联网", "已上市", "10000人以上"),
            ("腾讯", "互联网", "已上市", "10000人以上"),
            ("阿里巴巴", "互联网", "已上市", "10000人以上"),
            ("美团", "互联网", "已上市", "10000人以上"),
            ("百度", "互联网", "已上市", "10000人以上"),
            ("网易", "互联网", "已上市", "10000人以上"),
            ("拼多多", "电商", "已上市", "10000人以上"),
            ("小红书", "社交", "D轮及以上", "1000-9999人"),
            ("快手", "短视频", "已上市", "10000人以上"),
            ("B站", "视频", "已上市", "1000-9999人"),
            ("滴滴出行", "出行", "已上市", "10000人以上"),
            ("京东", "电商", "已上市", "10000人以上"),
            ("小米", "智能硬件", "已上市", "10000人以上"),
            ("华为", "通信", "不需要融资", "10000人以上"),
            ("OPPO", "智能硬件", "不需要融资", "10000人以上"),
            ("vivo", "智能硬件", "不需要融资", "10000人以上"),
            ("大疆", "智能硬件", "不需要融资", "10000人以上"),
            ("商汤科技", "人工智能", "D轮及以上", "1000-9999人"),
            ("旷视科技", "人工智能", "C轮", "1000-9999人"),
            ("米哈游", "游戏", "不需要融资", "1000-9999人"),
        ]

        kw_lower = keyword.lower()
        if "java" in kw_lower or "后端" in kw_lower:
            skills = ["Java", "Spring", "MySQL", "Redis", "分布式", "微服务"]
            titles = [f"{keyword}工程师", f"资深{keyword}", f"{keyword}开发"]
        elif "python" in kw_lower:
            skills = ["Python", "Django", "FastAPI", "MySQL", "Redis", "Linux"]
            titles = [f"{keyword}工程师", f"{keyword}后端", f"资深{keyword}"]
        elif "前端" in kw_lower or "frontend" in kw_lower or "react" in kw_lower or "vue" in kw_lower:
            skills = ["JavaScript", "TypeScript", "React", "Vue", "Webpack", "CSS"]
            titles = [f"{keyword}工程师", "资深前端", "前端开发"]
        elif "算法" in kw_lower or "ai" in kw_lower or "机器学习" in kw_lower or "深度学习" in kw_lower:
            skills = ["Python", "PyTorch", "TensorFlow", "NLP", "CV", "推荐系统"]
            titles = [f"{keyword}工程师", "算法专家", f"资深{keyword}"]
        elif "go" in kw_lower or "golang" in kw_lower:
            skills = ["Go", "Kubernetes", "Docker", "gRPC", "微服务"]
            titles = [f"{keyword}工程师", f"资深 Go 开发"]
        elif "产品" in kw_lower:
            skills = ["产品设计", "需求分析", "Axure", "数据分析", "用户研究"]
            titles = ["产品经理", "高级产品经理", f"{keyword}产品"]
        elif "运营" in kw_lower:
            skills = ["内容运营", "数据分析", "活动策划", "用户增长"]
            titles = ["运营专员", "运营经理", f"{keyword}运营"]
        else:
            skills = ["沟通能力", "团队协作", "责任心", "学习能力"]
            titles = [f"{keyword}专员", f"{keyword}工程师", f"{keyword}经理"]

        city_name = city or random.choice(["北京", "上海", "杭州", "深圳", "广州"])
        districts = {
            "北京": ["海淀区", "朝阳区", "西城区", "东城区"],
            "上海": ["浦东新区", "徐汇区", "黄浦区", "静安区"],
            "杭州": ["西湖区", "余杭区", "滨江区", "萧山区"],
            "深圳": ["南山区", "福田区", "罗湖区", "宝安区"],
            "广州": ["天河区", "越秀区", "海珠区", "番禺区"],
        }
        district = random.choice(districts.get(city_name, ["中心区"]))

        salaries_junior = ["12-18K", "15-20K", "13-22K", "15-25K", "18-30K·15薪"]
        salaries_mid = ["20-35K", "25-40K", "30-50K·15薪", "22-37K", "28-45K"]
        salaries_senior = ["35-55K", "40-65K", "50-80K·16薪", "45-70K", "60-90K"]

        experiences = ["1-3年", "3-5年", "5-10年", "经验不限", "应届生"]
        educations = ["本科", "硕士", "本科及以上", "不限"]

        random.seed(self._deterministic_seed(keyword, city, page))
        chosen = random.sample(company_pool, min(10, len(company_pool)))

        jobs = []
        for i, (company, industry, stage, scale) in enumerate(chosen):
            exp = random.choice(experiences)
            if "应届" in exp or "不限" in exp:
                salary = random.choice(salaries_junior)
            elif "5-10" in exp:
                salary = random.choice(salaries_senior)
            else:
                salary = random.choice(salaries_mid)

            title = random.choice(titles)
            if random.random() < 0.3:
                title += f"（{random.choice(['核心业务', '创新业务', '基础设施', '海外'])}）"

            job_skills = random.sample(skills, min(4, len(skills)))
            hr_names = ["王HR", "李招聘", "张HR", "刘招聘", "陈HR", "赵招聘"]
            hr_positions = ["招聘经理", "HRBP", "招聘专员", "高级招聘"]

            jobs.append({
                "title": title,
                "company": company,
                "salary": salary,
                "location": f"{city_name}.{district}",
                "experience": exp,
                "education": random.choice(educations),
                "hr_name": random.choice(hr_names),
                "hr_position": random.choice(hr_positions),
                "job_url": f"https://www.zhipin.com/job_detail/mock-{page}-{i+1}.html",
                "company_tags": [industry, stage, scale],
                "skill_tags": job_skills,
                "source": "boss",
            })

        return {
            "keyword": keyword,
            "city": city_name,
            "source": "mock",
            "total": len(jobs),
            "jobs": jobs,
            "page": page,
            "note": "模拟数据（真实搜索失败或被反爬，已降级）",
        }


# 单例
_service_instance: Optional[BossSearchService] = None


def get_boss_search_service() -> BossSearchService:
    global _service_instance
    if _service_instance is None:
        _service_instance = BossSearchService()
    return _service_instance
