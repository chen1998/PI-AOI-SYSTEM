# routers/piaoi/density/date_reset.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta

import pandas as pd
import json

from models.sql_db_connect import MySQLConnet
from models.piaoi.density.cim_density_job import Config as DensityJobConfig
from models.piaoi.density.API_Config import API_Config


router = APIRouter(tags=["duty_cell_piaoi_aoi_density"])


# =============================================================================
# Time helpers
# =============================================================================
def _parse_date_only(s: str) -> datetime:
    s = str(s).strip().replace("T", " ")
    fmts = ["%Y-%m-%d", "%y-%m-%d"]

    for f in fmts:
        try:
            dt = datetime.strptime(s, f)
            return dt.replace(hour=0, minute=0, second=0, microsecond=0)
        except ValueError:
            continue

    raise ValueError(f"Bad date: {s}")


def _month_span(start: datetime, end: datetime) -> List[str]:
    ym: List[str] = []

    cur = datetime(start.year, start.month, 1)
    last = datetime(end.year, end.month, 1)

    while cur <= last:
        ym.append(cur.strftime("%Y%m"))
        cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)

    return ym


def _compute_default_range(now: datetime) -> Tuple[datetime, datetime]:
    """
    預設查詢：
      起點：往前 3 天 07:00
      終點：目前所屬 pi_hour bucket
    """
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


def _date_range_to_pi_hour_query_range(
    start_date: datetime,
    end_date: datetime,
) -> Tuple[datetime, datetime]:
    """
    前端日期語意:
      D = [D 07:30, D+1 07:30)

    查 pi_hour:
      [D 07:00, D+1 07:00)
    """
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


def _format_pi_hour_for_key(v: Any) -> str:
    try:
        ts = pd.to_datetime(v, errors="coerce")
        if pd.isna(ts):
            return str(v)
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(v)


# =============================================================================
# density Data helpers
# =============================================================================
def _to_size_mask(row) -> int:
    mask = 0

    try:
        if float(row.get("small_defect_count", 0) or 0) > 0:
            mask |= 1
        if float(row.get("middle_defect_count", 0) or 0) > 0:
            mask |= 2
        if float(row.get("large_defect_count", 0) or 0) > 0:
            mask |= 4
        if float(row.get("over_defect_count", 0) or 0) > 0:
            mask |= 8
    except Exception:
        pass

    return mask


def _ensure_required_cols(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    out = df.copy()

    numeric_cols = {
        "recipe_total_defect_cnt",
        "recipe_total_glass_cnt",
        "recipe_total_density",
        "recipe_raw_defect_cnt",
        "recipe_total_defect_gap",

        "tab_total_glass_cnt",
        "tab_total_defect_cnt",
        "tab_total_density",
        "tab_raw_defect_cnt",
        "tab_total_defect_gap",

        "defect_cnt",
        "def_glass_cnt",
        "glass_cnt",
        "recipe_code_density",
        "density",

        "small_defect_count",
        "middle_defect_count",
        "large_defect_count",
        "over_defect_count",

        "size_mask",
    }

    for c in cols:
        if c not in out.columns:
            out[c] = 0 if c in numeric_cols else ""

    return out


def _normalize_code_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()

    out = df.copy()

    numeric_cols = [
        "recipe_total_defect_cnt",
        "recipe_total_glass_cnt",
        "recipe_total_density",
        "recipe_raw_defect_cnt",
        "recipe_total_defect_gap",

        "defect_cnt",
        "def_glass_cnt",
        "glass_cnt",
        "recipe_code_density",
        "density",

        "small_defect_count",
        "middle_defect_count",
        "large_defect_count",
        "over_defect_count",
    ]

    for c in numeric_cols:
        if c not in out.columns:
            out[c] = 0

        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)

    return out


