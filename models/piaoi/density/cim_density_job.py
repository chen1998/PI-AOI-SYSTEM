# cim_density_job.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import time
import json
import argparse
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Tuple, List, Optional, Any

import pandas as pd
from sqlalchemy import create_engine, text, inspect


# =============================================================================
# Logging
# =============================================================================
def setup_logger(log_dir: str = "logs", name: str = "cim_density") -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    from logging.handlers import TimedRotatingFileHandler

    log_path = os.path.join(log_dir, f"{name}.log")

    fh = TimedRotatingFileHandler(
        log_path,
        when="D",
        interval=1,
        backupCount=95,
        encoding="utf-8",
    )
    sh = logging.StreamHandler()

    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    fh.setFormatter(fmt)
    sh.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(sh)

    return logger


# =============================================================================
# Minimal MySQLConnet
# =============================================================================
class MySQLConnet:
    def __init__(self, dbname: str, host: str, username: str, password: str):
        self.db = dbname
        self.engine = create_engine(
            f"mysql+pymysql://{username}:{password}@{host}/{dbname}",
            pool_pre_ping=True,
            connect_args={"charset": "utf8mb4"},
        )

    def table_exists(self, table_name: str) -> bool:
        insp = inspect(self.engine)
        return insp.has_table(table_name, schema=self.db)

    def get_table(self, table_name: str) -> pd.DataFrame:
        return pd.read_sql_table(table_name, self.engine, schema=self.db)


# =============================================================================
# Config
# =============================================================================
@dataclass
class Config:
    # connection
    host: str = "10.97.142.217"
    username: str = "l6a01_user"
    password: str = "l6a01$user"

    # dbs
    src_db: str = "cim_piaoi"
    out_db: str = "piaoi_density"

    # source tables
    summary_table_tpl: str = "cim_pi_glass_yyyymm"
    defect_table_tpl: str = "cim_defect_yyyymm_aoi_line"

    # output tables
    tab_table_tpl: str = "density_tab_summary_yyyymm"
    recipe_table_tpl: str = "density_recipe_summary_yyyymm"
    code_table_tpl: str = "density_code_summary_yyyymm"

    # compatibility alias
    out_table_tpl: str = "density_code_summary_yyyymm"

    # AOI Density 只取 API。
    # 若要不篩 pi_type，CLI 使用 --allowed_pi_types ALL。
    allowed_pi_types: Tuple[str, ...] = ("API",)

    # -------------------------------------------------------------------------
    # Grains
    # -------------------------------------------------------------------------
    base_group_cols: Tuple[str, ...] = (
        "line_id",
        "aoi",
        "model",
        "glass_type",
        "pi_hour",
    )

    recipe_group_cols: Tuple[str, ...] = (
        "line_id",
        "aoi",
        "model",
        "glass_type",
        "pi_hour",
        "recipe_id",
    )

    code_group_cols: Tuple[str, ...] = (
        "line_id",
        "aoi",
        "model",
        "glass_type",
        "pi_hour",
        "recipe_id",
        "adc_def_code",
    )

    # tab summary 寫入覆寫 key。
    # recipe_family 會輸出，但不放 key，避免舊表 recipe_family NULL 時刪不到舊資料。
    tab_group_cols: Tuple[str, ...] = (
        "line_id",
        "aoi",
        "model",
        "glass_type",
        "pi_hour",
        "tab_name",
    )

    sort_cols: Tuple[str, ...] = ("pi_time", "scan_time")

    # AOI mapping
    aoi_map: Dict[str, str] = field(default_factory=lambda: {
        "CAPIT203": "aoi100",
        "CAAOI202": "aoi200",
        "CAAOI300": "aoi300",
    })

    # summary column mapping
    summary_coldict: Dict[str, str] = field(default_factory=lambda: {
        "line_id": "line_id",
        "aoi": "aoi",
        "model_no": "model",
        "abbr_cat": "glass_type",
        "recipe_id": "recipe_id",
        "cassette_id": "caset_id",
        "pi_hour": "pi_hour",
        "pi_type": "pi_type",
        "sheet_id_chip_id": "glass_id",
        "total_defect_qty": "total_defect_count",
        "pi_time": "pi_time",
        "test_time": "scan_time",
    })

    # defect column mapping
    defect_coldict: Dict[str, str] = field(default_factory=lambda: {
        "sheet_id_chip_id": "glass_id",
        "chip_id": "chip_name",
        "test_time": "scan_time",
        "defect_size": "defect_size",
        "pox_x1": "x",
        "pox_y1": "y",
        "image_file_path": "pic_path",
        "image_file_name": "pic_name",
        "retype_def_code": "retype_code",
        "adc_def_code": "adc_def_code",
        "pi_time": "pi_time",
        "pi_hour": "pi_hour",
    })

    # default output codes; actual codes from defect table are also kept
    target_defect_codes: Tuple[str, ...] = (
        "Polymer",
        "SSIU_Polymer",
        "PI_Spot_NP",
        "PIS With Particle",
        "SPS",
        "NPI_TFT",
        "others",
    )

    # tabs
    tab_names: Tuple[str, ...] = (
        "UPI",
        "UPI_Total",
        "PISpot",
        "PISpot_Total",
        "SPS",
    )

    # 一般 recipe 規則：
    #   4碼 2/3 -> UPI, UPI_Total
    #   4碼 0/1 -> PISpot, PISpot_Total, SPS
    #   3碼 -> all tabs
    #
    # 特別規則：
    #   aoi100 / aoi300 的 API 資料一律展開到 all tabs。
    recipe_family_4digit_prefix_map: Dict[str, Tuple[str, ...]] = field(default_factory=lambda: {
        "2": ("UPI", "UPI_Total"),
        "3": ("UPI", "UPI_Total"),
        "0": ("PISpot", "PISpot_Total", "SPS"),
        "1": ("PISpot", "PISpot_Total", "SPS"),
    })

    recipe_family_3digit_tabs: Tuple[str, ...] = (
        "UPI",
        "UPI_Total",
        "PISpot",
        "PISpot_Total",
        "SPS",
    )

    unknown_recipe_tabs: Tuple[str, ...] = tuple()

    all_backend_tabs: Tuple[str, ...] = (
        "UPI",
        "UPI_Total",
        "PISpot",
        "PISpot_Total",
        "SPS",
    )

    tab_recipe_family_map: Dict[str, str] = field(default_factory=lambda: {
        "UPI": "UPI",
        "UPI_Total": "UPI",
        "PISpot": "PISpot",
        "PISpot_Total": "PISpot",
        "SPS": "PISpot",
    })

    tab_default_codes: Dict[str, Tuple[str, ...]] = field(default_factory=lambda: {
        "UPI": ("Polymer", "SSIU_Polymer", "NPI_TFT"),
        "UPI_Total": ("others",),
        "PISpot": ("PI_Spot_NP", "PIS With Particle", "NPI_TFT"),
        "PISpot_Total": ("others",),
        "SPS": ("SPS",),
    })

    batch_size: int = 800
    loop_minutes: int = 10
    lookback_minutes: int = 180
    write_out: bool = True


