# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Iterable

import pandas as pd
from fastapi import APIRouter
from pydantic import BaseModel

from models.sql_db_connect import MySQLConnet
from models.piaoi.density.cim_density_job import Config as DensityJobConfig


router = APIRouter(tags=["duty_cell_piaoi_bpi_density"])

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(funcName)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# =============================================================================
# Request model
# =============================================================================
class DefectMapIn(BaseModel):
    rows: List[Dict[str, Any]] = []


# =============================================================================
# Helpers
# =============================================================================
BASE_URL = "http://10.97.139.98:1454//"
AIDI_URL = "http://l6apaimg103/dms/CELAIDI_L6A/"


def clean_text(v: Any) -> str:
    if v is None:
        return ""

    s = str(v).strip()
    if s.lower() in {"nan", "none", "null", "<na>", "nat"}:
        return ""

    return s


def parse_any_dt(v: Any) -> Optional[datetime]:
    if v is None:
        return None

    if isinstance(v, datetime):
        return v

    try:
        ts = pd.to_datetime(v, errors="coerce")
        if pd.isna(ts):
            return None

        if isinstance(ts, pd.Timestamp):
            return ts.to_pydatetime()

        return ts
    except Exception:
        return None


def dt_to_str(v: Any) -> str:
    dt = parse_any_dt(v)
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""


def safe_series(df: pd.DataFrame, col: str, default: Any = "") -> pd.Series:
    if col in df.columns:
        return df[col]
    return pd.Series([default] * len(df), index=df.index)


def load_glass_size_detail(val: Any) -> Dict[str, Dict[str, Any]]:
    if isinstance(val, dict):
        return val

    if not val:
        return {}

    try:
        obj = json.loads(val)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def normalize_aoi_name(aoi: str) -> str:
    s = clean_text(aoi).lower()
    if s in {"aoi100", "aoi200", "aoi300"}:
        return s
    return s


def get_cim_defect_table_name(cfg: DensityJobConfig, yyyymm: str, aoi: str, line_id: str) -> str:
    """
    cfg.defect_table_tpl 預期為 cim_defect_yyyymm_aoi_line
    e.g. cim_defect_202604_aoi200_capic400
    """
    return (
        cfg.defect_table_tpl
        .replace("yyyymm", yyyymm)
        .replace("aoi", aoi)
        .replace("line", line_id.lower())
        .lower()
    )


def get_rtms_raw_table_name(yyyymm: str) -> str:
    return f"rtms_aoi300_raw_{yyyymm}".lower()


def choose_cim_image_cols(yyyymm: str) -> tuple[str, Dict[str, str]]:
    """
    舊資料(<202602): 常用 image_file_path + image_file_name
    新資料(>=202602): 常用 img_file_url_path + image_file_name
    """
    if int(yyyymm) < 202602:
        img_col = "image_file_path"
    else:
        img_col = "img_file_url_path"

    colmap = {
        "defect_size": "defect_size",
        "pox_x1": "x",
        "pox_y1": "y",
        img_col: "pic_path",
        "image_file_name": "pic_name",
        "recipe_id": "recipe_id",
    }
    return img_col, colmap


def build_old_cim_image_path(
    def_tb: pd.DataFrame,
    *,
    gld: str,
    aoi: str,
    yyyymm: str,
    cim_db: MySQLConnet,
    cim_cfg: DensityJobConfig,
) -> pd.DataFrame:
    """
    舊 CIM 路徑規則，沿用 aoi_density 的邏輯。
    """
    re_aoimap = {v: k for k, v in cim_cfg.aoi_map.items()}

    if def_tb.empty or "image_file_path" not in def_tb.columns:
        return def_tb

    path0 = clean_text(def_tb["image_file_path"].iloc[0])

    if not path0:
        return def_tb

    # case 1: Image/CAxxxx/... 需拼完整 CaptureImage path
    if path0.startswith("Image"):
        latest_tt = pd.to_datetime(def_tb["test_time"], errors="coerce").max()
        match_dict2 = {
            "sheet_id_chip_id": gld,
            "test_time": latest_tt,
        }

        sum_tbn = cim_cfg.summary_table_tpl.replace("yyyymm", yyyymm).lower()
        s_rows = cim_db.get_rows(sum_tbn, match_dict2)
        s_df = pd.DataFrame(s_rows) if s_rows else pd.DataFrame()

        if s_df.empty:
            logger.warning(
                f"summary row not found for old CIM path build: "
                f"sheet_id_chip_id={gld}, test_time={latest_tt}, table={sum_tbn}"
            )
            return def_tb

        s_info = s_df.iloc[0, :].to_dict()
        op_id = clean_text(s_info.get("op_id"))

        try:
            str_time = pd.to_datetime(latest_tt).strftime("%Y%m%d%H%M%S")
        except Exception:
            str_time = str(latest_tt).replace("-", "").replace(":", "").replace(" ", "")

        p = path0.replace("\\", "/")
        p2 = p[6:] if p.startswith("Image/") else p

        if p2 and not p2.endswith("/"):
            p2 += "/"

        new_path = (
            BASE_URL
            + re_aoimap.get(aoi, aoi).upper()
            + "/"
            + p2
            + op_id
            + "/"
            + str_time
            + "/CaptureImage/"
        )

        def_tb["image_file_path"] = new_path
        return def_tb

    # case 2: UNC path -> http path
    unc_prefix = "\\\\192.168.5.88\\aoi"
    def_tb["image_file_path"] = (
        def_tb["image_file_path"]
        .astype(str)
        .str.replace(unc_prefix, BASE_URL, regex=False)
        .apply(lambda x: x[1:] if x.startswith("\\") else x)
    )

    return def_tb


