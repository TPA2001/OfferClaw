from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
import os

from app.core.paths import data_dir

# 数据库文件稳定放在运行时数据目录（exe 旁边 data/ 或 backend/data），与 CWD 无关
_DB_PATH = data_dir() / "offercabin.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_DB_PATH.as_posix()}")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

    # WAL 模式 + busy_timeout：进程被强杀/断电时不易出现
    # "database disk image is malformed"（回写日志由 WAL 统一管理）
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()
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