# routers/aoi_density_defect_map.py
from __future__ import annotations

import math
import re
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union
import numpy as np
import pandas as pd
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text, bindparam
from sqlalchemy.exc import SQLAlchemyError

from models.sql_db_connect import MySQLConnet

router = APIRouter()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(funcName)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ========= 工具 =========


def extract_pi_suffix(line_id: str, default: str = "100") -> str:
    """line_id 末尾 2-3 位數字（CAPIC500 → '500'）"""
    if not line_id:
        return default
    m = re.search(r"(\d{2,3})$", str(line_id))
    return m.group(1) if m else default

def group_defects_by_glass(
    rows: Union[List[Dict[str, Any]], "pd.DataFrame"]
) -> Dict[str, Dict[str, Any]]:
    if rows is None:
        return {}

    # 1) 統一轉成 DataFrame
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

    # 3) 型別與清理
    df["SHEET_ID"] = df["SHEET_ID"].astype(str).fillna("")
    df["TOOL_ID"] = df["TOOL_ID"].astype(str).fillna("")

    df["COORD_X"] = pd.to_numeric(df["COORD_X"], errors="coerce")
    df["COORD_Y"] = pd.to_numeric(df["COORD_Y"], errors="coerce")

    # DEFECT_SIZE_TYPE → size (S/M/L/O/None)
    df["size"] = (
        df["DEFECT_SIZE_TYPE"]
        .astype(str)
        .str.strip()
        .str.upper()
        .where(df["DEFECT_SIZE_TYPE"].notna(), None)
    )

    # 座標轉換（依 TOOL_ID）
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

    # * 1000 後取整數
    df["x_out"] = (df["x"] * 1000).round().astype("Int64")
    df["y_out"] = (df["y"] * 1000).round().astype("Int64")

    
    df = df.dropna(subset=["x_out", "y_out"])

    # print(df.groupby("SHEET_ID").size())

    out: Dict[str, List[Dict[str, Any]]] = {}

    for gid, g in df.groupby("SHEET_ID"):
        gid_str = str(gid) if gid is not None else ""

        # 各尺寸計數
        size_counts = g["size"].value_counts()
        s_cnt = int(size_counts.get("S", 0))
        m_cnt = int(size_counts.get("M", 0))
        l_cnt = int(size_counts.get("L", 0))
        o_cnt = int(size_counts.get("O", 0))
        total = s_cnt + m_cnt + l_cnt + o_cnt

        # defect_map list
        defect_map = []
        for x, y, size, img in zip(
            g["x_out"], g["y_out"], g["size"], g["IMG_URL"]
        ):
            defect_map.append(
                {
                    "x": str(int(x)),
                    "y": str(int(y)),
                    "size": size,
                    "img": img if img is not None else "",
                }
            )

        out[gid_str] = defect_map

    return out

# ========= 主查詢：pi_hour → SCAN_ENDTIME 範圍 + 其它鍵 =========

# ====== 請求模型 ======
class DefectMapIn(BaseModel):
    rows: List[Dict[str, Any]] = []

@router.post("/api/defect_map")
async def defect_map(payload: DefectMapIn):
    
    dbhandler = MySQLConnet("l6a01_project")
    out_rows: Dict[str, Any]= {}

    SUMMARY_KEYS = ["pi_hour", "line_id", "model", "glass_type", "glass"]
    RAW_KEYS = ['TOOL_ID', 'SHEET_ID', 'DEFECT_SIZE_TYPE', 'COORD_X', 'COORD_Y', 'IMG_URL']
    

    for row in payload.rows:
        #print('row',row)
        hourly, line_id, model, glass_type, glass_str = [row[k] if k !='pi_hour' else '20'+row[k] for k in SUMMARY_KEYS]
        ym = hourly[:7].replace("-", "")  # '2025-12-27 14' -> '2025-12' -> '202512'
        reicpe_name = f'{model}-{glass_type}'

        # summary
        """
        summary_tbn = f'inspection_api_summary_{ym}'
        match_s_dict = {
            "pi_hour": hourly,
            "line_id": line_id,
            "model": model,
            "glass_type": glass_type,
        }

        print(summary_tbn, match_s_dict)

        match_s_rows = dbhandler.get_rows(summary_tbn, match_s_dict)
        logging.info(f'[{summary_tbn}] 篩選筆數:{ len(match_s_rows)}')
        if len(match_s_rows) == 0:
            continue
        """
        # 收集所有 glass
        glass_list = glass_str.split(",")
        logging.info(f'取得GROUP片數: {len(glass_list)}')

        # raw
        raw_tbn = f'inspection_raw_table_{ym}'
        base_match = {
            'RECIPE_NAME': reicpe_name,
            'TOOL_ID': line_id
        }

        # 一次把所有 SHEET_ID 對應的 defect rows 拉回來（DataFrame）
        defect_df = dbhandler.get_rows_df_in(
            table_name=raw_tbn,
            base_keys=base_match,
            in_key='SHEET_ID',
            in_values=glass_list
        )
        logging.info(f'[{raw_tbn}] 篩選筆數: {len(defect_df)}')


        if defect_df.empty:
            continue
        defect_df = defect_df[RAW_KEYS]
        #cnt_by_sheet = defect_df.groupby('SHEET_ID').size()
        out = group_defects_by_glass(defect_df)
        out_rows.update(out)
        #for gls in glass_list:
        #    print(gls, int(cnt_by_sheet.get(gls, 0)))
        #print(out_rows)
        
    return {"DefectGroupDict": out_rows}
