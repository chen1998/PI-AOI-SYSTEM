
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
pidenisty_pihour monthly summary job (RAW → pidenisty_pihour_YYYYMM)

本版調整（重要）：
- 主分群鍵 **移除 pic_path**（與其 hash），避免同小時多路徑造成分母重覆。
- summary 新增 `pic_paths MEDIUMTEXT`，以 DISTINCT 逗號字串彙整（如同 glass 欄位）。
- 所有 GROUP BY **一律用 pi_time 切整點後的 pi_hour**（完全不吃 RAW 自帶的 pi_hour）。
- 分母以 glass_id 聯集去重（COUNT DISTINCT <pi_time,glass_id>），避免拿掉 pic_path 後的誤加總。
- 偵錯輸出僅保留你指定的關鍵數據。
"""

import os
import re
import logging
from datetime import datetime, timedelta, date
from typing import Optional, Tuple, List, Dict

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# =========================
# 小工具
# =========================
def _fmt_ts(x) -> str:
    if x is None:
        return "NULL"
    if isinstance(x, (datetime, date)):
        return x.strftime("%Y-%m-%d %H:%M:%S")
    s = str(x)
    try:
        return datetime.fromisoformat(s.replace(" ", "T")).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return s

# =========================
# Logging
# =========================
LOG_FILE = os.getenv("LOG_FILE", "pidenisty_pihour_job.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(funcName)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler()],
)

# =========================
# Config
# =========================
DB_HOST = os.getenv("DB_HOST", "10.97.142.217")
DB_USER = os.getenv("DB_USER", "l6a01_user")
DB_PASS = os.getenv("DB_PASS", "l6a01$user")
DB_NAME = os.getenv("DB_NAME", "l6a01_project")

RECIPE_LEN = int(os.getenv("RECIPE_LEN", "255"))
GROUP_CONCAT_MAX_LEN = int(os.getenv("GROUP_CONCAT_MAX_LEN", str(1_048_576)))
SUMMARY_PREFIX = (os.getenv("SUMMARY_PREFIX", "pidenisty_pihour") or "pidenisty_pihour").strip()
LIVE_WINDOW_MIN = int(os.getenv("LIVE_WINDOW_MIN", "60"))
DEBUG_GROUP_MAX = int(os.getenv("DEBUG_GROUP_MAX", "10"))  # 列出幾組主分群的最新 pi_hour

PIDENSITY_PATTERN = re.compile(r"^(AOI[123]00)_PIDENSITY_(\d{6})_(PI[1-7]00)$", re.IGNORECASE)

# 主分群鍵（**不含 pic_path**；也不含 ai_code_1；時間以派生 pi_hour 為準）
PRIMARY_MAIN_KEYS = ["pi_hour", "line_id", "model", "glass_type", "recipe_id"]
PRIMARY_WITH_AI = PRIMARY_MAIN_KEYS + ["ai_code_1"]

# =========================
# DB helpers
# =========================
CUSHION_MIN = int(os.getenv("CUSHION_MIN", "360"))

def get_engine(dbname: str):
    url = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}/{dbname}?charset=utf8mb4"
    return create_engine(url, pool_pre_ping=True, pool_recycle=3600)

def table_exists(engine, db: str, table: str) -> bool:
    sql = """
    SELECT 1 FROM information_schema.tables
    WHERE table_schema=:db AND table_name=:t LIMIT 1
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

def index_exists(engine, db: str, table: str, index_name: str) -> bool:
    sql = """
    SELECT 1
    FROM information_schema.statistics
    WHERE table_schema=:db AND table_name=:t AND index_name=:idx
    LIMIT 1
    """
    with engine.connect() as conn:
        return conn.execute(text(sql), {"db": db, "t": table, "idx": index_name}).fetchone() is not None

def _sanitize_yyyymm(yyyymm: str) -> str:
    yyyymm = (yyyymm or "").strip()
    if not re.fullmatch(r"\d{6}", yyyymm):
        raise ValueError(f"TARGET_YYYYMM 不合法：{yyyymm!r}")
    return yyyymm

