"""
智能填写模块 - 核心功能
整合原有的 automation 模块，提供智能表单填写能力
"""

from .form_extractor import FormExtractor
from .form_filler import FormFiller
from .field_matcher import FieldMatcher

__all__ = ["FormExtractor", "FormFiller", "FieldMatcher"]