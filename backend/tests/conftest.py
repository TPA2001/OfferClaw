"""
pytest 配置

测试策略：
- 使用 SQLite in-memory 数据库，隔离且快速
- AUTH_MODE=jwt：与生产一致的真实鉴权
  - client fixture：覆盖 get_current_user → test_user_id（旧业务测试保持单用户语义）
  - client_auth fixture：仅覆盖 get_db，走真实 JWT 流程（账号体系测试用）
"""
import os
import sys
from pathlib import Path

# 设置测试环境变量（必须在导入 app 之前）
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["AUTH_MODE"] = "jwt"
os.environ["SECRET_KEY"] = "test-secret-key-for-offercabin"
os.environ["AUTH_RESET_TOKEN_IN_RESPONSE"] = "1"  # 找回密码令牌直接返回，便于测试
os.environ["OPENAI_API_KEY"] = ""  # 强制使用 MockProvider

# 让 backend 目录可被导入
backend_dir = str(Path(__file__).parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.auth import get_current_user, get_current_admin, hash_password, create_access_token
from app.core.rate_limit import _counter as _rate_counter
from app.main import app
from app.admin_main import app as admin_app
from app.models.user import User


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """每个测试前后清空内存限流计数器，避免跨测试累积触发 429"""
    _rate_counter._buckets.clear()
    yield
    _rate_counter._buckets.clear()


@pytest.fixture(scope="function")
def db_session():
    """每个测试函数独立的内存数据库 session"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # 确保 in-memory db 在同一连接共享
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def _make_client(db_session, override_auth: bool):
    """构造测试客户端；override_auth=True 时覆盖鉴权依赖（固定本地用户）"""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    overrides = {get_db: override_get_db}
    if override_auth:
        overrides[get_current_user] = lambda: "test-user-001"

    app.dependency_overrides.update(overrides)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def client(db_session):
    """业务测试客户端：单用户语义（跳过真实鉴权）"""
    yield from _make_client(db_session, override_auth=True)


@pytest.fixture(scope="function")
def client_auth(db_session):
    """账号体系测试客户端：真实 JWT 鉴权"""
    yield from _make_client(db_session, override_auth=False)


@pytest.fixture
def test_user_id():
    """测试用户 ID"""
    return "test-user-001"


# ============ 管理后台测试 fixtures ============

@pytest.fixture(scope="function")
def admin_client(db_session):
    """管理后台测试客户端（基于 app.admin_main:app，共享 db_session）"""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    admin_app.dependency_overrides[get_db] = override_get_db
    with TestClient(admin_app) as c:
        yield c
    admin_app.dependency_overrides.clear()


def _make_user(db_session, username, role="user", password="Pass1234", is_active=True):
    """在 db_session 中直接创建用户（绕过 API）"""
    user = User(
        username=username,
        email=f"{username}@test.com",
        password_hash=hash_password(password),
        role=role,
        is_active=is_active,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_user(db_session):
    """活跃管理员账号"""
    return _make_user(db_session, "admin01", role="admin", password="Admin1234")


@pytest.fixture
def admin_headers(admin_client, admin_user):
    """管理员登录令牌头（通过 create_access_token 签发，避免依赖登录端点）"""
    token = create_access_token(admin_user.id, admin_user.token_version, ttl_hours=12)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def plain_user(db_session):
    """普通（非管理员）用户"""
    return _make_user(db_session, "plain01", role="user", password="Pass1234")


@pytest.fixture
def plain_headers(plain_user):
    """普通用户令牌头（用于验证非管理员被 403 拒绝）"""
    token = create_access_token(plain_user.id, plain_user.token_version)
    return {"Authorization": f"Bearer {token}"}