def get_column_types(engine, db: str, table: str) -> Dict[str, str]:
    """
    回傳 {column_name: data_type}，例如 {'aoi': 'text', 'line_id': 'varchar', ...}
    """
    sql = """
    SELECT COLUMN_NAME, DATA_TYPE
    FROM information_schema.COLUMNS
    WHERE table_schema=:db AND table_name=:t
    """
    with engine.connect() as conn:
        rows = conn.execute(text(sql), {"db": db, "t": table}).fetchall()
    return {r[0]: r[1].lower() for r in rows}


def has_primary_key(engine, db: str, table: str) -> bool:
    """
    檢查該表是否已經有 PRIMARY KEY（用 TABLE_CONSTRAINTS，比 statistics 更穩）
    """
    sql = """
    SELECT COUNT(*)
    FROM information_schema.TABLE_CONSTRAINTS
    WHERE table_schema = :db
      AND table_name   = :t
      AND CONSTRAINT_TYPE = 'PRIMARY KEY'
    """
    with engine.connect() as conn:
        (cnt,) = conn.execute(text(sql), {"db": db, "t": table}).fetchone()
    return cnt > 0

# =========================
# Schema ensure / migrate
# =========================
def ensure_monthly_summary_table(engine, db: str, yyyymm: str) -> str:
    yyyymm = _sanitize_yyyymm(yyyymm)
    t = f"{SUMMARY_PREFIX}_{yyyymm}"

    create_sql = f"""
    CREATE TABLE `{db}`.`{t}` (
        pi_hour   DATETIME NOT NULL,       -- 由 pi_time 切到整點
        aoi       VARCHAR(16) NOT NULL,
        line_id    VARCHAR(32),
        model      VARCHAR(128),
        glass_type VARCHAR(64),
        recipe_id  VARCHAR({RECIPE_LEN}),
        ai_code_1  VARCHAR(64) NOT NULL DEFAULT '',

        maingroup_glass_count   INT,
        maingroup_defect_count  INT,
        defect_code_glass_count INT,
        defect_code_count       INT,
        small_defect_count      INT,
        middle_defect_count     INT,
        large_defect_count      INT,
        over_defect_count       INT,

        glass      MEDIUMTEXT,            -- 逐小時/分群的玻璃清單（去重）
        pic_paths  MEDIUMTEXT,            -- 逐小時/分群的影像路徑清單（去重）
        comment   VARCHAR(1024) NULL DEFAULT NULL,

        PRIMARY KEY (pi_hour, aoi, line_id, model, glass_type, recipe_id, ai_code_1),
        INDEX idx_pi_hour (pi_hour),
        INDEX idx_model (model),
        INDEX idx_recipe (recipe_id),
        INDEX idx_line (line_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC;
    """

    # ---- 第一次建表：照新 schema 建 ----
    if not table_exists(engine, db, t):
        with engine.begin() as conn:
            conn.execute(text(create_sql))
        logging.info(f"[ensure] 已建立 {t}")
        return t

    # ---- 已存在表：做 schema 遷移 ----
    cols = set(get_columns(engine, db, t))
    col_types = get_column_types(engine, db, t)   # << 新增這行
    alters = []

    def add_if_missing(col_name: str, clause: str):
        if col_name not in cols:
            alters.append(clause)

    # 需要的欄位（若缺才加）
    add_if_missing("aoi", "ADD COLUMN `aoi` VARCHAR(16) NOT NULL AFTER `pi_hour`")
    for c in ["maingroup_glass_count","maingroup_defect_count","defect_code_glass_count","defect_code_count",
              "small_defect_count","middle_defect_count","large_defect_count","over_defect_count"]:
        add_if_missing(c, f"ADD COLUMN `{c}` INT")
    add_if_missing("glass", "ADD COLUMN `glass` MEDIUMTEXT")
    add_if_missing("pic_paths", "ADD COLUMN `pic_paths` MEDIUMTEXT")
    add_if_missing("comment", "ADD COLUMN `comment` VARCHAR(1024) NULL DEFAULT NULL")

    # 移除舊欄位
    if "pic_path_hash" in cols:
        alters.append("DROP COLUMN `pic_path_hash`")
    if "pic_path" in cols:
        alters.append("DROP COLUMN `pic_path`")
    if "scan_time" in cols:
        alters.append("DROP COLUMN `scan_time`")
    if "pi_time" in cols:
        alters.append("DROP COLUMN `pi_time`")

    #  關鍵：修正 aoi 型別，避免 TEXT/BLOB 被拿來當 PK
    PK_COLUMNS = {
        "aoi": "VARCHAR(16)",
        "line_id": "VARCHAR(32)",
        "model": "VARCHAR(128)",
        "glass_type": "VARCHAR(64)",
        "recipe_id": f"VARCHAR({RECIPE_LEN})",
        "ai_code_1": "VARCHAR(64)",
    }

    for col, target_type in PK_COLUMNS.items():
        if col in cols:
            dt = col_types.get(col, "")
            if any(x in dt for x in ["text", "blob"]):
                alters.append(f"MODIFY COLUMN `{col}` {target_type} NOT NULL")

    # 檢查目前是否已有 PRIMARY KEY
    has_pk = has_primary_key(engine, db, t)

    # 只要「有 schema 變更」或「目前沒有 PK」，就組 ALTER TABLE
    if alters or not has_pk:
        if has_pk:
            alters.insert(0, "DROP PRIMARY KEY")

        alters.append(
            "ADD PRIMARY KEY (pi_hour, aoi, line_id, model, glass_type, recipe_id, ai_code_1)"
        )

        alt_sql = f"ALTER TABLE `{db}`.`{t}` " + ", ".join(alters) + ";"

        with engine.begin() as conn:
            # 清理舊索引（若存在）
            if index_exists(engine, db, t, "idx_comment_hash"):
                conn.execute(text(f"ALTER TABLE `{db}`.`{t}` DROP INDEX idx_comment_hash"))

            logging.info(f"[ensure] {t} schema alter: {alt_sql}")
            conn.execute(text(alt_sql))

    # 確保必要索引存在
    with engine.begin() as conn:
        if not index_exists(engine, db, t, "idx_pi_hour"):
            conn.execute(text(f"ALTER TABLE `{db}`.`{t}` ADD INDEX idx_pi_hour (pi_hour)"))
        if not index_exists(engine, db, t, "idx_model"):
            conn.execute(text(f"ALTER TABLE `{db}`.`{t}` ADD INDEX idx_model (model)"))
        if not index_exists(engine, db, t, "idx_recipe"):
            conn.execute(text(f"ALTER TABLE `{db}`.`{t}` ADD INDEX idx_recipe (recipe_id)"))
        if not index_exists(engine, db, t, "idx_line"):
            conn.execute(text(f"ALTER TABLE `{db}`.`{t}` ADD INDEX idx_line (line_id)"))

    return t
