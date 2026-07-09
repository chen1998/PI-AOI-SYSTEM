# -*- coding: utf-8 -*-
"""
RUN_CELL_INCOMING_GOVERNANCE_V5.py

CELL 來料檢資料治理工程 V3

讀取：
    MySQL cim_piaoi
        - cim_pi_glass_yyyymm
        - cim_defect_yyyymm_aoi_line

寫入：
    MySQL cim_cell_aoi_to_array
        - incoming_source_cf_oc_defect_raw_yyyymm
        - incoming_source_cf_ps_defect_raw_yyyymm
        - incoming_source_array_mor_defect_raw_yyyymm
        - incoming_source_array_tar_defect_raw_yyyymm
        - incoming_source_array_tos_defect_raw_yyyymm
        - incoming_same_point_detail_yyyymm
        - incoming_glass_summary_yyyymm
        - api_aoi_summary_yyyymm
        - incoming_governance_state

使用：
    python RUN_CELL_INCOMING_GOVERNANCE_V5.py --once --start-time "2026-07-06 08:00:00" --end-time "2026-07-06 12:00:00"

    python RUN_CELL_INCOMING_GOVERNANCE_V5.py --once --lookback-hour 6

    python RUN_CELL_INCOMING_GOVERNANCE_V5.py --every-min 10 --lookback-hour 6
"""

from __future__ import annotations

import os
import re
import sys
import time
import json
import argparse
import logging
from logging.handlers import TimedRotatingFileHandler
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple, Iterable

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker, scoped_session

from sql_db_connect import MySQLConnet


# =============================================================================
# Logging
# =============================================================================

def setup_logging(
    log_dir: str = "logs",
    log_name: str = "cell_incoming_governance_V5.txt",
) -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, log_name)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    if logger.handlers:
        for h in list(logger.handlers):
            logger.removeHandler(h)

    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    fh = TimedRotatingFileHandler(
        filename=log_path,
        when="midnight",
        interval=1,
        backupCount=92,
        encoding="utf-8",
        utc=False,
    )
    fh.suffix = "%Y-%m-%d"
    fh.setFormatter(fmt)
    fh.setLevel(logging.INFO)

    sh = logging.StreamHandler(stream=sys.stdout)
    sh.setFormatter(fmt)
    sh.setLevel(logging.INFO)

    logger.addHandler(fh)
    logger.addHandler(sh)

    return logger


# =============================================================================
# Config
# =============================================================================

@dataclass
class OracleConfig:
    user_name: str = "L6AINT_AP"
    passwd: str = "L6AINT$AP"
    host: str = "TCPPA104"

    cf_port: str = "1547"
    cf_service_name: str = "C6AHSHA"

    array_port: str = "1549"
    array_service_name: str = "L6AHSHA"

    @property
    def cf_url(self) -> str:
        return (
            f"oracle+cx_oracle://{self.user_name}:{self.passwd}"
            f"@{self.host}:{self.cf_port}/?service_name={self.cf_service_name}"
        )

    @property
    def array_url(self) -> str:
        return (
            f"oracle+cx_oracle://{self.user_name}:{self.passwd}"
            f"@{self.host}:{self.array_port}/?service_name={self.array_service_name}"
        )


@dataclass
class IncomingGovernanceConfig:
    # MySQL DB
    cell_input_db_name: str = "cim_piaoi"
    output_db_name: str = "cim_cell_aoi_to_array"

    # Existing CELL tables in cim_piaoi
    cell_summary_base: str = "cim_pi_glass_yyyymm"
    cell_defect_prefix_template: str = "cim_defect_yyyymm_"

    # Output tables in cim_cell_aoi_to_array
    source_cf_oc_base: str = "incoming_source_cf_oc_defect_raw_yyyymm"
    source_cf_ps_base: str = "incoming_source_cf_ps_defect_raw_yyyymm"

    source_array_mor_base: str = "incoming_source_array_mor_defect_raw_yyyymm"
    source_array_tar_base: str = "incoming_source_array_tar_defect_raw_yyyymm"
    source_array_tos_base: str = "incoming_source_array_tos_defect_raw_yyyymm"

    same_point_base: str = "incoming_same_point_detail_yyyymm"
    glass_summary_base: str = "incoming_glass_summary_yyyymm"
    api_aoi_summary_base: str = "api_aoi_summary_yyyymm"

    state_table: str = "incoming_governance_state"
    state_job_name: str = "cell_incoming_governance_V5"
    source_group_state_table: str = "incoming_source_group_state"


    # Matching offset
    cf_offset_um: float = 3000.0
    array_offset_um: float = 1000.0

    # Panel / mapping height
    panel_height_um: float = 1500000.0

      # CELL cim_pi_glass.aoi -> cim_defect table token
    # cim_pi_glass.aoi 欄位是實體機台名稱；
    # cim_defect 分表名稱使用 aoi100/aoi200/aoi300。
    aoi_map: Dict[str, str] = field(default_factory=lambda: {
        "CAPIT203": "aoi100",
        "CAAOI202": "aoi200",
        "CAAOI300": "aoi300",
    })

    # 若 cim_pi_glass.test_time 與 cim_defect.test_time 有秒差，可開容忍。
    # 目前預設 0 = 完全相等。
    cell_defect_time_tolerance_sec: int = 0

    # URL base
    cell_aidi_url: str = "http://l6apaimg103/dms/CELAIDI_L6A/"
    cell_aoi_img_base: str = "http://10.97.139.98:1454//"
    cell_aoi_unc_prefix: str = "\\\\192.168.5.88\\aoi"

    cf_img_base: str = "http://10.97.148.181/faaint10/image/"
    #"http://tcweb002.corpnet.auo.com/fafle001/image/"
    mor_img_base: str = "http://l6apaimg103/dms/ARYAOI_L6A/ "
    #"http://10.97.140.60:8080/data/images/"  #http://10.97.140.46/yms/images/
    tar_tos_img_base: str = "http://tcweb002.corpnet.auo.com/aaimf001/aalsr/"

    # Batching
    oracle_batch_size: int = 800
    mysql_batch_size: int = 800

    # CF Oracle
    cf_table: str = "PIS2C10RPT.M_AOI_DEFT"
    cf_glass_col: str = "GLASS_ID"

    cf_return_keys: List[str] = field(default_factory=lambda: [
        "glass_id",
        "chip_id",
        "model_no",
        "testing_date",
        "eqp_id",
        "op",
        "defect_no",
        "defect_code",
        "defect_size_type",
        "coord_x",
        "coord_y",
        "repair_date",
        "repair_code",
        "repair_eqp_id",
        "repair_op",
    ])

    # ARRAY Oracle station config
    array_station_configs: List[Dict[str, Any]] = field(default_factory=lambda: [
        {
            "station": "MOR",
            "source_table": "L10HARY.H_AIDI_SECDEFECT",
            "time_col": "TEST_TIME",
            "glass_col": "TFT_SHEET_ID",
            "x_col": "POX_X",
            "y_col": "POX_Y",
            "op_filter_col": "OP_KEY",
            "op_filter_value": "PX1=MOR",
            "return_keys": [
                "tft_lot_id",
                "model_no",
                "test_time",
                "tft_sheet_id",
                "tft_chip_id",
                "signal_no",
                "gate_no",
                "pox_x",
                "pox_y",
                "defect_size",
                "image_file_name",
                "img_file_url_path",
                "op_key",
                "recipe_id",
                "eqp_id",
                "adc_repair_answers",
            ],
        },
        {
            "station": "TAR",
            "source_table": "AT.ALR_RPF",
            "time_col": "DDATE_TTIME",
            "glass_col": "BOARD_ID",
            "x_col": "X_CORD",
            "y_col": "Y_CORD",
            "return_keys": [
                "lot_id",
                "model_no",
                "board_id",
                "tool_id",
                "chip_id",
                "data_ax",
                "gate_ax",
                "dft_mode",
                "route",
                "chip_seq_no",
                "op_id",
                "ddate_ttime",
                "retype",
                "tar_judge",
                "x_cord",
                "y_cord",
                "tester_tool",
                "rp_flag",
            ],
        },
        {
            "station": "TOS",
            "source_table": "AT.TOS_RPF",
            "time_col": "DDATE_TTIME",
            "glass_col": "BOARD_ID",
            "x_col": "X_CORD",
            "y_col": "Y_CORD",
            "return_keys": [
                "lot_id",
                "model_no",
                "board_id",
                "tool_id",
                "chip_id",
                "data_ax",
                "gate_ax",
                "dft_mode",
                "route",
                "chip_seq_no",
                "op_id",
                "ddate_ttime",
                "retype",
                "tar_judge",
                "x_cord",
                "y_cord",
                "tester_tool",
                "rp_flag",
            ],
        },
    ])


# =============================================================================
# Utilities
# =============================================================================

def parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def yyyymm_range(start_dt: datetime, end_dt: datetime) -> List[str]:
    cur = datetime(start_dt.year, start_dt.month, 1)
    end_month = datetime(end_dt.year, end_dt.month, 1)

    out = []
    while cur <= end_month:
        out.append(cur.strftime("%Y%m"))
        if cur.month == 12:
            cur = datetime(cur.year + 1, 1, 1)
        else:
            cur = datetime(cur.year, cur.month + 1, 1)
    return out


def chunk_list(values: List[Any], batch_size: int) -> Iterable[List[Any]]:
    for i in range(0, len(values), batch_size):
        yield values[i:i + batch_size]


def safe_lower_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    out.columns = [str(c).lower() for c in out.columns]
    return out


def clean_text(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if s.lower() in {"nan", "none", "null", "<na>", "nat"}:
        return ""
    return s

def normalize_defect_size_by_first_char(v: Any, default: str = "O") -> str:
    """
    將 defect_size 正規化成 S/M/L/O。

    適用：
    - SMALL  -> S
    - MEDIUM -> M
    - LARGE  -> L
    - S/M/L/O -> 原值
    - nan/null/None/空字串 -> default
    """
    s = clean_text(v).upper()

    if not s:
        return default

    first = s[0]

    if first in {"S", "M", "L", "O"}:
        return first

    return default


def normalize_cell_defect_size(v: Any, *, aoi_token: str = "") -> str:
    """
    CELL cim_defect defect_size 規則。

    需求：
    - 若 aoi = aoi200 且 defect_size 為 nan/null/空值，判斷為 O。
    - 其他有值者維持 S/M/L/O 第一個字元。
    """
    token = clean_text(aoi_token).lower()
    s = clean_text(v).upper()

    if not s:
        if token == "aoi200":
            return "O"
        return ""

    first = s[0]
    if first in {"S", "M", "L", "O"}:
        return first

    if token == "aoi200":
        return "O"

    return s


def normalize_string_series(s: pd.Series) -> pd.Series:
    return s.astype("string").fillna("").str.strip()


def validate_identifier(identifier: str, name: str = "identifier") -> str:
    if identifier is None:
        raise ValueError(f"{name} is None")
    identifier = str(identifier).strip()
    if not identifier:
        raise ValueError(f"{name} is empty")
    if not re.fullmatch(r"[A-Za-z0-9_$#.]+", identifier):
        raise ValueError(f"Invalid {name}: {identifier}")
    return identifier.upper()


def split_owner_table(full_table_name: str) -> Tuple[str, str]:
    parts = str(full_table_name).strip().split(".")
    if len(parts) != 2:
        raise ValueError(f"Invalid table name: {full_table_name}. Use OWNER.TABLE_NAME.")
    return validate_identifier(parts[0], "owner"), validate_identifier(parts[1], "table")


def normalize_return_keys(keys: List[str]) -> List[str]:
    return [str(k).strip().upper() for k in keys if str(k).strip()]


def json_dumps_safe(obj: Any) -> str:
    def default(o):
        if isinstance(o, (datetime, pd.Timestamp)):
            if pd.isna(o):
                return None
            return o.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            if np.isnan(o):
                return None
            return float(o)
        try:
            if pd.isna(o):
                return None
        except Exception:
            pass
        return str(o)

    return json.dumps(obj, ensure_ascii=False, default=default)

def get_daily_debug_log_path(
    sub_dir: str = "logs/cell_incoming_size_debug",
    prefix: str = "cell_incoming_size_debug",
) -> str:
    os.makedirs(sub_dir, exist_ok=True)
    return os.path.join(
        sub_dir,
        f"{prefix}_{datetime.now().strftime('%Y%m%d')}.txt",
    )


def write_size_debug_log(
    *,
    station_label: str,
    df: pd.DataFrame,
    sheet_col: str = "sheet_id",
    time_col: str = "scan_time",
    size_col: str = "defect_size",
):
    """
    依站點輸出：
    - 每片 sheet_id
    - 最新量測時間
    - 不同 defect_size count

    log 檔案依執行日期儲存。
    """
    log_path = get_daily_debug_log_path()

    with open(log_path, "a", encoding="utf-8") as f:
        f.write("\n")
        f.write("=" * 120 + "\n")
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] STATION={station_label}\n")

        if df is None or df.empty:
            f.write("EMPTY\n")
            return

        d = df.copy()

        if sheet_col not in d.columns:
            f.write(f"MISSING sheet_col={sheet_col}\n")
            f.write(f"columns={list(d.columns)}\n")
            return

        if time_col not in d.columns:
            f.write(f"MISSING time_col={time_col}\n")
            f.write(f"columns={list(d.columns)}\n")
            return

        if size_col not in d.columns:
            f.write(f"MISSING size_col={size_col}\n")
            f.write(f"columns={list(d.columns)}\n")
            return

        d[sheet_col] = normalize_string_series(d[sheet_col])
        d[time_col] = pd.to_datetime(d[time_col], errors="coerce")
        d[size_col] = d[size_col].apply(lambda x: clean_text(x).upper() or "EMPTY")

        latest = (
            d.dropna(subset=[sheet_col, time_col])
            .groupby(sheet_col, as_index=False)[time_col]
            .max()
            .rename(columns={time_col: "latest_measure_time"})
        )

        cnt = (
            d.groupby([sheet_col, size_col], as_index=False)
            .size()
            .rename(columns={"size": "defect_count"})
        )

        pivot = cnt.pivot_table(
            index=sheet_col,
            columns=size_col,
            values="defect_count",
            aggfunc="sum",
            fill_value=0,
        ).reset_index()

        out = latest.merge(pivot, on=sheet_col, how="left")
        out = out.sort_values([sheet_col]).reset_index(drop=True)

        f.write(f"rows={len(d)} sheets={out[sheet_col].nunique()}\n")

        for _, r in out.iterrows():
            sheet_id = clean_text(r.get(sheet_col))
            latest_time = r.get("latest_measure_time")

            if isinstance(latest_time, (datetime, pd.Timestamp)):
                latest_time_str = latest_time.strftime("%Y-%m-%d %H:%M:%S")
            else:
                latest_time_str = clean_text(latest_time)

            size_parts = []
            for c in out.columns:
                if c in {sheet_col, "latest_measure_time"}:
                    continue

                try:
                    v = int(r.get(c) or 0)
                except Exception:
                    v = 0

                if v:
                    size_parts.append(f"{c}={v}")

            if not size_parts:
                size_parts.append("NO_SIZE_COUNT")

            f.write(
                f"sheet_id={sheet_id} | latest_measure_time={latest_time_str} | "
                + ", ".join(size_parts)
                + "\n"
            )



