# routers/common/editor.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import inspect

from models.sql_db_connect import MySQLConnet
from models.piaoi.density.cim_density_job import Config as DensityJobConfig


router = APIRouter(tags=["duty_cell_piaoi_common_chart_table_column_edit"])


# =============================================================================
# Helpers
# =============================================================================
def _clean_text(v: Any) -> str:
    if v is None:
        return ""

    s = str(v).strip()

    if s.lower() in {"", "nan", "none", "null", "nat", "<na>", "undefined"}:
        return ""

    return s


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
    """
    將 match_dict 中看起來像 datetime/date 的欄位轉成 Python datetime/date。
    bpi_same_point 的 editor_match_keys 不含時間欄位，所以不會把時間當 WHERE key。
    """
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


def _table_exists(dbhandler: MySQLConnet, table_name: str) -> bool:
    return inspect(dbhandler.engine).has_table(table_name, schema=dbhandler.db)


def _build_match_dict(raw_row: Dict[str, Any], match_keys: Optional[List[str]]) -> Dict[str, Any]:
    """
    match_keys 有設定：
      只取指定 key 當 WHERE 條件。

    match_keys 沒設定：
      沿用舊版邏輯，整個 row 都當 WHERE 條件。
    """
    if not isinstance(raw_row, dict) or not raw_row:
        raise HTTPException(status_code=400, detail="Missing row")

    if match_keys:
        out: Dict[str, Any] = {}

        for k in match_keys:
            v = raw_row.get(k)

            if v is None or str(v).strip() == "":
                raise HTTPException(status_code=400, detail=f"row.{k} is missing")

            out[k] = v

        return out

    return raw_row.copy()


def _capa_summary_table_name(aoi: str, yyyymm: str) -> str:
    return f"{aoi}_{yyyymm}_capa_summary"


def _derive_same_point_tab(row: Dict[str, Any]) -> str:
    """
    bpi_same_point editor fallback:
    若前端 row 沒帶 tab，後端依 api_aoi / api_recipe_id 補上。

    規則：
      api_aoi = aoi200:
        recipe 0 / 1 -> PISpot
        recipe 2 / 3 -> UPI

      api_aoi = aoi100 -> aoi100
      api_aoi = aoi300 -> aoi300
    """
    tab = _clean_text(row.get("tab"))
    if tab:
        return tab

    api_aoi = _clean_text(row.get("api_aoi"))
    api_recipe_id = _clean_text(row.get("api_recipe_id"))
    head = api_recipe_id[:1]

    if api_aoi == "aoi200":
        if head in {"0", "1"}:
            return "PISpot"

        if head in {"2", "3"}:
            return "UPI"

    if api_aoi in {"aoi100", "aoi300"}:
        return api_aoi

    return ""


def _resolve_bpi_same_point_table_name(
    target: Dict[str, Any],
    raw_row: Dict[str, Any],
) -> str:
    """
    bpi_same_point:
      - 優先使用 row._pair_source_table
      - fallback 才用 scan_hour 決定 yyyymm table
      - scan_hour 只用來決定月份表，不當 WHERE key
    """
    source_table = _clean_text(raw_row.get("_pair_source_table"))
    if source_table:
        return source_table

    table_tpl = target.get("table_tpl")
    if not table_tpl:
        raise HTTPException(status_code=500, detail="table_tpl is missing")

    time_key = target.get("time_key") or "scan_hour"
    time_raw = raw_row.get(time_key)

    if time_raw is None or str(time_raw).strip() == "":
        raise HTTPException(
            status_code=400,
            detail=f"row._pair_source_table or row.{time_key} is required for table resolving",
        )

    try:
        time_dt_full = _parse_dt(str(time_raw))
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"bad row.{time_key}: {time_raw}, err={e}",
        )

    if "yyyymm" in table_tpl:
        return table_tpl.replace("yyyymm", time_dt_full.strftime("%Y%m"))

    return table_tpl


