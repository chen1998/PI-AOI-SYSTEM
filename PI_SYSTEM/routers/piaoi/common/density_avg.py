# routers/common/density_avg.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import re
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from models.sql_db_connect import MySQLConnet


router = APIRouter(prefix="/density_avg", tags=["duty_cell_piaoi_density_avg"])
logger = logging.getLogger("density_avg")


# =============================================================================
# Constants
# =============================================================================
VALID_SIZE_ATOMS = ["S", "M", "L", "O"]
VALID_SIZES = VALID_SIZE_ATOMS[:]

SIZE_GROUP_OPTIONS = [
    "S",
    "MS",
    "LMS",
    "O",
    "OL",
    "OLM",
    "OLMS",
]

SIZE_GROUP_ATOMS = {
    "S": {"S"},
    "MS": {"M", "S"},
    "LMS": {"L", "M", "S"},
    "O": {"O"},
    "OL": {"O", "L"},
    "OLM": {"O", "L", "M"},
    "OLMS": {"O", "L", "M", "S"},
}

SIZE_GROUP_ALIASES = {
    "SM": "MS",
    "SML": "LMS",
    "SMLO": "OLMS",
}

SHIFT_HOUR = 7
SHIFT_MINUTE = 30
SHIFT_DELTA = timedelta(hours=SHIFT_HOUR, minutes=SHIFT_MINUTE)
LABEL_30MIN_DELTA = timedelta(minutes=30)


# =============================================================================
# Request Models
# =============================================================================
class DensityAvgRequest(BaseModel):
    system: str
    start_date: str
    end_date: str
    filters: Dict[str, List[Any]] = Field(default_factory=dict)
    limit: Optional[int] = None


# =============================================================================
# Config
# =============================================================================
@dataclass
class DensityAvgConfig:
    system: str
    db_name: str
    main_table_tpl: str
    time_col: str

    avg_config: Dict[str, Any] = field(default_factory=dict)

    group_keys: List[str] = field(default_factory=list)
    metric_columns: List[str] = field(default_factory=list)
    source_columns: Dict[str, str] = field(default_factory=dict)
    filter_item_coldict: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    cascade_order: List[str] = field(default_factory=list)
    table_columns: Dict[str, str] = field(default_factory=dict)
    download_columns: Dict[str, str] = field(default_factory=dict)
    recipe_defect_default_rules: List[Dict[str, Any]] = field(default_factory=list)
    denominator_identity_cols: List[str] = field(default_factory=list)
    summary_row_identity_cols: List[str] = field(default_factory=list)
    metric_definition: Dict[str, Any] = field(default_factory=dict)
    summary_labels: Dict[str, Dict[str, str]] = field(default_factory=dict)

    time_semantic: str = ""
    day_boundary: str = "07:30"

    preview_limit: int = 5000


# =============================================================================
# System / API_Config resolution
# =============================================================================
def _normalize_system(system: str) -> str:
    s = (system or "").strip()

    aliases = {
        "aoi-density": "aoi_density",
        "aoi_density": "aoi_density",

        "aoi-bpi-density": "aoi_bpi_density",
        "aoi_bpi_density": "aoi_bpi_density",
        "bpi_density": "aoi_bpi_density",

        "aoi-inspection-density": "aoi_inspection_density",
        "aoi_inspection_density": "aoi_inspection_density",
        "inspection_density": "aoi_inspection_density",

        "bpi_same_point": "bpi_same_point",
        "bpi-api-same-point": "bpi_same_point",
        "bpi_api_same_point": "bpi_same_point",
        "same_point": "bpi_same_point",
    }

    return aliases.get(s, s)


def _normalize_monthly_tpl(tpl: str, fallback: str) -> str:
    s = str(tpl or "").strip()
    if not s:
        s = fallback

    if "yyyymm" in s:
        return s

    if re.search(r"_\d{6}$", s):
        return re.sub(r"_\d{6}$", "_yyyymm", s)

    return s


def _get_density_average_config(api_cfg: Any, tab_key: str = "density_average") -> Dict[str, Any]:
    tab_cfg = getattr(api_cfg, "tab_filter_config", {}) or {}
    avg = tab_cfg.get(tab_key, {}) or {}

    if not isinstance(avg, dict) or not avg:
        raise HTTPException(
            status_code=500,
            detail=f"API_Config.tab_filter_config['{tab_key}'] is missing",
        )

    return avg


