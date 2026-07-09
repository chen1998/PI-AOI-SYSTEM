#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import text


# =========================================================
# import project models.sql_db_connect.py
# =========================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# build_capa_hourly_summary_job.py 位於:
# D:\A0_Project\PI_SYSTEM\models\piaoi\capa
#
# 要 import:
# D:\A0_Project\PI_SYSTEM\models\sql_db_connect.py
#
# 所以 sys.path 要加入:
# D:\A0_Project\PI_SYSTEM
PROJECT_ROOT = os.path.abspath(
    os.path.join(CURRENT_DIR, "..", "..", "..")
)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from models.sql_db_connect import MySQLConnet


# =========================================================
# Logging
# =========================================================
LOG_DIR = os.path.join(CURRENT_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "build_capa_hourly_summary_job.log")

logger = logging.getLogger("build_capa_hourly_summary_job")
logger.setLevel(logging.INFO)
logger.handlers.clear()
logger.propagate = False

fmt = logging.Formatter(
    "%(asctime)s %(levelname)s [%(funcName)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
fh.setFormatter(fmt)

sh = logging.StreamHandler()
sh.setFormatter(fmt)

logger.addHandler(fh)
logger.addHandler(sh)


# =========================================================
# Config
# =========================================================
DB_NAME = "piaoi_capa"

AOI_LIST_ALL = ["aoi100", "aoi200", "aoi300"]

TARGET_COUNT_CFG = {
    "aoi100": 168,
    "aoi200": 238,
    "aoi300": 203,
}

SPEC_CFG = {
    "aoi100": 90,
    "aoi200": 90,
    "aoi300": 90,
}

SUMMARY_PI_CFG = {
    "aoi100": ["API", "BPI", "OTHER", "ALL"],
    "aoi200": ["API", "BPI", "OTHER", "ALL"],
    "aoi300": ["API", "BPI", "ITO", "OTHER", "ALL"],
}

GLASS_TBN_RE = re.compile(
    r"^(aoi\d{3})_(\d{6})_capa_glass_table$",
    flags=re.IGNORECASE,
)

MAX_BATCH = 5000


# =========================================================
# Time helpers
# =========================================================
def parse_yyyymmdd(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None

    s = str(s).strip()

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue

    raise ValueError(f"無法解析日期時間: {s}")


def resolve_window(
    mode: str,
    date_str: Optional[str],
    start_str: Optional[str],
    end_str: Optional[str],
    lookback_min: int,
) -> Tuple[datetime, datetime]:
    """
    回傳使用者指定的查詢時間窗。
    注意：
    - 這裡只是用來判斷「哪些 run_day 受影響」
    - 真正讀 glass 資料時，會改用完整 run_day 區間：
      run_day 07:30:00 ~ run_day+1 07:30:00
    """
    now = datetime.now()

    if mode == "today":
        start_dt = datetime(now.year, now.month, now.day)
        end_dt = start_dt + timedelta(days=1)
        return start_dt, end_dt

    if mode == "date":
        if not date_str:
            raise ValueError("--mode date 時必須提供 --date YYYY-MM-DD")

        d = parse_yyyymmdd(date_str)
        start_dt = datetime(d.year, d.month, d.day)
        end_dt = start_dt + timedelta(days=1)
        return start_dt, end_dt

    if mode == "range":
        if not start_str:
            raise ValueError("--mode range 時必須提供 --start")

        start_dt = parse_dt(start_str)
        end_dt = parse_dt(end_str) if end_str else now

        if start_dt > end_dt:
            start_dt, end_dt = end_dt, start_dt

        return start_dt, end_dt

    if mode == "lookback":
        end_dt = now
        start_dt = end_dt - timedelta(minutes=int(lookback_min))
        return start_dt, end_dt

    raise ValueError(f"未知模式: {mode}")


def month_list_from_range(start_dt: datetime, end_dt: datetime) -> List[str]:
    """
    根據 datetime 區間產生 yyyymm 清單。

    end_dt 可為 exclusive。
    若要避免剛好落在下個月 00:00 被多抓，
    呼叫端可自行傳 end_dt - 1 second。
    """
    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt

    out: List[str] = []
    cur = datetime(start_dt.year, start_dt.month, 1)
    end_m = datetime(end_dt.year, end_dt.month, 1)

    while cur <= end_m:
        out.append(cur.strftime("%Y%m"))

        if cur.month == 12:
            cur = datetime(cur.year + 1, 1, 1)
        else:
            cur = datetime(cur.year, cur.month + 1, 1)

    return out


def run_day_start_dt(run_day: date) -> datetime:
    """
    CAPA 輪班日開始時間：
    run_day 07:30:00
    """
    return datetime(run_day.year, run_day.month, run_day.day, 7, 30, 0)


def run_day_end_dt(run_day: date) -> datetime:
    """
    CAPA 輪班日結束時間，exclusive：
    run_day+1 07:30:00
    """
    return run_day_start_dt(run_day) + timedelta(days=1)


def run_day_from_scantime(scantime: datetime) -> date:
    """
    與 build_capa_glass_table_job.py 的 build_shift_fields() 保持一致：

    run_day = DATE(scantime - 7h30m)
    """
    return (scantime - timedelta(hours=7, minutes=30)).date()


def build_run_day_list_from_window(start_dt: datetime, end_dt: datetime) -> List[date]:
    """
    根據使用者指定的 start_dt/end_dt 判斷受影響的 run_day。

    重點：
    - 不直接用 start_dt/end_dt 讀資料
    - 只用它們判斷有哪些 run_day 需要重算
    - 每個 run_day 重算時都會讀完整 07:30 ~ 隔天 07:30

    end_dt 視為 exclusive。
    """
    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt

    if start_dt == end_dt:
        return [run_day_from_scantime(start_dt)]

    # end_dt 是 exclusive，所以要退 1 秒判斷最後一個被影響的 scantime
    end_probe = end_dt - timedelta(seconds=1)

    start_day = run_day_from_scantime(start_dt)
    end_day = run_day_from_scantime(end_probe)

    out: List[date] = []
    cur = start_day

    while cur <= end_day:
        out.append(cur)
        cur += timedelta(days=1)

    return out


# =========================================================
# Normalize helpers
# =========================================================
def clean_text(v) -> str:
    if pd.isna(v):
        return ""

    s = str(v).strip()

    if s.lower() in {"nan", "none", "<na>", "nat"}:
        return ""

    return s


def normalize_pi_type(v) -> str:
    s = str(v or "").strip().upper()

    if s == "API":
        return "API"

    if s == "BPI":
        return "BPI"

    if "ITO" in s:
        return "ITO"

    return "OTHER"


# =========================================================
# Table names
# =========================================================
def glass_table_name(aoi: str, yyyymm: str) -> str:
    return f"{aoi}_{yyyymm}_capa_glass_table"


def hourly_table_name(aoi: str, yyyymm: str) -> str:
    return f"{aoi}_{yyyymm}_capa_hourly_rawdata"


def summary_table_name(aoi: str, yyyymm: str) -> str:
    return f"{aoi}_{yyyymm}_capa_summary"


# =========================================================
# DDL
# =========================================================
def ensure_hourly_table(db: MySQLConnet, table_name: str):
    ddl = f"""
    CREATE TABLE IF NOT EXISTS `{db.db}`.`{table_name}` (
        id BIGINT NOT NULL AUTO_INCREMENT,

        aoi VARCHAR(16) NOT NULL,
        run_day DATE NOT NULL,
        pi_type VARCHAR(16) NOT NULL,

        pi_hour DATETIME NOT NULL,
        hour_int TINYINT NOT NULL,
        hour_label CHAR(2) NOT NULL,
        hour_sort TINYINT NOT NULL,

        hour INT NOT NULL,
        cumu INT NOT NULL,

        real_hour_capa DOUBLE,
        real_cumu_capa DOUBLE,

        update_time DATETIME NOT NULL
            DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP,

        PRIMARY KEY (id),

        UNIQUE KEY uk_hour (
            aoi, run_day, pi_type, pi_hour
        ),

        KEY idx_run_day (run_day),
        KEY idx_hour_sort (hour_sort),
        KEY idx_pi_type (pi_type)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """

    with db.engine.begin() as conn:
        conn.execute(text(ddl))


def ensure_summary_table(db: MySQLConnet, table_name: str):
    ddl = f"""
    CREATE TABLE IF NOT EXISTS `{db.db}`.`{table_name}` (
        id BIGINT NOT NULL AUTO_INCREMENT,

        aoi VARCHAR(16) NOT NULL,
        run_day DATE NOT NULL,
        pi_type VARCHAR(16) NOT NULL,

        total_glass INT NOT NULL,
        target_count INT,
        spec INT,
        real_day_capa DOUBLE,

        comment TEXT,
        action TEXT,
        editor VARCHAR(255),
        modify_time DATETIME,

        update_time DATETIME NOT NULL
            DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP,

        PRIMARY KEY (id),

        UNIQUE KEY uk_summary (
            aoi, run_day, pi_type
        ),

        KEY idx_run_day (run_day),
        KEY idx_pi_type (pi_type)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """

    with db.engine.begin() as conn:
        conn.execute(text(ddl))


# =========================================================
# Upsert
# =========================================================
def upsert_hourly_df(db: MySQLConnet, table_name: str, df: pd.DataFrame):
    if df is None or df.empty:
        logger.info(f"[upsert_hourly_df] {table_name}: no rows")
        return

    ensure_hourly_table(db, table_name)

    cols = [
        "aoi",
        "run_day",
        "pi_type",
        "pi_hour",
        "hour_int",
        "hour_label",
        "hour_sort",
        "hour",
        "cumu",
        "real_hour_capa",
        "real_cumu_capa",
    ]

    d = df[cols].copy()

    d = d.drop_duplicates(
        subset=["aoi", "run_day", "pi_type", "pi_hour"],
        keep="last",
    ).reset_index(drop=True)

    d["run_day"] = pd.to_datetime(d["run_day"], errors="coerce").dt.date
    d["pi_hour"] = pd.to_datetime(d["pi_hour"], errors="coerce")

    d["hour_int"] = pd.to_numeric(d["hour_int"], errors="coerce").fillna(0).astype(int)
    d["hour_sort"] = pd.to_numeric(d["hour_sort"], errors="coerce").fillna(0).astype(int)
    d["hour"] = pd.to_numeric(d["hour"], errors="coerce").fillna(0).astype(int)
    d["cumu"] = pd.to_numeric(d["cumu"], errors="coerce").fillna(0).astype(int)

    d["real_hour_capa"] = pd.to_numeric(d["real_hour_capa"], errors="coerce").fillna(0.0)
    d["real_cumu_capa"] = pd.to_numeric(d["real_cumu_capa"], errors="coerce").fillna(0.0)

    for c in ["aoi", "pi_type", "hour_label"]:
        d[c] = d[c].map(clean_text)

    d = d.dropna(subset=["aoi", "run_day", "pi_type", "pi_hour"])

    rows = d.to_dict(orient="records")

    if not rows:
        logger.info(f"[upsert_hourly_df] {table_name}: no valid rows")
        return

    sql = f"""
    INSERT INTO `{db.db}`.`{table_name}` (
        aoi, run_day, pi_type,
        pi_hour, hour_int, hour_label, hour_sort,
        hour, cumu, real_hour_capa, real_cumu_capa
    ) VALUES (
        :aoi, :run_day, :pi_type,
        :pi_hour, :hour_int, :hour_label, :hour_sort,
        :hour, :cumu, :real_hour_capa, :real_cumu_capa
    )
    ON DUPLICATE KEY UPDATE
        hour = VALUES(hour),
        cumu = VALUES(cumu),
        real_hour_capa = VALUES(real_hour_capa),
        real_cumu_capa = VALUES(real_cumu_capa),
        hour_int = VALUES(hour_int),
        hour_label = VALUES(hour_label),
        hour_sort = VALUES(hour_sort)
    """

    with db.engine.begin() as conn:
        for i in range(0, len(rows), MAX_BATCH):
            conn.execute(text(sql), rows[i:i + MAX_BATCH])

    logger.info(f"[upsert_hourly_df] {table_name}: upserted {len(rows)} rows")


def upsert_summary_df(db: MySQLConnet, table_name: str, df: pd.DataFrame):
    if df is None or df.empty:
        logger.info(f"[upsert_summary_df] {table_name}: no rows")
        return

    ensure_summary_table(db, table_name)

    cols = [
        "aoi",
        "run_day",
        "pi_type",
        "total_glass",
        "target_count",
        "spec",
        "real_day_capa",
        "comment",
        "action",
        "editor",
        "modify_time",
    ]

    d = df[cols].copy()

    d = d.drop_duplicates(
        subset=["aoi", "run_day", "pi_type"],
        keep="last",
    ).reset_index(drop=True)

    d["run_day"] = pd.to_datetime(d["run_day"], errors="coerce").dt.date
    d["modify_time"] = pd.to_datetime(d["modify_time"], errors="coerce")

    d["total_glass"] = pd.to_numeric(d["total_glass"], errors="coerce").fillna(0).astype(int)
    d["target_count"] = pd.to_numeric(d["target_count"], errors="coerce").fillna(0).astype(int)
    d["spec"] = pd.to_numeric(d["spec"], errors="coerce").fillna(0).astype(int)
    d["real_day_capa"] = pd.to_numeric(d["real_day_capa"], errors="coerce").fillna(0.0)

    for c in ["aoi", "pi_type", "comment", "action", "editor"]:
        d[c] = d[c].map(clean_text)

    d = d.dropna(subset=["aoi", "run_day", "pi_type"])

    rows = d.to_dict(orient="records")

    if not rows:
        logger.info(f"[upsert_summary_df] {table_name}: no valid rows")
        return

    # 保留既有 comment/action/editor/modify_time
    sql = f"""
    INSERT INTO `{db.db}`.`{table_name}` (
        aoi, run_day, pi_type, total_glass,
        target_count, spec, real_day_capa,
        comment, action, editor, modify_time
    ) VALUES (
        :aoi, :run_day, :pi_type, :total_glass,
        :target_count, :spec, :real_day_capa,
        :comment, :action, :editor, :modify_time
    )
    ON DUPLICATE KEY UPDATE
        total_glass = VALUES(total_glass),
        target_count = VALUES(target_count),
        spec = VALUES(spec),
        real_day_capa = VALUES(real_day_capa)
    """

    with db.engine.begin() as conn:
        for i in range(0, len(rows), MAX_BATCH):
            conn.execute(text(sql), rows[i:i + MAX_BATCH])

    logger.info(f"[upsert_summary_df] {table_name}: upserted {len(rows)} rows")


# =========================================================
# Load source
# =========================================================
def empty_glass_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "aoi",
        "line_id",
        "glass_id",
        "recipe_id",
        "pi_type",
        "scantime",
        "run_day",
        "pi_hour",
        "hour_int",
        "hour_label",
        "hour_sort",
    ])


