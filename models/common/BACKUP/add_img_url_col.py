# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import argparse
import logging
from typing import List, Tuple, Optional

from sqlalchemy import text

# 你的 handler（請依你的實際路徑調整 import）
from sql_db_connect import MySQLConnet


LOG = logging.getLogger("add_img_url_col")


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )


RE_YYYYMM = re.compile(r"^cim_defect_(\d{6})_", re.IGNORECASE)


def extract_yyyymm(table_name: str) -> Optional[str]:
    m = RE_YYYYMM.match(table_name or "")
    return m.group(1) if m else None


def get_defect_tables_missing_col(
    engine,
    schema: str,
    table_like: str,
    col_name: str
) -> List[str]:
    sql = text("""
        SELECT t.TABLE_NAME
        FROM information_schema.TABLES t
        WHERE t.TABLE_SCHEMA = :schema
          AND t.TABLE_NAME LIKE :like_pat
          AND NOT EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS c
            WHERE c.TABLE_SCHEMA = t.TABLE_SCHEMA
              AND c.TABLE_NAME = t.TABLE_NAME
              AND c.COLUMN_NAME = :col_name
          )
        ORDER BY t.TABLE_NAME
    """)
    with engine.begin() as conn:
        rows = conn.execute(sql, {"schema": schema, "like_pat": table_like, "col_name": col_name}).fetchall()
    return [r[0] for r in rows]


def alter_add_column(engine, schema: str, table: str, col_name: str, after_col: str, col_type: str):
    ddl = f"ALTER TABLE `{schema}`.`{table}` ADD COLUMN `{col_name}` {col_type} NULL AFTER `{after_col}`"
    with engine.begin() as conn:
        conn.execute(text(ddl))


def update_fill_from_image_path(engine, schema: str, table: str, col_name: str, src_col: str):
    sql = text(f"""
        UPDATE `{schema}`.`{table}`
        SET `{col_name}` = `{src_col}`
        WHERE `{col_name}` IS NULL OR `{col_name}` = ''
    """)
    with engine.begin() as conn:
        r = conn.execute(sql)
        return r.rowcount


def main():
    setup_logging()

    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="cim_piaoi", help="MySQL database/schema name")
    ap.add_argument("--like", default="cim_defect\\_%", help="table name LIKE pattern (escape _ with \\_)")
    ap.add_argument("--col", default="img_file_url_path", help="new column name")
    ap.add_argument("--after", default="image_file_path", help="add column after this column")
    ap.add_argument("--type", default="TEXT", help="column type, default TEXT")
    ap.add_argument("--cutoff", default="202602", help="YYYYMM cutoff; before this fill col= image_file_path")
    ap.add_argument("--dry-run", action="store_true", help="print actions only, do not execute")
    args = ap.parse_args()

    db = args.db
    sql_db = MySQLConnet(db)
    engine = sql_db.engine

    # 1) 找缺欄位的 defect tables
    missing = get_defect_tables_missing_col(engine, db, args.like, args.col)
    LOG.info(f"[scan] missing column '{args.col}' tables = {len(missing)}")

    # 2) 逐表 ALTER
    for t in missing:
        LOG.info(f"[alter] {db}.{t} ADD COLUMN {args.col}")
        if not args.dry_run:
            alter_add_column(engine, db, t, args.col, args.after, args.type)

    LOG.info("[alter] done")

    # 3) 202602 以前：補值 img_file_url_path = image_file_path
    cutoff = args.cutoff  # '202602'
    filled_tables = 0
    filled_rows_total = 0

    # 只針對 cim_defect_YYYYMM_... 格式的表做判斷
    candidates = missing  # 缺欄位者剛新增完，先補它們
    # 如果你也想對「原本就有欄位但未補值」的舊表做補值，可改成掃全部 cim_defect_% 表

    for t in candidates:
        yyyymm = extract_yyyymm(t)
        if not yyyymm:
            LOG.warning(f"[skip] cannot parse yyyymm from table: {t}")
            continue

        if yyyymm < cutoff:
            LOG.info(f"[fill] {db}.{t} set {args.col}={args.after} where empty (yyyymm={yyyymm} < {cutoff})")
            if not args.dry_run:
                n = update_fill_from_image_path(engine, db, t, args.col, args.after)
                filled_tables += 1
                filled_rows_total += int(n or 0)

    LOG.info(f"[fill] done: tables={filled_tables}, rows_updated={filled_rows_total}")
    LOG.info("ALL DONE.")


if __name__ == "__main__":
    main()


#python add_img_url_col.py --dry-run

#python add_img_url_col.py