#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import text

# =========================================================
# import project models.sql_db_connect.py
# =========================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# build_capa_glass_table_job.py 位於:
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
LOG_FILE = os.path.join(LOG_DIR, "build_capa_glass_table_job.log")

logger = logging.getLogger("build_capa_glass_table_job")
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
CIM_DB = "cim_piaoi"
RTMS_DB = "rtms_piaoi_other"
OUT_DB = "piaoi_capa"

AOI_LIST_ALL = ["aoi100", "aoi200", "aoi300"]
AOI_AOI12 = ["aoi100", "aoi200"]

CAPIC_LIST = [f"capic{x}" for x in range(100, 701, 100)]

# AOI100 / AOI200 來源 defect table 支援正常 CAPIC 與 pi000
LINE_KEY_LIST_AOI12 = CAPIC_LIST + ["pi000"]

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


def normalize_pi_type_by_aoi(v, aoi: str) -> str:
    """
    AOI-aware pi_type fallback.

    需求：
    - aoi100 若 join 後 pi_type 為空值 / NULL / 無法辨識，預設 API
    - aoi200 若 join 後 pi_type 為空值 / NULL / 無法辨識，預設 OTHER
    - aoi300 若 join 後 pi_type 為空值 / NULL / 無法辨識，預設 OTHER
    """
    s = str(v or "").strip().upper()

    if s == "API":
        return "API"

    if s == "BPI":
        return "BPI"

    if "ITO" in s:
        return "ITO"

    if str(aoi or "").strip().lower() == "aoi100":
        return "API"

    return "OTHER"


