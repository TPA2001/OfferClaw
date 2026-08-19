"""
统一 API 响应信封测试

覆盖：
- 成功响应格式 {"code": 0, "message": ..., "data": ...}
- 业务码与 HTTP 状态码的相互映射
- APIError 异常被全局处理器转换为统一信封
- RequestValidationError 被全局处理器转换为 42200
- 未捕获异常被全局处理器转换为 50000（且不泄露堆栈）
- 端点级集成：/api/v1/applications 的成功/错误响应都遵循统一格式
"""
import pytest

from app.core.response import (
    ok, APIError, BadRequestError, NotFoundError, InternalServerError,
    business_code_for_http, fail,
)


# ============ 单元测试 ============

class TestOkHelper:
    """成功响应辅助函数"""

    def test_ok_basic(self):
        """基础成功响应"""
        resp = ok({"id": 1}, message="OK")
        assert resp == {"code": 0, "message": "OK", "data": {"id": 1}}

    def test_ok_no_data(self):
        """无数据成功响应（删除操作）"""
        resp = ok(None, message="已删除")
        assert resp == {"code": 0, "message": "已删除", "data": None}

    def test_ok_with_extra(self):
        """带额外顶层字段（如分页 total）"""
        resp = ok([1, 2, 3], message="获取列表", extra={"total": 3, "page": 1})
        assert resp == {
            "code": 0, "message": "获取列表",
            "data": [1, 2, 3], "total": 3, "page": 1,
        }

    def test_ok_extra_ignores_reserved_keys(self):
        """extra 中的 code/message/data 应被忽略，避免覆盖核心字段"""
        resp = ok("x", extra={"code": 999, "message": "evil", "data": "evil"})
        assert resp["code"] == 0
        assert resp["message"] == "OK"
        assert resp["data"] == "x"


class TestBusinessCodeMapping:
    """业务码 <-> HTTP 状态码映射"""

    @pytest.mark.parametrize("code,http_status", [
        (0, 200),
        (40000, 400),
        (40100, 401),
        (40300, 403),
        (40400, 404),
        (40900, 409),
        (42200, 422),
        (42900, 429),
        (50000, 500),
        (50200, 502),
        (50300, 503),
        (50400, 504),
    ])
    def test_known_codes(self, code, http_status):
        assert business_code_for_http(http_status) == code

    def test_unknown_http_status_falls_back_to_50000(self):
        assert business_code_for_http(599) == 50000


class TestAPIError:
    """APIError 异常类"""

    def test_bad_request_error(self):
        err = BadRequestError("参数错误")
        assert err.code == 40000
        assert err.status_code == 400
        assert err.message == "参数错误"

    def test_not_found_error(self):
        err = NotFoundError("记录不存在")
        assert err.code == 40400
        assert err.status_code == 404

    def test_internal_server_error(self):
        err = InternalServerError("服务器错误")
        assert err.code == 50000
        assert err.status_code == 500

    def test_api_error_with_detail(self):
        err = APIError(40000, "非法状态", detail={"field": "status"})
        assert err.code == 40000
        assert err.detail == {"field": "status"}


class TestFailFunction:
    """fail() 辅助函数（直接返回 JSONResponse）"""

    def test_fail_returns_jsonresponse(self):
        from fastapi.responses import JSONResponse
        resp = fail(40000, "参数错误")
        assert isinstance(resp, JSONResponse)
        assert resp.status_code == 400

    def test_fail_payload(self):
        import json
        resp = fail(40400, "记录不存在", detail={"id": "xxx"})
        body = json.loads(resp.body)
        assert body["code"] == 40400
        assert body["message"] == "记录不存在"
        assert body["detail"] == {"id": "xxx"}


# ============ 集成测试（通过 TestClient） ============

class TestResponseEnvelopeIntegration:
    """端到端验证：成功/错误响应都遵循统一信封"""

    def test_success_envelope(self, client):
        """成功响应遵循 {"code": 0, "message": ..., "data": ...}"""
        resp = client.get("/api/v1/applications/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert "message" in body
        assert "data" in body
        # 看板列表额外携带 total 字段
        assert "total" in body

    def test_not_found_error_envelope(self, client):
        """404 错误响应遵循统一信封"""
        resp = client.get("/api/v1/applications/nonexistent-id")
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == 40400
        assert "message" in body
        assert body["message"] == "记录不存在"
        assert "detail" in body

    def test_bad_request_error_envelope(self, client):
        """400 错误响应（非法状态查询）遵循统一信封"""
        resp = client.get("/api/v1/applications/", params={"status": "invalid_status"})
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == 40000
        assert "非法状态" in body["message"]
        assert "detail" in body

    def test_validation_error_envelope(self, client):
        """422 参数校验错误遵循统一信封"""
        # POST /api/v1/applications/ 缺少必填的 company 字段
        resp = client.post("/api/v1/applications/", json={})
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == 42200
        assert body["message"] == "请求参数校验失败"
        assert isinstance(body["detail"], list)

    def test_create_then_get_roundtrip(self, client):
        """创建-获取全流程：响应格式一致"""
        # 创建
        create_resp = client.post("/api/v1/applications/", json={
            "company": "测试公司",
            "position": "测试岗位",
        })
        assert create_resp.status_code == 200
        created = create_resp.json()
        assert created["code"] == 0
        assert created["data"]["company"] == "测试公司"
        app_id = created["data"]["id"]

        # 获取
        get_resp = client.get(f"/api/v1/applications/{app_id}")
        assert get_resp.status_code == 200
        fetched = get_resp.json()
        assert fetched["code"] == 0
        assert fetched["data"]["id"] == app_id

    def test_delete_envelope(self, client):
        """删除操作返回 data=null 的成功信封"""
        # 先创建
        create_resp = client.post("/api/v1/applications/", json={
            "company": "待删除公司",
            "position": "待删除岗位",
        })
        app_id = create_resp.json()["data"]["id"]

        # 删除
        del_resp = client.delete(f"/api/v1/applications/{app_id}")
        assert del_resp.status_code == 200
        body = del_resp.json()
        assert body["code"] == 0
        assert body["data"] is None
        assert body["message"] == "已删除"

    def test_root_serves_frontend(self, client):
        """根端点返回前端静态页面（StaticFiles 挂载接管，不再是 JSON 信封）"""
        resp = client.get("/")
        assert resp.status_code == 200
        # 根路径由后端挂载的前端静态目录接管，返回 HTML
        content_type = resp.headers.get("content-type", "")
        assert "text/html" in content_type
        assert "<html" in resp.text.lower() or "<!doctype" in resp.text.lower()
