# -*- coding: utf-8 -*-
"""
RUN_CELL_INSPECTION_INCOMING_GOVERNANCE.py

Inspection 來料檢資料治理工程 V1

目標：
    Inspection defect
        ↓
    直接追溯：
        AOI_BPI / AOI_API / CF_OC / CF_PS / ARRAY_MOR / ARRAY_TAR / ARRAY_TOS

讀取：
    MySQL piaoi_inspection_density
        - inspection_summary_table_yyyymm
        - inspection_raw_table_yyyymm

    MySQL cim_piaoi
        - cim_pi_glass_yyyymm
        - cim_defect_yyyymm_aoi_line

    MySQL cim_cell_aoi_to_array
        - incoming_source_cf_oc_defect_raw_yyyymm
        - incoming_source_cf_ps_defect_raw_yyyymm
        - incoming_source_array_mor_defect_raw_yyyymm
        - incoming_source_array_tar_defect_raw_yyyymm
        - incoming_source_array_tos_defect_raw_yyyymm
        - incoming_source_group_state

    Oracle CF / ARRAY
        - PIS2C10RPT.M_AOI_DEFT
        - L10HARY.H_AIDI_SECDEFECT
        - AT.ALR_RPF
        - AT.TOS_RPF

寫入：
    MySQL cim_cell_inspec_to_array
        - incoming_inspection_same_point_detail_yyyymm
        - incoming_inspection_glass_summary_yyyymm
        - api_inspection_summary_yyyymm
        - incoming_inspection_governance_state

使用：
    python RUN_CELL_INSPECTION_INCOMING_GOVERNANCE.py --once --start-time "2026-06-24 09:00:00" --end-time "2026-06-24 12:00:00"

    python RUN_CELL_INSPECTION_INCOMING_GOVERNANCE.py --once --lookback-hour 6

    python RUN_CELL_INSPECTION_INCOMING_GOVERNANCE.py --every-min 10 --lookback-hour 6
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
    log_name: str = "inspection_incoming_governance.txt",
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
class InspectionIncomingConfig:
    # MySQL DB
    inspection_input_db_name: str = "piaoi_inspection_density"
    aoi_input_db_name: str = "cim_piaoi"
    source_cache_db_name: str = "cim_cell_aoi_to_array"
    output_db_name: str = "cim_cell_inspec_to_array"

    # Inspection input tables
    inspection_summary_base: str = "inspection_summary_table_yyyymm"
    inspection_raw_base: str = "inspection_raw_table_yyyymm"

    # AOI source tables
    aoi_summary_base: str = "cim_pi_glass_yyyymm"
    aoi_defect_prefix_template: str = "cim_defect_yyyymm_"

    # CF / ARRAY source raw cache tables in cim_cell_aoi_to_array
    source_cf_oc_base: str = "incoming_source_cf_oc_defect_raw_yyyymm"
    source_cf_ps_base: str = "incoming_source_cf_ps_defect_raw_yyyymm"

    source_array_mor_base: str = "incoming_source_array_mor_defect_raw_yyyymm"
    source_array_tar_base: str = "incoming_source_array_tar_defect_raw_yyyymm"
    source_array_tos_base: str = "incoming_source_array_tos_defect_raw_yyyymm"

    source_group_state_table: str = "incoming_source_group_state"

    # Output tables in cim_cell_inspec_to_array
    same_point_base: str = "incoming_inspection_same_point_detail_yyyymm"
    glass_summary_base: str = "incoming_inspection_glass_summary_yyyymm"
    api_inspection_summary_base: str = "api_inspection_summary_yyyymm"

    state_table: str = "incoming_inspection_governance_state"
    state_job_name: str = "inspection_incoming_governance"

    # Matching offset
    aoi_offset_um: float = 1000.0
    cf_offset_um: float = 3000.0
    array_offset_um: float = 1000.0

    # Panel / mapping height
    panel_height_um: float = 1500000.0

    # Source lookup range for monthly raw cache table
    source_lookup_days: int = 120
    aoi_lookup_days: int = 120

    # AOI machine mapping
    aoi_map: Dict[str, str] = field(default_factory=lambda: {
        "CAPIT203": "aoi100",
        "CAAOI202": "aoi200",
        "CAAOI300": "aoi300",
    })

    # Image URL base
    cell_aidi_url: str = "http://l6apaimg103/dms/CELAIDI_L6A/"
    cf_img_base: str = "http://10.97.148.181/faaint10/"
    mor_img_base: str = "http://l6apaimg103/dms/ARYAOI_L6A/"
    tar_tos_img_base: str = "http://tcweb002.corpnet.auo.com/aaimf001/aalsr/"

    # Batch
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

    # ARRAY Oracle
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


def normalize_string_series(s: pd.Series) -> pd.Series:
    return s.astype("string").fillna("").str.strip()


def normalize_defect_size_by_first_char(v: Any, default: str = "O") -> str:
    s = clean_text(v).upper()
    if not s:
        return default
    first = s[0]
    if first in {"S", "M", "L", "O"}:
        return first
    return default


def normalize_cell_defect_size(v: Any, *, aoi_token: str = "") -> str:
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


def row_to_dict_safe(row: pd.Series) -> Dict[str, Any]:
    if row is None:
        return {}
    return {str(k): normalize_source_raw_value(v) for k, v in row.to_dict().items()}


def join_url_path(base: str, path: str) -> str:
    b = clean_text(base)
    p = clean_text(path)

    if not b:
        return p
    if not p:
        return b

    return b.rstrip("/") + "/" + p.lstrip("/")


def build_complete_img_url(pic_path: Any, pic_name: Any = "") -> str:
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


def safe_image_filename_from_url_or_path(v: Any) -> str:
    s = clean_text(v)
    if not s:
        return ""

    s = s.replace("\\", "/")
    s = s.split("?")[0].split("#")[0]
    return s.rstrip("/").split("/")[-1]


def process_from_glass_type(glass_type: Any) -> str:
    s = clean_text(glass_type).upper()
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


def display_source_op_id(process: str, station: str) -> str:
    process = clean_text(process).upper()
    station = clean_text(station).upper()

    if process == "ARRAY" and station == "MOR":
        return "PX1=MOR"

    return station


def build_source_group_state_df(
    *,
    input_sheet_ids: List[str],
    source_df: pd.DataFrame,
    process: str,
    station: str,
    cache_status_when_missing: str = "ORACLE_NOT_FOUND",
    status_detail_when_missing: str = "",
) -> pd.DataFrame:
    sheet_ids = sorted({clean_text(s) for s in input_sheet_ids if clean_text(s)})
    source_op_id = to_cache_source_op_id(process, station)
    display_op_id = display_source_op_id(process, station)

    if source_df is None or source_df.empty:
        source_df = pd.DataFrame()

    d = source_df.copy()

    if not d.empty and "sheet_id" in d.columns:
        d["sheet_id"] = normalize_string_series(d["sheet_id"])
    else:
        d["sheet_id"] = ""

    time_col = "repair_time" if clean_text(station).upper() in {"TAR", "TOS"} else "scan_time"

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
                "display_source_op_id": display_op_id,
                "process": clean_text(process).upper(),
                "station": clean_text(station).upper(),
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
                "display_source_op_id": display_op_id,
                "process": clean_text(process).upper(),
                "station": clean_text(station).upper(),
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

    for col in out.columns:
        out[col] = out[col].apply(
            lambda x: None
            if isinstance(x, str) and x.strip().lower() in {"nan", "none", "null", "<na>", "nat", "inf", "-inf"}
            else x
        )

    return out.astype(object)


def ensure_column_exists(conn, table_name: str, column_name: str, column_def_sql: str):
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
# Inspection Input Repository
# =============================================================================

class InspectionInputRepository:
    def __init__(self, db: MySQLConnet, cfg: InspectionIncomingConfig):
        self.db = db
        self.cfg = cfg
        self.engine = db.engine

    def table_exists(self, table_name: str) -> bool:
        insp = inspect(self.engine)
        return table_name.lower() in [t.lower() for t in insp.get_table_names()]

    def inspection_summary_table_name(self, yyyymm: str) -> str:
        return self.cfg.inspection_summary_base.replace("yyyymm", yyyymm).lower()

    def inspection_raw_table_name(self, yyyymm: str) -> str:
        return self.cfg.inspection_raw_base.replace("yyyymm", yyyymm).lower()

    def load_inspection_summary(self, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
        months = yyyymm_range(start_dt, end_dt)
        chunks = []

        for ym in months:
            tb = self.inspection_summary_table_name(ym)
            if not self.table_exists(tb):
                logging.warning("[InspectionSummary] table not exists: %s", tb)
                continue

            sql = text(f"""
            SELECT
                SHEET_ID,
                TYPE,
                SCAN_ENDTIME,
                TOOL_ID,
                MODEL_NO,
                TOTAL_DEFECT_COUNT
            FROM {tb}
            WHERE SCAN_ENDTIME >= :start_dt
              AND SCAN_ENDTIME <  :end_dt
            """)

            with self.engine.connect() as conn:
                df = pd.read_sql(sql, conn, params={
                    "start_dt": start_dt,
                    "end_dt": end_dt,
                })

            if not df.empty:
                chunks.append(df)

        if not chunks:
            return pd.DataFrame()

        return pd.concat(chunks, ignore_index=True)

    def normalize_inspection_summary(self, summary_df: pd.DataFrame) -> pd.DataFrame:
        cols = [
            "sheet_id",
            "glass_type",
            "scan_time",
            "line_id",
            "model_no",
            "total_defect_qty",
        ]

        if summary_df is None or summary_df.empty:
            return pd.DataFrame(columns=cols)

        d = summary_df.copy()

        need_cols = [
            "SHEET_ID",
            "TYPE",
            "SCAN_ENDTIME",
            "TOOL_ID",
            "MODEL_NO",
            "TOTAL_DEFECT_COUNT",
        ]

        for c in need_cols:
            if c not in d.columns:
                c_lower = c.lower()
                if c_lower in d.columns:
                    d[c] = d[c_lower]
                else:
                    d[c] = None

        out = pd.DataFrame()
        out["sheet_id"] = d["SHEET_ID"].astype("string").fillna("").str.strip()
        out["glass_type"] = d["TYPE"].astype("string").fillna("").str.strip().str.upper()
        out["scan_time"] = pd.to_datetime(d["SCAN_ENDTIME"], errors="coerce")
        out["line_id"] = d["TOOL_ID"].astype("string").fillna("").str.strip()
        out["model_no"] = d["MODEL_NO"].astype("string").fillna("").str.strip()
        out["total_defect_qty"] = pd.to_numeric(
            d["TOTAL_DEFECT_COUNT"],
            errors="coerce",
        ).fillna(0).astype(int)

        out = out.dropna(subset=["scan_time"])
        out = out[
            (out["sheet_id"] != "")
            & (out["glass_type"].isin(["CF", "TFT"]))
        ].copy()

        if out.empty:
            return out.reset_index(drop=True)

        out = out.sort_values(
            ["sheet_id", "glass_type", "scan_time"],
            ascending=[True, True, True],
            na_position="last",
        )

        out = (
            out.groupby(["sheet_id", "glass_type"], as_index=False)
            .tail(1)
            .reset_index(drop=True)
        )

        return out[cols].copy()

    def load_inspection_raw(self, inspection_summary_df: pd.DataFrame) -> pd.DataFrame:
        if inspection_summary_df is None or inspection_summary_df.empty:
            return pd.DataFrame()

        k = inspection_summary_df[["sheet_id", "scan_time"]].copy()
        k["sheet_id"] = normalize_string_series(k["sheet_id"])
        k["scan_time"] = pd.to_datetime(k["scan_time"], errors="coerce")
        k = k.dropna(subset=["sheet_id", "scan_time"])
        k = k.drop_duplicates(subset=["sheet_id", "scan_time"])

        if k.empty:
            return pd.DataFrame()

        months = sorted(k["scan_time"].dt.strftime("%Y%m").dropna().unique().tolist())
        chunks = []

        select_cols = [
            "COORD_X",
            "COORD_Y",
            "DEFECT_SIZE_TYPE",
            "IMG_URL",
            "RECIPE_NAME",
            "RUN_ID",
            "SCAN_ENDTIME",
            "SHEET_ID",
            "SP",
            "STAGE",
            "TOOL_ID",
            "TOTAL_DEFECT_COUNT",
        ]

        for ym in months:
            tb = self.inspection_raw_table_name(ym)
            if not self.table_exists(tb):
                logging.warning("[InspectionRaw] table not exists: %s", tb)
                continue

            km = k[k["scan_time"].dt.strftime("%Y%m").eq(ym)].copy()
            if km.empty:
                continue

            for batch in chunk_list(km.to_dict(orient="records"), self.cfg.mysql_batch_size):
                bind_parts = []
                params: Dict[str, Any] = {}

                for i, row in enumerate(batch):
                    s_key = f"s{i}"
                    t_key = f"t{i}"
                    bind_parts.append(f"(SHEET_ID = :{s_key} AND SCAN_ENDTIME = :{t_key})")
                    params[s_key] = row["sheet_id"]
                    params[t_key] = row["scan_time"]

                if not bind_parts:
                    continue

                where_sql = " OR ".join(bind_parts)
                sql = text(f"""
                SELECT {", ".join(select_cols)}
                FROM {tb}
                WHERE {where_sql}
                """)

                with self.engine.connect() as conn:
                    df = pd.read_sql(sql, conn, params=params)

                if not df.empty:
                    chunks.append(df)

        if not chunks:
            return pd.DataFrame()

        return pd.concat(chunks, ignore_index=True)

    def normalize_inspection_defects(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        cols = [
            "inspection_defect_uid",
            "sheet_id",
            "scan_time",
            "line_id",
            "defect_size",
            "defect_size_raw",
            "recipe_name",
            "run_id",
            "sp",
            "stage",
            "ori_x",
            "ori_y",
            "trans_x",
            "trans_y",
            "img_url_path",
            "image_name",
            "total_defect_count",
            "raw_json",
        ]

        if raw_df is None or raw_df.empty:
            return pd.DataFrame(columns=cols)

        d = raw_df.copy()

        for c in [
            "COORD_X",
            "COORD_Y",
            "DEFECT_SIZE_TYPE",
            "IMG_URL",
            "RECIPE_NAME",
            "RUN_ID",
            "SCAN_ENDTIME",
            "SHEET_ID",
            "SP",
            "STAGE",
            "TOOL_ID",
            "TOTAL_DEFECT_COUNT",
        ]:
            if c not in d.columns:
                c_lower = c.lower()
                if c_lower in d.columns:
                    d[c] = d[c_lower]
                else:
                    d[c] = None

        out = pd.DataFrame()
        out["sheet_id"] = normalize_string_series(d["SHEET_ID"])
        out["scan_time"] = pd.to_datetime(d["SCAN_ENDTIME"], errors="coerce")
        out["line_id"] = normalize_string_series(d["TOOL_ID"])

        out["defect_size_raw"] = d["DEFECT_SIZE_TYPE"]
        out["defect_size"] = out["defect_size_raw"].apply(
            lambda v: normalize_defect_size_by_first_char(v, default="O")
        )

        out["recipe_name"] = normalize_string_series(d["RECIPE_NAME"])
        out["run_id"] = normalize_string_series(d["RUN_ID"])
        out["sp"] = normalize_string_series(d["SP"])
        out["stage"] = normalize_string_series(d["STAGE"])

        out["ori_x"] = pd.to_numeric(d["COORD_X"], errors="coerce")
        out["ori_y"] = pd.to_numeric(d["COORD_Y"], errors="coerce")

        # Inspection coordinate transform
        out["trans_x"] = out["ori_y"]
        out["trans_y"] = self.cfg.panel_height_um - out["ori_x"]

        out["img_url_path"] = normalize_string_series(d["IMG_URL"])
        out["image_name"] = out["img_url_path"].apply(safe_image_filename_from_url_or_path)

        out["total_defect_count"] = pd.to_numeric(
            d["TOTAL_DEFECT_COUNT"],
            errors="coerce",
        ).fillna(0).astype(int)

        out["inspection_defect_uid"] = (
            "INSPECTION|"
            + out["sheet_id"].astype(str)
            + "|"
            + out["scan_time"].astype(str)
            + "|"
            + out["line_id"].astype(str)
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

        out = out.dropna(subset=["scan_time"])
        out = out[out["sheet_id"] != ""].copy()

        return out[cols].reset_index(drop=True)


# =============================================================================
# AOI Source Repository
# =============================================================================

class AoiSourceRepository:
    def __init__(self, db: MySQLConnet, cfg: InspectionIncomingConfig):
        self.db = db
        self.cfg = cfg
        self.engine = db.engine

    def table_exists(self, table_name: str) -> bool:
        insp = inspect(self.engine)
        return table_name.lower() in [t.lower() for t in insp.get_table_names()]

    def list_tables(self) -> List[str]:
        return inspect(self.engine).get_table_names()

    def aoi_summary_table_name(self, yyyymm: str) -> str:
        return self.cfg.aoi_summary_base.replace("yyyymm", yyyymm).lower()

    def defect_table_prefix(self, yyyymm: str) -> str:
        return self.cfg.aoi_defect_prefix_template.replace("yyyymm", yyyymm).lower()

    def find_aoi_defect_tables(self, yyyymm: str) -> List[str]:
        prefix = self.defect_table_prefix(yyyymm)
        return [t for t in self.list_tables() if t.lower().startswith(prefix)]

    def resolve_defect_aoi_token(self, aoi_value: Any) -> str:
        aoi = clean_text(aoi_value).upper()
        return self.cfg.aoi_map.get(aoi, "").lower()

    def filter_defect_tables_by_aoi_token(
        self,
        defect_tables: List[str],
        aoi_token: str,
    ) -> List[str]:
        token = clean_text(aoi_token).lower()
        if not token:
            return defect_tables

        out = []
        for tb in defect_tables:
            tb_l = tb.lower()
            if f"_{token}_" in tb_l or tb_l.endswith(f"_{token}"):
                out.append(tb)
        return out

    def load_latest_aoi_glass(
        self,
        inspection_df: pd.DataFrame,
        *,
        pi_type: str,
        start_dt: datetime,
        end_dt: datetime,
    ) -> pd.DataFrame:
        if inspection_df is None or inspection_df.empty:
            return pd.DataFrame()

        sheet_ids = (
            inspection_df["sheet_id"]
            .dropna()
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )

        if not sheet_ids:
            return pd.DataFrame()

        lookup_start = start_dt - timedelta(days=self.cfg.aoi_lookup_days)
        lookup_end = end_dt + timedelta(days=1)
        months = yyyymm_range(lookup_start, lookup_end)

        chunks = []

        for ym in months:
            tb = self.aoi_summary_table_name(ym)
            if not self.table_exists(tb):
                continue

            for batch in chunk_list(sheet_ids, self.cfg.mysql_batch_size):
                bind = {f"s{i}": v for i, v in enumerate(batch)}
                in_clause = ", ".join([f":s{i}" for i in range(len(batch))])

                sql = text(f"""
                SELECT *
                FROM {tb}
                WHERE sheet_id_chip_id IN ({in_clause})
                  AND UPPER(pi_type) = :pi_type
                  AND test_time >= :lookup_start
                  AND test_time <  :lookup_end
                """)

                params = dict(bind)
                params["pi_type"] = clean_text(pi_type).upper()
                params["lookup_start"] = lookup_start
                params["lookup_end"] = lookup_end

                with self.engine.connect() as conn:
                    df = pd.read_sql(sql, conn, params=params)

                df = safe_lower_columns(df)
                if not df.empty:
                    chunks.append(df)

        if not chunks:
            return pd.DataFrame()

        out = pd.concat(chunks, ignore_index=True)

        out["sheet_id_chip_id"] = normalize_string_series(out["sheet_id_chip_id"])
        out["pi_type"] = normalize_string_series(out.get("pi_type", pd.Series(dtype=str))).str.upper()
        out["test_time"] = pd.to_datetime(out.get("test_time"), errors="coerce")

        out = out.dropna(subset=["sheet_id_chip_id", "test_time"])
        out = out.sort_values(["sheet_id_chip_id", "pi_type", "test_time"])

        out = (
            out.groupby(["sheet_id_chip_id", "pi_type"], as_index=False)
            .tail(1)
            .reset_index(drop=True)
        )

        return out

    def build_cell_image_from_cim_row(self, row: pd.Series) -> Tuple[str, str]:
        base_url = clean_text(self.cfg.cell_aidi_url)

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

    def load_aoi_defects(self, aoi_glass_df: pd.DataFrame, *, source_op_id: str) -> pd.DataFrame:
        cols = [
            "source_defect_uid",
            "source_op_id",
            "sheet_id",
            "scan_time",
            "line_id",
            "aoi",
            "pi_type",
            "pi_time",
            "recipe_id",
            "model_no",
            "chip_id",
            "defect_code",
            "retype_def_code",
            "defect_size",
            "defect_size_raw",
            "ori_x",
            "ori_y",
            "trans_x",
            "trans_y",
            "image_name",
            "img_url_path",
            "raw_json",
        ]

        if aoi_glass_df is None or aoi_glass_df.empty:
            return pd.DataFrame(columns=cols)

        need_cols = [
            c for c in [
                "sheet_id_chip_id",
                "test_time",
                "aoi",
                "line_id",
                "pi_type",
                "pi_time",
                "recipe_id",
                "model_no",
            ]
            if c in aoi_glass_df.columns
        ]

        if "sheet_id_chip_id" not in need_cols or "test_time" not in need_cols:
            return pd.DataFrame(columns=cols)

        k = aoi_glass_df[need_cols].copy()
        k["sheet_id_chip_id"] = normalize_string_series(k["sheet_id_chip_id"])
        k["test_time"] = pd.to_datetime(k["test_time"], errors="coerce")
        k = k.dropna(subset=["sheet_id_chip_id", "test_time"])

        if "aoi" not in k.columns:
            k["aoi"] = ""
        k["aoi"] = normalize_string_series(k["aoi"]).str.upper()
        k["aoi_token"] = k["aoi"].apply(self.resolve_defect_aoi_token)

        if "pi_type" not in k.columns:
            k["pi_type"] = ""
        k["pi_type"] = normalize_string_series(k["pi_type"]).str.upper()

        months = sorted(k["test_time"].dt.strftime("%Y%m").dropna().unique().tolist())
        out_chunks = []

        for ym in months:
            all_defect_tables = self.find_aoi_defect_tables(ym)
            if not all_defect_tables:
                continue

            km = k[k["test_time"].dt.strftime("%Y%m").eq(ym)].copy()

            for aoi_token, km_aoi in km.groupby("aoi_token", dropna=False):
                aoi_token = clean_text(aoi_token).lower()
                defect_tables = self.filter_defect_tables_by_aoi_token(all_defect_tables, aoi_token)

                for tb in defect_tables:
                    for batch in chunk_list(km_aoi.to_dict(orient="records"), self.cfg.mysql_batch_size):
                        bind_parts = []
                        params: Dict[str, Any] = {}

                        for i, row in enumerate(batch):
                            g_key = f"g{i}"
                            t_key = f"t{i}"
                            bind_parts.append(f"(sheet_id_chip_id = :{g_key} AND test_time = :{t_key})")
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
                            logging.exception("[AOI source defect] query failed table=%s", tb)
                            continue

                        df = safe_lower_columns(df)

                        if not df.empty:
                            df["_source_defect_table"] = tb
                            df["_mapped_aoi_token"] = aoi_token
                            out_chunks.append(df)

        if not out_chunks:
            return pd.DataFrame(columns=cols)

        raw = pd.concat(out_chunks, ignore_index=True)
        raw["sheet_id_chip_id"] = normalize_string_series(raw["sheet_id_chip_id"])
        raw["test_time"] = pd.to_datetime(raw.get("test_time"), errors="coerce")

        meta_cols = [
            c for c in [
                "sheet_id_chip_id",
                "test_time",
                "aoi",
                "line_id",
                "pi_type",
                "pi_time",
                "recipe_id",
                "model_no",
            ]
            if c in aoi_glass_df.columns
        ]

        meta = aoi_glass_df[meta_cols].drop_duplicates(
            subset=[
                c for c in ["sheet_id_chip_id", "test_time", "pi_type"]
                if c in meta_cols
            ]
        ).copy()

        meta["sheet_id_chip_id"] = normalize_string_series(meta["sheet_id_chip_id"])
        meta["test_time"] = pd.to_datetime(meta["test_time"], errors="coerce")

        if "pi_type" in meta.columns:
            meta["pi_type"] = normalize_string_series(meta["pi_type"]).str.upper()

        if "pi_type" in raw.columns and "pi_type" in meta.columns:
            raw["pi_type"] = normalize_string_series(raw["pi_type"]).str.upper()
            merge_keys = ["sheet_id_chip_id", "test_time", "pi_type"]
        else:
            merge_keys = ["sheet_id_chip_id", "test_time"]

        raw = raw.merge(
            meta,
            on=merge_keys,
            how="left",
            suffixes=("", "_glass"),
        )

        out = pd.DataFrame()
        out["source_op_id"] = source_op_id
        out["sheet_id"] = raw["sheet_id_chip_id"]
        out["scan_time"] = raw["test_time"]
        out["line_id"] = raw.get("line_id", raw.get("line_id_glass", ""))
        out["aoi"] = raw.get("aoi", raw.get("aoi_glass", ""))
        out["pi_type"] = raw.get("pi_type", raw.get("pi_type_glass", ""))
        out["pi_time"] = pd.to_datetime(raw.get("pi_time", raw.get("pi_time_glass")), errors="coerce")
        out["recipe_id"] = raw.get("recipe_id", raw.get("recipe_id_glass", ""))
        out["model_no"] = raw.get("model_no", raw.get("model_no_glass", ""))

        out["chip_id"] = raw.get("chip_id")
        out["defect_code"] = raw.get("adc_def_code")
        out["retype_def_code"] = raw.get("retype_def_code")

        if "defect_size" not in raw.columns:
            raw["defect_size"] = ""

        out["defect_size_raw"] = raw["defect_size"]
        out["defect_size"] = raw.apply(
            lambda r: normalize_cell_defect_size(
                r.get("defect_size"),
                aoi_token=r.get("_mapped_aoi_token"),
            ),
            axis=1,
        )

        out["ori_x"] = pd.to_numeric(raw.get("pox_x1"), errors="coerce")
        out["ori_y"] = pd.to_numeric(raw.get("pox_y1"), errors="coerce")
        out["trans_x"] = out["ori_x"]
        out["trans_y"] = out["ori_y"]

        img_pairs = raw.apply(self.build_cell_image_from_cim_row, axis=1)
        out["img_url_path"] = img_pairs.apply(lambda x: x[0] if isinstance(x, tuple) else "")
        out["image_name"] = img_pairs.apply(lambda x: x[1] if isinstance(x, tuple) else "")

        out["source_defect_uid"] = (
            "AOI|"
            + out["source_op_id"].astype(str)
            + "|"
            + out["sheet_id"].astype(str)
            + "|"
            + out["scan_time"].astype(str)
            + "|"
            + out["chip_id"].astype(str)
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

        out["raw_json"] = raw.apply(lambda r: json_dumps_safe(r.to_dict()), axis=1)

        return out[cols].reset_index(drop=True)

    def load_aoi_source(self, inspection_df: pd.DataFrame, *, pi_type: str, start_dt: datetime, end_dt: datetime) -> Tuple[pd.DataFrame, pd.DataFrame]:
        source_op_id = f"AOI_{clean_text(pi_type).upper()}"
        glass = self.load_latest_aoi_glass(
            inspection_df,
            pi_type=pi_type,
            start_dt=start_dt,
            end_dt=end_dt,
        )

        defects = self.load_aoi_defects(glass, source_op_id=source_op_id)

        sheet_ids = (
            inspection_df["sheet_id"]
            .dropna()
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )

        rows = []
        glass_sheet_set = set()
        if glass is not None and not glass.empty:
            glass_sheet_set = set(glass["sheet_id_chip_id"].astype(str).str.strip())

        defect_cnt = {}
        if defects is not None and not defects.empty:
            defect_cnt = defects.groupby("sheet_id").size().to_dict()

        for sheet_id in sheet_ids:
            if sheet_id in glass_sheet_set:
                g = glass[glass["sheet_id_chip_id"].astype(str).str.strip().eq(sheet_id)].copy()
                st = None
                if not g.empty:
                    st = pd.to_datetime(g["test_time"], errors="coerce").max()

                cnt = int(defect_cnt.get(sheet_id, 0))

                rows.append({
                    "source_op_id": source_op_id,
                    "display_source_op_id": source_op_id,
                    "process": "AOI",
                    "station": clean_text(pi_type).upper(),
                    "sheet_id": sheet_id,
                    "source_scan_time": st,
                    "source_defect_cnt": cnt,
                    "cache_status": "AOI_WITH_DEFECT" if cnt > 0 else "AOI_NO_DEFECT",
                    "cache_status_detail": f"aoi source defect rows={cnt}",
                    "source_table_name": "",
                    "yyyymm": pd.to_datetime(st).strftime("%Y%m") if st is not None and not pd.isna(st) else None,
                    "last_query_time": datetime.now(),
                })
            else:
                rows.append({
                    "source_op_id": source_op_id,
                    "display_source_op_id": source_op_id,
                    "process": "AOI",
                    "station": clean_text(pi_type).upper(),
                    "sheet_id": sheet_id,
                    "source_scan_time": None,
                    "source_defect_cnt": None,
                    "cache_status": "AOI_NOT_FOUND",
                    "cache_status_detail": f"no aoi {pi_type} glass group",
                    "source_table_name": "",
                    "yyyymm": None,
                    "last_query_time": datetime.now(),
                })

        return defects, pd.DataFrame(rows)


# =============================================================================
# CF / ARRAY Oracle Source Extractors
# =============================================================================

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
    return f"R{glass_id}_{defect_no}_001_{x}_{y}.jpg"


def build_cf_img_url(row: pd.Series, cfg: InspectionIncomingConfig) -> str:
    sheet_id = clean_text(row.get("sheet_id"))
    image_name = clean_text(row.get("image_name"))
    op_id = clean_text(row.get("op_id")).upper()
    repair_op = clean_text(row.get("repair_op"))

    suffix = get_repair_last(repair_op)
    if suffix not in {"OC", "PS"}:
        suffix = op_id

    if suffix not in {"OC", "PS"}:
        suffix = "UNKNOWN"

    suffix = suffix if suffix == "PS" else "MVA"
    tail = sheet_id[-1:] if sheet_id else ""
    folder = f"{cfg.cf_img_base}{suffix}/{tail}/{sheet_id}/"
    return build_complete_img_url(folder, image_name)


def build_mor_img_url(image_file_name: Any, img_file_url_path: Any, cfg: InspectionIncomingConfig) -> str:
    fn = clean_text(image_file_name)
    folder = clean_text(img_file_url_path)
    base = clean_text(cfg.mor_img_base)

    if not fn or not folder:
        return ""

    if fn.startswith("http://") or fn.startswith("https://"):
        return fn

    if folder.startswith("http://") or folder.startswith("https://"):
        return folder.rstrip("/") + "/" + fn.lstrip("/")

    return base.rstrip("/") + "/" + folder.strip("/") + "/" + fn.lstrip("/")


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


def build_tar_tos_img_url(row: pd.Series, cfg: InspectionIncomingConfig) -> str:
    route = clean_text(row.get("route"))
    lot_id = clean_text(row.get("lot_id"))
    image_name = clean_text(row.get("image_name"))
    if not image_name:
        return ""
    folder = f"{cfg.tar_tos_img_base}{route}/{lot_id}/"
    return build_complete_img_url(folder, image_name)


class CFSourceExtractor:
    def __init__(self, oracle_db: OracleDBHandler, cfg: InspectionIncomingConfig):
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

        out["ori_x"] = df.get("coord_x")
        out["ori_y"] = df.get("coord_y")

        out["image_name"] = out.apply(build_cf_image_name, axis=1)

        out["trans_x"] = pd.to_numeric(df.get("coord_y"), errors="coerce")
        out["trans_y"] = self.cfg.panel_height_um - pd.to_numeric(df.get("coord_x"), errors="coerce")

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

    def run(self, sheet_ids: List[str]) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        sheet_ids = sorted({clean_text(s) for s in sheet_ids if clean_text(s)})
        if not sheet_ids:
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        logging.info("[CF] fetch candidates sheet_count=%s", len(sheet_ids))

        try:
            raw = self.fetch_candidates(sheet_ids)
            logging.info("[CF] candidate rows=%s", len(raw))

            oc_raw, ps_raw = self.build_latest_groups(raw)
            logging.info("[CF] latest OC rows=%s PS rows=%s", len(oc_raw), len(ps_raw))

            oc = self.normalize_cf(oc_raw, "OC")
            ps = self.normalize_cf(ps_raw, "PS")

            oc_state = build_source_group_state_df(
                input_sheet_ids=sheet_ids,
                source_df=oc,
                process="CF",
                station="OC",
            )

            ps_state = build_source_group_state_df(
                input_sheet_ids=sheet_ids,
                source_df=ps,
                process="CF",
                station="PS",
            )

            state_df = pd.concat([oc_state, ps_state], ignore_index=True)

            return oc, ps, state_df

        except Exception as e:
            logging.exception("[CF] oracle query failed")
            rows = []
            for station in ["OC", "PS"]:
                source_op_id = to_cache_source_op_id("CF", station)
                display_op_id = display_source_op_id("CF", station)
                for sheet_id in sheet_ids:
                    rows.append({
                        "source_op_id": source_op_id,
                        "display_source_op_id": display_op_id,
                        "process": "CF",
                        "station": station,
                        "sheet_id": sheet_id,
                        "source_scan_time": None,
                        "source_defect_cnt": None,
                        "cache_status": "ORACLE_QUERY_FAILED",
                        "cache_status_detail": str(e),
                        "source_table_name": "",
                        "yyyymm": None,
                        "last_query_time": datetime.now(),
                    })
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(rows)


class ArraySourceExtractor:
    def __init__(self, oracle_db: OracleDBHandler, cfg: InspectionIncomingConfig):
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

    def run(self, sheet_ids: List[str]) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        sheet_ids = sorted({clean_text(s) for s in sheet_ids if clean_text(s)})
        if not sheet_ids:
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        mor_out = pd.DataFrame()
        tar_out = pd.DataFrame()
        tos_out = pd.DataFrame()
        states = []

        for station_cfg in self.cfg.array_station_configs:
            station = station_cfg["station"]

            logging.info("[ARRAY:%s] fetch sheet_count=%s", station, len(sheet_ids))

            try:
                raw = self.fetch_station(station_cfg, sheet_ids)
                logging.info("[ARRAY:%s] raw rows=%s", station, len(raw))

                latest = self.build_latest_group(raw, station_cfg)
                logging.info("[ARRAY:%s] latest rows=%s", station, len(latest))

                if station == "MOR":
                    mor_out = self.normalize_mor(latest)
                    st = build_source_group_state_df(
                        input_sheet_ids=sheet_ids,
                        source_df=mor_out,
                        process="ARRAY",
                        station="MOR",
                    )
                    states.append(st)

                elif station == "TAR":
                    tar_out = self.normalize_tar_tos(latest, "TAR")
                    st = build_source_group_state_df(
                        input_sheet_ids=sheet_ids,
                        source_df=tar_out,
                        process="ARRAY",
                        station="TAR",
                    )
                    states.append(st)

                elif station == "TOS":
                    tos_out = self.normalize_tar_tos(latest, "TOS")
                    st = build_source_group_state_df(
                        input_sheet_ids=sheet_ids,
                        source_df=tos_out,
                        process="ARRAY",
                        station="TOS",
                    )
                    states.append(st)

            except Exception as e:
                logging.exception("[ARRAY:%s] oracle query failed", station)
                source_op_id = to_cache_source_op_id("ARRAY", station)
                display_op_id = display_source_op_id("ARRAY", station)
                rows = []
                for sheet_id in sheet_ids:
                    rows.append({
                        "source_op_id": source_op_id,
                        "display_source_op_id": display_op_id,
                        "process": "ARRAY",
                        "station": station,
                        "sheet_id": sheet_id,
                        "source_scan_time": None,
                        "source_defect_cnt": None,
                        "cache_status": "ORACLE_QUERY_FAILED",
                        "cache_status_detail": str(e),
                        "source_table_name": "",
                        "yyyymm": None,
                        "last_query_time": datetime.now(),
                    })
                states.append(pd.DataFrame(rows))

        state_df = pd.concat(states, ignore_index=True) if states else pd.DataFrame()
        return mor_out, tar_out, tos_out, state_df


# =============================================================================
# Source Cache Repository
# =============================================================================

class SourceCacheRepository:
    def __init__(self, db: MySQLConnet, cfg: InspectionIncomingConfig):
        self.db = db
        self.cfg = cfg
        self.engine = db.engine

    def table_exists(self, table_name: str) -> bool:
        insp = inspect(self.engine)
        return table_name.lower() in [t.lower() for t in insp.get_table_names()]

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

    def ensure_source_group_state_table(self):
        ddl = text(f"""
        CREATE TABLE IF NOT EXISTS {self.cfg.source_group_state_table} (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,

            source_op_id VARCHAR(80) NOT NULL,
            display_source_op_id VARCHAR(80) NULL,
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
            ensure_column_exists(conn, self.cfg.source_group_state_table, "display_source_op_id", "VARCHAR(80) NULL")

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
            "display_source_op_id",
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

    def load_source_group_state(self, source_op_id: str, sheet_ids: List[str]) -> pd.DataFrame:
        self.ensure_source_group_state_table()

        sheet_ids = sorted({clean_text(s) for s in sheet_ids if clean_text(s)})
        if not sheet_ids:
            return pd.DataFrame()

        chunks = []

        for batch in chunk_list(sheet_ids, self.cfg.mysql_batch_size):
            bind = {f"s{i}": v for i, v in enumerate(batch)}
            in_clause = ", ".join([f":s{i}" for i in range(len(batch))])

            sql = text(f"""
            SELECT *
            FROM {self.cfg.source_group_state_table}
            WHERE source_op_id = :source_op_id
              AND sheet_id IN ({in_clause})
            """)

            params = dict(bind)
            params["source_op_id"] = source_op_id

            with self.engine.connect() as conn:
                df = pd.read_sql(sql, conn, params=params)

            df = safe_lower_columns(df)
            if not df.empty:
                chunks.append(df)

        if not chunks:
            return pd.DataFrame()

        out = pd.concat(chunks, ignore_index=True)
        out["sheet_id"] = normalize_string_series(out["sheet_id"])
        out["source_op_id"] = normalize_string_series(out["source_op_id"]).str.upper()

        if "last_query_time" in out.columns:
            out["last_query_time"] = pd.to_datetime(out["last_query_time"], errors="coerce")

        return out

    def load_source_raw(
        self,
        *,
        process: str,
        station: str,
        sheet_ids: List[str],
        lookup_start: datetime,
        lookup_end: datetime,
    ) -> pd.DataFrame:
        sheet_ids = sorted({clean_text(s) for s in sheet_ids if clean_text(s)})
        if not sheet_ids:
            return pd.DataFrame()

        months = yyyymm_range(lookup_start, lookup_end)
        chunks = []

        for ym in months:
            tb = self.source_table_name(process, station, ym)
            if not self.table_exists(tb):
                continue

            for batch in chunk_list(sheet_ids, self.cfg.mysql_batch_size):
                bind = {f"s{i}": v for i, v in enumerate(batch)}
                in_clause = ", ".join([f":s{i}" for i in range(len(batch))])

                sql = text(f"""
                SELECT *
                FROM {tb}
                WHERE sheet_id IN ({in_clause})
                """)

                with self.engine.connect() as conn:
                    df = pd.read_sql(sql, conn, params=bind)

                df = safe_lower_columns(df)
                if not df.empty:
                    chunks.append(df)

        if not chunks:
            return pd.DataFrame()

        out = pd.concat(chunks, ignore_index=True)

        if "sheet_id" in out.columns:
            out["sheet_id"] = normalize_string_series(out["sheet_id"])

        return out

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
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        with self.engine.begin() as conn:
            conn.execute(ddl)
            ensure_column_exists(conn, table_name, "source_defect_uid", "VARCHAR(500) NULL")
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
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        with self.engine.begin() as conn:
            conn.execute(ddl)
            ensure_column_exists(conn, table_name, "source_defect_uid", "VARCHAR(500) NULL")
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
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        with self.engine.begin() as conn:
            conn.execute(ddl)
            ensure_column_exists(conn, table_name, "source_defect_uid", "VARCHAR(500) NULL")
            ensure_column_exists(conn, table_name, "defect_size_raw", "VARCHAR(200) NULL")

    def save_source_raw(self, process: str, station: str, df: pd.DataFrame):
        if df is None or df.empty:
            logging.info("[save_source_raw] %s/%s empty", process, station)
            return

        d = df.copy()

        process = clean_text(process).upper()
        station = clean_text(station).upper()

        time_col = "scan_time" if process == "CF" or station == "MOR" else "repair_time"
        d[time_col] = pd.to_datetime(d.get(time_col), errors="coerce")
        d["yyyymm"] = d[time_col].dt.strftime("%Y%m").fillna(datetime.now().strftime("%Y%m"))

        for ym, g in d.groupby("yyyymm"):
            tb = self.source_table_name(process, station, str(ym))

            if process == "CF":
                self.ensure_cf_raw_table(tb)
                datetime_cols = ["scan_time", "repair_time", "create_time", "update_time"]
                float_cols = ["ori_x", "ori_y", "trans_x", "trans_y"]
                text_cols = [
                    "sheet_id", "chip_id", "model_no", "eqp_id", "op",
                    "repair_code", "repair_eqp_id", "repair_op", "op_id",
                    "defect_no", "defect_code", "defect_size", "defect_size_raw",
                    "image_name", "img_url_path", "source_group_key", "source_defect_uid",
                ]
                json_cols = ["raw_json"]

            elif station == "MOR":
                self.ensure_mor_raw_table(tb)
                datetime_cols = ["scan_time", "create_time", "update_time"]
                float_cols = ["ori_x", "ori_y", "trans_x", "trans_y"]
                text_cols = [
                    "lot_id", "model_no", "sheet_id", "chip_id", "signal_no",
                    "gate_no", "defect_size", "defect_size_raw", "defect_code",
                    "image_name", "img_url_path", "op_id", "recipe_id", "eqp_id",
                    "source_group_key", "source_defect_uid",
                ]
                json_cols = ["raw_json"]

            else:
                self.ensure_tar_tos_raw_table(tb)
                datetime_cols = ["repair_time", "create_time", "update_time"]
                float_cols = ["ori_x", "ori_y", "trans_x", "trans_y"]
                text_cols = [
                    "lot_id", "model_no", "sheet_id", "tool_id", "chip_id",
                    "signal_no", "gate_no", "signal_gate_defect_code", "route",
                    "chip_seq_no", "op_id", "defect_code", "defect_size",
                    "defect_size_raw", "tester_tool", "ori_image_name",
                    "image_name", "img_url_path", "source_group_key", "source_defect_uid",
                ]
                json_cols = ["raw_json"]

            g2 = g.drop(columns=["yyyymm"], errors="ignore").copy()

            g2 = clean_df_by_schema(
                g2,
                datetime_cols=datetime_cols,
                float_cols=float_cols,
                text_cols=text_cols,
                json_cols=json_cols,
            )

            dedup_keys = ["source_defect_uid"]
            dedup_keys = [c for c in dedup_keys if c in g2.columns]

            logging.info("[save_source_raw] table=%s rows=%s dedup=%s", tb, len(g2), dedup_keys)

            self.db.append_or_create_dedup(
                table_name=tb,
                df=g2,
                dedup_keys=dedup_keys,
            )

    def load_or_fetch_source(
        self,
        *,
        process: str,
        station: str,
        sheet_ids: List[str],
        start_dt: datetime,
        end_dt: datetime,
        cf_extractor: Optional[CFSourceExtractor] = None,
        array_extractor: Optional[ArraySourceExtractor] = None,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        process = clean_text(process).upper()
        station = clean_text(station).upper()
        cache_source_op_id = to_cache_source_op_id(process, station)

        lookup_start = start_dt - timedelta(days=self.cfg.source_lookup_days)
        lookup_end = end_dt + timedelta(days=1)

        cached_df = self.load_source_raw(
            process=process,
            station=station,
            sheet_ids=sheet_ids,
            lookup_start=lookup_start,
            lookup_end=lookup_end,
        )

        cached_sheet_set = set()
        if cached_df is not None and not cached_df.empty and "sheet_id" in cached_df.columns:
            cached_sheet_set = set(cached_df["sheet_id"].astype(str).str.strip())

        state_df = self.load_source_group_state(cache_source_op_id, sheet_ids)

        known_no_query_set = set()
        if state_df is not None and not state_df.empty:
            st = state_df.copy()
            st["cache_status"] = normalize_string_series(st["cache_status"]).str.upper()
            known_no_query_set = set(
                st[
                    st["cache_status"].isin([
                        "CACHED_NO_DEFECT",
                        "ORACLE_NO_DEFECT",
                        "ORACLE_NOT_FOUND",
                    ])
                ]["sheet_id"].astype(str).str.strip()
            )

        need_fetch = [
            s for s in sorted({clean_text(x) for x in sheet_ids if clean_text(x)})
            if s not in cached_sheet_set
            and s not in known_no_query_set
        ]

        fetched_df = pd.DataFrame()
        fetched_state = pd.DataFrame()

        if need_fetch:
            logging.info(
                "[load_or_fetch_source] process=%s station=%s need_fetch=%s",
                process,
                station,
                len(need_fetch),
            )

            if process == "CF":
                if cf_extractor is None:
                    raise ValueError("cf_extractor is required for CF fetch")

                oc, ps, cf_state = cf_extractor.run(need_fetch)

                if station == "OC":
                    fetched_df = oc
                    fetched_state = cf_state[cf_state["source_op_id"].eq("CF_OC")].copy() if not cf_state.empty else pd.DataFrame()
                elif station == "PS":
                    fetched_df = ps
                    fetched_state = cf_state[cf_state["source_op_id"].eq("CF_PS")].copy() if not cf_state.empty else pd.DataFrame()

            elif process == "ARRAY":
                if array_extractor is None:
                    raise ValueError("array_extractor is required for ARRAY fetch")

                mor, tar, tos, arr_state = array_extractor.run(need_fetch)

                if station == "MOR":
                    fetched_df = mor
                    fetched_state = arr_state[arr_state["source_op_id"].eq("ARRAY_MOR")].copy() if not arr_state.empty else pd.DataFrame()
                elif station == "TAR":
                    fetched_df = tar
                    fetched_state = arr_state[arr_state["source_op_id"].eq("ARRAY_TAR")].copy() if not arr_state.empty else pd.DataFrame()
                elif station == "TOS":
                    fetched_df = tos
                    fetched_state = arr_state[arr_state["source_op_id"].eq("ARRAY_TOS")].copy() if not arr_state.empty else pd.DataFrame()

            if fetched_df is not None and not fetched_df.empty:
                self.save_source_raw(process, station, fetched_df)

            if fetched_state is not None and not fetched_state.empty:
                self.save_source_group_state(fetched_state)

            if fetched_df is not None and not fetched_df.empty:
                cached_df = pd.concat([cached_df, fetched_df], ignore_index=True)

            if fetched_state is not None and not fetched_state.empty:
                state_df = pd.concat([state_df, fetched_state], ignore_index=True)

        return cached_df, state_df


# =============================================================================
# Same Point Builder
# =============================================================================

class InspectionSamePointBuilder:
    def __init__(self, cfg: InspectionIncomingConfig):
        self.cfg = cfg

    @staticmethod
    def station_list_by_type(glass_type: str) -> List[Tuple[str, str, str, float]]:
        gt = clean_text(glass_type).upper()

        if gt == "CF":
            return [
                ("AOI", "BPI", "AOI_BPI", 1000.0),
                ("AOI", "API", "AOI_API", 1000.0),
                ("CF", "OC", "CF_OC", 3000.0),
                ("CF", "PS", "CF_PS", 3000.0),
            ]

        if gt == "TFT":
            return [
                ("AOI", "BPI", "AOI_BPI", 1000.0),
                ("AOI", "API", "AOI_API", 1000.0),
                ("ARRAY", "MOR", "ARRAY_MOR", 1000.0),
                ("ARRAY", "TAR", "ARRAY_TAR", 1000.0),
                ("ARRAY", "TOS", "ARRAY_TOS", 1000.0),
            ]

        return []

    @staticmethod
    def source_time_col(source_op_id: str) -> str:
        op = clean_text(source_op_id).upper()
        if op in {"ARRAY_TAR", "ARRAY_TOS"}:
            return "repair_time"
        return "scan_time"

    @staticmethod
    def get_state_row(state_df: pd.DataFrame, sheet_id: str, source_op_id: str) -> Optional[pd.Series]:
        if state_df is None or state_df.empty:
            return None

        d = state_df.copy()

        if "sheet_id" not in d.columns or "source_op_id" not in d.columns:
            return None

        d["sheet_id"] = normalize_string_series(d["sheet_id"])
        d["source_op_id"] = normalize_string_series(d["source_op_id"]).str.upper()

        m = d[
            d["sheet_id"].eq(clean_text(sheet_id))
            & d["source_op_id"].eq(clean_text(source_op_id).upper())
        ].copy()

        if m.empty:
            return None

        if "last_query_time" in m.columns:
            m["last_query_time"] = pd.to_datetime(m["last_query_time"], errors="coerce")
            m = m.sort_values("last_query_time")

        return m.iloc[-1]

    @staticmethod
    def build_target_detail(row: pd.Series) -> Dict[str, Any]:
        def num_or_none(v):
            try:
                if pd.isna(v):
                    return None
            except Exception:
                pass
            try:
                return float(v)
            except Exception:
                return None

        return {
            "system": "INSPECTION",
            "inspection_defect_uid": clean_text(row.get("inspection_defect_uid")),
            "sheet_id": clean_text(row.get("sheet_id")),
            "scan_time": normalize_source_raw_value(row.get("scan_time")),
            "line_id": clean_text(row.get("line_id")),
            "defect_size": clean_text(row.get("defect_size")),
            "defect_size_raw": clean_text(row.get("defect_size_raw")),
            "recipe_name": clean_text(row.get("recipe_name")),
            "run_id": clean_text(row.get("run_id")),
            "sp": clean_text(row.get("sp")),
            "stage": clean_text(row.get("stage")),
            "ori_x": num_or_none(row.get("ori_x")),
            "ori_y": num_or_none(row.get("ori_y")),
            "trans_x": num_or_none(row.get("trans_x")),
            "trans_y": num_or_none(row.get("trans_y")),
            "image_name": clean_text(row.get("image_name")),
            "img_url_path": clean_text(row.get("img_url_path")),
            "total_defect_count": int(row.get("total_defect_count") or 0),
            "raw": json.loads(row.get("raw_json") or "{}") if clean_text(row.get("raw_json")) else {},
        }

    @staticmethod
    def build_source_detail(row: pd.Series, source_op_id: str) -> Dict[str, Any]:
        def num_or_none(v):
            try:
                if pd.isna(v):
                    return None
            except Exception:
                pass
            try:
                return float(v)
            except Exception:
                return None

        raw = row_to_dict_safe(row)

        return {
            "system": clean_text(source_op_id).split("_")[0],
            "source_op_id": clean_text(source_op_id),
            "source_defect_uid": clean_text(row.get("source_defect_uid")),
            "sheet_id": clean_text(row.get("sheet_id")),
            "scan_time": normalize_source_raw_value(row.get("scan_time") or row.get("repair_time")),
            "line_id": clean_text(row.get("line_id")),
            "model_no": clean_text(row.get("model_no")),
            "chip_id": clean_text(row.get("chip_id")),
            "defect_no": clean_text(row.get("defect_no")),
            "signal_no": clean_text(row.get("signal_no")),
            "gate_no": clean_text(row.get("gate_no")),
            "defect_code": clean_text(row.get("defect_code")),
            "defect_size": clean_text(row.get("defect_size")),
            "defect_size_raw": clean_text(row.get("defect_size_raw")),
            "ori_x": num_or_none(row.get("ori_x")),
            "ori_y": num_or_none(row.get("ori_y")),
            "trans_x": num_or_none(row.get("trans_x")),
            "trans_y": num_or_none(row.get("trans_y")),
            "image_name": clean_text(row.get("image_name")),
            "img_url_path": clean_text(row.get("img_url_path")),
            "source_group_key": clean_text(row.get("source_group_key")),
            "raw": raw,
        }

    def build(
        self,
        inspection_df: pd.DataFrame,
        target_defects: pd.DataFrame,
        source_map: Dict[str, pd.DataFrame],
        source_state_map: Dict[str, pd.DataFrame],
    ) -> pd.DataFrame:
        if inspection_df is None or inspection_df.empty:
            return pd.DataFrame()

        targets = target_defects.copy() if target_defects is not None else pd.DataFrame()
        if not targets.empty:
            targets["sheet_id"] = normalize_string_series(targets["sheet_id"])
            targets["scan_time"] = pd.to_datetime(targets["scan_time"], errors="coerce")

        rows = []

        for _, insp_row in inspection_df.iterrows():
            sheet_id = clean_text(insp_row.get("sheet_id"))
            glass_type = clean_text(insp_row.get("glass_type")).upper()
            scan_time = pd.to_datetime(insp_row.get("scan_time"), errors="coerce")
            total_defect_qty = int(insp_row.get("total_defect_qty") or 0)

            station_list = self.station_list_by_type(glass_type)

            if not station_list:
                rows.append({
                    "sheet_id": sheet_id,
                    "glass_type": glass_type,
                    "scan_time": scan_time,
                    "line_id": insp_row.get("line_id"),
                    "model_no": insp_row.get("model_no"),
                    "total_defect_qty": total_defect_qty,
                    "source_op_id": "-",
                    "source_scan_time": None,
                    "source_defect_cnt": None,
                    "same_point_offset": None,
                    "same_point_defect_cnt": None,
                    "same_point_rate": None,
                    "point_detail": "[]",
                    "match_status": "INVALID_TYPE",
                    "match_status_detail": f"glass_type={glass_type}",
                })
                continue

            if not targets.empty:
                target_points = targets[
                    targets["sheet_id"].eq(sheet_id)
                    & targets["scan_time"].eq(scan_time)
                ].copy()
            else:
                target_points = pd.DataFrame()

            for process, station, source_op_id, offset in station_list:
                base = {
                    "sheet_id": sheet_id,
                    "glass_type": glass_type,
                    "scan_time": scan_time,
                    "line_id": insp_row.get("line_id"),
                    "model_no": insp_row.get("model_no"),
                    "total_defect_qty": total_defect_qty,
                    "source_op_id": source_op_id,
                }

                src = source_map.get(source_op_id, pd.DataFrame())
                if src is None:
                    src = pd.DataFrame()

                if not src.empty and "sheet_id" in src.columns:
                    src = src.copy()
                    src["sheet_id"] = normalize_string_series(src["sheet_id"])
                    ssrc = src[src["sheet_id"].eq(sheet_id)].copy()
                else:
                    ssrc = pd.DataFrame()

                stime_col = self.source_time_col(source_op_id)

                if ssrc.empty:
                    state_df = source_state_map.get(source_op_id, pd.DataFrame())
                    state_row = self.get_state_row(state_df, sheet_id, source_op_id)

                    cache_status = clean_text(state_row.get("cache_status")).upper() if state_row is not None else ""
                    cache_detail = clean_text(state_row.get("cache_status_detail")) if state_row is not None else ""

                    if cache_status in {"CACHED_NO_DEFECT", "ORACLE_NO_DEFECT", "AOI_NO_DEFECT"}:
                        base.update({
                            "source_scan_time": state_row.get("source_scan_time") if state_row is not None else None,
                            "source_defect_cnt": 0,
                            "same_point_offset": offset,
                            "same_point_defect_cnt": 0,
                            "same_point_rate": 0.0 if total_defect_qty > 0 else None,
                            "point_detail": "[]",
                            "match_status": "NO_SOURCE_DEFECT",
                            "match_status_detail": cache_detail or f"source group exists but no defect for {source_op_id}",
                        })
                    elif cache_status in {"ORACLE_QUERY_FAILED"}:
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
                source_defect_cnt = int(len(ssrc))

                if total_defect_qty <= 0 or target_points.empty:
                    base.update({
                        "source_scan_time": source_scan_time,
                        "source_defect_cnt": source_defect_cnt,
                        "same_point_offset": offset,
                        "same_point_defect_cnt": None,
                        "same_point_rate": None,
                        "point_detail": "[]",
                        "match_status": "NO_INSPECTION_DEFECT",
                        "match_status_detail": "no inspection defect raw or total_defect_qty=0",
                    })
                    rows.append(base)
                    continue

                valid_target = target_points.dropna(subset=["trans_x", "trans_y"]).copy()
                valid_src = ssrc.dropna(subset=["trans_x", "trans_y"]).copy()

                if valid_target.empty:
                    base.update({
                        "source_scan_time": source_scan_time,
                        "source_defect_cnt": source_defect_cnt,
                        "same_point_offset": offset,
                        "same_point_defect_cnt": None,
                        "same_point_rate": None,
                        "point_detail": "[]",
                        "match_status": "INSPECTION_COORD_INVALID",
                        "match_status_detail": "inspection defects exist but coordinates invalid",
                    })
                    rows.append(base)
                    continue

                if valid_src.empty:
                    base.update({
                        "source_scan_time": source_scan_time,
                        "source_defect_cnt": source_defect_cnt,
                        "same_point_offset": offset,
                        "same_point_defect_cnt": None,
                        "same_point_rate": None,
                        "point_detail": "[]",
                        "match_status": "SOURCE_COORD_INVALID",
                        "match_status_detail": "source defects exist but coordinates invalid",
                    })
                    rows.append(base)
                    continue

                pair_rows = []
                matched_target_uids = set()
                matched_source_uids = set()

                for _, t in valid_target.iterrows():
                    tx = float(t["trans_x"])
                    ty = float(t["trans_y"])
                    target_uid = clean_text(t.get("inspection_defect_uid"))

                    if not target_uid:
                        continue

                    temp = valid_src.copy()
                    temp["dx"] = (temp["trans_x"] - tx).abs()
                    temp["dy"] = (temp["trans_y"] - ty).abs()

                    temp = temp[
                        (temp["dx"] <= offset)
                        & (temp["dy"] <= offset)
                    ].copy()

                    if temp.empty:
                        continue

                    temp["distance"] = np.sqrt(temp["dx"] ** 2 + temp["dy"] ** 2)
                    temp = temp.sort_values(["distance"])
                    s = temp.iloc[0]

                    source_uid = clean_text(s.get("source_defect_uid"))

                    matched_target_uids.add(target_uid)

                    if source_uid:
                        matched_source_uids.add(source_uid)

                    target_detail = self.build_target_detail(t)
                    source_detail = self.build_source_detail(s, source_op_id)

                    pair_rows.append({
                        "index": len(pair_rows) + 1,
                        "group": "same_point",
                        "match": True,

                        # compatibility with existing frontend
                        "cell_defect_uid": target_uid,
                        "source_defect_uid": source_uid,

                        "cell_img": clean_text(t.get("img_url_path")),
                        "source_img": clean_text(s.get("img_url_path")),

                        "cell_info": target_detail,
                        "source_info": source_detail,

                        "cell_x": float(t["trans_x"]),
                        "cell_y": float(t["trans_y"]),
                        "source_x": float(s["trans_x"]),
                        "source_y": float(s["trans_y"]),

                        "cell_defect_code": "",
                        "source_defect_code": clean_text(s.get("defect_code")),
                        "cell_defect_size": clean_text(t.get("defect_size")),
                        "source_defect_size": clean_text(s.get("defect_size")),

                        "dx": float(s.get("dx")),
                        "dy": float(s.get("dy")),
                        "distance": float(s.get("distance")),

                        "target": target_detail,
                        "source": source_detail,
                        "match_detail": {
                            "offset": float(offset),
                            "dx": float(s.get("dx")),
                            "dy": float(s.get("dy")),
                            "distance": float(s.get("distance")),
                            "rank": 1,
                            "is_nearest": 1,
                            "coord_rule": "RECT_DX_DY",
                            "target_owner": "INSPECTION",
                        },
                    })

                same_point_defect_cnt = int(len(matched_target_uids))

                if same_point_defect_cnt > 0:
                    rate = same_point_defect_cnt / total_defect_qty if total_defect_qty > 0 else None
                    status = "MATCHED"
                    detail = (
                        f"same_point_cnt={same_point_defect_cnt}; "
                        f"target_same_point_cnt={same_point_defect_cnt}; "
                        f"source_same_point_cnt={len(matched_source_uids)}; "
                        f"inspection_defect_cnt={total_defect_qty}; "
                        f"source_defect_cnt={source_defect_cnt}; "
                        f"rate_def=target_same_point_cnt/inspection_defect_cnt"
                    )
                else:
                    rate = 0.0 if total_defect_qty > 0 else None
                    status = "NO_SAME_POINT"
                    detail = (
                        "source found but no same point; "
                        f"same_point_cnt=0; "
                        f"inspection_defect_cnt={total_defect_qty}; "
                        f"source_defect_cnt={source_defect_cnt}; "
                        f"rate_def=target_same_point_cnt/inspection_defect_cnt"
                    )

                base.update({
                    "source_scan_time": source_scan_time,
                    "source_defect_cnt": source_defect_cnt,
                    "same_point_offset": offset,
                    "same_point_defect_cnt": same_point_defect_cnt,
                    "same_point_rate": rate,
                    "point_detail": json_dumps_safe(pair_rows),
                    "match_status": status,
                    "match_status_detail": detail,
                })
                rows.append(base)

        out = pd.DataFrame(rows)

        for c in ["scan_time", "source_scan_time"]:
            if c in out.columns:
                out[c] = pd.to_datetime(out[c], errors="coerce")

        return out


# =============================================================================
# Summary Builders
# =============================================================================

class InspectionGlassSummaryBuilder:
    def build(self, same_point_df: pd.DataFrame) -> pd.DataFrame:
        if same_point_df is None or same_point_df.empty:
            return pd.DataFrame()

        d = same_point_df.copy()
        d["scan_time"] = pd.to_datetime(d.get("scan_time"), errors="coerce")

        base_cols = [
            "sheet_id",
            "glass_type",
            "scan_time",
            "line_id",
            "model_no",
            "total_defect_qty",
        ]

        for c in base_cols:
            if c not in d.columns:
                d[c] = None

        base = d[base_cols].drop_duplicates(
            subset=["sheet_id", "glass_type", "scan_time"]
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
            d.groupby(["sheet_id", "glass_type", "scan_time"], as_index=False)
            .agg(
                source_station_cnt=("source_op_id", "count"),
                source_found_station_cnt=("source_group_found_flag", "sum"),
                total_source_defect_cnt=("source_defect_cnt", sum_count),
                total_same_point_defect_cnt=("same_point_defect_cnt", sum_count),
            )
        )

        out = base.merge(grp, on=["sheet_id", "glass_type", "scan_time"], how="left")

        count_cols = [
            "total_defect_qty",
            "source_station_cnt",
            "source_found_station_cnt",
            "total_source_defect_cnt",
            "total_same_point_defect_cnt",
        ]

        for c in count_cols:
            if c not in out.columns:
                out[c] = 0
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0).astype(int)

        out["total_same_point_rate"] = np.where(
            out["total_defect_qty"].astype(float) > 0,
            out["total_same_point_defect_cnt"].astype(float) / out["total_defect_qty"].astype(float),
            0.0,
        )

        station_map = {
            "AOI_BPI": ("aoi_bpi_source_defect_cnt", "aoi_bpi_same_point_cnt"),
            "AOI_API": ("aoi_api_source_defect_cnt", "aoi_api_same_point_cnt"),
            "CF_OC": ("cf_oc_source_defect_cnt", "cf_oc_same_point_cnt"),
            "CF_PS": ("cf_ps_source_defect_cnt", "cf_ps_same_point_cnt"),
            "ARRAY_MOR": ("array_mor_source_defect_cnt", "array_mor_same_point_cnt"),
            "ARRAY_TAR": ("array_tar_source_defect_cnt", "array_tar_same_point_cnt"),
            "ARRAY_TOS": ("array_tos_source_defect_cnt", "array_tos_same_point_cnt"),
        }

        for src_col, sp_col in station_map.values():
            out[src_col] = 0
            out[sp_col] = 0

        for _, r in d.iterrows():
            src_col, sp_col = station_map.get(clean_text(r.get("source_op_id")).upper(), (None, None))
            if not src_col:
                continue

            m = (
                out["sheet_id"].eq(r["sheet_id"])
                & out["glass_type"].eq(r["glass_type"])
                & out["scan_time"].eq(r["scan_time"])
            )

            src_cnt = pd.to_numeric(r.get("source_defect_cnt"), errors="coerce")
            sp_cnt = pd.to_numeric(r.get("same_point_defect_cnt"), errors="coerce")

            out.loc[m, src_col] = 0 if pd.isna(src_cnt) else int(src_cnt)
            out.loc[m, sp_col] = 0 if pd.isna(sp_cnt) else int(sp_cnt)

        def judge_row(r):
            gt = clean_text(r.get("glass_type")).upper()
            if gt not in {"CF", "TFT"}:
                return "INVALID_TYPE"

            if int(r.get("total_defect_qty") or 0) == 0:
                return "NO_INSPECTION_DEFECT"

            same = int(r.get("total_same_point_defect_cnt") or 0)
            found = int(r.get("source_found_station_cnt") or 0)
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
            "inspection_defect_cnt=" + out["total_defect_qty"].astype(str)
            + "; source_station_cnt=" + out["source_station_cnt"].astype(str)
            + "; source_found_station_cnt=" + out["source_found_station_cnt"].astype(str)
            + "; total_source_defect_cnt=" + out["total_source_defect_cnt"].astype(str)
            + "; total_same_point_defect_cnt=" + out["total_same_point_defect_cnt"].astype(str)
        )

        final_cols = [
            "sheet_id",
            "glass_type",
            "scan_time",
            "line_id",
            "model_no",
            "total_defect_qty",

            "source_station_cnt",
            "source_found_station_cnt",
            "total_source_defect_cnt",
            "total_same_point_defect_cnt",
            "total_same_point_rate",

            "aoi_bpi_source_defect_cnt",
            "aoi_api_source_defect_cnt",
            "cf_oc_source_defect_cnt",
            "cf_ps_source_defect_cnt",
            "array_mor_source_defect_cnt",
            "array_tar_source_defect_cnt",
            "array_tos_source_defect_cnt",

            "aoi_bpi_same_point_cnt",
            "aoi_api_same_point_cnt",
            "cf_oc_same_point_cnt",
            "cf_ps_same_point_cnt",
            "array_mor_same_point_cnt",
            "array_tar_same_point_cnt",
            "array_tos_same_point_cnt",

            "judge",
            "judge_detail",
        ]

        for c in final_cols:
            if c not in out.columns:
                if c.endswith("_cnt") or c in {
                    "total_defect_qty",
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

        return out[final_cols].copy()


class ApiInspectionSummaryBuilder:
    def build(self, same_point_df: pd.DataFrame) -> pd.DataFrame:
        if same_point_df is None or same_point_df.empty:
            return pd.DataFrame()

        d = same_point_df.copy()

        out = pd.DataFrame()
        out["test_time"] = pd.to_datetime(d.get("scan_time"), errors="coerce")
        out["line_id"] = d.get("line_id")
        out["sheet_id_chip_id"] = d.get("sheet_id")
        out["abbr_cat"] = d.get("glass_type")
        out["model_no"] = d.get("model_no")
        out["total_defect_qty"] = d.get("total_defect_qty")

        out["source_op_id"] = d.get("source_op_id")
        out["source_scan_time"] = pd.to_datetime(d.get("source_scan_time"), errors="coerce")
        out["source_defect_cnt"] = d.get("source_defect_cnt")

        out["same_point_offset"] = d.get("same_point_offset")
        out["same_point_defect_cnt"] = d.get("same_point_defect_cnt")
        out["same_point_rate"] = d.get("same_point_rate")

        out["match_status"] = d.get("match_status")
        out["match_status_detail"] = d.get("match_status_detail")

        out["comment"] = None
        out["action"] = None
        out["modify_time"] = None
        out["editor"] = None

        final_cols = [
            "test_time",
            "line_id",
            "sheet_id_chip_id",
            "abbr_cat",
            "model_no",
            "total_defect_qty",

            "source_op_id",
            "source_scan_time",
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

        return out[final_cols].copy()


# =============================================================================
# Output Repository
# =============================================================================

class InspectionOutputRepository:
    def __init__(self, db: MySQLConnet, cfg: InspectionIncomingConfig):
        self.db = db
        self.cfg = cfg
        self.engine = db.engine

    def same_point_table_name(self, yyyymm: str) -> str:
        return self.cfg.same_point_base.replace("yyyymm", yyyymm).lower()

    def glass_summary_table_name(self, yyyymm: str) -> str:
        return self.cfg.glass_summary_base.replace("yyyymm", yyyymm).lower()

    def api_summary_table_name(self, yyyymm: str) -> str:
        return self.cfg.api_inspection_summary_base.replace("yyyymm", yyyymm).lower()

    def ensure_state_table(self):
        ddl = text(f"""
        CREATE TABLE IF NOT EXISTS {self.cfg.state_table} (
            job_name VARCHAR(80) PRIMARY KEY,
            last_end_dt DATETIME NULL,
            update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        with self.engine.begin() as conn:
            conn.execute(ddl)

    def set_last_end_dt(self, end_dt: datetime):
        self.ensure_state_table()
        sql = text(f"""
        INSERT INTO {self.cfg.state_table}(job_name, last_end_dt)
        VALUES(:job, :end_dt)
        ON DUPLICATE KEY UPDATE last_end_dt=VALUES(last_end_dt)
        """)
        with self.engine.begin() as conn:
            conn.execute(sql, {
                "job": self.cfg.state_job_name,
                "end_dt": end_dt,
            })

    def ensure_same_point_table(self, table_name: str):
        ddl = text(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,

            sheet_id VARCHAR(80) NOT NULL,
            glass_type VARCHAR(32) NULL,
            scan_time DATETIME NULL,

            line_id VARCHAR(120) NULL,
            model_no VARCHAR(120) NULL,
            total_defect_qty INT NULL,

            source_op_id VARCHAR(80) NOT NULL,
            source_scan_time DATETIME NULL,
            source_defect_cnt INT NULL,

            same_point_offset DOUBLE NULL,
            same_point_defect_cnt INT NULL,
            same_point_rate DOUBLE NULL,

            point_detail LONGTEXT NULL,

            match_status VARCHAR(80) NULL,
            match_status_detail VARCHAR(800) NULL,

            create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,

            INDEX idx_sheet_scan (sheet_id, scan_time),
            INDEX idx_sheet_type (sheet_id, glass_type),
            INDEX idx_source_op (source_op_id),
            INDEX idx_status (match_status),
            INDEX idx_rate (same_point_rate)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
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

            sheet_id VARCHAR(80) NOT NULL,
            glass_type VARCHAR(32) NULL,
            scan_time DATETIME NULL,

            line_id VARCHAR(120) NULL,
            model_no VARCHAR(120) NULL,
            total_defect_qty INT NULL,

            source_station_cnt INT DEFAULT 0,
            source_found_station_cnt INT DEFAULT 0,

            total_source_defect_cnt INT DEFAULT 0,
            total_same_point_defect_cnt INT DEFAULT 0,
            total_same_point_rate DOUBLE DEFAULT 0,

            aoi_bpi_source_defect_cnt INT DEFAULT 0,
            aoi_api_source_defect_cnt INT DEFAULT 0,
            cf_oc_source_defect_cnt INT DEFAULT 0,
            cf_ps_source_defect_cnt INT DEFAULT 0,
            array_mor_source_defect_cnt INT DEFAULT 0,
            array_tar_source_defect_cnt INT DEFAULT 0,
            array_tos_source_defect_cnt INT DEFAULT 0,

            aoi_bpi_same_point_cnt INT DEFAULT 0,
            aoi_api_same_point_cnt INT DEFAULT 0,
            cf_oc_same_point_cnt INT DEFAULT 0,
            cf_ps_same_point_cnt INT DEFAULT 0,
            array_mor_same_point_cnt INT DEFAULT 0,
            array_tar_same_point_cnt INT DEFAULT 0,
            array_tos_same_point_cnt INT DEFAULT 0,

            judge VARCHAR(80) NULL,
            judge_detail VARCHAR(800) NULL,

            create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,

            INDEX idx_sheet_scan (sheet_id, scan_time),
            INDEX idx_sheet_type (sheet_id, glass_type),
            INDEX idx_judge (judge)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        with self.engine.begin() as conn:
            conn.execute(ddl)

    def ensure_api_summary_table(self, table_name: str):
        ddl = text(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,

            test_time DATETIME NULL,
            line_id VARCHAR(120) NULL,
            sheet_id_chip_id VARCHAR(80) NOT NULL,
            abbr_cat VARCHAR(32) NULL,
            model_no VARCHAR(120) NULL,
            total_defect_qty INT NULL,

            source_op_id VARCHAR(80) NOT NULL,
            source_scan_time DATETIME NULL,
            source_defect_cnt INT NULL,

            same_point_offset DOUBLE NULL,
            same_point_defect_cnt INT NULL,
            same_point_rate DOUBLE NULL,

            match_status VARCHAR(80) NULL,
            match_status_detail VARCHAR(800) NULL,

            comment TEXT NULL,
            action VARCHAR(200) NULL,
            modify_time DATETIME NULL,
            editor VARCHAR(100) NULL,

            create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,

            INDEX idx_test_time (test_time),
            INDEX idx_sheet_time_station (sheet_id_chip_id, test_time, source_op_id),
            INDEX idx_type (abbr_cat),
            INDEX idx_source_op (source_op_id),
            INDEX idx_status (match_status),
            INDEX idx_rate (same_point_rate)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        with self.engine.begin() as conn:
            conn.execute(ddl)

    def save_same_point(self, df: pd.DataFrame):
        if df is None or df.empty:
            logging.info("[save_inspection_same_point] empty")
            return

        d = df.copy()
        d["scan_time"] = pd.to_datetime(d.get("scan_time"), errors="coerce")
        d["yyyymm"] = d["scan_time"].dt.strftime("%Y%m").fillna(datetime.now().strftime("%Y%m"))

        datetime_cols = [
            "scan_time",
            "source_scan_time",
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
            "sheet_id",
            "glass_type",
            "line_id",
            "model_no",
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

            dedup_keys = ["sheet_id", "glass_type", "scan_time", "source_op_id"]

            logging.info("[save_inspection_same_point] table=%s rows=%s dedup=%s", tb, len(g2), dedup_keys)

            self.db.append_or_create_dedup(
                table_name=tb,
                df=g2,
                dedup_keys=dedup_keys,
            )

    def save_glass_summary(self, df: pd.DataFrame):
        if df is None or df.empty:
            logging.info("[save_inspection_glass_summary] empty")
            return

        d = df.copy()
        d["scan_time"] = pd.to_datetime(d.get("scan_time"), errors="coerce")
        d["yyyymm"] = d["scan_time"].dt.strftime("%Y%m").fillna(datetime.now().strftime("%Y%m"))

        datetime_cols = ["scan_time", "create_time", "update_time"]

        zero_int_cols = [
            "total_defect_qty",
            "source_station_cnt",
            "source_found_station_cnt",
            "total_source_defect_cnt",
            "total_same_point_defect_cnt",

            "aoi_bpi_source_defect_cnt",
            "aoi_api_source_defect_cnt",
            "cf_oc_source_defect_cnt",
            "cf_ps_source_defect_cnt",
            "array_mor_source_defect_cnt",
            "array_tar_source_defect_cnt",
            "array_tos_source_defect_cnt",

            "aoi_bpi_same_point_cnt",
            "aoi_api_same_point_cnt",
            "cf_oc_same_point_cnt",
            "cf_ps_same_point_cnt",
            "array_mor_same_point_cnt",
            "array_tar_same_point_cnt",
            "array_tos_same_point_cnt",
        ]

        zero_float_cols = ["total_same_point_rate"]

        text_cols = [
            "sheet_id",
            "glass_type",
            "line_id",
            "model_no",
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

            dedup_keys = ["sheet_id", "glass_type", "scan_time"]

            logging.info("[save_inspection_glass_summary] table=%s rows=%s dedup=%s", tb, len(g2), dedup_keys)

            self.db.append_or_create_dedup(
                table_name=tb,
                df=g2,
                dedup_keys=dedup_keys,
            )

    def save_api_summary(self, df: pd.DataFrame):
        if df is None or df.empty:
            logging.info("[save_api_inspection_summary] empty")
            return

        d = df.copy()
        d["test_time"] = pd.to_datetime(d.get("test_time"), errors="coerce")
        d["yyyymm"] = d["test_time"].dt.strftime("%Y%m").fillna(datetime.now().strftime("%Y%m"))

        datetime_cols = [
            "test_time",
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
            "sheet_id_chip_id",
            "abbr_cat",
            "model_no",
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
            tb = self.api_summary_table_name(str(ym))
            self.ensure_api_summary_table(tb)

            g2 = g.drop(columns=["yyyymm"], errors="ignore").copy()

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

            dedup_keys = ["sheet_id_chip_id", "abbr_cat", "test_time", "source_op_id"]

            logging.info("[save_api_inspection_summary] table=%s rows=%s dedup=%s", tb, len(g2), dedup_keys)

            self.db.append_or_create_dedup(
                table_name=tb,
                df=g2,
                dedup_keys=dedup_keys,
            )


# =============================================================================
# Pipeline
# =============================================================================

class InspectionIncomingPipeline:
    def __init__(
        self,
        cfg: InspectionIncomingConfig,
        inspection_repo: InspectionInputRepository,
        aoi_repo: AoiSourceRepository,
        source_cache_repo: SourceCacheRepository,
        output_repo: InspectionOutputRepository,
        cf_extractor: CFSourceExtractor,
        array_extractor: ArraySourceExtractor,
        same_point_builder: InspectionSamePointBuilder,
        glass_summary_builder: InspectionGlassSummaryBuilder,
        api_summary_builder: ApiInspectionSummaryBuilder,
    ):
        self.cfg = cfg
        self.inspection_repo = inspection_repo
        self.aoi_repo = aoi_repo
        self.source_cache_repo = source_cache_repo
        self.output_repo = output_repo
        self.cf_extractor = cf_extractor
        self.array_extractor = array_extractor
        self.same_point_builder = same_point_builder
        self.glass_summary_builder = glass_summary_builder
        self.api_summary_builder = api_summary_builder

    def run(self, start_dt: datetime, end_dt: datetime):
        logging.info("[Pipeline] start_dt=%s end_dt=%s", start_dt, end_dt)

        summary_raw = self.inspection_repo.load_inspection_summary(start_dt, end_dt)
        logging.info("[Pipeline] inspection_summary_raw rows=%s", len(summary_raw))

        if summary_raw.empty:
            logging.info("[Pipeline] no inspection summary rows")
            self.output_repo.set_last_end_dt(end_dt)
            return

        inspection_df = self.inspection_repo.normalize_inspection_summary(summary_raw)
        logging.info("[Pipeline] latest inspection by sheet+type rows=%s", len(inspection_df))

        if inspection_df.empty:
            logging.info("[Pipeline] no valid inspection summary rows")
            self.output_repo.set_last_end_dt(end_dt)
            return

        raw_defect = self.inspection_repo.load_inspection_raw(inspection_df)
        logging.info("[Pipeline] inspection raw defect rows=%s", len(raw_defect))

        target_defects = self.inspection_repo.normalize_inspection_defects(raw_defect)
        logging.info("[Pipeline] normalized inspection defects rows=%s", len(target_defects))

        source_map: Dict[str, pd.DataFrame] = {}
        source_state_map: Dict[str, pd.DataFrame] = {}

        # AOI_BPI / AOI_API source
        aoi_bpi_df, aoi_bpi_state = self.aoi_repo.load_aoi_source(
            inspection_df,
            pi_type="BPI",
            start_dt=start_dt,
            end_dt=end_dt,
        )
        source_map["AOI_BPI"] = aoi_bpi_df
        source_state_map["AOI_BPI"] = aoi_bpi_state

        aoi_api_df, aoi_api_state = self.aoi_repo.load_aoi_source(
            inspection_df,
            pi_type="API",
            start_dt=start_dt,
            end_dt=end_dt,
        )
        source_map["AOI_API"] = aoi_api_df
        source_state_map["AOI_API"] = aoi_api_state

        logging.info(
            "[Pipeline] AOI source rows BPI=%s API=%s",
            len(aoi_bpi_df),
            len(aoi_api_df),
        )

        # CF source
        cf_df = inspection_df[inspection_df["glass_type"].astype(str).str.upper().eq("CF")].copy()
        cf_sheet_ids = cf_df["sheet_id"].dropna().astype(str).str.strip().unique().tolist()

        if cf_sheet_ids:
            cf_oc, cf_oc_state = self.source_cache_repo.load_or_fetch_source(
                process="CF",
                station="OC",
                sheet_ids=cf_sheet_ids,
                start_dt=start_dt,
                end_dt=end_dt,
                cf_extractor=self.cf_extractor,
            )

            cf_ps, cf_ps_state = self.source_cache_repo.load_or_fetch_source(
                process="CF",
                station="PS",
                sheet_ids=cf_sheet_ids,
                start_dt=start_dt,
                end_dt=end_dt,
                cf_extractor=self.cf_extractor,
            )
        else:
            cf_oc, cf_oc_state = pd.DataFrame(), pd.DataFrame()
            cf_ps, cf_ps_state = pd.DataFrame(), pd.DataFrame()

        source_map["CF_OC"] = cf_oc
        source_map["CF_PS"] = cf_ps
        source_state_map["CF_OC"] = cf_oc_state
        source_state_map["CF_PS"] = cf_ps_state

        # ARRAY source
        tft_df = inspection_df[inspection_df["glass_type"].astype(str).str.upper().eq("TFT")].copy()
        tft_sheet_ids = tft_df["sheet_id"].dropna().astype(str).str.strip().unique().tolist()

        if tft_sheet_ids:
            mor, mor_state = self.source_cache_repo.load_or_fetch_source(
                process="ARRAY",
                station="MOR",
                sheet_ids=tft_sheet_ids,
                start_dt=start_dt,
                end_dt=end_dt,
                array_extractor=self.array_extractor,
            )

            tar, tar_state = self.source_cache_repo.load_or_fetch_source(
                process="ARRAY",
                station="TAR",
                sheet_ids=tft_sheet_ids,
                start_dt=start_dt,
                end_dt=end_dt,
                array_extractor=self.array_extractor,
            )

            tos, tos_state = self.source_cache_repo.load_or_fetch_source(
                process="ARRAY",
                station="TOS",
                sheet_ids=tft_sheet_ids,
                start_dt=start_dt,
                end_dt=end_dt,
                array_extractor=self.array_extractor,
            )
        else:
            mor, mor_state = pd.DataFrame(), pd.DataFrame()
            tar, tar_state = pd.DataFrame(), pd.DataFrame()
            tos, tos_state = pd.DataFrame(), pd.DataFrame()

        source_map["ARRAY_MOR"] = mor
        source_map["ARRAY_TAR"] = tar
        source_map["ARRAY_TOS"] = tos

        source_state_map["ARRAY_MOR"] = mor_state
        source_state_map["ARRAY_TAR"] = tar_state
        source_state_map["ARRAY_TOS"] = tos_state

        logging.info(
            "[Pipeline] source rows CF_OC=%s CF_PS=%s MOR=%s TAR=%s TOS=%s",
            len(cf_oc),
            len(cf_ps),
            len(mor),
            len(tar),
            len(tos),
        )

        same_point_df = self.same_point_builder.build(
            inspection_df=inspection_df,
            target_defects=target_defects,
            source_map=source_map,
            source_state_map=source_state_map,
        )
        logging.info("[Pipeline] inspection same_point rows=%s", len(same_point_df))

        self.output_repo.save_same_point(same_point_df)

        glass_summary_df = self.glass_summary_builder.build(same_point_df)
        logging.info("[Pipeline] inspection glass_summary rows=%s", len(glass_summary_df))

        self.output_repo.save_glass_summary(glass_summary_df)

        api_summary_df = self.api_summary_builder.build(same_point_df)
        logging.info("[Pipeline] api_inspection_summary rows=%s", len(api_summary_df))

        self.output_repo.save_api_summary(api_summary_df)

        self.output_repo.set_last_end_dt(end_dt)

        logging.info("[Pipeline] done")


# =============================================================================
# Runner
# =============================================================================

def build_pipeline() -> InspectionIncomingPipeline:
    cfg = InspectionIncomingConfig()
    oracle_cfg = OracleConfig()

    inspection_input_db = MySQLConnet(cfg.inspection_input_db_name)
    aoi_input_db = MySQLConnet(cfg.aoi_input_db_name)
    source_cache_db = MySQLConnet(cfg.source_cache_db_name)
    output_db = MySQLConnet(cfg.output_db_name)

    inspection_repo = InspectionInputRepository(inspection_input_db, cfg)
    aoi_repo = AoiSourceRepository(aoi_input_db, cfg)
    source_cache_repo = SourceCacheRepository(source_cache_db, cfg)
    output_repo = InspectionOutputRepository(output_db, cfg)

    cf_oracle = OracleDBHandler(oracle_cfg.cf_url)
    array_oracle = OracleDBHandler(oracle_cfg.array_url)

    cf_extractor = CFSourceExtractor(cf_oracle, cfg)
    array_extractor = ArraySourceExtractor(array_oracle, cfg)

    same_point_builder = InspectionSamePointBuilder(cfg)
    glass_summary_builder = InspectionGlassSummaryBuilder()
    api_summary_builder = ApiInspectionSummaryBuilder()

    return InspectionIncomingPipeline(
        cfg=cfg,
        inspection_repo=inspection_repo,
        aoi_repo=aoi_repo,
        source_cache_repo=source_cache_repo,
        output_repo=output_repo,
        cf_extractor=cf_extractor,
        array_extractor=array_extractor,
        same_point_builder=same_point_builder,
        glass_summary_builder=glass_summary_builder,
        api_summary_builder=api_summary_builder,
    )


def one_run(
    pipe: InspectionIncomingPipeline,
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

    setup_logging(log_dir="logs", log_name="inspection_incoming_governance.txt")
    logging.info("=== Inspection Incoming Governance start ===")

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
        logging.info("=== Inspection Incoming Governance end once ===")
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
python RUN_CELL_INSPECTION_INCOMING_GOVERNANCE.py --once --start-time "2026-06-29 12:00:00" --end-time "2026-06-29 22:00:00"
python RUN_CELL_INSPECTION_INCOMING_GOVERNANCE.py --once --start-time "2026-06-16 12:00:00" --end-time "2026-06-16 15:00:00"
"""
