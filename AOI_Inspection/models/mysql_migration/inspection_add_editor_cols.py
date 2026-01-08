#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
from datetime import datetime
from typing import List, Optional, Tuple

import pandas as pd
from sqlalchemy import text

from sql_db_func import MySQLConnetFunc


# ===== Logging =====
LOG_FILE = "inspection_backfill_api_summary_upsert.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(funcName)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler()],
)

logger = logging.getLogger(__name__)

DB_NAME = "l6a01_project"

SUMMARY_BASE_TBN = "inspection_summary_table"
RAW_BASE_TBN = "inspection_raw_table"

DEFECT_SIZE_COL = "DEFECT_SIZE_TYPE"
UNI_DEFECT_SIZES = ["S", "M", "L", "O"]
GROUP_KEYS = ["HOURLY", "TOOL_ID", "MODEL_NO", "TYPE"]
UNI_GLASS_KEYS = ["SHEET_ID", "SCAN_ENDTIME"]

GROUP_TABLE_KEYS = (
    GROUP_KEYS
    + ["hourly_run_glass_count", "hourly_defect_count", "hourly_defect_glass_couunt"]
    + UNI_DEFECT_SIZES
    + ["glass", "glass_size_detail", "comment", "Editor", "modify_time"]
)

NEW_COLDICT = {
    "HOURLY": "pi_hour",
    "TOOL_ID": "line_id",
    "MODEL_NO": "model",
    "TYPE": "glass_type",
    "hourly_run_glass_count": "maingroup_glass_count",
    "hourly_defect_count": "maingroup_defect_count",
    "hourly_defect_glass_couunt": "defect_code_glass_count",
    "S": "small_defect_count",
    "M": "middle_defect_count",
    "L": "large_defect_count",
    "O": "over_defect_count",
    "glass": "glass",
    "glass_size_detail": "glass_size_detail",
    "comment": "comment",
    "Editor": "Editor",
    "modify_time": "modify_time",
}

API_COLS = [
    "pi_hour", "line_id", "model", "glass_type",
    "maingroup_glass_count", "maingroup_defect_count", "defect_code_glass_count",
    "small_defect_count", "middle_defect_count", "large_defect_count", "over_defect_count",
    "glass", "glass_size_detail",
    "comment", "Editor", "modify_time",
]


# =========================
# schema helpers
# =========================
def ensure_column(dbhandler: MySQLConnetFunc, table_name: str, col: str, ddl: str) -> None:
    sql = text("""
      SELECT COUNT(*) FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c
    """)
    with dbhandler.engine.begin() as conn:
        exists = conn.execute(sql, {"t": table_name, "c": col}).scalar()
        if not exists:
            conn.execute(text(f"ALTER TABLE `{table_name}` ADD COLUMN `{col}` {ddl}"))
            logger.info(f"[{table_name}] ADD COLUMN {col} {ddl}")


def get_col_type(dbhandler: MySQLConnetFunc, table_name: str, col: str) -> Optional[str]:
    sql = text("""
      SELECT DATA_TYPE FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c
    """)
    with dbhandler.engine.begin() as conn:
        t = conn.execute(sql, {"t": table_name, "c": col}).scalar()
    return None if t is None else str(t).lower()


def ensure_key_columns_are_indexable(dbhandler: MySQLConnetFunc, table_name: str) -> None:
    """
    避免 (1170) BLOB/TEXT used in key specification
    先把 key 欄位改成 VARCHAR。
    """
    targets = {
        "pi_hour": "VARCHAR(13)",    # 'YYYY-MM-DD HH'
        "line_id": "VARCHAR(32)",
        "model": "VARCHAR(64)",
        "glass_type": "VARCHAR(32)",
    }
    text_like = {"tinytext", "text", "mediumtext", "longtext", "blob", "mediumblob", "longblob"}

    with dbhandler.engine.begin() as conn:
        for col, ddl in targets.items():
            t = get_col_type(dbhandler, table_name, col)
            if t is None:
                continue
            if t in text_like:
                # 先把 NULL 轉成空字串避免 NOT NULL 報錯
                conn.execute(text(f"UPDATE `{table_name}` SET `{col}`='' WHERE `{col}` IS NULL"))
                conn.execute(text(f"ALTER TABLE `{table_name}` MODIFY COLUMN `{col}` {ddl} NOT NULL"))
                logger.info(f"[{table_name}] MODIFY COLUMN {col} {ddl} NOT NULL (was {t})")


