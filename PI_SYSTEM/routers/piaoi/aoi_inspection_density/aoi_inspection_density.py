# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List, Dict, Any
import pandas as pd
import copy
import json

try:
    from PI_SYSTEM.models.inspection_density.sql_db_connect2 import MySQLConnetFunc as _DBHandler
except Exception:
    try:
        from models.inspection_density.sql_db_connect2 import MySQLConnetFunc as _DBHandler
    except Exception:
        from models.sql_db_connect import MySQLConnet as _DBHandler

from models.inspection_density.API_Config import (
    CFG,
    parse_dt,
    month_span,
    to_pi_hour_range,
    compute_default_shift_range,
    resolve_query_dates_to_range,
    try_get_table,
    safe_fill_columns,
    normalize_datetime_cols,
    ensure_json_string_col,
    #build_action_history,
    spec_table_clean,
)

router = APIRouter(tags=["duty_cell_piaoi_aoi_inspeciton"])


@router.get("/reset_summary_filter")
async def reset_summary_filter(
    dates: Optional[List[str]] = Query(None),
    filter_ask_keys: Optional[str] = Query(None),
):
    dbhandler = _DBHandler(CFG.db_name)

    # =====================================================
    # time range
    # =====================================================
    try:
        if dates and len(dates) == 2:
            print('frontend dates:',dates)
            start, end = resolve_query_dates_to_range(dates[0], dates[1])
            if end < start:
                start, end = end, start
        else:
            # 預設抓近三個 shift day，且包含目前所在 bucket
            start, end = compute_default_shift_range()
        print(f"{start} ~ {end}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Bad dates: {dates} ({e})")

    months = month_span(start, end)

    # 與 core.py 一致：使用 pi_hour bucket 範圍查 API summary table
    pi_start, pi_end = to_pi_hour_range(start, end)

    # =====================================================
    # filters
    # 目前仍保留相容；主篩選還是前端做
    # =====================================================
    try:
        filters = json.loads(filter_ask_keys) if filter_ask_keys else {}
        if not isinstance(filters, dict):
            filters = {}
    except Exception:
        filters = {}

    # =====================================================
    # load API summary month tables
    # =====================================================
    frames: List[pd.DataFrame] = []

    option_sets: Dict[str, set] = {k: set() for k in CFG.filter_item_coldict.keys()}
    option_sets["defect_size"] = set(CFG.uni_defect_sizes)

    for ym in months:
        tbn = CFG.api_summary_table_tpl.replace("yyyymm", ym)
        df = try_get_table(dbhandler, tbn)
        if df is None or df.empty:
            continue

        if "pi_hour" not in df.columns:
            continue

        df = normalize_datetime_cols(df)

        # 用 pi_hour bucket 範圍篩選
        df = df[df["pi_hour"].notna()]
        df = df[(df["pi_hour"] >= pi_start) & (df["pi_hour"] <= pi_end)]

        if df.empty:
            continue

        # 收集 filter options
        for key in CFG.filter_item_coldict.keys():
            if key == "defect_size":
                continue

            if key in df.columns:
                vals = (
                    df[key]
                    .dropna()
                    .astype(str)
                    .map(str.strip)
                    .replace("", pd.NA)
                    .dropna()
                    .unique()
                    .tolist()
                )
                option_sets[key].update(vals)

        frames.append(df)

    clean_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    # =====================================================
    # ensure required columns
    # =====================================================
    required_cols = list(dict.fromkeys(CFG.api_summary_cols + CFG.api_summary_output_cols))
    clean_df = safe_fill_columns(clean_df, required_cols, default="")

    numeric_cols = [
        "maingroup_glass_count",
        "maingroup_defect_count",
        "defect_code_glass_count",
        "small_defect_count",
        "middle_defect_count",
        "large_defect_count",
        "over_defect_count",
    ]
    for c in numeric_cols:
        clean_df[c] = pd.to_numeric(clean_df[c], errors="coerce").fillna(0).astype(int)

    # defect size mask
    if not clean_df.empty:
        clean_df["size_mask"] = (
            clean_df["small_defect_count"].gt(0).astype(int) * 1
            + clean_df["middle_defect_count"].gt(0).astype(int) * 2
            + clean_df["large_defect_count"].gt(0).astype(int) * 4
            + clean_df["over_defect_count"].gt(0).astype(int) * 8
        )
    else:
        clean_df["size_mask"] = pd.Series(dtype="int64")

    # =====================================================
    # filter options / defaults
    # =====================================================
    option_dict = {
        k: sorted(v) if k != "defect_size" else CFG.uni_defect_sizes[:]
        for k, v in option_sets.items()
    }

    # =====================================================
    # spec + front config
    # =====================================================
    prospecdict, subtabs_filter_default_dict = spec_table_clean(
        dbhandler=dbhandler,
        summary_df=clean_df,
        base_subtabs_filter_default_dict=copy.deepcopy(
            CFG.front_config.get("SubTabsFilterDefaultDict", {})
        ),
    )

    # action history
    #prospecdict["EditSummary"] = build_action_history(clean_df)

    # =====================================================
    # front config
    # =====================================================
    param_dict = copy.deepcopy(CFG.front_config)
    param_dict["filterOptionDict"] = option_dict
    param_dict["DefectSize"] = {
        "maskBits": {"S": 1, "M": 2, "L": 4, "O": 8},
        "maskKey": "size_mask",
    }
    param_dict["TrendKeyDict"] = {
        "hour": "pi_hour",
        "day": "shift_day",
        "week": "shift_week",
        "month": "shift_month",
    }
    param_dict["SubTabsFilterDefaultDict"] = subtabs_filter_default_dict

    # 方便前端除錯 / 顯示目前後端實際解析的查詢區間
    param_dict["ResolvedQueryRange"] = {
        "start": pd.Timestamp(start).strftime("%Y-%m-%d %H:%M:%S"),
        "end": pd.Timestamp(end).strftime("%Y-%m-%d %H:%M:%S"),
        "pi_start": pd.Timestamp(pi_start).strftime("%Y-%m-%d %H:%M:%S"),
        "pi_end": pd.Timestamp(pi_end).strftime("%Y-%m-%d %H:%M:%S"),
    }

    # =====================================================
    # stable API output
    # =====================================================
    out_cols = [c for c in CFG.api_summary_output_cols if c in clean_df.columns] + ["size_mask"]
    out_df = clean_df[out_cols].copy()

    # datetime -> string
    if "pi_hour" in out_df.columns:
        out_df["pi_hour"] = pd.to_datetime(out_df["pi_hour"], errors="coerce")
        out_df["pi_hour"] = out_df["pi_hour"].dt.strftime("%Y-%m-%d %H:%M:%S").fillna("")

    if "modify_time" in out_df.columns:
        out_df["modify_time"] = pd.to_datetime(out_df["modify_time"], errors="coerce")
        out_df["modify_time"] = out_df["modify_time"].dt.strftime("%Y-%m-%d %H:%M:%S").fillna("")

    # JSON string col
    out_df = ensure_json_string_col(out_df, "glass_size_detail")

    # 全欄位補空字串
    out_df.fillna("", inplace=True)

    data = out_df.to_dict(orient="records")

    return {
        "DictData": data,
        "ParamDict": param_dict,
        "ProSpecDict": prospecdict,
    }
