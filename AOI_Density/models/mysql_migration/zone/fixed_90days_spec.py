
# %%
from datetime import datetime, timedelta
from typing import Iterable, Optional, Set, Dict, List,  Sequence,  Tuple
import pandas as pd
from zoneinfo import ZoneInfo
import numpy as np
import logging
import os
import re
import math

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine, Connection
from sqlalchemy.exc import SQLAlchemyError
import pymysql
from concurrent.futures import ThreadPoolExecutor, as_completed
# -*- coding: utf-8 -*-

import warnings
warnings.filterwarnings('ignore')
#os.chdir('D:\A0_Project\AOI_Density')

# %%
# 設定 logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("db_handler.log"),  # 記錄到檔案
        logging.StreamHandler()                 # 同時輸出到終端
    ]
)


# %%
class MySQLConnet:
    def __init__(self, dbname):
        self.db = dbname
        host = "10.97.142.217"
        username = "l6a01_user"
        password = "l6a01$user"
        self.engine = create_engine(f"mysql+pymysql://{username}:{password}@{host}/{dbname}")

    def list_tables(self):
        try:
            inspector = inspect(self.engine)
            tables = inspector.get_table_names()
            logging.info(f"[list_tables] 成功取得資料表名稱，共 {len(tables)} 張表。")
            return tables
        except SQLAlchemyError as e:
            logging.error(f"[list_tables] 取得資料表名稱時發生錯誤: {e}")
            return []
    
    def get_table(self, table_name):
        try:
            df = pd.read_sql_table(table_name, self.engine)
            #logging.info(f"get_table- 讀取資料表 '{table_name}' 成功 ({len(df)} rows).")
            return df
        except SQLAlchemyError as e:
            logging.error(f"[get_table] 讀取 '{table_name}' 發生錯誤: {e}")
            return pd.DataFrame()
        
   
    # ---------- 給 /api/defect_data 用：明細 ----------
    def get_defects_by_key(self, table: str, key_dict: dict):
        """
        key_dict: {"gid": glass_id, "rid": recipe_id, "t": scantime('YYYY-MM-DD HH:MM:SS')}
        會把 x,y 轉成數值欄位；欄位命名對齊前端（size/img/chip/type）。
        """
        sql = f"""
            SELECT
                CAST(x AS UNSIGNED)       AS x,
                CAST(y AS UNSIGNED)       AS y,
                defect_size               AS size,
                pic_name                  AS img,
                chip_name                 AS chip
            FROM `{table}`
            WHERE glass_id = :gid
              AND recipe_id = :rid
              AND scantime = :t
        """
        try:
            with self.engine.begin() as conn:
                rows = conn.execute(text(sql), key_dict).mappings().all()
                # 轉成 list[dict]，避免 RowMapping 不能 JSON 的問題
                return [dict(r) for r in rows]
        except SQLAlchemyError as e:
            logging.error(f"[get_defects_by_key] {e}")
            return []
    # --- 小工具：檢查 & 引用識別字 ---
    _IDENT_RE = re.compile(r"^[A-Za-z0-9_]+$")

    def _validate_ident(self, name: str) -> str:
        if not isinstance(name, str) or not self._IDENT_RE.match(name):
            raise ValueError(f"非法識別字: {name!r}")
        return name

    def _qual_table(self, table_name: str) -> str:
        self._validate_ident(table_name)
        return f"`{self.db}`.`{table_name}`"

    def table_exists(self, table_name: str) -> bool:
        insp = inspect(self.engine)
        return insp.has_table(table_name, schema=self.db)

    # 1) 儲存資料表：fillna('')、去重、存在覆蓋/不存在建立
    def save_table(self, table_name: str, df: pd.DataFrame, chunksize: int = 10000) -> int:
        """
        將 DataFrame 儲存為 {db}.{table_name}：
          - 先把「文字型欄位」的 NaN -> ''（避免把數值欄轉成字串）
          - 去除重複列
          - if_exists='replace'：存在則覆蓋，不在則新建
        回傳：實際寫入列數
        """
        if df is None:
            raise ValueError("df 不能是 None")
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df 需為 pandas.DataFrame")

        df = df.copy()

        # 僅替換「文字欄位」的 NaN，避免數值欄被轉字串
        obj_cols = df.select_dtypes(include=["object"]).columns
        if len(obj_cols) > 0:
            df[obj_cols] = df[obj_cols].fillna('')

        # 去重複
        before = len(df)
        df.drop_duplicates(inplace=True)
        after = len(df)

        # 寫入（覆蓋）
        # 空表時 to_sql 也能建立 schema（依據 df 的欄型）；若完全空 df 無法推斷型別，請傳入 dtype 參數。
        df.to_sql(
            name=table_name,
            con=self.engine,
            schema=self.db,
            if_exists='replace',
            index=False,
            chunksize=chunksize,
            method='multi'
        )

        logging.info(f"[save_table] {self.db}.{table_name} 已寫入 {after} 列（去除 {before-after} 重複）")
        return after

    def _columns_and_types(self, table_name: str):
        """
        回傳 [(column_name, data_type), ...]
        以明確別名 col/typ 取值，避免大小寫與驅動差異造成的 NoSuchColumnError。
        """
        sql = text("""
            SELECT
                COLUMN_NAME AS col,
                DATA_TYPE   AS typ
            FROM information_schema.columns
            WHERE table_schema = :db AND table_name = :tbl
            ORDER BY ORDINAL_POSITION
        """)
        with self.engine.begin() as conn:
            rp = conn.execute(sql, {"db": self.db, "tbl": table_name})
            try:
                rows = rp.mappings().all()
                return [(r["col"], r["typ"]) for r in rows]
            except Exception:
                # 某些驅動可能不支援 mappings；退回以位置索引取值
                rows = rp.fetchall()
                return [(r[0], r[1]) for r in rows]

    def append_or_create_dedup(
        self,
        table_name: str,
        df: pd.DataFrame,
        dedup_keys: list[str] | None = None,
        *,
        text_na: str = "nan",
        chunksize: int = 10_000
    ) -> int:
        """
        若表不存在 → 直接建立並寫入 df（先去重、文字欄位空值補 'nan'）。
        若表存在 → 將 df 寫入暫存表，再以 NOT EXISTS 去重後插入正式表。
        之後把正式表「文字欄位」中的 NULL 一次性補成 'nan'（避免殘留空值）。
        備註：
          - 去重鍵 `dedup_keys` 未指定時，採用「df 與目標表的共通欄位」作為比對鍵（全欄位完全一致才視為重複）。
          - 數值欄位保留 NULL（不以字串補值，避免型別污染）。
        回傳：實際新增列數（不含跳過的重複列）。
        """
        if df is None or not isinstance(df, pd.DataFrame):
            raise ValueError("df 必須是 pandas.DataFrame")

        df = df.copy().reset_index(drop=True)

        # 文字/字串/分類欄位的空值補 'nan'（數值欄位不處理，避免轉型）
        obj_like = list(df.select_dtypes(include=["object", "string", "category"]).columns)
        if obj_like:
            df[obj_like] = df[obj_like].astype("string").fillna(text_na)

        # 先行去重（減少寫入量）
        before = len(df)
        df.drop_duplicates(inplace=True, ignore_index=True)
        after = len(df)
        dropped_local = before - after

        tbl_qual = self._qual_table(table_name)

        with self.engine.begin() as conn:
            if not self.table_exists(table_name):
                # 表不存在：直接建立
                df.to_sql(
                    name=table_name,
                    con=self.engine,
                    schema=self.db,
                    if_exists="fail",
                    index=False,
                    chunksize=chunksize,
                    method="multi",
                )
                # 將文字欄位的 NULL（若有）統一補 'nan'
                cols_types = self._columns_and_types(table_name)
                char_types = {"char", "varchar", "tinytext", "text", "mediumtext", "longtext"}
                text_cols = [c for c, t in cols_types if t.lower() in char_types]
                for c in text_cols:
                    conn.execute(text(f"UPDATE {tbl_qual} SET `{c}` = :na WHERE `{c}` IS NULL"), {"na": text_na})
                logging.info(
                    f"[append_or_create_dedup] 建立新表 {self.db}.{table_name} 並寫入 {after} 列（df 端先去除 {dropped_local} 重複）。"
                )
                return after

            # 表已存在：寫入暫存表後去重插入
            # 取得目標表欄位與型別
            cols_types = self._columns_and_types(table_name)
            target_cols = [c for c, _ in cols_types]

            # 只保留 df 中存在於目標表的欄位（避免 schema 不一致）
            use_cols = [c for c in df.columns if c in target_cols]
            if not use_cols:
                logging.warning("[append_or_create_dedup] df 欄位與目標表無交集，無法寫入。")
                return 0
            df_use = df[use_cols].copy()

            # 暫存表名稱
            stg_name = f"__stg_{table_name}_{int(datetime.now().timestamp())}"
            stg_qual = self._qual_table(stg_name)

            # 建立暫存表（replace 可確保不存在）
            df_use.to_sql(
                name=stg_name,
                con=self.engine,
                schema=self.db,
                if_exists="replace",
                index=False,
                chunksize=chunksize,
                method="multi",
            )

            # 去重鍵（未指定 → 用所有共通欄位）
            if dedup_keys:
                # 僅保留鍵中存在於目標表的欄位
                keys = [k for k in dedup_keys if k in use_cols]
                if not keys:
                    logging.warning("[append_or_create_dedup] dedup_keys 不在目標表中，改用全欄位去重。")
                    keys = use_cols
            else:
                keys = use_cols

            # 準備 INSERT ... SELECT NOT EXISTS（使用 NULL-safe 相等 `<=>`）
            col_list = ", ".join(f"`{c}`" for c in use_cols)
            sel_list = ", ".join(f"s.`{c}`" for c in use_cols)
            cond = " AND ".join(f"(t.`{k}` <=> s.`{k}`)" for k in keys)

            insert_sql = f"""
                INSERT INTO {tbl_qual} ({col_list})
                SELECT {sel_list}
                FROM {stg_qual} AS s
                WHERE NOT EXISTS (
                    SELECT 1 FROM {tbl_qual} AS t
                    WHERE {cond}
                )
            """
            res = conn.execute(text(insert_sql))
            inserted = res.rowcount or 0

            # 刪除暫存表
            conn.execute(text(f"DROP TABLE IF EXISTS {stg_qual}"))

            # 文字欄位 NULL → 'nan'（僅更新為 NULL 的）
            char_types = {"char", "varchar", "tinytext", "text", "mediumtext", "longtext"}
            text_cols = [c for c, t in cols_types if t.lower() in char_types]
            for c in text_cols:
                conn.execute(text(f"UPDATE {tbl_qual} SET `{c}` = :na WHERE `{c}` IS NULL"), {"na": text_na})

            logging.info(
                f"[append_or_create_dedup] 追加完成：插入 {inserted} 列；df 端先去除 {dropped_local} 重複。"
            )
            return inserted
        
