from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List, Dict, Any, Literal
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
        self.now = datetime.now()
        ym = self.now.strftime("%Y%m")
        print(f"DENSITY連線時間: {self.now}({ym})")
        one_mon_ago = self.now - timedelta(days=30)

        # ================================================= 資料設定  =================================================
        # === PI Line & AOI Tool  ====
        self.uni_aoi_names = [f'aoi{i}00' for i in range(1,4,1)]
        self.uni_pi_names = [f'pi{i}00' for i in range(1,8,1)]

        # === particle type & defect code ====
        self.uni_UPI_defect_codes = ['Polymer', 'SSIU_Polymer']
        self.uni_SPOT_defect_codes = ['PI_Spot_NP', 'PIS With Particle']
        self.uni_SPS_defect_codes = ['SPS']
        self.uni_defect_types = ['Particle', 'PISpot']
        self.all_defect_codes = ['Polymer', 'SSIU_Polymer', 'PI_Spot_NP', 'PIS With Particle', 'SPS']

        # ==== defect size config  ===
        self.uni_defect_sizes = ['S', 'M', 'L', 'O']
        self.rawdata_defect_size_col = 'defect_size'
        self.size_group_keys = ['S','M','L','O','SM','SL','SO','ML','MO','LO','SML','SMO','SLO','MLO','SMLO']
        self.defect_size_rules = {
            "S": lambda x: x <= 20,
            "M": lambda x: 21 <= x <= 100,
            "L": lambda x: 101 <= x <= 400,
            "O": lambda x: x >= 401,
        }

        # === Glass side  ===
        self.glass_sides = ['CF', 'TFT']
         # ================================================= MySQL AOI Density 資料表設定 =================================================
        self.aoi_pidensit_summary_tbn = f'pidenisty_pihour_{ym}'
        self.aoi_pi_density_tbns = [f'{aoi}_pidensity_yyyymm_{pi}' for aoi in self.uni_aoi_names for pi in self.uni_pi_names]
        #print('預設讀取:', self.aoi_pidensit_summary_tbn)

        self.aoi_density_summary_sql_cols = [
            'pi_hour', 'aoi', 'line_id', 'model',
            'glass_type', 'recipe_id', 'ai_code_1', 'pic_paths',
            'maingroup_glass_count', 'maingroup_defect_count',
            'defect_code_glass_count', 'defect_code_count',
            'small_defect_count', 'middle_defect_count', 'large_defect_count', 'over_defect_count',
            'glass', 'comment'
        ]

        self.aoi_density_rawdata_sql_cols = [
            'scan_time', 'line_id', 'model', 'glass_type', 'recipe_id', 'glass_id',
            'pic_name', 'x', 'y', 'predict_code', 'judge_code', 'mark', 'hour','dayhour', 'day', 'year', 'month', 'season', 'week', 'yearmonth',
            'defect_count', 'defect_size', 'open_status', 'ai_code_1', 'ai_code_2',
            'ai_code_3', 'ai_code_4', 'ai_code_5', 'gray_name', 'ip_num',
            'first_code', 'chip_name', 'defect_seq', 'pi_time', 'pi_hour',
            'pic_path', 'recipe_comment'
        ]

        
        self.PRIMARY_GROUP_COLS = ["pi_hour", "line_id", "model", "glass_type", "recipe_id"]

        # ================================================= spec coldict =================================================
        self.default_spec_table_name = 'aoi_density_spec_for_aoimonitor'
        self.fixed_spec_table_name = "aoi_density_fixed_spec_table"

        self.default_spec_table_cols = ['line_id','MODEL_ID', 'MODEL_TYPE', 'DEFECT_CODE', 'PROCESS_TYPE', 'SIZE_TYPE',
       'OOC', 'OOS', 'Editor', 'modify_time', 'drop']
        
        self.fixed_spec_table_cols = ['line_id', 'aoi', 'model', 'recipe_id', 'glass_type', 'ai_code_1',
       'size_key', 'total_glass_count', 'defect_count', 'density', 'overD',
       'removed_glasses', 'removed_defects', 'final_glass_count',
       'final_defect_count', 'final_density', 'std', 'OOC', 'OOS', 'GEN_DT']

        self.default_spec_coldict = {
                                    'PI Line':'line_id',
                                    'MODEL_ID': 'model',
                                    'MODEL_TYPE': 'MODEL_TYPE',
                                    'DEFECT_CODE': 'ai_code_1',
                                    'PROCESS_TYPE': 'PROCESS_TYPE',
                                    'SIZE_TYPE': 'SIZE_TYPE',
                                    'OOC': 'OOC',
                                    'OOS': 'OOS', 
                                    'Editor': 'Editor', 
                                    'modify_time': 'modify_time'}

        # =================================================  UPI/SPOT Default config  =================================================
        self.tab_filter_config = {
            'UPI': {
                'line_id': ['CAPIC200'],#[f'CAPIC{i}00' for i in range(1,8,1)],#
                'ai_code_1': self.uni_UPI_defect_codes,
                'recipe_id':[]
            },
            'PISpot': {
                'line_id': ['CAPIC200'],#[f'CAPIC{i}00' for i in range(1,8,1)],
                'ai_code_1': self.uni_SPOT_defect_codes,
                'recipe_id':[]
            },
            'SPS': {
                'line_id': [f'CAPIC{i}00' for i in range(1,8,1)],
                'ai_code_1': self.uni_SPS_defect_codes,
                'recipe_id':[]
            },
            'fixed_spec_table':{
                'type':'table',
                'tab_name':'動態spec',
                'table_columns': {'line_id': 'PI Line', 
                                  'aoi': 'aoi tools', 
                                  'model': 'Model', 
                                  'recipe_id': 'recipe', 
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
                    'aoi': {'key':'aoi',
                            'values':[]},

                    'model': {'key':'model',
                            'values':[]},

                    'recipe_id': {'key':'recipe_id',
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
                'table_columns':{val: key for key, val in self.default_spec_coldict.items() if val not in  ['NO', 'modify_time']},
                'filter_item_coldict':{
                    'PI Line': {'key':'line_id',
                                'values':[f'CAPIC{i}00' for i in range(1,8,1)]},
                    'Model': {
                        'key': 'model',
                        'values': []
                        },
                    'MODEL_TYPE':{
                        'key':'MODEL_TYPE',
                        'values':['Normal', '高階']
                        },
                    'DEFECT_CODE': {
                        'key':'ai_code_1',
                        'values':['PI_Spot_NP', 'PIS With Particle', 'Polymer', 'SSIU_Polymer']
                        },
                    'SIZE_TYPE': {'key':'SIZE_TYPE',
                            'values':['S','MS','LMS','O','OL','OLM','OLMS']},
                },

            },
            'Trend Chart':{
                'type':'Chart',
                'tab_name':'趨勢分析(月週日)'
            }
            
        }

        # ================================================= 前端網頁CONFIG =================================================
        self.chart_table_coldict = {
            'line_id': 'PI Line',
            'aoi': 'aoi',
            'model': 'Model',
            'glass_type': 'side',
            'pi_hour': 'Hourly',
            'recipe_id': 'recipe',
            'maingroup_glass_count': 'total gld',   # maingroup分群後的玻璃總片數
            'ai_code_1': 'defect',
            'comment':'comment',
            #'maingroup_defect_count': 'total def',  # maingroup分群後的總defect 數
            'glass': 'glass',                        # list ,次分群中對應的glass名稱
            #'defect_code_glass_count': 'gld',  # 主群後再分ai_code_1的玻璃數
            'defect_code_count': 'def count ',        # 主群後再分ai_code_1的defect數
            
            'glass_defect_count': 'size' # dsict, 單片glass defect
        }

        self.table_group_key_dict = {
            'main_group': ['pi_hour', 'line_id', 'aoi', 'model', 'recipe_id', 'glass_type', 'maingroup_glass_count', 'ai_code_1', 'comment'],
                           #'maingroup_glass_count', 'maingroup_defect_count'],
            'uni_col': ['defect_code_glass_count', 'defect_code_count', 'glass_defect_count', 'glass']
            # glass 依照現有邏輯分割後單獨對應 uni_col 中的其他欄位資訊
        }

        self.chart_group_dict = {
            'left': ['line_id','model','maingroup_glass_count', 'defect_code_glass_count'],
            'up':   ['aoi', 'ai_code_1'],
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

        self.defect_group_coldict = {'x': 'x', 'y': 'y', 'chip_name': 'chip', 'pic_name':'img'}

        self.filter_item_coldict = {
            'line_id': 'PI Line',
            'aoi': 'aoi tools',
            'model': 'Model',
            'recipe_id': 'recipe',
            'glass_type': 'glass_side',
            'ai_code_1': 'defect code',
            'defect_size': 'defect size'
        }


        self.front_config = {
            'chartKeyDict': self.chart_group_dict,
            'filtetItemKeyDict': self.filter_item_coldict,
            'hourlyTable': self.chart_table_coldict,
            'hourlyTable_key_group': self.table_group_key_dict,
            'uniGlassInfo': self.uni_glass_row_info_dict,
            'uniGlassDefectTable': self.defect_group_coldict,
            'SubTabsFilterDefaultDict': self.tab_filter_config
        }


    def fetch_latest_spec_summary(self, dbhandler):
        engine = dbhandler.engine
        dbname = dbhandler.db
        table_name = self.fixed_spec_table_name

        sql = f"""
            SELECT t.*
            FROM `{dbname}`.`{table_name}` AS t
            INNER JOIN (
                SELECT
                    line_id, aoi, model, recipe_id, glass_type, ai_code_1, size_key,
                    MAX(GEN_DT) AS max_dt
                FROM `{dbname}`.`{table_name}`
                GROUP BY
                    line_id, aoi, model, recipe_id, glass_type, ai_code_1, size_key
            ) AS g
            ON  t.line_id     = g.line_id
            AND t.aoi         = g.aoi
            AND t.model       = g.model
            AND t.recipe_id   = g.recipe_id
            AND t.glass_type  = g.glass_type
            AND t.ai_code_1   = g.ai_code_1
            AND t.size_key    = g.size_key
            AND t.GEN_DT      = g.max_dt
        """

        with engine.begin() as conn:
            df = pd.read_sql_query(sql, conn)

        return df.fillna('')


    def spec_table_process(self, dbhandler):
        ### default spec table
        key_cols = ['line_id', 'MODEL_ID', 'MODEL_TYPE', 'DEFECT_CODE','SIZE_TYPE']
        default_df = dbhandler.get_table(self.default_spec_table_name)
        default_df = default_df[default_df['drop'] == 'F']
        default_df = default_df.drop_duplicates(subset=key_cols, keep='last')
        default_df = default_df.sort_values(key_cols)
        default_df.reset_index(drop = True, inplace = True)
        #print(default_df.head())
        default_df = default_df.rename(columns=self.default_spec_coldict, inplace=False).fillna('')

        ### fixed spec table
        fixed_df = self.fetch_latest_spec_summary(dbhandler)

        spec_table_dict = {}
        for data, key in zip([default_df, fixed_df], ['default_spec_table', 'fixed_spec_table']):
            rows = data.to_dict(orient='index')
            spec_table_dict[key] = rows
            #print(key, len(data))

        return spec_table_dict

    

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




# ============== 主要 API ==============

@router.get("/api/reset_summary_filter")
async def reset_summary_filter(
    dates: Optional[List[str]] = Query(None, description="['YYYY-MM-DD [HH:MM:SS]', 'YYYY-MM-DD [HH:MM:SS]']"),
    filter_ask_keys: Optional[str] = Query(None, description="JSON 物件字串：{'line_id': [...], 'aoi': [...], 'model': [...], 'glass_type': [...], 'ai_code_1': [...], 'glass_id': [...], 'defect_size': ['S','M','L','O']}")
):
    
    cfg = Config()
    dbhandler = MySQLConnet('l6a01_project')
    spec_table_dict = cfg.spec_table_process(dbhandler)
    #print(cfg.front_config['tabFunc'])
    

    # 解析日期區間
    if dates and len(dates) == 2:
        start = _parse_dt(dates[0])
        end   = _parse_dt(dates[1])
        if end < start:
            start, end = end, start
    else:
        # 預設：近 3 天（含當前小時）
        end = cfg.now.replace(minute=0, second=0, microsecond=0)
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
        tbn = f"pidenisty_pihour_{ym}"
        df = _try_get_table(dbhandler, tbn)
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
        clean_df = pd.DataFrame(columns=cfg.aoi_density_summary_sql_cols)
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
        clean_df['size_mask'] = clean_df.apply(_to_size_mask, axis=1).astype(int)
        clean_df['available_sizes'] = clean_df['size_mask'].apply(_mask_to_sizes)
    else:
        clean_df['size_mask'] = pd.Series([], dtype='int64')
        clean_df['available_sizes'] = pd.Series([], dtype='object')

    # 依當前時間窗內實際出現的 size 更新下拉選單
    if 'available_sizes' in clean_df.columns and not clean_df.empty:
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
    filter_cols = [c for c in cfg.aoi_density_summary_sql_cols if c in clean_df.columns]
    for extra in ['available_sizes', 'size_mask']:
        if extra in clean_df.columns and extra not in filter_cols:
            filter_cols.append(extra)
    clean_df[filter_cols].fillna("", inplace= True)
    #test_df = clean_df[clean_df['model'] == 'G101EAN2G']
    #print(test_df)
    Data =clean_df.to_dict(orient="records")
    cfg.front_config['filterOptionDict'] = optionDict

    # 依 recipe_id 分群填回各分頁預設（保留你原有邏輯）
    recipe_dict = {'UPI':[], 'PISpot':[], 'SPS':[]}
    for v in optionDict.get('recipe_id', []):
        if len(v) == 4:
            if v[0] == '2':
                recipe_dict['UPI'].append(v)
            elif v[0] == '0':
                recipe_dict['PISpot'].append(v)
                recipe_dict['SPS'].append(v)
        elif len(v) == 3:
            recipe_dict['PISpot'].append(v)
            recipe_dict['UPI'].append(v)
            recipe_dict['SPS'].append(v)

    #print('recipe_dict', recipe_dict)
    for key, val_dict in cfg.front_config['SubTabsFilterDefaultDict'].items():
        if key in recipe_dict:
            cfg.front_config['SubTabsFilterDefaultDict'][key]['recipe_id'] = recipe_dict[key]

    #print('data', len(Data))
    return {
        "DictData": Data,
        "ParamDict": cfg.front_config,
        "ProSpecDict": spec_table_dict
    }

