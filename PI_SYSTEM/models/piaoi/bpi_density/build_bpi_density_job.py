#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
build_bpi_density_job.py

建立 AOI100 / AOI200 / AOI300 的 BPI API Summary。

資料來源：
    AOI100 / AOI200:
        cim_piaoi.cim_pi_glass_yyyymm
        cim_piaoi.cim_pi_glass_YYYY00

    AOI300:
        rtms_piaoi_other.rtms_aoi300_glass_yyyymm

輸出：
    piaoi_bpi_density.bpi_api_summary_yyyymm

分群欄位：
    aoi
    model
    scan_hour
    cassette_id
    glass_side
    recipe_id

Hourly 定義：
    scan_hour = floor(test_time - 30min, hour)

run_day 定義：
    run_day = DATE(test_time - 7h30m)

注意：
    最終 output 不包含 line_id。

Usage:
    python build_bpi_density_job.py --mode loop --write-out
    python build_bpi_density_job.py --mode month --month 202604 --write-out
    python build_bpi_density_job.py --mode days --days 7 --write-out
    python build_bpi_density_job.py --mode date --date 2026-04-22 --write-out
    python build_bpi_density_job.py --mode range --start "2026-04-01 00:00:00" --end "2026-05-01 00:00:00" --write-out
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from logging.handlers import TimedRotatingFileHandler
from typing import Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine


# =============================================================================
# Logging
# =============================================================================
def setup_logger(log_dir: str = "logs", name: str = "build_bpi_density_job") -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    log_path = os.path.join(log_dir, f"{name}.log")

    fmt = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = TimedRotatingFileHandler(
        log_path,
        when="D",
        interval=1,
        backupCount=95,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(sh)

    return logger


logger = setup_logger()


# =============================================================================
# Config
# =============================================================================
@dataclass
class Config:
    host: str = "10.97.142.217"
    username: str = "l6a01_user"
    password: str = "l6a01$user"

    cim_db: str = "cim_piaoi"
    rtms_db: str = "rtms_piaoi_other"
    out_db: str = "piaoi_bpi_density"

    cim_summary_tpl: str = "cim_pi_glass_yyyymm"
    rtms_aoi300_glass_tpl: str = "rtms_aoi300_glass_yyyymm"
    out_table_tpl: str = "bpi_api_summary_yyyymm"

    loop_minutes: int = 10
    lookback_minutes: int = 180

    write_out: bool = False

    # 是否額外讀 cim_pi_glass_YYYY00
    include_year00: bool = True

    # 是否多讀前一年 YYYY00
    include_prev_year00: bool = True

    aoi_map: Dict[str, str] = None

    def __post_init__(self):
        if self.aoi_map is None:
            self.aoi_map = {
                "CAPIT203": "aoi100",
                "CAAOI202": "aoi200",
                "CAAOI300": "aoi300",
                "aoi100": "aoi100",
                "aoi200": "aoi200",
                "aoi300": "aoi300",
            }


AOI_LIST_ALL = ["aoi100", "aoi200", "aoi300"]

GROUP_COLS = [
    "aoi",
    "model",
    "scan_hour",
    "cassette_id",
    "glass_side",
    "recipe_id",
]

OUTPUT_COLS = [
    "aoi",
    "model",
    "scan_hour",
    "cassette_id",
    "glass_side",
    "recipe_id",
    "pi_type",
    "run_day",
    "glass_count",
    "total_defect_count",
    "small_defect_count",
    "middle_defect_count",
    "large_defect_count",
    "over_defect_count",
    "density",
    "glass_list",
    "glass_size_detail",
    "source_db",
    "source_table",
    "comment",
    "action",
    "editor",
    "modify_time",
]


# =============================================================================
# DB
# =============================================================================
class MySQLDB:
    def __init__(self, dbname: str, cfg: Config):
        self.db = dbname
        self.engine: Engine = create_engine(
            f"mysql+pymysql://{cfg.username}:{cfg.password}@{cfg.host}/{dbname}?charset=utf8mb4",
            pool_pre_ping=True,
            pool_recycle=3600,
        )

    def table_exists(self, table_name: str) -> bool:
        insp = inspect(self.engine)
        return insp.has_table(table_name, schema=self.db)

    def query_df(self, sql: str, params: Optional[dict] = None) -> pd.DataFrame:
        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params or {})

    def execute(self, sql: str, params: Optional[dict] = None):
        with self.engine.begin() as conn:
            return conn.execute(text(sql), params or {})


# =============================================================================
# Time helpers
# =============================================================================
def parse_dt(v: Optional[str]) -> Optional[datetime]:
    if not v:
        return None

    s = str(v).strip()

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue

    raise ValueError(f"無法解析日期時間格式: {v}")


def parse_yyyymmdd(v: str) -> date:
    return datetime.strptime(v, "%Y-%m-%d").date()