# =========================
# RAW 表名處理
# =========================
def parse_pidensity_table(t: str) -> Optional[Tuple[str, str, str]]:
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

# =========================
# Query 片段
# =========================
CASE_BUCKET_SQL = """
CASE
  WHEN TRIM(defect_size) REGEXP '^[0-9]+$' THEN
    CASE
      WHEN CAST(defect_size AS SIGNED) >= 401 THEN 'o'
      WHEN CAST(defect_size AS SIGNED) BETWEEN 101 AND 400 THEN 'l'
      WHEN CAST(defect_size AS SIGNED) BETWEEN 21  AND 100 THEN 'm'
      WHEN CAST(defect_size AS SIGNED) BETWEEN 0   AND 20  THEN 's'
      ELSE NULL
    END
  ELSE NULL
END
"""

def primary_not_null_filter(alias: str = "B") -> str:
    """
    必填鍵（去掉 recipe_comment / pic_path）：
    必填：scan_time、pi_time；文字必填：line_id/model/glass_type/recipe_id
    """
    text_cols = ["line_id", "model", "glass_type", "recipe_id"]
    parts = [f"{alias}.scan_time IS NOT NULL", f"{alias}.pi_time IS NOT NULL"]
    for c in text_cols:
        parts.append(
            f"{alias}.{c} IS NOT NULL AND "
            f"NULLIF(TRIM({alias}.{c}), '') IS NOT NULL AND "
            f"UPPER(TRIM({alias}.{c})) NOT IN ('NAN','NONE','NULL')"
        )
    return " AND ".join(parts)

