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

class EditSummaryRequest(BaseModel):
    system: str = "inspection"
    tabKey: Optional[str] = None  # 會是 "EditSummary"
    start_date: str               # "YYYY-MM-DD"
    end_date: str                 # "YYYY-MM-DD"

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
            match_keys = ["pi_hour", "line_id", "model", "glass_type"]
            if not payload.row:
                raise HTTPException(status_code=400, detail="row is required for comment")
            row = payload.row
            #print('row', row)
            pi_hour = row['pi_hour']
            ym = pi_hour[:5].replace("-", '')

            if payload.system == 'inspection':
                cond = {k:v for k, v in row.items() if v is not None and k in match_keys}
                cond.update({'pi_hour': f'20{pi_hour}'})
            else:
                raise HTTPException(status_code=400, detail="row is required for comment")
            
            new_value = getattr(payload, update_key, None)
            #print('new_value',new_value)
            if new_value is None:
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


@router.post("/api/edit_summary")
async def api_inspection_edit_summary(req: EditSummaryRequest):
    """
    EditSummary 專用：依日期範圍重撈資料，回傳：
    {
      "ok": true,
      "prospecdict": {
        "EditSummary": [ {...}, {...}, ... ]
      }
    }
    """
    if req.system != "inspection":
        raise HTTPException(status_code=400, detail="system must be 'inspection'")
    
    try:
        dt_start = _parse_dt(req.start_date)      # 00:00:00
        dt_end   = _parse_dt(req.end_date)        # 00:00:00
        dt_end_excl = dt_end + timedelta(days=1)  # 右開區間，含當天
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"bad date range: {e}")

    dbhandler = MySQLConnet("l6a01_project")

    # 這個時間區段涵蓋哪些年月
    ym_list = _month_span(dt_start, dt_end_excl)
    print(dt_start, dt_end, ym_list)
    dfs = []
    for ym in ym_list:
        #  根據你現有 comment/action 的 table 命名方式
        # inspection_api_summary_20{ym}，其中 ym 是 "2512" 這樣
        # 這裡我們直接用四碼年月，例如 "202512"
        tbn = f"inspection_api_summary_{ym}"
        df = _try_get_table(dbhandler, tbn)
        if df is None or df.empty:
            continue

        if "pi_hour" not in df.columns:
            continue

        # pi_hour 轉 datetime
        def _parse_pi_hour(x):
            s = str(x).strip()
            # 例： "25-12-27 14" → "2025-12-27 14:00"
            if re.match(r"^\d{2}-\d{2}-\d{2} \d{2}$", s):
                s2 = "20" + s       # "2025-12-27 14"
                return datetime.strptime(s2, "%Y-%m-%d %H")
            # 若本來就 "2025-12-27 14:00:00" 類型
            try:
                return pd.to_datetime(s)
            except Exception:
                return None

        df["pi_hour_dt"] = df["pi_hour"].apply(_parse_pi_hour)
        m = (df["pi_hour_dt"] >= dt_start) & (df["pi_hour_dt"] < dt_end_excl) & ((df['action'] !='') | (df['comment'] !=''))
        sub = df.loc[m].copy()
        if not sub.empty:
            dfs.append(sub)

    if dfs:
        df_all = pd.concat(dfs, ignore_index=True)
        # 你要的排序方式：假設用時間排序
        df_all = df_all.sort_values(by=["pi_hour_dt", "line_id", "model"], ascending=True)
        # 不要輸出 helper 欄位
        df_all = df_all.drop(columns=["pi_hour_dt"])
        rows = df_all.to_dict(orient="records")
    else:
        rows = []

    return {
        "ok": True,
        "prospecdict": {
            "EditSummary": rows
        }
    }