def _resolve_avg_config(system: str) -> DensityAvgConfig:
    key = _normalize_system(system)
    logger.info("[density_avg] resolve system raw=%s normalized=%s", system, _normalize_system(system))
    # ------------------------------------------------------------
    # AOI Density
    # ------------------------------------------------------------
    if key == "aoi_density":
        from models.piaoi.density.cim_density_job import Config as AoiDensityJobConfig
        from models.piaoi.density.API_Config import API_Config as AoiDensityApiConfig

        job_cfg = AoiDensityJobConfig()
        api_cfg = AoiDensityApiConfig(job_cfg)
        avg_cfg = _get_density_average_config(api_cfg, "density_average")

        table_tpl = getattr(job_cfg, "code_table_tpl", "density_code_summary_yyyymm")

        return DensityAvgConfig(
            system=key,
            db_name=getattr(job_cfg, "out_db", "piaoi_density"),
            main_table_tpl=_normalize_monthly_tpl(table_tpl, "density_code_summary_yyyymm"),
            time_col=str(avg_cfg.get("time_col") or "pi_hour"),
            avg_config=avg_cfg,
            group_keys=list(avg_cfg.get("group_keys") or ["line_id", "glass_type", "model"]),
            metric_columns=list(avg_cfg.get("metric_columns") or []),
            source_columns=dict(avg_cfg.get("source_columns") or {}),
            filter_item_coldict=dict(avg_cfg.get("filter_item_coldict") or {}),
            cascade_order=list(avg_cfg.get("cascade_order") or []),
            table_columns=dict(avg_cfg.get("table_columns") or {}),
            download_columns=dict(avg_cfg.get("download_columns") or {}),
            recipe_defect_default_rules=list(avg_cfg.get("recipe_defect_default_rules") or []),
            denominator_identity_cols=list(avg_cfg.get("denominator_identity_cols") or []),
            summary_row_identity_cols=list(avg_cfg.get("summary_row_identity_cols") or []),
            metric_definition=dict(avg_cfg.get("metric_definition") or {}),
            summary_labels=dict(avg_cfg.get("summary_labels") or {}),
            time_semantic=str(avg_cfg.get("time_semantic") or "pi_hour_label_30min"),
            day_boundary=str(avg_cfg.get("day_boundary") or "07:30"),
        )

    # ------------------------------------------------------------
    # BPI Density - 新版 API_Config
    # ------------------------------------------------------------
    if key == "aoi_bpi_density":
        from models.piaoi.bpi_density.API_Config import API_Config as BPIApiConfig

        api_cfg = BPIApiConfig()
        avg_cfg = _get_density_average_config(api_cfg, "bpi_density_average")

        return DensityAvgConfig(
            system=key,
            db_name=api_cfg.bpi_density_db_name,
            main_table_tpl=_normalize_monthly_tpl(
                api_cfg.bpi_density_summary_table_tpl,
                "bpi_api_summary_yyyymm",
            ),
            time_col=str(avg_cfg.get("time_col") or "scan_hour"),
            avg_config=avg_cfg,
            group_keys=list(avg_cfg.get("group_keys") or ["glass_side", "model"]),
            metric_columns=list(avg_cfg.get("metric_columns") or []),
            source_columns=dict(avg_cfg.get("source_columns") or {}),
            filter_item_coldict=dict(avg_cfg.get("filter_item_coldict") or {}),
            cascade_order=list(avg_cfg.get("cascade_order") or []),
            table_columns=dict(avg_cfg.get("table_columns") or {}),
            download_columns=dict(avg_cfg.get("download_columns") or {}),
            recipe_defect_default_rules=list(avg_cfg.get("recipe_defect_default_rules") or []),
            denominator_identity_cols=list(avg_cfg.get("denominator_identity_cols") or []),
            summary_row_identity_cols=list(avg_cfg.get("summary_row_identity_cols") or []),
            metric_definition=dict(avg_cfg.get("metric_definition") or {}),
            summary_labels=dict(avg_cfg.get("summary_labels") or {}),
            time_semantic=str(avg_cfg.get("time_semantic") or "scan_hour"),
            day_boundary=str(avg_cfg.get("day_boundary") or "07:30"),
        )

    # ------------------------------------------------------------
    # BPI/API Same Point Average
    # ------------------------------------------------------------
    if key == "bpi_same_point":
        from models.piaoi.bpi_density.API_Config import API_Config as BPIApiConfig

        api_cfg = BPIApiConfig()
        avg_cfg = _get_density_average_config(api_cfg, "bpi_same_point_average")

        logger.info(
            "[density_avg] same_point cfg db=%s tpl=%s avg_cfg_keys=%s",
            api_cfg.bpi_same_point_db_name,
            api_cfg.bpi_same_point_offset_table_tpl,
            list(avg_cfg.keys()),
        )
        
        return DensityAvgConfig(
            system=key,
            db_name=api_cfg.bpi_same_point_db_name,
            main_table_tpl=_normalize_monthly_tpl(
                api_cfg.bpi_same_point_offset_table_tpl,
                "bpi_same_point_offset_summary_yyyymm",
            ),
            time_col=str(avg_cfg.get("time_col") or "scan_hour"),
            avg_config=avg_cfg,
            group_keys=list(avg_cfg.get("group_keys") or ["glass_side", "model", "offset_um"]),
            metric_columns=list(avg_cfg.get("metric_columns") or []),
            source_columns=dict(avg_cfg.get("source_columns") or {}),
            filter_item_coldict=dict(avg_cfg.get("filter_item_coldict") or {}),
            cascade_order=list(avg_cfg.get("cascade_order") or []),
            table_columns=dict(avg_cfg.get("table_columns") or {}),
            download_columns=dict(avg_cfg.get("download_columns") or {}),
            recipe_defect_default_rules=list(avg_cfg.get("recipe_defect_default_rules") or []),
            denominator_identity_cols=list(avg_cfg.get("denominator_identity_cols") or []),
            summary_row_identity_cols=list(avg_cfg.get("summary_row_identity_cols") or []),
            metric_definition=dict(avg_cfg.get("metric_definition") or {}),
            summary_labels=dict(avg_cfg.get("summary_labels") or {}),
            time_semantic=str(avg_cfg.get("time_semantic") or "scan_hour"),
            day_boundary=str(avg_cfg.get("day_boundary") or "07:30"),
        )

    # ------------------------------------------------------------
    # Inspection Density
    # ------------------------------------------------------------
    if key == "aoi_inspection_density":
        from models.inspection_density.API_Config import InspectionDensityApiConfig

        api_cfg = InspectionDensityApiConfig()
        avg_cfg = _get_density_average_config(api_cfg, "density_average")

        db_name = (
            getattr(api_cfg, "db_name", None)
            or getattr(api_cfg, "out_db", None)
            or getattr(getattr(api_cfg, "core_cfg", None), "TARGET_DB", None)
            or "piaoi_inspection_density"
        )

        table_tpl = (
            getattr(api_cfg, "api_summary_table_tpl", None)
            or getattr(api_cfg, "summary_table_tpl", None)
            or getattr(api_cfg, "out_table_tpl", None)
            or "inspection_api_summary_yyyymm"
        )

        return DensityAvgConfig(
            system=key,
            db_name=db_name,
            main_table_tpl=_normalize_monthly_tpl(table_tpl, "inspection_api_summary_yyyymm"),
            time_col=str(avg_cfg.get("time_col") or "pi_hour"),
            avg_config=avg_cfg,
            group_keys=list(avg_cfg.get("group_keys") or ["line_id", "glass_type", "model"]),
            metric_columns=list(avg_cfg.get("metric_columns") or []),
            source_columns=dict(avg_cfg.get("source_columns") or {}),
            filter_item_coldict=dict(avg_cfg.get("filter_item_coldict") or {}),
            cascade_order=list(avg_cfg.get("cascade_order") or []),
            table_columns=dict(avg_cfg.get("table_columns") or {}),
            download_columns=dict(avg_cfg.get("download_columns") or {}),
            recipe_defect_default_rules=list(avg_cfg.get("recipe_defect_default_rules") or []),
            denominator_identity_cols=list(avg_cfg.get("denominator_identity_cols") or []),
            summary_row_identity_cols=list(avg_cfg.get("summary_row_identity_cols") or []),
            metric_definition=dict(avg_cfg.get("metric_definition") or {}),
            summary_labels=dict(avg_cfg.get("summary_labels") or {}),
            time_semantic=str(avg_cfg.get("time_semantic") or "pi_hour_label_30min"),
            day_boundary=str(avg_cfg.get("day_boundary") or "07:30"),
        )

    raise HTTPException(status_code=400, detail=f"unknown system: {system}")


