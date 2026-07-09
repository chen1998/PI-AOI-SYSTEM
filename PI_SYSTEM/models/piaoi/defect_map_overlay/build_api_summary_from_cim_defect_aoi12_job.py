#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine


# =========================================================
# Logging
# =========================================================
def setup_logger(
    log_dir: str = "logs",
    name: str = "build_api_summary_from_cim_defect_aoi12_job",
) -> logging.Logger:
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
# DB config
# =========================================================
@dataclass
class DBConfig:
    host: str = "127.0.0.1"
    port: int = 3306
    user: str = "l6a01_user"
    pwd: str = "l6a01$user"
    cim_db: str = "cim_piaoi"
    out_db: str = "piaoi_ol_defect_map"

    def make_url(self, dbname: str) -> str:
        return (
            f"mysql+pymysql://{self.user}:{self.pwd}"
            f"@{self.host}:{self.port}/{dbname}?charset=utf8mb4"
        )


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

    def list_candidate_defect_tables(
        self,
        aoi_list: Optional[List[str]] = None,
        line_key_list: Optional[List[str]] = None,
        yyyymm_list: Optional[List[str]] = None,
    ) -> List[str]:
        """
        從 information_schema 撈符合 cim_defect_% 的表。

        支援表名：
        - cim_defect_yyyymm_aoi100_capicxxx
        - cim_defect_yyyymm_aoi200_capicxxx
        - cim_defect_yyyymm_aoi100_pi000
        - cim_defect_yyyymm_aoi200_pi000
        """
        sql = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = :db
          AND table_name LIKE 'cim_defect\\_%'
        ORDER BY table_name
        """

        df = self.read_sql(sql, {"db": self.dbname})
        if df.empty:
            return []

        df.columns = [str(c).lower() for c in df.columns]

        if "table_name" not in df.columns:
            raise KeyError(f"查詢結果缺少 table_name 欄位，實際欄位為: {df.columns.tolist()}")

        out: List[str] = []

        aoi_norm = {x.lower() for x in aoi_list} if aoi_list else None
        line_key_norm = {x.lower() for x in line_key_list} if line_key_list else None
        ym_norm = set(yyyymm_list) if yyyymm_list else None

        for tb in df["table_name"].astype(str).tolist():
            meta = extract_table_meta(tb)
            if not meta:
                continue

            yyyymm, aoi, line_key = meta

            if aoi_norm and aoi not in aoi_norm:
                continue

            if line_key_norm and line_key not in line_key_norm:
                continue

            if ym_norm and yyyymm not in ym_norm:
                continue

            out.append(tb)

        return out


# =========================================================
# Constants / regex
# =========================================================
# 支援：
# cim_defect_202604_aoi100_capic100
# cim_defect_202604_aoi200_capic200
# cim_defect_202604_aoi100_pi000
# cim_defect_202604_aoi200_pi000
DEFECT_TABLE_REGEX = re.compile(
    r"^cim_defect_(\d{6})_(aoi\d{3})_((?:capic\d{3})|(?:pi000))$",
    flags=re.IGNORECASE,
)

AOI_CANONICAL = {"aoi100", "aoi200", "aoi300"}
AOI_AOI12_ONLY = {"aoi100", "aoi200"}

AOI_MAP_GLASS_TO_SHORT = {
    "CAPIT203": "aoi100",
    "CAAOI202": "aoi200",
    "CAAOI300": "aoi300",
}


# =========================================================
# Utils
# =========================================================
def normalize_aoi_short(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None

    s = str(v).strip()
    if not s:
        return None

    s_low = s.lower()
    if s_low in AOI_CANONICAL:
        return s_low

    return AOI_MAP_GLASS_TO_SHORT.get(s.upper())


def normalize_line_id(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None

    s = str(v).strip()
    if not s:
        return None

    return s.upper()


def parse_csv_list(v: Optional[str]) -> Optional[List[str]]:
    if v is None:
        return None

    items = [x.strip() for x in str(v).split(",") if x.strip()]
    return items or None


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


def build_out_table_name(aoi: str, yyyymm: str) -> str:
    return f"{str(aoi).lower()}_{str(yyyymm)}_api_summary_table"


def extract_table_meta(table_name: str) -> Optional[Tuple[str, str, str]]:
    """
    return:
        (yyyymm, aoi, line_key)

    line_key 可能是：
        capic100 / capic200 / ...
        pi000
    """
    m = DEFECT_TABLE_REGEX.match(str(table_name))
    if not m:
        return None

    yyyymm = m.group(1)
    aoi = m.group(2).lower()
    line_key = m.group(3).lower()

    return yyyymm, aoi, line_key


def month_list_from_range(
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
) -> Optional[List[str]]:
    if start_dt is None or end_dt is None:
        return None

    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt

    out: List[str] = []

    cur = datetime(start_dt.year, start_dt.month, 1)
    end_m = datetime(end_dt.year, end_dt.month, 1)

    while cur <= end_m:
        out.append(cur.strftime("%Y%m"))

        if cur.month == 12:
            cur = datetime(cur.year + 1, 1, 1)
        else:
            cur = datetime(cur.year, cur.month + 1, 1)

    return out


def clean_text_value(v) -> str:
    if pd.isna(v):
        return ""

    s = str(v).strip()
    if s.lower() in {"nan", "none", "<na>", "nat"}:
        return ""

    return s


def to_py_dt(v):
    """
    將 pandas Timestamp / NaT 轉成 Python datetime / None。
    避免 PyMySQL 寫入 NaT 報錯。
    """
    if pd.isna(v):
        return None

    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()

    return v


def resolve_glass_months_for_join(
    summary_df: pd.DataFrame,
    *,
    is_pi000: bool,
    run_year: Optional[int] = None,
) -> List[str]:
    """
    一般 capicxxx:
        用 defect.pi_time -> glass_yyyymm -> cim_pi_glass_yyyymm

    pi000:
        由於 pi_time 通常 NULL，額外讀：
        cim_pi_glass_當前年份00
        cim_pi_glass_前一年00
    """
    months: List[str] = []

    if summary_df is not None and not summary_df.empty and "glass_yyyymm" in summary_df.columns:
        s = summary_df["glass_yyyymm"].dropna().astype(str)
        s = s[s.str.match(r"^\d{6}$")]
        months = s.unique().tolist()

    if is_pi000:
        y = int(run_year or datetime.now().year)
        fallback_months = [f"{y}00", f"{y - 1}00"]

        for m in fallback_months:
            if m not in months:
                months.append(m)

    return months


def fill_output_defaults(
    merged: pd.DataFrame,
    *,
    src_aoi: str,
    src_line_key: str,
) -> pd.DataFrame:
    """
    join 不到 cim_pi_glass 時補安全值。

    capicxxx:
        line_id -> CAPICXXX

    pi000:
        line_id -> PI000

    文字欄位：
        recipe_id -> ""
        pi_type   -> ""

    時間欄位：
        pi_time 保持 NULL
    """
    out = merged.copy()

    line_fallback = str(src_line_key or "").strip().upper()
    if not line_fallback:
        line_fallback = "PI000"

    for c in ["recipe_id", "line_id", "aoi", "pi_type"]:
        if c not in out.columns:
            out[c] = ""

    out["recipe_id"] = out["recipe_id"].map(clean_text_value)
    out["line_id"] = out["line_id"].map(clean_text_value)
    out["aoi"] = out["aoi"].map(clean_text_value)
    out["pi_type"] = out["pi_type"].map(clean_text_value)

    out.loc[out["recipe_id"].str.strip().eq(""), "recipe_id"] = ""
    out.loc[out["line_id"].str.strip().eq(""), "line_id"] = line_fallback
    out.loc[out["aoi"].str.strip().eq(""), "aoi"] = str(src_aoi).lower()
    out.loc[out["pi_type"].str.strip().eq(""), "pi_type"] = ""

    out["aoi"] = out["aoi"].str.lower()
    out["line_id"] = out["line_id"].str.upper()

    return out


# =========================================================
# Target DDL
# =========================================================
def ensure_output_table(out_db: MySQLDB, table_name: str):
    ddl = f"""
    CREATE TABLE IF NOT EXISTS `{out_db.dbname}`.`{table_name}` (
        `id` BIGINT NOT NULL AUTO_INCREMENT,
        `sheet_id_chip_id` VARCHAR(64) NOT NULL,
        `test_time` DATETIME NOT NULL,
        `recipe_id` VARCHAR(255) NULL,
        `line_id` VARCHAR(32) NULL,
        `aoi` VARCHAR(16) NULL,

        `defect_count` INT NOT NULL DEFAULT 0,
        `small_defect_count` INT NOT NULL DEFAULT 0,
        `middle_defect_count` INT NOT NULL DEFAULT 0,
        `large_defect_count` INT NOT NULL DEFAULT 0,
        `over_defect_count` INT NOT NULL DEFAULT 0,

        `pi_time` DATETIME NULL,
        `pi_type` VARCHAR(16) NULL,
        `run_day` DATETIME NULL,

        `update_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP,

        PRIMARY KEY (`id`),
        UNIQUE KEY `uk_sheet_testtime` (`sheet_id_chip_id`, `test_time`),
        KEY `idx_recipe_id` (`recipe_id`),
        KEY `idx_line_id` (`line_id`),
        KEY `idx_aoi` (`aoi`),
        KEY `idx_pi_time` (`pi_time`),
        KEY `idx_run_day` (`run_day`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    out_db.execute(ddl)


def upsert_summary_df(out_db: MySQLDB, table_name: str, df: pd.DataFrame):
    if df is None or df.empty:
        logger.info(f"[upsert] {table_name}: no rows")
        return

    ensure_output_table(out_db, table_name)

    cols = [
        "sheet_id_chip_id",
        "test_time",
        "recipe_id",
        "line_id",
        "aoi",
        "defect_count",
        "small_defect_count",
        "middle_defect_count",
        "large_defect_count",
        "over_defect_count",
        "pi_time",
        "pi_type",
        "run_day",
    ]

    for c in cols:
        if c not in df.columns:
            if c in {
                "defect_count",
                "small_defect_count",
                "middle_defect_count",
                "large_defect_count",
                "over_defect_count",
            }:
                df[c] = 0
            else:
                df[c] = None

    d = df[cols].copy()

    # 必要 key 清理
    d["sheet_id_chip_id"] = d["sheet_id_chip_id"].map(clean_text_value)
    d = d[d["sheet_id_chip_id"].str.len() > 0].copy()

    # datetime 欄位轉成 Python datetime / None
    for c in ["test_time", "pi_time", "run_day"]:
        d[c] = pd.to_datetime(d[c], errors="coerce")
        d[c] = d[c].map(to_py_dt)

    # test_time 是 NOT NULL，無 test_time 不寫入
    d = d[d["test_time"].notna()].copy()

    # 文字欄位清理，避免 pandas <NA> / nan 字串寫入
    for c in ["recipe_id", "line_id", "aoi", "pi_type"]:
        d[c] = d[c].map(clean_text_value)

    # 數值欄位清理
    count_cols = [
        "defect_count",
        "small_defect_count",
        "middle_defect_count",
        "large_defect_count",
        "over_defect_count",
    ]

    for c in count_cols:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0).astype(int)

    rows = d.to_dict(orient="records")
    if not rows:
        logger.info(f"[upsert] {table_name}: no rows after conversion")
        return

    sql = f"""
    INSERT INTO `{out_db.dbname}`.`{table_name}` (
        sheet_id_chip_id, test_time, recipe_id, line_id, aoi,
        defect_count, small_defect_count, middle_defect_count,
        large_defect_count, over_defect_count,
        pi_time, pi_type, run_day
    ) VALUES (
        :sheet_id_chip_id, :test_time, :recipe_id, :line_id, :aoi,
        :defect_count, :small_defect_count, :middle_defect_count,
        :large_defect_count, :over_defect_count,
        :pi_time, :pi_type, :run_day
    )
    ON DUPLICATE KEY UPDATE
        recipe_id = VALUES(recipe_id),
        line_id = VALUES(line_id),
        aoi = VALUES(aoi),
        defect_count = VALUES(defect_count),
        small_defect_count = VALUES(small_defect_count),
        middle_defect_count = VALUES(middle_defect_count),
        large_defect_count = VALUES(large_defect_count),
        over_defect_count = VALUES(over_defect_count),
        pi_time = VALUES(pi_time),
        pi_type = VALUES(pi_type),
        run_day = VALUES(run_day)
    """

    with out_db.engine.begin() as conn:
        conn.execute(text(sql), rows)

    logger.info(f"[upsert] {table_name}: upserted {len(rows)} rows")


# =========================================================
# Read source
# =========================================================
def load_defect_table_filtered(
    cim_db: MySQLDB,
    table_name: str,
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
) -> pd.DataFrame:
    """
    只讀 summary 實際需要用到的欄位：
    - sheet_id_chip_id
    - test_time
    - defect_size
    - pi_time

    不再讀：
    - chip_id
    - pox_x1 / pox_y1
    - image path
    - adc/retype code
    - pi_hour
    """
    where = []
    params: Dict[str, object] = {}

    if start_dt is not None:
        where.append("test_time >= :start_dt")
        params["start_dt"] = start_dt

    if end_dt is not None:
        where.append("test_time < :end_dt")
        params["end_dt"] = end_dt

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    sql = f"""
    SELECT
        sheet_id_chip_id,
        test_time,
        defect_size,
        pi_time
    FROM `{cim_db.dbname}`.`{table_name}`
    {where_sql}
    """

    df = cim_db.read_sql(sql, params)

    if df.empty:
        return df

    df["test_time"] = pd.to_datetime(df["test_time"], errors="coerce")
    df["pi_time"] = pd.to_datetime(df["pi_time"], errors="coerce")

    return df


def aggregate_defect_summary(
    defect_df: pd.DataFrame,
    *,
    src_aoi: str,
) -> pd.DataFrame:
    if defect_df is None or defect_df.empty:
        return pd.DataFrame(
            columns=[
                "sheet_id_chip_id",
                "test_time",
                "defect_count",
                "small_defect_count",
                "middle_defect_count",
                "large_defect_count",
                "over_defect_count",
                "pi_time",
                "run_day",
                "out_yyyymm",
                "glass_yyyymm",
            ]
        )

    d = defect_df.copy()
    d = d.dropna(subset=["sheet_id_chip_id", "test_time"])

    if d.empty:
        return pd.DataFrame()

    d["sheet_id_chip_id"] = d["sheet_id_chip_id"].map(clean_text_value)
    d = d[d["sheet_id_chip_id"].str.len() > 0].copy()

    if d.empty:
        return pd.DataFrame()

    d["test_time"] = pd.to_datetime(d["test_time"], errors="coerce")
    d["pi_time"] = pd.to_datetime(d["pi_time"], errors="coerce")
    d = d.dropna(subset=["test_time"])

    if d.empty:
        return pd.DataFrame()

    d["defect_size"] = d["defect_size"].astype("string").str.upper().str.strip()
    d["defect_size"] = d["defect_size"].fillna("")

    empty_size_values = {"", "NAN", "NONE", "<NA>", "NAT", "NULL"}

    is_aoi200 = str(src_aoi).strip().lower() == "aoi200"

    grp = d.groupby(["sheet_id_chip_id", "test_time"], dropna=False)

    if is_aoi200:
        summary = grp.agg(
            defect_count=("defect_size", "size"),
            small_defect_count=("defect_size", lambda s: int((s == "S").sum())),
            middle_defect_count=("defect_size", lambda s: int((s == "M").sum())),
            large_defect_count=("defect_size", lambda s: int((s == "L").sum())),
            over_defect_count=(
                "defect_size",
                lambda s: int((s.eq("O") | s.isin(empty_size_values)).sum())
            ),
            pi_time=("pi_time", "first"),
        ).reset_index()
    else:
        summary = grp.agg(
            defect_count=("defect_size", "size"),
            small_defect_count=("defect_size", lambda s: int((s == "S").sum())),
            middle_defect_count=("defect_size", lambda s: int((s == "M").sum())),
            large_defect_count=("defect_size", lambda s: int((s == "L").sum())),
            over_defect_count=("defect_size", lambda s: int((s == "O").sum())),
            pi_time=("pi_time", "first"),
        ).reset_index()

    empty_size_cnt = int(d["defect_size"].isin(empty_size_values).sum())
    total_cnt = len(d)

    logger.info(
        f"[defect_size_policy] src_aoi={src_aoi}, "
        f"empty_size_cnt={empty_size_cnt}, "
        f"total_cnt={total_cnt}, "
        f"empty_size_to_over={is_aoi200}"
    )

    summary["test_time"] = pd.to_datetime(summary["test_time"], errors="coerce")
    summary["pi_time"] = pd.to_datetime(summary["pi_time"], errors="coerce")

    summary["run_day"] = summary["test_time"].dt.normalize()
    summary["out_yyyymm"] = summary["test_time"].dt.strftime("%Y%m")
    summary["glass_yyyymm"] = summary["pi_time"].dt.strftime("%Y%m")

    return summary


def load_glass_months(cim_db: MySQLDB, glass_months: List[str]) -> pd.DataFrame:
    """
    從 cim_pi_glass_yyyymm 補：
    - recipe_id
    - line_id
    - aoi
    - pi_type

    對 pi000 來源，glass_months 會包含：
    - 當前年份00
    - 前一年00
    """
    frames: List[pd.DataFrame] = []

    months: List[str] = []
    for m in glass_months or []:
        s = str(m).strip()
        if re.match(r"^\d{6}$", s):
            months.append(s)

    for yyyymm in sorted(set(months)):
        tb = f"cim_pi_glass_{yyyymm}"

        if not cim_db.table_exists(tb):
            logger.warning(f"[glass] table not found: {tb}")
            continue

        sql = f"""
        SELECT
            sheet_id_chip_id,
            test_time,
            recipe_id,
            line_id,
            aoi,
            pi_type
        FROM `{cim_db.dbname}`.`{tb}`
        """

        g = cim_db.read_sql(sql)
        if g.empty:
            continue

        g["sheet_id_chip_id"] = g["sheet_id_chip_id"].map(clean_text_value)
        g["test_time"] = pd.to_datetime(g["test_time"], errors="coerce")

        g = g.dropna(subset=["test_time"])
        g = g[g["sheet_id_chip_id"].str.len() > 0].copy()

        if g.empty:
            continue

        g["recipe_id"] = g["recipe_id"].map(clean_text_value)
        g["line_id"] = g["line_id"].map(normalize_line_id)
        g["aoi"] = g["aoi"].map(normalize_aoi_short)
        g["pi_type"] = g["pi_type"].map(clean_text_value)

        g = g.sort_values(["sheet_id_chip_id", "test_time"]).drop_duplicates(
            subset=["sheet_id_chip_id", "test_time"],
            keep="last",
        )

        g["glass_yyyymm"] = yyyymm
        frames.append(g)

    if not frames:
        return pd.DataFrame(
            columns=[
                "sheet_id_chip_id",
                "test_time",
                "recipe_id",
                "line_id",
                "aoi",
                "pi_type",
                "glass_yyyymm",
            ]
        )

    return pd.concat(frames, ignore_index=True)


def join_summary_with_glass(summary_df: pd.DataFrame, glass_df: pd.DataFrame) -> pd.DataFrame:
    if summary_df is None or summary_df.empty:
        return summary_df

    d = summary_df.copy()

    if glass_df is None or glass_df.empty:
        for c in ["recipe_id", "line_id", "aoi", "pi_type"]:
            if c not in d.columns:
                d[c] = None
        return d

    g = glass_df.copy()

    merged = d.merge(
        g[["sheet_id_chip_id", "test_time", "recipe_id", "line_id", "aoi", "pi_type"]],
        how="left",
        on=["sheet_id_chip_id", "test_time"],
        suffixes=("", "_glass"),
    )

    return merged


# =========================================================
# Main process for one table
# =========================================================
def process_one_defect_table(
    cim_db: MySQLDB,
    out_db: MySQLDB,
    defect_table: str,
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
):
    meta = extract_table_meta(defect_table)
    if not meta:
        logger.warning(f"[skip] invalid defect table name: {defect_table}")
        return

    src_yyyymm, src_aoi, src_line_key = meta
    is_pi000 = src_line_key.lower() == "pi000"

    if src_aoi not in AOI_AOI12_ONLY:
        logger.info(f"[skip] {defect_table}: not aoi100/aoi200")
        return

    logger.info(
        f"[start] table={defect_table} "
        f"yyyymm={src_yyyymm} aoi={src_aoi} "
        f"line_key={src_line_key} is_pi000={is_pi000}"
    )

    defect_df = load_defect_table_filtered(
        cim_db=cim_db,
        table_name=defect_table,
        start_dt=start_dt,
        end_dt=end_dt,
    )

    if defect_df.empty:
        logger.info(f"[empty] {defect_table}")
        return

    logger.info(f"[load] {defect_table}: {len(defect_df)} raw rows")

    summary_base = aggregate_defect_summary(
                        defect_df,
                        src_aoi=src_aoi,
                    )
    if summary_base.empty:
        logger.info(f"[summary] {defect_table}: no summary rows")
        return

    logger.info(f"[summary] {defect_table}: {len(summary_base)} grouped rows")

    glass_months = resolve_glass_months_for_join(
        summary_base,
        is_pi000=is_pi000,
        run_year=datetime.now().year,
    )

    logger.info(f"[glass] {defect_table}: glass_months={glass_months}")

    glass_df = load_glass_months(cim_db, glass_months)

    merged = join_summary_with_glass(summary_base, glass_df)

    merged = fill_output_defaults(
        merged,
        src_aoi=src_aoi,
        src_line_key=src_line_key,
    )

    for (out_yyyymm, out_aoi), g in merged.groupby(["out_yyyymm", "aoi"], dropna=False):
        if pd.isna(out_yyyymm) or pd.isna(out_aoi):
            logger.warning(f"[skip output group] invalid out_yyyymm/aoi in {defect_table}")
            continue

        out_aoi = str(out_aoi).strip().lower()
        if out_aoi not in AOI_AOI12_ONLY:
            logger.info(f"[skip output group] out_aoi={out_aoi} not in aoi100/aoi200")
            continue

        out_table = build_out_table_name(out_aoi, str(out_yyyymm))
        upsert_summary_df(out_db, out_table, g)

    logger.info(f"[done] {defect_table}")


# =========================================================
# Window resolution
# =========================================================
def resolve_window(
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
    date_str: Optional[str],
    lookback_min: int,
    lag_min: int,
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    優先序：
    1. --start-dt / --end-dt
    2. --date
    3. lookback window
    """
    if start_dt or end_dt:
        if start_dt is None and end_dt is not None:
            start_dt = end_dt - timedelta(minutes=lookback_min)

        if end_dt is None and start_dt is not None:
            end_dt = start_dt + timedelta(minutes=lookback_min)

        return start_dt, end_dt

    if date_str:
        day_start = parse_dt(date_str)
        if day_start is None:
            raise ValueError(f"invalid --date: {date_str}")

        day_start = datetime(day_start.year, day_start.month, day_start.day)
        day_end = day_start + timedelta(days=1)

        return day_start, day_end

    now = datetime.now()
    _end = now - timedelta(minutes=lag_min)
    _start = _end - timedelta(minutes=lookback_min)

    return _start, _end


# =========================================================
# One run
# =========================================================
def one_run(
    cfg: DBConfig,
    aoi_list: Optional[List[str]],
    line_key_list: Optional[List[str]],
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
):
    if aoi_list:
        aoi_list = [x.lower() for x in aoi_list if x.lower() in AOI_AOI12_ONLY]
    else:
        aoi_list = ["aoi100", "aoi200"]

    if line_key_list:
        line_key_list = [x.lower() for x in line_key_list]

    logger.info(f"[one_run] start_dt={start_dt}, end_dt={end_dt}")
    logger.info(f"[one_run] aoi_list={aoi_list}, line_key_list={line_key_list}")

    cim_db = MySQLDB(cfg.cim_db, cfg)
    out_db = MySQLDB(cfg.out_db, cfg)

    ym_list = month_list_from_range(start_dt, end_dt)

    defect_tables = cim_db.list_candidate_defect_tables(
        aoi_list=aoi_list,
        line_key_list=line_key_list,
        yyyymm_list=ym_list,
    )

    if not defect_tables:
        logger.warning("[one_run] no matching cim_defect tables found")
        return

    logger.info(f"[one_run] matched defect tables: {len(defect_tables)}")

    for tb in defect_tables:
        try:
            process_one_defect_table(
                cim_db=cim_db,
                out_db=out_db,
                defect_table=tb,
                start_dt=start_dt,
                end_dt=end_dt,
            )
        except Exception:
            logger.exception(f"[error] failed processing table: {tb}")

    logger.info("[one_run] done")


# =========================================================
# CLI
# =========================================================
def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Scheduled job: build aoi100/aoi200 api summary tables "
            "from cim_defect_* into piaoi_ol_defect_map"
        )
    )

    p.add_argument("--host", type=str, default="127.0.0.1")
    p.add_argument("--port", type=int, default=3306)
    p.add_argument("--user", type=str, default="l6a01_user")
    p.add_argument("--pwd", type=str, default="l6a01$user")
    p.add_argument("--cim-db", type=str, default="cim_piaoi")
    p.add_argument("--out-db", type=str, default="piaoi_ol_defect_map")

    p.add_argument("--once", action="store_true", help="Run once then exit")
    p.add_argument("--every-min", type=int, default=10, help="Loop interval minutes")
    p.add_argument(
        "--lookback-min",
        type=int,
        default=180,
        help="Default lookback minutes when no explicit time range is given",
    )
    p.add_argument("--lag-min", type=int, default=2, help="Lag minutes to avoid boundary issues")

    p.add_argument("--aoi-list", type=str, default="aoi100,aoi200", help="Comma-separated AOI list")

    # 保留舊參數名稱，仍可用 --capic-list pi000 或 --capic-list capic100,pi000
    p.add_argument(
        "--capic-list",
        type=str,
        default=None,
        help=(
            "Comma-separated line-key list. "
            "Support capicxxx and pi000. Example: capic100,capic200,pi000"
        ),
    )

    # 新參數名稱，比 capic-list 更精準；若兩者都有，優先用 line-key-list
    p.add_argument(
        "--line-key-list",
        type=str,
        default=None,
        help=(
            "Comma-separated line-key list. "
            "Support capicxxx and pi000. Example: capic100,capic200,pi000"
        ),
    )

    p.add_argument("--start-dt", type=str, default=None, help="YYYY-MM-DD or YYYY-MM-DD HH:MM[:SS]")
    p.add_argument("--end-dt", type=str, default=None, help="YYYY-MM-DD or YYYY-MM-DD HH:MM[:SS]")
    p.add_argument("--date", type=str, default=None, help="Single date mode, e.g. 2026-04-10")

    return p


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    cfg = DBConfig(
        host=args.host,
        port=args.port,
        user=args.user,
        pwd=args.pwd,
        cim_db=args.cim_db,
        out_db=args.out_db,
    )

    aoi_list = parse_csv_list(args.aoi_list)

    # 若 line-key-list 有給，優先使用；否則相容舊的 capic-list
    line_key_list = parse_csv_list(args.line_key_list)
    if line_key_list is None:
        line_key_list = parse_csv_list(args.capic_list)

    start_dt = parse_dt(args.start_dt)
    end_dt = parse_dt(args.end_dt)

    if aoi_list:
        aoi_list = [x.lower() for x in aoi_list]

    if line_key_list:
        line_key_list = [x.lower() for x in line_key_list]

    if args.once:
        run_start_dt, run_end_dt = resolve_window(
            start_dt=start_dt,
            end_dt=end_dt,
            date_str=args.date,
            lookback_min=args.lookback_min,
            lag_min=args.lag_min,
        )

        one_run(
            cfg=cfg,
            aoi_list=aoi_list,
            line_key_list=line_key_list,
            start_dt=run_start_dt,
            end_dt=run_end_dt,
        )
        return

    every_sec = max(1, int(args.every_min) * 60)

    while True:
        t0 = time.time()

        try:
            run_start_dt, run_end_dt = resolve_window(
                start_dt=start_dt,
                end_dt=end_dt,
                date_str=args.date,
                lookback_min=args.lookback_min,
                lag_min=args.lag_min,
            )

            one_run(
                cfg=cfg,
                aoi_list=aoi_list,
                line_key_list=line_key_list,
                start_dt=run_start_dt,
                end_dt=run_end_dt,
            )

        except Exception:
            logger.exception("[main] run failed")

        elapsed = time.time() - t0
        sleep_sec = max(0.0, every_sec - elapsed)
        time.sleep(sleep_sec)


if __name__ == "__main__":
    main()


"""
# =========================================================
# Usage
# =========================================================

# 常駐，每 10 分鐘跑一次，預設處理 aoi100/aoi200，包含 capicxxx 與 pi000
python build_api_summary_from_cim_defect_aoi12_job.py

# 單次執行，最近 180 分鐘
python build_api_summary_from_cim_defect_aoi12_job.py --once

# 單次執行，最近 1440 分鐘
python build_api_summary_from_cim_defect_aoi12_job.py --once --lookback-min 1440

# 單次執行，只處理 aoi200
python build_api_summary_from_cim_defect_aoi12_job.py --once --aoi-list aoi200

# 單次執行，只處理 aoi200 + capic100/capic200
python build_api_summary_from_cim_defect_aoi12_job.py --once --aoi-list aoi200 --start-dt "2026-01-01 00:00:00" --end-dt "2026-06-01 00:00:00"

# 單次執行，只處理 pi000
python build_api_summary_from_cim_defect_aoi12_job_copy.py --once --line-key-list pi000

# 單次執行，處理 capic100 與 pi000
python build_api_summary_from_cim_defect_aoi12_job.py --once --line-key-list capic100,pi000

# 舊參數仍可用
python build_api_summary_from_cim_defect_aoi12_job.py --once --capic-list pi000

# 指定時間區間
python build_api_summary_from_cim_defect_aoi12_job_copy.py --once --start-dt "2026-01-01 00:00:00" --end-dt "2026-04-01 00:00:00"

# 指定單日
python build_api_summary_from_cim_defect_aoi12_job.py --once --date 2026-04-10
"""