# =============================================================================
# Resolve target
# =============================================================================
def _resolve_edit_target(system: str) -> Dict[str, Any]:
    # ---------------------------------------------------------
    # AOI Density
    # ---------------------------------------------------------
    if system == "density":
        density_cfg = DensityJobConfig()

        return {
            "dbhandler": MySQLConnet(density_cfg.out_db),
            "table_tpl": getattr(density_cfg, "code_table_tpl", "density_code_summary_yyyymm"),
            "time_key": "pi_hour",
            "requires_time_key": True,
            "editor_col": "Editor",
            "match_keys": None,
            "special_system": "",
        }

    # ---------------------------------------------------------
    # Inspection Density
    # ---------------------------------------------------------
    if system == "aoi_inspection_density":
        return {
            "dbhandler": MySQLConnet("piaoi_inspection_density"),
            "table_tpl": "inspection_api_summary_yyyymm",
            "time_key": "pi_hour",
            "requires_time_key": True,
            "editor_col": "Editor",
            "match_keys": None,
            "special_system": "",
        }

    # ---------------------------------------------------------
    # BPI Density
    # ---------------------------------------------------------
    if system == "bpi_density":
        from models.piaoi.bpi_density.API_Config import API_Config

        api_cfg = API_Config()

        return {
            "dbhandler": MySQLConnet(api_cfg.bpi_density_db_name),
            "table_tpl": api_cfg.bpi_density_summary_table_tpl,
            "time_key": "scan_hour",
            "requires_time_key": True,
            "editor_col": "editor",
            "match_keys": [
                "scan_hour",
                "aoi",
                "model",
                "cassette_id",
                "glass_side",
                "recipe_id",
            ],
            "special_system": "",
        }

    # ---------------------------------------------------------
    # BPI/API Same Point Pair
    # ---------------------------------------------------------
    if system == "bpi_same_point":
        from models.piaoi.bpi_density.API_Config import API_Config

        api_cfg = API_Config()
        sp_cfg = api_cfg.front_config.get("bpiSamePoint", {})

        editor_match_keys = (
            sp_cfg.get("editor_match_keys")
            or sp_cfg.get("manual_key_cols")
            or [
                "model",
                "glass_side",
                "glass_id",
                "tab",
                "api_aoi",
                "api_recipe_id",
            ]
        )

        return {
            "dbhandler": MySQLConnet(api_cfg.bpi_same_point_db_name),
            "table_tpl": api_cfg.bpi_same_point_pair_table_tpl,

            # bpi_same_point 不用時間當 WHERE key。
            # scan_hour 只用於 fallback 決定月份表。
            "time_key": sp_cfg.get("editor_time_key", "scan_hour"),
            "requires_time_key": bool(sp_cfg.get("editor_requires_time_key", False)),

            "editor_col": sp_cfg.get("editor_col", "editor"),
            "match_keys": editor_match_keys,
            "special_system": "bpi_same_point",
        }

    # ---------------------------------------------------------
    # AOI CAPA
    # ---------------------------------------------------------
    if system == "aoi_capa":
        from models.piaoi.capa.API_Config import Config as CapaConfig

        cfg = CapaConfig()

        def _table_func(row: Dict[str, Any], time_dt: datetime) -> str:
            aoi = str(row.get("aoi", "")).strip()
            if not aoi:
                raise HTTPException(status_code=400, detail="row.aoi is missing")
            return _capa_summary_table_name(aoi, time_dt.strftime("%Y%m"))

        return {
            "dbhandler": MySQLConnet(cfg.DB_NAME),
            "table_tpl": None,
            "table_func": _table_func,
            "time_key": "run_day",
            "requires_time_key": True,
            "editor_col": "editor",
            "match_keys": [
                "aoi",
                "run_day",
            ],
            "special_system": "",
        }

    raise HTTPException(status_code=400, detail=f"Unknown system: {system}")


def _resolve_table_name(target: Dict[str, Any], raw_row: Dict[str, Any], time_dt: datetime) -> str:
    if callable(target.get("table_func")):
        return target["table_func"](raw_row, time_dt)

    tbn_tpl = target.get("table_tpl")

    if not tbn_tpl:
        raise HTTPException(status_code=500, detail="table_tpl is missing")

    if "yyyymm" in tbn_tpl:
        return tbn_tpl.replace("yyyymm", time_dt.strftime("%Y%m"))

    return tbn_tpl


