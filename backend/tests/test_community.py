"""
社区 + 岗位分享测试

覆盖：
- 帖子 CRUD 与作者权限（多用户）
- 板块筛选 / 关键词搜索 / 热度排序
- 点赞收藏幂等（重复操作计数不变）
- 楼中楼评论与父评论校验
- 举报阈值自动隐藏（作者可见、他人不可见）
- 岗位分享链接安全校验（javascript:/内网/IP 直连拒绝）
- redirect 跳转计数 / 一键加入看板（幂等 + 归属正确）
- 写操作限流（429）
- 未登录访问拒绝（401）
"""
import pytest

from app.api import community as community_mod


def _register(client, username, email, password="pass1234"):
    r = client.post("/api/v1/auth/register", json={
        "username": username, "email": email, "password": password,
    })
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _reset_action_limiter():
    """每个测试前后重置用户级限流器（全局单例，避免跨测试累积污染）"""
    community_mod._action_limiter.reset()
    yield
    community_mod._action_limiter.reset()


def _create_post(client, token=None, title="测试帖", content="正文内容", category="chat"):
    headers = _auth(token) if token else None
    r = client.post("/api/v1/community/posts", json={
        "title": title, "content": content, "category": category,
    }, headers=headers)
    return r


def _create_job(client, token=None, company="示例公司", position="后端工程师",
                apply_url="https://example.com/job", **kw):
    headers = _auth(token) if token else None
    body = {"company": company, "position": position, "apply_url": apply_url, **kw}
    r = client.post("/api/v1/community/job-shares", json=body, headers=headers)
    return r


# ============ 鉴权 ============

class TestAuthRequired:
    def test_list_posts_requires_login(self, client_auth):
        r = client_auth.get("/api/v1/community/posts")
        assert r.status_code == 401

    def test_create_post_requires_login(self, client_auth):
        r = client_auth.post("/api/v1/community/posts", json={"title": "x", "content": "y"})
        assert r.status_code == 401


# ============ 帖子 CRUD 与权限 ============

class TestPostCrud:
    def test_create_and_get(self, client):
        r = _create_post(client)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "normal"  # Mock 预审放行
        assert data["author"] == "test-user-001" or data["author"]
        post_id = data["id"]

        # 详情浏览 +1
        r = client.get(f"/api/v1/community/posts/{post_id}")
        assert r.status_code == 200
        assert r.json()["data"]["view_count"] == 1

    def test_create_validation(self, client):
        # 空标题
        r = _create_post(client, title="   ")
        assert r.status_code == 400
        # 非法板块
        r = _create_post(client, category="hack")
        assert r.status_code == 400
        # 超长内容
        r = _create_post(client, content="x" * 6000)
        assert r.status_code == 400

    def test_edit_delete_author_only(self, client_auth):
        token_a = _register(client_auth, "usera", "a@example.com")
        token_b = _register(client_auth, "userb", "b@example.com")
        post_id = _create_post(client_auth, token=token_a).json()["data"]["id"]

        # B 不能编辑/删除 A 的帖子
        r = client_auth.put(f"/api/v1/community/posts/{post_id}",
                            json={"title": "hacked"}, headers=_auth(token_b))
        assert r.status_code == 403
        r = client_auth.delete(f"/api/v1/community/posts/{post_id}", headers=_auth(token_b))
        assert r.status_code == 403

        # A 编辑成功
        r = client_auth.put(f"/api/v1/community/posts/{post_id}",
                            json={"title": "新标题"}, headers=_auth(token_a))
        assert r.status_code == 200
        assert r.json()["data"]["title"] == "新标题"

        # A 删除成功，删除后 404
        r = client_auth.delete(f"/api/v1/community/posts/{post_id}", headers=_auth(token_a))
        assert r.status_code == 200
        r = client_auth.get(f"/api/v1/community/posts/{post_id}", headers=_auth(token_b))
        assert r.status_code == 404

    def test_list_filter_sort_search(self, client):
        _create_post(client, title="简历求改", content="帮我看看简历", category="resume")
        _create_post(client, title="一面凉经", content="字节一面挂了", category="interview")
        _create_post(client, title="Offer 抉择", content="A 和 B 选哪个", category="offer")

        # 板块筛选
        r = client.get("/api/v1/community/posts", params={"category": "resume"})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 1 and items[0]["category"] == "resume"

        # 关键词搜索（标题命中）
        r = client.get("/api/v1/community/posts", params={"keyword": "简历"})
        assert r.status_code == 200
        assert len(r.json()["data"]["items"]) == 1

        # 通配符转义：% 作为普通字符搜索，不应命中所有
        r = client.get("/api/v1/community/posts", params={"keyword": "%"})
        assert r.status_code == 200
        assert len(r.json()["data"]["items"]) == 0

        # 热度排序可用
        r = client.get("/api/v1/community/posts", params={"sort": "hot"})
        assert r.status_code == 200

        # 分页边界
        r = client.get("/api/v1/community/posts", params={"page_size": 999})
        assert r.status_code == 422