def build_new_cim_image_path(def_tb: pd.DataFrame) -> pd.DataFrame:
    if def_tb.empty or "img_file_url_path" not in def_tb.columns:
        return def_tb

    def_tb["img_file_url_path"] = def_tb["img_file_url_path"].apply(
        lambda x: AIDI_URL + clean_text(x) if clean_text(x) else ""
    )
    return def_tb


def normalize_cim_defect_df(
    df: pd.DataFrame,
    *,
    gld: str,
    aoi: str,
    yyyymm: str,
    cim_db: MySQLConnet,
    cim_cfg: DensityJobConfig,
) -> pd.DataFrame:
    if df.empty:
        return df

    _img_col, colmap = choose_cim_image_cols(yyyymm)

    df = df.copy()
    df["test_time"] = pd.to_datetime(df["test_time"], errors="coerce")

    if int(yyyymm) < 202602:
        df = build_old_cim_image_path(
            df,
            gld=gld,
            aoi=aoi,
            yyyymm=yyyymm,
            cim_db=cim_db,
            cim_cfg=cim_cfg,
        )
    else:
        df = build_new_cim_image_path(df)

    keep_cols = [c for c in colmap.keys() if c in df.columns]
    df = df[keep_cols].copy()
    df.rename(columns=colmap, inplace=True)

    for c in ["defect_size", "pic_path", "pic_name", "recipe_id"]:
        if c not in df.columns:
            df[c] = ""

    for c in ["x", "y"]:
        if c not in df.columns:
            df[c] = 0

    return df


def normalize_rtms_defect_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()

    # RTMS raw 已經有 pic_path，保留即可
    colmap = {
        "defect_size": "defect_size",
        "pox_x1": "x",
        "pox_y1": "y",
        "pic_path": "pic_path",
        "image_file_name": "pic_name",
        "recipe_id": "recipe_id",
    }

    keep_cols = [c for c in colmap.keys() if c in df.columns]
    df = df[keep_cols].copy()
    df.rename(columns=colmap, inplace=True)

    for c in ["defect_size", "pic_path", "pic_name", "recipe_id"]:
        if c not in df.columns:
            df[c] = ""

    for c in ["x", "y"]:
        if c not in df.columns:
            df[c] = 0

    return df


def empty_defect_result() -> Dict[str, Any]:
    return {}