def month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_month_start(dt: datetime) -> datetime:
    if dt.month == 12:
        return dt.replace(year=dt.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    return dt.replace(month=dt.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)


def iter_yyyymm_in_range(start_dt: datetime, end_dt: datetime) -> List[str]:
    """
    start inclusive, end exclusive
    """
    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt

    out: List[str] = []
    cur = month_start(start_dt)

    while cur < end_dt:
        out.append(cur.strftime("%Y%m"))
        cur = next_month_start(cur)

    return out


def build_cim_months_for_range(cfg: Config, start_dt: datetime, end_dt: datetime) -> List[str]:
    """
    CIM AOI100 / AOI200 來源月份清單。

    正常月份：
        202604, 202605 ...

    額外 year00：
        202600
        202500

    注意：
        這裡只是讀來源表。
        output table 仍依 scan_hour / test_time 寫到正常月份，例如 bpi_api_summary_202604。
    """
    months = iter_yyyymm_in_range(start_dt, end_dt)

    if not cfg.include_year00:
        return sorted(set(months))

    years = {start_dt.year, end_dt.year}
    # 若 end_dt 剛好是隔月 00:00，也保留 end_dt.year 不會壞
    extra = []

    for y in sorted(years):
        extra.append(f"{y}00")
        if cfg.include_prev_year00:
            extra.append(f"{y - 1}00")

    return sorted(set(months + extra))


def resolve_window(
    mode: str,
    *,
    month: Optional[str],
    days: int,
    date_str: Optional[str],
    start_str: Optional[str],
    end_str: Optional[str],
    lookback_minutes: int,
) -> Tuple[datetime, datetime]:
    now = datetime.now()

    if mode == "month":
        yyyymm = month or now.strftime("%Y%m")
        start_dt = datetime.strptime(yyyymm + "01", "%Y%m%d")
        end_dt = next_month_start(start_dt)
        return start_dt, end_dt

    if mode == "days":
        end_dt = now
        start_dt = end_dt - timedelta(days=int(days))
        return start_dt, end_dt

    if mode == "date":
        if not date_str:
            raise ValueError("--mode date 必須提供 --date YYYY-MM-DD")
        d = parse_yyyymmdd(date_str)
        start_dt = datetime(d.year, d.month, d.day)
        end_dt = start_dt + timedelta(days=1)
        return start_dt, end_dt

    if mode == "range":
        if not start_str:
            raise ValueError("--mode range 必須提供 --start")
        start_dt = parse_dt(start_str)
        end_dt = parse_dt(end_str) if end_str else now
        if start_dt > end_dt:
            start_dt, end_dt = end_dt, start_dt
        return start_dt, end_dt

    if mode == "loop":
        end_dt = now
        start_dt = end_dt - timedelta(minutes=int(lookback_minutes))
        return start_dt, end_dt

    raise ValueError(f"未知 mode: {mode}")


def derive_scan_hour_from_test_time(ts: pd.Series, cut_minute: int = 30) -> pd.Series:
    """
    scan_hour = (test_time - 30min).floor("H")
    """
    s = pd.to_datetime(ts, errors="coerce")
    return (s - pd.to_timedelta(cut_minute, unit="m")).dt.floor("h")


def derive_run_day_from_test_time(ts: pd.Series) -> pd.Series:
    """
    run_day = DATE(test_time - 7h30m)
    """
    s = pd.to_datetime(ts, errors="coerce")
    return (s - pd.to_timedelta(7 * 60 + 30, unit="m")).dt.date


# =============================================================================
# Normalize helpers
# =============================================================================
def clean_text(v) -> str:
    if pd.isna(v):
        return ""

    s = str(v).strip()
    if s.lower() in {"nan", "none", "<na>", "nat", "null"}:
        return ""

    return s


def normalize_aoi(v, cfg: Config) -> str:
    s = clean_text(v)
    if not s:
        return ""

    s_low = s.lower()
    if s_low in cfg.aoi_map:
        return cfg.aoi_map[s_low]

    s_up = s.upper()
    if s_up in cfg.aoi_map:
        return cfg.aoi_map[s_up]

    return s_low


def normalize_model(v) -> str:
    s = clean_text(v)
    if "_" in s:
        return s.split("_")[0]
    return s


def normalize_count_col(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0).astype(int)


def safe_json(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def infer_pi_type_from_glass_row(row) -> str:
    """
    AOI100:
        pi_time NULL -> API
        test_time < pi_time -> BPI
        test_time >= pi_time -> API

    AOI200:
        recipe_id 第一碼 4/5 -> BPI
        recipe_id 第一碼 0/1/2/3 -> API
        其他 fallback source pi_type

    AOI300:
        使用 source pi_type，這裡通常已經在 RTMS SQL 篩 BPI。
    """
    aoi = clean_text(row.get("aoi")).lower()
    recipe_id = clean_text(row.get("recipe_id"))
    src_pi_type = clean_text(row.get("src_pi_type")).upper()

    test_time = pd.to_datetime(row.get("test_time"), errors="coerce")
    pi_time = pd.to_datetime(row.get("pi_time"), errors="coerce")

    if aoi == "aoi100" :
        if pd.isna(pi_time) or pd.isna(test_time):
            return "OTHER"
        if test_time < pi_time:
            return "BPI"
        
        if test_time > pi_time:
            return "API"
        
        return "OTHER"

    if aoi == "aoi200":
        first = recipe_id[:1]
        if first in {"4", "5"}:
            return "BPI"
        if first in {"0", "1", "2", "3"}:
            return "API"
        if src_pi_type in {"API", "BPI"}:
            return src_pi_type
        return "OTHER"
    
    
    if aoi == "aoi300":
        if src_pi_type == "BPI":
            return "BPI"
        return src_pi_type
    
    return src_pi_type


# =============================================================================
# Table names
# =============================================================================
def cim_summary_table(cfg: Config, yyyymm: str) -> str:
    return cfg.cim_summary_tpl.replace("yyyymm", yyyymm).lower()


def rtms_aoi300_glass_table(cfg: Config, yyyymm: str) -> str:
    return cfg.rtms_aoi300_glass_tpl.replace("yyyymm", yyyymm).lower()


def out_summary_table(cfg: Config, yyyymm: str) -> str:
    return cfg.out_table_tpl.replace("yyyymm", yyyymm).lower()


# =============================================================================
# Load AOI100 / AOI200 from cim_pi_glass
# =============================================================================
def load_cim_glass_for_month(
    db: MySQLDB,
    cfg: Config,
    yyyymm: str,
    start_dt: datetime,
    end_dt: datetime,
    aoi_list: List[str],
) -> pd.DataFrame:
    tb = cim_summary_table(cfg, yyyymm)

    if not db.table_exists(tb):
        logger.warning(f"[cim] table not found: {db.db}.{tb}")
        return pd.DataFrame()

    need_aoi_raw = []
    if "aoi100" in aoi_list:
        need_aoi_raw.append("CAPIT203")
    if "aoi200" in aoi_list:
        need_aoi_raw.append("CAAOI202")

    if not need_aoi_raw:
        return pd.DataFrame()

    # 不在 SQL 直接限定 pi_type='BPI'
    # 因為：
    # - AOI100 要依 test_time / pi_time 重新判斷
    # - AOI200 要依 recipe_id 第一碼判斷
    # - YYYY00 可能有 pi_time NULL / pi_type 異常，需要進 Python 統一規則
    sql = f"""
    SELECT
        sheet_id_chip_id,
        test_time,
        pi_time,
        pi_hour,
        aoi,
        model_no,
        abbr_cat,
        recipe_id,
        cassette_id,
        line_id,
        total_defect_qty,
        defect_size_s_qty,
        defect_size_m_qty,
        defect_size_l_qty,
        defect_size_o_qty,
        pi_type
    FROM `{db.db}`.`{tb}`
    WHERE test_time >= :start_dt
      AND test_time <  :end_dt
      AND aoi IN ('CAPIT203', 'CAAOI202')
    """

    df = db.query_df(sql, {"start_dt": start_dt, "end_dt": end_dt})
    if df.empty:
        return df

    out = pd.DataFrame()

    out["aoi"] = df["aoi"].map(lambda v: normalize_aoi(v, cfg))
    out = out[out["aoi"].isin(aoi_list)].copy()
    

    if out.empty:
        return out

    df = df.loc[out.index].copy()

    out["model"] = df["model_no"].map(normalize_model)
    out["test_time"] = pd.to_datetime(df["test_time"], errors="coerce")
    out["scan_hour"] = derive_scan_hour_from_test_time(out["test_time"])
    out["run_day"] = derive_run_day_from_test_time(out["test_time"])

    out["line_id"] = df["line_id"].map(clean_text)
    out["cassette_id"] = df["cassette_id"].map(clean_text)
    out["glass_side"] = df["abbr_cat"].map(clean_text)
    out["recipe_id"] = df["recipe_id"].map(clean_text)
    out["glass_id"] = df["sheet_id_chip_id"].map(clean_text)

    out["pi_time"] = pd.to_datetime(df["pi_time"], errors="coerce")
    out["src_pi_hour"] = pd.to_datetime(df["pi_hour"], errors="coerce")
    out["src_pi_type"] = df["pi_type"].map(clean_text)

    out["total_defect_count"] = normalize_count_col(df["total_defect_qty"])
    out["small_defect_count"] = normalize_count_col(df["defect_size_s_qty"])
    out["middle_defect_count"] = normalize_count_col(df["defect_size_m_qty"])
    out["large_defect_count"] = normalize_count_col(df["defect_size_l_qty"])

    # 預設：AOI100 維持吃 cim_pi_glass.defect_size_o_qty
    out["over_defect_count"] = normalize_count_col(df["defect_size_o_qty"])

    # AOI200 特別規則：
    # over_defect_count = total_defect_count - S - M - L
    # 用來把 defect_size 為空值 / nan / null / 未分類的 defect 全部歸到 O
    mask_aoi200 = out["aoi"].astype(str).str.lower().eq("aoi200")

    aoi200_over = (
        out["total_defect_count"]
        - out["small_defect_count"]
        - out["middle_defect_count"]
        - out["large_defect_count"]
    ).clip(lower=0)

    out.loc[mask_aoi200, "over_defect_count"] = aoi200_over[mask_aoi200].astype(int)

    out["source_db"] = db.db
    out["source_table"] = tb

    out = out.dropna(subset=["test_time", "scan_hour"])
    out = out[out["glass_id"].str.len() > 0].copy()

    if out.empty:
        return out

    out["pi_type"] = out.apply(infer_pi_type_from_glass_row, axis=1)

    # 只保留 BPI
    out = out[out["pi_type"] == "BPI"].copy()

    logger.info(f"[cim] {tb}: loaded BPI rows={len(out)}")

    return out


# =============================================================================
# Load AOI300 from rtms_aoi300_glass
# =============================================================================
def load_rtms_aoi300_bpi_glass_for_month(
    db: MySQLDB,
    cfg: Config,
    yyyymm: str,
    start_dt: datetime,
    end_dt: datetime,
    aoi_list: List[str],
) -> pd.DataFrame:
    if "aoi300" not in aoi_list:
        return pd.DataFrame()

    tb = rtms_aoi300_glass_table(cfg, yyyymm)

    if not db.table_exists(tb):
        logger.warning(f"[rtms] table not found: {db.db}.{tb}")
        return pd.DataFrame()

    sql = f"""
    SELECT
        sheet_id_chip_id,
        test_time,
        recipe_id,
        cst_id,
        aoi,
        model,
        glass_type,
        pi_time,
        pi_type,
        defect_count,
        small_defect_count,
        middle_defect_count,
        large_defect_count,
        over_defect_count,
        run_day
    FROM `{db.db}`.`{tb}`
    WHERE test_time >= :start_dt
      AND test_time <  :end_dt
      AND pi_type = 'BPI'
    """

    df = db.query_df(sql, {"start_dt": start_dt, "end_dt": end_dt})
    if df.empty:
        return df

    out = pd.DataFrame()
    out["aoi"] = df["aoi"].map(lambda v: normalize_aoi(v, cfg)).replace("", "aoi300")
    out["model"] = df["model"].map(normalize_model)
    out["test_time"] = pd.to_datetime(df["test_time"], errors="coerce")
    out["scan_hour"] = derive_scan_hour_from_test_time(out["test_time"])
    out["run_day"] = derive_run_day_from_test_time(out["test_time"])

    # 這裡改成直接吃 cst_id
    out["cassette_id"] = df["cst_id"].map(clean_text)
    out["line_id"] = ""

    out["glass_side"] = df["glass_type"].map(clean_text)
    out["recipe_id"] = df["recipe_id"].map(clean_text)
    out["glass_id"] = df["sheet_id_chip_id"].map(clean_text)

    out["pi_time"] = pd.to_datetime(df["pi_time"], errors="coerce")
    out["src_pi_hour"] = pd.NaT
    out["src_pi_type"] = df["pi_type"].map(clean_text)
    out["pi_type"] = "BPI"

    out["total_defect_count"] = normalize_count_col(df["defect_count"])
    out["small_defect_count"] = normalize_count_col(df["small_defect_count"])
    out["middle_defect_count"] = normalize_count_col(df["middle_defect_count"])
    out["large_defect_count"] = normalize_count_col(df["large_defect_count"])
    out["over_defect_count"] = normalize_count_col(df["over_defect_count"])

    out["source_db"] = db.db
    out["source_table"] = tb

    out = out.dropna(subset=["test_time", "scan_hour"])
    out = out[out["glass_id"].str.len() > 0].copy()

    logger.info(f"[rtms] {tb}: loaded BPI rows={len(out)}")

    return out
# =============================================================================
# Load standard glass layer
# =============================================================================
def load_bpi_standard_glass_in_range(
    cfg: Config,
    cim_db: MySQLDB,
    rtms_db: MySQLDB,
    start_dt: datetime,
    end_dt: datetime,
    aoi_list: List[str],
) -> pd.DataFrame:
    normal_months = iter_yyyymm_in_range(start_dt, end_dt)
    cim_months = build_cim_months_for_range(cfg, start_dt, end_dt)

    logger.info(
        f"[load] range={start_dt} ~ {end_dt}, "
        f"normal_months={normal_months}, cim_months={cim_months}, aoi_list={aoi_list}"
    )

    frames: List[pd.DataFrame] = []

    # AOI100 / AOI200 from CIM
    if "aoi100" in aoi_list or "aoi200" in aoi_list:
        for ym in cim_months:
            cim_df = load_cim_glass_for_month(
                db=cim_db,
                cfg=cfg,
                yyyymm=ym,
                start_dt=start_dt,
                end_dt=end_dt,
                aoi_list=aoi_list,
            )
            if cim_df is not None and not cim_df.empty:
                frames.append(cim_df)

    # AOI300 from RTMS normal months only
    if "aoi300" in aoi_list:
        for ym in normal_months:
            rtms_df = load_rtms_aoi300_bpi_glass_for_month(
                db=rtms_db,
                cfg=cfg,
                yyyymm=ym,
                start_dt=start_dt,
                end_dt=end_dt,
                aoi_list=aoi_list,
            )
            if rtms_df is not None and not rtms_df.empty:
                frames.append(rtms_df)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)

    standard_cols = [
        "aoi",
        "model",
        "scan_hour",
        "cassette_id",
        "glass_side",
        "recipe_id",
        "glass_id",
        "line_id",
        "test_time",
        "pi_time",
        "src_pi_hour",
        "src_pi_type",
        "pi_type",
        "run_day",
        "total_defect_count",
        "small_defect_count",
        "middle_defect_count",
        "large_defect_count",
        "over_defect_count",
        "source_db",
        "source_table",
    ]

    for c in standard_cols:
        if c not in df.columns:
            df[c] = ""

    df = df[standard_cols].copy()

    for c in [
        "aoi",
        "model",
        "cassette_id",
        "glass_side",
        "recipe_id",
        "glass_id",
        "source_db",
        "source_table",
        "src_pi_type",
        "pi_type",
    ]:
        df[c] = df[c].map(clean_text)

    df["scan_hour"] = pd.to_datetime(df["scan_hour"], errors="coerce")
    df["test_time"] = pd.to_datetime(df["test_time"], errors="coerce")
    df["pi_time"] = pd.to_datetime(df["pi_time"], errors="coerce")
    df["src_pi_hour"] = pd.to_datetime(df["src_pi_hour"], errors="coerce")
    df["run_day"] = pd.to_datetime(df["run_day"], errors="coerce").dt.date

    count_cols = [
        "total_defect_count",
        "small_defect_count",
        "middle_defect_count",
        "large_defect_count",
        "over_defect_count",
    ]

    for c in count_cols:
        df[c] = normalize_count_col(df[c])

    df = df.dropna(subset=["scan_hour", "test_time"])
    df = df[df["glass_id"].str.len() > 0].copy()

    # 只保留 BPI
    df = df[df["pi_type"] == "BPI"].copy()

    # 同一 AOI / glass / test_time 若正常月份與 YYYY00 都讀到，保留正常月份優先
    # 讓 cim_pi_glass_202604 優先於 cim_pi_glass_202600。
    df["_is_year00"] = df["source_table"].astype(str).str.match(r"cim_pi_glass_\d{4}00$")
    df = df.sort_values(
        ["aoi", "glass_id", "test_time", "_is_year00", "source_table"],
        ascending=[True, True, True, True, True],
    ).drop_duplicates(
        subset=["aoi", "glass_id", "test_time"],
        keep="first",
    )
    df = df.drop(columns=["_is_year00"], errors="ignore")

    logger.info(f"[load] standard BPI glass rows={len(df)}")

    return df.reset_index(drop=True)


def apply_cst_anchor_scan_hour(df: pd.DataFrame) -> pd.DataFrame:
    """
    規則：
    - 同一天(run_day)、同一個 aoi、同一個 cassette_id
    - 若同 cst 對應多片 glass 分散在不同 scan_hour
    - 全部歸到該 cst 在當天最早 test_time 對應的 scan_hour

    注意：
    - cassette_id 為空字串的資料不做 cst anchor，保留原本 scan_hour
    """
    if df is None or df.empty:
        return df

    d = df.copy()

    d["test_time"] = pd.to_datetime(d["test_time"], errors="coerce")
    d["scan_hour"] = pd.to_datetime(d["scan_hour"], errors="coerce")

    # 只對有 cst 的資料做 anchor
    has_cst = d["cassette_id"].astype(str).str.strip().ne("")
    if not has_cst.any():
        return d

    base = d.loc[has_cst, ["aoi", "run_day", "model", "cassette_id", "test_time"]].copy()
    base = base.dropna(subset=["run_day", "test_time"])

    if base.empty:
        return d

    # 找同 aoi + run_day + cassette_id 的最早 test_time
    first_tt = (
        base.groupby(["aoi", "run_day", "model", "cassette_id"], dropna=False)["test_time"]
        .min()
        .reset_index(name="first_test_time")
    )

    # 依最早 test_time 推 anchor scan_hour
    first_tt["anchor_scan_hour"] = derive_scan_hour_from_test_time(first_tt["first_test_time"])

    # merge 回原資料
    d = d.merge(
        first_tt[["aoi", "run_day", "model", "cassette_id", "anchor_scan_hour"]],
        how="left",
        on=["aoi", "run_day", "model",  "cassette_id"],
    )

    # 有 cassette_id 且有 anchor 的，改用 anchor_scan_hour
    d.loc[
        d["cassette_id"].astype(str).str.strip().ne("") & d["anchor_scan_hour"].notna(),
        "scan_hour"
    ] = d.loc[
        d["cassette_id"].astype(str).str.strip().ne("") & d["anchor_scan_hour"].notna(),
        "anchor_scan_hour"
    ]

    d = d.drop(columns=["anchor_scan_hour"], errors="ignore")
    return d

# =============================================================================
# Aggregate summary
# =============================================================================
def fmt_dt_str(v) -> str:
    if pd.isna(v):
        return ""
    try:
        return pd.to_datetime(v).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""

def build_glass_size_detail(sub: pd.DataFrame) -> Dict[str, Dict[str, object]]:
    detail: Dict[str, Dict[str, object]] = {}

    for _, r in sub.iterrows():
        gid = clean_text(r.get("glass_id"))
        if not gid:
            continue

        s = int(r.get("small_defect_count", 0) or 0)
        m = int(r.get("middle_defect_count", 0) or 0)
        l = int(r.get("large_defect_count", 0) or 0)
        o = int(r.get("over_defect_count", 0) or 0)

        t = int(r.get("total_defect_count", 0) or 0)
        if t <= 0:
            t = s + m + l + o

        line_id = clean_text(r.get("line_id"))
        test_time = fmt_dt_str(r.get("test_time"))

        if gid not in detail:
            detail[gid] = {
                "S": 0,
                "M": 0,
                "L": 0,
                "O": 0,
                "T": 0,
                "line_id": line_id,
                "test_time": test_time,
            }

        detail[gid]["S"] += s
        detail[gid]["M"] += m
        detail[gid]["L"] += l
        detail[gid]["O"] += o
        detail[gid]["T"] += s + m + l + o

        if not detail[gid].get("line_id") and line_id:
            detail[gid]["line_id"] = line_id
        if not detail[gid].get("test_time") and test_time:
            detail[gid]["test_time"] = test_time

    return detail

def build_bpi_api_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=OUTPUT_COLS)

    rows: List[dict] = []

    for gk, sub in df.groupby(GROUP_COLS, dropna=False):
        aoi, model, scan_hour, cassette_id, glass_side, recipe_id = gk

        glass_ids = sorted(set([clean_text(x) for x in sub["glass_id"].tolist() if clean_text(x)]))
        glass_count = len(glass_ids)

        total_defect_count = int(sub["total_defect_count"].sum())
        small_defect_count = int(sub["small_defect_count"].sum())
        middle_defect_count = int(sub["middle_defect_count"].sum())
        large_defect_count = int(sub["large_defect_count"].sum())
        over_defect_count = int(sub["over_defect_count"].sum())

        density = round(total_defect_count / max(glass_count, 1), 3)

        run_day = None
        if "run_day" in sub.columns and sub["run_day"].notna().any():
            run_day = sub["run_day"].dropna().iloc[0]

        source_db = ",".join(sorted(set([clean_text(x) for x in sub["source_db"].tolist() if clean_text(x)])))
        source_table = ",".join(sorted(set([clean_text(x) for x in sub["source_table"].tolist() if clean_text(x)])))

        glass_size_detail = build_glass_size_detail(sub)

        rows.append({
            "aoi": clean_text(aoi),
            "model": clean_text(model),
            "scan_hour": pd.to_datetime(scan_hour, errors="coerce"),
            "cassette_id": clean_text(cassette_id),
            "glass_side": clean_text(glass_side),
            "recipe_id": clean_text(recipe_id),
            "pi_type": "BPI",
            "run_day": run_day,

            "glass_count": glass_count,
            "total_defect_count": total_defect_count,
            "small_defect_count": small_defect_count,
            "middle_defect_count": middle_defect_count,
            "large_defect_count": large_defect_count,
            "over_defect_count": over_defect_count,
            "density": density,

            "glass_list": ",".join(glass_ids),
            "glass_size_detail": safe_json(glass_size_detail),

            "source_db": source_db,
            "source_table": source_table,

            "comment": "",
            "action": "",
            "editor": "",
            "modify_time": None,
        })

    out = pd.DataFrame(rows)
    logger.info(f"[summary] grouped rows={len(out)}")
    return out


