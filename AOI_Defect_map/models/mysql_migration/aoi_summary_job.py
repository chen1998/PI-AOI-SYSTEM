#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(funcName)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ---------------- Engine ----------------
class Connet:
    def __init__(self, dbname, host="127.0.0.1", port=3306, user="l6a01_user", pwd="l6a01$user"):
        self.dbname = dbname
        url = f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{dbname}?charset=utf8mb4"
        self.engine = create_engine(
            url,
            pool_pre_ping=True,   # 掉線自動偵測
            pool_recycle=3600,
        )
        # 啟動時做一次健康檢查，失敗就拋出明確訊息
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except SQLAlchemyError as e:
            logging.error(f"[connect] 無法連到 {host}:{port}/{dbname}，請檢查 MySQL 服務/防火牆/帳密/授權。原始錯誤：{e}")
            raise

# ---------------- Helpers ----------------
def table_exists(engine, db, table):
    sql = """
    SELECT 1 FROM information_schema.tables
    WHERE table_schema=:db AND table_name=:t LIMIT 1
    """
    with engine.connect() as conn:
        return conn.execute(text(sql), {"db": db, "t": table}).fetchone() is not None

def get_col_len(engine, db, table, col):
    sql = """
    SELECT CHARACTER_MAXIMUM_LENGTH
    FROM information_schema.columns
    WHERE table_schema=:db AND table_name=:t AND column_name=:c
    """
    with engine.connect() as conn:
        r = conn.execute(text(sql), {"db": db, "t": table, "c": col}).fetchone()
        return int(r[0]) if r and r[0] is not None else None

def safe_alter_varchar(engine, db, table, col, want_len):
    cur = get_col_len(engine, db, table, col)
    if cur is None:
        return
    if cur < want_len:
        sql = f"ALTER TABLE `{db}`.`{table}` MODIFY `{col}` VARCHAR({want_len})"
        with engine.begin() as conn:
            conn.execute(text(sql))
        logging.info(f"[{table}] widen {col} {cur} -> {want_len}")

# ---------------- Summary table DDL ----------------
def ensure_summary_table(engine, db, line):
    """
    建立彙整表（若不存在），或放大必要長度：
      line_id   VARCHAR(32)
      model     VARCHAR(128)
      glass_id  VARCHAR(64)
      recipe_id VARCHAR(255)
    """
    t = f"aoi_summary_{line}"
    if not table_exists(engine, db, t):
        sql = f"""
        CREATE TABLE `{db}`.`{t}` (
            run_day DATE NOT NULL,
            scantime DATETIME NOT NULL,
            line_id VARCHAR(32),
            model VARCHAR(128),
            glass_id VARCHAR(64),
            recipe_id VARCHAR(255),
            defect_count INT,
            over_defect_count INT,
            large_defect_count INT,
            middle_defect_count INT,
            small_defect_count INT,
            chips TEXT,
            sample_image_path TEXT,
            PRIMARY KEY (run_day, model, glass_id, recipe_id),
            INDEX idx_glass (glass_id),
            INDEX idx_recipe (recipe_id),
            INDEX idx_model (model),
            INDEX idx_run_day (run_day),
            INDEX idx_scantime (scantime)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        with engine.begin() as conn:
            conn.execute(text(sql))
        logging.info(f"[{line}] created {t}")
    else:
        logging.info(f"[{line}] ensured {t} (exists)")

    # 若已存在但長度太短 → 放大（不會縮小）
    safe_alter_varchar(engine, db, t, "line_id",   32)
    safe_alter_varchar(engine, db, t, "model",     128)
    safe_alter_varchar(engine, db, t, "glass_id",  64)
    safe_alter_varchar(engine, db, t, "recipe_id", 255)

# ---------------- Merge from monthly ----------------
def log_recipe_maxlen(engine, db, month_table):
    sql = f"SELECT MAX(CHAR_LENGTH(recipe_id)) FROM `{db}`.`{month_table}`"
    with engine.connect() as conn:
        r = conn.execute(text(sql)).fetchone()
    maxlen = int(r[0]) if r and r[0] is not None else 0
    logging.info(f"[check] {month_table}.recipe_id MAX len = {maxlen}")
    return maxlen

def upsert_summary_from_month(engine, db: str, line: str, month_table: str) -> None:
    """
    將月表彙總進 summary（ONLY_FULL_GROUP_BY-safe）
    - scantime 用 MAX(scantime)
    - chips 聚合 DISTINCT chip_name
    - recipe_id 以 LEFT(recipe_id,255) 防止來源超長報錯
    - 再次執行會以 PRIMARY KEY upsert：更新 chips、sample_image_path，並把 scantime 更新為較晚
    """
    dst = f"aoi_summary_{line}"

    # 診斷一下來源長度
    log_recipe_maxlen(engine, db, month_table)

    sql = f"""
    INSERT INTO `{db}`.`{dst}`
    (run_day, scantime, line_id, model, glass_id, recipe_id,
     defect_count, over_defect_count, large_defect_count, middle_defect_count, small_defect_count,
     chips, sample_image_path)
    SELECT
        DATE(COALESCE(day, scantime)) AS run_day,
        MAX(scantime)                 AS scantime,
        line_id,
        model,
        glass_id,
        LEFT(recipe_id, 255)          AS recipe_id,   -- 關鍵：保險截斷
        MIN(defect_count)             AS defect_count,
        MIN(over_defect_count)        AS over_defect_count,
        MIN(large_defect_count)       AS large_defect_count,
        MIN(middle_defect_count)      AS middle_defect_count,
        MIN(small_defect_count)       AS small_defect_count,
        GROUP_CONCAT(DISTINCT chip_name ORDER BY chip_name SEPARATOR ',') AS chips,
        MIN(image_path)               AS sample_image_path
    FROM `{db}`.`{month_table}`
    GROUP BY DATE(COALESCE(day, scantime)), line_id, model, glass_id, LEFT(recipe_id,255)
    ON DUPLICATE KEY UPDATE
        scantime = GREATEST(`{dst}`.scantime, VALUES(scantime)),
        chips = VALUES(chips),
        sample_image_path = LEAST(`{dst}`.sample_image_path, VALUES(sample_image_path));
    """
    with engine.begin() as conn:
        conn.execute(text(sql))
    logging.info(f"[{line}] merged {month_table} -> {dst}")

# ---------------- Orchestrator ----------------
def refresh_all(engine, db, lines):
    with engine.connect() as conn:
        tables = [r[0] for r in conn.execute(text("SHOW TABLES")).fetchall()]
    for line in lines:
        ensure_summary_table(engine, db, line)
        month_tables = [t for t in tables if t.startswith(f"{line}_rawdata_")]
        month_tables.sort()  # 由舊到新
        for mt in month_tables:
            upsert_summary_from_month(engine, db, line, mt)

# ---------------- Main ----------------
def main():
    dbname = 'l6a01_project'
    conn = Connet(dbname)
    engine = conn.engine
    lines = [ 'aoi100', 'aoi200', 'aoi300'] #
    refresh_all(engine, dbname, lines)

if __name__ == "__main__":
    main()