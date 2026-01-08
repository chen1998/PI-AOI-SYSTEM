from fastapi import APIRouter, Query
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict
import pandas as pd
import json
import re
from models.sql_db_connect import MySQLConnet

router = APIRouter()

class Config:
    def __init__(self):
        # ================================================= datetime =================================================
        now = datetime.now()
        ym = now.strftime("%Y%m")
        print(f"INSPECTION連線時間: {now}({ym})")
        self.now = now
        #one_mon_ago = now - timedelta(days=30)
        # ================================================= 資料設定  =================================================
        # === PI Line ====
        self.uni_pi_names = [f'CAPIC{i}07' for i in range(1,8,1)]

        # ==== defect size config  ===
        self.uni_defect_sizes = ['S', 'M', 'L', 'O']
        self.defect_size_col = 'DEFECT_SIZE_TYPE'
        self.size_group_keys = ['S','M','L','O','SM','SL','SO','ML','MO','LO','SML','SMO','SLO','MLO','SMLO']
        self.table_size_cols =['small_defect_count', 'middle_defect_count', 'large_defect_count', 'over_defect_count']
        # === Glass side  ===
        self.glass_sides = ['CF', 'TFT']
        # ==================================== MySQL AOI Inspection datamall 資料表設定 ==========================================
        self.datamall_summary_table_name = f'inspection_summary_table_{ym}'
        self.datamall_raw_table_name = f'inspection_raw_table_{ym}'
        self.api_summary_table_name = f'inspection_api_summary_{ym}'
        self.default_spec_table_name = 'aoi_inspection_default_spectable'
        
        self.datamall_summary_sql_cols = ['CHIP_COUNT', 'CHIP_JUDGE', 'CHIP_OK_COUNT', 'DEFECT', 'FAB',
       'MODEL_NO', 'RECIPE_NAME', 'RUN_ID', 'SCAN_ENDTIME', 'SCAN_STARTTIME',
       'SHEET_ID', 'STAGE', 'TOOL_ID', 'TOTAL_DEFECT_COUNT', 'TYPE']
        
        self.default_spec_tb_cols = ['pi', 'model', 'glass_type', 'line_id', 'OOC', 'OOS', 'Editor', 'modify_time', 'drop']
        self.datamall_rawdata_sql_cols = ['COORD_X', 'COORD_Y', 'DEFECT', 'DEFECT_AREA', 'DEFECT_ID',
       'DEFECT_SIZE_TYPE', 'FAB', 'FRONT_REVERSE', 'IMG_URL', 'RECIPE_NAME',
       'RUN_ID', 'SCAN_ENDTIME', 'SCAN_STARTTIME', 'SHEET_ID', 'SP', 'STAGE',
       'TOOL_ID', 'TOTAL_DEFECT_COUNT']
        
        ### 清理分群欄位
        self.group_keys = ["HOURLY", "TOOL_ID", "MODEL_NO", "TYPE"]
        self.calculate_keys = ['hourly_run_glass_count', 'hourly_defect_count','hourly_defect_glass_couunt']
        self.sub_table_keys = self.uni_defect_sizes + ['glass']
        self.group_table_keys = self.group_keys + self.calculate_keys + self.sub_table_keys 
        
        ## 片數唯一值
        self. uni_glass_keys = ['SHEET_ID','SCAN_ENDTIME']
        
        ### 更改列名為原density命名欄位
        self.datamall_match_api_key_dict = {'HOURLY': 'pi_hour',
                                            'TOOL_ID': 'line_id',
                                            'MODEL_NO': 'model',
                                            'TYPE': 'glass_type',
                                            'hourly_run_glass_count': 'maingroup_glass_count',
                                            'hourly_defect_count': 'maingroup_defect_count',
                                            'hourly_defect_glass_couunt': 'defect_code_glass_count',
                                            'S': 'small_defect_count',  ##datamall_rawdata分群計算
                                            'M': 'middle_defect_count',
                                            'L': 'large_defect_count',
                                            'O': 'over_defect_count',
                                            'glass':'glass',
                                            'comment': 'comment'
                                            }
        
        self.api_summary_sql_cols = ['pi_hour', 'line_id', 'model', 'glass_type', 'maingroup_glass_count',
                                    'maingroup_defect_count', 'defect_code_glass_count',
                                    'small_defect_count', 'middle_defect_count', 'large_defect_count',
                                    'over_defect_count', 'glass', 'comment', 'action', 'glass_size_detail', 'Editor',
                                    'modify_time']
        ['pi_hour', 'line_id', 'model', 'glass_type']
        self.PRIMARY_GROUP_COLS = ["pi_hour", "line_id", "model", "glass_type"]
     
        # =================================================  Default config  =================================================
        self.filter_config = {
            'line_id': ['CAPIC207'],
            'model': [],
            'glass_type': ['TFT'],
            'defect_size':['M', 'L', 'O']
        }

        # 新版：多 tab 用的設定
        self.tab_filter_config = {
            'hourly': {
                'line_id': self.uni_pi_names,
                'model': [],
                'glass_type': ['TFT'],
                'defect_size':['M', 'L', 'O']
            },
            'fixed_spec_table':{
                'type':'table',
                'tab_name':'動態spec',
                'table_columns': {'line_id': 'PI Line', 
                                  'model': 'Model', 
                                  'glass_type': 'glass_side', 
                                  'ai_code_1': 'defect code',
                                  'size_key': 'defect size', 
                                  'final_glass_count': 'total_glass', 
                                  'final_defect_count': 'defect_count', 
                                  'final_density': 'density', 
                                  'OOC':'OOC', 
                                  'OOS': 'OOS'},
                'filter_item_coldict':{
                    'PI Line': {'key':'line_id',
                                'values':[f'CAPIC{i}00' for i in range(1,8,1)]},

                    'model': {'key':'model',
                              'values':[]},

                    'glass_type': {'key': 'glass_type',
                                   'values':[]},
                    'ai_code_1': {'key':'ai_code_1',
                                  'values':[]},
                    'size group': {'key':'size_key',
                                   'values':[]},
                },
            },
            'default_spec_table':{
                'type':'table',
                'tab_name':'預設spec',
                'table_columns':{
                    'line_id': 'PI Line',
                    'model': 'Model',
                    'glass_type': 'Type',
                    'OOC':'OOC', 
                    'OOS':'OOS',
                    'Editor':''
                },
                'filter_item_coldict':{
                    'PI Line': {'key':'line_id',
                                'values':[f'CAPIC{i}07' for i in range(1,8,1)]},
                    'Model': {
                        'key': 'model',
                        'values': []
                    },
                    'Type':{
                        'key':'glass_type',
                        'values':self.glass_sides
                    }
                },
            },
            'TrendChart':{
                'type':'Chart',
                'tab_name':'趨勢分析(月週日)',
                
            },
            'EditSummary':{
                'type':'table',
                'tab_name':'Action_History',
                'filter_item_coldict':{
                    'PI Line': {'key':'line_id',
                                'values':[f'CAPIC{i}07' for i in range(1,8,1)]},
                    'Model': {
                        'key': 'model',
                        'values': []
                    },
                    'Type':{
                        'key':'glass_type',
                        'values':self.glass_sides
                    }
                },
                
            }
        }
    # ================================================= 前端網頁CONFIG =================================================
        self.chart_table_coldict = {
            'line_id': 'PI Line',
            'model': 'Model',
            'glass_type': 'side',
            'pi_hour': 'Hourly',
            'maingroup_glass_count': 'total gld',   # maingroup分群後的玻璃總片數
            'maingroup_defect_count': 'total def',  # maingroup分群後的總defect 數
            
            'glass': 'glass',                        # list ,次分群中對應的glass名稱
            'glass_size_detail':'detail',
            #'comment':'comment',
            #'action':'action'

        }
        

        self.table_group_key_dict = {
            'main_group': ['pi_hour', 'line_id',  'model',  'glass_type', 'maingroup_glass_count','maingroup_defect_count',
                           'comment',  'action', 'Editor','modify_time'],
                           #'maingroup_glass_count', 'maingroup_defect_count'],
            'uni_col': ['defect_code_glass_count', 'defect_code_count', 'glass_defect_count', 'glass']
            # glass 依照現有邏輯分割後單獨對應 uni_col 中的其他欄位資訊
        }

        self.chart_group_dict = {
            'left': ['line_id','model','maingroup_glass_count', 'defect_code_glass_count'],
            'down': ['pi_hour'],
            'right':['density'],
        }

        self.uni_glass_row_info_dict = {
            'glass_id': 'glass',
            'glass_defect_count':'glass_defect_count',
            'small_defect_count': 'S',
            'middle_defect_count': 'M',
            'large_defect_count': 'L',
            'over_defect_count':  'O'
        }

        self.defect_group_coldict = {'COORD_X': 'x', 'COORD_Y': 'y',  'IMG_URL':'img'}

        self.filter_item_coldict = {
            'line_id': 'PI Line',
            'model': 'Model',
            'glass_type': 'glass_side',
            'defect_size': 'defect size'
        }

        self.front_config = {
            'chartKeyDict': self.chart_group_dict,
            'filtetItemKeyDict': self.filter_item_coldict,
            'hourlyTable': self.chart_table_coldict,
            'hourlyTable_key_group': self.table_group_key_dict,
            'uniGlassInfo': self.uni_glass_row_info_dict,
            'uniGlassDefectTable': self.defect_group_coldict,
            # 保留舊的（如果 filter.js 有用到）
            'FilterDefaultDict': self.filter_config,
            # 新增：SubTabsFilterDefaultDict，給前端建右上 tab button 用
            'SubTabsFilterDefaultDict': self.tab_filter_config
        }
    
    
    def spec_table_clean(self, dbhandler):
        key_cols = ['pi', 'model', 'glass_type', 'line_id', 'OOC', 'OOS']
        default_df = dbhandler.get_table(self.default_spec_table_name)
        default_df = default_df[default_df['drop'] == 'F']
        default_df = default_df.drop_duplicates(subset=key_cols, keep='last')
        default_df = default_df.sort_values(key_cols)
        default_df.reset_index(drop = True, inplace = True)

        prospecdict = {'default_spec_table': default_df.iloc[:,1:].to_dict(orient = 'index'),
         'fixed_spec_table': {}}
        
        item_coldict = {}
        for key in ['model', 'line_id']:
            
            options = default_df[key].unique().tolist()
            item_coldict[key] = options

        item_coldict.update({
            'glass_type':self.glass_sides ,
            'defect_size': self.size_group_keys[:4]
        })

        self.front_config['SubTabsFilterDefaultDict']['TrendChart']['filter_item_coldict'] = item_coldict
        return prospecdict

