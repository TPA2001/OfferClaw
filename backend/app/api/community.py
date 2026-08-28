"""
社区 + 岗位分享 REST API

社区（求职广场）：帖子 CRUD + 楼中楼评论 + 点赞/收藏 + 举报
岗位分享（网申广场）：分享 CRUD + 一键跳转官网 + 一键加入看板 + 举报

安全设计（售卖场景硬要求）：
- 链接校验：仅 http/https、拒绝本机/内网域名与危险协议（防钓鱼/防 SSRF 式跳转）
- 用户级限流：发帖/评论/分享/举报按 user_id 滑动窗口限流（防刷）
- AI 预审：LLM 判断违规内容，命中自动隐藏（作者可见、他人不可见）；Mock/异常降级放行
- 举报阈值：同一内容举报达阈值自动隐藏
- 权限：仅作者可编辑/删除自己的内容
- 防注入：LIKE 搜索转义 % _ \\；分页上限；内容长度限制
- 隐私：对外只暴露用户名，不暴露邮箱/手机号等
"""
import json
import logging
import re
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from threading import Lock
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.response import (
    ok,
    BadRequestError,
    NotFoundError,
    ForbiddenError,
    ConflictError,
    RateLimitError,
)
from app.models.community import (
    CommunityPost,
    PostComment,
    CommunityJobShare,
    UserReaction,
    ContentReport,
)
from app.models.application import Application
from app.models.user import User

logger = logging.getLogger("offerclaw.api.community")

router = APIRouter(prefix="/api/v1/community", tags=["community"])


# ============ 常量 ============

POST_CATEGORIES = {
    "resume": "简历优化",
    "interview": "面试经验",
    "offer": "Offer 抉择",
    "help": "求职求助",
    "chat": "闲聊",
}

VALID_TARGET_TYPES = ("post", "jobshare")
VALID_ACTIONS = ("like", "collect")

# 举报隐藏阈值：同一内容 pending 举报数达到该值自动隐藏
REPORT_HIDE_THRESHOLD = 3

# 内容长度限制（字符）
TITLE_MAX = 100
POST_CONTENT_MAX = 5000
COMMENT_MAX = 2000
JOB_COMPANY_MAX = 200
JOB_POSITION_MAX = 200
JOB_DESC_MAX = 2000
REPORT_REASON_MAX = 200

# 分页上限
PAGE_SIZE_MAX = 50

# 热帖/热岗位排序权重（热度 = like*3 + comment*5 + view*0.1，岗位无 comment 用 collect 代替）
HOT_LIKE_WEIGHT = 3
HOT_COMMENT_WEIGHT = 5
HOT_COLLECT_WEIGHT = 4
HOT_VIEW_WEIGHT = 0.1

# ============ 安全：链接校验 ============

# 禁止的协议（防 javascript:/data: 等注入）
_BLOCKED_SCHEMES = {"javascript", "data", "vbscript", "file", "about", "blob"}
# 本机/内网域名黑名单（防钓鱼跳转回本地/内网地址）
_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "[::1]", "::1"}
# 内网 IP 段正则（IPv4）
_PRIVATE_IP_RE = re.compile(
    r"^(127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)"
)
# 仅允许公网 http/https 链接
ALLOWED_SCHEMES = {"http", "https"}


def validate_apply_url(url: str) -> str:
    """校验网申链接安全性，返回规范化后的 URL；不合法抛 BadRequestError

    规则：
    1. 必须能被 urlparse 解析，且 scheme ∈ {http, https}
    2. 必须有主机名
    3. 主机名不得为本机/内网（含 IP 直连与 localhost）
    4. 长度限制（防御超大 payload）
    """
    if not url or not url.strip():
        raise BadRequestError("网申链接不能为空")
    url = url.strip()
    if len(url) > 2048:
        raise BadRequestError("链接过长")
    try:
        parsed = urlparse(url)
    except ValueError:
        raise BadRequestError("链接格式无效")
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise BadRequestError("仅支持 http/https 链接")
    host = (parsed.hostname or "").lower()
    if not host:
        raise BadRequestError("链接缺少域名")
    # 去掉常见端口写法里的括号/末尾点
    host = host.rstrip(".")
    # IPv6 / IP 直连一律拒绝（网申链接不会用 IP 直连）
    if ":" in host:
        raise BadRequestError("不允许 IP 直连链接")
    if host in _BLOCKED_HOSTS:
        raise BadRequestError("不允许分享本机或内网链接")
    if _PRIVATE_IP_RE.match(host):
        raise BadRequestError("不允许分享内网链接")
    return url


