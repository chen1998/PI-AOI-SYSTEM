# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, date
import pandas as pd
import json
import logging

from sqlalchemy import text

from models.sql_db_connect import MySQLConnet
from models.piaoi.capa.API_Config import (
    cfg,
    resolve_query_dates_to_range,
    month_list_from_date_range,
    summary_table_name,
    hourly_table_name,
    normalize_pi_type_for_filter,
    empty_day_df,
    empty_hourly_df,
)

router = APIRouter(tags=["duty_cell_piaoi_aoi_capa"])
logger = logging.getLogger(__name__)

db = MySQLConnet(cfg.DB_NAME)


# =========================================================
# JSON helpers
# =========================================================
def _to_py_scalar(v):
    """
    將 pandas / numpy / datetime 類型轉成 FastAPI 可序列化的 Python 原生型別
    """
    if v is None:
        return None

    try:
        if pd.isna(v):
            return None
    except Exception:
        pass

    if isinstance(v, pd.Timestamp):
        if pd.isna(v):
            return None
        return v.to_pydatetime().isoformat(sep=" ")

    if isinstance(v, (datetime, date)):
        return v.isoformat()

    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            pass

    return v


def _df_to_jsonable_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    將 DataFrame 轉成 FastAPI 可安全回傳的 records
    """
    if df is None or df.empty:
        return []

    raw_rows = df.to_dict(orient="records")
    out_rows = []

    for row in raw_rows:
        out_rows.append({k: _to_py_scalar(v) for k, v in row.items()})

    return out_rows


def _build_spec_dict_from_day_df(df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    spec_dict: Dict[str, Dict[str, Any]] = {}

    for aoi in cfg.uni_aoi_names:
        sub = df[(df["aoi"] == aoi) & (df["pi_type"] == "ALL")].copy()
        if sub.empty:
            spec_dict[aoi] = {
                "target_count": None,
                "spec": None,
            }
            continue

        sub = sub.sort_values("run_day")
        row = sub.iloc[-1]

        spec_dict[aoi] = {
            "target_count": _to_py_scalar(row["target_count"]) if "target_count" in row else None,
            "spec": _to_py_scalar(row["spec"]) if "spec" in row else None,
        }

    return spec_dict


def _filter_action_history_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    EditSummary / ActionHistory 用：
    只保留 comment 或 action 有內容的列
    """
    if df is None or df.empty:
        return empty_day_df()

    out = df.copy()
    out.drop_duplicates(subset=['aoi', 'run_day'], inplace=True)
    if "comment" not in out.columns:
        out["comment"] = ""
    if "action" not in out.columns:
        out["action"] = ""

    out["comment"] = out["comment"].fillna("").astype(str)
    out["action"] = out["action"].fillna("").astype(str)

    out = out[
        (out["comment"].str.strip() != "") |
        (out["action"].str.strip() != "")
    ].copy()

    return out


# =========================================================
# Internal DB loaders
# =========================================================
def _table_exists(table_name: str) -> bool:
    try:
        return db.table_exists(table_name)
    except Exception as e:
        logger.error(f"[_table_exists] {table_name} error: {e}")
        return False


def _load_day_summary_for_aoi(
    aoi: str,
    start_day: date,
    end_day: date,
) -> pd.DataFrame:
    """
    從 piaoi_capa 月表彙整指定 AOI + 日期區間的 summary
    """
    if aoi not in cfg.aoi_dict:
        raise ValueError(f"Unknown AOI: {aoi}")

    ym_list = month_list_from_date_range(start_day, end_day)
    cols = cfg.day_sql_cols
    col_sql = ", ".join([f"`{c}`" for c in cols])

    frames: List[pd.DataFrame] = []

    for ym in ym_list:
        tbn = summary_table_name(aoi, ym)
        if not _table_exists(tbn):
            continue

        sql = text(f"""
            SELECT {col_sql}
            FROM `{cfg.DB_NAME}`.`{tbn}`
            WHERE run_day BETWEEN :start_day AND :end_day
        """)

        with db.engine.connect() as conn:
            sub = pd.read_sql(
                sql,
                conn,
                params={"start_day": start_day, "end_day": end_day}
            )

        if not sub.empty:
            frames.append(sub)

    if not frames:
        return empty_day_df()

    df = pd.concat(frames, ignore_index=True)
    df["run_day"] = pd.to_datetime(df["run_day"], errors="coerce").dt.date
    df["modify_time"] = pd.to_datetime(df["modify_time"], errors="coerce")

    for col in cfg.day_sql_cols:
        if col not in df.columns:
            df[col] = None

    df = df[cfg.day_sql_cols].copy()
    df = df.sort_values(["run_day", "pi_type"]).reset_index(drop=True)
    return df