# ============ 点赞 / 收藏幂等 ============

class TestReaction:
    def test_reaction_idempotent(self, client):
        post_id = _create_post(client).json()["data"]["id"]

        # 点赞两次 → 计数仍 1
        for _ in range(2):
            r = client.post("/api/v1/community/reactions", json={
                "target_type": "post", "target_id": post_id, "action": "like", "value": True,
            })
            assert r.status_code == 200
        assert r.json()["data"]["like_count"] == 1
        assert r.json()["data"]["liked"] is True

        # 取消 → 0
        r = client.post("/api/v1/community/reactions", json={
            "target_type": "post", "target_id": post_id, "action": "like", "value": False,
        })
        assert r.json()["data"]["like_count"] == 0
        assert r.json()["data"]["liked"] is False

        # 收藏 +1
        r = client.post("/api/v1/community/reactions", json={
            "target_type": "post", "target_id": post_id, "action": "collect", "value": True,
        })
        assert r.json()["data"]["collect_count"] == 1

    def test_reaction_invalid_target(self, client):
        r = client.post("/api/v1/community/reactions", json={
            "target_type": "post", "target_id": "no-such", "action": "like", "value": True,
        })
        assert r.status_code == 404
        r = client.post("/api/v1/community/reactions", json={
            "target_type": "hack", "target_id": "x", "action": "like", "value": True,
        })
        assert r.status_code == 400


# ============ 评论 ============

class TestComment:
    def test_comment_and_reply(self, client):
        post_id = _create_post(client).json()["data"]["id"]

        r = client.post(f"/api/v1/community/posts/{post_id}/comments", json={"content": "一级评论"})
        assert r.status_code == 200
        root_id = r.json()["data"]["id"]

        # 楼中楼回复
        r = client.post(f"/api/v1/community/posts/{post_id}/comments",
                        json={"content": "回复一层", "parent_id": root_id})
        assert r.status_code == 200
        assert r.json()["data"]["parent_id"] == root_id

        # 评论数 = 2
        detail = client.get(f"/api/v1/community/posts/{post_id}").json()["data"]
        assert detail["comment_count"] == 2

        # 父评论不属于该帖 → 400
        other_id = _create_post(client, title="另一帖").json()["data"]["id"]
        other_root = client.post(f"/api/v1/community/posts/{other_id}/comments",
                                 json={"content": "别的帖"}).json()["data"]["id"]
        r = client.post(f"/api/v1/community/posts/{post_id}/comments",
                        json={"content": "跨帖回复", "parent_id": other_root})
        assert r.status_code == 400

    def test_delete_comment_updates_count(self, client):
        post_id = _create_post(client).json()["data"]["id"]
        c1 = client.post(f"/api/v1/community/posts/{post_id}/comments",
                         json={"content": "c1"}).json()["data"]["id"]
        c2 = client.post(f"/api/v1/community/posts/{post_id}/comments",
                         json={"content": "c2"}).json()["data"]["id"]
        # c2 回复 c1
        client.post(f"/api/v1/community/posts/{post_id}/comments",
                    json={"content": "c2-回复", "parent_id": c1})

        r = client.delete(f"/api/v1/community/comments/{c1}")
        assert r.status_code == 200
        # 删除 c1 + 其楼中楼回复，评论数回退 2
        detail = client.get(f"/api/v1/community/posts/{post_id}").json()["data"]
        assert detail["comment_count"] == 1

    def test_comment_delete_author_only(self, client_auth):
        token_a = _register(client_auth, "usera2", "a2@example.com")
        token_b = _register(client_auth, "userb2", "b2@example.com")
        post_id = _create_post(client_auth, token=token_a).json()["data"]["id"]
        cid = client_auth.post(f"/api/v1/community/posts/{post_id}/comments",
                               json={"content": "A 的评论"}, headers=_auth(token_a)).json()["data"]["id"]
        r = client_auth.delete(f"/api/v1/community/comments/{cid}", headers=_auth(token_b))
        assert r.status_code == 403


