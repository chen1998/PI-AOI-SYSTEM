
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
import copy
import json

import pandas as pd

try:
    from PI_SYSTEM.models.inspection_density.sql_db_connect2 import MySQLConnetFunc
except Exception:
    try:
        from models.inspection_density.sql_db_connect2 import MySQLConnetFunc
    except Exception:
        from sql_db_connect2 import MySQLConnetFunc


# =========================================================
# Core-aligned shared config for API layer
# =========================================================
class InspectionDensityCoreConfig:
    def __init__(self):
        self.SOURCE_DB = "l6a01_project"
        self.TARGET_DB = "piaoi_inspection_density"

        self.SUMMARY_BASE_TBN = "inspection_summary_table"
        self.RAW_BASE_TBN = "inspection_raw_table"
        self.API_SUMMARY_BASE_TBN = "inspection_api_summary"
        self.API_GLASS_DETAIL_BASE_TBN = "inspection_api_glass_detail"

        # 與 core.py 對齊
        self.SHIFT_BUCKET_OFFSET_MINUTES = 30
        self.SHIFT_DAY_START_HOUR = 7
        self.SHIFT_DAY_START_MINUTE = 30


class InspectionDensityTableNamer:
    def __init__(self, cfg: InspectionDensityCoreConfig):
        self.cfg = cfg

    def summary_table(self, yyyymm: str) -> str:
        return f"{self.cfg.SUMMARY_BASE_TBN}_{yyyymm}"

    def raw_table(self, yyyymm: str) -> str:
        return f"{self.cfg.RAW_BASE_TBN}_{yyyymm}"

    def api_summary_table(self, yyyymm: str) -> str:
        return f"{self.cfg.API_SUMMARY_BASE_TBN}_{yyyymm}"

    def api_glass_detail_table(self, yyyymm: str) -> str:
        return f"{self.cfg.API_GLASS_DETAIL_BASE_TBN}_{yyyymm}"


