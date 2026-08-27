"""
账号体系测试：注册 / 登录 / 当前用户 / 修改密码 / 找回密码 / 重置密码 / 数据隔离

使用 client_auth fixture（真实 JWT 鉴权，AUTH_RESET_TOKEN_IN_RESPONSE=1）。
"""
import pytest


def _register(client, username="zhangsan", email="zhangsan@example.com", password="pass1234", **kw):
    return client.post("/api/v1/auth/register", json={
        "username": username, "email": email, "password": password, **kw,
    })


def _login(client, account, password):
    return client.post("/api/v1/auth/login", json={"account": account, "password": password})


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestRegister:
    def test_register_success(self, client_auth):
        r = _register(client_auth)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["token"]
        assert data["user"]["username"] == "zhangsan"
        assert data["user"]["email"] == "zhangsan@example.com"

    def test_register_duplicate_username(self, client_auth):
        _register(client_auth)
        r = _register(client_auth, email="other@example.com")
        assert r.status_code == 409
        assert "用户名" in r.json()["message"]

    def test_register_duplicate_email(self, client_auth):
        _register(client_auth)
        r = _register(client_auth, username="lisi")
        assert r.status_code == 409
        assert "邮箱" in r.json()["message"]

    def test_register_weak_password(self, client_auth):
        r = _register(client_auth, password="123")
        assert r.status_code == 400

    def test_register_invalid_email(self, client_auth):
        r = _register(client_auth, email="not-an-email")
        assert r.status_code == 400

    def test_register_with_invite_code(self, client_auth, monkeypatch):
        monkeypatch.setenv("REGISTRATION_INVITE_CODE", "secret-666")
        from app.core.config import settings
        monkeypatch.setattr(settings, "registration_invite_code", "secret-666")
        # 无邀请码 → 拒绝
        r = _register(client_auth, username="wanger")
        assert r.status_code == 403
        # 错误邀请码 → 拒绝
        r = _register(client_auth, username="wanger", invite_code="wrong")
        assert r.status_code == 403
        # 正确邀请码 → 成功
        r = _register(client_auth, username="wanger", invite_code="secret-666")
        assert r.status_code == 200


class TestLogin:
    def test_login_with_username(self, client_auth):
        _register(client_auth)
        r = _login(client_auth, "zhangsan", "pass1234")
        assert r.status_code == 200
        assert r.json()["data"]["token"]

    def test_login_with_email(self, client_auth):
        _register(client_auth)
        r = _login(client_auth, "zhangsan@example.com", "pass1234")
        assert r.status_code == 200

    def test_login_wrong_password(self, client_auth):
        _register(client_auth)
        r = _login(client_auth, "zhangsan", "wrongpass")
        assert r.status_code == 401
        assert "账号或密码错误" in r.json()["message"]

    def test_login_nonexistent(self, client_auth):
        r = _login(client_auth, "nobody", "pass1234")
        assert r.status_code == 401


class TestMe:
    def test_me_with_token(self, client_auth):
        reg = _register(client_auth).json()["data"]
        r = client_auth.get("/api/v1/auth/me", headers=_auth(reg["token"]))
        assert r.status_code == 200
        assert r.json()["data"]["username"] == "zhangsan"

    def test_me_without_token(self, client_auth):
        r = client_auth.get("/api/v1/auth/me")
        assert r.status_code == 401

    def test_me_with_garbage_token(self, client_auth):
        r = client_auth.get("/api/v1/auth/me", headers=_auth("garbage"))
        assert r.status_code == 401


class TestChangePassword:
    def test_change_password_flow(self, client_auth):
        reg = _register(client_auth).json()["data"]
        old_token = reg["token"]
        # 旧密码错误
        r = client_auth.post("/api/v1/auth/change-password",
                             json={"old_password": "wrong", "new_password": "newpass123"},
                             headers=_auth(old_token))
        assert r.status_code == 400
        # 正常改密 → 返回新 token
        r = client_auth.post("/api/v1/auth/change-password",
                             json={"old_password": "pass1234", "new_password": "newpass123"},
                             headers=_auth(old_token))
        assert r.status_code == 200
        new_token = r.json()["data"]["token"]
        # 旧 token 失效（token_version 递增）
        r = client_auth.get("/api/v1/auth/me", headers=_auth(old_token))
        assert r.status_code == 401
        # 新 token 有效
        r = client_auth.get("/api/v1/auth/me", headers=_auth(new_token))
        assert r.status_code == 200
        # 新密码可登录
        r = _login(client_auth, "zhangsan", "newpass123")
        assert r.status_code == 200


class TestForgotAndResetPassword:
    def test_forgot_returns_token_in_test_mode(self, client_auth):
        _register(client_auth)
        r = client_auth.post("/api/v1/auth/forgot-password", json={"email": "zhangsan@example.com"})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["delivered"] == "response"
        assert data["reset_token"]

    def test_forgot_unknown_email_returns_ok(self, client_auth):
        r = client_auth.post("/api/v1/auth/forgot-password", json={"email": "ghost@example.com"})
        assert r.status_code == 200  # 不泄露注册信息

    def test_reset_password_flow(self, client_auth):
        reg = _register(client_auth).json()["data"]
        old_token = reg["token"]
        f = client_auth.post("/api/v1/auth/forgot-password", json={"email": "zhangsan@example.com"})
        token = f.json()["data"]["reset_token"]
        # 无效 token
        r = client_auth.post("/api/v1/auth/reset-password", json={"token": "bad", "new_password": "reset1234"})
        assert r.status_code == 400
        # 正常重置
        r = client_auth.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "reset1234"})
        assert r.status_code == 200
        # 旧 token 失效
        r = client_auth.get("/api/v1/auth/me", headers=_auth(old_token))
        assert r.status_code == 401
        # 新密码登录
        r = _login(client_auth, "zhangsan", "reset1234")
        assert r.status_code == 200
        # 令牌一次性：再次使用失败
        r = client_auth.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "reset5678"})
        assert r.status_code == 400


class TestDataIsolation:
    def test_applications_isolated_between_users(self, client_auth):
        # 用户 A 注册并建一条投递
        a = _register(client_auth, username="usera", email="a@example.com").json()["data"]
        r = client_auth.post("/api/v1/applications/", json={
            "company": "腾讯", "position": "后端开发", "status": "applied",
        }, headers=_auth(a["token"]))
        assert r.status_code == 200

        # 用户 B 注册，列表为空
        b = _register(client_auth, username="userb", email="b@example.com").json()["data"]
        r = client_auth.get("/api/v1/applications/", headers=_auth(b["token"]))
        assert r.status_code == 200
        assert r.json()["data"] == []

        # 用户 A 能看到自己的
        r = client_auth.get("/api/v1/applications/", headers=_auth(a["token"]))
        assert r.status_code == 200
        assert len(r.json()["data"]) == 1

    def test_unauth_cannot_access_applications(self, client_auth):
        r = client_auth.get("/api/v1/applications/")
        assert r.status_code == 401