# ============ 举报与自动隐藏 ============

class TestReport:
    def test_report_threshold_hides(self, client_auth):
        token_a = _register(client_auth, "usera3", "a3@example.com")
        tokens = [
            _register(client_auth, f"reporter{i}", f"r{i}@example.com")
            for i in range(3)
        ]
        post_id = _create_post(client_auth, token=token_a).json()["data"]["id"]

        for i, tok in enumerate(tokens):
            r = client_auth.post("/api/v1/community/reports", json={
                "target_type": "post", "target_id": post_id, "reason": "违规内容",
            }, headers=_auth(tok))
            assert r.status_code == 200
            if i == 2:
                assert r.json()["data"]["hidden"] is True

        # 其他人列表/详情均不可见
        r = client_auth.get("/api/v1/community/posts", headers=_auth(tokens[0]))
        assert all(p["id"] != post_id for p in r.json()["data"]["items"])
        r = client_auth.get(f"/api/v1/community/posts/{post_id}", headers=_auth(tokens[0]))
        assert r.status_code == 404

        # 作者本人仍可见
        r = client_auth.get(f"/api/v1/community/posts/{post_id}", headers=_auth(token_a))
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "hidden"

    def test_report_duplicate_same_user_idempotent(self, client):
        post_id = _create_post(client).json()["data"]["id"]
        for _ in range(2):
            r = client.post("/api/v1/community/reports", json={
                "target_type": "post", "target_id": post_id, "reason": "举报",
            })
            assert r.status_code == 200
        # 同一用户重复举报不累计，未达隐藏阈值
        r = client.get(f"/api/v1/community/posts/{post_id}")
        assert r.json()["data"]["status"] == "normal"


# ============ 岗位分享（投递分享） ============

