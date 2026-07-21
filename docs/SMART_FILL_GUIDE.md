# 智能填写功能 - Web 版本（无需插件）

## 概述

OfferClaw 智能填写功能采用**完全 Web 化**的实现方式，用户**无需安装任何浏览器插件**，即可享受智能表单填写服务。

## 核心优势

### 1. 零门槛使用
- ✅ 无需安装浏览器扩展
- ✅ 无需担心隐私权限
- ✅ 跨浏览器兼容（Chrome/Firefox/Edge/Safari）
- ✅ 移动端同样可用

### 2. 安全可靠
- ✅ 敏感数据（身份证、家庭住址）仅存储在本地
- ✅ 后端不接触原始敏感数据
- ✅ 用户可查看并修改所有匹配结果

### 3. 简单易用
- ✅ 4 步完成智能填写
- ✅ 可视化字段识别
- ✅ 手动调整匹配结果
- ✅ 一键生成填写脚本

## 用户使用流程

### 步骤 1: 输入 URL
访问 OfferClaw 网站，输入目标企业网申页面的 URL。

```
例如：https://jobs.company.com/apply
```

### 步骤 2: 自动识别字段
系统后台自动抓取页面，识别所有表单字段：
- Input 文本框
- Select 下拉选择
- Textarea 多行文本
- Checkbox 复选框
- Radio 单选按钮

### 步骤 3: 智能匹配填写
系统根据用户画像自动匹配填写内容：
- 姓名、邮箱、手机号等基本信息
- 教育经历、工作经历
- 技能列表、求职意向

用户可以手动调整匹配结果。

### 步骤 4: 生成填写脚本
系统生成 JavaScript 填写脚本，用户：
1. 打开目标页面
2. 按 F12 打开浏览器控制台
3. 复制并执行脚本
4. 表单自动填写完成

## 技术架构

### 后端架构

```
backend/
├── app/
│   ├── api/
│   │   └── automation.py       # 智能填写 API
│   │
│   ├── services/
│   │   └── smart_fill.py       # 智能填写服务（核心）
│   │
│   ├── automation/
│   │   ├── form_extractor.py   # 表单字段提取
│   │   ├── form_filler.py      # 表单填写执行
│   │   └── field_matcher.py    # 字段语义匹配
│   │
│   ├── models/
│   │   └── profile.py          # 用户画像模型
│   │
│   └── core/
│       ├── database.py         # 数据库连接
│       ├── auth.py             # 用户认证
│       └── llm.py              # LLM 调用
```

### API 接口

#### 1. 从 URL 提取字段
```http
POST /api/v1/automation/extract-from-url
Authorization: Bearer <token>

{
  "url": "https://jobs.company.com/apply"
}

Response:
{
  "code": 0,
  "message": "提取成功",
  "data": {
    "url": "https://jobs.company.com/apply",
    "title": "职位申请 - Company",
    "fields": [
      {
        "id": "name",
        "label": "姓名",
        "type": "text",
        "required": true,
        "selector": "#name"
      },
      ...
    ],
    "field_count": 10
  }
}
```

#### 2. 字段语义匹配
```http
POST /api/v1/automation/match
Authorization: Bearer <token>

{
  "fields": [...]
}

Response:
{
  "code": 0,
  "message": "匹配成功",
  "data": {
    "mappings": [
      {
        "field_id": "name",
        "value": "张三",
        "confidence": 0.95,
        "source": "profile"
      },
      ...
    ],
    "profile_used": true
  }
}
```

#### 3. 生成填写脚本
```http
POST /api/v1/automation/generate-script
Authorization: Bearer <token>

{
  "fields": [...],
  "mappings": [...]
}

Response:
{
  "code": 0,
  "message": "脚本生成成功",
  "data": {
    "script": "// OfferClaw 智能填写脚本\n...",
    "usage": "请将上述脚本复制到浏览器控制台（按 F12 打开）并执行"
  }
}
```

### 前端架构

