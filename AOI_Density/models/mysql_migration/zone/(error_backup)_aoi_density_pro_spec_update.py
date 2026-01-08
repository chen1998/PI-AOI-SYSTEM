
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
每日規格值計算（90 天滾動視窗）
- 從「最近 LOOKBACK_DAYS（預設 90 天）」涵蓋到的 PIDENSITY_YYYYMM 表，以 pi_hour 篩選日期區間
- 計算各群組（line_id, aoi, model, ai_code_1）的 density 規格：
  * density = n_rows / n_glasses（逐列）
  * 先計第一次平均 m1，剔除所有 > 3×m1 的值，再以剩餘值計算 AVG/STD，
    OOC = AVG + 3*STD，OOS = AVG + 6*STD（皆四捨五入 1 位）
- 寫入：
  (1) spec_pro_update__table      —— 最新快照（僅 upsert 本批群組）
  (2) spec_pro_update_history     —— 歷史（run_date 維度；PK 含 run_date+group）
      * months_used 欄位：存此次 90 天視窗「起始日」的 yymmdd（例如 251018）
環境變數可調：
  DB_HOST, DB_USER, DB_PASS, DB_NAME
  LOOKBACK_DAYS=90
  RUN_TZ=Asia/Taipei
  DEFECT_CODES=Polymer,SSIU_Polymer,PI_Spot_NP,PIS With Particle