def normalize_aoi(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None

    s = str(v).strip()
    if not s:
        return None

    s_low = s.lower()
    if s_low in {"aoi100", "aoi200", "aoi300"}:
        return s_low

    s_up = s.upper()

    if s_up == "CAPIT203":
        return "aoi100"

    if s_up == "CAAOI202":
        return "aoi200"

    if s_up == "CAAOI300":
        return "aoi300"

    return s_low


def normalize_line_id(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None

    s = str(v).strip()
    if not s:
        return None

    if s.lower() in {"nan", "none", "<na>", "nat"}:
        return None

    return s.upper()


# =========================================================
# Shift helpers
# =========================================================
def build_shift_fields(scantime: datetime) -> Tuple[date, datetime, int, str, int]:
    """
    輪班切法：
    - run_day = DATE(scantime - 7h30m)
    - pi_hour = floor(scantime - 30m, hour)
    - hour_sort = (hour_int - 7) % 24
    """
    run_day = (scantime - timedelta(hours=7, minutes=30)).date()
    pi_hour = (scantime - timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0)
    hour_int = int(pi_hour.hour)
    hour_label = f"{hour_int:02d}"
    hour_sort = (hour_int - 7) % 24

    return run_day, pi_hour, hour_int, hour_label, hour_sort


# =========================================================
# Table names
# =========================================================
def out_glass_table_name(aoi: str, yyyymm: str) -> str:
    return f"{aoi}_{yyyymm}_capa_glass_table"


def rtms_raw_table_name(yyyymm: str) -> str:
    return f"rtms_aoi300_raw_{yyyymm}"


def cim_pi_glass_table_name(yyyymm: str) -> str:
    return f"cim_pi_glass_{yyyymm}"


def cim_defect_table_name(yyyymm: str, aoi: str, line_key: str) -> str:
    return f"cim_defect_{yyyymm}_{aoi}_{line_key}"


# =========================================================
# DDL / upsert
# =========================================================
def ensure_glass_table(db: MySQLConnet, table_name: str):
    ddl = f"""
    CREATE TABLE IF NOT EXISTS `{db.db}`.`{table_name}` (
        id BIGINT NOT NULL AUTO_INCREMENT,

        aoi VARCHAR(16) NOT NULL,
        line_id VARCHAR(32) NULL,

        glass_id VARCHAR(64) NOT NULL,
        recipe_id VARCHAR(255) NULL,
        pi_type VARCHAR(16) NOT NULL,

        scantime DATETIME NOT NULL,
        run_day DATE NOT NULL,
        pi_hour DATETIME NOT NULL,

        hour_int TINYINT NOT NULL,
        hour_label CHAR(2) NOT NULL,
        hour_sort TINYINT NOT NULL,

        source_table VARCHAR(128) NULL,

        update_time DATETIME NOT NULL
            DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP,

        PRIMARY KEY (id),
        UNIQUE KEY uk_glass (aoi, line_id, glass_id, scantime),

        KEY idx_run_day (run_day),
        KEY idx_pi_hour (pi_hour),
        KEY idx_hour_sort (hour_sort),
        KEY idx_pi_type (pi_type),
        KEY idx_aoi (aoi),
        KEY idx_line_id (line_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """

    with db.engine.begin() as conn:
        conn.execute(text(ddl))


def upsert_glass_df(db: MySQLConnet, table_name: str, df: pd.DataFrame):
    if df is None or df.empty:
        logger.info(f"[upsert_glass_df] {table_name}: no rows")
        return

    ensure_glass_table(db, table_name)

    use_cols = [
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
        "source_table",
    ]

    d = df[use_cols].copy()

    d = d.drop_duplicates(
        subset=["aoi", "line_id", "glass_id", "scantime"],
        keep="last",
    ).reset_index(drop=True)

    d["scantime"] = pd.to_datetime(d["scantime"], errors="coerce")
    d["run_day"] = pd.to_datetime(d["run_day"], errors="coerce").dt.date
    d["pi_hour"] = pd.to_datetime(d["pi_hour"], errors="coerce")

    d = d.dropna(subset=["aoi", "glass_id", "scantime", "run_day", "pi_hour"]).copy()

    for c in ["aoi", "line_id", "glass_id", "recipe_id", "pi_type", "hour_label", "source_table"]:
        d[c] = d[c].map(clean_text)

    d["hour_int"] = pd.to_numeric(d["hour_int"], errors="coerce").fillna(0).astype(int)
    d["hour_sort"] = pd.to_numeric(d["hour_sort"], errors="coerce").fillna(0).astype(int)

    rows = d.to_dict(orient="records")
    if not rows:
        logger.info(f"[upsert_glass_df] {table_name}: no valid rows")
        return

    sql = f"""
    INSERT INTO `{db.db}`.`{table_name}` (
        aoi, line_id, glass_id, recipe_id, pi_type,
        scantime, run_day, pi_hour, hour_int, hour_label,
        hour_sort, source_table
    ) VALUES (
        :aoi, :line_id, :glass_id, :recipe_id, :pi_type,
        :scantime, :run_day, :pi_hour, :hour_int, :hour_label,
        :hour_sort, :source_table
    )
    ON DUPLICATE KEY UPDATE
        recipe_id    = VALUES(recipe_id),
        pi_type      = VALUES(pi_type),
        pi_hour      = VALUES(pi_hour),
        hour_int     = VALUES(hour_int),
        hour_label   = VALUES(hour_label),
        hour_sort    = VALUES(hour_sort),
        source_table = VALUES(source_table)
    """

    with db.engine.begin() as conn:
        for i in range(0, len(rows), MAX_BATCH):
            conn.execute(text(sql), rows[i:i + MAX_BATCH])

    logger.info(f"[upsert_glass_df] {table_name}: upserted {len(rows)} rows")


# =========================================================
# Candidate tables without list_tables()
# =========================================================
def build_candidate_cim_defect_tables(
    aoi_list: List[str],
    yyyymm_list: List[str],
) -> List[Tuple[str, str, str, str]]:
    """
    return:
      [(table_name, yyyymm, aoi, line_key), ...]

    line_key:
      capic100 / capic200 / ... / capic700 / pi000
    """
    out: List[Tuple[str, str, str, str]] = []

    for ym in yyyymm_list:
        for aoi in aoi_list:
            for line_key in LINE_KEY_LIST_AOI12:
                tbn = cim_defect_table_name(ym, aoi, line_key)
                out.append((tbn, ym, aoi, line_key))

    return out


def existing_cim_defect_tables(
    cim_db: MySQLConnet,
    aoi_list: List[str],
    yyyymm_list: List[str],
) -> List[Tuple[str, str, str, str]]:
    out: List[Tuple[str, str, str, str]] = []
    candidates = build_candidate_cim_defect_tables(aoi_list, yyyymm_list)

    for tbn, ym, aoi, line_key in candidates:
        if cim_db.table_exists(tbn):
            out.append((tbn, ym, aoi, line_key))

    return out


def existing_rtms_raw_tables(
    rtms_db: MySQLConnet,
    yyyymm_list: List[str],
) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []

    for ym in yyyymm_list:
        tbn = rtms_raw_table_name(ym)
        if rtms_db.table_exists(tbn):
            out.append((tbn, ym))

    return out


# =========================================================
# Load source helpers
# =========================================================
def load_cim_pi_glass_lookup_for_month(
    cim_db: MySQLConnet,
    yyyymm: str,
    start_dt: datetime,
    end_dt: datetime,
) -> pd.DataFrame:
    tbn = cim_pi_glass_table_name(yyyymm)

    if not cim_db.table_exists(tbn):
        logger.warning(f"[load_cim_pi_glass_lookup_for_month] table not exists: {tbn}")
        return pd.DataFrame(columns=[
            "glass_id", "scantime", "recipe_id", "line_id", "aoi", "pi_type"
        ])

    sql = f"""
    SELECT
        sheet_id_chip_id AS glass_id,
        test_time        AS scantime,
        recipe_id,
        line_id,
        aoi,
        pi_type
    FROM `{cim_db.db}`.`{tbn}`
    WHERE test_time >= :start_dt
      AND test_time < :end_dt
    """

    df = cim_db.query_df(sql, {"start_dt": start_dt, "end_dt": end_dt})
    if df.empty:
        return df

    df["glass_id"] = df["glass_id"].map(clean_text)
    df["scantime"] = pd.to_datetime(df["scantime"], errors="coerce")
    df["recipe_id"] = df["recipe_id"].map(clean_text)
    df["aoi"] = df["aoi"].map(normalize_aoi)
    df["line_id"] = df["line_id"].map(normalize_line_id)
    df["pi_type"] = df["pi_type"].map(clean_text)

    df = df.dropna(subset=["scantime"])
    df = df[df["glass_id"].str.len() > 0].copy()

    df = df.sort_values(["glass_id", "scantime"]).drop_duplicates(
        subset=["glass_id", "scantime"],
        keep="last",
    )

    return df


def load_cim_pi_glass_lookup_for_months(
    cim_db: MySQLConnet,
    yyyymm_list: List[str],
    start_dt: datetime,
    end_dt: datetime,
) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []

    clean_months: List[str] = []
    for ym in yyyymm_list or []:
        s = str(ym).strip()
        if len(s) == 6 and s.isdigit():
            clean_months.append(s)

    for ym in sorted(set(clean_months)):
        df = load_cim_pi_glass_lookup_for_month(
            cim_db=cim_db,
            yyyymm=ym,
            start_dt=start_dt,
            end_dt=end_dt,
        )

        if df is not None and not df.empty:
            df["_lookup_yyyymm"] = ym
            frames.append(df)

    if not frames:
        return pd.DataFrame(columns=[
            "glass_id", "scantime", "recipe_id", "line_id", "aoi", "pi_type"
        ])

    out = pd.concat(frames, ignore_index=True)

    # 若不同 lookup 表同時存在同一 glass + scantime，保留最後排序後資料
    out = out.sort_values(["glass_id", "scantime", "_lookup_yyyymm"]).drop_duplicates(
        subset=["glass_id", "scantime"],
        keep="last",
    )

    out = out.drop(columns=["_lookup_yyyymm"], errors="ignore")

    return out


def resolve_glass_lookup_months_for_capa(
    defect_ym: str,
    line_key: str,
    run_year: Optional[int] = None,
) -> List[str]:
    """
    capicxxx:
        用 defect 表的 yyyymm 讀 cim_pi_glass_yyyymm

    pi000:
        額外讀 cim_pi_glass_當前年份00 / 前一年00
        同時保留 defect_ym，避免有資料落在正常月份表時漏補
    """
    months: List[str] = [str(defect_ym)]

    if str(line_key).strip().lower() == "pi000":
        y = int(run_year or datetime.now().year)

        for m in [f"{y}00", f"{y - 1}00"]:
            if m not in months:
                months.append(m)

    return months


def load_cim_defect_glass_runs(
    cim_db: MySQLConnet,
    defect_table: str,
    start_dt: datetime,
    end_dt: datetime,
) -> pd.DataFrame:
    sql = f"""
    SELECT
        sheet_id_chip_id AS glass_id,
        test_time AS scantime
    FROM `{cim_db.db}`.`{defect_table}`
    WHERE test_time >= :start_dt
      AND test_time < :end_dt
    GROUP BY sheet_id_chip_id, test_time
    """

    df = cim_db.query_df(sql, {"start_dt": start_dt, "end_dt": end_dt})
    if df.empty:
        return df

    df["glass_id"] = df["glass_id"].map(clean_text)
    df["scantime"] = pd.to_datetime(df["scantime"], errors="coerce")
    df = df.dropna(subset=["scantime"])
    df = df[df["glass_id"].str.len() > 0].copy()

    return df


def load_rtms_aoi300_glass_runs(
    rtms_db: MySQLConnet,
    raw_table: str,
    start_dt: datetime,
    end_dt: datetime,
) -> pd.DataFrame:
    sql = f"""
    SELECT
        sheet_id_chip_id AS glass_id,
        test_time AS scantime,
        recipe_id,
        pi_type,
        line_id
    FROM `{rtms_db.db}`.`{raw_table}`
    WHERE test_time >= :start_dt
      AND test_time < :end_dt
    """

    df = rtms_db.query_df(sql, {"start_dt": start_dt, "end_dt": end_dt})
    if df.empty:
        return df

    df["glass_id"] = df["glass_id"].map(clean_text)
    df["scantime"] = pd.to_datetime(df["scantime"], errors="coerce")
    df["recipe_id"] = df["recipe_id"].map(clean_text)
    df["line_id"] = df["line_id"].map(normalize_line_id)
    df["pi_type"] = df["pi_type"].map(normalize_pi_type)
    df["aoi"] = "aoi300"

    df = df.dropna(subset=["scantime"])
    df = df[df["glass_id"].str.len() > 0].copy()

    df = df.sort_values(["glass_id", "scantime"]).drop_duplicates(
        subset=["glass_id", "scantime"],
        keep="last",
    )

    return df


# =========================================================
# Finalize
# =========================================================
def finalize_glass_df(
    df: pd.DataFrame,
    aoi: str,
    source_table: str,
    default_line_id: Optional[str] = None,
) -> pd.DataFrame:
    if df is None or df.empty:
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
            "source_table",
        ])

    d = df.copy()

    if "glass_id" not in d.columns:
        return pd.DataFrame()

    d["glass_id"] = d["glass_id"].map(clean_text)
    d["scantime"] = pd.to_datetime(d["scantime"], errors="coerce")

    d = d.dropna(subset=["scantime"])
    d = d[d["glass_id"].str.len() > 0].copy()

    if d.empty:
        return pd.DataFrame()

    if "aoi" not in d.columns:
        d["aoi"] = aoi
    d["aoi"] = d["aoi"].map(normalize_aoi).fillna(aoi)

    if "line_id" not in d.columns:
        d["line_id"] = default_line_id
    d["line_id"] = d["line_id"].fillna(default_line_id).map(normalize_line_id)
    d["line_id"] = d["line_id"].fillna(default_line_id)
    d["line_id"] = d["line_id"].map(normalize_line_id)
    d["line_id"] = d["line_id"].fillna(default_line_id)

    if "recipe_id" not in d.columns:
        d["recipe_id"] = ""
    d["recipe_id"] = d["recipe_id"].map(clean_text)

    if "pi_type" not in d.columns:
        d["pi_type"] = None

    # 需求：
    # aoi100 pi_type join 後為空值/null/無法辨識時，預設 API
    # 其他 AOI 預設 OTHER
    d["pi_type"] = d["pi_type"].map(lambda v: normalize_pi_type_by_aoi(v, aoi))

    d["source_table"] = source_table

    shift_rows = d["scantime"].map(build_shift_fields)
    d["run_day"] = shift_rows.map(lambda x: x[0])
    d["pi_hour"] = shift_rows.map(lambda x: x[1])
    d["hour_int"] = shift_rows.map(lambda x: x[2])
    d["hour_label"] = shift_rows.map(lambda x: x[3])
    d["hour_sort"] = shift_rows.map(lambda x: x[4])

    out_cols = [
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
        "source_table",
    ]

    d = d[out_cols].copy()

    d = d.drop_duplicates(
        subset=["aoi", "line_id", "glass_id", "scantime"],
        keep="last",
    )

    return d


