"""
用户画像模型
存储用户的个人信息，用于智能填写
"""

from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.sql import func
import uuid

from app.core.database import Base


def _uuid_str() -> str:
    """生成 UUID 字符串（与 Application 表保持一致，兼容 SQLite）"""
    return str(uuid.uuid4())


class Profile(Base):
    """用户画像表"""
    __tablename__ = "profiles"

    # 用 String(36) 而非 UUID 类型，兼容 SQLite + 任意字符串 user_id
    id = Column(String(36), primary_key=True, default=_uuid_str)
    user_id = Column(String(64), unique=True, nullable=False, index=True)

    # 基本信息
    basic_info = Column(JSON, default={})
    # {
    #   "name": "张三",            # 姓名
    #   "english_name": "San Zhang",  # 英文名
    #   "gender": "男",
    #   "age": "30",
    #   "birth": "1995-01-01",
    #   "phone": "13800138000",
    #   "email": "zhangsan@example.com",
    #   "location": "上海",        # 现居城市
    #   "ethnicity": "汉族",
    #   "political_status": "群众",
    #   "marital_status": "未婚",
    #   "native_place": "江苏南京", # 籍贯
    #   "household_type": "城镇户籍",
    #   "height": "175", "weight": "65", "health": "健康",
    #   "wechat": "wechat-id", "qq": "123456",
    #   "website": "https://...", "github": "xxx", "linkedin": "https://...",
    #   "english_level": "CET-6", "driving_license": "C1",
    #   "job_status": "离职-随时到岗",
    #   "current_company": "某科技公司",   # 当前公司
    #   "current_title": "软件工程师",      # 当前职位
    #   "years_of_experience": "5",         # 工作年限
    #   "highest_education": "本科",        # 最高学历
    #   "available_date": "2026-10-01",     # 可入职日期
    #   "avatar": "https://..."
    #   # 注意：身份证号/住址/银行卡/护照/紧急联系人等敏感字段一律不存储
    # }

    # 教育经历
    education = Column(JSON, default=[])
    # [
    #   {
    #     "school": "清华大学",
    #     "major": "计算机科学与技术",
    #     "degree": "本科",
    #     "school_type": "985/双一流",      # 院校层次
    #     "edu_form": "全日制",              # 教育形式
    #     "study_mode": "统招",              # 培养方式（统招/非统招/联合培养/委托培养）
    #     "minor": "数学",                   # 辅修专业
    #     "faculty": "计算机学院",           # 院系
    #     "start_date": "2013-09",
    #     "end_date": "2017-07",
    #     "graduation_status": "已毕业",     # 已毕业/预计毕业/在读/肄业
    #     "gpa": "3.8/4.0",
    #     "ranking": "前 10%",
    #     "courses": "数据结构、操作系统",
    #     "description": "主修课程、学术成就等"
    #   }
    # ]

    # 工作经历
    experience = Column(JSON, default=[])
    # [
    #   {
    #     "company": "阿里巴巴",
    #     "title": "高级工程师",
    #     "department": "平台研发部",
    #     "industry": "互联网",
    #     "city": "杭州",
    #     "employment_type": "全职",        # 全职/兼职/实习/合同/自由职业
    #     "location_mode": "现场办公",      # 办公方式
    #     "team_size": "8",
    #     "start_date": "2017-08",
    #     "end_date": "2020-06",
    #     "is_current": false,
    #     "description": "负责...",
    #     "achievements": ["量化成果 1", "量化成果 2"],
    #     "technologies": "Java、Redis"
    #   }
    # ]

    # 技能列表
    skills = Column(JSON, default=[])
    # ["Python", "Java", "MySQL", "Docker"]

    # 项目经历
    projects = Column(JSON, default=[])
    # [
    #   {
    #     "name": "OfferCabin 求职管理系统",
    #     "role": "全栈开发",
    #     "organization": "个人项目",
    #     "start_date": "2024-01",
    #     "end_date": "2024-06",
    #     "is_current": false,
    #     "url": "https://...",
    #     "demo_url": "https://...",
    #     "description": "基于 FastAPI + Playwright 实现的求职管理工具...",
    #     "highlights": "效果、指标、架构亮点",
    #     "tech_stack": ["Python", "FastAPI", "Vue"]
    #   }
    # ]

    # 自我评价 / 个人简介
    summary = Column(JSON, default={})
    # {
    #   "self_eval": "5 年后端开发经验，熟悉分布式系统设计...",
    #   "advantage": "主导过百万级 QPS 系统的架构设计",
    #   "career_goal": "希望成长为技术专家..."
    # }

    # 证书 / 荣誉
    certifications = Column(JSON, default=[])
    # [
    #   {
    #     "name": "PMP 项目管理认证",
    #     "issuer": "PMI",
    #     "date": "2023-06",
    #     "score": ""
    #   }
    # ]

    # 求职意向
    job_intent = Column(JSON, default={})
    # {
    #   "role": "高级软件工程师",            # 目标岗位
    #   "target_positions": ["后端工程师", "架构师"],
    #   "cities": ["上海", "北京", "深圳"],
    #   "target_cities": ["上海", "北京"],
    #   "salary_min": 30000,
    #   "salary_max": 50000,
    #   "expected_salary": "30-50K",
    #   "job_type": "全职",
    #   "work_type": "全职",
    #   "employment_type": "全职",           # 全职/兼职/实习/合同/自由职业
    #   "remote_preference": "现场办公",      # 现场/混合/远程/灵活
    #   "notice_period": "30 天",             # 到岗周期
    #   "preferred_locations": "上海、北京、杭州、远程",
    #   "willing_to_relocate": "是",
    #   "willing_to_travel": "是",
    #   "target_industry": "AI / SaaS / 电商",
    #   "target_level": "高级 / 专家",
    #   "current_salary": "30-40K"
    # }

    # 语言能力（网申常见字段，独立于技能的语种与成绩）
    languages = Column(JSON, default=[])
    # [
    #   {
    #     "name": "英语",
    #     "proficiency": "流利",             # 母语/流利/工作熟练/中等/基础
    #     "test_score": "雅思 7.5 / 托福 105 / CET-6"
    #   }
    # ]

    # 获奖/荣誉（网申常考，独立于证书的荣誉奖项）
    awards = Column(JSON, default=[])
    # [
    #   {
    #     "name": "校级一等奖学金",
    #     "level": "校级",                   # 国家级/省级/市级/校级/企业级/其他
    #     "issuer": "XX大学",               # 颁发单位
    #     "date": "2023-06",
    #     "description": "专业成绩前 5%"
    #   }
    # ]

    # 开放题答案库（网申通用问题，可存多版本，如 互联网版/国央企版/外企英文版）
    essays = Column(JSON, default=[])
    # [
    #   {
    #     "question": "为什么选择我们公司",
    #     "answer": "贵公司在 AI 领域的技术积累...",
    #     "tag": "互联网版"
    #   }
    # ]

    # 论文/发表物（校招/央国企/科研岗常考）
    publications = Column(JSON, default=[])
    # [
    #   {
    #     "title": "基于深度学习的推荐系统研究",
    #     "venue": "计算机学报",           # 期刊/会议名称
    #     "level": "中文核心",            # SCI/SSCI/EI/中文核心/普刊/会议/其他
    #     "authors": "张三(第一作者), 李四", # 全部作者（含本人）
    #     "role": "第一作者",             # 第一作者/共同一作/通讯作者/参与
    #     "date": "2023-06",             # 发表/见刊时间
    #     "doi": "10.1234/xxxx",          # DOI 或链接
    #     "description": "简述研究内容与成果"
    #   }
    # ]

    # 专利（网申常考，区分 已授权/实审中/已申请）
    patents = Column(JSON, default=[])
    # [
    #   {
    #     "name": "一种数据处理方法及装置",
    #     "patent_no": "CN202310123456.7",  # 专利号/申请号
    #     "type": "发明专利",               # 发明专利/实用新型/外观设计/软件著作权
    #     "status": "已授权",               # 已授权/实审中/已申请
    #     "holder": "申请主体",             # 申请人
    #     "inventors": "发明人（含本人）",
    #     "date": "2023-06",               # 申请/授权时间
    #     "description": ""
    #   }
    # ]

    # 自定义字段（用于存储额外信息）
    extra_fields = Column(JSON, default={})

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())