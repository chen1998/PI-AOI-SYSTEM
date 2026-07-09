# %%
import pandas as pd
import logging
import os
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import URL
from typing import List, Any
from sqlalchemy.exc import SQLAlchemyError
import pymysql
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import re
from datetime import datetime, timedelta
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
_VALID_COL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

def _assert_safe_identifier(name: str, what: str = "identifier") -> str:
    if not isinstance(name, str) or not _VALID_COL_RE.match(name):
        raise ValueError(f"Invalid {what}: {name!r}")
    return name


# %%
class  MySQLConnetFunc:
    def __init__(self, dbname):
        self.db = dbname
        host = os.getenv("PI_MYSQL_HOST", "10.97.142.217")
        port_raw = os.getenv("PI_MYSQL_PORT", "")
        username = os.getenv("PI_MYSQL_USER", "l6a01_user")
        password = os.getenv("PI_MYSQL_PASSWORD", "l6a01$user")
        port = int(port_raw) if port_raw else None
        url = URL.create(
            "mysql+pymysql",
            username=username,
            password=password,
            host=host,
            port=port,
            database=dbname,
        )
        self.engine = create_engine(url)

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
    def get_rows(self, table_name: str, match_keys: dict):
        """
        撈出所有符合條件的列，回傳 list[dict]。
        """
        try:
            _assert_safe_identifier(table_name, "table_name")

            if match_keys:
                safe_keys = {}
                parts = []
                for k, v in match_keys.items():
                    _assert_safe_identifier(k, "column")
                    parts.append(f"`{k}` = :{k}")     # ★ 這行最重要：欄位名加反引號
                    safe_keys[k] = v

                where_clause = " AND ".join(parts)
                sql = f"SELECT * FROM `{table_name}` WHERE {where_clause}"
            else:
                sql = f"SELECT * FROM `{table_name}`"
                safe_keys = {}

            with self.engine.connect() as conn:
                result = conn.execute(text(sql), safe_keys)
                rows = result.mappings().all()

            if rows:
                #logging.info(f"[get_rows] 成功取得 '{table_name}' 共 {len(rows)} 筆符合條件資料.")
                return [dict(r) for r in rows]
            else:
                logging.info(f"[get_rows] '{table_name}' 無符合條件資料.")
                return []

        except SQLAlchemyError as e:
            logging.error(f"[get_rows] 查詢 '{table_name}' 發生錯誤: {e}")
            return []
        
    def get_rows_df_in(
            self,
            table_name: str,
            base_keys: dict,
            in_key: str,
            in_values: List[Any]
        ) -> pd.DataFrame:
        """
        一次撈出某欄位值在 in_values 裡的所有列，回傳 DataFrame。

        參數：
            - table_name: 資料表名稱
            - base_keys: 其他 AND 條件，例如 {'RECIPE_NAME': xxx, 'TOOL_ID': yyy}
            - in_key:    要做 IN 的欄位名稱，例如 'SHEET_ID'
            - in_values: 要篩選的值列表，例如 ['YH5ABVX2A', 'YH5ABVX2B', ...]

        回傳：
            - pandas.DataFrame（可能為空 df）
        """
        if not in_values:
            logging.info(f"[get_rows_df_in] in_values 為空，直接回傳空 DataFrame.")
            return pd.DataFrame()

        try:
            where_parts = []
            params = {}

            # 固定條件 (RECIPE_NAME / TOOL_ID ...) → k = :k
            for k, v in (base_keys or {}).items():
                where_parts.append(f"{k} = :{k}")
                params[k] = v

            # IN 條件：in_key IN (:in_0, :in_1, ...)
            placeholders = []
            for idx, val in enumerate(in_values):
                p_name = f"in_{idx}"
                placeholders.append(f":{p_name}")
                params[p_name] = val
            where_parts.append(f"{in_key} IN ({', '.join(placeholders)})")

            where_clause = " AND ".join(where_parts)
            sql = f"SELECT * FROM `{table_name}` WHERE {where_clause}"

            logging.debug(f"[get_rows_df_in] SQL: {sql}  params: {params}")

            with self.engine.connect() as conn:
                result = conn.execute(text(sql), params)
                rows = result.mappings().all()

            if not rows:
                logging.info(f"[get_rows_df_in] '{table_name}' 無符合條件資料.")
                return pd.DataFrame()

            df = pd.DataFrame(rows)
            logging.info(f"[get_rows_df_in] 成功取得 '{table_name}' 共 {len(df)} 筆符合條件資料.")
            return df

        except SQLAlchemyError as e:
            logging.error(f"[get_rows_df_in] 查詢 '{table_name}' 發生錯誤: {e}")
            return pd.DataFrame()
        
    def drop_table(self, table_name):
        try:
            with self.engine.begin() as conn:
                conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
            logging.info(f"[drop_table] 資料表 '{table_name}' 已刪除.")
        except SQLAlchemyError as e:
            logging.error(f"[drop_table] 刪除 '{table_name}' 發生錯誤: {e}")

    #=======================前端 ask ==============================
    # 抓近 N 天
    def get_runs_delta_days(self, tbn, days=30, time_col="scantime"):
        time_col = _assert_safe_identifier(time_col, "time_col")

        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=int(days))

        sql = f"""
        SELECT * FROM `{self.db}`.`{tbn}`
        WHERE `{time_col}` >= :start AND `{time_col}` < :end
        ORDER BY `{time_col}` DESC
        """
        return pd.read_sql(text(sql), self.engine, params={"start": start_dt, "end": end_dt})

    # 抓日期區間（用使用者指定的時間欄位）
    def get_runs_between(self, tbn, start_date, end_date, time_col="scantime"):
        time_col = _assert_safe_identifier(time_col, "time_col")

        sql = f"""
        SELECT * FROM {self.db}.{tbn}
        WHERE {time_col} >= :start AND {time_col} < :end
        ORDER BY {time_col} DESC
        """
        return pd.read_sql(
            text(sql),
            self.engine,
            params={"start": start_date, "end": end_date},
        )
    """
    # 近30天
    df = repo.get_runs_delta_days("apc_run_summary_aawma100", days=30, time_col="scantime")

    # 近7天
    df = repo.get_runs_delta_days("apc_run_summary_aawma100", days=7, time_col="run_day")

    # 指定區間
    df = repo.get_runs_between("apc_run_summary_aawma100",
                            "2026-01-01 00:00:00",
                            "2026-01-08 00:00:00",
                            time_col="scantime")
    
    """
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

    # 2) 更新 key/value：用 key_dict 條件，將符合列更新為 update_dict 的值
    def update_rows(self, table_name: str, key_dict: dict, update_dict: dict) -> int:
        """
        依 key_dict 條件（欄=值 / 欄 IN (...) / IS NULL），批次更新 update_dict 欄位。
        參數：
          - table_name: 資料表名
          - key_dict:   篩選條件，例如 {"glass_id":"A1", "recipe_id":["R1","R2"], "scantime": None}
          - update_dict:要更新的欄位和值，例如 {"noteText":"手動備註", "model":"M123"}
        回傳：受影響列數
        """
        if not update_dict:
            logging.warning("[update_rows] update_dict 為空，無需更新")
            return 0
        if not key_dict:
            raise ValueError("為避免全表更新，key_dict 不可為空")

        # 檢查欄名合法
        for c in list(key_dict.keys()) + list(update_dict.keys()):
            self._validate_ident(c)

        tbl = self._qual_table(table_name)

        # 構建 SET 子句
        set_clauses = []
        params = {}
        for i, (col, val) in enumerate(update_dict.items()):
            p = f"u_{i}"
            set_clauses.append(f"`{col}` = :{p}")
            params[p] = val

        # 構建 WHERE 子句（支援 =, IN, IS NULL）
        where_clauses = []
        for j, (col, val) in enumerate(key_dict.items()):
            if isinstance(val, (list, tuple, set)):
                val_list = list(val)
                if not val_list:  # 空 IN，直接讓條件為 FALSE
                    where_clauses.append("1=0")
                    continue
                placeholders = []
                for k, v in enumerate(val_list):
                    pname = f"w_{j}_{k}"
                    placeholders.append(f":{pname}")
                    params[pname] = v
                where_clauses.append(f"`{col}` IN ({', '.join(placeholders)})")
            elif val is None:
                where_clauses.append(f"`{col}` IS NULL")
            else:
                pname = f"w_{j}"
                where_clauses.append(f"`{col}` = :{pname}")
                params[pname] = val

        sql = f"UPDATE {tbl} SET {', '.join(set_clauses)} WHERE {' AND '.join(where_clauses)}"

        try:
            with self.engine.begin() as conn:
                res = conn.execute(text(sql), params)
                affected = res.rowcount or 0
            logging.info(f"[update_rows] {self.db}.{table_name} 更新完成，影響 {affected} 列。")
            return affected
        except SQLAlchemyError as e:
            logging.error(f"[update_rows] 更新失敗：{e}")
            return 0
    
    def append_single_row_with_nan(
        self,
        table_name: str,
        row_dict: dict,
        *,
        text_na: str = "nan"
    ) -> int:
        """
        新增一筆資料到指定資料表的最後一列。

        - row_dict: 新資料（欄位→值），允許缺欄位
        - 對於 row_dict 中「沒有出現」的欄位：
            * 文字型欄位：補字串 text_na（預設 'nan'）
            * 其他型別欄位：補 None（DB 會存成 NULL）
        回傳：實際新增列數（通常為 1，失敗為 0）
        """
        if not isinstance(row_dict, dict):
            raise TypeError("row_dict 必須是 dict")

        # 先確認表存在
        if not self.table_exists(table_name):
            raise ValueError(f"目標資料表不存在: {self.db}.{table_name}")

        # 取得欄位與型別
        cols_types = self._columns_and_types(table_name)
        if not cols_types:
            raise ValueError(f"無法取得 {self.db}.{table_name} 欄位資訊")

        tbl_qual = self._qual_table(table_name)

        # 資料型別分類：決定缺值要補什麼
        char_types  = {"char", "varchar", "tinytext", "text", "mediumtext", "longtext"}
        # 這裡你也可以依需要擴充 numeric / datetime 型別等

        # 準備完整一列資料：每個欄位都要有一個值
        full_row = {}
        for col, typ in cols_types:
            # 這裡 col 來自 information_schema，已是安全欄名
            if col in row_dict:
                full_row[col] = row_dict[col]
            else:
                # 缺欄位：依型別補值
                if typ.lower() in char_types:
                    full_row[col] = text_na
                else:
                    full_row[col] = None

        # 組 INSERT 語句
        col_names = [c for c, _ in cols_types]
        col_list = ", ".join(f"`{c}`" for c in col_names)
        val_placeholders = ", ".join(f":{c}" for c in col_names)

        sql = text(f"INSERT INTO {tbl_qual} ({col_list}) VALUES ({val_placeholders})")

        try:
            with self.engine.begin() as conn:
                res = conn.execute(sql, full_row)
                affected = res.rowcount or 0
            logging.info(
                f"[append_single_row_with_nan] 向 {self.db}.{table_name} 新增 1 列（實際影響 {affected} 列）。"
            )
            return affected
        except SQLAlchemyError as e:
            logging.error(f"[append_single_row_with_nan] 插入失敗: {e}")
            return 0
    
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
        
   #%%
if __name__ == "__main__":
    #main()
    dbhandler = MySQLConnet('l6a01_project')
    tables = dbhandler.list_tables()