def load_glass_df(
    db: MySQLConnet,
    table_name: str,
    start_dt: datetime,
    end_dt: datetime,
) -> pd.DataFrame:
    """
    從單一 glass table 讀 scantime 區間資料。
    start_dt inclusive, end_dt exclusive。
    """
    sql = f"""
    SELECT
        aoi,
        line_id,
        glass_id,
        recipe_id,
        pi_type,
        scantime,
        run_day,
        pi_hour,
        hour_int,
        hour_label,
        hour_sort
    FROM `{db.db}`.`{table_name}`
    WHERE scantime >= :start_dt
      AND scantime < :end_dt
    """

    df = db.query_df(sql, {
        "start_dt": start_dt,
        "end_dt": end_dt,
    })

    if df.empty:
        return df

    df["aoi"] = df["aoi"].map(clean_text).str.lower()
    df["line_id"] = df["line_id"].map(clean_text)
    df["glass_id"] = df["glass_id"].map(clean_text)
    df["recipe_id"] = df["recipe_id"].map(clean_text)
    df["pi_type"] = df["pi_type"].map(normalize_pi_type)

    df["scantime"] = pd.to_datetime(df["scantime"], errors="coerce")
    df["run_day"] = pd.to_datetime(df["run_day"], errors="coerce").dt.date
    df["pi_hour"] = pd.to_datetime(df["pi_hour"], errors="coerce")

    df["hour_int"] = pd.to_numeric(df["hour_int"], errors="coerce").fillna(0).astype(int)
    df["hour_sort"] = pd.to_numeric(df["hour_sort"], errors="coerce").fillna(0).astype(int)
    df["hour_label"] = df["hour_label"].map(clean_text)

    df = df.dropna(subset=["scantime", "run_day", "pi_hour"])
    df = df[df["glass_id"].str.len() > 0].copy()

    return df


