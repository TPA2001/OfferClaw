"""
账号管理脚本（管理员用）

功能：
- 创建账号 / 重置密码 / 停用账号（账号售卖运营场景）
用法（本地）：
    python scripts/admin.py create  <username> <email> <password>
    python scripts/admin.py reset   <username或email> <new_password>
    python scripts/admin.py disable <username或email>
    python scripts/admin.py list
Docker 环境：
    docker exec -it offerclaw python /app/scripts/admin.py list
"""

import os
import sys
from pathlib import Path

# 让 backend 可被导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.database import SessionLocal, engine, Base
from app.core.auth import hash_password
from app.models.user import User

# 确保表结构存在（服务首次启动也会建，此处兜底以便独立运行）
Base.metadata.create_all(bind=engine)


def find_user(db, key: str):
    return db.execute(
        select(User).where((User.username == key) | (User.email == key.lower()))
    ).scalar_one_or_none()


def cmd_create(username: str, email: str, password: str):
    db = SessionLocal()
    try:
        if find_user(db, username) or find_user(db, email):
            print(f"[错误] 用户名或邮箱已存在: {username} / {email}")
            sys.exit(1)
        user = User(username=username, email=email.lower(), password_hash=hash_password(password))
        db.add(user)
        db.commit()
        print(f"[OK] 已创建账号: {username} ({email}) id={user.id}")
    finally:
        db.close()


def cmd_reset(key: str, new_password: str):
    db = SessionLocal()
    try:
        user = find_user(db, key)
        if not user:
            print(f"[错误] 账号不存在: {key}")
            sys.exit(1)
        user.password_hash = hash_password(new_password)
        user.token_version += 1  # 使该用户所有旧 token 失效
        user.reset_token_hash = None
        user.reset_token_expires_at = None
        db.commit()
        print(f"[OK] 已重置密码并注销全部会话: {user.username} (id={user.id})")
    finally:
        db.close()


def cmd_disable(key: str):
    db = SessionLocal()
    try:
        user = find_user(db, key)
        if not user:
            print(f"[错误] 账号不存在: {key}")
            sys.exit(1)
        user.is_active = False
        db.commit()
        print(f"[OK] 已停用账号: {user.username} (id={user.id})")
    finally:
        db.close()


def cmd_list():
    db = SessionLocal()
    try:
        users = db.execute(select(User).order_by(User.created_at)).scalars().all()
        print(f"{'用户名':<20}{'邮箱':<32}{'状态':<6}{'注册时间'}")
        print("-" * 80)
        for u in users:
            created = u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "-"
            print(f"{u.username:<20}{u.email:<32}{'正常' if u.is_active else '停用':<6}{created}")
        print(f"\n共 {len(users)} 个账号")
    finally:
        db.close()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    op = sys.argv[1]
    if op == "create" and len(sys.argv) == 5:
        cmd_create(sys.argv[2], sys.argv[3], sys.argv[4])
    elif op == "reset" and len(sys.argv) == 4:
        cmd_reset(sys.argv[2], sys.argv[3])
    elif op == "disable" and len(sys.argv) == 3:
        cmd_disable(sys.argv[2])
    elif op == "list":
        cmd_list()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
