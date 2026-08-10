"""
Boss 直聘 HTML 公开页解析降级方案

当 wapi 接口被风控（code=36/121/122）或用户未登录时，
通过 Playwright 抓取 https://www.zhipin.com/web/geek/job?query=xxx 公开搜索页，
解析其中的岗位卡片，无需登录态即可获取 30 条岗位。

降级链：
    wapi 真实搜索 → HTML 公开页解析 → mock 数据
"""

import asyncio
import logging
import urllib.parse
from typing import Dict, Any, List, Optional

from playwright.async_api import async_playwright

from app.services.playwright_runtime import start_chrome, stop_chrome, human_delay

logger = logging.getLogger("offerclaw.boss_html")

# 公开搜索页 URL（无需登录即可访问，Boss 为 SEO 暴露此页面）
PUBLIC_SEARCH_URL = "https://www.zhipin.com/web/geek/job"


async def fetch_jobs_via_html(
    keyword: str,
    city_code: str = "100010000",
    page: int = 1,
    user_id: str = "default",
    timeout_ms: int = 30000,
) -> Dict[str, Any]:
    """
    通过 Playwright 抓取 Boss 公开搜索页 HTML，解析岗位卡片

    Args:
        keyword: 搜索关键字
        city_code: 城市编码
        page: 页码
        user_id: 用户 ID（隔离 userDataDir，复用已建立的反爬指纹）
        timeout_ms: 页面加载超时（毫秒）

    Returns:
        dict: {
            "jobs": [岗位列表],
            "source": "html",
            "total": int,
            "need_login": bool,
            "anti_crawl": bool,
            "error": Optional[str],
        }
    """
    params = {"query": keyword, "city": city_code, "page": page}
    url = f"{PUBLIC_SEARCH_URL}?{urllib.parse.urlencode(params)}"
    logger.info(f"HTML 降级抓取: {url}")

    # 复用 boss 站点的 userDataDir（共享 Cookie 与指纹，减少反爬触发）
    port, proc = start_chrome(site="boss", user_id=user_id, headless=True)
    try:
        async with async_playwright() as pw:
            try:
                browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            except Exception as e:
                logger.error(f"HTML 降级：CDP 连接失败: {e}")
                return {"jobs": [], "source": "html", "total": 0,
                        "need_login": False, "anti_crawl": False, "error": f"CDP 连接失败: {e}"}

            try:
                if len(browser.contexts) > 0:
                    context = browser.contexts[0]
                else:
                    context = await browser.new_context()

                page_obj = await context.new_page()
                try:
                    # 导航到公开搜索页（此页面 Boss 允许未登录访问）
                    try:
                        await page_obj.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    except Exception:
                        try:
                            await page_obj.goto(url, wait_until="load", timeout=timeout_ms)
                        except Exception as e:
                            logger.warning(f"HTML 降级：页面加载失败: {e}")
                            return {"jobs": [], "source": "html", "total": 0,
                                    "need_login": False, "anti_crawl": False, "error": f"页面加载失败: {e}"}

                    # 等待岗位列表渲染（Boss 是 SPA，需要等 JS 执行完）
                    await human_delay(2.0, 3.5)

                    # 检测是否被重定向到登录页
                    current_url = page_obj.url
                    if "/user" in current_url or "login" in current_url.lower():
                        logger.warning("HTML 降级：被重定向到登录页")
                        return {"jobs": [], "source": "html", "total": 0,
                                "need_login": True, "anti_crawl": False, "error": None}

                    # 检测是否触发安全验证
                    page_text = await page_obj.evaluate("() => document.body.innerText || ''")
                    if any(kw in page_text for kw in ["安全验证", "滑动验证", "验证码", "blocked"]):
                        logger.warning("HTML 降级：触发安全验证")
                        return {"jobs": [], "source": "html", "total": 0,
                                "need_login": False, "anti_crawl": True, "error": None}

                    # 滚动触发懒加载
                    for _ in range(3):
                        await page_obj.evaluate("window.scrollBy(0, 800)")
                        await human_delay(0.5, 1.0)

                    # 解析岗位卡片
                    jobs = await _parse_job_cards(page_obj)
                    logger.info(f"HTML 降级：解析到 {len(jobs)} 个岗位")
                    return {
                        "jobs": jobs,
                        "source": "html",
                        "total": len(jobs),
                        "need_login": False,
                        "anti_crawl": False,
                        "error": None,
                    }
                finally:
                    try:
                        await page_obj.close()
                    except Exception:
                        pass
            finally:
                try:
                    await browser.close()
                except Exception:
                    pass
    finally:
        # headless 模式抓完即关
        try:
            cmdline = " ".join(proc.args) if hasattr(proc, "args") and proc.args else ""
            if "--headless" in cmdline:
                stop_chrome(site="boss", user_id=user_id)
        except Exception as e:
            logger.warning(f"stop_chrome 异常: {e}")