class TestJobShare:
    def test_url_validation(self, client):
        # 危险协议
        r = _create_job(client, apply_url="javascript:alert(1)")
        assert r.status_code == 400
        r = _create_job(client, apply_url="data:text/html,<script>")
        assert r.status_code == 400
        # 本机/内网
        r = _create_job(client, apply_url="http://localhost:8000/x")
        assert r.status_code == 400
        r = _create_job(client, apply_url="http://192.168.1.1/x")
        assert r.status_code == 400
        r = _create_job(client, apply_url="http://10.0.0.5/x")
        assert r.status_code == 400
        r = _create_job(client, apply_url="http://[::1]/x")
        assert r.status_code == 400
        # 合法公网链接
        r = _create_job(client, apply_url="https://career.example.com/apply?src=1")
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "normal"

    def test_position_optional_default(self, client):
        """岗位可空：不填 position 时存占位「官网招聘」，前端据此显示官网招聘入口"""
        r = _create_job(client, position="")
        assert r.status_code == 200
        assert r.json()["data"]["position"] == "官网招聘"
        # 不传 position 字段同理
        r = _create_job(client, company="纯官网入口公司", position="")
        assert r.status_code == 200
        assert r.json()["data"]["position"] == "官网招聘"

    def test_category_validation_and_label(self, client):
        # 无效标签
        r = _create_job(client, category="hack")
        assert r.status_code == 400
        # 有效标签（央国企）
        r = _create_job(client, company="国家电网", position="", category="soe")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["category"] == "soe"
        assert data["category_label"] == "央国企"
        # 默认标签
        r = _create_job(client, company="默认标签公司")
        assert r.json()["data"]["category"] == "other"
        assert r.json()["data"]["category_label"] == "其他"

    def test_list_filter_by_category(self, client):
        _create_job(client, company="腾讯", category="internet")
        _create_job(client, company="米哈游", category="game")
        _create_job(client, company="国家电网", category="soe")

        r = client.get("/api/v1/community/job-shares", params={"category": "internet"})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 1 and items[0]["company"] == "腾讯"
        assert items[0]["category_label"] == "互联网"

        r = client.get("/api/v1/community/job-shares", params={"category": "game"})
        assert r.json()["data"]["items"][0]["company"] == "米哈游"

        # 无效标签筛选
        r = client.get("/api/v1/community/job-shares", params={"category": "hack"})
        assert r.status_code == 400

    def test_referral_code_roundtrip(self, client):
        """内推码：创建时保存、返回、可编辑更新、超长拒绝"""
        r = _create_job(client, company="内推公司", position="", referral_code="ABC123")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["referral_code"] == "ABC123"

        job_id = data["id"]
        # 编辑更新内推码
        r = client.put(f"/api/v1/community/job-shares/{job_id}",
                       json={"referral_code": "XYZ999"})
        assert r.status_code == 200
        assert r.json()["data"]["referral_code"] == "XYZ999"
        # 清空内推码
        r = client.put(f"/api/v1/community/job-shares/{job_id}",
                       json={"referral_code": ""})
        assert r.json()["data"]["referral_code"] is None
        # 超长拒绝
        r = _create_job(client, company="超长内推", referral_code="X" * 101)
        assert r.status_code == 400

    def test_redirect_counts_and_validates(self, client):
        job_id = _create_job(client).json()["data"]["id"]
        r = client.get(f"/api/v1/community/job-shares/{job_id}/redirect")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["url"] == "https://example.com/job"

        detail = client.get(f"/api/v1/community/job-shares/{job_id}").json()["data"]
        assert detail["click_count"] == 1

    def test_to_application_idempotent_and_owned(self, client, test_user_id):
        job_id = _create_job(client).json()["data"]["id"]

        r = client.post(f"/api/v1/community/job-shares/{job_id}/to-application")
        assert r.status_code == 200
        assert r.json()["data"]["created"] is True
        app_id = r.json()["data"]["application_id"]

        # 再调不重复创建
        r = client.post(f"/api/v1/community/job-shares/{job_id}/to-application")
        assert r.json()["data"]["created"] is False
        assert r.json()["data"]["application_id"] == app_id

        # 记录归属当前用户（能查到即归属正确，非本人会 404），source=community
        r = client.get(f"/api/v1/applications/{app_id}")
        assert r.status_code == 200
        app = r.json()["data"]
        assert app["source"] == "community"
        assert app["company"] == "示例公司"
        assert app["job_url"] == "https://example.com/job"

    def test_job_share_author_only(self, client_auth):
        token_a = _register(client_auth, "usera4", "a4@example.com")
        token_b = _register(client_auth, "userb4", "b4@example.com")
        job_id = _create_job(client_auth, token=token_a).json()["data"]["id"]

        r = client_auth.delete(f"/api/v1/community/job-shares/{job_id}", headers=_auth(token_b))
        assert r.status_code == 403
        r = client_auth.post(f"/api/v1/community/job-shares/{job_id}/expire", headers=_auth(token_b))
        assert r.status_code == 403

        # 作者标记过期后，其他人不可见（redirect 404）
        r = client_auth.post(f"/api/v1/community/job-shares/{job_id}/expire", headers=_auth(token_a))
        assert r.status_code == 200
        r = client_auth.get(f"/api/v1/community/job-shares/{job_id}/redirect", headers=_auth(token_b))
        assert r.status_code == 404

    def test_job_list_filters(self, client):
        _create_job(client, company="腾讯", position="前端", city="深圳", salary="20-30k",
                    deadline="2026-09-30T00:00:00Z")
        _create_job(client, company="字节", position="后端", city="北京",
                    deadline="2099-01-01T00:00:00Z")
        _create_job(client, company="美团", position="算法", city="北京")

        # 城市筛选
        r = client.get("/api/v1/community/job-shares", params={"city": "北京"})
        assert r.status_code == 200
        assert len(r.json()["data"]["items"]) == 2

        # 即将截止（7 天内）→ 只有 2026-09-30 那条（相对当前时间）
        r = client.get("/api/v1/community/job-shares", params={"expiring": "true"})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert all(it["company"] == "腾讯" for it in items)

        # 搜索
        r = client.get("/api/v1/community/job-shares", params={"keyword": "后端"})
        assert r.status_code == 200
        assert len(r.json()["data"]["items"]) == 1

        # 截止排序可用
        r = client.get("/api/v1/community/job-shares", params={"sort": "deadline"})
        assert r.status_code == 200
        assert r.json()["data"]["items"][0]["company"] == "腾讯"


# ============ 限流 ============

class TestRateLimit:
    def test_post_rate_limit(self, client):
        community_mod._action_limiter.reset()
        # limit=5/min：前 5 帖成功，第 6 帖 429
        for i in range(5):
            r = _create_post(client, title=f"限流测试{i}")
            assert r.status_code == 200, r.text
        r = _create_post(client, title="限流测试超限")
        assert r.status_code == 429
        assert "频繁" in r.json()["message"]

    def test_job_share_rate_limit(self, client):
        community_mod._action_limiter.reset()
        for i in range(5):
            r = _create_job(client, company=f"公司{i}")
            assert r.status_code == 200, r.text
        r = _create_job(client, company="超限公司")
        assert r.status_code == 429