# =============================================================================
# Time helpers
# =============================================================================
def month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_month_start(dt: datetime) -> datetime:
    y, m = dt.year, dt.month
    if m == 12:
        return dt.replace(year=y + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return dt.replace(month=m + 1, day=1, hour=0, minute=0, second=0, microsecond=0)


def iter_yyyymm_in_range(start_dt: datetime, end_dt: datetime) -> List[str]:
    cur = month_start(start_dt)
    out: List[str] = []

    while cur < end_dt:
        out.append(cur.strftime("%Y%m"))
        cur = next_month_start(cur)

    return out


def derive_pi_hour_from_pi_time(ts: pd.Series, cut_minute: int = 30) -> pd.Series:
    """
    pi_hour = (pi_time - 30min).floor("h")

    07:30:00 ~ 08:29:59 -> 07:00
    08:30:00 ~ 09:29:59 -> 08:00
    00:00:00 ~ 00:29:59 -> previous day 23:00
    """
    s = pd.to_datetime(ts, errors="coerce")
    return (s - pd.to_timedelta(cut_minute, unit="m")).dt.floor("h")


def normalize_aoi(series: pd.Series, aoi_map: Dict[str, str]) -> pd.Series:
    s = series.astype("string")
    mapped = s.map(aoi_map)
    return mapped.fillna(s)


def standardize_model(x: Any) -> str:
    if x is None:
        return ""
    s = str(x)
    return s.split("_")[0] if "_" in s else s


def is_empty_like(v: Any) -> bool:
    if v is None:
        return True

    try:
        if pd.isna(v):
            return True
    except Exception:
        pass

    s = str(v).strip()
    return s.lower() in {"", "nan", "none", "null", "nat", "<na>", "undefined"}


def normalize_defect_size_for_aoi(v: Any, aoi: Any = "") -> str:
    aoi_norm = "" if aoi is None else str(aoi).strip().lower()

    if is_empty_like(v):
        return "O" if aoi_norm == "aoi200" else ""

    s = str(v).strip().upper()

    if s in {"S", "SMALL"}:
        return "S"
    if s in {"M", "MID", "MIDDLE"}:
        return "M"
    if s in {"L", "LARGE"}:
        return "L"
    if s in {"O", "OVER"}:
        return "O"

    n = pd.to_numeric(s, errors="coerce")
    if not pd.isna(n):
        if n <= 20:
            return "S"
        if n <= 100:
            return "M"
        if n <= 400:
            return "L"
        return "O"

    if aoi_norm == "aoi200":
        return "O"

    return ""


def recipe_id_to_tabs(recipe_id: Any, cfg: Config, aoi: Any = "") -> List[str]:
    """
    決定 recipe row 要展開到哪些 backend tabs。

    新需求：
      aoi100 / aoi300 的 API 資料一律出現在所有 tab。
      pi_type=API 已在前面 filter_summary_by_pi_type() 篩過。

    其他 AOI：
      4碼 2/3 -> UPI, UPI_Total
      4碼 0/1 -> PISpot, PISpot_Total, SPS
      3碼 -> all tabs
    """
    aoi_s = str(aoi or "").strip().lower()

    if aoi_s in {"aoi100", "aoi300"}:
        return list(cfg.all_backend_tabs)

    s = "" if recipe_id is None else str(recipe_id).strip()

    if not s:
        return list(cfg.unknown_recipe_tabs)

    if len(s) == 4:
        return list(cfg.recipe_family_4digit_prefix_map.get(s[0], cfg.unknown_recipe_tabs))

    if len(s) == 3:
        return list(cfg.recipe_family_3digit_tabs)

    return list(cfg.unknown_recipe_tabs)


def tab_to_recipe_family(tab_name: Any, cfg: Config) -> str:
    s = "" if tab_name is None else str(tab_name).strip()
    return cfg.tab_recipe_family_map.get(s, "")


def split_glass_string(s: Any) -> List[str]:
    if s is None:
        return []

    out = []
    for x in str(s).split(","):
        v = x.strip()
        if v:
            out.append(v)

    return out


def join_unique_sorted(values: List[Any]) -> str:
    vals = sorted(set([str(v).strip() for v in values if str(v).strip()]))
    return ",".join(vals)


def format_dt_value(v: Any) -> str:
    if v is None:
        return ""

    try:
        ts = pd.to_datetime(v, errors="coerce")
        if pd.isna(ts):
            return ""
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


# =============================================================================
# Load & clean summary
# =============================================================================
def load_summary_for_month(
    db_src: MySQLConnet,
    cfg: Config,
    yyyymm: str,
    logger: logging.Logger,
) -> pd.DataFrame:
    tb = cfg.summary_table_tpl.replace("yyyymm", yyyymm).lower()

    if not db_src.table_exists(tb):
        logger.warning(f"[load_summary] missing table `{db_src.db}`.`{tb}` -> skip")
        return pd.DataFrame()

    df = db_src.get_table(tb)
    logger.info(f"[load_summary] {yyyymm} get_table rows={len(df)}")

    if df is None or df.empty:
        return pd.DataFrame()

    need_src_cols = list(cfg.summary_coldict.keys())
    exist = [c for c in need_src_cols if c in df.columns]

    df = df[exist].copy()
    df.rename(columns=cfg.summary_coldict, inplace=True)

    if "total_defect_count" not in df.columns:
        df["total_defect_count"] = 0

    before = len(df)
    df.dropna(axis=0, how="any", subset=["glass_id", "scan_time", "pi_time"], inplace=True)
    logger.info(f"[load_summary] after dropna rows={len(df)}, dropped={before - len(df)}")

    return df


def clean_summary(df: pd.DataFrame, cfg: Config, logger: logging.Logger) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    for c in ["scan_time", "pi_time", "pi_hour"]:
        if c in out.columns:
            out[c] = pd.to_datetime(out[c], errors="coerce")

    out["pi_hour"] = derive_pi_hour_from_pi_time(out["pi_time"], cut_minute=30)

    if "aoi" in out.columns:
        out["aoi"] = normalize_aoi(out["aoi"], cfg.aoi_map)

    if "model" in out.columns:
        out["model"] = out["model"].apply(standardize_model)

    for c in ["line_id", "aoi", "model", "glass_type", "recipe_id", "glass_id", "pi_type"]:
        if c in out.columns:
            out[c] = out[c].astype("string").fillna("").astype(str).str.strip()

    if "pi_type" not in out.columns:
        out["pi_type"] = ""

    if "total_defect_count" not in out.columns:
        out["total_defect_count"] = 0

    out["total_defect_count"] = (
        pd.to_numeric(out["total_defect_count"], errors="coerce")
        .fillna(0)
        .astype(int)
    )

    before = len(out)
    out.dropna(axis=0, how="any", subset=["glass_id", "scan_time", "pi_time", "pi_hour"], inplace=True)
    out = out[out["glass_id"].astype(str).str.len() > 0].copy()
    out.reset_index(drop=True, inplace=True)

    logger.info(f"[clean_summary] clean rows={len(out)}, dropped={before - len(out)}")
    return out


def filter_summary_by_pi_type(
    summary: pd.DataFrame,
    allowed_pi_types: Tuple[str, ...],
    logger: logging.Logger,
) -> pd.DataFrame:
    if summary is None or summary.empty:
        return pd.DataFrame()

    if not allowed_pi_types:
        logger.info("[pi_type_filter] allowed_pi_types empty -> skip filter")
        return summary.copy()

    if "pi_type" not in summary.columns:
        logger.warning("[pi_type_filter] summary missing pi_type -> return empty")
        return pd.DataFrame()

    allowed = {str(x).strip().upper() for x in allowed_pi_types if str(x).strip()}
    if not allowed:
        logger.info("[pi_type_filter] allowed set empty -> skip filter")
        return summary.copy()

    out = summary.copy()
    before_counts = out["pi_type"].astype(str).str.strip().str.upper().value_counts(dropna=False).to_dict()

    out["pi_type"] = out["pi_type"].astype(str).str.strip().str.upper()

    before = len(out)
    out = out[out["pi_type"].isin(allowed)].copy()
    out.reset_index(drop=True, inplace=True)

    logger.info(
        "[pi_type_filter] allowed=%s before=%s after=%s dropped=%s counts_before=%s",
        sorted(allowed),
        before,
        len(out),
        before - len(out),
        before_counts,
    )

    return out


def load_summary_in_range(
    db_src: MySQLConnet,
    cfg: Config,
    start_dt: datetime,
    end_dt: datetime,
    logger: logging.Logger,
) -> pd.DataFrame:
    yyyymms = iter_yyyymm_in_range(start_dt, end_dt)
    all_df: List[pd.DataFrame] = []

    logger.info(f"[load_summary_in_range] range={start_dt}~{end_dt}")

    for yyyymm in yyyymms:
        dfm = load_summary_for_month(db_src, cfg, yyyymm, logger)
        if dfm is not None and not dfm.empty:
            all_df.append(dfm)

    if not all_df:
        return pd.DataFrame()

    df = pd.concat(all_df, ignore_index=True)
    logger.info(f"[load_summary_in_range] concat rows={len(df)}")

    df = clean_summary(df, cfg, logger)

    # source range is pi_time based
    mask = (df["pi_time"] >= start_dt) & (df["pi_time"] < end_dt)
    df = df.loc[mask].copy()

    df.reset_index(drop=True, inplace=True)
    logger.info(f"[load_summary_in_range] END: rows={len(df)} months={yyyymms}")

    return df


# =============================================================================
# Summary dedup
# =============================================================================
def dedup_summary_keep_latest_per_recipe_glass(
    summary: pd.DataFrame,
    cfg: Config,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Keep latest record per:
      line_id + aoi + model + glass_type + pi_hour + recipe_id + glass_id

    1) 同片 + 同 pi_hour + 不同 recipe_id：保留多筆。
    2) 同片 + 同 pi_hour + 同 recipe_id + 多 scan_time：只保留最新。
    3) 進入本函式前已先篩 pi_type = API。
    """
    if summary is None or summary.empty:
        return pd.DataFrame()

    need_cols = set(cfg.recipe_group_cols) | {"glass_id", "scan_time", "pi_time", "total_defect_count"}
    miss = [c for c in need_cols if c not in summary.columns]
    if miss:
        raise ValueError(f"summary missing columns: {miss}")

    tmp = summary.copy()
    sort_cols = [c for c in cfg.sort_cols if c in tmp.columns]
    order_cols = list(cfg.recipe_group_cols) + ["glass_id"] + sort_cols

    ori_len = len(tmp)
    tmp = tmp.sort_values(order_cols, ascending=True)
    tmp = tmp.drop_duplicates(subset=list(cfg.recipe_group_cols) + ["glass_id"], keep="last")
    tmp.reset_index(drop=True, inplace=True)

    logger.info(f"[keep latest] ori rows={ori_len}, kept rows={len(tmp)}")
    return tmp


# =============================================================================
# Defect fetch
# =============================================================================
def defect_table_name(yyyymm: str, aoi: str, line_id: str) -> str:
    return f"cim_defect_{yyyymm}_{str(aoi).lower()}_{str(line_id).lower()}".lower()


def fetch_defects_for_keys(
    cfg: Config,
    db_src: MySQLConnet,
    defect_tb: str,
    keys_df: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    keys_df columns:
      glass_id, scan_time

    Fetch by:
      test_time BETWEEN min/max
      sheet_id_chip_id IN (...)

    Then exact merge:
      glass_id + scan_time
    """
    if keys_df is None or keys_df.empty:
        return pd.DataFrame()

    k = keys_df[["glass_id", "scan_time"]].copy()
    k = k.dropna(subset=["glass_id", "scan_time"]).drop_duplicates()
    k["glass_id"] = k["glass_id"].astype(str).str.strip()
    k["scan_time"] = pd.to_datetime(k["scan_time"], errors="coerce")
    k = k.dropna(subset=["scan_time"])

    if k.empty:
        return pd.DataFrame()

    if not db_src.table_exists(defect_tb):
        logger.warning(f"[defect] missing `{db_src.db}`.`{defect_tb}`")
        return pd.DataFrame()

    t_min = k["scan_time"].min()
    t_max = k["scan_time"].max()
    gids = k["glass_id"].unique().tolist()

    out_chunks: List[pd.DataFrame] = []

    with db_src.engine.connect() as conn:
        for i in range(0, len(gids), cfg.batch_size):
            batch = gids[i:i + cfg.batch_size]
            bind = {f"g{j}": v for j, v in enumerate(batch)}
            in_clause = ", ".join([f":g{j}" for j in range(len(batch))])

            sql = f"""
                SELECT *
                FROM `{db_src.db}`.`{defect_tb}`
                WHERE `test_time` BETWEEN :t_min AND :t_max
                  AND `sheet_id_chip_id` IN ({in_clause})
            """

            params = dict(bind)
            params.update({"t_min": t_min, "t_max": t_max})

            df = pd.read_sql(text(sql), conn, params=params)
            if df is not None and not df.empty:
                out_chunks.append(df)

    if not out_chunks:
        return pd.DataFrame()

    defects = pd.concat(out_chunks, ignore_index=True)
    if defects.empty:
        return defects

    defects["test_time"] = pd.to_datetime(defects["test_time"], errors="coerce")
    defects["sheet_id_chip_id"] = defects["sheet_id_chip_id"].astype(str).str.strip()

    if "adc_def_code" in defects.columns:
        defects["adc_def_code"] = (
            defects["adc_def_code"]
            .astype("string")
            .str.strip()
            .replace({"": pd.NA, "nan": pd.NA, "NaN": pd.NA, "None": pd.NA, "NULL": pd.NA})
            .fillna("others")
        )

    defects.rename(columns=cfg.defect_coldict, inplace=True)

    defects = defects.merge(k, on=["glass_id", "scan_time"], how="inner")
    return defects


