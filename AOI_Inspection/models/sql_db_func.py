import pandas as pd
import logging
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import SQLAlchemyError
import pymysql



# 設定 logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("db_handler.log"),  # 記錄到檔案
        logging.StreamHandler()                 # 同時輸出到終端
    ]
)

class MySQLConnetFunc:
    def __init__(self, dbname):
        host = "10.97.142.217"
        username = "l6a01_user"
        password = "l6a01$user"

        self.engine = create_engine(f"mysql+pymysql://{username}:{password}@{host}/{dbname}")
        #cvd_toolbox
    def save_df(self, df, table_name):
        try:
            df.to_sql(table_name, con=self.engine, index=False, if_exists='replace')
            logging.info(f"[save_df] 資料表 '{table_name}' 已覆蓋儲存 ({len(df)} rows).")
        except SQLAlchemyError as e:
            logging.error(f"[save_df] 儲存 '{table_name}' 發生錯誤: {e}")

    def append_new_rows(self, df, table_name, key_cols):
        try:
            db_df = pd.read_sql_table(table_name, self.engine)
            new_rows = df.merge(db_df[key_cols], on=key_cols, how='left', indicator=True)
            append_df = new_rows[new_rows['_merge'] == 'left_only'].drop(columns=['_merge'])
            if not append_df.empty:
                append_df.to_sql(table_name, con=self.engine, index=False, if_exists='append')
                logging.info(f"[append_new_rows] 向 '{table_name}' 新增 {len(append_df)} 筆資料.")
            else:
                logging.info(f"[append_new_rows] 無新增資料可寫入 '{table_name}'.")
        except Exception as e:
            logging.warning(f"[append_new_rows] 無法取得 '{table_name}'，直接新建。")
            try:
                df.to_sql(table_name, con=self.engine, index=False, if_exists='replace')
                logging.info(f"[append_new_rows] '{table_name}' 已建立，新增 {len(df)} 筆資料.")
            except SQLAlchemyError as e:
                logging.error(f"[append_new_rows] 建立 '{table_name}' 發生錯誤: {e}")

    def get_table(self, table_name):
        try:
            df = pd.read_sql_table(table_name, self.engine)
            #logging.info(f"get_table- 讀取資料表 '{table_name}' 成功 ({len(df)} rows).")
            return df
        except SQLAlchemyError as e:
            logging.error(f"[get_table] 讀取 '{table_name}' 發生錯誤: {e}")
            return pd.DataFrame()
    """
    def update_row(self, table_name, match_keys: dict, new_values: dict):
        try:
            set_clause = ', '.join([f"{k} = :{k}" for k in new_values])
            where_clause = ' AND '.join([f"{k} = :{k}" for k in match_keys])
            sql = f"UPDATE `{table_name}` SET {set_clause} WHERE {where_clause}"
            params = {**new_values, **match_keys}
            with self.engine.begin() as conn:
                result = conn.execute(text(sql), params)
                logging.info(f"[update_row] 更新 '{table_name}' {result.rowcount} 筆資料.")
        except SQLAlchemyError as e:
            logging.error(f"[update_row] 更新 '{table_name}' 發生錯誤: {e}")
    """
    
    def update_row(self, table_name, match_keys: dict, new_values: dict):
        try:
            set_clause = ', '.join([f"{k} = :{k}" for k in new_values])
            where_clause = ' AND '.join([
                f"{k} LIKE :{k}" if isinstance(v, str) and '%' in v else f"{k} = :{k}"
                for k, v in match_keys.items()
            ])
            sql = f"UPDATE `{table_name}` SET {set_clause} WHERE {where_clause}"
            params = {**new_values, **match_keys}
            with self.engine.begin() as conn:
                result = conn.execute(text(sql), params)
                logging.info(f"[update_row] 更新 '{table_name}' {result.rowcount} 筆資料.")
        except SQLAlchemyError as e:
            logging.error(f"[update_row] 更新 '{table_name}' 發生錯誤: {e}")

    def get_row(self, table_name, match_keys: dict):
        try:
            where_clause = ' AND '.join([f"{k} = :{k}" for k in match_keys])
            sql = f"SELECT * FROM `{table_name}` WHERE {where_clause}"
            with self.engine.connect() as conn:
                result = conn.execute(text(sql), match_keys).fetchone()
            if result:
                logging.info(f"[get_row] 成功取得 '{table_name}' 符合條件資料.")
                return dict(result._mapping)
            else:
                logging.info(f"[get_row] '{table_name}' 無符合條件資料.")
                return {}
        except SQLAlchemyError as e:
            logging.error(f"[get_row] 查詢 '{table_name}' 發生錯誤: {e}")
            return {}

    def get_rows_by_months(self, table_name, last_ym, current_ym):
        try:
            sql = f"""
                SELECT * FROM `{table_name}`
                WHERE last_ym = :last_ym AND current_ym = :current_ym
            """
            with self.engine.connect() as conn:
                df = pd.read_sql(text(sql), conn, params={'last_ym': last_ym, 'current_ym': current_ym})
            logging.info(f"[get_rows_by_months] 查詢 '{table_name}' 成功 ({len(df)} rows).")
            return df
        except SQLAlchemyError as e:
            logging.error(f"[get_rows_by_months] 查詢 '{table_name}' 發生錯誤: {e}")
            return pd.DataFrame()

    def get_rows_by_conditions(self, table_name, match_dicts: dict):
        try:
            where_clause = ' AND '.join([f"{k} = :{k}" for k in match_dicts])
            sql = f"SELECT * FROM `{table_name}` WHERE {where_clause}"
            with self.engine.connect() as conn:
                df = pd.read_sql(text(sql), conn, params=match_dicts)
            logging.info(f"[get_rows_by_conditions] 查詢 '{table_name}' 成功 ({len(df)} rows).")
            return df
        except SQLAlchemyError as e:
            logging.error(f"[get_rows_by_conditions] 查詢 '{table_name}' 發生錯誤: {e}")
            return pd.DataFrame()

    def drop_table(self, table_name):
        try:
            with self.engine.begin() as conn:
                conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
            logging.info(f"[drop_table] 資料表 '{table_name}' 已刪除.")
        except SQLAlchemyError as e:
            logging.error(f"[drop_table] 刪除 '{table_name}' 發生錯誤: {e}")
    
    def list_tables(self):
        try:
            inspector = inspect(self.engine)
            tables = inspector.get_table_names()
            logging.info(f"[list_tables] 成功取得資料表名稱，共 {len(tables)} 張表。")
            return tables
        except SQLAlchemyError as e:
            logging.error(f"[list_tables] 取得資料表名稱時發生錯誤: {e}")
            return []
        
    def get_tables_containing(self, substring: str):
        """回傳所有資料表中包含指定子字串的名稱 list"""
        with self.engine.connect() as conn:
            result = conn.execute(text("SHOW TABLES"))
            all_tables = [row[0] for row in result]
        return [t for t in all_tables if substring.lower() in t]
    
    def delete_row_by_key(self, table_name, match_keys: dict):
        try:
            where_clause = ' AND '.join([f"{k} = :{k}" for k in match_keys])
            sql = f"DELETE FROM `{table_name}` WHERE {where_clause}"
            with self.engine.begin() as conn:
                result = conn.execute(text(sql), match_keys)
            logging.info(f"[delete_row_by_key] 刪除 '{table_name}' 中 {result.rowcount} 筆符合條件的資料。")
        except SQLAlchemyError as e:
            logging.error(f"[delete_row_by_key] 刪除 '{table_name}' 資料時發生錯誤: {e}")

    def rename_tables_remove_9d(self):
        """
        將所有以 '_9d' 結尾的資料表，重新命名為去除 '_9d' 的版本。
        若目標表已存在，將略過並發出警告。
        """
        try:
            inspector = inspect(self.engine)
            all_tables = inspector.get_table_names()
            target_tables = [t for t in all_tables if t.lower().endswith('_9d')]

            renamed_count = 0
            for old_name in target_tables:
                new_name = old_name[:-3]  # 去掉最後三個字元 "_9d"
                if new_name in all_tables:
                    logging.warning(f"[rename_tables_remove_9d] 目標表 '{new_name}' 已存在，略過 '{old_name}'。")
                    continue

                sql = f"RENAME TABLE `{old_name}` TO `{new_name}`"
                with self.engine.begin() as conn:
                    conn.execute(text(sql))
                    logging.info(f"[rename_tables_remove_9d] 資料表 '{old_name}' 已重新命名為 '{new_name}'。")
                    renamed_count += 1

            logging.info(f"[rename_tables_remove_9d] 共重新命名 {renamed_count} 張資料表。")

        except SQLAlchemyError as e:
            logging.error(f"[rename_tables_remove_9d] 重命名過程發生錯誤: {e}")
