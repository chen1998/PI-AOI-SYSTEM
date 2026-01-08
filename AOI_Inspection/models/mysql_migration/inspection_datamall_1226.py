#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

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

MAX_RETRY = 6          # 最多 retry 次數
RETRY_SLEEP_SEC = 30   # retry 間隔
REQUEST_TIMEOUT = 20   # requests timeout 秒數


# Datamall API URL
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
SUMMARY_BASE_TBN = "inspection_summary_table"

RAW_COLS = [
    "COORD_X", "COORD_Y", "DEFECT", "DEFECT_AREA", "DEFECT_ID",
    "DEFECT_SIZE_TYPE", "FAB", "FRONT_REVERSE", "IMG_URL", "RECIPE_NAME",
    "RUN_ID", "SCAN_ENDTIME", "SCAN_STARTTIME", "SHEET_ID", "SP", "STAGE",
    "TOOL_ID", "TOTAL_DEFECT_COUNT",
]

# API summary 用到的常數
DEFECT_SIZE_COL = "DEFECT_SIZE_TYPE"
UNI_DEFECT_SIZES: List[str] = ["S", "M", "L", "O"]
GROUP_KEYS = ["HOURLY", "TOOL_ID", "MODEL_NO", "TYPE"]
UNI_GLASS_KEYS = ["SHEET_ID", "SCAN_ENDTIME"]

# api_summary_df 欄位順序（產出時用舊名，之後再 rename）
GROUP_TABLE_KEYS = (
    GROUP_KEYS
    + ["hourly_run_glass_count", "hourly_defect_count", "hourly_defect_glass_couunt"]
    + UNI_DEFECT_SIZES
    + ["glass", "glass_size_detail", "comment"]
)

# 欄位 rename mapping（舊名 -> 新名）
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
}


