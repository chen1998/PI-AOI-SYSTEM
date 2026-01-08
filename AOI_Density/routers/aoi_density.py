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
        print(f"連線時間: {now}({ym})")
        one_mon_ago = now - timedelta(days=30)
        # ================================================= 資料設定  =================================================
        # === PI Line & AOI Tool  ====
        self.uni_aoi_names = [f'aoi{i}00' for i in range(1,4,1)]
        self.uni_pi_names = [f'pi{i}00' for i in range(1,8,1)]
        # === particle type & defect code ====
        self.uni_UPI_defect_codes = ['Polymer', 'SSIU_Polymer']
        self.uni_SPOT_defect_codes = ['PI_Spot_NP', 'PIS With Particle']
        self.uni_SPS_defect_codes= ['SPS']
        self.uni_defect_types = ['Particle', 'PISpot']
        self.all_defect_codes = ['Polymer', 'SSIU_Polymer', 'PI_Spot_NP', 'PIS With Particle', 'SPS']
        # ==== defect size config  ===
        self.uni_defect_sizes = ['S', 'M', 'L', 'O']
        self.rawdata_defect_size_col = 'defect_size'
        self.size_group_keys= ['S','M','L','O','SM','SL','SO','ML','MO','LO','SML','SMO','SLO','MLO','SMLO']
        self.defect_size_rules = {
            "S": lambda x: x <= 20,
            "M": lambda x: 21 <= x <= 100,
            "L": lambda x: 101 <= x <= 400,
            "O": lambda x: x >= 401,
        }
        # === Glass side  ===
        self.glass_sides = ['CF', 'TFT']

        # =================================================  UPI/SPOT Default config  ================================================= 
        
        self.tab_filter_config = {
            'UPI': {
                'line_id': ['CAPIC200'],
                'ai_code_1': self.uni_UPI_defect_codes,
                'recipe_id':[]
                },
            'PISpot': {
                'line_id': ['CAPIC200'],
                'ai_code_1': self.uni_SPOT_defect_codes,
                'recipe_id':[]
                },
            'SPS': {
                'line_id': [f'CAPIC{i}00' for i in range(1,8,1)],
                'ai_code_1': self.uni_SPS_defect_codes,
                'recipe_id':[]
                },
            'SPEC':{

            }
        }
        
        # ================================================= MySQL AOI Density 資料表設定 ================================================= 
        self.aoi_pidensit_summary_tbn = f'pidensity_{ym}'
        self.aoi_pi_density_tbns = [f'{aoi}_pidensity_yyyymm_{pi}' for aoi in self.uni_aoi_names for pi in self.uni_pi_names]
        self.aoi_pidensity_spec_tbn = 'aoi_spec_for_aoimonitor'
        print('預設讀取:',self.aoi_pidensit_summary_tbn)


        self.aoi_pidensity_spec_cols = ['NO', 'MODEL_ID', 'MODEL_TYPE', 'DEFECT_CODE', 'PROCESS_TYPE', 'SIZE_TYPE', 'OOC', 'OOS']
        self.aoi_density_summary_sql_cols = ['pi_hour', 'aoi', 'pi', 'line_id', 'model', 'glass_type', 'recipe_id','defect_type', 'ai_code_1', 
                                             'n_rows', 'n_glasses', 'small_defect_count','middle_defect_count', 'large_defect_count', 'over_defect_count',
                                             'unknown_defect_count', 'glass']
        
        self.aoi_density_rawdata_sql_cols = ['scan_time', 'line_id', 'model', 'glass_type', 'recipe_id', 'glass_id',
       'pic_name', 'x', 'y', 'predict_code', 'judge_code', 'mark', 'hour','dayhour', 'day', 'year', 'month', 'season', 'week', 'yearmonth',
       'defect_count', 'defect_size', 'open_status', 'ai_code_1', 'ai_code_2','ai_code_3', 'ai_code_4', 'ai_code_5', 'gray_name', 'ip_num',
       'first_code', 'chip_name', 'defect_seq']
        
        self.sql_group_keys = ['line_id', 'aoi', 'model', 'glass_type', 'recipe_id','defect_type', 'ai_code_1','pi_hour'  ]
        
        # ================================================= 前端網頁CONFIG ================================================= 
        self.chart_table_coldict = {
                                    'line_id': 'PI Line',
                                    'aoi':'aoi',
                                    'model': 'Model', 
                                    'glass_type': 'side',
                                    'pi_hour': 'Hourly',
                                    'recipe_id':'recipe',
                                    'ai_code_1': 'defect', 
                                    'n_glasses': 'glassNum', 
                                    'n_rows': 'defNum',
                                    'glass': 'glass', #list ,group中的所有glass
                                    'glass_defect_count': 'glass def statis'} #dict, group中的所有glass_id對應單片glass defect
        """
        
        """   
                                                
        self.chart_group_dict = {
            'left':['line_id','model','n_glasses'],
            'up': [ 'aoi', 'ai_code_1'] ,
            'down':['pi_hour'],
            'right':['density'],
            }
        
        self.uni_glass_row_info_dict = {'glass_id': 'glass', 
                                        'glass_defect_count':'glass_defect_count',  
                                        'small_defect_count': 'S',
                                        'middle_defect_count': 'M', 
                                        'large_defect_count': 'L', 
                                        'over_defect_count': 'O'}
        self.defect_group_coldict = {
            'x': 'x',
            'y': 'y',
            'chip_name': 'chip',
            'pic_name':'img'}
        
        self.filter_item_coldict = {
            'line_id': 'PI Line',
            'aoi':'aoi tools',
            'model': 'Model', 
            'recipe_id':'recipe',
            'glass_type': 'glass_side',
            'ai_code_1': 'defect code', 
            'defect_size': 'defect size',
        }


        self.front_config = {
            'chartKeyDict': self.chart_group_dict,
            'filtetItemKeyDict':self.filter_item_coldict,
            'hourlyTable': self.chart_table_coldict,
            'uniGlassInfo': self.uni_glass_row_info_dict,
            'uniGlassDefectTable': self.defect_group_coldict,
            'SubTabsFilterDefaultDict':self.tab_filter_config
        }
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
        # 下一個月
        nxt = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
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