def _normalize_tab_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()

    out = df.copy()

    numeric_cols = [
        "tab_total_glass_cnt",
        "tab_total_defect_cnt",
        "tab_total_density",
        "tab_raw_defect_cnt",
        "tab_total_defect_gap",
    ]

    for c in numeric_cols:
        if c not in out.columns:
            out[c] = 0

        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)

    return out


def _recipe_id_to_backend_tabs(recipe_id: Any, aoi: Any = "") -> List[str]:
    """
    與 cim_density_job.py 的 recipe_id_to_tabs() 同步。

    新需求：
      aoi100 / aoi300 的 API 資料一律出現在所有 tab。

    其他 AOI：
      4碼 2/3 -> UPI, UPI_Total
      4碼 0/1 -> PISpot, PISpot_Total, SPS
      3碼 -> all tabs
    """
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

def _recipe_id_match_family(recipe_id: Any, recipe_family: str) -> bool:
    s = str(recipe_id or "").strip()
    fam = str(recipe_family or "").strip()

    if not s:
        return False

    # 3碼 recipe：所有 family 都可出現
    if len(s) == 3:
        return True

    # 4碼 recipe：依 family 分
    if len(s) == 4:
        if fam == "UPI":
            return s.startswith(("2", "3"))

        if fam in {"PISpot", "SPS"}:
            return s.startswith(("0", "1"))

    return False

def _build_recipe_dict(option_recipe_ids: List[str], code_df: Optional[pd.DataFrame] = None) -> Dict[str, List[str]]:
    """
    依 recipe_id 分群填回各分頁預設。

    若有 code_df，會同時參考 aoi，確保 aoi100/aoi300 的 recipe 出現在所有 tab。
    """
    recipe_dict = {
        "UPI": [],
        "PISpot": [],
        "SPS": [],
    }

    if code_df is not None and not code_df.empty and {"recipe_id", "aoi"}.issubset(set(code_df.columns)):
        pairs = (
            code_df[["recipe_id", "aoi"]]
            .fillna("")
            .astype(str)
            .drop_duplicates()
            .to_dict("records")
        )

        for r in pairs:
            recipe_id = str(r.get("recipe_id", "") or "").strip()
            aoi = str(r.get("aoi", "") or "").strip()

            if not recipe_id:
                continue

            tabs = _recipe_id_to_backend_tabs(recipe_id=recipe_id, aoi=aoi)

            if "UPI" in tabs:
                recipe_dict["UPI"].append(recipe_id)

            if "PISpot" in tabs:
                recipe_dict["PISpot"].append(recipe_id)

            if "SPS" in tabs:
                recipe_dict["SPS"].append(recipe_id)

    else:
        for v in option_recipe_ids or []:
            s = str(v or "").strip()

            if not s:
                continue

            tabs = _recipe_id_to_backend_tabs(recipe_id=s, aoi="")

            if "UPI" in tabs:
                recipe_dict["UPI"].append(s)

            if "PISpot" in tabs:
                recipe_dict["PISpot"].append(s)

            if "SPS" in tabs:
                recipe_dict["SPS"].append(s)

    for k, arr in recipe_dict.items():
        seen = set()
        dedup = []

        for x in arr:
            if x in seen:
                continue

            seen.add(x)
            dedup.append(x)

        recipe_dict[k] = dedup

    return recipe_dict


def _tab_total_key_from_values(
    pi_hour,
    line_id,
    aoi,
    model,
    glass_type,
) -> str:
    return "||".join([
        _format_pi_hour_for_key(pi_hour),
        str(line_id),
        str(aoi),
        str(model),
        str(glass_type),
    ])


