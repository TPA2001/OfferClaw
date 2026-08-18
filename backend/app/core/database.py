from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

from app.core.paths import data_dir

# 数据库文件稳定放在运行时数据目录（exe 旁边 data/ 或 backend/data），与 CWD 无关
_DB_PATH = data_dir() / "offerclaw.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_DB_PATH.as_posix()}")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()