# =============================================================================
# Request
# =============================================================================
class EditSummaryRequest(BaseModel):
    system: Literal[
        "density",
        "aoi_inspection_density",
        "bpi_density",
        "bpi_same_point",
        "aoi_capa",
    ]
    mode: Literal["comment", "action"]
    row: Dict[str, Any]

    comment: Optional[str] = None
    action: Optional[str] = None
    editor: Optional[str] = None
    modify_time: Optional[str] = None


# =============================================================================
# API
# =============================================================================
@router.post("/edit_table")
async def api_edit_table(req: EditSummaryRequest):
    """
    更新 summary table 的 comment / action。

    支援:
      - density
      - aoi_inspection_density
      - bpi_density
      - bpi_same_point
      - aoi_capa

    bpi_same_point 特別規則：
      - WHERE key 由 API_Config.front_config["bpiSamePoint"]["editor_match_keys"] 決定
      - 預設為 model + glass_side + glass_id + tab + api_aoi + api_recipe_id
      - 不使用 scan_hour / api_scan_time / bpi_scan_time 當 WHERE key
      - scan_hour 只用來 fallback 決定月份表
      - 優先使用 row._pair_source_table 決定要更新哪張月表
    """
    print("[edit_table] req=", req.model_dump())

    if req.mode == "comment" and req.comment is None:
        raise HTTPException(status_code=400, detail="mode=comment but comment is missing")

    if req.mode == "action" and req.action is None:
        raise HTTPException(status_code=400, detail="mode=action but action is missing")

    target = _resolve_edit_target(req.system)

    dbhandler = target["dbhandler"]
    time_key = target.get("time_key", "pi_hour")
    editor_col = target.get("editor_col", "Editor")
    match_keys = target.get("match_keys")
    special_system = target.get("special_system", "")
    requires_time_key = bool(target.get("requires_time_key", True))

    raw_row = dict(req.row or {})
    if not raw_row:
        raise HTTPException(status_code=400, detail="row is missing")

    # -------------------------------------------------------------------------
    # bpi_same_point:
    #   1. 補 tab
    #   2. 用 _pair_source_table 或 scan_hour 決定 table
    #   3. 不要求 scan_hour 當 key
    # -------------------------------------------------------------------------
    if special_system == "bpi_same_point":
        raw_row["tab"] = _derive_same_point_tab(raw_row)

        tbn = _resolve_bpi_same_point_table_name(
            target=target,
            raw_row=raw_row,
        )

    else:
        time_raw = raw_row.get(time_key)

        if requires_time_key and (time_raw is None or str(time_raw).strip() == ""):
            raise HTTPException(status_code=400, detail=f"row.{time_key} is missing")

        try:
            time_dt_full = _parse_dt(str(time_raw))
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"bad row.{time_key}: {time_raw}, err={e}",
            )

        tbn = _resolve_table_name(target, raw_row, time_dt_full)

    if not _table_exists(dbhandler, tbn):
        raise HTTPException(status_code=404, detail=f"table not found: {tbn}")

    match_dict = _build_match_dict(raw_row, match_keys)
    match_dict = _normalize_match_datetime_cols(match_dict)

    mt = req.modify_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    update_dict: Dict[str, Any] = {
        editor_col: req.editor or "",
        "modify_time": mt,
    }

    if req.mode == "comment":
        update_dict["comment"] = req.comment
    else:
        update_dict["action"] = req.action

    print(f"[edit_table] system={req.system}")
    print(f"[edit_table] table={tbn}")
    print(f"[edit_table] special_system={special_system}")
    print(f"[edit_table] match_keys={match_keys}")
    print(f"[edit_table] match={match_dict}")
    print(f"[edit_table] update={update_dict}")

    try:
        dbhandler.update_rows(tbn, match_dict, update_dict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"update failed: {repr(e)}")

    return {
        "ok": True,
        "system": req.system,
        "table": tbn,
        "special_system": special_system,
        "match_keys": match_keys,
        "match_dict": match_dict,
        "update_dict": update_dict,
    }