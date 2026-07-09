# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Union, Optional, Tuple

import numpy as np
import pandas as pd
from fastapi import APIRouter
from pydantic import BaseModel, Field

try:
    from PI_SYSTEM.models.inspection_density.sql_db_connect2 import MySQLConnetFunc as _DBHandler
except Exception:
    try:
        from models.inspection_density.sql_db_connect2 import MySQLConnetFunc as _DBHandler
    except Exception:
        from models.sql_db_connect import MySQLConnet as _DBHandler

router = APIRouter(tags=["duty_cell_piaoi_aoi_inspeciton"])

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(funcName)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# =========================================================
# Config
# =========================================================
class InspectionDefectMapConfig:
    def __init__(self):
        self.db_name = "piaoi_inspection_density"
        self.raw_table_tpl = "inspection_raw_table_{yyyymm}"

        # 與 core.py 對齊
        self.shift_bucket_offset_minutes = 30  # pi_hour = floor(SCAN_ENDTIME - 30min, hour)

        # 前端送來的 summary row keys
        self.summary_keys = ["pi_hour", "line_id", "model", "glass_type", "glass"]

        # raw table 需要的欄位
        self.raw_keys = [
            "TOOL_ID",
            "SHEET_ID",
            "DEFECT_SIZE_TYPE",
            "COORD_X",
            "COORD_Y",
            "IMG_URL",
            "SCAN_ENDTIME",
            "RECIPE_NAME",
        ]


CFG = InspectionDefectMapConfig()


# =========================================================
# Utils
# =========================================================
def parse_pi_hour_to_dt(v: Any) -> Optional[datetime]:
    """
    相容：
    - 2026-03-19 15:00:00
    - 2026-03-19 15:00
    - 2026-03-19 15
    - 26-03-19 15
    """
    if v is None:
        return None

    s = str(v).strip().replace("T", " ")
    if not s:
        return None

    fmts = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H",
        "%y-%m-%d %H",
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
            if fmt == "%Y-%m-%d %H":
                return dt.replace(minute=0, second=0, microsecond=0)
            if fmt == "%y-%m-%d %H":
                return dt.replace(minute=0, second=0, microsecond=0)
            if fmt == "%Y-%m-%d %H:%M":
                return dt.replace(second=0, microsecond=0)
            return dt.replace(microsecond=0)
        except ValueError:
            continue
    return None


def pi_hour_to_scan_end_range(pi_hour_dt: datetime) -> Tuple[datetime, datetime]:
    """
    與 core.py bucket 對齊：
    pi_hour = floor(SCAN_ENDTIME - 30min, hour)

    所以某個 pi_hour bucket 對應的實際 SCAN_ENDTIME 範圍為：
      [pi_hour + 30min, pi_hour + 90min)
    """
    start_dt = pi_hour_dt + timedelta(minutes=CFG.shift_bucket_offset_minutes)
    end_dt = start_dt + timedelta(hours=1)
    return start_dt, end_dt


def parse_glass_list(row: Dict[str, Any]) -> List[str]:
    """
    相容：
    1) glass 為 list
    2) glass 為 CSV 字串
    3) glass_size_detail 為 JSON 字串 / list[dict]
    """
    glass_val = row.get("glass")

    if isinstance(glass_val, list):
        return [str(x).strip() for x in glass_val if str(x).strip()]

    if isinstance(glass_val, str) and glass_val.strip():
        return [g.strip() for g in glass_val.split(",") if g.strip()]

    detail_val = row.get("glass_size_detail")

    if isinstance(detail_val, list):
        out = []
        for item in detail_val:
            if not isinstance(item, dict):
                continue
            gid = str(item.get("glass_id", "")).strip()
            if gid:
                out.append(gid)
        return out

    if isinstance(detail_val, str) and detail_val.strip():
        try:
            arr = json.loads(detail_val)
            if isinstance(arr, list):
                out = []
                for item in arr:
                    if not isinstance(item, dict):
                        continue
                    gid = str(item.get("glass_id", "")).strip()
                    if gid:
                        out.append(gid)
                return out
        except Exception:
            pass

    return []


def filter_raw_df_by_bucket(
    df: pd.DataFrame,
    pi_hour_dt: datetime,
    line_id: str,
    recipe_name: str,
    glass_list: List[str],
) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=CFG.raw_keys)

    out = df.copy()

    for col in CFG.raw_keys:
        if col not in out.columns:
            out[col] = np.nan if col in ("COORD_X", "COORD_Y") else ""

    # 基本條件
    out["TOOL_ID"] = out["TOOL_ID"].fillna("").astype(str).str.strip()
    out["SHEET_ID"] = out["SHEET_ID"].fillna("").astype(str).str.strip()
    out["RECIPE_NAME"] = out["RECIPE_NAME"].fillna("").astype(str).str.strip()
    out["SCAN_ENDTIME"] = pd.to_datetime(out["SCAN_ENDTIME"], errors="coerce")

    start_dt, end_dt = pi_hour_to_scan_end_range(pi_hour_dt)
    glass_set = set([str(g).strip() for g in glass_list if str(g).strip()])

    out = out[out["TOOL_ID"] == str(line_id).strip()]
    out = out[out["RECIPE_NAME"] == str(recipe_name).strip()]
    out = out[out["SHEET_ID"].isin(glass_set)]
    out = out[out["SCAN_ENDTIME"].notna()]
    out = out[(out["SCAN_ENDTIME"] >= start_dt) & (out["SCAN_ENDTIME"] < end_dt)]

    return out.reset_index(drop=True)