# 子查詢：把 pi_hour 派生出來 + 清洗欄位
BASE_SUBQUERY = lambda db, raw, recipe_len: f"""
    SELECT
      scan_time,
      pi_time,
      CAST(DATE_FORMAT(pi_time, '%Y-%m-%d %H:00:00') AS DATETIME) AS pi_hour,
      line_id,
      model,
      glass_type,
      LEFT(recipe_id, {recipe_len}) AS recipe_id,
      glass_id,
      TRIM(ai_code_1)   AS ai_code_1,
      TRIM(defect_size) AS defect_size,
      COALESCE(NULLIF(TRIM(pic_path), ''), '') AS pic_path
    FROM `{db}`.`{raw}` AS B
    WHERE {primary_not_null_filter('B')}
"""

# =========================
# 小計工具
# =========================
def _shorten(s: Optional[str], maxlen: int = 120) -> str:
    if s is None:
        return ""
    s = str(s)
    return s if len(s) <= maxlen else (s[:maxlen-3] + "...")

def minutes_before(ts_str: str, minutes: int) -> str:
    dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    return (dt - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")

# =========================
# Upsert：單一 RAW → 月表
# =========================
def upsert_single_raw_into_monthly_summary(engine, db: str, raw_table: str,
                                           aoi_raw: str, yyyymm: str,
                                           window_from: Optional[str] = None) -> Dict[str, int]:
    """
    回傳簡要統計：{'total_raw':..., 'after_clean':..., 'main_groups':..., 'main_ai_groups':..., 'added_rows':...}
    """
    t = ensure_monthly_summary_table(engine, db, yyyymm)
    aoi_std = aoi_raw.lower()
    base_sql = BASE_SUBQUERY(db, raw_table, RECIPE_LEN)

    # 視窗條件
    time_filter_B = "WHERE B.pi_time >= :window_from" if window_from else ""
    time_filter_L = "WHERE L.pi_time >= :window_from" if window_from else ""

    # 寫入 SQL（以派生 pi_hour 為唯一時間粒度；分母用 glass_id 聯集）
    sql = f"""
    INSERT INTO `{db}`.`{t}`
      (pi_hour, aoi, line_id, model, glass_type, recipe_id, ai_code_1,
       maingroup_glass_count, maingroup_defect_count,
       defect_code_glass_count, defect_code_count,
       small_defect_count, middle_defect_count, large_defect_count, over_defect_count,
       glass, pic_paths, comment)
    SELECT
       L.pi_hour,
       :aoi AS aoi,
       L.line_id, L.model, L.glass_type, L.recipe_id,
       L.ai_code_1_clean AS ai_code_1,

       M.maingroup_glass_count,
       M.maingroup_defect_count,

       COUNT(DISTINCT CONCAT(
         DATE_FORMAT(L.pi_time, '%Y-%m-%d %H:%i:%s'), '#', COALESCE(L.glass_id, '')
       )) AS defect_code_glass_count,

       COUNT(*) AS defect_code_count,

       SUM(CASE WHEN L.size_bucket='s' THEN 1 ELSE 0 END) AS small_defect_count,
       SUM(CASE WHEN L.size_bucket='m' THEN 1 ELSE 0 END) AS middle_defect_count,
       SUM(CASE WHEN L.size_bucket='l' THEN 1 ELSE 0 END) AS large_defect_count,
       SUM(CASE WHEN L.size_bucket='o' THEN 1 ELSE 0 END) AS over_defect_count,

       GROUP_CONCAT(DISTINCT NULLIF(TRIM(L.glass_id), '') ORDER BY L.glass_id SEPARATOR ',') AS glass,
       GROUP_CONCAT(DISTINCT NULLIF(TRIM(L.pic_path), '') ORDER BY L.pic_path SEPARATOR ',') AS pic_paths,
       NULL AS comment
    FROM (
        SELECT
          B.scan_time, B.pi_time, B.pi_hour, B.line_id, B.model, B.glass_type,
          B.recipe_id, B.pic_path, B.glass_id,
          {CASE_BUCKET_SQL} AS size_bucket,
          COALESCE(NULLIF(TRIM(B.ai_code_1), ''), '') AS ai_code_1_clean
        FROM (
          {base_sql}
        ) AS B
        {time_filter_B}
    ) AS L
    JOIN (
        SELECT
          B.pi_hour, B.line_id, B.model, B.glass_type, B.recipe_id,
          COUNT(*) AS maingroup_defect_count,
          COUNT(DISTINCT CONCAT(
            DATE_FORMAT(B.pi_time, '%Y-%m-%d %H:%i:%s'), '#', COALESCE(B.glass_id, '')
          )) AS maingroup_glass_count
        FROM (
          {base_sql}
        ) AS B
        {time_filter_B}
        GROUP BY B.pi_hour, B.line_id, B.model, B.glass_type, B.recipe_id
    ) AS M
      ON L.pi_hour    = M.pi_hour
     AND L.line_id    = M.line_id
     AND L.model      = M.model
     AND L.glass_type = M.glass_type
     AND L.recipe_id  = M.recipe_id
    GROUP BY
      L.pi_hour, L.line_id, L.model, L.glass_type, L.recipe_id, L.ai_code_1_clean
    ON DUPLICATE KEY UPDATE
      maingroup_glass_count   = VALUES(maingroup_glass_count),
      maingroup_defect_count  = VALUES(maingroup_defect_count),
      defect_code_glass_count = VALUES(defect_code_glass_count),
      defect_code_count       = VALUES(defect_code_count),
      small_defect_count      = VALUES(small_defect_count),
      middle_defect_count     = VALUES(middle_defect_count),
      large_defect_count      = VALUES(large_defect_count),
      over_defect_count       = VALUES(over_defect_count),
      glass                   = VALUES(glass),
      pic_paths               = VALUES(pic_paths);
    """

    stats = {"total_raw": 0, "after_clean": 0, "main_groups": 0, "main_ai_groups": 0, "added_rows": 0}

    with engine.begin() as conn:
        conn.execute(text(f"SET SESSION group_concat_max_len = {GROUP_CONCAT_MAX_LEN}"))

        params = {"aoi": aoi_std}
        if window_from:
            params["window_from"] = window_from

        # 1) RAW 總筆數（不過濾）
        (total_raw,) = conn.execute(text(f"SELECT COUNT(*) FROM `{db}`.`{raw_table}`")).fetchone()
        stats["total_raw"] = int(total_raw)

        # 2) 清理後（必填鍵 + 視窗）
        q_after_clean = f"SELECT COUNT(*) FROM ({base_sql}) AS B {time_filter_B.replace('B.', '')}"
        (after_clean,) = conn.execute(text(q_after_clean), params).fetchone()
        stats["after_clean"] = int(after_clean)

        # 3) 主分群數（不含 ai）+ 含 ai 的分群數
        q_main = f"""
          SELECT COUNT(*) FROM (
            SELECT B.pi_hour, B.line_id, B.model, B.glass_type, B.recipe_id
            FROM ({base_sql}) AS B
            {time_filter_B}
            GROUP BY B.pi_hour, B.line_id, B.model, B.glass_type, B.recipe_id
          ) X
        """
        (main_groups,) = conn.execute(text(q_main), params).fetchone()
        stats["main_groups"] = int(main_groups)

        q_main_ai = f"""
          SELECT COUNT(*) FROM (
            SELECT B.pi_hour, B.line_id, B.model, B.glass_type, B.recipe_id, COALESCE(NULLIF(TRIM(B.ai_code_1),''),'') AS ai_code_1
            FROM ({base_sql}) AS B
            {time_filter_B}
            GROUP BY B.pi_hour, B.line_id, B.model, B.glass_type, B.recipe_id, ai_code_1
          ) X
        """
        (main_ai_groups,) = conn.execute(text(q_main_ai), params).fetchone()
        stats["main_ai_groups"] = int(main_ai_groups)

        # 4) 每個主分群的最新 pi_hour（預設列前 N 組）
        q_latest = f"""
          SELECT B.line_id, B.model, B.glass_type, B.recipe_id, MAX(B.pi_hour) AS latest_h
          FROM ({base_sql}) AS B
          {time_filter_B}
          GROUP BY B.line_id, B.model, B.glass_type, B.recipe_id
          ORDER BY latest_h DESC
          LIMIT {max(0, DEBUG_GROUP_MAX)}
        """
        latest_rows = conn.execute(text(q_latest), params).fetchall()
        if latest_rows:
            for r in latest_rows:
                line_id, model, glass_type, recipe_id, latest_h = r
                logging.info(f"[latest] {line_id} | {model} | {glass_type} | {recipe_id} → { _fmt_ts(latest_h) }")

        # 5) 本次 sweep 寫入前/後的 summary 筆數（估新增量）
        where = []
        p2: Dict[str, object] = {"aoi": aoi_std}
        if window_from:
            where.append("pi_hour >= :window_from")
            p2["window_from"] = window_from
        clause = ("WHERE aoi=:aoi AND " + " AND ".join(where)) if where else "WHERE aoi=:aoi"

        (before_cnt,) = conn.execute(text(f"SELECT COUNT(*) FROM `{db}`.`{t}` {clause}"), p2).fetchone()
        conn.execute(text(sql), params)  # 寫入
        (after_cnt,) = conn.execute(text(f"SELECT COUNT(*) FROM `{db}`.`{t}` {clause}"), p2).fetchone()
        stats["added_rows"] = max(0, int(after_cnt) - int(before_cnt))

    return stats

# =========================
# 月度刷新
# =========================
def get_summary_max_pi_hour(engine, db: str, yyyymm: str, aoi: str) -> Optional[str]:
    t = f"{SUMMARY_PREFIX}_{yyyymm}"
    if not table_exists(engine, db, t):
        return None
    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT MAX(pi_hour) FROM `{db}`.`{t}` WHERE aoi=:aoi"),
            {"aoi": aoi.lower()},
        ).fetchone()
    return None if (not row or row[0] is None) else row[0].strftime("%Y-%m-%d %H:%M:%S")

