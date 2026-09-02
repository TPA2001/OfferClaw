"""
管理后台 API（仅挂载于管理端口，公开端口 8000 无此路由）

两类端点：
1. 自管鉴权：/login、/me、/change-password —— 管理员独立登录，签发更短 TTL 令牌
2. 管理操作：Depends(get_current_admin) —— 校验 role==admin，所有写操作落审计日志

设计要点：
- 管理路由不挂主 app，纵深防御：即便令牌泄露，公开端口也无可触达的管理端点
- 所有写操作调用 _audit() 留痕，便于事后追溯
- disable / reset-password / demote / revoke-sessions 会递增 token_version，使该用户既有会话立即失效
"""

import secrets
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_, func, desc
from sqlalchemy.orm import Session

from app.core.auth import (
    create_access_token,
    get_current_admin,
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.response import ok, APIError
from app.core.rate_limit import rate_limit
from app.models.user import User
from app.models.admin_audit import AdminAuditLog
from app.models.community import (
    CommunityPost,
    CommunityJobShare,
    PostComment,
    ContentReport,
)

logger = logging.getLogger("offercabin.api.admin")

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# ============ 请求模型 ============

class AdminLoginRequest(BaseModel):
    account: str  # 用户名或邮箱
    password: str


class AdminChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class ResetUserPasswordRequest(BaseModel):
    new_password: Optional[str] = None  # 为空则服务端生成临时密码


class ReportHandleRequest(BaseModel):
    action: str  # hide / dismiss / delete
    note: Optional[str] = None


# ============ 辅助函数 ============

def _audit(
    db: Session,
    actor: User,
    action: str,
    target_type: str,
    target_id: Optional[str],
    detail: Optional[str] = None,
) -> None:
    """记录一条管理操作审计日志（由调用方负责 commit）"""
    log = AdminAuditLog(
        actor_id=actor.id,
        actor_username=actor.username,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
    )
    db.add(log)


def _admin_info(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role or "user",
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def _admin_token_payload(user: User) -> dict:
    return {
        "token": create_access_token(
            user.id, user.token_version, ttl_hours=settings.admin_token_ttl_hours
        ),
        "token_type": "bearer",
        "ttl_hours": settings.admin_token_ttl_hours,
        "user": _admin_info(user),
    }


def _user_summary(user: User) -> dict:
    """用户管理列表/详情用（管理员可见 email）"""
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role or "user",
        "is_active": user.is_active,
        "token_version": user.token_version,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def _get_user_or_404(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise APIError(40400, "用户不存在")
    return user


def _get_post_or_404(db: Session, post_id: str) -> CommunityPost:
    post = db.get(CommunityPost, post_id)
    if post is None:
        raise APIError(40400, "帖子不存在")
    return post


def _get_jobshare_or_404(db: Session, jobshare_id: str) -> CommunityJobShare:
    share = db.get(CommunityJobShare, jobshare_id)
    if share is None:
        raise APIError(40400, "岗位分享不存在")
    return share


# ============ 自管鉴权 ============

@router.post("/login")
async def admin_login(
    req: AdminLoginRequest,
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit(5, 60)),
):
    """管理员登录：校验账号密码 + role==admin，签发短 TTL 令牌"""
    account = req.account.strip()
    user = (
        db.query(User)
        .filter(or_(User.username == account, User.email == account.lower()))
        .first()
    )
    # 统一错误文案，避免枚举是否存在管理员账号
    if user is None or not verify_password(req.password, user.password_hash):
        raise APIError(40100, "账号或密码错误")
    if not user.is_active:
        raise APIError(40102, "账号已被停用")
    if (user.role or "user") != "admin":
        raise APIError(40300, "该账号无管理后台权限")

    logger.info(f"管理员登录: {user.username}")
    return ok(_admin_token_payload(user), message="登录成功")


@router.get("/me")
async def admin_me(
    admin_id: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """当前管理员信息"""
    user = _get_user_or_404(db, admin_id)
    return ok(_admin_info(user))


@router.post("/change-password")
async def admin_change_password(
    req: AdminChangePasswordRequest,
    admin_id: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """管理员修改自己的密码（校验旧密码，成功后签发新令牌，旧会话失效）"""
    admin = _get_user_or_404(db, admin_id)
    if not verify_password(req.old_password, admin.password_hash):
        raise APIError(40000, "原密码错误")
    weak_reason = validate_password_strength(req.new_password)
    if weak_reason:
        raise APIError(40000, weak_reason)

    admin.password_hash = hash_password(req.new_password)
    admin.token_version += 1
    _audit(db, admin, "admin.change-password", "user", admin.id, "管理员修改自身密码")
    db.commit()
    db.refresh(admin)

    logger.info(f"管理员修改自身密码: {admin.username}")
    return ok(_admin_token_payload(admin), message="密码已修改，已自动刷新登录状态")


# ============ 仪表盘 ============

@router.get("/stats")
async def stats(
    admin_id: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """仪表盘聚合统计"""
    total_users = db.query(func.count(User.id)).scalar() or 0
    active_users = db.query(func.count(User.id)).filter(User.is_active.is_(True)).scalar() or 0
    admin_users = db.query(func.count(User.id)).filter(User.role == "admin").scalar() or 0

    post_normal = db.query(func.count(CommunityPost.id)).filter(CommunityPost.status == "normal").scalar() or 0
    post_pinned = db.query(func.count(CommunityPost.id)).filter(CommunityPost.status == "pinned").scalar() or 0
    post_hidden = db.query(func.count(CommunityPost.id)).filter(CommunityPost.status == "hidden").scalar() or 0
    post_deleted = db.query(func.count(CommunityPost.id)).filter(CommunityPost.status == "deleted").scalar() or 0

    jobshare_normal = db.query(func.count(CommunityJobShare.id)).filter(CommunityJobShare.status == "normal").scalar() or 0
    jobshare_hidden = db.query(func.count(CommunityJobShare.id)).filter(CommunityJobShare.status == "hidden").scalar() or 0

    pending_reports = db.query(func.count(ContentReport.id)).filter(ContentReport.status == "pending").scalar() or 0
    handled_reports = db.query(func.count(ContentReport.id)).filter(ContentReport.status == "handled").scalar() or 0

    data = {
        "users": {
            "total": total_users,
            "active": active_users,
            "admins": admin_users,
        },
        "posts": {
            "normal": post_normal,
            "pinned": post_pinned,
            "hidden": post_hidden,
            "deleted": post_deleted,
        },
        "job_shares": {
            "normal": jobshare_normal,
            "hidden": jobshare_hidden,
        },
        "reports": {
            "pending": pending_reports,
            "handled": handled_reports,
        },
    }
    return ok(data)


# ============ 用户管理 ============

@router.get("/users")
async def list_users(
    admin_id: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
    q: str = Query("", description="按用户名/邮箱模糊搜索"),
    role: str = Query("", description="user / admin"),
    status: str = Query("", description="active / disabled"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """用户列表（管理员可见 email 与角色）"""
    query = db.query(User)
    kw = q.strip()
    if kw:
        query = query.filter(or_(User.username.contains(kw), User.email.contains(kw)))
    if role in ("user", "admin"):
        query = query.filter(User.role == role)
    if status == "active":
        query = query.filter(User.is_active.is_(True))
    elif status == "disabled":
        query = query.filter(User.is_active.is_(False))

    total = query.count()
    rows = (
        query.order_by(desc(User.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ok(
        [_user_summary(u) for u in rows],
        message="OK",
        extra={"total": total, "page": page, "page_size": page_size},
    )


@router.post("/users/{user_id}/disable")
async def disable_user(
    user_id: str,
    admin_id: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """停用用户（token_version+1，既有会话立即失效）"""
    admin = _get_user_or_404(db, admin_id)
    user = _get_user_or_404(db, user_id)
    if user.id == admin.id:
        raise APIError(40000, "不能停用当前登录的管理员账号")
    if not user.is_active:
        return ok(message="该账号已处于停用状态")
    user.is_active = False
    user.token_version += 1
    _audit(db, admin, "user.disable", "user", user.id, f"username={user.username}")
    db.commit()
    return ok(message=f"已停用账号 {user.username}")


@router.post("/users/{user_id}/enable")
async def enable_user(
    user_id: str,
    admin_id: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """启用用户"""
    admin = _get_user_or_404(db, admin_id)
    user = _get_user_or_404(db, user_id)
    if user.is_active:
        return ok(message="该账号已处于启用状态")
    user.is_active = True
    _audit(db, admin, "user.enable", "user", user.id, f"username={user.username}")
    db.commit()
    return ok(message=f"已启用账号 {user.username}")


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: str,
    req: ResetUserPasswordRequest,
    admin_id: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """管理员重置用户密码

    new_password 为空时服务端生成临时口令并随响应返回（仅管理员可见）；
    成功后 token_version+1，用户既有会话全部失效。
    """
    admin = _get_user_or_404(db, admin_id)
    user = _get_user_or_404(db, user_id)

    if req.new_password:
        weak_reason = validate_password_strength(req.new_password)
        if weak_reason:
            raise APIError(40000, weak_reason)
        new_pwd = req.new_password
        generated = False
    else:
        new_pwd = secrets.token_urlsafe(12)
        generated = True

    user.password_hash = hash_password(new_pwd)
    user.token_version += 1
    _audit(db, admin, "user.reset-password", "user", user.id, f"username={user.username}, generated={generated}")
    db.commit()

    data = {"generated": generated}
    if generated:
        data["temp_password"] = new_pwd
    return ok(data, message=f"已重置 {user.username} 的密码")


@router.post("/users/{user_id}/promote")
async def promote_user(
    user_id: str,
    admin_id: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """提升为管理员"""
    admin = _get_user_or_404(db, admin_id)
    user = _get_user_or_404(db, user_id)
    if (user.role or "user") == "admin":
        return ok(message="该账号已是管理员")
    user.role = "admin"
    _audit(db, admin, "user.promote", "user", user.id, f"username={user.username}")
    db.commit()
    return ok(message=f"已将 {user.username} 提升为管理员")


@router.post("/users/{user_id}/demote")
async def demote_user(
    user_id: str,
    admin_id: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """取消管理员角色

    守卫：不可降级自己；不可降级最后一名管理员（避免无人可管）。
    """
    admin = _get_user_or_404(db, admin_id)
    user = _get_user_or_404(db, user_id)
    if user.id == admin.id:
        raise APIError(40000, "不能降级当前登录的管理员账号")
    if (user.role or "user") != "admin":
        return ok(message="该账号并非管理员")
    admin_count = db.query(func.count(User.id)).filter(User.role == "admin", User.is_active.is_(True)).scalar() or 0
    if admin_count <= 1:
        raise APIError(40900, "系统至少需保留一名管理员，无法降级")

    user.role = "user"
    user.token_version += 1  # 收回管理权限的同时使其既有令牌失效
    _audit(db, admin, "user.demote", "user", user.id, f"username={user.username}")
    db.commit()
    return ok(message=f"已取消 {user.username} 的管理员角色")


@router.post("/users/{user_id}/revoke-sessions")
async def revoke_user_sessions(
    user_id: str,
    admin_id: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """强制下线用户（token_version+1，既有令牌立即失效）"""
    admin = _get_user_or_404(db, admin_id)
    user = _get_user_or_404(db, user_id)
    user.token_version += 1
    _audit(db, admin, "user.revoke-sessions", "user", user.id, f"username={user.username}")
    db.commit()
    return ok(message=f"已强制 {user.username} 的所有会话下线")


# ============ 内容举报 ============

def _report_target_summary(report: ContentReport, db: Session) -> dict:
    """联表取举报目标摘要"""
    if report.target_type == "post":
        target = db.get(CommunityPost, report.target_id)
        return {
            "title": target.title if target else None,
            "status": target.status if target else None,
            "missing": target is None,
        }
    if report.target_type == "jobshare":
        target = db.get(CommunityJobShare, report.target_id)
        return {
            "company": target.company if target else None,
            "position": target.position if target else None,
            "status": target.status if target else None,
            "missing": target is None,
        }
    return {"status": None, "missing": True}


def _report_info(report: ContentReport, db: Session) -> dict:
    return {
        "id": report.id,
        "user_id": report.user_id,
        "target_type": report.target_type,
        "target_id": report.target_id,
        "reason": report.reason,
        "status": report.status,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "target": _report_target_summary(report, db),
    }


@router.get("/reports")
async def list_reports(
    admin_id: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
    status: str = Query("pending", description="pending / handled / dismissed / all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """举报列表"""
    query = db.query(ContentReport)
    if status != "all":
        query = query.filter(ContentReport.status == status)
    total = query.count()
    rows = (
        query.order_by(desc(ContentReport.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ok(
        [_report_info(r, db) for r in rows],
        message="OK",
        extra={"total": total, "page": page, "page_size": page_size},
    )


@router.post("/reports/{report_id}/handle")
async def handle_report(
    report_id: str,
    req: ReportHandleRequest,
    admin_id: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """处理举报

    action=hide    → 目标 status=hidden，举报 status=handled
    action=delete  → 目标 status=deleted，举报 status=handled
    action=dismiss → 举报 status=dismissed（目标不动）
    """
    admin = _get_user_or_404(db, admin_id)
    report = db.get(ContentReport, report_id)
    if report is None:
        raise APIError(40400, "举报记录不存在")

    action = (req.action or "").strip().lower()
    if action not in ("hide", "delete", "dismiss"):
        raise APIError(40000, "action 需为 hide / delete / dismiss")

    detail_parts = [f"report={report_id}", f"action={action}"]
    if req.note:
        detail_parts.append(f"note={req.note}")

    if action == "dismiss":
        report.status = "dismissed"
        _audit(db, admin, "report.dismiss", "report", report_id, ", ".join(detail_parts))
        db.commit()
        return ok(message="已驳回该举报")

    # hide / delete 需操作目标
    if report.target_type == "post":
        target = db.get(CommunityPost, report.target_id)
        if target is None:
            raise APIError(40400, "举报目标帖子已不存在")
        target.status = "hidden" if action == "hide" else "deleted"
        _audit(db, admin, f"report.{action}", "post", target.id, ", ".join(detail_parts))
    elif report.target_type == "jobshare":
        target = db.get(CommunityJobShare, report.target_id)
        if target is None:
            raise APIError(40400, "举报目标岗位分享已不存在")
        target.status = "hidden" if action == "hide" else "deleted"
        _audit(db, admin, f"report.{action}", "jobshare", target.id, ", ".join(detail_parts))
    else:
        raise APIError(40000, f"未知的举报目标类型: {report.target_type}")

    report.status = "handled"
    db.commit()
    return ok(message="举报已处理")


# ============ 帖子审核 ============

def _post_info(post: CommunityPost) -> dict:
    return {
        "id": post.id,
        "user_id": post.user_id,
        "title": post.title,
        "category": post.category,
        "status": post.status,
        "view_count": post.view_count,
        "like_count": post.like_count,
        "comment_count": post.comment_count,
        "created_at": post.created_at.isoformat() if post.created_at else None,
    }


@router.get("/posts")
async def list_posts(
    admin_id: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
    status: str = Query("", description="normal / pinned / hidden / deleted / all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """帖子列表（含 hidden/deleted）"""
    query = db.query(CommunityPost)
    if status and status != "all":
        query = query.filter(CommunityPost.status == status)
    total = query.count()
    rows = (
        query.order_by(desc(CommunityPost.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ok(
        [_post_info(p) for p in rows],
        message="OK",
        extra={"total": total, "page": page, "page_size": page_size},
    )


@router.post("/posts/{post_id}/hide")
async def hide_post(
    post_id: str,
    admin_id: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """隐藏帖子（hide 覆盖 pin）"""
    admin = _get_user_or_404(db, admin_id)
    post = _get_post_or_404(db, post_id)
    prev_status = post.status
    post.status = "hidden"
    _audit(db, admin, "post.hide", "post", post.id, f"prev_status={prev_status}")
    db.commit()
    return ok(message=f"已隐藏帖子「{post.title}」")


@router.post("/posts/{post_id}/unhide")
async def unhide_post(
    post_id: str,
    admin_id: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """取消隐藏（恢复为 normal）"""
    admin = _get_user_or_404(db, admin_id)
    post = _get_post_or_404(db, post_id)
    prev_status = post.status
    post.status = "normal"
    _audit(db, admin, "post.unhide", "post", post.id, f"prev_status={prev_status}")
    db.commit()
    return ok(message=f"已恢复帖子「{post.title}」")


@router.post("/posts/{post_id}/pin")
async def pin_post(
    post_id: str,
    admin_id: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """置顶帖子（与 hide 互斥：hidden 状态需先取消隐藏）"""
    admin = _get_user_or_404(db, admin_id)
    post = _get_post_or_404(db, post_id)
    if post.status == "hidden":
        raise APIError(40900, "该帖子处于隐藏状态，请先取消隐藏再置顶")
    if post.status == "deleted":
        raise APIError(40900, "该帖子已被删除，无法置顶")
    prev_status = post.status
    post.status = "pinned"
    _audit(db, admin, "post.pin", "post", post.id, f"prev_status={prev_status}")
    db.commit()
    return ok(message=f"已置顶帖子「{post.title}」")


@router.post("/posts/{post_id}/unpin")
async def unpin_post(
    post_id: str,
    admin_id: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """取消置顶（恢复为 normal）"""
    admin = _get_user_or_404(db, admin_id)
    post = _get_post_or_404(db, post_id)
    prev_status = post.status
    post.status = "normal"
    _audit(db, admin, "post.unpin", "post", post.id, f"prev_status={prev_status}")
    db.commit()
    return ok(message=f"已取消置顶帖子「{post.title}」")


@router.delete("/posts/{post_id}")
async def delete_post(
    post_id: str,
    admin_id: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """删除帖子（软删，status=deleted）"""
    admin = _get_user_or_404(db, admin_id)
    post = _get_post_or_404(db, post_id)
    prev_status = post.status
    post.status = "deleted"
    _audit(db, admin, "post.delete", "post", post.id, f"prev_status={prev_status}, title={post.title}")
    db.commit()
    return ok(message=f"已删除帖子「{post.title}」")


# ============ 岗位分享审核 ============

def _jobshare_info(share: CommunityJobShare) -> dict:
    return {
        "id": share.id,
        "user_id": share.user_id,
        "company": share.company,
        "position": share.position,
        "category": share.category,
        "city": share.city,
        "salary": share.salary,
        "status": share.status,
        "view_count": share.view_count,
        "click_count": share.click_count,
        "like_count": share.like_count,
        "created_at": share.created_at.isoformat() if share.created_at else None,
    }


@router.get("/job-shares")
async def list_job_shares(
    admin_id: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
    status: str = Query("", description="normal / hidden / deleted / expired / all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """岗位分享列表"""
    query = db.query(CommunityJobShare)
    if status and status != "all":
        query = query.filter(CommunityJobShare.status == status)
    total = query.count()
    rows = (
        query.order_by(desc(CommunityJobShare.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ok(
        [_jobshare_info(s) for s in rows],
        message="OK",
        extra={"total": total, "page": page, "page_size": page_size},
    )


@router.post("/job-shares/{jobshare_id}/hide")
async def hide_job_share(
    jobshare_id: str,
    admin_id: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """隐藏岗位分享"""
    admin = _get_user_or_404(db, admin_id)
    share = _get_jobshare_or_404(db, jobshare_id)
    prev_status = share.status
    share.status = "hidden"
    _audit(db, admin, "jobshare.hide", "jobshare", share.id, f"prev_status={prev_status}, company={share.company}")
    db.commit()
    return ok(message=f"已隐藏「{share.company}」的岗位分享")


@router.post("/job-shares/{jobshare_id}/unhide")
async def unhide_job_share(
    jobshare_id: str,
    admin_id: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """取消隐藏岗位分享"""
    admin = _get_user_or_404(db, admin_id)
    share = _get_jobshare_or_404(db, jobshare_id)
    prev_status = share.status
    share.status = "normal"
    _audit(db, admin, "jobshare.unhide", "jobshare", share.id, f"prev_status={prev_status}")
    db.commit()
    return ok(message=f"已恢复「{share.company}」的岗位分享")


@router.delete("/job-shares/{jobshare_id}")
async def delete_job_share(
    jobshare_id: str,
    admin_id: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """删除岗位分享（软删）"""
    admin = _get_user_or_404(db, admin_id)
    share = _get_jobshare_or_404(db, jobshare_id)
    prev_status = share.status
    share.status = "deleted"
    _audit(db, admin, "jobshare.delete", "jobshare", share.id, f"prev_status={prev_status}, company={share.company}")
    db.commit()
    return ok(message=f"已删除「{share.company}」的岗位分享")


# ============ 评论管理 ============

@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: str,
    admin_id: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """删除评论（硬删，与社区现有删除一致）"""
    admin = _get_user_or_404(db, admin_id)
    comment = db.get(PostComment, comment_id)
    if comment is None:
        raise APIError(40400, "评论不存在")

    # 软删所属帖子的评论计数同步
    post = db.get(CommunityPost, comment.post_id)
    if post and post.comment_count and post.comment_count > 0:
        post.comment_count -= 1

    db.delete(comment)
    _audit(db, admin, "comment.delete", "comment", comment_id, f"post_id={comment.post_id}")
    db.commit()
    return ok(message="已删除评论")


# ============ 审计日志 ============

def _audit_info(log: AdminAuditLog) -> dict:
    return {
        "id": log.id,
        "actor_id": log.actor_id,
        "actor_username": log.actor_username,
        "action": log.action,
        "target_type": log.target_type,
        "target_id": log.target_id,
        "detail": log.detail,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


@router.get("/audit-log")
async def list_audit_log(
    admin_id: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
    action: str = Query("", description="按 action 过滤，如 user.disable"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """审计日志（只读）"""
    query = db.query(AdminAuditLog)
    if action:
        query = query.filter(AdminAuditLog.action == action)
    total = query.count()
    rows = (
        query.order_by(desc(AdminAuditLog.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ok(
        [_audit_info(r) for r in rows],
        message="OK",
        extra={"total": total, "page": page, "page_size": page_size},
    )