# =============================================================================
# Time helpers
# =============================================================================
def _parse_date_only(s: str) -> datetime:
    s = str(s or "").strip().replace("T", " ")

    for fmt in ("%Y-%m-%d", "%y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
        except ValueError:
            continue

    raise ValueError(f"Bad date: {s}")


def _to_actual_query_range(start_date: str, end_date: str) -> Tuple[datetime, datetime]:
    """
    使用者日期語意：
      D = [D 07:30, D+1 07:30)

    若 start > end，自動交換。
    """
    st = _parse_date_only(start_date)
    ed = _parse_date_only(end_date)

    if ed < st:
        st, ed = ed, st

    start = st.replace(hour=SHIFT_HOUR, minute=SHIFT_MINUTE, second=0, microsecond=0)
    end_exclusive = (ed + timedelta(days=1)).replace(
        hour=SHIFT_HOUR,
        minute=SHIFT_MINUTE,
        second=0,
        microsecond=0,
    )

    return start, end_exclusive


def _time_col_query_range(cfg: DensityAvgConfig, actual_start: datetime, actual_end: datetime) -> Tuple[datetime, datetime]:
    sem = str(cfg.time_semantic or "").lower()

    if "label_30min" in sem or "30min" in sem:
        return actual_start - LABEL_30MIN_DELTA, actual_end - LABEL_30MIN_DELTA

    return actual_start, actual_end


def _actual_hour_from_stored_time(cfg: DensityAvgConfig, s: pd.Series) -> pd.Series:
    t = pd.to_datetime(s, errors="coerce")
    sem = str(cfg.time_semantic or "").lower()

    if "label_30min" in sem or "30min" in sem:
        return t + pd.to_timedelta(30, unit="m")

    return t


def _business_day_from_actual_hour(actual_hour: pd.Series) -> pd.Series:
    t = pd.to_datetime(actual_hour, errors="coerce")
    return (t - pd.to_timedelta(SHIFT_HOUR * 60 + SHIFT_MINUTE, unit="m")).dt.date


def _iter_yyyymm_from_time_range(q_start: datetime, q_end: datetime) -> List[str]:
    if q_end <= q_start:
        return []

    q_end_incl = q_end - timedelta(seconds=1)

    cur = datetime(q_start.year, q_start.month, 1)
    end_m = datetime(q_end_incl.year, q_end_incl.month, 1)

    out: List[str] = []

    while cur <= end_m:
        out.append(cur.strftime("%Y%m"))

        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)

    return out