def split_df_by_month(df: pd.DataFrame, dt_col: str = "scantime") -> Dict[str, pd.DataFrame]:
    if df is None or df.empty:
        return {}

    d = df.copy()
    d[dt_col] = pd.to_datetime(d[dt_col], errors="coerce")
    d["_yyyymm"] = d[dt_col].dt.strftime("%Y%m")

    out: Dict[str, pd.DataFrame] = {}

    for ym, sub in d.groupby("_yyyymm"):
        if pd.isna(ym):
            continue

        out[str(ym)] = sub.drop(columns=["_yyyymm"]).copy()

    return out


def prefer_capic_over_pi000(final_df: pd.DataFrame) -> pd.DataFrame:
    """
    PI000 是 fallback line。
    若同一 aoi + glass_id + scantime 同時有正常 CAPIC 與 PI000：
        保留正常 CAPIC
        丟掉 PI000
    避免 CAPA 重複計算。
    """
    if final_df is None or final_df.empty:
        return final_df

    d = final_df.copy()

    d["_line_upper"] = d["line_id"].astype(str).str.upper()
    d["_is_pi000"] = d["_line_upper"].eq("PI000")

    d = d.sort_values(
        ["aoi", "glass_id", "scantime", "_is_pi000"],
        ascending=[True, True, True, True],
    ).drop_duplicates(
        subset=["aoi", "glass_id", "scantime"],
        keep="first",
    )

    d = d.drop(columns=["_line_upper", "_is_pi000"], errors="ignore")

    return d


