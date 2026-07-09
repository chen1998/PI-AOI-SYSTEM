# routers/bpi_same_point.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text, inspect

from models.sql_db_connect import MySQLConnet
from models.piaoi.bpi_density.API_Config import API_Config


router = APIRouter(tags=["duty_cell_piaoi_bpi_same_point"])
logger = logging.getLogger("bpi_same_point")


# =============================================================================
# Request Models
# =============================================================================
class SamePointFilterIn(BaseModel):
    dates: Optional[List[str]] = None
    filters: Dict[str, List[Any]] = Field(default_factory=dict)
    offset_um: int = 20
    sub_page: str = "PISpot"


class SamePointDefectMapIn(BaseModel):
    mode: str = "MATCH"  # BPI / API / MATCH
    row: Dict[str, Any] = Field(default_factory=dict)
    offset_um: int = 20
    size_filter: List[str] = Field(default_factory=list)


# =============================================================================
# Constants
# =============================================================================
VALID_SIZE_ATOMS = ["S", "M", "L", "O"]

# 保留 group 寫法相容舊前端；新版同點點位篩選建議直接用 S/M/L/O。
SIZE_GROUP_OPTIONS = ["S", "M", "L", "O", "MS", "LMS", "O", "OL", "OLM", "OLMS"]

SIZE_GROUP_ATOMS = {
    "S": {"S"},
    "M": {"M"},
    "L": {"L"},
    "O": {"O"},
    "MS": {"M", "S"},
    "LMS": {"L", "M", "S"},
    "OL": {"O", "L"},
    "OLM": {"O", "L", "M"},
    "OLMS": {"O", "L", "M", "S"},
}

AOI_VALUES = ["aoi100", "aoi200", "aoi300"]

BASE_URL = "http://10.97.139.98:1454//"
AIDI_URL = "http://l6apaimg103/dms/CELAIDI_L6A/"

CIM_AOI_TO_MACHINE = {
    "aoi100": "CAPIT203",
    "aoi200": "CAAOI202",
    "aoi300": "CAAOI300",
}


# =============================================================================
# Basic helpers
# =============================================================================
def clean_text(v: Any) -> str:
    if v is None:
        return ""

    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass

    s = str(v).strip()
    if s.lower() in {"", "nan", "none", "null", "nat", "<na>"}:
        return ""

    return s


def parse_dt(v: Any) -> Optional[datetime]:
    if v is None:
        return None

    if isinstance(v, datetime):
        return v

    try:
        ts = pd.to_datetime(v, errors="coerce")
        if pd.isna(ts):
            return None
        if isinstance(ts, pd.Timestamp):
            return ts.to_pydatetime()
        return ts
    except Exception:
        return None


def dt_to_str(v: Any) -> str:
    dt = parse_dt(v)
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""


def _table_exists(db: MySQLConnet, table_name: str) -> bool:
    return inspect(db.engine).has_table(table_name, schema=db.db)


def _query_df(db: MySQLConnet, sql: str, params: Optional[dict] = None) -> pd.DataFrame:
    with db.engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


