from sqlalchemy import text, bindparam, create_engine, text, inspect
from sqlalchemy.exc import SQLAlchemyError
from concurrent.futures import ThreadPoolExecutor, as_completed
import pymysql
import re
import logging

# routers/aoi_density_defect_map.py
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict
import pandas as pd
import json
from routers.aoi_density import Config
from models.sql_db_connect import MySQLConnet

router = APIRouter()





def get_defects_by_key(self, table: str, key_dict: dict):
    """
    依 key_dict 產生多欄位條件：
      - 單值: '='
      - list/tuple/set: 'IN (...)'
      - None: IS NULL
    只使用實際存在於資料表的欄位，並回傳完整列（list[dict]）。
    """
    if not key_dict:
        return []

    # 表名防呆
    if not re.fullmatch(r"[A-Za-z0-9_]+", table or ""):
        logging.error(f"[get_defects_by_key] illegal table name: {table!r}")
        return []

    # 取得該表實際欄位
    try:
        with self.engine.begin() as conn:
            cols = conn.execute(
                text("""
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :tbl
                """),
                {"db": getattr(self, "db", None), "tbl": table},
            ).scalars().all()
    except Exception:
        try:
            with self.engine.begin() as conn:
                rows = conn.execute(text(f"SHOW COLUMNS FROM `{table}`")).all()
            cols = [r[0] for r in rows]
        except Exception as e:
            logging.error(f"[get_defects_by_key] fetch columns failed: {e}")
            return []

    colset = set(cols)
    if not colset:
        return []

    where, params, expanding = [], {}, []

    for k, v in key_dict.items():
        if k not in colset:
            continue  # 忽略不存在的欄位
        col = f"`{k}`"

        if v is None:
            where.append(f"{col} IS NULL")
        elif isinstance(v, (list, tuple, set)):
            lst = list(v)
            if not lst:
                # 空 IN 沒意義，跳過
                continue
            pname = f"{k}_list"
            where.append(f"{col} IN :{pname}")
            params[pname] = lst
            expanding.append(bindparam(pname, expanding=True))
        else:
            where.append(f"{col} = :{k}")
            params[k] = v

    if not where:
        return []  # 沒條件避免掃全表

    sql = f"SELECT * FROM `{table}` WHERE " + " AND ".join(where)

    try:
        with self.engine.begin() as conn:
            stmt = text(sql)
            if expanding:
                stmt = stmt.bindparams(*expanding)
            rows = conn.execute(stmt, params).mappings().all()
            return [dict(r) for r in rows]   # 完整列
    except SQLAlchemyError as e:
        logging.error(f"[get_defects_by_key] {e}")
        return []






def normalize_pi_hour(pi_hour: str) -> str | None:
    """
    只校驗/標準化成 'YYYY-MM-DD HH'（不做時間區間篩選）。
    若是 'YY-MM-DD HH' 會自動補 '20'。
    """
    if not pi_hour:
        return None
    s = str(pi_hour).strip()
    # 'YY-MM-DD HH' → 補 '20'
    if re.fullmatch(r"\d{2}-\d{2}-\d{2}\s+\d{2}", s):
        return "20" + s
    # 允許 'YYYY-MM-DD HH'（長度 13）
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}\s+\d{2}", s):
        return s
    return None

def ym_from_pi_hour(pi_hour_yyyy: str) -> str:
    """從 'YYYY-MM-DD HH' 取出 yymm（例：'2025-09-30 10' → '2509'）"""
    yy = int(pi_hour_yyyy[2:4])
    mm = pi_hour_yyyy[5:7]
    return f"{yy:02d}{mm}"

def extract_pi_suffix(line_id: str, default: str = "100") -> str:
    """
    從 line_id 取末尾 2~3 位數字當作 PI 代號（如 CAPIC100 → '100'）。
    取不到時回傳 default。
    """
    if not line_id:
        return default
    m = re.search(r"(\d{2,3})$", str(line_id))
    return m.group(1) if m else default

def to_bucket(size_val) -> str | None:
    """
    將 defect_size 轉為 S/M/L/O（文字 S/M/L/O 直返；數字用門檻：<=20,S; <=100,M; <=400,L; >=401,O）
    """
    if size_val is None:
        return None
    # 文字 S/M/L/O
    if isinstance(size_val, str):
        up = size_val.strip().upper()
        if up in ("S","M","L","O"):
            return up
        try:
            num = int(float(up))
        except Exception:
            return None
    else:
        try:
            num = int(float(size_val))
        except Exception:
            return None
    if num <= 20: return "S"
    if num <= 100: return "M"
    if num <= 400: return "L"
    return "O"