async def _parse_job_cards(page) -> List[Dict[str, Any]]:
    """
    从已加载的搜索页解析岗位卡片

    Boss 搜索页 DOM 结构（多种卡片选择器兼容）：
    - .job-card-wrapper（新版）
    - .job-list li（旧版）
    - li[ka="search_list_x"]
    """
    # 用 JS 一次性提取所有卡片信息，减少 Python ↔ JS 来回开销
    js = """
    () => {
        const cards = [];
        // 多选择器兼容
        const selectors = '.job-card-wrapper, .job-list li, li[ka^="search_list_"], .search-job-result li';
        const elements = document.querySelectorAll(selectors);
        elements.forEach((el, idx) => {
            try {
                // 标题
                const titleEl = el.querySelector('.job-name, .job-title, .card-title a, h3 a');
                const title = titleEl ? titleEl.textContent.trim() : '';

                // 公司名称
                const companyEl = el.querySelector('.company-name a, .company-name, .card-company a, .company-info a');
                const company = companyEl ? companyEl.textContent.trim() : '';

                // 薪资
                const salaryEl = el.querySelector('.salary, .job-salary, .red');
                const salary = salaryEl ? salaryEl.textContent.trim() : '';

                // 地区
                const areaEl = el.querySelector('.job-area, .job-area-wrapper, .area-list');
                const area = areaEl ? areaEl.textContent.trim() : '';

                // 经验/学历（通常在 .job-info 或 .tag-list 里）
                const infoEl = el.querySelector('.job-info, .tag-list, .card-desc');
                const infoText = infoEl ? infoText.textContent.trim() : '';

                // HR 信息
                const hrEl = el.querySelector('.hr-name, .boss-name, .boss-info');
                const hrName = hrEl ? hrEl.textContent.trim() : '';

                const hrPosEl = el.querySelector('.hr-position, .boss-title');
                const hrPosition = hrPosEl ? hrPosEl.textContent.trim() : '';

                // 链接
                const linkEl = el.querySelector('a[href*="/job_detail/"], a[jobid]');
                let jobUrl = '';
                if (linkEl) {
                    const href = linkEl.getAttribute('href') || '';
                    jobUrl = href.startsWith('http') ? href : 'https://www.zhipin.com' + href;
                }

                // 公司标签（行业 / 规模 / 融资阶段）
                const companyTags = [];
                const tagEls = el.querySelectorAll('.company-tag-list li, .company-text li, .info-desc');
                tagEls.forEach(t => {
                    const txt = t.textContent.trim();
                    if (txt) companyTags.push(txt);
                });

                // 技能标签
                const skillTags = [];
                const skillEls = el.querySelectorAll('.tag-list .tag-item, .job-tags .tag');
                skillEls.forEach(t => {
                    const txt = t.textContent.trim();
                    if (txt) skillTags.push(txt);
                });

                if (title && company) {
                    cards.push({
                        title, company, salary, location: area,
                        experience: '', education: '',
                        hr_name: hrName, hr_position: hrPosition,
                        job_url: jobUrl,
                        company_tags: companyTags,
                        skill_tags: skillTags,
                        source: 'boss_html',
                    });
                }
            } catch (e) {
                // 跳过解析失败的卡片
            }
        });
        return cards;
    }
    """
    try:
        result = await page.evaluate(js)
        return result if isinstance(result, list) else []
    except Exception as e:
        logger.warning(f"HTML 降级：解析岗位卡片失败: {e}")
        return []
