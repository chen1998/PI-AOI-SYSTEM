#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple

import requests
import pandas as pd
from sqlalchemy import text

from sql_db_func import MySQLConnetFunc


# ===== Logging 設定 =====
LOG_FILE = "datamall_inspection_job.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(funcName)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ],
)
logger = logging.getLogger(__name__)


# ===== 常數設定 =====
DB_NAME = "l6a01_project"

PROXY_DICT = {
    "http": "http://10.97.4.1:8080",
    "https": "http://10.97.4.1:8080",
}

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/74.0.3729.157 Safari/537.36"
    ),
    "Content-Type": "application/json",
}

MAX_RETRY = 6
RETRY_SLEEP_SEC = 30
REQUEST_TIMEOUT = 20


SUMMARY_URL = (
    "http://tcpaaie101.corpnet.auo.com:8005/api/datamall/"
    "eyJrZXkiOiAiMTcwZWNhZWMxNzAyZmJiZmQ4ZDljMTA3Y2U2YzI3NTQiLCAiaWQiOiAiMjAyMzA5MDYxNzUyMTU3MTE0MyJ9"
)
RAW_URL = (
    "http://tcpaaie101.corpnet.auo.com:8005/api/datamall/"
    "eyJrZXkiOiAiMjcwOWJlNzc4ZWNmOWZhMGEzYjc2MjBjN2MzNjMwN2YiLCAiaWQiOiAiMjAyMzA5MDYxNzUyNDg3MTE0NCJ9"
)

SUMMARY_COLS = [
    "CHIP_COUNT", "CHIP_JUDGE", "CHIP_OK_COUNT", "DEFECT", "FAB",
    "MODEL_NO", "RECIPE_NAME", "RUN_ID", "SCAN_ENDTIME", "SCAN_STARTTIME",
    "SHEET_ID", "STAGE", "TOOL_ID", "TOTAL_DEFECT_COUNT", "TYPE",
]
RAW_COLS = [
    "COORD_X", "COORD_Y", "DEFECT", "DEFECT_AREA", "DEFECT_ID",
    "DEFECT_SIZE_TYPE", "FAB", "FRONT_REVERSE", "IMG_URL", "RECIPE_NAME",
    "RUN_ID", "SCAN_ENDTIME", "SCAN_STARTTIME", "SHEET_ID", "SP", "STAGE",
    "TOOL_ID", "TOTAL_DEFECT_COUNT",
]

SUMMARY_BASE_TBN = "inspection_summary_table"
RAW_BASE_TBN = "inspection_raw_table"

DEFECT_SIZE_COL = "DEFECT_SIZE_TYPE"
UNI_DEFECT_SIZES: List[str] = ["S", "M", "L", "O"]
GROUP_KEYS = ["HOURLY", "TOOL_ID", "MODEL_NO", "TYPE"]
UNI_GLASS_KEYS = ["SHEET_ID", "SCAN_ENDTIME"]

GROUP_TABLE_KEYS = (
    GROUP_KEYS
    + ["hourly_run_glass_count", "hourly_defect_count", "hourly_defect_glass_couunt"]
    + UNI_DEFECT_SIZES
    + ["glass", "glass_size_detail", "comment", "action", "Editor", "modify_time"]
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
    "action": "action",
    "Editor": "Editor",
    "modify_time": "modify_time",
}