# =========================================================
# Process AOI100 / AOI200
# =========================================================
def process_aoi12(
    cim_db: MySQLConnet,
    out_db: MySQLConnet,
    aoi: str,
    start_dt: datetime,
    end_dt: datetime,
):
    ym_list = month_list_from_range(start_dt, end_dt)
    defect_tables = existing_cim_defect_tables(cim_db, [aoi], ym_list)

    if not defect_tables:
        logger.info(f"[{aoi}] no matching cim_defect tables")
        return

    all_rows: List[pd.DataFrame] = []

    for defect_table, ym, _, line_key in defect_tables:
        is_pi000 = str(line_key).strip().lower() == "pi000"
        default_line_id = "PI000" if is_pi000 else line_key.upper()

        logger.info(
            f"[{aoi}] processing {defect_table}, "
            f"line_key={line_key}, is_pi000={is_pi000}, default_line_id={default_line_id}"
        )

        defect_glass_df = load_cim_defect_glass_runs(
            cim_db=cim_db,
            defect_table=defect_table,
            start_dt=start_dt,
            end_dt=end_dt,
        )

        if defect_glass_df.empty:
            logger.info(f"[{aoi}] {defect_table}: no defect glass rows in window")
            continue

        lookup_months = resolve_glass_lookup_months_for_capa(
            defect_ym=ym,
            line_key=line_key,
            run_year=datetime.now().year,
        )

        logger.info(f"[{aoi}] {defect_table}: lookup_months={lookup_months}")

        glass_lookup_df = load_cim_pi_glass_lookup_for_months(
            cim_db=cim_db,
            yyyymm_list=lookup_months,
            start_dt=start_dt,
            end_dt=end_dt,
        )

        if glass_lookup_df.empty:
            merged = defect_glass_df.copy()
            merged["recipe_id"] = ""
            merged["line_id"] = default_line_id
            merged["aoi"] = aoi

            # aoi100 預設 API；aoi200 預設 OTHER
            merged["pi_type"] = "API" if aoi == "aoi100" else "OTHER"

        else:
            merged = defect_glass_df.merge(
                glass_lookup_df,
                how="left",
                on=["glass_id", "scantime"],
                suffixes=("", "_glass"),
            )

            if "recipe_id" not in merged.columns:
                merged["recipe_id"] = ""
            merged["recipe_id"] = merged["recipe_id"].map(clean_text)

            if "line_id" not in merged.columns:
                merged["line_id"] = default_line_id
            else:
                merged["line_id"] = merged["line_id"].fillna(default_line_id)

            # 空字串也要補 default_line_id
            merged["line_id"] = merged["line_id"].map(normalize_line_id)
            merged["line_id"] = merged["line_id"].fillna(default_line_id)

            if "aoi" not in merged.columns:
                merged["aoi"] = aoi
            else:
                merged["aoi"] = merged["aoi"].map(normalize_aoi).fillna(aoi)

            if "pi_type" not in merged.columns:
                merged["pi_type"] = None

            # 最終仍交給 finalize_glass_df 做 AOI-aware fallback
            merged["pi_type"] = merged["pi_type"]

        out_df = finalize_glass_df(
            df=merged,
            aoi=aoi,
            source_table=defect_table,
            default_line_id=default_line_id,
        )

        if not out_df.empty:
            all_rows.append(out_df)

    if not all_rows:
        logger.info(f"[{aoi}] no output rows")
        return

    final_df = pd.concat(all_rows, ignore_index=True)

    # PI000 是 fallback；若同一 aoi + glass_id + scantime 同時存在 CAPIC 與 PI000，保留 CAPIC
    before = len(final_df)
    final_df = prefer_capic_over_pi000(final_df)
    after = len(final_df)

    if before != after:
        logger.info(f"[{aoi}] prefer CAPIC over PI000 dedup: before={before}, after={after}")

    month_map = split_df_by_month(final_df, "scantime")

    for ym, sub in month_map.items():
        out_tbn = out_glass_table_name(aoi, ym)
        upsert_glass_df(out_db, out_tbn, sub)


