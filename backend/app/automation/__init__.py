"""
智能填写模块 - 表单字段提取与语义匹配

提供底层表单自动化能力：
- FormExtractor: 表单字段提取（Playwright 渲染后的页面解析）
- FieldMatcher: 字段语义匹配（LLM + 规则降级）

实际的表单填写执行由 services/auto_filler.py（CDP-based）负责。
"""

from .form_extractor import FormExtractor
from .field_matcher import FieldMatcher

__all__ = ["FormExtractor", "FieldMatcher"]
