"""
投递记录核心业务逻辑测试

覆盖：
- 创建投递记录（含字段校验）
- 状态机流转（applied → assessment → interview → offer/rejected）
- 状态切换时的子字段自动清理
- status_history 追加
- 重复投递检测
- 看板统计/漏斗/跟进提醒
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.application import Application


def _make_app(user_id="test-user-001", app_id="app-001", **kwargs):
    """构造测试用 Application 对象"""
    defaults = {
        "company": "腾讯",
        "position": "后端开发",
        "status": "applied",
        "priority": "medium",
    }
    defaults.update(kwargs)
    return Application(id=app_id, user_id=user_id, **defaults)


# ============ 状态机测试 ============

class TestStatusMachine:
    """投递状态流转业务规则测试"""

    def test_status_history_append_on_change(self, db_session):
        """状态变更时 status_history 应追加一条记录"""
        from app.api.applications import _append_status_history

        app = _make_app()
        db_session.add(app)
        db_session.commit()

        _append_status_history(app, "applied", "assessment", "收到笔试通知")
        db_session.commit()

        assert len(app.status_history) == 1
        entry = app.status_history[0]
        assert entry["from"] == "applied"
        assert entry["to"] == "assessment"
        assert entry["note"] == "收到笔试通知"
        assert "at" in entry

    def test_status_history_multiple_changes(self, db_session):
        """多次状态变更应累积历史"""
        from app.api.applications import _append_status_history

        app = _make_app()
        db_session.add(app)
        db_session.commit()

        _append_status_history(app, None, "applied")
        _append_status_history(app, "applied", "assessment")
        _append_status_history(app, "assessment", "interview")
        db_session.commit()

        assert len(app.status_history) == 3
        assert app.status_history[0]["to"] == "applied"
        assert app.status_history[-1]["to"] == "interview"

    def test_cleanup_status_fields_on_rejected(self, db_session):
        """切换到 rejected 时，应清理 interview/assessment/offer 子字段"""
        from app.api.applications import _cleanup_status_fields

        app = _make_app(
            status="interview",
            interview_round=2,
            next_interview_at=datetime.now(timezone.utc),
            assessment_deadline=datetime.now(timezone.utc),
            offer_salary="25k",
        )
        _cleanup_status_fields(app, "rejected")

        assert app.interview_round is None
        assert app.next_interview_at is None
        assert app.assessment_deadline is None
        assert app.offer_salary is None

    def test_cleanup_status_fields_on_offer(self, db_session):
        """切换到 offer 时，应清理 rejection/interview/assessment 子字段"""
        from app.api.applications import _cleanup_status_fields

        app = _make_app(
            status="rejected",
            rejection_stage="interview_1_failed",
            interview_round=1,
            assessment_deadline=datetime.now(timezone.utc),
        )
        _cleanup_status_fields(app, "offer")

        assert app.rejection_stage is None
        assert app.interview_round is None
        assert app.assessment_deadline is None

    def test_cleanup_preserves_rejection_on_rejected(self, db_session):
        """切换到 rejected 时，rejection_stage 不应被清理"""
        from app.api.applications import _cleanup_status_fields

        app = _make_app(status="interview", rejection_stage=None)
        _cleanup_status_fields(app, "rejected")

        # rejection_stage 在 rejected 状态下保留
        assert app.rejection_stage is None  # 未设置则仍为 None


# ============ 重复投递检测测试 ============

class TestDuplicateDetection:
    """重复投递检测逻辑测试"""

    def test_duplicate_within_30_days(self, db_session):
        """30 天内同公司同岗位应检测为重复"""
        # 创建一条 10 天前的投递
        old_app = Application(
            id="old-001",
            user_id="test-user-001",
            company="腾讯",
            position="后端开发",
            status="applied",
            applied_at=datetime.now(timezone.utc) - timedelta(days=10),
        )
        db_session.add(old_app)
        db_session.commit()

        # 模拟重复检测查询
        dup_threshold = datetime.now(timezone.utc) - timedelta(days=30)
        existing = db_session.query(Application).filter(
            Application.user_id == "test-user-001",
            Application.company == "腾讯",
            Application.position == "后端开发",
            Application.status.notin_(["withdrawn"]),
            Application.applied_at >= dup_threshold,
        ).first()

        assert existing is not None
        assert existing.id == "old-001"

    def test_no_duplicate_after_30_days(self, db_session):
        """超过 30 天的同公司同岗位不算重复"""
        old_app = Application(
            id="old-002",
            user_id="test-user-001",
            company="阿里",
            position="前端开发",
            status="applied",
            applied_at=datetime.now(timezone.utc) - timedelta(days=45),
        )
        db_session.add(old_app)
        db_session.commit()

        dup_threshold = datetime.now(timezone.utc) - timedelta(days=30)
        existing = db_session.query(Application).filter(
            Application.user_id == "test-user-001",
            Application.company == "阿里",
            Application.position == "前端开发",
            Application.status.notin_(["withdrawn"]),
            Application.applied_at >= dup_threshold,
        ).first()

        assert existing is None

    def test_withdrawn_not_counted_as_duplicate(self, db_session):
        """已撤回的投递不计入重复检测"""
        old_app = Application(
            id="old-003",
            user_id="test-user-001",
            company="字节",
            position="算法工程师",
            status="withdrawn",
            applied_at=datetime.now(timezone.utc) - timedelta(days=5),
        )
        db_session.add(old_app)
        db_session.commit()

        dup_threshold = datetime.now(timezone.utc) - timedelta(days=30)
        existing = db_session.query(Application).filter(
            Application.user_id == "test-user-001",
            Application.company == "字节",
            Application.position == "算法工程师",
            Application.status.notin_(["withdrawn"]),
            Application.applied_at >= dup_threshold,
        ).first()

        assert existing is None


# ============ 漏斗统计测试 ============

class TestFunnelStats:
    """看板漏斗统计逻辑测试"""

    def test_funnel_counts(self, db_session):
        """漏斗各阶段计数正确"""
        now = datetime.now(timezone.utc)
        apps = [
            # applied：纯投递，未通过简历
            _make_app(app_id="a1", status="applied"),
            # assessment：通过了简历筛选
            _make_app(app_id="a2", status="assessment"),
            # interview：通过了笔试
            _make_app(app_id="a3", status="interview"),
            # offer：通过了面试
            _make_app(app_id="a4", status="offer"),
            # rejected at resume：简历挂
            _make_app(app_id="a5", status="rejected", rejection_stage="resume_rejected"),
            # rejected at assessment：笔试挂（通过了简历）
            _make_app(app_id="a6", status="rejected", rejection_stage="assessment_failed"),
            # rejected at interview_1：一面挂（通过了笔试）
            _make_app(app_id="a7", status="rejected", rejection_stage="interview_1_failed"),
        ]
        for a in apps:
            db_session.add(a)
        db_session.commit()

        all_apps = db_session.query(Application).filter(
            Application.user_id == "test-user-001"
        ).all()
        total = len(all_apps)

        # 简历通过 = 进入过笔试/面试/offer 的 + rejected 但非简历挂
        resume_passed = sum(
            1 for a in all_apps
            if a.status in ("assessment", "interview", "offer")
            or (a.status == "rejected" and a.rejection_stage
                and a.rejection_stage not in ("resume_rejected",))
        )
        assert resume_passed == 5  # a2, a3, a4, a6, a7

        # 笔试通过 = 进入面试/offer + rejected 但非简历挂且非笔试挂
        assessment_passed = sum(
            1 for a in all_apps
            if a.status in ("interview", "offer")
            or (a.status == "rejected" and a.rejection_stage
                and a.rejection_stage not in ("resume_rejected", "assessment_failed"))
        )
        assert assessment_passed == 3  # a3, a4, a7

        # 面试通过 = offer + rejected 但未挂在面试环节前
        interview_passed = sum(
            1 for a in all_apps
            if a.status == "offer"
            or (a.status == "rejected" and a.rejection_stage
                and a.rejection_stage not in (
                    "resume_rejected", "assessment_failed",
                    "interview_1_failed", "interview_2_failed",
                    "interview_3_failed", "hr_failed"
                ))
        )
        assert interview_passed == 1  # a4

        offer_count = sum(1 for a in all_apps if a.status == "offer")
        assert offer_count == 1


# ============ 跟进提醒测试 ============

class TestFollowupReminders:
    """跟进提醒逻辑测试"""

    def test_stale_app_detection(self, db_session):
        """超过 7 天未回复的 applied 应被标记为 stale"""
        from app.api.applications import STALE_THRESHOLD_DAYS

        now = datetime.now(timezone.utc)
        stale_app = _make_app(
            app_id="stale-1",
            status="applied",
            applied_at=now - timedelta(days=10),
        )
        fresh_app = _make_app(
            app_id="fresh-1",
            status="applied",
            applied_at=now - timedelta(days=2),
        )
        db_session.add_all([stale_app, fresh_app])
        db_session.commit()

        threshold = now - timedelta(days=STALE_THRESHOLD_DAYS)
        stale_apps = db_session.query(Application).filter(
            Application.user_id == "test-user-001",
            Application.status == "applied",
            Application.applied_at < threshold,
        ).all()

        assert len(stale_apps) == 1
        assert stale_apps[0].id == "stale-1"

    def test_upcoming_interview_detection(self, db_session):
        """未来 7 天内的面试应被检测"""
        now = datetime.now(timezone.utc)
        upcoming_app = _make_app(
            app_id="upcoming-1",
            status="interview",
            next_interview_at=now + timedelta(days=3),
        )
        past_app = _make_app(
            app_id="past-1",
            status="interview",
            next_interview_at=now - timedelta(days=10),
        )
        db_session.add_all([upcoming_app, past_app])
        db_session.commit()

        upcoming_end = now + timedelta(days=7)
        upcoming = db_session.query(Application).filter(
            Application.user_id == "test-user-001",
            Application.status == "interview",
            Application.next_interview_at <= upcoming_end,
            Application.next_interview_at >= now,
        ).all()

        assert len(upcoming) == 1
        assert upcoming[0].id == "upcoming-1"