def load_glass_df_for_run_day(
    db: MySQLConnet,
    aoi: str,
    run_day: date,
) -> pd.DataFrame:
    """
    修復重點：
    每個 run_day 都讀完整輪班區間：

        run_day 07:30:00 <= scantime < run_day+1 07:30:00

    並且依 scantime 橫跨的月份讀取多張 glass table。
    例如：
        run_day = 2026-05-31
        來源時間 = 2026-05-31 07:30 ~ 2026-06-01 07:30

    需要讀：
        aoi_202605_capa_glass_table
        aoi_202606_capa_glass_table
    """
    start_dt = run_day_start_dt(run_day)
    end_dt = run_day_end_dt(run_day)

    # end_dt 是 exclusive，month 判斷用 end_dt - 1 秒
    ym_list = month_list_from_range(
        start_dt=start_dt,
        end_dt=end_dt - timedelta(seconds=1),
    )

    frames: List[pd.DataFrame] = []

    for ym in ym_list:
        tbn = glass_table_name(aoi, ym)

        if not db.table_exists(tbn):
            logger.info(f"[{aoi}][{run_day}] glass table not exists: {tbn}")
            continue

        sub = load_glass_df(
            db=db,
            table_name=tbn,
            start_dt=start_dt,
            end_dt=end_dt,
        )

        if sub is not None and not sub.empty:
            frames.append(sub)

    if not frames:
        return empty_glass_df()

    out = pd.concat(frames, ignore_index=True)

    # 保險：只保留該 run_day
    out = out[out["run_day"] == run_day].copy()

    # 防止跨表或重跑產生完全重複資料
    out = out.drop_duplicates(
        subset=["aoi", "line_id", "glass_id", "scantime", "pi_type"],
        keep="last",
    ).reset_index(drop=True)

    return out