def _parse_date_only(s: str) -> datetime:
    s = str(s or "").strip().replace("T", " ")
    for fmt in ("%Y-%m-%d", "%y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(hour=0, minute=0, second=0, microsecond=0)
        except ValueError:
            continue
    raise ValueError(f"Bad date: {s}")


def _current_scan_hour(now: Optional[datetime] = None) -> datetime:
    n = now or datetime.now()
    return (pd.Timestamp(n) - pd.Timedelta(minutes=30)).floor("h").to_pydatetime()


def _default_3day_range(now: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    """
    預設查最近 15 天。
    scan_hour 查詢範圍使用 label hour：
      D 07:00 ~ current scan_hour + 1h
    """
    n = now or datetime.now()
    today = n.replace(hour=0, minute=0, second=0, microsecond=0)

    start = (today - timedelta(days=15)).replace(hour=7, minute=0, second=0, microsecond=0)
    end_excl = _current_scan_hour(n) + timedelta(hours=1)
    return start, end_excl


def _date_range_to_scan_hour_range(dates: Optional[List[str]]) -> Tuple[datetime, datetime]:
    """
    前端日期語意：
      D = [D 07:30, D+1 07:30)

    表內 scan_hour 已經是：
      floor(api_scan_time - 30min, hour)

    所以查 scan_hour：
      [D 07:00, D+1 07:00)
    """
    if not dates or len(dates) != 2:
        return _default_3day_range()

    d1 = _parse_date_only(dates[0])
    d2 = _parse_date_only(dates[1])

    if d2 < d1:
        d1, d2 = d2, d1

    start = d1.replace(hour=7, minute=0, second=0, microsecond=0)
    end_excl = (d2 + timedelta(days=1)).replace(hour=7, minute=0, second=0, microsecond=0)

    return start, end_excl


def _month_span(start: datetime, end_excl: datetime) -> List[str]:
    if end_excl <= start:
        return []

    end_incl = end_excl - timedelta(seconds=1)
    cur = datetime(start.year, start.month, 1)
    last = datetime(end_incl.year, end_incl.month, 1)

    out: List[str] = []

    while cur <= last:
        out.append(cur.strftime("%Y%m"))
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)

    return out


def _safe_num(v: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        if pd.isna(v):
            return default
        return int(float(v))
    except Exception:
        return default


def _normalize_filters(filters: Any) -> Dict[str, List[str]]:
    if not isinstance(filters, dict):
        return {}

    out: Dict[str, List[str]] = {}

    for k, arr in filters.items():
        if not isinstance(arr, list):
            continue

        vals = [str(x).strip() for x in arr if str(x).strip()]
        if vals:
            out[str(k)] = vals

    return out


def _normalize_offset(v: Any, allowed: Optional[List[int]] = None) -> int:
    try:
        n = int(v)
    except Exception:
        n = 20

    allowed = allowed or list(range(5, 55, 5))
    if n not in allowed:
        return 20 if 20 in allowed else allowed[0]

    return n


def _normalize_sub_page(v: Any) -> str:
    sub = clean_text(v)

    if sub.upper() == "UPI":
        return "UPI"

    if sub.upper() in {"PISPOT", "PI_SPOT", "PI-SPOT"}:
        return "PISpot"

    return "PISpot"


def _same_point_tab_key(sub_page: str) -> str:
    sub = _normalize_sub_page(sub_page)

    if sub == "UPI":
        return "bpi_same_point_upi"

    return "bpi_same_point_pispot"


def _row_hits_sub_page(row: pd.Series, sub_page: str) -> bool:
    """
    PISpot / UPI 分頁語意：

    - api_aoi = aoi200：
        需要依 tab 或 api_recipe_id 分到 PISpot / UPI。

    - api_aoi = aoi100 / aoi300：
        不做 PISpot / UPI 分流，兩個子頁都顯示。

    原因：
      PISpot / UPI 只是 aoi200 的製程區分。
      aoi100 recipe 通常是三碼，aoi300 recipe 通常是字串，
      不應被 PISpot / UPI 子頁濾掉。
    """
    sub = _normalize_sub_page(sub_page)
    api_aoi = clean_text(row.get("api_aoi")).lower()

    # 非 aoi200 不做 PISpot / UPI 分流，兩邊都顯示
    if api_aoi != "aoi200":
        return True

    tab = clean_text(row.get("tab"))
    if tab:
        return tab == sub

    recipe = clean_text(row.get("api_recipe_id"))

    # aoi200 recipe rule：
    # PISpot: 0/1/4/5 或三碼
    # UPI:    2/3/4/5 或三碼
    #
    # 注意：4/5 同時出現在兩邊，代表這類 recipe 兩頁都可顯示。
    if len(recipe) == 3 and recipe.isdigit():
        return True

    first = recipe[:1]

    if sub == "PISpot":
        return first in {"0", "1", "4", "5"}

    if sub == "UPI":
        return first in {"2", "3", "4", "5"}

    return True

def _project_same_point_counts_by_size(df: pd.DataFrame, filters: Dict[str, List[str]]) -> pd.DataFrame:
    """
    defect_size 不應該過濾掉 chart row。
    它只影響同點 scatter / matched count 類欄位。

    設計：
      - BPI/API defect_count 保持原值，bar 不變。
      - matched_pair_count 依勾選尺寸重算。
      - matched_bpi_defect_count / matched_api_defect_count 跟著重算。
      - matched_bpi_s/m/l/o_count、matched_api_s/m/l/o_count：
          未勾選尺寸歸 0，已勾選尺寸保留。
      - unmatched_* 不建議用 defect_size filter 重算，因為它代表 raw unmatched 母體。
        若前端目前有顯示，可先保留原值。
    """
    if df is None or df.empty:
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()

    atoms = _selected_size_atoms(filters)
    if not atoms:
        return df

    out = df.copy()

    bpi_size_cols = {
        "S": "matched_bpi_s_count",
        "M": "matched_bpi_m_count",
        "L": "matched_bpi_l_count",
        "O": "matched_bpi_o_count",
    }

    api_size_cols = {
        "S": "matched_api_s_count",
        "M": "matched_api_m_count",
        "L": "matched_api_l_count",
        "O": "matched_api_o_count",
    }

    selected_bpi_cols = []
    selected_api_cols = []

    for atom in VALID_SIZE_ATOMS:
        bpi_col = bpi_size_cols[atom]
        api_col = api_size_cols[atom]

        if bpi_col not in out.columns:
            out[bpi_col] = 0
        if api_col not in out.columns:
            out[api_col] = 0

        out[bpi_col] = pd.to_numeric(out[bpi_col], errors="coerce").fillna(0).astype(int)
        out[api_col] = pd.to_numeric(out[api_col], errors="coerce").fillna(0).astype(int)

        if atom in atoms:
            selected_bpi_cols.append(bpi_col)
            selected_api_cols.append(api_col)
        else:
            out[bpi_col] = 0
            out[api_col] = 0

    if selected_bpi_cols:
        out["matched_bpi_defect_count"] = out[selected_bpi_cols].sum(axis=1)
    else:
        out["matched_bpi_defect_count"] = 0

    if selected_api_cols:
        out["matched_api_defect_count"] = out[selected_api_cols].sum(axis=1)
    else:
        out["matched_api_defect_count"] = 0

    # 同點 scatter 建議用 BPI/API matched 後的較大值。
    # 若你的 match pair 一筆一定對應 BPI/API 各一點，兩邊應該會一樣。
    out["matched_pair_count"] = out[
        ["matched_bpi_defect_count", "matched_api_defect_count"]
    ].max(axis=1)

    return out



# =============================================================================
# URL / Image helpers
# =============================================================================
def _is_http_url(v: Any) -> bool:
    s = clean_text(v).lower()
    return s.startswith("http://") or s.startswith("https://")


def _join_url_path(base: str, path: str) -> str:
    b = clean_text(base)
    p = clean_text(path).replace("\\", "/")

    if not b:
        return p
    if not p:
        return b

    return b.rstrip("/") + "/" + p.lstrip("/")


def _normalize_aidi_or_direct_path(v: Any) -> str:
    s = clean_text(v).replace("\\", "/")
    if not s:
        return ""

    if _is_http_url(s):
        return s

    if s.startswith("PIT/") or s.startswith("/PIT/"):
        return _join_url_path(AIDI_URL, s)

    return s


def _normalize_unc_image_path(v: Any) -> str:
    s0 = clean_text(v)
    if not s0:
        return ""

    if _is_http_url(s0):
        return s0

    s = s0.replace("\\", "/")
    prefix = "//192.168.5.88/aoi"

    if s.startswith(prefix):
        rest = s[len(prefix):].lstrip("/")
        return _join_url_path(BASE_URL, rest)

    return s


def _load_cim_op_id(
    *,
    db: MySQLConnet,
    yyyymm: str,
    glass_id: str,
    test_time: datetime,
) -> str:
    tbn = f"cim_pi_glass_{yyyymm}".lower()

    if not _table_exists(db, tbn):
        logger.warning(f"[_load_cim_op_id] missing summary table={tbn}")
        return ""

    sql = f"""
    SELECT op_id
    FROM `{db.db}`.`{tbn}`
    WHERE sheet_id_chip_id = :glass_id
      AND test_time = :test_time
    LIMIT 1
    """

    try:
        df = _query_df(db, sql, {
            "glass_id": glass_id,
            "test_time": test_time,
        })
    except Exception as e:
        logger.warning(
            f"[_load_cim_op_id] query failed: table={tbn}, "
            f"glass={glass_id}, test_time={test_time}, err={e}"
        )
        return ""

    if df is None or df.empty:
        logger.warning(
            f"[_load_cim_op_id] summary row not found: table={tbn}, "
            f"glass={glass_id}, test_time={test_time}"
        )
        return ""

    return clean_text(df.iloc[0].get("op_id", ""))


def _build_cim_image_capture_path(
    *,
    raw_path: Any,
    latest_tt: Any,
    op_id: Any,
    aoi: str,
) -> str:
    path0 = clean_text(raw_path).replace("\\", "/")
    if not path0:
        return ""

    try:
        str_time = pd.to_datetime(latest_tt).strftime("%Y%m%d%H%M%S")
    except Exception:
        str_time = (
            str(latest_tt)
            .replace("-", "")
            .replace(":", "")
            .replace(" ", "")
        )

    p2 = path0[6:] if path0.startswith("Image/") else path0
    p2 = p2.lstrip("/")

    if p2 and not p2.endswith("/"):
        p2 += "/"

    machine_id = CIM_AOI_TO_MACHINE.get(clean_text(aoi).lower(), clean_text(aoi))

    return (
        BASE_URL
        + machine_id
        + "/"
        + p2
        + clean_text(op_id)
        + "/"
        + str_time
        + "/CaptureImage/"
    )


def _normalize_cim_pic_path_for_row(
    *,
    db: MySQLConnet,
    row: pd.Series,
    aoi: str,
    glass_id: str,
    scan_time: datetime,
) -> str:
    src = clean_text(row.get("img_file_url_path", ""))
    if not src:
        src = clean_text(row.get("image_file_path", ""))

    if not src:
        return ""

    s = src.replace("\\", "/")

    if _is_http_url(s):
        return s

    if s.startswith("PIT/") or s.startswith("/PIT/"):
        return _normalize_aidi_or_direct_path(s)

    if s.startswith("Image"):
        yyyymm = scan_time.strftime("%Y%m") if scan_time else ""
        op_id = _load_cim_op_id(
            db=db,
            yyyymm=yyyymm,
            glass_id=glass_id,
            test_time=scan_time,
        ) if yyyymm and glass_id and scan_time else ""

        return _build_cim_image_capture_path(
            raw_path=s,
            latest_tt=scan_time,
            op_id=op_id,
            aoi=aoi,
        )

    if "192.168.5.88/aoi" in s or "\\\\192.168.5.88\\aoi" in src:
        return _normalize_unc_image_path(src)

    return s


def _normalize_rtms_pic_path(v: Any) -> str:
    return _normalize_aidi_or_direct_path(v)


# =============================================================================
# Size helpers
# =============================================================================
def _normalize_size_group(v: Any) -> str:
    s = str(v or "").upper().strip()

    aliases = {
        "SM": "MS",
        "SML": "LMS",
        "SMLO": "OLMS",
    }

    return aliases.get(s, s)


def _size_group_to_atoms(v: Any) -> set[str]:
    g = _normalize_size_group(v)
    return set(SIZE_GROUP_ATOMS.get(g, set()))


def _selected_size_atoms_from_list(arr: Optional[List[Any]]) -> set[str]:
    if not arr:
        return set()

    atoms: set[str] = set()
    for x in arr:
        atoms |= _size_group_to_atoms(x)

    return atoms


def _selected_size_atoms(filters: Dict[str, List[str]]) -> set[str]:
    return _selected_size_atoms_from_list(filters.get("defect_size") or [])


def _row_hits_size_filter(row: pd.Series, filters: Dict[str, List[str]]) -> bool:
    """
    新版 list row 用 offset_summary 的 BPI/API size count 判斷。

    邏輯：
      selected size 命中 matched_bpi_* 或 matched_api_* 任一邊，即符合。
    """
    atoms = _selected_size_atoms(filters)

    if not atoms:
        return True

    bpi_col = {
        "S": "matched_bpi_s_count",
        "M": "matched_bpi_m_count",
        "L": "matched_bpi_l_count",
        "O": "matched_bpi_o_count",
    }

    api_col = {
        "S": "matched_api_s_count",
        "M": "matched_api_m_count",
        "L": "matched_api_l_count",
        "O": "matched_api_o_count",
    }

    for a in atoms:
        bc = bpi_col.get(a)
        ac = api_col.get(a)

        if bc and _safe_int(row.get(bc), 0) > 0:
            return True

        if ac and _safe_int(row.get(ac), 0) > 0:
            return True

    return False


def _filter_match_df_by_size(df: pd.DataFrame, size_filter: Optional[List[Any]]) -> pd.DataFrame:
    """
    MATCH 點位層級篩選：
      bpi_defect_size in selected OR api_defect_size in selected

    BPI/API raw mode 則使用 defect_size。
    """
    if df is None or df.empty:
        return pd.DataFrame()

    atoms = _selected_size_atoms_from_list(size_filter or [])
    if not atoms:
        return df

    out = df.copy()

    if "bpi_defect_size" in out.columns or "api_defect_size" in out.columns:
        mask = pd.Series(False, index=out.index)

        if "bpi_defect_size" in out.columns:
            mask = mask | out["bpi_defect_size"].astype(str).str.upper().isin(atoms)

        if "api_defect_size" in out.columns:
            mask = mask | out["api_defect_size"].astype(str).str.upper().isin(atoms)

        return out[mask].copy()

    if "defect_size" in out.columns:
        return out[out["defect_size"].astype(str).str.upper().isin(atoms)].copy()

    return out

def _is_empty_like(v: Any) -> bool:
    if v is None:
        return True

    try:
        if pd.isna(v):
            return True
    except Exception:
        pass

    s = str(v).strip()
    return s.lower() in {"", "nan", "none", "null", "nat", "<na>", "undefined"}


def _normalize_defect_size_for_aoi(v: Any, aoi: Any = "") -> str:
    """
    同點後端路由用 defect_size normalize。

    AOI200:
        NULL / 空字串 / nan / none / null / <NA> / nat / undefined
        或其他非 S/M/L/O 的異常值，一律歸 O。

    其他 AOI:
        S/M/L/O 正常保留。
        無法歸類則回空字串，後續會被濾掉。
    """
    aoi_norm = clean_text(aoi).lower()

    if _is_empty_like(v):
        return "O" if aoi_norm == "aoi200" else ""

    s = str(v).strip().upper()

    if s in {"S", "SMALL"}:
        return "S"
    if s in {"M", "MID", "MIDDLE"}:
        return "M"
    if s in {"L", "LARGE"}:
        return "L"
    if s in {"O", "OVER"}:
        return "O"

    # 若 defect_size 是數值，也順手轉 S/M/L/O
    n = pd.to_numeric(s, errors="coerce")
    if not pd.isna(n):
        if n <= 20:
            return "S"
        if n <= 100:
            return "M"
        if n <= 400:
            return "L"
        return "O"

    # AOI200 其他異常值也歸 O，避免 raw defect 被丟掉
    if aoi_norm == "aoi200":
        return "O"

    return ""

def _normalize_match_size_cols(df: pd.DataFrame, row: Dict[str, Any]) -> pd.DataFrame:
    """
    MATCH mode 用。
    將 match_detail / matched_points_json 裡的 bpi_defect_size、api_defect_size
    依 bpi_aoi / api_aoi 做 normalize。

    主要目的：
      - AOI200 空 size 顯示 / 篩選時歸 O
      - 兼容舊資料
    """
    if df is None or df.empty:
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()

    out = df.copy()

    bpi_aoi = clean_text(row.get("bpi_aoi"))
    api_aoi = clean_text(row.get("api_aoi"))

    if "bpi_defect_size" in out.columns:
        out["bpi_defect_size"] = out["bpi_defect_size"].apply(
            lambda v: _normalize_defect_size_for_aoi(v, bpi_aoi)
        )

    if "api_defect_size" in out.columns:
        out["api_defect_size"] = out["api_defect_size"].apply(
            lambda v: _normalize_defect_size_for_aoi(v, api_aoi)
        )

    return out
# =============================================================================
# Read tables
# =============================================================================
def _read_pair_rows(
    *,
    db: MySQLConnet,
    api_cfg: API_Config,
    start: datetime,
    end_excl: datetime,
) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []

    for ym in _month_span(start, end_excl):
        tbn = api_cfg.bpi_same_point_pair_table_tpl.replace("yyyymm", ym).lower()

        if not _table_exists(db, tbn):
            continue

        cols = ", ".join([f"`{c}`" for c in api_cfg.bpi_same_point_pair_sql_cols])

        sql = f"""
        SELECT {cols}
        FROM `{db.db}`.`{tbn}`
        WHERE `scan_hour` >= :start_dt
          AND `scan_hour` <  :end_dt
        """

        df = _query_df(db, sql, {"start_dt": start, "end_dt": end_excl})

        if df is not None and not df.empty:
            df["_pair_source_table"] = tbn
            frames.append(df)

    if not frames:
        return pd.DataFrame(columns=api_cfg.bpi_same_point_pair_sql_cols)

    return pd.concat(frames, ignore_index=True)


def _read_offset_rows(
    *,
    db: MySQLConnet,
    api_cfg: API_Config,
    start: datetime,
    end_excl: datetime,
    offset_um: int,
) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []

    for ym in _month_span(start, end_excl):
        tbn = api_cfg.bpi_same_point_offset_table_tpl.replace("yyyymm", ym).lower()

        if not _table_exists(db, tbn):
            continue

        cols = ", ".join([f"`{c}`" for c in api_cfg.bpi_same_point_offset_sql_cols])

        sql = f"""
        SELECT {cols}
        FROM `{db.db}`.`{tbn}`
        WHERE `scan_hour` >= :start_dt
          AND `scan_hour` <  :end_dt
          AND `offset_um` = :offset_um
        """

        df = _query_df(db, sql, {
            "start_dt": start,
            "end_dt": end_excl,
            "offset_um": int(offset_um),
        })

        if df is not None and not df.empty:
            df["_offset_source_table"] = tbn
            frames.append(df)

    if not frames:
        return pd.DataFrame(columns=api_cfg.bpi_same_point_offset_sql_cols)

    return pd.concat(frames, ignore_index=True)


def _merge_pair_offset(pair_df: pd.DataFrame, offset_df: pd.DataFrame) -> pd.DataFrame:
    if offset_df is None or offset_df.empty:
        return pd.DataFrame()

    if pair_df is None or pair_df.empty:
        return offset_df.copy()

    join_keys = [
        "model",
        "glass_side",
        "glass_id",
        "tab",
        "bpi_aoi",
        "bpi_recipe_id",
        "bpi_scan_time",
        "api_aoi",
        "api_recipe_id",
        "api_scan_time",
    ]

    pair_keep_cols = join_keys + [
        "bpi_line_id",
        "bpi_cassette_id",
        "bpi_pi_time",
        "bpi_scan_hour",
        "bpi_run_day",
        "bpi_source_db",
        "bpi_source_table",

        "api_line_id",
        "api_cassette_id",
        "api_pi_time",
        "api_scan_hour",
        "api_run_day",
        "api_source_db",
        "api_source_table",

        "pair_status",
        "pair_message",
        "default_offset_um",
        "matched_points_json",

        "comment",
        "action",
        "editor",
        "modify_time",
        "gen_time",
    ]

    existing = [c for c in pair_keep_cols if c in pair_df.columns]

    out = offset_df.merge(
        pair_df[existing].drop_duplicates(subset=join_keys),
        on=join_keys,
        how="left",
    )

    return out


# =============================================================================
# Filter / Options
# =============================================================================
NO_SELECTION_TOKEN = "__NO_SELECTION__"


def _has_no_selection_filter(filters: Dict[str, List[str]]) -> bool:
    if not isinstance(filters, dict):
        return False

    for vals in filters.values():
        if not isinstance(vals, list):
            continue

        if any(str(v).strip() == NO_SELECTION_TOKEN for v in vals):
            return True

    return False

def _apply_filters(df: pd.DataFrame, filters: Dict[str, List[str]], sub_page: str) -> pd.DataFrame:
    if df is None or df.empty:
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()
    if _has_no_selection_filter(filters):
        return df.iloc[0:0].copy()
    out = df.copy()

    # sub_page 直接對應 tab
    if sub_page:
        out = out[out.apply(lambda r: _row_hits_sub_page(r, sub_page), axis=1)].copy()

    def _in_col(col: str, vals: List[str]):
        nonlocal out
        if col not in out.columns or not vals:
            return
        want = set(vals)
        out = out[out[col].astype(str).isin(want)].copy()

    def _in_any(cols: List[str], vals: List[str]):
        nonlocal out
        if not vals:
            return

        want = set(vals)
        mask = pd.Series(False, index=out.index)

        for c in cols:
            if c in out.columns:
                mask = mask | out[c].astype(str).isin(want)

        out = out[mask].copy()

    # 新版 filters
    _in_col("tab", filters.get("tab", []))
    _in_any(["bpi_aoi", "api_aoi"], filters.get("aoi", []))
    _in_col("bpi_aoi", filters.get("bpi_aoi", []))
    _in_col("api_aoi", filters.get("api_aoi", []))
    _in_col("model", filters.get("model", []))
    _in_col("glass_side", filters.get("glass_side", []))

    # 舊 recipe_id 相容：任一側命中即可。
    _in_any(["bpi_recipe_id", "api_recipe_id"], filters.get("recipe_id", []))
    _in_col("bpi_recipe_id", filters.get("bpi_recipe_id", []))
    _in_col("api_recipe_id", filters.get("api_recipe_id", []))

     # defect_size 不刪 row，只投影同點數值。
    out = _project_same_point_counts_by_size(out, filters)

    return out

def _build_filter_options(
    df: pd.DataFrame,
    filters: Dict[str, List[str]],
    sub_page: str,
) -> Dict[str, List[Any]]:
    """
    filter options 只依 date range + sub_page(tab) 產生。

    重要：
      不吃目前 filters。
      避免使用者勾選後 options 越變越少。
    """
    opt = {
        "tab": [],
        "aoi": [],
        "bpi_aoi": [],
        "api_aoi": [],
        "model": [],
        "recipe_id": [],
        "bpi_recipe_id": [],
        "api_recipe_id": [],
        "glass_side": [],
        "defect_size": ["S", "M", "L", "O"],
        "offset_um": list(range(5, 55, 5)),
    }

    if df is None or df.empty:
        return opt

    base = df.copy()

    # options 只卡目前子頁 PISpot / UPI / aoi100 / aoi300
    if sub_page:
        base = base[base.apply(lambda r: _row_hits_sub_page(r, sub_page), axis=1)].copy()

    if base.empty:
        return opt

    def _uniq(col: str) -> List[str]:
        if col not in base.columns:
            return []

        vals = (
            base[col]
            .dropna()
            .astype(str)
            .map(lambda x: x.strip())
            .unique()
            .tolist()
        )

        return sorted([
            x for x in vals
            if x and x.lower() not in {"nan", "none", "null", "nat", "<na>"}
        ])

    opt["tab"] = _uniq("tab")
    opt["bpi_aoi"] = _uniq("bpi_aoi")
    opt["api_aoi"] = _uniq("api_aoi")
    opt["model"] = _uniq("model")
    opt["glass_side"] = _uniq("glass_side")
    opt["bpi_recipe_id"] = _uniq("bpi_recipe_id")
    opt["api_recipe_id"] = _uniq("api_recipe_id")

    # 舊版相容：如果前端還有 aoi / recipe_id 這類混合欄位
    aoi_vals = []
    for c in ["bpi_aoi", "api_aoi"]:
        if c in base.columns:
            aoi_vals.extend(base[c].dropna().astype(str).map(lambda x: x.strip()).tolist())

    opt["aoi"] = sorted([
        x for x in set(aoi_vals)
        if x and x.lower() not in {"nan", "none", "null", "nat", "<na>"}
    ])

    recipe_vals = []
    for c in ["bpi_recipe_id", "api_recipe_id"]:
        if c in base.columns:
            recipe_vals.extend(base[c].dropna().astype(str).map(lambda x: x.strip()).tolist())

    opt["recipe_id"] = sorted([
        x for x in set(recipe_vals)
        if x and x.lower() not in {"nan", "none", "null", "nat", "<na>"}
    ])

    return opt

def _format_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []

    out = df.copy()

    for c in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[c]):
            out[c] = out[c].apply(lambda x: "" if pd.isna(x) else x.strftime("%Y-%m-%d %H:%M:%S"))

    for c in ["run_day", "bpi_run_day", "api_run_day"]:
        if c in out.columns:
            out[c] = pd.to_datetime(out[c], errors="coerce")
            out[c] = out[c].apply(lambda x: "" if pd.isna(x) else x.strftime("%Y-%m-%d"))

    out = out.fillna("")
    return out.to_dict(orient="records")


# =============================================================================
# reset_filter route
# =============================================================================
@router.post("/reset_filter")
async def reset_filter(payload: SamePointFilterIn):
    api_cfg = API_Config()

    start, end_excl = _date_range_to_scan_hour_range(payload.dates)
    offset_um = _normalize_offset(payload.offset_um, api_cfg.common_same_point_offsets)

    filters = _normalize_filters(payload.filters)
    sub_page = _normalize_sub_page(payload.sub_page)

    tab_key = _same_point_tab_key(sub_page)
    tab_conf = api_cfg.tab_filter_config.get(tab_key, {})

    db = MySQLConnet(api_cfg.bpi_same_point_db_name)

    # 新增：讀取 Same Point default spec
    pro_spec_dict = api_cfg.bpi_same_point_spec_table_process(db)

    pair_df = _read_pair_rows(
        db=db,
        api_cfg=api_cfg,
        start=start,
        end_excl=end_excl,
    )

    offset_df = _read_offset_rows(
        db=db,
        api_cfg=api_cfg,
        start=start,
        end_excl=end_excl,
        offset_um=offset_um,
    )

    merged = _merge_pair_offset(pair_df, offset_df)
    filtered = _apply_filters(merged, filters, sub_page)
    option_dict = _build_filter_options(merged, filters, sub_page)

    pair_filtered = pair_df.copy()
    if not pair_filtered.empty:
        pair_filtered = pair_filtered[
            pair_filtered.apply(lambda r: _row_hits_sub_page(r, sub_page), axis=1)
        ].copy()

    return {
        "ok": True,
        "PairData": _format_records(pair_filtered),
        "OffsetData": _format_records(filtered),
        "ChartRows": _format_records(filtered),
        "TableRows": _format_records(filtered),

        # 新增：給前端 default spec / spec line 使用
        "ProSpecDict": pro_spec_dict,

        "ParamDict": {
            "filterOptionDict": option_dict,
            "Config": {
                "db_name": api_cfg.bpi_same_point_db_name,
                "pair_table_tpl": api_cfg.bpi_same_point_pair_table_tpl,
                "offset_table_tpl": api_cfg.bpi_same_point_offset_table_tpl,
                "match_table_tpl": api_cfg.bpi_same_point_match_table_tpl,

                "tab_key": tab_key,
                "sub_page": sub_page,
                "same_point_page": tab_conf.get("same_point_page", sub_page),
                "section_id": tab_conf.get("section_id", "bpi-same-point-root"),
                "recipe_rule": tab_conf.get("recipe_rule", {}),

                "offsets": api_cfg.common_same_point_offsets,
                "default_offset": tab_conf.get("default_offset", 20),

                "filter_item_coldict": tab_conf.get("filter_item_coldict", {}),
                "cascade_order": tab_conf.get("cascade_order", []),
                "table_columns": tab_conf.get("table_columns", {}),
                "defect_map": tab_conf.get("defect_map", {}),

                "pair_key_cols": api_cfg.front_config.get("bpiSamePoint", {}).get("pair_key_cols", []),
                "manual_key_cols": api_cfg.front_config.get("bpiSamePoint", {}).get("manual_key_cols", []),
                "default_offset_field": "default_offset_um",
                "matched_points_field": "matched_points_json",
                "size_filter_logic": "bpi_or_api",
                "size_filter_fields": ["bpi_defect_size", "api_defect_size"],
            },
        },
        "Debug": {
            "start": start.strftime("%Y-%m-%d %H:%M:%S"),
            "end_exclusive": end_excl.strftime("%Y-%m-%d %H:%M:%S"),
            "offset_um": offset_um,
            "sub_page": sub_page,
            "tab_key": tab_key,
            "filters": filters,
            "pair_rows": int(len(pair_df)),
            "pair_filtered_rows": int(len(pair_filtered)),
            "offset_rows": int(len(offset_df)),
            "filtered_rows": int(len(filtered)),
        },
    }


# =============================================================================
# defect_map helpers
# =============================================================================
def _query_cim_raw_defects(row: Dict[str, Any], side: str) -> pd.DataFrame:
    """
    side = BPI / API
    依 pair row 內的 source table 查 CIM raw defects。
    若該端 aoi = aoi200，需額外卡 recipe_id，避免同片同時間多 recipe 混入。
    """
    prefix = side.lower()
    aoi = clean_text(row.get(f"{prefix}_aoi"))

    db_name = clean_text(row.get(f"{prefix}_source_db")) or "cim_piaoi"
    source_table = clean_text(row.get(f"{prefix}_source_table"))

    if not source_table:
        return pd.DataFrame()

    db = MySQLConnet(db_name)

    if not _table_exists(db, source_table):
        return pd.DataFrame()

    glass_id = clean_text(row.get("glass_id"))
    scan_time = parse_dt(row.get(f"{prefix}_scan_time"))
    recipe_id = clean_text(row.get(f"{prefix}_recipe_id"))

    if not glass_id or not scan_time:
        return pd.DataFrame()

    sql = f"""
    SELECT *
    FROM `{db.db}`.`{source_table}`
    WHERE `sheet_id_chip_id` = :glass_id
      AND `test_time` = :scan_time
    """

    params = {
        "glass_id": glass_id,
        "scan_time": scan_time,
    }

    df = _query_df(db, sql, params)

    if df.empty:
        return df

    if "defect_size" in df.columns:
        empty_mask = df["defect_size"].apply(_is_empty_like)
        logger.info(
            "[_query_cim_raw_defects] side=%s, aoi=%s, table=%s, rows=%s, empty_defect_size_rows=%s",
            side,
            aoi,
            source_table,
            len(df),
            int(empty_mask.sum()),
        )

    if aoi == "aoi200" and recipe_id and "recipe_id" in df.columns:
        df = df[df["recipe_id"].map(clean_text).eq(recipe_id)].copy()

    if df.empty:
        return pd.DataFrame()

    out = pd.DataFrame()
    out["x"] = pd.to_numeric(df.get("pox_x1"), errors="coerce")
    out["y"] = pd.to_numeric(df.get("pox_y1"), errors="coerce")

    # AOI200 特別規則：
    # defect_size 為 NULL / nan / null / 空字串 / 異常值時，一律補成 O
    out["defect_size"] = df.apply(
        lambda r: _normalize_defect_size_for_aoi(r.get("defect_size", ""), aoi),
        axis=1,
    )

    out["adc_def_code"] = df.get("adc_def_code", "").map(clean_text)
    out["retype_code"] = df.get("retype_def_code", "").map(clean_text)
    out["chip_id"] = df.get("chip_id", "").map(clean_text)
    out["pic_path"] = df.apply(
        lambda r: _normalize_cim_pic_path_for_row(
            db=db,
            row=r,
            aoi=aoi,
            glass_id=glass_id,
            scan_time=scan_time,
        ),
        axis=1,
    )
    out["pic_name"] = df.get("image_file_name", "").map(clean_text)
    out["source_table"] = source_table
    out["source_db"] = db.db
    out["mode"] = side.upper()

    out = out.dropna(subset=["x", "y"]).copy()
    out = out[out["defect_size"].astype(str).str.upper().isin(VALID_SIZE_ATOMS)]

    return out.reset_index(drop=True)


def _query_rtms_raw_defects(row: Dict[str, Any], side: str) -> pd.DataFrame:
    prefix = side.lower()

    db_name = clean_text(row.get(f"{prefix}_source_db")) or "rtms_piaoi_other"
    source_table = clean_text(row.get(f"{prefix}_source_table"))

    if not source_table:
        return pd.DataFrame()

    db = MySQLConnet(db_name)

    if not _table_exists(db, source_table):
        return pd.DataFrame()

    glass_id = clean_text(row.get("glass_id"))
    scan_time = parse_dt(row.get(f"{prefix}_scan_time"))
    recipe_id = clean_text(row.get(f"{prefix}_recipe_id"))

    if not glass_id or not scan_time:
        return pd.DataFrame()

    sql = f"""
    SELECT *
    FROM `{db.db}`.`{source_table}`
    WHERE `sheet_id_chip_id` = :glass_id
      AND `test_time` = :scan_time
    """

    df = _query_df(db, sql, {"glass_id": glass_id, "scan_time": scan_time})

    if df.empty:
        return df

    if recipe_id and "recipe_id" in df.columns:
        df = df[df["recipe_id"].map(clean_text).eq(recipe_id)].copy()

    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    df["defect_size_norm"] = df["defect_size"].map(clean_text).str.upper()
    df["defect_id_str"] = df["defect_id"].map(clean_text).str.upper()
    df["x_num"] = pd.to_numeric(df["pox_x1"], errors="coerce").fillna(0)
    df["y_num"] = pd.to_numeric(df["pox_y1"], errors="coerce").fillna(0)

    df = df[
        df["defect_size_norm"].isin(VALID_SIZE_ATOMS)
        & ~df["defect_id_str"].str.startswith("MACRO_", na=False)
        & df["defect_id_str"].ne("NO_DEFECT")
        & ~((df["x_num"] == 0) & (df["y_num"] == 0))
    ].copy()

    if df.empty:
        return pd.DataFrame()

    out = pd.DataFrame()
    out["x"] = pd.to_numeric(df.get("pox_x1"), errors="coerce")
    out["y"] = pd.to_numeric(df.get("pox_y1"), errors="coerce")
    out["defect_size"] = df.get("defect_size", "").map(clean_text)
    out["adc_def_code"] = df.get("adc_def_code", "").map(clean_text)
    out["retype_code"] = df.get("retype_def_code", "").map(clean_text)
    out["chip_id"] = df.get("chip_id", "").map(clean_text)
    out["pic_path"] = df.get("pic_path", "").map(_normalize_rtms_pic_path)
    out["pic_name"] = df.get("image_file_name", "").map(clean_text)
    out["source_table"] = source_table
    out["source_db"] = db.db
    out["mode"] = side.upper()

    out = out.dropna(subset=["x", "y"]).copy()
    return out.reset_index(drop=True)


def _query_full_raw_defects(row: Dict[str, Any], side: str) -> pd.DataFrame:
    side = side.upper()
    prefix = side.lower()
    aoi = clean_text(row.get(f"{prefix}_aoi"))

    if aoi in {"aoi100", "aoi200"}:
        return _query_cim_raw_defects(row, side)

    if aoi == "aoi300":
        return _query_rtms_raw_defects(row, side)

    return pd.DataFrame()


def _query_match_detail(row: Dict[str, Any], offset_um: int) -> pd.DataFrame:
    api_cfg = API_Config()
    db = MySQLConnet(api_cfg.bpi_same_point_db_name)

    scan_hour = parse_dt(row.get("scan_hour"))
    if not scan_hour:
        return pd.DataFrame()

    ym = scan_hour.strftime("%Y%m")
    tbn = api_cfg.bpi_same_point_match_table_tpl.replace("yyyymm", ym).lower()

    if not _table_exists(db, tbn):
        return pd.DataFrame()

    sql = f"""
    SELECT *
    FROM `{db.db}`.`{tbn}`
    WHERE `model` = :model
      AND `glass_side` = :glass_side
      AND `glass_id` = :glass_id
      AND `tab` = :tab
      AND `bpi_aoi` = :bpi_aoi
      AND `bpi_recipe_id` = :bpi_recipe_id
      AND `bpi_scan_time` = :bpi_scan_time
      AND `api_aoi` = :api_aoi
      AND `api_recipe_id` = :api_recipe_id
      AND `api_scan_time` = :api_scan_time
      AND `offset_um` = :offset_um
    ORDER BY `match_rank` ASC, `distance` ASC
    """

    params = {
        "model": clean_text(row.get("model")),
        "glass_side": clean_text(row.get("glass_side")),
        "glass_id": clean_text(row.get("glass_id")),
        "tab": clean_text(row.get("tab")),
        "bpi_aoi": clean_text(row.get("bpi_aoi")),
        "bpi_recipe_id": clean_text(row.get("bpi_recipe_id")),
        "bpi_scan_time": parse_dt(row.get("bpi_scan_time")),
        "api_aoi": clean_text(row.get("api_aoi")),
        "api_recipe_id": clean_text(row.get("api_recipe_id")),
        "api_scan_time": parse_dt(row.get("api_scan_time")),
        "offset_um": int(offset_um),
    }

    return _query_df(db, sql, params)


def _matched_points_json_to_df(row: Dict[str, Any], offset_um: int) -> pd.DataFrame:
    raw = clean_text(row.get("matched_points_json", ""))
    if not raw:
        return pd.DataFrame()

    try:
        data = json.loads(raw)
    except Exception:
        return pd.DataFrame()

    if not isinstance(data, list) or not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)

    if df.empty:
        return df

    if "offset_um" in df.columns:
        df = df[pd.to_numeric(df["offset_um"], errors="coerce").fillna(-1).astype(int).eq(int(offset_um))].copy()

    return df.reset_index(drop=True)


