"""
智能填写服务 - Web 版本（无需插件）
用户输入 URL，系统自动抓取页面并识别表单
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright, Page
import json

logger = logging.getLogger("offerclaw.smart_fill")


class SmartFillService:
    """智能填写服务（Web 版本）"""
    
    async def extract_fields_from_url(self, url: str) -> Dict[str, Any]:
        """
        从 URL 提取表单字段
        
        Args:
            url: 目标网页 URL
            
        Returns:
            dict: {
                "url": "原始URL",
                "title": "页面标题",
                "fields": [字段列表],
                "html_preview": "HTML预览（可选）"
            }
        """
        logger.info(f"开始抓取页面: {url}")
        
        try:
            async with async_playwright() as p:
                # 启动浏览器（无头模式）
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                # 访问页面
                try:
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                except Exception as e:
                    logger.warning(f"页面加载超时，继续尝试: {e}")
                    await page.goto(url, timeout=30000)
                
                # 获取页面标题
                title = await page.title()
                logger.info(f"页面标题: {title}")
                
                # 提取表单字段
                fields = await self._extract_form_fields(page)
                
                # 截图（用于预览）
                screenshot = await page.screenshot(type="jpeg", quality=50)
                screenshot_base64 = screenshot.hex() if screenshot else None
                
                await browser.close()
                
                return {
                    "url": url,
                    "title": title,
                    "fields": fields,
                    "field_count": len(fields),
                    "screenshot": screenshot_base64  # 可选：用于前端预览
                }
                
        except Exception as e:
            logger.error(f"页面抓取失败: {e}")
            raise Exception(f"页面抓取失败: {str(e)}")
    
    async def _extract_form_fields(self, page: Page) -> List[Dict[str, Any]]:
        """
        提取页面表单字段

        策略：
        1. 识别原生表单元素（input/select/textarea）
        2. 识别 contenteditable 富文本区
        3. 识别自定义下拉（role=combobox / ant-select / el-select）
        4. 识别 data-* 属性标记的自定义字段
        5. 识别常见字段类型（姓名、邮箱、手机号等）
        """
        fields = []
        seen_keys = set()  # 去重用

        logger.info("开始提取表单字段...")

        def _dedup(field: Dict[str, Any]) -> bool:
            key = field.get("id") or field.get("selector") or field.get("label")
            if not key or key in seen_keys:
                return False
            seen_keys.add(key)
            return True

        # 策略1：原生 input
        inputs = await page.query_selector_all(
            'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="reset"])'
        )
        for idx, element in enumerate(inputs):
            field = await self._extract_input_field(element, idx, page)
            if field and _dedup(field):
                fields.append(field)

        # 策略2：原生 select
        selects = await page.query_selector_all('select')
        for idx, element in enumerate(selects):
            field = await self._extract_select_field(element, idx, page)
            if field and _dedup(field):
                fields.append(field)

        # 策略3：原生 textarea
        textareas = await page.query_selector_all('textarea')
        for idx, element in enumerate(textareas):
            field = await self._extract_textarea_field(element, idx, page)
            if field and _dedup(field):
                fields.append(field)

        # 策略4：contenteditable 富文本/自定义输入
        editables = await page.query_selector_all(
            '[contenteditable="true"], [contenteditable=""]'
        )
        for idx, element in enumerate(editables):
            field = await self._extract_editable_field(element, idx, page)
            if field and _dedup(field):
                fields.append(field)

        # 策略5：自定义下拉组件（Ant Design / ElementUI / 通用 role=combobox）
        custom_selects = await page.query_selector_all(
            '[role="combobox"], .ant-select-selector, .el-select, .el-select .el-input__inner, '
            '.select-trigger, [class*="dropdown-trigger"]'
        )
        for idx, element in enumerate(custom_selects):
            field = await self._extract_custom_select_field(element, idx, page)
            if field and _dedup(field):
                fields.append(field)

        # 策略6：data-oc-field 属性标记（用户/插件自定义字段）
        data_fields = await page.query_selector_all('[data-oc-field]')
        for idx, element in enumerate(data_fields):
            field = await self._extract_data_attribute_field(element, idx, page)
            if field and _dedup(field):
                fields.append(field)

        logger.info(f"提取到 {len(fields)} 个表单字段")
        return fields

    async def _extract_editable_field(self, element, idx: int, page: Page) -> Optional[Dict[str, Any]]:
        """提取 contenteditable 字段"""
        try:
            element_id = await element.get_attribute('id')
            label = await self._get_field_label(element, page)
            if not label or label == '未知字段':
                # contenteditable 通常用 placeholder 或 data-placeholder
                placeholder = (
                    await element.get_attribute('data-placeholder')
                    or await element.get_attribute('placeholder')
                )
                if placeholder:
                    label = placeholder.strip()

            field_id = element_id or f'editable_{idx}'
            selector = f'#{element_id}' if element_id else f'[contenteditable]:nth-of-type({idx+1})'

            field_type_inferred = self._infer_field_type(label, element_id, 'textarea')

            return {
                'id': field_id,
                'label': label,
                'type': 'contenteditable',
                'tag': 'div',
                'required': False,
                'selector': selector,
                'field_type_inferred': field_type_inferred,
            }
        except Exception as e:
            logger.error(f"提取 contenteditable 字段失败: {e}")
            return None

    async def _extract_custom_select_field(self, element, idx: int, page: Page) -> Optional[Dict[str, Any]]:
        """提取自定义下拉组件字段"""
        try:
            element_id = await element.get_attribute('id')

            # 标签：找最近的 label 或前置文本
            label = await self._get_field_label(element, page)
            if not label or label == '未知字段':
                # 尝试从父容器的前置文本推断
                try:
                    parent_text = await element.evaluate(
                        """el => {
                            const wrap = el.closest('.ant-form-item, .el-form-item, .form-group, .field') || el.parentElement;
                            if (!wrap) return '';
                            const lbl = wrap.querySelector('label, .label, .ant-form-item-label, .el-form-item__label');
                            return lbl ? lbl.textContent.trim() : '';
                        }"""
                    )
                    if parent_text:
                        label = parent_text
                except Exception:
                    pass

            if not label or label == '未知字段':
                label = f'自定义下拉 {idx+1}'

            field_id = element_id or f'custom_select_{idx}'

            # selector 优先用 class 组合（更稳定）
            cls = await element.get_attribute('class') or ''
            if cls:
                first_cls = cls.split()[0]
                selector = f'.{first_cls}'
            elif element_id:
                selector = f'#{element_id}'
            else:
                selector = f'[role="combobox"]:nth-of-type({idx+1})'

            field_type_inferred = self._infer_field_type(label, element_id, 'select')

            return {
                'id': field_id,
                'label': label,
                'type': 'custom-select',
                'tag': 'div',
                'required': False,
                'options': [],  # 选项需点击展开才能获取
                'selector': selector,
                'field_type_inferred': field_type_inferred,
            }
        except Exception as e:
            logger.error(f"提取自定义下拉失败: {e}")
            return None

    async def _extract_data_attribute_field(self, element, idx: int, page: Page) -> Optional[Dict[str, Any]]:
        """提取通过 data-oc-field 标记的自定义字段"""
        try:
            field_name = await element.get_attribute('data-oc-field') or f'data_field_{idx}'
            label = (
                await element.get_attribute('data-oc-label')
                or await self._get_field_label(element, page)
                or field_name
            )
            field_type_attr = await element.get_attribute('data-oc-type') or 'text'

            tag = (await element.evaluate('el => el.tagName.toLowerCase()')) or 'input'
            element_id = await element.get_attribute('id')
            field_id = element_id or field_name

            if element_id:
                selector = f'#{element_id}'
            else:
                selector = f'[data-oc-field="{field_name}"]'

            field_type_inferred = self._infer_field_type(label, field_name, field_type_attr)

            return {
                'id': field_id,
                'label': label,
                'type': field_type_attr,
                'tag': tag,
                'required': (await element.get_attribute('data-oc-required')) == 'true',
                'selector': selector,
                'field_type_inferred': field_type_inferred,
            }
        except Exception as e:
            logger.error(f"提取 data-* 字段失败: {e}")
            return None
    
    async def _extract_input_field(self, element, idx: int, page: Page) -> Optional[Dict[str, Any]]:
        """提取 input 字段"""
        try:
            # 获取元素属性
            element_id = await element.get_attribute('id')
            element_name = await element.get_attribute('name')
            field_id = element_id or element_name or f'input_{idx}'
            
            # 获取标签（多策略）
            label = await self._get_field_label(element, page)
            
            # 获取类型
            input_type = await element.get_attribute('type') or 'text'
            
            # 判断是否必填
            required = await element.get_attribute('required') is not None
            aria_required = await element.get_attribute('aria-required')
            if aria_required and aria_required.lower() == 'true':
                required = True
            
            # 构建选择器
            if element_id:
                selector = f'#{element_id}'
            elif element_name:
                selector = f'input[name="{element_name}"]'
            else:
                selector = f'input:nth-of-type({idx+1})'
            
            # 推断字段类型（用于智能匹配）
            field_type_inferred = self._infer_field_type(label, element_name, input_type)
            
            return {
                'id': field_id,
                'label': label,
                'type': input_type,
                'tag': 'input',
                'required': required,
                'selector': selector,
                'field_type_inferred': field_type_inferred  # 推断的字段类型
            }
            
        except Exception as e:
            logger.error(f"提取 input 字段失败: {e}")
            return None
    
    async def _extract_select_field(self, element, idx: int, page: Page) -> Optional[Dict[str, Any]]:
        """提取 select 字段"""
        try:
            element_id = await element.get_attribute('id')
            element_name = await element.get_attribute('name')
            field_id = element_id or element_name or f'select_{idx}'
            
            label = await self._get_field_label(element, page)
            
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
            
            required = await element.get_attribute('required') is not None
            
            # 构建选择器
            if element_id:
                selector = f'#{element_id}'
            elif element_name:
                selector = f'select[name="{element_name}"]'
            else:
                selector = f'select:nth-of-type({idx+1})'
            
            field_type_inferred = self._infer_field_type(label, element_name, 'select')
            
            return {
                'id': field_id,
                'label': label,
                'type': 'select',
                'tag': 'select',
                'required': required,
                'options': option_texts,
                'selector': selector,
                'field_type_inferred': field_type_inferred
            }
            
        except Exception as e:
            logger.error(f"提取 select 字段失败: {e}")
            return None
    
    async def _extract_textarea_field(self, element, idx: int, page: Page) -> Optional[Dict[str, Any]]:
        """提取 textarea 字段"""
        try:
            element_id = await element.get_attribute('id')
            element_name = await element.get_attribute('name')
            field_id = element_id or element_name or f'textarea_{idx}'
            
            label = await self._get_field_label(element, page)
            required = await element.get_attribute('required') is not None
            
            if element_id:
                selector = f'#{element_id}'
            elif element_name:
                selector = f'textarea[name="{element_name}"]'
            else:
                selector = f'textarea:nth-of-type({idx+1})'
            
            field_type_inferred = self._infer_field_type(label, element_name, 'textarea')
            
            return {
                'id': field_id,
                'label': label,
                'type': 'textarea',
                'tag': 'textarea',
                'required': required,
                'selector': selector,
                'field_type_inferred': field_type_inferred
            }
            
        except Exception as e:
            logger.error(f"提取 textarea 字段失败: {e}")
            return None
    
    async def _get_field_label(self, element, page: Page) -> str:
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
        
        return '未知字段'
    
    def _name_to_readable(self, name: str) -> str:
        """将 name 属性转换为可读文本"""
        import re
        
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
        
        # 驼峰转可读
        readable = re.sub(r'([a-z])([A-Z])', r'\1 \2', name).lower()
        return readable
    
    def _infer_field_type(self, label: str, name: Optional[str], input_type: str) -> str:
        """
        推断字段类型（用于智能匹配）
        
        Returns:
            str: 字段类型（name/email/phone/education/experience/...）
        """
        label_lower = (label or '').lower()
        name_lower = (name or '').lower()
        
        # 基于标签和名称推断
        if '姓名' in label_lower or 'name' in label_lower:
            return 'name'
        if '邮箱' in label_lower or 'email' in label_lower:
            return 'email'
        if '手机' in label_lower or '电话' in label_lower or 'phone' in label_lower or 'mobile' in label_lower:
            return 'phone'
        if '性别' in label_lower or 'gender' in label_lower:
            return 'gender'
        if '年龄' in label_lower or 'age' in label_lower:
            return 'age'
        if '生日' in label_lower or 'birth' in label_lower:
            return 'birthday'
        if '学历' in label_lower or 'education' in label_lower:
            return 'education'
        if '专业' in label_lower or 'major' in label_lower:
            return 'major'
        if '学校' in label_lower or 'school' in label_lower:
            return 'school'
        if '公司' in label_lower or 'company' in label_lower:
            return 'company'
        if '职位' in label_lower or 'title' in label_lower or 'position' in label_lower:
            return 'title'
        if '简历' in label_lower or 'resume' in label_lower:
            return 'resume'
        if '身份证' in label_lower or 'id' in label_lower:
            return 'id_number'
        if '地址' in label_lower or 'address' in label_lower:
            return 'address'
        
        return 'unknown'


# Dependency injection
def get_smart_fill_service():
    return SmartFillService()