def empty_summary_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "aoi",
        "run_day",
        "pi_type",
        "total_glass",
        "target_count",
        "spec",
        "real_day_capa",
        "comment",
        "action",
        "editor",
        "modify_time",
    ])


def load_existing_summary_from_table(
    db: MySQLConnet,
    aoi: str,
    table_name: str,
    start_day: date,
    end_day: date,
) -> pd.DataFrame:
    if not db.table_exists(table_name):
        return empty_summary_df()

    sql = f"""
    SELECT
        aoi,
        run_day,
        pi_type,
        total_glass,
        target_count,
        spec,
        real_day_capa,
        comment,
        action,
        editor,
        modify_time
    FROM `{db.db}`.`{table_name}`
    WHERE aoi = :aoi
      AND run_day >= :start_day
      AND run_day <= :end_day
    """

    df = db.query_df(sql, {
        "aoi": aoi,
        "start_day": start_day,
        "end_day": end_day,
    })

    if df.empty:
        return df

    df["aoi"] = df["aoi"].map(clean_text).str.lower()
    df["pi_type"] = df["pi_type"].map(normalize_pi_type)
    df["run_day"] = pd.to_datetime(df["run_day"], errors="coerce").dt.date
    df["modify_time"] = pd.to_datetime(df["modify_time"], errors="coerce")

    return df


