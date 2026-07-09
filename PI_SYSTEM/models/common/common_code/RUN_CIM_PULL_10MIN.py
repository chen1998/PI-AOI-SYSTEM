
# -*- coding: utf-8 -*-
"""
run_cim_pull_10min.py
- 每 N 分鐘增量拉 Oracle CIM (secsheetchip + trans_ods + secdefect) 寫入 MySQL
- Log: txt, UTF-8, 每日切檔，保留近 3 個月
- 支援 --once：跑一次就結束（適合 Windows 工作排程器）

本版改動重點：
1) 用 --every-min 控制每 N 分鐘跑一次（避免 drift）
2) 用 --lookback-min 控制每次只處理最近 R 分鐘內的資料（window-based）
3) secsheetchip 的時間條件固定用 complete_time（不需要在 need_cols 中選出、也不會出現在 df）

#python run_cim_pull_10min.py  --every-min 10 lookback-min 120
python RUN_CIM_PULL_10MIN.py --once --lookback-min 4320
"""

from __future__ import annotations

import os
import sys
import time
import argparse
import logging
from logging.handlers import TimedRotatingFileHandler
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict, Any

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text, inspect
import sys
# 你的 MySQLConnet（需包含 append_or_create_dedup）
from sql_db_connect import MySQLConnet


# =============================================================================
# Logging (txt + UTF-8 + keep 3 months)
# =============================================================================
def setup_logging(log_dir: str = "logs", log_name: str = "cim_pull.txt") -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, log_name)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # 避免重複加 handler（例如被其他 module basicConfig 影響）
    if logger.handlers:
        for h in list(logger.handlers):
            logger.removeHandler(h)

    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # 每日切檔，保留約 3 個月（92 天）
    fh = TimedRotatingFileHandler(
        filename=log_path,
        when="midnight",
        interval=1,
        backupCount=92,
        encoding="utf-8",
        utc=False,
    )
    fh.suffix = "%Y-%m-%d"  # cim_pull.txt.2026-01-26
    fh.setFormatter(fmt)
    fh.setLevel(logging.INFO)

    sh = logging.StreamHandler(stream=sys.stdout)
    sh.setFormatter(fmt)
    sh.setLevel(logging.INFO)

    logger.addHandler(fh)
    logger.addHandler(sh)

    return logger


# =============================================================================
# MySQL watermark state (保留做觀測/追蹤用；本版不靠它推算 start_dt)
# =============================================================================
STATE_JOB = "aoi_cim_pull_window"

def ensure_state_table(sql_db: MySQLConnet):
    ddl = text("""
    CREATE TABLE IF NOT EXISTS cim_pipeline_state (
      job_name VARCHAR(64) PRIMARY KEY,
      last_end_dt DATETIME NULL,
      update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
    )
    """)
    with sql_db.engine.begin() as conn:
        conn.execute(ddl)

def get_last_end_dt(sql_db: MySQLConnet) -> Optional[datetime]:
    sql = text("SELECT last_end_dt FROM cim_pipeline_state WHERE job_name=:job")
    with sql_db.engine.begin() as conn:
        r = conn.execute(sql, {"job": STATE_JOB}).fetchone()
    if not r or r[0] is None:
        return None
    return r[0]

def set_last_end_dt(sql_db: MySQLConnet, end_dt: datetime):
    sql = text("""
    INSERT INTO cim_pipeline_state(job_name, last_end_dt)
    VALUES(:job, :end_dt)
    ON DUPLICATE KEY UPDATE last_end_dt=VALUES(last_end_dt)
    """)
    with sql_db.engine.begin() as conn:
        conn.execute(sql, {"job": STATE_JOB, "end_dt": end_dt})