# ===== 工具函式 =====
def datamall_get(
    url: str,
    session: requests.Session,
    max_retry: int = MAX_RETRY,
) -> Optional[Dict[str, Any]]:
    """
    從 Datamall 取得 JSON 資料。
    回傳: data (dict) 或 None
    """
    for attempt in range(1, max_retry + 1):
        try:
            logger.info(f"Datamall GET (try {attempt}/{max_retry}): {url}")
            resp = session.get(
                url,
                headers=REQUEST_HEADERS,
                proxies=PROXY_DICT,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info("Datamall GET 成功")
            return data
        except requests.RequestException as e:
            logger.warning(f"Datamall GET 失敗 (attempt {attempt}): {e}")
            if attempt < max_retry:
                logger.info(f"等待 {RETRY_SLEEP_SEC} 秒後重試...")
                time.sleep(RETRY_SLEEP_SEC)
            else:
                logger.error("已達最大重試次數，放棄此 URL。")
                return None
        except ValueError as e:
            logger.error(f"JSON 解析失敗: {e}")
            return None

    return None


def load_and_append(
    dbhandler: MySQLConnetFunc,
    url: str,
    table_name: str,
    cols: list,
    session: requests.Session,
    key_in_json: str = "1",
) -> None:
    """
    從 Datamall 抓資料 → 轉 DataFrame → 寫入 MySQL 指定 table。
    並記錄：
      - 原本資料表筆數 (before_count)  → 用 SELECT COUNT(*)，不撈整張表
      - Datamall 取得的資料筆數 (len(df))
      - 寫入後資料表總筆數 (after_count) → 用 SELECT COUNT(*)
      - 實際新增筆數 (inserted_count = after_count - before_count)
    """

    def get_row_count(tbn: str) -> Optional[int]:
        try:
            sql = text(f"SELECT COUNT(*) AS cnt FROM `{tbn}`")
            with dbhandler.engine.begin() as conn:
                cnt = conn.execute(sql).scalar()
            logger.info(f"[{tbn}] COUNT(*) = {cnt}")
            return cnt
        except Exception as e:
            logger.warning(f"[{tbn}] 取得 COUNT(*) 失敗（可能是新表或其他錯誤）: {e}")
            return None

    # 先取得原本資料表筆數（不撈整張表）
    before_count = get_row_count(table_name)

    data = datamall_get(url, session=session)
    if data is None:
        logger.error(f"[{table_name}] 取得資料失敗，略過本次處理。")
        return

    if key_in_json not in data:
        logger.error(f"[{table_name}] 回傳 JSON 不含 key='{key_in_json}'，原始 keys={list(data.keys())}")
        return

    df = pd.DataFrame(data[key_in_json])
    logger.info(f"[{table_name}] Datamall row 數: {len(df)}")

    if df.empty:
        logger.info(f"[{table_name}] 無新資料 (df 為空)，不寫入。")
        return

    # 僅保留需要的欄位（避免 Datamall schema 改動影響）
    df = df[cols].copy()
    logger.info(f"[{table_name}] 實際寫入欄位: {list(df.columns)}")
    logger.info(f"[{table_name}] 範例資料:\n{df.head(3)}")

    try:
        dbhandler.append_new_rows(df, table_name, cols)
        logger.info(f"[{table_name}] append_new_rows 完成，候選新增筆數(原始 df): {len(df)}")
    except Exception as e:
        logger.exception(f"[{table_name}] 寫入資料庫失敗: {e}")
        return

    # 寫入後再次取得總筆數（仍用 COUNT(*)）
    after_count = get_row_count(table_name)

    # 計算實際新增筆數（若前後筆數皆取得成功）
    if before_count is not None and after_count is not None:
        inserted_count = after_count - before_count
        logger.info(
            f"[{table_name}] 實際新增筆數 (after - before): {inserted_count} "
            f"(before={before_count}, after={after_count}, datamall_rows={len(df)})"
        )
    else:
        logger.info(
            f"[{table_name}] 無法計算實際新增筆數 "
            f"(before_count={before_count}, after_count={after_count}, datamall_rows={len(df)})"
        )


# ===== 清理用小工具 =====
def _add_hourly_col(df: pd.DataFrame, time_col: str = "SCAN_ENDTIME") -> pd.DataFrame:
    """
    由 time_col 產生 'HOURLY' 欄位，格式為 'YYYY-MM-DD HH'。
    若 time_col 不存在則原樣回傳。
    """
    if time_col not in df.columns:
        logger.warning(f"[clean] 欄位 {time_col} 不存在，無法產生 HOURLY")
        return df

    df = df.copy()
    dt = pd.to_datetime(df[time_col], errors="coerce")
    df["HOURLY"] = dt.dt.floor("H").dt.strftime("%Y-%m-%d %H")
    return df


def _split_recipe_to_model_type(df: pd.DataFrame, col: str = "RECIPE_NAME") -> pd.DataFrame:
    """
    將 RECIPE_NAME 切割成 MODEL_NO 與 TYPE 兩欄。
    假設格式類似 'MODELNO-TYPE'，用第一次 '-' 分割。
    若沒有 '-'，MODEL_NO = 原字串，TYPE = 空字串。
    """
    if col not in df.columns:
        logger.warning(f"[clean] 欄位 {col} 不存在，無法切割 MODEL_NO / TYPE")
        return df

    df = df.copy()
    s = df[col].astype(str)
    parts = s.str.split("-", n=1, expand=True)

    df["MODEL_NO"] = parts[0]
    if parts.shape[1] > 1:
        df["TYPE"] = parts[1]
    else:
        df["TYPE"] = ""

    return df


def get_tables(
    dbhandler: MySQLConnetFunc,
    summary_tbn: str,
    raw_tbn: str,
    boundary_hour: Optional[str] = None,
):
    """
    讀取 summary/raw 資料表並做清理：
      - summary: 加 HOURLY
      - raw: RECIPE_NAME -> MODEL_NO/TYPE + HOURLY

    若 boundary_hour 不為 None，則只保留 HOURLY >= boundary_hour 的資料，
    也就是「最後一筆 pi_hour 往前一小時」之後的資料，用來重新計算並覆蓋。
    """
    summary_df = dbhandler.get_table(summary_tbn)
    logger.info(f"[{summary_tbn}] 讀取筆數: {len(summary_df)}")

    raw_df = dbhandler.get_table(raw_tbn)
    logger.info(f"[{raw_tbn}] 讀取筆數: {len(raw_df)}")

    # summary: 加 HOURLY
    summary_df = _add_hourly_col(summary_df, time_col="SCAN_ENDTIME")

    # raw: MODEL_NO / TYPE + HOURLY
    raw_df = _split_recipe_to_model_type(raw_df, col="RECIPE_NAME")
    raw_df = _add_hourly_col(raw_df, time_col="SCAN_ENDTIME")

    if boundary_hour:
        # HOURLY 格式為 'YYYY-MM-DD HH'，字串比較 = 時間排序
        before_summary_len = len(summary_df)
        before_raw_len = len(raw_df)

        summary_df = summary_df[summary_df["HOURLY"] >= boundary_hour].copy()
        raw_df     = raw_df[raw_df["HOURLY"] >= boundary_hour].copy()

        logger.info(
            f"[incremental] boundary_hour = {boundary_hour} | "
            f"summary: {before_summary_len} -> {len(summary_df)} | "
            f"raw: {before_raw_len} -> {len(raw_df)}"
        )
    else:
        logger.info("[incremental] boundary_hour = None，使用當月全部資料")

    return summary_df, raw_df


def build_api_summary_df(summary_df: pd.DataFrame, raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    由 summary_df / raw_df 產生 api_summary_df（欄位名稱用舊名，最後再 rename）。
    """
    if summary_df.empty:
        logger.info("[api_summary] summary_df 為空，無資料可彙總")
        return pd.DataFrame(columns=GROUP_TABLE_KEYS)

    summary_groups = summary_df.groupby(GROUP_KEYS)
    raw_groups = raw_df.groupby(GROUP_KEYS) if not raw_df.empty else {}

    api_rows = []

    for main_keys, summary_rows in summary_groups:
        hour, tool_id, model_no, type_ = main_keys
        hourly_run_glass_count = len(summary_rows)

        logger.info(
            f"[SummaryGroup] HOURLY={hour}, TOOL_ID={tool_id}, MODEL_NO={model_no}, "
            f"TYPE={type_}, rows={len(summary_rows)}"
        )

        # 預設值
        hourly_defect_count = 0
        hourly_defect_glass_couunt = 0
        size_counts = {size: 0 for size in UNI_DEFECT_SIZES}
        glass_size_detail = ""
        
        try:
            raw_rows = raw_groups.get_group(main_keys)  # type: ignore[union-attr]

            # ---- glass_size_detail：每片 glass 的 S/M/L/O 計數 ----
            # 以 summary_rows 的 glass 為主（避免 raw 有但 summary 沒有的雜訊）
            glass_ids = summary_rows["SHEET_ID"].astype(str).dropna().unique().tolist()

            # raw_rows 先確保 SHEET_ID 字串化
            raw_rows2 = raw_rows.copy()
            raw_rows2["SHEET_ID"] = raw_rows2["SHEET_ID"].astype(str)

            detail_parts = []
            for gid in glass_ids:
                one = raw_rows2[raw_rows2["SHEET_ID"] == gid]
                # 計數（沒有就 0）
                s_cnt = int((one[DEFECT_SIZE_COL] == "S").sum())
                m_cnt = int((one[DEFECT_SIZE_COL] == "M").sum())
                l_cnt = int((one[DEFECT_SIZE_COL] == "L").sum())
                o_cnt = int((one[DEFECT_SIZE_COL] == "O").sum())

                # 格式：glass_id:S=..;M=..;L=..;O=..
                detail_parts.append(f"{gid}:S={s_cnt};M={m_cnt};L={l_cnt};O={o_cnt}")

            glass_size_detail = ",".join(detail_parts)

            hourly_defect_count = len(raw_rows)
            hourly_defect_glass_couunt = len(raw_rows.groupby(UNI_GLASS_KEYS))

            logger.info(
                f"[RawGroup] HOURLY={hour}, TOOL_ID={tool_id}, MODEL_NO={model_no}, "
                f"TYPE={type_}, defect_rows={hourly_defect_count}, "
                f"glass_count={hourly_defect_glass_couunt}"
            )

            for size in UNI_DEFECT_SIZES:
                size_counts[size] = len(raw_rows[raw_rows[DEFECT_SIZE_COL] == size])

        except KeyError:
            logger.info(
                f"[RawGroup] HOURLY={hour}, TOOL_ID={tool_id}, MODEL_NO={model_no}, "
                f"TYPE={type_}, 無對應 raw 資料"
            )

        glass_str = ",".join(summary_rows["SHEET_ID"].astype(str).unique())

        row = {
            "HOURLY": hour,
            "TOOL_ID": tool_id,
            "MODEL_NO": model_no,
            "TYPE": type_,
            "hourly_run_glass_count": hourly_run_glass_count,
            "hourly_defect_count": hourly_defect_count,
            "hourly_defect_glass_couunt": hourly_defect_glass_couunt,
            "glass": glass_str,
            "glass_size_detail": glass_size_detail,
            "comment": "",
        }

        row.update(size_counts)

        api_rows.append(row)

    api_summary_df = pd.DataFrame(api_rows, columns=GROUP_TABLE_KEYS)
    logger.info(f"[api_summary] 產出 api_summary_df 筆數: {len(api_summary_df)}")

    return api_summary_df

def ensure_column(dbhandler, table_name: str, col: str, ddl: str):
    sql = text("""
      SELECT COUNT(*) FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c
    """)
    with dbhandler.engine.begin() as conn:
        exists = conn.execute(sql, {"t": table_name, "c": col}).scalar()
        if not exists:
            conn.execute(text(f"ALTER TABLE `{table_name}` ADD COLUMN `{col}` {ddl}"))
            logger.info(f"[{table_name}] ADD COLUMN {col} {ddl}")


def save_api_summary_to_db(dbhandler: MySQLConnetFunc, df: pd.DataFrame, table_name: str) -> None:
    """
    將 API summary DataFrame append 到 inspection_api_summary_YYYYMM。
    若是第一次建立（表不存在），to_sql 會自動建表。
    之後跑 job 時，由 main 先刪除 pi_hour >= 邊界 的舊資料，再 append。
    """
    ensure_column(dbhandler, table_name, "glass_size_detail", "LONGTEXT")
    if df.empty:
        logger.info(f"[{table_name}] api_summary_df 為空，略過寫入。")
        return

    # 取得原本筆數（純記錄用）
    try:
        sql = text(f"SELECT COUNT(*) FROM `{table_name}`")
        with dbhandler.engine.begin() as conn:
            before_count = conn.execute(sql).scalar()
        logger.info(f"[{table_name}] 原本筆數：{before_count}")
    except Exception:
        before_count = 0
        logger.warning(f"[{table_name}] 目前不存在，將建立新表（before_count=0）")

    # 寫入（append）
    try:
        df.to_sql(
            name=table_name,
            con=dbhandler.engine,
            if_exists="append",
            index=False,
            chunksize=2000,
            method="multi",
        )
        logger.info(f"[{table_name}] 成功新增 {len(df)} 筆資料（增量）")
    except Exception as e:
        logger.exception(f"[{table_name}] 寫入 API summary 發生錯誤：{e}")
        return

    # 寫入後的筆數（純確認）
    try:
        sql = text(f"SELECT COUNT(*) FROM `{table_name}`")
        with dbhandler.engine.begin() as conn:
            after_count = conn.execute(sql).scalar()
        inserted = after_count - before_count
        logger.info(f"[{table_name}] 寫入後筆數：{after_count}（實際新增 {inserted} 筆）")
    except Exception:
        logger.warning(f"[{table_name}] 寫入後筆數無法取得")


# ===== 新增：取得 api_summary 中最後一筆 pi_hour =====
def get_last_pi_hour_from_api(dbhandler: MySQLConnetFunc, table_name: str) -> Optional[str]:
    """
    從 inspection_api_summary_YYYYMM 取得目前最大 pi_hour。
    若資料表不存在或沒有資料，回傳 None。
    """
    try:
        sql = text(f"SELECT MAX(pi_hour) FROM `{table_name}`")
        with dbhandler.engine.begin() as conn:
            val = conn.execute(sql).scalar()
        if val is None:
            logger.info(f"[{table_name}] MAX(pi_hour) 為 None（表存在但無資料）")
            return None

        last_pi_hour = str(val)
        logger.info(f"[{table_name}] 目前最大 pi_hour = {last_pi_hour}")
        return last_pi_hour
    except Exception as e:
        logger.warning(f"[{table_name}] 取得 MAX(pi_hour) 失敗（可能表不存在）: {e}")
        return None


def compute_boundary_hour(last_pi_hour: str) -> str:
    """
    將資料表中最後一筆 pi_hour（可能是 'YYYY-MM-DD HH' 或 datetime）
    轉成 datetime 後往前推 1 小時，再砍到整點，
    最後輸出為 'YYYY-MM-DD HH' 字串（跟 HOURLY 格式一致）。
    """
    try:
        dt = pd.to_datetime(last_pi_hour)
    except Exception:
        logger.warning(f"[compute_boundary_hour] 無法解析 last_pi_hour={last_pi_hour}，直接使用原值作為邊界")
        return str(last_pi_hour)

    dt = dt - timedelta(hours=1)
    dt = dt.replace(minute=0, second=0, microsecond=0)
    boundary = dt.strftime("%Y-%m-%d %H")
    logger.info(f"[compute_boundary_hour] last_pi_hour={last_pi_hour} → boundary={boundary}")
    return boundary


# ===== 主流程 =====
def main():
    now = datetime.now()
    ym = now.strftime("%Y%m")

    logger.info(f"=== Datamall inspection job 開始 ===")
    logger.info(f"連線時間: {now} (yyyymm = {ym})")

    dbhandler = MySQLConnetFunc(DB_NAME)

    # 建立 requests Session 共用連線
    with requests.Session() as session:
        # 1) summary table (依月份分表)
        summary_tbn = f"{SUMMARY_BASE_TBN}_{ym}"
        load_and_append(
            dbhandler=dbhandler,
            url=SUMMARY_URL,
            table_name=summary_tbn,
            cols=SUMMARY_COLS,
            session=session,
        )

        # 2) raw table (依月份分表)
        raw_tbn = f"inspection_raw_table_{ym}"
        load_and_append(
            dbhandler=dbhandler,
            url=RAW_URL,
            table_name=raw_tbn,
            cols=RAW_COLS,
            session=session,
        )

    # 3) 產生 / 更新 inspection_api_summary_{ym}
    api_tbn = f"inspection_api_summary_{ym}"

    # 先看目前 api_summary 表裡的最後一個 pi_hour
    last_pi_hour = get_last_pi_hour_from_api(dbhandler, api_tbn)

    if last_pi_hour:
        boundary_hour = compute_boundary_hour(last_pi_hour)
        logger.info(
            f"[main] {api_tbn} 已存在且有資料，"
            f"將以 boundary_hour={boundary_hour} 之後的資料重新計算，"
            f"並覆蓋 api_summary 中 pi_hour >= boundary_hour 的舊資料"
        )
    else:
        boundary_hour = None
        logger.info(
            f"[main] {api_tbn} 不存在或無資料，"
            f"將以當月所有 summary/raw 資料建立初始彙總表"
        )

    # 依 boundary_hour 取得「全量 / 部分」的 summary/raw
    summary_df, raw_df = get_tables(
        dbhandler,
        summary_tbn,
        raw_tbn,
        boundary_hour=boundary_hour,
    )

    if summary_df.empty:
        logger.info(
            f"[main] 自 boundary_hour={boundary_hour or '本月起'} 無新 summary 資料，略過 api_summary 產生"
        )
        logger.info("=== Datamall inspection job 結束（無新資料）===")
        return

    api_summary_df = build_api_summary_df(summary_df, raw_df)
    api_summary_df = api_summary_df.rename(columns=NEW_COLDICT)

    if api_summary_df.empty:
        logger.info("[main] build_api_summary_df 後無資料，略過寫入 api_summary")
        logger.info("=== Datamall inspection job 結束（無新資料）===")
        return

    # 如果有 boundary_hour，先刪掉 api_summary 中該時間後的舊資料
    if boundary_hour:
        try:
            sql = text(f"DELETE FROM `{api_tbn}` WHERE pi_hour >= :bnd")
            with dbhandler.engine.begin() as conn:
                deleted = conn.execute(sql, {"bnd": boundary_hour}).rowcount
            logger.info(
                f"[main] 已從 {api_tbn} 刪除 pi_hour >= {boundary_hour} 的舊資料 {deleted} 筆，準備寫入新彙總"
            )
        except Exception as e:
            logger.exception(
                f"[main] 刪除 {api_tbn} 中 pi_hour >= {boundary_hour} 時發生錯誤：{e}"
            )

    # 實際寫入（append）
    save_api_summary_to_db(dbhandler, api_summary_df, api_tbn)

    logger.info("=== Datamall inspection job 結束 ===")


if __name__ == "__main__":
    main()