# =========================================================
# Process AOI300
# =========================================================
def process_aoi300(
    rtms_db: MySQLConnet,
    out_db: MySQLConnet,
    start_dt: datetime,
    end_dt: datetime,
):
    ym_list = month_list_from_range(start_dt, end_dt)
    raw_tables = existing_rtms_raw_tables(rtms_db, ym_list)

    if not raw_tables:
        logger.info("[aoi300] no matching rtms raw tables")
        return

    all_rows: List[pd.DataFrame] = []

    for raw_table, ym in raw_tables:
        logger.info(f"[aoi300] processing {raw_table}")

        base_df = load_rtms_aoi300_glass_runs(
            rtms_db=rtms_db,
            raw_table=raw_table,
            start_dt=start_dt,
            end_dt=end_dt,
        )

        if base_df.empty:
            logger.info(f"[aoi300] {raw_table}: no raw rows in window")
            continue

        out_df = finalize_glass_df(
            df=base_df,
            aoi="aoi300",
            source_table=raw_table,
            default_line_id="NULL",
        )

        if not out_df.empty:
            all_rows.append(out_df)

    if not all_rows:
        logger.info("[aoi300] no output rows")
        return

    final_df = pd.concat(all_rows, ignore_index=True)
    month_map = split_df_by_month(final_df, "scantime")

    for ym, sub in month_map.items():
        out_tbn = out_glass_table_name("aoi300", ym)
        upsert_glass_df(out_db, out_tbn, sub)