# =============================================================================
# Single-glass query, retained as fallback
# =============================================================================
def query_cim_one_glass(
    cim_db: MySQLConnet,
    cim_cfg: DensityJobConfig,
    *,
    aoi: str,
    glass_id: str,
    line_id: str,
    test_time: datetime,
) -> pd.DataFrame:
    """
    aoi100/aoi200:
    - line_id 有值 -> cim_defect_yyyymm_aoi_line_id
    - line_id 空值 -> fallback cim_defect_yyyymm_aoi_pi000
    """
    yyyymm = test_time.strftime("%Y%m")
    line_id_use = clean_text(line_id).lower() or "pi000"

    tbn = get_cim_defect_table_name(cim_cfg, yyyymm, aoi, line_id_use)

    logger.info(
        f"[query_cim_one_glass] aoi={aoi}, glass={glass_id}, line_id={line_id_use}, "
        f"test_time={test_time}, table={tbn}"
    )

    match_dict = {
        "sheet_id_chip_id": glass_id,
        "test_time": test_time,
    }
    #logger.info(f'[match_dict]: {match_dict}')
    try:
        rows = cim_db.get_rows(tbn, match_dict)
    except Exception as e:
        logger.warning(f"[query_cim_one_glass] get_rows failed: table={tbn}, err={e}")
        rows = []
    #logger.info(f'rows: {rows}')
    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if df.empty:
        return df
    #unis = df['defect_size'].unique()
    #logger.info(f'[defect_size], {unis}')
    return normalize_cim_defect_df(
        df,
        gld=glass_id,
        aoi=aoi,
        yyyymm=yyyymm,
        cim_db=cim_db,
        cim_cfg=cim_cfg,
    )


def query_rtms_one_glass(
    rtms_db: MySQLConnet,
    *,
    glass_id: str,
    test_time: datetime,
) -> pd.DataFrame:
    yyyymm = test_time.strftime("%Y%m")
    tbn = get_rtms_raw_table_name(yyyymm)

    logger.info(
        f"[query_rtms_one_glass] glass={glass_id}, test_time={test_time}, table={tbn}"
    )

    match_dict = {
        "sheet_id_chip_id": glass_id,
        "test_time": test_time,
    }

    try:
        rows = rtms_db.get_rows(tbn, match_dict)
    except Exception as e:
        logger.warning(f"[query_rtms_one_glass] get_rows failed: table={tbn}, err={e}")
        rows = []

    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if df.empty:
        return df

    return normalize_rtms_defect_df(df)


def build_one_glass_result(
    *,
    aoi: str,
    glass_id: str,
    glass_info: Dict[str, Any],
    cim_db: MySQLConnet,
    rtms_db: MySQLConnet,
    cim_cfg: DensityJobConfig,
) -> Dict[str, Any]:
    test_time = parse_any_dt(glass_info.get("test_time"))
    line_id = clean_text(glass_info.get("line_id"))

    if not test_time:
        logger.warning(
            f"[build_one_glass_result] invalid test_time, glass={glass_id}, info={glass_info}"
        )
        return empty_defect_result()

    if aoi in {"aoi100", "aoi200"}:
        df = query_cim_one_glass(
            cim_db,
            cim_cfg,
            aoi=aoi,
            glass_id=glass_id,
            line_id=line_id,
            test_time=test_time,
        )
    elif aoi == "aoi300":
        df = query_rtms_one_glass(
            rtms_db,
            glass_id=glass_id,
            test_time=test_time,
        )
    else:
        logger.warning(f"[build_one_glass_result] unsupported aoi={aoi}")
        return empty_defect_result()

    if df.empty:
        return empty_defect_result()

    return df.to_dict(orient="index")


# =============================================================================
# Batch query helpers
# =============================================================================
def build_glass_query_items(glass_items: Iterable) -> List[Dict[str, Any]]:
    """
    將 glass_size_detail.items() 整理成批次查詢需要的資料。

    每筆 item:
    {
        glass_id,
        test_time,
        line_id,
        info
    }
    """
    out: List[Dict[str, Any]] = []

    for glass_id, info in glass_items:
        glass_id = clean_text(glass_id)
        if not glass_id:
            continue

        info = info if isinstance(info, dict) else {}

        test_time = parse_any_dt(info.get("test_time"))
        if not test_time:
            logger.warning(
                f"[build_glass_query_items] invalid test_time, glass={glass_id}, info={info}"
            )
            continue

        line_id = clean_text(info.get("line_id"))

        out.append({
            "glass_id": glass_id,
            "test_time": test_time,
            "line_id": line_id,
            "info": info,
        })

    return out


def make_cim_batch_group_key(item: Dict[str, Any], aoi: str) -> tuple:
    """
    AOI100 / AOI200:
    table = cim_defect_yyyymm_aoi_line

    line_id 空值要落 pi000。
    """
    test_time = item["test_time"]
    yyyymm = test_time.strftime("%Y%m")
    line_id_use = clean_text(item.get("line_id")).lower() or "pi000"

    return yyyymm, aoi, line_id_use


def make_rtms_batch_group_key(item: Dict[str, Any]) -> tuple:
    """
    AOI300:
    table = rtms_aoi300_raw_yyyymm
    """
    test_time = item["test_time"]
    yyyymm = test_time.strftime("%Y%m")
    return (yyyymm,)


