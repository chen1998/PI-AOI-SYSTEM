#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
build_bpi_same_point_job.py

建立 BPI/API 同片同點來料檢資料。

新版邏輯：
  1. API-driven：
     start_dt ~ end_dt 只代表 API scan_time 查詢範圍。

  2. BPI backward lookup：
     先取得 API raw / candidates，再依 API 同片 key 回頭找 BPI。
     BPI 查詢範圍：
       api_start_dt - bpi_lookback_days <= bpi_scan_time < api_end_dt
     最終配對仍需：
       bpi_scan_time <= api_scan_time

  3. 同片母體：
       model + glass_side + glass_id

  4. API candidate：
       model + glass_side + glass_id + aoi + recipe_id
       取最新 API scan_time。

     AOI200 API recipe:
       0xxx / 1xxx -> tab = PISpot
       2xxx / 3xxx -> tab = UPI

     AOI100 / AOI300:
       tab = aoi100 / aoi300

  5. BPI selection：
       每筆 API candidate 只取 API scan_time 以前最近一筆 BPI。
       若 API/BPI 都是 AOI200：
         API 0/2 -> BPI 4
         API 1/3 -> BPI 5

  6. 最新保留與 manual 欄位保留 key：
       model + glass_side + glass_id + tab + api_aoi + api_recipe_id

     同 recipe 新 API 進來：
       刪舊資料、寫新資料、保留 comment/action/editor/modify_time。

     不同 api_recipe_id：
       不互相覆蓋、不繼承 manual 欄位。

  7. pair table：
       不寫 offset_summary_json。
       新增:
         tab
         default_offset_um
         matched_points_json

     matched_points_json 只存 default_offset_um 的同點明細，用於前端預設點位顯示與 size filter。

  8. offset summary：
       不寫 bpi_match_rate / api_match_rate。
       使用：
         matched_bpi_s/m/l/o_count
         matched_api_s/m/l/o_count
         matched_size_transition_json

來源：
  AOI100 / AOI200:
    cim_piaoi.cim_pi_glass_yyyymm
    cim_piaoi.cim_defect_yyyymm_aoi_line

  AOI300:
    rtms_piaoi_other.rtms_aoi300_raw_yyyymm

輸出 DB：
  piaoi_bpi_same_point

輸出表：
  bpi_same_point_yyyymm
  bpi_same_point_offset_summary_yyyymm
  bpi_same_point_match_detail_yyyymm