def load_existing_summary_cfg_for_run_days(
    db: MySQLConnet,
    aoi: str,
    run_days: List[date],
) -> pd.DataFrame:
    """
    載入既有 summary 設定，用來：
    1. 保留 comment/action/editor/modify_time
    2. 沿用 target_count/spec

    修復點：
    - 若 run_days 跨月，要讀多個 summary table
    - 為了讓月初第一天可以沿用前一天設定，也會多讀 min(run_days)-1
    """
    if not run_days:
        return empty_summary_df()

    days_needed = set(run_days)
    days_needed.add(min(run_days) - timedelta(days=1))

    by_month: Dict[str, List[date]] = {}

    for d in sorted(days_needed):
        ym = d.strftime("%Y%m")
        by_month.setdefault(ym, []).append(d)

    frames: List[pd.DataFrame] = []

    for ym, days in by_month.items():
        tbn = summary_table_name(aoi, ym)
        start_day = min(days)
        end_day = max(days)

        sub = load_existing_summary_from_table(
            db=db,
            aoi=aoi,
            table_name=tbn,
            start_day=start_day,
            end_day=end_day,
        )

        if sub is not None and not sub.empty:
            frames.append(sub)

    if not frames:
        return empty_summary_df()

    out = pd.concat(frames, ignore_index=True)

    out = out.drop_duplicates(
        subset=["aoi", "run_day", "pi_type"],
        keep="last",
    ).reset_index(drop=True)

    return out


# =========================================================
# Business logic
# =========================================================
def decide_target_and_spec_for_day(
    aoi: str,
    day: date,
    existing_summary: pd.DataFrame,
    last_target: Optional[int],
    last_spec: Optional[int],
) -> Tuple[int, int]:
    """
    target/spec 決策順序：

    1. 若當天既有 summary 有 target/spec，沿用當天既有設定
    2. 若本次處理前一日已決定 target/spec，沿用前一日
    3. 若資料庫中有更早 summary，沿用最近一筆
    4. 否則使用預設 TARGET_COUNT_CFG / SPEC_CFG
    """
    if existing_summary is not None and not existing_summary.empty:
        today_rows = existing_summary[
            (existing_summary["aoi"] == aoi) &
            (existing_summary["run_day"] == day)
        ]

        if not today_rows.empty:
            row0 = today_rows.iloc[0]

            t = (
                int(row0["target_count"])
                if pd.notna(row0["target_count"])
                else TARGET_COUNT_CFG[aoi]
            )

            s = (
                int(row0["spec"])
                if pd.notna(row0["spec"])
                else SPEC_CFG[aoi]
            )

            return t, s

    if last_target is not None and last_spec is not None:
        return last_target, last_spec

    if existing_summary is not None and not existing_summary.empty:
        older = existing_summary[
            (existing_summary["aoi"] == aoi) &
            (existing_summary["run_day"] < day)
        ]

        if not older.empty:
            older = older.sort_values("run_day")
            row_last = older.iloc[-1]

            t = (
                int(row_last["target_count"])
                if pd.notna(row_last["target_count"])
                else TARGET_COUNT_CFG[aoi]
            )

            s = (
                int(row_last["spec"])
                if pd.notna(row_last["spec"])
                else SPEC_CFG[aoi]
            )

            return t, s

    return TARGET_COUNT_CFG[aoi], SPEC_CFG[aoi]