# =========================================================
# Main
# =========================================================
def one_run(
    aoi_list: List[str],
    start_dt: datetime,
    end_dt: datetime,
):
    logger.info(f"[one_run] start_dt={start_dt}, end_dt={end_dt}, aoi_list={aoi_list}")

    cim_db = MySQLConnet(CIM_DB)
    rtms_db = MySQLConnet(RTMS_DB)
    out_db = MySQLConnet(OUT_DB)

    if "aoi100" in aoi_list:
        process_aoi12(cim_db, out_db, "aoi100", start_dt, end_dt)

    if "aoi200" in aoi_list:
        process_aoi12(cim_db, out_db, "aoi200", start_dt, end_dt)

    if "aoi300" in aoi_list:
        process_aoi300(rtms_db, out_db, start_dt, end_dt)

    logger.info("[one_run] done")


# =========================================================
# CLI
# =========================================================
def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build capa glass monthly tables without full table scan")

    p.add_argument(
        "--mode",
        choices=["today", "date", "range", "lookback"],
        default="today",
        help="today/date/range/lookback",
    )
    p.add_argument("--date", help="指定單日 YYYY-MM-DD")
    p.add_argument("--start", help="range 起始 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS")
    p.add_argument("--end", help="range 結束 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS")
    p.add_argument("--lookback-min", type=int, default=180, help="lookback 模式分鐘數")

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
python build_capa_glass_table_job.py --mode range --start 2026-05-01 --end 2026-05-07

# 指定單日
python build_capa_glass_table_job.py --mode date --date 2026-04-21

# 今日
python build_capa_glass_table_job.py --mode today

# 最近 1440 分鐘
python build_capa_glass_table_job.py --mode lookback --lookback-min 1440

# 只處理 AOI100 / AOI200
python build_capa_glass_table_job.py --mode range --start 2026-04-22 --end 2026-04-27 --aoi-list aoi100,aoi200

# 只處理 AOI300
python build_capa_glass_table_job.py --mode range --start 2026-04-01 --end 2026-04-21 --aoi-list aoi300
"""