# ============ 安全：用户级限流 ============

class _UserActionLimiter:
    """按 user_id + action 的内存滑动窗口限流器

    与 core/rate_limit 的区别：key 基于用户而非 IP+路径，
    适合对"单用户高频写操作"（发帖/评论/分享/举报）限流。
    单实例部署足够；多实例需换共享存储。
    """

    def __init__(self):
        self._lock = Lock()
        self._buckets: dict[str, deque] = defaultdict(deque)

    def hit(self, key: str, limit: int, window: int) -> bool:
        now = time.time()
        cutoff = now - window
        with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True

    def reset(self):
        """清空计数（仅供测试）"""
        with self._lock:
            self._buckets.clear()


# 全局单例
_action_limiter = _UserActionLimiter()

# 限流阈值（次/60 秒）
RATE_LIMITS = {
    "post": 5,
    "comment": 20,
    "jobshare": 5,
    "report": 10,
}


def _check_rate(user_id: str, action: str) -> None:
    """写操作限流，超限抛 429"""
    limit = RATE_LIMITS.get(action, 10)
    key = f"{user_id}:{action}"
    if not _action_limiter.hit(key, limit, 60):
        raise RateLimitError("操作过于频繁，请稍后再试")


# ============ 安全：AI 预审 ============

async def _ai_precheck(title: str, content: str) -> bool:
    """内容安全预审：返回 True=放行，False=命中违规（转 hidden）

    设计原则：任何异常（超时/无 Key/解析失败）一律降级放行，
    绝不因审核故障阻塞用户发布。Mock 模式下直接放行。
    """
    try:
        from app.core.llm import get_gen_provider, Message
        provider = get_gen_provider()
        if provider.name == "mock":
            return True
        prompt = (
            "你是求职社区的内容安全审核员。判断以下内容是否包含：违法违规、色情低俗、"
            "暴力、赌博、诈骗、广告营销（如兜售账号/简历代做/加微信）、仇恨或歧视言论、"
            "人身攻击。仅回复 JSON：{\"pass\": true或false, \"reason\": \"原因\"}。\n"
            f"标题：{title}\n内容：{content[:1500]}"
        )
        resp = await provider.chat(
            messages=[Message(role="user", content=prompt)],
            temperature=0.0,
            max_tokens=120,
        )
        text = (resp.content or "").strip()
        # 提取 JSON（兼容 ```json 包裹）
        if "{" in text:
            text = text[text.index("{"): text.rindex("}") + 1]
        data = json.loads(text)
        return bool(data.get("pass", True))
    except Exception:
        logger.debug("AI 预审降级放行", exc_info=True)
        return True


# ============ 工具函数 ============

def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        raise BadRequestError(f"时间格式无效: {s}")
    # 统一转 UTC aware：naive 视为 UTC（与 func.now() 一致），
    # 保证 SQLite 字符串比较格式一致，避免时区错乱
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _escape_like(s: str) -> str:
    """转义 LIKE 通配符，防止 SQL 注入/通配符滥用"""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _user_names(db: Session, user_ids: set) -> dict:
    """批量取用户名（对外仅暴露 username）"""
    if not user_ids:
        return {}
    rows = db.query(User.id, User.username).filter(User.id.in_(list(user_ids))).all()
    return {r[0]: r[1] for r in rows}


def _my_reactions(db: Session, user_id: str, target_type: str, target_ids: list) -> dict:
    """返回当前用户对各目标的 reaction 集合: {target_id: {"like": bool, "collect": bool}}"""
    out: dict = {}
    if not target_ids:
        return out
    rows = db.query(UserReaction.target_id, UserReaction.action).filter(
        UserReaction.user_id == user_id,
        UserReaction.target_type == target_type,
        UserReaction.target_id.in_(target_ids),
    ).all()
    for tid, action in rows:
        out.setdefault(tid, {})[action] = True
    return out