def build_hourly_for_day(
    aoi: str,
    day: date,
    raw_day: pd.DataFrame,
    target_count: int,
) -> pd.DataFrame:
    """
    建立單一 run_day 的 24 小時 CAPA。

    小時順序固定：
        07, 08, 09, ..., 23, 00, 01, ..., 06

    pi_hour 對應：
        run_day 07:00
        run_day 08:00
        ...
        run_day+1 06:00

    注意：
    glass table 內的 pi_hour 是由 scantime - 30 min floor hour 得來。
    例如：
        scantime 2026-06-25 00:10
        pi_hour 2026-06-24 23:00

        scantime 2026-06-25 00:40
        pi_hour 2026-06-25 00:00
    """
    pi_types = SUMMARY_PI_CFG[aoi]
    pi_types_detail = [x for x in pi_types if x != "ALL"]

    hours = pd.DataFrame({
        "hour_int": [
            7, 8, 9, 10, 11, 12,
            13, 14, 15, 16, 17, 18,
            19, 20, 21, 22, 23,
            0, 1, 2, 3, 4, 5, 6,
        ]
    })

    hours["hour_label"] = hours["hour_int"].map(lambda x: f"{int(x):02d}")
    hours["hour_sort"] = range(24)

    # pi_hour 骨架從 run_day 07:00 開始，不是 07:30
    # 這與 build_capa_glass_table_job.py 的 pi_hour 計算邏輯一致
    base_dt = datetime(day.year, day.month, day.day, 7, 0, 0)
    hours["pi_hour"] = [base_dt + timedelta(hours=i) for i in range(24)]

    hourly_rows: List[pd.DataFrame] = []

    if raw_day is None or raw_day.empty:
        for pi in pi_types:
            df_pi = hours.copy()
            df_pi["aoi"] = aoi
            df_pi["run_day"] = day
            df_pi["pi_type"] = pi
            df_pi["hour"] = 0
            df_pi["cumu"] = 0
            df_pi["real_hour_capa"] = 0.0
            df_pi["real_cumu_capa"] = 0.0
            hourly_rows.append(df_pi)

        return pd.concat(hourly_rows, ignore_index=True)

    raw_day = raw_day.copy()
    raw_day["pi_type"] = raw_day["pi_type"].map(normalize_pi_type)
    raw_day["pi_hour"] = pd.to_datetime(raw_day["pi_hour"], errors="coerce")
    raw_day["glass_id"] = raw_day["glass_id"].map(clean_text)

    raw_day = raw_day.dropna(subset=["pi_hour"])
    raw_day = raw_day[raw_day["glass_id"].str.len() > 0].copy()

    detail_map: Dict[str, pd.DataFrame] = {}

    for pi in pi_types_detail:
        sub = raw_day[raw_day["pi_type"] == pi].copy()

        if sub.empty:
            cnt = pd.Series(dtype=int)
        else:
            # 每小時用不同 glass_id 數量
            cnt = sub.groupby("pi_hour")["glass_id"].nunique()

        df_pi = hours.merge(
            cnt.rename("hour"),
            how="left",
            left_on="pi_hour",
            right_index=True,
        ).fillna({"hour": 0})

        df_pi["hour"] = df_pi["hour"].astype(int)
        df_pi["cumu"] = df_pi["hour"].cumsum()

        df_pi["real_hour_capa"] = (
            df_pi["hour"] / target_count
            if target_count
            else 0.0
        )

        df_pi["real_cumu_capa"] = (
            df_pi["cumu"] / target_count
            if target_count
            else 0.0
        )

        df_pi["aoi"] = aoi
        df_pi["run_day"] = day
        df_pi["pi_type"] = pi

        detail_map[pi] = df_pi.copy()
        hourly_rows.append(df_pi)

    # ALL = 各 detail pi_type 每小時 hour 加總
    df_all = hours.copy()
    df_all["hour"] = 0

    for pi in pi_types_detail:
        if pi in detail_map:
            df_all["hour"] += detail_map[pi]["hour"].values

    df_all["cumu"] = df_all["hour"].cumsum()

    df_all["real_hour_capa"] = (
        df_all["hour"] / target_count
        if target_count
        else 0.0
    )

    df_all["real_cumu_capa"] = (
        df_all["cumu"] / target_count
        if target_count
        else 0.0
    )

    df_all["aoi"] = aoi
    df_all["run_day"] = day
    df_all["pi_type"] = "ALL"

    hourly_rows.append(df_all)

    return pd.concat(hourly_rows, ignore_index=True)


