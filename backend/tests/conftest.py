"""
pytest 配置

测试策略：
- 使用 SQLite in-memory 数据库，隔离且快速
- 测试启动时覆盖 AUTH_MODE=demo 和 SECRET_KEY，避免真实鉴权依赖
- 通过 fixture 提供干净的 db session 和测试 client
"""
import os
import sys
from pathlib import Path

# 设置测试环境变量（必须在导入 app 之前）
os.environ["AUTH_MODE"] = "demo"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
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


@pytest.fixture(scope="function")
def client(db_session):
    """测试客户端，覆盖 get_db 依赖注入"""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass  # session 由 db_session fixture 管理

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def test_user_id():
    """测试用户 ID"""
    return "test-user-001"
