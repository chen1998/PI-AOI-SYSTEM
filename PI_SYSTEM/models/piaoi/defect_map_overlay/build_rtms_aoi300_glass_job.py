#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import pandas as pd
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine


# =========================================================
# Logging
# =========================================================
def setup_logger(log_dir: str = "logs", name: str = "build_rtms_aoi300_glass_job") -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(funcName)s] %(message)s")

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    fh = logging.FileHandler(os.path.join(log_dir, f"{name}.log"), encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


logger = setup_logger()


# =========================================================
# DB
# =========================================================
@dataclass
class DBConfig:
    host: str = "127.0.0.1"
    port: int = 3306
    user: str = "l6a01_user"
    pwd: str = "l6a01$user"
    raw_db: str = "rtms_piaoi_other"

    def make_url(self, dbname: str) -> str:
        return f"mysql+pymysql://{self.user}:{self.pwd}@{self.host}:{self.port}/{dbname}?charset=utf8mb4"


class MySQLDB:
    def __init__(self, dbname: str, cfg: DBConfig):
        self.dbname = dbname
        self.engine: Engine = create_engine(
            cfg.make_url(dbname),
            pool_pre_ping=True,
            pool_recycle=3600,
        )

    def execute(self, sql: str, params: Optional[dict] = None):
        with self.engine.begin() as conn:
            return conn.execute(text(sql), params or {})

    def read_sql(self, sql: str, params: Optional[dict] = None) -> pd.DataFrame:
        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params or {})

    def table_exists(self, table_name: str) -> bool:
        insp = inspect(self.engine)
        return insp.has_table(table_name)