def load_defects_for_summary(
    cfg: Config,
    db_src: MySQLConnet,
    recipe_summary: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Fetch all needed defect rows across month/aoi/line defect tables.

    1) defect source table 月份使用 scan_time/test_time。
    2) density output table 月份使用 pi_hour。
    3) 統計維度以 recipe_summary 為準。
    """
    if recipe_summary is None or recipe_summary.empty:
        return pd.DataFrame()

    dim_cols = [
        "line_id",
        "aoi",
        "model",
        "glass_type",
        "pi_hour",
        "recipe_id",
        "glass_id",
        "scan_time",
    ]

    miss = [c for c in dim_cols if c not in recipe_summary.columns]
    if miss:
        raise ValueError(f"recipe_summary missing columns for defect merge: {miss}")

    keys = recipe_summary[dim_cols].drop_duplicates().copy()

    keys["_defect_yyyymm"] = pd.to_datetime(keys["scan_time"], errors="coerce").dt.strftime("%Y%m")
    keys["_density_yyyymm"] = pd.to_datetime(keys["pi_hour"], errors="coerce").dt.strftime("%Y%m")

    cross_month = keys[
        keys["_defect_yyyymm"].notna()
        & keys["_density_yyyymm"].notna()
        & (keys["_defect_yyyymm"] != keys["_density_yyyymm"])
    ].copy()

    if not cross_month.empty:
        logger.warning(
            "[defect] cross month rows=%s sample=%s",
            len(cross_month),
            cross_month[
                ["glass_id", "scan_time", "pi_hour", "_defect_yyyymm", "_density_yyyymm"]
            ].head(10).to_dict("records"),
        )

    keys["_yyyymm"] = keys["_defect_yyyymm"]

    out_chunks: List[pd.DataFrame] = []

    for (yyyymm, aoi, line_id), kg in keys.groupby(["_yyyymm", "aoi", "line_id"], dropna=False):
        if not yyyymm or pd.isna(yyyymm):
            continue

        tb = defect_table_name(str(yyyymm), str(aoi), str(line_id))

        def_rows = fetch_defects_for_keys(
            cfg,
            db_src,
            tb,
            kg[["glass_id", "scan_time"]],
            logger,
        )

        if def_rows is None or def_rows.empty:
            continue

        dims = kg.drop(columns=["_yyyymm", "_defect_yyyymm", "_density_yyyymm"]).drop_duplicates().copy()

        conflict_cols = [
            "line_id",
            "aoi",
            "model",
            "glass_type",
            "pi_hour",
            "recipe_id",
        ]

        drop_cols = [c for c in conflict_cols if c in def_rows.columns]
        def_clean = def_rows.drop(columns=drop_cols, errors="ignore").copy()

        d = def_clean.merge(
            dims,
            on=["glass_id", "scan_time"],
            how="inner",
        )

        if not d.empty:
            out_chunks.append(d)

    if not out_chunks:
        return pd.DataFrame()

    out = pd.concat(out_chunks, ignore_index=True)

    need_after_merge = [
        "line_id",
        "aoi",
        "model",
        "glass_type",
        "pi_hour",
        "recipe_id",
        "glass_id",
        "scan_time",
    ]

    miss2 = [c for c in need_after_merge if c not in out.columns]
    if miss2:
        raise ValueError(
            f"defects after merge missing columns: {miss2}; "
            f"columns={out.columns.tolist()}"
        )

    if "adc_def_code" not in out.columns:
        out["adc_def_code"] = "others"

    out["adc_def_code"] = (
        out["adc_def_code"]
        .astype("string")
        .fillna("others")
        .astype(str)
        .str.strip()
        .replace({"": "others", "nan": "others", "NaN": "others", "None": "others"})
    )

    if "defect_size" not in out.columns:
        out["defect_size"] = ""

    if "aoi" not in out.columns:
        out["aoi"] = ""

    raw_empty_mask = out["defect_size"].apply(is_empty_like)
    aoi200_mask = out["aoi"].astype(str).str.lower().eq("aoi200")

    logger.info(
        "[defect] raw defect_size empty rows=%s, aoi200_empty_rows=%s, total_rows=%s",
        int(raw_empty_mask.sum()),
        int((raw_empty_mask & aoi200_mask).sum()),
        len(out),
    )

    out["defect_size"] = out.apply(
        lambda r: normalize_defect_size_for_aoi(
            r.get("defect_size", ""),
            r.get("aoi", ""),
        ),
        axis=1,
    )

    logger.info(
        "[defect] normalized defect_size counts=%s",
        out["defect_size"].value_counts(dropna=False).to_dict(),
    )

    logger.info(f"[defect] all fetched rows={len(out)}")
    logger.info(f"[defect] columns={out.columns.tolist()}")

    return out


# =============================================================================
# Build recipe summary
# =============================================================================
def build_recipe_summary(
    recipe_summary_src: pd.DataFrame,
    defects: pd.DataFrame,
    cfg: Config,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Output table:
      density_recipe_summary_yyyymm

    Grain:
      line_id + aoi + model + glass_type + pi_hour + recipe_id

    recipe_total_defect_cnt 來自 cim_pi_glass.total_defect_qty。
    recipe_raw_defect_cnt 來自 cim_defect rows count。
    """
    if recipe_summary_src is None or recipe_summary_src.empty:
        return pd.DataFrame()

    recipe_keys = list(cfg.recipe_group_cols)
    src = recipe_summary_src.copy()

    if "total_defect_count" not in src.columns:
        src["total_defect_count"] = 0

    src["total_defect_count"] = (
        pd.to_numeric(src["total_defect_count"], errors="coerce")
        .fillna(0)
        .astype(int)
    )

    g = (
        src.groupby(recipe_keys, dropna=False)
        .agg(
            recipe_total_glass_cnt=("glass_id", lambda s: int(s.astype(str).nunique())),
            recipe_total_defect_cnt=("total_defect_count", "sum"),
            glass=("glass_id", lambda s: join_unique_sorted(list(s))),
        )
        .reset_index()
    )

    if defects is not None and not defects.empty:
        raw_cnt = (
            defects.groupby(recipe_keys, dropna=False)
            .size()
            .reset_index(name="recipe_raw_defect_cnt")
        )
        g = g.merge(raw_cnt, on=recipe_keys, how="left")
    else:
        g["recipe_raw_defect_cnt"] = 0

    for c in ["recipe_total_glass_cnt", "recipe_total_defect_cnt", "recipe_raw_defect_cnt"]:
        g[c] = pd.to_numeric(g[c], errors="coerce").fillna(0).astype(int)

    g["recipe_total_defect_gap"] = (
        g["recipe_total_defect_cnt"] - g["recipe_raw_defect_cnt"]
    ).astype(int)

    g["recipe_total_density"] = (
        g["recipe_total_defect_cnt"]
        / g["recipe_total_glass_cnt"].replace(0, pd.NA)
    ).fillna(0).round(3)

    cols = recipe_keys + [
        "recipe_total_glass_cnt",
        "recipe_total_defect_cnt",
        "recipe_total_density",
        "recipe_raw_defect_cnt",
        "recipe_total_defect_gap",
        "glass",
    ]

    g = g[cols].copy()

    logger.info(f"[build_recipe_summary] rows={len(g)}")
    return g


