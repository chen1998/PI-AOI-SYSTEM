
# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, Body
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timedelta
import json
import logging

import pandas as pd
from sqlalchemy import text

try:
    from PI_SYSTEM.models.inspection_density.sql_db_connect2 import MySQLConnetFunc as _DBHandler
except Exception:
    try:
        from models.inspection_density.sql_db_connect2 import MySQLConnetFunc as _DBHandler
    except Exception:
        from models.sql_db_connect import MySQLConnet as _DBHandler

from models.inspection_density.API_Config import CFG

logger = logging.getLogger("aoi_inspection_density_trend")
router = APIRouter(tags=["duty_cell_piaoi_aoi_inspeciton"])

# ============================================================
# Constants
# ============================================================
VALID_SIZES = CFG.uni_defect_sizes[:] if getattr(CFG, "uni_defect_sizes", None) else ["S", "M", "L", "O"]
FILTER_KEYS = ["line_id", "model", "glass_type", "defect_size"]

# inspection_api_summary_yyyymm 的 group 粒度
GROUP_KEYS = ["pi_hour", "line_id", "model", "glass_type"]

MONTH_TOKEN_PREFIX = "M"  # MYYMM

SHIFT_HOUR = CFG.core_cfg.SHIFT_DAY_START_HOUR
SHIFT_MIN = CFG.core_cfg.SHIFT_DAY_START_MINUTE
SHIFT_DELTA = timedelta(hours=SHIFT_HOUR, minutes=SHIFT_MIN)

LABEL_OFFSET_MIN = CFG.core_cfg.SHIFT_BUCKET_OFFSET_MINUTES
LABEL_DELTA = timedelta(minutes=LABEL_OFFSET_MIN)

VALID_TARGETS = {"summary", "month", "week", "day"}

DEFAULT_TREND_FILTERS: Dict[str, List[str]] = {
    "glass_type": ["TFT"],
    "defect_size": ["M", "L", "O"],
}


# ============================================================
# Basic helpers
# ============================================================
def _now_floor_hour() -> datetime:
    n = datetime.now()
    return n.replace(minute=0, second=0, microsecond=0)


def _cap_end_to_now_hour(d_end_excl: datetime) -> datetime:
    cap = _now_floor_hour()
    return d_end_excl if d_end_excl <= cap else cap


def _cap_range_to_now_hour(d_start: datetime, d_end_excl: datetime) -> Tuple[datetime, datetime]:
    d_end2 = _cap_end_to_now_hour(d_end_excl)
    if d_end2 != d_end_excl:
        logger.warning("[inspection_trend] end capped: %s -> %s", d_end_excl, d_end2)
    if d_start >= d_end2:
        return d_end2, d_end2
    return d_start, d_end2


