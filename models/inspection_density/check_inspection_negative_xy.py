#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_inspection_negative_xy.py

用途：
    檢查 piaoi_inspection_density.inspection_raw_table_yyyymm
    經 inspection 座標轉換後，x_out / y_out 是否有負數。

檢查邏輯沿用前端/既有 group_defects_by_glass：

    原始：
        COORD_X
        COORD_Y

    預設：
        x = COORD_X
        y = COORD_Y

    CAPIC207 / CAPIC507 / CAPIC407:
        x = 1850 + COORD_Y
        y = -COORD_X

    CAPIC107 / CAPIC307 / CAPIC607 / CAPIC707:
        x = 1850 - COORD_Y
        y = COORD_X

    輸出：
        x_out = round(x * 1000)
        y_out = round(y * 1000)

    判斷：
        x_out < 0 OR y_out < 0

輸出：
    output_csv/inspection_negative_xy_yyyymm_YYYYMMDD_HHMMSS.csv
    logs/check_inspection_negative_xy.txt

使用：

    # 檢查單一月份
    python check_inspection_negative_xy.py --yyyymm 202606

    # 檢查多個月份
    python check_inspection_negative_xy.py --yyyymm 202511,202512

    # 檢查特定時間區間
    python check_inspection_negative_xy.py --start-time "2026-01-01 00:00:00" --end-time "2026-03-31 23:59:59"

    # 指定輸出資料夾
    python check_inspection_negative_xy.py --yyyymm 202606 --output-dir output_csv