# =============================================================================
# Oracle config + table config
# =============================================================================
@dataclass
class CIMDB_Config:
    user_name: str = "L6AINT_AP"
    passwd: str = "L6AINT$AP"
    port: str = "1549"
    host: str = "TCPPA104"
    service_name: str = "L6AHSHA"

    # MySQL
    SQL_DBNAME: str = "cim_piaoi"
    CIM_SUMMARY_TB_NAME: str = "cim_pi_glass_yyyymm"
    CIM_DEFECT_TB_NAME: str = "cim_defect_yyyymm_aoi_line"

    @property
    def DATABASE_URL(self) -> str:
        return f"oracle+cx_oracle://{self.user_name}:{self.passwd}@{self.host}:{self.port}/?service_name={self.service_name}"

    @property
    def oracle_cim_table_config(self) -> Dict[str, Dict[str, Any]]:
        return {
            "celaidi.h_aidi_secsheetchip": {
                "need_cols": [
                    "sheet_id_chip_id", "test_time", "model_no", "op_id", "abbr_cat",
                    "recipe_id", "cassette_id", "eqp_id",
                    "total_defect_qty", "defect_size_o_qty", "defect_size_l_qty",
                    "defect_size_m_qty", "defect_size_s_qty"
                ],
                # 注意：本版 fetch_secsheetchip_dt 會固定用 complete_time
                # 所以這裡的 cim_time_col 設不設定都無所謂
                "cim_time_col": "test_time",
            },
            "celaidi.h_aidi_secdefect": {
                "need_cols": [
                    "sheet_id_chip_id", "chip_id", "test_time",
                    "defect_size", "pox_x1", "pox_y1",
                    "image_file_path", "image_file_name","img_file_url_path",
                    "retype_def_code", "adc_def_code",
                    # 若你願意，強烈建議加上 defect_seq_no 作唯一鍵：
                    # "defect_seq_no",
                ],
                "ori_time_column": "test_time",
            },
            "celods.h_chip_trans_ods": {
                "need_cols": [
                    "sheet_id_chip_id", "eqp_id", "trans_timestamp", "op_id", "trans_id"
                ],
                "ori_time_column": "trans_timestamp",
            }
        }


