#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import logging
from datetime import datetime
from typing import Optional, Tuple, List

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# -------- Logging --------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(funcName)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ====== 可調參數 ======
DB_HOST = os.getenv("DB_HOST", "10.97.142.217")
DB_USER = os.getenv("DB_USER", "l6a01_user")
DB_PASS = os.getenv("DB_PASS", "l6a01$user")
DB_NAME = os.getenv("DB_NAME", "l6a01_project")

RECIPE_LEN = int(os.getenv("RECIPE_LEN", "255"))
GROUP_CONCAT_MAX_LEN = int(os.getenv("GROUP_CONCAT_MAX_LEN", str(1_048_576)))
PIDENSITY_PATTERN = re.compile(r"^(AOI[123]00)_PIDENSITY_(\d{6})_(PI[1-7]00)$", re.IGNORECASE)

# ====== 分桶規則（與 SQL CASE 對齊） ======
CASE_BUCKET_SQL = """
CASE
  WHEN CAST(NULLIF(defect_size,'') AS SIGNED) >= 401 THEN 'o'
  WHEN CAST(NULLIF(defect_size,'') AS SIGNED) BETWEEN 101 AND 400 THEN 'l'
  WHEN CAST(NULLIF(defect_size,'') AS SIGNED) BETWEEN 21  AND 100 THEN 'm'
  WHEN CAST(NULLIF(defect_size,'') AS SIGNED) <= 20 THEN 's'
  ELSE NULL
END
"""

# defect_type：
DEFECT_TYPE_SQL = """
CASE
  WHEN NULLIF(TRIM(ai_code_1), '') IN ('Polymer','SSIU_Polymer')
       THEN 'Particle'
  WHEN NULLIF(TRIM(ai_code_1), '') IN ('PI_Spot_NP','PIS With Particle')
       THEN 'PISpot'
  ELSE ''
END
"""

BASE_SUBQUERY = lambda db, raw, recipe_len: f"""
  SELECT
    /* 整點取齊，命名為 pi_hour */
    CAST(DATE_FORMAT(COALESCE(scan_time, `day`), '%Y-%m-%d %H:00:00') AS DATETIME) AS pi_hour,
    line_id,
    model,
    glass_type,
    LEFT(recipe_id, {recipe_len}) AS recipe_id,
    glass_id,
    CAST(NULLIF(defect_size,'') AS SIGNED)   AS defect_size,
    CAST(NULLIF(defect_count,'') AS SIGNED)  AS defect_count,
    NULLIF(TRIM(chip_name), '')              AS chip_name,
    NULLIF(TRIM(ai_code_1), '')              AS ai_code_1
  FROM `{db}`.`{raw}`
"""

# ====== 連線 & schema helpers ======
def get_engine(dbname: str):
    url = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}/{dbname}?charset=utf8mb4"
    return create_engine(url, pool_pre_ping=True, pool_recycle=3600)

def set_group_concat_big(engine, size: int = GROUP_CONCAT_MAX_LEN):
    with engine.begin() as conn:
        conn.execute(text(f"SET SESSION group_concat_max_len = {size}"))

def table_exists(engine, db: str, table: str) -> bool:
    sql = """
    SELECT 1 FROM information_schema.tables
    WHERE table_schema=:db AND table_name=:t
    LIMIT 1
    """
    with engine.connect() as conn:
        return conn.execute(text(sql), {"db": db, "t": table}).fetchone() is not None

