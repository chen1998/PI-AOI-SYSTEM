# %%
import pandas as pd
import numpy as np
import logging
from sqlalchemy import create_engine, text, inspect
from typing import List, Any, Optional
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
        in_values: List[Any],
        empty_cols: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        一次撈出某欄位值在 in_values 裡的所有列，回傳 DataFrame。

        支援：
            1. base_keys 一般等值條件：
            {'RECIPE_NAME': xxx, 'TOOL_ID': yyy}

            2. base_keys 欄位值為 None：
            {'defect_size': None}
            會轉成 defect_size IS NULL

            3. empty_cols：
            empty_cols=['defect_size']
            會轉成：
            defect_size IS NULL
            OR TRIM(defect_size) = ''
            OR LOWER(TRIM(defect_size)) IN ('nan', 'none', '<na>', 'nat', 'null')

        參數：
            - table_name: 資料表名稱
            - base_keys: 其他 AND 條件
            - in_key:    要做 IN 的欄位名稱
            - in_values: 要篩選的值列表
            - empty_cols: 要判斷為空值的欄位列表

        回傳：
            - pandas.DataFrame
        """
        if not in_values:
            logging.info("[get_rows_df_in] in_values 為空，直接回傳空 DataFrame.")
            return pd.DataFrame()

        try:
            where_parts = []
            params = {}

            # 固定條件
            for k, v in (base_keys or {}).items():
                if v is None:
                    where_parts.append(f"`{k}` IS NULL")
                else:
                    where_parts.append(f"`{k}` = :{k}")
                    params[k] = v

            # 空值條件：NULL / 空字串 / 常見文字空值
            for col in (empty_cols or []):
                where_parts.append(
                    f"""(
                        `{col}` IS NULL
                        OR TRIM(`{col}`) = ''
                        OR LOWER(TRIM(`{col}`)) IN ('nan', 'none', '<na>', 'nat', 'null')
                    )"""
                )

            # IN 條件
            placeholders = []
            for idx, val in enumerate(in_values):
                p_name = f"in_{idx}"
                placeholders.append(f":{p_name}")
                params[p_name] = val

            where_parts.append(f"`{in_key}` IN ({', '.join(placeholders)})")

            where_clause = " AND ".join(where_parts)

            sql = f"""
            SELECT *
            FROM `{table_name}`
            WHERE {where_clause}
            """

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
    def query_df(self, sql: str, params: dict | None = None) -> pd.DataFrame:
        """
        直接執行自訂 SQL，回傳 DataFrame。
        適合新版 router / ETL 使用。
        """
        try:
            with self.engine.connect() as conn:
                return pd.read_sql(text(sql), conn, params=params or {})
        except SQLAlchemyError as e:
            logging.error(f"[query_df] 查詢發生錯誤: {e}")
            return pd.DataFrame()

    def query_rows(self, sql: str, params: dict | None = None) -> list[dict]:
        """
        直接執行自訂 SQL，回傳 list[dict]。
        適合 API 直接 JSON 回傳。
        """
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(text(sql), params or {}).mappings().all()
            return [dict(r) for r in rows]
        except SQLAlchemyError as e:
            logging.error(f"[query_rows] 查詢發生錯誤: {e}")
            return []

    def get_table_between(self, table_name: str, start_date, end_date, time_col="test_time") -> pd.DataFrame:
        """
        安全版單表時間區間查詢。
        """
        table_name = self._validate_ident(table_name)
        time_col = _assert_safe_identifier(time_col, "time_col")

        sql = f"""
        SELECT * FROM `{self.db}`.`{table_name}`
        WHERE `{time_col}` >= :start AND `{time_col}` < :end
        ORDER BY `{time_col}` DESC
        """
        return self.query_df(sql, {"start": start_date, "end": end_date})

    def get_cim_defects_by_key(self, table: str, key_dict: dict, cols: list[str] | None = None):
        """
        給新版 ol_defect_map 用：查 cim_defect_yyyymm_aoi_capic raw defect 明細

        key_dict:
            {
            "gid": sheet_id_chip_id,
            "t":   test_time('YYYY-MM-DD HH:MM:SS')
            }

        cols:
            可指定要撈的原始欄位名稱清單，例如：
            [
                'sheet_id_chip_id', 'chip_id', 'test_time', 'defect_size',
                'pox_x1', 'pox_y1', 'img_file_url_path', 'adc_def_code'
            ]

        回傳：
            list[dict]
            其中 pox_x1 / pox_y1 會自動轉成 x / y（unsigned）
        """
        table = self._validate_ident(table)
        """
        allowed_cols = {
            "sheet_id_chip_id",
            "chip_id",
            "test_time",
            "defect_size",
            "pox_x1",
            "pox_y1",
            "img_file_url_path",
            "adc_def_code",
            "retype_def_code",
            "image_file_path",
            "image_file_name",
            "pi_time",
            "pi_hour",
        }
        

        default_cols = [
            "sheet_id_chip_id",
            "chip_id",
            "test_time",
            "defect_size",
            "pox_x1",
            "pox_y1",
            "img_file_url_path",
            "adc_def_code",
        ]
        """

        use_cols = cols #or default_cols

        # 驗證欄位安全性與白名單
        safe_cols = []
        for c in use_cols:
            c = self._validate_ident(c)
            #if c not in allowed_cols:
            #    raise ValueError(f"欄位不允許查詢: {c}")
            safe_cols.append(c)

        # 組 SELECT 子句
        select_parts = []
        for c in safe_cols:
            if c == "pox_x1":
                select_parts.append("CAST(pox_x1 AS UNSIGNED) AS x")
            elif c == "pox_y1":
                select_parts.append("CAST(pox_y1 AS UNSIGNED) AS y")
            else:
                select_parts.append(f"`{c}`")

        select_sql = ",\n                ".join(select_parts)

        sql = f"""
            SELECT
                    {select_sql}
            FROM `{self.db}`.`{table}`
            WHERE sheet_id_chip_id = :gid
            AND test_time = :t
            ORDER BY chip_id, pox_x1, pox_y1
        """

        try:
            with self.engine.begin() as conn:
                rows = conn.execute(text(sql), key_dict).mappings().all()
                return [dict(r) for r in rows]
        except SQLAlchemyError as e:
            logging.error(f"[get_cim_defects_by_key] {e}")
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
        chunksize: int = 10_000,
    ) -> int:
        """
        安全版 append_or_create_dedup

        重點：
        1. 不再對所有 object 欄位補 'nan'。
        2. 依目標表欄位型態清理 DataFrame。
        3. staging table 建好後，再用 SQL 把非文字欄位中的 '', 'nan', 'None', 'NULL', 'NaT' 強制改 NULL。
        4. 最後才 INSERT INTO target SELECT FROM staging。
        """
        if df is None or not isinstance(df, pd.DataFrame):
            raise ValueError("df 必須是 pandas.DataFrame")

        if df.empty:
            logging.info("[append_or_create_dedup] df empty，略過。")
            return 0

        import numpy as np
        import pandas as pd
        from datetime import datetime
        from sqlalchemy import text

        bad_strings = {"", "nan", "none", "null", "<na>", "nat", "inf", "-inf"}

        def _base_mysql_type(type_text: str) -> str:
            return str(type_text or "").lower().split("(")[0].strip()

        def _is_bad(v):
            if v is None:
                return True
            if isinstance(v, str):
                return v.strip().lower() in bad_strings
            try:
                if pd.isna(v):
                    return True
            except Exception:
                pass
            return False

        def _to_text(v):
            if _is_bad(v):
                return text_na
            return str(v).strip()

        def _to_datetime(v):
            if _is_bad(v):
                return None
            dt = pd.to_datetime(v, errors="coerce")
            if pd.isna(dt):
                return None
            if hasattr(dt, "to_pydatetime"):
                return dt.to_pydatetime()
            return dt

        def _to_int(v):
            if _is_bad(v):
                return None
            n = pd.to_numeric(v, errors="coerce")
            if pd.isna(n):
                return None
            return int(float(n))

        def _to_float(v):
            if _is_bad(v):
                return None
            n = pd.to_numeric(v, errors="coerce")
            if pd.isna(n):
                return None
            return float(n)

        def _normalize_basic(d: pd.DataFrame) -> pd.DataFrame:
            out = d.copy().reset_index(drop=True)
            out = out.replace([np.inf, -np.inf], None)
            out = out.astype(object).where(pd.notna(out), None)

            for c in out.columns:
                out[c] = out[c].apply(
                    lambda x: None
                    if isinstance(x, str) and x.strip().lower() in bad_strings
                    else x
                )

            return out.astype(object)

        def _normalize_by_target_schema(
            d: pd.DataFrame,
            cols_types: list[tuple[str, str]],
        ) -> pd.DataFrame:
            out = _normalize_basic(d)
            type_map = {str(c): _base_mysql_type(t) for c, t in cols_types}

            char_types = {
                "char",
                "varchar",
                "tinytext",
                "text",
                "mediumtext",
                "longtext",
                "json",
            }
            int_types = {
                "tinyint",
                "smallint",
                "mediumint",
                "int",
                "integer",
                "bigint",
            }
            float_types = {
                "float",
                "double",
                "decimal",
                "numeric",
                "real",
            }
            datetime_types = {
                "datetime",
                "timestamp",
                "date",
                "time",
            }

            for c in out.columns:
                t = type_map.get(c, "")

                if t in char_types:
                    out[c] = out[c].apply(_to_text).astype(object)
                elif t in datetime_types:
                    out[c] = out[c].apply(_to_datetime).astype(object)
                elif t in int_types:
                    out[c] = out[c].apply(_to_int).astype(object)
                elif t in float_types:
                    out[c] = out[c].apply(_to_float).astype(object)
                else:
                    # 未知型態不要補 nan，避免污染
                    out[c] = out[c].apply(
                        lambda x: None
                        if isinstance(x, str) and x.strip().lower() in bad_strings
                        else x
                    ).astype(object)

            return out.astype(object)

        def _clean_staging_table_by_target_schema(
            conn,
            stg_qual: str,
            use_cols: list[str],
            cols_types: list[tuple[str, str]],
        ):
            """
            最重要的保險：
            pandas.to_sql 建完 staging 後，直接在 MySQL 端把非文字欄位中的 'nan' 等字串改成 NULL。
            這可以解掉 Incorrect datetime value: 'nan'。
            """
            type_map = {str(c): _base_mysql_type(t) for c, t in cols_types}

            char_types = {
                "char",
                "varchar",
                "tinytext",
                "text",
                "mediumtext",
                "longtext",
                "json",
            }

            bad_list_sql = "'', 'nan', 'none', 'null', '<na>', 'nat', 'inf', '-inf'"

            for c in use_cols:
                base_type = type_map.get(c, "")

                # 文字欄位允許 text_na，不清成 NULL
                if base_type in char_types:
                    continue

                # 非文字欄位：datetime / int / double / decimal 全部清掉字串 nan
                sql = f"""
                UPDATE {stg_qual}
                SET `{c}` = NULL
                WHERE LOWER(TRIM(CAST(`{c}` AS CHAR))) IN ({bad_list_sql})
                """
                conn.execute(text(sql))

        df = _normalize_basic(df)

        before = len(df)
        df.drop_duplicates(inplace=True, ignore_index=True)
        after = len(df)
        dropped_local = before - after

        if after == 0:
            logging.info("[append_or_create_dedup] df 去重後為空，略過。")
            return 0

        tbl_qual = self._qual_table(table_name)

        with self.engine.begin() as conn:
            if not self.table_exists(table_name):
                # 表不存在：先建立，不對 object 全欄補 nan
                df_create = _normalize_basic(df)

                df_create.to_sql(
                    name=table_name,
                    con=self.engine,
                    schema=self.db,
                    if_exists="fail",
                    index=False,
                    chunksize=chunksize,
                    method="multi",
                )

                cols_types = self._columns_and_types(table_name)
                char_types = {
                    "char",
                    "varchar",
                    "tinytext",
                    "text",
                    "mediumtext",
                    "longtext",
                    "json",
                }

                text_cols = [
                    c for c, t in cols_types
                    if _base_mysql_type(t) in char_types
                ]

                for c in text_cols:
                    conn.execute(
                        text(f"UPDATE {tbl_qual} SET `{c}` = :na WHERE `{c}` IS NULL"),
                        {"na": text_na},
                    )

                logging.info(
                    f"[append_or_create_dedup] 建立新表 {self.db}.{table_name} 並寫入 {after} 列（df 端先去除 {dropped_local} 重複）。"
                )
                return after

            # 目標表已存在
            cols_types = self._columns_and_types(table_name)
            target_cols = [c for c, _ in cols_types]

            use_cols = [c for c in df.columns if c in target_cols]
            if not use_cols:
                logging.warning("[append_or_create_dedup] df 欄位與目標表無交集，無法寫入。")
                return 0

            df_use = df[use_cols].copy()
            df_use = _normalize_by_target_schema(df_use, cols_types)

            before2 = len(df_use)
            df_use.drop_duplicates(inplace=True, ignore_index=True)
            dropped_local += before2 - len(df_use)

            if df_use.empty:
                logging.info("[append_or_create_dedup] df_use 去重後為空，略過。")
                return 0

            stg_name = f"__stg_{table_name}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
            stg_qual = self._qual_table(stg_name)

            try:
                df_use.to_sql(
                    name=stg_name,
                    con=self.engine,
                    schema=self.db,
                    if_exists="replace",
                    index=False,
                    chunksize=chunksize,
                    method="multi",
                )

                # 這段是本次修正核心：staging table 寫入後再強制清一次
                _clean_staging_table_by_target_schema(
                    conn=conn,
                    stg_qual=stg_qual,
                    use_cols=use_cols,
                    cols_types=cols_types,
                )

                if dedup_keys:
                    keys = [k for k in dedup_keys if k in use_cols]
                    if not keys:
                        logging.warning("[append_or_create_dedup] dedup_keys 不在目標表中，改用全欄位去重。")
                        keys = use_cols
                else:
                    keys = use_cols

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

            finally:
                conn.execute(text(f"DROP TABLE IF EXISTS {stg_qual}"))

            char_types = {
                "char",
                "varchar",
                "tinytext",
                "text",
                "mediumtext",
                "longtext",
                "json",
            }

            text_cols = [
                c for c, t in cols_types
                if _base_mysql_type(t) in char_types
            ]

            for c in text_cols:
                conn.execute(
                    text(f"UPDATE {tbl_qual} SET `{c}` = :na WHERE `{c}` IS NULL"),
                    {"na": text_na},
                )

            logging.info(
                f"[append_or_create_dedup] 追加完成：插入 {inserted} 列；df 端先去除 {dropped_local} 重複。"
            )
            return inserted

if __name__ == "__main__":
    #main()
    dbhandler = MySQLConnet('l6a01_project')
    tables = dbhandler.list_tables()