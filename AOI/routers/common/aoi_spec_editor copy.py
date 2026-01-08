from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime, timedelta
from collections import defaultdict
import pandas as pd
import json
import re
from models.sql_db_connect import MySQLConnet
from pydantic import BaseModel
#from routers.aoi_density_pihour import Config
#from routers.aoi_inspection import Config
router = APIRouter()

    

# -------- 小工具 --------

def _parse_dt(s: str) -> datetime:
    """接受多種格式：YYYY-MM-DD[ HH[:MM[:SS]]] 與 YY-MM-DD[ HH]."""
    s = s.strip().replace("T", " ")
    fmts = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H", "%Y-%m-%d",
            "%y-%m-%d %H", "%y-%m-%d"]
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

def _month_span(start: datetime, end: datetime) -> List[str]:
    ym = []
    cur = datetime(start.year, start.month, 1)
    last = datetime(end.year, end.month, 1)
    while cur <= last:
        ym.append(cur.strftime("%Y%m"))
        nxt = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)  # 下一個月
        cur = nxt
    return ym

def _try_get_table(dbhandler, tbn: str) -> Optional[pd.DataFrame]:
    try:
        df = dbhandler.get_table(tbn)
        if df is not None and len(df) > 0:
            return df
    except Exception:
        pass
    # 試試大寫
    try:
        df = dbhandler.get_table(tbn.upper())
        if df is not None and len(df) > 0:
            return df
    except Exception:
        pass
    return None





class EditChange(BaseModel):
    rowIndex: int
    row: Dict[str, Any]
    key: str
    oldValue: Any = None
    newValue: Any


class FrontEditorPayload(BaseModel):
    mode: Literal["edit", "add", "delete", "comment", "action"]
    tabKey: Optional[str] = None

    # edit 用
    changes: Optional[List[EditChange]] = None

    # add/delete/edit 可用
    row: Optional[Dict[str, Any]] = None

    # 系統別
    system: str

    # comment 專用（你前端目前想送的欄位）
    comment: Optional[str] = None          # 更新後 comment
    action: Optional[str] = None          # 更新後 action
    editor: Optional[str] = None           # 更新後 editor
    modify_time: Optional[str] = None      # 更新後 modify_time（字串，後端可直接存或 parse）

@router.post("/api/front_editor")
async def front_editor(payload: FrontEditorPayload):
    """
    前端 default_spec_table 編輯 / 新增的寫回 API

    body 結構：
    - 編輯：
        {
          "mode": "edit",
          "tabKey": "default_spec_table",
          "changes": [
            {
              "rowIndex": 0,
              "row": {...原本整列...},
              "key": "OOC",
              "oldValue": "0.5",
              "newValue": "0.7"
            },
            ...
          ]
        }

    - 新增：
        {
          "mode": "add",
          "tabKey": "default_spec_table",
          "row": {
            "MODEL_ID": "...",
            "MODEL_TYPE": "...",
            ...
          }
        }
    """
      
    dbhandler = MySQLConnet('l6a01_project')

    print(payload.system)
    if payload.system == 'density':
        from routers.density.aoi_density_pihour import Config
    elif payload.system == 'inspection':
        from routers.inspection.aoi_inspection import Config
    cfg = Config()
    table_name = cfg.default_spec_table_name
    
    if payload.system == 'density':
        coldict = {v: k for k, v in cfg.default_spec_coldict.items()}
        #print(coldict)
    
    try:
        if payload.mode == "edit":
            
            if not payload.changes:
                raise HTTPException(status_code=400, detail="changes is required for edit")

            for ch in payload.changes:
                row = ch.row or {}
                update_col = ch.key
                #
                # 組 WHERE 條件
                if payload.system == 'density':
                    cond = {coldict[k]: row.get(k) for k, val in row.items() if k in coldict.keys() and k not in ['Editor', 'modify_time', update_col]}  
                elif payload.system == 'inspection':
                    cond = {k: val for k, val in row.items() if  k not in ['Editor', 'modify_time', update_col]}  
                if not cond :
                   continue
                #print('cond', cond)
                update_dict = {key: row.get(key) for key in ['Editor', 'modify_time', update_col]}
                #print('update_dict', update_dict)
                #dbhandler.append_single_row_with_nan(cfg.default_spec_table_name, cond)
                dbhandler.update_rows(table_name, cond, update_dict)

        elif payload.mode == "add":
            if not payload.row:
                raise HTTPException(status_code=400, detail="row is required for add")

            row = payload.row
            if payload.system == 'density':
                cond = {coldict[k]: val for k, val in row.items() if k in coldict.keys()  }
            elif payload.system == 'inspection':
                cond = row
            cond.update({'drop': 'F'})
            #print('cond', cond)
            dbhandler.append_single_row_with_nan(table_name, cond)
        
        elif payload.mode == "delete":
            if not payload.row:
                raise HTTPException(status_code=400, detail="row is required for delete")
            row = payload.row
            update_dict = {
                'modify_time': cfg.now.strftime("%Y-%m-%d %H:%M:%S"), 
                'drop': 'T'
            }
            if payload.system == 'density':
                cond = {coldict[k]: val for k, val in row.items() if k in coldict.keys() and k not in  update_dict.keys()}
            elif payload.system == 'inspection':
                cond = {k: val for k, val in row.items() if  k not in ['Editor', 'modify_time']}  

            #print('cond', cond)
            #print('update_dict', update_dict)
            dbhandler.update_rows(table_name, cond, update_dict)
            
        elif payload.mode in ["comment", "action"]:
            # ===== 先確認 payload =====
            print("[comment / action] payload =", payload.model_dump())
            update_key = payload.mode
            if not payload.row:
                raise HTTPException(status_code=400, detail="row is required for comment")
            row = payload.row
            print('row', row)
            pi_hour = row['pi_hour']
            ym = pi_hour[:5].replace("-", '')

            if payload.system == 'inspection':
                cond = row
                cond.update({'pi_hour': f'20{pi_hour}'})
            else:
                raise HTTPException(status_code=400, detail="row is required for comment")
            
            new_value = getattr(payload, update_key, None)
            if new_value is None:
                # 給一個明確錯誤訊息，方便 debug
                raise HTTPException(
                    status_code=400,
                    detail=f"{update_key} value is missing in payload",
                )
            
            table_name = f'inspection_api_summary_20{ym}'
            update_dict = {'Editor': payload.editor, 
                           'modify_time': payload.modify_time,
                           update_key: new_value}
            print(f"[{table_name}] match_dict =", cond, "update = ", update_dict)
            dbhandler.update_rows(table_name, cond, update_dict)

    except Exception as e:
        print("[front_editor] error:", e)
        raise HTTPException(status_code=500, detail=str(e))
  
    return {"ok": True}


