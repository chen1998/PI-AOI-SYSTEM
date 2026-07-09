# routers/piaoi/density/recipe_same_point.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from fastapi import APIRouter, Query, HTTPException

from models.sql_db_connect import MySQLConnet
from models.piaoi.density.cim_density_job import Config as DensityJobConfig
from models.piaoi.density.API_Config import API_Config


router = APIRouter(tags=["duty_cell_piaoi_aoi_density"])
logger = logging.getLogger("aoi_density.recipe_same_point")


# =============================================================================
# Helpers
# =============================================================================
def _parse_date_only(s: str) -> datetime:
    s = str(s or "").strip().replace("T", " ")

    for fmt in ["%Y-%m-%d", "%y-%m-%d"]:
        try:
            return datetime.strptime(s, fmt).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
        except ValueError:
            pass

    raise ValueError(f"Bad date: {s}")


def _date_range_to_pi_hour_query_range(
    start_date: datetime,
    end_date: datetime,
) -> Tuple[datetime, datetime]:
    if end_date < start_date:
        start_date, end_date = end_date, start_date

    start = start_date.replace(hour=7, minute=0, second=0, microsecond=0)

    end_exclusive = (end_date + timedelta(days=1)).replace(
        hour=7,
        minute=0,
        second=0,
        microsecond=0,
    )

    return start, end_exclusive


def _compute_default_range(now: datetime) -> Tuple[datetime, datetime]:
    current_pi_hour = (now - timedelta(minutes=30)).replace(
        minute=0,
        second=0,
        microsecond=0,
    )

    start = (
        now.replace(hour=0, minute=0, second=0, microsecond=0)
        - timedelta(days=3)
    ).replace(hour=7, minute=0, second=0, microsecond=0)

    return start, current_pi_hour


def _month_span(start: datetime, end: datetime) -> List[str]:
    months: List[str] = []

    cur = datetime(start.year, start.month, 1)
    last = datetime(end.year, end.month, 1)

    while cur <= last:
        months.append(cur.strftime("%Y%m"))
        cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)

    return months


def _normalize_backend_tab_name(tab_name: str) -> str:
    s = str(tab_name or "").strip()

    if s == "UPI(Total)":
        return "UPI_Total"

    if s == "PISpot(Total)":
        return "PISpot_Total"

    return s


def _is_same_point_tab(tab_name: str) -> bool:
    return str(tab_name or "").strip() in {
        "UPI(Total)",
        "PISpot(Total)",
        "UPI_Total",
        "PISpot_Total",
    }


def _recipe_id_to_backend_tabs(recipe_id: Any, aoi: Any = "") -> List[str]:
    aoi_s = str(aoi or "").strip().lower()
    all_tabs = ["UPI", "UPI_Total", "PISpot", "PISpot_Total", "SPS"]

    if aoi_s in {"aoi100", "aoi300"}:
        return all_tabs

    s = str(recipe_id or "").strip()

    if not s:
        return []

    if len(s) == 4:
        if s.startswith(("2", "3")):
            return ["UPI", "UPI_Total"]

        if s.startswith(("0", "1")):
            return ["PISpot", "PISpot_Total", "SPS"]

    if len(s) == 3:
        return all_tabs

    return []


def _format_pi_hour_for_key(v: Any) -> str:
    try:
        ts = pd.to_datetime(v, errors="coerce")
        if pd.isna(ts):
            return str(v or "")
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(v or "")


def _same_point_key_from_row(r: Dict[str, Any]) -> str:
    return "||".join([
        _format_pi_hour_for_key(r.get("pi_hour")),
        str(r.get("line_id", "") or ""),
        str(r.get("aoi", "") or ""),
        str(r.get("model", "") or ""),
        str(r.get("glass_type", "") or ""),
        str(r.get("recipe_id", "") or ""),
    ])


def _safe_json_array(v: Any) -> str:
    if v is None:
        return "[]"

    if isinstance(v, list):
        try:
            return json.dumps(v, ensure_ascii=False)
        except Exception:
            return "[]"

    if isinstance(v, str):
        s = v.strip()

        if not s:
            return "[]"

        try:
            obj = json.loads(s)
            return json.dumps(obj if isinstance(obj, list) else [], ensure_ascii=False)
        except Exception:
            return "[]"

    return "[]"