# =============================================================================
# DB read
# =============================================================================
def _read_monthly_source_rows(
    *,
    cfg: DensityAvgConfig,
    actual_start: datetime,
    actual_end: datetime,
) -> Tuple[pd.DataFrame, List[str]]:
    db = MySQLConnet(cfg.db_name)

    q_start, q_end = _time_col_query_range(cfg, actual_start, actual_end)
    months = _iter_yyyymm_from_time_range(q_start, q_end)

    frames: List[pd.DataFrame] = []
    missing_tables: List[str] = []

    for ym in months:
        table_name = cfg.main_table_tpl.replace("yyyymm", ym).lower()
        
        if not db.table_exists(table_name):
            missing_tables.append(table_name)
            continue

        sql = f"""
            SELECT *
            FROM `{db.db}`.`{table_name}`
            WHERE `{cfg.time_col}` >= :q_start
              AND `{cfg.time_col}` <  :q_end
        """

        params = {
            "q_start": q_start,
            "q_end": q_end,
        }

        part = db.query_df(sql, params)
        logger.info("[density_avg] read sql tbn=%s, rows=%s", table_name, len(part) )
        if part is not None and not part.empty:
            part["_source_table"] = table_name
            frames.append(part)

    if not frames:
        return pd.DataFrame(), missing_tables

    out = pd.concat(frames, ignore_index=True)
    return out, missing_tables


