# aoi_capa_api.py
from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, date
from collections import defaultdict
import pandas as pd
import json
import logging
import re

from sqlalchemy import text

from models.sql_db_connect import MySQLConnet

router = APIRouter()

logger = logging.getLogger(__name__)

# =========================================================
# Config 設定
# =========================================================

class Config:
    def __init__(self):
        #now = datetime.now()
        #ym = now.strftime("%Y%m")
        #print(f"CAPA連線時間: {now}({ym})")
        # ====== AOI 名稱 ======
        self.uni_aoi_names = [f'aoi{i}00' for i in range(1, 4, 1)]  # aoi100, aoi200, aoi300

        # ====== PI Type 列表（全域可選值，用在 filter、table index）======
        self.pi_types = ["API", "BPI", "ITO"]

        # ====== 每個 AOI 對應的 source/summary/hourly 資料表與 pi_type 設定 ======
        
        self.aoi_dict = {
            'aoi100': {
                'source': 'aoi_summary_aoi100',         # 原始日彙總來源（你原本的表）
                'day_tbn': 'aoi100_capa_summary',      # 日 capa 結果表
                'hourly_tbn': 'aoi100_capa_hourly_rawdata',
                'recipe_charts': [],
                'pi_types': ["API", "BPI"],            # 此 AOI 有的 pi_type
                'recipe_map': {}
            },
            'aoi200': {
                'source': 'aoi_summary_aoi200',
                'day_tbn': 'aoi200_capa_summary',
                'hourly_tbn': 'aoi200_capa_hourly_rawdata',
                'recipe_charts': ["2", "3", "4", "5"],
                'pi_types': ["API", "BPI"],
                'recipe_map': {
                    "2": "API",
                    "4": "API",
                    "3": "BPI",
                    "5": "BPI"
                }
            },
            'aoi300': {
                'source': 'aoi_summary_aoi300_capa',
                'day_tbn': 'aoi300_capa_summary',
                'hourly_tbn': 'aoi300_capa_hourly_rawdata',
                'recipe_charts': ["CELL-ITO", "API", "BPI", "ITO"],
                'pi_types': ["CELL-ITO", "API", "BPI", "ITO"],
                'recipe_map': {
                    "API": "API",
                    "BPI": "BPI",
                    "CELL-ITO": "ITO",
                    "ITO": "ITO"
                }
            },
        }

        # ====== DB 欄位定義（實際從 summary / hourly 撈出來的欄位）======
        self.day_sql_cols = [
            'aoi', 'run_day', 'pi_type',
            'total_glass', 'target_count', 'spec',
            'real_day_capa', 'comment', 'editor'
        ]

        self.rawdata_sql_cols = [
            'aoi', 'run_day', 'hour_int', 'pi_type',
            'hour', 'cumu', 'real_hour_capa', 'real_cumu_capa'
        ]

        # ====== Filter 預設值（前端 Filter 用）======
        self.filter_config = {
            'aoi': self.uni_aoi_names,
            'pi_type': self.pi_types
        }

        # ====== 前端 Hourly Table 的設定（這邊只是提供欄位/索引配置）======
        self.hourly_table_coldict = {
            'columns': ['aoi'] + [str(i) for i in range(24)],
            'index': self.pi_types + ['hour', 'cumu', 'real_hour_capa']
        }

        # ====== Chart Group 設定（給前端做分組）======
        self.chart_group_dict = {
            'left': ['aoi', 'total_glass'],   # 左軸可以畫 total_glass
            'down': ['run_day'],              # x 軸：日期
            'right': ['real_day_capa'],       # 右軸：使用率
        }

        # ====== Filter Item 對應欄位 ======
        self.filter_item_coldict = {
            'aoi': 'aoi',
            'pi_type': 'pi_type'
        }

        # ====== 給前端的整體設定 ======
        self.front_config = {
            'chartKeyDict': self.chart_group_dict,
            'filtetItemKeyDict': self.filter_item_coldict,
            'hourlyTableCfg': self.hourly_table_coldict,
            'FilterDefaultDict': self.filter_config
        }

cfg = Config()
db = MySQLConnet("l6a01_project")

# =========================================================
# 共用小工具
# =========================================================