def _target_or_404(db: Session, target_type: str, target_id: str):
    """取目标内容（帖子/岗位），deleted 视为不存在"""
    if target_type == "post":
        obj = db.get(CommunityPost, target_id)
    else:
        obj = db.get(CommunityJobShare, target_id)
    if obj is None or obj.status == "deleted":
        raise NotFoundError("内容不存在")
    return obj


def _apply_reaction_counts(obj, action: str, add: bool) -> None:
    """按 reaction 变更同步冗余计数（like/collect 互不影响）"""
    if action == "like":
        obj.like_count = max(0, (obj.like_count or 0) + (1 if add else -1))
    else:
        obj.collect_count = max(0, (obj.collect_count or 0) + (1 if add else -1))


def _maybe_hide_by_reports(db: Session, target_type: str, target_id: str) -> bool:
    """举报达阈值 → 隐藏内容；返回是否隐藏"""
    cnt = db.query(ContentReport).filter(
        ContentReport.target_type == target_type,
        ContentReport.target_id == target_id,
        ContentReport.status == "pending",
    ).count()
    if cnt >= REPORT_HIDE_THRESHOLD:
        obj = _target_or_404(db, target_type, target_id)
        if obj.status == "normal":
            obj.status = "hidden"
            db.commit()
        return True
    return False


# ============ Schemas ============

class PostCreate(BaseModel):
    title: str
    content: str
    category: str = "chat"


class PostUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None


class CommentCreate(BaseModel):
    content: str
    parent_id: Optional[str] = None


class JobShareCreate(BaseModel):
    company: str
    position: str
    apply_url: str
    city: Optional[str] = None
    salary: Optional[str] = None
    deadline: Optional[str] = None
    description: Optional[str] = None


class JobShareUpdate(BaseModel):
    company: Optional[str] = None
    position: Optional[str] = None
    apply_url: Optional[str] = None
    city: Optional[str] = None
    salary: Optional[str] = None
    deadline: Optional[str] = None
    description: Optional[str] = None


class ReactionBody(BaseModel):
    target_type: str
    target_id: str
    action: str
    value: bool = True


class ReportBody(BaseModel):
    target_type: str
    target_id: str
    reason: Optional[str] = None


# ============ 序列化 ============

def _serialize_post(post: CommunityPost, username: str, my: dict = None) -> dict:
    return {
        "id": post.id,
        "title": post.title,
        "category": post.category,
        "category_label": POST_CATEGORIES.get(post.category, post.category),
        "status": post.status,
        "author_id": post.user_id,
        "author": username or "匿名",
        "view_count": post.view_count,
        "like_count": post.like_count,
        "comment_count": post.comment_count,
        "collect_count": post.collect_count,
        "content": post.content,
        "is_pinned": post.status == "pinned",
        "liked": bool(my and my.get("like")),
        "collected": bool(my and my.get("collect")),
        "created_at": _iso(post.created_at),
        "updated_at": _iso(post.updated_at),
    }


def _serialize_comment(c: PostComment, username: str) -> dict:
    return {
        "id": c.id,
        "post_id": c.post_id,
        "parent_id": c.parent_id,
        "author": username or "匿名",
        "content": c.content,
        "created_at": _iso(c.created_at),
    }


def _serialize_job(job: CommunityJobShare, username: str, my: dict = None) -> dict:
    return {
        "id": job.id,
        "company": job.company,
        "position": job.position,
        "apply_url": job.apply_url,
        "city": job.city,
        "salary": job.salary,
        "deadline": _iso(job.deadline),
        "description": job.description,
        "status": job.status,
        "author_id": job.user_id,
        "author": username or "匿名",
        "view_count": job.view_count,
        "click_count": job.click_count,
        "like_count": job.like_count,
        "collect_count": job.collect_count,
        "liked": bool(my and my.get("like")),
        "collected": bool(my and my.get("collect")),
        "created_at": _iso(job.created_at),
        "updated_at": _iso(job.updated_at),
    }


# =====================================================================
# 社区帖子
# =====================================================================

