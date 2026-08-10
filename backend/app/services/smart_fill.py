"""
智能填写服务 - Web 版本（无需插件）

用户输入 URL，系统自动抓取页面并识别表单。

提取逻辑已统一迁移到 app.automation.form_extractor.FormExtractor，
本模块只做「URL → Page → 调 FormExtractor」的编排。

支持多步骤向导表单：
- extract_fields_from_url: 单页提取（含向导结构检测）
- extract_all_steps: 自动点击「下一步」遍历所有步骤，合并字段
"""

import asyncio
import logging
from typing import Dict, Any, List

from playwright.async_api import async_playwright

from app.automation.form_extractor import FormExtractor

logger = logging.getLogger("offerclaw.smart_fill")


class SmartFillService:
    """智能填写服务（Web 版本）"""

    def __init__(self):
        self._extractor = FormExtractor()

    async def extract_fields_from_url(self, url: str) -> Dict[str, Any]:
        """
        从 URL 提取表单字段（单页提取，含多步骤向导检测）

        Args:
            url: 目标网页 URL

        Returns:
            dict: {
                "url": "原始URL",
                "title": "页面标题",
                "fields": [字段列表]，每个字段含 selectors 多重备选数组,
                "field_count": int,
                "screenshot": str,  # base64 jpeg
                "wizard": {  # 多步骤向导信息（即使不是多步骤也会返回此字段）
                    "is_multi_step": bool,
                    "current_step": int,
                    "total_steps": int,
                    "step_titles": List[str],
                    "next_button_selector": Optional[str],
                    "submit_button_selector": Optional[str],
                }
            }
        """
        logger.info(f"开始抓取页面: {url}")

        try:
            async with async_playwright() as p:
                # 启动浏览器（无头模式）
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                # SPA 页面用 domcontentloaded + 等待，避免 networkidle 超时
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    logger.warning(f"domcontentloaded 加载超时，重试 load: {e}")
                    try:
                        await page.goto(url, wait_until="load", timeout=30000)
                    except Exception as e2:
                        logger.warning(f"load 也超时，继续尝试: {e2}")
                        await page.goto(url, timeout=30000)

                # 等待 SPA 渲染完成
                await asyncio.sleep(2.0)

                # 获取页面标题
                title = await page.title()
                logger.info(f"页面标题: {title}")

                # 提取表单字段（统一调用 FormExtractor）
                fields = await self._extractor.extract_fields(page)

                # 检测多步骤向导结构
                wizard = await self._extractor.detect_wizard_steps(page)
                if wizard.get("is_multi_step"):
                    logger.info(
                        f"检测到多步骤向导: 当前第 {wizard.get('current_step', 0)} / "
                        f"{wizard.get('total_steps', 0)} 步, "
                        f"标题={wizard.get('step_titles', [])[:3]}"
                    )

                # 截图（用于预览）
                screenshot = await page.screenshot(type="jpeg", quality=50)
                screenshot_base64 = screenshot.hex() if screenshot else None

                await browser.close()

                return {
                    "url": url,
                    "title": title,
                    "fields": fields,
                    "field_count": len(fields),
                    "screenshot": screenshot_base64,
                    "wizard": wizard,
                }

        except Exception as e:
            logger.error(f"页面抓取失败: {e}", exc_info=True)
            raise Exception(f"页面抓取失败: {e}")

    async def extract_all_steps(
        self, url: str, max_steps: int = 10
    ) -> Dict[str, Any]:
        """
        自动遍历多步骤向导的所有步骤，合并字段

        流程：
        1. 打开页面，提取当前步骤字段
        2. 检测到「下一步」按钮则点击，等待新字段渲染
        3. 重复直到无「下一步」或达到 max_steps 上限
        4. 合并所有步骤的字段（按 id 去重，保留首次出现）

        Args:
            url: 目标网页 URL
            max_steps: 最大遍历步数（防止无限循环）

        Returns:
            dict: {
                "url": str,
                "title": str,
                "fields": List[Dict],  # 所有步骤合并后的字段
                "field_count": int,
                "steps": List[Dict],   # 每步的信息：{step, title, field_count, screenshot}
                "total_steps_traversed": int,
                "screenshot": str,  # 最后一步截图
            }
        """
        logger.info(f"开始多步骤向导提取: {url}, max_steps={max_steps}")

        all_fields: List[Dict[str, Any]] = []
        seen_ids = set()
        steps_info: List[Dict[str, Any]] = []
        step_count = 0

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                try:
                    # 加载页面
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    except Exception:
                        try:
                            await page.goto(url, wait_until="load", timeout=30000)
                        except Exception:
                            await page.goto(url, timeout=30000)
                    await asyncio.sleep(2.0)

                    title = await page.title()

                    while step_count < max_steps:
                        step_count += 1
                        await asyncio.sleep(1.0)  # 等待步骤渲染

                        # 提取当前步骤字段
                        fields = await self._extractor.extract_fields(page)
                        wizard = await self._extractor.detect_wizard_steps(page)

                        # 合并字段（去重）
                        new_count = 0
                        for f in fields:
                            fid = f.get("id") or f.get("label") or ""
                            if fid and fid not in seen_ids:
                                seen_ids.add(fid)
                                f["step"] = step_count  # 标记来源步骤
                                all_fields.append(f)
                                new_count += 1

                        # 截图当前步骤
                        shot = await page.screenshot(type="jpeg", quality=40)
                        steps_info.append({
                            "step": step_count,
                            "title": (wizard.get("step_titles") or [None])[0] if wizard.get("step_titles") else f"步骤 {step_count}",
                            "field_count": len(fields),
                            "new_field_count": new_count,
                            "screenshot": shot.hex() if shot else None,
                        })

                        logger.info(
                            f"步骤 {step_count}: 提取 {len(fields)} 字段（新增 {new_count}），"
                            f"标题={steps_info[-1]['title']}"
                        )

                        # 寻找并点击「下一步」按钮
                        next_selector = wizard.get("next_button_selector")
                        if not next_selector:
                            logger.info(f"步骤 {step_count} 无「下一步」按钮，遍历结束")
                            break

                        try:
                            # 优先用 text= 选择器（更鲁棒）
                            if next_selector.startswith("text="):
                                btn_text = next_selector[5:]
                                btn = page.locator(f"button:has-text('{btn_text}'), [role='button']:has-text('{btn_text}')").first
                            else:
                                btn = page.locator(next_selector).first

                            if await btn.count() == 0:
                                logger.info(f"步骤 {step_count} 「下一步」按钮未找到，遍历结束")
                                break

                            await btn.click()
                            logger.info(f"已点击「下一步」（步骤 {step_count} → {step_count + 1}）")
                            # 等待新步骤渲染
                            await asyncio.sleep(2.0)

                        except Exception as e:
                            logger.warning(f"点击「下一步」失败: {e}")
                            break

                    # 最终截图
                    final_shot = await page.screenshot(type="jpeg", quality=50)

                    return {
                        "url": url,
                        "title": title,
                        "fields": all_fields,
                        "field_count": len(all_fields),
                        "steps": steps_info,
                        "total_steps_traversed": step_count,
                        "screenshot": final_shot.hex() if final_shot else None,
                    }
                finally:
                    await browser.close()

        except Exception as e:
            logger.error(f"多步骤向导提取失败: {e}", exc_info=True)
            raise Exception(f"多步骤向导提取失败: {e}")


# Dependency injection
def get_smart_fill_service():
    return SmartFillService()