# =========================================================
# DDL
# =========================================================
def ensure_glass_table(db: MySQLDB, table_name: str):
    ddl = f"""
    CREATE TABLE IF NOT EXISTS `{db.dbname}`.`{table_name}` (
        id BIGINT NOT NULL AUTO_INCREMENT,
        sheet_id_chip_id VARCHAR(64) NOT NULL,
        test_time DATETIME NOT NULL,
        recipe_id VARCHAR(255) NULL,
        cst_id VARCHAR(128) NULL,
        line_id VARCHAR(32) NULL,
        aoi VARCHAR(16) NULL,
        model VARCHAR(255) NULL,
        glass_type VARCHAR(64) NULL,
        pi_time DATETIME NULL,
        pi_type VARCHAR(16) NULL,

        defect_count INT NOT NULL DEFAULT 0,
        small_defect_count INT NOT NULL DEFAULT 0,
        middle_defect_count INT NOT NULL DEFAULT 0,
        large_defect_count INT NOT NULL DEFAULT 0,
        over_defect_count INT NOT NULL DEFAULT 0,

        run_day DATETIME NULL,
        update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP,

        PRIMARY KEY (id),
        UNIQUE KEY uk_glass_testtime (sheet_id_chip_id, test_time),
        KEY idx_test_time (test_time),
        KEY idx_aoi (aoi),
        KEY idx_line_id (line_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    db.execute(ddl)

def upsert_glass_df(db: MySQLDB, table_name: str, df: pd.DataFrame):
    if df is None or df.empty:
        logger.info(f"[upsert_glass_df] {table_name}: no rows")
        return

    ensure_glass_table(db, table_name)

    cols = [
        "sheet_id_chip_id", "test_time", "recipe_id", "cst_id", "line_id", "aoi",
        "model", "glass_type", "pi_time", "pi_type",
        "defect_count", "small_defect_count", "middle_defect_count",
        "large_defect_count", "over_defect_count", "run_day"
    ]

    d = df[cols].copy()

    # 先轉 datetime
    for c in ["test_time", "pi_time", "run_day"]:
        d[c] = pd.to_datetime(d[c], errors="coerce")

    # 關鍵：把 pandas Timestamp / NaT 轉成 python datetime / None
    def _to_py_dt(v):
        if pd.isna(v):
            return None
        if isinstance(v, pd.Timestamp):
            return v.to_pydatetime()
        return v

    for c in ["test_time", "pi_time", "run_day"]:
        d[c] = d[c].map(_to_py_dt)

    rows = d.to_dict(orient="records")
    if not rows:
        logger.info(f"[upsert_glass_df] {table_name}: no rows after conversion")
        return

    sql = f"""
    INSERT INTO `{db.dbname}`.`{table_name}` (
        sheet_id_chip_id, test_time, recipe_id, cst_id, line_id, aoi,
        model, glass_type, pi_time, pi_type,
        defect_count, small_defect_count, middle_defect_count,
        large_defect_count, over_defect_count, run_day
    ) VALUES (
        :sheet_id_chip_id, :test_time, :recipe_id, :cst_id, :line_id, :aoi,
        :model, :glass_type, :pi_time, :pi_type,
        :defect_count, :small_defect_count, :middle_defect_count,
        :large_defect_count, :over_defect_count, :run_day
    )
    ON DUPLICATE KEY UPDATE
        recipe_id = VALUES(recipe_id),
        cst_id = VALUES(cst_id),
        line_id = VALUES(line_id),
        aoi = VALUES(aoi),
        model = VALUES(model),
        glass_type = VALUES(glass_type),
        pi_time = VALUES(pi_time),
        pi_type = VALUES(pi_type),
        defect_count = VALUES(defect_count),
        small_defect_count = VALUES(small_defect_count),
        middle_defect_count = VALUES(middle_defect_count),
        large_defect_count = VALUES(large_defect_count),
        over_defect_count = VALUES(over_defect_count),
        run_day = VALUES(run_day)
    """
    with db.engine.begin() as conn:
        conn.execute(text(sql), rows)

    logger.info(f"[upsert_glass_df] {table_name}: upserted {len(rows)} rows")
# =========================================================
# Helpers
# =========================================================
def parse_dt(v: Optional[str]) -> Optional[datetime]:
    if not v:
        return None
    v = str(v).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue
    raise ValueError(f"無法解析日期時間格式: {v}")


def resolve_window(
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
    date_str: Optional[str],
    lookback_min: int,
    lag_min: int,
) -> Tuple[datetime, datetime]:
    if start_dt or end_dt:
        if start_dt is None and end_dt is not None:
            start_dt = end_dt - timedelta(minutes=lookback_min)
        if end_dt is None and start_dt is not None:
            end_dt = start_dt + timedelta(minutes=lookback_min)
        return start_dt, end_dt

    if date_str:
        d = parse_dt(date_str)
        d0 = datetime(d.year, d.month, d.day)
        return d0, d0 + timedelta(days=1)

    now = datetime.now()
    end_dt = now - timedelta(minutes=lag_min)
    start_dt = end_dt - timedelta(minutes=lookback_min)
    return start_dt, end_dt


def month_list_from_range(start_dt: datetime, end_dt: datetime) -> List[str]:
    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt

    out = []
    cur = datetime(start_dt.year, start_dt.month, 1)
    end_m = datetime(end_dt.year, end_dt.month, 1)

    while cur <= end_m:
        out.append(cur.strftime("%Y%m"))
        if cur.month == 12:
            cur = datetime(cur.year + 1, 1, 1)
        else:
            cur = datetime(cur.year, cur.month + 1, 1)
    return out


def raw_table_name(yyyymm: str) -> str:
    return f"rtms_aoi300_raw_{yyyymm}"


def glass_table_name(yyyymm: str) -> str:
    return f"rtms_aoi300_glass_{yyyymm}"


def normalize_size(v) -> str:
    """
    將輸入標準化成 S/M/L/O/OK。

    說明：
    - macro 原點圖 defect_size 會是 OK，應保留為 OK。
    - size_class = 0 也視為 OK。
    - 真實 defect 才分成 S/M/L/O。
    - 無法判斷時回傳空字串，避免被誤算成 S。
    """
    s = str(v or "").strip().upper()

    if s in {"S", "M", "L", "O", "OK"}:
        return s

    if s in {"", "NULL", "NONE", "NAN", "<NA>", "NAT"}:
        return ""

    try:
        n = float(s)
        if n == 0:
            return "OK"
        if n <= 20:
            return "S"
        if n <= 100:
            return "M"
        if n <= 400:
            return "L"
        return "O"
    except Exception:
        return ""
# =========================================================
# Main logic
# =========================================================
def load_raw_rows(
    db: MySQLDB,
    table_name: str,
    start_dt: datetime,
    end_dt: datetime,
) -> pd.DataFrame:
    sql = f"""
    SELECT
        sheet_id_chip_id,
        chip_id,
        test_time,
        defect_size,
        size_class,
        recipe_id,
        cst_id,
        line_id,
        aoi,
        model,
        glass_type,
        pi_time,
        pi_type
    FROM `{db.dbname}`.`{table_name}`
    WHERE test_time >= :start_dt
      AND test_time < :end_dt
    """
    df = db.read_sql(sql, {"start_dt": start_dt, "end_dt": end_dt})
    if df.empty:
        return df

    df["test_time"] = pd.to_datetime(df["test_time"], errors="coerce")
    df["pi_time"] = pd.to_datetime(df["pi_time"], errors="coerce")
    return df


def build_glass_summary(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    對齊新的 rtms_aoi300_raw_job.py：
    - defect_size：存 S/M/L/O 類別
    - size_class：存原始面積數值
    """
    if raw_df is None or raw_df.empty:
        return pd.DataFrame()

    d = raw_df.copy()
    d = d.dropna(subset=["sheet_id_chip_id", "test_time"])

    # 優先使用 defect_size（現在已是 S/M/L/O）
    d["size_norm"] = d["defect_size"].map(normalize_size)

    # 若 defect_size 空，才 fallback 用 size_class 數值分桶
    empty_mask = d["defect_size"].isna() | (d["defect_size"].astype(str).str.strip() == "")
    d.loc[empty_mask, "size_norm"] = d.loc[empty_mask, "size_class"].map(normalize_size)

    grp = d.groupby(["sheet_id_chip_id", "test_time"], dropna=False)

    out = grp.agg(
        recipe_id=("recipe_id", "first"),
        line_id=("line_id", "first"),
        aoi=("aoi", "first"),
        model=("model", "first"),
        glass_type=("glass_type", "first"),
        cst_id=("cst_id", "first"),
        pi_time=("pi_time", "first"),
        pi_type=("pi_type", "first"),
        defect_count=("sheet_id_chip_id", "size"),
        small_defect_count=("size_norm", lambda s: int((s == "S").sum())),
        middle_defect_count=("size_norm", lambda s: int((s == "M").sum())),
        large_defect_count=("size_norm", lambda s: int((s == "L").sum())),
        over_defect_count=("size_norm", lambda s: int((s == "O").sum())),
    ).reset_index()

    out["run_day"] = pd.to_datetime(out["test_time"], errors="coerce").dt.normalize()

    # 保底：避免 None
    out["line_id"] = out["line_id"].fillna("Null")
    out["pi_type"] = out["pi_type"].fillna("Null")
    out["aoi"] = out["aoi"].fillna("aoi300")

    return out


