# routers/bpi_density/bpi_density.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from models.sql_db_connect import MySQLConnet
from models.piaoi.bpi_density.API_Config import API_Config


router = APIRouter(tags=["duty_cell_piaoi_bpi_density"])


# =============================================================================
# Time helpers
# =============================================================================
def _parse_dt(s: str) -> datetime:
    """
    接受多種格式:
      YYYY-MM-DD[ HH[:MM[:SS]]]
      YY-MM-DD[ HH]

    若只給日期 -> 00:00:00
    若含時間 -> 回到整點
    """
    s = str(s or "").strip().replace("T", " ")

    fmts = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H",
        "%Y-%m-%d",
        "%y-%m-%d %H",
        "%y-%m-%d",
    ]

    for f in fmts:
        try:
            dt = datetime.strptime(s, f)
            if f in ("%Y-%m-%d", "%y-%m-%d"):
                return dt.replace(hour=0, minute=0, second=0, microsecond=0)
            return dt.replace(minute=0, second=0, microsecond=0)
        except ValueError:
            continue

    raise ValueError(f"Bad datetime: {s}")


def _parse_date_only(s: str) -> datetime:
    s = str(s or "").strip().replace("T", " ")

    for f in ("%Y-%m-%d", "%y-%m-%d"):
        try:
            dt = datetime.strptime(s, f)
            return dt.replace(hour=0, minute=0, second=0, microsecond=0)
        except ValueError:
            continue

    raise ValueError(f"Bad date: {s}")


def _month_span(start: datetime, end: datetime) -> List[str]:
    """
    回傳 [YYYYMM, ...]，涵蓋 start~end 的所有月份。
    end 可為 exclusive 或接近 exclusive。
    """
    ym: List[str] = []

    cur = datetime(start.year, start.month, 1)
    last = datetime(end.year, end.month, 1)

    while cur <= last:
        ym.append(cur.strftime("%Y%m"))
        cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)

    return ym


def _compute_default_range(now: datetime) -> tuple[datetime, datetime]:
    """
    預設查詢：
      起點：往前 3 天 07:00
      終點：目前所屬 scan_hour bucket

    scan_hour 定義：
      floor(test_time - 30min, 1H)
    """
    current_scan_hour = (now - timedelta(minutes=30)).replace(
        minute=0,
        second=0,
        microsecond=0,
    )

    start = (
        now.replace(hour=0, minute=0, second=0, microsecond=0)
        - timedelta(days=3)
    ).replace(hour=7, minute=0, second=0, microsecond=0)

    end_exclusive = current_scan_hour
    return start, end_exclusive


def _date_range_to_scan_hour_query_range(
    start_date: datetime,
    end_date: datetime,
) -> tuple[datetime, datetime]:
    """
    前端日期語意：
      D = [D 07:30:00, D+1 07:30:00)

    查 summary scan_hour：
      [D 07:00:00, D+1 07:00:00)
    """
    if end_date < start_date:
        start_date, end_date = end_date, start_date

    start = start_date.replace(hour=7, minute=0, second=0, microsecond=0)
    end_exclusive = end_date.replace(hour=7, minute=0, second=0, microsecond=0)

    return start, end_exclusive


# =============================================================================
# Data helpers
# =============================================================================
def _to_size_mask(row) -> int:
    mask = 0

    try:
        mask |= 1 if float(row.get("small_defect_count", 0) or 0) > 0 else 0
        mask |= 2 if float(row.get("middle_defect_count", 0) or 0) > 0 else 0
        mask |= 4 if float(row.get("large_defect_count", 0) or 0) > 0 else 0
        mask |= 8 if float(row.get("over_defect_count", 0) or 0) > 0 else 0
    except Exception:
        pass

    return mask