# =============================================================================
# Output DDL / manual fields / write
# =============================================================================
def ensure_out_table(db: MySQLDB, table_name: str):
    ddl = f"""
    CREATE TABLE IF NOT EXISTS `{db.db}`.`{table_name}` (
        id BIGINT NOT NULL AUTO_INCREMENT,

        aoi VARCHAR(16) NOT NULL,
        model VARCHAR(255) NOT NULL,
        scan_hour DATETIME NOT NULL,
        cassette_id VARCHAR(255) NOT NULL,
        glass_side VARCHAR(64) NOT NULL,
        recipe_id VARCHAR(255) NOT NULL,

        pi_type VARCHAR(16) NOT NULL DEFAULT 'OTHER',
        run_day DATE NULL,

        glass_count INT NOT NULL DEFAULT 0,
        total_defect_count INT NOT NULL DEFAULT 0,
        small_defect_count INT NOT NULL DEFAULT 0,
        middle_defect_count INT NOT NULL DEFAULT 0,
        large_defect_count INT NOT NULL DEFAULT 0,
        over_defect_count INT NOT NULL DEFAULT 0,

        density DOUBLE NULL,

        glass_list LONGTEXT NULL,
        glass_size_detail LONGTEXT NULL,

        source_db VARCHAR(64) NULL,
        source_table LONGTEXT NULL,

        comment TEXT NULL,
        action TEXT NULL,
        editor VARCHAR(255) NULL,
        modify_time DATETIME NULL,

        update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP,

        PRIMARY KEY (id),

        KEY idx_aoi (aoi),
        KEY idx_scan_hour (scan_hour),
        KEY idx_run_day (run_day),
        KEY idx_model (model),
        KEY idx_recipe_id (recipe_id),
        KEY idx_cassette_id (cassette_id),
        KEY idx_glass_side (glass_side),

        KEY idx_group_lookup (
            aoi,
            scan_hour,
            model(80),
            cassette_id(80),
            glass_side,
            recipe_id(80)
        )
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    db.execute(ddl)

def load_existing_manual_fields(db: MySQLDB, table_name: str, keys_df: pd.DataFrame) -> pd.DataFrame:
    if keys_df is None or keys_df.empty or not db.table_exists(table_name):
        return pd.DataFrame(columns=GROUP_COLS + ["comment", "action", "editor", "modify_time"])

    ts = int(datetime.now().timestamp())
    key_tbn = f"__keys_manual_{table_name}_{ts}"

    keys = keys_df[GROUP_COLS].drop_duplicates().copy()
    keys.to_sql(
        name=key_tbn,
        con=db.engine,
        schema=db.db,
        if_exists="replace",
        index=False,
        chunksize=10000,
        method="multi",
    )

    join_cond = " AND ".join([f"t.`{c}` <=> k.`{c}`" for c in GROUP_COLS])

    sql = f"""
    SELECT
        t.aoi,
        t.model,
        t.scan_hour,
        t.cassette_id,
        t.glass_side,
        t.recipe_id,
        t.comment,
        t.action,
        t.editor,
        t.modify_time
    FROM `{db.db}`.`{table_name}` t
    JOIN `{db.db}`.`{key_tbn}` k
      ON {join_cond}
    """

    try:
        out = db.query_df(sql)
    finally:
        db.execute(f"DROP TABLE IF EXISTS `{db.db}`.`{key_tbn}`")

    if out.empty:
        return pd.DataFrame(columns=GROUP_COLS + ["comment", "action", "editor", "modify_time"])

    out["scan_hour"] = pd.to_datetime(out["scan_hour"], errors="coerce")
    out["modify_time"] = pd.to_datetime(out["modify_time"], errors="coerce")

    return out


def merge_manual_fields(summary_df: pd.DataFrame, manual_df: pd.DataFrame) -> pd.DataFrame:
    if summary_df is None or summary_df.empty:
        return summary_df

    out = summary_df.copy()

    if manual_df is None or manual_df.empty:
        return out

    m = manual_df.copy()
    m["scan_hour"] = pd.to_datetime(m["scan_hour"], errors="coerce")
    out["scan_hour"] = pd.to_datetime(out["scan_hour"], errors="coerce")

    out = out.merge(
        m[GROUP_COLS + ["comment", "action", "editor", "modify_time"]],
        how="left",
        on=GROUP_COLS,
        suffixes=("", "_old"),
    )

    for c in ["comment", "action", "editor", "modify_time"]:
        old_col = f"{c}_old"
        if old_col in out.columns:
            out[c] = out[old_col].combine_first(out[c])
            out.drop(columns=[old_col], inplace=True)

    for c in ["comment", "action", "editor"]:
        out[c] = out[c].map(clean_text)

    out["modify_time"] = pd.to_datetime(out["modify_time"], errors="coerce")

    return out


def to_py_dt(v):
    if pd.isna(v):
        return None
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    return v


def write_summary_overwrite_groups(db: MySQLDB, table_name: str, summary_df: pd.DataFrame):
    if summary_df is None or summary_df.empty:
        logger.info(f"[write] {table_name}: no rows")
        return

    ensure_out_table(db, table_name)

    d = summary_df.copy()

    manual_df = load_existing_manual_fields(db, table_name, d)
    d = merge_manual_fields(d, manual_df)

    for c in OUTPUT_COLS:
        if c not in d.columns:
            d[c] = None

    d = d[OUTPUT_COLS].copy()

    text_cols = [
        "aoi",
        "model",
        "cassette_id",
        "glass_side",
        "recipe_id",
        "pi_type",
        "glass_list",
        "glass_size_detail",
        "source_db",
        "source_table",
        "comment",
        "action",
        "editor",
    ]

    for c in text_cols:
        d[c] = d[c].map(clean_text)

    d["scan_hour"] = pd.to_datetime(d["scan_hour"], errors="coerce")
    d["run_day"] = pd.to_datetime(d["run_day"], errors="coerce").dt.date
    d["modify_time"] = pd.to_datetime(d["modify_time"], errors="coerce")

    d["scan_hour"] = d["scan_hour"].map(to_py_dt)
    d["modify_time"] = d["modify_time"].map(to_py_dt)

    count_cols = [
        "glass_count",
        "total_defect_count",
        "small_defect_count",
        "middle_defect_count",
        "large_defect_count",
        "over_defect_count",
    ]

    for c in count_cols:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0).astype(int)

    d["density"] = pd.to_numeric(d["density"], errors="coerce").fillna(0.0)

    d = d.dropna(subset=["scan_hour"])
    if d.empty:
        logger.info(f"[write] {table_name}: no valid rows after clean")
        return

    ts = int(datetime.now().timestamp())
    stg = f"__stg_{table_name}_{ts}"
    keys = f"__keys_{table_name}_{ts}"

    stg_qual = f"`{db.db}`.`{stg}`"
    keys_qual = f"`{db.db}`.`{keys}`"
    tgt_qual = f"`{db.db}`.`{table_name}`"

    d.to_sql(
        name=stg,
        con=db.engine,
        schema=db.db,
        if_exists="replace",
        index=False,
        chunksize=20000,
        method="multi",
    )

    d[GROUP_COLS].drop_duplicates().to_sql(
        name=keys,
        con=db.engine,
        schema=db.db,
        if_exists="replace",
        index=False,
        chunksize=20000,
        method="multi",
    )

    join_cond = " AND ".join([f"t.`{c}` <=> k.`{c}`" for c in GROUP_COLS])
    col_list = ", ".join([f"`{c}`" for c in OUTPUT_COLS])

    with db.engine.begin() as conn:
        del_sql = f"""
        DELETE t
        FROM {tgt_qual} t
        JOIN {keys_qual} k
          ON {join_cond}
        """
        deleted = conn.execute(text(del_sql)).rowcount or 0

        ins_sql = f"""
        INSERT INTO {tgt_qual} ({col_list})
        SELECT {col_list}
        FROM {stg_qual}
        """
        inserted = conn.execute(text(ins_sql)).rowcount or 0

        conn.execute(text(f"DROP TABLE IF EXISTS {stg_qual}"))
        conn.execute(text(f"DROP TABLE IF EXISTS {keys_qual}"))

    logger.info(f"[write] {db.db}.{table_name}: deleted={deleted}, inserted={inserted}")


# =============================================================================
# Run
# =============================================================================
def run_once_for_range(
    cfg: Config,
    start_dt: datetime,
    end_dt: datetime,
    aoi_list: List[str],
) -> pd.DataFrame:
    logger.info(f"[run] start_dt={start_dt}, end_dt={end_dt}, aoi_list={aoi_list}")

    cim_db = MySQLDB(cfg.cim_db, cfg)
    rtms_db = MySQLDB(cfg.rtms_db, cfg)
    out_db = MySQLDB(cfg.out_db, cfg)

    glass_df = load_bpi_standard_glass_in_range(
        cfg=cfg,
        cim_db=cim_db,
        rtms_db=rtms_db,
        start_dt=start_dt,
        end_dt=end_dt,
        aoi_list=aoi_list,
    )

    if glass_df.empty:
        logger.warning("[run] no BPI glass rows")
        return pd.DataFrame()

    # 新規則：同 cst 同天全部歸到最早 scantime 的 hourly
    glass_df = apply_cst_anchor_scan_hour(glass_df)

    summary_df = build_bpi_api_summary(glass_df)

    if summary_df.empty:
        logger.warning("[run] summary empty")
        return pd.DataFrame()

    if cfg.write_out:
        summary_df["_yyyymm"] = pd.to_datetime(summary_df["scan_hour"], errors="coerce").dt.strftime("%Y%m")

        for yyyymm, part in summary_df.groupby("_yyyymm", dropna=True):
            out_tbn = out_summary_table(cfg, str(yyyymm))
            write_summary_overwrite_groups(out_db, out_tbn, part.drop(columns=["_yyyymm"]))

        summary_df.drop(columns=["_yyyymm"], inplace=True)
    else:
        logger.info("[run] write_out disabled, skip DB write")

    return summary_df


def mode_loop(cfg: Config, aoi_list: List[str]):
    logger.info(
        f"[mode=loop] every={cfg.loop_minutes}min, "
        f"lookback={cfg.lookback_minutes}min, "
        f"include_year00={cfg.include_year00}, "
        f"include_prev_year00={cfg.include_prev_year00}, "
        f"write_out={cfg.write_out}"
    )

    while True:
        try:
            start_dt, end_dt = resolve_window(
                "loop",
                month=None,
                days=0,
                date_str=None,
                start_str=None,
                end_str=None,
                lookback_minutes=cfg.lookback_minutes,
            )
            run_once_for_range(cfg, start_dt, end_dt, aoi_list)
        except Exception as e:
            logger.exception(f"[loop] failed: {e}")

        time.sleep(cfg.loop_minutes * 60)


# =============================================================================
# CLI
# =============================================================================
def parse_csv_list(v: Optional[str]) -> List[str]:
    if not v:
        return []
    return [x.strip().lower() for x in str(v).split(",") if x.strip()]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build BPI API summary from CIM/RTMS glass tables")

    p.add_argument(
        "--mode",
        choices=["loop", "month", "days", "date", "range"],
        default="loop",
    )

    p.add_argument("--month", default="", help="YYYYMM for month mode")
    p.add_argument("--days", type=int, default=7, help="N days for days mode")
    p.add_argument("--date", default="", help="YYYY-MM-DD for date mode")
    p.add_argument("--start", default="", help="range start datetime")
    p.add_argument("--end", default="", help="range end datetime")

    p.add_argument("--host", default="10.97.142.217")
    p.add_argument("--username", default="l6a01_user")
    p.add_argument("--password", default="l6a01$user")

    p.add_argument("--cim-db", default="cim_piaoi")
    p.add_argument("--rtms-db", default="rtms_piaoi_other")
    p.add_argument("--out-db", default="piaoi_bpi_density")

    p.add_argument("--loop-minutes", type=int, default=10)
    p.add_argument("--lookback-minutes", type=int, default=180)

    p.add_argument(
        "--aoi-list",
        default="aoi100,aoi200,aoi300",
        help="comma-separated AOI list, e.g. aoi100,aoi300",
    )

    p.add_argument(
        "--write-out",
        action="store_true",
        help="enable writing output DB",
    )

    p.add_argument(
        "--no-year00",
        action="store_true",
        help="do not read cim_pi_glass_YYYY00 tables",
    )

    p.add_argument(
        "--no-prev-year00",
        action="store_true",
        help="do not read previous year's cim_pi_glass_YYYY00 table",
    )

    return p


def main(argv: Optional[List[str]] = None):
    parser = build_parser()
    args, _unknown = parser.parse_known_args(argv)

    aoi_list = parse_csv_list(args.aoi_list)
    if not aoi_list:
        aoi_list = AOI_LIST_ALL.copy()

    aoi_list = [x for x in aoi_list if x in AOI_LIST_ALL]
    if not aoi_list:
        raise ValueError("aoi-list 無有效 AOI，需為 aoi100/aoi200/aoi300")

    cfg = Config(
        host=args.host,
        username=args.username,
        password=args.password,
        cim_db=args.cim_db,
        rtms_db=args.rtms_db,
        out_db=args.out_db,
        loop_minutes=args.loop_minutes,
        lookback_minutes=args.lookback_minutes,
        write_out=bool(args.write_out),
        include_year00=not bool(args.no_year00),
        include_prev_year00=not bool(args.no_prev_year00),
    )

    logger.info(
        f"[start] mode={args.mode}, cim_db={cfg.cim_db}, rtms_db={cfg.rtms_db}, "
        f"out_db={cfg.out_db}, write_out={cfg.write_out}, "
        f"include_year00={cfg.include_year00}, include_prev_year00={cfg.include_prev_year00}, "
        f"aoi_list={aoi_list}"
    )

    if args.mode == "loop":
        mode_loop(cfg, aoi_list)
        return

    start_dt, end_dt = resolve_window(
        args.mode,
        month=args.month.strip() or None,
        days=args.days,
        date_str=args.date.strip() or None,
        start_str=args.start.strip() or None,
        end_str=args.end.strip() or None,
        lookback_minutes=args.lookback_minutes,
    )

    run_once_for_range(cfg, start_dt, end_dt, aoi_list)


if __name__ == "__main__":
    main()


"""
Usage:

# Loop，每 10 分鐘跑一次，回看 180 分鐘
python build_bpi_density_job.py --mode loop --write-out --lookback-minutes 1440

# 指定月份，會讀：
#   cim_pi_glass_202604
#   cim_pi_glass_202600
#   cim_pi_glass_202500
#   rtms_aoi300_glass_202604
python build_bpi_density_job.py --mode month --month 202606 --write-out

# 最近 N 天
python build_bpi_density_job.py --mode days --days 7  --aoi-list aoi100,aoi200,aoi300 --write-out

# 指定單日
python build_bpi_density_job.py --mode date --date 2026-04-22 --write-out

# 指定區間
python build_bpi_density_job.py --mode range --start "2026-05-01 00:00:00" --end "2026-05-07 17:00:00" --write-out

# 只處理 AOI100 / AOI200
python build_bpi_density_job.py --mode month --month 202604 --aoi-list aoi100,aoi200 --write-out

# 只處理 AOI300
python build_bpi_density_job.py --mode month --month 202604 --aoi-list aoi300 --write-out

# 不讀 YYYY00
python build_bpi_density_job.py --mode month --month 202604 --no-year00 --write-out

# 只讀當年 YYYY00，不讀前一年 YYYY00
python build_bpi_density_job.py --mode month --month 202604 --no-prev-year00 --write-out

# 不寫入 DB，只測試流程
python build_bpi_density_job.py --mode days --days 1
"""