def one_run(
    cfg: DBConfig,
    start_dt: datetime,
    end_dt: datetime,
):
    logger.info(f"[one_run] start_dt={start_dt}, end_dt={end_dt}")

    db = MySQLDB(cfg.raw_db, cfg)
    months = month_list_from_range(start_dt, end_dt)

    for ym in months:
        rt = raw_table_name(ym)
        gt = glass_table_name(ym)

        if not db.table_exists(rt):
            logger.info(f"[one_run] skip raw table not exists: {rt}")
            continue

        df = load_raw_rows(db, rt, start_dt, end_dt)
        if df.empty:
            logger.info(f"[one_run] empty raw rows: {rt}")
            continue

        glass_df = build_glass_summary(df)
        if glass_df.empty:
            logger.info(f"[one_run] empty glass summary: {rt}")
            continue

        upsert_glass_df(db, gt, glass_df)
        logger.info(f"[one_run] upsert {gt}: {len(glass_df)} rows")

    logger.info("[one_run] done")


# =========================================================
# CLI
# =========================================================
def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build RTMS AOI300 glass summary job")

    p.add_argument("--host", type=str, default="127.0.0.1")
    p.add_argument("--port", type=int, default=3306)
    p.add_argument("--user", type=str, default="l6a01_user")
    p.add_argument("--pwd", type=str, default="l6a01$user")
    p.add_argument("--raw-db", type=str, default="rtms_piaoi_other")

    p.add_argument("--once", action="store_true")
    p.add_argument("--every-min", type=int, default=10)
    p.add_argument("--lookback-min", type=int, default=180)
    p.add_argument("--lag-min", type=int, default=2)

    p.add_argument("--start-dt", type=str, default=None)
    p.add_argument("--end-dt", type=str, default=None)
    p.add_argument("--date", type=str, default=None)

    return p


def main():
    args = build_arg_parser().parse_args()

    cfg = DBConfig(
        host=args.host,
        port=args.port,
        user=args.user,
        pwd=args.pwd,
        raw_db=args.raw_db,
    )

    start_dt = parse_dt(args.start_dt)
    end_dt = parse_dt(args.end_dt)

    if args.once:
        sdt, edt = resolve_window(
            start_dt=start_dt,
            end_dt=end_dt,
            date_str=args.date,
            lookback_min=args.lookback_min,
            lag_min=args.lag_min,
        )
        one_run(cfg, sdt, edt)
        return

    every_sec = max(1, args.every_min * 60)
    while True:
        t0 = time.time()
        try:
            sdt, edt = resolve_window(
                start_dt=start_dt,
                end_dt=end_dt,
                date_str=args.date,
                lookback_min=args.lookback_min,
                lag_min=args.lag_min,
            )
            one_run(cfg, sdt, edt)
        except Exception:
            logger.exception("[main] run failed")

        sleep_sec = max(0.0, every_sec - (time.time() - t0))
        time.sleep(sleep_sec)


if __name__ == "__main__":
    main()


"""
# 單次執行：最近 3 小時
python build_rtms_aoi300_glass_job.py --once

# 單次執行：指定區間
python build_rtms_aoi300_glass_job.py --once --start-dt "2026-05-01 00:00:00" --end-dt "2026-05-07 17:25:00"

# 單次執行：指定單日
python build_rtms_aoi300_glass_job.py --once --date 2026-04-14

# 常駐，每 10 分鐘跑一次
python build_rtms_aoi300_glass_job.py
"""