def _parse_ymd(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def _shift_basis(dt: datetime) -> datetime:
    """
    inspection 的 pi_hour:
      pi_hour = floor(actual_scan_endtime - 30min, hour)

    真實 bucket start:
      bucket_start = pi_hour + 30min

    shift day boundary = 07:30
    所以 basis 可寫成：
      (pi_hour + 30m) - 07:30 = pi_hour - 07:00
    """
    return dt - timedelta(hours=7)


def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    if b == 0:
        return None
    return float(a) / float(b)


def _compact_for_log(d: Any, max_items: int = 8) -> Any:
    if isinstance(d, dict):
        return {k: _compact_for_log(v, max_items=max_items) for k, v in d.items()}
    if isinstance(d, list):
        if len(d) <= max_items:
            return d
        return d[:max_items] + ["..."]
    return d


# ============================================================
# Time token helpers
# ============================================================
def _month_token_from_ts(ts: pd.Timestamp) -> str:
    return f"{MONTH_TOKEN_PREFIX}{ts.strftime('%y%m')}"


def _month_token_from_yyyymm(yyyymm: str) -> str:
    s = str(yyyymm).strip()
    if len(s) != 6 or not s.isdigit():
        return ""
    yy = int(s[:4]) % 100
    mm = int(s[4:6])
    return f"{MONTH_TOKEN_PREFIX}{yy:02d}{mm:02d}"


def _week_label(year: int, week: int) -> str:
    return f"W{year % 100:02d}{week:02d}"


def _w_token_to_year_week(tok: str) -> Tuple[int, int]:
    s = str(tok).upper().strip()
    if not s.startswith("W"):
        raise ValueError(f"Invalid week token: {tok}")
    core = s[1:]
    if len(core) != 4 or not core.isdigit():
        raise ValueError(f"Invalid week token (expect WYYWW): {tok}")
    yy = int(core[:2])
    ww = int(core[2:])
    return 2000 + yy, ww


def _iso_monday(y: int, w: int) -> datetime:
    return datetime.fromisocalendar(y, w, 1).replace(hour=0, minute=0, second=0, microsecond=0)


# ============================================================
# Range builders
# ============================================================
def _ym_to_range_shift(ym_start: str, ym_end: str) -> Tuple[datetime, datetime]:
    ys = int(str(ym_start)[:4])
    ms = int(str(ym_start)[4:6])
    ye = int(str(ym_end)[:4])
    me = int(str(ym_end)[4:6])

    start = datetime(ys, ms, 1, SHIFT_HOUR, SHIFT_MIN, 0)

    if me == 12:
        end_excl = datetime(ye + 1, 1, 1, SHIFT_HOUR, SHIFT_MIN, 0)
    else:
        end_excl = datetime(ye, me + 1, 1, SHIFT_HOUR, SHIFT_MIN, 0)

    return _cap_range_to_now_hour(start, end_excl)


def _week_tokens_to_range_shift(w_start: str, w_end: str) -> Tuple[datetime, datetime]:
    y1, ws = _w_token_to_year_week(w_start)
    y2, we = _w_token_to_year_week(w_end)

    start_sun_00 = _iso_monday(y1, ws) - timedelta(days=1)
    end_sun_00 = (_iso_monday(y2, we) - timedelta(days=1)) + timedelta(days=7)

    start = start_sun_00.replace(hour=SHIFT_HOUR, minute=SHIFT_MIN, second=0, microsecond=0)
    end_excl = end_sun_00.replace(hour=SHIFT_HOUR, minute=SHIFT_MIN, second=0, microsecond=0)
    return _cap_range_to_now_hour(start, end_excl)


def _day_to_range_shift(d_start_str: str, d_end_str: str) -> Tuple[datetime, datetime]:
    ds = _parse_ymd(d_start_str).date()
    de = _parse_ymd(d_end_str).date()

    start = datetime(ds.year, ds.month, ds.day, SHIFT_HOUR, SHIFT_MIN, 0)
    end_excl = datetime(de.year, de.month, de.day, SHIFT_HOUR, SHIFT_MIN, 0) + timedelta(days=1)
    return _cap_range_to_now_hour(start, end_excl)


def _default_range_months_shift(n_months: int) -> Tuple[datetime, datetime]:
    now_h = _now_floor_hour()
    cur_m_start = datetime(now_h.year, now_h.month, 1, SHIFT_HOUR, SHIFT_MIN, 0)
    start_period = (pd.Timestamp(cur_m_start).to_period("M") - (n_months - 1)).to_timestamp()
    start = start_period.to_pydatetime().replace(hour=SHIFT_HOUR, minute=SHIFT_MIN, second=0, microsecond=0)
    end_excl = now_h
    return _cap_range_to_now_hour(start, end_excl)


def _default_range_weeks_shift(n_weeks: int) -> Tuple[datetime, datetime]:
    now_h = _now_floor_hour()
    b = now_h - SHIFT_DELTA

    s = b.replace(hour=0, minute=0, second=0, microsecond=0)
    dow = s.weekday()
    sun_offset = (dow + 1) % 7
    this_sun_00 = s - timedelta(days=sun_offset)

    start_sun_00 = this_sun_00 - timedelta(days=7 * (n_weeks - 1))
    start = start_sun_00 + SHIFT_DELTA

    end_excl = now_h
    return _cap_range_to_now_hour(start, end_excl)


def _default_range_days_shift(n_days: int) -> Tuple[datetime, datetime]:
    now_h = _now_floor_hour()
    end_label = (now_h - SHIFT_DELTA).date()
    start_label = end_label - timedelta(days=(n_days - 1))

    start = datetime(start_label.year, start_label.month, start_label.day, SHIFT_HOUR, SHIFT_MIN, 0)
    end_excl = now_h
    return _cap_range_to_now_hour(start, end_excl)


def _parse_date_block(block: Any, *, is_summary: bool) -> Dict[str, Tuple[datetime, datetime]]:
    if not isinstance(block, dict):
        block = {}

    def_m = 6 if is_summary else 7
    def_w = 9 if is_summary else 7
    def_d = 6 if is_summary else 7

    out: Dict[str, Tuple[datetime, datetime]] = {}

    m = block.get("month", [])
    if isinstance(m, list) and len(m) == 2 and m[0] and m[1]:
        out["month"] = _ym_to_range_shift(str(m[0]), str(m[1]))
    else:
        out["month"] = _default_range_months_shift(def_m)

    w = block.get("week", [])
    if isinstance(w, list) and len(w) == 2 and w[0] and w[1]:
        out["week"] = _week_tokens_to_range_shift(str(w[0]), str(w[1]))
    else:
        out["week"] = _default_range_weeks_shift(def_w)

    d = block.get("day", [])
    if isinstance(d, list) and len(d) == 2 and d[0] and d[1]:
        out["day"] = _day_to_range_shift(str(d[0]), str(d[1]))
    else:
        out["day"] = _default_range_days_shift(def_d)

    return out


def _extract_blocks(date_dict: Any) -> Tuple[dict, dict]:
    if not isinstance(date_dict, dict):
        return {}, {"month": [], "week": [], "day": []}

    summary_block = date_dict.get("summary", {})
    if not isinstance(summary_block, dict):
        summary_block = {}

    normal_block = {
        "month": date_dict.get("month", []),
        "week": date_dict.get("week", []),
        "day": date_dict.get("day", []),
    }
    return summary_block, normal_block


def _pick_ranges_for_target(date_dict: Any, target: str) -> Tuple[Dict[str, Tuple[datetime, datetime]], Dict[str, Any]]:
    summary_block, normal_block = _extract_blocks(date_dict)

    if target == "summary":
        sr = _parse_date_block(summary_block, is_summary=True)
        ranges = sr
    elif target == "month":
        nr = _parse_date_block(normal_block, is_summary=False)
        ranges = {"month": nr["month"]}
    elif target == "week":
        nr = _parse_date_block(normal_block, is_summary=False)
        ranges = {"week": nr["week"]}
    elif target == "day":
        nr = _parse_date_block(normal_block, is_summary=False)
        ranges = {"day": nr["day"]}
    else:
        sr = _parse_date_block(summary_block, is_summary=True)
        nr = _parse_date_block(normal_block, is_summary=False)
        ranges = {"summary": sr, "normal": nr}

    def _fmt(r: Tuple[datetime, datetime]) -> List[str]:
        return [r[0].strftime("%Y-%m-%d %H:%M:%S"), r[1].strftime("%Y-%m-%d %H:%M:%S")]

    if target in ("month", "week", "day"):
        meta_ranges = {target: _fmt(ranges[target])}
    elif target == "summary":
        meta_ranges = {k: _fmt(v) for k, v in ranges.items()}
    else:
        meta_ranges = {
            "normal": {k: _fmt(v) for k, v in ranges["normal"].items()},
            "summary": {k: _fmt(v) for k, v in ranges["summary"].items()},
        }

    return ranges, meta_ranges


def _minmax_from_ranges_nested(ranges_any: Any) -> Tuple[datetime, datetime]:
    rs: List[Tuple[datetime, datetime]] = []

    def _collect(x: Any):
        if isinstance(x, dict):
            for v in x.values():
                _collect(v)
        elif (
            isinstance(x, tuple)
            and len(x) == 2
            and isinstance(x[0], datetime)
            and isinstance(x[1], datetime)
        ):
            rs.append(x)

    _collect(ranges_any)

    if not rs:
        nowh = _now_floor_hour()
        return nowh, nowh

    d_min = min(r[0] for r in rs)
    d_max = max(r[1] for r in rs)
    return d_min, d_max


# ============================================================
# Query months / DB fetch
# ============================================================
def _month_list_between(d_min: datetime, d_max_excl: datetime) -> List[str]:
    if d_max_excl <= d_min:
        return []

    q_min = d_min - LABEL_DELTA
    q_max_excl = d_max_excl - LABEL_DELTA

    if q_max_excl <= q_min:
        return []

    q_max_incl = q_max_excl - timedelta(seconds=1)
    start = pd.Timestamp(q_min).to_period("M")
    end = pd.Timestamp(q_max_incl).to_period("M")
    periods = pd.period_range(start, end, freq="M")
    return [p.strftime("%Y%m") for p in periods]


def _is_table_missing_error(e: Exception) -> bool:
    msg = str(e).lower()
    return ("doesn't exist" in msg) or ("unknown table" in msg) or ("1146" in msg)


def _fetch_inspection_rows(dbhandler: _DBHandler, d_min: datetime, d_max_excl: datetime) -> Tuple[pd.DataFrame, List[str]]:
    ym_list = _month_list_between(d_min, d_max_excl)

    q_min = d_min - LABEL_DELTA
    q_max = d_max_excl - LABEL_DELTA
    """
    cols = [
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
    """

    cols = [
        "pi_hour",
        "line_id",
        "model",
        "glass_type",
        "maingroup_glass_count",
        "maingroup_defect_count",
        "defect_code_glass_count",
        "small_defect_count",
        "middle_defect_count",
        "large_defect_count",
        "over_defect_count",
        #"glass",
        "glass_size_detail",
        
    ]

    dfs: List[pd.DataFrame] = []
    missing_tables: List[str] = []

    for ym in ym_list:
        tbn = CFG.api_summary_table_tpl.replace("yyyymm", ym)

        sql = text(f"""
            SELECT {",".join(cols)}
            FROM `{CFG.db_name}`.`{tbn}`
            WHERE `pi_hour` >= :q_min
              AND `pi_hour` < :q_max
              AND `glass_type` IN ('CF', 'TFT')
        """)

        try:
            with dbhandler.engine.begin() as conn:
                part = pd.read_sql(sql, conn, params={"q_min": q_min, "q_max": q_max})
        except Exception as e:
            if _is_table_missing_error(e):
                logger.warning("[inspection_trend] table missing: %s doesn't exist", tbn)
                missing_tables.append(tbn)
                continue

            logger.exception("[inspection_trend] read table failed: %s (skip).", tbn)
            continue

        if part is not None and not part.empty:
            dfs.append(part)

    if dfs:
        df = pd.concat(dfs, ignore_index=True)
    else:
        df = pd.DataFrame(columns=cols)

    if not df.empty:
        df["pi_hour"] = pd.to_datetime(df["pi_hour"], errors="coerce")

        for k in ["line_id", "model", "glass_type",  "glass_size_detail"]:
            if k in df.columns:
                df[k] = df[k].astype(str)

        num_cols = [
            "maingroup_glass_count",
            "maingroup_defect_count",
            "defect_code_glass_count",
            "small_defect_count",
            "middle_defect_count",
            "large_defect_count",
            "over_defect_count",
        ]
        for c in num_cols:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

    return df, missing_tables

# ============================================================
# Filters
# ============================================================
def _apply_common_filters(df: pd.DataFrame, filters: Dict[str, Any]) -> pd.DataFrame:
    if df.empty:
        return df
    if not isinstance(filters, dict):
        filters = {}

    df2 = df
    for k in ["line_id", "model", "glass_type"]:
        arr = filters.get(k)
        if isinstance(arr, list) and arr:
            want = set([str(x) for x in arr if x is not None and str(x) != ""])
            if want:
                df2 = df2[df2[k].astype(str).isin(want)]
    return df2


def _normalize_selected_sizes(filters: Dict[str, Any]) -> List[str]:
    arr = (filters or {}).get("defect_size")
    if not (isinstance(arr, list) and arr):
        return []

    sel = []
    for x in arr:
        sx = str(x).upper().strip()
        if sx in VALID_SIZES:
            sel.append(sx)

    order = {s: i for i, s in enumerate(VALID_SIZES)}
    sel = sorted(set(sel), key=lambda s: order[s])
    return sel


# ============================================================
# glass_size_detail parsing
#   inspection format:
#   [
#     {"glass_id":"xxx","S":0,"M":1,"L":0,"O":0,"def_count":1},
#     ...
#   ]
# ============================================================
def _parse_gsd_list(v: Any) -> List[Dict[str, Any]]:
    if isinstance(v, list):
        return [x for x in v if isinstance(x, dict)]

    if not v or not isinstance(v, str):
        return []

    try:
        obj = json.loads(v)
        if isinstance(obj, list):
            return [x for x in obj if isinstance(x, dict)]
    except Exception:
        pass
    return []


def _calc_num_from_glass_size_detail(df_num: pd.DataFrame, selected_sizes: List[str]) -> pd.DataFrame:
    if df_num is None or df_num.empty:
        out = (df_num.copy() if isinstance(df_num, pd.DataFrame) else pd.DataFrame())
        if out.empty:
            for c in ["select_def_cnt", "select_def_glass_cnt", "__gsd"]:
                out[c] = []
        else:
            out["select_def_cnt"] = 0
            out["select_def_glass_cnt"] = 0
            out["__gsd"] = None
        return out

    df = df_num.copy()
    if not selected_sizes:
        df["select_def_cnt"] = df["maingroup_defect_count"].astype(int)
        df["select_def_glass_cnt"] = df["defect_code_glass_count"].astype(int)
        return df
    
    df["__gsd"] = df["glass_size_detail"].apply(_parse_gsd_list)

    

    size_map = {
        "S": "small_defect_count",
        "M": "middle_defect_count",
        "L": "large_defect_count",
        "O": "over_defect_count",
    }
    cols = [size_map[s] for s in selected_sizes]

    def _fallback_row(r: pd.Series) -> Tuple[int, int]:
        sel_def = int(sum(int(r.get(c, 0) or 0) for c in cols))
        sel_glass = int(r.get("defect_code_glass_count", 0) or 0)
        return sel_def, sel_glass

    def _row_calc(r: pd.Series) -> Tuple[int, int]:
        gsd_list = r.get("__gsd", [])
        if not isinstance(gsd_list, list) or not gsd_list:
            return _fallback_row(r)

        hit_glass = 0
        sel_def = 0
        for stat in gsd_list:
            if not isinstance(stat, dict):
                continue
            per = 0
            for s in selected_sizes:
                per += int(stat.get(s, 0) or 0)
            if per > 0:
                hit_glass += 1
                sel_def += per

        return int(sel_def), int(hit_glass)

    tmp = df.apply(_row_calc, axis=1, result_type="expand")
    df["select_def_cnt"] = tmp[0].astype(int)
    df["select_def_glass_cnt"] = tmp[1].astype(int)
    return df


# ============================================================
# Tick builders
# ============================================================
def _mk_month_ticks(d_start: datetime, d_end_excl: datetime) -> List[str]:
    if d_end_excl <= d_start:
        return []
    b0 = _shift_basis(d_start - LABEL_DELTA)
    b1 = _shift_basis((d_end_excl - timedelta(seconds=1)) - LABEL_DELTA)
    start = pd.Timestamp(b0).to_period("M")
    end = pd.Timestamp(b1).to_period("M")
    periods = pd.period_range(start, end, freq="M")
    return [f"{MONTH_TOKEN_PREFIX}{p.strftime('%y%m')}" for p in periods]


def _mk_day_ticks(d_start: datetime, d_end_excl: datetime) -> List[str]:
    if d_end_excl <= d_start:
        return []
    b0 = _shift_basis(d_start - LABEL_DELTA)
    b1 = _shift_basis((d_end_excl - timedelta(seconds=1)) - LABEL_DELTA)
    start_d = b0.date()
    end_d = b1.date()
    days = (end_d - start_d).days

    out = []
    for i in range(days + 1):
        d = datetime(start_d.year, start_d.month, start_d.day) + timedelta(days=i)
        out.append("D" + d.strftime("%m%d"))
    return out


def _mk_week_ticks(d_start: datetime, d_end_excl: datetime) -> List[str]:
    if d_end_excl <= d_start:
        return []
    b_start = _shift_basis(d_start - LABEL_DELTA)
    b_end_incl = _shift_basis((d_end_excl - timedelta(seconds=1)) - LABEL_DELTA)

    s = b_start.replace(hour=0, minute=0, second=0, microsecond=0)
    dow = s.weekday()
    sun_offset = (dow + 1) % 7
    cur = s - timedelta(days=sun_offset)

    out = []
    while cur <= b_end_incl:
        monday = cur + timedelta(days=1)
        iso = monday.isocalendar()
        out.append(_week_label(int(iso.year), int(iso.week)))
        cur += timedelta(days=7)
    return out


# ============================================================
# Aggregation - TOTAL
# ============================================================
def _agg_total_by_x(df: pd.DataFrame, x_col: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["x", "glass_cnt", "defect_cnt"])

    # inspection 每列本來就是一個 main-group
    g = (
        df.groupby(GROUP_KEYS + [x_col], as_index=False)
        .agg(
            glass_cnt=("maingroup_glass_count", "max"),
            defect_cnt=("maingroup_defect_count", "max"),
        )
    )
    out = g.groupby(x_col, as_index=False).agg({"glass_cnt": "sum", "defect_cnt": "sum"})
    out = out.rename(columns={x_col: "x"})
    return out


# ============================================================
# Aggregation - SELECT
#   denominator: ignore defect_size
# ============================================================
def _agg_select_total_glass_by_x(df_denom: pd.DataFrame, x_col: str) -> pd.DataFrame:
    if df_denom.empty:
        return pd.DataFrame(columns=["x", "select_total_glass_cnt"])

    g = (
        df_denom.groupby(GROUP_KEYS + [x_col], as_index=False)
        .agg(select_total_glass_cnt=("maingroup_glass_count", "max"))
    )
    out = g.groupby(x_col, as_index=False).agg({"select_total_glass_cnt": "sum"})
    out = out.rename(columns={x_col: "x"})
    return out


def _union_def_glass_cnt_from_gsd_list(g: pd.DataFrame, selected_sizes: List[str]) -> Optional[int]:
    if g is None or g.empty:
        return 0

    if "__gsd" not in g.columns:
        return None

    any_gsd = False
    hit = set()

    for lst in g["__gsd"].tolist():
        if not isinstance(lst, list) or not lst:
            continue
        any_gsd = True

        for stat in lst:
            if not isinstance(stat, dict):
                continue

            gid = str(stat.get("glass_id", "") or "")
            if not gid:
                continue

            if selected_sizes:
                per = 0
                for s in selected_sizes:
                    per += int(stat.get(s, 0) or 0)
            else:
                per = (
                    int(stat.get("S", 0) or 0)
                    + int(stat.get("M", 0) or 0)
                    + int(stat.get("L", 0) or 0)
                    + int(stat.get("O", 0) or 0)
                )

            if per > 0:
                hit.add(gid)

    if not any_gsd:
        return None
    return int(len(hit))


def _agg_select_num_by_x(df_num_calc: pd.DataFrame, x_col: str, selected_sizes: List[str]) -> pd.DataFrame:
    if df_num_calc.empty:
        return pd.DataFrame(columns=["x", "select_def_glass_cnt", "select_def_cnt"])

    def _per_group_calc(g: pd.DataFrame) -> pd.Series:
        s_def = int(g["select_def_cnt"].max())
        u = _union_def_glass_cnt_from_gsd_list(g, selected_sizes)
        if u is None:
            s_glass = int(g["select_def_glass_cnt"].max())
        else:
            s_glass = int(u)
        return pd.Series({"select_def_glass_cnt": s_glass, "select_def_cnt": s_def})

    gg = (
        df_num_calc.groupby(GROUP_KEYS + [x_col], as_index=False)
        .apply(_per_group_calc)
        .reset_index()
    )

    keep_cols = GROUP_KEYS + [x_col, "select_def_glass_cnt", "select_def_cnt"]
    gg = gg[keep_cols].copy()

    out = gg.groupby(x_col, as_index=False).agg({"select_def_glass_cnt": "sum", "select_def_cnt": "sum"})
    out = out.rename(columns={x_col: "x"})
    return out


def _agg_select_by_x(df_denom: pd.DataFrame, df_num_calc: pd.DataFrame, x_col: str, selected_sizes: List[str]) -> pd.DataFrame:
    a = _agg_select_total_glass_by_x(df_denom, x_col)
    b = _agg_select_num_by_x(df_num_calc, x_col, selected_sizes)
    out = a.merge(b, on="x", how="left")
    return out


# ============================================================
# Segment-specific aggregation
# ============================================================
def _agg_month_total(df: pd.DataFrame, d_range: Tuple[datetime, datetime]) -> pd.DataFrame:
    d_start, d_end = d_range
    label_start = d_start - LABEL_DELTA
    label_end = d_end - LABEL_DELTA

    xdf = df[(df["pi_hour"] >= label_start) & (df["pi_hour"] < label_end)].copy()
    if xdf.empty:
        return pd.DataFrame(columns=["x", "glass_cnt", "defect_cnt"])

    xdf["__b"] = xdf["pi_hour"] - pd.Timedelta(hours=7)
    bdt = pd.to_datetime(xdf["__b"])
    xdf["x"] = MONTH_TOKEN_PREFIX + bdt.dt.strftime("%y%m")
    return _agg_total_by_x(xdf, "x")


def _agg_month_select(df_denom: pd.DataFrame, df_num_calc: pd.DataFrame,
                      d_range: Tuple[datetime, datetime], selected_sizes: List[str]) -> pd.DataFrame:
    d_start, d_end = d_range
    label_start = d_start - LABEL_DELTA
    label_end = d_end - LABEL_DELTA

    xd = df_denom[(df_denom["pi_hour"] >= label_start) & (df_denom["pi_hour"] < label_end)].copy()
    xn = df_num_calc[(df_num_calc["pi_hour"] >= label_start) & (df_num_calc["pi_hour"] < label_end)].copy()

    if not xd.empty:
        xd["__b"] = xd["pi_hour"]- pd.Timedelta(hours=7)
        bdt = pd.to_datetime(xd["__b"])
        xd["x"] = MONTH_TOKEN_PREFIX + bdt.dt.strftime("%y%m")
    if not xn.empty:
        xn["__b"] = xn["pi_hour"]- pd.Timedelta(hours=7)
        bdt = pd.to_datetime(xn["__b"])
        xn["x"] = MONTH_TOKEN_PREFIX + bdt.dt.strftime("%y%m")

    return _agg_select_by_x(xd, xn, "x", selected_sizes)


def _trend_month(df_total: pd.DataFrame,
                 df_denom: pd.DataFrame,
                 df_num_calc: pd.DataFrame,
                 d_range: Tuple[datetime, datetime],
                 selected_sizes: List[str]) -> List[Dict[str, Any]]:
    d_start, d_end = d_range
    ticks = _mk_month_ticks(d_start, d_end)
    base = pd.DataFrame({"x": ticks})

    gt = _agg_month_total(df_total, d_range)
    gs = _agg_month_select(df_denom, df_num_calc, d_range, selected_sizes)

    m = base.merge(gt, on="x", how="left").merge(gs, on="x", how="left")

    out = []
    for _, r in m.iterrows():
        glass = None if pd.isna(r.get("glass_cnt")) else int(r["glass_cnt"])
        defect = None if pd.isna(r.get("defect_cnt")) else int(r["defect_cnt"])

        sel_total_glass = None if pd.isna(r.get("select_total_glass_cnt")) else int(r["select_total_glass_cnt"])
        sel_def_glass = None if pd.isna(r.get("select_def_glass_cnt")) else int(r["select_def_glass_cnt"])
        sel_def = None if pd.isna(r.get("select_def_cnt")) else int(r["select_def_cnt"])

        out.append({
            "x": str(r["x"]),
            "x_label": str(r["x"]),
            "segment": "month",
            "glass_cnt": glass,
            "defect_cnt": defect,
            "density": _safe_div(defect, glass),
            "select_total_glass_cnt": sel_total_glass,
            "select_def_glass_cnt": sel_def_glass,
            "select_def_cnt": sel_def,
            "select_glass_cnt": sel_total_glass,
            "select_density": _safe_div(sel_def, sel_total_glass),
        })
    return out


def _agg_week_total(df: pd.DataFrame, d_range: Tuple[datetime, datetime]) -> pd.DataFrame:
    d_start, d_end = d_range
    label_start = d_start - LABEL_DELTA
    label_end = d_end - LABEL_DELTA

    xdf = df[(df["pi_hour"] >= label_start) & (df["pi_hour"] < label_end)].copy()
    if xdf.empty:
        return pd.DataFrame(columns=["x", "week_start", "glass_cnt", "defect_cnt"])

    xdf["__b"] = xdf["pi_hour"]- pd.Timedelta(hours=7)
    bdt = pd.to_datetime(xdf["__b"])

    dow = bdt.dt.dayofweek
    sun_offset = (dow + 1) % 7
    xdf["week_start"] = (bdt - pd.to_timedelta(sun_offset, unit="D")).dt.normalize()

    monday = xdf["week_start"] + pd.to_timedelta(1, unit="D")
    iso = monday.dt.isocalendar()
    xdf["x"] = iso.apply(lambda rr: _week_label(int(rr["year"]), int(rr["week"])), axis=1)

    g = _agg_total_by_x(xdf, "x")
    wk = xdf.groupby("x", as_index=False)["week_start"].min()
    out = wk.merge(g, on="x", how="left").sort_values("week_start")
    return out[["x", "week_start", "glass_cnt", "defect_cnt"]]


def _agg_week_select(df_denom: pd.DataFrame, df_num_calc: pd.DataFrame,
                     d_range: Tuple[datetime, datetime], selected_sizes: List[str]) -> pd.DataFrame:
    d_start, d_end = d_range
    label_start = d_start - LABEL_DELTA
    label_end = d_end - LABEL_DELTA

    xd = df_denom[(df_denom["pi_hour"] >= label_start) & (df_denom["pi_hour"] < label_end)].copy()
    xn = df_num_calc[(df_num_calc["pi_hour"] >= label_start) & (df_num_calc["pi_hour"] < label_end)].copy()

    if xd.empty and xn.empty:
        return pd.DataFrame(columns=["x", "week_start", "select_total_glass_cnt", "select_def_glass_cnt", "select_def_cnt"])

    def _add_week_x(df0: pd.DataFrame) -> pd.DataFrame:
        if df0.empty:
            return df0
        df0["__b"] = df0["pi_hour"]- pd.Timedelta(hours=7)
        bdt = pd.to_datetime(df0["__b"])
        dow = bdt.dt.dayofweek
        sun_offset = (dow + 1) % 7
        df0["week_start"] = (bdt - pd.to_timedelta(sun_offset, unit="D")).dt.normalize()
        monday = df0["week_start"] + pd.to_timedelta(1, unit="D")
        iso = monday.dt.isocalendar()
        df0["x"] = iso.apply(lambda rr: _week_label(int(rr["year"]), int(rr["week"])), axis=1)
        return df0

    xd = _add_week_x(xd)
    xn = _add_week_x(xn)

    gsel = _agg_select_by_x(xd, xn, "x", selected_sizes)
    if not xd.empty:
        wk = xd.groupby("x", as_index=False)["week_start"].min()
    else:
        wk = xn.groupby("x", as_index=False)["week_start"].min()

    out = wk.merge(gsel, on="x", how="left").sort_values("week_start")
    return out


def _trend_week(df_total: pd.DataFrame,
                df_denom: pd.DataFrame,
                df_num_calc: pd.DataFrame,
                d_range: Tuple[datetime, datetime],
                selected_sizes: List[str]) -> List[Dict[str, Any]]:
    d_start, d_end = d_range
    ticks = _mk_week_ticks(d_start, d_end)
    base = pd.DataFrame({"x": ticks})

    gt = _agg_week_total(df_total, d_range)[["x", "glass_cnt", "defect_cnt"]]
    gs = _agg_week_select(df_denom, df_num_calc, d_range, selected_sizes)[["x", "select_total_glass_cnt", "select_def_glass_cnt", "select_def_cnt"]]

    m = base.merge(gt, on="x", how="left").merge(gs, on="x", how="left")

    out = []
    for _, r in m.iterrows():
        glass = None if pd.isna(r.get("glass_cnt")) else int(r["glass_cnt"])
        defect = None if pd.isna(r.get("defect_cnt")) else int(r["defect_cnt"])

        sel_total_glass = None if pd.isna(r.get("select_total_glass_cnt")) else int(r["select_total_glass_cnt"])
        sel_def_glass = None if pd.isna(r.get("select_def_glass_cnt")) else int(r["select_def_glass_cnt"])
        sel_def = None if pd.isna(r.get("select_def_cnt")) else int(r["select_def_cnt"])

        out.append({
            "x": str(r["x"]),
            "x_label": str(r["x"]),
            "segment": "week",
            "glass_cnt": glass,
            "defect_cnt": defect,
            "density": _safe_div(defect, glass),
            "select_total_glass_cnt": sel_total_glass,
            "select_def_glass_cnt": sel_def_glass,
            "select_def_cnt": sel_def,
            "select_glass_cnt": sel_total_glass,
            "select_density": _safe_div(sel_def, sel_total_glass),
        })
    return out


def _agg_day_total(df: pd.DataFrame, d_range: Tuple[datetime, datetime]) -> pd.DataFrame:
    d_start, d_end = d_range
    label_start = d_start - LABEL_DELTA
    label_end = d_end - LABEL_DELTA

    xdf = df[(df["pi_hour"] >= label_start) & (df["pi_hour"] < label_end)].copy()
    if xdf.empty:
        return pd.DataFrame(columns=["x", "pi_date", "glass_cnt", "defect_cnt"])

    xdf["__b"] = xdf["pi_hour"]- pd.Timedelta(hours=7)
    bdt = pd.to_datetime(xdf["__b"])
    xdf["pi_date"] = bdt.dt.date
    xdf["x"] = "D" + bdt.dt.strftime("%m%d")

    g = _agg_total_by_x(xdf, "x")
    dd = xdf.groupby("x", as_index=False)["pi_date"].min()
    out = dd.merge(g, on="x", how="left").sort_values("pi_date")
    return out[["x", "pi_date", "glass_cnt", "defect_cnt"]]


def _agg_day_select(df_denom: pd.DataFrame, df_num_calc: pd.DataFrame,
                    d_range: Tuple[datetime, datetime], selected_sizes: List[str]) -> pd.DataFrame:
    d_start, d_end = d_range
    label_start = d_start - LABEL_DELTA
    label_end = d_end - LABEL_DELTA

    xd = df_denom[(df_denom["pi_hour"] >= label_start) & (df_denom["pi_hour"] < label_end)].copy()
    xn = df_num_calc[(df_num_calc["pi_hour"] >= label_start) & (df_num_calc["pi_hour"] < label_end)].copy()

    if xd.empty and xn.empty:
        return pd.DataFrame(columns=["x", "pi_date", "select_total_glass_cnt", "select_def_glass_cnt", "select_def_cnt"])

    def _add_day_x(df0: pd.DataFrame) -> pd.DataFrame:
        if df0.empty:
            return df0
        df0["__b"] = df0["pi_hour"]- pd.Timedelta(hours=7)
        bdt = pd.to_datetime(df0["__b"])
        df0["pi_date"] = bdt.dt.date
        df0["x"] = "D" + bdt.dt.strftime("%m%d")
        return df0

    xd = _add_day_x(xd)
    xn = _add_day_x(xn)

    gsel = _agg_select_by_x(xd, xn, "x", selected_sizes)
    if not xd.empty:
        dd = xd.groupby("x", as_index=False)["pi_date"].min()
    else:
        dd = xn.groupby("x", as_index=False)["pi_date"].min()

    out = dd.merge(gsel, on="x", how="left").sort_values("pi_date")
    return out


def _trend_day(df_total: pd.DataFrame,
               df_denom: pd.DataFrame,
               df_num_calc: pd.DataFrame,
               d_range: Tuple[datetime, datetime],
               selected_sizes: List[str]) -> List[Dict[str, Any]]:
    d_start, d_end = d_range
    ticks = _mk_day_ticks(d_start, d_end)
    base = pd.DataFrame({"x": ticks})

    gt = _agg_day_total(df_total, d_range)[["x", "glass_cnt", "defect_cnt"]]
    gs = _agg_day_select(df_denom, df_num_calc, d_range, selected_sizes)[["x", "select_total_glass_cnt", "select_def_glass_cnt", "select_def_cnt"]]

    m = base.merge(gt, on="x", how="left").merge(gs, on="x", how="left")

    out = []
    for _, r in m.iterrows():
        glass = None if pd.isna(r.get("glass_cnt")) else int(r["glass_cnt"])
        defect = None if pd.isna(r.get("defect_cnt")) else int(r["defect_cnt"])

        sel_total_glass = None if pd.isna(r.get("select_total_glass_cnt")) else int(r["select_total_glass_cnt"])
        sel_def_glass = None if pd.isna(r.get("select_def_glass_cnt")) else int(r["select_def_glass_cnt"])
        sel_def = None if pd.isna(r.get("select_def_cnt")) else int(r["select_def_cnt"])

        out.append({
            "x": str(r["x"]),
            "x_label": str(r["x"]),
            "segment": "day",
            "glass_cnt": glass,
            "defect_cnt": defect,
            "density": _safe_div(defect, glass),
            "select_total_glass_cnt": sel_total_glass,
            "select_def_glass_cnt": sel_def_glass,
            "select_def_cnt": sel_def,
            "select_glass_cnt": sel_total_glass,
            "select_density": _safe_div(sel_def, sel_total_glass),
        })
    return out


def _build_summary(month_pts, week_pts, day_pts) -> List[Dict[str, Any]]:
    return month_pts + week_pts + day_pts


# ============================================================
# Options
# ============================================================
def _build_filter_options(df: pd.DataFrame) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    if df.empty:
        for k in FILTER_KEYS:
            out[k] = []
        out["defect_size"] = VALID_SIZES[:]
        return out

    for k in ["line_id", "model", "glass_type"]:
        vals = df[k].astype(str)
        uniq = sorted([v for v in vals.unique().tolist() if v and v not in ("nan", "None")])
        print(k, len(vals), len(uniq))
        out[k] = uniq

    out["defect_size"] = VALID_SIZES[:]
    return out


# ============================================================
# bucket filters adapter
# ============================================================
def _is_bucket_filters(filters: Any) -> bool:
    if not isinstance(filters, dict):
        return False
    return any(k in filters for k in ["summary", "month", "week", "day"])


def _get_bucket_filters(filters_any: Any, bucket: str) -> Dict[str, Any]:
    if not isinstance(filters_any, dict):
        return {}
    if _is_bucket_filters(filters_any):
        b = filters_any.get(bucket, {})
        return b if isinstance(b, dict) else {}
    return filters_any


def _normalize_target(payload: Dict[str, Any]) -> str:
    t = payload.get("target") or payload.get("scope")
    t = str(t or "").strip().lower()
    return t if t in VALID_TARGETS else ""


def _is_init_date_dict_all_empty(date_dict: Any) -> bool:
    if not isinstance(date_dict, dict):
        return True

    s = date_dict.get("summary", {})
    if not isinstance(s, dict):
        s = {}

    def _is_empty_list(x):
        return isinstance(x, list) and len(x) == 0

    cond = True
    cond = cond and _is_empty_list(s.get("month", []))
    cond = cond and _is_empty_list(s.get("week", []))
    cond = cond and _is_empty_list(s.get("day", []))
    cond = cond and _is_empty_list(date_dict.get("month", []))
    cond = cond and _is_empty_list(date_dict.get("week", []))
    cond = cond and _is_empty_list(date_dict.get("day", []))
    return cond


def _merge_default_filters_if_needed(date_dict: Any, filters_any: Any, is_init: bool) -> Tuple[Dict[str, Any], bool]:
    if not is_init:
        return (filters_any if isinstance(filters_any, dict) else {}), False

    if not _is_init_date_dict_all_empty(date_dict):
        return (filters_any if isinstance(filters_any, dict) else {}), False

    base = DEFAULT_TREND_FILTERS.copy()

    if isinstance(filters_any, dict) and filters_any:
        if _is_bucket_filters(filters_any):
            out = {}
            for b in ["summary", "month", "week", "day"]:
                bf = filters_any.get(b, {})
                if not isinstance(bf, dict):
                    bf = {}
                merged = {**base, **bf}
                out[b] = merged
            return out, True
        else:
            merged = {**base, **filters_any}
            out = {b: merged for b in ["summary", "month", "week", "day"]}
            return out, True

    out = {b: base for b in ["summary", "month", "week", "day"]}
    return out, True


# ============================================================
# Route
# ============================================================




@router.post("/trend")
async def get_aoi_inspection_density_trend(payload: Dict[str, Any] = Body(...)):
    """
    init:
      - 不帶 target / scope，回 summary/month/week/day 四張圖 + options

    單張更新:
      - target in {"summary","month","week","day"}
      - 只回該 target 的 points
    """
    date_dict = payload.get("date_dict") or {}
    filters_any = payload.get("filters") or {}

    target = _normalize_target(payload)
    is_init = (target == "")

    filters_any, default_applied = _merge_default_filters_if_needed(date_dict, filters_any, is_init)

    logger.info("[InspectionTrend] target=%s is_init=%s default_applied=%s", target or "(init)", is_init, default_applied)
    logger.info("[InspectionTrend] payload(date_dict)=%s", _compact_for_log(date_dict))
    logger.info("[InspectionTrend] payload(filters)=%s", _compact_for_log(filters_any))

    if is_init:
        summary_block, normal_block = _extract_blocks(date_dict)
        summary_ranges = _parse_date_block(summary_block, is_summary=True)
        normal_ranges = _parse_date_block(normal_block, is_summary=False)

        all_ranges = list(summary_ranges.values()) + list(normal_ranges.values())
        d_min = min(r[0] for r in all_ranges)
        d_max = max(r[1] for r in all_ranges)

        meta_ranges = {
            "normal": {
                "month": [normal_ranges["month"][0].strftime("%Y-%m-%d %H:%M:%S"),
                          normal_ranges["month"][1].strftime("%Y-%m-%d %H:%M:%S")],
                "week": [normal_ranges["week"][0].strftime("%Y-%m-%d %H:%M:%S"),
                         normal_ranges["week"][1].strftime("%Y-%m-%d %H:%M:%S")],
                "day": [normal_ranges["day"][0].strftime("%Y-%m-%d %H:%M:%S"),
                        normal_ranges["day"][1].strftime("%Y-%m-%d %H:%M:%S")],
            },
            "summary": {
                "month": [summary_ranges["month"][0].strftime("%Y-%m-%d %H:%M:%S"),
                          summary_ranges["month"][1].strftime("%Y-%m-%d %H:%M:%S")],
                "week": [summary_ranges["week"][0].strftime("%Y-%m-%d %H:%M:%S"),
                         summary_ranges["week"][1].strftime("%Y-%m-%d %H:%M:%S")],
                "day": [summary_ranges["day"][0].strftime("%Y-%m-%d %H:%M:%S"),
                        summary_ranges["day"][1].strftime("%Y-%m-%d %H:%M:%S")],
            },
        }
    else:
        ranges, meta_ranges = _pick_ranges_for_target(date_dict, target)
        d_min, d_max = _minmax_from_ranges_nested(ranges)

    dbhandler = _DBHandler(CFG.db_name)
    df_base, missing_tables = _fetch_inspection_rows(dbhandler, d_min, d_max)

    filterOptionDict = _build_filter_options(df_base)

    def _build_bucket_datasets(bucket_filters: Dict[str, Any]) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, List[str]]:
        ss = _normalize_selected_sizes(bucket_filters)

        # total：完全不受 filter 影響，對應 total 系列
        #df_total = df_base
        df_common = _apply_common_filters(df_base, bucket_filters)
        # denominator：只吃 line/model/glass_type；不吃 defect_size
        df_denom = df_common#_apply_common_filters(df_base, bucket_filters)

        # numerator base：跟 denominator 一樣，defect_size 另外由 glass_size_detail 計算
        #df_num = _apply_common_filters(df_base, bucket_filters)
        df_num_calc = _calc_num_from_glass_size_detail(df_common, ss)

        return df_base, df_denom, df_num_calc, ss

    dataset_cache: Dict[str, Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, List[str]]] = {}

    def _filters_cache_key(bucket_filters: Dict[str, Any]) -> str:
        return json.dumps(bucket_filters or {}, sort_keys=True, ensure_ascii=False)

    def _build_bucket_datasets_cached(bucket_filters: Dict[str, Any]):
        key = _filters_cache_key(bucket_filters)
        if key in dataset_cache:
            return dataset_cache[key]
        result = _build_bucket_datasets(bucket_filters)
        dataset_cache[key] = result
        return result


    if is_init:
        f_summary = _get_bucket_filters(filters_any, "summary")
        f_month = _get_bucket_filters(filters_any, "month")
        f_week = _get_bucket_filters(filters_any, "week")
        f_day = _get_bucket_filters(filters_any, "day")

        df_total_m, df_denom_m, df_num_m, ss_month =  _build_bucket_datasets_cached(f_month)
        df_total_w, df_denom_w, df_num_w, ss_week =  _build_bucket_datasets_cached(f_week)
        df_total_d, df_denom_d, df_num_d, ss_day =  _build_bucket_datasets_cached(f_day)

        df_total_s, df_denom_s, df_num_s, ss_summary = _build_bucket_datasets_cached(f_summary)

        month_pts = _trend_month(df_total_m, df_denom_m, df_num_m, normal_ranges["month"], ss_month)
        week_pts = _trend_week(df_total_w, df_denom_w, df_num_w, normal_ranges["week"], ss_week)
        day_pts = _trend_day(df_total_d, df_denom_d, df_num_d, normal_ranges["day"], ss_day)

        s_month_pts = _trend_month(df_total_s, df_denom_s, df_num_s, summary_ranges["month"], ss_summary)
        s_week_pts = _trend_week(df_total_s, df_denom_s, df_num_s, summary_ranges["week"], ss_summary)
        s_day_pts = _trend_day(df_total_s, df_denom_s, df_num_s, summary_ranges["day"], ss_summary)
        summary_pts = _build_summary(s_month_pts, s_week_pts, s_day_pts)

        logger.info(
            "[InspectionTrend:init] points summary=%d month=%d week=%d day=%d",
            len(summary_pts), len(month_pts), len(week_pts), len(day_pts)
        )

        return {
            "TrendDict": {
                "summary": {"points": summary_pts},
                "month": {"points": month_pts},
                "week": {"points": week_pts},
                "day": {"points": day_pts},
            },
            "ParamDict": {
                "filterOptionDict": filterOptionDict,
                "defaultTrendFilters": (DEFAULT_TREND_FILTERS if default_applied else {}),
                "week_format": "WYYWW",
                "day_format": "DMMDD",
                "month_format": "MYYMM",
            },
            "Meta": {
                "target": "(init)",
                "default_applied": default_applied,
                "missing_tables": missing_tables,
                "requested_months": _month_list_between(d_min, d_max),
                "rows_fetched": int(len(df_base)),
                "now_floor_hour": _now_floor_hour().strftime("%Y-%m-%d %H:%M:%S"),
                "shift_boundary": f"{SHIFT_HOUR:02d}:{SHIFT_MIN:02d}",
                "label_offset_minutes": LABEL_OFFSET_MIN,
                "d_min": d_min.strftime("%Y-%m-%d %H:%M:%S"),
                "d_max_excl": d_max.strftime("%Y-%m-%d %H:%M:%S"),
                "query_pi_hour_min": (d_min - LABEL_DELTA).strftime("%Y-%m-%d %H:%M:%S"),
                "query_pi_hour_max_excl": (d_max - LABEL_DELTA).strftime("%Y-%m-%d %H:%M:%S"),
                "selected_sizes": {
                    "summary": ss_summary,
                    "month": ss_month,
                    "week": ss_week,
                    "day": ss_day,
                },
                "ranges": meta_ranges,
                "filters_compact": {
                    "summary": _compact_for_log(f_summary),
                    "month": _compact_for_log(f_month),
                    "week": _compact_for_log(f_week),
                    "day": _compact_for_log(f_day),
                    "mode": "bucket" if _is_bucket_filters(filters_any) else "flat",
                },
                "select_denominator_policy": "IGNORE defect_size (do not shrink total glass denominator)",
            }
        }

    f = _get_bucket_filters(filters_any, target)
    df_total, df_denom, df_num_calc, ss = _build_bucket_datasets(f)

    if target == "month":
        pts = _trend_month(df_total, df_denom, df_num_calc, ranges["month"], ss)
    elif target == "week":
        pts = _trend_week(df_total, df_denom, df_num_calc, ranges["week"], ss)
    elif target == "day":
        pts = _trend_day(df_total, df_denom, df_num_calc, ranges["day"], ss)
    else:
        s_month_pts = _trend_month(df_total, df_denom, df_num_calc, ranges["month"], ss)
        s_week_pts = _trend_week(df_total, df_denom, df_num_calc, ranges["week"], ss)
        s_day_pts = _trend_day(df_total, df_denom, df_num_calc, ranges["day"], ss)
        pts = _build_summary(s_month_pts, s_week_pts, s_day_pts)

    logger.info("[InspectionTrend:%s] points=%d selected_sizes=%s", target, len(pts), ss)

    return {
        "TrendDict": {
            target: {"points": pts}
        },
        "ParamDict": {
            "filterOptionDict": filterOptionDict,
            "defaultTrendFilters": {},
            "week_format": "WYYWW",
            "day_format": "DMMDD",
            "month_format": "MYYMM",
        },
        "Meta": {
            "target": target,
            "default_applied": False,
            "missing_tables": missing_tables,
            "requested_months": _month_list_between(d_min, d_max),
            "rows_fetched": int(len(df_base)),
            "now_floor_hour": _now_floor_hour().strftime("%Y-%m-%d %H:%M:%S"),
            "shift_boundary": f"{SHIFT_HOUR:02d}:{SHIFT_MIN:02d}",
            "label_offset_minutes": LABEL_OFFSET_MIN,
            "d_min": d_min.strftime("%Y-%m-%d %H:%M:%S"),
            "d_max_excl": d_max.strftime("%Y-%m-%d %H:%M:%S"),
            "query_pi_hour_min": (d_min - LABEL_DELTA).strftime("%Y-%m-%d %H:%M:%S"),
            "query_pi_hour_max_excl": (d_max - LABEL_DELTA).strftime("%Y-%m-%d %H:%M:%S"),
            "selected_sizes": {target: ss},
            "ranges": meta_ranges,
            "filters_compact": {
                target: _compact_for_log(f),
                "mode": "bucket" if _is_bucket_filters(filters_any) else "flat",
            },
            "select_denominator_policy": "IGNORE defect_size (do not shrink total glass denominator)",
        }
    }
