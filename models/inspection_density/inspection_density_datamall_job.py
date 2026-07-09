#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any

import pandas as pd
import requests
from sqlalchemy import text

from sql_db_connect2 import MySQLConnetFunc


# =========================================================
# Logging
# =========================================================
def build_daily_log_file(log_dir: str = "logs", prefix: str = "inspection_density_datamall") -> str:
    os.makedirs(log_dir, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    return os.path.join(log_dir, f"{prefix}_{today}.log")


def setup_logger(name: str = "inspection_density_datamall", log_dir: str = "logs") -> tuple[logging.Logger, str]:
    log_file = build_daily_log_file(log_dir=log_dir, prefix=name)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger, log_file

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s [%(funcName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    fh = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    sh = logging.StreamHandler()

    fh.setLevel(logging.INFO)
    sh.setLevel(logging.INFO)
    fh.setFormatter(fmt)
    sh.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(sh)

    return logger, log_file


logger, LOG_FILE = setup_logger()


# =========================================================
# Config / Schema / Table helper
# =========================================================
class InspectionDensityConfig:
    TARGET_DB = "piaoi_inspection_density"

    SUMMARY_BASE_TBN = "inspection_summary_table"
    RAW_BASE_TBN = "inspection_raw_table"
    API_SUMMARY_BASE_TBN = "inspection_api_summary"
    API_GLASS_DETAIL_BASE_TBN = "inspection_api_glass_detail"
    JOB_STATE_TBN = "inspection_datamall_job_state"

    SHIFT_BUCKET_OFFSET_MINUTES = 30
    SHIFT_DAY_START_HOUR = 7
    SHIFT_DAY_START_MINUTE = 30

    SUMMARY_URL = (
        "http://tcpaaie101.corpnet.auo.com:8005/api/datamall/"
        "eyJrZXkiOiAiMTcwZWNhZWMxNzAyZmJiZmQ4ZDljMTA3Y2U2YzI3NTQiLCAiaWQiOiAiMjAyMzA5MDYxNzUyMTU3MTE0MyJ9"
    )
    RAW_URL = (
        "http://tcpaaie101.corpnet.auo.com:8005/api/datamall/"
        "eyJrZXkiOiAiMjcwOWJlNzc4ZWNmOWZhMGEzYjc2MjBjN2MzNjMwN2YiLCAiaWQiOiAiMjAyMzA5MDYxNzUyNDg3MTE0NCJ9"
    )
    DATAMALL_JSON_KEY = "1"
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
    REQUEST_TIMEOUT = 20
    MAX_RETRY = 6
    RETRY_SLEEP_SEC = 30

    DEFAULT_REBUILD_HOURS = 3
    CHUNK_SIZE = 2000
    JOB_NAME = "inspection_density_datamall_job"


class InspectionDensitySchema:
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

    UNI_DEFECT_SIZES = ["S", "M", "L", "O"]
    DEFECT_SIZE_COL = "DEFECT_SIZE_TYPE"

    GROUP_KEYS = ["PI_HOUR", "TOOL_ID", "MODEL_NO", "TYPE"]

    MANUAL_KEY_COLS = ["pi_hour", "line_id", "model", "glass_type"]
    MANUAL_COLS = ["comment", "action", "Editor", "modify_time"]

    API_SUMMARY_COLS = [
        "pi_hour",
        "shift_day",
        "shift_week",
        "shift_month",
        "shift_start",
        "shift_end",
        "line_id",
        "model",
        "glass_type",
        "maingroup_glass_count",
        "maingroup_defect_count",
        "maingroup_density",
        "defect_code_glass_count",
        "small_defect_count",
        "middle_defect_count",
        "large_defect_count",
        "over_defect_count",
        "glass",
        "glass_size_detail",
        "comment",
        "action",
        "Editor",
        "modify_time",
    ]

    API_GLASS_DETAIL_COLS = [
        "pi_hour",
        "shift_day",
        "shift_week",
        "shift_month",
        "shift_start",
        "shift_end",
        "line_id",
        "model",
        "glass_type",
        "glass_id",
        "small_defect_count",
        "middle_defect_count",
        "large_defect_count",
        "over_defect_count",
        "defect_count",
        "has_defect",
    ]

    SUMMARY_DEDUP_KEYS = [
        "RUN_ID", "SHEET_ID", "SCAN_ENDTIME", "SCAN_STARTTIME",
        "TOOL_ID", "MODEL_NO", "TYPE", "RECIPE_NAME"
    ]

    RAW_DEDUP_KEYS = [
        "RUN_ID", "SHEET_ID", "SCAN_ENDTIME", "SCAN_STARTTIME",
        "TOOL_ID", "RECIPE_NAME", "DEFECT_ID", "COORD_X", "COORD_Y",
        "IMG_URL", "SP", "DEFECT", "DEFECT_AREA", "DEFECT_SIZE_TYPE",
        "FRONT_REVERSE"
    ]

    LATEST_GLASS_KEYS = ["SHEET_ID", "TOOL_ID", "MODEL_NO", "TYPE", "RECIPE_NAME"]

    RAW_MATCH_BASE_KEYS = ["RUN_ID", "SHEET_ID", "TOOL_ID", "RECIPE_NAME"]


class InspectionDensityTables:
    def __init__(self, cfg: InspectionDensityConfig):
        self.cfg = cfg

    def summary_table(self, yyyymm: str) -> str:
        return f"{self.cfg.SUMMARY_BASE_TBN}_{yyyymm}"

    def raw_table(self, yyyymm: str) -> str:
        return f"{self.cfg.RAW_BASE_TBN}_{yyyymm}"

    def api_summary_table(self, yyyymm: str) -> str:
        return f"{self.cfg.API_SUMMARY_BASE_TBN}_{yyyymm}"

    def api_glass_detail_table(self, yyyymm: str) -> str:
        return f"{self.cfg.API_GLASS_DETAIL_BASE_TBN}_{yyyymm}"


class InspectionDensityTime:
    def __init__(self, cfg: InspectionDensityConfig):
        self.cfg = cfg

    def add_shift_columns(self, df: pd.DataFrame, time_col: str = "SCAN_ENDTIME") -> pd.DataFrame:
        if df is None or df.empty:
            out = df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
            for c in ["PI_HOUR", "SHIFT_DAY", "SHIFT_WEEK", "SHIFT_MONTH", "SHIFT_START", "SHIFT_END"]:
                out[c] = pd.Series(dtype="object")
            return out

        out = df.copy()
        dt = pd.to_datetime(out[time_col], errors="coerce")

        shifted_hour = dt - pd.Timedelta(minutes=self.cfg.SHIFT_BUCKET_OFFSET_MINUTES)
        pi_hour_dt = shifted_hour.dt.floor("h")

        shift_day_anchor = dt - pd.Timedelta(
            hours=self.cfg.SHIFT_DAY_START_HOUR,
            minutes=self.cfg.SHIFT_DAY_START_MINUTE
        )
        shift_day = shift_day_anchor.dt.date

        shift_day_dt = pd.to_datetime(shift_day, errors="coerce")
        iso = shift_day_dt.dt.isocalendar()

        out["PI_HOUR"] = pi_hour_dt
        out["SHIFT_DAY"] = shift_day
        out["SHIFT_WEEK"] = iso["year"].astype(str) + "W" + iso["week"].astype(str).str.zfill(2)
        out["SHIFT_MONTH"] = shift_day_dt.dt.strftime("%Y%m")
        out["SHIFT_START"] = pi_hour_dt + pd.Timedelta(minutes=self.cfg.SHIFT_BUCKET_OFFSET_MINUTES)
        out["SHIFT_END"] = out["SHIFT_START"] + pd.Timedelta(hours=1)

        return out

    def to_pi_hour_range(self, start: datetime, end: datetime) -> Tuple[datetime, datetime]:
        start_bucket = (pd.Timestamp(start) - pd.Timedelta(minutes=self.cfg.SHIFT_BUCKET_OFFSET_MINUTES)).floor("h")
        end_bucket = (pd.Timestamp(end) - pd.Timedelta(minutes=self.cfg.SHIFT_BUCKET_OFFSET_MINUTES)).floor("h")
        return start_bucket.to_pydatetime(), end_bucket.to_pydatetime()

    def to_scan_time_cover_range(self, start: datetime, end: datetime) -> Tuple[datetime, datetime, datetime, datetime]:
        pi_start, pi_end = self.to_pi_hour_range(start, end)

        scan_start = pi_start + timedelta(minutes=self.cfg.SHIFT_BUCKET_OFFSET_MINUTES)
        scan_end = (
            pi_end
            + timedelta(minutes=self.cfg.SHIFT_BUCKET_OFFSET_MINUTES)
            + timedelta(hours=1)
            - timedelta(seconds=1)
        )
        return pi_start, pi_end, scan_start, scan_end


@dataclass
class InspectionDensityDomain:
    cfg: InspectionDensityConfig = InspectionDensityConfig()
    schema: InspectionDensitySchema = InspectionDensitySchema()

    def __post_init__(self):
        self.tables = InspectionDensityTables(self.cfg)
        self.time = InspectionDensityTime(self.cfg)


DOMAIN = InspectionDensityDomain()


# =========================================================
# DB helpers
# =========================================================
def table_exists(dbhandler: MySQLConnetFunc, table_name: str) -> bool:
    sql = text("""
      SELECT COUNT(*) FROM information_schema.TABLES
      WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :t
    """)
    with dbhandler.engine.begin() as conn:
        cnt = conn.execute(sql, {"db": dbhandler.db, "t": table_name}).scalar()
    return bool(cnt)


def get_table_safe(dbhandler: MySQLConnetFunc, table_name: str) -> pd.DataFrame:
    if not table_exists(dbhandler, table_name):
        return pd.DataFrame()
    sql = text(f"SELECT * FROM `{dbhandler.db}`.`{table_name}`")
    try:
        with dbhandler.engine.begin() as conn:
            df = pd.read_sql(sql, conn)
        return df if df is not None else pd.DataFrame()
    except Exception as e:
        logger.warning(f"[{dbhandler.db}.{table_name}] get_table failed: {e}")
        return pd.DataFrame()


def get_table_range_safe(
    dbhandler: MySQLConnetFunc,
    table_name: str,
    start: datetime,
    end: datetime,
    time_col: str = "SCAN_ENDTIME"
) -> pd.DataFrame:
    if not table_exists(dbhandler, table_name):
        return pd.DataFrame()

    sql = text(f"""
        SELECT *
        FROM `{dbhandler.db}`.`{table_name}`
        WHERE `{time_col}` >= :start_dt
          AND `{time_col}` <= :end_dt
    """)
    try:
        with dbhandler.engine.begin() as conn:
            df = pd.read_sql(sql, conn, params={"start_dt": start, "end_dt": end})
        return df if df is not None else pd.DataFrame()
    except Exception as e:
        logger.warning(
            f"[{dbhandler.db}.{table_name}] get_table_range_safe failed: {e}, "
            f"time_col={time_col}, start={start}, end={end}"
        )
        return pd.DataFrame()


def count_rows_in_range(
    dbhandler: MySQLConnetFunc,
    table_name: str,
    start: datetime,
    end: datetime,
    time_col: str
) -> int:
    if not table_exists(dbhandler, table_name):
        return 0

    sql = text(f"""
        SELECT COUNT(*) AS cnt
        FROM `{dbhandler.db}`.`{table_name}`
        WHERE `{time_col}` >= :start_dt
          AND `{time_col}` <= :end_dt
    """)
    with dbhandler.engine.begin() as conn:
        cnt = conn.execute(sql, {"start_dt": start, "end_dt": end}).scalar()
    return int(cnt or 0)


def count_total_rows(dbhandler: MySQLConnetFunc, table_name: str) -> int:
    if not table_exists(dbhandler, table_name):
        return 0
    sql = text(f"SELECT COUNT(*) FROM `{dbhandler.db}`.`{table_name}`")
    with dbhandler.engine.begin() as conn:
        cnt = conn.execute(sql).scalar()
    return int(cnt or 0)


def delete_rows_in_range(
    dbhandler: MySQLConnetFunc,
    table_name: str,
    start: datetime,
    end: datetime,
    time_col: str
) -> int:
    if not table_exists(dbhandler, table_name):
        return 0

    deleted_cnt = count_rows_in_range(dbhandler, table_name, start, end, time_col)
    if deleted_cnt <= 0:
        return 0

    sql = text(f"""
        DELETE FROM `{dbhandler.db}`.`{table_name}`
        WHERE `{time_col}` >= :start_dt
          AND `{time_col}` <= :end_dt
    """)
    with dbhandler.engine.begin() as conn:
        conn.execute(sql, {"start_dt": start, "end_dt": end})
    return deleted_cnt


def ensure_table_like_df(
    dbhandler: MySQLConnetFunc,
    table_name: str,
    df: pd.DataFrame
) -> None:
    if table_exists(dbhandler, table_name):
        return

    empty_df = df.iloc[0:0].copy()
    empty_df.to_sql(
        name=table_name,
        con=dbhandler.engine,
        schema=dbhandler.db,
        if_exists="fail",
        index=False
    )
    logger.info(f"[{dbhandler.db}.{table_name}] create table by dataframe schema 完成")


# =========================================================
# Schema ensure
# =========================================================
def ensure_column(dbhandler: MySQLConnetFunc, table_name: str, col: str, ddl: str) -> None:
    sql = text("""
      SELECT COUNT(*) FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :t AND COLUMN_NAME = :c
    """)
    with dbhandler.engine.begin() as conn:
        exists = conn.execute(sql, {"db": dbhandler.db, "t": table_name, "c": col}).scalar()
        if not exists:
            conn.execute(text(f"ALTER TABLE `{dbhandler.db}`.`{table_name}` ADD COLUMN `{col}` {ddl}"))
            logger.info(f"[{dbhandler.db}.{table_name}] ADD COLUMN {col} {ddl}")


def ensure_api_summary_table(dbhandler: MySQLConnetFunc, table_name: str) -> None:
    if not table_exists(dbhandler, table_name):
        ddl = f"""
        CREATE TABLE `{dbhandler.db}`.`{table_name}` (
          `pi_hour` DATETIME NOT NULL,
          `shift_day` DATE NULL,
          `shift_week` VARCHAR(8) NULL,
          `shift_month` CHAR(6) NULL,
          `shift_start` DATETIME NULL,
          `shift_end` DATETIME NULL,
          `line_id` VARCHAR(32) NOT NULL,
          `model` VARCHAR(64) NOT NULL,
          `glass_type` VARCHAR(32) NOT NULL,
          `maingroup_glass_count` INT DEFAULT 0,
          `maingroup_defect_count` INT DEFAULT 0,
          `maingroup_density` DOUBLE DEFAULT 0,
          `defect_code_glass_count` INT DEFAULT 0,
          `small_defect_count` INT DEFAULT 0,
          `middle_defect_count` INT DEFAULT 0,
          `large_defect_count` INT DEFAULT 0,
          `over_defect_count` INT DEFAULT 0,
          `glass` LONGTEXT,
          `glass_size_detail` LONGTEXT,
          `comment` TEXT,
          `action` TEXT,
          `Editor` VARCHAR(64),
          `modify_time` DATETIME NULL,
          UNIQUE KEY `uniq_pi_hour_line_model_type`
            (`pi_hour`,`line_id`,`model`,`glass_type`),
          KEY `idx_shift_day` (`shift_day`),
          KEY `idx_shift_week` (`shift_week`),
          KEY `idx_shift_month` (`shift_month`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        with dbhandler.engine.begin() as conn:
            conn.execute(text(ddl))
        logger.info(f"[{dbhandler.db}.{table_name}] create summary table 完成")
        return

    ensure_column(dbhandler, table_name, "shift_day", "DATE")
    ensure_column(dbhandler, table_name, "shift_week", "VARCHAR(8)")
    ensure_column(dbhandler, table_name, "shift_month", "CHAR(6)")
    ensure_column(dbhandler, table_name, "shift_start", "DATETIME")
    ensure_column(dbhandler, table_name, "shift_end", "DATETIME")
    ensure_column(dbhandler, table_name, "glass_size_detail", "LONGTEXT")
    ensure_column(dbhandler, table_name, "comment", "TEXT")
    ensure_column(dbhandler, table_name, "action", "TEXT")
    ensure_column(dbhandler, table_name, "Editor", "VARCHAR(64)")
    ensure_column(dbhandler, table_name, "modify_time", "DATETIME")
    ensure_column(dbhandler, table_name, "maingroup_density", "DOUBLE DEFAULT 0")


def ensure_api_glass_detail_table(dbhandler: MySQLConnetFunc, table_name: str) -> None:
    if table_exists(dbhandler, table_name):
        return

    ddl = f"""
    CREATE TABLE `{dbhandler.db}`.`{table_name}` (
      `pi_hour` DATETIME NOT NULL,
      `shift_day` DATE NULL,
      `shift_week` VARCHAR(8) NULL,
      `shift_month` CHAR(6) NULL,
      `shift_start` DATETIME NULL,
      `shift_end` DATETIME NULL,
      `line_id` VARCHAR(32) NOT NULL,
      `model` VARCHAR(64) NOT NULL,
      `glass_type` VARCHAR(32) NOT NULL,
      `glass_id` VARCHAR(64) NOT NULL,
      `small_defect_count` INT DEFAULT 0,
      `middle_defect_count` INT DEFAULT 0,
      `large_defect_count` INT DEFAULT 0,
      `over_defect_count` INT DEFAULT 0,
      `defect_count` INT DEFAULT 0,
      `has_defect` TINYINT(1) DEFAULT 0,
      PRIMARY KEY (`pi_hour`,`line_id`,`model`,`glass_type`,`glass_id`),
      KEY `idx_shift_day` (`shift_day`),
      KEY `idx_shift_week` (`shift_week`),
      KEY `idx_shift_month` (`shift_month`),
      KEY `idx_line_model_type` (`line_id`,`model`,`glass_type`),
      KEY `idx_glass_id` (`glass_id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    with dbhandler.engine.begin() as conn:
        conn.execute(text(ddl))
    logger.info(f"[{dbhandler.db}.{table_name}] create glass detail table 完成")


def ensure_job_state_table(dbhandler: MySQLConnetFunc, table_name: str) -> None:
    if table_exists(dbhandler, table_name):
        return

    ddl = f"""
    CREATE TABLE `{dbhandler.db}`.`{table_name}` (
      `job_name` VARCHAR(128) NOT NULL,
      `last_run_start_time` DATETIME NULL,
      `last_run_end_time` DATETIME NULL,
      `last_success_time` DATETIME NULL,
      `last_window_start` DATETIME NULL,
      `last_window_end` DATETIME NULL,
      `last_summary_rows` INT DEFAULT 0,
      `last_raw_rows` INT DEFAULT 0,
      `last_summary_new_rows` INT DEFAULT 0,
      `last_raw_new_rows` INT DEFAULT 0,
      `last_summary_max_scan_endtime` DATETIME NULL,
      `last_raw_max_scan_endtime` DATETIME NULL,
      `last_max_pi_hour` DATETIME NULL,
      `status` VARCHAR(32) NULL,
      `message` TEXT,
      `modify_time` DATETIME NULL,
      PRIMARY KEY (`job_name`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    with dbhandler.engine.begin() as conn:
        conn.execute(text(ddl))
    logger.info(f"[{dbhandler.db}.{table_name}] create job state table 完成")


# =========================================================
# Time range / month helpers
# =========================================================
def parse_dt(s: str) -> datetime:
    s = str(s).strip().replace("T", " ")
    fmts = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H",
        "%Y-%m-%d",
    ]
    for f in fmts:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            pass
    raise ValueError(f"Bad datetime: {s}")


def month_span(start: datetime, end: datetime) -> List[str]:
    yms = []
    cur = datetime(start.year, start.month, 1)
    last = datetime(end.year, end.month, 1)
    while cur <= last:
        yms.append(cur.strftime("%Y%m"))
        cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
    return yms


def month_span_by_pi_hour(start: datetime, end: datetime) -> List[str]:
    pi_start, pi_end = DOMAIN.time.to_pi_hour_range(start, end)
    return month_span(pi_start, pi_end)


def norm_pi_hour_key(v) -> str:
    ts = pd.to_datetime(v, errors="coerce")
    if pd.isna(ts):
        return ""
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def get_df_max_dt(df: pd.DataFrame, time_col: str) -> Optional[datetime]:
    if df is None or df.empty or time_col not in df.columns:
        return None
    s = pd.to_datetime(df[time_col], errors="coerce").dropna()
    if s.empty:
        return None
    return s.max().to_pydatetime()


def split_df_by_month(df: pd.DataFrame, time_col: str) -> Dict[str, pd.DataFrame]:
    if df is None or df.empty or time_col not in df.columns:
        return {}
    out = df.copy()
    out[time_col] = pd.to_datetime(out[time_col], errors="coerce")
    out = out[out[time_col].notna()].copy()
    if out.empty:
        return {}
    out["__yyyymm__"] = out[time_col].dt.strftime("%Y%m")
    result = {}
    for ym, g in out.groupby("__yyyymm__"):
        result[str(ym)] = g.drop(columns=["__yyyymm__"]).copy()
    return result


# =========================================================
# Load manual fields (preserve editor input)
# =========================================================
def load_manual_field_map(
    target_db: str,
    source_db: str,
    api_tbn: str
) -> Dict[Tuple[str, str, str, str], Dict[str, Any]]:
    manual_map: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}

    for db_name, tag in [(target_db, "target"), (source_db, "source")]:
        db = MySQLConnetFunc(db_name)
        if not table_exists(db, api_tbn):
            continue

        df = get_table_safe(db, api_tbn)
        if df.empty:
            continue

        for c in DOMAIN.schema.MANUAL_KEY_COLS + DOMAIN.schema.MANUAL_COLS:
            if c not in df.columns:
                df[c] = None

        for _, r in df.iterrows():
            key = (
                norm_pi_hour_key(r["pi_hour"]),
                str(r["line_id"] if pd.notna(r["line_id"]) else ""),
                str(r["model"] if pd.notna(r["model"]) else ""),
                str(r["glass_type"] if pd.notna(r["glass_type"]) else ""),
            )

            comment = r.get("comment", "")
            action = r.get("action", "")
            editor = r.get("Editor", "")
            modify_time = r.get("modify_time", None)

            has_manual = (
                (pd.notna(comment) and str(comment) != "") or
                (pd.notna(action) and str(action) != "") or
                (pd.notna(editor) and str(editor) != "")
            )
            if not has_manual:
                continue

            if key not in manual_map:
                manual_map[key] = {
                    "comment": "" if pd.isna(comment) else comment,
                    "action": "" if pd.isna(action) else action,
                    "Editor": "" if pd.isna(editor) else editor,
                    "modify_time": modify_time if pd.notna(modify_time) else None,
                    "__from": tag
                }

    logger.info(f"[load_manual_field_map] [{api_tbn}] manual fields 載入 {len(manual_map)} 筆")
    return manual_map


# =========================================================
# Data cleaning helpers
# =========================================================
def norm_str(v: Any) -> str:
    if pd.isna(v):
        return ""
    return str(v).strip()


def safe_int(v: Any, default: int = 0) -> int:
    try:
        if pd.isna(v):
            return default
        return int(float(v))
    except Exception:
        return default


def normalize_defect_size(v: Any) -> str:
    s = norm_str(v).upper()
    if s in {"S", "SMALL"}:
        return "S"
    if s in {"M", "MID", "MIDDLE"}:
        return "M"
    if s in {"L", "LARGE"}:
        return "L"
    if s in {"O", "OVER"}:
        return "O"
    return ""


def split_recipe_to_model_type(df: pd.DataFrame, col: str = "RECIPE_NAME") -> pd.DataFrame:
    if df is None or df.empty:
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()

    out = df.copy()
    if col not in out.columns:
        if "MODEL_NO" not in out.columns:
            out["MODEL_NO"] = ""
        if "TYPE" not in out.columns:
            out["TYPE"] = ""
        return out

    s = out[col].astype(str)
    parts = s.str.split("-", n=1, expand=True)

    if "MODEL_NO" not in out.columns:
        out["MODEL_NO"] = ""
    if "TYPE" not in out.columns:
        out["TYPE"] = ""

    out["MODEL_NO"] = parts[0].fillna("").astype(str).str.strip()
    out["TYPE"] = (
        parts[1].fillna("").astype(str).str.strip()
        if parts.shape[1] > 1 else ""
    )
    return out


def filter_df_by_time(
    df: pd.DataFrame,
    start: Optional[datetime],
    end: Optional[datetime],
    time_col: str = "SCAN_ENDTIME"
) -> pd.DataFrame:
    if df is None or df.empty or time_col not in df.columns:
        return df

    out = df.copy()
    out[time_col] = pd.to_datetime(out[time_col], errors="coerce")
    out = out[out[time_col].notna()]

    if start is not None:
        out = out[out[time_col] >= start]
    if end is not None:
        out = out[out[time_col] <= end]

    return out


def dedup_by_keys(df: pd.DataFrame, keys: List[str], keep: str = "last") -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=df.columns if isinstance(df, pd.DataFrame) else None)

    out = df.copy()
    use_keys = [k for k in keys if k in out.columns]

    if not use_keys:
        return out.drop_duplicates(keep=keep).reset_index(drop=True)

    for c in use_keys:
        if pd.api.types.is_datetime64_any_dtype(out[c]):
            out[c] = pd.to_datetime(out[c], errors="coerce")
        else:
            out[c] = out[c].astype("object").where(out[c].notna(), None)

    out = out.drop_duplicates(subset=use_keys, keep=keep).reset_index(drop=True)
    return out


def preprocess_raw_for_detail(raw_df: pd.DataFrame) -> pd.DataFrame:
    if raw_df is None or raw_df.empty:
        out = pd.DataFrame(columns=DOMAIN.schema.RAW_COLS)
        out["MODEL_NO"] = pd.Series(dtype="object")
        out["TYPE"] = pd.Series(dtype="object")
        out["PI_HOUR"] = pd.Series(dtype="datetime64[ns]")
        return out

    out = raw_df.copy()

    out = split_recipe_to_model_type(out, "RECIPE_NAME")

    for c in ["RUN_ID", "SHEET_ID", "TOOL_ID", "RECIPE_NAME", "MODEL_NO", "TYPE", "DEFECT_ID"]:
        if c not in out.columns:
            out[c] = ""
        out[c] = out[c].map(norm_str)

    for c in ["SCAN_ENDTIME", "SCAN_STARTTIME"]:
        if c not in out.columns:
            out[c] = pd.NaT
        out[c] = pd.to_datetime(out[c], errors="coerce")

    for c in ["COORD_X", "COORD_Y"]:
        if c not in out.columns:
            out[c] = pd.NA
        out[c] = pd.to_numeric(out[c], errors="coerce")

    if "DEFECT_SIZE_TYPE" not in out.columns:
        out["DEFECT_SIZE_TYPE"] = ""
    out["DEFECT_SIZE_TYPE"] = out["DEFECT_SIZE_TYPE"].map(normalize_defect_size)

    if "PI_HOUR" not in out.columns:
        out = DOMAIN.time.add_shift_columns(out, "SCAN_ENDTIME")

    sort_cols = [c for c in ["RUN_ID", "SHEET_ID", "TOOL_ID", "RECIPE_NAME", "PI_HOUR", "SCAN_ENDTIME", "SCAN_STARTTIME"] if c in out.columns]
    if sort_cols:
        out = out.sort_values(sort_cols, ascending=True, na_position="last").reset_index(drop=True)

    return out


def pick_latest_summary_per_glass(summary_rows_df: pd.DataFrame) -> pd.DataFrame:
    """
    同片條件：
    SHEET_ID + TOOL_ID + MODEL_NO + TYPE + RECIPE_NAME
    只保留最新 SCAN_ENDTIME / SCAN_STARTTIME
    """
    if summary_rows_df is None or summary_rows_df.empty:
        return pd.DataFrame(columns=summary_rows_df.columns if isinstance(summary_rows_df, pd.DataFrame) else None)

    out = summary_rows_df.copy()

    for c in ["SHEET_ID", "TOOL_ID", "MODEL_NO", "TYPE", "RECIPE_NAME"]:
        if c not in out.columns:
            out[c] = ""
        out[c] = out[c].map(norm_str)

    for c in ["SCAN_ENDTIME", "SCAN_STARTTIME"]:
        if c not in out.columns:
            out[c] = pd.NaT
        out[c] = pd.to_datetime(out[c], errors="coerce")

    out = out.sort_values(
        by=["SCAN_ENDTIME", "SCAN_STARTTIME"],
        ascending=[True, True],
        na_position="last"
    ).reset_index(drop=True)

    out = out.drop_duplicates(
        subset=["SHEET_ID", "TOOL_ID", "MODEL_NO", "TYPE", "RECIPE_NAME"],
        keep="last"
    ).reset_index(drop=True)

    return out

def filter_raw_like_defect_map_for_group(
    raw_df: pd.DataFrame,
    pi_hour: Any,
    line_id: Any,
    model_no: Any,
    glass_type: Any,
    glass_ids: List[str],
) -> pd.DataFrame:
    """
    完全比照 aoi_inspection_density_defect_map.py 的群組篩選方式：

    條件：
      1. TOOL_ID == line_id
      2. RECIPE_NAME == f"{model_no}-{glass_type}"
      3. SHEET_ID in glass_ids
      4. SCAN_ENDTIME 落在 pi_hour 對應 bucket:
         [pi_hour + 30min, pi_hour + 90min)

    注意：
      - 不使用 RUN_ID
      - 不使用 summary row 自己的 RECIPE_NAME
      - 不做單片候選 lookup
    """
    if raw_df is None or raw_df.empty:
        return pd.DataFrame(columns=DOMAIN.schema.RAW_COLS)

    out = raw_df.copy()

    for col in ["TOOL_ID", "SHEET_ID", "RECIPE_NAME", "SCAN_ENDTIME"]:
        if col not in out.columns:
            out[col] = pd.NA

    out["TOOL_ID"] = out["TOOL_ID"].map(norm_str)
    out["SHEET_ID"] = out["SHEET_ID"].map(norm_str)
    out["RECIPE_NAME"] = out["RECIPE_NAME"].map(norm_str)
    out["SCAN_ENDTIME"] = pd.to_datetime(out["SCAN_ENDTIME"], errors="coerce")

    pi_hour_dt = pd.to_datetime(pi_hour, errors="coerce")
    if pd.isna(pi_hour_dt):
        return out.iloc[0:0].copy()

    bucket_start, bucket_end = pi_hour_to_scan_end_range_for_rebuild(pi_hour_dt)
    recipe_name = f"{norm_str(model_no)}-{norm_str(glass_type)}"
    glass_set = {norm_str(g) for g in glass_ids if norm_str(g)}

    if not glass_set:
        return out.iloc[0:0].copy()

    out = out[out["TOOL_ID"] == norm_str(line_id)]
    out = out[out["RECIPE_NAME"] == recipe_name]
    out = out[out["SHEET_ID"].isin(glass_set)]
    out = out[out["SCAN_ENDTIME"].notna()]
    out = out[(out["SCAN_ENDTIME"] >= bucket_start) & (out["SCAN_ENDTIME"] < bucket_end)]

    return out.reset_index(drop=True)







def build_raw_glass_map_from_group_raw(raw_group_df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """
    將已經過 group 條件篩選後的 raw，
    依 SHEET_ID 切成每片 glass 的 dataframe。
    """
    result: Dict[str, pd.DataFrame] = {}

    if raw_group_df is None or raw_group_df.empty:
        return result

    work = raw_group_df.copy()

    if "SHEET_ID" not in work.columns:
        work["SHEET_ID"] = ""

    work["SHEET_ID"] = work["SHEET_ID"].map(norm_str)
    work["SCAN_ENDTIME"] = pd.to_datetime(work.get("SCAN_ENDTIME"), errors="coerce")
    work["SCAN_STARTTIME"] = pd.to_datetime(work.get("SCAN_STARTTIME"), errors="coerce")

    work = work.sort_values(
        by=["SHEET_ID", "SCAN_ENDTIME", "SCAN_STARTTIME"],
        ascending=True,
        na_position="last"
    ).reset_index(drop=True)

    for gid, g in work.groupby("SHEET_ID", dropna=False, sort=False):
        gid = norm_str(gid)
        if not gid:
            continue
        result[gid] = g.reset_index(drop=True).copy()

    return result









    
def keep_latest_scan_batch_per_glass(raw_one_glass: pd.DataFrame) -> pd.DataFrame:
    """
    對單片 glass 的 raw，只保留最新的一批 scan：
      1. 最大 SCAN_ENDTIME
      2. 若同 endtime 多批，再取最大 SCAN_STARTTIME
    """
    if raw_one_glass is None or raw_one_glass.empty:
        return pd.DataFrame(columns=raw_one_glass.columns if isinstance(raw_one_glass, pd.DataFrame) else None)

    out = raw_one_glass.copy()
    out["SCAN_ENDTIME"] = pd.to_datetime(out["SCAN_ENDTIME"], errors="coerce")
    out["SCAN_STARTTIME"] = pd.to_datetime(out["SCAN_STARTTIME"], errors="coerce")

    valid = out[out["SCAN_ENDTIME"].notna()].copy()
    if valid.empty:
        return out.iloc[0:0].copy()

    max_end = valid["SCAN_ENDTIME"].max()
    valid = valid[valid["SCAN_ENDTIME"] == max_end].copy()

    valid2 = valid[valid["SCAN_STARTTIME"].notna()].copy()
    if not valid2.empty:
        max_start = valid2["SCAN_STARTTIME"].max()
        valid = valid2[valid2["SCAN_STARTTIME"] == max_start].copy()

    return valid.reset_index(drop=True)


def dedup_raw_xy_keep_first(raw_one_glass: pd.DataFrame) -> pd.DataFrame:
    """
    同片同次 scan 的 raw defect：
    用 COORD_X, COORD_Y 去重
    重複保留第一筆
    """
    if raw_one_glass is None or raw_one_glass.empty:
        return pd.DataFrame(columns=raw_one_glass.columns if isinstance(raw_one_glass, pd.DataFrame) else None)

    out = raw_one_glass.copy()

    for c in ["COORD_X", "COORD_Y"]:
        if c not in out.columns:
            out[c] = pd.NA
        out[c] = pd.to_numeric(out[c], errors="coerce")

    out = out.reset_index(drop=True)
    out = out.drop_duplicates(subset=["COORD_X", "COORD_Y"], keep="first").reset_index(drop=True)
    return out


def calc_size_counts_from_raw(raw_one_glass_xy_dedup: pd.DataFrame) -> Tuple[int, int, int, int, int]:
    if raw_one_glass_xy_dedup is None or raw_one_glass_xy_dedup.empty:
        return 0, 0, 0, 0, 0

    size_series = raw_one_glass_xy_dedup["DEFECT_SIZE_TYPE"].astype(str).str.strip().str.upper()
    s_cnt = int((size_series == "S").sum())
    m_cnt = int((size_series == "M").sum())
    l_cnt = int((size_series == "L").sum())
    o_cnt = int((size_series == "O").sum())
    def_cnt = int(len(raw_one_glass_xy_dedup))
    return s_cnt, m_cnt, l_cnt, o_cnt, def_cnt


def dedup_detail_df_by_pk(detail_df: pd.DataFrame) -> pd.DataFrame:
    if detail_df is None or detail_df.empty:
        return pd.DataFrame(columns=DOMAIN.schema.API_GLASS_DETAIL_COLS)

    out = detail_df.copy()
    for c in ["pi_hour", "shift_start", "shift_end"]:
        if c in out.columns:
            out[c] = pd.to_datetime(out[c], errors="coerce")

    out = out.drop_duplicates(
        subset=["pi_hour", "line_id", "model", "glass_type", "glass_id"],
        keep="last"
    ).reset_index(drop=True)

    return out


# =========================================================
# Build detail & summary DF
# =========================================================
def fetch_raw_group_like_router(
    dbhandler: MySQLConnetFunc,
    pi_hour: Any,
    line_id: Any,
    model_no: Any,
    glass_type: Any,
    glass_ids: List[str],
) -> pd.DataFrame:
    """
    完全比照 aoi_inspection_density_defect_map.py 的查法：
    1. 先直接去對應月份 raw table 查 DB
    2. base_match:
         - RECIPE_NAME = f"{model_no}-{glass_type}"
         - TOOL_ID = line_id
    3. in_key = SHEET_ID, in_values = glass_ids
    4. 再用 bucket 過濾 SCAN_ENDTIME

    這樣 rebuild 與 router 就走同一條資料路徑。
    """
    pi_hour_dt = pd.to_datetime(pi_hour, errors="coerce")
    if pd.isna(pi_hour_dt):
        return pd.DataFrame(columns=DOMAIN.schema.RAW_COLS)

    glass_list = [norm_str(g) for g in glass_ids if norm_str(g)]
    if not glass_list:
        return pd.DataFrame(columns=DOMAIN.schema.RAW_COLS)

    yyyymm = pi_hour_dt.strftime("%Y%m")
    raw_tbn = DOMAIN.tables.raw_table(yyyymm)
    recipe_name = f"{norm_str(model_no)}-{norm_str(glass_type)}"

    if not table_exists(dbhandler, raw_tbn):
        logger.warning(f"[fetch_raw_group_like_router] table not exists: {dbhandler.db}.{raw_tbn}")
        return pd.DataFrame(columns=DOMAIN.schema.RAW_COLS)

    base_match = {
        "RECIPE_NAME": recipe_name,
        "TOOL_ID": norm_str(line_id),
    }

    try:
        df = dbhandler.get_rows_df_in(
            table_name=raw_tbn,
            base_keys=base_match,
            in_key="SHEET_ID",
            in_values=glass_list,
        )
    except Exception as e:
        logger.warning(
            f"[fetch_raw_group_like_router] get_rows_df_in failed, "
            f"table={raw_tbn}, base_match={base_match}, glass_cnt={len(glass_list)}, err={e}"
        )
        return pd.DataFrame(columns=DOMAIN.schema.RAW_COLS)

    if df is None or df.empty:
        logger.info(
            f"[fetch_raw_group_like_router] DB no rows, "
            f"table={raw_tbn}, tool={line_id}, recipe={recipe_name}, glass_cnt={len(glass_list)}"
        )
        return pd.DataFrame(columns=DOMAIN.schema.RAW_COLS)

    for c in DOMAIN.schema.RAW_COLS:
        if c not in df.columns:
            df[c] = None

    df = df.copy()
    df["TOOL_ID"] = df["TOOL_ID"].map(norm_str)
    df["SHEET_ID"] = df["SHEET_ID"].map(norm_str)
    df["RECIPE_NAME"] = df["RECIPE_NAME"].map(norm_str)
    df["SCAN_ENDTIME"] = pd.to_datetime(df["SCAN_ENDTIME"], errors="coerce")
    if "SCAN_STARTTIME" in df.columns:
        df["SCAN_STARTTIME"] = pd.to_datetime(df["SCAN_STARTTIME"], errors="coerce")
    else:
        df["SCAN_STARTTIME"] = pd.NaT

    bucket_start, bucket_end = pi_hour_to_scan_end_range_for_rebuild(pi_hour_dt)

    before_bucket = len(df)
    df = df[df["SCAN_ENDTIME"].notna()].copy()
    df = df[(df["SCAN_ENDTIME"] >= bucket_start) & (df["SCAN_ENDTIME"] < bucket_end)].copy()

    logger.info(
        f"[fetch_raw_group_like_router] "
        f"table={raw_tbn}, tool={line_id}, recipe={recipe_name}, glass_cnt={len(glass_list)}, "
        f"db_rows={before_bucket}, bucket_rows={len(df)}, "
        f"bucket=({bucket_start} ~ {bucket_end})"
    )

    return df.reset_index(drop=True)

def build_detail_and_summary_df(
    dbhandler: MySQLConnetFunc,
    summary_df: pd.DataFrame,
    manual_map: Optional[Dict[Tuple[str, str, str, str], Dict[str, Any]]] = None
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    schema = DOMAIN.schema

    if summary_df is None or summary_df.empty:
        return (
            pd.DataFrame(columns=schema.API_SUMMARY_COLS),
            pd.DataFrame(columns=schema.API_GLASS_DETAIL_COLS)
        )

    summary_work = summary_df.copy()

    for c in ["RUN_ID", "SHEET_ID", "TOOL_ID", "RECIPE_NAME", "MODEL_NO", "TYPE"]:
        if c not in summary_work.columns:
            summary_work[c] = ""
        summary_work[c] = summary_work[c].map(norm_str)

    for c in ["SCAN_ENDTIME", "SCAN_STARTTIME", "PI_HOUR", "SHIFT_START", "SHIFT_END"]:
        if c in summary_work.columns:
            summary_work[c] = pd.to_datetime(summary_work[c], errors="coerce")

    summary_groups = summary_work.groupby(schema.GROUP_KEYS, dropna=False)

    detail_rows: List[Dict[str, Any]] = []
    summary_rows_out: List[Dict[str, Any]] = []

    for main_keys, summary_rows_df in summary_groups:
        pi_hour, tool_id, model_no, type_ = main_keys

        if summary_rows_df.empty:
            continue

        first = summary_rows_df.iloc[0]
        shift_day = first.get("SHIFT_DAY", None)
        shift_week = first.get("SHIFT_WEEK", None)
        shift_month = first.get("SHIFT_MONTH", None)
        shift_start = first.get("SHIFT_START", None)
        shift_end = first.get("SHIFT_END", None)

        glass_summary_rows = pick_latest_summary_per_glass(summary_rows_df)

        glass_ids = (
            glass_summary_rows["SHEET_ID"]
            .astype(str)
            .dropna()
            .map(str.strip)
            .replace("", pd.NA)
            .dropna()
            .drop_duplicates()
            .tolist()
        )

        raw_group = fetch_raw_group_like_router(
            dbhandler=dbhandler,
            pi_hour=pi_hour,
            line_id=tool_id,
            model_no=model_no,
            glass_type=type_,
            glass_ids=glass_ids,
        )

        raw_group = preprocess_raw_for_detail(raw_group)
        raw_glass_map = build_raw_glass_map_from_group_raw(raw_group)

        glass_detail_json_list: List[Dict[str, Any]] = []

        total_s = 0
        total_m = 0
        total_l = 0
        total_o = 0
        maingroup_defect_count_sum = 0
        defect_glass_count = 0

        matched_raw_rows_total = 0
        matched_raw_glass_count = 0
        missing_raw_glass_count = 0

        for _, srow in glass_summary_rows.iterrows():
            gid = norm_str(srow.get("SHEET_ID"))
            if not gid:
                continue

            raw_one = raw_glass_map.get(gid, pd.DataFrame())

            logger.info(
                f"[glass_match] "
                f"gid={gid}, "
                f"tool={norm_str(tool_id)}, "
                f"std_recipe={norm_str(model_no)}-{norm_str(type_)}, "
                f"summary_recipe={norm_str(srow.get('RECIPE_NAME'))}, "
                f"run_id={norm_str(srow.get('RUN_ID'))}, "
                f"pi_hour={pd.to_datetime(pi_hour, errors='coerce')}, "
                f"matched_raw_rows_before_latest={0 if raw_one is None else len(raw_one)}"
            )

            if raw_one is None or raw_one.empty:
                missing_raw_glass_count += 1
                s_cnt = m_cnt = l_cnt = o_cnt = def_cnt = 0
            else:
                raw_one = keep_latest_scan_batch_per_glass(raw_one)

                if raw_one.empty:
                    missing_raw_glass_count += 1
                    s_cnt = m_cnt = l_cnt = o_cnt = def_cnt = 0
                else:
                    matched_raw_glass_count += 1
                    raw_one_xy = dedup_raw_xy_keep_first(raw_one)
                    matched_raw_rows_total += len(raw_one_xy)
                    s_cnt, m_cnt, l_cnt, o_cnt, def_cnt = calc_size_counts_from_raw(raw_one_xy)

            total_s += s_cnt
            total_m += m_cnt
            total_l += l_cnt
            total_o += o_cnt
            maingroup_defect_count_sum += def_cnt
            if def_cnt > 0:
                defect_glass_count += 1

            detail_rows.append({
                "pi_hour": pi_hour,
                "shift_day": shift_day,
                "shift_week": shift_week,
                "shift_month": shift_month,
                "shift_start": shift_start,
                "shift_end": shift_end,
                "line_id": tool_id,
                "model": model_no,
                "glass_type": type_,
                "glass_id": gid,
                "small_defect_count": s_cnt,
                "middle_defect_count": m_cnt,
                "large_defect_count": l_cnt,
                "over_defect_count": o_cnt,
                "defect_count": def_cnt,
                "has_defect": 1 if def_cnt > 0 else 0,
            })

            glass_detail_json_list.append({
                "glass_id": gid,
                "S": s_cnt,
                "M": m_cnt,
                "L": l_cnt,
                "O": o_cnt,
                "def_count": def_cnt,
            })

        key = (
            norm_pi_hour_key(pi_hour),
            norm_str(tool_id),
            norm_str(model_no),
            norm_str(type_),
        )
        manual = manual_map.get(key, {}) if manual_map else {}

        comment = manual.get("comment", "") or ""
        action = manual.get("action", "") or ""
        editor = manual.get("Editor", "") or ""
        modify_time = manual.get("modify_time", None)

        if modify_time is None or modify_time == "":
            modify_time = datetime.now()
        else:
            modify_time = pd.to_datetime(modify_time, errors="coerce")
        if pd.isna(modify_time):
            modify_time = datetime.now()

        logger.info(
            f"[build_api_group] "
            f"pi_hour={pi_hour}, tool={tool_id}, model={model_no}, type={type_}, "
            f"glass_count={len(glass_summary_rows)}, display_glass_count={len(glass_ids)}, "
            f"matched_raw_glass={matched_raw_glass_count}, missing_raw_glass={missing_raw_glass_count}, "
            f"matched_raw_rows={matched_raw_rows_total}, "
            f"maingroup_defect_count={maingroup_defect_count_sum}, defect_glass_count={defect_glass_count}, "
            f"raw_S/M/L/O={total_s}/{total_m}/{total_l}/{total_o}, "
            f"db_route_rule=TOOL_ID + MODEL-TYPE recipe + SHEET_ID in glass_list + bucket(SCAN_ENDTIME)"
        )

        maingroup_glass_count = int(len(glass_summary_rows))
        maingroup_defect_count = int(maingroup_defect_count_sum)
        maingroup_density = (
            float(maingroup_defect_count) / float(maingroup_glass_count)
            if maingroup_glass_count > 0 else 0.0
        )

        summary_rows_out.append({
            "pi_hour": pi_hour,
            "shift_day": shift_day,
            "shift_week": shift_week,
            "shift_month": shift_month,
            "shift_start": shift_start,
            "shift_end": shift_end,
            "line_id": tool_id,
            "model": model_no,
            "glass_type": type_,
            "maingroup_glass_count": maingroup_glass_count,
            "maingroup_defect_count": maingroup_defect_count,
            "maingroup_density": maingroup_density,
            "defect_code_glass_count": int(defect_glass_count),
            "small_defect_count": int(total_s),
            "middle_defect_count": int(total_m),
            "large_defect_count": int(total_l),
            "over_defect_count": int(total_o),
            "glass": ",".join(glass_ids),
            "glass_size_detail": json.dumps(glass_detail_json_list, ensure_ascii=False),
            "comment": comment,
            "action": action,
            "Editor": editor,
            "modify_time": modify_time,
        })

    detail_df = pd.DataFrame(detail_rows, columns=schema.API_GLASS_DETAIL_COLS)
    detail_df = dedup_detail_df_by_pk(detail_df)

    summary_df_out = pd.DataFrame(summary_rows_out, columns=schema.API_SUMMARY_COLS)
    if not summary_df_out.empty:
        summary_df_out = summary_df_out.drop_duplicates(
            subset=["pi_hour", "line_id", "model", "glass_type"],
            keep="last"
        ).reset_index(drop=True)

    return summary_df_out, detail_df


# =========================================================
# Insert / replace API tables
# =========================================================
def insert_df(dbhandler: MySQLConnetFunc, table_name: str, df: pd.DataFrame, cols: List[str]) -> int:
    if df is None or df.empty:
        logger.info(f"[{dbhandler.db}.{table_name}] df empty, skip insert")
        return 0

    df2 = df.copy()
    for c in cols:
        if c not in df2.columns:
            df2[c] = None
    df2 = df2[cols].copy()

    rows = df2.to_dict(orient="records")
    cols_sql = ",".join([f"`{c}`" for c in cols])
    placeholders = ",".join([f":{c}" for c in cols])

    sql = text(f"""
      INSERT INTO `{dbhandler.db}`.`{table_name}` ({cols_sql})
      VALUES ({placeholders})
    """)

    chunk = DOMAIN.cfg.CHUNK_SIZE
    with dbhandler.engine.begin() as conn:
        for i in range(0, len(rows), chunk):
            conn.execute(sql, rows[i:i + chunk])

    logger.info(f"[{dbhandler.db}.{table_name}] insert 完成，共 {len(rows)} 筆")
    return int(len(rows))


def replace_api_month_by_range(
    dbhandler: MySQLConnetFunc,
    api_summary_tbn: str,
    api_detail_tbn: str,
    summary_df: pd.DataFrame,
    detail_df: pd.DataFrame,
    start: datetime,
    end: datetime
) -> Dict[str, int]:
    ensure_api_summary_table(dbhandler, api_summary_tbn)
    ensure_api_glass_detail_table(dbhandler, api_detail_tbn)

    pi_start, pi_end = DOMAIN.time.to_pi_hour_range(start, end)

    deleted_summary = delete_rows_in_range(dbhandler, api_summary_tbn, pi_start, pi_end, time_col="pi_hour")
    deleted_detail = delete_rows_in_range(dbhandler, api_detail_tbn, pi_start, pi_end, time_col="pi_hour")

    inserted_summary = insert_df(dbhandler, api_summary_tbn, summary_df, DOMAIN.schema.API_SUMMARY_COLS)
    inserted_detail = insert_df(dbhandler, api_detail_tbn, detail_df, DOMAIN.schema.API_GLASS_DETAIL_COLS)

    total_summary = count_total_rows(dbhandler, api_summary_tbn)
    total_detail = count_total_rows(dbhandler, api_detail_tbn)

    logger.info(
        f"[replace_api_month_by_range] [{api_summary_tbn}] / [{api_detail_tbn}] "
        f"time_range=({start} ~ {end}), pi_hour_range=({pi_start} ~ {pi_end}), "
        f"刪除 summary={deleted_summary}, detail={deleted_detail}, "
        f"新增 summary={inserted_summary}, detail={inserted_detail}, "
        f"總筆數 summary={total_summary}, detail={total_detail}"
    )

    return {
        "deleted_summary": deleted_summary,
        "deleted_detail": deleted_detail,
        "inserted_summary": inserted_summary,
        "inserted_detail": inserted_detail,
        "total_summary": total_summary,
        "total_detail": total_detail,
    }


# =========================================================
# Datamall helpers
# =========================================================
class InspectionDensityDatamallClient:
    def __init__(self, cfg: InspectionDensityConfig):
        self.cfg = cfg

    def datamall_get(self, url: str, session: requests.Session, max_retry: Optional[int] = None) -> Optional[Dict[str, Any]]:
        retry = max_retry or self.cfg.MAX_RETRY
        for attempt in range(1, retry + 1):
            try:
                logger.info(f"Datamall GET (try {attempt}/{retry}): {url}")
                resp = session.get(
                    url,
                    headers=self.cfg.REQUEST_HEADERS,
                    proxies=self.cfg.PROXY_DICT,
                    timeout=self.cfg.REQUEST_TIMEOUT
                )
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                logger.warning(f"Datamall GET 失敗 (attempt {attempt}): {e}")
                if attempt < retry:
                    time.sleep(self.cfg.RETRY_SLEEP_SEC)
                else:
                    return None
            except ValueError as e:
                logger.warning(f"Datamall JSON parse 失敗: {e}")
                return None
        return None

    def fetch_df(
        self,
        session: requests.Session,
        url: str,
        cols: List[str]
    ) -> pd.DataFrame:
        data = self.datamall_get(url, session=session)
        if data is None or self.cfg.DATAMALL_JSON_KEY not in data:
            logger.error(f"[fetch_df] datamall 取得失敗或缺 key={self.cfg.DATAMALL_JSON_KEY}")
            return pd.DataFrame(columns=cols)

        df = pd.DataFrame(data[self.cfg.DATAMALL_JSON_KEY])
        logger.info(f"[fetch_df] datamall 原始筆數={len(df)}, url={url}")

        if df.empty:
            return pd.DataFrame(columns=cols)

        for c in cols:
            if c not in df.columns:
                df[c] = None
        df = df[cols].copy()

        return df.reset_index(drop=True)


# =========================================================
# Landing append
# =========================================================
def append_df_direct(
    dbhandler: MySQLConnetFunc,
    table_name: str,
    df: pd.DataFrame,
    cols: List[str]
) -> int:
    if df is None or df.empty:
        logger.info(f"[{dbhandler.db}.{table_name}] 無資料可 append")
        return 0

    df2 = df.copy()
    for c in cols:
        if c not in df2.columns:
            df2[c] = None
    df2 = df2[cols].copy()

    ensure_table_like_df(dbhandler, table_name, df2)

    df2.to_sql(
        name=table_name,
        con=dbhandler.engine,
        schema=dbhandler.db,
        if_exists="append",
        index=False,
        chunksize=DOMAIN.cfg.CHUNK_SIZE,
        method="multi"
    )
    logger.info(f"[{dbhandler.db}.{table_name}] direct append 完成，共 {len(df2)} 筆")
    return int(len(df2))


# =========================================================
# Job state
# =========================================================
class InspectionDensityStateRepository:
    def __init__(self, dbhandler: MySQLConnetFunc, cfg: InspectionDensityConfig):
        self.db = dbhandler
        self.cfg = cfg
        ensure_job_state_table(self.db, self.cfg.JOB_STATE_TBN)

    def upsert_state(
        self,
        *,
        last_run_start_time: datetime,
        last_run_end_time: datetime,
        last_success_time: Optional[datetime],
        last_window_start: Optional[datetime],
        last_window_end: Optional[datetime],
        last_summary_rows: int,
        last_raw_rows: int,
        last_summary_new_rows: int,
        last_raw_new_rows: int,
        last_summary_max_scan_endtime: Optional[datetime],
        last_raw_max_scan_endtime: Optional[datetime],
        last_max_pi_hour: Optional[datetime],
        status: str,
        message: str,
    ) -> None:
        sql = text(f"""
        INSERT INTO `{self.db.db}`.`{self.cfg.JOB_STATE_TBN}` (
            job_name,
            last_run_start_time,
            last_run_end_time,
            last_success_time,
            last_window_start,
            last_window_end,
            last_summary_rows,
            last_raw_rows,
            last_summary_new_rows,
            last_raw_new_rows,
            last_summary_max_scan_endtime,
            last_raw_max_scan_endtime,
            last_max_pi_hour,
            status,
            message,
            modify_time
        ) VALUES (
            :job_name,
            :last_run_start_time,
            :last_run_end_time,
            :last_success_time,
            :last_window_start,
            :last_window_end,
            :last_summary_rows,
            :last_raw_rows,
            :last_summary_new_rows,
            :last_raw_new_rows,
            :last_summary_max_scan_endtime,
            :last_raw_max_scan_endtime,
            :last_max_pi_hour,
            :status,
            :message,
            :modify_time
        )
        ON DUPLICATE KEY UPDATE
            last_run_start_time = VALUES(last_run_start_time),
            last_run_end_time = VALUES(last_run_end_time),
            last_success_time = VALUES(last_success_time),
            last_window_start = VALUES(last_window_start),
            last_window_end = VALUES(last_window_end),
            last_summary_rows = VALUES(last_summary_rows),
            last_raw_rows = VALUES(last_raw_rows),
            last_summary_new_rows = VALUES(last_summary_new_rows),
            last_raw_new_rows = VALUES(last_raw_new_rows),
            last_summary_max_scan_endtime = VALUES(last_summary_max_scan_endtime),
            last_raw_max_scan_endtime = VALUES(last_raw_max_scan_endtime),
            last_max_pi_hour = VALUES(last_max_pi_hour),
            status = VALUES(status),
            message = VALUES(message),
            modify_time = VALUES(modify_time)
        """)
        params = {
            "job_name": self.cfg.JOB_NAME,
            "last_run_start_time": last_run_start_time,
            "last_run_end_time": last_run_end_time,
            "last_success_time": last_success_time,
            "last_window_start": last_window_start,
            "last_window_end": last_window_end,
            "last_summary_rows": int(last_summary_rows),
            "last_raw_rows": int(last_raw_rows),
            "last_summary_new_rows": int(last_summary_new_rows),
            "last_raw_new_rows": int(last_raw_new_rows),
            "last_summary_max_scan_endtime": last_summary_max_scan_endtime,
            "last_raw_max_scan_endtime": last_raw_max_scan_endtime,
            "last_max_pi_hour": last_max_pi_hour,
            "status": status,
            "message": message,
            "modify_time": datetime.now(),
        }
        with self.db.engine.begin() as conn:
            conn.execute(sql, params)


# =========================================================
# Landing service
# =========================================================
class InspectionDensityLandingService:
    def __init__(self, dbhandler: MySQLConnetFunc):
        self.db = dbhandler
        self.cfg = DOMAIN.cfg
        self.schema = DOMAIN.schema
        self.tables = DOMAIN.tables
        self.datamall = InspectionDensityDatamallClient(self.cfg)

    def fetch_datamall_snapshot(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        with requests.Session() as session:
            summary_df = self.datamall.fetch_df(
                session=session,
                url=self.cfg.SUMMARY_URL,
                cols=self.schema.SUMMARY_COLS
            )
            raw_df = self.datamall.fetch_df(
                session=session,
                url=self.cfg.RAW_URL,
                cols=self.schema.RAW_COLS
            )
        return summary_df, raw_df

    def append_snapshot_to_landing(
        self,
        summary_df: pd.DataFrame,
        raw_df: pd.DataFrame
    ) -> Dict[str, Any]:
        summary_months = split_df_by_month(summary_df, "SCAN_ENDTIME")
        raw_months = split_df_by_month(raw_df, "SCAN_ENDTIME")

        impacted_months = sorted(set(summary_months.keys()) | set(raw_months.keys()))
        stats = {
            "months": impacted_months,
            "summary_rows": len(summary_df),
            "raw_rows": len(raw_df),
            "summary_new_rows": 0,
            "raw_new_rows": 0,
            "summary_max_scan_endtime": get_df_max_dt(summary_df, "SCAN_ENDTIME"),
            "raw_max_scan_endtime": get_df_max_dt(raw_df, "SCAN_ENDTIME"),
            "summary": {},
            "raw": {},
        }

        for ym, df_m in summary_months.items():
            tbn = self.tables.summary_table(ym)
            n = append_df_direct(self.db, tbn, df_m, self.schema.SUMMARY_COLS)
            stats["summary"][ym] = {
                "append_rows": n,
                "total_rows": count_total_rows(self.db, tbn),
                "max_time": get_df_max_dt(df_m, "SCAN_ENDTIME"),
            }
            stats["summary_new_rows"] += n

        for ym, df_m in raw_months.items():
            tbn = self.tables.raw_table(ym)
            n = append_df_direct(self.db, tbn, df_m, self.schema.RAW_COLS)
            stats["raw"][ym] = {
                "append_rows": n,
                "total_rows": count_total_rows(self.db, tbn),
                "max_time": get_df_max_dt(df_m, "SCAN_ENDTIME"),
            }
            stats["raw_new_rows"] += n

        for ym, st in stats["summary"].items():
            logger.info(
                f"[landing-summary] table={self.tables.summary_table(ym)}, "
                f"append={st['append_rows']}, total={st['total_rows']}, max={st['max_time']}"
            )
        for ym, st in stats["raw"].items():
            logger.info(
                f"[landing-raw] table={self.tables.raw_table(ym)}, "
                f"append={st['append_rows']}, total={st['total_rows']}, max={st['max_time']}"
            )

        return stats

    def run_pull_landing(self) -> Dict[str, Any]:
        summary_df, raw_df = self.fetch_datamall_snapshot()
        return self.append_snapshot_to_landing(summary_df, raw_df)


# =========================================================
# API rebuild service
# =========================================================
class InspectionDensityRebuildService:
    def __init__(self, dbhandler: MySQLConnetFunc):
        self.db = dbhandler
        self.cfg = DOMAIN.cfg
        self.schema = DOMAIN.schema
        self.tables = DOMAIN.tables

    def load_landing_frames_for_month(
        self,
        yyyymm: str,
        start: datetime,
        end: datetime
    ) -> Tuple[pd.DataFrame, pd.DataFrame, datetime, datetime, datetime, datetime]:
        summary_tbn = self.tables.summary_table(yyyymm)
        raw_tbn = self.tables.raw_table(yyyymm)

        pi_start, pi_end, scan_start, scan_end = DOMAIN.time.to_scan_time_cover_range(start, end)

        summary_df = get_table_range_safe(self.db, summary_tbn, scan_start, scan_end, time_col="SCAN_ENDTIME")
        raw_df = get_table_range_safe(self.db, raw_tbn, scan_start, scan_end, time_col="SCAN_ENDTIME")

        return summary_df, raw_df, pi_start, pi_end, scan_start, scan_end

    def preprocess_landing_frames(
        self,
        summary_df: pd.DataFrame,
        raw_df: pd.DataFrame,
        scan_start: datetime,
        scan_end: datetime
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        if summary_df is None:
            summary_df = pd.DataFrame(columns=self.schema.SUMMARY_COLS)
        if raw_df is None:
            raw_df = pd.DataFrame(columns=self.schema.RAW_COLS)

        summary_df = filter_df_by_time(summary_df, scan_start, scan_end, "SCAN_ENDTIME")
        raw_df = filter_df_by_time(raw_df, scan_start, scan_end, "SCAN_ENDTIME")

        summary_before = len(summary_df)
        raw_before = len(raw_df)

        summary_df = dedup_by_keys(summary_df, self.schema.SUMMARY_DEDUP_KEYS, keep="last")
        raw_df = dedup_by_keys(raw_df, self.schema.RAW_DEDUP_KEYS, keep="last")

        logger.info(
            f"[preprocess] summary dedup: {summary_before} -> {len(summary_df)}, "
            f"raw dedup: {raw_before} -> {len(raw_df)}"
        )

        summary_df = DOMAIN.time.add_shift_columns(summary_df, "SCAN_ENDTIME")
        raw_df = split_recipe_to_model_type(raw_df, "RECIPE_NAME")
        raw_df = DOMAIN.time.add_shift_columns(raw_df, "SCAN_ENDTIME")

        summary_df = filter_df_by_time(summary_df, scan_start, scan_end, "SCAN_ENDTIME")
        raw_df = filter_df_by_time(raw_df, scan_start, scan_end, "SCAN_ENDTIME")

        return summary_df, raw_df

    def rebuild_range(self, yyyymm: str, start: datetime, end: datetime) -> Dict[str, Any]:
        api_summary_tbn = self.tables.api_summary_table(yyyymm)
        api_detail_tbn = self.tables.api_glass_detail_table(yyyymm)

        summary_df, raw_df, pi_start, pi_end, scan_start, scan_end = self.load_landing_frames_for_month(
            yyyymm, start, end
        )

        logger.info(
            f"[rebuild_range] {yyyymm} "
            f"raw_window=({start} ~ {end}), "
            f"pi_hour_range=({pi_start} ~ {pi_end}), "
            f"scan_cover_range=({scan_start} ~ {scan_end}), "
            f"landing summary/raw rows={len(summary_df)}/{len(raw_df)}"
        )

        if summary_df.empty and raw_df.empty:
            return {
                "deleted_summary": 0,
                "deleted_detail": 0,
                "inserted_summary": 0,
                "inserted_detail": 0,
                "total_summary": count_total_rows(self.db, api_summary_tbn),
                "total_detail": count_total_rows(self.db, api_detail_tbn),
                "max_pi_hour": None,
                "pi_start": pi_start,
                "pi_end": pi_end,
                "scan_start": scan_start,
                "scan_end": scan_end,
            }

        summary_df, raw_df = self.preprocess_landing_frames(summary_df, raw_df, scan_start, scan_end)

        if summary_df.empty:
            logger.warning(
                f"[rebuild_range] {yyyymm} 經 dedup + filter 後 summary 為空, "
                f"scan_cover_range=({scan_start} ~ {scan_end})"
            )
            return {
                "deleted_summary": 0,
                "deleted_detail": 0,
                "inserted_summary": 0,
                "inserted_detail": 0,
                "total_summary": count_total_rows(self.db, api_summary_tbn),
                "total_detail": count_total_rows(self.db, api_detail_tbn),
                "max_pi_hour": None,
                "pi_start": pi_start,
                "pi_end": pi_end,
                "scan_start": scan_start,
                "scan_end": scan_end,
            }

        manual_map = load_manual_field_map(
            target_db=self.db.db,
            source_db=self.db.db,
            api_tbn=api_summary_tbn
        )

        summary_api_df, detail_api_df = build_detail_and_summary_df(
            dbhandler=self.db,
            summary_df=summary_df,
            manual_map=manual_map
        )
        logger.info(
            f"[rebuild_range-check] {yyyymm} "
            f"summary_api_rows={len(summary_api_df)}, detail_api_rows={len(detail_api_df)}, "
            f"summary_defect_sum={summary_api_df['maingroup_defect_count'].sum() if not summary_api_df.empty else 0}, "
            f"raw_size_sum="
            f"{summary_api_df['small_defect_count'].sum() if not summary_api_df.empty else 0}/"
            f"{summary_api_df['middle_defect_count'].sum() if not summary_api_df.empty else 0}/"
            f"{summary_api_df['large_defect_count'].sum() if not summary_api_df.empty else 0}/"
            f"{summary_api_df['over_defect_count'].sum() if not summary_api_df.empty else 0}"
        )

        stats = replace_api_month_by_range(
            dbhandler=self.db,
            api_summary_tbn=api_summary_tbn,
            api_detail_tbn=api_detail_tbn,
            summary_df=summary_api_df,
            detail_df=detail_api_df,
            start=scan_start,
            end=scan_end
        )

        stats["max_pi_hour"] = get_df_max_dt(summary_api_df, "pi_hour")
        stats["pi_start"] = pi_start
        stats["pi_end"] = pi_end
        stats["scan_start"] = scan_start
        stats["scan_end"] = scan_end

        logger.info(
            f"[rebuild_range] {yyyymm} 完成，"
            f"pi_hour_range=({pi_start} ~ {pi_end}), "
            f"scan_cover_range=({scan_start} ~ {scan_end}), "
            f"刪除 summary/detail={stats['deleted_summary']}/{stats['deleted_detail']}，"
            f"新增 summary/detail={stats['inserted_summary']}/{stats['inserted_detail']}，"
            f"總筆數 summary/detail={stats['total_summary']}/{stats['total_detail']}，"
            f"最新 pi_hour={stats['max_pi_hour']}"
        )
        return stats


# =========================================================
# Main Job Service
# =========================================================
class InspectionDensityDatamallJobService:
    def __init__(self):
        self.cfg = DOMAIN.cfg
        self.schema = DOMAIN.schema
        self.tables = DOMAIN.tables
        self.db = MySQLConnetFunc(self.cfg.TARGET_DB)
        self.state_repo = InspectionDensityStateRepository(self.db, self.cfg)
        self.landing = InspectionDensityLandingService(self.db)
        self.rebuilder = InspectionDensityRebuildService(self.db)

    def rebuild_api_for_months(
        self,
        months: List[str],
        start: datetime,
        end: datetime
    ) -> Dict[str, Any]:
        api_stats = {
            "by_month": {},
            "deleted_summary": 0,
            "deleted_detail": 0,
            "inserted_summary": 0,
            "inserted_detail": 0,
            "total_summary": 0,
            "total_detail": 0,
            "max_pi_hour": None,
        }

        max_pi = None

        for ym in months:
            month_start = datetime(int(ym[:4]), int(ym[4:6]), 1, 0, 0, 0)
            if int(ym[4:6]) == 12:
                next_month = datetime(int(ym[:4]) + 1, 1, 1, 0, 0, 0)
            else:
                next_month = datetime(int(ym[:4]), int(ym[4:6]) + 1, 1, 0, 0, 0)
            month_end = next_month - timedelta(seconds=1)

            real_start = max(start, month_start)
            real_end = min(end, month_end)
            if real_end < real_start:
                continue

            stat = self.rebuilder.rebuild_range(ym, real_start, real_end)
            api_stats["by_month"][ym] = stat
            api_stats["deleted_summary"] += int(stat["deleted_summary"])
            api_stats["deleted_detail"] += int(stat["deleted_detail"])
            api_stats["inserted_summary"] += int(stat["inserted_summary"])
            api_stats["inserted_detail"] += int(stat["inserted_detail"])
            api_stats["total_summary"] += int(stat["total_summary"])
            api_stats["total_detail"] += int(stat["total_detail"])

            if stat.get("max_pi_hour") is not None:
                if max_pi is None or stat["max_pi_hour"] > max_pi:
                    max_pi = stat["max_pi_hour"]

        api_stats["max_pi_hour"] = max_pi

        for ym, stat in api_stats["by_month"].items():
            logger.info(
                f"[api] ym={ym}, "
                f"pi_hour_range=({stat.get('pi_start')} ~ {stat.get('pi_end')}), "
                f"scan_cover_range=({stat.get('scan_start')} ~ {stat.get('scan_end')}), "
                f"刪除 summary/detail={stat['deleted_summary']}/{stat['deleted_detail']}, "
                f"新增 summary/detail={stat['inserted_summary']}/{stat['inserted_detail']}, "
                f"總筆數 summary/detail={stat['total_summary']}/{stat['total_detail']}, "
                f"最新 pi_hour={stat['max_pi_hour']}"
            )

        return api_stats

    def pull_landing_only(self) -> Dict[str, Any]:
        job_start = datetime.now()
        logger.info("============================================================")
        logger.info(f"[pull-landing-start] log_file={os.path.abspath(LOG_FILE)}")

        try:
            landing_stats = self.landing.run_pull_landing()

            msg = (
                f"landing months={landing_stats['months']}, "
                f"summary抓取={landing_stats['summary_rows']}, raw抓取={landing_stats['raw_rows']}, "
                f"summary append={landing_stats['summary_new_rows']}, raw append={landing_stats['raw_new_rows']}, "
                f"summary_max={landing_stats['summary_max_scan_endtime']}, raw_max={landing_stats['raw_max_scan_endtime']}"
            )
            logger.info(f"[pull-landing-end] {msg}")

            self.state_repo.upsert_state(
                last_run_start_time=job_start,
                last_run_end_time=datetime.now(),
                last_success_time=datetime.now(),
                last_window_start=None,
                last_window_end=None,
                last_summary_rows=landing_stats["summary_rows"],
                last_raw_rows=landing_stats["raw_rows"],
                last_summary_new_rows=landing_stats["summary_new_rows"],
                last_raw_new_rows=landing_stats["raw_new_rows"],
                last_summary_max_scan_endtime=landing_stats["summary_max_scan_endtime"],
                last_raw_max_scan_endtime=landing_stats["raw_max_scan_endtime"],
                last_max_pi_hour=None,
                status="SUCCESS",
                message=msg,
            )
            return landing_stats

        except Exception as e:
            logger.exception("[pull-landing-fail] 執行失敗")
            self.state_repo.upsert_state(
                last_run_start_time=job_start,
                last_run_end_time=datetime.now(),
                last_success_time=None,
                last_window_start=None,
                last_window_end=None,
                last_summary_rows=0,
                last_raw_rows=0,
                last_summary_new_rows=0,
                last_raw_new_rows=0,
                last_summary_max_scan_endtime=None,
                last_raw_max_scan_endtime=None,
                last_max_pi_hour=None,
                status="FAILED",
                message=str(e),
            )
            raise

    def rebuild_only(self, start: datetime, end: datetime) -> Dict[str, Any]:
        job_start = datetime.now()
        logger.info("============================================================")
        logger.info(f"[rebuild-start] time_window=({start} ~ {end}), log_file={os.path.abspath(LOG_FILE)}")

        try:
            months = month_span_by_pi_hour(start, end)
            api_stats = self.rebuild_api_for_months(months, start, end)

            msg = (
                f"rebuild months={months}, "
                f"API刪除 summary/detail={api_stats['deleted_summary']}/{api_stats['deleted_detail']}, "
                f"API新增 summary/detail={api_stats['inserted_summary']}/{api_stats['inserted_detail']}, "
                f"最新pi_hour={api_stats['max_pi_hour']}"
            )
            logger.info(f"[rebuild-end] {msg}")

            self.state_repo.upsert_state(
                last_run_start_time=job_start,
                last_run_end_time=datetime.now(),
                last_success_time=datetime.now(),
                last_window_start=start,
                last_window_end=end,
                last_summary_rows=0,
                last_raw_rows=0,
                last_summary_new_rows=0,
                last_raw_new_rows=0,
                last_summary_max_scan_endtime=None,
                last_raw_max_scan_endtime=None,
                last_max_pi_hour=api_stats["max_pi_hour"],
                status="SUCCESS",
                message=msg,
            )
            return api_stats

        except Exception as e:
            logger.exception("[rebuild-fail] 執行失敗")
            self.state_repo.upsert_state(
                last_run_start_time=job_start,
                last_run_end_time=datetime.now(),
                last_success_time=None,
                last_window_start=start,
                last_window_end=end,
                last_summary_rows=0,
                last_raw_rows=0,
                last_summary_new_rows=0,
                last_raw_new_rows=0,
                last_summary_max_scan_endtime=None,
                last_raw_max_scan_endtime=None,
                last_max_pi_hour=None,
                status="FAILED",
                message=str(e),
            )
            raise

    def run_job(self, hours: Optional[int] = None) -> None:
        hours = int(hours or self.cfg.DEFAULT_REBUILD_HOURS)

        logger.info("============================================================")
        logger.info(f"[job] 先 pull landing，再 rebuild 最近 {hours} 小時")

        self.pull_landing_only()

        end = datetime.now()
        start = end - timedelta(hours=hours)
        self.rebuild_only(start, end)

    def run_rebuild_hours(self, hours: int) -> None:
        end = datetime.now()
        start = end - timedelta(hours=int(hours))
        self.rebuild_only(start, end)

    def run_rebuild_days(self, days: int) -> None:
        end = datetime.now()
        start = end - timedelta(days=int(days))
        self.rebuild_only(start, end)

    def run_rebuild_range(self, start: datetime, end: datetime) -> None:
        if end < start:
            start, end = end, start
        self.rebuild_only(start, end)


# =========================================================
# CLI
# =========================================================

def pi_hour_to_scan_end_range_for_rebuild(pi_hour_dt: datetime) -> Tuple[datetime, datetime]:
    """
    與 defect_map.py 完全一致：
    pi_hour = floor(SCAN_ENDTIME - 30min, hour)

    所以某個 pi_hour bucket 對應的實際 SCAN_ENDTIME 範圍為：
      [pi_hour + 30min, pi_hour + 90min)
    """
    start_dt = pi_hour_dt + timedelta(minutes=DOMAIN.cfg.SHIFT_BUCKET_OFFSET_MINUTES)
    end_dt = start_dt + timedelta(hours=1)
    return start_dt, end_dt

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    p_job = sub.add_parser("job")
    p_job.add_argument("--hours", type=int, default=DOMAIN.cfg.DEFAULT_REBUILD_HOURS)

    sub.add_parser("pull-landing")

    p_hours = sub.add_parser("rebuild-hours")
    p_hours.add_argument("--hours", type=int, required=True)

    p_days = sub.add_parser("rebuild-days")
    p_days.add_argument("--days", type=int, required=True)

    p_range = sub.add_parser("rebuild-range")
    p_range.add_argument("--start", required=True)
    p_range.add_argument("--end", required=True)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

    svc = InspectionDensityDatamallJobService()

    if args.cmd == "job":
        svc.run_job(hours=args.hours)
        return

    if args.cmd == "pull-landing":
        svc.pull_landing_only()
        return

    if args.cmd == "rebuild-hours":
        svc.run_rebuild_hours(int(args.hours))
        return

    if args.cmd == "rebuild-days":
        svc.run_rebuild_days(int(args.days))
        return

    if args.cmd == "rebuild-range":
        start = parse_dt(args.start)
        end = parse_dt(args.end)
        svc.run_rebuild_range(start, end)
        return


if __name__ == "__main__":
    main()


# =========================================================
# Examples
# =========================================================
# 1) Datamall 原始快照直接落地到 landing tables
# python inspection_density_datamall_job2.py pull-landing
#
# 2) 先拉 Datamall，再重建最近 3 小時 API
# python inspection_density_datamall_job2.py job
#
# 3) 先拉 Datamall，再重建最近 N 小時 API
# python inspection_density_datamall_job2.py job --hours 6
#
# 4) 只從 landing tables 重建最近 N 小時 API
# python inspection_density_datamall_job2.py rebuild-hours --hours 24
#
# 5) 只從 landing tables 重建最近 N 天 API
# python inspection_density_datamall_job2.py rebuild-days --days 9
#
# 6) 只從 landing tables 重建指定區間 API
# python inspection_density_datamall_job3.py rebuild-range --start "2026-06-01 07:30:00" --end "2026-06-04 14:00:00"