def build_pair_in_clause(
    items: List[Dict[str, Any]],
    *,
    glass_col: str = "sheet_id_chip_id",
    time_col: str = "test_time",
    prefix: str = "p",
) -> tuple[str, Dict[str, Any]]:
    """
    建立複合鍵 IN 條件：

    (`sheet_id_chip_id`, `test_time`) IN (
        (:p_g0, :p_t0),
        (:p_g1, :p_t1)
    )
    """
    params: Dict[str, Any] = {}
    parts: List[str] = []

    for i, it in enumerate(items):
        g_key = f"{prefix}_g{i}"
        t_key = f"{prefix}_t{i}"

        parts.append(f"(:{g_key}, :{t_key})")
        params[g_key] = clean_text(it["glass_id"])
        params[t_key] = it["test_time"]

    clause = f"(`{glass_col}`, `{time_col}`) IN ({', '.join(parts)})"
    return clause, params


def normalize_cim_defect_df_keep_key(
    df: pd.DataFrame,
    *,
    gld: str,
    aoi: str,
    yyyymm: str,
    cim_db: MySQLConnet,
    cim_cfg: DensityJobConfig,
) -> pd.DataFrame:
    """
    normalize_cim_defect_df() 會只保留前端需要欄位，
    因此 batch 查詢時要另外保留 _glass_id / _test_time 作為分群 key。
    """
    if df is None or df.empty:
        return pd.DataFrame()

    src = df.copy()

    key_df = pd.DataFrame({
        "_glass_id": safe_series(src, "sheet_id_chip_id", "").map(clean_text),
        "_test_time": pd.to_datetime(safe_series(src, "test_time", None), errors="coerce").map(dt_to_str),
    })

    norm = normalize_cim_defect_df(
        src,
        gld=gld,
        aoi=aoi,
        yyyymm=yyyymm,
        cim_db=cim_db,
        cim_cfg=cim_cfg,
    )

    if norm is None or norm.empty:
        return pd.DataFrame()

    norm = norm.reset_index(drop=True)
    key_df = key_df.reset_index(drop=True)

    if len(norm) == len(key_df):
        norm["_glass_id"] = key_df["_glass_id"]
        norm["_test_time"] = key_df["_test_time"]
    else:
        logger.warning(
            f"[normalize_cim_defect_df_keep_key] length mismatch: norm={len(norm)}, key={len(key_df)}"
        )

    return norm


def normalize_rtms_defect_df_keep_key(df: pd.DataFrame) -> pd.DataFrame:
    """
    normalize_rtms_defect_df() 會只保留前端需要欄位，
    因此 batch 查詢時要另外保留 _glass_id / _test_time 作為分群 key。
    """
    if df is None or df.empty:
        return pd.DataFrame()

    src = df.copy()

    key_df = pd.DataFrame({
        "_glass_id": safe_series(src, "sheet_id_chip_id", "").map(clean_text),
        "_test_time": pd.to_datetime(safe_series(src, "test_time", None), errors="coerce").map(dt_to_str),
    })

    norm = normalize_rtms_defect_df(src)

    if norm is None or norm.empty:
        return pd.DataFrame()

    norm = norm.reset_index(drop=True)
    key_df = key_df.reset_index(drop=True)

    if len(norm) == len(key_df):
        norm["_glass_id"] = key_df["_glass_id"]
        norm["_test_time"] = key_df["_test_time"]
    else:
        logger.warning(
            f"[normalize_rtms_defect_df_keep_key] length mismatch: norm={len(norm)}, key={len(key_df)}"
        )

    return norm