```
frontend/web/
└── smart-fill.html    # 智能填写页面
```

#### 页面功能
- ✅ 步骤指示器（可视化进度）
- ✅ URL 输入框
- ✅ 字段列表展示
- ✅ 匹配结果编辑
- ✅ 脚本生成与复制
- ✅ 加载动画提示

## 技术实现细节

### 1. 页面抓取（Playwright）

使用 Playwright 无头浏览器抓取页面：

```python
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page()
    await page.goto(url, wait_until="networkidle", timeout=30000)
    
    # 提取表单字段
    inputs = await page.query_selector_all('input:not([type="hidden"])')
    selects = await page.query_selector_all('select')
    textareas = await page.query_selector_all('textarea')
```

### 2. 字段识别策略

**多策略识别标签：**
1. aria-label 属性
2. <label for="id"> 元素
3. placeholder 属性
4. name 属性（驼峰转可读）
5. 相邻 label 元素

**字段类型推断：**
- 基于标签文本和字段名称
- 识别常见字段（姓名、邮箱、手机号等）
- 支持自定义映射规则

### 3. 语义匹配（LLM）

使用大语言模型进行语义匹配：

```python
MATCH_PROMPT = """你是表单填写助手。给定表单字段列表和用户画像，输出 JSON 映射数组：
[{
  "field_id": "字段ID",
  "value": "填写值或 null",
  "confidence": 0.0-1.0,
  "source": "profile|local_sensitive|file_upload",
  "reason": "匹配理由(低置信度时必填)"
}]"""
```

### 4. 脚本生成

生成可执行的 JavaScript 代码：

```javascript
(function() {
  'use strict';
  
  const fillData = {
    'name': '张三',
    'email': 'zhangsan@example.com',
    'phone': '13800138000'
  };
  
  for (const [fieldId, value] of Object.entries(fillData)) {
    const field = document.querySelector(`[id="${fieldId}"], [name="${fieldId}"]`);
    if (field) {
      field.value = value;
      field.dispatchEvent(new Event('input', { bubbles: true }));
      field.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }
})();
```

## 与传统插件方案的对比

| 维度 | 插件方案 | Web 版方案 |
|------|----------|------------|
| 用户门槛 | 需要安装插件 | 无需安装，即开即用 |
| 隐私担忧 | 需要所有网页权限 | 无需额外权限 |
| 跨平台 | 需要适配不同浏览器 | 跨平台兼容 |
| 维护成本 | 需要适配浏览器API变化 | 仅需维护后端服务 |
| 用户体验 | 复杂的安装流程 | 简单的4步流程 |
| 适用人群 | 技术用户 | 所有用户 |

## 隐私保护

### 数据分级存储

**云端存储（非敏感）：**
- 姓名、邮箱、手机号
- 教育经历、工作经历
- 技能列表、求职意向

**本地存储（敏感）：**
- 身份证号
- 家庭住址
- 其他敏感信息

### 填写流程

1. 非敏感数据从云端加载
2. 敏感数据从浏览器本地存储读取
3. 脚本在浏览器端执行
4. 后端不接触原始敏感数据

## 未来优化方向

### 短期（1-2周）
- ✅ 优化字段识别准确率
- ✅ 增加更多字段类型支持
- ✅ 优化前端交互体验

### 中期（1-2月）
- 🔲 支持批量填写（多页面）
- 🔲 增加填写成功率统计
- 🔲 支持简历附件上传

### 长期（3-6月）
- 🔲 集成到企业招聘系统（B2B）
- 🔲 支持自定义字段映射规则
- 🔲 AI 辅助填写策略优化

## 快速开始

### 启动后端
```bash
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

### 启动前端
```bash
cd frontend/web
python -m http.server 3000
```

### 访问应用
打开浏览器访问：http://localhost:3000/smart-fill.html

---

**注意**：此方案需要安装 Playwright 浏览器驱动：
```bash
pip install playwright
playwright install chromium
```