def _build_tab_total_dict(tab_df: pd.DataFrame) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    使用 density_tab_summary_yyyymm 建立 TabTotalDict。
    """
    empty = {
        "UPI": {},
        "UPI_Total": {},
        "PISpot": {},
        "PISpot_Total": {},
        "SPS": {},
    }

    if tab_df is None or tab_df.empty:
        return empty

    df = _normalize_tab_columns(tab_df)

    need_cols = [
        "pi_hour",
        "line_id",
        "aoi",
        "model",
        "glass_type",
        "tab_name",
        "tab_total_glass_cnt",
        "tab_total_defect_cnt",
        "tab_total_density",
    ]

    miss = [c for c in need_cols if c not in df.columns]

    if miss:
        return empty

    out: Dict[str, Dict[str, Dict[str, Any]]] = {k: {} for k in empty.keys()}

    for _, r in df.iterrows():
        tab = str(r.get("tab_name", "") or "").strip()

        if not tab:
            continue

        if tab not in out:
            out[tab] = {}

        key = _tab_total_key_from_values(
            r["pi_hour"],
            r["line_id"],
            r["aoi"],
            r["model"],
            r["glass_type"],
        )

        out[tab][key] = {
            "tab_total_glass_cnt": int(r.get("tab_total_glass_cnt", 0) or 0),
            "tab_total_defect_cnt": int(r.get("tab_total_defect_cnt", 0) or 0),
            "tab_total_density": float(r.get("tab_total_density", 0) or 0),
            "tab_raw_defect_cnt": int(r.get("tab_raw_defect_cnt", 0) or 0),
            "tab_total_defect_gap": int(r.get("tab_total_defect_gap", 0) or 0),
            "recipe_family": str(r.get("recipe_family", "") or ""),
            "recipe_list": str(r.get("recipe_list", "") or ""),
            "glass": str(r.get("glass", "") or ""),
        }

    return out


def _apply_recipe_dict_to_subtabs(
    param_dict: Dict[str, Any],
    recipe_dict: Dict[str, List[str]],
) -> Dict[str, Any]:
    """
    將 recipe family 寫回 SubTabsFilterDefaultDict。
    """
    subtabs = param_dict.get("SubTabsFilterDefaultDict", {})

    mapping = {
        "UPI": "UPI",
        "UPI(Total)": "UPI",
        "PISpot": "PISpot",
        "PISpot(Total)": "PISpot",
        "SPS": "SPS",
    }

    for tab_key, recipe_key in mapping.items():
        if tab_key in subtabs:
            subtabs[tab_key]["recipe_id"] = recipe_dict.get(recipe_key, [])

    return param_dict

def _days_between(start: datetime, end_exclusive: datetime) -> int:
    return max(1, int((end_exclusive - start).total_seconds() // 86400))


def _first_existing_value(df: pd.DataFrame, col: str) -> str:
    if df is None or df.empty or col not in df.columns:
        return ""

    vals = (
        df[col]
        .fillna("")
        .astype(str)
        .map(str.strip)
    )

    vals = vals[vals != ""].drop_duplicates().sort_values().tolist()
    return vals[0] if vals else ""


def _filter_df_by_selected(df: pd.DataFrame, selected: Dict[str, List[str]]) -> pd.DataFrame:
    out = df.copy()

    for col, vals in selected.items():
        if col not in out.columns:
            continue

        vals = [str(v).strip() for v in vals if str(v).strip()]
        if not vals:
            continue

        out = out[out[col].fillna("").astype(str).isin(vals)].copy()

        if out.empty:
            break

    return out

def _unique_sorted(df: pd.DataFrame, col: str) -> List[str]:
    if df is None or df.empty or col not in df.columns:
        return []

    return (
        df[col]
        .fillna("")
        .astype(str)
        .map(str.strip)
        .loc[lambda s: s != ""]
        .drop_duplicates()
        .sort_values()
        .tolist()
    )


def _filter_by_values(df: pd.DataFrame, col: str, vals: List[str]) -> pd.DataFrame:
    if df is None or df.empty or col not in df.columns:
        return df

    vals = [str(v).strip() for v in vals if str(v).strip()]
    if not vals:
        return df

    return df[df[col].fillna("").astype(str).isin(vals)].copy()


def _build_dynamic_filter_config(
    clean_df: pd.DataFrame,
    param_dict: Dict[str, Any],
    start: datetime,
    end_exclusive: datetime,
    api_cfg: API_Config,
) -> Tuple[Dict[str, Dict[str, List[str]]], Dict[str, Dict[str, List[str]]]]:
    """
    回傳：
      1) DefaultFilterDict：每個 tab 預設勾選值
      2) DynamicFilterOptionDict：每個 tab 專用 options

    日期 > 3 天規則：
      line_id：API_Config 預設
      aoi：只選 aoi200
      model：line_id + aoi200 + tab 下有 run 的第一個 model
      glass_type：line_id + aoi200 + model 下有 run 的 glass_type 全選
      recipe_id：
        option：符合 tab recipe_family 的 recipe
        selected：line_id + aoi200 + model + glass_type 下有 run 的 recipe
      adc_def_code：照 API_Config tab 設定
      defect_size：全選
    """
    default_dict: Dict[str, Dict[str, List[str]]] = {}
    option_dict: Dict[str, Dict[str, List[str]]] = {}

    if clean_df is None or clean_df.empty:
        return default_dict, option_dict

    days = _days_between(start, end_exclusive)

    # 只在日期 > 3 天時建立動態預設
    if days <= 3:
        return default_dict, option_dict

    target_tabs = {
        "UPI",
        "UPI(Total)",
        "PISpot",
        "PISpot(Total)",
        "SPS",
    }

    subtabs = param_dict.get("SubTabsFilterDefaultDict", {}) or {}

    for tab_name in target_tabs:
        tab_cfg = subtabs.get(tab_name, {})
        if not tab_cfg:
            continue

        backend_tab = str(tab_cfg.get("backend_tab_name", tab_name)).strip()
        recipe_family = str(tab_cfg.get("recipe_family", "")).strip()

        df_tab = clean_df.copy()

        # 先限制到目前分頁的 backend tab
        if "tab_name" in df_tab.columns and backend_tab:
            df_tab = df_tab[df_tab["tab_name"].fillna("").astype(str) == backend_tab].copy()

        if df_tab.empty:
            continue

        # recipe option 先用 recipe_family 過濾，避免 UPI 出現 0xxx
        if "recipe_id" in df_tab.columns and recipe_family:
            df_tab = df_tab[
                df_tab["recipe_id"].apply(
                    lambda x: _recipe_id_match_family(x, recipe_family)
                )
            ].copy()

        if df_tab.empty:
            continue

        selected: Dict[str, List[str]] = {}
        options: Dict[str, List[str]] = {}

        # -----------------------------------------------------
        # 1) line_id：維持 API_Config.py 預設
        # -----------------------------------------------------
        cfg_lines = [
            str(x).strip()
            for x in (tab_cfg.get("line_id", []) or [])
            if str(x).strip()
        ]

        existing_lines = _unique_sorted(df_tab, "line_id")
        line_selected = [x for x in cfg_lines if x in existing_lines]

        if not line_selected and existing_lines:
            line_selected = [existing_lines[0]]

        selected["line_id"] = line_selected
        options["line_id"] = existing_lines

        df_line = _filter_by_values(df_tab, "line_id", line_selected)

        if df_line.empty:
            default_dict[tab_name] = selected
            option_dict[tab_name] = options
            continue

        # -----------------------------------------------------
        # 2) aoi：日期 > 3 天只預設 aoi200
        # -----------------------------------------------------
        existing_aoi = _unique_sorted(df_line, "aoi")
        options["aoi"] = existing_aoi

        if "aoi200" in existing_aoi:
            selected["aoi"] = ["aoi200"]
        elif existing_aoi:
            selected["aoi"] = [existing_aoi[0]]
        else:
            selected["aoi"] = []

        df_aoi = _filter_by_values(df_line, "aoi", selected["aoi"])

        if df_aoi.empty:
            default_dict[tab_name] = selected
            option_dict[tab_name] = options
            continue

        # -----------------------------------------------------
        # 3) model：
        #    option = line_id + aoi200 下全部有 run 的 model
        #    selected = 第一個 model
        # -----------------------------------------------------
        model_options = _unique_sorted(df_aoi, "model")
        options["model"] = model_options
        selected["model"] = [model_options[0]] if model_options else []

        df_model = _filter_by_values(df_aoi, "model", selected["model"])

        # -----------------------------------------------------
        # 4) glass_type：
        #    option = line_id + aoi200 下全部有 run 的 glass_type
        #    selected = line_id + aoi200 + model 下有 run 的 glass_type
        # -----------------------------------------------------
        options["glass_type"] = _unique_sorted(df_aoi, "glass_type")
        selected["glass_type"] = _unique_sorted(df_model, "glass_type")

        df_glass = _filter_by_values(df_model, "glass_type", selected["glass_type"])

        # -----------------------------------------------------
        # 5) recipe_id：
        #    option = line_id + aoi200 + recipe_family 下全部 recipe
        #    selected = line_id + aoi200 + model + glass_type 下有 run 的 recipe
        # -----------------------------------------------------
        options["recipe_id"] = _unique_sorted(df_aoi, "recipe_id")
        selected["recipe_id"] = _unique_sorted(df_glass, "recipe_id")

        # -----------------------------------------------------
        # 6) adc_def_code：
        #    option = 該 tab 下全部 code
        #    selected = API_Config.py tab_filter_config 設定
        # -----------------------------------------------------
        code_options = _unique_sorted(df_tab, "adc_def_code")
        cfg_codes = [
            str(x).strip()
            for x in (tab_cfg.get("adc_def_code", []) or [])
            if str(x).strip()
        ]

        options["adc_def_code"] = code_options
        selected["adc_def_code"] = [
            x for x in cfg_codes
            if not code_options or x in code_options
        ]

        # -----------------------------------------------------
        # 7) defect_size：永遠全選
        # -----------------------------------------------------
        options["defect_size"] = api_cfg.uni_defect_sizes[:]
        selected["defect_size"] = api_cfg.uni_defect_sizes[:]

        default_dict[tab_name] = selected
        option_dict[tab_name] = options

    return default_dict, option_dict



def _merge_tab_total_to_code_df(
    code_df: pd.DataFrame,
    tab_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    將 density_tab_summary 的 tab total 欄位 merge 回 code summary。

    注意：
      一筆 code row 可能對應多個 tab。
      例如 aoi100/aoi300 會展開到所有 tab。
      merge 後 DictData row 數可能增加。
    """
    if code_df is None or code_df.empty:
        return pd.DataFrame()

    base_keys = ["pi_hour", "line_id", "aoi", "model", "glass_type"]

    out = code_df.copy()

    for c in base_keys + ["recipe_id"]:
        if c not in out.columns:
            out[c] = ""

    out["__tabs"] = out.apply(
        lambda r: _recipe_id_to_backend_tabs(
            recipe_id=r.get("recipe_id", ""),
            aoi=r.get("aoi", ""),
        ),
        axis=1,
    )

    out = out.explode("__tabs").rename(columns={"__tabs": "tab_name"})
    out = out.dropna(subset=["tab_name"])
    out["tab_name"] = out["tab_name"].astype(str).str.strip()
    out = out[out["tab_name"].astype(str).str.len() > 0].copy()

    if out.empty:
        return out

    tab_cols = base_keys + [
        "tab_name",
        "recipe_family",
        "tab_total_glass_cnt",
        "tab_total_defect_cnt",
        "tab_total_density",
        "tab_raw_defect_cnt",
        "tab_total_defect_gap",
    ]

    if tab_df is None or tab_df.empty:
        for c in tab_cols:
            if c not in out.columns:
                out[c] = 0 if c.startswith("tab_") else ""

        return out

    t = tab_df.copy()

    for c in tab_cols:
        if c not in t.columns:
            t[c] = 0 if c.startswith("tab_") else ""

    for c in base_keys + ["tab_name"]:
        t[c] = t[c].astype(str)
        out[c] = out[c].astype(str)

    t = t[tab_cols].drop_duplicates(subset=base_keys + ["tab_name"])

    out = out.merge(
        t,
        on=base_keys + ["tab_name"],
        how="left",
    )

    numeric_cols = [
        "tab_total_glass_cnt",
        "tab_total_defect_cnt",
        "tab_total_density",
        "tab_raw_defect_cnt",
        "tab_total_defect_gap",
    ]

    for c in numeric_cols:
        if c not in out.columns:
            out[c] = 0

        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)

    if "recipe_family" not in out.columns:
        out["recipe_family"] = ""

    out["recipe_family"] = out["recipe_family"].fillna("").astype(str)

    return out