# %%
# ===== Logging =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(funcName)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# %%
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
        self.defect_size_rules = {
            "S": lambda x: x <= 20,
            "M": lambda x: 21 <= x <= 100,
            "L": lambda x: 101 <= x <= 400,
            "O": lambda x: x >= 401,
        }
        self.size_group_keys= ['S','M','L','O','SM','SL','SO','ML','MO','LO','SML','SMO','SLO','MLO','SMLO']

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
        
        # MOD: 將 rawdata 的時間欄位改成 pi_time
        self.aoi_density_rawdata_sql_cols = ['pi_time', 'line_id', 'model', 'glass_type', 'recipe_id', 'glass_id',
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

# %%
def months_in_last_n_days(ref: datetime, days: int = 90) -> List[str]:
    """
    取「近 N 天」內，所有第一天落在此區間內的月份（YYYYMM），用來粗篩表名中的 yyyymm。
    例如 ref=2025-11-04, days=90 -> ['202511','202510','202509']
    """
    threshold = ref - timedelta(days=days)
    cur = datetime(ref.year, ref.month, 1)
    out = []
    while cur >= datetime(threshold.year, threshold.month, 1):
        out.append(f"{cur.year}{cur.month:02d}")
        # 前一個月第一天
        if cur.month == 1:
            cur = datetime(cur.year - 1, 12, 1)
        else:
            cur = datetime(cur.year, cur.month - 1, 1)
    return out

def months_for_window(end_dt_tz: datetime, days: int = 90) -> list[str]:
    """
    取 [end_dt - days, end_dt) 視窗內所涵蓋的 YYYYMM（用月初做遞減）。
    end_dt_tz 必須是 timezone-aware。
    """
    start_dt_tz = end_dt_tz - timedelta(days=days)
    cur = end_dt_tz.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    out = []
    while cur >= start_dt_tz.replace(day=1, hour=0, minute=0, second=0, microsecond=0):
        out.append(f"{cur.year}{cur.month:02d}")
        if cur.month == 1:
            cur = cur.replace(year=cur.year-1, month=12)
        else:
            cur = cur.replace(month=cur.month-1)
    return out

def compute_cutoff_730_local(ref_datetime: datetime | None = None,
                             tz: str = "Asia/Taipei",
                             hh: int = 7, mm: int = 30) -> datetime:
    """
    回傳「當天 hh:mm:00」的 timezone-aware datetime（預設 07:30, Asia/Taipei）。
    若 ref_datetime 為 None，取現在時間；若 ref 是 naive，視為 tz 當地時間。
    """
    tzinfo = ZoneInfo(tz)
    if ref_datetime is None:
        now = datetime.now(tzinfo)
    else:
        now = ref_datetime
        if now.tzinfo is None:
            now = now.replace(tzinfo=tzinfo)
        else:
            now = now.astimezone(tzinfo)
    return now.replace(hour=hh, minute=mm, second=0, microsecond=0)

# ===== 表名 Regex =====
_PID_TBL_RE = re.compile(r'^(aoi[0-9]{3})_pidensity_([0-9]{6})_pi([0-9]{3})$')


# ===== 列表符合命名規則的 pidensity 資料表 =====
def list_pidensity_tables(conn: Connection, dbname: str, yyyymm_whitelist: Set[str],
                          aoi_filter: Optional[Iterable[str]] = None,
                          pi_filter: Optional[Iterable[str]] = None) -> List[str]:
    """
    從 information_schema.table 列出符合命名規則的表，再以 yyyymm / aoi / pi 篩選。
    """
    sql = text("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = :db
          AND table_name REGEXP '^aoi[0-9]{3}_pidensity_[0-9]{6}_pi[0-9]{3}$'
    """)
    names = conn.execute(sql, {"db": dbname}).scalars().all()

    aoi_set = set(aoi_filter) if aoi_filter else None
    pi_set  = set(pi_filter) if pi_filter else None

    picked = []
    for t in names:
        m = _PID_TBL_RE.match(t)
        if not m:
            continue
        aoi_str, yyyymm, pi3 = m.groups()
        if yyyymm not in yyyymm_whitelist:
            continue
        if aoi_set and aoi_str not in aoi_set:
            continue
        if pi_set and pi3 not in pi_set:
            continue
        picked.append(t)
    logging.info(f"候選表數量：{len(picked)} / 原始 {len(names)}（已按月份與可選 aoi/pi 粗篩）")
    return sorted(picked)


# ===== 查詢表欄位（做容錯） =====
def get_table_columns(conn: Connection, dbname: str, table_name: str) -> Set[str]:
    sql = text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = :db AND table_name = :tbl
    """)
    return set(conn.execute(sql, {"db": dbname, "tbl": table_name}).scalars().all())


# ===== 從單表抓資料（SQL 端先過濾 pi_time + recipe_id） =====
def fetch_one_table(conn, dbname: str, table_name: str,
                    start_dt: datetime, end_dt: datetime,
                    need_cols: list[str]) -> pd.DataFrame:
    try:
        avail = get_table_columns(conn, dbname, table_name)
    except Exception as e:
        logging.warning(f"[{table_name}] 無法讀取欄位，略過。err={e}")
        return pd.DataFrame(columns=need_cols)

    # MOD: 時間欄位改成 pi_time
    if 'pi_time' not in avail:
        logging.info(f"[{table_name}] 無 pi_time 欄位，略過。")
        return pd.DataFrame(columns=need_cols)

    select_cols = [c for c in need_cols if c in avail and c not in ('aoi', 'size_bucket')]
    if not select_cols:
        logging.info(f"[{table_name}] 無可選欄位，略過。")
        return pd.DataFrame(columns=need_cols)

    # 注意：右界使用 < end_dt（嚴格早於 cutoff）。若你想含 cutoff，改成 <= :end_dt
    sql = text(f"""
        SELECT {', '.join([f'`{c}`' for c in select_cols])}
        FROM `{table_name}`
        WHERE `pi_time` >= :start_dt
          AND `pi_time` <  :end_dt
          AND (
            SUBSTRING(CAST(`recipe_id` AS CHAR), 1, 1) IN ('2','0')
            OR CHAR_LENGTH(CAST(`recipe_id` AS CHAR)) = 3
          )
    """)

    try:
        df = pd.read_sql_query(sql, conn, params={"start_dt": start_dt, "end_dt": end_dt})
    except Exception as e:
        logging.warning(f"[{table_name}] 查詢失敗，略過。err={e}")
        return pd.DataFrame(columns=need_cols)

    m = _PID_TBL_RE.match(table_name)
    df['aoi'] = (m.group(1) if m else None)

    for c in need_cols:
        if c not in df.columns:
            df[c] = pd.NA

    # MOD: 將 pi_time 轉成 datetime，並排除 NaT / None
    try:
        df['pi_time'] = pd.to_datetime(df['pi_time'], errors='coerce', utc=False)
        df = df[df['pi_time'].notna()].copy()
    except Exception:
        pass

    if 'defect_size' in df.columns:
        df['defect_size'] = pd.to_numeric(df['defect_size'], errors='coerce')
        bins = [-float('inf'), 20, 100, 400, float('inf')]
        labels = ['S', 'M', 'L', 'O']
        df['size_bucket'] = pd.cut(df['defect_size'], bins=bins, labels=labels, right=True)
    else:
        df['size_bucket'] = pd.NA

    return df[need_cols]

def keep_latest_measurement_group(
    df: pd.DataFrame,
    time_col: str = 'pi_time',   # MOD: default 改為 pi_time
    key_cols = ['line_id', 'aoi', 'model', 'recipe_id', 'glass_type', 'glass_id'],
    print_limit: int = 500
):
    """
    依 key_cols 分群，若同群內有多個 time_col（預設 pi_time），僅保留最新 time_col 的整批資料。
    會印出被刪除的 (群 + time_col + 刪除筆數)；回傳 (filtered_df, removed_df)。
    """
    tb = df.copy()
    
    # 1) 時間欄位轉成 datetime（容錯）
    if time_col not in tb.columns:
        raise KeyError(f"缺少時間欄位: {time_col}")
    tb[time_col] = pd.to_datetime(tb[time_col], errors='coerce')

    # 2) 驗證 key 欄
    missing = [c for c in key_cols if c not in tb.columns]
    if missing:
        raise KeyError(f"缺少必要分群欄位: {missing}")

    # 3) 每群的最新時間（transform 回填到每列）
    grp_max = tb.groupby(key_cols, dropna=False)[time_col].transform('max')

    # 4) 標記要保留的列：時間=該群最大時間；若該群的最大時間為 NaT（全 NaT），則保留整群
    keep_mask = (tb[time_col] == grp_max) | grp_max.isna()

    kept = tb[keep_mask].copy()
    removed = tb[~keep_mask].copy()

    # 5) 印出被刪除的群與 time_col
    if not removed.empty:
        summary = (
            removed.groupby(key_cols + [time_col], dropna=False)
                   .size().reset_index(name='rows_removed')
                   .sort_values(key_cols + [time_col])
        )
        # 僅印前 print_limit 筆，避免洗版
        for _, row in summary.head(print_limit).iterrows():
            grp_info = ", ".join(f"{k}={row[k]}" for k in key_cols)
            print(f"[REMOVED] {grp_info} | {time_col}={row[time_col]} | rows={row['rows_removed']}")
        if len(summary) > print_limit:
            print(f"... and {len(summary) - print_limit} more removed groups.")
    else:
        print("沒有發現同群多次量測（無需刪除）。")
    kept.reset_index(drop=True, inplace = True)
    removed.reset_index(drop=True, inplace = True)

    print(f'確認前筆數:{len(df)}')
    print(f'確認後筆數:{len(kept)}')
    print(f'刪除筆數:{len(removed)}')
    return kept, removed

# ===== 主流程：抓多表合併 =====
def fetch_pidensity_recent(mysql: MySQLConnet,
                           days: int = 90,
                           ref_datetime: datetime | None = None,
                           aoi_filter: Iterable[str] | None = None,
                           pi_filter: Iterable[str] | None = None,
                           *,
                           tz: str = "Asia/Taipei",
                           cutoff_hh: int = 7, cutoff_mm: int = 30) -> pd.DataFrame:
    """
    以「當天 {cutoff_hh}:{cutoff_mm}（{tz}）」為截止點，回傳近 days 天資料（pi_time ∈ [start, end)）。
    """
    engine = mysql.engine
    dbname = mysql.db

    # 1) 計算截止點（含時區），與起始點；轉成「naive 本地時間」給 MySQL
    end_dt_tz = compute_cutoff_730_local(ref_datetime, tz=tz, hh=cutoff_hh, mm=cutoff_mm)
    start_dt_tz = end_dt_tz - timedelta(days=days)
    end_dt = end_dt_tz.replace(tzinfo=None)
    start_dt = start_dt_tz.replace(tzinfo=None)

    # 2) 以視窗涵蓋月份粗篩表名
    months = set(months_for_window(end_dt_tz, days=days))  # e.g., {'202507','202506','202505'}

    # MOD: final_cols 用 pi_time 取代 scan_time
    final_cols = ['pi_time', 'line_id', 'aoi', 'model', 'recipe_id',
                  'glass_type', 'glass_id', 'ai_code_1', 'defect_size', 'size_bucket']

    frames: list[pd.DataFrame] = []
    with engine.connect() as conn:
        tables = list_pidensity_tables(conn, dbname, months,
                                       aoi_filter=aoi_filter, pi_filter=pi_filter)
        logging.info(f"開始查詢 {len(tables)} 張表 ... "
                     f"起始：{start_dt:%Y-%m-%d %H:%M:%S}, 截止（不含）：{end_dt:%Y-%m-%d %H:%M:%S}")

        for tbl in tables:
            df = fetch_one_table(conn, dbname, tbl, start_dt, end_dt, final_cols)
            if not df.empty:
                frames.append(df)

    if not frames:
        logging.info("沒有符合條件的資料。")
        return pd.DataFrame(columns=final_cols)

    out = pd.concat(frames, ignore_index=True)
    # MOD: 用 pi_time 排序
    if 'pi_time' in out.columns:
        out = out.sort_values('pi_time', ascending=False, kind='mergesort')
    return out.reset_index(drop=True)


# %%

# ===== 設定 =====
MAIN_KEYS     = ['line_id', 'aoi', 'model', 'recipe_id']
GLASS_ID_KEYS = ['pi_time', 'glass_id']   # MOD: 改為 pi_time
SIZE_ATOMS    = ['S','M','L','O']

def _size_combo_map(size_key_names: Sequence[str]) -> Dict[str, Tuple[str, ...]]:
    out = {}
    for k in size_key_names:
        out[k] = tuple([ch for ch in k if ch in SIZE_ATOMS])
    return out

def _cast_to_category(df: pd.DataFrame, cols: Sequence[str]):
    for c in cols:
        if c in df.columns and df[c].dtype == object:
            df[c] = df[c].astype('category')

def compute_dynamic_spec_summary_streaming(
    df: pd.DataFrame,
    glass_sides: Sequence[str] = Config().glass_sides,       # MOD: 預設改用 CF/TFT
    all_defect_codes: Sequence[str] = Config().all_defect_codes,
    size_key_names: Sequence[str] = Config().size_group_keys,
    verbose: bool = False,
) -> pd.DataFrame:
    """
    低記憶體串流版：
      - 分母：全部片（到 glass_type 以前不看 code）；ALL=CF∪TFT 去重
      - 分子：僅重點 codes；逐群處理，不做全表 pivot
      - 標準差：用 Σx、Σx² 與 n 計算，隱含 0（沒缺陷的片）
    """
    need = set(MAIN_KEYS + ['glass_type','ai_code_1','size_bucket'] + GLASS_ID_KEYS)
    miss = need - set(df.columns)
    if miss:
        raise KeyError(f"缺少必要欄位: {sorted(miss)}")

    tb = df[MAIN_KEYS + ['glass_type','ai_code_1','size_bucket'] + GLASS_ID_KEYS].copy()
    # MOD: 使用 pi_time
    tb['pi_time'] = pd.to_datetime(tb['pi_time'], errors='coerce')

    # 節省記憶體：高重複欄位轉 category
    _cast_to_category(tb, MAIN_KEYS + ['glass_type','ai_code_1','size_bucket'])

    # ===== 1) 分母：全部片（ALL=CF∪TFT 去重） =====
    side_whitelist = set(list(glass_sides) + ['all'])

    # CF/TFT 各自分母
    raw_glasses = tb[MAIN_KEYS + ['glass_type'] + GLASS_ID_KEYS].drop_duplicates()
    raw_tot = (raw_glasses
               .groupby(MAIN_KEYS + ['glass_type'], dropna=False, observed=True)
               .size())
    # ALL 分母（忽略 glass_type 後去重）
    all_glasses = tb[MAIN_KEYS + GLASS_ID_KEYS].drop_duplicates()
    all_tot = (all_glasses
               .groupby(MAIN_KEYS, dropna=False, observed=True)
               .size())

    # 建 tot_map 查表
    tot_map: Dict[Tuple, int] = {}
    for idx, v in raw_tot.items():
        *main, gtype = idx
        if gtype in side_whitelist:
            tot_map[tuple(main)+(''+gtype,)] = int(v)
    for idx, v in all_tot.items():
        tot_map[tuple(idx)+('all',)] = int(v)

    # ===== 2) 分子：僅重點 codes；逐群處理 =====
    combo_map = _size_combo_map(size_key_names)
    out_rows: List[dict] = []

    # 只留下重點 code 進行分子計算（不影響分母）
    tf = tb[tb['ai_code_1'].isin(all_defect_codes)].copy()
    _cast_to_category(tf, MAIN_KEYS + ['glass_type','ai_code_1','size_bucket'])

    # 先排序，讓 groupby 產生小塊迭代，減少記憶體峰值
    tf.sort_values(by=MAIN_KEYS + ['glass_type','ai_code_1','glass_id','pi_time'],
                   kind='mergesort', inplace=True)

    # === 2a) 製程分群（CF/TFT）：逐 (主群 + glass_type + code) 迭代
    for (line_id, aoi, model, recipe_id, glass_type, ai_code), g in \
        tf.groupby(MAIN_KEYS + ['glass_type','ai_code_1'], sort=False, observed=True):

        if glass_type not in side_whitelist or glass_type == 'all':
            continue  # 'all' 在 2b 處理

        tg = int(tot_map.get((line_id, aoi, model, recipe_id, glass_type), 0) or 0)
        if tg == 0:
            # 沒分母：直接輸出 NaN 一列 per size_key
            for size_key in size_key_names:
                out_rows.append({
                    'line_id': line_id, 'aoi': aoi, 'model': model, 'recipe_id': recipe_id,
                    'glass_type': glass_type, 'ai_code_1': ai_code, 'size_key': size_key,
                    'total_glass_count': 0, 'defect_count': 0.0, 'density': np.nan, 'overD': np.nan,
                    'removed_glasses': 0, 'removed_defects': 0.0,
                    'final_glass_count': np.nan, 'final_defect_count': 0.0, 'final_density': np.nan,
                    'std': np.nan, 'OOC': np.nan, 'OOS': np.nan
                })
            continue

        # 每片×尺寸原子計數（只用到 S/M/L/O）
        # 注意：這裡只在「這個小群」上 groupby，記憶體很省
        per_glass = (g[g['size_bucket'].isin(SIZE_ATOMS)]
                       .groupby(GLASS_ID_KEYS + ['size_bucket'], sort=False, observed=True)
                       .size()
                       .unstack('size_bucket', fill_value=0))
        if per_glass.empty:
            # 這個 (group, code) 完全沒有缺陷，分子=0，但標準差需要 n
            for size_key in size_key_names:
                final_tg = tg
                final_density = 0.0 if final_tg > 0 else np.nan
                std = np.nan if final_tg <= 1 else 0.0  # 全 0，變異 0
                OOC = (final_density + 3*std) if np.isfinite(final_density) and np.isfinite(std) else np.nan
                OOS = (final_density + 6*std) if np.isfinite(final_density) and np.isfinite(std) else np.nan
                out_rows.append({
                    'line_id': line_id, 'aoi': aoi, 'model': model, 'recipe_id': recipe_id,
                    'glass_type': glass_type, 'ai_code_1': ai_code, 'size_key': size_key,
                    'total_glass_count': tg, 'defect_count': 0.0, 'density': 0.0, 'overD': 0.0,
                    'removed_glasses': 0, 'removed_defects': 0.0,
                    'final_glass_count': final_tg, 'final_defect_count': 0.0, 'final_density': final_density,
                    'std': std, 'OOC': OOC, 'OOS': OOS
                })
            continue

        # 確保四個原子欄位存在
        for c in SIZE_ATOMS:
            if c not in per_glass.columns:
                per_glass[c] = 0
        # 逐尺寸組合
        for size_key, atoms in combo_map.items():
            x = per_glass[list(atoms)].sum(axis=1) if len(atoms) else pd.Series(0, index=per_glass.index)

            defect_count = float(x.sum())
            density = defect_count / tg if tg > 0 else np.nan
            overD = density * 3 if np.isfinite(density) else np.nan

            # outlier：只在有缺陷的片上判斷；0 不會被剔除
            removed_mask = (x > overD) if np.isfinite(overD) else pd.Series(False, index=x.index)
            removed_glasses = int(removed_mask.sum())
            removed_defects = float(x[removed_mask].sum())
            final_tg = tg - removed_glasses

            # 保留的片（仍然只包含「有缺陷的片」）
            xk = x[~removed_mask]
            sum_x = float(xk.sum())
            sum_x2 = float((xk**2).sum())
            final_defect_count = sum_x
            final_density = sum_x / final_tg if final_tg > 0 else np.nan

            if final_tg <= 1 or not np.isfinite(final_density):
                std = np.nan
            else:
                # 變異數：包含 0（沒缺陷）的片，透過 n 與 mean 隱含
                var = (sum_x2 - final_tg*(final_density**2)) / (final_tg - 1)
                std = np.sqrt(var) if np.isfinite(var) and var >= 0 else np.nan

            OOC = final_density + 3*std if np.isfinite(final_density) and np.isfinite(std) else np.nan
            OOS = final_density + 6*std if np.isfinite(final_density) and np.isfinite(std) else np.nan

            if verbose and removed_glasses > 0:
                head = x[removed_mask].head(5)
                print(f"[OUTLIER REMOVED][CF/TFT] line_id={line_id}, aoi={aoi}, model={model}, recipe_id={recipe_id}, "
                      f"glass_type={glass_type}, ai_code_1={ai_code}, size_key={size_key}, "
                      f"removed_glasses={removed_glasses}, removed_defects={removed_defects:.0f}, overD={overD:.6f}")
                if len(head) < removed_glasses:
                    print(f"... and {removed_glasses - len(head)} more")

            out_rows.append({
                'line_id': line_id, 'aoi': aoi, 'model': model, 'recipe_id': recipe_id,
                'glass_type': glass_type, 'ai_code_1': ai_code, 'size_key': size_key,
                'total_glass_count': tg, 'defect_count': defect_count, 'density': density, 'overD': overD,
                'removed_glasses': removed_glasses, 'removed_defects': removed_defects,
                'final_glass_count': final_tg, 'final_defect_count': final_defect_count, 'final_density': final_density,
                'std': std, 'OOC': OOC, 'OOS': OOS
            })

    # === 2b) ALL 不分製程：逐 (主群 + code) 迭代
    tf_all = tf.copy()
    tf_all = tf_all.drop(columns=['glass_type'])  # 忽略製程
    tf_all.sort_values(by=MAIN_KEYS + ['ai_code_1','glass_id','pi_time'],
                       kind='mergesort', inplace=True)

    for (line_id, aoi, model, recipe_id, ai_code), g in \
        tf_all.groupby(MAIN_KEYS + ['ai_code_1'], sort=False, observed=True):

        tg = int(tot_map.get((line_id, aoi, model, recipe_id, 'all'), 0) or 0)
        if tg == 0:
            for size_key in size_key_names:
                out_rows.append({
                    'line_id': line_id, 'aoi': aoi, 'model': model, 'recipe_id': recipe_id,
                    'glass_type': 'all', 'ai_code_1': ai_code, 'size_key': size_key,
                    'total_glass_count': 0, 'defect_count': 0.0, 'density': np.nan, 'overD': np.nan,
                    'removed_glasses': 0, 'removed_defects': 0.0,
                    'final_glass_count': np.nan, 'final_defect_count': 0.0, 'final_density': np.nan,
                    'std': np.nan, 'OOC': np.nan, 'OOS': np.nan
                })
            continue

        per_glass = (g[g['size_bucket'].isin(SIZE_ATOMS)]
                       .groupby(GLASS_ID_KEYS + ['size_bucket'], sort=False, observed=True)
                       .size()
                       .unstack('size_bucket', fill_value=0))
        if per_glass.empty:
            for size_key in size_key_names:
                final_tg = tg
                final_density = 0.0 if final_tg > 0 else np.nan
                std = np.nan if final_tg <= 1 else 0.0
                OOC = (final_density + 3*std) if np.isfinite(final_density) and np.isfinite(std) else np.nan
                OOS = (final_density + 6*std) if np.isfinite(final_density) and np.isfinite(std) else np.nan
                out_rows.append({
                    'line_id': line_id, 'aoi': aoi, 'model': model, 'recipe_id': recipe_id,
                    'glass_type': 'all', 'ai_code_1': ai_code, 'size_key': size_key,
                    'total_glass_count': tg, 'defect_count': 0.0, 'density': 0.0, 'overD': 0.0,
                    'removed_glasses': 0, 'removed_defects': 0.0,
                    'final_glass_count': final_tg, 'final_defect_count': 0.0, 'final_density': final_density,
                    'std': std, 'OOC': OOC, 'OOS': OOS
                })
            continue

        for c in SIZE_ATOMS:
            if c not in per_glass.columns:
                per_glass[c] = 0

        for size_key, atoms in combo_map.items():
            x = per_glass[list(atoms)].sum(axis=1) if len(atoms) else pd.Series(0, index=per_glass.index)

            defect_count = float(x.sum())
            density = defect_count / tg if tg > 0 else np.nan
            overD = density * 3 if np.isfinite(density) else np.nan

            removed_mask = (x > overD) if np.isfinite(overD) else pd.Series(False, index=x.index)
            removed_glasses = int(removed_mask.sum())
            removed_defects = float(x[removed_mask].sum())
            final_tg = tg - removed_glasses

            xk = x[~removed_mask]
            sum_x = float(xk.sum())
            sum_x2 = float((xk**2).sum())

            final_defect_count = sum_x
            final_density = sum_x / final_tg if final_tg > 0 else np.nan

            if final_tg <= 1 or not np.isfinite(final_density):
                std = np.nan
            else:
                var = (sum_x2 - final_tg*(final_density**2)) / (final_tg - 1)
                std = np.sqrt(var) if np.isfinite(var) and var >= 0 else np.nan

            OOC = final_density + 3*std if np.isfinite(final_density) and np.isfinite(std) else np.nan
            OOS = final_density + 6*std if np.isfinite(final_density) and np.isfinite(std) else np.nan

            if verbose and removed_glasses > 0:
                head = x[removed_mask].head(5)
                print(f"[OUTLIER REMOVED][ALL] line_id={line_id}, aoi={aoi}, model={model}, recipe_id={recipe_id}, "
                      f"ai_code_1={ai_code}, size_key={size_key}, "
                      f"removed_glasses={removed_glasses}, removed_defects={removed_defects:.0f}, overD={overD:.6f}")
                if len(head) < removed_glasses:
                    print(f"... and {removed_glasses - len(head)} more")
            row_dict = {
                'line_id': line_id, 'aoi': aoi, 'model': model, 'recipe_id': recipe_id,
                'glass_type': 'all', 'ai_code_1': ai_code, 'size_key': size_key,
                'total_glass_count': tg, 'defect_count': defect_count, 'density': density, 'overD': overD,
                'removed_glasses': removed_glasses, 'removed_defects': removed_defects,
                'final_glass_count': final_tg, 'final_defect_count': final_defect_count, 'final_density': final_density,
                'std': std, 'OOC': OOC, 'OOS': OOS
            }
            out_rows.append(row_dict)

    # ===== 3) 組裝輸出 =====
    cols = (MAIN_KEYS + ['glass_type','ai_code_1','size_key',
                         'total_glass_count','defect_count','density','overD',
                         'removed_glasses','removed_defects',
                         'final_glass_count','final_defect_count','final_density',
                         'std','OOC','OOS'])
    out = pd.DataFrame(out_rows, columns=cols) if out_rows else pd.DataFrame(columns=cols)

    # 排序輸出（依 size_key 順序）
    size_order = {k:i for i,k in enumerate(size_key_names)}
    out['__ord__'] = out['size_key'].map(size_order).fillna(9999).astype(int)
    out = out.sort_values(MAIN_KEYS + ['glass_type','ai_code_1','__ord__']).drop(columns='__ord__')
    out['GEN_DT'] = datetime.today().strftime('%y%m%d%H%M%S')
    return out.reset_index(drop=True)



# %%
if __name__ == "__main__":
    dbhandler = MySQLConnet("l6a01_project")
    cfg = Config()
    # 例：抓全部 AOI、全部 PI，預設 90 天（以現在時間為基準）
    df = fetch_pidensity_recent(dbhandler, days=90)
    print(f'資料庫撈取完成,筆數:{len(df)}')
    print(df.head(2))
    kept, removed = keep_latest_measurement_group(df)  # 預設 time_col 已改為 'pi_time'
    result = compute_dynamic_spec_summary_streaming(kept)
    if not result.empty:
        dbhandler.append_or_create_dedup('aoi_density_fixed_spec_table', result)