@router.post("/posts")
async def create_post(
    body: PostCreate,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """发帖（限流 + AI 预审；命中违规自动 hidden，作者本人可见）"""
    title = (body.title or "").strip()
    content = (body.content or "").strip()
    if not title:
        raise BadRequestError("标题不能为空")
    if len(title) > TITLE_MAX:
        raise BadRequestError(f"标题不能超过 {TITLE_MAX} 字")
    if not content:
        raise BadRequestError("内容不能为空")
    if len(content) > POST_CONTENT_MAX:
        raise BadRequestError(f"内容不能超过 {POST_CONTENT_MAX} 字")
    if body.category not in POST_CATEGORIES:
        raise BadRequestError(f"无效板块: {body.category}")
    _check_rate(user_id, "post")

    passed = await _ai_precheck(title, content)
    post = CommunityPost(
        id=str(uuid.uuid4()),
        user_id=user_id,
        title=title,
        content=content,
        category=body.category,
        status="normal" if passed else "hidden",
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    username = _user_names(db, {user_id}).get(user_id, "")
    return ok(
        _serialize_post(post, username),
        message="发布成功" if passed else "内容审核中，通过后将对其他用户可见",
    )


@router.get("/posts")
async def list_posts(
    category: Optional[str] = Query(None),
    sort: str = Query("newest", pattern="^(newest|hot)$"),
    keyword: Optional[str] = Query(None, max_length=50),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=PAGE_SIZE_MAX),
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """帖子列表：板块筛选 + 最新/最热排序 + 关键词搜索"""
    q = db.query(CommunityPost).filter(
        CommunityPost.status.in_(["normal", "pinned"])
    )
    if category:
        if category not in POST_CATEGORIES:
            raise BadRequestError(f"无效板块: {category}")
        q = q.filter(CommunityPost.category == category)
    if keyword:
        kw = _escape_like(keyword)
        q = q.filter(or_(
            CommunityPost.title.like(f"%{kw}%", escape="\\"),
            CommunityPost.content.like(f"%{kw}%", escape="\\"),
        ))

    total = q.count()
    if sort == "hot":
        q = q.order_by(
            CommunityPost.status != "pinned",
            (
                CommunityPost.like_count * HOT_LIKE_WEIGHT
                + CommunityPost.comment_count * HOT_COMMENT_WEIGHT
                + CommunityPost.view_count * HOT_VIEW_WEIGHT
            ).desc(),
            CommunityPost.created_at.desc(),
        )
    else:
        q = q.order_by(
            CommunityPost.status != "pinned",
            CommunityPost.created_at.desc(),
        )
    items = q.offset((page - 1) * page_size).limit(page_size).all()

    names = _user_names(db, {p.user_id for p in items})
    my = _my_reactions(db, user_id, "post", [p.id for p in items])
    return ok({
        "items": [_serialize_post(p, names.get(p.user_id, ""), my.get(p.id)) for p in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.get("/posts/{post_id}")
async def get_post(
    post_id: str,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """帖子详情（浏览 +1；hidden 内容仅作者可见）"""
    post = db.get(CommunityPost, post_id)
    if post is None or post.status == "deleted":
        raise NotFoundError("帖子不存在")
    if post.status == "hidden" and post.user_id != user_id:
        raise NotFoundError("帖子不存在")

    # 浏览计数（5 分钟窗口防刷：以内存 set 记录）
    _bump_view(db, post, "post", user_id)

    names = _user_names(db, {post.user_id})
    my = _my_reactions(db, user_id, "post", [post.id]).get(post.id)
    return ok(_serialize_post(post, names.get(post.user_id, ""), my))


# 浏览防刷窗口（内存；key: user:{type}:{id} -> set[user_id]）
_VIEW_WINDOW_SECONDS = 300
_view_seen: dict = defaultdict(set)
_view_seen_ts: dict = {}


def _bump_view(db: Session, obj, target_type: str, user_id: str) -> None:
    """浏览 +1（同一用户 5 分钟窗口内只计一次）"""
    now = time.time()
    key = f"{user_id}:{target_type}:{obj.id}"
    if _view_seen_ts.get(key, 0) > now - _VIEW_WINDOW_SECONDS:
        return
    _view_seen_ts[key] = now
    obj.view_count = (obj.view_count or 0) + 1
    db.commit()


@router.put("/posts/{post_id}")
async def update_post(
    post_id: str,
    body: PostUpdate,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """编辑帖子（仅作者；编辑后重新预审）"""
    post = db.get(CommunityPost, post_id)
    if post is None or post.status == "deleted":
        raise NotFoundError("帖子不存在")
    if post.user_id != user_id:
        raise ForbiddenError("只能编辑自己发布的帖子")

    if body.title is not None:
        title = body.title.strip()
        if not title:
            raise BadRequestError("标题不能为空")
        if len(title) > TITLE_MAX:
            raise BadRequestError(f"标题不能超过 {TITLE_MAX} 字")
        post.title = title
    if body.content is not None:
        content = body.content.strip()
        if not content:
            raise BadRequestError("内容不能为空")
        if len(content) > POST_CONTENT_MAX:
            raise BadRequestError(f"内容不能超过 {POST_CONTENT_MAX} 字")
        post.content = content
    if body.category is not None:
        if body.category not in POST_CATEGORIES:
            raise BadRequestError(f"无效板块: {body.category}")
        post.category = body.category

    # 编辑后重新预审；曾违规的帖子编辑后自动恢复可见
    passed = await _ai_precheck(post.title, post.content)
    if post.status == "hidden" and passed:
        post.status = "normal"
    elif not passed:
        post.status = "hidden"

    db.commit()
    db.refresh(post)
    names = _user_names(db, {post.user_id})
    my = _my_reactions(db, user_id, "post", [post.id]).get(post.id)
    return ok(_serialize_post(post, names.get(post.user_id, ""), my))


@router.delete("/posts/{post_id}")
async def delete_post(
    post_id: str,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除帖子（软删，仅作者）"""
    post = db.get(CommunityPost, post_id)
    if post is None or post.status == "deleted":
        raise NotFoundError("帖子不存在")
    if post.user_id != user_id:
        raise ForbiddenError("只能删除自己发布的帖子")
    post.status = "deleted"
    db.commit()
    return ok({"id": post_id}, message="已删除")


# ============ 评论 ============

@router.post("/posts/{post_id}/comments")
async def create_comment(
    post_id: str,
    body: CommentCreate,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """评论帖子（支持楼中楼 parent_id）"""
    post = db.get(CommunityPost, post_id)
    if post is None or post.status == "deleted":
        raise NotFoundError("帖子不存在")
    if post.status == "hidden" and post.user_id != user_id:
        raise NotFoundError("帖子不存在")

    content = (body.content or "").strip()
    if not content:
        raise BadRequestError("评论内容不能为空")
    if len(content) > COMMENT_MAX:
        raise BadRequestError(f"评论不能超过 {COMMENT_MAX} 字")

    parent_id = None
    if body.parent_id:
        parent = db.get(PostComment, body.parent_id)
        if parent is None or parent.post_id != post_id:
            raise BadRequestError("回复的评论不存在")
        parent_id = parent.id
    _check_rate(user_id, "comment")

    comment = PostComment(
        id=str(uuid.uuid4()),
        post_id=post_id,
        user_id=user_id,
        content=content,
        parent_id=parent_id,
    )
    db.add(comment)
    post.comment_count = (post.comment_count or 0) + 1
    db.commit()
    db.refresh(comment)
    names = _user_names(db, {user_id})
    return ok(_serialize_comment(comment, names.get(user_id, "")), message="评论成功")


@router.get("/posts/{post_id}/comments")
async def list_comments(
    post_id: str,
    limit: int = Query(200, ge=1, le=500),
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """评论列表（按时间正序，含楼中楼 parent_id 供前端缩进）"""
    post = db.get(CommunityPost, post_id)
    if post is None or post.status == "deleted":
        raise NotFoundError("帖子不存在")
    if post.status == "hidden" and post.user_id != user_id:
        raise NotFoundError("帖子不存在")

    rows = db.query(PostComment).filter(
        PostComment.post_id == post_id,
    ).order_by(PostComment.created_at.asc()).limit(limit).all()
    names = _user_names(db, {c.user_id for c in rows})
    return ok({
        "items": [_serialize_comment(c, names.get(c.user_id, "")) for c in rows],
        "total": len(rows),
    })


@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: str,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除评论（仅作者；级联删除其下楼中楼回复）"""
    comment = db.get(PostComment, comment_id)
    if comment is None:
        raise NotFoundError("评论不存在")
    if comment.user_id != user_id:
        raise ForbiddenError("只能删除自己的评论")

    # 级联删除该评论的楼中楼回复
    replies = db.query(PostComment).filter(
        PostComment.parent_id == comment_id,
    ).all()
    for r in replies:
        db.delete(r)
    db.delete(comment)

    # 同步帖子评论数（减去本评论 + 回复数）
    post = db.get(CommunityPost, comment.post_id)
    if post is not None:
        post.comment_count = max(0, (post.comment_count or 0) - 1 - len(replies))
    db.commit()
    return ok({"id": comment_id}, message="已删除")


# =====================================================================
# 岗位分享
# =====================================================================

@router.post("/job-shares")
async def create_job_share(
    body: JobShareCreate,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """分享岗位（限流 + 链接校验 + AI 预审）"""
    company = (body.company or "").strip()
    position = (body.position or "").strip()
    if not company:
        raise BadRequestError("公司名不能为空")
    if len(company) > JOB_COMPANY_MAX:
        raise BadRequestError(f"公司名不能超过 {JOB_COMPANY_MAX} 字")
    if not position:
        raise BadRequestError("岗位名不能为空")
    if len(position) > JOB_POSITION_MAX:
        raise BadRequestError(f"岗位名不能超过 {JOB_POSITION_MAX} 字")
    apply_url = validate_apply_url(body.apply_url)
    deadline = _parse_dt(body.deadline)
    description = (body.description or "").strip() or None
    if description and len(description) > JOB_DESC_MAX:
        raise BadRequestError(f"备注不能超过 {JOB_DESC_MAX} 字")
    _check_rate(user_id, "jobshare")

    passed = await _ai_precheck(f"{company} {position}", description or "")
    job = CommunityJobShare(
        id=str(uuid.uuid4()),
        user_id=user_id,
        company=company,
        position=position,
        apply_url=apply_url,
        city=(body.city or "").strip() or None,
        salary=(body.salary or "").strip() or None,
        deadline=deadline,
        description=description,
        status="normal" if passed else "hidden",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    names = _user_names(db, {user_id})
    return ok(
        _serialize_job(job, names.get(user_id, "")),
        message="分享成功" if passed else "内容审核中，通过后将对其他用户可见",
    )


@router.get("/job-shares")
async def list_job_shares(
    city: Optional[str] = Query(None, max_length=50),
    expiring: bool = Query(False, description="只看 7 天内截止"),
    keyword: Optional[str] = Query(None, max_length=50),
    sort: str = Query("newest", pattern="^(newest|hot|deadline)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=PAGE_SIZE_MAX),
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """岗位列表：城市/即将截止/搜索 + 最新/最热/截止排序"""
    q = db.query(CommunityJobShare).filter(
        CommunityJobShare.status.in_(["normal"])
    )
    if city:
        q = q.filter(CommunityJobShare.city == city.strip())
    if expiring:
        now = datetime.now(timezone.utc)
        week_later = now + timedelta(days=7)
        q = q.filter(
            CommunityJobShare.deadline.isnot(None),
            CommunityJobShare.deadline >= now,
            CommunityJobShare.deadline <= week_later,
        )
    if keyword:
        kw = _escape_like(keyword)
        q = q.filter(or_(
            CommunityJobShare.company.like(f"%{kw}%", escape="\\"),
            CommunityJobShare.position.like(f"%{kw}%", escape="\\"),
        ))

    total = q.count()
    if sort == "hot":
        q = q.order_by((
            CommunityJobShare.like_count * HOT_LIKE_WEIGHT
            + CommunityJobShare.collect_count * HOT_COLLECT_WEIGHT
            + CommunityJobShare.view_count * HOT_VIEW_WEIGHT
        ).desc(), CommunityJobShare.created_at.desc())
    elif sort == "deadline":
        # 截止时间升序（未填截止的排最后）
        q = q.order_by(
            CommunityJobShare.deadline.is_(None).asc(),
            CommunityJobShare.deadline.asc(),
        )
    else:
        q = q.order_by(CommunityJobShare.created_at.desc())
    items = q.offset((page - 1) * page_size).limit(page_size).all()

    names = _user_names(db, {j.user_id for j in items})
    my = _my_reactions(db, user_id, "jobshare", [j.id for j in items])
    return ok({
        "items": [_serialize_job(j, names.get(j.user_id, ""), my.get(j.id)) for j in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.get("/job-shares/{job_id}")
async def get_job_share(
    job_id: str,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """岗位详情（浏览 +1；hidden 仅作者可见）"""
    job = db.get(CommunityJobShare, job_id)
    if job is None or job.status == "deleted":
        raise NotFoundError("岗位不存在")
    if job.status == "hidden" and job.user_id != user_id:
        raise NotFoundError("岗位不存在")

    _bump_view(db, job, "jobshare", user_id)
    names = _user_names(db, {job.user_id})
    my = _my_reactions(db, user_id, "jobshare", [job.id]).get(job.id)
    return ok(_serialize_job(job, names.get(job.user_id, ""), my))


@router.get("/job-shares/{job_id}/redirect")
async def redirect_job_share(
    job_id: str,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """一键跳转官网：校验内容 + 二次校验链接 + 点击计数，返回 {url}

    前端拿到 url 后 window.open(url, '_blank', 'noopener')。
    不直接返回原始用户输入，杜绝危险协议注入。
    """
    job = db.get(CommunityJobShare, job_id)
    if job is None or job.status != "normal":
        raise NotFoundError("岗位不存在或不可用")
    # 二次校验（防止 DB 被直接篡改后绕过创建时校验）
    url = validate_apply_url(job.apply_url)
    job.click_count = (job.click_count or 0) + 1
    db.commit()
    return ok({
        "url": url,
        "company": job.company,
        "position": job.position,
    })


@router.post("/job-shares/{job_id}/to-application")
async def job_share_to_application(
    job_id: str,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """一键加入我的看板：创建投递记录（预填公司/岗位/链接，source=community）

    幂等：同用户同公司同岗位已有未撤回记录时不重复创建，返回已有记录 id。
    """
    job = db.get(CommunityJobShare, job_id)
    if job is None or job.status != "normal":
        raise NotFoundError("岗位不存在或不可用")

    # 重复检测：同用户同公司同岗位（排除已撤回）
    existing = db.query(Application).filter(
        Application.user_id == user_id,
        Application.company == job.company,
        Application.position == job.position,
        Application.status != "withdrawn",
    ).first()
    if existing:
        return ok({
            "created": False,
            "application_id": existing.id,
            "message": "该岗位已在你的看板中",
        })

    note = f"来自社区岗位分享（分享者：{job.user_id[:8]}）"
    if job.description:
        note += f"\n{job.description[:800]}"
    app = Application(
        id=str(uuid.uuid4()),
        user_id=user_id,
        company=job.company,
        position=job.position,
        job_url=job.apply_url,
        source="community",
        notes=note,
        status="applied",
        priority="medium",
    )
    db.add(app)
    db.commit()
    return ok({
        "created": True,
        "application_id": app.id,
        "message": "已加入投递看板",
    })


@router.put("/job-shares/{job_id}")
async def update_job_share(
    job_id: str,
    body: JobShareUpdate,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """编辑岗位分享（仅分享者；链接变更需重新校验）"""
    job = db.get(CommunityJobShare, job_id)
    if job is None or job.status == "deleted":
        raise NotFoundError("岗位不存在")
    if job.user_id != user_id:
        raise ForbiddenError("只能编辑自己分享的岗位")

    if body.company is not None:
        company = body.company.strip()
        if not company:
            raise BadRequestError("公司名不能为空")
        if len(company) > JOB_COMPANY_MAX:
            raise BadRequestError(f"公司名不能超过 {JOB_COMPANY_MAX} 字")
        job.company = company
    if body.position is not None:
        position = body.position.strip()
        if not position:
            raise BadRequestError("岗位名不能为空")
        if len(position) > JOB_POSITION_MAX:
            raise BadRequestError(f"岗位名不能超过 {JOB_POSITION_MAX} 字")
        job.position = position
    if body.apply_url is not None:
        job.apply_url = validate_apply_url(body.apply_url)
    if body.city is not None:
        job.city = body.city.strip() or None
    if body.salary is not None:
        job.salary = body.salary.strip() or None
    if body.deadline is not None:
        job.deadline = _parse_dt(body.deadline)
    if body.description is not None:
        desc = body.description.strip() or None
        if desc and len(desc) > JOB_DESC_MAX:
            raise BadRequestError(f"备注不能超过 {JOB_DESC_MAX} 字")
        job.description = desc

    db.commit()
    db.refresh(job)
    names = _user_names(db, {job.user_id})
    my = _my_reactions(db, user_id, "jobshare", [job.id]).get(job.id)
    return ok(_serialize_job(job, names.get(job.user_id, ""), my))


@router.delete("/job-shares/{job_id}")
async def delete_job_share(
    job_id: str,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除岗位分享（软删，仅分享者）"""
    job = db.get(CommunityJobShare, job_id)
    if job is None or job.status == "deleted":
        raise NotFoundError("岗位不存在")
    if job.user_id != user_id:
        raise ForbiddenError("只能删除自己分享的岗位")
    job.status = "deleted"
    db.commit()
    return ok({"id": job_id}, message="已删除")


@router.post("/job-shares/{job_id}/expire")
async def expire_job_share(
    job_id: str,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """标记岗位已过期（仅分享者）"""
    job = db.get(CommunityJobShare, job_id)
    if job is None or job.status == "deleted":
        raise NotFoundError("岗位不存在")
    if job.user_id != user_id:
        raise ForbiddenError("只能操作自己分享的岗位")
    job.status = "expired"
    db.commit()
    return ok({"id": job_id}, message="已标记过期")


# =====================================================================
# 统一互动（点赞/收藏）与举报
# =====================================================================

@router.post("/reactions")
async def toggle_reaction(
    body: ReactionBody,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """点赞/收藏/取消（幂等：重复操作不改变计数）"""
    if body.target_type not in VALID_TARGET_TYPES:
        raise BadRequestError(f"无效目标类型: {body.target_type}")
    if body.action not in VALID_ACTIONS:
        raise BadRequestError(f"无效操作: {body.action}")

    obj = _target_or_404(db, body.target_type, body.target_id)
    # hidden 内容不可互动
    if obj.status != "normal":
        raise NotFoundError("内容不存在")

    existing = db.query(UserReaction).filter(
        UserReaction.user_id == user_id,
        UserReaction.target_type == body.target_type,
        UserReaction.target_id == body.target_id,
        UserReaction.action == body.action,
    ).first()

    if body.value and existing is None:
        db.add(UserReaction(
            id=str(uuid.uuid4()),
            user_id=user_id,
            target_type=body.target_type,
            target_id=body.target_id,
            action=body.action,
        ))
        _apply_reaction_counts(obj, body.action, add=True)
        db.commit()
    elif not body.value and existing is not None:
        db.delete(existing)
        _apply_reaction_counts(obj, body.action, add=False)
        db.commit()
    # 其余情况幂等，不重复计数

    like = db.query(UserReaction).filter(
        UserReaction.user_id == user_id,
        UserReaction.target_type == body.target_type,
        UserReaction.target_id == body.target_id,
        UserReaction.action == "like",
    ).first() is not None
    collect = db.query(UserReaction).filter(
        UserReaction.user_id == user_id,
        UserReaction.target_type == body.target_type,
        UserReaction.target_id == body.target_id,
        UserReaction.action == "collect",
    ).first() is not None

    return ok({
        "target_type": body.target_type,
        "target_id": body.target_id,
        "liked": like,
        "collected": collect,
        "like_count": obj.like_count,
        "collect_count": obj.collect_count,
    })


@router.post("/reports")
async def create_report(
    body: ReportBody,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """举报内容（限流；同用户重复举报幂等；达阈值自动隐藏）"""
    if body.target_type not in VALID_TARGET_TYPES:
        raise BadRequestError(f"无效目标类型: {body.target_type}")

    obj = _target_or_404(db, body.target_type, body.target_id)
    if obj.status != "normal":
        raise NotFoundError("内容不存在")
    reason = (body.reason or "").strip() or None
    if reason and len(reason) > REPORT_REASON_MAX:
        raise BadRequestError(f"举报原因不能超过 {REPORT_REASON_MAX} 字")
    _check_rate(user_id, "report")

    # 同用户对同一内容重复举报 → 幂等成功
    dup = db.query(ContentReport).filter(
        ContentReport.user_id == user_id,
        ContentReport.target_type == body.target_type,
        ContentReport.target_id == body.target_id,
    ).first()
    if dup is None:
        db.add(ContentReport(
            id=str(uuid.uuid4()),
            user_id=user_id,
            target_type=body.target_type,
            target_id=body.target_id,
            reason=reason,
        ))
        db.commit()

    hidden = _maybe_hide_by_reports(db, body.target_type, body.target_id)
    return ok(
        {"hidden": hidden},
        message="已举报，我们将尽快处理" if not hidden else "该内容已被隐藏",
    )