# ============== 主要 API ==============

@router.get("/api/reset_summary_filter") #, tags=["run-info"]
async def reset_summary_filter(
    dates: Optional[List[str]] = Query(None, description="['YYYY-MM-DD [HH:MM:SS]', 'YYYY-MM-DD [HH:MM:SS]']"),
    filter_ask_keys: Optional[str] = Query(None, description="JSON 物件字串：{'line_id': [...], 'aoi': [...], 'model': [...], 'glass_type': [...], 'ai_code_1': [...], 'glass_id': [...], 'defect_size': ['S','M','L','O']}")
):
    """
    回傳：
    - ChartDataDict：巢狀 dict，鍵順序 line_id→aoi→model→glass_type→ai_code_1→pi_hour
    - FilterData：依 filter_ask_keys 過濾後的列資料（list of dict）
    - ParamDict：給前端的固定設定（來自 Config.front_config）
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
    # 解析 filters
    try:
        filters: Dict[str, List[str]] = json.loads(filter_ask_keys) if filter_ask_keys else {}
        if not isinstance(filters, dict):
            filters = {}
    except Exception:
        filters = {}
    print(f'日期: {start}, {end} \nfilters: {filters}')

    # 載入資料
    frames: List[pd.DataFrame] = []
    optionDict = {key: [] for key in cfg.filter_item_coldict.keys()}
    optionDict['defect_size'] = cfg.uni_defect_sizes
    
    for ym in months:
        tbn = f"pidensity_{ym}"
        df = _try_get_table(dbhandler, tbn)
        if df is None or df.empty:
            continue
        # 保留 summary 欄位
        keep_cols = [c for c in cfg.aoi_density_summary_sql_cols if c in df.columns]
        df = df[keep_cols].copy()
        df = df[df['ai_code_1'] != 'Not_Found']
        df.reset_index(inplace = True, drop = True)
        for key in cfg.filter_item_coldict.keys():
            if key in df.columns:
                new_options = [v for v in df[key].unique().tolist() if v not in optionDict[key]]
                optionDict[key] = optionDict[key] + new_options
        
        df["pi_hour"] = pd.to_datetime(df["pi_hour"])
        frames.append(df[(df["pi_hour"] >= start) & (df["pi_hour"] <= end)])
    
    if frames:
        clean_df = pd.concat(frames, ignore_index=True)
    else:
        clean_df = pd.DataFrame(columns=cfg.aoi_density_summary_sql_cols)
    
    filter_cols = [c for c in cfg.aoi_density_summary_sql_cols if c in clean_df.columns]
    #print( clean_df[filter_cols].fillna(""))
    clean_df['noteText'] = ''
    Data = clean_df[filter_cols].fillna("").to_dict(orient="records")
    cfg.front_config['filterOptionDict'] = optionDict
    
    recipe_dict = {'UPI':[], 'PISpot':[], 'SPS':[]}
    for v in optionDict['recipe_id']:
        if len(v)==4  :
            if  v[0]=='2':
                recipe_dict['UPI'].append(v)
                recipe_dict['SPS'].append(v)
            elif  v[0]=='0' :
                recipe_dict['PISpot'].append(v)
        elif len(v)==3:
            recipe_dict['PISpot'].append(v)
            recipe_dict['UPI'].append(v)
            recipe_dict['SPS'].append(v)
            
    print('recipe_dict',recipe_dict)
    for key, val_dict in cfg.front_config['SubTabsFilterDefaultDict'].items():
        if key in recipe_dict.keys():
            cfg.front_config['SubTabsFilterDefaultDict'][key]['recipe_id'] = recipe_dict[key]
    
    return {
        "DictData": Data,
        "ParamDict": cfg.front_config,
        "ProSpecDict": dbhandler.get_table('spec_pro_update__table').to_dict(orient = 'index')
    }