def _normalize_same_point_df(df: pd.DataFrame, api_cols: List[str]) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=api_cols)

    out = df.copy()

    for c in api_cols:
        if c not in out.columns:
            if c in {"offset", "common_cnt", "common_glass_cnt"}:
                out[c] = 0
            elif c == "common_points_details":
                out[c] = "[]"
            else:
                out[c] = ""

    for c in ["offset", "common_cnt", "common_glass_cnt"]:
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0).astype(int)

    out["common_points_details"] = out["common_points_details"].apply(_safe_json_array)

    if "pi_hour" in out.columns:
        out["pi_hour"] = pd.to_datetime(out["pi_hour"], errors="coerce")

    if "gen_time" in out.columns:
        out["gen_time"] = pd.to_datetime(out["gen_time"], errors="coerce")

    return out


def _filter_by_backend_tab(df: pd.DataFrame, backend_tab: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    out["__tabs"] = out.apply(
        lambda r: _recipe_id_to_backend_tabs(
            recipe_id=r.get("recipe_id", ""),
            aoi=r.get("aoi", ""),
        ),
        axis=1,
    )

    out = out[
        out["__tabs"].apply(lambda arr: backend_tab in (arr or []))
    ].copy()

    out.drop(columns=["__tabs"], inplace=True, errors="ignore")

    return out


# =============================================================================
# Main API
# =============================================================================
@router.get("/recipe_same_point")
async def recipe_same_point(
    tab_name: str = Query(..., description="UPI(Total) or PISpot(Total)"),
    offset: int = Query(20, ge=0, description="same point offset"),
    dates: Optional[List[str]] = Query(None, description="['YYYY-MM-DD', 'YYYY-MM-DD']"),
):
    req_start_ts = datetime.now()

    cim_job_cfg = DensityJobConfig()
    api_cfg = API_Config(cim_job_cfg)
    dbhandler = MySQLConnet(cim_job_cfg.out_db)

    raw_tab = str(tab_name or "").strip()
    backend_tab = _normalize_backend_tab_name(raw_tab)

    logger.info(
        "[SamePoint][REQ] tab_name=%s backend_tab=%s offset=%s dates=%s",
        raw_tab,
        backend_tab,
        offset,
        dates,
    )

    if not _is_same_point_tab(raw_tab):
        logger.info(
            "[SamePoint][SKIP] not same point tab. tab_name=%s",
            raw_tab,
        )

        return {
            "ok": True,
            "tab_name": raw_tab,
            "backend_tab_name": backend_tab,
            "offset": int(offset),
            "SamePointData": [],
            "SamePointIndex": {},
            "Debug": {
                "reason": "not same point tab",
            },
        }

    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    if dates and len(dates) == 2:
        try:
            start_date = _parse_date_only(dates[0])
            end_date = _parse_date_only(dates[1])
            start, end_exclusive = _date_range_to_pi_hour_query_range(start_date, end_date)
        except Exception as e:
            logger.exception("[SamePoint][BAD_DATES] dates=%s", dates)
            raise HTTPException(status_code=400, detail=f"Bad dates: {dates} ({e})")
    else:
        start, end_exclusive = _compute_default_range(api_cfg.now)

    # 與 reset_summary_filter 保持一致：原本多抓一天
    end_exclusive = end_exclusive + timedelta(days=1)

    months = _month_span(start, end_exclusive - timedelta(hours=1))

    logger.info(
        "[SamePoint][QUERY_RANGE] tab=%s backend_tab=%s offset=%s "
        "pi_hour=[%s ~ %s) months=%s",
        raw_tab,
        backend_tab,
        int(offset),
        start.strftime("%Y-%m-%d %H:%M:%S"),
        end_exclusive.strftime("%Y-%m-%d %H:%M:%S"),
        months,
    )

    frames: List[pd.DataFrame] = []
    table_debug: List[Dict[str, Any]] = []

    for ym in months:
        tbn = f"density_recipe_same_point_{ym}".lower()

        if not dbhandler.table_exists(tbn):
            logger.warning("[SamePoint][TABLE_MISSING] table=%s.%s", cim_job_cfg.out_db, tbn)

            table_debug.append({
                "table": tbn,
                "exists": False,
                "raw_rows": 0,
            })

            continue

        sql = f"""
        SELECT *
        FROM `{cim_job_cfg.out_db}`.`{tbn}`
        WHERE `pi_hour` >= :start
          AND `pi_hour` < :end
          AND `offset` = :offset
        ORDER BY `pi_hour` DESC
        """

        df = dbhandler.query_df(
            sql,
            {
                "start": start,
                "end": end_exclusive,
                "offset": int(offset),
            },
        )

        raw_rows = 0 if df is None or df.empty else len(df)

        if df is None or df.empty:
            logger.info("[SamePoint][TABLE_ROWS] table=%s rows=0", tbn)

            table_debug.append({
                "table": tbn,
                "exists": True,
                "raw_rows": 0,
            })

            continue

        logger.info(
            "[SamePoint][TABLE_ROWS] table=%s raw_rows=%s pi_hour=[%s ~ %s]",
            tbn,
            len(df),
            df["pi_hour"].min() if "pi_hour" in df.columns else "",
            df["pi_hour"].max() if "pi_hour" in df.columns else "",
        )

        table_debug.append({
            "table": tbn,
            "exists": True,
            "raw_rows": int(raw_rows),
        })

        frames.append(df.copy())

    if frames:
        clean_df = pd.concat(frames, ignore_index=True)
    else:
        clean_df = pd.DataFrame(columns=api_cfg.aoi_density_same_point_api_cols)

    raw_concat_rows = len(clean_df)

    clean_df = _normalize_same_point_df(
        clean_df,
        api_cfg.aoi_density_same_point_api_cols,
    )

    before_tab_filter_rows = len(clean_df)

    clean_df = _filter_by_backend_tab(clean_df, backend_tab)

    after_tab_filter_rows = len(clean_df)

    clean_df = _normalize_same_point_df(
        clean_df,
        api_cfg.aoi_density_same_point_api_cols,
    )

    if clean_df.empty:
        data: List[Dict[str, Any]] = []
    else:
        df = clean_df[api_cfg.aoi_density_same_point_api_cols].copy()

        for c in ["pi_hour", "gen_time"]:
            if c in df.columns:
                df[c] = pd.to_datetime(df[c], errors="coerce").dt.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                df[c] = df[c].fillna("")

        df = df.fillna("")
        data = df.to_dict(orient="records")

    index: Dict[str, Dict[str, Any]] = {}

    common_rows = 0
    common_cnt_sum = 0
    common_glass_cnt_sum = 0

    for r in data:
        key = _same_point_key_from_row(r)

        common_cnt = int(r.get("common_cnt", 0) or 0)
        common_glass_cnt = int(r.get("common_glass_cnt", 0) or 0)

        if common_cnt > 0:
            common_rows += 1

        common_cnt_sum += common_cnt
        common_glass_cnt_sum += common_glass_cnt

        index[key] = {
            "offset": int(r.get("offset", 0) or 0),
            "common_cnt": common_cnt,
            "common_glass_cnt": common_glass_cnt,
            "common_points_details": r.get("common_points_details", "[]") or "[]",
            "gen_time": r.get("gen_time", "") or "",
        }

    cost_ms = round((datetime.now() - req_start_ts).total_seconds() * 1000, 1)

    logger.info(
        "[SamePoint][RESP] tab=%s backend_tab=%s offset=%s "
        "raw_concat_rows=%s before_tab_filter=%s after_tab_filter=%s "
        "data_rows=%s index_keys=%s common_rows=%s common_cnt_sum=%s "
        "common_glass_cnt_sum=%s cost_ms=%s",
        raw_tab,
        backend_tab,
        int(offset),
        raw_concat_rows,
        before_tab_filter_rows,
        after_tab_filter_rows,
        len(data),
        len(index),
        common_rows,
        common_cnt_sum,
        common_glass_cnt_sum,
        cost_ms,
    )

    return {
        "ok": True,
        "tab_name": raw_tab,
        "backend_tab_name": backend_tab,
        "offset": int(offset),
        "SamePointData": data,
        "SamePointIndex": index,
        "Debug": {
            "months": months,
            "query_start": start.strftime("%Y-%m-%d %H:%M:%S"),
            "query_end_exclusive": end_exclusive.strftime("%Y-%m-%d %H:%M:%S"),
            "raw_concat_rows": raw_concat_rows,
            "before_tab_filter_rows": before_tab_filter_rows,
            "after_tab_filter_rows": after_tab_filter_rows,
            "rows": len(data),
            "index_keys": len(index),
            "common_rows": common_rows,
            "common_cnt_sum": common_cnt_sum,
            "common_glass_cnt_sum": common_glass_cnt_sum,
            "table_debug": table_debug,
            "cost_ms": cost_ms,
        },
    }