# -------- 小工具 --------
def action_history(df):
    history_keys = ['pi_hour', 'line_id', 'model', 'glass_type', 'comment', 'action', 'Editor','modify_time']
    clean_df = df[(df['action'] !='') | (df['comment'] !='')][history_keys]
    #clean_df['pi_hour'] = clean_df['pi_hour'].apply(lambda x: x.split(":")[0])
    clean_df['pi_hour'] = clean_df['pi_hour'].apply(lambda x: str(x.strftime("%Y-%m-%d %H"))[2:])
    #print(clean_df)
    return clean_df.to_dict(orient = 'index')
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

# -------------- datamall clean to api ------------------
def _add_hourly_col(df: pd.DataFrame, time_col: str = "SCAN_ENDTIME") -> pd.DataFrame:
    """
    由 time_col 產生 'HOURLY' 欄位，格式為整點時間。
    若 time_col 不存在則原樣回傳。
    """
    if time_col not in df.columns:
        print(f"[WARN] 欄位 {time_col} 不存在，無法產生 HOURLY")
        return df

    df = df.copy()
    dt = pd.to_datetime(df[time_col], errors="coerce")
    # 依需求可選擇用 floor('H') 或字串格式，這裡用 floor:
    #df["HOURLY"] = dt.dt.floor("H")
    df["HOURLY"] = dt.dt.floor("H").dt.strftime("%Y-%m-%d %H")
    return df