def group_defects_by_glass(rows: list[dict]) -> dict[str, dict]:
    """
    rows → 依 glass_id 分組，累計 S/M/L/O/total，並輸出 defect_map。
    defect_map 欄位盡量提供前端會用到的鍵：x,y,size,img,chip,recipe_id,ai_code_1,lot/lotid…
    """
    out: dict[str, dict] = {}
    img_flds = []
    for r in rows or []:
        gid = str(r.get("glass_id", "") or "")
        g = out.setdefault(gid, {"defect_map": [], "S": 0, "M": 0, "L": 0, "O": 0, "total": 0})
        img_flds.append(r.get("pic_path"))
        item = {
            # 常見命名對應
            "x": r.get("x"),
            "y": r.get("y"),
            "size": r.get("defect_size") if r.get("defect_size") is not None else r.get("size"),
            "img": r.get("pic_path")+ f'{r.get("pic_name")}.jpg' if (r.get("pic_name") is not None and  r.get("pic_path") is not None) else '',
            "chip": r.get("chip_name") or r.get("chip"),
            "recipe_id": r.get("recipe_id"),
            "ai_code_1": r.get("ai_code_1")
        }
        g["defect_map"].append(item)
        
        b = to_bucket(item.get("size"))
        if b in ("S","M","L","O"):
            g[b] += 1
            g["total"] += 1
    print('影像資料夾:',set(img_flds))
    return out






# ====== 請求模型 ======
class DefectMapIn(BaseModel):
    rows: List[Dict[str, Any]] = []

RAW_KEYS = ['pi_hour', 'line_id', 'model', 'glass_type', 'recipe_id', 'ai_code_1']

@router.post("/api/defect_map")
async def defect_map(payload: DefectMapIn):
    """
    前端傳入 rows（圖表/表格所選），
    依 AOI + pi_hour + line_id 組出資料表名，套 RAW_KEYS 多欄位條件查詢（不含時間篩），
    回傳 DefectGroupDict（每列 filters + defect_group）。
    """
    row_keys = ['ai_code_1','maingroup_glass_count', 'maingroup_defect_count','defect_code_glass_count', 'defect_code_count'
        ,'small_defect_count', 'middle_defect_count', 'large_defect_count', 'over_defect_count','glass']
    main_group = ['glass_id', 'x', 'y','defect_count', 'defect_size', 'ai_code_1',  'pi_time', 'pi_hour']
    dbhandler = MySQLConnet('l6a01_project')
    return_dict = []
    for filters in payload.rows:
        # 1) 基本解析
        aoi = str(filters.get('aoi') or '').strip().lower()
        pi_hour_raw = filters.get('pi_hour')
        pi_hour_std = normalize_pi_hour(pi_hour_raw)  # 只做格式標準化
        if not aoi or not pi_hour_std:
            # 格式不對或缺欄位 → 直接回傳空 group
            filters['defect_group'] = {}
            return_dict.append(filters)
            continue
        
        # 2) 組表名：{aoi}_pidensity_20{yymm}_pi{pi}00
        #    例：aoi_density_202509_pi700 → 700 線
        yymm = ym_from_pi_hour(pi_hour_std)         # '2509'
        pi_suffix = extract_pi_suffix(filters.get('line_id', ''))  # '100'/'200'/'700'…
        #print(aoi, yymm, pi_suffix)
        tbname = f'{aoi}_pidensity_20{yymm}_pi{pi_suffix}'.lower()
        # 3) 組查詢條件（只保留 RAW_KEYS 中有提供的）
        key_dict = {k: v for k, v in filters.items() if k in RAW_KEYS}
        
        # 額外：把 pi_hour 替換成標準化字串（供等值匹配；若資料表沒有此欄位會自動被忽略）
        key_dict['pi_hour'] = pi_hour_std
        print('key_dict',key_dict)

        # 4) 查詢（回傳完整列） 
        rows = get_defects_by_key(dbhandler, tbname, key_dict)
        print(f'資料表:{tbname} 查找 defect 資料: {len(rows)}')
        for r in [{key: val for key , val in data.items() if key  in  main_group} for data in rows]:
            print(r)
        # 5) 依 glass_id 分組 + S/M/L/O/total 統計 + defect_map
        defect_group = group_defects_by_glass(rows)
        #print(defect_group)
        filters['defect_group'] = defect_group
        return_dict.append(filters)

    return {"DefectGroupDict": return_dict}