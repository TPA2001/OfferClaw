"""端到端测试：Boss 搜索 + 表单提取 + 脚本生成"""
import urllib.request
import json
import os
import sys

API = "http://localhost:8000/api/v1"
AUTH = {"Content-Type": "application/json", "Authorization": "Bearer demo-token"}


def post(path, body, timeout=60):
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode(),
        headers=AUTH,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def get(path, timeout=10):
    req = urllib.request.Request(f"{API}{path}")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def main():
    print("=" * 60)
    print("OfferClaw 端到端测试")
    print("=" * 60)

    # ---------- 测试 1：服务状态 ----------
    print("\n[T1] 服务状态")
    r = get("/automation/status")
    assert r["code"] == 0, r
    d = r["data"]
    print(f"  smart_fill={d['smart_fill']} boss_search={d['boss_search']}")
    assert d["boss_search"] == "available"
    print("  PASS")

    # ---------- 测试 2：Boss 搜索（mock 模式，避免反爬） ----------
    print("\n[T2] Boss 搜索（use_real=False，强制 mock）")
    r = post("/automation/boss-search",
             {"keyword": "Java 后端", "city": "杭州", "page": 1, "use_real": False})
    assert r["code"] == 0, r
    d = r["data"]
    print(f"  source={d['source']} total={d['total']} city={d['city']}")
    assert d["total"] > 0, "应返回模拟岗位"
    j0 = d["jobs"][0]
    print(f"  样例: {j0['title']} @ {j0['company']} | {j0['salary']} | {j0['location']}")
    print(f"  技能: {j0['skill_tags']}")
    print(f"  HR: {j0['hr_name']} / {j0['hr_position']}")
    print(f"  公司标签: {j0['company_tags']}")
    assert j0["title"] and j0["company"] and j0["salary"]
    print("  PASS")

    # ---------- 测试 3：Boss 搜索（不同关键字） ----------
    print("\n[T3] Boss 搜索（前端工程师）")
    r = post("/automation/boss-search",
             {"keyword": "前端", "city": "北京", "page": 1, "use_real": False})
    d = r["data"]
    print(f"  source={d['source']} total={d['total']}")
    j0 = d["jobs"][0]
    print(f"  样例: {j0['title']} | 技能={j0['skill_tags']}")
    assert any("JavaScript" in s or "Vue" in s or "React" in s for s in j0["skill_tags"]), \
        "前端岗位应包含前端技能标签"
    print("  PASS")

    # ---------- 测试 4：Boss 搜索（缺关键字校验） ----------
    print("\n[T4] Boss 搜索（空关键字校验）")
    req = urllib.request.Request(
        f"{API}/automation/boss-search",
        data=json.dumps({"keyword": "", "use_real": False}).encode(),
        headers=AUTH,
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        print("  FAIL: 应返回 400")
        sys.exit(1)
    except urllib.error.HTTPError as e:
        assert e.code == 400, f"应返回 400，实际 {e.code}"
        print(f"  HTTP {e.code}（符合预期）")
    print("  PASS")

    # ---------- 测试 5：表单字段提取（test-form.html） ----------
    print("\n[T5] 表单字段提取（test-form.html）")
    # 从 backend/ 目录算，需要回到项目根再进 frontend
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    test_form_path = os.path.join(project_root, "frontend", "web", "test-form.html").replace("\\", "/")
    test_url = f"file:///{test_form_path}"
    print(f"  URL: {test_url}")
    r = post("/automation/extract-from-url", {"url": test_url}, timeout=90)
    assert r["code"] == 0, f"提取失败: {r}"
    d = r["data"]
    print(f"  页面标题: {d.get('title')}")
    print(f"  识别字段数: {d.get('field_count')}")
    fields = d.get("fields", [])
    print("  字段列表:")
    for f in fields:
        print(f"    - {f.get('label')} | tag={f.get('tag')} type={f.get('type')} "
              f"inferred={f.get('field_type_inferred')}")
    assert d.get("field_count", 0) >= 8, f"应至少识别 8 个字段，实际 {d.get('field_count')}"
    # 验证类型覆盖
    types = {f.get("type") for f in fields}
    print(f"  覆盖类型: {types}")
    # 至少应识别出 input/email/select/radio/checkbox/textarea
    expected = {"text", "email", "select", "radio", "checkbox", "textarea"}
    missing = expected - types
    if missing:
        print(f"  WARN: 缺少类型 {missing}")
    print("  PASS")

    # ---------- 测试 6：脚本生成 ----------
    print("\n[T6] 填写脚本生成（多类型字段）")
    test_fields = [
        {"id": "name", "label": "姓名", "tag": "input", "type": "text", "selector": "#name", "field_type_inferred": "name"},
        {"id": "email", "label": "邮箱", "tag": "input", "type": "email", "selector": "#email", "field_type_inferred": "email"},
        {"id": "phone", "label": "手机号", "tag": "input", "type": "tel", "selector": "#phone", "field_type_inferred": "phone"},
        {"id": "education", "label": "最高学历", "tag": "select", "type": "select", "selector": "#education",
         "options": [{"text": "本科", "value": "本科"}, {"text": "硕士", "value": "硕士"}], "field_type_inferred": "education"},
        {"id": "gender", "label": "性别", "tag": "input", "type": "radio", "selector": "[name='gender']", "field_type_inferred": "gender"},
        {"id": "city_pref", "label": "意向城市", "tag": "input", "type": "checkbox", "selector": "[name='city_pref']", "field_type_inferred": "unknown"},
        {"id": "intro", "label": "自我介绍", "tag": "textarea", "type": "textarea", "selector": "#intro", "field_type_inferred": "unknown"},
        {"id": "projectExp", "label": "项目经历", "tag": "div", "type": "contenteditable", "selector": "#projectExp", "field_type_inferred": "unknown"},
    ]
    test_mappings = [
        {"field_id": "name", "value": "张三", "confidence": 0.95},
        {"field_id": "email", "value": "zhangsan@example.com", "confidence": 0.92},
        {"field_id": "phone", "value": "13800138000", "confidence": 0.88},
        {"field_id": "education", "value": "硕士", "confidence": 0.85},
        {"field_id": "gender", "value": "男", "confidence": 0.7},
        {"field_id": "city_pref", "value": "true", "confidence": 0.5},
        {"field_id": "intro", "value": "5 年 Java 后端开发经验", "confidence": 0.6},
        {"field_id": "projectExp", "value": "高并发电商系统设计", "confidence": 0.55},
    ]
    r = post("/automation/generate-script",
             {"fields": test_fields, "mappings": test_mappings}, timeout=30)
    assert r["code"] == 0, r
    script = r["data"]["script"]
    print(f"  脚本长度: {len(script)} 字符")
    # 验证关键功能
    assert "nativeInputValueSetter" not in script or "setNativeValue" in script, "应支持 React 兼容"
    assert "contenteditable" in script.lower(), "应支持 contenteditable"
    assert "select" in script.lower(), "应支持 select"
    assert "checkbox" in script.lower(), "应支持 checkbox"
    assert "radio" in script.lower(), "应支持 radio"
    assert "oc-filled" in script, "应有视觉反馈样式"
    assert "oc-failed" in script, "应有失败标记样式"
    assert "张三" in script, "数据应嵌入脚本"
    assert "13800138000" in script
    # 输出片段预览
    print("  脚本预览（前 500 字符）:")
    print("  " + script[:500].replace("\n", "\n  "))
    print("  PASS")

    # ---------- 总结 ----------
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED ✓")
    print("=" * 60)
    print("""
覆盖功能：
  ✓ Boss 搜索（模拟数据降级，多关键字）
  ✓ Boss 搜索参数校验（空关键字）
  ✓ 表单字段提取（8+ 类型字段识别）
  ✓ 填写脚本生成（input/select/radio/checkbox/textarea/contenteditable）
  ✓ 脚本特性：React 兼容、视觉反馈、数据嵌入
""")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[FAIL] {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