def _split_recipe_to_model_type(df: pd.DataFrame, col: str = "RECIPE_NAME") -> pd.DataFrame:
    """
    將 RECIPE_NAME 切割成 MODEL_NO 與 TYPE 兩欄。
    假設格式類似 'MODEL_NO_TYPE'，用第一次 '_' 分割。
    若沒有 '_'，MODEL_NO = 原字串，TYPE = 空字串。
    """
    if col not in df.columns:
        print(f"[WARN] 欄位 {col} 不存在，無法切割 MODEL_NO / TYPE")
        return df

    df = df.copy()
    # 確保是字串
    s = df[col].astype(str)
    parts = s.str.split("-", n=1, expand=True)

    df["MODEL_NO"] = parts[0]
    if parts.shape[1] > 1:
        df["TYPE"] = parts[1]
    else:
        df["TYPE"] = ""

    return df


def get_tables(dbhandler, cfg):
    # 取得 summary、raw
    summary_df = dbhandler.get_table(cfg.summary_table_name)
    #print("summary_df 原始筆數:", len(summary_df))

    raw_df = dbhandler.get_table(cfg.raw_table_name)
    #print("raw_df 原始筆數:", len(raw_df))

    # ===== 清理 summary：SCAN_ENDTIME → HOURLY =====
    summary_df = _add_hourly_col(summary_df, time_col="SCAN_ENDTIME")
    #print("summary_df 加 HOURLY 後欄位:", summary_df.columns.tolist())

    # ===== 清理 raw：RECIPE_NAME 切 MODEL_NO / TYPE, SCAN_ENDTIME → HOURLY =====
    raw_df = _split_recipe_to_model_type(raw_df, col="RECIPE_NAME")
    raw_df = _add_hourly_col(raw_df, time_col="SCAN_ENDTIME")
    #print("raw_df 加 MODEL_NO / TYPE / HOURLY 後欄位:", raw_df.columns.tolist())

    return summary_df, raw_df