def summary_row_count(engine, db: str, yyyymm: str, aoi: Optional[str] = None,
                      window_from: Optional[str] = None) -> int:
    yyyymm = _sanitize_yyyymm(yyyymm)
    t = f"{SUMMARY_PREFIX}_{yyyymm}"
    if not table_exists(engine, db, t):
        return 0
    where = []
    params: Dict[str, object] = {"db": db, "t": t}
    if aoi:
        where.append("aoi=:aoi")
        params["aoi"] = aoi.lower()
    if window_from:
        where.append("pi_hour >= :window_from")
        params["window_from"] = window_from
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    with engine.connect() as conn:
        (cnt,) = conn.execute(text(f"SELECT COUNT(*) FROM `{db}`.`{t}` {clause}"), params).fetchone()
    return int(cnt)

def minutes_before(ts_str: str, minutes: int) -> str:
    dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    return (dt - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")

def refresh_month(engine, db: str, yyyymm: str,
                  live_window_from: Optional[datetime] = None,
                  force_full_month: bool = False) -> int:
    yyyymm = _sanitize_yyyymm(yyyymm)
    sources = list_pidensity_tables(engine, db, yyyymm=yyyymm)
    if not sources:
        logging.info(f"[refresh_month] 該月無來源表：{yyyymm}")
        return 0

    total_added = 0
    fallback_from = live_window_from.strftime("%Y-%m-%d %H:%M:%S") if live_window_from else None
    month_begin = f"{yyyymm[:4]}-{yyyymm[4:]}-01 00:00:00"

    # 重要：若 force_full_month=True，整輪都固定月初；否則才依 last_max 動態退回
    for raw in sorted(sources):
        parsed = parse_pidensity_table(raw)
        if not parsed:
            continue
        aoi_raw, mm, _pi = parsed

        if force_full_month:
            sweep_from = month_begin
        else:
            last_max = get_summary_max_pi_hour(engine, db, yyyymm, aoi_raw)
            backfill_from = minutes_before(last_max, CUSHION_MIN) if last_max else month_begin
            sweep_from = min(backfill_from, fallback_from) if fallback_from else backfill_from

        before = summary_row_count(engine, db, yyyymm, aoi=aoi_raw, window_from=sweep_from)
        try:
            stats = upsert_single_raw_into_monthly_summary(engine, db, raw, aoi_raw, yyyymm, window_from=sweep_from)
        except SQLAlchemyError as e:
            logging.exception(f"[refresh_month] 處理 {raw} 失敗：{e}")
            continue
        after = summary_row_count(engine, db, yyyymm, aoi=aoi_raw, window_from=sweep_from)
        added = max(0, after - before)
        total_added += added

        logging.info(
            "[merge] src=%s | aoi=%s | sweep_from=%s | total_raw=%d | after_clean=%d | main_groups=%d | main_ai_groups=%d | added_rows=%d (after=%d)",
            raw, aoi_raw.lower(), sweep_from,
            stats.get("total_raw", 0), stats.get("after_clean", 0),
            stats.get("main_groups", 0), stats.get("main_ai_groups", 0),
            stats.get("added_rows", 0), after
        )

    logging.info(f"[refresh_month] {yyyymm} 合計新增摘要列數(估) = {total_added}")
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
    for _ in rows:
        pass  # 需要時自行打開

# =========================
# Main
# =========================
def main():
    engine = get_engine(DB_NAME)

    prefer = os.getenv("RAW_TABLE")
    target_yyyymm = os.getenv("TARGET_YYYYMM")
    now = datetime.now()

    if prefer:
        parsed = parse_pidensity_table(prefer)
        if not parsed:
            raise ValueError(f"來源表名不符合規則：{prefer}")
        aoi_raw, yyyymm, _pi = parsed
        yyyymm = _sanitize_yyyymm(yyyymm)
        logging.info(f"[run:single] 來源表={prefer} | aoi={aoi_raw} | yyyymm={yyyymm}")

        ensure_monthly_summary_table(engine, DB_NAME, yyyymm)
        before = summary_row_count(engine, DB_NAME, yyyymm, aoi=aoi_raw)
        stats = upsert_single_raw_into_monthly_summary(engine, DB_NAME, prefer, aoi_raw, yyyymm, window_from=None)
        after = summary_row_count(engine, DB_NAME, yyyymm, aoi=aoi_raw)

        logging.info(
            "[run:single] total_raw=%d | after_clean=%d | main_groups=%d | main_ai_groups=%d | added_rows=%d (before=%d, after=%d)",
            stats.get("total_raw", 0), stats.get("after_clean", 0),
            stats.get("main_groups", 0), stats.get("main_ai_groups", 0),
            stats.get("added_rows", 0), before, after
        )
        print_table_schema(engine, DB_NAME, f"{SUMMARY_PREFIX}_{yyyymm}")
        return

    if target_yyyymm:
        target_yyyymm = _sanitize_yyyymm(target_yyyymm)
        logging.info(f"[run:month] 目標月份={target_yyyymm}（整月）")
        ensure_monthly_summary_table(engine, DB_NAME, target_yyyymm)
        # 固定整月都從 1 號 00:00 跑
        refresh_month(engine, DB_NAME, target_yyyymm, live_window_from=None, force_full_month=True)
        print_table_schema(engine, DB_NAME, f"{SUMMARY_PREFIX}_{target_yyyymm}")
        return

    current_yyyymm = now.strftime("%Y%m")
    live_from = now - timedelta(minutes=LIVE_WINDOW_MIN)
    logging.info(f"[run:live] 當月={current_yyyymm} | 僅處理最近 {LIVE_WINDOW_MIN} 分鐘（pi_time >= {live_from:%Y-%m-%d %H:%M:%S}）")
    ensure_monthly_summary_table(engine, DB_NAME, current_yyyymm)
    refresh_month(engine, DB_NAME, current_yyyymm, live_window_from=live_from)
    print_table_schema(engine, DB_NAME, f"{SUMMARY_PREFIX}_{current_yyyymm}")

if __name__ == "__main__":
    try:
        main()
    except SQLAlchemyError as e:
        logging.exception(f"DB Error: {e}")
    except Exception as e:
        logging.exception(f"Unhandled Error: {e}")


"""
# 單表（驗證）
RAW_TABLE=aoi100_pidensity_202511_pi100 python pidenisty_pihour_job.py

# 指定 2025-11 整月重算
TARGET_YYYYMM=202511 python pidenisty_pihour_job.py

# 預設：當月 + 最近 60 分鐘
python pidenisty_pihour_job.py

# 調整即時視窗（例如 30 分鐘）
LIVE_WINDOW_MIN=30 python pidenisty_pihour_job.py
"""