def sanitize_mysql_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    寫入 MySQL 前清理：
    - np.nan / pd.NA / NaT -> None
    - np.inf / -np.inf -> None
    - 字串 'nan' / 'NaT' / '<NA>' / 'None' / 'null' -> None
    - 轉 object，避免 pandas dtype 把 None 又轉回 NaN
    """
    if df is None or df.empty:
        return df

    out = df.copy().astype(object)

    out = out.replace([np.inf, -np.inf], None)
    out = out.where(pd.notna(out), None)

    bad_strings = {"", "nan", "none", "null", "<na>", "nat", "inf", "-inf"}

    for col in out.columns:
        out[col] = out[col].apply(
            lambda x: None
            if isinstance(x, str) and x.strip().lower() in bad_strings
            else x
        )

    return out.astype(object)

def clean_df_by_schema(
    df: pd.DataFrame,
    *,
    datetime_cols: Optional[List[str]] = None,
    int_cols: Optional[List[str]] = None,
    float_cols: Optional[List[str]] = None,
    text_cols: Optional[List[str]] = None,
    json_cols: Optional[List[str]] = None,
    zero_int_cols: Optional[List[str]] = None,
    zero_float_cols: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    append_or_create_dedup 前最後一層 schema-aware 清理。

    目的：
    - 避免 None / NaN / NaT 經 staging table 後變成字串 'nan'
    - DATETIME 欄位：無效值 -> None
    - 一般 INT/FLOAT 欄位：無效值 -> None
    - zero_int_cols / zero_float_cols：無效值 -> 0 / 0.0
    - TEXT 欄位：無效值 -> ''
    - JSON/LONGTEXT 欄位：無效值 -> ''
    """
    if df is None or df.empty:
        return df

    datetime_cols = datetime_cols or []
    int_cols = int_cols or []
    float_cols = float_cols or []
    text_cols = text_cols or []
    json_cols = json_cols or []
    zero_int_cols = zero_int_cols or []
    zero_float_cols = zero_float_cols or []

    bad_strings = {"", "nan", "none", "null", "<na>", "nat", "inf", "-inf", "NaN", "None", "NULL", "NaT"}

    def is_bad(v: Any) -> bool:
        if v is None:
            return True

        if isinstance(v, str):
            return v.strip() in bad_strings or v.strip().lower() in {x.lower() for x in bad_strings}

        try:
            if pd.isna(v):
                return True
        except Exception:
            pass

        return False

    def clean_datetime(v: Any):
        if is_bad(v):
            return None

        dt = pd.to_datetime(v, errors="coerce")
        if pd.isna(dt):
            return None

        # PyMySQL / SQLAlchemy 可接受 Python datetime
        return dt.to_pydatetime() if hasattr(dt, "to_pydatetime") else dt

    def clean_int_or_none(v: Any):
        if is_bad(v):
            return None

        n = pd.to_numeric(v, errors="coerce")
        if pd.isna(n):
            return None

        return int(float(n))

    def clean_float_or_none(v: Any):
        if is_bad(v):
            return None

        n = pd.to_numeric(v, errors="coerce")
        if pd.isna(n):
            return None

        return float(n)

    def clean_int_zero(v: Any):
        if is_bad(v):
            return 0

        n = pd.to_numeric(v, errors="coerce")
        if pd.isna(n):
            return 0

        return int(float(n))

    def clean_float_zero(v: Any):
        if is_bad(v):
            return 0.0

        n = pd.to_numeric(v, errors="coerce")
        if pd.isna(n):
            return 0.0

        return float(n)

    def clean_text_value(v: Any):
        if is_bad(v):
            return ""

        return str(v).strip()

    out = df.copy().astype(object)
    out = out.replace([np.inf, -np.inf], None)
    out = out.where(pd.notna(out), None)

    for col in datetime_cols:
        if col in out.columns:
            out[col] = out[col].apply(clean_datetime).astype(object)

    for col in int_cols:
        if col in out.columns:
            out[col] = out[col].apply(clean_int_or_none).astype(object)

    for col in float_cols:
        if col in out.columns:
            out[col] = out[col].apply(clean_float_or_none).astype(object)

    for col in zero_int_cols:
        if col in out.columns:
            out[col] = out[col].apply(clean_int_zero).astype(object)

    for col in zero_float_cols:
        if col in out.columns:
            out[col] = out[col].apply(clean_float_zero).astype(object)

    for col in text_cols:
        if col in out.columns:
            out[col] = out[col].apply(clean_text_value).astype(object)

    for col in json_cols:
        if col in out.columns:
            out[col] = out[col].apply(clean_text_value).astype(object)

    # 最後保險：所有剩餘欄位若還有字串 nan/null，統一轉 None
    for col in out.columns:
        out[col] = out[col].apply(
            lambda x: None
            if isinstance(x, str) and x.strip().lower() in {"nan", "none", "null", "<na>", "nat", "inf", "-inf"}
            else x
        )

    return out.astype(object)

def latest_cell_by_sheet_pi_type(cell_glass_df: pd.DataFrame) -> pd.DataFrame:
    """
    CELL 母體依 sheet_id_chip_id + pi_type 取最新 test_time。
    若同片同 pi_type 有多次 CELL 量測，只保留最新一次。
    """
    if cell_glass_df is None or cell_glass_df.empty:
        return pd.DataFrame()

    d = cell_glass_df.copy()

    if "sheet_id_chip_id" not in d.columns or "test_time" not in d.columns:
        return d

    if "pi_type" not in d.columns:
        d["pi_type"] = ""

    d["sheet_id_chip_id"] = normalize_string_series(d["sheet_id_chip_id"])
    d["pi_type"] = normalize_string_series(d["pi_type"]).str.upper()
    d["test_time"] = pd.to_datetime(d["test_time"], errors="coerce")

    d = d.dropna(subset=["sheet_id_chip_id", "pi_type", "test_time"])

    if d.empty:
        return d

    d = d.sort_values(["sheet_id_chip_id", "pi_type", "test_time"])
    out = d.groupby(["sheet_id_chip_id", "pi_type"], as_index=False).tail(1).copy()

    return out.reset_index(drop=True)


def get_repair_last(v: Any) -> str:
    s = clean_text(v).upper()
    if not s:
        return ""
    return s.split("-")[-1].strip()


def build_cf_image_name(row: pd.Series) -> str:
    glass_id = clean_text(row.get("sheet_id"))
    defect_no = clean_text(row.get("defect_no"))
    x = clean_text(row.get("ori_x"))
    y = clean_text(row.get("ori_y"))
    img_name = f"R{glass_id}_{defect_no}_001_{x}_{y}.jpg"
    """
    logging.info(
        "[build_cf_image_name] row=%s \nglass=%s defect_no=%s ori_x=%s ori_y=%s img_name=%s",
        row,
        glass_id,
        defect_no ,
        x,
        y,
        img_name
    )
    """
    
    return img_name


def build_cf_img_url(row: pd.Series, cfg: IncomingGovernanceConfig) -> str:
    """
    repair_op 後綴僅用來拼接 img_url_path。
    若 repair_op 為空或後綴非 OC/PS，suffix fallback 為 op_id。
    最後回傳完整含 .jpg URL。
    """
    sheet_id = clean_text(row.get("sheet_id"))
    image_name = clean_text(row.get("image_name"))
    op_id = clean_text(row.get("op_id")).upper()
    repair_op = clean_text(row.get("repair_op"))

    suffix = get_repair_last(repair_op)
    if suffix not in {"OC", "PS"}:
        suffix = op_id

    if suffix not in {"OC", "PS"}:
        suffix = "UNKNOWN"
    suffix  = suffix if suffix =="PS" else "MVA"
    
    tail = sheet_id[-1:] if sheet_id else ""
    folder = f"{cfg.cf_img_base}{suffix}/{tail}/{sheet_id}/"
    return build_complete_img_url(folder, image_name)

def build_mor_img_url(
    image_file_name: Any,
    img_file_url_path: Any,
    cfg: IncomingGovernanceConfig,
) -> str:
    """
    MOR 影像 URL 組法：

    mor_img_base + img_file_url_path + image_file_name

    Example:
        mor_img_base       = http://l6apaimg103/dms/ARYAOI_L6A/
        img_file_url_path  = xxx/yyy/zzz/
        image_file_name    = abc.jpg
    """
    fn = clean_text(image_file_name)
    folder = clean_text(img_file_url_path)
    base = clean_text(cfg.mor_img_base)

    if not fn or not folder:
        return ""

    if fn.startswith("http://") or fn.startswith("https://"):
        return fn

    if folder.startswith("http://") or folder.startswith("https://"):
        return folder.rstrip("/") + "/" + fn.lstrip("/")

    return (
        base.rstrip("/")
        + "/"
        + folder.strip("/")
        + "/"
        + fn.lstrip("/")
    )



def build_tar_tos_image_name(row: Dict[str, Any]) -> str:
    lot_id = clean_text(row.get("lot_id"))
    dft_mode = row.get("dft_mode") or ""
    op_id = clean_text(row.get("op_id"))
    chip_id = row.get("chip_id") or ""
    chip_seq_no = row.get("chip_seq_no")
    data_ax = clean_text(row.get("data_ax"))
    gate_ax = clean_text(row.get("gate_ax"))
    rp_flag = clean_text(row.get("rp_flag"))
    route = clean_text(row.get("route"))

    seq_map = {
        1: "A", 2: "B", 3: "C", 4: "D", 5: "E", 6: "F", 7: "G", 8: "H", 9: "J",
        10: "K", 11: "L", 12: "M", 13: "N", 14: "P", 15: "Q", 16: "R", 17: "S",
        18: "T", 19: "U", 20: "V", 21: "W", 22: "X", 23: "Y", 24: "Z",
        25: "0", 26: "1", 27: "2", 28: "3", 29: "4", 30: "5",
        31: "6", 32: "7", 33: "8", 34: "9",
    }

    if op_id == "auto_rp":
        chip_part = chip_id[3:]
    else:
        chip_char = chip_id[8] if len(chip_id) >= 9 else ""
        try:
            seq_num = int(str(chip_seq_no).strip())
        except (ValueError, TypeError):
            seq_num = 0
        seq_char = seq_map.get(seq_num, "1")
        chip_part = chip_char + seq_char

    rp_flag_map = {"Y": "(AR)", "B": "(FR)", "F": "(FR)", "N": "(ND)", "S": "(SC)"}
    rp_flag_str = rp_flag_map.get(rp_flag, "")

    if op_id == "auto_rp":
        route_str = ""
    elif route == "TOS_G":
        route_str = "_G"
    elif route == "TOS_D":
        route_str = "_D"
    elif route == "CVD":
        route_str = "_C"
    else:
        route_str = ""

    return f"{lot_id} {dft_mode} {chip_part} {data_ax} {gate_ax} {rp_flag_str}{route_str}.jpg"


def build_tar_tos_img_url(row: pd.Series, cfg: IncomingGovernanceConfig) -> str:
    route = clean_text(row.get("route"))
    lot_id = clean_text(row.get("lot_id"))
    image_name = clean_text(row.get("image_name"))
    if not image_name:
        return ""
    folder = f"{cfg.tar_tos_img_base}{route}/{lot_id}/"
    return build_complete_img_url(folder, image_name)


def is_http_url(v: Any) -> bool:
    s = clean_text(v).lower()
    return s.startswith("http://") or s.startswith("https://")


def join_url_path(base: str, path: str) -> str:
    b = clean_text(base)
    p = clean_text(path)

    if not b:
        return p
    if not p:
        return b

    return b.rstrip("/") + "/" + p.lstrip("/")


def safe_image_filename_from_url_or_path(v: Any) -> str:
    """
    從完整 URL / Windows path / Linux path 取最後檔名。
    """
    s = clean_text(v)
    if not s:
        return ""

    s = s.replace("\\", "/")
    s = s.split("?")[0].split("#")[0]
    return s.rstrip("/").split("/")[-1]