def build_summary_for_day(
    aoi: str,
    day: date,
    hourly_day_df: pd.DataFrame,
    target_count: int,
    spec: int,
    existing_summary: pd.DataFrame,
    now_str: str,
) -> pd.DataFrame:
    pi_types = SUMMARY_PI_CFG[aoi]

    if existing_summary is None or existing_summary.empty:
        existing_today = empty_summary_df()
    else:
        existing_today = existing_summary[
            (existing_summary["aoi"] == aoi) &
            (existing_summary["run_day"] == day)
        ]

    rows = []

    default_editor = f"default\n{now_str}"
    default_modify_time = pd.to_datetime(now_str)

    for pi in pi_types:
        sub = hourly_day_df[hourly_day_df["pi_type"] == pi].copy()

        total_glass = int(sub["cumu"].iloc[-1]) if not sub.empty else 0

        real_day_capa = (
            total_glass / target_count
            if target_count
            else 0.0
        )

        old_row = existing_today[existing_today["pi_type"] == pi]

        if not old_row.empty:
            old0 = old_row.iloc[0]

            comment = old0["comment"] if pd.notna(old0["comment"]) else ""
            action = old0["action"] if pd.notna(old0["action"]) else ""
            editor = old0["editor"] if pd.notna(old0["editor"]) else default_editor
            modify_time = (
                old0["modify_time"]
                if pd.notna(old0["modify_time"])
                else default_modify_time
            )
        else:
            comment = ""
            action = ""
            editor = default_editor
            modify_time = default_modify_time

        rows.append({
            "aoi": aoi,
            "run_day": day,
            "pi_type": pi,
            "total_glass": total_glass,
            "target_count": target_count,
            "spec": spec,
            "real_day_capa": real_day_capa,
            "comment": comment,
            "action": action,
            "editor": editor,
            "modify_time": modify_time,
        })

    return pd.DataFrame(rows)


# =========================================================
# Process AOI by run_day
# =========================================================
def process_aoi_run_days(
    db: MySQLConnet,
    aoi: str,
    run_days: List[date],
):
    """
    修復後的主處理邏輯：

    舊版：
        依 yyyymm 處理，讀 start_dt/end_dt partial window，
        再用 run_day 重算整天，容易覆蓋成較小值。

    新版：
        依 run_day 處理。
        每個 run_day 都讀完整：
            run_day 07:30 ~ run_day+1 07:30

        再依 run_day 所屬 yyyymm 寫入：
            aoi_yyyymm_capa_hourly_rawdata
            aoi_yyyymm_capa_summary
    """
    if not run_days:
        logger.info(f"[{aoi}] no run_days")
        return

    run_days = sorted(set(run_days))

    logger.info(
        f"[{aoi}] process run_days: "
        f"{run_days[0]} ~ {run_days[-1]}, count={len(run_days)}"
    )

    existing_summary = load_existing_summary_cfg_for_run_days(
        db=db,
        aoi=aoi,
        run_days=run_days,
    )

    hourly_by_ym: Dict[str, List[pd.DataFrame]] = {}
    summary_by_ym: Dict[str, List[pd.DataFrame]] = {}

    last_target: Optional[int] = None
    last_spec: Optional[int] = None

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for run_day in run_days:
        target_count, spec = decide_target_and_spec_for_day(
            aoi=aoi,
            day=run_day,
            existing_summary=existing_summary,
            last_target=last_target,
            last_spec=last_spec,
        )

        last_target = target_count
        last_spec = spec

        raw_day = load_glass_df_for_run_day(
            db=db,
            aoi=aoi,
            run_day=run_day,
        )

        logger.info(
            f"[{aoi}][{run_day}] raw_day rows={len(raw_day)}, "
            f"target_count={target_count}, spec={spec}"
        )

        hourly_day = build_hourly_for_day(
            aoi=aoi,
            day=run_day,
            raw_day=raw_day,
            target_count=target_count,
        )

        summary_day = build_summary_for_day(
            aoi=aoi,
            day=run_day,
            hourly_day_df=hourly_day,
            target_count=target_count,
            spec=spec,
            existing_summary=existing_summary,
            now_str=now_str,
        )

        out_ym = run_day.strftime("%Y%m")

        hourly_by_ym.setdefault(out_ym, []).append(hourly_day)
        summary_by_ym.setdefault(out_ym, []).append(summary_day)

    for ym, frames in sorted(hourly_by_ym.items()):
        hourly_df = pd.concat(frames, ignore_index=True)
        hourly_tbn = hourly_table_name(aoi, ym)

        upsert_hourly_df(
            db=db,
            table_name=hourly_tbn,
            df=hourly_df,
        )

    for ym, frames in sorted(summary_by_ym.items()):
        summary_df = pd.concat(frames, ignore_index=True)
        summary_tbn = summary_table_name(aoi, ym)

        upsert_summary_df(
            db=db,
            table_name=summary_tbn,
            df=summary_df,
        )

    logger.info(f"[{aoi}] done")


