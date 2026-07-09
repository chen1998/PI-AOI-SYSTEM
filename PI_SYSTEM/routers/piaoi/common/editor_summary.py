# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from typing import Optional, List, Dict, Any, Literal, Callable
from datetime import datetime, timedelta, date

import pandas as pd
from pydantic import BaseModel

from models.sql_db_connect import MySQLConnet
from models.piaoi.density.cim_density_job import Config as DensityJobConfig
from models.piaoi.density.API_Config import API_Config as AoiDensityApiConfig


router = APIRouter( tags=["duty_cell_piaoi_common_action_history_tab_edit"])


class EditorSummaryReq(BaseModel):
    mode: Literal["date", "edit"] = "date"
    dates: Optional[List[str]] = None

    system: Literal[
        "density",
        "aoi_inspection_density",
        "aoi_capa",
        "bpi_density",
        "bpi_same_point",
    ] = "density"

    # edit 用
    row: Optional[Dict[str, Any]] = None
    comment: Optional[str] = None
    action: Optional[str] = None
    editor: Optional[str] = None
    modify_time: Optional[str] = None


# =============================================================================
# Time helpers
# =============================================================================
def _parse_dt(s: str) -> datetime:
    """
    接受：
      YYYY-MM-DD
      YYYY-MM-DD HH
      YYYY-MM-DD HH:MM
      YYYY-MM-DD HH:MM:SS
      YY-MM-DD
      YY-MM-DD HH
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


def _month_span(start: datetime, end: datetime) -> List[str]:
    ym: List[str] = []
    cur = datetime(start.year, start.month, 1)
    last = datetime(end.year, end.month, 1)

    while cur <= last:
        ym.append(cur.strftime("%Y%m"))
        cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)

    return ym


def _compute_default_range(now: datetime) -> tuple[datetime, datetime]:
    end = now.replace(minute=0, second=0, microsecond=0)
    start = (end - timedelta(days=3)).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, end


def _is_date_like_time_key(time_key: str) -> bool:
    return time_key in {"run_day", "shift_day"}


def _parse_time_for_key(v: Any, time_key: str) -> Any:
    if v is None or str(v).strip() == "":
        return None

    dt = _parse_dt(str(v))

    if _is_date_like_time_key(time_key):
        return dt.date()

    return dt


def _normalize_match_datetime_cols(match_dict: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(match_dict)

    for k, v in list(out.items()):
        if v is None or str(v).strip() == "":
            continue

        if (
            k.endswith("_time")
            or k.endswith("_hour")
            or k in {"pi_hour", "scan_hour"}
        ):
            out[k] = _parse_dt(str(v))

        elif k in {"run_day", "shift_day"}:
            out[k] = _parse_dt(str(v)).date()

    return out


# =============================================================================
# DB helpers
# =============================================================================
def _try_get_table(dbhandler: MySQLConnet, tbn: str) -> Optional[pd.DataFrame]:
    try:
        df = dbhandler.get_table(tbn)
        if df is not None and len(df) > 0:
            return df
    except Exception:
        pass

    try:
        df = dbhandler.get_table(tbn.upper())
        if df is not None and len(df) > 0:
            return df
    except Exception:
        pass

    return None


def _filter_history_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    out = df.copy()

    if "comment" not in out.columns:
        out["comment"] = ""
    if "action" not in out.columns:
        out["action"] = ""

    return out[
        (out["comment"].fillna("").astype(str) != "") |
        (out["action"].fillna("").astype(str) != "")
    ].copy()


def _normalize_editor_cols(df: pd.DataFrame, editor_col: str) -> pd.DataFrame:
    """
    editor 欄位大小寫不一致，統一補齊 editor / Editor。
    """
    if df is None or df.empty:
        return df

    out = df.copy()

    if "editor" not in out.columns and "Editor" in out.columns:
        out["editor"] = out["Editor"]

    if "Editor" not in out.columns and "editor" in out.columns:
        out["Editor"] = out["editor"]

    if editor_col == "editor":
        if "editor" not in out.columns:
            out["editor"] = ""
    else:
        if "Editor" not in out.columns:
            out["Editor"] = ""

    if "modify_time" not in out.columns:
        out["modify_time"] = ""

    return out


def _build_match_dict(raw_row: Dict[str, Any], match_keys: Optional[List[str]]) -> Dict[str, Any]:
    """
    match_keys 有設定：
      只取指定 key 當 WHERE 條件。

    match_keys 沒設定：
      沿用舊邏輯，整個 row 都當 WHERE 條件。
    """
    if not isinstance(raw_row, dict) or not raw_row:
        raise HTTPException(status_code=400, detail="Missing row")

    if match_keys:
        out = {}

        for k in match_keys:
            v = raw_row.get(k)
            if v is None or str(v).strip() == "":
                raise HTTPException(status_code=400, detail=f"row.{k} is required")
            out[k] = v

        return out

    return raw_row.copy()


# =============================================================================
# Capa table helpers
# =============================================================================
def _capa_summary_table_name(aoi: str, yyyymm: str) -> str:
    return f"{aoi}_{yyyymm}_capa_summary"


def _capa_months_from_dates(start: datetime, end: datetime) -> List[str]:
    cur = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)

    out = []
    while cur <= last:
        out.append(cur.strftime("%Y%m"))
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)

    return out


# =============================================================================
# Resolve system
# =============================================================================
def _resolve_summary_system(system: str) -> Dict[str, Any]:
    """
    回傳：
      dbhandler
      table_cols
      table_tpl 或 table_name_func
      now
      time_key
      editor_col
      match_keys optional
      date_tables_func optional
    """
    # ---------------------------------------------------------
    # AOI Density
    # ---------------------------------------------------------
    if system == "density":
        density_cfg = DensityJobConfig()
        api_cfg = AoiDensityApiConfig(density_cfg)

        table_cols = list(
            (api_cfg.tab_filter_config.get("EditSummary") or {})
            .get("table_columns", [])
        )

        if not table_cols:
            table_cols = [
                "line_id",
                "aoi",
                "model",
                "glass_type",
                "recipe_id",
                "pi_hour",
                "adc_def_code",
                "density",
                "comment",
                "action",
                "Editor",
                "modify_time",
            ]

        return {
            "dbhandler": MySQLConnet(density_cfg.out_db),
            "table_cols": table_cols,
            "table_tpl": getattr(density_cfg, "code_table_tpl", "density_code_summary_yyyymm"),
            "now": getattr(api_cfg, "now", datetime.now()),
            "time_key": "pi_hour",
            "editor_col": "Editor",
            "match_keys": None,
        }

    # ---------------------------------------------------------
    # Inspection Density
    # ---------------------------------------------------------
    if system == "aoi_inspection_density":
        from models.inspection_density.API_Config import InspectionDensityApiConfig

        cfg = InspectionDensityApiConfig()

        table_cols = list(getattr(cfg, "action_his_keys", []))
        if not table_cols:
            table_cols = [
                "pi_hour",
                "line_id",
                "model",
                "glass_type",
                "comment",
                "action",
                "Editor",
                "modify_time",
            ]

        return {
            "dbhandler": MySQLConnet(cfg.db_name),
            "table_cols": table_cols,
            "table_tpl": getattr(cfg, "api_summary_table_tpl", "inspection_api_summary_yyyymm"),
            "now": getattr(cfg, "now", datetime.now()),
            "time_key": "pi_hour",
            "editor_col": "Editor",
            "match_keys": None,
        }

    # ---------------------------------------------------------
    # BPI Density - 新版 API_Config
    # ---------------------------------------------------------
    if system == "bpi_density":
        from models.piaoi.bpi_density.API_Config import API_Config as BPIApiConfig

        api_cfg = BPIApiConfig()

        tab_key = "bpi_density_action_history"
        table_cols = list(
            (api_cfg.tab_filter_config.get(tab_key) or {})
            .get("table_columns", [])
        )

        if not table_cols:
            table_cols = [
                "aoi",
                "model",
                "scan_hour",
                "cassette_id",
                "glass_side",
                "recipe_id",
                "density",
                "comment",
                "action",
                "editor",
                "modify_time",
            ]

        return {
            "dbhandler": MySQLConnet(api_cfg.bpi_density_db_name),
            "table_cols": table_cols,
            "table_tpl": api_cfg.bpi_density_summary_table_tpl,
            "now": getattr(api_cfg, "now", datetime.now()),
            "time_key": "scan_hour",
            "editor_col": "editor",
            # BPI Density 前端 EditSummary 通常 row 已是主鍵集合。
            # 這裡明確指定，避免 density/comment/action 被帶進 WHERE。
            "match_keys": [
                "scan_hour",
                "aoi",
                "model",
                "cassette_id",
                "glass_side",
                "recipe_id",
            ],
        }

    # ---------------------------------------------------------
    # BPI/API Same Point Pair
    # ---------------------------------------------------------
    if system == "bpi_same_point":
        from models.piaoi.bpi_density.API_Config import API_Config as BPIApiConfig

        api_cfg = BPIApiConfig()

        tab_key = "bpi_same_point_action_history"
        table_cols = list(
            (api_cfg.tab_filter_config.get(tab_key) or {})
            .get("table_columns", [])
        )
        bpi_same_cfg = api_cfg.front_config.get("bpiSamePoint", {})

        tab_conf = api_cfg.tab_filter_config.get(tab_key) or {}

        match_keys = list(
            tab_conf.get("editor_match_keys")
            or tab_conf.get("manual_key_cols")
            or api_cfg.front_config.get("bpiSamePoint", {}).get("editor_match_keys", [])
        )

        if not match_keys:
            match_keys = [
                "model",
                "glass_side",
                "glass_id",
                "tab",
                "api_recipe_id",
            ]

        return {
            "dbhandler": MySQLConnet(api_cfg.bpi_same_point_db_name),
            "table_cols": table_cols,
            "table_tpl": api_cfg.bpi_same_point_pair_table_tpl,
            "now": getattr(api_cfg, "now", datetime.now()),
            "time_key": "scan_hour",
            "editor_col": tab_conf.get("editor_col", "editor"),
            "match_keys": match_keys,
            "editor_requires_time_key": bool(tab_conf.get("editor_requires_time_key", False)),
        }
    # ---------------------------------------------------------
    # AOI CAPA
    # ---------------------------------------------------------
    if system == "aoi_capa":
        from models.piaoi.capa.API_Config import Config as CapaConfig

        cfg = CapaConfig()

        table_cols = list(
            (cfg.tab_filter_config.get("EditSummary") or {})
            .get("table_columns", [])
        )

        if not table_cols:
            table_cols = [
                "aoi",
                "run_day",
                "comment",
                "action",
                "Editor",
                "modify_time",
            ]

        def _date_tables_func(start: datetime, end: datetime) -> List[str]:
            months = _capa_months_from_dates(start, end)
            tables = []
            for aoi in cfg.uni_aoi_names:
                for ym in months:
                    tables.append(_capa_summary_table_name(aoi, ym))
            return tables

        def _edit_table_func(row: Dict[str, Any], time_dt: datetime) -> str:
            aoi = str(row.get("aoi", "")).strip()
            if not aoi:
                raise HTTPException(status_code=400, detail="row.aoi is required for aoi_capa")
            return _capa_summary_table_name(aoi, time_dt.strftime("%Y%m"))

        return {
            "dbhandler": MySQLConnet(cfg.DB_NAME),
            "table_cols": table_cols,
            "table_tpl": None,
            "date_tables_func": _date_tables_func,
            "edit_table_func": _edit_table_func,
            "now": datetime.now(),
            "time_key": "run_day",
            "editor_col": "editor",
            # 依目前 CAPA EditSummary table_columns，不含 pi_type。
            # 會更新同 aoi + run_day 的 rows。
            "match_keys": [
                "aoi",
                "run_day",
            ],
        }

    raise HTTPException(status_code=400, detail=f"Unknown system: {system}")


def _resolve_table_name_for_edit(sys_cfg: Dict[str, Any], raw_row: Dict[str, Any], time_dt: datetime) -> str:
    if callable(sys_cfg.get("edit_table_func")):
        return sys_cfg["edit_table_func"](raw_row, time_dt)

    table_tpl = sys_cfg.get("table_tpl")
    if not table_tpl:
        raise HTTPException(status_code=500, detail="table_tpl is missing")

    if "yyyymm" in table_tpl:
        return table_tpl.replace("yyyymm", time_dt.strftime("%Y%m"))

    return table_tpl


def _resolve_date_tables(sys_cfg: Dict[str, Any], start: datetime, end: datetime) -> List[str]:
    if callable(sys_cfg.get("date_tables_func")):
        return sys_cfg["date_tables_func"](start, end)

    table_tpl = sys_cfg.get("table_tpl")
    if not table_tpl:
        return []

    return [
        table_tpl.replace("yyyymm", ym)
        if "yyyymm" in table_tpl else table_tpl
        for ym in _month_span(start, end)
    ]


# =============================================================================
# Main
# =============================================================================
@router.post("/editor_summary")
async def editor_summary(req: EditorSummaryReq):
    """
    mode:
      - date: 依日期區間抓 history rows
      - edit: 更新 comment / action

    systems:
      - density
      - aoi_inspection_density
      - aoi_capa
      - bpi_density
      - bpi_same_point
    """
    sys_cfg = _resolve_summary_system(req.system)

    dbhandler = sys_cfg["dbhandler"]
    table_cols = list(sys_cfg["table_cols"])
    now = sys_cfg["now"]
    time_key = sys_cfg["time_key"]
    editor_col = sys_cfg.get("editor_col", "Editor")
    match_keys = sys_cfg.get("match_keys")

    # =========================================================
    # mode: edit
    # =========================================================
    if req.mode == "edit":
        if not req.row or not isinstance(req.row, dict):
            raise HTTPException(status_code=400, detail="Missing req.row for edit mode")

        raw_row = req.row.copy()

        editor_requires_time_key = bool(sys_cfg.get("editor_requires_time_key", True))

        time_raw = raw_row.get(time_key)
        if time_raw is None or str(time_raw).strip() == "":
            if editor_requires_time_key:
                raise HTTPException(status_code=400, detail=f"row.{time_key} is required")
            else:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"row.{time_key} is required for resolving monthly table. "
                        f"Please make sure backend returns hidden {time_key} in DictData."
                    )
                )
            

        try:
            time_dt_full = _parse_dt(str(time_raw))
            time_value = _parse_time_for_key(time_raw, time_key)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Bad row.{time_key}: {time_raw} ({e})")

        tbn = _resolve_table_name_for_edit(sys_cfg, raw_row, time_dt_full)

        match_dict = _build_match_dict(raw_row, match_keys)
        match_dict = _normalize_match_datetime_cols(match_dict)

        update_dict: Dict[str, Any] = {
            "modify_time": str(req.modify_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            editor_col: str(req.editor or ""),
        }

        if req.comment is not None:
            update_dict["comment"] = str(req.comment)

        if req.action is not None:
            update_dict["action"] = str(req.action)

        if "comment" not in update_dict and "action" not in update_dict:
            raise HTTPException(status_code=400, detail="Nothing to update")

        print("[editor_summary][edit] system =", req.system)
        print("[editor_summary][edit] table =", tbn)
        print("[editor_summary][edit] match_dict =", match_dict)
        print("[editor_summary][edit] update_dict =", update_dict)

        try:
            dbhandler.update_rows(tbn, match_dict, update_dict)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"update failed: {repr(e)}")

        return {
            "ok": True,
            "table": tbn,
            "match_dict": match_dict,
            "update_dict": update_dict,
        }

    # =========================================================
    # mode: date
    # =========================================================
    dates = req.dates if (req.dates and len(req.dates) == 2) else None

    if dates:
        start = _parse_dt(dates[0])
        end = _parse_dt(dates[1])

        if end < start:
            start, end = end, start

        # 結束日補到 23:59:59
        if len(str(dates[1]).strip()) <= 10:
            end = end.replace(hour=23, minute=59, second=59, microsecond=0)
    else:
        start, end = _compute_default_range(now)

    tables = _resolve_date_tables(sys_cfg, start, end)

    frames = []

    for tbn in tables:
        df = _try_get_table(dbhandler, tbn)
        if df is None or df.empty:
            continue

        df = df.copy()

        if time_key not in df.columns:
            continue

        if _is_date_like_time_key(time_key):
            df[time_key] = pd.to_datetime(df[time_key], errors="coerce").dt.date
            start_cmp = start.date()
            end_cmp = end.date()
            df = df[(df[time_key] >= start_cmp) & (df[time_key] <= end_cmp)]
        else:
            df[time_key] = pd.to_datetime(df[time_key], errors="coerce")
            df = df[(df[time_key] >= start) & (df[time_key] <= end)]

        if df.empty:
            continue

        df = _normalize_editor_cols(df, editor_col)

        for col in table_cols:
            if col not in df.columns:
                df[col] = ""

        if "editor" not in df.columns:
            df["editor"] = ""
        if "Editor" not in df.columns:
            df["Editor"] = ""
        if "modify_time" not in df.columns:
            df["modify_time"] = ""

        # 時間格式化
        if _is_date_like_time_key(time_key):
            df[time_key] = pd.to_datetime(df[time_key], errors="coerce")
            df[time_key] = df[time_key].dt.strftime("%Y-%m-%d").fillna("")
        else:
            df[time_key] = pd.to_datetime(df[time_key], errors="coerce")
            df[time_key] = df[time_key].dt.strftime("%Y-%m-%d %H:%M:%S").fillna("")

        if "modify_time" in df.columns:
            df["modify_time"] = pd.to_datetime(df["modify_time"], errors="coerce") \
                .dt.strftime("%Y-%m-%d %H:%M:%S").fillna("")

        frames.append(df)

    if frames:
        clean_df = pd.concat(frames, ignore_index=True)
    else:
        clean_df = pd.DataFrame(columns=table_cols)

    clean_df = _filter_history_rows(clean_df)

    final_cols = table_cols[:]

    # time_key 不一定顯示在前端 table_columns，
    # 但 edit 時需要用它判斷更新哪個月份表，所以必須作為 hidden row data 回傳。
    if time_key not in final_cols:
        final_cols.append(time_key)

    for extra_col in ["editor", "Editor", "modify_time"]:
        if extra_col not in final_cols and extra_col in clean_df.columns:
            final_cols.append(extra_col)

    if clean_df.empty:
        clean_df = pd.DataFrame(columns=final_cols)
    else:
        for c in final_cols:
            if c not in clean_df.columns:
                clean_df[c] = ""
        clean_df = clean_df[final_cols]

    data = clean_df.to_dict(orient="index")

    return {
        "DictData": data,
        "status": "ok",
    }