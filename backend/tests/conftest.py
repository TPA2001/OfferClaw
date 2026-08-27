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
os.environ["SECRET_KEY"] = "test-secret-key-for-offerclaw"
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
from app.core.auth import get_current_user
from app.main import app


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