def get_columns(engine, db: str, table: str) -> List[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT COLUMN_NAME
                FROM information_schema.COLUMNS
                WHERE table_schema=:db AND table_name=:t
            """),
            {"db": db, "t": table},
        ).fetchall()
    return [r[0] for r in rows]

def ensure_monthly_pidensity_summary_table(engine, db: str, yyyymm: str):
    """
    建立（若不存在）或遷移 PIDENSITY_YYYYMM 月彙總表：
      - 移除 total_defects
      - 移除 chips
      - 新增 glass (TEXT)
      - 新增 comment (VARCHAR(1024) NOT NULL DEFAULT '')
    """
    t = f"PIDENSITY_{yyyymm}"
    if not table_exists(engine, db, t):
        # 新建表（不含 total_defects / chips，含 glass、comment）
        sql = f"""
        CREATE TABLE `{db}`.`{t}` (
            pi_hour DATETIME NOT NULL,
            aoi VARCHAR(8) NOT NULL,
            pi  VARCHAR(8) NOT NULL,
            line_id    VARCHAR(32),
            model      VARCHAR(128),
            glass_type VARCHAR(64),
            recipe_id  VARCHAR({RECIPE_LEN}),
            defect_type VARCHAR(32) NOT NULL DEFAULT '',
            ai_code_1   VARCHAR(64) NOT NULL DEFAULT '',
            n_rows        INT,
            n_glasses     INT,
            small_defect_count  INT,
            middle_defect_count INT,
            large_defect_count  INT,
            over_defect_count   INT,
            unknown_defect_count INT,
            glass TEXT,
            comment VARCHAR(1024) NOT NULL DEFAULT '',
            PRIMARY KEY (pi_hour, aoi, pi, line_id, model, glass_type, recipe_id, defect_type, ai_code_1),
            INDEX idx_pi_hour (pi_hour),
            INDEX idx_model (model),
            INDEX idx_recipe (recipe_id),
            INDEX idx_line (line_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        with engine.begin() as conn:
            conn.execute(text(sql))
        logging.info(f"[ensure] 已建立 {t}")
        return t
    
    # 已存在 → 做 schema 遷移
    cols = set(get_columns(engine, db, t))
    alters = []
    if "total_defects" in cols:
        alters.append("DROP COLUMN `total_defects`")
    if "chips" in cols:
        alters.append("DROP COLUMN `chips`")
    if "glass" not in cols:
        alters.append("ADD COLUMN `glass` TEXT")
    if "comment" not in cols:
        alters.append("ADD COLUMN `comment` VARCHAR(1024) NOT NULL DEFAULT '' AFTER `glass`")

    if alters:
        alt_sql = f"ALTER TABLE `{db}`.`{t}` " + ", ".join(alters) + ";"
        with engine.begin() as conn:
            conn.execute(text(alt_sql))
        logging.info(f"[ensure] {t} schema 遷移完成：{' | '.join(alters)}")
    else:
        logging.info(f"[ensure] {t} 已存在，且 schema 符合")

    return t

# ====== 解析 RAW 表名 ======
def parse_pidensity_table(t: str) -> Optional[Tuple[str, str, str]]:
    """
    回傳 (AOI?00, YYYYMM, PI?00)；不符合則 None
    """
    m = PIDENSITY_PATTERN.match(t)
    if not m:
        return None
    aoi, yyyymm, pi = m.group(1).upper(), m.group(2), m.group(3).upper()
    return aoi, yyyymm, pi

def list_pidensity_tables(engine, db: str, yyyymm: Optional[str] = None) -> List[str]:
    with engine.connect() as conn:
        tables: List[str] = [r[0] for r in conn.execute(text("SHOW TABLES")).fetchall()]
    cands = [t for t in tables if parse_pidensity_table(t)]
    if yyyymm:
        cands = [t for t in cands if parse_pidensity_table(t)[1] == yyyymm]
    return cands

# ====== 小工具：摘要列數（用來判斷是否有新增） ======
def summary_row_count(engine, db: str, yyyymm: str, aoi: Optional[str] = None, pi: Optional[str] = None) -> int:
    t = f"PIDENSITY_{yyyymm}"
    if not table_exists(engine, db, t):
        return 0
    where = []
    params = {"db": db, "t": t}
    if aoi:
        where.append("aoi=:aoi")
        params["aoi"] = aoi
    if pi:
        where.append("pi=:pi")
        params["pi"] = pi
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    with engine.connect() as conn:
        (cnt,) = conn.execute(text(f"SELECT COUNT(*) FROM `{db}`.`{t}` {clause}"), params).fetchone()
    return int(cnt)

# ====== 匯入：單一 RAW 表 → 月彙總表（冪等） ======
def upsert_single_raw_into_monthly_summary(engine, db: str, raw_table: str,
                                           aoi: str, yyyymm: str, pi: str) -> int:
    """
    #回傳：本次「新增的摘要列數」(估算為 upsert 前後的 row_count 差值)
    """
    t = ensure_monthly_pidensity_summary_table(engine, db, yyyymm)
    set_group_concat_big(engine)

    before = summary_row_count(engine, db, yyyymm, aoi, pi)

    base_sql = BASE_SUBQUERY(db, raw_table, RECIPE_LEN)

    sql = f"""
    INSERT INTO `{db}`.`{t}`
      (pi_hour, aoi, pi, line_id, model, glass_type, recipe_id,
       defect_type, ai_code_1,
       n_rows, n_glasses,
       small_defect_count, middle_defect_count, large_defect_count, over_defect_count,
       unknown_defect_count, glass, comment)
    SELECT
       L.pi_hour,
       :aoi AS aoi,
       :pi  AS pi,
       L.line_id, L.model, L.glass_type, L.recipe_id,
       L.defect_type,
       L.ai_code_1_clean AS ai_code_1,
       COUNT(*)                                  AS n_rows,
       COUNT(DISTINCT L.glass_id)                AS n_glasses,
       SUM(CASE WHEN L.size_bucket='s' THEN 1 ELSE 0 END) AS small_defect_count,
       SUM(CASE WHEN L.size_bucket='m' THEN 1 ELSE 0 END) AS middle_defect_count,
       SUM(CASE WHEN L.size_bucket='l' THEN 1 ELSE 0 END) AS large_defect_count,
       SUM(CASE WHEN L.size_bucket='o' THEN 1 ELSE 0 END) AS over_defect_count,
       SUM(CASE WHEN L.size_bucket IS NULL THEN 1 ELSE 0 END) AS unknown_defect_count,
       GROUP_CONCAT(DISTINCT NULLIF(TRIM(L.glass_id), '') ORDER BY L.glass_id SEPARATOR ',') AS glass,
       '' AS comment
    FROM (
        SELECT
            B.*,
            {CASE_BUCKET_SQL} AS size_bucket,
            {DEFECT_TYPE_SQL} AS defect_type,
            COALESCE(B.ai_code_1, '') AS ai_code_1_clean
        FROM (
            {base_sql}
        ) AS B
    ) AS L
    GROUP BY
       L.pi_hour, L.line_id, L.model, L.glass_type, L.recipe_id, L.defect_type, L.ai_code_1_clean
    ON DUPLICATE KEY UPDATE
       n_rows               = VALUES(n_rows),
       n_glasses            = VALUES(n_glasses),
       small_defect_count   = VALUES(small_defect_count),
       middle_defect_count  = VALUES(middle_defect_count),
       large_defect_count   = VALUES(large_defect_count),
       over_defect_count    = VALUES(over_defect_count),
       unknown_defect_count = VALUES(unknown_defect_count),
       glass                = VALUES(glass);
       /* 不更新 comment，避免覆寫既有備註 */
    """
    with engine.begin() as conn:
        conn.execute(text(sql), {"aoi": aoi, "pi": pi})

    after = summary_row_count(engine, db, yyyymm, aoi, pi)
    added = max(0, after - before)
    logging.info(f"[merge] {raw_table} → {t} 完成；新增摘要列數 = {added}")
    return added

# ====== 月度刷新（適合每小時排程呼叫） ======
def refresh_month(engine, db: str, yyyymm: str) -> int:
    """
    針對指定 YYYYMM：
      - 找到所有 AOI?00_PIDENSITY_YYYYMM_PI?00
      - 逐一 upsert 到 PIDENSITY_YYYYMM
      - 回傳：本次所有來源表合計「新增的摘要列數」
    """
    sources = list_pidensity_tables(engine, db, yyyymm=yyyymm)
    if not sources:
        logging.info(f"[refresh_month] 該月無來源表：{yyyymm}")
        return 0

    total_added = 0
    for raw in sorted(sources):
        parsed = parse_pidensity_table(raw)
        if not parsed:
            continue
        aoi, mm, pi = parsed
        try:
            added = upsert_single_raw_into_monthly_summary(engine, db, raw, aoi, mm, pi)
            total_added += added
        except SQLAlchemyError as e:
            logging.exception(f"[refresh_month] 處理 {raw} 失敗：{e}")

    logging.info(f"[refresh_month] {yyyymm} 完成；本次新增摘要列數總計 = {total_added}")
    return total_added

def print_table_schema(engine, db: str, table: str):
    q = """
    SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY, COLUMN_DEFAULT, EXTRA
    FROM information_schema.COLUMNS
    WHERE table_schema=:db AND table_name=:t
    ORDER BY ORDINAL_POSITION;
    """
    with engine.connect() as conn:
        rows = conn.execute(text(q), {"db": db, "t": table}).fetchall()
    logging.info(f"[schema] {table} 欄位：")
    for r in rows:
        col, ctype, nullable, key, default, extra = r
        #logging.info(f"  - {col:22s} {ctype:20s} NULLABLE={nullable} KEY={key or ''} DEFAULT={default if default is not None else ''} {extra or ''}")

# ====== 主程式 ======
def main():
    engine = get_engine(DB_NAME)

    prefer = os.getenv("RAW_TABLE")
    target_yyyymm = os.getenv("TARGET_YYYYMM")

    if prefer:
        raw = prefer
        parsed = parse_pidensity_table(raw)
        if not parsed:
            raise ValueError(f"來源表名不符合規則：{raw}")
        aoi, yyyymm, pi = parsed
        logging.info(f"[run:single] 來源表={raw} | aoi={aoi} | yyyymm={yyyymm} | pi={pi}")
        upsert_single_raw_into_monthly_summary(engine, DB_NAME, raw, aoi, yyyymm, pi)
        print_table_schema(engine, DB_NAME, f"PIDENSITY_{yyyymm}")
        return

    if not target_yyyymm:
        target_yyyymm = datetime.now().strftime("%Y%m")
    logging.info(f"[run:month] 目標月份={target_yyyymm}")

    refresh_month(engine, DB_NAME, target_yyyymm)
    print_table_schema(engine, DB_NAME, f"PIDENSITY_{target_yyyymm}")

if __name__ == "__main__":
    try:
        main()
    except SQLAlchemyError as e:
        logging.exception(f"DB Error: {e}")
    except Exception as e:
        logging.exception(f"Unhandled Error: {e}")

"""
# 支援三種模式：
# 1) RAW_TABLE 指定單一來源表（立即 upsert）
#    set RAW_TABLE=aoi100_pidensity_202509_pi100
#    python aoi_density_summary_job.py
#
# 2) TARGET_YYYYMM 指定月份跑整月
#    set TARGET_YYYYMM=202509
#    python aoi_density_summary_job.py
#
# 3) 預設：跑「當月」整月（適合每小時排程）
#    python aoi_density_summary_job.py

"""