def ensure_unique_index(dbhandler: MySQLConnetFunc, table_name: str) -> None:
    idx_name = "uniq_pi_hour_line_model_type"
    sql = text("""
      SELECT COUNT(*) FROM information_schema.STATISTICS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND INDEX_NAME = :idx
    """)
    with dbhandler.engine.begin() as conn:
        exists = conn.execute(sql, {"t": table_name, "idx": idx_name}).scalar()
        if not exists:
            # 先確保 key 欄位可索引
            ensure_key_columns_are_indexable(dbhandler, table_name)
            conn.execute(text(
                f"ALTER TABLE `{table_name}` "
                f"ADD UNIQUE KEY `{idx_name}` (`pi_hour`,`line_id`,`model`,`glass_type`)"
            ))
            logger.info(f"[{table_name}] ADD UNIQUE KEY {idx_name} (pi_hour,line_id,model,glass_type)")


def ensure_api_table_schema(dbhandler: MySQLConnetFunc, api_tbn: str) -> None:
    ensure_column(dbhandler, api_tbn, "glass_size_detail", "LONGTEXT")
    ensure_column(dbhandler, api_tbn, "comment", "TEXT")
    ensure_column(dbhandler, api_tbn, "Editor", "VARCHAR(64)")
    ensure_column(dbhandler, api_tbn, "modify_time", "DATETIME")
    # 這裡會先修正欄位型別再加 unique
    ensure_unique_index(dbhandler, api_tbn)


# =========================
# clean helpers
# =========================
def _add_hourly_col(df: pd.DataFrame, time_col: str = "SCAN_ENDTIME") -> pd.DataFrame:
    if time_col not in df.columns:
        return df
    df = df.copy()
    dt = pd.to_datetime(df[time_col], errors="coerce")
    df["HOURLY"] = dt.dt.floor("h").dt.strftime("%Y-%m-%d %H")
    return df


def _split_recipe_to_model_type(df: pd.DataFrame, col: str = "RECIPE_NAME") -> pd.DataFrame:
    if col not in df.columns:
        return df
    df = df.copy()
    s = df[col].astype(str)
    parts = s.str.split("-", n=1, expand=True)
    df["MODEL_NO"] = parts[0]
    df["TYPE"] = parts[1] if parts.shape[1] > 1 else ""
    return df


# =========================
# build api df
# =========================
def build_api_summary_df(summary_df: pd.DataFrame, raw_df: pd.DataFrame) -> pd.DataFrame:
    if summary_df.empty:
        return pd.DataFrame(columns=GROUP_TABLE_KEYS)

    summary_groups = summary_df.groupby(GROUP_KEYS)
    raw_groups = raw_df.groupby(GROUP_KEYS) if not raw_df.empty else None

    api_rows = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for main_keys, summary_rows in summary_groups:
        hour, tool_id, model_no, type_ = main_keys

        glass_ids = summary_rows["SHEET_ID"].astype(str).dropna().unique().tolist()
        glass_str = ",".join(glass_ids)

        hourly_run_glass_count = int(len(summary_rows))
        hourly_defect_count = 0
        hourly_defect_glass_couunt = 0
        size_counts = {s: 0 for s in UNI_DEFECT_SIZES}
        glass_size_detail = ""

        if raw_groups is not None:
            try:
                raw_rows = raw_groups.get_group(main_keys)

                hourly_defect_count = int(len(raw_rows))
                hourly_defect_glass_couunt = int(len(raw_rows.groupby(UNI_GLASS_KEYS)))

                for s in UNI_DEFECT_SIZES:
                    size_counts[s] = int((raw_rows[DEFECT_SIZE_COL] == s).sum())

                raw_rows2 = raw_rows.copy()
                raw_rows2["SHEET_ID"] = raw_rows2["SHEET_ID"].astype(str)

                parts = []
                for gid in glass_ids:
                    one = raw_rows2[raw_rows2["SHEET_ID"] == gid]
                    s_cnt = int((one[DEFECT_SIZE_COL] == "S").sum())
                    m_cnt = int((one[DEFECT_SIZE_COL] == "M").sum())
                    l_cnt = int((one[DEFECT_SIZE_COL] == "L").sum())
                    o_cnt = int((one[DEFECT_SIZE_COL] == "O").sum())
                    parts.append(f"{gid}:S={s_cnt};M={m_cnt};L={l_cnt};O={o_cnt}")
                glass_size_detail = ",".join(parts)

            except KeyError:
                pass

        row = {
            "HOURLY": hour,
            "TOOL_ID": tool_id,
            "MODEL_NO": model_no,
            "TYPE": type_,
            "hourly_run_glass_count": hourly_run_glass_count,
            "hourly_defect_count": hourly_defect_count,
            "hourly_defect_glass_couunt": hourly_defect_glass_couunt,
            "S": size_counts["S"],
            "M": size_counts["M"],
            "L": size_counts["L"],
            "O": size_counts["O"],
            "glass": glass_str,
            "glass_size_detail": glass_size_detail,
            "comment": "",
            "Editor": "",
            "modify_time": now_str,
        }
        api_rows.append(row)

    return pd.DataFrame(api_rows, columns=GROUP_TABLE_KEYS)


