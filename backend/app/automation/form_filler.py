"""
表单填写执行器
根据匹配结果自动填写表单
"""

from playwright.async_api import Page, ElementHandle
import json
import logging

logger = logging.getLogger("offerclaw.form_filler")


class FormFiller:
    """表单填写执行器"""

    async def fill(self, page: Page, fields: list, mappings: list, sensitive_data: dict = None):
        """
        执行表单填写

        Args:
            page: Playwright 页面对象
            fields: 表单字段列表
            mappings: LLM 匹配结果列表
            sensitive_data: 敏感数据（身份证号、家庭住址等）
        """
        logger.info(f"开始填写表单，共 {len(fields)} 个字段")

        filled_count = 0

        for mapping in mappings:
            # 查找对应字段
            field = next((f for f in fields if f['id'] == mapping['field_id']), None)
            if not field:
                logger.warning(f"  ⚠️  字段不存在: {mapping['field_id']}")
                continue

            # 获取填写值
            value = mapping.get('value')

            if not value:
                # 敏感字段从本地读取
                if mapping.get('source') == 'local_sensitive':
                    sensitive_key = self._infer_sensitive_key(field['label'])
                    value = sensitive_data.get(sensitive_key) if sensitive_data else None

                    if not value:
                        logger.warning(f"  ⚠️  敏感字段未提供数据: {field['label']}")
                        continue

                    logger.info(f"  📝 [敏感] {field['label']}: {value[:3]}***（本地数据）")

                else:
                    logger.warning(f"  ⚠️  无法匹配: {field['label']}")
                    continue

            else:
                logger.info(f"  📝 {field['label']}: {value}")

            # 执行填写
            try:
                await self._fill_field(page, field, value)
                filled_count += 1
                logger.info(f"  ✅ 填写成功: {field['label']}")
            except Exception as e:
                logger.error(f"  ❌ 填写失败: {field['label']} - {e}")

        logger.info(f"表单填写完成，成功填写 {filled_count}/{len(fields)} 个字段")

    async def _fill_field(self, page: Page, field: dict, value: str):
        """填写单个字段"""

        selector = field['selector']
        field_type = field['type']

        # 根据字段类型执行填写
        if field_type in ['text', 'email', 'tel', 'number', 'password', 'url']:
            await self._fill_text(page, selector, value)

        elif field_type == 'select':
            await self._fill_select(page, selector, value, field.get('options', []))

        elif field_type == 'textarea':
            await self._fill_text(page, selector, value)

        elif field_type == 'checkbox':
            await self._fill_checkbox(page, selector, value)

        elif field_type == 'radio':
            await self._fill_radio(page, selector, value)

        elif field_type == 'file':
            await self._fill_file(page, selector, value)

        else:
            await self._fill_text(page, selector, value)

    async def _fill_text(self, page: Page, selector: str, value: str):
        """填写文本输入框（兼容 React/Vue）"""

        # 策略1：Playwright 原生 fill 方法
        try:
            await page.fill(selector, value)
            return
        except Exception as e:
            logger.debug(f"    fill 失败，尝试 evaluate 方法: {e}")

        # 策略2：手动触发原生事件（React/Vue 兼容）
        try:
            await page.evaluate("""
                (args) => {
                    const selector = args[0];
                    const value = args[1];

                    const element = document.querySelector(selector);
                    if (!element) return;

                    // React/Vue 需要使用原生 setter
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    ).set;

                    if (nativeInputValueSetter) {
                        nativeInputValueSetter.call(element, value);
                    } else {
                        element.value = value;
                    }

                    // 触发事件
                    element.dispatchEvent(new Event('input', { bubbles: true }));
                    element.dispatchEvent(new Event('change', { bubbles: true }));
                    element.dispatchEvent(new Event('blur', { bubbles: true }));
                }
            """, [selector, value])
        except Exception as e:
            logger.error(f"    evaluate 失败: {e}")
            raise

    async def _fill_select(self, page: Page, selector: str, value: str, options: list):
        """填写下拉选择框"""

        matched_option = None

        # 策略1：精确匹配 value
        for option in options:
            if option['value'] == value:
                matched_option = option
                break

        # 策略2：匹配显示文本
        if not matched_option:
            for option in options:
                if option['text'] == value or value in option['text']:
                    matched_option = option
                    break

        if matched_option:
            await page.select_option(selector, matched_option['value'])
            logger.info(f"    选择选项: {matched_option['text']}")
        else:
            logger.warning(f"    ⚠️  未找到匹配选项: {value}")
            await page.select_option(selector, value)

    async def _fill_checkbox(self, page: Page, selector: str, value: str):
        """填写复选框"""

        should_check = value in ['true', 'yes', '1', 'checked', '√']

        if should_check:
            await page.check(selector)
        else:
            await page.uncheck(selector)

    async def _fill_radio(self, page: Page, selector: str, value: str):
        """填写单选框"""

        await page.check(selector)

    async def _fill_file(self, page: Page, selector: str, value: str):
        """填写文件上传"""

        if value.startswith('FILE:'):
            file_path = value.replace('FILE:', '')
            await page.set_input_files(selector, file_path)
        else:
            logger.warning(f"    ⚠️  文件上传需要 FILE:路径 格式")

    def _infer_sensitive_key(self, label: str) -> str:
        """推断敏感字段 key"""

        if '身份证' in label or '证件号' in label or 'identity' in label.lower():
            return 'id_number'

        if '住址' in label or '地址' in label or 'address' in label.lower():
            return 'home_address'

        return ''