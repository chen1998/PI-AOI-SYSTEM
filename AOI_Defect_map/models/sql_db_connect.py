# %%
import pandas as pd
import logging
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import SQLAlchemyError
import pymysql
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

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
        
   
    def drop_table(self, table_name):
        try:
            with self.engine.begin() as conn:
                conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
            logging.info(f"[drop_table] 資料表 '{table_name}' 已刪除.")
        except SQLAlchemyError as e:
            logging.error(f"[drop_table] 刪除 '{table_name}' 發生錯誤: {e}")

    #=======================前端 ask ==============================
    # 抓近 N 天
    def get_runs_delta_days(self, tbn, days=30):
        sql = f"""
        SELECT * FROM {self.db}.{tbn}
        WHERE scantime >= NOW() - INTERVAL :days DAY
        ORDER BY scantime DESC
        """
        return pd.read_sql(text(sql), self.engine, params={"days": days})

    # 抓日期區間
    def get_runs_between(self, tbn, start_date, end_date):
         
        sql = f"""
        SELECT * FROM {self.db}.{tbn}
        WHERE run_day BETWEEN :start AND :end
        ORDER BY scantime DESC
        """
        return pd.read_sql(text(sql), self.engine, params={"start": start_date, "end": end_date})
    
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
    

#%%
if __name__ == "__main__":
    #main()
    dbhandler = MySQLConnet('l6a01_project')
    tables = dbhandler.list_tables()