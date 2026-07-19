"""
表单字段提取器
自动识别页面表单字段，支持多种表单控件
"""

from playwright.async_api import Page, ElementHandle
import json
import re
import logging

logger = logging.getLogger("offerclaw.form_extractor")


class FormExtractor:
    """表单字段提取器"""

    async def extract_fields(self, page: Page) -> list:
        """
        提取页面表单字段

        Args:
            page: Playwright 页面对象

        Returns:
            list: 字段列表 [{id, label, type, required, options, selector}]
        """
        fields = []

        logger.info("开始提取表单字段...")

        # 策略1：原生表单元素（input/select/textarea）
        inputs = await page.query_selector_all(
            'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="reset"])'
        )
        selects = await page.query_selector_all('select')
        textareas = await page.query_selector_all('textarea')

        # 处理 input 元素
        for idx, element in enumerate(inputs):
            field = await self._extract_input_field(element, idx, page)
            if field:
                fields.append(field)

        # 处理 select 元素
        for idx, element in enumerate(selects):
            field = await self._extract_select_field(element, idx, page)
            if field:
                fields.append(field)

        # 处理 textarea 元素
        for idx, element in enumerate(textareas):
            field = await self._extract_textarea_field(element, idx, page)
            if field:
                fields.append(field)

        logger.info(f"提取到 {len(fields)} 个表单字段")

        # 策略2：无障碍树补充（如果有遗漏）
        try:
            accessibility = await page.accessibility.snapshot()
            accessibility_fields = self._extract_from_accessibility(accessibility)

            # 合并无障碍树提取的字段（去重）
            for acc_field in accessibility_fields:
                if not any(f['id'] == acc_field['id'] for f in fields):
                    fields.append(acc_field)
                    logger.info(f"  [无障碍树] 添加字段: {acc_field['label']}")
        except Exception as e:
            logger.warning(f"无障碍树提取失败: {e}")

        return fields

    async def _extract_input_field(self, element: ElementHandle, idx: int, page: Page) -> dict:
        """提取 input 字段信息"""
        try:
            element_id = await element.get_attribute('id')
            element_name = await element.get_attribute('name')
            field_id = element_id or element_name or f'input_{idx}'

            label = await self._get_label(element, page)
            input_type = await element.get_attribute('type') or 'text'
            required = await element.get_attribute('required') is not None

            # 构建选择器
            if element_id:
                selector = f'#{element_id}'
            elif element_name:
                selector = f'input[name="{element_name}"]'
            else:
                selector = f'input:nth-of-type({idx+1})'

            field = {
                'id': field_id,
                'label': label,
                'type': input_type,
                'required': required,
                'tag': 'input',
                'selector': selector,
            }

            logger.debug(f"  [{idx+1}] input: {label} ({input_type}) - {field_id}")

            return field

        except Exception as e:
            logger.error(f"提取 input 字段失败: {e}")
            return None

    async def _extract_select_field(self, element: ElementHandle, idx: int, page: Page) -> dict:
        """提取 select 字段信息"""
        try:
            element_id = await element.get_attribute('id')
            element_name = await element.get_attribute('name')
            field_id = element_id or element_name or f'select_{idx}'

            label = await self._get_label(element, page)
            required = await element.get_attribute('required') is not None

            # 提取选项
            options = await element.query_selector_all('option')
            option_texts = []
            for opt in options:
                text = await opt.inner_text()
                value = await opt.get_attribute('value')
                option_texts.append({
                    'text': text.strip(),
                    'value': value or text.strip()
                })

            # 构建选择器
            if element_id:
                selector = f'#{element_id}'
            elif element_name:
                selector = f'select[name="{element_name}"]'
            else:
                selector = f'select:nth-of-type({idx+1})'

            field = {
                'id': field_id,
                'label': label,
                'type': 'select',
                'required': required,
                'tag': 'select',
                'options': option_texts,
                'selector': selector,
            }

            logger.debug(f"  [{idx+1}] select: {label} ({len(option_texts)}个选项) - {field_id}")

            return field

        except Exception as e:
            logger.error(f"提取 select 字段失败: {e}")
            return None

    async def _extract_textarea_field(self, element: ElementHandle, idx: int, page: Page) -> dict:
        """提取 textarea 字段信息"""
        try:
            element_id = await element.get_attribute('id')
            element_name = await element.get_attribute('name')
            field_id = element_id or element_name or f'textarea_{idx}'

            label = await self._get_label(element, page)
            required = await element.get_attribute('required') is not None

            # 构建选择器
            if element_id:
                selector = f'#{element_id}'
            elif element_name:
                selector = f'textarea[name="{element_name}"]'
            else:
                selector = f'textarea:nth-of-type({idx+1})'

            field = {
                'id': field_id,
                'label': label,
                'type': 'textarea',
                'required': required,
                'tag': 'textarea',
                'selector': selector,
            }

            logger.debug(f"  [{idx+1}] textarea: {label} - {field_id}")

            return field

        except Exception as e:
            logger.error(f"提取 textarea 字段失败: {e}")
            return None

    async def _get_label(self, element: ElementHandle, page: Page) -> str:
        """获取字段标签（多策略）"""
        # 策略1：aria-label 属性
        aria_label = await element.get_attribute('aria-label')
        if aria_label:
            return aria_label.strip()

        # 策略2：<label for="id">
        element_id = await element.get_attribute('id')
        if element_id:
            try:
                label_element = await page.query_selector(f'label[for="{element_id}"]')
                if label_element:
                    label_text = await label_element.inner_text()
                    return label_text.strip()
            except:
                pass

        # 策略3：placeholder 属性
        placeholder = await element.get_attribute('placeholder')
        if placeholder:
            return placeholder.strip()

        # 策略4：name 属性（驼峰转可读）
        name = await element.get_attribute('name')
        if name:
            return self._name_to_readable(name)

        # 策略5：相邻 label 元素
        try:
            parent = await element.evaluate_handle('el => el.parentElement')
            label_element = await parent.query_selector('label')
            if label_element:
                label_text = await label_element.inner_text()
                return label_text.strip()
        except:
            pass

        return ''

    def _name_to_readable(self, name: str) -> str:
        """将 name 属性转换为可读文本"""
        # 常见字段名映射
        common_mappings = {
            'name': '姓名',
            'username': '用户名',
            'email': '邮箱',
            'phone': '手机号',
            'mobile': '手机号',
            'password': '密码',
            'gender': '性别',
            'age': '年龄',
            'birthday': '生日',
            'address': '地址',
            'city': '城市',
            'province': '省份',
            'school': '学校',
            'education': '学历',
            'major': '专业',
            'company': '公司',
            'title': '职位',
            'salary': '薪资',
            'resume': '简历',
            'file': '文件',
            'idcard': '身份证号',
            'identity': '身份证号',
        }

        name_lower = name.lower().replace('_', '').replace('-', '')

        if name_lower in common_mappings:
            return common_mappings[name_lower]

        # 驼峰转下划线
        readable = re.sub(r'([a-z])([A-Z])', r'\1 \2', name).lower()

        return readable

    def _extract_from_accessibility(self, accessibility_tree: dict) -> list:
        """从无障碍树提取字段（补充策略）"""
        fields = []

        def traverse(node, depth=0):
            if node.get('role') in ['textbox', 'combobox', 'checkbox', 'radio', 'edit']:
                field = {
                    'id': node.get('name') or f'acc_{len(fields)}',
                    'label': node.get('name', ''),
                    'type': node.get('role'),
                    'required': False,
                    'tag': 'accessibility',
                }
                fields.append(field)

            for child in node.get('children', []):
                traverse(child, depth+1)

        traverse(accessibility_tree)
        return fields