# =============================================================================
# Source normalization
# =============================================================================
def _first_existing_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _normalize_source_df(df: pd.DataFrame, cfg: DensityAvgConfig) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()
    sc = cfg.source_columns or {}

    # ------------------------------------------------------------
    # Ensure configured alias columns
    # ------------------------------------------------------------
    for canonical, source in sc.items():
        canonical = str(canonical or "").strip()
        source = str(source or "").strip()

        if not canonical or not source:
            continue

        if source == "__row_count__":
            continue

        if canonical not in out.columns and source in out.columns:
            out[canonical] = out[source]
    # ------------------------------------------------------------
    # total_glass_cnt
    # ------------------------------------------------------------
    total_src = sc.get("total_glass_cnt") or ""

    if total_src == "__row_count__":
        out["total_glass_cnt"] = 1
    elif total_src and total_src in out.columns:
        out["total_glass_cnt"] = out[total_src]
    else:
        c = _first_existing_col(
            out,
            [
                "total_glass_cnt",
                "tab_total_glass_cnt",
                "recipe_total_glass_cnt",
                "glass_count",
                "maingroup_glass_count",
                "glass_cnt",
            ],
        )
        out["total_glass_cnt"] = out[c] if c else 0

    # ------------------------------------------------------------
    # defect_cnt
    # ------------------------------------------------------------
    defect_src = sc.get("defect_cnt") or ""

    if defect_src and defect_src in out.columns:
        out["defect_cnt"] = out[defect_src]
    else:
        c = _first_existing_col(
            out,
            [
                "defect_cnt",
                "matched_pair_count",
                "total_defect_count",
                "maingroup_defect_count",
                "total_def",
                "def_cnt",
            ],
        )
        out["defect_cnt"] = out[c] if c else 0

    # ------------------------------------------------------------
    # size counts
    # ------------------------------------------------------------
    size_defaults = {
        "small_defect_count": ["small_defect_count", "matched_s_count", "S"],
        "middle_defect_count": ["middle_defect_count", "matched_m_count", "M"],
        "large_defect_count": ["large_defect_count", "matched_l_count", "L"],
        "over_defect_count": ["over_defect_count", "matched_o_count", "O"],
    }

    for dst, candidates in size_defaults.items():
        src = sc.get(dst) or ""
        if src and src in out.columns:
            out[dst] = out[src]
        elif dst not in out.columns:
            c = _first_existing_col(out, candidates)
            out[dst] = out[c] if c else 0

    # ------------------------------------------------------------
    # numeric cleanup
    # ------------------------------------------------------------
    num_cols = [
        "total_glass_cnt",
        "defect_cnt",
        "small_defect_count",
        "middle_defect_count",
        "large_defect_count",
        "over_defect_count",
    ]

    for c in num_cols:
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)

    # ------------------------------------------------------------
    # time
    # ------------------------------------------------------------
    if cfg.time_col not in out.columns:
        raise HTTPException(
            status_code=500,
            detail=f"time_col `{cfg.time_col}` not found in source table",
        )

    out["__stored_time"] = pd.to_datetime(out[cfg.time_col], errors="coerce")
    out = out.dropna(subset=["__stored_time"]).copy()

    out["__actual_hour"] = _actual_hour_from_stored_time(cfg, out["__stored_time"])
    out["__business_day"] = _business_day_from_actual_hour(out["__actual_hour"])
    out["__hour_key"] = pd.to_datetime(out["__actual_hour"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")

    # ------------------------------------------------------------
    # common string cleanup
    # ------------------------------------------------------------
    possible_str_cols = set(cfg.group_keys or [])
    possible_str_cols.update(cfg.cascade_order or [])

    for item in (cfg.filter_item_coldict or {}).values():
        if isinstance(item, dict) and item.get("key"):
            possible_str_cols.add(str(item.get("key")))

    for c in possible_str_cols:
        if c in out.columns:
            out[c] = out[c].astype("string").fillna("").astype(str).str.strip()

    return out.reset_index(drop=True)


# =============================================================================
# Filters / Cascade
# =============================================================================
def _normalize_size_group_name(v: Any) -> str:
    s = str(v or "").upper().strip()
    return SIZE_GROUP_ALIASES.get(s, s)


def _size_group_to_atoms(v: Any) -> List[str]:
    g = _normalize_size_group_name(v)
    atoms = SIZE_GROUP_ATOMS.get(g, set())

    order = {s: i for i, s in enumerate(VALID_SIZE_ATOMS)}
    return sorted(atoms, key=lambda s: order[s])


def _normalize_size_groups(filters: Dict[str, List[str]]) -> List[str]:
    arr = filters.get("defect_size") or []
    out = []

    for x in arr:
        sx = _normalize_size_group_name(x)
        if sx in SIZE_GROUP_OPTIONS:
            out.append(sx)

    return sorted(set(out), key=lambda x: SIZE_GROUP_OPTIONS.index(x))


def _selected_size_atoms(filters: Dict[str, List[str]]) -> List[str]:
    groups = _normalize_size_groups(filters)

    atoms = []
    for g in groups:
        atoms.extend(_size_group_to_atoms(g))

    order = {s: i for i, s in enumerate(VALID_SIZE_ATOMS)}
    return sorted(set(atoms), key=lambda s: order[s])


def _clean_filter_values(v: Any) -> List[str]:
    if not isinstance(v, list):
        return []

    out = []
    for x in v:
        sx = str(x).strip()
        if sx:
            out.append(sx)

    return out


def _normalize_filters(filters: Any) -> Dict[str, List[str]]:
    if not isinstance(filters, dict):
        return {}

    out: Dict[str, List[str]] = {}

    for k, v in filters.items():
        arr = _clean_filter_values(v)
        if arr:
            out[str(k)] = arr

    return out


def _filter_keys_from_config(cfg: DensityAvgConfig) -> List[str]:
    keys: List[str] = []

    for item in (cfg.filter_item_coldict or {}).values():
        if not isinstance(item, dict):
            continue

        k = str(item.get("key") or "").strip()
        if not k or k == "date":
            continue

        if k not in keys:
            keys.append(k)

    return keys


def _apply_filters(
    df: pd.DataFrame,
    filters: Dict[str, List[str]],
    *,
    exclude_keys: Optional[List[str]] = None,
    ignore_missing: bool = True,
) -> pd.DataFrame:
    if df is None or df.empty:
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()

    if not filters:
        return df.copy()

    exclude = set(exclude_keys or [])
    out = df.copy()

    for k, arr in filters.items():
        if k in exclude:
            continue

        if not arr:
            continue

        if k not in out.columns:
            if ignore_missing:
                continue
            return out.iloc[0:0].copy()

        want = set(str(x).strip() for x in arr if str(x).strip())
        if not want:
            continue

        out = out[out[k].astype(str).isin(want)].copy()

    return out


def _apply_size_to_numerator(df: pd.DataFrame, selected_size_atoms: List[str]) -> pd.DataFrame:
    if df is None or df.empty:
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()

    out = df.copy()

    if not selected_size_atoms:
        out["__selected_defect_cnt"] = pd.to_numeric(out["defect_cnt"], errors="coerce").fillna(0)
        return out

    size_to_col = {
        "S": "small_defect_count",
        "M": "middle_defect_count",
        "L": "large_defect_count",
        "O": "over_defect_count",
    }

    cols = [size_to_col[s] for s in selected_size_atoms if s in size_to_col]

    if not cols:
        out["__selected_defect_cnt"] = pd.to_numeric(out["defect_cnt"], errors="coerce").fillna(0)
        return out

    total = None

    for c in cols:
        if c not in out.columns:
            out[c] = 0

        v = pd.to_numeric(out[c], errors="coerce").fillna(0)
        total = v if total is None else total + v

    out["__selected_defect_cnt"] = total if total is not None else 0
    return out


def _expand_rows_by_size_group(df: pd.DataFrame, filters: Dict[str, List[str]]) -> pd.DataFrame:
    """
    將每筆 summary row 展開成 SIZE_GROUP rows。

    total_glass_cnt 不變。
    defect_cnt 改為該 SIZE_GROUP 對應的 defect count。
    """
    if df is None or df.empty:
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()

    selected_groups = _normalize_size_groups(filters)
    groups = selected_groups if selected_groups else SIZE_GROUP_OPTIONS[:]

    rows = []

    size_col_map = {
        "S": "small_defect_count",
        "M": "middle_defect_count",
        "L": "large_defect_count",
        "O": "over_defect_count",
    }

    for _, r in df.iterrows():
        base = r.to_dict()

        for g in groups:
            atoms = _size_group_to_atoms(g)

            cnt = 0
            for atom in atoms:
                col = size_col_map.get(atom)
                if col:
                    cnt += int(float(r.get(col, 0) or 0))

            x = dict(base)
            x["defect_size"] = g
            x["defect_cnt"] = cnt
            rows.append(x)

    return pd.DataFrame(rows)


def _build_filter_options(
    df: pd.DataFrame,
    cfg: DensityAvgConfig,
    filters: Dict[str, List[str]],
) -> Dict[str, List[str]]:
    option_dict: Dict[str, List[str]] = {}

    filter_keys = _filter_keys_from_config(cfg)
    order = cfg.cascade_order or filter_keys

    for k in filter_keys:
        if k not in order:
            order.append(k)

    key_to_cfg: Dict[str, Dict[str, Any]] = {}

    for item in (cfg.filter_item_coldict or {}).values():
        if isinstance(item, dict) and item.get("key"):
            key_to_cfg[str(item.get("key"))] = item

    if df is None or df.empty:
        for k in filter_keys:
            item_cfg = key_to_cfg.get(k, {})
            vals = item_cfg.get("values", [])
            if isinstance(vals, list) and vals:
                option_dict[k] = [str(x) for x in vals]
            elif k == "defect_size":
                option_dict[k] = SIZE_GROUP_OPTIONS[:]
            else:
                option_dict[k] = []
        return option_dict

    for k in filter_keys:
        item_cfg = key_to_cfg.get(k, {})

        if k == "defect_size":
            vals = item_cfg.get("values", [])
            option_dict[k] = [str(x) for x in vals] if isinstance(vals, list) and vals else SIZE_GROUP_OPTIONS[:]
            continue

        if k not in df.columns:
            option_dict[k] = []
            continue

        prior_keys = []
        if k in order:
            prior_keys = order[:order.index(k)]

        prior_filters = {
            kk: vv
            for kk, vv in filters.items()
            if kk in prior_keys
        }

        sub = _apply_filters(df, prior_filters, exclude_keys=[], ignore_missing=True)

        vals = (
            sub[k]
            .astype("string")
            .fillna("")
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )

        vals = sorted([v for v in vals if v and v.lower() not in ("nan", "none", "null")])

        cfg_vals = item_cfg.get("values", [])
        if isinstance(cfg_vals, list) and cfg_vals:
            cfg_set = set(str(x).strip() for x in cfg_vals if str(x).strip())
            vals = [v for v in vals if v in cfg_set]

        option_dict[k] = vals

    return option_dict


def _recipe_default_suggestions(
    cfg: DensityAvgConfig,
    filters: Dict[str, List[str]],
    option_dict: Dict[str, List[str]],
) -> Dict[str, List[str]]:
    suggestions: Dict[str, List[str]] = {}

    rules = cfg.recipe_defect_default_rules or []

    if not rules:
        return suggestions

    for rule in rules:
        try:
            when = rule.get("when", {}) or {}
            field = str(when.get("field") or "").strip()
            pattern = str(when.get("pattern") or "").strip()
            set_part = rule.get("set", {}) or {}

            if not field or not pattern:
                continue

            selected = filters.get(field) or []
            if not selected:
                continue

            matched = any(re.match(pattern, str(v).strip()) for v in selected)
            if not matched:
                continue

            for target_key, vals in set_part.items():
                if target_key not in option_dict:
                    continue

                arr = [str(x).strip() for x in vals if str(x).strip()]
                if not arr:
                    continue

                opt_set = set(option_dict.get(target_key) or [])
                keep = [x for x in arr if x in opt_set]

                suggestions[target_key] = keep if keep else []
        except Exception:
            logger.exception("[density_avg] recipe default rule failed: %s", rule)

    return suggestions


# =============================================================================
# Aggregation
# =============================================================================
def _denominator_identity_cols(df: pd.DataFrame, cfg: DensityAvgConfig) -> List[str]:
    cols: List[str] = []

    for c in cfg.group_keys:
        if c in df.columns and c not in cols:
            cols.append(c)

    if "__hour_key" not in cols:
        cols.append("__hour_key")

    possible_identity = cfg.denominator_identity_cols or [
        "line_id",
        "aoi",
        "cassette_id",
        "recipe_id",
        "pi_type",
        "run_day",
        "offset_um",
    ]

    for c in possible_identity:
        if c in df.columns and c not in cols:
            cols.append(c)

    return cols


def _aggregate_density(df: pd.DataFrame, cfg: DensityAvgConfig, filters: Dict[str, List[str]]) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=(cfg.group_keys + cfg.metric_columns))

    if "defect_size" in (cfg.group_keys or []):
        df = _expand_rows_by_size_group(df, filters)
        filters = {
            k: v
            for k, v in (filters or {}).items()
            if k != "defect_size"
        }

    selected_size_atoms = _selected_size_atoms(filters)

    denom_filters = {
        k: v
        for k, v in filters.items()
        if k not in ("defect_size", "adc_def_code")
    }

    df_denom = _apply_filters(df, denom_filters, ignore_missing=True)

    df_num = _apply_filters(df, filters, exclude_keys=["defect_size"], ignore_missing=True)
    df_num = _apply_size_to_numerator(df_num, selected_size_atoms)

    group_keys = [c for c in cfg.group_keys if c in df.columns]

    if not group_keys:
        raise HTTPException(
            status_code=500,
            detail="density_average group_keys are empty or not found in source table",
        )

    if df_denom.empty:
        denom_out = pd.DataFrame(columns=group_keys + ["total_glass_cnt", "hour_count", "day_count"])
    else:
        denom_id_cols = _denominator_identity_cols(df_denom, cfg)

        denom_unit = (
            df_denom.groupby(denom_id_cols, dropna=False, as_index=False)
            .agg(total_glass_cnt=("total_glass_cnt", "max"))
        )

        hour_day_map = (
            df_denom[["__hour_key", "__business_day"]]
            .drop_duplicates()
            .copy()
        )

        denom_unit = denom_unit.merge(hour_day_map, on="__hour_key", how="left")

        denom_out = (
            denom_unit.groupby(group_keys, dropna=False, as_index=False)
            .agg(
                total_glass_cnt=("total_glass_cnt", "sum"),
                hour_count=("__hour_key", "nunique"),
                day_count=("__business_day", "nunique"),
            )
        )

    if df_num.empty:
        num_out = pd.DataFrame(columns=group_keys + ["defect_cnt"])
    else:
        num_out = (
            df_num.groupby(group_keys, dropna=False, as_index=False)
            .agg(defect_cnt=("__selected_defect_cnt", "sum"))
        )

    out = denom_out.merge(num_out, on=group_keys, how="left")

    out["defect_cnt"] = pd.to_numeric(out.get("defect_cnt", 0), errors="coerce").fillna(0)
    out["total_glass_cnt"] = pd.to_numeric(out.get("total_glass_cnt", 0), errors="coerce").fillna(0)

    den = out["total_glass_cnt"].replace(0, pd.NA)
    out["density"] = (out["defect_cnt"] / den).fillna(0).round(6)

    for c in ["defect_cnt", "total_glass_cnt", "hour_count", "day_count"]:
        if c not in out.columns:
            out[c] = 0
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)

    for c in ["defect_cnt", "total_glass_cnt", "hour_count", "day_count"]:
        out[c] = out[c].round(0).astype(int)

    ordered = []

    for c in cfg.group_keys:
        if c in out.columns and c not in ordered:
            ordered.append(c)

    for c in cfg.metric_columns:
        if c in out.columns and c not in ordered:
            ordered.append(c)

    for c in ["defect_cnt", "total_glass_cnt", "density", "day_count", "hour_count"]:
        if c in out.columns and c not in ordered:
            ordered.append(c)

    return out[ordered].copy()