# =============================================================================
# Main API
# =============================================================================


@router.get("/reset_summary_filter")
async def reset_summary_filter(
    dates: Optional[List[str]] = Query(
        None,
        description="['YYYY-MM-DD', 'YYYY-MM-DD']",
    )
):
    cim_job_cfg = DensityJobConfig()
    api_cfg = API_Config(cim_job_cfg)
    dbhandler = MySQLConnet(cim_job_cfg.out_db)

    # -----------------------
    # Spec table
    # -----------------------
    try:
        spec_table_dict = api_cfg.spec_table_process(dbhandler)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"spec_table_process failed: {e}")

    # -----------------------
    # Date range
    # -----------------------
    if dates and len(dates) == 2:
        try:
            start_date = _parse_date_only(dates[0])
            end_date = _parse_date_only(dates[1])
            start, end_exclusive = _date_range_to_pi_hour_query_range(start_date, end_date)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Bad dates: {dates} ({e})")
    else:
        start, end_exclusive = _compute_default_range(api_cfg.now)

    # 保留原本多抓一天
    end_exclusive = end_exclusive #+ timedelta(days=1)

    months = _month_span(start, end_exclusive - timedelta(hours=1))

    print(f"[Density] 撈取資料(pi_hour): [{start} ~ {end_exclusive}) months={months}")

    # -----------------------
    # Load code summary + tab summary
    # -----------------------
    code_frames: List[pd.DataFrame] = []
    tab_frames: List[pd.DataFrame] = []

    optionDict: Dict[str, List[str]] = {
        k: [] for k in api_cfg.filter_item_coldict.keys()
    }

    optionDict["defect_size"] = api_cfg.uni_defect_sizes[:]

    for ym in months:
        code_tbn = cim_job_cfg.code_table_tpl.replace("yyyymm", ym).lower()
        tab_tbn = cim_job_cfg.tab_table_tpl.replace("yyyymm", ym).lower()

        # -----------------------
        # code summary
        # -----------------------
        if dbhandler.table_exists(code_tbn):
            code_df = dbhandler.get_runs_between(
                code_tbn,
                start,
                end_exclusive,
                time_col="pi_hour",
            )

            if code_df is not None and not code_df.empty:
                print(
                    f"[Density] code table:{code_tbn}, rows:{len(code_df)}, "
                    f"{min(code_df['pi_hour'])} ~ {max(code_df['pi_hour'])}"
                )

                code_df = code_df.copy()
                code_frames.append(code_df)

                for key in api_cfg.filter_item_coldict.keys():
                    if key in code_df.columns and key != "defect_size":
                        uniq = code_df[key].fillna("").astype(str).unique().tolist()
                        optionDict[key].extend([
                            v for v in uniq
                            if v not in optionDict[key] and v != ""
                        ])
            else:
                print(f"[Density] code table:{code_tbn}, rows:0")
        else:
            print(f"[Density] missing code table:{code_tbn}")

        # -----------------------
        # tab summary
        # -----------------------
        if dbhandler.table_exists(tab_tbn):
            tab_df = dbhandler.get_runs_between(
                tab_tbn,
                start,
                end_exclusive,
                time_col="pi_hour",
            )

            if tab_df is not None and not tab_df.empty:
                print(
                    f"[Density] tab table:{tab_tbn}, rows:{len(tab_df)}, "
                    f"{min(tab_df['pi_hour'])} ~ {max(tab_df['pi_hour'])}"
                )
                tab_frames.append(tab_df.copy())
            else:
                print(f"[Density] tab table:{tab_tbn}, rows:0")
        else:
            print(f"[Density] missing tab table:{tab_tbn}")

    if code_frames:
        clean_df = pd.concat(code_frames, ignore_index=True)
    else:
        clean_df = pd.DataFrame(columns=api_cfg.aoi_density_summary_sql_cols)

    if tab_frames:
        tab_df_all = pd.concat(tab_frames, ignore_index=True)
    else:
        tab_df_all = pd.DataFrame(columns=api_cfg.aoi_density_tab_sql_cols)

    # -----------------------
    # Normalize
    # -----------------------
    clean_df = _normalize_code_columns(clean_df)
    tab_df_all = _normalize_tab_columns(tab_df_all)

    # -----------------------
    # Merge tab total to code rows
    # -----------------------
    clean_df = _merge_tab_total_to_code_df(clean_df, tab_df_all)

    # merge 後補 tab_name / recipe_family 到 optionDict
    for key in api_cfg.filter_item_coldict.keys():
        if key in clean_df.columns and key != "defect_size":
            uniq = clean_df[key].fillna("").astype(str).unique().tolist()
            optionDict[key].extend([
                v for v in uniq
                if v not in optionDict[key] and v != ""
            ])

    # -----------------------
    # size_mask
    # -----------------------
    if not clean_df.empty:
        clean_df["size_mask"] = clean_df.apply(_to_size_mask, axis=1).astype(int)
    else:
        clean_df["size_mask"] = pd.Series([], dtype="int64")

    # -----------------------
    # TabTotalDict from tab summary table
    # -----------------------
    tab_total_dict = _build_tab_total_dict(tab_df_all)

    # -----------------------
    # Ensure API cols
    # -----------------------
    clean_df = _ensure_required_cols(clean_df, api_cfg.aoi_density_summary_api_cols)

    # -----------------------
    # front_config
    # -----------------------
    param_dict = dict(api_cfg.front_config)
    param_dict["filterOptionDict"] = optionDict

    dynamic_default_filter_dict, dynamic_option_dict = _build_dynamic_filter_config(
        clean_df=clean_df,
        param_dict=param_dict,
        start=start,
        end_exclusive=end_exclusive,
        api_cfg=api_cfg,
    )

    param_dict["DefaultFilterDict"] = dynamic_default_filter_dict
    param_dict["DynamicFilterOptionDict"] = dynamic_option_dict

    # -----------------------
    # recipe options for sub tabs
    # -----------------------
    recipe_dict = _build_recipe_dict(
        option_recipe_ids=optionDict.get("recipe_id", []),
        code_df=clean_df,
    )

    #param_dict = _apply_recipe_dict_to_subtabs(param_dict, recipe_dict)

    # -----------------------
    # Return
    # -----------------------
    df = clean_df[api_cfg.aoi_density_summary_api_cols].copy()
    df = df.fillna("")

    data = df.to_dict(orient="records")

    tab_summary_data = tab_df_all.fillna("").to_dict(orient="records")

    return {
        "DictData": data,
        "TabSummaryData": tab_summary_data,
        "TabTotalDict": tab_total_dict,
        "ParamDict": param_dict,
        "ProSpecDict": spec_table_dict,
        "Debug": {
            "recipe_dict": recipe_dict,
            "dynamic_default_filter_dict": dynamic_default_filter_dict,
            "option_recipe_count": len(optionDict.get("recipe_id", [])),
            "code_rows": len(clean_df),
            "tab_rows": len(tab_df_all),
            "months": months,
            "query_start": start.strftime("%Y-%m-%d %H:%M:%S"),
            "query_end_exclusive": end_exclusive.strftime("%Y-%m-%d %H:%M:%S"),
        },
            }