API_COLS = [
    "pi_hour", "line_id", "model", "glass_type",
    "maingroup_glass_count", "maingroup_defect_count", "defect_code_glass_count",
    "small_defect_count", "middle_defect_count", "large_defect_count", "over_defect_count",
    "glass", "glass_size_detail",
    "comment", "action", "Editor", "modify_time",
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
            ensure_key_columns_are_indexable(dbhandler, table_name)
            conn.execute(text(
                f"ALTER TABLE `{table_name}` "
                f"ADD UNIQUE KEY `{idx_name}` (`pi_hour`,`line_id`,`model`,`glass_type`)"
            ))
            logger.info(f"[{table_name}] ADD UNIQUE KEY {idx_name} (pi_hour,line_id,model,glass_type)")


def _table_exists(dbhandler: MySQLConnetFunc, table_name: str) -> bool:
    sql = text("""
      SELECT COUNT(*) FROM information_schema.TABLES
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t
    """)
    with dbhandler.engine.begin() as conn:
        cnt = conn.execute(sql, {"t": table_name}).scalar()
    return bool(cnt)


def _get_latest_api_template_table(dbhandler: MySQLConnetFunc) -> Optional[str]:
    """
    從現有 DB 中找一張已存在的 inspection_api_summary_% 當 template。
    取 TABLE_NAME 最大的一個（通常是最新月份）。
    """
    sql = text("""
      SELECT TABLE_NAME
      FROM information_schema.TABLES
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME LIKE 'inspection_api_summary_%'
      ORDER BY TABLE_NAME DESC
      LIMIT 1
    """)
    with dbhandler.engine.begin() as conn:
        row = conn.execute(sql).scalar()
    return None if row is None else str(row)


def ensure_api_table_exists(dbhandler: MySQLConnetFunc, api_tbn: str) -> None:
    """
    確保 inspection_api_summary_YYYYMM 這張表存在。
    - 若已存在：直接 return
    - 若不存在：
        1) 優先找一張現有的 inspection_api_summary_% 當 template → CREATE TABLE new LIKE template
        2) 若完全沒有 template → 用 fallback DDL 建一張有完整欄位與 unique key 的表
    """
    if _table_exists(dbhandler, api_tbn):
        return

    logger.info(f"[{api_tbn}] 不存在，嘗試以既有 inspection_api_summary_% 為模板建立")

    template_tbn = _get_latest_api_template_table(dbhandler)

    with dbhandler.engine.begin() as conn:
        if template_tbn:
            logger.info(f"[{api_tbn}] 使用 template: {template_tbn}")
            conn.execute(text(f"CREATE TABLE `{api_tbn}` LIKE `{template_tbn}`"))
            logger.info(f"[{api_tbn}] CREATE TABLE LIKE `{template_tbn}` 完成")
            return

        # ---- 沒有任何 template，使用 fallback DDL 建表 ----
        logger.warning(
            f"[{api_tbn}] 找不到任何 inspection_api_summary_% template，"
            f"將使用 fallback DDL 建立新表"
        )

        ddl = f"""
        CREATE TABLE `{api_tbn}` (
          `pi_hour`              VARCHAR(13)  NOT NULL,
          `line_id`              VARCHAR(32)  NOT NULL,
          `model`                VARCHAR(64)  NOT NULL,
          `glass_type`           VARCHAR(32)  NOT NULL,
          `maingroup_glass_count`   INT       DEFAULT NULL,
          `maingroup_defect_count`  INT       DEFAULT NULL,
          `defect_code_glass_count` INT       DEFAULT NULL,
          `small_defect_count`      INT       DEFAULT NULL,
          `middle_defect_count`     INT       DEFAULT NULL,
          `large_defect_count`      INT       DEFAULT NULL,
          `over_defect_count`       INT       DEFAULT NULL,
          `glass`                LONGTEXT,
          `glass_size_detail`    LONGTEXT,
          `comment`              TEXT,
          `Editor`               VARCHAR(64)  DEFAULT NULL,
          `modify_time`          DATETIME     DEFAULT NULL,
          UNIQUE KEY `uniq_pi_hour_line_model_type`
            (`pi_hour`,`line_id`,`model`,`glass_type`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        conn.execute(text(ddl))
        logger.info(f"[{api_tbn}] fallback DDL 建表完成")


def ensure_api_table_schema(dbhandler: MySQLConnetFunc, api_tbn: str) -> None:
    # 先確保這個月份的 inspection_api_summary_YYYYMM 表一定存在
    ensure_api_table_exists(dbhandler, api_tbn)

    # 再確保欄位 & unique key schema OK
    ensure_column(dbhandler, api_tbn, "glass_size_detail", "LONGTEXT")
    ensure_column(dbhandler, api_tbn, "comment", "TEXT")
    ensure_column(dbhandler, api_tbn, "action", "TEXT")
    ensure_column(dbhandler, api_tbn, "Editor", "VARCHAR(64)")
    ensure_column(dbhandler, api_tbn, "modify_time", "DATETIME")
    ensure_unique_index(dbhandler, api_tbn)


# =========================
# Datamall helpers
# =========================
def datamall_get(url: str, session: requests.Session, max_retry: int = MAX_RETRY) -> Optional[Dict[str, Any]]:
    for attempt in range(1, max_retry + 1):
        try:
            logger.info(f"Datamall GET (try {attempt}/{max_retry}): {url}")
            resp = session.get(url, headers=REQUEST_HEADERS, proxies=PROXY_DICT, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.warning(f"Datamall GET 失敗 (attempt {attempt}): {e}")
            if attempt < max_retry:
                time.sleep(RETRY_SLEEP_SEC)
            else:
                return None
        except ValueError:
            return None


def load_and_append(dbhandler: MySQLConnetFunc, url: str, table_name: str, cols: list, session: requests.Session, key_in_json: str = "1") -> None:
    data = datamall_get(url, session=session)
    if data is None or key_in_json not in data:
        logger.error(f"[{table_name}] datamall 取得失敗或缺 key={key_in_json}")
        return

    df = pd.DataFrame(data[key_in_json])
    if df.empty:
        logger.info(f"[{table_name}] 無新資料")
        return

    df = df[cols].copy()
    dbhandler.append_new_rows(df, table_name, cols)
    logger.info(f"[{table_name}] append_new_rows done, datamall_rows={len(df)}")


# =========================
# Clean helpers
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


def get_tables(dbhandler: MySQLConnetFunc, summary_tbn: str, raw_tbn: str, boundary_hour: Optional[str] = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
    summary_df = dbhandler.get_table(summary_tbn)
    raw_df = dbhandler.get_table(raw_tbn)

    summary_df = _add_hourly_col(summary_df, "SCAN_ENDTIME")
    raw_df = _split_recipe_to_model_type(raw_df, "RECIPE_NAME")
    raw_df = _add_hourly_col(raw_df, "SCAN_ENDTIME")

    if boundary_hour:
        summary_df = summary_df[summary_df["HOURLY"] >= boundary_hour].copy()
        raw_df = raw_df[raw_df["HOURLY"] >= boundary_hour].copy()

    return summary_df, raw_df


# =========================
# Build api summary df
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
        else:
            for gid in glass_ids:
                parts.append(f"{gid}:S=0;M=0;L=0;O=0")


        api_rows.append({
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
            "action": "",
            "Editor": "",
            "modify_time": now_str,
        })

    return pd.DataFrame(api_rows, columns=GROUP_TABLE_KEYS)


# =========================
# Upsert
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
      `action`  = IF(`action` IS NOT NULL AND `action` <> '', `action`, VALUES(`action`)),
      `Editor`  = IF(`Editor`  IS NOT NULL AND `Editor`  <> '', `Editor`,  VALUES(`Editor`)),

      `modify_time` = IF(
            (`comment` IS NOT NULL AND `comment` <> '') 
        OR (`Editor`  IS NOT NULL AND `Editor`  <> '')
        OR (`action`  IS NOT NULL AND `action`  <> ''),
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


def get_last_pi_hour_from_api(dbhandler: MySQLConnetFunc, api_tbn: str) -> Optional[str]:
    try:
        sql = text(f"SELECT MAX(pi_hour) FROM `{api_tbn}`")
        with dbhandler.engine.begin() as conn:
            v = conn.execute(sql).scalar()
        return None if v is None else str(v)
    except Exception:
        return None


def compute_boundary_hour(last_pi_hour: str) -> str:
    dt = pd.to_datetime(last_pi_hour, errors="coerce")
    if pd.isna(dt):
        return str(last_pi_hour)
    dt = dt - timedelta(hours=1)
    dt = dt.replace(minute=0, second=0, microsecond=0)
    return dt.strftime("%Y-%m-%d %H")


# =========================
# 主流程
# =========================
def main():
    now = datetime.now()
    ym = now.strftime("%Y%m")
    logger.info(f"=== Datamall inspection job (Upsert) 開始 yyyymm={ym} ===")

    dbhandler = MySQLConnetFunc(DB_NAME)

    with requests.Session() as session:
        summary_tbn = f"{SUMMARY_BASE_TBN}_{ym}"
        raw_tbn = f"{RAW_BASE_TBN}_{ym}"

        load_and_append(dbhandler, SUMMARY_URL, summary_tbn, SUMMARY_COLS, session)
        load_and_append(dbhandler, RAW_URL, raw_tbn, RAW_COLS, session)

    api_tbn = f"inspection_api_summary_{ym}"
    last_pi_hour = get_last_pi_hour_from_api(dbhandler, api_tbn)
    boundary_hour = compute_boundary_hour(last_pi_hour) if last_pi_hour else None
    logger.info(f"[main] last_pi_hour={last_pi_hour} | boundary_hour={boundary_hour}")

    summary_tbn = f"{SUMMARY_BASE_TBN}_{ym}"
    raw_tbn = f"{RAW_BASE_TBN}_{ym}"
    summary_df, raw_df = get_tables(dbhandler, summary_tbn, raw_tbn, boundary_hour=boundary_hour)

    if summary_df.empty:
        logger.info("[main] boundary 後無新資料，結束")
        logger.info("=== Datamall inspection job (Upsert) 結束（無新資料）===")
        return

    api_df = build_api_summary_df(summary_df, raw_df).rename(columns=NEW_COLDICT)
    upsert_api_summary(dbhandler, api_tbn, api_df)

    logger.info("=== Datamall inspection job (Upsert) 結束 ===")


if __name__ == "__main__":
    main()