# =============================================================================
# Output helpers
# =============================================================================
def _columns_from_config(cfg: DensityAvgConfig, *, for_download: bool) -> List[str]:
    d = cfg.download_columns if for_download else cfg.table_columns

    if isinstance(d, dict) and d:
        return list(d.keys())

    out = []

    for c in cfg.group_keys:
        if c not in out:
            out.append(c)

    for c in cfg.metric_columns:
        if c not in out:
            out.append(c)

    for c in ["defect_cnt", "total_glass_cnt", "density", "day_count", "hour_count"]:
        if c not in out:
            out.append(c)

    return out


def _apply_output_columns(df: pd.DataFrame, cfg: DensityAvgConfig, *, for_download: bool) -> pd.DataFrame:
    if df is None:
        df = pd.DataFrame()

    out = df.copy()
    cols = _columns_from_config(cfg, for_download=for_download)

    for c in cols:
        if c not in out.columns:
            out[c] = ""

    return out[cols].copy()


def _csv_filename(system: str, start_date: str, end_date: str) -> str:
    s = start_date.replace("-", "")
    e = end_date.replace("-", "")
    return f"{_normalize_system(system)}_density_avg_{s}_{e}.csv"


def _summary_rows_from_source(
    df: pd.DataFrame,
    cfg: DensityAvgConfig,
    filters: Dict[str, List[str]],
) -> Optional[int]:
    if df is None or df.empty:
        return 0

    cols = [c for c in (cfg.summary_row_identity_cols or []) if c in df.columns]

    if not cols:
        return None

    row_filters = {
        k: v
        for k, v in (filters or {}).items()
        if k not in ("defect_size", "adc_def_code")
    }
    sub = _apply_filters(df, row_filters, ignore_missing=True)

    if sub is None or sub.empty:
        return 0

    return int(sub[cols].drop_duplicates().shape[0])