def build_complete_img_url(pic_path: Any, pic_name: Any = "") -> str:
    """
    將 pic_path + pic_name 組成完整影像 URL。

    規則：
    1. pic_path 已含 .jpg/.jpeg/.png/.bmp/.gif/.webp → 直接回傳 pic_path
    2. pic_path 沒有檔名，但 pic_name 有 → pic_path/pic_name
    3. pic_path 空 → 空字串
    """
    path = clean_text(pic_path)
    name = clean_text(pic_name)

    if not path:
        return ""

    low = path.lower()
    if any(ext in low for ext in [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"]):
        return path

    if name:
        return path.rstrip("/") + "/" + name.lstrip("/")

    return path

def build_cell_image_from_cim_row(
    row: pd.Series,
    cfg: IncomingGovernanceConfig,
    *,
    machine_id: str = "",
    op_id: str = "",
    test_time: Any = None,
) -> Tuple[str, str]:
    """
    根據 cim_piaoi.cim_defect raw 欄位產出：
        image_url  : 完整含 .jpg 的 URL
        image_name : 影像檔名

    目前 cim_defect 實際欄位範例：
        img_file_url_path = 'PIT/2606/11/CAAOI202/5H6A5704A/2355/'
        image_file_name   = 'RV1_1553299_1208129_0.jpg'

    目標：
        image_name   = image_file_name
        img_url_path = http://l6apaimg103/dms/CELAIDI_L6A/{img_file_url_path}/{image_file_name}
    """
    base_url = clean_text(cfg.cell_aidi_url)

    img_url_folder = (
        clean_text(row.get("img_file_url_path"))
        or clean_text(row.get("img_filter_url_path"))
    )

    image_name = (
        clean_text(row.get("image_file_name"))
        or clean_text(row.get("img_file_name"))
        or clean_text(row.get("pic_name"))
        or clean_text(row.get("image_name"))
    )

    if img_url_folder and image_name:
        folder_url = join_url_path(base_url, img_url_folder)
        final_url = build_complete_img_url(folder_url, image_name)
        return final_url, image_name

    if img_url_folder:
        folder_url = join_url_path(base_url, img_url_folder)
        final_name = safe_image_filename_from_url_or_path(folder_url)
        return folder_url, final_name

    if image_name:
        final_url = join_url_path(base_url, image_name)
        return final_url, image_name

    return "", ""

def normalize_source_raw_value(v: Any) -> Any:
    if v is None:
        return None

    try:
        if pd.isna(v):
            return None
    except Exception:
        pass

    if isinstance(v, (datetime, pd.Timestamp)):
        return v.strftime("%Y-%m-%d %H:%M:%S")

    if isinstance(v, np.integer):
        return int(v)

    if isinstance(v, np.floating):
        if np.isnan(v):
            return None
        return float(v)

    return v


def source_raw_dict(row: pd.Series) -> Dict[str, Any]:
    if row is None:
        return {}
    return {str(k): normalize_source_raw_value(v) for k, v in row.to_dict().items()}

def build_source_subtable_detail(
    source_row: pd.Series,
    *,
    process: str,
    source_op_id: str,
    source_scan_time: Any,
) -> Dict[str, Any]:
    """
    依 source_op_id 產出 point_detail.source 給前端 defect table 子表格使用。

    輸出包含：
    - source_defect_uid
    - 指定子表格欄位
    - source_op_id / trans_x / trans_y / image_name / img_url_path / source_group_key
    - display：共用顯示欄位
    - raw：完整 source raw row
    """
    op = clean_text(source_op_id).upper()
    raw = source_raw_dict(source_row)

    def num_or_none(key: str):
        v = source_row.get(key)
        try:
            if pd.isna(v):
                return None
        except Exception:
            pass
        try:
            return float(v)
        except Exception:
            return None

    common = {
        "source_defect_uid": clean_text(source_row.get("source_defect_uid")),
        "source_op_id": clean_text(source_op_id),
        "trans_x": num_or_none("trans_x"),
        "trans_y": num_or_none("trans_y"),
        "image_name": clean_text(source_row.get("image_name")),
        "img_url_path": clean_text(source_row.get("img_url_path")),
        "source_group_key": clean_text(source_row.get("source_group_key")),
        "defect_size_raw": clean_text(source_row.get("defect_size_raw")),
    }

    if op == "PX1=MOR":
        detail = {
            "lot_id": clean_text(source_row.get("lot_id")),
            "scan_time": normalize_source_raw_value(
                source_scan_time if source_scan_time is not None else source_row.get("scan_time")
            ),
            "chip_id": clean_text(source_row.get("chip_id")),
            "signal_no": clean_text(source_row.get("signal_no")),
            "gate_no": clean_text(source_row.get("gate_no")),
            "ori_x": num_or_none("ori_x"),
            "ori_y": num_or_none("ori_y"),
            "defect_code": clean_text(source_row.get("defect_code")),
            "defect_size": clean_text(source_row.get("defect_size")),
            "defect_size_raw": clean_text(source_row.get("defect_size_raw")),
            "recipe_id": clean_text(source_row.get("recipe_id")),
            "eqp_id": clean_text(source_row.get("eqp_id")),
            "adc_repair_answers": clean_text(source_row.get("defect_code")),
        }

    elif op in {"TAR", "TOS"}:
        detail = {
            "lot_id": clean_text(source_row.get("lot_id")),
            "chip_id": clean_text(source_row.get("chip_id")),
            "signal_no": clean_text(source_row.get("signal_no")),
            "gate_no": clean_text(source_row.get("gate_no")),
            "dft_mode": clean_text(source_row.get("signal_gate_defect_code")),
            "tool_id": clean_text(source_row.get("tool_id")),
            "repair_time": normalize_source_raw_value(
                source_scan_time if source_scan_time is not None else source_row.get("repair_time")
            ),
            "retype": clean_text(source_row.get("defect_code")),
            "defect_code": clean_text(source_row.get("defect_code")),
            "defect_size": clean_text(source_row.get("defect_size")),
            "defect_size_raw": clean_text(source_row.get("defect_size_raw")),
            "ori_x": num_or_none("ori_x"),
            "ori_y": num_or_none("ori_y"),
            "tester_tool": clean_text(source_row.get("tester_tool")),
            "model_no": clean_text(source_row.get("model_no")),
        }

    elif op in {"OC", "PS"}:
        detail = {
            "chip_id": clean_text(source_row.get("chip_id")),
            "model_no": clean_text(source_row.get("model_no")),
            "scan_time": normalize_source_raw_value(
                source_scan_time if source_scan_time is not None else source_row.get("scan_time")
            ),
            "eqp_id": clean_text(source_row.get("eqp_id")),
            "op": clean_text(source_row.get("op")),
            "defect_code": clean_text(source_row.get("defect_code")),
            "defect_size_type": clean_text(source_row.get("defect_size")),
            "defect_size": clean_text(source_row.get("defect_size")),
            "ori_x": num_or_none("ori_x"),
            "ori_y": num_or_none("ori_y"),
            "repair_time": normalize_source_raw_value(source_row.get("repair_time")),
            "repair_code": clean_text(source_row.get("repair_code")),
            "repair_eqp_id": clean_text(source_row.get("repair_eqp_id")),
            "repair_op": clean_text(source_row.get("repair_op")),
        }

    else:
        detail = {}

    display = {
        "process": clean_text(process),
        "source_defect_uid": common["source_defect_uid"],
        "source_op_id": clean_text(source_op_id),
        "scan_time": normalize_source_raw_value(source_scan_time),
        "chip_id": clean_text(source_row.get("chip_id")),
        "defect_no": clean_text(source_row.get("defect_no")),
        "signal_no": clean_text(source_row.get("signal_no")),
        "gate_no": clean_text(source_row.get("gate_no")),
        "defect_code": clean_text(source_row.get("defect_code")),
        "defect_size": clean_text(source_row.get("defect_size")),
        "ori_x": num_or_none("ori_x"),
        "ori_y": num_or_none("ori_y"),
        "trans_x": common["trans_x"],
        "trans_y": common["trans_y"],
        "image_name": common["image_name"],
        "img_url_path": common["img_url_path"],
        "source_group_key": common["source_group_key"],
    }

    out: Dict[str, Any] = {}
    out.update(detail)
    out.update(common)
    out["process"] = clean_text(process)
    out["display"] = display
    out["raw"] = raw

    return out



def process_from_abbr(abbr_cat: Any) -> str:
    s = clean_text(abbr_cat).upper()
    if s == "CF":
        return "CF"
    if s == "TFT":
        return "ARRAY"
    return ""

def to_cache_source_op_id(process: str, station: str) -> str:
    process = clean_text(process).upper()
    station = clean_text(station).upper()

    if process == "CF" and station == "OC":
        return "CF_OC"
    if process == "CF" and station == "PS":
        return "CF_PS"
    if process == "ARRAY" and station == "MOR":
        return "ARRAY_MOR"
    if process == "ARRAY" and station == "TAR":
        return "ARRAY_TAR"
    if process == "ARRAY" and station == "TOS":
        return "ARRAY_TOS"

    return f"{process}_{station}"

def build_source_group_state_df(
    *,
    input_sheet_ids: List[str],
    source_df: pd.DataFrame,
    process: str,
    station: str,
    cache_status_when_missing: str = "ORACLE_NOT_FOUND",
    status_detail_when_missing: str = "",
) -> pd.DataFrame:
    """
    根據 Oracle 查詢後 normalize 的 source_df，為每個 input sheet 建立 station-level cache state。

    注意：
    - 如果 source_df 有該 sheet 的 defect rows → ORACLE_WITH_DEFECT
    - 如果 source_df 沒該 sheet 的 rows → ORACLE_NOT_FOUND
    - 若未來有 source header 可判斷 defect=0，再改成 ORACLE_NO_DEFECT
    """
    sheet_ids = sorted({clean_text(s) for s in input_sheet_ids if clean_text(s)})
    source_op_id = to_cache_source_op_id(process, station)

    if source_df is None or source_df.empty:
        source_df = pd.DataFrame()

    d = source_df.copy()

    if not d.empty and "sheet_id" in d.columns:
        d["sheet_id"] = normalize_string_series(d["sheet_id"])
    else:
        d["sheet_id"] = ""

    time_col = "repair_time" if station.upper() in {"TAR", "TOS"} else "scan_time"

    if not d.empty and time_col in d.columns:
        d[time_col] = pd.to_datetime(d[time_col], errors="coerce")

    rows = []

    for sheet_id in sheet_ids:
        g = d[d["sheet_id"].eq(sheet_id)].copy() if not d.empty else pd.DataFrame()

        if not g.empty:
            source_scan_time = None
            if time_col in g.columns:
                source_scan_time = g[time_col].max()

            rows.append({
                "source_op_id": source_op_id,
                "process": process,
                "station": station,
                "sheet_id": sheet_id,
                "source_scan_time": source_scan_time,
                "source_defect_cnt": int(len(g)),
                "cache_status": "ORACLE_WITH_DEFECT",
                "cache_status_detail": f"oracle defect rows={len(g)}",
                "source_table_name": "",
                "yyyymm": pd.to_datetime(source_scan_time).strftime("%Y%m")
                    if source_scan_time is not None and not pd.isna(source_scan_time)
                    else None,
                "last_query_time": datetime.now(),
            })
        else:
            rows.append({
                "source_op_id": source_op_id,
                "process": process,
                "station": station,
                "sheet_id": sheet_id,
                "source_scan_time": None,
                "source_defect_cnt": None,
                "cache_status": cache_status_when_missing,
                "cache_status_detail": status_detail_when_missing
                    or f"oracle returned no defect rows for {source_op_id}",
                "source_table_name": "",
                "yyyymm": None,
                "last_query_time": datetime.now(),
            })

    return pd.DataFrame(rows)

def ensure_column_exists(conn, table_name: str, column_name: str, column_def_sql: str):
    """
    MySQL: 若欄位不存在則 ALTER TABLE ADD COLUMN。
    """
    sql = text("""
    SELECT COUNT(*) AS cnt
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = :table_name
      AND COLUMN_NAME = :column_name
    """)

    cnt = conn.execute(sql, {
        "table_name": table_name,
        "column_name": column_name,
    }).scalar()

    if int(cnt or 0) == 0:
        conn.execute(text(f"""
        ALTER TABLE {table_name}
        ADD COLUMN {column_name} {column_def_sql}
        """))


def ensure_index_exists(conn, table_name: str, index_name: str, column_name: str):
    """
    MySQL: 若 index 不存在則建立單欄 index。
    """
    sql = text("""
    SELECT COUNT(*) AS cnt
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = :table_name
      AND INDEX_NAME = :index_name
    """)

    cnt = conn.execute(sql, {
        "table_name": table_name,
        "index_name": index_name,
    }).scalar()

    if int(cnt or 0) == 0:
        conn.execute(text(f"""
        CREATE INDEX {index_name}
        ON {table_name} ({column_name})
        """))

# =============================================================================
# Oracle Handler
# =============================================================================

class OracleDBHandler:
    def __init__(self, database_url: str, echo: bool = False):
        self.database_url = database_url
        self.engine = create_engine(
            database_url,
            echo=echo,
            connect_args={
                "encoding": "UTF-8",
                "nencoding": "UTF-8",
                "events": True,
            },
        )
        self.Session = sessionmaker(bind=self.engine)
        self.session_factory = scoped_session(self.Session)

    @contextmanager
    def get_session(self):
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
            self.session_factory.remove()

    def query_df(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
        debug_sql: bool = False,
    ) -> pd.DataFrame:
        params = params or {}

        if debug_sql:
            logging.info("[Oracle SQL]\n%s", sql)
            logging.info("[Oracle PARAMS] %s", params)

        with self.get_session() as session:
            result = session.execute(text(sql), params)
            rows = [dict(row._mapping) for row in result]

        df = pd.DataFrame(rows)
        return safe_lower_columns(df)

    def fetch_by_in_batches(
        self,
        table_name: str,
        select_cols: List[str],
        in_col: str,
        values: List[str],
        where_extra_sql: str = "",
        params_extra: Optional[Dict[str, Any]] = None,
        batch_size: int = 800,
    ) -> pd.DataFrame:
        if not values:
            return pd.DataFrame()

        owner, table = split_owner_table(table_name)
        table_sql = f"{owner}.{table}"

        select_cols_norm = normalize_return_keys(select_cols)
        in_col_norm = validate_identifier(in_col, "in_col")
        col_sql = ", ".join(select_cols_norm)

        out_chunks = []
        params_extra = params_extra or {}

        for batch in chunk_list(values, batch_size):
            bind = {f"v{j}": str(v) for j, v in enumerate(batch)}
            in_clause = ", ".join([f":v{j}" for j in range(len(batch))])

            sql = f"""
            SELECT {col_sql}
            FROM {table_sql}
            WHERE {in_col_norm} IN ({in_clause})
            {where_extra_sql}
            """

            params = dict(bind)
            params.update(params_extra)

            df = self.query_df(sql, params)
            if not df.empty:
                out_chunks.append(df)

        if not out_chunks:
            return pd.DataFrame()

        return pd.concat(out_chunks, ignore_index=True)


# =============================================================================
# MySQL Repositories
# =============================================================================

class CellInputRepository:
    def __init__(self, db: MySQLConnet, cfg: IncomingGovernanceConfig):
        self.db = db
        self.cfg = cfg
        self.engine = db.engine

    def table_exists(self, table_name: str) -> bool:
        insp = inspect(self.engine)
        return table_name.lower() in [t.lower() for t in insp.get_table_names()]

    def list_tables(self) -> List[str]:
        return inspect(self.engine).get_table_names()

    def cell_summary_table_name(self, yyyymm: str) -> str:
        return self.cfg.cell_summary_base.replace("yyyymm", yyyymm).lower()

    def defect_table_prefix(self, yyyymm: str) -> str:
        return self.cfg.cell_defect_prefix_template.replace("yyyymm", yyyymm).lower()

    def find_cell_defect_tables(self, yyyymm: str) -> List[str]:
        prefix = self.defect_table_prefix(yyyymm)
        return [t for t in self.list_tables() if t.lower().startswith(prefix)]

    def load_cell_glass(self, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
        months = yyyymm_range(start_dt, end_dt)
        chunks = []

        for ym in months:
            tb = self.cell_summary_table_name(ym)
            if not self.table_exists(tb):
                logging.warning("[load_cell_glass] table not exists: %s", tb)
                continue

            sql = text(f"""
            SELECT *
            FROM {tb}
            WHERE test_time >= :start_dt
              AND test_time <  :end_dt
            """)

            with self.engine.connect() as conn:
                df = pd.read_sql(sql, conn, params={"start_dt": start_dt, "end_dt": end_dt})

            df = safe_lower_columns(df)
            if not df.empty:
                chunks.append(df)

        if not chunks:
            return pd.DataFrame()

        out = pd.concat(chunks, ignore_index=True)

        for c in ["test_time", "pi_time", "pi_hour"]:
            if c in out.columns:
                out[c] = pd.to_datetime(out[c], errors="coerce")

        if "sheet_id_chip_id" in out.columns:
            out["sheet_id_chip_id"] = normalize_string_series(out["sheet_id_chip_id"])

        if "abbr_cat" in out.columns:
            out["abbr_cat"] = normalize_string_series(out["abbr_cat"]).str.upper()

        if "pi_type" in out.columns:
            out["pi_type"] = normalize_string_series(out["pi_type"]).str.upper()

        out = out.drop_duplicates(subset=[c for c in ["sheet_id_chip_id", "test_time", "pi_type"] if c in out.columns])
        return out

    def resolve_defect_aoi_token(self, aoi_value: Any) -> str:
        """
        cim_pi_glass.aoi -> cim_defect table token

        例：
            CAPIT203 -> aoi100
            CAAOI202 -> aoi200
            CAAOI300 -> aoi300
        """
        aoi = clean_text(aoi_value).upper()
        return self.cfg.aoi_map.get(aoi, "").lower()

    def filter_defect_tables_by_aoi_token(
        self,
        defect_tables: List[str],
        aoi_token: str,
    ) -> List[str]:
        """
        根據 aoi_token 過濾 defect table。

        table 範例：
            cim_defect_202606_aoi100_pi100
            cim_defect_202606_aoi200_pi200
            cim_defect_202606_aoi300_pi300
        """
        token = clean_text(aoi_token).lower()

        if not token:
            return defect_tables

        out = []

        for tb in defect_tables:
            tb_l = tb.lower()

            if f"_{token}_" in tb_l or tb_l.endswith(f"_{token}"):
                out.append(tb)

        return out

    def load_cell_defects(self, cell_glass_df: pd.DataFrame) -> pd.DataFrame:
        """
        從 cim_piaoi.cim_defect_yyyymm_* 查 CELL AOI defect raw。

        修正版：
        1. 從 cim_pi_glass 母體帶入 aoi。
        2. 使用 cfg.aoi_map 將 CAPIT203/CAAOI202/CAAOI300 對應到 aoi100/aoi200/aoi300。
        3. 只查對應 aoi token 的 defect 分表，避免掃錯機台資料。
        4. 預設 test_time 完全相等；若 cfg.cell_defect_time_tolerance_sec > 0，改用 ±N 秒容忍。
        5. 產出 cell_img_url_path / cell_image_name / cell_defect_uid。
        """
        if cell_glass_df is None or cell_glass_df.empty:
            return pd.DataFrame()

        need_cols = [
            c for c in [
                "sheet_id_chip_id",
                "test_time",
                "aoi",
                "line_id",
                "op_id",
                "pi_type",
            ]
            if c in cell_glass_df.columns
        ]

        if "sheet_id_chip_id" not in need_cols or "test_time" not in need_cols:
            logging.warning("[load_cell_defects] missing sheet_id_chip_id/test_time in cell_glass_df")
            return pd.DataFrame()

        k = cell_glass_df[need_cols].copy()
        k = k.dropna(subset=["sheet_id_chip_id", "test_time"])

        k["sheet_id_chip_id"] = normalize_string_series(k["sheet_id_chip_id"])
        k["test_time"] = pd.to_datetime(k["test_time"], errors="coerce")
        k = k.dropna(subset=["test_time"])

        if "aoi" not in k.columns:
            k["aoi"] = ""

        if "pi_type" not in k.columns:
            k["pi_type"] = ""

        k["aoi"] = normalize_string_series(k["aoi"]).str.upper()
        k["pi_type"] = normalize_string_series(k["pi_type"]).str.upper()
        k["aoi_token"] = k["aoi"].apply(self.resolve_defect_aoi_token)

        k = k.drop_duplicates(
            subset=[
                c for c in [
                    "sheet_id_chip_id",
                    "test_time",
                    "pi_type",
                    "aoi",
                    "aoi_token",
                ]
                if c in k.columns
            ]
        )

        if k.empty:
            return pd.DataFrame()

        months = sorted(
            k["test_time"].dt.strftime("%Y%m").dropna().unique().tolist()
        )

        out_chunks = []

        tolerance_sec = int(getattr(self.cfg, "cell_defect_time_tolerance_sec", 0) or 0)

        for ym in months:
            all_defect_tables = self.find_cell_defect_tables(ym)

            if not all_defect_tables:
                logging.warning("[load_cell_defects] no defect tables for yyyymm=%s", ym)
                continue

            km = k[k["test_time"].dt.strftime("%Y%m").eq(ym)].copy()
            if km.empty:
                continue

            # 依 aoi_token 分組查對應 defect table
            for aoi_token, km_aoi in km.groupby("aoi_token", dropna=False):
                aoi_token = clean_text(aoi_token).lower()

                defect_tables = self.filter_defect_tables_by_aoi_token(
                    all_defect_tables,
                    aoi_token,
                )

                if not defect_tables:
                    logging.warning(
                        "[load_cell_defects] no mapped defect table ym=%s aoi_token=%s rows=%s sample_aoi=%s",
                        ym,
                        aoi_token,
                        len(km_aoi),
                        sorted(km_aoi["aoi"].dropna().unique().tolist())[:5],
                    )
                    continue

                logging.info(
                    "[load_cell_defects] ym=%s aoi_token=%s mother_rows=%s defect_tables=%s",
                    ym,
                    aoi_token or "ALL",
                    len(km_aoi),
                    defect_tables,
                )

                for tb in defect_tables:
                    for batch in chunk_list(km_aoi.to_dict(orient="records"), self.cfg.mysql_batch_size):
                        bind_parts = []
                        params: Dict[str, Any] = {}

                        for i, row in enumerate(batch):
                            g_key = f"g{i}"

                            if tolerance_sec > 0:
                                ts_key = f"ts{i}"
                                te_key = f"te{i}"

                                bind_parts.append(
                                    f"(sheet_id_chip_id = :{g_key} "
                                    f"AND test_time >= :{ts_key} "
                                    f"AND test_time < :{te_key})"
                                )

                                params[g_key] = row["sheet_id_chip_id"]
                                params[ts_key] = row["test_time"] - timedelta(seconds=tolerance_sec)
                                params[te_key] = row["test_time"] + timedelta(seconds=tolerance_sec)
                            else:
                                t_key = f"t{i}"

                                bind_parts.append(
                                    f"(sheet_id_chip_id = :{g_key} AND test_time = :{t_key})"
                                )

                                params[g_key] = row["sheet_id_chip_id"]
                                params[t_key] = row["test_time"]

                        if not bind_parts:
                            continue

                        where_sql = " OR ".join(bind_parts)

                        sql = text(f"""
                        SELECT *
                        FROM {tb}
                        WHERE {where_sql}
                        """)

                        try:
                            with self.engine.connect() as conn:
                                df = pd.read_sql(sql, conn, params=params)
                        except Exception:
                            logging.exception("[load_cell_defects] query failed table=%s", tb)
                            continue

                        df = safe_lower_columns(df)

                        if not df.empty:
                            df["_source_defect_table"] = tb
                            df["_mapped_aoi_token"] = aoi_token
                            out_chunks.append(df)

        if not out_chunks:
            logging.warning("[load_cell_defects] no cell defects loaded after aoi mapping")
            return pd.DataFrame()

        out = pd.concat(out_chunks, ignore_index=True)

        for c in ["test_time", "pi_time", "pi_hour"]:
            if c in out.columns:
                out[c] = pd.to_datetime(out[c], errors="coerce")

        if "sheet_id_chip_id" not in out.columns:
            logging.warning("[load_cell_defects] output missing sheet_id_chip_id")
            return pd.DataFrame()

        out["sheet_id_chip_id"] = normalize_string_series(out["sheet_id_chip_id"])

        out["cell_ori_x"] = pd.to_numeric(out.get("pox_x1"), errors="coerce")
        out["cell_ori_y"] = pd.to_numeric(out.get("pox_y1"), errors="coerce")

        # CELL AOI 座標不做 Y 軸反轉
        out["cell_trans_x"] = out["cell_ori_x"]
        out["cell_trans_y"] = out["cell_ori_y"]

        # -------------------------------------------------------------
        # CELL defect_size normalization
        # -------------------------------------------------------------
        # 需求：
        #   cim_defect 資料中若 aoi200 的 defect_size 為 nan/null/空值，視為 O。
        #   其餘 S/M/L/O 維持第一個字元。
        # -------------------------------------------------------------
        if "defect_size" not in out.columns:
            out["defect_size"] = ""

        if "_mapped_aoi_token" not in out.columns:
            out["_mapped_aoi_token"] = ""

        out["defect_size_raw"] = out["defect_size"]

        out["defect_size"] = out.apply(
            lambda r: normalize_cell_defect_size(
                r.get("defect_size"),
                aoi_token=r.get("_mapped_aoi_token"),
            ),
            axis=1,
        )


        # -------------------------------------------------------------
        # Merge cim_pi_glass meta for image path building
        # -------------------------------------------------------------
        meta_cols = [
            c for c in [
                "sheet_id_chip_id",
                "test_time",
                "aoi",
                "line_id",
                "op_id",
                "pi_type",
            ]
            if c in cell_glass_df.columns
        ]

        if meta_cols:
            meta = cell_glass_df[meta_cols].drop_duplicates(
                subset=[
                    c for c in [
                        "sheet_id_chip_id",
                        "test_time",
                        "pi_type",
                    ]
                    if c in meta_cols
                ]
            ).copy()

            meta["sheet_id_chip_id"] = normalize_string_series(meta["sheet_id_chip_id"])
            meta["test_time"] = pd.to_datetime(meta["test_time"], errors="coerce")

            if "pi_type" in meta.columns:
                meta["pi_type"] = normalize_string_series(meta["pi_type"]).str.upper()

            merge_keys = ["sheet_id_chip_id", "test_time"]

            if "pi_type" in out.columns and "pi_type" in meta.columns:
                out["pi_type"] = normalize_string_series(out["pi_type"]).str.upper()
                merge_keys.append("pi_type")

            out = out.merge(
                meta,
                on=merge_keys,
                how="left",
                suffixes=("", "_cell_meta"),
            )

        def _cell_img_pair(r: pd.Series) -> Tuple[str, str]:
            machine_id = clean_text(
                r.get("aoi")
                or r.get("aoi_cell_meta")
                or ""
            )

            op_id = clean_text(
                r.get("op_id")
                or r.get("op_id_cell_meta")
                or ""
            )

            return build_cell_image_from_cim_row(
                r,
                self.cfg,
                machine_id=machine_id,
                op_id=op_id,
                test_time=r.get("test_time"),
            )

        img_pairs = out.apply(_cell_img_pair, axis=1)

        out["cell_img_url_path"] = img_pairs.apply(
            lambda x: x[0] if isinstance(x, tuple) else ""
        )
        out["cell_image_name"] = img_pairs.apply(
            lambda x: x[1] if isinstance(x, tuple) else ""
        )

        missing_img_cnt = int(
            (out["cell_img_url_path"].astype(str).str.strip() == "").sum()
        )

        logging.info(
            "[load_cell_defects] image build rows=%s missing_img_url=%s has_img_file_url_path=%s has_image_file_name=%s has_img_file_name=%s has_img_filter_url_path=%s",
            len(out),
            missing_img_cnt,
            "img_file_url_path" in out.columns,
            "image_file_name" in out.columns,
            "img_file_name" in out.columns,
            "img_filter_url_path" in out.columns,
        )
        out["cell_img_url_path"] = img_pairs.apply(lambda x: x[0] if isinstance(x, tuple) else "")
        out["cell_image_name"] = img_pairs.apply(lambda x: x[1] if isinstance(x, tuple) else "")

        out = out.reset_index(drop=True)

        if "cell_image_name" in out.columns:
            uid_img_name = out["cell_image_name"]
        elif "img_file_name" in out.columns:
            uid_img_name = out["img_file_name"]
        elif "image_file_name" in out.columns:
            uid_img_name = out["image_file_name"]
        else:
            uid_img_name = pd.Series([""] * len(out))

        uid_code = out.get("adc_def_code", pd.Series([""] * len(out)))
        uid_size = out.get("defect_size", pd.Series([""] * len(out)))

        out["cell_defect_uid"] = (
            out["sheet_id_chip_id"].astype(str)
            + "|"
            + out["test_time"].astype(str)
            + "|"
            + uid_code.astype(str)
            + "|"
            + uid_size.astype(str)
            + "|"
            + out["cell_ori_x"].astype(str)
            + "|"
            + out["cell_ori_y"].astype(str)
            + "|"
            + uid_img_name.astype(str)
        )

        logging.info(
            "[load_cell_defects] loaded rows=%s tables=%s",
            len(out),
            sorted(out["_source_defect_table"].dropna().unique().tolist())
            if "_source_defect_table" in out.columns
            else [],
        )

        return out


class OutputRepository:
    def __init__(self, db: MySQLConnet, cfg: IncomingGovernanceConfig):
        self.db = db
        self.cfg = cfg
        self.engine = db.engine

    def ensure_state_table(self):
        ddl = text(f"""
        CREATE TABLE IF NOT EXISTS {self.cfg.state_table} (
            job_name VARCHAR(64) PRIMARY KEY,
            last_end_dt DATETIME NULL,
            update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP
        )
        """)
        with self.engine.begin() as conn:
            conn.execute(ddl)

    def ensure_source_group_state_table(self):
        ddl = text(f"""
        CREATE TABLE IF NOT EXISTS {self.cfg.source_group_state_table} (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,

            source_op_id VARCHAR(80) NOT NULL,
            process VARCHAR(40) NULL,
            station VARCHAR(40) NULL,

            sheet_id VARCHAR(80) NOT NULL,

            source_scan_time DATETIME NULL,
            source_defect_cnt INT NULL,

            cache_status VARCHAR(80) NOT NULL,
            cache_status_detail VARCHAR(800) NULL,

            source_table_name VARCHAR(160) NULL,
            yyyymm CHAR(6) NULL,

            last_query_time DATETIME NULL,

            create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,

            UNIQUE KEY uniq_source_group (
                source_op_id,
                sheet_id
            ),

            KEY idx_sheet (sheet_id),
            KEY idx_source_op (source_op_id),
            KEY idx_status (cache_status),
            KEY idx_yyyymm (yyyymm)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        with self.engine.begin() as conn:
            conn.execute(ddl)

    def save_source_group_state(self, df: pd.DataFrame):
        if df is None or df.empty:
            logging.info("[save_source_group_state] empty")
            return

        self.ensure_source_group_state_table()

        d = df.copy()

        datetime_cols = [
            "source_scan_time",
            "last_query_time",
            "create_time",
            "update_time",
        ]

        int_cols = [
            "source_defect_cnt",
        ]

        text_cols = [
            "source_op_id",
            "process",
            "station",
            "sheet_id",
            "cache_status",
            "cache_status_detail",
            "source_table_name",
            "yyyymm",
        ]

        d = clean_df_by_schema(
            d,
            datetime_cols=datetime_cols,
            int_cols=int_cols,
            text_cols=text_cols,
        )

        dedup_keys = ["source_op_id", "sheet_id"]

        logging.info(
            "[save_source_group_state] table=%s rows=%s dedup=%s",
            self.cfg.source_group_state_table,
            len(d),
            dedup_keys,
        )

        self.db.append_or_create_dedup(
            table_name=self.cfg.source_group_state_table,
            df=d,
            dedup_keys=dedup_keys,
        )
    
    def set_last_end_dt(self, end_dt: datetime):
        self.ensure_state_table()
        sql = text(f"""
        INSERT INTO {self.cfg.state_table}(job_name, last_end_dt)
        VALUES(:job, :end_dt)
        ON DUPLICATE KEY UPDATE last_end_dt=VALUES(last_end_dt)
        """)
        with self.engine.begin() as conn:
            conn.execute(sql, {"job": self.cfg.state_job_name, "end_dt": end_dt})

    def source_table_name(self, process: str, station: str, yyyymm: str) -> str:
        process = process.upper()
        station = station.upper()

        if process == "CF" and station == "OC":
            base = self.cfg.source_cf_oc_base
        elif process == "CF" and station == "PS":
            base = self.cfg.source_cf_ps_base
        elif process == "ARRAY" and station == "MOR":
            base = self.cfg.source_array_mor_base
        elif process == "ARRAY" and station == "TAR":
            base = self.cfg.source_array_tar_base
        elif process == "ARRAY" and station == "TOS":
            base = self.cfg.source_array_tos_base
        else:
            raise ValueError(f"Unsupported source table: process={process}, station={station}")

        return base.replace("yyyymm", yyyymm).lower()

    def same_point_table_name(self, yyyymm: str) -> str:
        return self.cfg.same_point_base.replace("yyyymm", yyyymm).lower()

    def glass_summary_table_name(self, yyyymm: str) -> str:
        return self.cfg.glass_summary_base.replace("yyyymm", yyyymm).lower()

    def api_aoi_summary_table_name(self, yyyymm: str) -> str:
        return self.cfg.api_aoi_summary_base.replace("yyyymm", yyyymm).lower()

    def ensure_cf_raw_table(self, table_name: str):
        ddl = text(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,

            sheet_id VARCHAR(50) NOT NULL,
            chip_id VARCHAR(50) NULL,
            model_no VARCHAR(80) NULL,
            scan_time DATETIME NULL,
            eqp_id VARCHAR(80) NULL,

            op VARCHAR(50) NULL,
            repair_time DATETIME NULL,
            repair_code VARCHAR(100) NULL,
            repair_eqp_id VARCHAR(100) NULL,
            repair_op VARCHAR(100) NULL,
            op_id VARCHAR(20) NULL,

            defect_no VARCHAR(50) NULL,
            defect_code VARCHAR(50) NULL,
            defect_size VARCHAR(50) NULL,
            defect_size_raw VARCHAR(200) NULL,

            ori_x DOUBLE NULL,
            ori_y DOUBLE NULL,
            trans_x DOUBLE NULL,
            trans_y DOUBLE NULL,

            image_name VARCHAR(500) NULL,
            img_url_path VARCHAR(1000) NULL,

            source_group_key VARCHAR(200) NULL,
            source_defect_uid VARCHAR(500) NULL,
            raw_json LONGTEXT NULL,

            create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

            INDEX idx_sheet_time (sheet_id, scan_time),
            INDEX idx_op_id (op_id),
            INDEX idx_group_key (source_group_key),
            INDEX idx_source_defect_uid (source_defect_uid),
            INDEX idx_coord (sheet_id, trans_x, trans_y)
        )
        """)

        with self.engine.begin() as conn:
            conn.execute(ddl)
            ensure_column_exists(conn, table_name, "source_defect_uid", "VARCHAR(500) NULL")
            ensure_index_exists(conn, table_name, "idx_source_defect_uid", "source_defect_uid")
            ensure_column_exists(conn, table_name, "defect_size_raw", "VARCHAR(200) NULL")

    def ensure_mor_raw_table(self, table_name: str):
        ddl = text(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,

            lot_id VARCHAR(80) NULL,
            model_no VARCHAR(120) NULL,
            scan_time DATETIME NULL,
            sheet_id VARCHAR(80) NOT NULL,
            chip_id VARCHAR(80) NULL,

            signal_no VARCHAR(80) NULL,
            gate_no VARCHAR(80) NULL,

            ori_x DOUBLE NULL,
            ori_y DOUBLE NULL,
            trans_x DOUBLE NULL,
            trans_y DOUBLE NULL,

            defect_size VARCHAR(200) NULL,
            defect_code VARCHAR(200) NULL,
            defect_size_raw VARCHAR(200) NULL,

            image_name VARCHAR(800) NULL,
            img_url_path VARCHAR(1500) NULL,

            op_id VARCHAR(80) NULL,
            recipe_id VARCHAR(200) NULL,
            eqp_id VARCHAR(120) NULL,

            source_group_key VARCHAR(300) NULL,
            source_defect_uid VARCHAR(500) NULL,
            raw_json LONGTEXT NULL,

            create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

            INDEX idx_sheet_time (sheet_id, scan_time),
            INDEX idx_op_id (op_id),
            INDEX idx_group_key (source_group_key),
            INDEX idx_source_defect_uid (source_defect_uid),
            INDEX idx_coord (sheet_id, trans_x, trans_y)
        )
        """)

        with self.engine.begin() as conn:
            conn.execute(ddl)
            ensure_column_exists(conn, table_name, "source_defect_uid", "VARCHAR(500) NULL")
            ensure_index_exists(conn, table_name, "idx_source_defect_uid", "source_defect_uid")
            ensure_column_exists(conn, table_name, "defect_size_raw", "VARCHAR(200) NULL")


    def ensure_tar_tos_raw_table(self, table_name: str):
        ddl = text(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,

            lot_id VARCHAR(80) NULL,
            model_no VARCHAR(120) NULL,
            sheet_id VARCHAR(80) NOT NULL,
            tool_id VARCHAR(120) NULL,
            chip_id VARCHAR(80) NULL,

            signal_no VARCHAR(80) NULL,
            gate_no VARCHAR(80) NULL,
            signal_gate_defect_code TEXT NULL,

            route VARCHAR(200) NULL,
            chip_seq_no VARCHAR(80) NULL,
            op_id VARCHAR(50) NULL,
            repair_time DATETIME NULL,

            defect_code VARCHAR(200) NULL,
            defect_size VARCHAR(200) NULL,
            defect_size_raw VARCHAR(200) NULL,

            ori_x DOUBLE NULL,
            ori_y DOUBLE NULL,
            trans_x DOUBLE NULL,
            trans_y DOUBLE NULL,

            tester_tool VARCHAR(200) NULL,

            ori_image_name VARCHAR(800) NULL,
            image_name VARCHAR(800) NULL,
            img_url_path VARCHAR(1500) NULL,

            source_group_key VARCHAR(300) NULL,
            source_defect_uid VARCHAR(500) NULL,
            raw_json LONGTEXT NULL,

            create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

            INDEX idx_sheet_time (sheet_id, repair_time),
            INDEX idx_op_id (op_id),
            INDEX idx_group_key (source_group_key),
            INDEX idx_source_defect_uid (source_defect_uid),
            INDEX idx_coord (sheet_id, trans_x, trans_y)
        )
        """)

        with self.engine.begin() as conn:
            conn.execute(ddl)
            ensure_column_exists(conn, table_name, "source_defect_uid", "VARCHAR(500) NULL")
            ensure_index_exists(conn, table_name, "idx_source_defect_uid", "source_defect_uid")
            ensure_column_exists(conn, table_name, "defect_size_raw", "VARCHAR(200) NULL")


    def ensure_same_point_table(self, table_name: str):
        ddl = text(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,

            sheet_id VARCHAR(50) NOT NULL,
            scan_time DATETIME NULL,
            model_no VARCHAR(80) NULL,
            abbr_cat VARCHAR(20) NULL,
            process VARCHAR(20) NULL,
            recipe_id VARCHAR(100) NULL,
            cassette_id VARCHAR(100) NULL,
            cell_aoi VARCHAR(50) NULL,
            cell_line_id VARCHAR(50) NULL,
            pi_time DATETIME NULL,
            cell_op VARCHAR(50) NULL,
            cell_defect_cnt INT NULL,

            source_op_id VARCHAR(50) NOT NULL,
            source_scan_time DATETIME NULL,
            source_defect_cnt INT NULL,

            same_point_offset DOUBLE NULL,
            same_point_defect_cnt INT NULL,
            same_point_rate DOUBLE NULL,

            point_detail LONGTEXT NULL,

            match_status VARCHAR(50) NULL,
            match_status_detail VARCHAR(500) NULL,

            create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

            INDEX idx_sheet_scan (sheet_id, scan_time),
            INDEX idx_process_op (process, source_op_id),
            INDEX idx_status (match_status),
            INDEX idx_rate (same_point_rate)
        )
        """)

        with self.engine.begin() as conn:
            conn.execute(ddl)

            conn.execute(text(f"""
            ALTER TABLE {table_name}
            MODIFY COLUMN point_detail LONGTEXT NULL
            """))

    def ensure_glass_summary_table(self, table_name: str):
        ddl = text(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,

            sheet_id VARCHAR(50) NOT NULL,
            scan_time DATETIME NULL,
            model_no VARCHAR(80) NULL,
            abbr_cat VARCHAR(20) NULL,
            process VARCHAR(20) NULL,
            recipe_id VARCHAR(100) NULL,
            cassette_id VARCHAR(100) NULL,
            cell_aoi VARCHAR(50) NULL,
            cell_line_id VARCHAR(50) NULL,
            pi_time DATETIME NULL,
            cell_op VARCHAR(50) NULL,

            cell_defect_cnt INT NULL,

            source_station_cnt INT DEFAULT 0,
            source_found_station_cnt INT DEFAULT 0,

            total_source_defect_cnt INT NULL,
            total_same_point_defect_cnt INT NULL,
            total_same_point_rate DOUBLE NULL,

            cf_oc_source_defect_cnt INT NULL,
            cf_ps_source_defect_cnt INT NULL,
            array_mor_source_defect_cnt INT NULL,
            array_tar_source_defect_cnt INT NULL,
            array_tos_source_defect_cnt INT NULL,

            cf_oc_same_point_cnt INT NULL,
            cf_ps_same_point_cnt INT NULL,
            array_mor_same_point_cnt INT NULL,
            array_tar_same_point_cnt INT NULL,
            array_tos_same_point_cnt INT NULL,

            judge VARCHAR(50) NULL,
            judge_detail VARCHAR(500) NULL,

            create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

            INDEX idx_sheet_scan (sheet_id, scan_time),
            INDEX idx_process (process),
            INDEX idx_judge (judge),
            INDEX idx_rate (total_same_point_rate)
        )
        """)
        with self.engine.begin() as conn:
            conn.execute(ddl)

    def ensure_api_aoi_summary_table(self, table_name: str):
        ddl = text(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,

            test_time DATETIME NULL,
            line_id VARCHAR(50) NULL,
            cassette_id VARCHAR(100) NULL,
            sheet_id_chip_id VARCHAR(50) NOT NULL,
            model_no VARCHAR(100) NULL,
            abbr_cat VARCHAR(20) NULL,
            recipe_id VARCHAR(100) NULL,
            aoi VARCHAR(50) NULL,
            total_defect_qty INT NULL,
            pi_time DATETIME NULL,
            pi_type VARCHAR(50) NULL,

            source_scan_time DATETIME NULL,
            source_op_id VARCHAR(50) NOT NULL,
            source_defect_cnt INT NULL,

            same_point_offset DOUBLE NULL,
            same_point_defect_cnt INT NULL,
            same_point_rate DOUBLE NULL,

            match_status VARCHAR(50) NULL,
            match_status_detail VARCHAR(500) NULL,

            comment TEXT NULL,
            action VARCHAR(200) NULL,
            modify_time DATETIME NULL,
            editor VARCHAR(100) NULL,

            create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

            INDEX idx_test_time (test_time),
            INDEX idx_sheet_pi (sheet_id_chip_id, pi_type),
            INDEX idx_sheet_time_station (sheet_id_chip_id, test_time, source_op_id),
            INDEX idx_abbr_cat (abbr_cat),
            INDEX idx_source_op (source_op_id),
            INDEX idx_status (match_status),
            INDEX idx_rate (same_point_rate)
        )
        """)
        with self.engine.begin() as conn:
            conn.execute(ddl)

    @staticmethod
    def _clean_numeric_columns(df: pd.DataFrame, int_cols: List[str], float_cols: List[str]) -> pd.DataFrame:
        """
        寫入 MySQL 前強制清理數值欄位：
        - INT 欄位：NaN / 'nan' / '' / None -> None，其餘轉 int
        - FLOAT 欄位：NaN / 'nan' / '' / None -> None，其餘轉 float
        """
        if df is None or df.empty:
            return df

        d = df.copy().astype(object)
        bad_strings = {"", "nan", "none", "null", "<na>", "nat", "inf", "-inf"}

        def to_int_or_none(v):
            if v is None:
                return None

            if isinstance(v, str):
                s = v.strip()
                if s.lower() in bad_strings:
                    return None
                v = s

            try:
                if pd.isna(v):
                    return None
            except Exception:
                pass

            try:
                n = pd.to_numeric(v, errors="coerce")
                if pd.isna(n):
                    return None
                return int(float(n))
            except Exception:
                return None

        def to_float_or_none(v):
            if v is None:
                return None

            if isinstance(v, str):
                s = v.strip()
                if s.lower() in bad_strings:
                    return None
                v = s

            try:
                if pd.isna(v):
                    return None
            except Exception:
                pass

            try:
                n = pd.to_numeric(v, errors="coerce")
                if pd.isna(n):
                    return None
                return float(n)
            except Exception:
                return None

        for col in int_cols:
            if col in d.columns:
                d[col] = d[col].map(to_int_or_none).astype(object)

        for col in float_cols:
            if col in d.columns:
                d[col] = d[col].map(to_float_or_none).astype(object)

        d = sanitize_mysql_df(d)

        for col in int_cols + float_cols:
            if col in d.columns:
                d[col] = d[col].apply(
                    lambda x: None
                    if isinstance(x, str) and x.strip().lower() in bad_strings
                    else x
                )

        return d.astype(object)

    @staticmethod
    def _force_zero_int_columns(df: pd.DataFrame, int_cols: List[str]) -> pd.DataFrame:
        """
        給 glass summary 這種 count 欄位使用。
        因為 append_or_create_dedup 內部 staging 可能把 None 轉成字串 'nan'，
        所以 count 類欄位統一固定為 0，避免寫入 INT 欄位失敗。
        """
        if df is None or df.empty:
            return df

        d = df.copy()

        for col in int_cols:
            if col not in d.columns:
                d[col] = 0
            d[col] = pd.to_numeric(d[col], errors="coerce").fillna(0).astype(int)

        return d

    @staticmethod
    def _force_zero_float_columns(df: pd.DataFrame, float_cols: List[str]) -> pd.DataFrame:
        if df is None or df.empty:
            return df

        d = df.copy()

        for col in float_cols:
            if col not in d.columns:
                d[col] = 0.0
            d[col] = pd.to_numeric(d[col], errors="coerce").fillna(0.0).astype(float)

        return d

    def save_source_raw(self, process: str, station: str, df: pd.DataFrame):
        if df is None or df.empty:
            logging.info("[save_source_raw] %s/%s empty", process, station)
            return

        d = df.copy()

        time_col = "scan_time" if process == "CF" or station == "MOR" else "repair_time"
        d[time_col] = pd.to_datetime(d.get(time_col), errors="coerce")
        d["yyyymm"] = d[time_col].dt.strftime("%Y%m").fillna(datetime.now().strftime("%Y%m"))

        for ym, g in d.groupby("yyyymm"):
            tb = self.source_table_name(process, station, str(ym))

            if process == "CF":
                self.ensure_cf_raw_table(tb)

                datetime_cols = [
                    "scan_time",
                    "repair_time",
                    "create_time",
                    "update_time",
                ]
                int_cols = []
                float_cols = [
                    "ori_x",
                    "ori_y",
                    "trans_x",
                    "trans_y",
                ]
                text_cols = [
                    "sheet_id",
                    "chip_id",
                    "model_no",
                    "eqp_id",
                    "op",
                    "repair_code",
                    "repair_eqp_id",
                    "repair_op",
                    "op_id",
                    "defect_no",
                    "defect_code",
                    "defect_size",
                    "defect_size_raw",
                    "image_name",
                    "img_url_path",
                    "source_group_key",
                    "source_defect_uid",
                ]
                json_cols = ["raw_json"]

                dedup_keys = [
                    "source_defect_uid",
                ]

            elif station == "MOR":
                self.ensure_mor_raw_table(tb)

                datetime_cols = [
                    "scan_time",
                    "create_time",
                    "update_time",
                ]
                int_cols = []
                float_cols = [
                    "ori_x",
                    "ori_y",
                    "trans_x",
                    "trans_y",
                ]
                text_cols = [
                    "lot_id",
                    "model_no",
                    "sheet_id",
                    "chip_id",
                    "signal_no",
                    "gate_no",
                    "defect_size",
                    "defect_size_raw",
                    "defect_code",
                    "image_name",
                    "img_url_path",
                    "op_id",
                    "recipe_id",
                    "eqp_id",
                    "source_group_key",
                    "source_defect_uid",
                ]
                json_cols = ["raw_json"]

                dedup_keys = [
                    "source_defect_uid",
                ]

            else:
                self.ensure_tar_tos_raw_table(tb)

                datetime_cols = [
                    "repair_time",
                    "create_time",
                    "update_time",
                ]
                int_cols = []
                float_cols = [
                    "ori_x",
                    "ori_y",
                    "trans_x",
                    "trans_y",
                ]
                text_cols = [
                    "lot_id",
                    "model_no",
                    "sheet_id",
                    "tool_id",
                    "chip_id",
                    "signal_no",
                    "gate_no",
                    "signal_gate_defect_code",
                    "route",
                    "chip_seq_no",
                    "op_id",
                    "defect_code",
                    "defect_size",
                    "defect_size_raw",
                    "tester_tool",
                    "ori_image_name",
                    "image_name",
                    "img_url_path",
                    "source_group_key",
                    "source_defect_uid",
                ]
                json_cols = ["raw_json"]

                dedup_keys = [
                    "source_defect_uid",
                ]


            g2 = g.drop(columns=["yyyymm"], errors="ignore").copy()

            # 關鍵：依 schema 清理，不讓 DATETIME 變成字串 'nan'
            g2 = clean_df_by_schema(
                g2,
                datetime_cols=datetime_cols,
                int_cols=int_cols,
                float_cols=float_cols,
                text_cols=text_cols,
                json_cols=json_cols,
            )

            dedup_keys = [c for c in dedup_keys if c in g2.columns]

            logging.info("[save_source_raw] table=%s rows=%s dedup=%s", tb, len(g2), dedup_keys)
            self.db.append_or_create_dedup(table_name=tb, df=g2, dedup_keys=dedup_keys)


    
    def save_same_point(self, df: pd.DataFrame):
        if df is None or df.empty:
            logging.info("[save_same_point] empty")
            return

        d = df.copy()
        d["scan_time"] = pd.to_datetime(d.get("scan_time"), errors="coerce")
        d["yyyymm"] = d["scan_time"].dt.strftime("%Y%m").fillna(datetime.now().strftime("%Y%m"))

        datetime_cols = [
            "scan_time",
            "pi_time",
            "source_scan_time",
            "create_time",
            "update_time",
        ]

        int_cols = [
            "cell_defect_cnt",
            "source_defect_cnt",
            "same_point_defect_cnt",
        ]

        float_cols = [
            "same_point_offset",
            "same_point_rate",
        ]

        text_cols = [
            "sheet_id",
            "model_no",
            "abbr_cat",
            "process",
            "recipe_id",
            "cassette_id",
            "cell_aoi",
            "cell_line_id",
            "cell_op",
            "source_op_id",
            "match_status",
            "match_status_detail",
        ]

        json_cols = ["point_detail"]

        d = clean_df_by_schema(
            d,
            datetime_cols=datetime_cols,
            int_cols=int_cols,
            float_cols=float_cols,
            text_cols=text_cols,
            json_cols=json_cols,
        )

        for ym, g in d.groupby("yyyymm"):
            tb = self.same_point_table_name(str(ym))
            self.ensure_same_point_table(tb)

            g2 = g.drop(columns=["yyyymm"], errors="ignore").copy()

            g2 = clean_df_by_schema(
                g2,
                datetime_cols=datetime_cols,
                int_cols=int_cols,
                float_cols=float_cols,
                text_cols=text_cols,
                json_cols=json_cols,
            )

            dedup_keys = ["sheet_id", "scan_time", "cell_op", "process", "source_op_id"]
            dedup_keys = [c for c in dedup_keys if c in g2.columns]

            logging.info("[save_same_point] table=%s rows=%s dedup=%s", tb, len(g2), dedup_keys)
            self.db.append_or_create_dedup(table_name=tb, df=g2, dedup_keys=dedup_keys)

    def save_glass_summary(self, df: pd.DataFrame):
        if df is None or df.empty:
            logging.info("[save_glass_summary] empty")
            return

        d = df.copy()
        d["scan_time"] = pd.to_datetime(d.get("scan_time"), errors="coerce")
        d["yyyymm"] = d["scan_time"].dt.strftime("%Y%m").fillna(datetime.now().strftime("%Y%m"))

        datetime_cols = [
            "scan_time",
            "pi_time",
            "create_time",
            "update_time",
        ]

        zero_int_cols = [
            "cell_defect_cnt",
            "source_station_cnt",
            "source_found_station_cnt",
            "total_source_defect_cnt",
            "total_same_point_defect_cnt",
            "cf_oc_source_defect_cnt",
            "cf_ps_source_defect_cnt",
            "array_mor_source_defect_cnt",
            "array_tar_source_defect_cnt",
            "array_tos_source_defect_cnt",
            "cf_oc_same_point_cnt",
            "cf_ps_same_point_cnt",
            "array_mor_same_point_cnt",
            "array_tar_same_point_cnt",
            "array_tos_same_point_cnt",
        ]

        zero_float_cols = [
            "total_same_point_rate",
        ]

        text_cols = [
            "sheet_id",
            "model_no",
            "abbr_cat",
            "process",
            "recipe_id",
            "cassette_id",
            "cell_aoi",
            "cell_line_id",
            "cell_op",
            "judge",
            "judge_detail",
        ]

        d = clean_df_by_schema(
            d,
            datetime_cols=datetime_cols,
            zero_int_cols=zero_int_cols,
            zero_float_cols=zero_float_cols,
            text_cols=text_cols,
        )

        for ym, g in d.groupby("yyyymm"):
            tb = self.glass_summary_table_name(str(ym))
            self.ensure_glass_summary_table(tb)

            g2 = g.drop(columns=["yyyymm"], errors="ignore").copy()

            g2 = clean_df_by_schema(
                g2,
                datetime_cols=datetime_cols,
                zero_int_cols=zero_int_cols,
                zero_float_cols=zero_float_cols,
                text_cols=text_cols,
            )

            dedup_keys = ["sheet_id", "scan_time", "cell_op"]
            dedup_keys = [c for c in dedup_keys if c in g2.columns]

            logging.info("[save_glass_summary] table=%s rows=%s dedup=%s", tb, len(g2), dedup_keys)
            self.db.append_or_create_dedup(table_name=tb, df=g2, dedup_keys=dedup_keys)


    def save_api_aoi_summary(self, df: pd.DataFrame):
        if df is None or df.empty:
            logging.info("[save_api_aoi_summary] empty")
            return

        d = df.copy()
        d["test_time"] = pd.to_datetime(d.get("test_time"), errors="coerce")
        d["yyyymm"] = d["test_time"].dt.strftime("%Y%m").fillna(datetime.now().strftime("%Y%m"))

        datetime_cols = [
            "test_time",
            "pi_time",
            "source_scan_time",
            "modify_time",
            "create_time",
            "update_time",
        ]

        int_cols = [
            "total_defect_qty",
            "source_defect_cnt",
            "same_point_defect_cnt",
        ]

        float_cols = [
            "same_point_offset",
            "same_point_rate",
        ]

        text_cols = [
            "line_id",
            "cassette_id",
            "sheet_id_chip_id",
            "model_no",
            "abbr_cat",
            "recipe_id",
            "aoi",
            "pi_type",
            "source_op_id",
            "match_status",
            "match_status_detail",
            "comment",
            "action",
            "editor",
        ]

        d = clean_df_by_schema(
            d,
            datetime_cols=datetime_cols,
            int_cols=int_cols,
            float_cols=float_cols,
            text_cols=text_cols,
        )

        for ym, g in d.groupby("yyyymm"):
            tb = self.api_aoi_summary_table_name(str(ym))
            self.ensure_api_aoi_summary_table(tb)

            g2 = g.drop(columns=["yyyymm"], errors="ignore").copy()

            # ETL 新增時不覆蓋使用者維護欄位
            g2 = g2.drop(
                columns=["comment", "action", "modify_time", "editor"],
                errors="ignore",
            )

            g2 = clean_df_by_schema(
                g2,
                datetime_cols=datetime_cols,
                int_cols=int_cols,
                float_cols=float_cols,
                text_cols=text_cols,
            )

            dedup_keys = ["sheet_id_chip_id", "pi_type", "test_time", "source_op_id"]
            dedup_keys = [c for c in dedup_keys if c in g2.columns]

            logging.info("[save_api_aoi_summary] table=%s rows=%s dedup=%s", tb, len(g2), dedup_keys)
            self.db.append_or_create_dedup(table_name=tb, df=g2, dedup_keys=dedup_keys)


# =============================================================================
# CF Extractor
# =============================================================================

class CFSourceExtractor:
    def __init__(self, oracle_db: OracleDBHandler, cfg: IncomingGovernanceConfig):
        self.oracle_db = oracle_db
        self.cfg = cfg

    def fetch_candidates(self, glass_ids: List[str]) -> pd.DataFrame:
        if not glass_ids:
            return pd.DataFrame()

        where_extra = """
        AND (
            TRIM(OP) IN ('OC', 'PS')
            OR TRIM(OP) = 'MVA'
        )
        """

        df = self.oracle_db.fetch_by_in_batches(
            table_name=self.cfg.cf_table,
            select_cols=self.cfg.cf_return_keys,
            in_col=self.cfg.cf_glass_col,
            values=glass_ids,
            where_extra_sql=where_extra,
            batch_size=self.cfg.oracle_batch_size,
        )

        if df.empty:
            return df

        df["glass_id"] = normalize_string_series(df["glass_id"])
        df["testing_date"] = pd.to_datetime(df.get("testing_date"), errors="coerce")
        return df

    @staticmethod
    def add_op_id(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()

        out = df.copy()
        out["op_norm"] = normalize_string_series(out.get("op", pd.Series(dtype=str))).str.upper()
        out["eqp_id_norm"] = normalize_string_series(out.get("eqp_id", pd.Series(dtype=str))).str.upper()

        out["op_id"] = None
        out["source_rule"] = "OTHER"

        m_oc = out["op_norm"].eq("OC")
        out.loc[m_oc, "op_id"] = "OC"
        out.loc[m_oc, "source_rule"] = "OP_OC"

        m_ps = out["op_norm"].eq("PS")
        out.loc[m_ps, "op_id"] = "PS"
        out.loc[m_ps, "source_rule"] = "OP_PS"

        m_mva_oc = out["op_norm"].eq("MVA") & out["eqp_id_norm"].eq("FAPAOI20")
        out.loc[m_mva_oc, "op_id"] = "OC"
        out.loc[m_mva_oc, "source_rule"] = "MVA_EQP_FAPAOI20_OC"

        m_mva_ps = out["op_norm"].eq("MVA") & out["eqp_id_norm"].eq("FAVAOI10")
        out.loc[m_mva_ps, "op_id"] = "PS"
        out.loc[m_mva_ps, "source_rule"] = "MVA_EQP_FAVAOI10_PS"

        return out

    def build_latest_groups(self, raw_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        if raw_df is None or raw_df.empty:
            return pd.DataFrame(), pd.DataFrame()

        d = self.add_op_id(raw_df)
        d["testing_date"] = pd.to_datetime(d.get("testing_date"), errors="coerce")

        anchors = d[d["op_id"].isin(["OC", "PS"])].copy()
        anchors = anchors.dropna(subset=["glass_id", "op_id", "testing_date"])

        if anchors.empty:
            return pd.DataFrame(), pd.DataFrame()

        latest = (
            anchors
            .groupby(["glass_id", "op_id"], as_index=False)["testing_date"]
            .max()
            .rename(columns={"testing_date": "latest_scan_time"})
        )

        group_rows = d.merge(
            latest,
            left_on=["glass_id", "testing_date"],
            right_on=["glass_id", "latest_scan_time"],
            how="inner",
            suffixes=("", "_anchor"),
        )

        if "op_id_anchor" in group_rows.columns:
            group_rows["op_id_final"] = group_rows["op_id_anchor"]
        else:
            group_rows["op_id_final"] = group_rows["op_id"]

        group_rows["op_id_final"] = group_rows["op_id_final"].astype(str).str.upper()

        oc = group_rows[group_rows["op_id_final"].eq("OC")].copy()
        ps = group_rows[group_rows["op_id_final"].eq("PS")].copy()

        return oc, ps

    def normalize_cf(self, df: pd.DataFrame, station: str) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()

        out = pd.DataFrame()

        out["sheet_id"] = normalize_string_series(df["glass_id"])
        out["chip_id"] = df.get("chip_id")
        out["model_no"] = df.get("model_no")
        out["scan_time"] = pd.to_datetime(df.get("testing_date"), errors="coerce")
        out["eqp_id"] = df.get("eqp_id")

        out["op"] = df.get("op")
        out["repair_time"] = pd.to_datetime(df.get("repair_date"), errors="coerce")
        out["repair_code"] = df.get("repair_code")
        out["repair_eqp_id"] = df.get("repair_eqp_id")
        out["repair_op"] = df.get("repair_op")
        out["op_id"] = station

        out["defect_no"] = df.get("defect_no")
        out["defect_code"] = df.get("defect_code")
        out["defect_size_raw"] = df.get("defect_size_type")
        out["defect_size"] = out["defect_size_raw"].apply(
            lambda v: normalize_defect_size_by_first_char(v, default="O")
        )
        
         #out["ori_x"] = pd.to_numeric(df.get("coord_x"), errors="coerce")
        #out["ori_y"] = pd.to_numeric(df.get("coord_y"), errors="coerce")

        out["ori_x"] = df.get("coord_x") 
        out["ori_y"] = df.get("coord_y") 

        out["image_name"] = out.apply(build_cf_image_name, axis=1)

        #out["ori_x"] = pd.to_numeric(df.get("coord_x"), errors="coerce")
        #out["ori_y"] = pd.to_numeric(df.get("coord_y"), errors="coerce")

        
        out["trans_x"] = pd.to_numeric(df.get("coord_y"), errors="coerce")
        out["trans_y"] = self.cfg.panel_height_um - pd.to_numeric(df.get("coord_x"), errors="coerce")

        #out["image_name"] = out.apply(build_cf_image_name, axis=1)
        out["img_url_path"] = out.apply(lambda r: build_cf_img_url(r, self.cfg), axis=1)

        out["source_group_key"] = (
            "CF|"
            + out["sheet_id"].astype(str)
            + "|"
            + out["op_id"].astype(str)
            + "|"
            + out["scan_time"].astype(str)
        )

        out["source_defect_uid"] = (
            "CF|"
            + out["sheet_id"].astype(str)
            + "|"
            + out["op_id"].astype(str)
            + "|"
            + out["scan_time"].astype(str)
            + "|"
            + out["chip_id"].astype(str)
            + "|"
            + out["defect_no"].astype(str)
            + "|"
            + out["defect_code"].astype(str)
            + "|"
            + out["defect_size"].astype(str)
            + "|"
            + out["ori_x"].astype(str)
            + "|"
            + out["ori_y"].astype(str)
            + "|"
            + out["image_name"].astype(str)
        )

        out["raw_json"] = df.apply(lambda r: json_dumps_safe(r.to_dict()), axis=1)

        return out
    
    def run(self, cf_cell_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        if cf_cell_df is None or cf_cell_df.empty:
            return pd.DataFrame(), pd.DataFrame()

        glass_ids = (
            cf_cell_df["sheet_id_chip_id"]
            .dropna()
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )

        logging.info("[CF] fetch candidates glass_count=%s", len(glass_ids))

        raw = self.fetch_candidates(glass_ids)
        logging.info("[CF] candidate rows=%s", len(raw))

        oc_raw, ps_raw = self.build_latest_groups(raw)
        logging.info("[CF] latest OC rows=%s PS rows=%s", len(oc_raw), len(ps_raw))

        oc = self.normalize_cf(oc_raw, "OC")
        ps = self.normalize_cf(ps_raw, "PS")

        oc_state = build_source_group_state_df(
            input_sheet_ids=glass_ids,
            source_df=oc,
            process="CF",
            station="OC",
        )

        ps_state = build_source_group_state_df(
            input_sheet_ids=glass_ids,
            source_df=ps,
            process="CF",
            station="PS",
        )

        state_df = pd.concat([oc_state, ps_state], ignore_index=True)

        write_size_debug_log(
            station_label="CF_OC",
            df=oc,
            sheet_col="sheet_id",
            time_col="scan_time",
            size_col="defect_size",
        )

        write_size_debug_log(
            station_label="CF_PS",
            df=ps,
            sheet_col="sheet_id",
            time_col="scan_time",
            size_col="defect_size",
        )

        logging.info("[CF] normalized OC rows=%s PS rows=%s", len(oc), len(ps))
        return oc, ps, state_df


# =============================================================================
# ARRAY Extractor
# =============================================================================

class ArraySourceExtractor:
    def __init__(self, oracle_db: OracleDBHandler, cfg: IncomingGovernanceConfig):
        self.oracle_db = oracle_db
        self.cfg = cfg

    def fetch_station(self, station_cfg: Dict[str, Any], sheet_ids: List[str]) -> pd.DataFrame:
        if not sheet_ids:
            return pd.DataFrame()

        where_extra = ""
        params_extra = {}

        if station_cfg.get("station") == "MOR":
            where_extra = " AND OP_KEY = :op_key "
            params_extra = {"op_key": station_cfg.get("op_filter_value", "PX1=MOR")}

        df = self.oracle_db.fetch_by_in_batches(
            table_name=station_cfg["source_table"],
            select_cols=station_cfg["return_keys"],
            in_col=station_cfg["glass_col"],
            values=sheet_ids,
            where_extra_sql=where_extra,
            params_extra=params_extra,
            batch_size=self.cfg.oracle_batch_size,
        )

        return safe_lower_columns(df)

    def build_latest_group(self, df: pd.DataFrame, station_cfg: Dict[str, Any]) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()

        d = df.copy()
        station = station_cfg["station"]
        glass_col = station_cfg["glass_col"].lower()
        time_col = station_cfg["time_col"].lower()

        d["sheet_id_norm"] = normalize_string_series(d[glass_col])
        d["source_time"] = pd.to_datetime(d[time_col], errors="coerce")
        d = d.dropna(subset=["sheet_id_norm", "source_time"])

        if d.empty:
            return pd.DataFrame()

        latest = (
            d.groupby(["sheet_id_norm"], as_index=False)["source_time"]
            .max()
            .rename(columns={"source_time": "latest_source_time"})
        )

        out = d.merge(
            latest,
            left_on=["sheet_id_norm", "source_time"],
            right_on=["sheet_id_norm", "latest_source_time"],
            how="inner",
        )

        out["station"] = station
        return out

    def normalize_mor(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()

        out = pd.DataFrame()

        out["lot_id"] = df.get("tft_lot_id")
        out["model_no"] = df.get("model_no")
        out["scan_time"] = pd.to_datetime(df.get("test_time"), errors="coerce")
        out["sheet_id"] = normalize_string_series(df.get("tft_sheet_id"))
        out["chip_id"] = df.get("tft_chip_id")

        out["signal_no"] = df.get("signal_no")
        out["gate_no"] = df.get("gate_no")

        out["ori_x"] = pd.to_numeric(df.get("pox_x"), errors="coerce")
        out["ori_y"] = pd.to_numeric(df.get("pox_y"), errors="coerce")

        out["trans_x"] = out["ori_x"]
        out["trans_y"] = self.cfg.panel_height_um - out["ori_y"]

        out["defect_size_raw"] = df.get("defect_size")
        out["defect_size"] = out["defect_size_raw"].apply(
            lambda v: normalize_defect_size_by_first_char(v, default="O")
        )

        out["defect_code"] = df.get("adc_repair_answers")

        out["image_name"] = df.get("image_file_name")

        # MOR source raw path，若 Oracle 沒有撈到 img_file_url_path，先給空字串
        if "img_file_url_path" in df.columns:
            out["img_file_url_path"] = df.get("img_file_url_path")
        else:
            out["img_file_url_path"] = ""

        out["img_url_path"] = out.apply(
            lambda r: build_mor_img_url(
                r.get("image_name"),
                r.get("img_file_url_path"),
                self.cfg,
            ),
            axis=1,
        )
        out["op_id"] = df.get("op_key")
        out["recipe_id"] = df.get("recipe_id")
        out["eqp_id"] = df.get("eqp_id")

        out["source_group_key"] = (
            "ARRAY|"
            + out["sheet_id"].astype(str)
            + "|"
            + out["op_id"].astype(str)
            + "|"
            + out["scan_time"].astype(str)
        )

        out["source_defect_uid"] = (
            "ARRAY|"
            + out["sheet_id"].astype(str)
            + "|"
            + out["op_id"].astype(str)
            + "|"
            + out["scan_time"].astype(str)
            + "|"
            + out["chip_id"].astype(str)
            + "|"
            + out["signal_no"].astype(str)
            + "|"
            + out["gate_no"].astype(str)
            + "|"
            + out["defect_code"].astype(str)
            + "|"
            + out["defect_size"].astype(str)
            + "|"
            + out["ori_x"].astype(str)
            + "|"
            + out["ori_y"].astype(str)
            + "|"
            + out["image_name"].astype(str)
        )

        out["raw_json"] = df.apply(lambda r: json_dumps_safe(r.to_dict()), axis=1)

        return out
    
    def normalize_tar_tos(self, df: pd.DataFrame, station: str) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()

        rows = df.to_dict(orient="records")
        for r in rows:
            r["image_name_new"] = build_tar_tos_image_name(r)

        d = pd.DataFrame(rows)

        out = pd.DataFrame()

        out["lot_id"] = d.get("lot_id")
        out["model_no"] = d.get("model_no")
        out["sheet_id"] = normalize_string_series(d.get("board_id"))
        out["tool_id"] = d.get("tool_id")
        out["chip_id"] = d.get("chip_id")

        out["signal_no"] = d.get("data_ax")
        out["gate_no"] = d.get("gate_ax")
        out["signal_gate_defect_code"] = d.get("dft_mode")

        out["route"] = d.get("route")
        out["chip_seq_no"] = d.get("chip_seq_no")
        out["op_id"] = station
        out["repair_time"] = pd.to_datetime(d.get("ddate_ttime"), errors="coerce")

        out["defect_code"] = d.get("retype")
        out["defect_size_raw"] = d.get("tar_judge")
        out["defect_size"] = out["defect_size_raw"].apply(
            lambda v: normalize_defect_size_by_first_char(v, default="O")
        )

        out["ori_x"] = pd.to_numeric(d.get("x_cord"), errors="coerce")
        out["ori_y"] = pd.to_numeric(d.get("y_cord"), errors="coerce")

        out["trans_x"] = out["ori_x"]
        out["trans_y"] = self.cfg.panel_height_um - out["ori_y"]

        out["tester_tool"] = d.get("tester_tool")

        if "ori_image_name" in d.columns:
            out["ori_image_name"] = d.get("ori_image_name")
        elif "image_name" in d.columns:
            out["ori_image_name"] = d.get("image_name")
        else:
            out["ori_image_name"] = None

        out["image_name"] = d.get("image_name_new")
        out["img_url_path"] = out.apply(lambda r: build_tar_tos_img_url(r, self.cfg), axis=1)

        out["source_group_key"] = (
            "ARRAY|"
            + out["sheet_id"].astype(str)
            + "|"
            + out["op_id"].astype(str)
            + "|"
            + out["repair_time"].astype(str)
        )

        out["source_defect_uid"] = (
            "ARRAY|"
            + out["sheet_id"].astype(str)
            + "|"
            + out["op_id"].astype(str)
            + "|"
            + out["repair_time"].astype(str)
            + "|"
            + out["chip_id"].astype(str)
            + "|"
            + out["signal_no"].astype(str)
            + "|"
            + out["gate_no"].astype(str)
            + "|"
            + out["defect_code"].astype(str)
            + "|"
            + out["defect_size"].astype(str)
            + "|"
            + out["ori_x"].astype(str)
            + "|"
            + out["ori_y"].astype(str)
            + "|"
            + out["image_name"].astype(str)
        )

        out["raw_json"] = d.apply(lambda r: json_dumps_safe(r.to_dict()), axis=1)

        return out


    def run(self, array_cell_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        if array_cell_df is None or array_cell_df.empty:
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        sheet_ids = (
            array_cell_df["sheet_id_chip_id"]
            .dropna()
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )

        mor_out = pd.DataFrame()
        tar_out = pd.DataFrame()
        tos_out = pd.DataFrame()

        for station_cfg in self.cfg.array_station_configs:
            station = station_cfg["station"]
            logging.info("[ARRAY:%s] fetch sheet_count=%s", station, len(sheet_ids))

            raw = self.fetch_station(station_cfg, sheet_ids)
            logging.info("[ARRAY:%s] raw rows=%s", station, len(raw))

            latest = self.build_latest_group(raw, station_cfg)
            logging.info("[ARRAY:%s] latest rows=%s", station, len(latest))

            if station == "MOR":
                mor_out = self.normalize_mor(latest)

                write_size_debug_log(
                    station_label="ARRAY_MOR",
                    df=mor_out,
                    sheet_col="sheet_id",
                    time_col="scan_time",
                    size_col="defect_size",
                )

                logging.info("[ARRAY:%s] normalized rows=%s", station, len(mor_out))
            elif station == "TAR":
                tar_out = self.normalize_tar_tos(latest, "TAR")

                write_size_debug_log(
                    station_label="ARRAY_TAR",
                    df=tar_out,
                    sheet_col="sheet_id",
                    time_col="repair_time",
                    size_col="defect_size",
                )

                logging.info("[ARRAY:%s] normalized rows=%s", station, len(tar_out))
            elif station == "TOS":
                tos_out = self.normalize_tar_tos(latest, "TOS")

                write_size_debug_log(
                    station_label="ARRAY_TOS",
                    df=tos_out,
                    sheet_col="sheet_id",
                    time_col="repair_time",
                    size_col="defect_size",
                )

                logging.info("[ARRAY:%s] normalized rows=%s", station, len(tos_out))

        mor_state = build_source_group_state_df(
            input_sheet_ids=sheet_ids,
            source_df=mor_out,
            process="ARRAY",
            station="MOR",
        )

        tar_state = build_source_group_state_df(
            input_sheet_ids=sheet_ids,
            source_df=tar_out,
            process="ARRAY",
            station="TAR",
        )

        tos_state = build_source_group_state_df(
            input_sheet_ids=sheet_ids,
            source_df=tos_out,
            process="ARRAY",
            station="TOS",
        )

        state_df = pd.concat([mor_state, tar_state, tos_state], ignore_index=True)

        return mor_out, tar_out, tos_out, state_df


# =============================================================================
# Same Point Builder
# =============================================================================

class SamePointBuilder:
    def __init__(self, cfg: IncomingGovernanceConfig):
        self.cfg = cfg

    @staticmethod
    def _source_time_col(station: str) -> str:
        return "repair_time" if station in {"TAR", "TOS"} else "scan_time"

    @staticmethod
    def _source_defect_uid(source_row: pd.Series, process: str, station: str) -> str:
        """
        建立單一 source defect 的唯一 key。

        source_group_key 只代表同 sheet / station / 最新量測時間，
        不代表單一 defect，所以不能直接當 unique key。
        """
        existed = clean_text(source_row.get("source_defect_uid"))
        if existed:
            return existed

        process = clean_text(process).upper()
        station = clean_text(station).upper()

        time_col = "repair_time" if station in {"TAR", "TOS"} else "scan_time"

        parts = [
            process,
            clean_text(source_row.get("sheet_id")),
            clean_text(source_row.get("op_id") or station),
            clean_text(source_row.get(time_col)),
            clean_text(source_row.get("chip_id")),
            clean_text(source_row.get("defect_no")),
            clean_text(source_row.get("signal_no")),
            clean_text(source_row.get("gate_no")),
            clean_text(source_row.get("defect_code")),
            clean_text(source_row.get("defect_size")),
            clean_text(source_row.get("ori_x")),
            clean_text(source_row.get("ori_y")),
            clean_text(source_row.get("image_name")),
        ]

        return "|".join(parts)
    @staticmethod
    def _source_station_display(process: str, station: str) -> str:
        if process == "ARRAY" and station == "MOR":
            return "PX1=MOR"
        return station

    def _base_cell_row(self, cell_row: pd.Series, source_op_id: str) -> Dict[str, Any]:
        abbr_cat = clean_text(cell_row.get("abbr_cat")).upper()
        process = process_from_abbr(abbr_cat)

        return {
            "sheet_id": clean_text(cell_row.get("sheet_id_chip_id")),
            "scan_time": cell_row.get("test_time"),
            "model_no": cell_row.get("model_no"),
            "abbr_cat": abbr_cat,
            "process": process,
            "recipe_id": cell_row.get("recipe_id"),
            "cassette_id": cell_row.get("cassette_id"),
            "cell_aoi": cell_row.get("aoi"),
            "cell_line_id": cell_row.get("line_id"),
            "pi_time": cell_row.get("pi_time"),
            "cell_op": cell_row.get("pi_type"),
            "cell_defect_cnt": int(cell_row.get("cell_defect_cnt", 0) or 0),
            "source_op_id": source_op_id,
        }

    def build(
        self,
        cell_glass_df: pd.DataFrame,
        cell_defect_df: pd.DataFrame,
        sources: Dict[Tuple[str, str], pd.DataFrame],
        source_state_df: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        if cell_glass_df is None or cell_glass_df.empty:
            return pd.DataFrame()

        cg = cell_glass_df.copy()
        cg["sheet_id_chip_id"] = normalize_string_series(cg["sheet_id_chip_id"])
        cg["test_time"] = pd.to_datetime(cg.get("test_time"), errors="coerce")

        if cell_defect_df is None:
            cell_defect_df = pd.DataFrame()

        cd = cell_defect_df.copy()
        if not cd.empty:
            cd["sheet_id_chip_id"] = normalize_string_series(cd["sheet_id_chip_id"])
            cd["test_time"] = pd.to_datetime(cd.get("test_time"), errors="coerce")

        if not cd.empty:
            cnt = (
                cd.groupby(["sheet_id_chip_id", "test_time"], as_index=False)
                .size()
                .rename(columns={"size": "cell_defect_cnt"})
            )
        else:
            cnt = pd.DataFrame(columns=["sheet_id_chip_id", "test_time", "cell_defect_cnt"])

        cg = cg.merge(
            cnt,
            on=["sheet_id_chip_id", "test_time"],
            how="left",
        )
        cg["cell_defect_cnt"] = cg["cell_defect_cnt"].fillna(0).astype(int)

        rows = []

        for _, cell_row in cg.iterrows():
            sheet_id = clean_text(cell_row.get("sheet_id_chip_id"))
            scan_time = cell_row.get("test_time")
            abbr_cat = clean_text(cell_row.get("abbr_cat")).upper()

            if abbr_cat == "CF":
                station_list = [("CF", "OC"), ("CF", "PS")]
                offset = self.cfg.cf_offset_um
            elif abbr_cat == "TFT":
                station_list = [("ARRAY", "MOR"), ("ARRAY", "TAR"), ("ARRAY", "TOS")]
                offset = self.cfg.array_offset_um
            else:
                row = self._base_cell_row(cell_row, "-")
                row.update({
                    "source_scan_time": None,
                    "source_defect_cnt": None,
                    "same_point_offset": None,
                    "same_point_defect_cnt": None,
                    "same_point_rate": None,
                    "point_detail": "[]",
                    "match_status": "INVALID_ABBR_CAT",
                    "match_status_detail": f"abbr_cat={abbr_cat}",
                })
                rows.append(row)
                continue

            cell_points = pd.DataFrame()
            if not cd.empty:
                cell_points = cd[
                    cd["sheet_id_chip_id"].eq(sheet_id)
                    & cd["test_time"].eq(scan_time)
                ].copy()

            for process, station in station_list:
                source_op_id = self._source_station_display(process, station)
                base = self._base_cell_row(cell_row, source_op_id)

                src = sources.get((process, station), pd.DataFrame())
                if src is None:
                    src = pd.DataFrame()

                stime_col = self._source_time_col(station)

                if not src.empty:
                    ssrc = src[src["sheet_id"].astype(str).str.strip().eq(sheet_id)].copy()
                else:
                    ssrc = pd.DataFrame()

                if ssrc.empty:
                    state_row = self._get_source_state(
                        source_state_df,
                        sheet_id=sheet_id,
                        process=process,
                        station=station,
                    )

                    cache_status = clean_text(state_row.get("cache_status")) if state_row is not None else ""
                    cache_detail = clean_text(state_row.get("cache_status_detail")) if state_row is not None else ""

                    if cache_status in {"CACHED_NO_DEFECT", "ORACLE_NO_DEFECT"}:
                        # 前站 group 有確認，但 defect = 0
                        base.update({
                            "source_scan_time": state_row.get("source_scan_time") if state_row is not None else None,
                            "source_defect_cnt": 0,
                            "same_point_offset": offset,
                            "same_point_defect_cnt": 0,
                            "same_point_rate": 0.0 if int(cell_row.get("cell_defect_cnt", 0) or 0) > 0 else None,
                            "point_detail": "[]",
                            "match_status": "NO_SOURCE_DEFECT",
                            "match_status_detail": cache_detail or f"source group exists but no defect for {source_op_id}",
                        })

                    elif cache_status == "ORACLE_QUERY_FAILED":
                        # 前站查詢失敗，不能算 0
                        base.update({
                            "source_scan_time": None,
                            "source_defect_cnt": None,
                            "same_point_offset": offset,
                            "same_point_defect_cnt": None,
                            "same_point_rate": None,
                            "point_detail": "[]",
                            "match_status": "SOURCE_QUERY_FAILED",
                            "match_status_detail": cache_detail or f"source query failed for {source_op_id}",
                        })

                    else:
                        # 沒有 source group，或目前只能確認 defect table 查不到 row
                        base.update({
                            "source_scan_time": state_row.get("source_scan_time") if state_row is not None else None,
                            "source_defect_cnt": None,
                            "same_point_offset": offset,
                            "same_point_defect_cnt": None,
                            "same_point_rate": None,
                            "point_detail": "[]",
                            "match_status": "SOURCE_NOT_FOUND",
                            "match_status_detail": cache_detail or f"no source defect group for {source_op_id}",
                        })

                    rows.append(base)
                    continue

                ssrc[stime_col] = pd.to_datetime(ssrc.get(stime_col), errors="coerce")
                source_scan_time = ssrc[stime_col].max()
                source_defect_cnt = len(ssrc)

                if cell_points.empty:
                    base.update({
                        "source_scan_time": source_scan_time,
                        "source_defect_cnt": int(source_defect_cnt),
                        "same_point_offset": offset,
                        "same_point_defect_cnt": None,
                        "same_point_rate": None,
                        "point_detail": "[]",
                        "match_status": "NO_CELL_DEFECT",
                        "match_status_detail": "no cell defect raw",
                    })
                    rows.append(base)
                    continue

                valid_cell = cell_points.dropna(subset=["cell_trans_x", "cell_trans_y"]).copy()
                valid_src = ssrc.dropna(subset=["trans_x", "trans_y"]).copy()

                if valid_cell.empty:
                    base.update({
                        "source_scan_time": source_scan_time,
                        "source_defect_cnt": int(source_defect_cnt),
                        "same_point_offset": offset,
                        "same_point_defect_cnt": None,
                        "same_point_rate": None,
                        "point_detail": "[]",
                        "match_status": "CELL_COORD_INVALID",
                        "match_status_detail": "cell defects exist but coordinates invalid",
                    })
                    rows.append(base)
                    continue

                if valid_src.empty:
                    base.update({
                        "source_scan_time": source_scan_time,
                        "source_defect_cnt": int(source_defect_cnt),
                        "same_point_offset": offset,
                        "same_point_defect_cnt": None,
                        "same_point_rate": None,
                        "point_detail": "[]",
                        "match_status": "SOURCE_COORD_INVALID",
                        "match_status_detail": "source defects exist but coordinates invalid",
                    })
                    rows.append(base)
                    continue

                 # -------------------------------------------------------------
                # CELL owner 視角配對邏輯：
                #
                # 目標：
                #   判斷 CELL AOI 量到的每一個 defect，
                #   是否可以在前製程 source defect 的 offset 範圍內找到對應點。
                #
                # 配對方式：
                #   1. 以 CELL defect 為主體逐點判斷。
                #   2. 每個 CELL defect 找 offset 範圍內最近的一個 source defect。
                #   3. 單一 CELL defect 若附近有多個 source defect，只算 1 個，取最近 source。
                #   4. 同一個 source defect 可以對應多個 CELL defect。
                #
                # 統計方式：
                #   same_point_defect_cnt = 可追溯到前製程的 CELL defect 數
                #   same_point_rate       = same_point_defect_cnt / cell_defect_cnt
                # -------------------------------------------------------------
                pair_rows = []
                matched_cell_uids = set()
                matched_source_uids = set()

                for _, c in valid_cell.iterrows():
                    cx = float(c["cell_trans_x"])
                    cy = float(c["cell_trans_y"])
                    cell_uid = clean_text(c.get("cell_defect_uid"))

                    if not cell_uid:
                        continue

                    temp = valid_src.copy()
                    temp["dx"] = (temp["trans_x"] - cx).abs()
                    temp["dy"] = (temp["trans_y"] - cy).abs()

                    # offset 判斷：目前使用矩形範圍 dx <= offset 且 dy <= offset
                    temp = temp[
                        (temp["dx"] <= offset)
                        & (temp["dy"] <= offset)
                    ].copy()

                    if temp.empty:
                        continue

                    temp["distance"] = np.sqrt(temp["dx"] ** 2 + temp["dy"] ** 2)
                    temp = temp.sort_values(["distance"])

                    # 單一 CELL defect 只取最近的一個 source defect
                    s = temp.iloc[0]
                    source_uid = self._source_defect_uid(s, process, station)

                    matched_cell_uids.add(cell_uid)

                    if source_uid:
                        # 只做 debug 統計，不限制 source 被多個 CELL defect 使用
                        matched_source_uids.add(source_uid)

                    source_detail = build_source_subtable_detail(
                        s,
                        process=process,
                        source_op_id=source_op_id,
                        source_scan_time=source_scan_time,
                    )

                    source_detail["source_defect_uid"] = source_uid
                    source_detail.setdefault("display", {})
                    source_detail["display"]["source_defect_uid"] = source_uid

                    cell_detail = {
                        "cell_defect_uid": cell_uid,
                        "chip_id": clean_text(c.get("chip_id")),
                        "defect_code": clean_text(c.get("adc_def_code")),
                        "retype_def_code": clean_text(c.get("retype_def_code")),
                        "defect_size": clean_text(c.get("defect_size")),
                        "ori_x": None if pd.isna(c.get("cell_ori_x")) else float(c.get("cell_ori_x")),
                        "ori_y": None if pd.isna(c.get("cell_ori_y")) else float(c.get("cell_ori_y")),
                        "trans_x": cx,
                        "trans_y": cy,
                        "image_name": clean_text(c.get("cell_image_name")) or clean_text(c.get("img_file_name")) or clean_text(c.get("image_file_name")),
                        "img_url_path": clean_text(c.get("cell_img_url_path")),
                    }

                    pair_rows.append({
                        "cell": cell_detail,
                        "source": source_detail,
                        "match": {
                            "offset": float(offset),
                            "dx": float(s.get("dx")),
                            "dy": float(s.get("dy")),
                            "distance": float(s.get("distance")),
                            "rank": 1,
                            "is_nearest": 1,
                        }
                    })

                # -------------------------------------------------------------
                # CELL owner 主指標：
                #
                #   same_point_defect_cnt = 可追溯到前製程的 CELL defect 數
                #   same_point_rate       = same_point_defect_cnt / CELL AOI defect 總數
                #
                # 輔助 debug：
                #   source_same_point_cnt = 被命中的 unique source defect 數
                # -------------------------------------------------------------
                cell_same_point_defect_cnt = len(matched_cell_uids)
                source_same_point_defect_cnt = len(matched_source_uids)

                same_point_defect_cnt = cell_same_point_defect_cnt

                cell_defect_cnt = int(cell_row.get("cell_defect_cnt", 0) or 0)

                if same_point_defect_cnt > 0:
                    rate = same_point_defect_cnt / cell_defect_cnt if cell_defect_cnt > 0 else None
                    status = "MATCHED"
                    detail = (
                        f"same_point_cnt={same_point_defect_cnt}; "
                        f"cell_same_point_cnt={cell_same_point_defect_cnt}; "
                        f"source_same_point_cnt={source_same_point_defect_cnt}; "
                        f"cell_defect_cnt={cell_defect_cnt}; "
                        f"source_defect_cnt={source_defect_cnt}; "
                        f"rate_def=cell_same_point_cnt/cell_defect_cnt"
                    )
                else:
                    rate = 0.0 if cell_defect_cnt > 0 else None
                    status = "NO_SAME_POINT"
                    detail = (
                        "source found but no same point; "
                        f"same_point_cnt={same_point_defect_cnt}; "
                        f"cell_same_point_cnt={cell_same_point_defect_cnt}; "
                        f"source_same_point_cnt={source_same_point_defect_cnt}; "
                        f"cell_defect_cnt={cell_defect_cnt}; "
                        f"source_defect_cnt={source_defect_cnt}; "
                        f"rate_def=cell_same_point_cnt/cell_defect_cnt"
                    )



                base.update({
                    "source_scan_time": source_scan_time,
                    "source_defect_cnt": int(source_defect_cnt),
                    "same_point_offset": offset,
                    "same_point_defect_cnt": int(same_point_defect_cnt),
                    "same_point_rate": rate,
                    "point_detail": json_dumps_safe(pair_rows),
                    "match_status": status,
                    "match_status_detail": detail,
                })
                rows.append(base)

        out = pd.DataFrame(rows)

        for c in ["scan_time", "pi_time", "source_scan_time"]:
            if c in out.columns:
                out[c] = pd.to_datetime(out[c], errors="coerce")

        return out

    @staticmethod
    def _cache_source_op_id(process: str, station: str) -> str:
        return to_cache_source_op_id(process, station)

    @staticmethod
    def _get_source_state(
        source_state_df: Optional[pd.DataFrame],
        *,
        sheet_id: str,
        process: str,
        station: str,
    ) -> Optional[pd.Series]:
        if source_state_df is None or source_state_df.empty:
            return None

        d = source_state_df.copy()

        if "sheet_id" not in d.columns or "source_op_id" not in d.columns:
            return None

        source_op_id = to_cache_source_op_id(process, station)

        d["sheet_id"] = normalize_string_series(d["sheet_id"])
        d["source_op_id"] = normalize_string_series(d["source_op_id"]).str.upper()

        m = d[
            d["sheet_id"].eq(clean_text(sheet_id))
            & d["source_op_id"].eq(source_op_id)
        ].copy()

        if m.empty:
            return None

        if "last_query_time" in m.columns:
            m["last_query_time"] = pd.to_datetime(m["last_query_time"], errors="coerce")
            m = m.sort_values("last_query_time")

        return m.iloc[-1]


# =============================================================================
# Summary Builders
# =============================================================================

class GlassSummaryBuilder:
    def build(self, same_point_df: pd.DataFrame) -> pd.DataFrame:
        if same_point_df is None or same_point_df.empty:
            return pd.DataFrame()

        d = same_point_df.copy()
        d["scan_time"] = pd.to_datetime(d.get("scan_time"), errors="coerce")

        base_cols = [
            "sheet_id", "scan_time", "model_no", "abbr_cat", "process",
            "recipe_id", "cassette_id", "cell_aoi", "cell_line_id",
            "pi_time", "cell_op", "cell_defect_cnt",
        ]

        for c in base_cols:
            if c not in d.columns:
                d[c] = None

        base = d[base_cols].drop_duplicates(
            subset=["sheet_id", "scan_time", "cell_op"]
        ).copy()

        def sum_count(x):
            vals = pd.to_numeric(x, errors="coerce")
            if vals.notna().sum() == 0:
                return 0
            return int(vals.fillna(0).sum())
        d["source_group_found_flag"] = d["match_status"].astype(str).str.upper().isin([
            "MATCHED",
            "NO_SAME_POINT",
            "NO_SOURCE_DEFECT",
            "SOURCE_COORD_INVALID",
        ]).astype(int)
        
        grp = (
            d.groupby(["sheet_id", "scan_time", "cell_op"], as_index=False)
            .agg(
                source_station_cnt=("source_op_id", "count"),
                source_found_station_cnt=("source_group_found_flag", "sum"),
                total_source_defect_cnt=("source_defect_cnt", sum_count),
                total_same_point_defect_cnt=("same_point_defect_cnt", sum_count),
            )
        )
        
        out = base.merge(grp, on=["sheet_id", "scan_time", "cell_op"], how="left")

        base_count_cols = [
            "cell_defect_cnt",
            "source_station_cnt",
            "source_found_station_cnt",
            "total_source_defect_cnt",
            "total_same_point_defect_cnt",
        ]

        for c in base_count_cols:
            if c not in out.columns:
                out[c] = 0
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0).astype(int)

        out["total_same_point_rate"] = np.where(
            out["cell_defect_cnt"].astype(float) > 0,
            out["total_same_point_defect_cnt"].astype(float) / out["cell_defect_cnt"].astype(float),
            0.0,
        )


        station_map = {
            "OC": ("cf_oc_source_defect_cnt", "cf_oc_same_point_cnt"),
            "PS": ("cf_ps_source_defect_cnt", "cf_ps_same_point_cnt"),
            "PX1=MOR": ("array_mor_source_defect_cnt", "array_mor_same_point_cnt"),
            "TAR": ("array_tar_source_defect_cnt", "array_tar_same_point_cnt"),
            "TOS": ("array_tos_source_defect_cnt", "array_tos_same_point_cnt"),
        }

        # 關鍵：站點 count 欄位預設 0，不用 None，避免 staging table 產生 'nan'
        for src_col, sp_col in station_map.values():
            out[src_col] = 0
            out[sp_col] = 0

        for _, r in d.iterrows():
            src_col, sp_col = station_map.get(clean_text(r.get("source_op_id")), (None, None))
            if not src_col:
                continue

            m = (
                out["sheet_id"].eq(r["sheet_id"])
                & out["scan_time"].eq(r["scan_time"])
                & out["cell_op"].eq(r["cell_op"])
            )

            src_cnt = pd.to_numeric(r.get("source_defect_cnt"), errors="coerce")
            sp_cnt = pd.to_numeric(r.get("same_point_defect_cnt"), errors="coerce")

            out.loc[m, src_col] = 0 if pd.isna(src_cnt) else int(src_cnt)
            out.loc[m, sp_col] = 0 if pd.isna(sp_cnt) else int(sp_cnt)

        station_count_cols = []
        for src_col, sp_col in station_map.values():
            station_count_cols.append(src_col)
            station_count_cols.append(sp_col)

        for c in station_count_cols:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0).astype(int)

        def judge_row(r):
            if clean_text(r.get("abbr_cat")).upper() not in {"CF", "TFT"}:
                return "INVALID_ABBR_CAT"

            if int(r.get("cell_defect_cnt") or 0) == 0:
                return "NO_CELL_DEFECT"

            found = int(r.get("source_found_station_cnt") or 0)
            same = int(r.get("total_same_point_defect_cnt") or 0)
            total_source = int(r.get("total_source_defect_cnt") or 0)

            if same > 0:
                return "MATCHED"

            if found > 0 and total_source == 0:
                return "NO_SOURCE_DEFECT"

            if found > 0 and total_source > 0:
                return "NO_SAME_POINT"

            return "SOURCE_NOT_FOUND"

        out["judge"] = out.apply(judge_row, axis=1)

        out["judge_detail"] = (
            "cell_defect_cnt=" + out["cell_defect_cnt"].astype(str)
            + "; source_found_station_cnt=" + out["source_found_station_cnt"].astype(str)
            + "; total_source_defect_cnt=" + out["total_source_defect_cnt"].astype(str)
            + "; total_same_point_defect_cnt=" + out["total_same_point_defect_cnt"].astype(str)
        )

        final_cols = [
            "sheet_id", "scan_time", "model_no", "abbr_cat", "process",
            "recipe_id", "cassette_id", "cell_aoi", "cell_line_id",
            "pi_time", "cell_op", "cell_defect_cnt",

            "source_station_cnt", "source_found_station_cnt",
            "total_source_defect_cnt", "total_same_point_defect_cnt", "total_same_point_rate",

            "cf_oc_source_defect_cnt", "cf_ps_source_defect_cnt",
            "array_mor_source_defect_cnt", "array_tar_source_defect_cnt", "array_tos_source_defect_cnt",

            "cf_oc_same_point_cnt", "cf_ps_same_point_cnt",
            "array_mor_same_point_cnt", "array_tar_same_point_cnt", "array_tos_same_point_cnt",

            "judge", "judge_detail",
        ]

        for c in final_cols:
            if c not in out.columns:
                if c.endswith("_cnt") or c in {
                    "cell_defect_cnt",
                    "source_station_cnt",
                    "source_found_station_cnt",
                    "total_source_defect_cnt",
                    "total_same_point_defect_cnt",
                }:
                    out[c] = 0
                elif c == "total_same_point_rate":
                    out[c] = 0.0
                else:
                    out[c] = None

        count_cols = [
            "cell_defect_cnt",
            "source_station_cnt",
            "source_found_station_cnt",
            "total_source_defect_cnt",
            "total_same_point_defect_cnt",
            "cf_oc_source_defect_cnt",
            "cf_ps_source_defect_cnt",
            "array_mor_source_defect_cnt",
            "array_tar_source_defect_cnt",
            "array_tos_source_defect_cnt",
            "cf_oc_same_point_cnt",
            "cf_ps_same_point_cnt",
            "array_mor_same_point_cnt",
            "array_tar_same_point_cnt",
            "array_tos_same_point_cnt",
        ]

        for c in count_cols:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0).astype(int)

        out["total_same_point_rate"] = pd.to_numeric(
            out["total_same_point_rate"],
            errors="coerce",
        ).fillna(0.0).astype(float)

        bad = out[
            (out["total_same_point_defect_cnt"] > out["cell_defect_cnt"])
            | (out["cf_oc_same_point_cnt"] > out["cell_defect_cnt"])
            | (out["cf_ps_same_point_cnt"] > out["cell_defect_cnt"])
            | (out["array_mor_same_point_cnt"] > out["cell_defect_cnt"])
            | (out["array_tar_same_point_cnt"] > out["cell_defect_cnt"])
            | (out["array_tos_same_point_cnt"] > out["cell_defect_cnt"])
        ]

        if not bad.empty:
            logging.warning(
                "[GlassSummaryBuilder] same_point_cnt > cell_defect_cnt abnormal rows=%s sample=%s",
                len(bad),
                bad[
                    [
                        "sheet_id",
                        "scan_time",
                        "cell_op",
                        "cell_defect_cnt",
                        "total_source_defect_cnt",
                        "total_same_point_defect_cnt",
                        "array_mor_same_point_cnt",
                        "array_tar_same_point_cnt",
                        "array_tos_same_point_cnt",
                    ]
                ].head(10).to_dict(orient="records"),
            )
        return out[final_cols].copy()

class ApiAoiSummaryBuilder:
    """
    產出前端主表 api_aoi_summary_yyyymm。
    粒度：
        sheet_id_chip_id + pi_type + test_time + source_op_id

    來源：
        same_point_df + 最新 CELL 母體欄位
    """
    def build(self, same_point_df: pd.DataFrame, cell_glass_df: pd.DataFrame) -> pd.DataFrame:
        if same_point_df is None or same_point_df.empty:
            return pd.DataFrame()

        sp = same_point_df.copy()
        sp["scan_time"] = pd.to_datetime(sp.get("scan_time"), errors="coerce")

        cg = cell_glass_df.copy()
        cg["sheet_id_chip_id"] = normalize_string_series(cg["sheet_id_chip_id"])
        cg["test_time"] = pd.to_datetime(cg.get("test_time"), errors="coerce")

        if "pi_type" not in cg.columns:
            cg["pi_type"] = ""
        cg["pi_type"] = normalize_string_series(cg["pi_type"]).str.upper()

        keep_cell_cols = [
            "test_time",
            "line_id",
            "cassette_id",
            "sheet_id_chip_id",
            "model_no",
            "abbr_cat",
            "recipe_id",
            "aoi",
            "total_defect_qty",
            "pi_time",
            "pi_type",
        ]

        for c in keep_cell_cols:
            if c not in cg.columns:
                cg[c] = None

        cell_base = cg[keep_cell_cols].drop_duplicates(
            subset=["sheet_id_chip_id", "pi_type", "test_time"]
        ).copy()

        out = sp.rename(columns={
            "sheet_id": "sheet_id_chip_id",
            "scan_time": "test_time",
            "cell_op": "pi_type",
        }).copy()

        out["sheet_id_chip_id"] = normalize_string_series(out["sheet_id_chip_id"])
        out["test_time"] = pd.to_datetime(out["test_time"], errors="coerce")
        out["pi_type"] = normalize_string_series(out["pi_type"]).str.upper()

        metric_cols = [
            "sheet_id_chip_id",
            "test_time",
            "pi_type",
            "source_scan_time",
            "source_op_id",
            "source_defect_cnt",
            "same_point_offset",
            "same_point_defect_cnt",
            "same_point_rate",
            "match_status",
            "match_status_detail",
        ]

        for c in metric_cols:
            if c not in out.columns:
                out[c] = None

        metric = out[metric_cols].copy()

        api = cell_base.merge(
            metric,
            on=["sheet_id_chip_id", "pi_type", "test_time"],
            how="inner",
        )

        api["comment"] = None
        api["action"] = None
        api["modify_time"] = None
        api["editor"] = None

        final_cols = [
            "test_time",
            "line_id",
            "cassette_id",
            "sheet_id_chip_id",
            "model_no",
            "abbr_cat",
            "recipe_id",
            "aoi",
            "total_defect_qty",
            "pi_time",
            "pi_type",

            "source_scan_time",
            "source_op_id",
            "source_defect_cnt",
            "same_point_offset",
            "same_point_defect_cnt",
            "same_point_rate",
            "match_status",
            "match_status_detail",

            "comment",
            "action",
            "modify_time",
            "editor",
        ]

        for c in final_cols:
            if c not in api.columns:
                api[c] = None

        return api[final_cols].copy()


# =============================================================================
# Pipeline
# =============================================================================

class IncomingGovernancePipelineV3:
    def __init__(
        self,
        cfg: IncomingGovernanceConfig,
        cell_repo: CellInputRepository,
        output_repo: OutputRepository,
        cf_extractor: CFSourceExtractor,
        array_extractor: ArraySourceExtractor,
        same_point_builder: SamePointBuilder,
        glass_summary_builder: GlassSummaryBuilder,
        api_aoi_summary_builder: ApiAoiSummaryBuilder,
    ):
        self.cfg = cfg
        self.cell_repo = cell_repo
        self.output_repo = output_repo
        self.cf_extractor = cf_extractor
        self.array_extractor = array_extractor
        self.same_point_builder = same_point_builder
        self.glass_summary_builder = glass_summary_builder
        self.api_aoi_summary_builder = api_aoi_summary_builder

    def run(self, start_dt: datetime, end_dt: datetime):
        logging.info("[Pipeline] start_dt=%s end_dt=%s", start_dt, end_dt)

        cell_glass_df_all = self.cell_repo.load_cell_glass(start_dt, end_dt)
        logging.info("[Pipeline] cell_glass_all rows=%s", len(cell_glass_df_all))

        if cell_glass_df_all.empty:
            logging.info("[Pipeline] no cell glass rows")
            self.output_repo.set_last_end_dt(end_dt)
            return

        cell_glass_df = latest_cell_by_sheet_pi_type(cell_glass_df_all)
        logging.info("[Pipeline] latest cell_glass by sheet+pi_type rows=%s", len(cell_glass_df))

        if "abbr_cat" not in cell_glass_df.columns:
            cell_glass_df["abbr_cat"] = ""

        cf_cell_df = cell_glass_df[cell_glass_df["abbr_cat"].astype(str).str.upper().eq("CF")].copy()
        array_cell_df = cell_glass_df[cell_glass_df["abbr_cat"].astype(str).str.upper().eq("TFT")].copy()

        logging.info("[Pipeline] cf_cell rows=%s array_cell rows=%s", len(cf_cell_df), len(array_cell_df))

        cf_oc_df, cf_ps_df, cf_state_df = self.cf_extractor.run(cf_cell_df)
        arr_mor_df, arr_tar_df, arr_tos_df, array_state_df = self.array_extractor.run(array_cell_df)
        
        self.output_repo.save_source_raw("CF", "OC", cf_oc_df)
        self.output_repo.save_source_raw("CF", "PS", cf_ps_df)
        self.output_repo.save_source_raw("ARRAY", "MOR", arr_mor_df)
        self.output_repo.save_source_raw("ARRAY", "TAR", arr_tar_df)
        self.output_repo.save_source_raw("ARRAY", "TOS", arr_tos_df)

        source_state_df = pd.concat(
            [
                cf_state_df if cf_state_df is not None else pd.DataFrame(),
                array_state_df if array_state_df is not None else pd.DataFrame(),
            ],
            ignore_index=True,
        )

        self.output_repo.save_source_group_state(source_state_df)

        cell_defect_df = self.cell_repo.load_cell_defects(cell_glass_df)

        write_size_debug_log(
            station_label="CELL_AOI",
            df=cell_defect_df,
            sheet_col="sheet_id_chip_id",
            time_col="test_time",
            size_col="defect_size",
        )

        logging.info("[Pipeline] cell_defect rows=%s", len(cell_defect_df))

        sources = {
            ("CF", "OC"): cf_oc_df,
            ("CF", "PS"): cf_ps_df,
            ("ARRAY", "MOR"): arr_mor_df,
            ("ARRAY", "TAR"): arr_tar_df,
            ("ARRAY", "TOS"): arr_tos_df,
        }

        same_point_df = self.same_point_builder.build(
            cell_glass_df=cell_glass_df,
            cell_defect_df=cell_defect_df,
            sources=sources,
            source_state_df=source_state_df,
        )
        logging.info("[Pipeline] same_point station rows=%s", len(same_point_df))

        self.output_repo.save_same_point(same_point_df)

        summary_df = self.glass_summary_builder.build(same_point_df)
        logging.info("[Pipeline] glass_summary rows=%s", len(summary_df))
        self.output_repo.save_glass_summary(summary_df)

        api_summary_df = self.api_aoi_summary_builder.build(
            same_point_df=same_point_df,
            cell_glass_df=cell_glass_df,
        )
        logging.info("[Pipeline] api_aoi_summary rows=%s", len(api_summary_df))
        self.output_repo.save_api_aoi_summary(api_summary_df)

        self.output_repo.set_last_end_dt(end_dt)
        logging.info("[Pipeline] done")


# =============================================================================
# Runner
# =============================================================================

def build_pipeline() -> IncomingGovernancePipelineV3:
    cfg = IncomingGovernanceConfig()
    oracle_cfg = OracleConfig()

    cell_input_db = MySQLConnet(cfg.cell_input_db_name)
    output_db = MySQLConnet(cfg.output_db_name)

    cell_repo = CellInputRepository(cell_input_db, cfg)
    output_repo = OutputRepository(output_db, cfg)

    cf_oracle = OracleDBHandler(oracle_cfg.cf_url)
    array_oracle = OracleDBHandler(oracle_cfg.array_url)

    cf_extractor = CFSourceExtractor(cf_oracle, cfg)
    array_extractor = ArraySourceExtractor(array_oracle, cfg)
    same_point_builder = SamePointBuilder(cfg)
    glass_summary_builder = GlassSummaryBuilder()
    api_aoi_summary_builder = ApiAoiSummaryBuilder()

    return IncomingGovernancePipelineV3(
        cfg=cfg,
        cell_repo=cell_repo,
        output_repo=output_repo,
        cf_extractor=cf_extractor,
        array_extractor=array_extractor,
        same_point_builder=same_point_builder,
        glass_summary_builder=glass_summary_builder,
        api_aoi_summary_builder=api_aoi_summary_builder,
    )


def one_run(
    pipe: IncomingGovernancePipelineV3,
    *,
    start_dt: Optional[datetime] = None,
    end_dt: Optional[datetime] = None,
    lookback_hour: int = 6,
    lag_min: int = 2,
):
    now = datetime.now()

    if end_dt is None:
        end_dt = now - timedelta(minutes=lag_min)

    if start_dt is None:
        start_dt = end_dt - timedelta(hours=lookback_hour)

    pipe.run(start_dt=start_dt, end_dt=end_dt)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--once", action="store_true", help="Run once then exit.")
    parser.add_argument("--every-min", type=int, default=10, help="Loop interval minutes.")
    parser.add_argument("--lookback-hour", type=int, default=6, help="Default lookback hours.")
    parser.add_argument("--lag-min", type=int, default=2, help="End time lag minutes.")

    parser.add_argument("--start-time", type=str, default=None, help='Format: "YYYY-MM-DD HH24:MI:SS"')
    parser.add_argument("--end-time", type=str, default=None, help='Format: "YYYY-MM-DD HH24:MI:SS"')

    args = parser.parse_args()

    setup_logging(log_dir="logs", log_name="cell_incoming_governance_V5.txt")
    logging.info("=== CELL Incoming Governance V3 start ===")

    pipe = build_pipeline()

    start_dt = parse_dt(args.start_time)
    end_dt = parse_dt(args.end_time)

    if args.once:
        try:
            one_run(
                pipe,
                start_dt=start_dt,
                end_dt=end_dt,
                lookback_hour=args.lookback_hour,
                lag_min=args.lag_min,
            )
        except Exception:
            logging.exception("[main] run failed")
        logging.info("=== CELL Incoming Governance V3 end once ===")
        return

    every_sec = max(1, int(args.every_min) * 60)

    while True:
        t0 = time.time()

        try:
            one_run(
                pipe,
                start_dt=start_dt,
                end_dt=end_dt,
                lookback_hour=args.lookback_hour,
                lag_min=args.lag_min,
            )
        except Exception:
            logging.exception("[main] run failed loop")

        elapsed = time.time() - t0
        sleep_sec = max(0.0, every_sec - elapsed)
        time.sleep(sleep_sec)


if __name__ == "__main__":
    main()

"""
python RUN_CELL_INCOMING_GOVERNANCE_V5.py --once --start-time "2026-07-05 08:00:00" --end-time "2026-07-07 10:00:00"
python RUN_CELL_INCOMING_GOVERNANCE_V5.py --once --start-time "2026-06-16 12:00:00" --end-time "2026-06-16 15:00:00"
"""


   
"""
CELL defect = 210
前站 defect = 1
有 36 個 CELL defect 都在該前站 defect offset 範圍內
same_point_defect_cnt = 36
same_point_rate = 36 / 210 = 17.14%
same_point_defect_cnt = 有找到前站對應點的 CELL defect 數
same_point_rate       = same_point_defect_cnt / cell_defect_cnt
CELL 看到的 210 個 defect 中，有 36 個附近存在前製程 defect，可視為可追溯前製程。

單一 CELL defect 對多個前站 defect → 算 1 點
多個 CELL defect 對同一個前站 defect → 算多點，以 CELL defect 數計

"""