from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text
from typing import Optional, Dict, List
from datetime import datetime, timedelta
from models.sql_db_connect import MySQLConnet
import pandas as pd

router = APIRouter()

    

class Config:
    def __init__(self):
        # =================== datetime ==========================
        now = datetime.now()
        ym = now.strftime("%Y%m")
        print(f"連線時間: {now}({ym})")
        one_mon_ago = now - timedelta(days=30)
        # ================== 摘要資料表名稱 ========================
        self.aoi_names = [f'aoi{i}00' for i in range(1,4,1)]
        self.all_aoi_summary_tbns = [f'aoi_summary_{n}' for n in self.aoi_names]
        
        self.aoi_name_vs_lineid = { 'CAPIT203': 'aoi_summary_aoi100',
                                'CAAOI202': 'aoi_summary_aoi200',
                                'CAAOI300': 'aoi_summary_aoi300'}
        
        self.all_line_tabs = list(self.aoi_name_vs_lineid.keys())
        
        # ======================= 欄位設定 ========================
        #'run_day', 'scantime', 'line_id', 'model', 'glass_id', 'recipe_id', \
        # 'defect_count', 'over_defect_count', 'large_defect_count', 'middle_defect_count', 'small_defect_count', 'chips', 'sample_image_path'
        self.run_info_keys = ['run_day', 'scantime', 'line_id', 'model', 'glass_id', 'recipe_id', 'chips', 'image_path'] #'sample_image_path'
        self.defect_summary_keys = ['defect_count', 'over_defect_count', 'large_defect_count', 'middle_defect_count', 'small_defect_count'] 
        self.run_info_table_cols = self.run_info_keys + ['defect_summary']
        self.defect_position_keys = ['x', 'y', 'defect_size', 'pic_name']

        #======================= 前端要求參數設定 =====================
        self.run_info_ask_keys = ['dates', 'line_id']

    def summary_table_clean_process(self, tb):
        tb['defect_summary'] = [{key: row[key] for key in self.defect_summary_keys} for _, row in tb.iterrows()]
        if 'sample_image_path' in tb.columns:
            tb['image_path'] = tb['sample_image_path'].tolist()
        return tb[self.run_info_table_cols ]
    
    def get_all_run_info_data(self, dbhandler):
        lines = [f'aoi{i}00' for i in range(1,4,1)]
        all_line_summary = {}
       # aoi_name_vs_line_id = {}
        for tbn in self.all_aoi_summary_tbns:
            tb = dbhandler.get_runs_delta_days(tbn, days=3)
            print(tbn, len(tb))
            if tb.empty:
                if len([key for key, val in self.aoi_name_vs_lineid.items() if val == tbn]) ==1:
                    line_id = [key for key, val in self.aoi_name_vs_lineid.items() if val == tbn][0]
                    tb = pd.DataFrame(columns = self.run_info_table_cols)
                else:
                    continue
            else:
                line_id = tb['line_id'].unique()[0]
                tb = self.summary_table_clean_process(tb)
            all_line_summary[line_id] = tb.to_dict(orient = 'index')

        return all_line_summary



@router.get("/api/run-info", tags=["run-info"])
async def api_run_info(
    line_id: Optional[str] = Query(default=None),
    start: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    end: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
):
    cfg = Config()
    dbhandler = MySQLConnet('l6a01_project')

    # 根據 request去篩選資料
    if not line_id:
        all_run_info_dict = cfg.get_all_run_info_data(dbhandler)

    else  :
        if line_id in cfg.aoi_name_vs_lineid.keys():
            try:
            #CAPIT203
                aoi_name = cfg.aoi_name_vs_lineid[line_id]
                print(f'請求 {aoi_name} 資料')
                tb = dbhandler.get_runs_between(aoi_name, start, end)
                
                tb = cfg.summary_table_clean_process(tb)

                return {
                    'UniRunInfoTableData':tb.to_dict(orient = 'index'),
                    "AllLineTabs":cfg.all_line_tabs
                    }
                
            except:
                
                print(f'[ERROR] {line_id} 匹配 aoi_summary table失敗')
                return  {
                    'UniRunInfoTableData':{},
                    "AllLineTabs":cfg.all_line_tabs
                    }
            

    return{ 
        "AllRunInfoTableData": all_run_info_dict,
        "AllLineTabs":cfg.all_line_tabs
        }
    

# ======== 新增：/api/defect-data（支援 key 與拆參數）========
@router.get("/api/defect-data", tags=["run-info"])
async def api_defect_data(
    key: Optional[str] = Query(default=None),
    line_id: Optional[str] = Query(default=None)):
    """
    glass_id: Optional[str] = Query(default=None),
    recipe_id: Optional[str] = Query(default=None),
    scantime: Optional[str] = Query(default=None),  # 'YYYY-MM-DD HH:MM:SS'
    """
    dbhandler = MySQLConnet('l6a01_project')

    print(f'[前端參數] {key} ...........')
    try:
        parts = key.split("|")
        if len(parts) == 3:
            scantime, glass_id, recipe_id = parts
    except Exception:
        return JSONResponse({"defects": []})
        

    if not (glass_id and recipe_id and scantime):
        return JSONResponse({"defects": []})
    
    cfg = Config()
    # line_id -> 系列（aoi100/aoi200/aoi300）
    aoi_name = None
    if line_id:
        aoi_name = cfg.aoi_name_vs_lineid[line_id].split("_")[-1]
    # 依 scantime -> yyyymm -> 月表
    try:
        yyyymm = scantime[:7].replace("-", "")
    except Exception:
        return JSONResponse({"defects": []})

    aoi_line_ym_tbn = f"{aoi_name}_rawdata_{yyyymm}"
    #print('aoi_line_ym_tbn',aoi_line_ym_tbn)
    key_dict = {"gid": glass_id, "rid": recipe_id, "t": scantime}
    print(f'[查詢] {aoi_line_ym_tbn} - {key_dict}')
    #print('key_dict',key_dict)
    key_rows = dbhandler.get_defects_by_key(aoi_line_ym_tbn , key_dict)
    print(f'[查詢結果] Defect 筆數: {len(key_rows)}')
    #print('key_rows',key_rows)
    #print(pd.DataFrame(key_rows))
    if key_rows:
        return JSONResponse({"defects": key_rows, "key": key})
    else:
        return JSONResponse({"defects": [], "key": key})
