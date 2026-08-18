"""泛化自动迁移框架

目标：用户更新版本后直接重启即可，旧数据库自动升级，零操作。

策略（SQLite 友好）：
1. 不存在的表 → 由 Base.metadata.create_all 创建（main.py 已做）
2. 已存在的表 → 比对 models 列与 DB 实际列，缺失列用 ALTER TABLE ADD COLUMN 补齐
3. 迁移前自动 JSON 备份所有表到 data/backups/pre_migrate_<ts>/，绝不丢数据

SQLite 限制（已知，记日志提示）：
- 不支持 ALTER COLUMN 改类型/重命名/删列（这类变更需手动处理，已备份）
- ADD COLUMN NOT NULL 必须有 DEFAULT；无默认值的 NOT NULL 列降级为可空（旧数据 NULL）
- 主键列缺失说明表结构异常，跳过并告警
"""
import logging
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Set

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.sql.schema import Table

logger = logging.getLogger("offerclaw.migrations")

# 迁移前自动备份根目录
from app.core.paths import data_dir as _data_dir
BACKUP_DIR = _data_dir() / "backups"


def backup_all_tables(engine: Engine) -> Path | None:
    """迁移前把所有表导出为 JSON 备份（安全网，绝不丢数据）"""
    try:
        insp = inspect(engine)
        tables = insp.get_table_names()
        if not tables:
            return None
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        bk_dir = BACKUP_DIR / f"pre_migrate_{ts}"
        bk_dir.mkdir(parents=True, exist_ok=True)

        def _default(o):
            if isinstance(o, datetime):
                return o.isoformat()
            return str(o)

        with engine.begin() as conn:
            for tname in tables:
                try:
                    rows = conn.execute(text(f'SELECT * FROM "{tname}"')).fetchall()
                    data = [dict(r._mapping) for r in rows]
                    (bk_dir / f"{tname}.json").write_text(
                        json.dumps(data, ensure_ascii=False, indent=2, default=_default),
                        encoding="utf-8",
                    )
                except Exception as e:
                    logger.warning(f"备份表 {tname} 失败：{e}")
        logger.info(f"迁移前备份完成：{len(tables)} 张表 → {bk_dir}")
        return bk_dir
    except Exception as e:
        logger.error(f"迁移前备份失败（继续迁移）：{e}")
        return None


def _compile_col_type(col, dialect) -> str:
    """把 SQLAlchemy 列类型编译为目标方言的类型字符串"""
    try:
        type_str = str(col.type.compile(dialect=dialect))
        return type_str or "TEXT"
    except Exception:
        # 退化：按常见类型映射
        tname = type(col.type).__name__.lower()
        return {
            "string": "VARCHAR(255)", "text": "TEXT", "integer": "INTEGER",
            "float": "REAL", "boolean": "BOOLEAN", "datetime": "DATETIME",
            "date": "DATE", "time": "TIME", "json": "JSON", "enum": "VARCHAR(50)",
        }.get(tname, "TEXT")


def _server_default_sql(col) -> str | None:
    """提取列的默认值 SQL 片段（server_default 优先，其次 Python scalar default）

    用于 ADD COLUMN 的 DEFAULT 子句，确保旧数据行有合理默认值
    （如 priority='medium'、status='applied'）。
    """
    # 1. server_default（数据库层）
    sd = col.server_default
    # 2. Python 层 default（如 default="medium"）
    default = getattr(col, "default", None)
    for src in (sd, default):
        if src is None:
            continue
        try:
            a = getattr(src, "arg", src)
            if callable(a) or a is None:
                continue
            if isinstance(a, bool):
                return "1" if a else "0"
            if isinstance(a, str):
                return f"'{a}'" if not a.startswith("'") else a
            if isinstance(a, (int, float)):
                return str(a)
        except Exception:
            continue
    return None


def _migrate_table(engine: Engine, table: Table, existing_cols: Set[str]) -> int:
    """对单张已存在的表补齐缺失列；返回新增列数"""
    dialect = engine.dialect
    added = 0
    for col in table.columns:
        if col.name in existing_cols:
            continue
        # 主键列缺失 = 表结构异常（不应自动加），跳过告警
        if col.primary_key:
            logger.warning(
                f"  ⚠ {table.name}.{col.name} 为主键列但缺失，表结构异常，跳过（请手动处理）"
            )
            continue

        col_type = _compile_col_type(col, dialect)
        # SQLite：ADD COLUMN NOT NULL 必须有 DEFAULT，否则报错；无默认值时降级为可空
        nullable = col.nullable
        if not nullable and _server_default_sql(col) is None:
            nullable = True
            logger.info(
                f"  ℹ {table.name}.{col.name} 标记 NOT NULL 但无默认值，迁移降级为可空（旧数据 NULL）"
            )

        stmt = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col_type}'
        if not nullable:
            stmt += " NOT NULL"
        sd_sql = _server_default_sql(col)
        if sd_sql is not None:
            stmt += f" DEFAULT {sd_sql}"

        try:
            with engine.begin() as conn:
                conn.execute(text(stmt))
            added += 1
            logger.info(f"  + {table.name}.{col.name} ({col_type})")
        except Exception as e:
            logger.warning(f"  ✗ {table.name}.{col.name} 迁移失败：{e}")
    return added


def auto_migrate(engine: Engine, base_meta) -> int:
    """泛化自动迁移入口：对所有注册的 model 表补齐缺失列

    Args:
        engine: SQLAlchemy engine
        base_meta: Base.metadata（含所有 Table 定义）

    Returns:
        新增列总数
    """
    insp = inspect(engine)
    db_tables = set(insp.get_table_names())
    total_added = 0

    if db_tables:
        # 有表才备份（首次启动无表无需备份）
        backup_all_tables(engine)

    for table_name, table in base_meta.tables.items():
        if table_name not in db_tables:
            # 不存在的表由 create_all 创建，此处跳过
            continue
        existing_cols = {c["name"] for c in insp.get_columns(table_name)}
        missing = [c for c in table.columns if c.name not in existing_cols and not c.primary_key]
        if not missing:
            continue
        logger.info(f"迁移表 {table_name}：补齐 {len(missing)} 列")
        total_added += _migrate_table(engine, table, existing_cols)

    if total_added:
        logger.info(f"自动迁移完成：共新增 {total_added} 列")
    else:
        logger.info("自动迁移完成：无需变更")
    return total_added