def _load_hourly_for_aoi(
    aoi: str,
    run_day: date,
    pi_type: Optional[str] = None,
) -> pd.DataFrame:
    """
    從 piaoi_capa 月表讀取指定 AOI + run_day 的 hourly
    """
    if aoi not in cfg.aoi_dict:
        raise ValueError(f"Unknown AOI: {aoi}")

    ym = run_day.strftime("%Y%m")
    tbn = hourly_table_name(aoi, ym)

    if not _table_exists(tbn):
        return empty_hourly_df()

    cols = cfg.rawdata_sql_cols
    col_sql = ", ".join([f"`{c}`" for c in cols])

    pi_type = normalize_pi_type_for_filter(pi_type)

    base_sql = f"""
        SELECT {col_sql}
        FROM `{cfg.DB_NAME}`.`{tbn}`
        WHERE run_day = :run_day
    """
    params: Dict[str, Any] = {"run_day": run_day}

    if pi_type and pi_type != "ALL":
        base_sql += " AND pi_type = :pi_type"
        params["pi_type"] = pi_type

    sql = text(base_sql)

    with db.engine.connect() as conn:
        df = pd.read_sql(sql, conn, params=params)

    if df.empty:
        return empty_hourly_df()

    df["run_day"] = pd.to_datetime(df["run_day"], errors="coerce").dt.date
    df["pi_hour"] = pd.to_datetime(df["pi_hour"], errors="coerce")

    for col in cfg.rawdata_sql_cols:
        if col not in df.columns:
            df[col] = None

    df = df[cfg.rawdata_sql_cols].copy()
    df = df.sort_values(["hour_sort", "pi_type"]).reset_index(drop=True)
    return df


# =========================================================
# API 1: reset summary filter
# =========================================================
@router.get("/api/reset_summary_filter")
async def reset_summary_filter(
    dates: Optional[List[str]] = Query(
        None,
        description="['YYYY-MM-DD [HH:MM:SS]', 'YYYY-MM-DD [HH:MM:SS]']"
    )
):
    """
    回傳：
    - DictData: summary rows
    - ParamDict: front config
    - DateRange: 後端實際使用日期區間
    """
    try:
        start_dt, end_dt = resolve_query_dates_to_range(dates)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    start_day = start_dt.date()
    end_day = end_dt.date()

    logger.info(f"[reset_summary_filter] start_day={start_day}, end_day={end_day}")

    all_frames: List[pd.DataFrame] = []

    for aoi in cfg.uni_aoi_names:
        try:
            df = _load_day_summary_for_aoi(aoi, start_day, end_day)
        except Exception as e:
            logger.error(f"[reset_summary_filter] 讀取 {aoi} summary 失敗: {e}")
            continue

        if df.empty:
            logger.info(f"[reset_summary_filter] {aoi} 無資料")
            continue

        df["aoi"] = aoi
        all_frames.append(df)

    if all_frames:
        final_df = pd.concat(all_frames, ignore_index=True)
    else:
        final_df = empty_day_df()

    spec_dict = _build_spec_dict_from_day_df(final_df)
    front_cfg = dict(cfg.front_config)
    front_cfg["SpecDict"] = spec_dict

    rows = _df_to_jsonable_records(final_df)

    payload = {
        "DictData": rows,
        "ParamDict": front_cfg,
        "DateRange": {
            "start": start_day.isoformat(),
            "end": end_day.isoformat(),
        }
    }
    return payload