"""

import argparse
import json
import logging
import math
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine


# =============================================================================
# Logging
# =============================================================================
def setup_logger(log_dir: str = "logs", name: str = "build_bpi_same_point_job") -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s [%(funcName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    fh = TimedRotatingFileHandler(
        os.path.join(log_dir, f"{name}.log"),
        when="D",
        interval=1,
        backupCount=95,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


logger = setup_logger()


# =============================================================================
# Config
# =============================================================================
BASE_URL = "http://10.97.139.98:1454//"
AIDI_URL = "http://l6apaimg103/dms/CELAIDI_L6A/"


@dataclass
class Config:
    host: str = "10.97.142.217"
    username: str = "l6a01_user"
    password: str = "l6a01$user"

    cim_db: str = "cim_piaoi"
    rtms_db: str = "rtms_piaoi_other"
    out_db: str = "piaoi_bpi_same_point"

    cim_summary_tpl: str = "cim_pi_glass_yyyymm"
    cim_defect_tpl: str = "cim_defect_yyyymm_aoi_line"
    rtms_raw_tpl: str = "rtms_aoi300_raw_yyyymm"

    pair_out_tpl: str = "bpi_same_point_yyyymm"
    offset_out_tpl: str = "bpi_same_point_offset_summary_yyyymm"
    match_out_tpl: str = "bpi_same_point_match_detail_yyyymm"

    loop_minutes: int = 10
    lookback_minutes: int = 180
    bpi_lookback_days: int = 30

    offsets_um: Tuple[int, ...] = (5, 10, 15, 20, 25, 30, 35, 40, 45, 50)
    default_offset_um: int = 20
    match_method: str = "nearest_one_to_one"

    write_out: bool = False
    write_match_detail: bool = True

    batch_size: int = 900
    delete_key_batch_size: int = 300

    aoi_map: Dict[str, str] = field(default_factory=lambda: {
        "CAPIT203": "aoi100",
        "CAAOI202": "aoi200",
        "CAAOI300": "aoi300",
        "AOI300": "aoi300",
        "aoi100": "aoi100",
        "aoi200": "aoi200",
        "aoi300": "aoi300",
    })


AOI_LIST_ALL = ["aoi100", "aoi200", "aoi300"]
PI_TYPES = ["BPI", "API"]


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
# Basic helpers
# =============================================================================
def clean_text(v: Any) -> str:
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass

    s = str(v).strip()
    if s.lower() in {"", "nan", "none", "null", "nat", "<na>", "undefined"}:
        return ""
    return s


def normalize_model(v: Any) -> str:
    s = clean_text(v)
    if "_" in s:
        return s.split("_")[0]
    return s


def normalize_aoi(v: Any, cfg: Config) -> str:
    s = clean_text(v)
    if not s:
        return ""

    if s in cfg.aoi_map:
        return cfg.aoi_map[s]

    su = s.upper()
    if su in cfg.aoi_map:
        return cfg.aoi_map[su]

    sl = s.lower()
    if sl in cfg.aoi_map:
        return cfg.aoi_map[sl]

    return sl


def normalize_line_id(v: Any) -> str:
    s = clean_text(v)
    if not s or s.lower() in {"null", "none", "nan"}:
        return ""
    return s.upper()


def normalize_glass_side(v: Any) -> str:
    s = clean_text(v).upper()
    if s in {"T", "TFT"}:
        return "TFT"
    if s in {"C", "CF"}:
        return "CF"
    if s in {"ITO", "TD", "CELL-ITO"}:
        return "ITO"
    if s == "PASS":
        return "PASS"
    return s


def normalize_pi_type(v: Any) -> str:
    s = clean_text(v).upper()
    if s in {"BPI", "API"}:
        return s
    return s


def is_empty_like(v: Any) -> bool:
    if v is None:
        return True

    try:
        if pd.isna(v):
            return True
    except Exception:
        pass

    s = str(v).strip()
    return s.lower() in {"", "nan", "none", "null", "nat", "<na>", "undefined"}


def normalize_defect_size(v: Any, aoi: Any = "") -> str:
    """
    defect_size 正規化。

    一般規則：
        S / SMALL  -> S
        M / MID / MIDDLE -> M
        L / LARGE -> L
        O / OVER  -> O

    AOI200 特別規則：
        defect_size 為 NULL / 空字串 / nan / none / null / <NA> / nat / undefined
        或其他無法歸類值時，統一歸 O。

    非 AOI200：
        無法歸類則回傳空字串，後續仍會被濾掉。
    """
    aoi_norm = clean_text(aoi).lower()

    if is_empty_like(v):
        return "O" if aoi_norm == "aoi200" else ""

    s = str(v).strip().upper()

    if s in {"S", "SMALL"}:
        return "S"
    if s in {"M", "MID", "MIDDLE"}:
        return "M"
    if s in {"L", "LARGE"}:
        return "L"
    if s in {"O", "OVER"}:
        return "O"

    # 如果 defect_size 是數值，也順手轉 S/M/L/O。
    n = pd.to_numeric(s, errors="coerce")
    if not pd.isna(n):
        if n <= 20:
            return "S"
        if n <= 100:
            return "M"
        if n <= 400:
            return "L"
        return "O"

    # AOI200 其他異常值也歸 O，避免 defect row 被丟掉。
    if aoi_norm == "aoi200":
        return "O"

    return ""


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def parse_dt(v: Optional[str]) -> Optional[datetime]:
    if not v:
        return None

    s = str(v).strip().replace("T", " ")

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue

    raise ValueError(f"Bad datetime: {v}")


def month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_month_start(dt: datetime) -> datetime:
    if dt.month == 12:
        return dt.replace(
            year=dt.year + 1,
            month=1,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

    return dt.replace(
        month=dt.month + 1,
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )


def iter_yyyymm_in_range(start_dt: datetime, end_dt: datetime) -> List[str]:
    if end_dt < start_dt:
        start_dt, end_dt = end_dt, start_dt

    out: List[str] = []
    cur = month_start(start_dt)

    while cur < end_dt:
        out.append(cur.strftime("%Y%m"))
        cur = next_month_start(cur)

    return out


def parse_csv_list(v: Optional[str]) -> List[str]:
    if not v:
        return []
    return [str(x).strip().lower() for x in str(v).split(",") if str(x).strip()]


def parse_int_csv(v: Optional[str]) -> List[int]:
    if not v:
        return []

    out = []

    for x in str(v).split(","):
        sx = str(x).strip()
        if not sx:
            continue

        try:
            out.append(int(sx))
        except Exception:
            pass

    return sorted(set(out))


def derive_scan_hour(ts: pd.Series, cut_minute: int = 30) -> pd.Series:
    s = pd.to_datetime(ts, errors="coerce")
    return (s - pd.to_timedelta(cut_minute, unit="m")).dt.floor("h")


def derive_run_day(ts: pd.Series) -> pd.Series:
    s = pd.to_datetime(ts, errors="coerce")
    return (s - pd.to_timedelta(7 * 60 + 30, unit="m")).dt.date


def derive_scan_hour_one(v: Any, cut_minute: int = 30):
    dt = pd.to_datetime(v, errors="coerce")
    if pd.isna(dt):
        return None
    return (dt - pd.Timedelta(minutes=cut_minute)).floor("h")


def derive_run_day_one(v: Any):
    dt = pd.to_datetime(v, errors="coerce")
    if pd.isna(dt):
        return None
    return (dt - pd.Timedelta(hours=7, minutes=30)).date()


def recipe_head(v: Any) -> str:
    s = clean_text(v)
    return s[0] if s else ""


def resolve_window(
    mode: str,
    *,
    month: str = "",
    days: int = 7,
    date_str: str = "",
    start_str: str = "",
    end_str: str = "",
    lookback_minutes: int = 180,
) -> Tuple[datetime, datetime]:
    now = datetime.now()

    if mode == "loop":
        end_dt = now
        start_dt = end_dt - timedelta(minutes=int(lookback_minutes))
        return start_dt, end_dt

    if mode == "month":
        yyyymm = str(month or "").strip() or now.strftime("%Y%m")
        start_dt = datetime.strptime(yyyymm + "01", "%Y%m%d")
        end_dt = next_month_start(start_dt)
        return start_dt, end_dt

    if mode == "days":
        end_dt = now
        start_dt = end_dt - timedelta(days=int(days))
        return start_dt, end_dt

    if mode == "date":
        if not date_str:
            raise ValueError("--mode date requires --date YYYY-MM-DD")
        d = parse_dt(date_str)
        start_dt = d.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = start_dt + timedelta(days=1)
        return start_dt, end_dt

    if mode == "range":
        if not start_str:
            raise ValueError("--mode range requires --start")
        start_dt = parse_dt(start_str)
        end_dt = parse_dt(end_str) if end_str else now
        if end_dt < start_dt:
            start_dt, end_dt = end_dt, start_dt
        return start_dt, end_dt

    raise ValueError(f"unknown mode: {mode}")


# =============================================================================
# Image path helpers
# =============================================================================
def is_http_url(v: Any) -> bool:
    s = clean_text(v).lower()
    return s.startswith("http://") or s.startswith("https://")


def join_url_path(base: str, path: str) -> str:
    b = clean_text(base)
    p = clean_text(path).replace("\\", "/")

    if not b:
        return p
    if not p:
        return b

    return b.rstrip("/") + "/" + p.lstrip("/")


def normalize_aidi_or_direct_path(v: Any) -> str:
    """
    支援：
      http(s)://... -> 原樣
      PIT/...       -> AIDI_URL + PIT/...
      /PIT/...      -> AIDI_URL + PIT/...
      其他          -> 原樣
    """
    s = clean_text(v).replace("\\", "/")
    if not s:
        return ""

    if is_http_url(s):
        return s

    if s.startswith("PIT/") or s.startswith("/PIT/"):
        return join_url_path(AIDI_URL, s)

    return s


def normalize_unc_image_path(v: Any) -> str:
    """
    支援：
      \\\\192.168.5.88\\aoi\\CAPIT203\\...
      //192.168.5.88/aoi/CAPIT203/...
    """
    s0 = clean_text(v)
    if not s0:
        return ""

    if is_http_url(s0):
        return s0

    s = s0.replace("\\", "/")
    prefix = "//192.168.5.88/aoi"

    if s.startswith(prefix):
        rest = s[len(prefix):].lstrip("/")
        return join_url_path(BASE_URL, rest)

    return s


def build_cim_image_capture_path(
    *,
    raw_path: Any,
    latest_tt: Any,
    op_id: Any,
    aoi: str,
    cfg: Config,
) -> str:
    """
    raw_path example:
      Image/CA002302/VP5GAHT5Q/

    output:
      BASE_URL + machine_id + / + CA002302/VP5GAHT5Q/ + op_id + / + YYYYMMDDHHMMSS + /CaptureImage/
    """
    path0 = clean_text(raw_path).replace("\\", "/")
    if not path0:
        return ""

    try:
        str_time = pd.to_datetime(latest_tt).strftime("%Y%m%d%H%M%S")
    except Exception:
        str_time = (
            str(latest_tt)
            .replace("-", "")
            .replace(":", "")
            .replace(" ", "")
        )

    p2 = path0[6:] if path0.startswith("Image/") else path0
    p2 = p2.lstrip("/")

    if p2 and not p2.endswith("/"):
        p2 += "/"

    re_aoimap = {v: k for k, v in cfg.aoi_map.items()}
    machine_id = re_aoimap.get(aoi, aoi)

    return (
        BASE_URL
        + machine_id
        + "/"
        + p2
        + clean_text(op_id)
        + "/"
        + str_time
        + "/CaptureImage/"
    )


def load_cim_op_id(
    *,
    cim_db: MySQLDB,
    cfg: Config,
    yyyymm: str,
    gld: str,
    latest_tt: Any,
) -> str:
    sum_tbn = cim_summary_table(cfg, yyyymm)

    if not cim_db.table_exists(sum_tbn):
        logger.warning(f"[load_cim_op_id] missing summary table={sum_tbn}")
        return ""

    try:
        sql = f"""
        SELECT op_id
        FROM `{cim_db.db}`.`{sum_tbn}`
        WHERE sheet_id_chip_id = :gld
          AND test_time = :latest_tt
        LIMIT 1
        """
        df = cim_db.query_df(sql, {
            "gld": gld,
            "latest_tt": latest_tt,
        })
    except Exception as e:
        logger.warning(
            f"[load_cim_op_id] query failed: table={sum_tbn}, "
            f"glass={gld}, test_time={latest_tt}, err={e}"
        )
        return ""

    if df is None or df.empty:
        logger.warning(
            f"[load_cim_op_id] summary row not found: table={sum_tbn}, "
            f"glass={gld}, test_time={latest_tt}"
        )
        return ""

    return clean_text(df.iloc[0].get("op_id", ""))


def normalize_cim_image_paths_for_group(
    *,
    def_tb: pd.DataFrame,
    gld: str,
    latest_tt: Any,
    aoi: str,
    yyyymm: str,
    cim_db: MySQLDB,
    cfg: Config,
) -> pd.DataFrame:
    """
    AOI100/AOI200 CIM defect image path normalization.

    優先順序：
      1. img_file_url_path 有值
      2. image_file_path 有值
      3. PIT/...      -> AIDI_URL + PIT/...
      4. Image/...    -> 查 summary op_id 後組 CaptureImage path
      5. UNC path     -> BASE_URL + converted path
      6. http(s)      -> 原樣
      7. 其他         -> 原樣
    """
    if def_tb is None or def_tb.empty:
        return def_tb

    out = def_tb.copy()

    if "img_file_url_path" not in out.columns:
        out["img_file_url_path"] = ""

    if "image_file_path" not in out.columns:
        out["image_file_path"] = ""

    values = []
    values.extend(out["img_file_url_path"].map(clean_text).tolist())
    values.extend(out["image_file_path"].map(clean_text).tolist())

    need_op_id = any(v.replace("\\", "/").startswith("Image") for v in values if v)
    op_id = ""

    if need_op_id:
        op_id = load_cim_op_id(
            cim_db=cim_db,
            cfg=cfg,
            yyyymm=yyyymm,
            gld=gld,
            latest_tt=latest_tt,
        )

    def normalize_one(row: pd.Series) -> str:
        src = clean_text(row.get("img_file_url_path", ""))
        if not src:
            src = clean_text(row.get("image_file_path", ""))

        if not src:
            return ""

        s = src.replace("\\", "/")

        if s.startswith("PIT/") or s.startswith("/PIT/"):
            return normalize_aidi_or_direct_path(s)

        if s.startswith("Image"):
            return build_cim_image_capture_path(
                raw_path=s,
                latest_tt=latest_tt,
                op_id=op_id,
                aoi=aoi,
                cfg=cfg,
            )

        if "192.168.5.88/aoi" in s or "\\\\192.168.5.88\\aoi" in src:
            return normalize_unc_image_path(src)

        if is_http_url(s):
            return s

        return s

    out["__norm_pic_path"] = out.apply(normalize_one, axis=1)

    return out


def normalize_rtms_pic_path(v: Any) -> str:
    """
    AOI300 RTMS pic_path normalization.

    RTMS raw 若已經是完整 URL -> 原樣
    若是 PIT/... -> AIDI_URL + PIT/...
    其他 -> 原樣
    """
    return normalize_aidi_or_direct_path(v)


# =============================================================================
# Table names
# =============================================================================
def cim_summary_table(cfg: Config, yyyymm: str) -> str:
    return cfg.cim_summary_tpl.replace("yyyymm", yyyymm).lower()


def cim_defect_table(cfg: Config, yyyymm: str, aoi: str, line_id: str) -> str:
    return (
        cfg.cim_defect_tpl
        .replace("yyyymm", yyyymm)
        .replace("aoi", aoi.lower())
        .replace("line", line_id.lower())
        .lower()
    )


def rtms_raw_table(cfg: Config, yyyymm: str) -> str:
    return cfg.rtms_raw_tpl.replace("yyyymm", yyyymm).lower()


def out_table(tpl: str, yyyymm: str) -> str:
    return tpl.replace("yyyymm", yyyymm).lower()


# =============================================================================
# Output schemas
# =============================================================================
PAIR_OUT_COLS = [
    "model",
    "glass_side",
    "glass_id",
    "scan_hour",
    "run_day",
    "tab",

    "bpi_aoi",
    "bpi_line_id",
    "bpi_recipe_id",
    "bpi_cassette_id",
    "bpi_scan_time",
    "bpi_pi_time",
    "bpi_scan_hour",
    "bpi_run_day",
    "bpi_source_db",
    "bpi_source_table",

    "api_aoi",
    "api_line_id",
    "api_recipe_id",
    "api_cassette_id",
    "api_scan_time",
    "api_pi_time",
    "api_scan_hour",
    "api_run_day",
    "api_source_db",
    "api_source_table",

    "bpi_defect_count",
    "api_defect_count",

    "bpi_small_defect_count",
    "bpi_middle_defect_count",
    "bpi_large_defect_count",
    "bpi_over_defect_count",

    "api_small_defect_count",
    "api_middle_defect_count",
    "api_large_defect_count",
    "api_over_defect_count",

    "pair_status",
    "pair_message",
    "default_offset_um",
    "matched_points_json",

    "comment",
    "action",
    "editor",
    "modify_time",

    "gen_time",
]

OFFSET_OUT_COLS = [
    "model",
    "glass_side",
    "glass_id",
    "scan_hour",
    "run_day",
    "tab",

    "bpi_aoi",
    "bpi_scan_time",
    "bpi_recipe_id",

    "api_aoi",
    "api_scan_time",
    "api_recipe_id",

    "offset_um",

    "bpi_defect_count",
    "api_defect_count",
    "matched_pair_count",
    "matched_bpi_defect_count",
    "matched_api_defect_count",
    "unmatched_bpi_defect_count",
    "unmatched_api_defect_count",

    "matched_bpi_s_count",
    "matched_bpi_m_count",
    "matched_bpi_l_count",
    "matched_bpi_o_count",

    "matched_api_s_count",
    "matched_api_m_count",
    "matched_api_l_count",
    "matched_api_o_count",

    "matched_size_transition_json",

    "gen_time",
]

MATCH_OUT_COLS = [
    "model",
    "glass_side",
    "glass_id",
    "scan_hour",
    "run_day",
    "tab",

    "bpi_aoi",
    "bpi_line_id",
    "bpi_recipe_id",
    "bpi_scan_time",

    "api_aoi",
    "api_line_id",
    "api_recipe_id",
    "api_scan_time",

    "offset_um",

    "bpi_defect_uid",
    "bpi_chip_id",
    "bpi_x",
    "bpi_y",
    "bpi_defect_size",
    "bpi_adc_def_code",
    "bpi_retype_code",
    "bpi_pic_path",
    "bpi_pic_name",

    "api_defect_uid",
    "api_chip_id",
    "api_x",
    "api_y",
    "api_defect_size",
    "api_adc_def_code",
    "api_retype_code",
    "api_pic_path",
    "api_pic_name",

    "dx",
    "dy",
    "distance",
    "match_rank",
    "match_method",
    "gen_time",
]

MANUAL_COLS = ["comment", "action", "editor", "modify_time"]

AFFECTED_KEY_COLS = [
    "model",
    "glass_side",
    "glass_id",
    "tab",
    "api_aoi",
    "api_recipe_id",
]

PAIR_MANUAL_KEY_COLS = AFFECTED_KEY_COLS.copy()


# =============================================================================
# DDL
# =============================================================================
def ensure_column(db: MySQLDB, table_name: str, col: str, ddl: str):
    sql = text("""
        SELECT COUNT(*)
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = :db
          AND TABLE_NAME = :t
          AND COLUMN_NAME = :c
    """)

    with db.engine.begin() as conn:
        exists = conn.execute(sql, {
            "db": db.db,
            "t": table_name,
            "c": col,
        }).scalar()

        if not exists:
            conn.execute(text(
                f"ALTER TABLE `{db.db}`.`{table_name}` ADD COLUMN `{col}` {ddl}"
            ))
            logger.info(f"[ensure_column] {db.db}.{table_name} ADD {col} {ddl}")


def ensure_pair_out_table(db: MySQLDB, table_name: str):
    ddl = f"""
    CREATE TABLE IF NOT EXISTS `{db.db}`.`{table_name}` (
        id BIGINT NOT NULL AUTO_INCREMENT,

        model VARCHAR(128) NOT NULL,
        glass_side VARCHAR(32) NOT NULL,
        glass_id VARCHAR(128) NOT NULL,
        scan_hour DATETIME NULL,
        run_day DATE NULL,
        tab VARCHAR(32) NULL,

        bpi_aoi VARCHAR(32) NOT NULL,
        bpi_line_id VARCHAR(64) NULL,
        bpi_recipe_id VARCHAR(128) NULL,
        bpi_cassette_id VARCHAR(128) NULL,
        bpi_scan_time DATETIME NOT NULL,
        bpi_pi_time DATETIME NULL,
        bpi_scan_hour DATETIME NULL,
        bpi_run_day DATE NULL,
        bpi_source_db VARCHAR(64) NULL,
        bpi_source_table VARCHAR(128) NULL,

        api_aoi VARCHAR(32) NOT NULL,
        api_line_id VARCHAR(64) NULL,
        api_recipe_id VARCHAR(128) NULL,
        api_cassette_id VARCHAR(128) NULL,
        api_scan_time DATETIME NOT NULL,
        api_pi_time DATETIME NULL,
        api_scan_hour DATETIME NULL,
        api_run_day DATE NULL,
        api_source_db VARCHAR(64) NULL,
        api_source_table VARCHAR(128) NULL,

        bpi_defect_count INT NOT NULL DEFAULT 0,
        api_defect_count INT NOT NULL DEFAULT 0,

        bpi_small_defect_count INT NOT NULL DEFAULT 0,
        bpi_middle_defect_count INT NOT NULL DEFAULT 0,
        bpi_large_defect_count INT NOT NULL DEFAULT 0,
        bpi_over_defect_count INT NOT NULL DEFAULT 0,

        api_small_defect_count INT NOT NULL DEFAULT 0,
        api_middle_defect_count INT NOT NULL DEFAULT 0,
        api_large_defect_count INT NOT NULL DEFAULT 0,
        api_over_defect_count INT NOT NULL DEFAULT 0,

        pair_status VARCHAR(32) NOT NULL DEFAULT 'OK',
        pair_message TEXT NULL,
        default_offset_um INT NULL,
        matched_points_json LONGTEXT NULL,

        comment TEXT NULL,
        action TEXT NULL,
        editor VARCHAR(64) NULL,
        modify_time DATETIME NULL,

        gen_time DATETIME NULL,

        PRIMARY KEY (id),

        UNIQUE KEY uniq_pair (
            model,
            glass_side,
            glass_id,
            tab,
            bpi_aoi,
            bpi_recipe_id,
            bpi_scan_time,
            api_aoi,
            api_recipe_id,
            api_scan_time
        ),

        KEY idx_scan_hour (scan_hour),
        KEY idx_run_day (run_day),
        KEY idx_tab_scan_hour (tab, scan_hour),
        KEY idx_glass (model, glass_side, glass_id),
        KEY idx_latest_key (model, glass_side, glass_id, tab, api_aoi, api_recipe_id),
        KEY idx_bpi_time (bpi_scan_time),
        KEY idx_api_time (api_scan_time),
        KEY idx_bpi_aoi (bpi_aoi),
        KEY idx_api_aoi (api_aoi)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    db.execute(ddl)


def ensure_offset_out_table(db: MySQLDB, table_name: str):
    ddl = f"""
    CREATE TABLE IF NOT EXISTS `{db.db}`.`{table_name}` (
        id BIGINT NOT NULL AUTO_INCREMENT,

        model VARCHAR(128) NOT NULL,
        glass_side VARCHAR(32) NOT NULL,
        glass_id VARCHAR(128) NOT NULL,
        scan_hour DATETIME NULL,
        run_day DATE NULL,
        tab VARCHAR(32) NULL,

        bpi_aoi VARCHAR(32) NOT NULL,
        bpi_scan_time DATETIME NOT NULL,
        bpi_recipe_id VARCHAR(128) NULL,

        api_aoi VARCHAR(32) NOT NULL,
        api_scan_time DATETIME NOT NULL,
        api_recipe_id VARCHAR(128) NULL,

        offset_um INT NOT NULL,

        bpi_defect_count INT NOT NULL DEFAULT 0,
        api_defect_count INT NOT NULL DEFAULT 0,

        matched_pair_count INT NOT NULL DEFAULT 0,
        matched_bpi_defect_count INT NOT NULL DEFAULT 0,
        matched_api_defect_count INT NOT NULL DEFAULT 0,
        unmatched_bpi_defect_count INT NOT NULL DEFAULT 0,
        unmatched_api_defect_count INT NOT NULL DEFAULT 0,

        matched_bpi_s_count INT NOT NULL DEFAULT 0,
        matched_bpi_m_count INT NOT NULL DEFAULT 0,
        matched_bpi_l_count INT NOT NULL DEFAULT 0,
        matched_bpi_o_count INT NOT NULL DEFAULT 0,

        matched_api_s_count INT NOT NULL DEFAULT 0,
        matched_api_m_count INT NOT NULL DEFAULT 0,
        matched_api_l_count INT NOT NULL DEFAULT 0,
        matched_api_o_count INT NOT NULL DEFAULT 0,

        matched_size_transition_json LONGTEXT NULL,

        gen_time DATETIME NULL,

        PRIMARY KEY (id),

        UNIQUE KEY uniq_offset (
            model,
            glass_side,
            glass_id,
            tab,
            bpi_aoi,
            bpi_recipe_id,
            bpi_scan_time,
            api_aoi,
            api_recipe_id,
            api_scan_time,
            offset_um
        ),

        KEY idx_scan_hour (scan_hour),
        KEY idx_run_day (run_day),
        KEY idx_tab_scan_hour (tab, scan_hour),
        KEY idx_latest_key (model, glass_side, glass_id, tab, api_aoi, api_recipe_id),
        KEY idx_glass_offset (model, glass_side, glass_id, offset_um),
        KEY idx_bpi_time (bpi_scan_time),
        KEY idx_api_time (api_scan_time)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    db.execute(ddl)


def ensure_match_out_table(db: MySQLDB, table_name: str):
    ddl = f"""
    CREATE TABLE IF NOT EXISTS `{db.db}`.`{table_name}` (
        id BIGINT NOT NULL AUTO_INCREMENT,

        model VARCHAR(128) NOT NULL,
        glass_side VARCHAR(32) NOT NULL,
        glass_id VARCHAR(128) NOT NULL,
        scan_hour DATETIME NULL,
        run_day DATE NULL,
        tab VARCHAR(32) NULL,

        bpi_aoi VARCHAR(32) NOT NULL,
        bpi_line_id VARCHAR(64) NULL,
        bpi_recipe_id VARCHAR(128) NULL,
        bpi_scan_time DATETIME NOT NULL,

        api_aoi VARCHAR(32) NOT NULL,
        api_line_id VARCHAR(64) NULL,
        api_recipe_id VARCHAR(128) NULL,
        api_scan_time DATETIME NOT NULL,

        offset_um INT NOT NULL,

        bpi_defect_uid VARCHAR(255) NULL,
        bpi_chip_id VARCHAR(128) NULL,
        bpi_x DOUBLE NOT NULL,
        bpi_y DOUBLE NOT NULL,
        bpi_defect_size VARCHAR(32) NULL,
        bpi_adc_def_code VARCHAR(128) NULL,
        bpi_retype_code VARCHAR(128) NULL,
        bpi_pic_path LONGTEXT NULL,
        bpi_pic_name VARCHAR(512) NULL,

        api_defect_uid VARCHAR(255) NULL,
        api_chip_id VARCHAR(128) NULL,
        api_x DOUBLE NOT NULL,
        api_y DOUBLE NOT NULL,
        api_defect_size VARCHAR(32) NULL,
        api_adc_def_code VARCHAR(128) NULL,
        api_retype_code VARCHAR(128) NULL,
        api_pic_path LONGTEXT NULL,
        api_pic_name VARCHAR(512) NULL,

        dx DOUBLE NULL,
        dy DOUBLE NULL,
        distance DOUBLE NULL,
        match_rank INT NULL,
        match_method VARCHAR(64) NOT NULL DEFAULT 'nearest_one_to_one',
        gen_time DATETIME NULL,

        PRIMARY KEY (id),

        KEY idx_scan_hour (scan_hour),
        KEY idx_run_day (run_day),
        KEY idx_tab_scan_hour (tab, scan_hour),
        KEY idx_latest_key (model, glass_side, glass_id, tab, api_aoi, api_recipe_id),
        KEY idx_glass_offset (model, glass_side, glass_id, offset_um),
        KEY idx_bpi_scan (bpi_scan_time),
        KEY idx_api_scan (api_scan_time),
        KEY idx_bpi_xy (bpi_x, bpi_y),
        KEY idx_api_xy (api_x, api_y),
        KEY idx_size (bpi_defect_size, api_defect_size)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    db.execute(ddl)


def ensure_pair_manual_columns(db: MySQLDB, table_name: str):
    ensure_column(db, table_name, "comment", "TEXT NULL")
    ensure_column(db, table_name, "action", "TEXT NULL")
    ensure_column(db, table_name, "editor", "VARCHAR(64) NULL")
    ensure_column(db, table_name, "modify_time", "DATETIME NULL")


# =============================================================================
# SQL write helpers
# =============================================================================
def prepare_df_for_sql(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    if df is None:
        df = pd.DataFrame()

    out = df.copy()

    for c in cols:
        if c not in out.columns:
            out[c] = None

    out = out[cols].copy()

    dt_cols = [
        c for c in out.columns
        if c.endswith("_time")
        or c.endswith("_hour")
        or c in {"scan_hour", "gen_time", "modify_time"}
    ]

    for c in dt_cols:
        out[c] = pd.to_datetime(out[c], errors="coerce")
        out[c] = out[c].map(lambda v: None if pd.isna(v) else v.to_pydatetime())

    for c in ["run_day", "bpi_run_day", "api_run_day"]:
        if c in out.columns:
            out[c] = pd.to_datetime(out[c], errors="coerce").dt.date
            out[c] = out[c].where(pd.notna(out[c]), None)

    for c in out.columns:
        if out[c].dtype == "object":
            out[c] = out[c].where(out[c].notna(), None)

    return out


def append_df(
    db: MySQLDB,
    table_name: str,
    df: pd.DataFrame,
    cols: List[str],
    *,
    ensure_fn,
) -> Dict[str, int]:
    ensure_fn(db, table_name)

    if df is None or df.empty:
        logger.info(f"[append] {table_name}: inserted=0")
        return {"inserted": 0}

    out = prepare_df_for_sql(df, cols)

    out.to_sql(
        name=table_name,
        con=db.engine,
        schema=db.db,
        if_exists="append",
        index=False,
        chunksize=20000,
        method="multi",
    )

    logger.info(f"[append] {table_name}: inserted={len(out)}")
    return {"inserted": len(out)}


def list_month_tables(db: MySQLDB, tpl: str) -> List[str]:
    prefix, suffix = tpl.lower().split("yyyymm")
    like_pat = f"{prefix}%{suffix}"

    sql = """
    SELECT TABLE_NAME
    FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = :db
      AND TABLE_NAME LIKE :pat
    """

    df = db.query_df(sql, {"db": db.db, "pat": like_pat})
    if df is None or df.empty:
        return []

    rgx = re.compile("^" + re.escape(prefix) + r"\d{6}" + re.escape(suffix) + "$")
    tables = [str(x) for x in df["TABLE_NAME"].tolist() if rgx.match(str(x))]
    return sorted(tables)


def build_key_or_conditions(
    affected_keys: pd.DataFrame,
    key_cols: List[str],
    batch_index: int = 0,
) -> Tuple[str, Dict[str, Any]]:
    conditions = []
    params: Dict[str, Any] = {}

    for i, (_, row) in enumerate(affected_keys.iterrows()):
        parts = []
        for c in key_cols:
            p = f"{c}_{batch_index}_{i}"
            parts.append(f"`{c}` = :{p}")
            params[p] = clean_text(row.get(c, ""))
        conditions.append("(" + " AND ".join(parts) + ")")

    return " OR ".join(conditions), params


def delete_by_affected_keys(
    db: MySQLDB,
    table_name: str,
    affected_keys: pd.DataFrame,
    key_cols: List[str],
    batch_size: int = 300,
) -> int:
    if affected_keys is None or affected_keys.empty:
        return 0

    if not db.table_exists(table_name):
        return 0

    total = 0
    keys = affected_keys[key_cols].drop_duplicates().copy()

    for start in range(0, len(keys), batch_size):
        batch = keys.iloc[start:start + batch_size].copy()
        cond, params = build_key_or_conditions(batch, key_cols, batch_index=start)

        if not cond:
            continue

        sql = f"""
        DELETE FROM `{db.db}`.`{table_name}`
        WHERE {cond}
        """
        r = db.execute(sql, params)
        total += int(r.rowcount or 0)

    logger.info(f"[delete_by_keys] {table_name}: deleted={total}")
    return total


def load_existing_manual_by_keys(
    db: MySQLDB,
    table_names: List[str],
    affected_keys: pd.DataFrame,
    key_cols: List[str],
    batch_size: int = 300,
) -> pd.DataFrame:
    cols = key_cols + MANUAL_COLS + ["gen_time", "api_scan_time"]

    if affected_keys is None or affected_keys.empty:
        return pd.DataFrame(columns=cols)

    keys = affected_keys[key_cols].drop_duplicates().copy()
    frames: List[pd.DataFrame] = []

    for table_name in table_names:
        if not db.table_exists(table_name):
            continue

        ensure_pair_manual_columns(db, table_name)

        for start in range(0, len(keys), batch_size):
            batch = keys.iloc[start:start + batch_size].copy()
            cond, params = build_key_or_conditions(batch, key_cols, batch_index=start)

            if not cond:
                continue

            sql = f"""
            SELECT
                {", ".join([f"`{c}`" for c in key_cols])},
                comment,
                action,
                editor,
                modify_time,
                gen_time,
                api_scan_time
            FROM `{db.db}`.`{table_name}`
            WHERE {cond}
            """

            part = db.query_df(sql, params)
            if part is not None and not part.empty:
                frames.append(part)

    if not frames:
        return pd.DataFrame(columns=cols)

    out = pd.concat(frames, ignore_index=True)

    for c in ["modify_time", "gen_time", "api_scan_time"]:
        if c in out.columns:
            out[c] = pd.to_datetime(out[c], errors="coerce")

    out = out.sort_values(
        key_cols + ["modify_time", "gen_time", "api_scan_time"],
        na_position="first",
    )

    out = out.drop_duplicates(key_cols, keep="last")
    return out.reset_index(drop=True)


def preserve_pair_manual_fields_by_recipe(
    new_df: pd.DataFrame,
    old_manual_df: pd.DataFrame,
) -> pd.DataFrame:
    if new_df is None or new_df.empty:
        return new_df

    if old_manual_df is None or old_manual_df.empty:
        return new_df

    out = new_df.copy()
    old = old_manual_df.copy()

    old = old[PAIR_MANUAL_KEY_COLS + MANUAL_COLS].drop_duplicates(
        PAIR_MANUAL_KEY_COLS,
        keep="last",
    )

    out = out.merge(
        old,
        how="left",
        on=PAIR_MANUAL_KEY_COLS,
        suffixes=("", "_old"),
    )

    for c in MANUAL_COLS:
        old_c = f"{c}_old"
        if old_c not in out.columns:
            continue

        if c == "modify_time":
            out[c] = out[old_c].combine_first(out[c])
        else:
            old_val = out[old_c].astype("string").fillna("").astype(str).str.strip()
            out[c] = out[old_c].where(old_val.ne(""), out[c])

        out = out.drop(columns=[old_c])

    return out


def split_by_month(df: pd.DataFrame, time_col: str) -> Dict[str, pd.DataFrame]:
    if df is None or df.empty:
        return {}

    d = df.copy()
    d[time_col] = pd.to_datetime(d[time_col], errors="coerce")
    d = d.dropna(subset=[time_col]).copy()

    if d.empty:
        return {}

    d["_yyyymm"] = d[time_col].dt.strftime("%Y%m")

    return {
        str(ym): g.drop(columns=["_yyyymm"]).copy()
        for ym, g in d.groupby("_yyyymm", dropna=False)
    }


# =============================================================================
# Load CIM AOI100 / AOI200
# =============================================================================
def load_cim_summary_in_range(
    cfg: Config,
    db: MySQLDB,
    start_dt: datetime,
    end_dt: datetime,
    aoi_list: List[str],
    pi_type_filter: str,
) -> pd.DataFrame:
    pi_type_filter = normalize_pi_type(pi_type_filter)
    if pi_type_filter not in PI_TYPES:
        raise ValueError("pi_type_filter must be API or BPI")

    months = iter_yyyymm_in_range(start_dt, end_dt)
    frames: List[pd.DataFrame] = []

    for ym in months:
        tbn = cim_summary_table(cfg, ym)

        if not db.table_exists(tbn):
            logger.warning(f"[cim_summary] missing {db.db}.{tbn}")
            continue

        sql = f"""
        SELECT
            sheet_id_chip_id,
            test_time,
            model_no,
            abbr_cat,
            recipe_id,
            cassette_id,
            aoi,
            line_id,
            pi_time,
            pi_hour,
            pi_type,
            total_defect_qty,
            defect_size_s_qty,
            defect_size_m_qty,
            defect_size_l_qty,
            defect_size_o_qty
        FROM `{db.db}`.`{tbn}`
        WHERE test_time >= :start_dt
          AND test_time <  :end_dt
          AND pi_type = :pi_type
        """

        part = db.query_df(sql, {
            "start_dt": start_dt,
            "end_dt": end_dt,
            "pi_type": pi_type_filter,
        })

        if part is None or part.empty:
            continue

        part["_source_table"] = tbn
        frames.append(part)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)

    out = pd.DataFrame()
    out["glass_id"] = df["sheet_id_chip_id"].map(clean_text)
    out["scan_time"] = pd.to_datetime(df["test_time"], errors="coerce")
    out["model"] = df["model_no"].map(normalize_model)
    out["glass_side"] = df["abbr_cat"].map(normalize_glass_side)
    out["recipe_id"] = df["recipe_id"].map(clean_text)
    out["cassette_id"] = df["cassette_id"].map(clean_text)
    out["aoi"] = df["aoi"].map(lambda v: normalize_aoi(v, cfg))
    out["line_id"] = df["line_id"].map(normalize_line_id)
    out["pi_time"] = pd.to_datetime(df["pi_time"], errors="coerce")
    out["scan_hour"] = pd.to_datetime(df["pi_hour"], errors="coerce")
    out["run_day"] = derive_run_day(out["scan_time"])
    out["pi_type"] = df["pi_type"].map(normalize_pi_type)

    out["total_defect_count"] = pd.to_numeric(df["total_defect_qty"], errors="coerce").fillna(0).astype(int)
    out["small_defect_count"] = pd.to_numeric(df["defect_size_s_qty"], errors="coerce").fillna(0).astype(int)
    out["middle_defect_count"] = pd.to_numeric(df["defect_size_m_qty"], errors="coerce").fillna(0).astype(int)
    out["large_defect_count"] = pd.to_numeric(df["defect_size_l_qty"], errors="coerce").fillna(0).astype(int)
    out["over_defect_count"] = pd.to_numeric(df["defect_size_o_qty"], errors="coerce").fillna(0).astype(int)

    out["source_db"] = db.db
    out["source_table"] = df["_source_table"].map(clean_text)

    out = out.dropna(subset=["scan_time"])
    out = out[
        out["glass_id"].ne("")
        & out["model"].ne("")
        & out["glass_side"].ne("")
        & out["pi_type"].eq(pi_type_filter)
        & out["aoi"].isin(aoi_list)
        & out["aoi"].isin(["aoi100", "aoi200"])
    ].copy()

    return out.reset_index(drop=True)


def load_cim_defects_for_summary(
    cfg: Config,
    db: MySQLDB,
    summary_df: pd.DataFrame,
) -> pd.DataFrame:
    if summary_df is None or summary_df.empty:
        return pd.DataFrame()

    frames: List[pd.DataFrame] = []

    keys = summary_df[
        [
            "glass_id",
            "scan_time",
            "model",
            "glass_side",
            "recipe_id",
            "cassette_id",
            "aoi",
            "line_id",
            "pi_time",
            "scan_hour",
            "run_day",
            "pi_type",
            "source_table",
        ]
    ].drop_duplicates().copy()

    keys["_yyyymm"] = pd.to_datetime(keys["scan_time"], errors="coerce").dt.strftime("%Y%m")

    for (yyyymm, aoi, line_id), kg in keys.groupby(["_yyyymm", "aoi", "line_id"], dropna=False):
        if not yyyymm or not aoi or not line_id:
            continue

        tbn = cim_defect_table(cfg, str(yyyymm), str(aoi), str(line_id))

        if not db.table_exists(tbn):
            logger.warning(f"[cim_defect] missing {db.db}.{tbn}")
            continue

        gids = kg["glass_id"].astype(str).unique().tolist()
        if not gids:
            continue

        t_min = kg["scan_time"].min()
        t_max = kg["scan_time"].max()

        for i in range(0, len(gids), cfg.batch_size):
            batch = gids[i:i + cfg.batch_size]
            bind = {f"g{j}": v for j, v in enumerate(batch)}
            in_clause = ", ".join([f":g{j}" for j in range(len(batch))])

            sql = f"""
            SELECT *
            FROM `{db.db}`.`{tbn}`
            WHERE test_time BETWEEN :t_min AND :t_max
              AND sheet_id_chip_id IN ({in_clause})
            """

            params = dict(bind)
            params.update({"t_min": t_min, "t_max": t_max})

            part = db.query_df(sql, params)

            if part is None or part.empty:
                continue

            part["_source_table"] = tbn
            frames.append(part)

    if not frames:
        return pd.DataFrame()

    d = pd.concat(frames, ignore_index=True)
    d["sheet_id_chip_id"] = d["sheet_id_chip_id"].map(clean_text)
    d["test_time"] = pd.to_datetime(d["test_time"], errors="coerce")

    dims = keys.rename(columns={
        "glass_id": "sheet_id_chip_id",
        "scan_time": "test_time",
    }).drop(columns=["_yyyymm"], errors="ignore")

    d = d.merge(
        dims,
        how="inner",
        on=["sheet_id_chip_id", "test_time"],
        suffixes=("", "_sum"),
    )

    if not d.empty and "defect_size" in d.columns:
        raw_empty_mask = d["defect_size"].apply(is_empty_like)
        aoi200_mask = d["aoi"].map(clean_text).str.lower().eq("aoi200")

        logger.info(
            "[cim_defect] raw defect_size empty rows=%s, aoi200_empty_rows=%s, total_rows=%s",
            int(raw_empty_mask.sum()),
            int((raw_empty_mask & aoi200_mask).sum()),
            len(d),
        )

        logger.info(
            "[cim_defect] raw defect_size unique=%s",
            d["defect_size"]
            .where(d["defect_size"].notna(), "<NULL>")
            .astype(str)
            .unique()
            .tolist()
        )


    if not d.empty:
        d["_yyyymm"] = pd.to_datetime(d["test_time"], errors="coerce").dt.strftime("%Y%m")

        img_frames: List[pd.DataFrame] = []

        for (gld, tt, aoi0, yyyymm), sub in d.groupby(
            ["sheet_id_chip_id", "test_time", "aoi", "_yyyymm"],
            dropna=False,
        ):
            if not yyyymm:
                img_frames.append(sub)
                continue

            sub2 = normalize_cim_image_paths_for_group(
                def_tb=sub,
                gld=clean_text(gld),
                latest_tt=tt,
                aoi=clean_text(aoi0),
                yyyymm=str(yyyymm),
                cim_db=db,
                cfg=cfg,
            )

            img_frames.append(sub2)

        d = pd.concat(img_frames, ignore_index=True) if img_frames else d
        d = d.drop(columns=["_yyyymm"], errors="ignore")

    out = pd.DataFrame()
    out["model"] = d["model"].map(clean_text)
    out["glass_side"] = d["glass_side"].map(normalize_glass_side)
    out["glass_id"] = d["sheet_id_chip_id"].map(clean_text)
    out["pi_type"] = d["pi_type"].map(normalize_pi_type)
    out["aoi"] = d["aoi"].map(clean_text)
    out["line_id"] = d["line_id"].map(normalize_line_id)
    out["recipe_id"] = d["recipe_id"].map(clean_text)
    out["cassette_id"] = d["cassette_id"].map(clean_text)
    out["scan_time"] = pd.to_datetime(d["test_time"], errors="coerce")
    out["pi_time"] = pd.to_datetime(d["pi_time"], errors="coerce")
    out["scan_hour"] = pd.to_datetime(d["scan_hour"], errors="coerce")
    out["run_day"] = d["run_day"]

    out["x"] = pd.to_numeric(d["pox_x1"], errors="coerce")
    out["y"] = pd.to_numeric(d["pox_y1"], errors="coerce")
    out["defect_size"] = d.apply(
            lambda r: normalize_defect_size(r.get("defect_size", ""), r.get("aoi", "")),
            axis=1,
        )
    if not out.empty:
        logger.info(
            "[cim_defect] normalized defect_size counts=%s",
            out["defect_size"].value_counts(dropna=False).to_dict()
        )
    out["adc_def_code"] = d.get("adc_def_code", "").map(clean_text) if "adc_def_code" in d.columns else ""
    out["retype_code"] = d.get("retype_def_code", "").map(clean_text) if "retype_def_code" in d.columns else ""
    out["chip_id"] = d.get("chip_id", "").map(clean_text) if "chip_id" in d.columns else ""

    if "__norm_pic_path" in d.columns:
        out["pic_path"] = d["__norm_pic_path"].map(clean_text)
    elif "img_file_url_path" in d.columns:
        out["pic_path"] = d["img_file_url_path"].map(normalize_aidi_or_direct_path)
    elif "image_file_path" in d.columns:
        out["pic_path"] = d["image_file_path"].map(normalize_unc_image_path)
    else:
        out["pic_path"] = ""

    out["pic_name"] = d.get("image_file_name", "").map(clean_text) if "image_file_name" in d.columns else ""

    out["source_db"] = db.db
    out["source_table"] = d["_source_table"].map(clean_text)

    out["source_id"] = (
        out["glass_id"].astype(str)
        + "|"
        + out["scan_time"].astype(str)
        + "|"
        + out["chip_id"].astype(str)
        + "|"
        + out["x"].astype(str)
        + "|"
        + out["y"].astype(str)
        + "|"
        + out["pic_name"].astype(str)
    )

    out["defect_uid"] = "CIM|" + out["source_id"]

    out = out.dropna(subset=["scan_time", "x", "y"])
    out = out[
        out["model"].ne("")
        & out["glass_side"].ne("")
        & out["glass_id"].ne("")
        & out["pi_type"].isin(PI_TYPES)
        & out["defect_size"].isin(["S", "M", "L", "O"])
    ].copy()

    return out.reset_index(drop=True)


# =============================================================================
# Load RTMS AOI300
# =============================================================================
def load_rtms_raw_in_range(
    cfg: Config,
    db: MySQLDB,
    start_dt: datetime,
    end_dt: datetime,
    aoi_list: List[str],
    pi_type_filter: str,
) -> pd.DataFrame:
    if "aoi300" not in aoi_list:
        return pd.DataFrame()

    pi_type_filter = normalize_pi_type(pi_type_filter)
    if pi_type_filter not in PI_TYPES:
        raise ValueError("pi_type_filter must be API or BPI")

    months = iter_yyyymm_in_range(start_dt, end_dt)
    frames: List[pd.DataFrame] = []

    for ym in months:
        tbn = rtms_raw_table(cfg, ym)

        if not db.table_exists(tbn):
            logger.warning(f"[rtms_raw] missing {db.db}.{tbn}")
            continue

        sql = f"""
        SELECT *
        FROM `{db.db}`.`{tbn}`
        WHERE test_time >= :start_dt
          AND test_time <  :end_dt
          AND pi_type = :pi_type
        """

        part = db.query_df(sql, {
            "start_dt": start_dt,
            "end_dt": end_dt,
            "pi_type": pi_type_filter,
        })

        if part is None or part.empty:
            continue

        part["_source_table"] = tbn
        frames.append(part)

    if not frames:
        return pd.DataFrame()

    d = pd.concat(frames, ignore_index=True)

    d["defect_size_norm"] = d["defect_size"].apply(
        lambda v: normalize_defect_size(v, "aoi300")
    )
    d["defect_id_str"] = d["defect_id"].map(clean_text).str.upper()
    d["x_num"] = pd.to_numeric(d["pox_x1"], errors="coerce").fillna(0)
    d["y_num"] = pd.to_numeric(d["pox_y1"], errors="coerce").fillna(0)

    d = d[
        d["defect_size_norm"].isin(["S", "M", "L", "O"])
        & ~d["defect_id_str"].str.startswith("MACRO_", na=False)
        & d["defect_id_str"].ne("NO_DEFECT")
        & ~((d["x_num"] == 0) & (d["y_num"] == 0))
    ].copy()

    if d.empty:
        return pd.DataFrame()

    out = pd.DataFrame()
    out["model"] = d["model"].map(normalize_model)
    out["glass_side"] = d["glass_type"].map(normalize_glass_side)
    out["glass_id"] = d["sheet_id_chip_id"].map(clean_text)
    out["pi_type"] = d["pi_type"].map(normalize_pi_type)
    out["aoi"] = d["aoi"].map(lambda v: normalize_aoi(v, cfg))
    out["line_id"] = d["line_id"].map(normalize_line_id)
    out["recipe_id"] = d["recipe_id"].map(clean_text)
    out["cassette_id"] = d["cst_id"].map(clean_text)
    out["scan_time"] = pd.to_datetime(d["test_time"], errors="coerce")
    out["pi_time"] = pd.to_datetime(d["pi_time"], errors="coerce")
    out["scan_hour"] = derive_scan_hour(out["scan_time"])
    out["run_day"] = derive_run_day(out["scan_time"])

    out["x"] = pd.to_numeric(d["pox_x1"], errors="coerce")
    out["y"] = pd.to_numeric(d["pox_y1"], errors="coerce")
    out["defect_size"] = d["defect_size_norm"]
    out["adc_def_code"] = d["adc_def_code"].map(clean_text)
    out["retype_code"] = d["retype_def_code"].map(clean_text)
    out["chip_id"] = d["chip_id"].map(clean_text)
    out["defect_uid"] = "RTMS|" + d["id"].astype(str)

    out["pic_path"] = d["pic_path"].map(normalize_rtms_pic_path)
    out["pic_name"] = d["image_file_name"].map(clean_text)

    out["source_db"] = db.db
    out["source_table"] = d["_source_table"].map(clean_text)

    out = out.dropna(subset=["scan_time", "x", "y"])
    out = out[
        out["model"].ne("")
        & out["glass_side"].ne("")
        & out["glass_id"].ne("")
        & out["pi_type"].eq(pi_type_filter)
        & out["aoi"].eq("aoi300")
    ].copy()

    return out.reset_index(drop=True)


# =============================================================================
# API-driven load functions
# =============================================================================
def load_api_raw_in_range(
    cfg: Config,
    cim_db: MySQLDB,
    rtms_db: MySQLDB,
    start_dt: datetime,
    end_dt: datetime,
    aoi_list: List[str],
) -> pd.DataFrame:
    cim_summary_api = load_cim_summary_in_range(
        cfg=cfg,
        db=cim_db,
        start_dt=start_dt,
        end_dt=end_dt,
        aoi_list=aoi_list,
        pi_type_filter="API",
    )
    logger.info(f"[load API] cim_summary_api_rows={len(cim_summary_api)}")

    cim_api_raw = load_cim_defects_for_summary(cfg, cim_db, cim_summary_api)
    logger.info(f"[load API] cim_api_raw_rows={len(cim_api_raw)}")

    rtms_api_raw = load_rtms_raw_in_range(
        cfg=cfg,
        db=rtms_db,
        start_dt=start_dt,
        end_dt=end_dt,
        aoi_list=aoi_list,
        pi_type_filter="API",
    )
    logger.info(f"[load API] rtms_api_raw_rows={len(rtms_api_raw)}")

    frames = [x for x in [cim_api_raw, rtms_api_raw] if x is not None and not x.empty]
    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


def extract_api_glass_keys(api_raw_df: pd.DataFrame) -> pd.DataFrame:
    if api_raw_df is None or api_raw_df.empty:
        return pd.DataFrame(columns=["model", "glass_side", "glass_id"])

    return (
        api_raw_df[["model", "glass_side", "glass_id"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )


def filter_raw_by_api_keys(raw_df: pd.DataFrame, api_keys: pd.DataFrame) -> pd.DataFrame:
    if raw_df is None or raw_df.empty:
        return pd.DataFrame()

    if api_keys is None or api_keys.empty:
        return pd.DataFrame()

    keys = api_keys[["model", "glass_side", "glass_id"]].drop_duplicates().copy()

    out = raw_df.merge(
        keys,
        how="inner",
        on=["model", "glass_side", "glass_id"],
    )

    return out.reset_index(drop=True)


def load_bpi_raw_for_api_keys(
    cfg: Config,
    cim_db: MySQLDB,
    rtms_db: MySQLDB,
    api_keys: pd.DataFrame,
    bpi_start_dt: datetime,
    bpi_end_dt: datetime,
    aoi_list: List[str],
) -> pd.DataFrame:
    if api_keys is None or api_keys.empty:
        return pd.DataFrame()

    cim_summary_bpi = load_cim_summary_in_range(
        cfg=cfg,
        db=cim_db,
        start_dt=bpi_start_dt,
        end_dt=bpi_end_dt,
        aoi_list=aoi_list,
        pi_type_filter="BPI",
    )
    cim_summary_bpi = filter_raw_by_api_keys(cim_summary_bpi, api_keys)
    logger.info(f"[load BPI] cim_summary_bpi_after_key_filter={len(cim_summary_bpi)}")

    cim_bpi_raw = load_cim_defects_for_summary(cfg, cim_db, cim_summary_bpi)
    logger.info(f"[load BPI] cim_bpi_raw_rows={len(cim_bpi_raw)}")

    rtms_bpi_raw = load_rtms_raw_in_range(
        cfg=cfg,
        db=rtms_db,
        start_dt=bpi_start_dt,
        end_dt=bpi_end_dt,
        aoi_list=aoi_list,
        pi_type_filter="BPI",
    )
    rtms_bpi_raw = filter_raw_by_api_keys(rtms_bpi_raw, api_keys)
    logger.info(f"[load BPI] rtms_bpi_raw_after_key_filter={len(rtms_bpi_raw)}")

    frames = [x for x in [cim_bpi_raw, rtms_bpi_raw] if x is not None and not x.empty]
    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


# =============================================================================
# Meta / candidates
# =============================================================================
def derive_pair_tab_from_api(api_aoi: Any, api_recipe_id: Any) -> str:
    aoi = clean_text(api_aoi)
    h = recipe_head(api_recipe_id)

    if aoi == "aoi200":
        if h in {"0", "1"}:
            return "PISpot"
        if h in {"2", "3"}:
            return "UPI"
        return ""

    if aoi == "aoi100":
        return "aoi100"

    if aoi == "aoi300":
        return "aoi300"

    return aoi


def enrich_same_point_meta(raw_df: pd.DataFrame) -> pd.DataFrame:
    if raw_df is None or raw_df.empty:
        return pd.DataFrame()

    d = raw_df.copy()
    d["recipe_head"] = d["recipe_id"].map(recipe_head)
    d["pair_tab"] = d.apply(
        lambda r: derive_pair_tab_from_api(r.get("aoi", ""), r.get("recipe_id", ""))
        if normalize_pi_type(r.get("pi_type", "")) == "API"
        else "",
        axis=1,
    )
    return d.reset_index(drop=True)


def aggregate_defect_events(d: pd.DataFrame, group_cols: List[str]) -> pd.DataFrame:
    if d is None or d.empty:
        return pd.DataFrame()

    agg = (
        d.groupby(group_cols, dropna=False, as_index=False)
        .agg(
            line_id=("line_id", "first"),
            cassette_id=("cassette_id", "first"),
            pi_time=("pi_time", "first"),
            scan_hour=("scan_hour", "first"),
            run_day=("run_day", "first"),
            source_db=("source_db", "first"),
            source_table=("source_table", "first"),
            defect_count=("defect_uid", "nunique"),
            small_defect_count=("defect_size", lambda s: int((s == "S").sum())),
            middle_defect_count=("defect_size", lambda s: int((s == "M").sum())),
            large_defect_count=("defect_size", lambda s: int((s == "L").sum())),
            over_defect_count=("defect_size", lambda s: int((s == "O").sum())),
        )
    )

    agg["scan_time"] = pd.to_datetime(agg["scan_time"], errors="coerce")
    return agg.reset_index(drop=True)


def build_api_candidates(api_raw_df: pd.DataFrame) -> pd.DataFrame:
    if api_raw_df is None or api_raw_df.empty:
        return pd.DataFrame()

    d = api_raw_df.copy()
    d["scan_time"] = pd.to_datetime(d["scan_time"], errors="coerce")
    d["recipe_head"] = d["recipe_id"].map(recipe_head)
    d["tab"] = d.apply(lambda r: derive_pair_tab_from_api(r.get("aoi", ""), r.get("recipe_id", "")), axis=1)

    d = d[d["pi_type"].eq("API")].copy()

    # AOI200 API 僅接受 recipe 0/1/2/3。
    d = d[
        ~d["aoi"].eq("aoi200")
        | d["recipe_head"].isin(["0", "1", "2", "3"])
    ].copy()

    d = d[d["tab"].ne("")].copy()

    group_cols = [
        "model",
        "glass_side",
        "glass_id",
        "pi_type",
        "aoi",
        "recipe_id",
        "recipe_head",
        "tab",
        "scan_time",
    ]

    agg = aggregate_defect_events(d, group_cols)
    if agg.empty:
        return pd.DataFrame()

    latest_key = [
        "model",
        "glass_side",
        "glass_id",
        "aoi",
        "recipe_id",
    ]

    agg = agg.sort_values(latest_key + ["scan_time"])
    latest = agg.drop_duplicates(latest_key, keep="last")

    return latest.reset_index(drop=True)


def build_bpi_candidates_pool(bpi_raw_df: pd.DataFrame) -> pd.DataFrame:
    if bpi_raw_df is None or bpi_raw_df.empty:
        return pd.DataFrame()

    d = bpi_raw_df.copy()
    d["scan_time"] = pd.to_datetime(d["scan_time"], errors="coerce")
    d["recipe_head"] = d["recipe_id"].map(recipe_head)
    d = d[d["pi_type"].eq("BPI")].copy()

    # AOI200 BPI 僅接受 recipe 4/5；其他 AOI 不額外卡 recipe。
    d = d[
        ~d["aoi"].eq("aoi200")
        | d["recipe_head"].isin(["4", "5"])
    ].copy()

    group_cols = [
        "model",
        "glass_side",
        "glass_id",
        "pi_type",
        "aoi",
        "recipe_id",
        "recipe_head",
        "scan_time",
    ]

    agg = aggregate_defect_events(d, group_cols)
    if agg.empty:
        return pd.DataFrame()

    return agg.reset_index(drop=True)


def filter_bpi_candidates_for_api(api_row: pd.Series, bpi_df: pd.DataFrame) -> pd.DataFrame:
    if bpi_df is None or bpi_df.empty:
        return pd.DataFrame()

    ar_aoi = clean_text(api_row.get("aoi", ""))
    ar_head = recipe_head(api_row.get("recipe_id", ""))

    if ar_aoi != "aoi200":
        return bpi_df.copy()

    out = bpi_df.copy()

    # 只有 BPI 也是 AOI200 時才套 4/5 對應規則。
    mask_non_aoi200_bpi = ~out["aoi"].eq("aoi200")

    if ar_head in {"0", "2"}:
        mask_aoi200_bpi = out["aoi"].eq("aoi200") & out["recipe_head"].eq("4")
        return out[mask_non_aoi200_bpi | mask_aoi200_bpi].copy()

    if ar_head in {"1", "3"}:
        mask_aoi200_bpi = out["aoi"].eq("aoi200") & out["recipe_head"].eq("5")
        return out[mask_non_aoi200_bpi | mask_aoi200_bpi].copy()

    return pd.DataFrame()


def build_pair_row_from_candidates(
    *,
    br: pd.Series,
    ar: pd.Series,
    model: str,
    side: str,
    gid: str,
    tab: str,
    default_offset_um: int,
) -> Dict[str, Any]:
    api_scan_time = ar["scan_time"]
    pair_scan_hour = derive_scan_hour_one(api_scan_time)
    pair_run_day = derive_run_day_one(api_scan_time)

    return {
        "model": model,
        "glass_side": side,
        "glass_id": gid,
        "scan_hour": pair_scan_hour,
        "run_day": pair_run_day,
        "tab": tab,

        "bpi_aoi": br["aoi"],
        "bpi_line_id": br.get("line_id", ""),
        "bpi_recipe_id": br.get("recipe_id", ""),
        "bpi_cassette_id": br.get("cassette_id", ""),
        "bpi_scan_time": br["scan_time"],
        "bpi_pi_time": br.get("pi_time", None),
        "bpi_scan_hour": br.get("scan_hour", None),
        "bpi_run_day": br.get("run_day", None),
        "bpi_source_db": br.get("source_db", ""),
        "bpi_source_table": br.get("source_table", ""),

        "api_aoi": ar["aoi"],
        "api_line_id": ar.get("line_id", ""),
        "api_recipe_id": ar.get("recipe_id", ""),
        "api_cassette_id": ar.get("cassette_id", ""),
        "api_scan_time": ar["scan_time"],
        "api_pi_time": ar.get("pi_time", None),
        "api_scan_hour": ar.get("scan_hour", None),
        "api_run_day": ar.get("run_day", None),
        "api_source_db": ar.get("source_db", ""),
        "api_source_table": ar.get("source_table", ""),

        "bpi_defect_count": int(br.get("defect_count", 0) or 0),
        "api_defect_count": int(ar.get("defect_count", 0) or 0),

        "bpi_small_defect_count": int(br.get("small_defect_count", 0) or 0),
        "bpi_middle_defect_count": int(br.get("middle_defect_count", 0) or 0),
        "bpi_large_defect_count": int(br.get("large_defect_count", 0) or 0),
        "bpi_over_defect_count": int(br.get("over_defect_count", 0) or 0),

        "api_small_defect_count": int(ar.get("small_defect_count", 0) or 0),
        "api_middle_defect_count": int(ar.get("middle_defect_count", 0) or 0),
        "api_large_defect_count": int(ar.get("large_defect_count", 0) or 0),
        "api_over_defect_count": int(ar.get("over_defect_count", 0) or 0),

        "pair_status": "OK",
        "pair_message": "",
        "default_offset_um": int(default_offset_um),
        "matched_points_json": "",

        "comment": "",
        "action": "",
        "editor": "",
        "modify_time": None,
        "gen_time": datetime.now(),
    }


def build_pair_df_api_driven(
    api_candidates: pd.DataFrame,
    bpi_pool: pd.DataFrame,
    default_offset_um: int,
) -> pd.DataFrame:
    if api_candidates is None or api_candidates.empty:
        return pd.DataFrame(columns=PAIR_OUT_COLS)

    if bpi_pool is None or bpi_pool.empty:
        return pd.DataFrame(columns=PAIR_OUT_COLS)

    api = api_candidates.copy()
    bpi = bpi_pool.copy()

    api["scan_time"] = pd.to_datetime(api["scan_time"], errors="coerce")
    bpi["scan_time"] = pd.to_datetime(bpi["scan_time"], errors="coerce")

    rows: List[Dict[str, Any]] = []

    for _, ar in api.iterrows():
        model = clean_text(ar.get("model", ""))
        side = clean_text(ar.get("glass_side", ""))
        gid = clean_text(ar.get("glass_id", ""))
        tab = clean_text(ar.get("tab", ""))

        if not model or not side or not gid or not tab:
            continue

        api_scan_time = pd.to_datetime(ar.get("scan_time"), errors="coerce")
        if pd.isna(api_scan_time):
            continue

        bpi_g = bpi[
            (bpi["model"] == model)
            & (bpi["glass_side"] == side)
            & (bpi["glass_id"] == gid)
            & (pd.to_datetime(bpi["scan_time"], errors="coerce") <= api_scan_time)
        ].copy()

        if bpi_g.empty:
            continue

        bpi_g = filter_bpi_candidates_for_api(ar, bpi_g)

        if bpi_g.empty:
            continue

        # 選項 A：每筆 API 只取 API 前最近一筆 BPI。
        bpi_g["scan_time"] = pd.to_datetime(bpi_g["scan_time"], errors="coerce")
        bpi_g = bpi_g.sort_values(
            ["scan_time", "aoi", "recipe_id"],
            ascending=[True, True, True],
        )
        br = bpi_g.iloc[-1]

        rows.append(build_pair_row_from_candidates(
            br=br,
            ar=ar,
            model=model,
            side=side,
            gid=gid,
            tab=tab,
            default_offset_um=default_offset_um,
        ))

    if not rows:
        return pd.DataFrame(columns=PAIR_OUT_COLS)

    return pd.DataFrame(rows, columns=PAIR_OUT_COLS)


# =============================================================================
# Pair and matching
# =============================================================================
def subset_raw_for_pair(
    raw_df: pd.DataFrame,
    pair_row: pd.Series,
    pi_type: str,
) -> pd.DataFrame:
    if raw_df is None or raw_df.empty:
        return pd.DataFrame()

    if pi_type == "BPI":
        aoi = pair_row["bpi_aoi"]
        st = pd.to_datetime(pair_row["bpi_scan_time"], errors="coerce")
        recipe_id = clean_text(pair_row.get("bpi_recipe_id", ""))
    else:
        aoi = pair_row["api_aoi"]
        st = pd.to_datetime(pair_row["api_scan_time"], errors="coerce")
        recipe_id = clean_text(pair_row.get("api_recipe_id", ""))

    d = raw_df[
        (raw_df["model"] == pair_row["model"])
        & (raw_df["glass_side"] == pair_row["glass_side"])
        & (raw_df["glass_id"] == pair_row["glass_id"])
        & (raw_df["pi_type"] == pi_type)
        & (raw_df["aoi"] == aoi)
        & (pd.to_datetime(raw_df["scan_time"], errors="coerce") == st)
    ].copy()

    # AOI200 需要卡 recipe_id，避免同片同 scan_time 不同 recipe 混入。
    if clean_text(aoi) == "aoi200" and recipe_id:
        d = d[d["recipe_id"].map(clean_text).eq(recipe_id)].copy()

    return d.reset_index(drop=True)


def nearest_one_to_one_match(
    bpi_df: pd.DataFrame,
    api_df: pd.DataFrame,
    offset_um: int,
) -> List[Dict[str, Any]]:
    if bpi_df is None or bpi_df.empty or api_df is None or api_df.empty:
        return []

    candidates: List[Tuple[float, float, float, int, int]] = []

    bpi = bpi_df.reset_index(drop=True)
    api = api_df.reset_index(drop=True)

    for bi, br in bpi.iterrows():
        bx = safe_float(br["x"])
        by = safe_float(br["y"])

        for ai, ar in api.iterrows():
            ax = safe_float(ar["x"])
            ay = safe_float(ar["y"])

            dx = bx - ax
            dy = by - ay
            dist = math.sqrt(dx * dx + dy * dy)

            if dist <= float(offset_um):
                candidates.append((dist, dx, dy, bi, ai))

    candidates.sort(key=lambda x: x[0])

    used_bpi = set()
    used_api = set()
    matches: List[Dict[str, Any]] = []

    rank = 1

    for dist, dx, dy, bi, ai in candidates:
        if bi in used_bpi or ai in used_api:
            continue

        used_bpi.add(bi)
        used_api.add(ai)

        matches.append({
            "distance": float(dist),
            "dx": float(dx),
            "dy": float(dy),
            "bpi_idx": bi,
            "api_idx": ai,
            "match_rank": rank,
        })

        rank += 1

    return matches


def make_matched_point_json_item(
    *,
    pr: pd.Series,
    br: pd.Series,
    ar: pd.Series,
    m: Dict[str, Any],
    offset_um: int,
) -> Dict[str, Any]:
    return {
        "offset_um": int(offset_um),
        "distance": float(m["distance"]),
        "dx": float(m["dx"]),
        "dy": float(m["dy"]),
        "match_rank": int(m["match_rank"]),

        "bpi_defect_uid": clean_text(br.get("defect_uid", "")),
        "bpi_chip_id": clean_text(br.get("chip_id", "")),
        "bpi_x": float(br.get("x", 0) or 0),
        "bpi_y": float(br.get("y", 0) or 0),
        "bpi_defect_size": clean_text(br.get("defect_size", "")),
        "bpi_adc_def_code": clean_text(br.get("adc_def_code", "")),
        "bpi_retype_code": clean_text(br.get("retype_code", "")),
        "bpi_pic_path": clean_text(br.get("pic_path", "")),
        "bpi_pic_name": clean_text(br.get("pic_name", "")),

        "api_defect_uid": clean_text(ar.get("defect_uid", "")),
        "api_chip_id": clean_text(ar.get("chip_id", "")),
        "api_x": float(ar.get("x", 0) or 0),
        "api_y": float(ar.get("y", 0) or 0),
        "api_defect_size": clean_text(ar.get("defect_size", "")),
        "api_adc_def_code": clean_text(ar.get("adc_def_code", "")),
        "api_retype_code": clean_text(ar.get("retype_code", "")),
        "api_pic_path": clean_text(ar.get("pic_path", "")),
        "api_pic_name": clean_text(ar.get("pic_name", "")),
    }


def build_offset_and_match_detail(
    pair_df: pd.DataFrame,
    raw_df: pd.DataFrame,
    offsets_um: List[int],
    match_method: str = "nearest_one_to_one",
    default_offset_um: int = 20,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if pair_df is None or pair_df.empty:
        return (
            pd.DataFrame(columns=PAIR_OUT_COLS),
            pd.DataFrame(columns=OFFSET_OUT_COLS),
            pd.DataFrame(columns=MATCH_OUT_COLS),
        )

    pair_rows: List[Dict[str, Any]] = []
    offset_rows: List[Dict[str, Any]] = []
    match_rows: List[Dict[str, Any]] = []

    for _, pr in pair_df.iterrows():
        bpi_raw = subset_raw_for_pair(raw_df, pr, "BPI")
        api_raw = subset_raw_for_pair(raw_df, pr, "API")

        bpi_cnt = len(bpi_raw)
        api_cnt = len(api_raw)

        default_points: List[Dict[str, Any]] = []

        for offset_um in offsets_um:
            matches = nearest_one_to_one_match(bpi_raw, api_raw, int(offset_um))

            matched_pair_count = len(matches)
            matched_bpi = matched_pair_count
            matched_api = matched_pair_count

            unmatched_bpi = max(0, bpi_cnt - matched_bpi)
            unmatched_api = max(0, api_cnt - matched_api)

            bpi_size_counts = {"S": 0, "M": 0, "L": 0, "O": 0}
            api_size_counts = {"S": 0, "M": 0, "L": 0, "O": 0}
            transition_counts: Dict[str, int] = {}

            for m in matches:
                br = bpi_raw.iloc[m["bpi_idx"]]
                ar = api_raw.iloc[m["api_idx"]]

                bpi_sz = normalize_defect_size(br.get("defect_size"), br.get("aoi", pr.get("bpi_aoi", "")))
                api_sz = normalize_defect_size(ar.get("defect_size"), ar.get("aoi", pr.get("api_aoi", "")))

                if bpi_sz in bpi_size_counts:
                    bpi_size_counts[bpi_sz] += 1

                if api_sz in api_size_counts:
                    api_size_counts[api_sz] += 1

                if bpi_sz and api_sz:
                    k = f"{bpi_sz}->{api_sz}"
                    transition_counts[k] = transition_counts.get(k, 0) + 1

                point_item = make_matched_point_json_item(
                    pr=pr,
                    br=br,
                    ar=ar,
                    m=m,
                    offset_um=int(offset_um),
                )

                if int(offset_um) == int(default_offset_um):
                    default_points.append(point_item)

                match_rows.append({
                    "model": pr["model"],
                    "glass_side": pr["glass_side"],
                    "glass_id": pr["glass_id"],

                    "scan_hour": pr.get("scan_hour", None),
                    "run_day": pr.get("run_day", None),
                    "tab": pr.get("tab", ""),

                    "bpi_aoi": pr["bpi_aoi"],
                    "bpi_line_id": pr.get("bpi_line_id", ""),
                    "bpi_recipe_id": pr.get("bpi_recipe_id", ""),
                    "bpi_scan_time": pr["bpi_scan_time"],

                    "api_aoi": pr["api_aoi"],
                    "api_line_id": pr.get("api_line_id", ""),
                    "api_recipe_id": pr.get("api_recipe_id", ""),
                    "api_scan_time": pr["api_scan_time"],

                    "offset_um": int(offset_um),

                    "bpi_defect_uid": br.get("defect_uid", ""),
                    "bpi_chip_id": br.get("chip_id", ""),
                    "bpi_x": float(br.get("x", 0) or 0),
                    "bpi_y": float(br.get("y", 0) or 0),
                    "bpi_defect_size": br.get("defect_size", ""),
                    "bpi_adc_def_code": br.get("adc_def_code", ""),
                    "bpi_retype_code": br.get("retype_code", ""),
                    "bpi_pic_path": br.get("pic_path", ""),
                    "bpi_pic_name": br.get("pic_name", ""),

                    "api_defect_uid": ar.get("defect_uid", ""),
                    "api_chip_id": ar.get("chip_id", ""),
                    "api_x": float(ar.get("x", 0) or 0),
                    "api_y": float(ar.get("y", 0) or 0),
                    "api_defect_size": ar.get("defect_size", ""),
                    "api_adc_def_code": ar.get("adc_def_code", ""),
                    "api_retype_code": ar.get("retype_code", ""),
                    "api_pic_path": ar.get("pic_path", ""),
                    "api_pic_name": ar.get("pic_name", ""),

                    "dx": float(m["dx"]),
                    "dy": float(m["dy"]),
                    "distance": float(m["distance"]),
                    "match_rank": int(m["match_rank"]),
                    "match_method": match_method,
                    "gen_time": datetime.now(),
                })

            offset_rows.append({
                "model": pr["model"],
                "glass_side": pr["glass_side"],
                "glass_id": pr["glass_id"],

                "scan_hour": pr.get("scan_hour", None),
                "run_day": pr.get("run_day", None),
                "tab": pr.get("tab", ""),

                "bpi_aoi": pr["bpi_aoi"],
                "bpi_scan_time": pr["bpi_scan_time"],
                "bpi_recipe_id": pr.get("bpi_recipe_id", ""),

                "api_aoi": pr["api_aoi"],
                "api_scan_time": pr["api_scan_time"],
                "api_recipe_id": pr.get("api_recipe_id", ""),

                "offset_um": int(offset_um),

                "bpi_defect_count": int(bpi_cnt),
                "api_defect_count": int(api_cnt),
                "matched_pair_count": int(matched_pair_count),
                "matched_bpi_defect_count": int(matched_bpi),
                "matched_api_defect_count": int(matched_api),
                "unmatched_bpi_defect_count": int(unmatched_bpi),
                "unmatched_api_defect_count": int(unmatched_api),

                "matched_bpi_s_count": int(bpi_size_counts["S"]),
                "matched_bpi_m_count": int(bpi_size_counts["M"]),
                "matched_bpi_l_count": int(bpi_size_counts["L"]),
                "matched_bpi_o_count": int(bpi_size_counts["O"]),

                "matched_api_s_count": int(api_size_counts["S"]),
                "matched_api_m_count": int(api_size_counts["M"]),
                "matched_api_l_count": int(api_size_counts["L"]),
                "matched_api_o_count": int(api_size_counts["O"]),

                "matched_size_transition_json": json.dumps(transition_counts, ensure_ascii=False),

                "gen_time": datetime.now(),
            })

        pr2 = pr.to_dict()
        pr2["bpi_defect_count"] = int(bpi_cnt)
        pr2["api_defect_count"] = int(api_cnt)

        if bpi_cnt == 0 and api_cnt == 0:
            pr2["pair_status"] = "NO_BOTH_DEFECT"
        elif bpi_cnt == 0:
            pr2["pair_status"] = "NO_BPI_DEFECT"
        elif api_cnt == 0:
            pr2["pair_status"] = "NO_API_DEFECT"
        else:
            pr2["pair_status"] = "OK"

        pr2["default_offset_um"] = int(default_offset_um)
        pr2["matched_points_json"] = json.dumps(default_points, ensure_ascii=False)
        pair_rows.append(pr2)

    return (
        pd.DataFrame(pair_rows, columns=PAIR_OUT_COLS),
        pd.DataFrame(offset_rows, columns=OFFSET_OUT_COLS),
        pd.DataFrame(match_rows, columns=MATCH_OUT_COLS),
    )


# =============================================================================
# Write orchestration
# =============================================================================
def write_outputs_by_affected_keys(
    cfg: Config,
    out_db: MySQLDB,
    pair_out: pd.DataFrame,
    offset_out: pd.DataFrame,
    match_out: pd.DataFrame,
):
    if pair_out is None or pair_out.empty:
        logger.info("[write] pair_out empty, skip writing")
        return

    affected_keys = (
        pair_out[AFFECTED_KEY_COLS]
        .fillna("")
        .astype(str)
        .drop_duplicates()
        .reset_index(drop=True)
    )

    if affected_keys.empty:
        logger.info("[write] affected_keys empty, skip writing")
        return

    # 1. 確保本次新資料月份表存在。
    for ym in set(split_by_month(pair_out, "scan_hour").keys()):
        ensure_pair_out_table(out_db, out_table(cfg.pair_out_tpl, ym))
    for ym in set(split_by_month(offset_out, "scan_hour").keys()):
        ensure_offset_out_table(out_db, out_table(cfg.offset_out_tpl, ym))
    if cfg.write_match_detail:
        for ym in set(split_by_month(match_out, "scan_hour").keys()):
            ensure_match_out_table(out_db, out_table(cfg.match_out_tpl, ym))

    # 2. 讀歷史 pair manual。
    pair_tables = list_month_tables(out_db, cfg.pair_out_tpl)
    old_manual = load_existing_manual_by_keys(
        out_db,
        pair_tables,
        affected_keys,
        AFFECTED_KEY_COLS,
        batch_size=cfg.delete_key_batch_size,
    )

    pair_out = preserve_pair_manual_fields_by_recipe(pair_out, old_manual)

    # 3. 依 affected keys 刪除歷史 pair / offset / match。
    pair_tables = list_month_tables(out_db, cfg.pair_out_tpl)
    offset_tables = list_month_tables(out_db, cfg.offset_out_tpl)
    match_tables = list_month_tables(out_db, cfg.match_out_tpl)

    for tbn in pair_tables:
        delete_by_affected_keys(
            out_db,
            tbn,
            affected_keys,
            AFFECTED_KEY_COLS,
            batch_size=cfg.delete_key_batch_size,
        )

    for tbn in offset_tables:
        delete_by_affected_keys(
            out_db,
            tbn,
            affected_keys,
            AFFECTED_KEY_COLS,
            batch_size=cfg.delete_key_batch_size,
        )

    if cfg.write_match_detail:
        for tbn in match_tables:
            delete_by_affected_keys(
                out_db,
                tbn,
                affected_keys,
                AFFECTED_KEY_COLS,
                batch_size=cfg.delete_key_batch_size,
            )

    # 4. 依 scan_hour 分月寫入新資料。
    for ym, part in split_by_month(pair_out, "scan_hour").items():
        tbn = out_table(cfg.pair_out_tpl, ym)
        append_df(
            out_db,
            tbn,
            part,
            PAIR_OUT_COLS,
            ensure_fn=ensure_pair_out_table,
        )

    for ym, part in split_by_month(offset_out, "scan_hour").items():
        tbn = out_table(cfg.offset_out_tpl, ym)
        append_df(
            out_db,
            tbn,
            part,
            OFFSET_OUT_COLS,
            ensure_fn=ensure_offset_out_table,
        )

    if cfg.write_match_detail:
        for ym, part in split_by_month(match_out, "scan_hour").items():
            tbn = out_table(cfg.match_out_tpl, ym)
            append_df(
                out_db,
                tbn,
                part,
                MATCH_OUT_COLS,
                ensure_fn=ensure_match_out_table,
            )


# =============================================================================
# Run core
# =============================================================================
def run_once_for_range(
    cfg: Config,
    start_dt: datetime,
    end_dt: datetime,
    aoi_list: List[str],
    offsets_um: List[int],
) -> Dict[str, pd.DataFrame]:
    logger.info(
        f"[run] API-driven start={start_dt}, end={end_dt}, "
        f"aoi_list={aoi_list}, offsets={offsets_um}, "
        f"default_offset_um={cfg.default_offset_um}, "
        f"bpi_lookback_days={cfg.bpi_lookback_days}"
    )

    cim_db = MySQLDB(cfg.cim_db, cfg)
    rtms_db = MySQLDB(cfg.rtms_db, cfg)
    out_db = MySQLDB(cfg.out_db, cfg)

    if not offsets_um:
        offsets_um = list(cfg.offsets_um)

    offsets_um = sorted(set([int(x) for x in offsets_um if int(x) > 0]))

    if not offsets_um:
        offsets_um = [20]

    default_offset_um = int(cfg.default_offset_um)
    if default_offset_um not in offsets_um:
        logger.warning(
            f"[run] default_offset_um={default_offset_um} not in offsets={offsets_um}; "
            f"use first offset={offsets_um[0]} as default"
        )
        default_offset_um = int(offsets_um[0])

    # 1. API raw。
    api_raw_df = load_api_raw_in_range(
        cfg=cfg,
        cim_db=cim_db,
        rtms_db=rtms_db,
        start_dt=start_dt,
        end_dt=end_dt,
        aoi_list=aoi_list,
    )
    logger.info(f"[load] api_raw_rows={len(api_raw_df)}")

    if api_raw_df is None or api_raw_df.empty:
        logger.warning("[run] no API raw defect rows")
        return {
            "pair": pd.DataFrame(columns=PAIR_OUT_COLS),
            "offset": pd.DataFrame(columns=OFFSET_OUT_COLS),
            "match": pd.DataFrame(columns=MATCH_OUT_COLS),
        }

    api_keys = extract_api_glass_keys(api_raw_df)
    logger.info(f"[build] api_glass_keys={len(api_keys)}")

    # 2. BPI raw backward lookup。
    bpi_start_dt = start_dt - timedelta(days=int(cfg.bpi_lookback_days))
    bpi_end_dt = end_dt

    bpi_raw_df = load_bpi_raw_for_api_keys(
        cfg=cfg,
        cim_db=cim_db,
        rtms_db=rtms_db,
        api_keys=api_keys,
        bpi_start_dt=bpi_start_dt,
        bpi_end_dt=bpi_end_dt,
        aoi_list=aoi_list,
    )
    logger.info(f"[load] bpi_raw_rows={len(bpi_raw_df)}")

    if bpi_raw_df is None or bpi_raw_df.empty:
        logger.warning("[run] no BPI raw defect rows for API keys")
        return {
            "pair": pd.DataFrame(columns=PAIR_OUT_COLS),
            "offset": pd.DataFrame(columns=OFFSET_OUT_COLS),
            "match": pd.DataFrame(columns=MATCH_OUT_COLS),
        }

    # 3. meta。
    api_raw_df = enrich_same_point_meta(api_raw_df)
    bpi_raw_df = enrich_same_point_meta(bpi_raw_df)

    # 4. candidates。
    api_candidates = build_api_candidates(api_raw_df)
    logger.info(f"[build] api_candidates={len(api_candidates)}")

    bpi_pool = build_bpi_candidates_pool(bpi_raw_df)
    logger.info(f"[build] bpi_pool={len(bpi_pool)}")

    if api_candidates.empty or bpi_pool.empty:
        logger.warning("[run] no valid candidates")
        return {
            "pair": pd.DataFrame(columns=PAIR_OUT_COLS),
            "offset": pd.DataFrame(columns=OFFSET_OUT_COLS),
            "match": pd.DataFrame(columns=MATCH_OUT_COLS),
        }

    # 5. pair。
    pair_df = build_pair_df_api_driven(
        api_candidates=api_candidates,
        bpi_pool=bpi_pool,
        default_offset_um=default_offset_um,
    )
    logger.info(f"[build] pair_rows={len(pair_df)}")

    if pair_df.empty:
        logger.warning("[run] no pair rows")
        return {
            "pair": pd.DataFrame(columns=PAIR_OUT_COLS),
            "offset": pd.DataFrame(columns=OFFSET_OUT_COLS),
            "match": pd.DataFrame(columns=MATCH_OUT_COLS),
        }

    # 6. matching。
    raw_df = pd.concat([api_raw_df, bpi_raw_df], ignore_index=True)

    pair_out, offset_out, match_out = build_offset_and_match_detail(
        pair_df=pair_df,
        raw_df=raw_df,
        offsets_um=offsets_um,
        match_method=cfg.match_method,
        default_offset_um=default_offset_um,
    )

    logger.info(
        f"[build] final pair={len(pair_out)}, "
        f"offset={len(offset_out)}, match={len(match_out)}"
    )

    if cfg.write_out:
        write_outputs_by_affected_keys(
            cfg=cfg,
            out_db=out_db,
            pair_out=pair_out,
            offset_out=offset_out,
            match_out=match_out,
        )
    else:
        logger.info("[run] write_out disabled")

    return {
        "pair": pair_out,
        "offset": offset_out,
        "match": match_out,
    }


# =============================================================================
# CLI
# =============================================================================
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build BPI/API same-point pair data")

    p.add_argument("--mode", choices=["loop", "month", "days", "date", "range"], default="loop")
    p.add_argument("--month", default="", help="YYYYMM")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--date", default="", help="YYYY-MM-DD")
    p.add_argument("--start", default="")
    p.add_argument("--end", default="")

    p.add_argument("--host", default="10.97.142.217")
    p.add_argument("--username", default="l6a01_user")
    p.add_argument("--password", default="l6a01$user")

    p.add_argument("--cim-db", default="cim_piaoi")
    p.add_argument("--rtms-db", default="rtms_piaoi_other")
    p.add_argument("--out-db", default="piaoi_bpi_same_point")

    p.add_argument("--loop-minutes", type=int, default=10)
    p.add_argument("--lookback-minutes", type=int, default=180)
    p.add_argument("--bpi-lookback-days", type=int, default=30)

    p.add_argument("--aoi-list", default="aoi100,aoi200,aoi300")
    p.add_argument("--offsets", default="5,10,15,20,25,30,35,40,45,50")
    p.add_argument("--default-offset-um", type=int, default=20)
    p.add_argument("--match-method", choices=["nearest_one_to_one"], default="nearest_one_to_one")

    p.add_argument("--write-out", action="store_true")
    p.add_argument("--no-match-detail", action="store_true")

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

    offsets_um = parse_int_csv(args.offsets)
    if not offsets_um:
        offsets_um = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]

    cfg = Config(
        host=args.host,
        username=args.username,
        password=args.password,
        cim_db=args.cim_db,
        rtms_db=args.rtms_db,
        out_db=args.out_db,
        loop_minutes=args.loop_minutes,
        lookback_minutes=args.lookback_minutes,
        bpi_lookback_days=args.bpi_lookback_days,
        offsets_um=tuple(offsets_um),
        default_offset_um=args.default_offset_um,
        match_method=args.match_method,
        write_out=bool(args.write_out),
        write_match_detail=not bool(args.no_match_detail),
    )

    logger.info(
        f"[start] mode={args.mode}, cim_db={cfg.cim_db}, rtms_db={cfg.rtms_db}, "
        f"out_db={cfg.out_db}, aoi_list={aoi_list}, offsets={offsets_um}, "
        f"default_offset_um={cfg.default_offset_um}, "
        f"bpi_lookback_days={cfg.bpi_lookback_days}, "
        f"write_out={cfg.write_out}, write_match_detail={cfg.write_match_detail}"
    )

    if args.mode == "loop":
        while True:
            start_dt, end_dt = resolve_window(
                "loop",
                lookback_minutes=cfg.lookback_minutes,
            )

            try:
                run_once_for_range(
                    cfg=cfg,
                    start_dt=start_dt,
                    end_dt=end_dt,
                    aoi_list=aoi_list,
                    offsets_um=offsets_um,
                )
            except Exception as e:
                logger.exception(f"[loop] failed: {e}")

            time.sleep(cfg.loop_minutes * 60)

    else:
        start_dt, end_dt = resolve_window(
            args.mode,
            month=args.month,
            days=args.days,
            date_str=args.date,
            start_str=args.start,
            end_str=args.end,
            lookback_minutes=cfg.lookback_minutes,
        )

        run_once_for_range(
            cfg=cfg,
            start_dt=start_dt,
            end_dt=end_dt,
            aoi_list=aoi_list,
            offsets_um=offsets_um,
        )


if __name__ == "__main__":
    main()


"""
Examples:

python build_bpi_same_point_job.py --mode date --date 2026-05-01 --write-out

python build_bpi_same_point_job.py --mode month --month 202606 --write-out

python build_bpi_same_point_job.py --mode days --days 3 --write-out

python build_bpi_same_point_job.py --mode range --start "2026-06-21 00:00:00" --end "2026-06-21 00:00:00" --write-out

python build_bpi_same_point_job.py --mode date --date 2026-05-01 --aoi-list aoi100,aoi200 --write-out

python build_bpi_same_point_job.py --mode date --date 2026-05-01 --aoi-list aoi300 --write-out

python build_bpi_same_point_job.py --mode date --date 2026-05-01 --write-out --no-match-detail

python build_bpi_same_point_job.py --mode date --date 2026-05-01 --offsets 5,10,20,50 --default-offset-um 20 --write-out

python build_bpi_same_point_job.py --mode loop --write-out --lookback-minutes 180 --bpi-lookback-days 30 --loop-minutes 10
"""