# =============================================================================
# Build tab summary
# =============================================================================
def build_tab_summary(
    recipe_summary: pd.DataFrame,
    cfg: Config,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Output table:
      density_tab_summary_yyyymm

    Grain:
      line_id + aoi + model + glass_type + pi_hour + recipe_family + tab_name

    特別規則：
      aoi100 / aoi300 的 API 資料已在 recipe_id_to_tabs() 中展開到所有 tab。
    """
    if recipe_summary is None or recipe_summary.empty:
        return pd.DataFrame()

    base_keys = list(cfg.base_group_cols)

    x = recipe_summary.copy()
    x["__tabs"] = x.apply(
        lambda r: recipe_id_to_tabs(
            recipe_id=r.get("recipe_id", ""),
            cfg=cfg,
            aoi=r.get("aoi", ""),
        ),
        axis=1,
    )

    x = x.explode("__tabs").rename(columns={"__tabs": "tab_name"})
    x = x.dropna(subset=["tab_name"])
    x["tab_name"] = x["tab_name"].astype(str).str.strip()
    x = x[x["tab_name"].astype(str).str.len() > 0].copy()

    if x.empty:
        logger.warning("[build_tab_summary] no recipe matched tab rule")
        return pd.DataFrame()

    x["recipe_family"] = x["tab_name"].apply(lambda v: tab_to_recipe_family(v, cfg))

    glass_rows: List[Dict[str, Any]] = []

    for _, r in x.iterrows():
        base = {k: r[k] for k in base_keys}
        base["recipe_family"] = r["recipe_family"]
        base["tab_name"] = r["tab_name"]

        for gid in split_glass_string(r.get("glass", "")):
            rr = dict(base)
            rr["glass_id"] = gid
            glass_rows.append(rr)

    glass_df = pd.DataFrame(glass_rows)

    tab = (
        x.groupby(base_keys + ["recipe_family", "tab_name"], dropna=False)
        .agg(
            tab_total_defect_cnt=("recipe_total_defect_cnt", "sum"),
            tab_raw_defect_cnt=("recipe_raw_defect_cnt", "sum"),
            tab_total_defect_gap=("recipe_total_defect_gap", "sum"),
            recipe_list=("recipe_id", lambda s: join_unique_sorted(list(s))),
        )
        .reset_index()
    )

    if glass_df is not None and not glass_df.empty:
        glass_agg = (
            glass_df.groupby(base_keys + ["recipe_family", "tab_name"], dropna=False)
            .agg(
                tab_total_glass_cnt=("glass_id", lambda s: int(pd.Series(s).astype(str).nunique())),
                glass=("glass_id", lambda s: join_unique_sorted(list(s))),
            )
            .reset_index()
        )

        tab = tab.merge(
            glass_agg,
            on=base_keys + ["recipe_family", "tab_name"],
            how="left",
        )
    else:
        tab["tab_total_glass_cnt"] = 0
        tab["glass"] = ""

    for c in [
        "tab_total_glass_cnt",
        "tab_total_defect_cnt",
        "tab_raw_defect_cnt",
        "tab_total_defect_gap",
    ]:
        tab[c] = pd.to_numeric(tab[c], errors="coerce").fillna(0).astype(int)

    tab["tab_total_density"] = (
        tab["tab_total_defect_cnt"]
        / tab["tab_total_glass_cnt"].replace(0, pd.NA)
    ).fillna(0).round(3)

    cols = base_keys + [
        "recipe_family",
        "tab_name",
        "tab_total_glass_cnt",
        "tab_total_defect_cnt",
        "tab_total_density",
        "tab_raw_defect_cnt",
        "tab_total_defect_gap",
        "recipe_list",
        "glass",
    ]

    tab = tab[cols].copy()

    logger.info(f"[build_tab_summary] rows={len(tab)}")
    return tab


# =============================================================================
# Build code summary
# =============================================================================
def _normalize_size_to_s_m_l_o(s: pd.Series) -> pd.Series:
    mapping = {
        "S": "S",
        "SMALL": "S",
        "M": "M",
        "MID": "M",
        "MIDDLE": "M",
        "L": "L",
        "LARGE": "L",
        "O": "O",
        "OVER": "O",
    }

    x = s.astype("string").fillna("").astype(str).str.upper().str.strip()
    return x.map(mapping).fillna("")


def _build_recipe_glass_time_lookup(
    recipe_summary_src: pd.DataFrame,
    cfg: Config,
) -> Dict[Tuple[str, ...], Dict[str, str]]:
    """
    建立每個 recipe group 底下：
      glass_id -> test_time

    test_time = recipe_summary_src.scan_time = cim_pi_glass.test_time。
    recipe_summary_src 已是 dedup 後母體。
    """
    lookup: Dict[Tuple[str, ...], Dict[str, str]] = {}

    if recipe_summary_src is None or recipe_summary_src.empty:
        return lookup

    recipe_keys = list(cfg.recipe_group_cols)
    need_cols = recipe_keys + ["glass_id", "scan_time"]

    miss = [c for c in need_cols if c not in recipe_summary_src.columns]
    if miss:
        return lookup

    src = recipe_summary_src[need_cols].copy()
    src["glass_id"] = src["glass_id"].astype(str).str.strip()
    src["scan_time"] = pd.to_datetime(src["scan_time"], errors="coerce")

    src = src.dropna(subset=["glass_id", "scan_time"]).copy()
    src = src[src["glass_id"].astype(str).str.len() > 0].copy()

    if src.empty:
        return lookup

    for k, g in src.groupby(recipe_keys, dropna=False):
        key = tuple(str(x) for x in k)

        d: Dict[str, str] = {}
        for _, r in g.iterrows():
            gid = str(r["glass_id"]).strip()
            if not gid:
                continue

            d[gid] = format_dt_value(r["scan_time"])

        lookup[key] = d

    return lookup


def _build_glass_size_detail_for_code(
    recipe_glasses: List[str],
    sub_code_defects: pd.DataFrame,
    glass_time_map: Optional[Dict[str, str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    output:
      每個 recipe group 的完整 glass 母體都會出現。
      每片 glass 都會有 test_time。
      對目前 adc_def_code 無 defect 的 glass，S/M/L/O/T = 0。
    """
    glass_time_map = glass_time_map or {}

    detail: Dict[str, Dict[str, Any]] = {
        gid: {
            "test_time": glass_time_map.get(gid, ""),
            "S": 0,
            "M": 0,
            "L": 0,
            "O": 0,
            "T": 0,
        }
        for gid in recipe_glasses
    }

    if sub_code_defects is None or sub_code_defects.empty:
        return detail

    d = sub_code_defects.copy()
    d["__sz"] = _normalize_size_to_s_m_l_o(
        d.get("defect_size", pd.Series([], dtype="object"))
    )

    d = d[d["__sz"].isin(["S", "M", "L", "O"])].copy()

    if d.empty:
        return detail

    pv = (
        d.groupby(["glass_id", "__sz"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )

    for sz in ["S", "M", "L", "O"]:
        if sz not in pv.columns:
            pv[sz] = 0

    for _, r in pv.iterrows():
        gid = str(r["glass_id"]).strip()

        if gid not in detail:
            detail[gid] = {
                "test_time": glass_time_map.get(gid, ""),
                "S": 0,
                "M": 0,
                "L": 0,
                "O": 0,
                "T": 0,
            }

        s_cnt = int(r["S"] or 0)
        m_cnt = int(r["M"] or 0)
        l_cnt = int(r["L"] or 0)
        o_cnt = int(r["O"] or 0)

        detail[gid].update({
            "S": s_cnt,
            "M": m_cnt,
            "L": l_cnt,
            "O": o_cnt,
            "T": s_cnt + m_cnt + l_cnt + o_cnt,
        })

    return detail


def build_code_summary(
    recipe_summary: pd.DataFrame,
    defects: pd.DataFrame,
    cfg: Config,
    logger: logging.Logger,
    recipe_summary_src: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Output table:
      density_code_summary_yyyymm

    Grain:
      line_id + aoi + model + glass_type + pi_hour + recipe_id + adc_def_code

    glass_size_detail:
      full recipe glass population + current adc_def_code size distribution + test_time
    """
    if recipe_summary is None or recipe_summary.empty:
        return pd.DataFrame()

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    recipe_keys = list(cfg.recipe_group_cols)
    code_keys = list(cfg.code_group_cols)

    recipe_base = recipe_summary.copy()

    target_codes = [str(c).strip() for c in (cfg.target_defect_codes or []) if str(c).strip()]
    if "others" not in target_codes:
        target_codes.append("others")

    actual_codes_df = pd.DataFrame(columns=recipe_keys + ["adc_def_code"])

    if defects is not None and not defects.empty:
        actual_codes_df = (
            defects[recipe_keys + ["adc_def_code"]]
            .dropna(subset=["adc_def_code"])
            .drop_duplicates()
            .copy()
        )

    target_rows = []

    for _, r in recipe_base[recipe_keys].drop_duplicates().iterrows():
        base = {k: r[k] for k in recipe_keys}

        for code in target_codes:
            rr = dict(base)
            rr["adc_def_code"] = code
            target_rows.append(rr)

    target_codes_df = pd.DataFrame(target_rows)

    all_code_keys = pd.concat([target_codes_df, actual_codes_df], ignore_index=True)
    all_code_keys = all_code_keys.drop_duplicates(subset=code_keys).reset_index(drop=True)

    out = all_code_keys.merge(
        recipe_summary[
            recipe_keys
            + [
                "recipe_total_glass_cnt",
                "recipe_total_defect_cnt",
                "recipe_total_density",
                "recipe_raw_defect_cnt",
                "recipe_total_defect_gap",
                "glass",
            ]
        ],
        on=recipe_keys,
        how="left",
    )

    if defects is not None and not defects.empty:
        code_cnt = (
            defects.groupby(code_keys, dropna=False)
            .size()
            .reset_index(name="defect_cnt")
        )

        code_glass = (
            defects.groupby(code_keys, dropna=False)["glass_id"]
            .apply(lambda s: int(pd.Series(s).astype(str).nunique()))
            .reset_index(name="def_glass_cnt")
        )

        d2 = defects.copy()
        d2["__sz"] = _normalize_size_to_s_m_l_o(d2["defect_size"])

        size_cnt = (
            d2[d2["__sz"].isin(["S", "M", "L", "O"])]
            .groupby(code_keys + ["__sz"], dropna=False)
            .size()
            .unstack(fill_value=0)
            .reset_index()
        )

        for sz in ["S", "M", "L", "O"]:
            if sz not in size_cnt.columns:
                size_cnt[sz] = 0

        size_cnt = size_cnt.rename(columns={
            "S": "small_defect_count",
            "M": "middle_defect_count",
            "L": "large_defect_count",
            "O": "over_defect_count",
        })

        out = out.merge(code_cnt, on=code_keys, how="left")
        out = out.merge(code_glass, on=code_keys, how="left")
        out = out.merge(
            size_cnt[
                code_keys
                + [
                    "small_defect_count",
                    "middle_defect_count",
                    "large_defect_count",
                    "over_defect_count",
                ]
            ],
            on=code_keys,
            how="left",
        )
    else:
        out["defect_cnt"] = 0
        out["def_glass_cnt"] = 0
        out["small_defect_count"] = 0
        out["middle_defect_count"] = 0
        out["large_defect_count"] = 0
        out["over_defect_count"] = 0

    for c in [
        "recipe_total_glass_cnt",
        "recipe_total_defect_cnt",
        "recipe_raw_defect_cnt",
        "recipe_total_defect_gap",
        "defect_cnt",
        "def_glass_cnt",
        "small_defect_count",
        "middle_defect_count",
        "large_defect_count",
        "over_defect_count",
    ]:
        if c not in out.columns:
            out[c] = 0

        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0).astype(int)

    out["glass_cnt"] = pd.to_numeric(out["recipe_total_glass_cnt"], errors="coerce").fillna(0).astype(int)

    out["recipe_code_density"] = (
        out["defect_cnt"]
        / out["recipe_total_glass_cnt"].replace(0, pd.NA)
    ).fillna(0).round(3)

    out["density"] = out["recipe_code_density"]

    defect_lookup: Dict[Tuple[str, ...], pd.DataFrame] = {}

    if defects is not None and not defects.empty:
        for k, g in defects.groupby(code_keys, dropna=False):
            defect_lookup[tuple(str(x) for x in k)] = g.copy()

    glass_time_lookup = _build_recipe_glass_time_lookup(
        recipe_summary_src=recipe_summary_src,
        cfg=cfg,
    )

    glass_detail_list = []

    for _, r in out.iterrows():
        recipe_glasses = [
            x.strip()
            for x in str(r.get("glass", "")).split(",")
            if x.strip()
        ]

        code_key = tuple(str(r[c]) for c in code_keys)
        recipe_key = tuple(str(r[c]) for c in recipe_keys)

        sub = defect_lookup.get(code_key, pd.DataFrame())
        glass_time_map = glass_time_lookup.get(recipe_key, {})

        glass_detail_list.append(
            _build_glass_size_detail_for_code(
                recipe_glasses=recipe_glasses,
                sub_code_defects=sub,
                glass_time_map=glass_time_map,
            )
        )

    out["glass_size_detail"] = glass_detail_list

    out["comment"] = ""
    out["action"] = ""
    out["Editor"] = ""
    out["modify_time"] = now_str

    cols = code_keys + [
        "recipe_total_glass_cnt",
        "recipe_total_defect_cnt",
        "recipe_total_density",
        "recipe_raw_defect_cnt",
        "recipe_total_defect_gap",
        "defect_cnt",
        "def_glass_cnt",
        "glass_cnt",
        "recipe_code_density",
        "density",
        "small_defect_count",
        "middle_defect_count",
        "large_defect_count",
        "over_defect_count",
        "glass",
        "glass_size_detail",
        "comment",
        "action",
        "Editor",
        "modify_time",
    ]

    out = out[cols].copy()

    logger.info(f"[build_code_summary] rows={len(out)}")
    return out


# =============================================================================
# Write helpers
# =============================================================================
def _jsonify_object_columns(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    import numpy as np

    out = df.copy()

    obj_cols = [c for c in out.columns if out[c].dtype == "object"]
    cols_need_json = []

    for c in obj_cols:
        sample = out[c].dropna().head(50).tolist()

        if any(isinstance(v, (dict, list)) for v in sample):
            cols_need_json.append(c)

    if not cols_need_json:
        return out

    def _to_json(v):
        if v is None:
            return None

        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False)

        if isinstance(v, float) and np.isnan(v):
            return None

        try:
            if pd.isna(v):
                return None
        except Exception:
            pass

        return v

    for c in cols_need_json:
        out[c] = out[c].apply(_to_json).astype("object")

    logger.info(f"[write] jsonified cols={cols_need_json}")
    return out


def _mysql_type_for_series(s: pd.Series) -> str:
    if pd.api.types.is_integer_dtype(s):
        return "BIGINT"

    if pd.api.types.is_float_dtype(s):
        return "DOUBLE"

    if pd.api.types.is_datetime64_any_dtype(s):
        return "DATETIME"

    return "LONGTEXT"


def _drop_deprecated_columns_if_needed(
    db_out: MySQLConnet,
    table_name: str,
    deprecated_cols: Tuple[str, ...],
    logger: logging.Logger,
):
    if not deprecated_cols:
        return

    if not db_out.table_exists(table_name):
        return

    insp = inspect(db_out.engine)
    current_cols = [c["name"] for c in insp.get_columns(table_name, schema=db_out.db)]
    to_drop = [c for c in deprecated_cols if c in current_cols]

    if not to_drop:
        return

    with db_out.engine.begin() as conn:
        for c in to_drop:
            conn.execute(text(f"ALTER TABLE `{db_out.db}`.`{table_name}` DROP COLUMN `{c}`"))

    logger.warning(f"[write] dropped deprecated cols from `{db_out.db}`.`{table_name}`: {to_drop}")


def write_overwrite_groups(
    db_out: MySQLConnet,
    table_name: str,
    df: pd.DataFrame,
    key_cols: Tuple[str, ...],
    logger: logging.Logger,
    chunksize: int = 20000,
    deprecated_cols: Tuple[str, ...] = tuple(),
):
    """
    DELETE by touched key groups + INSERT new rows.
    """
    if df is None or df.empty:
        logger.info(f"[write] {table_name} empty -> skip")
        return

    df = df.copy()
    df = _jsonify_object_columns(df, logger)

    _drop_deprecated_columns_if_needed(db_out, table_name, deprecated_cols, logger)

    if not db_out.table_exists(table_name):
        df.head(0).to_sql(
            name=table_name,
            con=db_out.engine,
            schema=db_out.db,
            if_exists="fail",
            index=False,
        )
        logger.info(f"[write] created `{db_out.db}`.`{table_name}`")

    insp = inspect(db_out.engine)
    tgt_cols = [c["name"] for c in insp.get_columns(table_name, schema=db_out.db)]
    tgt_set = set(tgt_cols)

    new_cols = [c for c in df.columns if c not in tgt_set]

    if new_cols:
        with db_out.engine.begin() as conn:
            for c in new_cols:
                col_type = _mysql_type_for_series(df[c])
                conn.execute(text(
                    f"ALTER TABLE `{db_out.db}`.`{table_name}` ADD COLUMN `{c}` {col_type} NULL"
                ))

        logger.info(f"[write] `{table_name}` alter add cols={new_cols}")

        insp = inspect(db_out.engine)
        tgt_cols = [c["name"] for c in insp.get_columns(table_name, schema=db_out.db)]

    for c in tgt_cols:
        if c not in df.columns:
            df[c] = None

    df = df[tgt_cols].copy()

    valid_key_cols = [c for c in key_cols if c in df.columns]

    if not valid_key_cols:
        raise ValueError(f"[write] no valid key cols for {table_name}: {key_cols}")

    ts = int(datetime.now().timestamp())
    stg = f"__stg_{table_name}_{ts}"
    keys = f"__keys_{table_name}_{ts}"

    stg_qual = f"`{db_out.db}`.`{stg}`"
    keys_qual = f"`{db_out.db}`.`{keys}`"
    tgt_qual = f"`{db_out.db}`.`{table_name}`"

    df.to_sql(
        name=stg,
        con=db_out.engine,
        schema=db_out.db,
        if_exists="replace",
        index=False,
        chunksize=chunksize,
        method="multi",
    )

    df[valid_key_cols].drop_duplicates().to_sql(
        name=keys,
        con=db_out.engine,
        schema=db_out.db,
        if_exists="replace",
        index=False,
        chunksize=chunksize,
        method="multi",
    )

    join_cond = " AND ".join([f"t.`{c}` <=> k.`{c}`" for c in valid_key_cols])
    col_list = ", ".join([f"`{c}`" for c in tgt_cols])

    with db_out.engine.begin() as conn:
        deleted = (conn.execute(text(f"""
            DELETE t
            FROM {tgt_qual} t
            JOIN {keys_qual} k
              ON {join_cond}
        """)).rowcount or 0)

        inserted = (conn.execute(text(f"""
            INSERT INTO {tgt_qual} ({col_list})
            SELECT {col_list}
            FROM {stg_qual}
        """)).rowcount or 0)

        conn.execute(text(f"DROP TABLE IF EXISTS {stg_qual}"))
        conn.execute(text(f"DROP TABLE IF EXISTS {keys_qual}"))

    logger.info(f"[write] `{db_out.db}`.`{table_name}` deleted={deleted} inserted={inserted}")


# =============================================================================
# Run once
# =============================================================================
def run_once_for_range(
    cfg: Config,
    start_dt: datetime,
    end_dt: datetime,
    logger: logging.Logger,
) -> Dict[str, pd.DataFrame]:
    db_src = MySQLConnet(cfg.src_db, cfg.host, cfg.username, cfg.password)
    db_out = MySQLConnet(cfg.out_db, cfg.host, cfg.username, cfg.password)

    summary = load_summary_in_range(db_src, cfg, start_dt, end_dt, logger)

    if summary is None or summary.empty:
        logger.warning("[run_once] summary empty -> no output")
        return {
            "tab": pd.DataFrame(),
            "recipe": pd.DataFrame(),
            "code": pd.DataFrame(),
        }

    summary = filter_summary_by_pi_type(
        summary=summary,
        allowed_pi_types=cfg.allowed_pi_types,
        logger=logger,
    )

    if summary is None or summary.empty:
        logger.warning("[run_once] summary empty after pi_type filter -> no output")
        return {
            "tab": pd.DataFrame(),
            "recipe": pd.DataFrame(),
            "code": pd.DataFrame(),
        }

    recipe_summary_src = dedup_summary_keep_latest_per_recipe_glass(summary, cfg, logger)

    defects = load_defects_for_summary(cfg, db_src, recipe_summary_src, logger)

    recipe_summary = build_recipe_summary(recipe_summary_src, defects, cfg, logger)
    tab_summary = build_tab_summary(recipe_summary, cfg, logger)
    code_summary = build_code_summary(
        recipe_summary=recipe_summary,
        defects=defects,
        cfg=cfg,
        logger=logger,
        recipe_summary_src=recipe_summary_src,
    )

    if cfg.write_out:
        for name, df, tpl, key_cols in [
            ("tab", tab_summary, cfg.tab_table_tpl, cfg.tab_group_cols),
            ("recipe", recipe_summary, cfg.recipe_table_tpl, cfg.recipe_group_cols),
            ("code", code_summary, cfg.code_table_tpl, cfg.code_group_cols),
        ]:
            if df is None or df.empty:
                logger.info(f"[write] {name} output empty -> skip")
                continue

            x = df.copy()
            x["_yyyymm"] = pd.to_datetime(x["pi_hour"], errors="coerce").dt.strftime("%Y%m")

            for yyyymm, part in x.groupby("_yyyymm", dropna=True):
                table_name = tpl.replace("yyyymm", str(yyyymm)).lower()

                deprecated = ()

                if name == "code":
                    deprecated = (
                        "tab_family",
                        "tab_total_defect_cnt",
                        "tab_total_glass_cnt",
                        "tab_total_density",
                        "tab_metric_detail",
                    )

                write_overwrite_groups(
                    db_out=db_out,
                    table_name=table_name,
                    df=part.drop(columns=["_yyyymm"]),
                    key_cols=key_cols,
                    logger=logger,
                    deprecated_cols=deprecated,
                )

    return {
        "tab": tab_summary,
        "recipe": recipe_summary,
        "code": code_summary,
    }


# =============================================================================
# Modes
# =============================================================================
def mode_loop(cfg: Config, logger: logging.Logger):
    logger.info(
        f"[mode=loop] every {cfg.loop_minutes} min; "
        f"lookback={cfg.lookback_minutes} min; "
        f"allowed_pi_types={cfg.allowed_pi_types}"
    )

    while True:
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(minutes=cfg.lookback_minutes)

        try:
            run_once_for_range(cfg, start_dt, end_dt, logger)
        except Exception as e:
            logger.exception(f"[loop] failed: {e}")

        time.sleep(cfg.loop_minutes * 60)


def mode_month(cfg: Config, logger: logging.Logger, yyyymm: Optional[str] = None):
    if not yyyymm:
        yyyymm = datetime.now().strftime("%Y%m")

    start_dt = datetime.strptime(yyyymm + "01", "%Y%m%d")
    end_dt = next_month_start(start_dt)

    logger.info(
        f"[mode=month] yyyymm={yyyymm} range={start_dt}~{end_dt} "
        f"allowed_pi_types={cfg.allowed_pi_types}"
    )

    return run_once_for_range(cfg, start_dt, end_dt, logger)


def mode_days(cfg: Config, logger: logging.Logger, days: int):
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=days)

    logger.info(
        f"[mode=days] days={days} range={start_dt}~{end_dt} "
        f"allowed_pi_types={cfg.allowed_pi_types}"
    )

    return run_once_for_range(cfg, start_dt, end_dt, logger)


# =============================================================================
# CLI
# =============================================================================
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="CIM density job (3-layer output, pi_type API only)")

    p.add_argument("--mode", choices=["loop", "month", "days"], default="loop")
    p.add_argument("--month", default="", help="YYYYMM for month mode")
    p.add_argument("--days", type=int, default=7, help="N days for days mode")

    p.add_argument("--host", default="10.97.142.217")
    p.add_argument("--username", default="l6a01_user")
    p.add_argument("--password", default="l6a01$user")

    p.add_argument("--src_db", default="cim_piaoi")
    p.add_argument("--out_db", default="piaoi_density")

    p.add_argument("--loop_minutes", type=int, default=10)
    p.add_argument("--lookback_minutes", type=int, default=180)

    p.add_argument("--write_out", action="store_true")

    p.add_argument(
        "--allowed_pi_types",
        default="API",
        help="Comma-separated pi_type filter. Default: API. Use ALL to disable filter.",
    )

    return p


def parse_allowed_pi_types(s: str) -> Tuple[str, ...]:
    v = str(s or "").strip()

    if not v:
        return ("API",)

    if v.upper() == "ALL":
        return tuple()

    parts = [x.strip().upper() for x in v.split(",") if x.strip()]
    return tuple(parts)


def main(argv: Optional[List[str]] = None):
    logger = setup_logger()

    parser = build_parser()
    args, _unknown = parser.parse_known_args(argv)

    cfg = Config(
        host=args.host,
        username=args.username,
        password=args.password,
        src_db=args.src_db,
        out_db=args.out_db,
        loop_minutes=args.loop_minutes,
        lookback_minutes=args.lookback_minutes,
        write_out=bool(args.write_out),
        allowed_pi_types=parse_allowed_pi_types(args.allowed_pi_types),
    )

    logger.info(
        f"[start] mode={args.mode} src_db={cfg.src_db} "
        f"out_db={cfg.out_db} write_out={cfg.write_out} "
        f"allowed_pi_types={cfg.allowed_pi_types}"
    )

    if args.mode == "loop":
        mode_loop(cfg, logger)
    elif args.mode == "month":
        mode_month(cfg, logger, yyyymm=args.month.strip() or None)
    elif args.mode == "days":
        mode_days(cfg, logger, days=args.days)
    else:
        raise ValueError(f"unknown mode: {args.mode}")


if __name__ == "__main__":
    main()


"""
Usage:
python cim_density_job.py --mode loop  --write_out --loop_minutes 10 --lookback_minutes 180
python cim_density_job.py --mode month --month 202605 --write_out
python cim_density_job.py --mode month --month 202607 --write_out
python cim_density_job.py --mode days  --days 5 --write_out

預設只取 pi_type=API：
python cim_density_job.py --mode month --month 202607 --write_out

若要不篩 pi_type：
python cim_density_job.py --mode month --month 202607 --write_out --allowed_pi_types ALL

若要同時取 API/BPI：
python cim_density_job.py --mode month --month 202607 --write_out --allowed_pi_types API,BPI

改版後建議重跑：
python cim_density_job.py --mode month --month 202606 --write_out
python cim_density_job.py --mode month --month 202607 --write_out
"""