"""
统一 API 响应封装

所有业务接口遵循统一信封：
    成功：{"code": 0,    "message": "...", "data": ...}
    失败：{"code": <非0>, "message": "...", "detail": ...}

业务码与 HTTP 状态码对齐（用整数千位表示）：
    0      成功
    40000  参数错误 / Bad Request          (HTTP 400)
    40100  未授权 / Unauthorized           (HTTP 401)
    40300  禁止访问 / Forbidden            (HTTP 403)
    40400  资源不存在 / Not Found          (HTTP 404)
    40900  资源冲突 / Conflict             (HTTP 409)
    42200  请求格式正确但语义错误          (HTTP 422)
    42900  请求过于频繁 / Rate Limited     (HTTP 429)
    50000  服务器内部错误                  (HTTP 500)
    50200  上游服务错误                    (HTTP 502)
    50300  服务暂不可用                    (HTTP 503)
    50400  上游超时                        (HTTP 504)

设计原则：
1. 业务码 = HTTP 状态码 × 100，便于前端一眼对照
2. message 永远是面向用户可读的中文文案
3. data 永远是业务数据对象；无数据时为 null
4. detail 用于错误的额外诊断信息（非必须）
"""

from typing import Any, Optional, Union
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse


# ============ 业务码 <-> HTTP 状态码映射 ============

_CODE_TO_HTTP = {
    0:      200,
    40000:  400,
    40100:  401,
    40101:  401,  # 登录已过期
    40102:  401,  # 账号已停用
    40103:  401,  # 密码已变更，需重新登录
    40300:  403,
    40301:  403,  # 未激活
    40302:  403,  # 已过期
    40303:  403,  # 功能未授权
    40400:  404,
    40900:  409,
    42200:  422,
    42900:  429,
    50000:  500,
    50200:  502,
    50300:  503,
    50400:  504,
}

# 反向映射：HTTP -> 业务码。同一 HTTP 码有多个子码时保留整百的基准码
_HTTP_TO_CODE = {}
for _c, _h in _CODE_TO_HTTP.items():
    if _h not in _HTTP_TO_CODE:
        _HTTP_TO_CODE[_h] = _c


def _http_status_for(code: int) -> int:
    """业务码转 HTTP 状态码；未知码退回到 500。"""
    return _CODE_TO_HTTP.get(code, 500)


def business_code_for_http(http_status: int) -> int:
    """HTTP 状态码转业务码；未知码退回到 50000。"""
    return _HTTP_TO_CODE.get(http_status, 50000)


# ============ 成功响应辅助 ============

def ok(
    data: Any = None,
    message: str = "OK",
    *,
    extra: Optional[dict] = None,
) -> dict:
    """构造成功响应字典（用于 return 的端点）

    Args:
        data: 业务数据；无数据传 None
        message: 面向用户的提示文案
        extra: 额外顶层字段（如 total/warning 等，会并入返回 dict）
               注意：extra 字段会原样合并到顶层，请避免与 code/message/data 重名
    """
    payload: dict = {"code": 0, "message": message, "data": data}
    if extra:
        for k, v in extra.items():
            if k not in ("code", "message", "data"):
                payload[k] = v
    return payload


# ============ 错误响应辅助 ============

class APIError(HTTPException):
    """业务异常基类

    用法：
        raise APIError(40400, "记录不存在")
        raise APIError(40000, "非法状态", detail={"field": "status", "value": "foo"})

    它会被全局异常处理器拦截并转换为统一信封。

    注意：HTTPException 父类的 __init__ 会设置 self.detail = message，
    因此我们在 super().__init__ 之后再覆盖 self.detail 为业务诊断信息。
    """

    def __init__(
        self,
        code: int,
        message: str,
        detail: Any = None,
        headers: Optional[dict] = None,
    ):
        self.code = code
        self.message = message
        super().__init__(
            status_code=_http_status_for(code),
            detail=message,
            headers=headers,
        )
        # 覆盖父类的 detail（业务诊断信息，可为 dict/str/None）
        self.detail = detail


def fail(
    code: int,
    message: str,
    *,
    detail: Any = None,
    headers: Optional[dict] = None,
) -> JSONResponse:
    """直接返回失败 JSONResponse（用于不能 raise 的场景）

    一般推荐用 raise APIError(...)；此函数保留给少数场景（如 SSE 之外的同步返回）。
    """
    return JSONResponse(
        status_code=_http_status_for(code),
        content={
            "code": code,
            "message": message,
            "detail": detail,
        },
        headers=headers,
    )


# ============ 便捷错误构造 ============

class BadRequestError(APIError):
    def __init__(self, message: str = "请求参数错误", detail: Any = None, headers: Optional[dict] = None):
        super().__init__(40000, message, detail=detail, headers=headers)


class UnauthorizedError(APIError):
    def __init__(self, message: str = "未授权", detail: Any = None, headers: Optional[dict] = None):
        super().__init__(40100, message, detail=detail, headers=headers)


class ForbiddenError(APIError):
    def __init__(self, message: str = "禁止访问", detail: Any = None, headers: Optional[dict] = None):
        super().__init__(40300, message, detail=detail, headers=headers)


class NotFoundError(APIError):
    def __init__(self, message: str = "资源不存在", detail: Any = None, headers: Optional[dict] = None):
        super().__init__(40400, message, detail=detail, headers=headers)


class ConflictError(APIError):
    def __init__(self, message: str = "资源冲突", detail: Any = None, headers: Optional[dict] = None):
        super().__init__(40900, message, detail=detail, headers=headers)


class ValidationError(APIError):
    def __init__(self, message: str = "请求格式正确但语义错误", detail: Any = None, headers: Optional[dict] = None):
        super().__init__(42200, message, detail=detail, headers=headers)


class RateLimitError(APIError):
    def __init__(self, message: str = "请求过于频繁", detail: Any = None, headers: Optional[dict] = None):
        super().__init__(42900, message, detail=detail, headers=headers)


class InternalServerError(APIError):
    def __init__(self, message: str = "服务器内部错误", detail: Any = None, headers: Optional[dict] = None):
        super().__init__(50000, message, detail=detail, headers=headers)