"""

import os
import logging
from datetime import datetime, date, timedelta
from typing import Optional, Tuple, List, Dict, Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# -------- Logging --------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(funcName)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ====== 可調參數（環境變數）======
DB_HOST = os.getenv("DB_HOST", "10.97.142.217")
DB_USER = os.getenv("DB_USER", "l6a01_user")
DB_PASS = os.getenv("DB_PASS", "l6a01$user")
DB_NAME = os.getenv("DB_NAME", "l6a01_project")

LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "90"))
RUN_TZ = os.getenv("RUN_TZ", "Asia/Taipei")

DEFECT_CODES = [
    s.strip() for s in os.getenv(
        "DEFECT_CODES",
        "Polymer,SSIU_Polymer,PI_Spot_NP,PIS With Particle"
    ).split(",")
    if s.strip()
]

SNAPSHOT_TBL = "spec_pro_update__table"
HISTORY_TBL  = "spec_pro_update_history"

# ====== DB helpers ======
def get_engine(dbname: str):
    url = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}/{dbname}?charset=utf8mb4"
    return create_engine(url, pool_pre_ping=True, pool_recycle=3600)

def table_exists(engine, db: str, table: str) -> bool:
    sql = """
    SELECT 1 FROM information_schema.tables
    WHERE table_schema=:db AND table_name=:t
    LIMIT 1
    """
    with engine.connect() as conn:
        return conn.execute(text(sql), {"db": db, "t": table}).fetchone() is not None

def ensure_snapshot_table(engine, db: str, table: str = SNAPSHOT_TBL) -> str:
    """快照表（最新規格）—— 不動 schema 僅確保存在"""
    if table_exists(engine, db, table):
        return table
    sql = f"""
    CREATE TABLE `{db}`.`{table}` (
        pi_line     VARCHAR(32)  NOT NULL,
        aoi         VARCHAR(8)   NOT NULL,
        model       VARCHAR(128) NOT NULL,
        defect_code VARCHAR(64)  NOT NULL,
        glass_side  VARCHAR(32)  NOT NULL,
        avg         FLOAT NULL,
        std         FLOAT NULL,
        ooc         FLOAT NULL,
        oos         FLOAT NULL,
        row_num     INT NULL,
        updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                                  ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (pi_line, aoi, model, defect_code, glass_side),
        INDEX idx_model (model)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    with engine.begin() as conn:
        conn.execute(text(sql))
    logging.info(f"[ensure] created {table}")
    return table

def ensure_history_table(engine, db: str, table: str = HISTORY_TBL) -> str:
    """歷史表（每日一筆／每群組；months_used 存 yymmdd 起始日字串）"""
    if table_exists(engine, db, table):
        return table
    sql = f"""
    CREATE TABLE `{db}`.`{table}` (
        run_date    DATE NOT NULL,
        run_ts      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        pi_line     VARCHAR(32)  NOT NULL,
        aoi         VARCHAR(8)   NOT NULL,
        model       VARCHAR(128) NOT NULL,
        defect_code VARCHAR(64)  NOT NULL,
        glass_side  VARCHAR(32)  NOT NULL,
        avg         FLOAT NULL,
        std         FLOAT NULL,
        ooc         FLOAT NULL,
        oos         FLOAT NULL,
        row_num     INT NULL,
        months_used VARCHAR(16) NULL,   -- 這裡存 yymmdd 起始日，例如 '251018'
        PRIMARY KEY (run_date, pi_line, aoi, model, defect_code, glass_side),
        INDEX idx_group (pi_line, aoi, model, defect_code, glass_side),
        INDEX idx_model (model)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    with engine.begin() as conn:
        conn.execute(text(sql))
    logging.info(f"[ensure] created {table}")
    return table

# ====== 日期工具 ======
def calc_window(now_tz: datetime, lookback_days: int) -> Tuple[date, date, datetime, datetime, str]:
    """
    回傳：
      start_d: 視窗起始「日期」(含) —— 近 lookback_days 天的第一天
      end_d  : 視窗結束「日期」(含) —— 今天（依 RUN_TZ）
      start_dt: 當地時區的起始時間 00:00:00（丟 DB 用時轉 naive）
      end_dt  : 當地時區的隔日 00:00:00（SQL 用 < end_dt）
      yymmdd  : 起始日的 yymmdd 字串
    """
    end_d = now_tz.date()
    # 含今日共計 lookback_days 天 → 起始日 = 今天 - (lookback_days - 1)
    start_d = end_d - timedelta(days=max(1, lookback_days) - 1)
    start_dt = datetime(start_d.year, start_d.month, start_d.day, 0, 0, 0, tzinfo=now_tz.tzinfo)
    end_dt   = datetime(end_d.year, end_d.month, end_d.day, 0, 0, 0, tzinfo=now_tz.tzinfo) + timedelta(days=1)
    yymmdd = start_d.strftime("%y%m%d")
    return start_d, end_d, start_dt, end_dt, yymmdd

def months_covering(start_d: date, end_d: date) -> List[str]:
    """給 90 天區間，回傳會用到的 YYYYMM 清單（用來決定要查哪些月表）"""
    y, m = start_d.year, start_d.month
    out = set()
    cur = date(y, m, 1)
    while cur <= end_d:
        out.add(f"{cur.year}{cur.month:02d}")
        # 下個月
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return sorted(out)

# ====== 資料抓取（依日期區間）======
def fetch_pidensity_by_daterange(engine, db: str, start_dt: datetime, end_dt: datetime,
                                 months: List[str]) -> pd.DataFrame:
    """
    從涵蓋月份的 PIDENSITY_YYYYMM 表拉資料，並用 pi_hour 做日期篩選（[start_dt, end_dt)）。
    注意：MySQL DATETIME 為 naive；丟參數時用 naive。
    """
    cols = "pi_hour, aoi, line_id, model, glass_type, ai_code_1, n_rows, n_glasses"
    dfs: List[pd.DataFrame] = []
    # 轉成 naive（去掉 tzinfo）
    _start = start_dt.replace(tzinfo=None)
    _end   = end_dt.replace(tzinfo=None)
    with engine.connect() as conn:
        for mm in months:
            t = f"PIDENSITY_{mm}"
            if not table_exists(engine, db, t):
                logging.info(f"[fetch] skip missing table {t}")
                continue
            sql = text(f"SELECT {cols} FROM `{db}`.`{t}` WHERE pi_hour >= :s AND pi_hour < :e")
            df = pd.read_sql(sql, conn, params={"s": _start, "e": _end})
            if not df.empty:
                dfs.append(df)
    if not dfs:
        return pd.DataFrame(columns=[
            "pi_hour","aoi","line_id","model","glass_type",
            "ai_code_1","n_rows","n_glasses"
        ])
    return pd.concat(dfs, ignore_index=True)

# ====== 強健統計（先算一次平均後剔除 > 3×平均）======
def robust_density_stats(series: pd.Series, trim_mult: float = 3.0) -> Tuple[float, float, float, float]:
    s = pd.to_numeric(series, errors='coerce').replace([np.inf, -np.inf], np.nan).dropna()
    if s.empty:
        return (0.0, 0.0, 0.0, 0.0)
    m1 = float(s.mean())
    if m1 > 0:
        thresh = trim_mult * m1
        s2 = s[s <= thresh]
        if s2.empty:
            s2 = s
    else:
        s2 = s
    mean = float(s2.mean())
    std  = float(s2.std(ddof=1))
    if np.isnan(std):
        std = 0.0
    ooc = mean + 3.0 * std
    oos = mean + 6.0 * std
    return (round(mean, 1), round(std, 1), round(ooc, 1), round(oos, 1))

# ====== 規格計算 ======
def compute_spec_dataframe(df: pd.DataFrame, defect_codes: List[str]) -> pd.DataFrame:
    """
    以 90 天資料計算：各群組（all + glass_side）規格 DataFrame。
    欄位：pi_line,aoi,model,defect_code,glass_side,avg,std,ooc,oos,row_num
    """
    if df.empty:
        return pd.DataFrame(columns=[
            "pi_line","aoi","model","defect_code","glass_side","avg","std","ooc","oos","row_num"
        ])

    df = df[df["ai_code_1"].isin(defect_codes)].copy()
    if df.empty:
        return pd.DataFrame(columns=[
            "pi_line","aoi","model","defect_code","glass_side","avg","std","ooc","oos","row_num"
        ])

    df = df[pd.to_numeric(df["n_glasses"], errors="coerce").fillna(0) > 0].copy()
    if df.empty:
        return pd.DataFrame(columns=[
            "pi_line","aoi","model","defect_code","glass_side","avg","std","ooc","oos","row_num"
        ])

    df["n_rows"]    = pd.to_numeric(df["n_rows"], errors="coerce")
    df["n_glasses"] = pd.to_numeric(df["n_glasses"], errors="coerce")
    df["density"]   = df["n_rows"] / df["n_glasses"]

    out_rows: List[Dict[str, Any]] = []
    gkeys = ["line_id", "aoi", "model", "ai_code_1"]

    for (line, aoi, model, code), g in df.groupby(gkeys, dropna=False):
        avg, std, ooc, oos = robust_density_stats(g["density"])
        out_rows.append({
            "pi_line": str(line),
            "aoi": str(aoi),
            "model": str(model),
            "defect_code": str(code),
            "glass_side": "all",
            "avg": avg, "std": std, "ooc": ooc, "oos": oos,
            "row_num": int(len(g))
        })
        for side, sg in g.groupby("glass_type", dropna=False):
            side_name = (str(side).strip() if pd.notna(side) and str(side).strip() else "UNK")
            avg, std, ooc, oos = robust_density_stats(sg["density"])
            out_rows.append({
                "pi_line": str(line),
                "aoi": str(aoi),
                "model": str(model),
                "defect_code": str(code),
                "glass_side": side_name,
                "avg": avg, "std": std, "ooc": ooc, "oos": oos,
                "row_num": int(len(sg))
            })

    return pd.DataFrame(out_rows, columns=[
        "pi_line","aoi","model","defect_code","glass_side","avg","std","ooc","oos","row_num"
    ])

# ====== 寫入（快照 + 歷史）======
def upsert_snapshot(engine, db: str, rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    ensure_snapshot_table(engine, db, SNAPSHOT_TBL)
    sql = f"""
    INSERT INTO `{db}`.`{SNAPSHOT_TBL}`
      (pi_line, aoi, model, defect_code, glass_side, avg, std, ooc, oos, row_num)
    VALUES
      (:pi_line, :aoi, :model, :defect_code, :glass_side, :avg, :std, :ooc, :oos, :row_num)
    ON DUPLICATE KEY UPDATE
      avg=VALUES(avg),
      std=VALUES(std),
      ooc=VALUES(ooc),
      oos=VALUES(oos),
      row_num=VALUES(row_num),
      updated_at=NOW();
    """
    with engine.begin() as conn:
        conn.execute(text(sql), rows)
    return len(rows)

def upsert_history(engine, db: str, run_date: date, yymmdd_start: str,
                   rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    ensure_history_table(engine, db, HISTORY_TBL)
    payload = []
    for r in rows:
        rr = dict(r)
        rr["run_date"] = run_date.isoformat()
        rr["months_used"] = yymmdd_start  # ← 90 天視窗起始日（yymmdd）
        payload.append(rr)

    sql = f"""
    INSERT INTO `{db}`.`{HISTORY_TBL}`
      (run_date, pi_line, aoi, model, defect_code, glass_side,
       avg, std, ooc, oos, row_num, months_used)
    VALUES
      (:run_date, :pi_line, :aoi, :model, :defect_code, :glass_side,
       :avg, :std, :ooc, :oos, :row_num, :months_used)
    ON DUPLICATE KEY UPDATE
      avg=VALUES(avg),
      std=VALUES(std),
      ooc=VALUES(ooc),
      oos=VALUES(oos),
      row_num=VALUES(row_num),
      months_used=VALUES(months_used),
      run_ts=CURRENT_TIMESTAMP;
    """
    with engine.begin() as conn:
        conn.execute(text(sql), payload)
    return len(rows)

# ====== 主控 ======
def main():
    tz = ZoneInfo(RUN_TZ)
    now = datetime.now(tz)
    run_date = now.date()

    start_d, end_d, start_dt, end_dt, yymmdd_start = calc_window(now, LOOKBACK_DAYS)
    months = months_covering(start_d, end_d)
    logging.info(f"[run] run_date={run_date} window=[{start_d} ~ {end_d}] months={months} yymmdd_start={yymmdd_start}")

    engine = get_engine(DB_NAME)
    df = fetch_pidensity_by_daterange(engine, DB_NAME, start_dt, end_dt, months)
    if df.empty:
        logging.info("[run] no PIDENSITY rows in window; nothing to update.")
        return

    spec_df = compute_spec_dataframe(df, DEFECT_CODES)
    if spec_df.empty:
        logging.info("[run] no groups match DEFECT_CODES; nothing to update.")
        return

    rows = spec_df.to_dict(orient="records")
    n1 = upsert_snapshot(engine, DB_NAME, rows)
    n2 = upsert_history(engine, DB_NAME, run_date, yymmdd_start, rows)
    logging.info(f"[done] snapshot_upserted={n1}, history_upserted={n2}")

if __name__ == "__main__":
    try:
        main()
    except SQLAlchemyError as e:
        logging.exception(f"DB Error: {e}")
    except Exception as e:
        logging.exception(f"Unhandled Error: {e}")