# =========================================================
# Main run
# =========================================================
def one_run(
    aoi_list: List[str],
    start_dt: datetime,
    end_dt: datetime,
):
    logger.info(
        f"[one_run] requested start_dt={start_dt}, "
        f"end_dt={end_dt}, aoi_list={aoi_list}"
    )

    db = MySQLConnet(DB_NAME)

    run_days = build_run_day_list_from_window(
        start_dt=start_dt,
        end_dt=end_dt,
    )

    logger.info(
        f"[one_run] affected run_days: "
        f"{run_days[0] if run_days else None} ~ "
        f"{run_days[-1] if run_days else None}, "
        f"count={len(run_days)}"
    )

    for aoi in aoi_list:
        process_aoi_run_days(
            db=db,
            aoi=aoi,
            run_days=run_days,
        )

    logger.info("[one_run] done")


# =========================================================
# CLI
# =========================================================
def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Build CAPA hourly/summary from capa glass table by full run_day window"
    )

    p.add_argument(
        "--mode",
        choices=["today", "date", "range", "lookback"],
        default="today",
        help="today/date/range/lookback",
    )

    p.add_argument("--date", help="指定單日 YYYY-MM-DD")
    p.add_argument("--start", help="range 起始 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS")
    p.add_argument("--end", help="range 結束 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS")
    p.add_argument("--lookback-min", type=int, default=180)

    p.add_argument(
        "--aoi-list",
        type=str,
        default="aoi100,aoi200,aoi300",
        help="逗號分隔，例如 aoi100,aoi300",
    )

    return p


def parse_csv_list(v: Optional[str]) -> List[str]:
    if not v:
        return []

    return [x.strip().lower() for x in str(v).split(",") if x.strip()]


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    aoi_list = parse_csv_list(args.aoi_list)

    if not aoi_list:
        aoi_list = AOI_LIST_ALL.copy()

    aoi_list = [x for x in aoi_list if x in AOI_LIST_ALL]

    if not aoi_list:
        raise ValueError("aoi-list 無有效 AOI，需為 aoi100/aoi200/aoi300")

    start_dt, end_dt = resolve_window(
        mode=args.mode,
        date_str=args.date,
        start_str=args.start,
        end_str=args.end,
        lookback_min=args.lookback_min,
    )

    one_run(
        aoi_list=aoi_list,
        start_dt=start_dt,
        end_dt=end_dt,
    )


if __name__ == "__main__":
    main()


"""
# =========================================================
# Usage
# =========================================================

# 指定區間
# 注意：range 只是用來判斷受影響 run_day。
# 每個受影響 run_day 都會用完整 07:30 ~ 隔天 07:30 重算。
python build_capa_hourly_summary_job.py --mode range --start 2026-05-01 --end 2026-06-25

# 指定單日
# 例如 --date 2026-06-24：
# 會判斷 2026-06-24 00:00 ~ 2026-06-25 00:00 影響到哪些 run_day。
# 通常會包含 2026-06-23 與 2026-06-24。
python build_capa_hourly_summary_job.py --mode date --date 2026-06-24

# 今日
python build_capa_hourly_summary_job.py --mode today

# 最近 1440 分鐘
# 修復後不會用 partial 1440 分鐘直接覆蓋整天，
# 而是先找受影響 run_day，再完整重算那些 run_day。
python build_capa_hourly_summary_job.py --mode lookback --lookback-min 1440

# 只處理 AOI100 / AOI200
python build_capa_hourly_summary_job.py --mode range --start 2026-04-22 --end 2026-04-27 --aoi-list aoi100,aoi200

# 只處理 AOI300
python build_capa_hourly_summary_job.py --mode range --start 2026-04-01 --end 2026-04-21 --aoi-list aoi300
"""