# =========================
# upsert
# =========================
def upsert_api_summary(dbhandler: MySQLConnetFunc, api_tbn: str, df: pd.DataFrame) -> None:
    if df.empty:
        logger.info(f"[{api_tbn}] df empty, skip")
        return

    ensure_api_table_schema(dbhandler, api_tbn)

    df2 = df.copy()
    for c in API_COLS:
        if c not in df2.columns:
            df2[c] = None
    df2 = df2[API_COLS].copy()

    cols_sql = ",".join([f"`{c}`" for c in API_COLS])
    placeholders = ",".join([f":{c}" for c in API_COLS])

    update_sql = """
      `maingroup_glass_count`=VALUES(`maingroup_glass_count`),
      `maingroup_defect_count`=VALUES(`maingroup_defect_count`),
      `defect_code_glass_count`=VALUES(`defect_code_glass_count`),
      `small_defect_count`=VALUES(`small_defect_count`),
      `middle_defect_count`=VALUES(`middle_defect_count`),
      `large_defect_count`=VALUES(`large_defect_count`),
      `over_defect_count`=VALUES(`over_defect_count`),
      `glass`=VALUES(`glass`),
      `glass_size_detail`=VALUES(`glass_size_detail`),

      `comment` = IF(`comment` IS NOT NULL AND `comment` <> '', `comment`, VALUES(`comment`)),
      `Editor`  = IF(`Editor`  IS NOT NULL AND `Editor`  <> '', `Editor`,  VALUES(`Editor`)),

      `modify_time` = IF(
          (`comment` IS NOT NULL AND `comment` <> '') OR (`Editor` IS NOT NULL AND `Editor` <> ''),
          `modify_time`,
          VALUES(`modify_time`)
      )
    """

    sql = text(f"""
      INSERT INTO `{api_tbn}` ({cols_sql})
      VALUES ({placeholders})
      ON DUPLICATE KEY UPDATE
      {update_sql}
    """)

    rows = df2.to_dict(orient="records")
    chunk = 2000
    with dbhandler.engine.begin() as conn:
        for i in range(0, len(rows), chunk):
            conn.execute(sql, rows[i:i+chunk])

    logger.info(f"[{api_tbn}] upsert 完成，共 {len(df2)} 筆（含更新/新增）")


def backfill_one_month(dbhandler: MySQLConnetFunc, ym: str) -> None:
    summary_tbn = f"{SUMMARY_BASE_TBN}_{ym}"
    raw_tbn = f"{RAW_BASE_TBN}_{ym}"
    api_tbn = f"inspection_api_summary_{ym}"

    logger.info(f"=== Backfill {ym} -> {api_tbn} ===")

    summary_df = dbhandler.get_table(summary_tbn)
    raw_df = dbhandler.get_table(raw_tbn)

    if summary_df.empty:
        logger.warning(f"[{summary_tbn}] 無資料，略過")
        return

    summary_df = _add_hourly_col(summary_df, "SCAN_ENDTIME")
    raw_df = _split_recipe_to_model_type(raw_df, "RECIPE_NAME")
    raw_df = _add_hourly_col(raw_df, "SCAN_ENDTIME")

    api_df = build_api_summary_df(summary_df, raw_df).rename(columns=NEW_COLDICT)

    upsert_api_summary(dbhandler, api_tbn, api_df)


def main():
    dbhandler = MySQLConnetFunc(DB_NAME)

    for ym in ["202511", "202512"]:
        backfill_one_month(dbhandler, ym)

    logger.info("=== Backfill Done ===")


if __name__ == "__main__":
    main()