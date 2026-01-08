#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
from typing import Optional, List, Dict, Any
import argparse

import pandas as pd
from sqlalchemy import text

from sql_db_func import MySQLConnetFunc


# ===== Logging 設定 =====
LOG_FILE = "inspection_backfill_glass_size_detail.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ],
)
logger = logging.getLogger(__name__)

DB_NAME = "l6a01_project"


def ensure_column(dbhandler: MySQLConnetFunc, table_name: str, col: str, ddl: str):
    sql = text("""
      SELECT COUNT(*) FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c
    """)
    with dbhandler.engine.begin() as conn:
        exists = conn.execute(sql, {"t": table_name, "c": col}).scalar()
        if not exists:
            conn.execute(text(f"ALTER TABLE `{table_name}` ADD COLUMN `{col}` {ddl}"))
            logger.info(f"[{table_name}] ADD COLUMN {col} {ddl}")


def load_raw_month(dbhandler: MySQLConnetFunc, ym: str) -> pd.DataFrame:
    raw_tbn = f"inspection_raw_table_{ym}"
    logger.info(f"讀取 raw: {raw_tbn}")

    sql = text(f"""
        SELECT
          SHEET_ID,
          TOOL_ID,
          RECIPE_NAME,
          SCAN_ENDTIME,
          DEFECT_SIZE_TYPE
        FROM `{raw_tbn}`
    """)

    with dbhandler.engine.begin() as conn:
        df = pd.read_sql(sql, conn)

    logger.info(f"[{raw_tbn}] rows={len(df)}")
    return df


def build_detail_map_from_raw(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    輸出 df_detail：
      key: pi_hour,line_id,model,glass_type
      value: glass_size_detail (LONGTEXT)
    """
    if raw_df.empty:
        return pd.DataFrame(columns=["pi_hour", "line_id", "model", "glass_type", "glass_size_detail"])

    df = raw_df.copy()

    # ---- normalize / derive columns ----
    dt = pd.to_datetime(df["SCAN_ENDTIME"], errors="coerce")
    df["pi_hour"] = dt.dt.floor("h").dt.strftime("%Y-%m-%d %H")  # ✅ 用 'h'，避免 FutureWarning
    df["line_id"] = df["TOOL_ID"].astype(str)
    df["glass_id"] = df["SHEET_ID"].astype(str)
    df["size"] = df["DEFECT_SIZE_TYPE"].astype(str)

    # RECIPE_NAME -> model, glass_type（用第一個 '-' 切）
    parts = df["RECIPE_NAME"].astype(str).str.split("-", n=1, expand=True)
    df["model"] = parts[0]
    if parts.shape[1] > 1:
        df["glass_type"] = parts[1]
    else:
        df["glass_type"] = ""

    # 去掉欄位重名（保險）
    df = df.loc[:, ~df.columns.duplicated()].copy()

    # 避免 size 空值/怪值
    df = df[df["size"].isin(["S", "M", "L", "O"])].copy()

    if df.empty:
        return pd.DataFrame(columns=["pi_hour", "line_id", "model", "glass_type", "glass_size_detail"])

    # ---- per-glass count ----
    # group keys: pi_hour,line_id,model,glass_type,glass_id,size => count
    g = (
        df.groupby(["pi_hour", "line_id", "model", "glass_type", "glass_id", "size"])
          .size()
          .unstack(fill_value=0)
          .reset_index()
    )

    # 確保 S/M/L/O 欄都存在
    for c in ["S", "M", "L", "O"]:
        if c not in g.columns:
            g[c] = 0

    # 每片玻璃字串：gid:S=..;M=..;L=..;O=..
    g["glass_part"] = (
        g["glass_id"].astype(str)
        + ":S=" + g["S"].astype(int).astype(str)
        + ";M=" + g["M"].astype(int).astype(str)
        + ";L=" + g["L"].astype(int).astype(str)
        + ";O=" + g["O"].astype(int).astype(str)
    )

    # ---- group aggregate: join parts into LONGTEXT ----
    detail = (
        g.groupby(["pi_hour", "line_id", "model", "glass_type"])["glass_part"]
         .apply(lambda s: ",".join(s.tolist()))
         .reset_index()
         .rename(columns={"glass_part": "glass_size_detail"})
    )

    return detail


def update_api_summary(dbhandler: MySQLConnetFunc, ym: str, detail_df: pd.DataFrame, chunk_size: int = 1000):
    api_tbn = f"inspection_api_summary_{ym}"
    ensure_column(dbhandler, api_tbn, "glass_size_detail", "LONGTEXT")

    if detail_df.empty:
        logger.info(f"[{api_tbn}] detail_df is empty, skip update.")
        return

    logger.info(f"[{api_tbn}] 準備回灌筆數: {len(detail_df)}")

    sql_update = text(f"""
        UPDATE `{api_tbn}`
        SET glass_size_detail = :glass_size_detail
        WHERE pi_hour = :pi_hour
          AND line_id = :line_id
          AND model = :model
          AND glass_type = :glass_type
    """)

    rows = detail_df.to_dict("records")

    updated_total = 0
    with dbhandler.engine.begin() as conn:
        for i in range(0, len(rows), chunk_size):
            batch = rows[i:i+chunk_size]
            res = conn.execute(sql_update, batch)
            # MySQL rowcount：通常是匹配到的列數（有時候會受 client 設定影響）
            updated_total += int(res.rowcount or 0)
            logger.info(f"[{api_tbn}] batch {i}~{i+len(batch)-1} updated(rowcount)={res.rowcount}")

    logger.info(f"[{api_tbn}] 回灌完成，累計 rowcount={updated_total}")


def backfill_glass_size_detail(dbhandler: MySQLConnetFunc, ym: str):
    logger.info(f"=== Backfill {ym} -> inspection_api_summary_{ym}.glass_size_detail ===")
    raw_df = load_raw_month(dbhandler, ym)
    detail_df = build_detail_map_from_raw(raw_df)
    update_api_summary(dbhandler, ym, detail_df, chunk_size=500)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--months",
        nargs="*",
        default=[],
        help="指定要回灌的月份，例如: --months 202511 202512"
    )
    args = parser.parse_args()

    months: List[str] = args.months or ["202511", "202512"]  #  你要回灌兩個月，預設就跑這兩個

    dbhandler = MySQLConnetFunc(DB_NAME)

    for ym in months:
        try:
            backfill_glass_size_detail(dbhandler, ym)
        except Exception as e:
            logger.exception(f"[{ym}] backfill failed: {e}")

    logger.info("=== ALL DONE ===")


if __name__ == "__main__":
    main()