# ============== 主要 API ==============

@router.get("/api/reset_summary_filter")
async def reset_summary_filter(
    dates: Optional[List[str]] = Query(None, description="['YYYY-MM-DD [HH:MM:SS]', 'YYYY-MM-DD [HH:MM:SS]']"),
    filter_ask_keys: Optional[str] = Query(None, description="JSON 物件字串：{'line_id': [...], 'aoi': [...], 'model': [...], 'glass_type': [...], 'ai_code_1': [...], 'glass_id': [...], 'defect_size': ['S','M','L','O']}")
):
    """
    回傳：
    - DictData：摘要列資料（list of dict），增加 defect size 前端可用欄位：
        * available_sizes: 例如 ['S','L']，此列出現過的 size
        * size_mask: 位元遮罩（S=1, M=2, L=4, O=8）
    - ParamDict：給前端的固定設定與選項（含 DefectSize.maskBits/virtualKey/maskKey）
    - ProSpecDict：規格表
    """
    cfg = Config()
    dbhandler = MySQLConnet('l6a01_project')

    # 解析日期區間
    if dates and len(dates) == 2:
        start = _parse_dt(dates[0])
        end   = _parse_dt(dates[1])
        if end < start:
            start, end = end, start
    else:
        # 預設：近 3 天（含當前小時）
        now = datetime.now()
        end = now.replace(minute=0, second=0, microsecond=0)
        start = end - timedelta(days=3)

    months = _month_span(start, end)

    # 解析 filters（本 API 不做篩選，僅解析保留）
    try:
        filters: Dict[str, List[str]] = json.loads(filter_ask_keys) if filter_ask_keys else {}
        if not isinstance(filters, dict):
            filters = {}
    except Exception:
        filters = {}
    #print(f'日期: {start}, {end} \nfilters: {filters}')

    # 載入資料
    frames: List[pd.DataFrame] = []
    optionDict = {key: [] for key in cfg.filter_item_coldict.keys()}
    optionDict['defect_size'] = cfg.uni_defect_sizes  # 先放預設，之後改成「實際出現」的 size

    for ym in months:
        tbn = f'inspection_api_summary_{ym}'
        df = _try_get_table(dbhandler, tbn)
        #print('get_table',len(df))
        if df is None or df.empty:
            continue
        # 移除 *_hash 欄位
        df.fillna('', inplace=True)
        df.reset_index(inplace=True, drop=True)

        # 蒐集 option 值（先不包含 defect_size，稍後從 computed 欄位補）
        for key in cfg.filter_item_coldict.keys():
            if key in df.columns and key != 'defect_size':
                new_options = [v for v in df[key].unique().tolist() if v not in optionDict[key]]
                optionDict[key] = optionDict[key] + new_options

        # 時間窗
        df["pi_hour"] = pd.to_datetime(df["pi_hour"], errors='coerce')
        frames.append(df[(df["pi_hour"] >= start) & (df["pi_hour"] <= end)])

    if frames:
        clean_df = pd.concat(frames, ignore_index=True)
    else:
        clean_df = pd.DataFrame(columns=cfg.api_summary_sql_cols)
    #print('clean_df', len(clean_df))

    # ======================== 前置作業：給前端做 defect size 篩選 ========================
    SIZE_COLS: Dict[str, str] = {
        'S': 'small_defect_count',
        'M': 'middle_defect_count',
        'L': 'large_defect_count',
        'O': 'over_defect_count',
    }
    # 數值化四個 count 欄位
    for _sz, _col in SIZE_COLS.items():
        if _col in clean_df.columns:
            clean_df[_col] = pd.to_numeric(clean_df[_col], errors='coerce').fillna(0).astype(int)
        else:
            clean_df[_col] = 0  # 若不存在，補 0 以便後續運算

    # 產生位元遮罩與每列可用 size 陣列
    def _to_size_mask(row) -> int:
        mask = 0
        mask |= 1 if row.get('small_defect_count', 0)  > 0 else 0  # S
        mask |= 2 if row.get('middle_defect_count', 0) > 0 else 0  # M
        mask |= 4 if row.get('large_defect_count', 0)  > 0 else 0  # L
        mask |= 8 if row.get('over_defect_count', 0)   > 0 else 0  # O
        return mask

    def _mask_to_sizes(mask: int) -> List[str]:
        return [s for s,b in [('S',1),('M',2),('L',4),('O',8)] if (mask & b) != 0]

    if not clean_df.empty:
       # print(clean_df.iloc[0,:].to_dict())
        clean_df['size_mask'] = clean_df.apply(_to_size_mask, axis=1).astype(int)
        clean_df['available_sizes'] = clean_df['size_mask'].apply(_mask_to_sizes)
    else:
        clean_df['size_mask'] = pd.Series([], dtype='int64')
        clean_df['available_sizes'] = pd.Series([], dtype='object')

    # 依當前時間窗內實際出現的 size 更新下拉選單
    if 'available_sizes' in clean_df.columns and not clean_df.empty:
        #print('available_sizes\n',clean_df.iloc[0,:].to_dict())
        appear = set()
        for lst in clean_df['available_sizes']:
            if isinstance(lst, list):
                appear.update(lst)
        optionDict['defect_size'] = sorted(list(appear)) or cfg.uni_defect_sizes
    else:
        optionDict['defect_size'] = cfg.uni_defect_sizes

    # 告訴前端位元定義與欄位名
    DEFECT_SIZE_META = {
        'maskBits': {'S':1, 'M':2, 'L':4, 'O':8},
        'virtualKey': 'available_sizes',  # 前端可用此欄位直接做包含判斷
        'maskKey': 'size_mask'            # 或用位元遮罩做 AND/OR 判斷
    }
    cfg.front_config['DefectSize'] = DEFECT_SIZE_META

    # ======================== 回傳資料整備 ========================
    # 只抽出要回傳的欄位 + 新增的 size 欄位
    filter_cols = [c for c in cfg.api_summary_sql_cols if c in clean_df.columns]
    for extra in ['available_sizes', 'size_mask']:
        if extra in clean_df.columns and extra not in filter_cols:
            filter_cols.append(extra)
    clean_df[filter_cols].fillna("", inplace= True)
    #test_df = clean_df[clean_df['model'] == 'G101EAN2G']
    #print(test_df)
    Data =clean_df.to_dict(orient="records")
    cfg.front_config['filterOptionDict'] = optionDict
    #print(optionDict)
    #print('enddata \n',clean_df.iloc[-1,:].to_dict())
    prospecdict = cfg.spec_table_clean(dbhandler)

    prospecdict['EditSummary'] = action_history(clean_df)
    #print(cfg.front_config['SubTabsFilterDefaultDict']['TrendChart'])
    #print('data', len(Data))
    return {
        "DictData": Data,
        "ParamDict": cfg.front_config,
        "ProSpecDict": prospecdict
    }