def group_defects_by_glass(
    rows: Union[List[Dict[str, Any]], pd.DataFrame]
) -> Dict[str, List[Dict[str, Any]]]:
    if rows is None:
        return {}

    if isinstance(rows, pd.DataFrame):
        df = rows.copy()
    else:
        if not rows:
            return {}
        df = pd.DataFrame.from_records(rows)

    needed_cols = ["SHEET_ID", "TOOL_ID", "COORD_X", "COORD_Y", "DEFECT_SIZE_TYPE", "IMG_URL"]
    for col in needed_cols:
        if col not in df.columns:
            df[col] = np.nan if col in ("COORD_X", "COORD_Y") else ""

    df = df[needed_cols].copy()

    df["SHEET_ID"] = df["SHEET_ID"].fillna("").astype(str)
    df["TOOL_ID"] = df["TOOL_ID"].fillna("").astype(str)

    df["COORD_X"] = pd.to_numeric(df["COORD_X"], errors="coerce")
    df["COORD_Y"] = pd.to_numeric(df["COORD_Y"], errors="coerce")

    df["size"] = (
        df["DEFECT_SIZE_TYPE"]
        .astype(str)
        .str.strip()
        .str.upper()
        .where(df["DEFECT_SIZE_TYPE"].notna(), None)
    )

    # =====================================================
    # 座標轉換（沿用 inspection 規則）
    # =====================================================
    df["x"] = df["COORD_X"]
    df["y"] = df["COORD_Y"]

    mask_flip1 = df["TOOL_ID"].isin(["CAPIC207", "CAPIC507", "CAPIC407"])
    mask_flip2 = df["TOOL_ID"].isin(["CAPIC107", "CAPIC307", "CAPIC607", "CAPIC707"])

    # CAPIC207 / 507 / 407
    df.loc[mask_flip1, "x"] = 1850 + df.loc[mask_flip1, "COORD_Y"]
    df.loc[mask_flip1, "y"] = -df.loc[mask_flip1, "COORD_X"]

    # CAPIC107 / 307 / 607 / 707
    df.loc[mask_flip2, "x"] = 1850 - df.loc[mask_flip2, "COORD_Y"]
    df.loc[mask_flip2, "y"] = df.loc[mask_flip2, "COORD_X"]

    df["x_out"] = (df["x"] * 1000).round().astype("Int64")
    df["y_out"] = (df["y"] * 1000).round().astype("Int64")

    df = df.dropna(subset=["x_out", "y_out"])

    out: Dict[str, List[Dict[str, Any]]] = {}

    for gid, g in df.groupby("SHEET_ID"):
        gid_str = str(gid) if gid is not None else ""
        defect_map = []

        for x, y, size, img in zip(g["x_out"], g["y_out"], g["size"], g["IMG_URL"]):
            defect_map.append(
                {
                    "x": str(int(x)),
                    "y": str(int(y)),
                    "size": size,
                    "img": "" if img is None else str(img),
                }
            )

        out[gid_str] = defect_map

    return out


# =========================================================
# Schema
# =========================================================
class DefectMapIn(BaseModel):
    rows: List[Dict[str, Any]] = Field(default_factory=list)


# =========================================================
# API
# =========================================================
@router.post("/defect_map")
async def defect_map(payload: DefectMapIn):
    dbhandler = _DBHandler(CFG.db_name)
    out_rows: Dict[str, Any] = {}

    for row in payload.rows:
        try:
            hourly_raw = row["pi_hour"]
            line_id = str(row["line_id"]).strip()
            model = str(row["model"]).strip()
            glass_type = str(row["glass_type"]).strip()
        except KeyError:
            continue
        print('hourly_raw', hourly_raw)
        pi_hour_dt = parse_pi_hour_to_dt(hourly_raw)
        print('pi_hour_dt', pi_hour_dt)
        if not pi_hour_dt:
            logger.warning(f"[defect_map] 無法解析 pi_hour: {hourly_raw}")
            continue

        ym = pi_hour_dt.strftime("%Y%m")
        raw_tbn = CFG.raw_table_tpl.format(yyyymm=ym)

        glass_list = parse_glass_list(row)
        logger.info(f"[{raw_tbn}] 取得 GROUP 片數: {len(glass_list)}")

        if not glass_list:
            continue

        recipe_name = f"{model}-{glass_type}"

        # 先用較寬條件抓，再用 bucket 時間做精準過濾
        base_match = {
            "RECIPE_NAME": recipe_name,
            "TOOL_ID": line_id,
        }

        try:
            defect_df = dbhandler.get_rows_df_in(
                table_name=raw_tbn,
                base_keys=base_match,
                in_key="SHEET_ID",
                in_values=glass_list,
            )
        except Exception as e:
            logger.warning(f"[{raw_tbn}] 取得 raw data 失敗: {e}")
            continue

        logger.info(f"[{raw_tbn}] 初始篩選筆數: {0 if defect_df is None else len(defect_df)}")

        if defect_df is None or defect_df.empty:
            continue

        defect_df = filter_raw_df_by_bucket(
            df=defect_df,
            pi_hour_dt=pi_hour_dt,
            line_id=line_id,
            recipe_name=recipe_name,
            glass_list=glass_list,
        )

        logger.info(f"[{raw_tbn}] bucket 精準篩選後筆數: {len(defect_df)}")

        if defect_df.empty:
            continue

        defect_df = defect_df[CFG.raw_keys].copy()
        print(defect_df)
        out = group_defects_by_glass(defect_df)
        out_rows.update(out)

    return {"DefectGroupDict": out_rows}