# =========================================================
# API 2: hourly rawdata filter
# =========================================================
@router.get("/api/hourly_rawdata_filter")
async def hourly_rawdata_filter(
    filter_ask_keys: Optional[str] = Query(
        None,
        description="JSON 物件字串：{'aoi': aoi, 'pi_type': pi_type, 'run_day': 'YYYY-MM-DD'}"
    )
):
    """
    query example:
    {
      "aoi": "aoi200",
      "pi_type": "API",
      "run_day": "2026-04-17"
    }
    """
    if not filter_ask_keys:
        raise HTTPException(status_code=400, detail="filter_ask_keys is required")

    try:
        ask: Dict[str, Any] = json.loads(filter_ask_keys)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="filter_ask_keys 必須為 JSON 格式")

    aoi = ask.get("aoi")
    run_day_str = ask.get("run_day")
    pi_type = ask.get("pi_type")

    if not aoi or not run_day_str:
        raise HTTPException(status_code=400, detail="filter_ask_keys 需包含 'aoi' 與 'run_day'")

    if aoi not in cfg.aoi_dict:
        raise HTTPException(status_code=400, detail=f"未知的 AOI: {aoi}")

    try:
        run_day = datetime.strptime(run_day_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="run_day 格式應為 YYYY-MM-DD")

    logger.info(f"[hourly_rawdata_filter] aoi={aoi}, run_day={run_day}, pi_type={pi_type}")

    try:
        df = _load_hourly_for_aoi(aoi, run_day, pi_type)
    except Exception as e:
        logger.error(f"[hourly_rawdata_filter] 讀取 hourly 失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    rows = _df_to_jsonable_records(df)

    return {
        "rows": rows,
        "meta": {
            "aoi": aoi,
            "run_day": run_day.isoformat(),
            "pi_type": pi_type,
        }
    }


# =========================================================
# API 3: action history data
# =========================================================
@router.get("/api/action_history_data")
async def action_history_data(
    dates: Optional[List[str]] = Query(
        None,
        description="['YYYY-MM-DD [HH:MM:SS]', 'YYYY-MM-DD [HH:MM:SS]']"
    )
):
    """
    給 aoi-capa EditSummary / ActionHistory 使用

    規則：
    - dates 有傳：依 dates 區間撈
    - dates 為 None：預設最近 7 天
    - 從 aoi100 / aoi200 / aoi300 對應 summary 月表撈資料
    - 只回傳 comment 或 action 有值的列
    """
    try:
        start_dt, end_dt = resolve_query_dates_to_range(dates)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    start_day = start_dt.date()
    end_day = end_dt.date()

    logger.info(f"[action_history_data] start_day={start_day}, end_day={end_day}")

    all_frames: List[pd.DataFrame] = []

    for aoi in cfg.uni_aoi_names:
        try:
            df = _load_day_summary_for_aoi(aoi, start_day, end_day)
        except Exception as e:
            logger.error(f"[action_history_data] 讀取 {aoi} summary 失敗: {e}")
            continue

        if df.empty:
            continue

        df["aoi"] = aoi
        all_frames.append(df)

    if all_frames:
        final_df = pd.concat(all_frames, ignore_index=True)
    else:
        final_df = empty_day_df()

    final_df = _filter_action_history_rows(final_df)

    if not final_df.empty:
        final_df = final_df.sort_values(
            ["run_day", "aoi", "pi_type", "modify_time"],
            ascending=[False, True, True, False]
        ).reset_index(drop=True)

    rows = _df_to_jsonable_records(final_df)

    return {
        "rows": rows,
        "DateRange": {
            "start": start_day.isoformat(),
            "end": end_day.isoformat(),
        },
        "total": len(rows),
    }