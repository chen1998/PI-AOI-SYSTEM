#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
build_density_recipe_same_point_job.py

目的：
  針對 AOI Density 的 PISpot(Total) / UPI(Total) 新增 recipe 母體同點分析資料。

資料來源：
  1. piaoi_density.density_code_summary_yyyymm
     - 使用 glass_size_detail 取得 recipe_total_glass 母體所有 glass_id + test_time
     - 不再回查 cim_pi_glass_yyyymm

  2. cim_piaoi.cim_defect_yyyymm_aoi_line
     - 依 glass_id + test_time exact match 撈 defect raw
     - img_url 拼接邏輯對齊 routers/aoi_density_defect_map.py
     - 目前只支援 202602 後邏輯：
         img_file_url_path -> AIDI_URL
         image_file_path   -> BASE_URL fallback

輸出：
  piaoi_density.density_recipe_same_point_yyyymm

輸出 grain：
  line_id + aoi + model + glass_type + pi_hour + recipe_id + offset

輸出欄位：
  common_cnt
  common_glass_cnt
  common_points_details

同點定義：
  同一 recipe 母體內，不同 glass 的 defect 點距離 <= offset_um，
  透過 graph connected component 建立 cluster。
  每個 cluster 至少需要 2 片不同 glass 才算同點。

offset：
  20,30,40,50,60,70,80,90,100
  每個 recipe group 固定輸出 9 筆，即使沒有同點也寫 common_cnt=0。