def _format_df(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []

    out = df.copy()

    for c in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[c]):
            out[c] = out[c].apply(lambda x: "" if pd.isna(x) else x.strftime("%Y-%m-%d %H:%M:%S"))

    for c in ["run_day"]:
        if c in out.columns:
            out[c] = pd.to_datetime(out[c], errors="coerce")
            out[c] = out[c].apply(lambda x: "" if pd.isna(x) else x.strftime("%Y-%m-%d"))

    out = out.fillna("")
    return out.to_dict(orient="records")


# =============================================================================
# defect_map route
# =============================================================================
@router.post("/defect_map")
async def defect_map(payload: SamePointDefectMapIn):
    mode = clean_text(payload.mode).upper() or "MATCH"
    offset_um = _normalize_offset(payload.offset_um)
    row = payload.row or {}
    size_filter = payload.size_filter or []

    if mode == "BPI":
        df = _query_full_raw_defects(row, "BPI")
        df = _filter_match_df_by_size(df, size_filter)
        return {
            "ok": True,
            "mode": "BPI",
            "DefectRows": _format_df(df),
            "MatchRows": [],
        }

    if mode == "API":
        df = _query_full_raw_defects(row, "API")
        df = _filter_match_df_by_size(df, size_filter)
        return {
            "ok": True,
            "mode": "API",
            "DefectRows": _format_df(df),
            "MatchRows": [],
        }

    if mode == "MATCH":
        default_offset = _safe_int(row.get("default_offset_um"), 20)

        # default offset 優先使用 pair.matched_points_json，避免每次切 size 都查 DB。
        if int(offset_um) == int(default_offset):
            df = _matched_points_json_to_df(row, offset_um)
        else:
            df = pd.DataFrame()

        # 非 default offset 或 json 無資料時，查 match_detail table。
        if df.empty:
            df = _query_match_detail(row, offset_um)

        # 保險：將 AOI200 空 size 補成 O，兼容舊資料
        df = _normalize_match_size_cols(df, row)

        df = _filter_match_df_by_size(df, size_filter)

        return {
            "ok": True,
            "mode": "MATCH",
            "offset_um": offset_um,
            "DefectRows": [],
            "MatchRows": _format_df(df),
            "source": "matched_points_json" if int(offset_um) == int(default_offset) and clean_text(row.get("matched_points_json")) else "match_detail",
        }

    raise HTTPException(status_code=400, detail=f"unsupported mode: {mode}")