def _summary_cards(
    df: pd.DataFrame,
    *,
    cfg: Optional[DensityAvgConfig] = None,
    source_df: Optional[pd.DataFrame] = None,
    filters: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    if df is None or df.empty:
        row_count = 0
        if cfg is not None and source_df is not None:
            row_count = _summary_rows_from_source(source_df, cfg, filters or {}) or 0

        return {
            "rows": row_count,
            "defect_cnt": 0,
            "total_glass_cnt": 0,
            "density": 0,
            "day_count": 0,
            "hour_count": 0,
        }

    defect = int(pd.to_numeric(df.get("defect_cnt", 0), errors="coerce").fillna(0).sum())
    glass = int(pd.to_numeric(df.get("total_glass_cnt", 0), errors="coerce").fillna(0).sum())
    density = round(defect / glass, 6) if glass else 0

    day_count = int(pd.to_numeric(df.get("day_count", 0), errors="coerce").fillna(0).max()) if "day_count" in df.columns else 0
    hour_count = int(pd.to_numeric(df.get("hour_count", 0), errors="coerce").fillna(0).max()) if "hour_count" in df.columns else 0
    row_count = int(len(df))

    if cfg is not None and source_df is not None:
        row_count = _summary_rows_from_source(source_df, cfg, filters or {}) or row_count

    return {
        "rows": row_count,
        "defect_cnt": defect,
        "total_glass_cnt": glass,
        "density": density,
        "day_count": day_count,
        "hour_count": hour_count,
    }


# =============================================================================
# Core read / calculate
# =============================================================================
def _read_and_prepare(req: DensityAvgRequest) -> Tuple[DensityAvgConfig, pd.DataFrame, Dict[str, List[str]], List[str], Dict[str, Any]]:
    cfg = _resolve_avg_config(req.system)
    filters = _normalize_filters(req.filters)

    actual_start, actual_end = _to_actual_query_range(req.start_date, req.end_date)
    q_start, q_end = _time_col_query_range(cfg, actual_start, actual_end)

    raw_df, missing_tables = _read_monthly_source_rows(
        cfg=cfg,
        actual_start=actual_start,
        actual_end=actual_end,
    )

    df = _normalize_source_df(raw_df, cfg) if raw_df is not None and not raw_df.empty else pd.DataFrame()

    meta = {
        "system": cfg.system,
        "db_name": cfg.db_name,
        "main_table_tpl": cfg.main_table_tpl,
        "time_col": cfg.time_col,
        "time_semantic": cfg.time_semantic,
        "day_boundary": cfg.day_boundary,
        "actual_start": actual_start.strftime("%Y-%m-%d %H:%M:%S"),
        "actual_end_exclusive": actual_end.strftime("%Y-%m-%d %H:%M:%S"),
        "query_start": q_start.strftime("%Y-%m-%d %H:%M:%S"),
        "query_end_exclusive": q_end.strftime("%Y-%m-%d %H:%M:%S"),
        "missing_tables": missing_tables,
        "rows_source": int(len(raw_df)) if raw_df is not None else 0,
        "rows_normalized": int(len(df)) if df is not None else 0,
        "group_keys": cfg.group_keys,
        "metric_columns": cfg.metric_columns,
    }

    return cfg, df, filters, missing_tables, meta


# =============================================================================
# APIs
# =============================================================================
@router.post("/options")
async def density_avg_options(req: DensityAvgRequest):
    try:
        cfg, df, filters, missing_tables, meta = _read_and_prepare(req)

        option_dict = _build_filter_options(df, cfg, filters)
        suggested = _recipe_default_suggestions(cfg, filters, option_dict)

        return {
            "ok": True,
            "system": cfg.system,
            "filterOptionDict": option_dict,
            "suggestedFilters": suggested,
            "Config": {
                "group_keys": cfg.group_keys,
                "metric_columns": cfg.metric_columns,
                "filter_item_coldict": cfg.filter_item_coldict,
                "cascade_order": cfg.cascade_order,
                "table_columns": cfg.table_columns,
                "download_columns": cfg.download_columns,
                "recipe_defect_default_rules": cfg.recipe_defect_default_rules,
                "denominator_identity_cols": cfg.denominator_identity_cols,
                "summary_row_identity_cols": cfg.summary_row_identity_cols,
                "metric_definition": cfg.metric_definition,
                "summary_labels": cfg.summary_labels,
            },
            "Meta": meta,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[density_avg/options] failed")
        raise HTTPException(status_code=500, detail=f"options failed: {repr(e)}")


@router.post("/preview")
async def preview_density_avg(req: DensityAvgRequest):
    try:
        cfg, df, filters, missing_tables, meta = _read_and_prepare(req)

        option_dict = _build_filter_options(df, cfg, filters)
        suggested = _recipe_default_suggestions(cfg, filters, option_dict)

        result_df = _aggregate_density(df, cfg, filters) if df is not None and not df.empty else pd.DataFrame()
        total_count = int(len(result_df))

        limit = req.limit
        if limit is not None:
            preview_df = result_df.head(int(limit)).copy()
        else:
            preview_df = result_df.copy()

        preview_df = _apply_output_columns(preview_df, cfg, for_download=False)
        preview_df = preview_df.fillna("")

        return {
            "ok": True,
            "system": cfg.system,
            "columns": preview_df.columns.tolist(),
            "rows": preview_df.to_dict(orient="records"),
            "preview_count": int(len(preview_df)),
            "total_count": total_count,
            "count": int(len(preview_df)),
            "summary": _summary_cards(result_df, cfg=cfg, source_df=df, filters=filters),
            "filterOptionDict": option_dict,
            "suggestedFilters": suggested,
            "metric_definition": cfg.metric_definition or {
                "density": "sum(defect_cnt) / sum(total_glass_cnt)",
                "day_boundary": "07:30~next day 07:30",
                "denominator_policy": "defect_size and adc_def_code do not shrink total_glass_cnt",
            },
            "Meta": {
                **meta,
                "filters": filters,
                "selected_size_groups": _normalize_size_groups(filters),
                "selected_size_atoms": _selected_size_atoms(filters),
                "rows_result": total_count,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[density_avg/preview] failed")
        raise HTTPException(status_code=500, detail=f"preview failed: {repr(e)}")


@router.post("/download")
async def download_density_avg(req: DensityAvgRequest):
    try:
        cfg, df, filters, missing_tables, meta = _read_and_prepare(req)
        result_df = _aggregate_density(df, cfg, filters) if df is not None and not df.empty else pd.DataFrame()

        out_df = _apply_output_columns(result_df, cfg, for_download=True)
        out_df = out_df.fillna("")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[density_avg/download] failed")
        raise HTTPException(status_code=500, detail=f"download failed: {repr(e)}")

    csv_bytes = out_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    mem = io.BytesIO(csv_bytes)
    mem.seek(0)

    filename = _csv_filename(cfg.system, req.start_date, req.end_date)

    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{filename}"
    }

    return StreamingResponse(
        mem,
        media_type="text/csv; charset=utf-8",
        headers=headers,
    )