class InspectionDensityApiConfig:
    def __init__(self):
        self.now = datetime.now()

        self.core_cfg = InspectionDensityCoreConfig()
        self.tables = InspectionDensityTableNamer(self.core_cfg)

        # =====================================================
        # DB / table
        # =====================================================
        self.db_name = self.core_cfg.TARGET_DB
        self.api_summary_table_tpl = "inspection_api_summary_yyyymm"
        self.default_spec_table_name = "default_spec_table"

        # =====================================================
        # base domain options
        # =====================================================
        self.uni_pi_names = [f"CAPIC{i}07" for i in range(1, 8)]
        self.glass_sides = ["CF", "TFT"]
        self.uni_defect_sizes = ["S", "M", "L", "O"]
        self.size_group_keys = ["S", "MS", "LMS", "O", "OL", "OLM", "OLMS"]
        # =====================================================
        # summary table cols
        # =====================================================
        self.api_summary_cols = [
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
            "maingroup_density",
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

        self.api_summary_output_cols = [
            "pi_hour",
            "line_id",
            "model",
            "glass_type",
            "maingroup_glass_count",
            "maingroup_defect_count",
            "maingroup_density",
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

        self.primary_group_cols = ["pi_hour", "line_id", "model", "glass_type"]

        self.action_his_keys = [
                                "pi_hour",
                                "line_id",
                                "model",
                                "glass_type",
                                "comment",
                                "action",
                                "Editor",
                                "modify_time",
                            ]
        # =====================================================
        # filter config
        # =====================================================
        self.filter_item_coldict = {
            "line_id": "PI Line",
            "model": "Model",
            "glass_type": "glass_side",
            "defect_size": "defect size",
        }

        self.filter_config = {
            "line_id": [],
            "model": [],
            "glass_type": ["TFT"],
            "defect_size": ["M", "L", "O"],
        }

        # =====================================================
        # chart / table / front display config
        # =====================================================
        self.chart_group_dict = {
            "left": ["line_id", "model", "maingroup_glass_count", "defect_code_glass_count"],
            "down": ["pi_hour"],
            "right": ["density"],
        }

        self.chart_table_coldict = {
            "line_id": "PI Line",
            "model": "Model",
            "glass_type": "side",
            "pi_hour": "Hourly",
            "maingroup_glass_count": "total gld",
            "maingroup_defect_count": "total def",
            "defect_code_glass_count": "defect gld",
            "glass": "glass",
            "small_defect_count": "S",
            "middle_defect_count": "M",
            "large_defect_count": "L",
            "over_defect_count": "O",
        }

        self.table_group_key_dict = {
            "main_group": [
                "pi_hour",
                "line_id",
                "model",
                "glass_type",
                "maingroup_glass_count",
                "maingroup_defect_count",
                "maingroup_density",
                "defect_code_glass_count",
                "comment",
                "action",
                "Editor",
                "modify_time",
            ],
            "uni_col": [
                "glass",
            ],
        }

        self.uni_glass_row_info_dict = {
            "glass_id": "glass",
            "small_defect_count": "S",
            "middle_defect_count": "M",
            "large_defect_count": "L",
            "over_defect_count": "O",
        }

        self.defect_group_coldict = {
            "COORD_X": "x",
            "COORD_Y": "y",
            "IMG_URL": "img",
        }

        # =====================================================
        # SubTabs config
        # =====================================================
        self.tab_filter_config = {
            "hourly": {
                "type": "",
                "tab_name": "Hourly",
                "filter_item_coldict": {
                    "line_id": [],
                    "model": [],
                    "glass_type": ["TFT"],
                    "defect_size": ["M", "L", "O"],
                },
            },
            "default_spec_table": {
                "type": "table",
                "tab_name": "預設spec",
                "table_columns": {
                    "line_id": "PI Line",
                    "model": "Model",
                    "glass_type": "Type",
                    "defect_size": "Defect Size",
                    "OOC": "OOC",
                    "OOS": "OOS",
                    "Editor": "",
                },
                "filter_item_coldict": {
                    "PI Line": {"key": "line_id", "values": self.uni_pi_names[:]},
                    "Model": {"key": "model", "values": []},
                    "Type": {"key": "glass_type", "values": self.glass_sides[:]},
                    "Defect Size": {"key": "defect_size", "values": self.size_group_keys },
                },
            },
            
            "TrendChart": {
                "type": "Chart",
                "tab_name": "趨勢分析(月週日)",
                "filter_item_coldict": {
                    "line_id": [],
                    "model": [],
                    "glass_type": self.glass_sides[:],
                    "defect_size": self.uni_defect_sizes[:],
                },
            },
            "EditSummary": {
                "type": "table",
                "tab_name": "Action_History",
                "filter_item_coldict": {
                    "PI Line": {"key": "line_id", "values": self.uni_pi_names[:]},
                    "Model": {"key": "model", "values": []},
                    "Type": {"key": "glass_type", "values": self.glass_sides[:]},
                },
            },
             "csv_download": {
                "type": "csv",
                "tab_name": "資料下載",
                "table_columns": {
                    "line_id": "PI Line",
                    "model": "Model",
                    "glass_type": "glass_side",
                    "pi_hour":"hourly",
                    "maingroup_glass_count": "total_glass",
                    "maingroup_defect_count": "defect_cnt",
                    "density": "density",
                },
            },

            "density_average": {
                "type": "density_avg",
                "tab_name": "Density平均值",

                # Inspection 有 line_id / glass_type / model。
                # 使用者需求：by line、glass_side、Model。
                "group_keys": [
                    
                    "glass_type",
                    "line_id",
                    "model",
                    "defect_size",
                ],

                "metric_columns": [
                    "defect_cnt",
                    "total_glass_cnt",
                    "density",
                    "day_count",
                    "hour_count",
                ],

                "time_col": "pi_hour",
                "time_semantic": "pi_hour_label_30min",
                "day_boundary": "07:30",

                "source_columns": {
                    "glass_side": "glass_type",
                    "line_id": "line_id",
                    "model": "model",
                    
                    "defect_size": "defect_size",

                    "total_glass_cnt": "maingroup_glass_count",
                    "defect_cnt": "maingroup_defect_count",

                    "small_defect_count": "small_defect_count",
                    "middle_defect_count": "middle_defect_count",
                    "large_defect_count": "large_defect_count",
                    "over_defect_count": "over_defect_count",
                    "glass_size_detail": "glass_size_detail",
                },

                "filter_item_coldict": {
                    
                    "glass_side": {
                        "key": "glass_type",
                        "values": ["TFT", "CF"],
                        "cascade": True,
                    },
                    "PI Line": {
                        "key": "line_id",
                        "values": [f"CAPIC{i}07" for i in range(1, 8)],
                        "cascade": True,
                    },
                    "Model": {
                        "key": "model",
                        "values": [],
                        "cascade": True,
                    },
                   "defect size": {
                        "key": "defect_size",
                        "values": ["S", "MS", "LMS", "O", "OL", "OLM", "OLMS"],
                        "cascade": True,
                    },

                },

                "cascade_order": [
                    "glass_type",
                    "line_id",
                    "model",
                    "defect_size",
                ],

                # Inspection 若沒有 recipe_id / adc_def_code，就不做此規則。
                "recipe_defect_default_rules": [],

                "table_columns": {
                    
                    "glass_type": "glass_side",
                    "line_id": "PI Line",
                    "model": "Model",
                    "defect_size": "SIZE_GROUP",
                    "defect_cnt": "defect count",
                    "total_glass_cnt": "total glass",
                    "density": "density",
                    "day_count": "days",
                    "hour_count": "hours",
                },

                "download_columns": {
                    
                    "glass_type": "glass_side",
                    "line_id": "PI Line",
                    "model": "Model",
                    "defect_size": "SIZE_GROUP",
                    "defect_cnt": "defect count",
                    "total_glass_cnt": "total glass",
                    "density": "density",
                    "day_count": "days",
                    "hour_count": "hours",
                },
            },


        }

        # =====================================================
        # front config
        # =====================================================
        self.front_config = {
            "chartKeyDict": self.chart_group_dict,
            "filtetItemKeyDict": self.filter_item_coldict,
            "hourlyTable": self.chart_table_coldict,
            "hourlyTable_key_group": self.table_group_key_dict,
            "uniGlassInfo": self.uni_glass_row_info_dict,
            "uniGlassDefectTable": self.defect_group_coldict,
            "FilterDefaultDict": self.filter_config,
            "SubTabsFilterDefaultDict": self.tab_filter_config,
            "primaryGroupCols": self.primary_group_cols,
        }

        # =====================================================
        # spec table schema
        # =====================================================
        self.spec_cols = [
            "line_id",
            "model",
            "glass_type",
            "defect_size",
            "OOC",
            "OOS",
            "Editor",
            "modify_time",
            "drop",
        ]


CFG = InspectionDensityApiConfig()


# =========================================================
# Common helpers
# =========================================================
def is_date_only_str(s: Any) -> bool:
    s = str(s).strip()
    fmts = ["%Y-%m-%d", "%y-%m-%d"]
    for f in fmts:
        try:
            datetime.strptime(s, f)
            return True
        except ValueError:
            continue
    return False


def parse_dt(s: str) -> datetime:
    s = str(s).strip().replace("T", " ")
    fmts = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H",
        "%Y-%m-%d",
        "%y-%m-%d %H:%M:%S",
        "%y-%m-%d %H:%M",
        "%y-%m-%d %H",
        "%y-%m-%d",
    ]
    for f in fmts:
        try:
            dt = datetime.strptime(s, f)
            if f in ("%Y-%m-%d", "%y-%m-%d"):
                return dt.replace(hour=0, minute=0, second=0, microsecond=0)
            if f in ("%Y-%m-%d %H", "%y-%m-%d %H"):
                return dt.replace(minute=0, second=0, microsecond=0)
            if f in ("%Y-%m-%d %H:%M", "%y-%m-%d %H:%M"):
                return dt.replace(second=0, microsecond=0)
            return dt.replace(microsecond=0)
        except ValueError:
            continue
    raise ValueError(f"Bad datetime: {s}")


def month_span(start: datetime, end: datetime) -> List[str]:
    yms = []
    cur = datetime(start.year, start.month, 1)
    last = datetime(end.year, end.month, 1)
    while cur <= last:
        yms.append(cur.strftime("%Y%m"))
        cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
    return yms


def to_pi_hour_range(start: datetime, end: datetime) -> Tuple[datetime, datetime]:
    """
    與 core.py 的 to_pi_hour_range 對齊：
    pi_hour = floor(actual_time - 30min, hour)
    """
    offset = CFG.core_cfg.SHIFT_BUCKET_OFFSET_MINUTES
    start_bucket = (pd.Timestamp(start) - pd.Timedelta(minutes=offset)).floor("h")
    end_bucket = (pd.Timestamp(end) - pd.Timedelta(minutes=offset)).floor("h")
    return start_bucket.to_pydatetime(), end_bucket.to_pydatetime()


def shift_day_start_of(dt: datetime) -> datetime:
    return dt.replace(
        hour=CFG.core_cfg.SHIFT_DAY_START_HOUR,
        minute=CFG.core_cfg.SHIFT_DAY_START_MINUTE,
        second=0,
        microsecond=0,
    )


def shift_day_range_from_date_str(s: str) -> Tuple[datetime, datetime]:
    """
    將 YYYY-MM-DD 視為 shift day：
    start = 當天 07:30:00
    end   = 次日 07:29:59
    """
    dt = parse_dt(s)
    start = shift_day_start_of(dt)
    end = start + timedelta(days=1) - timedelta(seconds=1)
    return start, end


def resolve_query_dates_to_range(start_raw: str, end_raw: str) -> Tuple[datetime, datetime]:
    """
    規則：
    - 若 start/end 都是 date-only（YYYY-MM-DD / YY-MM-DD）
      則視為 shift day 範圍
    - 否則視為一般 datetime 點位
    """
    start_is_date_only = is_date_only_str(start_raw)
    end_is_date_only = is_date_only_str(end_raw)

    if start_is_date_only and end_is_date_only:
        start_dt, _ = shift_day_range_from_date_str(start_raw)
        _, end_dt = shift_day_range_from_date_str(end_raw)
        return start_dt, end_dt

    return parse_dt(start_raw), parse_dt(end_raw)


def compute_default_shift_range() :
    """
    預設抓近三個 shift day，包含目前所在 bucket 的實際結束時間。
    """
    now = datetime.now()
    shifted =  now - timedelta(minutes=CFG.core_cfg.SHIFT_BUCKET_OFFSET_MINUTES)
    bucket_floor = shifted.replace(minute=0, second=0, microsecond=0)
    current_bucket_end = bucket_floor + timedelta(minutes=90)

    shift_anchor = now - timedelta(
        hours=CFG.core_cfg.SHIFT_DAY_START_HOUR,
        minutes=CFG.core_cfg.SHIFT_DAY_START_MINUTE,
    )
    shift_day = shift_anchor.date()
    shift_day_start = datetime.combine(shift_day, datetime.min.time()) + timedelta(
        hours=CFG.core_cfg.SHIFT_DAY_START_HOUR,
        minutes=CFG.core_cfg.SHIFT_DAY_START_MINUTE,
    )

    start = shift_day_start - timedelta(days=2)
    end = current_bucket_end
    return start, end


def try_get_table(dbhandler: MySQLConnetFunc, tbn: str) -> Optional[pd.DataFrame]:
    try:
        return dbhandler.get_table(tbn)
    except Exception:
        return None


def safe_fill_columns(df: pd.DataFrame, cols: List[str], default="") -> pd.DataFrame:
    if df is None:
        df = pd.DataFrame()
    for c in cols:
        if c not in df.columns:
            df[c] = default
    return df


def normalize_datetime_cols(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    out = df.copy()

    for c in ["pi_hour", "shift_start", "shift_end", "modify_time"]:
        if c in out.columns:
            out[c] = pd.to_datetime(out[c], errors="coerce")

    if "shift_day" in out.columns:
        out["shift_day"] = pd.to_datetime(out["shift_day"], errors="coerce")

    return out


def ensure_json_string_col(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()
    if df.empty:
        out = df.copy()
        if col not in out.columns:
            out[col] = ""
        return out

    out = df.copy()
    if col not in out.columns:
        out[col] = ""

    def _to_json_str(v):
        if v is None:
            return ""
        if isinstance(v, str):
            return v.strip()
        try:
            return json.dumps(v, ensure_ascii=False)
        except Exception:
            return str(v)

    out[col] = out[col].apply(_to_json_str)
    return out

def _clean_unique_values(df: pd.DataFrame, col: str) -> List[str]:
    if df is None or df.empty or col not in df.columns:
        return []
    vals = (
        df[col]
        .dropna()
        .astype(str)
        .map(str.strip)
        .replace("", pd.NA)
        .dropna()
        .unique()
        .tolist()
    )
    return sorted(vals)


def _merge_unique_values(a: List[str], b: List[str]) -> List[str]:
    return sorted(set(a or []) | set(b or []))


def spec_table_clean(
    dbhandler: MySQLConnetFunc,
    summary_df: Optional[pd.DataFrame] = None,
    base_subtabs_filter_default_dict: Optional[Dict[str, Any]] = None,
):
    """
    不直接修改全域 CFG.front_config。

    回傳：
    1. prospecdict
    2. 新的 subtabs_filter_default_dict
    """
    try:
        df = dbhandler.get_table(CFG.default_spec_table_name)
        if df is None or df.empty:
            df = pd.DataFrame(columns=CFG.spec_cols)
        else:
            for c in CFG.spec_cols:
                if c not in df.columns:
                    df[c] = ""
            if "drop" in df.columns:
                df = df[~df["drop"].fillna("").astype(str).str.upper().isin(["T", "1", "TRUE"])]
            df = df.reset_index(drop=True)
    except Exception:
        df = pd.DataFrame(columns=CFG.spec_cols)

    for c in CFG.spec_cols:
        if c not in df.columns:
            df[c] = ""

    for c in ["OOC", "OOS"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    for c in ["line_id", "model", "glass_type", "defect_size", "Editor", "drop"]:
        if c in df.columns:
            df[c] = df[c].fillna("").astype(str)

    if "modify_time" in df.columns:
        df["modify_time"] = pd.to_datetime(df["modify_time"], errors="coerce")
        df["modify_time"] = df["modify_time"].dt.strftime("%Y-%m-%d %H:%M:%S").fillna("")

    spec_line_values = _clean_unique_values(df, "line_id")
    spec_model_values = _clean_unique_values(df, "model")
    spec_glass_type_values = _clean_unique_values(df, "glass_type")
    spec_defect_size_values = _clean_unique_values(df, "defect_size")

    summary_line_values = _clean_unique_values(summary_df, "line_id")
    summary_model_values = _clean_unique_values(summary_df, "model")
    summary_glass_type_values = _clean_unique_values(summary_df, "glass_type")

    line_values = _merge_unique_values(spec_line_values, summary_line_values) or CFG.uni_pi_names[:]
    model_values = _merge_unique_values(spec_model_values, summary_model_values)
    glass_type_values = _merge_unique_values(spec_glass_type_values, summary_glass_type_values) or CFG.glass_sides[:]
    defect_size_values = spec_defect_size_values or CFG.uni_defect_sizes[:]

    subtabs_filter_default_dict = copy.deepcopy(
        base_subtabs_filter_default_dict
        if base_subtabs_filter_default_dict is not None
        else CFG.front_config.get("SubTabsFilterDefaultDict", {})
    )

    if "default_spec_table" in subtabs_filter_default_dict:
        node = subtabs_filter_default_dict["default_spec_table"].get("filter_item_coldict", {})
        if "PI Line" in node:
            node["PI Line"]["values"] = line_values
        if "Model" in node:
            node["Model"]["values"] = model_values
        if "Type" in node:
            node["Type"]["values"] = glass_type_values
        #if "Defect Size" in node:
        #    node["Defect Size"]["values"] = defect_size_values


    if "TrendChart" in subtabs_filter_default_dict:
        subtabs_filter_default_dict["TrendChart"]["filter_item_coldict"] = {
            "line_id": line_values,
            "model": model_values,
            "glass_type": glass_type_values,
            "defect_size": defect_size_values,
        }

    if "EditSummary" in subtabs_filter_default_dict:
        node = subtabs_filter_default_dict["EditSummary"].get("filter_item_coldict", {})
        if "PI Line" in node:
            node["PI Line"]["values"] = line_values
        if "Model" in node:
            node["Model"]["values"] = model_values
        if "Type" in node:
            node["Type"]["values"] = glass_type_values

    prospecdict = {
        "default_spec_table": df.to_dict(orient="index")
    }

    return prospecdict, subtabs_filter_default_dict
