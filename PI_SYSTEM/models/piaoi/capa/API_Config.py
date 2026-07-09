# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any
import pandas as pd


class Config:
    def __init__(self):
        # =========================================================
        # DB / AOI / PI Type
        # =========================================================
        self.DB_NAME = "piaoi_capa"

        self.uni_aoi_names = ["aoi100", "aoi200", "aoi300"]

        self.pi_types_all = ["API", "BPI", "ITO", "OTHER"]

        self.aoi_dict = {
            "aoi100": {
                "summary_pi_types": ["API", "BPI", "OTHER", "ALL"],
                "detail_pi_types": ["API", "BPI", "OTHER"],
            },
            "aoi200": {
                "summary_pi_types": ["API", "BPI", "OTHER", "ALL"],
                "detail_pi_types": ["API", "BPI", "OTHER"],
            },
            "aoi300": {
                "summary_pi_types": ["API", "BPI", "ITO", "OTHER", "ALL"],
                "detail_pi_types": ["API", "BPI", "ITO", "OTHER"],
            },
        }

        # =========================================================
        # SQL Columns
        # =========================================================
        self.day_sql_cols = [
            "aoi",
            "run_day",
            "pi_type",
            "total_glass",
            "target_count",
            "spec",
            "real_day_capa",
            "comment",
            "action",
            "editor",
            "modify_time",
        ]

        self.rawdata_sql_cols = [
            "aoi",
            "run_day",
            "pi_type",
            "pi_hour",
            "hour_int",
            "hour_label",
            "hour_sort",
            "hour",
            "cumu",
            "real_hour_capa",
            "real_cumu_capa",
        ]

        # =========================================================
        # Filter Default
        # =========================================================
        self.filter_config = {
            "aoi": self.uni_aoi_names,
            "pi_type": self.pi_types_all,
        }

        # =========================================================
        # Front Config
        # =========================================================
        hours = [7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,0,1,2,3,4,5,6]
        self.hourly_table_coldict = {
            "columns": ["aoi"] + [f"{h:02d}" for h in hours],
            "index": self.pi_types_all + ["ALL", "hour", "cumu", "real_hour_capa"],
        }

        self.chart_group_dict = {
            "left": ["aoi", "total_glass"],
            "down": ["run_day"],
            "right": ["real_day_capa"],
        }

        self.filter_item_coldict = {
            "aoi": "aoi",
            "pi_type": "pi_type",
        }

        self.tab_filter_config = {
            "Day_Hourly": {"aoi": self.uni_aoi_names}, #,  "pi_type": self.pi_types_all
            'EditSummary':{
                'type':'table',
                'tab_name':'Action_History',
                "table_columns": [ 'aoi', "run_day", 'comment', 'action', 'Editor', 'modify_time'], #
                'filter_item_coldict':{
                    'aoi': {'key':'aoi',
                                'values':self.uni_aoi_names},
                    #'pi_type': {
                    #    'key': 'pi_type',
                    #    'values': self.pi_types_all
                    #}
                },
            },
            
        }

   

        self.front_config = {
            "chartKeyDict": self.chart_group_dict,
            "filtetItemKeyDict": self.filter_item_coldict,
            "hourlyTableCfg": self.hourly_table_coldict,
            "FilterDefaultDict": self.filter_config,
            "SubTabsFilterDefaultDict":self.tab_filter_config
        }


cfg = Config()


# =========================================================
# Common Helpers
# =========================================================
def parse_dt(s: str) -> datetime:
    """
    接受：
    - YYYY-MM-DD
    - YYYY-MM-DD HH
    - YYYY-MM-DD HH:MM
    - YYYY-MM-DD HH:MM:SS
    - YY-MM-DD
    - YY-MM-DD HH
    """
    s = s.strip().replace("T", " ")
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
                dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                dt = dt.replace(minute=0, second=0, microsecond=0)
            return dt
        except ValueError:
            continue
    raise ValueError(f"Bad datetime: {s}")


def resolve_query_dates_to_range(dates: Optional[List[str]]) -> tuple[datetime, datetime]:
    """
    - 若無 dates: 預設今天往回 6 天，共 7 天
    - 若 dates 有 2 筆: [start, end]
    """
    if dates and len(dates) == 2:
        start_dt = parse_dt(dates[0])
        end_dt = parse_dt(dates[1])
        if end_dt < start_dt:
            start_dt, end_dt = end_dt, start_dt
    else:
        end_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        start_dt = end_dt - timedelta(days=6)

    return start_dt, end_dt


def month_list_from_date_range(start_day: date, end_day: date) -> List[str]:
    """
    傳回日期區間內涵蓋的 YYYYMM 清單
    end_day 為實際日期，不是 exclusive
    """
    cur = date(start_day.year, start_day.month, 1)
    end_m = date(end_day.year, end_day.month, 1)

    out = []
    while cur <= end_m:
        out.append(cur.strftime("%Y%m"))
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return out


def summary_table_name(aoi: str, yyyymm: str) -> str:
    return f"{aoi}_{yyyymm}_capa_summary"


def hourly_table_name(aoi: str, yyyymm: str) -> str:
    return f"{aoi}_{yyyymm}_capa_hourly_rawdata"


def normalize_pi_type_for_filter(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip().upper()
    if not s:
        return None
    return s


def empty_day_df() -> pd.DataFrame:
    return pd.DataFrame(columns=cfg.day_sql_cols)


def empty_hourly_df() -> pd.DataFrame:
    return pd.DataFrame(columns=cfg.rawdata_sql_cols)