def query_cim_glass_batch(
    cim_db: MySQLConnet,
    cim_cfg: DensityJobConfig,
    *,
    aoi: str,
    items: List[Dict[str, Any]],
) -> pd.DataFrame:
    """
    批次查 AOI100 / AOI200 CIM defect rows。

    items 必須屬於同一個:
    yyyymm + aoi + line_id_use
    """
    if not items:
        return pd.DataFrame()

    yyyymm, _, line_id_use = make_cim_batch_group_key(items[0], aoi)
    tbn = get_cim_defect_table_name(cim_cfg, yyyymm, aoi, line_id_use)

    clause, params = build_pair_in_clause(items, prefix="cim")

    sql = f"""
    SELECT *
    FROM `{cim_db.db}`.`{tbn}`
    WHERE {clause}
    """

    logger.info(
        f"[query_cim_glass_batch] aoi={aoi}, table={tbn}, "
        f"line_id={line_id_use}, items={len(items)}"
    )

    try:
        df = cim_db.query_df(sql, params)
    except Exception as e:
        logger.warning(f"[query_cim_glass_batch] query failed: table={tbn}, err={e}")
        return pd.DataFrame()

    if df.empty:
        return df

    # 舊 CIM path build 需要依單片 glass 找 summary row 補路徑，
    # 所以 <202602 仍逐 glass normalize；但 SQL 已經批次查回來。
    if int(yyyymm) < 202602:
        frames: List[pd.DataFrame] = []

        for (glass_id, test_time), sub in df.groupby(["sheet_id_chip_id", "test_time"], dropna=False):
            one = normalize_cim_defect_df_keep_key(
                sub.copy(),
                gld=clean_text(glass_id),
                aoi=aoi,
                yyyymm=yyyymm,
                cim_db=cim_db,
                cim_cfg=cim_cfg,
            )

            if not one.empty:
                frames.append(one)

        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    return normalize_cim_defect_df_keep_key(
        df.copy(),
        gld="",
        aoi=aoi,
        yyyymm=yyyymm,
        cim_db=cim_db,
        cim_cfg=cim_cfg,
    )


def query_rtms_glass_batch(
    rtms_db: MySQLConnet,
    *,
    items: List[Dict[str, Any]],
) -> pd.DataFrame:
    """
    批次查 AOI300 RTMS raw rows。

    items 必須屬於同一個 yyyymm。
    """
    if not items:
        return pd.DataFrame()

    yyyymm = make_rtms_batch_group_key(items[0])[0]
    tbn = get_rtms_raw_table_name(yyyymm)

    clause, params = build_pair_in_clause(items, prefix="rtms")

    sql = f"""
    SELECT *
    FROM `{rtms_db.db}`.`{tbn}`
    WHERE {clause}
    """

    logger.info(
        f"[query_rtms_glass_batch] table={tbn}, items={len(items)}"
    )

    try:
        df = rtms_db.query_df(sql, params)
    except Exception as e:
        logger.warning(f"[query_rtms_glass_batch] query failed: table={tbn}, err={e}")
        return pd.DataFrame()

    if df.empty:
        return df

    return normalize_rtms_defect_df_keep_key(df)


def chunk_list(items: List[Dict[str, Any]], size: int = 500):
    """
    避免一次 IN 條件太長。
    一般 CST 片數不多，但保留 chunk 比較穩。
    """
    for i in range(0, len(items), size):
        yield items[i:i + size]


def batch_build_defect_group_dict(
    *,
    aoi: str,
    glass_items,
    cim_db: MySQLConnet,
    rtms_db: MySQLConnet,
    cim_cfg: DensityJobConfig,
) -> Dict[str, Any]:
    """
    取代原本逐片查詢的 batch 版本。

    回傳格式維持:
    {
        glass_id: {
            0: {...},
            1: {...}
        }
    }
    """
    query_items = build_glass_query_items(glass_items)

    out: Dict[str, Any] = {
        it["glass_id"]: empty_defect_result()
        for it in query_items
    }

    if not query_items:
        return out

    frames: List[pd.DataFrame] = []

    if aoi in {"aoi100", "aoi200"}:
        grouped: Dict[tuple, List[Dict[str, Any]]] = {}

        for it in query_items:
            key = make_cim_batch_group_key(it, aoi)
            grouped.setdefault(key, []).append(it)

        for key, items in grouped.items():
            logger.info(f"[batch_build_defect_group_dict] CIM group={key}, count={len(items)}")

            for chunk in chunk_list(items, size=5000):
                df = query_cim_glass_batch(
                    cim_db,
                    cim_cfg,
                    aoi=aoi,
                    items=chunk,
                )
                
                if df is not None and not df.empty:
                    frames.append(df)

    elif aoi == "aoi300":
        grouped: Dict[tuple, List[Dict[str, Any]]] = {}

        for it in query_items:
            key = make_rtms_batch_group_key(it)
            grouped.setdefault(key, []).append(it)

        for key, items in grouped.items():
            logger.info(f"[batch_build_defect_group_dict] RTMS group={key}, count={len(items)}")

            for chunk in chunk_list(items, size=500):
                df = query_rtms_glass_batch(
                    rtms_db,
                    items=chunk,
                )

                if df is not None and not df.empty:
                    frames.append(df)

    else:
        logger.warning(f"[batch_build_defect_group_dict] unsupported aoi={aoi}")
        return out

    if not frames:
        return out

    all_df = pd.concat(frames, ignore_index=True)
    if all_df.empty or "_glass_id" not in all_df.columns:
        return out

    for glass_id, sub in all_df.groupby("_glass_id", dropna=False):
        gid = clean_text(glass_id)
        if not gid:
            continue

        sub2 = (
            sub
            .drop(columns=["_glass_id", "_test_time"], errors="ignore")
            .reset_index(drop=True)
        )

        out[gid] = sub2.to_dict(orient="index")

    return out