def _parse_dt(s: str) -> datetime:
    """
    接受多種格式：YYYY-MM-DD[ HH[:MM[:SS]]] 或 YY-MM-DD[ HH]
    統一回傳「整點」的 datetime（分鐘、秒清 0）
    """
    s = s.strip().replace("T", " ")
    fmts = [
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H", "%Y-%m-%d",
        "%y-%m-%d %H", "%y-%m-%d"
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

def _load_day_summary_for_aoi(
    aoi: str,
    start_day: date,
    end_day: date
) -> pd.DataFrame:
    """
    從 {aoi}_capa_summary 撈出指定日期區間的日彙總 (day summary)
    """
    if aoi not in cfg.aoi_dict:
        raise ValueError(f"Unknown AOI: {aoi}")

    tbn = cfg.aoi_dict[aoi]['day_tbn']
    cols = cfg.day_sql_cols

    col_sql = ", ".join([f"`{c}`" for c in cols])
    sql = text(f"""
        SELECT {col_sql}
        FROM `{tbn}`
        WHERE run_day BETWEEN :start_day AND :end_day
    """)

    with db.engine.connect() as conn:
        df = pd.read_sql(
            sql,
            conn,
            params={"start_day": start_day, "end_day": end_day}
        )

    # 確保 run_day 是 date 型別或可轉成 yyyy-mm-dd 字串
    if not df.empty:
        df["run_day"] = pd.to_datetime(df["run_day"]).dt.date

    return df


def _load_hourly_for_aoi(
    aoi: str,
    run_day: date,
    pi_type: Optional[str] = None
) -> pd.DataFrame:
    """
    從 {aoi}_capa_hourly_rawdata 撈出指定 run_day、pi_type 的每小時資料
    """
    if aoi not in cfg.aoi_dict:
        raise ValueError(f"Unknown AOI: {aoi}")

    tbn = cfg.aoi_dict[aoi]['hourly_tbn']
    cols = cfg.rawdata_sql_cols
    col_sql = ", ".join([f"`{c}`" for c in cols])

    base_sql = f"""
        SELECT {col_sql}
        FROM `{tbn}`
        WHERE run_day = :run_day
    """
    params = {"run_day": run_day}

    if pi_type and pi_type.upper() != "ALL":
        base_sql += " AND pi_type = :pi_type"
        params["pi_type"] = pi_type
    # pi_type=ALL 或 None → 不加條件，前端可以自行篩

    sql = text(base_sql)

    with db.engine.connect() as conn:
        df = pd.read_sql(sql, conn, params=params)

    if not df.empty:
        df["run_day"] = pd.to_datetime(df["run_day"]).dt.date

    return df

# =========================================================
# 1) /api/reset_summary_filter
#    - 初始 Chart Data（預設 7 天，或由 dates 指定區間）
#    - 回傳前端需要的 front_config
# =========================================================

@router.get("/api/reset_summary_filter")
async def reset_summary_filter(
    dates: Optional[List[str]] = Query(
        None,
        description="['YYYY-MM-DD [HH:MM:SS]', 'YYYY-MM-DD [HH:MM:SS]']"
    )
):
    """
    回傳：
    - DictData: 由各 AOI 的 day summary 組成的大 list，
                每筆資料包含 aoi, run_day, pi_type, total_glass, target_count, spec, real_day_capa, comment, editor
    - ParamDict：給前端的固定設定與選項 (chart 分組, filter 預設, hourly table 配置)
    - DateRange: 後端實際使用的日期區間（給前端顯示用）

    日期邏輯：
    - 若沒有帶 dates → 預設抓「今天往回 6 天」（共 7 天）
    - 若有帶 dates 且長度為 2 → 視為 [start, end]
    """
    now = datetime.now()
    # 1) 處理日期區間
    try:
        if dates and len(dates) == 2:
            start_dt = _parse_dt(dates[0])
            end_dt = _parse_dt(dates[1])
        else:
            # 預設 7 天：今天往回 7 天
            end_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            start_dt = end_dt - timedelta(days=6)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    start_day = start_dt.date()
    end_day = end_dt.date()

    logger.info(f"CAPA連線時間: {now}")#\n[reset_summary_filter] 日期區間：{start_day} ~ {end_day}")

    # 2) 逐 AOI 撈取 day summary
    all_rows: List[Dict[str, Any]] = []
    spec_dict = {}
    for aoi in cfg.uni_aoi_names:
        
        if aoi not in cfg.aoi_dict:
            logger.warning(f"[reset_summary_filter] 未在 cfg.aoi_dict 找到 AOI: {aoi}，略過。")
            continue

        try:
            df = _load_day_summary_for_aoi(aoi, start_day, end_day)
            
            val_dict = df.iloc[-1,:].to_dict()
            spec_dict[aoi] = {
                'target_count':val_dict['target_count'],
                'spec':val_dict['spec']
            }
        except Exception as e:
            logger.error(f"[reset_summary_filter] 讀取 {aoi} day summary 發生錯誤：{e}")
            continue

        if df.empty:
            logger.info(f"[reset_summary_filter] {aoi} 在 {start_day}~{end_day} 無日彙總資料。")
            continue
        #print(aoi, len(df))
        # 確保欄位完整（避免少欄位）
        for col in cfg.day_sql_cols:
            if col not in df.columns:
                df[col] = None

        df["aoi"] = aoi  # 保險起見
        df = df[cfg.day_sql_cols]  # 按既定欄位順序

        rows = df.to_dict(orient="records")
        #print(df.iloc[-1:,:].to_dict())
        all_rows.extend(rows)
    cfg.front_config['SpecDict'] = spec_dict
    # 3) 組回傳 payload
    payload = {
        "DictData": all_rows,        # 給 chart / table 用的一大包 row
        "ParamDict": cfg.front_config,
        "DateRange": {
            "start": start_day.isoformat(),
            "end": end_day.isoformat()
        }
    }
    """
    print({
            "start": start_day.isoformat(),
            "end": end_day.isoformat()
        })
    """
    return payload


# =========================================================
# 2) /api/hourly_rawdata_filter
#    - 依 AOI + run_day + pi_type 撈每小時的 raw data
# =========================================================

@router.get("/api/hourly_rawdata_filter")
async def hourly_rawdata_filter(
    filter_ask_keys: Optional[str] = Query(
        None,
        description="JSON 物件字串：{'aoi': aoi, 'pi_type': pi_type, 'run_day': 'YYYY-MM-DD'}"
    )
):
    """
    使用方式：
    - filter_ask_keys 為 JSON 字串，例如：
      {
        "aoi": "aoi200",
        "pi_type": "API",     # 或 "ALL" / "" / null → 代表不分 pi_type 全部撈出
        "run_day": "2025-11-20"
      }

    回傳：
    - rows: 每小時 raw data list
      欄位：['aoi','run_day','hour_int','pi_type','hour','cumu','real_hour_capa','real_cumu_capa']
    """
    if not filter_ask_keys:
        raise HTTPException(status_code=400, detail="filter_ask_keys is required")

    try:
        ask: Dict[str, Any] = json.loads(filter_ask_keys)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="filter_ask_keys 必須為 JSON 格式")

    aoi = ask.get("aoi")
    run_day_str = ask.get("run_day")
    pi_type = ask.get("pi_type")

    if not aoi or not run_day_str:
        raise HTTPException(status_code=400, detail="filter_ask_keys 需包含 'aoi' 與 'run_day'")

    if aoi not in cfg.aoi_dict:
        raise HTTPException(status_code=400, detail=f"未知的 AOI: {aoi}")

    try:
        run_day = datetime.strptime(run_day_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="run_day 格式應為 YYYY-MM-DD")

    logger.info(f"[hourly_rawdata_filter] ask: aoi={aoi}, run_day={run_day}, pi_type={pi_type}")

    try:
        df = _load_hourly_for_aoi(aoi, run_day, pi_type)
    except Exception as e:
        logger.error(f"[hourly_rawdata_filter] 讀取 {aoi} hourly 發生錯誤：{e}")
        raise HTTPException(status_code=500, detail=str(e))

    if df.empty:
        logger.info(f"[hourly_rawdata_filter] {aoi} 在 {run_day} 無 hourly 資料。")
        rows: List[Dict[str, Any]] = []
    else:
        # 確保欄位完整
        for col in cfg.rawdata_sql_cols:
            if col not in df.columns:
                df[col] = None

        df = df[cfg.rawdata_sql_cols].sort_values(["pi_type", "hour_int"])
        #print(df.iloc[:3,:].to_dict())
        rows = df.to_dict(orient="records")

    return {
        "rows": rows,
        "meta": {
            "aoi": aoi,
            "run_day": run_day.isoformat(),
            "pi_type": pi_type
        }
    }