# =============================================================================
# Save functions (MySQL)
# =============================================================================
def ensure_mysql_columns(
    dbhandler: MySQLConnet,
    table_name: str,
    col_defs: Dict[str, str],
) -> None:
    """
    若 table 已存在，檢查並補欄位。
    若 table 不存在，跳過，讓 append_or_create_dedup 建表時直接依 df 欄位建立。
    """
    if not table_name or not col_defs:
        return

    with dbhandler.engine.begin() as conn:
        dbname = conn.execute(text("SELECT DATABASE()")).scalar()

        table_exists = conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = :db
              AND TABLE_NAME = :t
        """), {
            "db": dbname,
            "t": table_name,
        }).scalar()

        if not table_exists:
            return

        for col, ddl in col_defs.items():
            exists = conn.execute(text("""
                SELECT COUNT(*)
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = :db
                  AND TABLE_NAME = :t
                  AND COLUMN_NAME = :c
            """), {
                "db": dbname,
                "t": table_name,
                "c": col,
            }).scalar()

            if not exists:
                logging.info(f"[ensure_column] `{dbname}`.`{table_name}` ADD COLUMN `{col}` {ddl}")
                conn.execute(text(
                    f"ALTER TABLE `{dbname}`.`{table_name}` "
                    f"ADD COLUMN `{col}` {ddl}"
                ))

def save_summary_by_pi_yyyymm(dbhandler: MySQLConnet, base_name: str, df: pd.DataFrame):
    """
    base_name: cim_pi_glass_yyyymm -> cim_pi_glass_202601
    """
    if df is None or df.empty:
        return

    ym_na = datetime.now().strftime("%Y") + "00"
    d = df.copy()
    d["pi_time"] = pd.to_datetime(d.get("pi_time"), errors="coerce")
    d["yyyymm"] = d["pi_time"].dt.strftime("%Y%m").fillna(ym_na)

    for yyyymm, g in d.groupby("yyyymm"):
        tb = base_name.replace("yyyymm", str(yyyymm)).lower()
        g2 = g.drop(columns=["yyyymm"])

        # summary dedup key（同片同 scan 一筆）
        dedup_keys = [c for c in ["sheet_id_chip_id", "test_time"] if c in g2.columns]

        logging.info(f"[save_summary] {tb} append {len(g2)} rows; dedup_keys={dedup_keys}")
        dbhandler.append_or_create_dedup(table_name=tb, df=g2, dedup_keys=dedup_keys)

def save_defect_by_time_aoi_line(dbhandler: MySQLConnet, base_name: str, df: pd.DataFrame):
    """
    base_name: cim_defect_yyyymm_aoi_line -> cim_defect_202601_aoi100_CAPIC300
    yyyymm 取 test_time；aoi / line_id 用 df 欄位
    """
    if df is None or df.empty:
        return

    ym_na = datetime.now().strftime("%Y") + "00"
    d = df.copy()
    d["test_time"] = pd.to_datetime(d.get("test_time"), errors="coerce")
    d["yyyymm"] = d["test_time"].dt.strftime("%Y%m").fillna(ym_na)

    # aoi / line_id 缺失補值
    if "aoi" not in d.columns:
        d["aoi"] = ""
    if "line_id" not in d.columns:
        d["line_id"] = "pi000"

    d["aoi"] = d["aoi"].astype("string").fillna("")
    # aoi 欄位是原始 eqp_id（CAPIT203/CAAOI202/CAAOI300），可映射成 aoi100/200/300
    d["aoi"] = d["aoi"].map({"CAPIT203": "aoi100", "CAAOI202": "aoi200", "CAAOI300": "aoi300"}).fillna("aoi000")
    d["line_id"] = d["line_id"].astype("string").fillna("pi000")
    d.loc[d["line_id"].str.len().fillna(0).eq(0), "line_id"] = "pi000"

    for (yyyymm, aoi, line_id), g in d.groupby(["yyyymm", "aoi", "line_id"], dropna=False):
        tb = base_name.replace("yyyymm", str(yyyymm)).replace("aoi", str(aoi)).replace("line", str(line_id)).lower()
        g2 = g.drop(columns=["yyyymm", "aoi", "line_id"])

        # defect 的 dedup key 建議包含 defect_seq_no（你目前 df 沒有就只能降級）
        if "defect_seq_no" in g2.columns:
            dedup_keys = [
                "sheet_id_chip_id",
                "test_time",
                "chip_id",
                "defect_seq_no",
            ]
        else:
            dedup_keys = [
                c for c in [
                    "sheet_id_chip_id",
                    "test_time",
                    "chip_id",
                    "pox_x1",
                    "pox_y1",
                    "image_file_name",
                ]
                if c in g2.columns
            ]
        if not dedup_keys:
            # 最差情況：用主要欄位 + 座標 + 圖檔名 近似去重
            fallback = ["sheet_id_chip_id", "test_time", "chip_id", "pox_x1", "pox_y1", "image_file_name"]
            dedup_keys = [c for c in fallback if c in g2.columns]

        # 舊表若已存在，要先補 recipe_id 欄位。
        # 新表若不存在，append_or_create_dedup 建表時會直接依 g2 欄位建立。
        ensure_mysql_columns(
            dbhandler,
            tb,
            {
                "recipe_id": "VARCHAR(128) NULL",
            },
        )

        logging.info(f"[save_defect] {tb} append {len(g2)} rows; dedup_keys={dedup_keys}")
        dbhandler.append_or_create_dedup(table_name=tb, df=g2, dedup_keys=dedup_keys)


# =============================================================================
# Pipeline
# =============================================================================
class AOI_CIM_Pipeline:
    def __init__(self, oracle_url: str, oracle_cim_table_config: Dict[str, Dict[str, Any]]):
        self.oracle_url = oracle_url
        self.cfg = oracle_cim_table_config
        self.engine = create_engine(self.oracle_url)  # 필요시 pool_pre_ping=True

    @staticmethod
    def _cols_sql(cols: List[str]) -> str:
        cols = [c.strip() for c in cols if c and str(c).strip()]
        return ", ".join(cols)

    def fetch_secsheetchip_dt(
        self,
        start_dt: datetime,
        end_dt: datetime,
        *,
        eqp_id: Optional[str] = None,
        use_eqp_filter: bool = False,
    ) -> pd.DataFrame:
        """
        重要：時間欄位固定用 complete_time 做 WHERE
        - SELECT 欄位仍只取 need_cols（不包含 complete_time）
        """
        tname = "celaidi.h_aidi_secsheetchip"
        cfg = self.cfg[tname]
        need_cols = cfg.get("need_cols") or cfg.get("columns") or cfg.get("cim_cols")

        time_col = "complete_time"  # ★固定用 complete_time

        where_eqp = ""
        params: Dict[str, Any] = {"start_dt": start_dt, "end_dt": end_dt}

        if use_eqp_filter and eqp_id:
            where_eqp = " AND eqp_id = :eqp_id "
            params["eqp_id"] = eqp_id

        sql = f"""
        SELECT {self._cols_sql(need_cols)}
        FROM {tname}
        WHERE {time_col} >= :start_dt
          AND {time_col} <  :end_dt
          {where_eqp}
        """

        with self.engine.connect() as conn:
            df = pd.read_sql(text(sql), conn, params=params)
        return df

    def fetch_trans_ods_for_glass_ids(
        self,
        glass_ids: List[str],
        *,
        op_like: str = "PI PRINT_%",
        trans_id: str = "LOGF",
        batch_size: int = 900,
    ) -> pd.DataFrame:
        tname = "celods.h_chip_trans_ods"
        cfg = self.cfg[tname]
        time_col = cfg.get("ori_time_column", "trans_timestamp")
        cols = cfg.get("need_cols") or cfg.get("columns") or [
            "sheet_id_chip_id", "eqp_id", time_col, "op_id", "trans_id"
        ]

        if not glass_ids:
            return pd.DataFrame(columns=["glass_id", "line_id", "pi_time"])

        col_sql = self._cols_sql(cols)
        out_chunks: List[pd.DataFrame] = []

        with self.engine.connect() as conn:
            for i in range(0, len(glass_ids), batch_size):
                batch = glass_ids[i:i + batch_size]

                bind_keys = {f"g{j}": v for j, v in enumerate(batch)}
                in_clause = ", ".join([f":g{j}" for j in range(len(batch))])

                sql = f"""
                SELECT {col_sql}
                FROM {tname}
                WHERE sheet_id_chip_id IN ({in_clause})
                AND op_id LIKE :op_like
                AND trans_id = :trans_id
                """
                params = dict(bind_keys)
                params.update({"op_like": op_like, "trans_id": trans_id})

                df = pd.read_sql(text(sql), conn, params=params)
                out_chunks.append(df)

        if not out_chunks:
            return pd.DataFrame(columns=["glass_id", "line_id", "pi_time"])

        df = pd.concat(out_chunks, ignore_index=True)

        df = df.rename(columns={
            "sheet_id_chip_id": "glass_id",
            "eqp_id": "line_id",
            time_col: "pi_time",
        })

        df["glass_id"] = df["glass_id"].astype(str)
        df["pi_time"] = pd.to_datetime(df.get("pi_time"), errors="coerce")

        # 取每片最新一筆 PI PRINT LOGF
        df = df.sort_values(["glass_id", "pi_time"]).drop_duplicates(["glass_id"], keep="last")

        # line_id 若為 NULL / NaN / 空字串，補 pi000
        if "line_id" not in df.columns:
            df["line_id"] = "pi000"

        df["line_id"] = df["line_id"].astype("string").fillna("pi000").str.strip()
        df.loc[df["line_id"].eq(""), "line_id"] = "pi000"

        return df[["glass_id", "line_id", "pi_time"]]


    def build_cim_pi_glass_sdf(self, cim_glass_sdf: pd.DataFrame) -> pd.DataFrame:
        if cim_glass_sdf is None or cim_glass_sdf.empty:
            return pd.DataFrame()

        df = cim_glass_sdf.copy()

        # secsheetchip 的 eqp_id -> aoi（保留原始 eqp_id，後面 save_defect 再映射 aoi100/200/300）
        if "eqp_id" in df.columns:
            df = df.rename(columns={"eqp_id": "aoi"})

        glass_ids = df["sheet_id_chip_id"].dropna().astype(str).unique().tolist()
        trans_df = self.fetch_trans_ods_for_glass_ids(glass_ids)

        df = df.merge(
            trans_df,
            how="left",
            left_on="sheet_id_chip_id",
            right_on="glass_id",
            suffixes=("", "_trans")
        )
        if "glass_id" in df.columns:
            df = df.drop(columns=["glass_id"])

        if "line_id" in df.columns:
            df["line_id"] = df["line_id"].fillna("")
        df["pi_time"] = pd.to_datetime(df.get("pi_time"), errors="coerce")

        return df

    @staticmethod
    def add_pi_hour(df: pd.DataFrame) -> pd.DataFrame:
        """
        新規則：
          pi_hour = (pi_time - 30min).floor("H")
        """
        out = df.copy()
        out["pi_time"] = pd.to_datetime(out.get("pi_time"), errors="coerce")
        out["pi_hour"] = (out["pi_time"] - pd.to_timedelta(30, unit="m")).dt.floor("H")

        try:
            sample = out[["pi_time", "pi_hour"]].dropna()#.head(5)
            logging.info(f"[add_pi_hour] sample=\n{sample.iloc[-5:,:]}")
        except Exception:
            pass

        return out

    @staticmethod
    def add_pi_type(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        for col in ["aoi", "recipe_id", "test_time", "pi_time"]:
            if col not in out.columns:
                out[col] = None

        scantime = pd.to_datetime(out["test_time"], errors="coerce")
        pitime = pd.to_datetime(out["pi_time"], errors="coerce")

        aoi = out["aoi"].astype("string").fillna("").str.strip()
        recipe = out["recipe_id"].astype("string").fillna("").str.strip()
        recipe_upper = recipe.str.upper()

        # 預設全部 OTHER，後續能判斷才覆蓋
        out["pi_type"] = "OTHER"

        # =====================================================
        # aoi100 / CAPIT203
        # 規則：
        #   pi_time 為 NULL 或 test_time 為 NULL → OTHER
        #   test_time < pi_time → BPI
        #   test_time >= pi_time → API
        # =====================================================
        m100 = aoi.eq("CAPIT203")
        valid100 = m100 & scantime.notna() & pitime.notna()

        out.loc[valid100 & (scantime < pitime), "pi_type"] = "BPI"
        out.loc[valid100 & (scantime >= pitime), "pi_type"] = "API"

        # =====================================================
        # aoi200 / CAAOI202
        # 規則：
        #   recipe_id 第一碼 0/1/2/3 → API
        #   recipe_id 第一碼 4/5     → BPI
        #   其他 / 空值              → OTHER
        # =====================================================
        m200 = aoi.eq("CAAOI202")
        first = recipe.str.slice(0, 1)

        out.loc[m200 & first.isin(["0", "1", "2", "3"]), "pi_type"] = "API"
        out.loc[m200 & first.isin(["4", "5"]), "pi_type"] = "BPI"

        # =====================================================
        # aoi300 / CAAOI300
        # 規則：
        #   recipe_id 包含 API → API
        #   recipe_id 包含 BPI → BPI
        #   recipe_id 包含 ITO → ITO
        #   其他 / 空值        → OTHER
        #
        # 若同時包含多個關鍵字，目前優先順序：API > BPI > ITO
        # =====================================================
        m300 = aoi.eq("CAAOI300")
        """
        out.loc[m300 & recipe_upper.str.contains("ITO", na=False), "pi_type"] = "ITO"
        out.loc[m300 & recipe_upper.str.contains("BPI", na=False), "pi_type"] = "BPI"
        out.loc[m300 & recipe_upper.str.contains("API", na=False), "pi_type"] = "API"
        """
        valid300 = m300 & scantime.notna() & pitime.notna()

        out.loc[valid300 & (scantime < pitime), "pi_type"] = "BPI"
        out.loc[valid300 & (scantime >= pitime), "pi_type"] = "API"

        return out

    def fetch_secdefect_for_keys(self, keys_df: pd.DataFrame, *, batch_size: int = 800) -> pd.DataFrame:
        tname = "celaidi.h_aidi_secdefect"
        cfg = self.cfg[tname]
        need_cols = cfg.get("need_cols") or cfg.get("columns") or cfg.get("cim_cols")
        time_col = cfg.get("ori_time_column", "test_time")

        if keys_df is None or keys_df.empty:
            return pd.DataFrame(columns=need_cols)

        k = keys_df[["sheet_id_chip_id", "test_time"]].copy()
        k = k.dropna(subset=["sheet_id_chip_id", "test_time"])
        k["sheet_id_chip_id"] = k["sheet_id_chip_id"].astype(str)
        k["test_time"] = pd.to_datetime(k["test_time"], errors="coerce")
        k = k.dropna(subset=["test_time"]).drop_duplicates()
        if k.empty:
            return pd.DataFrame(columns=need_cols)

        t_min = k["test_time"].min()
        t_max = k["test_time"].max()
        glass_ids = k["sheet_id_chip_id"].unique().tolist()

        col_sql = self._cols_sql(need_cols)
        out_chunks = []

        with self.engine.connect() as conn:
            for i in range(0, len(glass_ids), batch_size):
                batch = glass_ids[i:i + batch_size]
                bind = {f"g{j}": v for j, v in enumerate(batch)}
                in_clause = ", ".join([f":g{j}" for j in range(len(batch))])

                sql = f"""
                SELECT {col_sql}
                FROM {tname}
                WHERE {time_col} BETWEEN :t_min AND :t_max
                  AND sheet_id_chip_id IN ({in_clause})
                """
                params = dict(bind)
                params.update({"t_min": t_min, "t_max": t_max})

                df = pd.read_sql(text(sql), conn, params=params)
                out_chunks.append(df)

        if not out_chunks:
            return pd.DataFrame(columns=need_cols)

        defects = pd.concat(out_chunks, ignore_index=True)
        defects["sheet_id_chip_id"] = defects["sheet_id_chip_id"].astype(str)
        defects["test_time"] = pd.to_datetime(defects["test_time"], errors="coerce")

        defects = defects.merge(k, on=["sheet_id_chip_id", "test_time"], how="inner")
        return defects

    def run_glass_pipeline_dt(
        self,
        start_dt: datetime,
        end_dt: datetime,
        *,
        eqp_id: str , #= "CAAOI300"
        use_eqp_filter: bool = False,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        cim_glass_sdf = self.fetch_secsheetchip_dt(
            start_dt,
            end_dt,
            eqp_id=eqp_id,
            use_eqp_filter=use_eqp_filter,
        )
        cim_pi_glass_sdf = self.build_cim_pi_glass_sdf(cim_glass_sdf)
        if cim_pi_glass_sdf.empty:
            return cim_glass_sdf, cim_pi_glass_sdf
        cim_pi_glass_sdf = self.add_pi_hour(cim_pi_glass_sdf)
        cim_pi_glass_sdf = self.add_pi_type(cim_pi_glass_sdf)
        return cim_glass_sdf, cim_pi_glass_sdf


# =============================================================================
# Runner (window-based)
# =============================================================================
def one_run(
    sql_db: MySQLConnet,
    pipe: AOI_CIM_Pipeline,
    cim_cfg: CIMDB_Config,
    *,
    eqp_id: str = "CAAOI300",
    lag_min: int = 2,
    lookback_min: int = 120,
    use_eqp_filter: bool = False,
):
    """
    window-based：
      end_dt   = now - lag_min
      start_dt = end_dt - lookback_min
    """
    ensure_state_table(sql_db)

    now = datetime.now()
    end_dt = now - timedelta(minutes=lag_min)
    start_dt = end_dt - timedelta(minutes=lookback_min)

    logging.info(
        f"[window] start_dt={start_dt} end_dt={end_dt} eqp_id={eqp_id} "
        f"lookback_min={lookback_min} lag_min={lag_min} use_eqp_filter={use_eqp_filter}"
    )

    cim_chip_df, cim_pi_glass_sdf = pipe.run_glass_pipeline_dt(
        start_dt, end_dt,
        eqp_id=eqp_id,
        use_eqp_filter=use_eqp_filter,
    )

    if cim_pi_glass_sdf is None or cim_pi_glass_sdf.empty:
        logging.info("[result] no new glass rows (window empty)")
        set_last_end_dt(sql_db, end_dt)  # 仍記錄觀測值
        return

    logging.info(f"[result] glass_rows={cim_pi_glass_sdf.shape}")

    # 1) summary
    save_summary_by_pi_yyyymm(sql_db, cim_cfg.CIM_SUMMARY_TB_NAME, cim_pi_glass_sdf)

    # 2) defect
    defect_df = pipe.fetch_secdefect_for_keys(cim_pi_glass_sdf)
    if defect_df is None or defect_df.empty:
        logging.info("[result] no defect rows")
    else:
        merge_cols = [
            "sheet_id_chip_id",
            "test_time",
            "recipe_id",
            "pi_time",
            "aoi",
            "line_id",
            "pi_hour",
            "pi_type",
        ]

        merge_cols = [c for c in merge_cols if c in cim_pi_glass_sdf.columns]

        defect_df = defect_df.merge(
            cim_pi_glass_sdf[merge_cols].drop_duplicates(),
            on=["sheet_id_chip_id", "test_time"],
            how="left"
        )

        if "recipe_id" in defect_df.columns:
            null_recipe_cnt = int(
                defect_df["recipe_id"]
                .astype("string")
                .fillna("")
                .str.strip()
                .eq("")
                .sum()
            )
            logging.info(
                f"[result] defect recipe_id merged. "
                f"rows={len(defect_df)}, empty_recipe_id_rows={null_recipe_cnt}"
            )
        logging.info(f"[result] defect_rows={defect_df.shape}")
        save_defect_by_time_aoi_line(sql_db, cim_cfg.CIM_DEFECT_TB_NAME, defect_df)

    set_last_end_dt(sql_db, end_dt)
    logging.info("[state] last_end_dt updated")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run once then exit (for Windows Task Scheduler).")

    # ★新：用分鐘
    parser.add_argument("--every-min", type=int, default=10, help="Run every N minutes (default 10).")
    parser.add_argument("--lookback-min", type=int, default=30, help="Fetch last R minutes from secsheetchip (default 30).")

    # 保留 lag_min
    parser.add_argument("--lag-min", type=int, default=2, help="End time lags behind now to avoid boundary issues.")
    parser.add_argument("--eqp-id", type=str, default="CAAOI300", help="AOI eqp_id filter, e.g. CAAOI300.")

    # 可選：是否真的加 eqp_id filter（預設 False，因為你原本註解掉）
    parser.add_argument("--use-eqp-filter", action="store_true", help="If set, add 'AND eqp_id=:eqp_id' in secsheetchip query.")

    args = parser.parse_args()

    setup_logging(log_dir="logs", log_name="cim_pull.txt")
    logging.info("=== CIM pull start ===")

    cim_cfg = CIMDB_Config()
    oracle_url = cim_cfg.DATABASE_URL

    # MySQL handler
    sql_db = MySQLConnet(cim_cfg.SQL_DBNAME)

    pipe = AOI_CIM_Pipeline(
        oracle_url=oracle_url,
        oracle_cim_table_config=cim_cfg.oracle_cim_table_config,
    )

    if args.once:
        try:
            one_run(
                sql_db, pipe, cim_cfg,
                eqp_id=args.eqp_id,
                lag_min=args.lag_min,
                lookback_min=args.lookback_min,
                use_eqp_filter=args.use_eqp_filter,
            )
        except Exception:
            logging.exception("Run failed")
        logging.info("=== CIM pull end (once) ===")
        return

    # loop mode (no drift)
    every_sec = max(1, int(args.every_min) * 60)

    while True:
        t0 = time.time()
        try:
            one_run(
                sql_db, pipe, cim_cfg,
                eqp_id=args.eqp_id,
                lag_min=args.lag_min,
                lookback_min=args.lookback_min,
                use_eqp_filter=args.use_eqp_filter,
            )
        except Exception:
            logging.exception("Run failed (loop)")

        elapsed = time.time() - t0
        sleep_sec = max(0.0, every_sec - elapsed)
        time.sleep(sleep_sec)


if __name__ == "__main__":
    main()