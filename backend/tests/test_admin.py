"""
管理后台 API 测试

覆盖：
- 鉴权：非管理员 403 / 登录失败 401 / 管理令牌可用
- 仪表盘 stats
- 用户管理：disable/enable/reset-password/promote/demote/revoke-sessions（含 demote 自我被拒）
- 举报处理：hide/delete/dismiss
- 帖子审核：hide/unhide/pin/unpin/delete
- 岗位分享：hide/unhide/delete
- 评论删除
- 审计日志写入与查询
- validate_password_strength 单测
"""
import pytest

from app.core.auth import validate_password_strength, create_access_token
from app.models.community import (
    CommunityPost,
    CommunityJobShare,
    PostComment,
    ContentReport,
)
from app.models.admin_audit import AdminAuditLog


# ============ 鉴权 ============

def test_non_admin_forbidden(admin_client, plain_headers):
    """非管理员访问管理端点 → 403"""
    resp = admin_client.get("/api/v1/admin/stats", headers=plain_headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == 40300


def test_no_token_unauthorized(admin_client):
    """无令牌 → 401"""
    resp = admin_client.get("/api/v1/admin/stats")
    assert resp.status_code == 401


def test_admin_login_success(admin_client, admin_user):
    """管理员登录成功，返回短 TTL 令牌"""
    resp = admin_client.post(
        "/api/v1/admin/login",
        json={"account": "admin01", "password": "Admin1234"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["token"]
    assert data["user"]["role"] == "admin"


def test_admin_login_wrong_password(admin_client, admin_user):
    """登录密码错误 → 401，文案不泄露账号是否存在"""
    resp = admin_client.post(
        "/api/v1/admin/login",
        json={"account": "admin01", "password": "wrong-password"},
    )
    assert resp.status_code == 401
    assert resp.json()["message"] == "账号或密码错误"


def test_admin_login_non_admin_forbidden(admin_client, plain_user):
    """普通用户登录管理后台 → 403"""
    resp = admin_client.post(
        "/api/v1/admin/login",
        json={"account": "plain01", "password": "Pass1234"},
    )
    assert resp.status_code == 403


def test_admin_me(admin_client, admin_headers, admin_user):
    resp = admin_client.get("/api/v1/admin/me", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["username"] == "admin01"


# ============ 仪表盘 ============

def test_stats(admin_client, admin_headers, admin_user, plain_user, db_session):
    # 造一条帖子
    db_session.add(CommunityPost(user_id=plain_user.id, title="t", content="c", status="normal"))
    db_session.commit()
    resp = admin_client.get("/api/v1/admin/stats", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["users"]["total"] == 2
    assert data["users"]["admins"] == 1
    assert data["posts"]["normal"] == 1


# ============ 用户管理 ============

def test_disable_enable_user(admin_client, admin_headers, plain_user, db_session):
    # 停用
    resp = admin_client.post(f"/api/v1/admin/users/{plain_user.id}/disable", headers=admin_headers)
    assert resp.status_code == 200
    db_session.refresh(plain_user)
    assert plain_user.is_active is False
    # token_version 递增使旧令牌失效
    assert plain_user.token_version >= 1
    # 启用
    resp = admin_client.post(f"/api/v1/admin/users/{plain_user.id}/enable", headers=admin_headers)
    assert resp.status_code == 200
    db_session.refresh(plain_user)
    assert plain_user.is_active is True


def test_disable_self_rejected(admin_client, admin_headers, admin_user):
    """不能停用当前登录的管理员"""
    resp = admin_client.post(f"/api/v1/admin/users/{admin_user.id}/disable", headers=admin_headers)
    assert resp.status_code == 400
    assert resp.json()["code"] == 40000


def test_reset_password_generated(admin_client, admin_headers, plain_user, db_session):
    resp = admin_client.post(
        f"/api/v1/admin/users/{plain_user.id}/reset-password",
        json={"new_password": None},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["generated"] is True
    assert data["temp_password"]
    db_session.refresh(plain_user)
    assert plain_user.token_version >= 1


def test_reset_password_custom_weak_rejected(admin_client, admin_headers, plain_user):
    """自定义弱密码 → 400"""
    resp = admin_client.post(
        f"/api/v1/admin/users/{plain_user.id}/reset-password",
        json={"new_password": "12345678"},
        headers=admin_headers,
    )
    assert resp.status_code == 400


def test_promote_demote(admin_client, admin_headers, plain_user, admin_user, db_session):
    # 提升
    resp = admin_client.post(f"/api/v1/admin/users/{plain_user.id}/promote", headers=admin_headers)
    assert resp.status_code == 200
    db_session.refresh(plain_user)
    assert plain_user.role == "admin"
    # 现在有两名管理员，降级 plain_user 应成功
    resp = admin_client.post(f"/api/v1/admin/users/{plain_user.id}/demote", headers=admin_headers)
    assert resp.status_code == 200
    db_session.refresh(plain_user)
    assert plain_user.role == "user"


def test_demote_self_rejected(admin_client, admin_headers, admin_user):
    """不能降级自己"""
    resp = admin_client.post(f"/api/v1/admin/users/{admin_user.id}/demote", headers=admin_headers)
    assert resp.status_code == 400


def test_revoke_sessions(admin_client, admin_headers, plain_user, db_session):
    before = plain_user.token_version
    resp = admin_client.post(f"/api/v1/admin/users/{plain_user.id}/revoke-sessions", headers=admin_headers)
    assert resp.status_code == 200
    db_session.refresh(plain_user)
    assert plain_user.token_version > before


# ============ 举报处理 ============

def _make_reported_post(db_session, plain_user):
    post = CommunityPost(user_id=plain_user.id, title="被举报帖", content="x", status="normal")
    db_session.add(post)
    db_session.flush()
    report = ContentReport(user_id=plain_user.id, target_type="post", target_id=post.id, reason="spam", status="pending")
    db_session.add(report)
    db_session.commit()
    return post, report


def test_report_hide(admin_client, admin_headers, plain_user, db_session):
    post, report = _make_reported_post(db_session, plain_user)
    resp = admin_client.post(
        f"/api/v1/admin/reports/{report.id}/handle",
        json={"action": "hide"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    db_session.refresh(post)
    db_session.refresh(report)
    assert post.status == "hidden"
    assert report.status == "handled"


def test_report_delete(admin_client, admin_headers, plain_user, db_session):
    post, report = _make_reported_post(db_session, plain_user)
    resp = admin_client.post(
        f"/api/v1/admin/reports/{report.id}/handle",
        json={"action": "delete"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    db_session.refresh(post)
    db_session.refresh(report)
    assert post.status == "deleted"
    assert report.status == "handled"


def test_report_dismiss(admin_client, admin_headers, plain_user, db_session):
    post, report = _make_reported_post(db_session, plain_user)
    resp = admin_client.post(
        f"/api/v1/admin/reports/{report.id}/handle",
        json={"action": "dismiss"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    db_session.refresh(report)
    assert report.status == "dismissed"
    db_session.refresh(post)
    assert post.status == "normal"  # dismiss 不动目标


# ============ 帖子审核 ============

def test_post_lifecycle(admin_client, admin_headers, plain_user, db_session):
    post = CommunityPost(user_id=plain_user.id, title="t", content="c", status="normal")
    db_session.add(post); db_session.commit()
    # pin
    resp = admin_client.post(f"/api/v1/admin/posts/{post.id}/pin", headers=admin_headers)
    assert resp.status_code == 200
    db_session.refresh(post); assert post.status == "pinned"
    # unpin
    resp = admin_client.post(f"/api/v1/admin/posts/{post.id}/unpin", headers=admin_headers)
    assert resp.status_code == 200
    db_session.refresh(post); assert post.status == "normal"
    # hide (覆盖 pin)
    admin_client.post(f"/api/v1/admin/posts/{post.id}/pin", headers=admin_headers)
    resp = admin_client.post(f"/api/v1/admin/posts/{post.id}/hide", headers=admin_headers)
    assert resp.status_code == 200
    db_session.refresh(post); assert post.status == "hidden"
    # pin hidden 应被拒
    resp = admin_client.post(f"/api/v1/admin/posts/{post.id}/pin", headers=admin_headers)
    assert resp.status_code == 409
    # unhide
    resp = admin_client.post(f"/api/v1/admin/posts/{post.id}/unhide", headers=admin_headers)
    assert resp.status_code == 200
    db_session.refresh(post); assert post.status == "normal"
    # delete
    resp = admin_client.delete(f"/api/v1/admin/posts/{post.id}", headers=admin_headers)
    assert resp.status_code == 200
    db_session.refresh(post); assert post.status == "deleted"


# ============ 岗位分享审核 ============

def test_job_share_lifecycle(admin_client, admin_headers, plain_user, db_session):
    share = CommunityJobShare(user_id=plain_user.id, company="ACME", apply_url="https://acme.com", status="normal")
    db_session.add(share); db_session.commit()
    resp = admin_client.post(f"/api/v1/admin/job-shares/{share.id}/hide", headers=admin_headers)
    assert resp.status_code == 200
    db_session.refresh(share); assert share.status == "hidden"
    resp = admin_client.post(f"/api/v1/admin/job-shares/{share.id}/unhide", headers=admin_headers)
    assert resp.status_code == 200
    db_session.refresh(share); assert share.status == "normal"
    resp = admin_client.delete(f"/api/v1/admin/job-shares/{share.id}", headers=admin_headers)
    assert resp.status_code == 200
    db_session.refresh(share); assert share.status == "deleted"


# ============ 评论删除 ============

def test_comment_delete(admin_client, admin_headers, plain_user, db_session):
    post = CommunityPost(user_id=plain_user.id, title="t", content="c", status="normal", comment_count=1)
    db_session.add(post); db_session.flush()
    comment = PostComment(post_id=post.id, user_id=plain_user.id, content="hi")
    db_session.add(comment); db_session.commit()
    resp = admin_client.delete(f"/api/v1/admin/comments/{comment.id}", headers=admin_headers)
    assert resp.status_code == 200
    assert db_session.get(PostComment, comment.id) is None
    # 帖子评论计数同步
    db_session.refresh(post)
    assert post.comment_count == 0


# ============ 审计日志 ============

def test_audit_log_written(admin_client, admin_headers, plain_user, db_session):
    """管理写操作应留痕审计"""
    admin_client.post(f"/api/v1/admin/users/{plain_user.id}/disable", headers=admin_headers)
    logs = db_session.query(AdminAuditLog).filter(AdminAuditLog.action == "user.disable").all()
    assert len(logs) >= 1
    assert logs[0].target_id == plain_user.id
    # 审计日志只读查询
    resp = admin_client.get("/api/v1/admin/audit-log?action=user.disable", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) >= 1


# ============ 密码强度单测 ============

def test_password_strength():
    assert validate_password_strength("") == "密码不能为空"
    assert validate_password_strength("short") == "密码至少 8 位"
    assert validate_password_strength("12345678") is not None  # 纯数字且在黑名单
    assert validate_password_strength("abc12345") is not None  # 黑名单
    assert validate_password_strength("Abc12345") is not None  # 黑名单（小写后命中）
    assert validate_password_strength("GoodPass99") is None     # 字母+数字，不在黑名单
    assert validate_password_strength("onlyletters") is not None  # 11 位 <12 且无数字 → 不通过
    assert validate_password_strength("longenoughnopair!") is None  # 17 位 ≥12 → 通过
    assert validate_password_strength("has space1") is not None      # 含空白