def _ensure_cols(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    out = df.copy()

    for c in cols:
        if c not in out.columns:
            out[c] = ""

    return out


def _format_datetime_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    for dt_col in ["scan_hour", "modify_time"]:
        if dt_col in out.columns:
            out[dt_col] = pd.to_datetime(out[dt_col], errors="coerce")
            out[dt_col] = out[dt_col].apply(
                lambda x: "" if pd.isna(x) else x.strftime("%Y-%m-%d %H:%M:%S")
            )

    if "run_day" in out.columns:
        out["run_day"] = pd.to_datetime(out["run_day"], errors="coerce")
        out["run_day"] = out["run_day"].apply(
            lambda x: "" if pd.isna(x) else x.strftime("%Y-%m-%d")
        )

    return out


# =============================================================================
# Main API
# =============================================================================
@router.get("/reset_summary_filter")
async def reset_summary_filter(
    dates: Optional[List[str]] = Query(
        None,
        description="['YYYY-MM-DD [HH:MM:SS]', 'YYYY-MM-DD [HH:MM:SS]']",
    )
):
    # -----------------------
    # Config
    # -----------------------
    api_cfg = API_Config()

    dbhandler = MySQLConnet(api_cfg.bpi_density_db_name)

    # -----------------------
    # Spec table
    # -----------------------
    try:
        spec_table_dict = api_cfg.bpi_density_spec_table_process(dbhandler)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"bpi_density_spec_table_process failed: {e}")

    # -----------------------
    # Date range
    # -----------------------
    if dates and len(dates) == 2:
        try:
            start_date = _parse_date_only(dates[0])
            end_date = _parse_date_only(dates[1])
            start, end_exclusive = _date_range_to_scan_hour_query_range(start_date, end_date)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Bad dates: {dates} ({e})")
    else:
        start, end_exclusive = _compute_default_range(api_cfg.now)

    # 保留額外一天，避免跨班資料沒撈到
    end_exclusive = end_exclusive + timedelta(days=1)

    months = _month_span(start, end_exclusive - timedelta(hours=1))

    print(f"[BPI Density] 撈取資料(scan_hour): [{start} ~ {end_exclusive})")

    # -----------------------
    # Load data
    # -----------------------
    frames: List[pd.DataFrame] = []

    option_dict: Dict[str, List[str]] = {
        k: [] for k in api_cfg.bpi_density_filter_item_coldict.keys()
    }

    # BPI Density 主頁仍使用 S/M/L/O mask
    option_dict["defect_size"] = ["S", "M", "L", "O"]

    for ym in months:
        tbn = api_cfg.bpi_density_summary_table_tpl.replace("yyyymm", ym).lower()

        if not dbhandler.table_exists(tbn):
            print(f"[BPI Density] missing table: {tbn}")
            continue

        df = dbhandler.get_runs_between(
            tbn,
            start,
            end_exclusive,
            time_col="scan_hour",
        )

        if df is None or len(df) == 0:
            print(f"[BPI Density] table:{tbn}, rows:0")
            continue

        df = pd.DataFrame(df).copy()
        if df.empty:
            print(f"[BPI Density] table:{tbn}, rows:0")
            continue

        df.fillna("", inplace=True)

        if "scan_hour" in df.columns:
            df["scan_hour"] = pd.to_datetime(df["scan_hour"], errors="coerce")

        if "modify_time" in df.columns:
            df["modify_time"] = pd.to_datetime(df["modify_time"], errors="coerce")

        # Build filter options for BPI Density only
        for key in api_cfg.bpi_density_filter_item_coldict.keys():
            if key in df.columns:
                uniq = (
                    df[key]
                    .astype(str)
                    .fillna("")
                    .unique()
                    .tolist()
                )
                option_dict[key].extend([
                    v for v in uniq
                    if v and v not in option_dict[key]
                ])

        frames.append(df)

        try:
            print(
                f"[BPI Density] 資料表:{tbn}, rows:{len(df)}, "
                f"{df['scan_hour'].min()} ~ {df['scan_hour'].max()}"
            )
        except Exception:
            print(f"[BPI Density] 資料表:{tbn}, rows:{len(df)}")

    if frames:
        clean_df = pd.concat(frames, ignore_index=True)
    else:
        clean_df = pd.DataFrame(columns=api_cfg.bpi_density_summary_sql_cols)

    # -----------------------
    # size_mask
    # -----------------------
    if not clean_df.empty:
        clean_df["size_mask"] = clean_df.apply(_to_size_mask, axis=1).astype(int)
    else:
        clean_df["size_mask"] = pd.Series([], dtype="int64")

    # -----------------------
    # ParamDict
    # -----------------------
    param_dict = copy.deepcopy(api_cfg.front_config)

    # 新版 BPI Density namespace
    param_dict.setdefault("bpiDensity", {})
    param_dict["bpiDensity"]["filterOptionDict"] = option_dict

    # -----------------------
    # Action History data for BPI Density
    # -----------------------
    try:
        action_tab_key = "bpi_density_action_history"

        action_conf = param_dict["SubTabsFilterDefaultDict"].get(action_tab_key, {})
        hs_cols = action_conf.get("table_columns", [])

        hs_cols = [c for c in hs_cols if c in clean_df.columns]
        hs_df = clean_df[hs_cols].copy() if hs_cols else pd.DataFrame()

        if not hs_df.empty:
            if "action" in hs_df.columns and "comment" in hs_df.columns:
                hs_df = hs_df[(hs_df["action"] != "") | (hs_df["comment"] != "")]
            elif "action" in hs_df.columns:
                hs_df = hs_df[hs_df["action"] != ""]
            elif "comment" in hs_df.columns:
                hs_df = hs_df[hs_df["comment"] != ""]

        param_dict["SubTabsFilterDefaultDict"][action_tab_key]["data"] = hs_df.to_dict(orient="index")
    except Exception:
        try:
            param_dict["SubTabsFilterDefaultDict"]["bpi_density_action_history"]["data"] = {}
        except Exception:
            pass

    # -----------------------
    # Return DictData
    # -----------------------
    clean_df = _ensure_cols(clean_df, api_cfg.bpi_density_summary_api_cols)
    df = clean_df[api_cfg.bpi_density_summary_api_cols].copy()
    df = _format_datetime_cols(df)

    data = df.to_dict(orient="records")

    return {
        "DictData": data,
        "ParamDict": param_dict,
        "ProSpecDict": spec_table_dict,
        "Debug": {
            "db_name": api_cfg.bpi_density_db_name,
            "summary_table_tpl": api_cfg.bpi_density_summary_table_tpl,
            "months": months,
            "start": start.strftime("%Y-%m-%d %H:%M:%S"),
            "end_exclusive": end_exclusive.strftime("%Y-%m-%d %H:%M:%S"),
            "rows": len(clean_df),
            "option_keys": list(option_dict.keys()),
        },
    }