"""

import argparse
import json
import logging
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine


# =============================================================================
# Logging
# =============================================================================
def setup_logger(
    log_dir: str = "logs",
    name: str = "build_density_recipe_same_point_job",
) -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s [%(funcName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    fh = TimedRotatingFileHandler(
        os.path.join(log_dir, f"{name}.log"),
        when="D",
        interval=1,
        backupCount=95,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


logger = setup_logger()


# =============================================================================
# Config
# =============================================================================
BASE_URL = "http://10.97.139.98:1454/"
AIDI_URL = "http://l6apaimg103/dms/CELAIDI_L6A/"


@dataclass
class Config:
    host: str = "10.97.142.217"
    username: str = "l6a01_user"
    password: str = "l6a01$user"

    density_db: str = "piaoi_density"
    cim_db: str = "cim_piaoi"

    density_code_tpl: str = "density_code_summary_yyyymm"
    defect_tpl: str = "cim_defect_yyyymm_aoi_line"
    out_tpl: str = "density_recipe_same_point_yyyymm"

    offsets_um: Tuple[int, ...] = (20, 30, 40, 50, 60, 70, 80, 90, 100)

    loop_minutes: int = 10
    lookback_minutes: int = 180
    batch_size: int = 800
    write_out: bool = False

    # 若 density_code_summary 同一個 recipe grain 有多個 adc_def_code，
    # 優先使用 adc_def_code = others 的 row 取得完整母體 glass_size_detail。
    prefer_adc_def_code: str = "others"


RECIPE_GRAIN_COLS = [
    "line_id",
    "aoi",
    "model",
    "glass_type",
    "pi_hour",
    "recipe_id",
]

OUT_COLS = RECIPE_GRAIN_COLS + [
    "offset",
    "common_cnt",
    "common_glass_cnt",
    "common_points_details",
    "gen_time",
]


# =============================================================================
# DB
# =============================================================================
class MySQLDB:
    def __init__(self, dbname: str, cfg: Config):
        self.db = dbname
        self.engine: Engine = create_engine(
            f"mysql+pymysql://{cfg.username}:{cfg.password}@{cfg.host}/{dbname}?charset=utf8mb4",
            pool_pre_ping=True,
            pool_recycle=3600,
        )

    def table_exists(self, table_name: str) -> bool:
        insp = inspect(self.engine)
        return insp.has_table(table_name, schema=self.db)

    def query_df(self, sql: str, params: Optional[dict] = None) -> pd.DataFrame:
        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params or {})

    def execute(self, sql: str, params: Optional[dict] = None):
        with self.engine.begin() as conn:
            return conn.execute(text(sql), params or {})


# =============================================================================
# Basic helpers
# =============================================================================
def clean_text(v: Any) -> str:
    if v is None:
        return ""

    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass

    s = str(v).strip()
    if s.lower() in {"", "nan", "none", "null", "nat", "<na>", "undefined"}:
        return ""

    return s


def parse_dt(v: Any) -> Optional[datetime]:
    if v is None:
        return None

    s = str(v or "").strip()
    if not s:
        return None

    s = s.replace("T", " ").replace(".000", "").strip()

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass

    try:
        ts = pd.to_datetime(s, errors="coerce")
        if pd.isna(ts):
            return None
        return ts.to_pydatetime()
    except Exception:
        return None


def format_dt(v: Any) -> str:
    try:
        ts = pd.to_datetime(v, errors="coerce")
        if pd.isna(ts):
            return ""
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_month_start(dt: datetime) -> datetime:
    if dt.month == 12:
        return dt.replace(
            year=dt.year + 1,
            month=1,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

    return dt.replace(
        month=dt.month + 1,
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )


def iter_yyyymm_in_range(start_dt: datetime, end_dt: datetime) -> List[str]:
    if end_dt < start_dt:
        start_dt, end_dt = end_dt, start_dt

    out: List[str] = []
    cur = month_start(start_dt)

    while cur < end_dt:
        out.append(cur.strftime("%Y%m"))
        cur = next_month_start(cur)

    return out


def defect_table_name(cfg: Config, yyyymm: str, aoi: Any, line_id: Any) -> str:
    return (
        cfg.defect_tpl
        .replace("yyyymm", str(yyyymm))
        .replace("aoi", clean_text(aoi).lower())
        .replace("line", clean_text(line_id).lower())
        .lower()
    )


def density_code_table_name(cfg: Config, yyyymm: str) -> str:
    return cfg.density_code_tpl.replace("yyyymm", str(yyyymm)).lower()


def out_table_name(cfg: Config, yyyymm: str) -> str:
    return cfg.out_tpl.replace("yyyymm", str(yyyymm)).lower()


def safe_json_loads(v: Any) -> Dict[str, Any]:
    if isinstance(v, dict):
        return v

    if isinstance(v, str):
        s = v.strip()
        if not s:
            return {}

        try:
            obj = json.loads(s)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}

    return {}


def parse_glass_size_detail(v: Any) -> Dict[str, datetime]:
    """
    解析 density_code_summary.glass_size_detail。

    input:
      {
        "GLASS_ID": {
          "test_time": "2026-07-01 00:10:23",
          "S": 0,
          "M": 0,
          "L": 1,
          "O": 0,
          "T": 1
        }
      }

    output:
      {
        "GLASS_ID": datetime(...)
      }

    注意：
      這裡不看 T 是否 > 0。
      因為 recipe 母體同點需要完整 recipe_total_glass 母體。
    """
    obj = safe_json_loads(v)
    out: Dict[str, datetime] = {}

    if not obj:
        return out

    for gid, stat in obj.items():
        glass_id = clean_text(gid)
        if not glass_id:
            continue

        if not isinstance(stat, dict):
            continue

        dt = parse_dt(
            stat.get("test_time")
            or stat.get("scan_time")
            or stat.get("TEST_TIME")
            or stat.get("SCAN_TIME")
        )

        if dt is None:
            continue

        out[glass_id] = dt

    return out


def safe_float(v: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def first_existing_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def is_http_url(v: Any) -> bool:
    s = clean_text(v).lower()
    return s.startswith("http://") or s.startswith("https://")


def with_prefix(prefix: str, value: Any) -> str:
    s = clean_text(value).replace("\\", "/")
    if not s:
        return ""

    if is_http_url(s):
        return s

    return prefix.rstrip("/") + "/" + s.lstrip("/")


def build_img_url(row: pd.Series) -> str:
    """
    對齊 routers/aoi_density_defect_map.py 的 202602 後邏輯。

    優先：
      img_file_url_path -> AIDI_URL
    fallback：
      image_file_path -> BASE_URL
    """
    img_new = clean_text(row.get("img_file_url_path", ""))
    img_old = clean_text(row.get("image_file_path", ""))

    if img_new:
        return with_prefix(AIDI_URL, img_new)

    if img_old:
        return with_prefix(BASE_URL, img_old)

    return ""


def normalize_defect_code(v: Any) -> str:
    s = clean_text(v)
    if not s:
        return "others"

    if s.lower() in {"nan", "none", "null", "undefined"}:
        return "others"

    return s


def normalize_defect_size(v: Any) -> str:
    s = clean_text(v).upper()

    if s in {"S", "SMALL"}:
        return "S"
    if s in {"M", "MID", "MIDDLE"}:
        return "M"
    if s in {"L", "LARGE"}:
        return "L"
    if s in {"O", "OVER"}:
        return "O"

    return s


def to_sql_value(v: Any):
    if v is None:
        return None

    try:
        if pd.isna(v):
            return None
    except Exception:
        pass

    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()

    return v


# =============================================================================
# Load density code summary
# =============================================================================
def load_density_code_summary_in_range(
    cfg: Config,
    db_density: MySQLDB,
    start_dt: datetime,
    end_dt: datetime,
) -> pd.DataFrame:
    months = iter_yyyymm_in_range(start_dt, end_dt)
    frames: List[pd.DataFrame] = []

    for ym in months:
        tbn = density_code_table_name(cfg, ym)

        if not db_density.table_exists(tbn):
            logger.warning(f"[density_code] missing table: {db_density.db}.{tbn}")
            continue

        sql = f"""
        SELECT *
        FROM `{db_density.db}`.`{tbn}`
        WHERE pi_hour >= :start_dt
          AND pi_hour <  :end_dt
        """

        part = db_density.query_df(sql, {
            "start_dt": start_dt,
            "end_dt": end_dt,
        })

        if part is None or part.empty:
            continue

        part["_src_yyyymm"] = ym
        frames.append(part)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)

    for c in RECIPE_GRAIN_COLS:
        if c not in df.columns:
            raise ValueError(f"density_code_summary missing required column: {c}")

    if "glass_size_detail" not in df.columns:
        raise ValueError("density_code_summary missing required column: glass_size_detail")

    df["pi_hour"] = pd.to_datetime(df["pi_hour"], errors="coerce")
    df = df.dropna(subset=["pi_hour"]).copy()

    for c in ["line_id", "aoi", "model", "glass_type", "recipe_id", "adc_def_code"]:
        if c not in df.columns:
            df[c] = ""
        df[c] = df[c].map(clean_text)

    logger.info(f"[density_code] loaded rows={len(df)} months={months}")
    return df.reset_index(drop=True)


def dedupe_recipe_groups_from_code_summary(
    code_df: pd.DataFrame,
    cfg: Config,
) -> pd.DataFrame:
    """
    density_code_summary 是 code grain。
    本功能要 recipe grain，所以同 recipe group 只取一筆 glass_size_detail。

    優先取 adc_def_code = others。
    若沒有 others，取第一筆。
    """
    if code_df is None or code_df.empty:
        return pd.DataFrame()

    d = code_df.copy()

    prefer = clean_text(cfg.prefer_adc_def_code)
    d["__prefer"] = d["adc_def_code"].map(clean_text).eq(prefer).astype(int)

    # 順手計算 glass_size_detail 解析後母體數，方便 prefer 相同時取比較完整者。
    d["__glass_map"] = d["glass_size_detail"].apply(parse_glass_size_detail)
    d["__glass_cnt"] = d["__glass_map"].apply(lambda x: len(x) if isinstance(x, dict) else 0)

    d = d[d["__glass_cnt"] > 0].copy()

    if d.empty:
        logger.warning("[recipe_group] no row has valid glass_size_detail")
        return pd.DataFrame()

    d = d.sort_values(
        RECIPE_GRAIN_COLS + ["__prefer", "__glass_cnt"],
        ascending=[True, True, True, True, True, True, False, False],
    )

    d = d.drop_duplicates(subset=RECIPE_GRAIN_COLS, keep="first").reset_index(drop=True)

    logger.info(f"[recipe_group] recipe groups={len(d)}")
    return d


# =============================================================================
# Load raw defects by glass_id + test_time
# =============================================================================
def fetch_defects_for_recipe_group(
    cfg: Config,
    db_cim: MySQLDB,
    group_row: pd.Series,
    glass_time_map: Dict[str, datetime],
) -> pd.DataFrame:
    """
    直接根據 glass_size_detail 內的 glass_id + test_time 去 cim_defect 撈 defect。

    不回查 cim_pi_glass。
    """
    if not glass_time_map:
        return pd.DataFrame()

    aoi = clean_text(group_row.get("aoi", ""))
    line_id = clean_text(group_row.get("line_id", ""))
    recipe_id = clean_text(group_row.get("recipe_id", ""))
    pi_hour = pd.to_datetime(group_row.get("pi_hour"), errors="coerce")

    keys = pd.DataFrame([
        {
            "sheet_id_chip_id": gid,
            "test_time": pd.to_datetime(tt, errors="coerce"),
        }
        for gid, tt in glass_time_map.items()
        if gid and tt is not None
    ])

    keys = keys.dropna(subset=["sheet_id_chip_id", "test_time"]).copy()
    keys["sheet_id_chip_id"] = keys["sheet_id_chip_id"].map(clean_text)

    if keys.empty:
        return pd.DataFrame()

    keys["_yyyymm"] = keys["test_time"].dt.strftime("%Y%m")

    df_parts: List[pd.DataFrame] = []

    for yyyymm, kg in keys.groupby("_yyyymm", dropna=False):
        if not yyyymm:
            continue

        tbn = defect_table_name(cfg, str(yyyymm), aoi, line_id)

        if not db_cim.table_exists(tbn):
            logger.warning(f"[defect] missing table: {db_cim.db}.{tbn}")
            continue

        gids = kg["sheet_id_chip_id"].drop_duplicates().tolist()
        t_min = kg["test_time"].min()
        t_max = kg["test_time"].max()

        if not gids:
            continue

        for i in range(0, len(gids), cfg.batch_size):
            batch = gids[i:i + cfg.batch_size]
            bind = {f"g{j}": v for j, v in enumerate(batch)}
            in_clause = ", ".join([f":g{j}" for j in range(len(batch))])

            sql = f"""
            SELECT *
            FROM `{db_cim.db}`.`{tbn}`
            WHERE test_time BETWEEN :t_min AND :t_max
              AND sheet_id_chip_id IN ({in_clause})
            """

            params = dict(bind)
            params.update({
                "t_min": t_min,
                "t_max": t_max,
            })

            part = db_cim.query_df(sql, params)

            if part is None or part.empty:
                continue

            part["_src_yyyymm"] = str(yyyymm)
            part["_src_table"] = tbn
            df_parts.append(part)

    if not df_parts:
        return pd.DataFrame()

    raw = pd.concat(df_parts, ignore_index=True)

    if raw.empty:
        return pd.DataFrame()

    raw["sheet_id_chip_id"] = raw["sheet_id_chip_id"].map(clean_text)
    raw["test_time"] = pd.to_datetime(raw["test_time"], errors="coerce")
    raw = raw.dropna(subset=["sheet_id_chip_id", "test_time"]).copy()

    # exact match glass_id + test_time，避免 BETWEEN 撈到同片其他 scan。
    exact_keys = keys[["sheet_id_chip_id", "test_time"]].drop_duplicates().copy()
    raw = raw.merge(
        exact_keys,
        on=["sheet_id_chip_id", "test_time"],
        how="inner",
    )

    if raw.empty:
        return pd.DataFrame()

    # 若 defect table 有 recipe_id，補做 recipe filter。
    if recipe_id and "recipe_id" in raw.columns:
        raw = raw[raw["recipe_id"].map(clean_text).eq(recipe_id)].copy()

    # 若 defect table 有 pi_type，限制 API。
    if "pi_type" in raw.columns:
        raw = raw[raw["pi_type"].map(clean_text).str.upper().eq("API")].copy()

    # 若 defect table 有 pi_hour，補做 pi_hour filter。
    if "pi_hour" in raw.columns and not pd.isna(pi_hour):
        raw["pi_hour"] = pd.to_datetime(raw["pi_hour"], errors="coerce")
        raw = raw[raw["pi_hour"].eq(pi_hour)].copy()

    if raw.empty:
        return pd.DataFrame()

    x_col = first_existing_col(raw, ["pox_x1", "pox_x", "coord_x", "x"])
    y_col = first_existing_col(raw, ["pox_y1", "pox_y", "coord_y", "y"])

    if not x_col or not y_col:
        logger.warning(
            f"[defect] missing xy columns. table sample columns={raw.columns.tolist()}"
        )
        return pd.DataFrame()

    raw["__x"] = pd.to_numeric(raw[x_col], errors="coerce")
    raw["__y"] = pd.to_numeric(raw[y_col], errors="coerce")
    raw = raw.dropna(subset=["__x", "__y"]).copy()

    if raw.empty:
        return pd.DataFrame()

    logger.info(
        "[defect] group line=%s aoi=%s model=%s type=%s pi_hour=%s recipe=%s "
        "glass_cnt=%s raw_rows=%s",
        line_id,
        aoi,
        clean_text(group_row.get("model", "")),
        clean_text(group_row.get("glass_type", "")),
        format_dt(pi_hour),
        recipe_id,
        len(glass_time_map),
        len(raw),
    )

    return raw.reset_index(drop=True)


# =============================================================================
# Convert raw defect rows to points
# =============================================================================
def raw_defects_to_points(raw_df: pd.DataFrame) -> List[Dict[str, Any]]:
    if raw_df is None or raw_df.empty:
        return []

    points: List[Dict[str, Any]] = []

    for idx, row in raw_df.reset_index(drop=True).iterrows():
        glass = clean_text(row.get("sheet_id_chip_id", ""))

        x = safe_float(row.get("__x"))
        y = safe_float(row.get("__y"))

        if not glass or x is None or y is None:
            continue

        chip = (
            clean_text(row.get("chip_id", ""))
            or clean_text(row.get("chip_name", ""))
            or clean_text(row.get("chip", ""))
        )

        pic_name = clean_text(row.get("image_file_name", ""))

        point = {
            "_idx": int(idx),
            "glass": glass,
            "test_time": format_dt(row.get("test_time", "")),
            "x": float(x),
            "y": float(y),
            "img_url": build_img_url(row),
            "defect_size": normalize_defect_size(row.get("defect_size", "")),
            "defect_code": normalize_defect_code(row.get("adc_def_code", "")),
            "chip_id": chip,
            "pic_name": pic_name,
        }

        points.append(point)

    return points


# =============================================================================
# Same-point matching
# =============================================================================
class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int):
        ra = self.find(a)
        rb = self.find(b)

        if ra == rb:
            return

        if self.rank[ra] < self.rank[rb]:
            self.parent[ra] = rb
        elif self.rank[ra] > self.rank[rb]:
            self.parent[rb] = ra
        else:
            self.parent[rb] = ra
            self.rank[ra] += 1


def distance(p1: Dict[str, Any], p2: Dict[str, Any]) -> float:
    dx = float(p1["x"]) - float(p2["x"])
    dy = float(p1["y"]) - float(p2["y"])
    return math.sqrt(dx * dx + dy * dy)


def build_common_clusters(
    points: List[Dict[str, Any]],
    offset_um: int,
) -> List[Dict[str, Any]]:
    """
    同點 cluster 建法：
      1. 任兩點距離 <= offset_um 且來自不同 glass，即連線。
      2. connected component 視為一個同點 cluster。
      3. cluster 至少要有 2 片不同 glass。
    """
    if not points:
        return []

    n = len(points)
    uf = UnionFind(n)

    for i in range(n):
        for j in range(i + 1, n):
            if points[i]["glass"] == points[j]["glass"]:
                continue

            if distance(points[i], points[j]) <= float(offset_um):
                uf.union(i, j)

    comp_map: Dict[int, List[int]] = {}

    for i in range(n):
        root = uf.find(i)
        comp_map.setdefault(root, []).append(i)

    clusters: List[Dict[str, Any]] = []
    cluster_id = 1

    for _, idxs in comp_map.items():
        comp_points = [points[i] for i in idxs]
        glass_set = {p["glass"] for p in comp_points}

        if len(glass_set) < 2:
            continue

        center_x = sum(float(p["x"]) for p in comp_points) / len(comp_points)
        center_y = sum(float(p["y"]) for p in comp_points) / len(comp_points)

        clean_points = []

        for p in comp_points:
            clean_points.append({
                "glass": p["glass"],
                "test_time": p["test_time"],
                "x": p["x"],
                "y": p["y"],
                "img_url": p["img_url"],
                "defect_size": p["defect_size"],
                "defect_code": p["defect_code"],
                "chip_id": p.get("chip_id", ""),
                "pic_name": p.get("pic_name", ""),
            })

        clusters.append({
            "cluster_id": cluster_id,
            "offset": int(offset_um),
            "center_x": round(float(center_x), 3),
            "center_y": round(float(center_y), 3),
            "glass_cnt": int(len(glass_set)),
            "point_cnt": int(len(clean_points)),
            "points": clean_points,
        })

        cluster_id += 1

    clusters = sorted(
        clusters,
        key=lambda x: (
            -int(x["glass_cnt"]),
            -int(x["point_cnt"]),
            float(x["center_x"]),
            float(x["center_y"]),
        ),
    )

    # 重新編 cluster_id，讓排序後 id 連續。
    for i, c in enumerate(clusters, start=1):
        c["cluster_id"] = i

    return clusters


def build_same_point_rows_for_group(
    group_row: pd.Series,
    raw_df: pd.DataFrame,
    glass_time_map: Dict[str, datetime],
    cfg: Config,
) -> pd.DataFrame:
    """
    每個 recipe group 固定產生 9 筆 offset row。
    """
    points = raw_defects_to_points(raw_df)
    rows: List[Dict[str, Any]] = []

    for offset_um in cfg.offsets_um:
        clusters = build_common_clusters(points, int(offset_um))

        common_glass_set = set()
        for c in clusters:
            for p in c.get("points", []):
                gid = clean_text(p.get("glass", ""))
                if gid:
                    common_glass_set.add(gid)

        row = {
            "line_id": clean_text(group_row.get("line_id", "")),
            "aoi": clean_text(group_row.get("aoi", "")),
            "model": clean_text(group_row.get("model", "")),
            "glass_type": clean_text(group_row.get("glass_type", "")),
            "pi_hour": pd.to_datetime(group_row.get("pi_hour"), errors="coerce"),
            "recipe_id": clean_text(group_row.get("recipe_id", "")),
            "offset": int(offset_um),
            "common_cnt": int(len(clusters)),
            "common_glass_cnt": int(len(common_glass_set)),
            "common_points_details": json.dumps(clusters, ensure_ascii=False),
            "gen_time": datetime.now(),
        }

        rows.append(row)

    return pd.DataFrame(rows, columns=OUT_COLS)


# =============================================================================
# Output table / write
# =============================================================================
def ensure_out_table(db: MySQLDB, table_name: str):
    ddl = f"""
    CREATE TABLE IF NOT EXISTS `{db.db}`.`{table_name}` (
        id BIGINT NOT NULL AUTO_INCREMENT,

        line_id VARCHAR(64) NOT NULL,
        aoi VARCHAR(32) NOT NULL,
        model VARCHAR(128) NOT NULL,
        glass_type VARCHAR(32) NOT NULL,
        pi_hour DATETIME NOT NULL,
        recipe_id VARCHAR(128) NOT NULL,
        `offset` INT NOT NULL,

        common_cnt INT NOT NULL DEFAULT 0,
        common_glass_cnt INT NOT NULL DEFAULT 0,
        common_points_details LONGTEXT NULL,
        gen_time DATETIME NULL,

        PRIMARY KEY (id),

        UNIQUE KEY uniq_recipe_offset (
            line_id,
            aoi,
            model,
            glass_type,
            pi_hour,
            recipe_id,
            `offset`
        ),

        KEY idx_pi_hour (pi_hour),
        KEY idx_recipe_group (line_id, aoi, model, glass_type, recipe_id),
        KEY idx_offset (`offset`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """

    db.execute(ddl)


def upsert_same_point_rows(
    db: MySQLDB,
    table_name: str,
    df: pd.DataFrame,
):
    ensure_out_table(db, table_name)

    if df is None or df.empty:
        logger.info(f"[write] {table_name}: empty skip")
        return

    d = df.copy()

    for c in OUT_COLS:
        if c not in d.columns:
            d[c] = None

    d = d[OUT_COLS].copy()

    for c in ["pi_hour", "gen_time"]:
        d[c] = pd.to_datetime(d[c], errors="coerce")
        d[c] = d[c].map(to_sql_value)

    rows = d.to_dict(orient="records")

    sql = text(f"""
    INSERT INTO `{db.db}`.`{table_name}` (
        line_id,
        aoi,
        model,
        glass_type,
        pi_hour,
        recipe_id,
        `offset`,
        common_cnt,
        common_glass_cnt,
        common_points_details,
        gen_time
    ) VALUES (
        :line_id,
        :aoi,
        :model,
        :glass_type,
        :pi_hour,
        :recipe_id,
        :offset,
        :common_cnt,
        :common_glass_cnt,
        :common_points_details,
        :gen_time
    )
    ON DUPLICATE KEY UPDATE
        common_cnt = VALUES(common_cnt),
        common_glass_cnt = VALUES(common_glass_cnt),
        common_points_details = VALUES(common_points_details),
        gen_time = VALUES(gen_time)
    """)

    with db.engine.begin() as conn:
        conn.execute(sql, rows)

    logger.info(f"[write] {db.db}.{table_name}: upsert rows={len(rows)}")


# =============================================================================
# Run core
# =============================================================================
def run_once_for_range(
    cfg: Config,
    start_dt: datetime,
    end_dt: datetime,
) -> Dict[str, pd.DataFrame]:
    logger.info(
        f"[run] start={start_dt}, end={end_dt}, "
        f"offsets={cfg.offsets_um}, write_out={cfg.write_out}"
    )

    db_density = MySQLDB(cfg.density_db, cfg)
    db_cim = MySQLDB(cfg.cim_db, cfg)

    code_df = load_density_code_summary_in_range(
        cfg=cfg,
        db_density=db_density,
        start_dt=start_dt,
        end_dt=end_dt,
    )

    if code_df.empty:
        logger.warning("[run] density_code_summary empty")
        return {"same_point": pd.DataFrame(columns=OUT_COLS)}

    recipe_groups = dedupe_recipe_groups_from_code_summary(code_df, cfg)

    if recipe_groups.empty:
        logger.warning("[run] no valid recipe groups")
        return {"same_point": pd.DataFrame(columns=OUT_COLS)}

    all_rows: List[pd.DataFrame] = []

    for idx, gr in recipe_groups.iterrows():
        glass_time_map = gr.get("__glass_map", {})

        if not isinstance(glass_time_map, dict):
            glass_time_map = parse_glass_size_detail(gr.get("glass_size_detail", ""))

        try:
            raw_df = fetch_defects_for_recipe_group(
                cfg=cfg,
                db_cim=db_cim,
                group_row=gr,
                glass_time_map=glass_time_map,
            )

            same_df = build_same_point_rows_for_group(
                group_row=gr,
                raw_df=raw_df,
                glass_time_map=glass_time_map,
                cfg=cfg,
            )

            if same_df is not None and not same_df.empty:
                all_rows.append(same_df)

            logger.info(
                "[group_done] %s/%s line=%s aoi=%s model=%s type=%s pi_hour=%s recipe=%s "
                "mother_glass=%s raw_defect=%s out_rows=%s",
                idx + 1,
                len(recipe_groups),
                clean_text(gr.get("line_id", "")),
                clean_text(gr.get("aoi", "")),
                clean_text(gr.get("model", "")),
                clean_text(gr.get("glass_type", "")),
                format_dt(gr.get("pi_hour", "")),
                clean_text(gr.get("recipe_id", "")),
                len(glass_time_map),
                0 if raw_df is None else len(raw_df),
                0 if same_df is None else len(same_df),
            )

        except Exception as e:
            logger.exception(
                "[group_failed] line=%s aoi=%s model=%s type=%s pi_hour=%s recipe=%s err=%s",
                clean_text(gr.get("line_id", "")),
                clean_text(gr.get("aoi", "")),
                clean_text(gr.get("model", "")),
                clean_text(gr.get("glass_type", "")),
                format_dt(gr.get("pi_hour", "")),
                clean_text(gr.get("recipe_id", "")),
                e,
            )

    if not all_rows:
        logger.warning("[run] no output rows")
        return {"same_point": pd.DataFrame(columns=OUT_COLS)}

    out_df = pd.concat(all_rows, ignore_index=True)

    # 每個 recipe group 固定 9 筆 offset。
    logger.info(
        "[run] output rows=%s groups=%s offsets=%s common_cnt_sum=%s",
        len(out_df),
        len(recipe_groups),
        list(cfg.offsets_um),
        int(out_df["common_cnt"].sum()) if "common_cnt" in out_df.columns else 0,
    )

    if cfg.write_out:
        x = out_df.copy()
        x["_yyyymm"] = pd.to_datetime(x["pi_hour"], errors="coerce").dt.strftime("%Y%m")

        for yyyymm, part in x.groupby("_yyyymm", dropna=True):
            tbn = out_table_name(cfg, str(yyyymm))
            upsert_same_point_rows(
                db=db_density,
                table_name=tbn,
                df=part.drop(columns=["_yyyymm"]),
            )
    else:
        logger.info("[run] write_out disabled")

    return {"same_point": out_df}


# =============================================================================
# Modes / CLI
# =============================================================================
def resolve_window(
    mode: str,
    *,
    month: str = "",
    days: int = 7,
    start_str: str = "",
    end_str: str = "",
    lookback_minutes: int = 180,
) -> Tuple[datetime, datetime]:
    now = datetime.now()

    if mode == "loop":
        end_dt = now
        start_dt = end_dt - timedelta(minutes=int(lookback_minutes))
        return start_dt, end_dt

    if mode == "month":
        yyyymm = str(month or "").strip() or now.strftime("%Y%m")
        start_dt = datetime.strptime(yyyymm + "01", "%Y%m%d")
        end_dt = next_month_start(start_dt)
        return start_dt, end_dt

    if mode == "days":
        end_dt = now
        start_dt = end_dt - timedelta(days=int(days))
        return start_dt, end_dt

    if mode == "range":
        if not start_str:
            raise ValueError("--mode range requires --start")
        start_dt = parse_dt(start_str)
        end_dt = parse_dt(end_str) if end_str else now
        if start_dt is None:
            raise ValueError(f"bad --start: {start_str}")
        if end_dt is None:
            raise ValueError(f"bad --end: {end_str}")

        if end_dt < start_dt:
            start_dt, end_dt = end_dt, start_dt

        return start_dt, end_dt

    raise ValueError(f"unknown mode: {mode}")


def parse_int_csv(v: Optional[str]) -> List[int]:
    if not v:
        return []

    out = []

    for x in str(v).split(","):
        sx = str(x).strip()
        if not sx:
            continue

        try:
            out.append(int(sx))
        except Exception:
            pass

    return sorted(set(out))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build AOI Density recipe same-point data")

    p.add_argument("--mode", choices=["loop", "month", "days", "range"], default="loop")
    p.add_argument("--month", default="", help="YYYYMM for month mode")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--start", default="")
    p.add_argument("--end", default="")

    p.add_argument("--host", default="10.97.142.217")
    p.add_argument("--username", default="l6a01_user")
    p.add_argument("--password", default="l6a01$user")

    p.add_argument("--density-db", default="piaoi_density")
    p.add_argument("--cim-db", default="cim_piaoi")

    p.add_argument("--loop-minutes", type=int, default=10)
    p.add_argument("--lookback-minutes", type=int, default=180)

    p.add_argument("--offsets", default="20,30,40,50,60,70,80,90,100")

    p.add_argument("--write-out", action="store_true")

    return p


def main(argv: Optional[List[str]] = None):
    parser = build_parser()
    args, _unknown = parser.parse_known_args(argv)

    offsets = parse_int_csv(args.offsets)
    if not offsets:
        offsets = [20, 30, 40, 50, 60, 70, 80, 90, 100]

    cfg = Config(
        host=args.host,
        username=args.username,
        password=args.password,
        density_db=args.density_db,
        cim_db=args.cim_db,
        loop_minutes=args.loop_minutes,
        lookback_minutes=args.lookback_minutes,
        offsets_um=tuple(offsets),
        write_out=bool(args.write_out),
    )

    logger.info(
        f"[start] mode={args.mode}, density_db={cfg.density_db}, cim_db={cfg.cim_db}, "
        f"offsets={cfg.offsets_um}, write_out={cfg.write_out}"
    )

    if args.mode == "loop":
        while True:
            start_dt, end_dt = resolve_window(
                "loop",
                lookback_minutes=cfg.lookback_minutes,
            )

            try:
                run_once_for_range(cfg, start_dt, end_dt)
            except Exception as e:
                logger.exception(f"[loop] failed: {e}")

            time.sleep(cfg.loop_minutes * 60)

    else:
        start_dt, end_dt = resolve_window(
            args.mode,
            month=args.month,
            days=args.days,
            start_str=args.start,
            end_str=args.end,
            lookback_minutes=cfg.lookback_minutes,
        )

        run_once_for_range(cfg, start_dt, end_dt)


if __name__ == "__main__":
    main()


"""
Examples:

# 重跑整月
python build_density_recipe_same_point_job.py --mode month --month 202607 --write-out

# 重跑最近 5 天
python build_density_recipe_same_point_job.py --mode days --days 1 --write-out

# 指定區間
python build_density_recipe_same_point_job.py --mode range --start "2026-07-04 00:00:00" --end "2026-07-05 12:00:00" --write-out

# 常駐
python build_density_recipe_same_point_job.py --mode loop --lookback-minutes 180 --loop-minutes 10 --write-out
"""