def fallback_build_defect_group_dict(
    *,
    aoi: str,
    glass_items,
    cim_db: MySQLConnet,
    rtms_db: MySQLConnet,
    cim_cfg: DensityJobConfig,
) -> Dict[str, Any]:
    """
    batch 失敗時，退回原本逐片查詢。
    """
    out: Dict[str, Any] = {}

    for glass_id, info in glass_items:
        glass_id = clean_text(glass_id)
        if not glass_id:
            continue

        info = info if isinstance(info, dict) else {}

        try:
            out[glass_id] = build_one_glass_result(
                aoi=aoi,
                glass_id=glass_id,
                glass_info=info,
                cim_db=cim_db,
                rtms_db=rtms_db,
                cim_cfg=cim_cfg,
            )
        except Exception as e:
            logger.exception(
                f"[fallback_build_defect_group_dict] failed: aoi={aoi}, glass={glass_id}, err={e}"
            )
            out[glass_id] = empty_defect_result()

    return out


# =============================================================================
# Route
# =============================================================================
@router.post("/cst_defect_map")
async def cst_defect_map(payload: DefectMapIn):
    """
    前端 rows 格式示意:
    [
      {
        "aoi": "aoi200",
        "cassette_id": "AA1795",
        "glass_list": "YH6A3X18A,YH6A3X18B,...",
        "glass_side": "TFT",
        "glass_size_detail": "{\"YH6A3X18A\": {..., \"line_id\": \"CAPIC400\", \"test_time\": \"2026-04-22 16:23:14\"}, ...}",
        "model": "B160UAV01",
        "recipe_id": "4283",
        "scan_hour": "2026-04-22 15:00:00"
      }
    ]
    """
    cim_cfg = DensityJobConfig()
    cim_db = MySQLConnet(cim_cfg.src_db)          # cim_piaoi
    rtms_db = MySQLConnet("rtms_piaoi_other")     # aoi300 raw

    if not payload.rows:
        return {"DefectGroupDict": {}}

    row_in = payload.rows[0]

    aoi = normalize_aoi_name(row_in.get("aoi", ""))
    if aoi not in {"aoi100", "aoi200", "aoi300"}:
        logger.warning(f"[cst_defect_map] skip unsupported aoi: {aoi}")
        return {"DefectGroupDict": {}}

    glass_size_detail = load_glass_size_detail(row_in.get("glass_size_detail"))

    if glass_size_detail:
        glass_items = list(glass_size_detail.items())
    else:
        # 若意外沒傳到 glass_size_detail，至少先從 glass_list 建骨架。
        # 注意：沒有 test_time 時 batch 與 fallback 都無法精準查 defect，只會回空。
        glass_list = clean_text(row_in.get("glass_list"))
        glass_ids = [x.strip() for x in glass_list.split(",") if x.strip()]
        glass_items = [(gid, {}) for gid in glass_ids]

    logger.info(
        f"[cst_defect_map] aoi={aoi}, "
        f"cassette_id={clean_text(row_in.get('cassette_id'))}, "
        f"scan_hour={clean_text(row_in.get('scan_hour'))}, "
        f"glass_count={len(glass_items)}"
    )

    try:
        out = batch_build_defect_group_dict(
            aoi=aoi,
            glass_items=glass_items,
            cim_db=cim_db,
            rtms_db=rtms_db,
            cim_cfg=cim_cfg,
        )
        #print(out)
    except Exception as e:
        logger.exception(f"[cst_defect_map] batch failed: aoi={aoi}, err={e}")

        out = fallback_build_defect_group_dict(
            aoi=aoi,
            glass_items=glass_items,
            cim_db=cim_db,
            rtms_db=rtms_db,
            cim_cfg=cim_cfg,
        )

    return {"DefectGroupDict": out}