"""

from __future__ import annotations

import os
import sys
import argparse
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sqlalchemy import inspect, text


# =============================================================================
# Import project MySQLConnet
# =============================================================================

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# 假設本檔可能放在：
# D:\A0_Project\PI_SYSTEM\models\piaoi\inspection
#
# 需要 import：
# D:\A0_Project\PI_SYSTEM\models\sql_db_connect.py
#
# 所以 PROJECT_ROOT = D:\A0_Project\PI_SYSTEM
PROJECT_ROOT = os.path.abspath(
    os.path.join(CURRENT_DIR, "..", )
)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from models.sql_db_connect import MySQLConnet
except Exception:
    # 如果你把檔案放在 models 同層或其他位置，fallback 給舊寫法
    from sql_db_connect import MySQLConnet


# =============================================================================
# Config
# =============================================================================

INSPECTION_DB_NAME = "piaoi_inspection_density"
INSPECTION_RAW_BASE = "inspection_raw_table_yyyymm"

PANEL_WIDTH_MM = 1850.0

FLIP1_TOOLS = {"CAPIC207", "CAPIC507", "CAPIC407"}
FLIP2_TOOLS = {"CAPIC107", "CAPIC307", "CAPIC607", "CAPIC707"}

NEEDED_COLS = [
    "COORD_X",
    "COORD_Y",
    "DEFECT",
    "DEFECT_AREA",
    "DEFECT_ID",
    "DEFECT_SIZE_TYPE",
    "FAB",
    "FRONT_REVERSE",
    "IMG_URL",
    "RECIPE_NAME",
    "RUN_ID",
    "SCAN_ENDTIME",
    "SCAN_STARTTIME",
    "SHEET_ID",
    "SP",
    "STAGE",
    "TOOL_ID",
    "TOTAL_DEFECT_COUNT",
]


# =============================================================================
# Logging
# =============================================================================

def setup_logging(
    log_dir: str = "logs",
    log_name: str = "check_inspection_negative_xy.txt",
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
# Date helpers
# =============================================================================

def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None

    s = str(value).strip()

    if len(s) == 10:
        return datetime.strptime(s, "%Y-%m-%d")

    return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")


def normalize_yyyymm_list(value: Optional[str]) -> List[str]:
    if not value:
        return []

    out: List[str] = []

    for part in str(value).split(","):
        ym = part.strip().replace("-", "")
        if not ym:
            continue

        if len(ym) != 6 or not ym.isdigit():
            raise ValueError(f"Invalid yyyymm: {part}")

        out.append(ym)

    return sorted(set(out))


def yyyymm_range(start_dt: datetime, end_dt_exclusive: datetime) -> List[str]:
    cur = datetime(start_dt.year, start_dt.month, 1)
    end_month = datetime(end_dt_exclusive.year, end_dt_exclusive.month, 1)

    if (
        end_dt_exclusive.day == 1
        and end_dt_exclusive.hour == 0
        and end_dt_exclusive.minute == 0
        and end_dt_exclusive.second == 0
        and end_dt_exclusive.microsecond == 0
    ):
        if end_month.month == 1:
            end_month = datetime(end_month.year - 1, 12, 1)
        else:
            end_month = datetime(end_month.year, end_month.month - 1, 1)

    out: List[str] = []

    while cur <= end_month:
        out.append(cur.strftime("%Y%m"))

        if cur.month == 12:
            cur = datetime(cur.year + 1, 1, 1)
        else:
            cur = datetime(cur.year, cur.month + 1, 1)

    return out


def month_start_end(yyyymm: str) -> Tuple[datetime, datetime]:
    start_dt = datetime.strptime(yyyymm + "01", "%Y%m%d")

    if start_dt.month == 12:
        end_dt = datetime(start_dt.year + 1, 1, 1)
    else:
        end_dt = datetime(start_dt.year, start_dt.month + 1, 1)

    return start_dt, end_dt


# =============================================================================
# DB helpers
# =============================================================================

def table_name_by_yyyymm(base: str, yyyymm: str) -> str:
    return base.replace("yyyymm", yyyymm).lower()


def table_exists(engine, table_name: str) -> bool:
    insp = inspect(engine)
    tables = {t.lower() for t in insp.get_table_names()}
    return table_name.lower() in tables


def get_table_columns(engine, table_name: str) -> List[str]:
    insp = inspect(engine)
    return [c["name"] for c in insp.get_columns(table_name)]


def load_inspection_raw(
    engine,
    table_name: str,
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
) -> pd.DataFrame:
    cols = get_table_columns(engine, table_name)
    colset = set(cols)

    select_cols = [c for c in NEEDED_COLS if c in colset]

    # 最低必要欄位
    for required in ["SHEET_ID", "TOOL_ID", "COORD_X", "COORD_Y", "SCAN_ENDTIME"]:
        if required not in colset:
            logging.warning(
                "[load_inspection_raw] table=%s missing required col=%s",
                table_name,
                required,
            )

    if not select_cols:
        return pd.DataFrame()

    select_sql = ", ".join([f"`{c}`" for c in select_cols])

    where_parts = ["1=1"]
    params: Dict[str, Any] = {}

    if start_dt is not None:
        where_parts.append("`SCAN_ENDTIME` >= :start_dt")
        params["start_dt"] = start_dt

    if end_dt is not None:
        where_parts.append("`SCAN_ENDTIME` < :end_dt")
        params["end_dt"] = end_dt

    sql = text(f"""
    SELECT {select_sql}
    FROM `{table_name}`
    WHERE {" AND ".join(where_parts)}
    """)

    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params=params)

    return df


# =============================================================================
# Transform / check
# =============================================================================

def clean_text(value: Any) -> str:
    if value is None:
        return ""

    s = str(value).strip()

    if s.lower() in {"nan", "none", "null", "<na>", "nat"}:
        return ""

    return s


def apply_inspection_xy_transform(df: pd.DataFrame) -> pd.DataFrame:
    """
    完整保留原始欄位，再新增：
        coord_x_num
        coord_y_num
        transform_rule
        x_mm
        y_mm
        x_out
        y_out
        has_negative_xy
    """
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    for col in NEEDED_COLS:
        if col not in out.columns:
            out[col] = np.nan if col in {"COORD_X", "COORD_Y"} else ""

    out["SHEET_ID"] = out["SHEET_ID"].fillna("").astype(str).str.strip()
    out["TOOL_ID"] = out["TOOL_ID"].fillna("").astype(str).str.strip().str.upper()
    out["SCAN_ENDTIME"] = pd.to_datetime(out["SCAN_ENDTIME"], errors="coerce")

    out["coord_x_num"] = pd.to_numeric(out["COORD_X"], errors="coerce")
    out["coord_y_num"] = pd.to_numeric(out["COORD_Y"], errors="coerce")

    out["size"] = (
        out["DEFECT_SIZE_TYPE"]
        .astype(str)
        .str.strip()
        .str.upper()
        .where(out["DEFECT_SIZE_TYPE"].notna(), None)
    )

    # =====================================================
    # 座標轉換：沿用你提供的 inspection 規則
    # =====================================================
    out["x_mm"] = out["coord_x_num"]
    out["y_mm"] = out["coord_y_num"]
    out["transform_rule"] = "DEFAULT_X_COORD_X_Y_COORD_Y"

    mask_flip1 = out["TOOL_ID"].isin(FLIP1_TOOLS)
    mask_flip2 = out["TOOL_ID"].isin(FLIP2_TOOLS)

    # CAPIC207 / 507 / 407
    out.loc[mask_flip1, "x_mm"] = PANEL_WIDTH_MM + out.loc[mask_flip1, "coord_y_num"]
    out.loc[mask_flip1, "y_mm"] = -out.loc[mask_flip1, "coord_x_num"]
    out.loc[mask_flip1, "transform_rule"] = "FLIP1_X_1850_PLUS_COORD_Y_Y_NEG_COORD_X"

    # CAPIC107 / 307 / 607 / 707
    out.loc[mask_flip2, "x_mm"] = PANEL_WIDTH_MM - out.loc[mask_flip2, "coord_y_num"]
    out.loc[mask_flip2, "y_mm"] = out.loc[mask_flip2, "coord_x_num"]
    out.loc[mask_flip2, "transform_rule"] = "FLIP2_X_1850_MINUS_COORD_Y_Y_COORD_X"

    out["x_out"] = (out["x_mm"] * 1000).round().astype("Int64")
    out["y_out"] = (out["y_mm"] * 1000).round().astype("Int64")

    out["has_invalid_xy"] = out["x_out"].isna() | out["y_out"].isna()
    out["has_negative_xy"] = (
        out["x_out"].notna()
        & out["y_out"].notna()
        & (
            (out["x_out"] < 0)
            | (out["y_out"] < 0)
        )
    )

    return out


def build_negative_output(df: pd.DataFrame, source_table: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    neg = df[df["has_negative_xy"].eq(True)].copy()

    if neg.empty:
        return pd.DataFrame()

    neg["source_table"] = source_table

    output_cols = [
        "source_table",
        "TOOL_ID",
        "SHEET_ID",
        "SCAN_ENDTIME",

        "COORD_X",
        "COORD_Y",
        "coord_x_num",
        "coord_y_num",

        "transform_rule",
        "x_mm",
        "y_mm",
        "x_out",
        "y_out",

        "DEFECT_ID",
        "DEFECT_SIZE_TYPE",
        "size",
        "DEFECT",
        "DEFECT_AREA",
        "FAB",
        "FRONT_REVERSE",
        "IMG_URL",
        "RECIPE_NAME",
        "RUN_ID",
        "SCAN_STARTTIME",
        "SP",
        "STAGE",
        "TOTAL_DEFECT_COUNT",
    ]

    for col in output_cols:
        if col not in neg.columns:
            neg[col] = None

    neg = neg[output_cols].copy()

    neg = neg.sort_values(
        ["SCAN_ENDTIME", "TOOL_ID", "SHEET_ID", "x_out", "y_out"],
        na_position="last",
    ).reset_index(drop=True)

    return neg


def build_sheet_summary(negative_df: pd.DataFrame) -> pd.DataFrame:
    if negative_df is None or negative_df.empty:
        return pd.DataFrame()

    d = negative_df.copy()

    summary = (
        d.groupby(["source_table", "TOOL_ID", "SHEET_ID", "SCAN_ENDTIME"], dropna=False)
        .agg(
            negative_defect_count=("SHEET_ID", "size"),
            min_x_out=("x_out", "min"),
            min_y_out=("y_out", "min"),
            max_x_out=("x_out", "max"),
            max_y_out=("y_out", "max"),
        )
        .reset_index()
        .sort_values(["SCAN_ENDTIME", "TOOL_ID", "SHEET_ID"])
    )

    return summary


# =============================================================================
# Main
# =============================================================================

def run_check(
    *,
    yyyymm_list: List[str],
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
    output_dir: str,
) -> Tuple[str, str, int]:
    os.makedirs(output_dir, exist_ok=True)

    db = MySQLConnet(INSPECTION_DB_NAME)
    engine = db.engine

    if start_dt and end_dt:
        months = yyyymm_range(start_dt, end_dt)
    else:
        months = yyyymm_list

    if not months:
        raise ValueError("請指定 --yyyymm 或 --start-time / --end-time")

    logging.info("[run_check] db=%s months=%s", INSPECTION_DB_NAME, months)
    logging.info("[run_check] start_dt=%s end_dt=%s", start_dt, end_dt)

    all_negative_chunks: List[pd.DataFrame] = []
    all_summary_chunks: List[pd.DataFrame] = []

    total_rows = 0
    total_valid_rows = 0
    total_invalid_xy_rows = 0
    total_negative_rows = 0

    for ym in months:
        table_name = table_name_by_yyyymm(INSPECTION_RAW_BASE, ym)

        if not table_exists(engine, table_name):
            logging.warning("[run_check] table not exists: %s", table_name)
            continue

        month_start, month_end = month_start_end(ym)

        real_start = start_dt
        real_end = end_dt

        if start_dt is None and end_dt is None:
            real_start = month_start
            real_end = month_end

        logging.info(
            "[run_check] loading table=%s start=%s end=%s",
            table_name,
            real_start,
            real_end,
        )

        raw_df = load_inspection_raw(
            engine=engine,
            table_name=table_name,
            start_dt=real_start,
            end_dt=real_end,
        )

        logging.info("[run_check] table=%s raw rows=%s", table_name, len(raw_df))

        if raw_df.empty:
            continue

        transformed = apply_inspection_xy_transform(raw_df)

        row_cnt = len(transformed)
        invalid_cnt = int(transformed["has_invalid_xy"].sum())
        negative_cnt = int(transformed["has_negative_xy"].sum())
        valid_cnt = row_cnt - invalid_cnt

        total_rows += row_cnt
        total_valid_rows += valid_cnt
        total_invalid_xy_rows += invalid_cnt
        total_negative_rows += negative_cnt

        logging.info(
            "[run_check] table=%s rows=%s valid_xy=%s invalid_xy=%s negative_xy=%s",
            table_name,
            row_cnt,
            valid_cnt,
            invalid_cnt,
            negative_cnt,
        )

        if negative_cnt > 0:
            neg_df = build_negative_output(transformed, source_table=table_name)
            summary_df = build_sheet_summary(neg_df)

            all_negative_chunks.append(neg_df)

            if not summary_df.empty:
                all_summary_chunks.append(summary_df)

            logging.warning(
                "[run_check] NEGATIVE FOUND table=%s negative_rows=%s affected_sheets=%s",
                table_name,
                len(neg_df),
                neg_df["SHEET_ID"].nunique(),
            )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    month_label = "_".join(months)

    negative_csv = os.path.join(
        output_dir,
        f"inspection_negative_xy_{month_label}_{timestamp}.csv",
    )

    summary_csv = os.path.join(
        output_dir,
        f"inspection_negative_xy_summary_{month_label}_{timestamp}.csv",
    )

    if all_negative_chunks:
        final_negative = pd.concat(all_negative_chunks, ignore_index=True)
    else:
        final_negative = pd.DataFrame(columns=[
            "source_table",
            "TOOL_ID",
            "SHEET_ID",
            "SCAN_ENDTIME",
            "COORD_X",
            "COORD_Y",
            "coord_x_num",
            "coord_y_num",
            "transform_rule",
            "x_mm",
            "y_mm",
            "x_out",
            "y_out",
        ])

    if all_summary_chunks:
        final_summary = pd.concat(all_summary_chunks, ignore_index=True)
    else:
        final_summary = pd.DataFrame(columns=[
            "source_table",
            "TOOL_ID",
            "SHEET_ID",
            "SCAN_ENDTIME",
            "negative_defect_count",
            "min_x_out",
            "min_y_out",
            "max_x_out",
            "max_y_out",
        ])

    final_negative.to_csv(negative_csv, index=False, encoding="utf-8-sig")
    final_summary.to_csv(summary_csv, index=False, encoding="utf-8-sig")

    logging.info("=" * 100)
    logging.info("[run_check] total_rows=%s", total_rows)
    logging.info("[run_check] total_valid_xy_rows=%s", total_valid_rows)
    logging.info("[run_check] total_invalid_xy_rows=%s", total_invalid_xy_rows)
    logging.info("[run_check] total_negative_xy_rows=%s", total_negative_rows)
    logging.info("[run_check] negative_csv=%s", negative_csv)
    logging.info("[run_check] summary_csv=%s", summary_csv)
    logging.info("=" * 100)

    return negative_csv, summary_csv, total_negative_rows


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--yyyymm",
        type=str,
        default=None,
        help='西元年月，可用逗號多選，例如 "202606" 或 "202605,202606"',
    )

    parser.add_argument(
        "--start-time",
        type=str,
        default=None,
        help='開始時間，格式 "YYYY-MM-DD HH:MM:SS"',
    )

    parser.add_argument(
        "--end-time",
        type=str,
        default=None,
        help='結束時間，不含此時間，格式 "YYYY-MM-DD HH:MM:SS"',
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default="output_csv",
        help="CSV 輸出資料夾",
    )

    parser.add_argument(
        "--log-dir",
        type=str,
        default="logs",
        help="log 輸出資料夾",
    )

    args = parser.parse_args()

    setup_logging(
        log_dir=args.log_dir,
        log_name="check_inspection_negative_xy.txt",
    )

    logging.info("=== check_inspection_negative_xy start ===")

    try:
        yyyymm_list = normalize_yyyymm_list(args.yyyymm)

        start_dt = parse_dt(args.start_time)
        end_dt = parse_dt(args.end_time)

        if (start_dt is None) ^ (end_dt is None):
            raise ValueError("若使用時間區間，--start-time 與 --end-time 必須同時指定")

        if start_dt and end_dt and start_dt >= end_dt:
            raise ValueError("--start-time 不可晚於或等於 --end-time")

        negative_csv, summary_csv, negative_rows = run_check(
            yyyymm_list=yyyymm_list,
            start_dt=start_dt,
            end_dt=end_dt,
            output_dir=args.output_dir,
        )

        if negative_rows > 0:
            logging.warning(
                "[main] finished with negative xy rows=%s csv=%s summary=%s",
                negative_rows,
                negative_csv,
                summary_csv,
            )
        else:
            logging.info(
                "[main] finished. no negative xy found. csv=%s summary=%s",
                negative_csv,
                summary_csv,
            )

    except Exception:
        logging.exception("[main] failed")
        raise

    finally:
        logging.info("=== check_inspection_negative_xy end ===")


if __name__ == "__main__":
    main()