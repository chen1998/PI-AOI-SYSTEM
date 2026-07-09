# routers/aoi_density_defect_map.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Set, Tuple, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from models.sql_db_connect import MySQLConnet
from models.piaoi.density.cim_density_job import Config as DensityJobConfig


router = APIRouter(tags=["duty_cell_piaoi_aoi_density"])

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(funcName)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


# =============================================================================
# Helpers
# =============================================================================
def parse_pi_hour_to_dt(pi_hour: str) -> datetime:
    """
    支援前端可能送來的 pi_hour 格式：

    舊版：
      26-06-30 21

    新版 service1.js 會優先送 pi_hour_raw：
      2026-06-30 21:00:00
      2026-06-30 21:00
      2026-06-30 21
      2026-06-30T21:00:00
    """
    s = str(pi_hour or "").strip()
    if not s:
        raise ValueError("empty pi_hour")

    s = s.replace("T", " ").replace(".000", "").strip()

    fmts = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H",
        "%y-%m-%d %H",
    ]

    last_err: Optional[Exception] = None

    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt)
        except Exception as e:
            last_err = e

    raise ValueError(f"unsupported pi_hour format: {pi_hour}, err={last_err}")


def pi_hour_to_mysql_str(pi_hour: str) -> str:
    return parse_pi_hour_to_dt(pi_hour).strftime("%Y-%m-%d %H:%M:%S")


def _safe_json_loads(v: Any) -> Dict[str, Any]:
    """
    glass_size_detail may be:
      1) JSON string
      2) already dict
      3) empty / invalid

    新版格式：
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
    """
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


def _parse_dt(v: Any) -> Optional[datetime]:
    if v is None:
        return None

    s = str(v or "").strip()
    if not s:
        return None

    s = s.replace("T", " ").replace(".000", "").strip()

    fmts = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H",
    ]

    for fmt in fmts:
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


def _extract_defect_glasses_and_test_times(
    gld_details: Dict[str, Any],
) -> Tuple[Set[str], Dict[str, datetime]]:
    """
    只撈目前 code 的 T > 0 的 glass。

    同時擷取新版 density job 放進 glass_size_detail 的 test_time。
    後續 defect_map 優先用每片 glass 的 test_time 對 raw defect 表對時。
    """
    glds: Set[str] = set()
    test_time_map: Dict[str, datetime] = {}

    if not isinstance(gld_details, dict):
        return glds, test_time_map

    for gld, stat in gld_details.items():
        gid = str(gld or "").strip()
        if not gid:
            continue

        if not isinstance(stat, dict):
            continue
        """
        try:
            total = int(stat.get("T", 0) or 0)
        except Exception:
            total = 0

        if total == 0:
            continue
        """
        glds.add(gid)

        dt = _parse_dt(
            stat.get("test_time")
            or stat.get("scan_time")
            or stat.get("TEST_TIME")
            or stat.get("SCAN_TIME")
        )

        if dt:
            test_time_map[gid] = dt

    return glds, test_time_map


def _months_between(start_dt: datetime, end_dt: datetime) -> List[str]:
    """
    回傳 start_dt ~ end_dt 涉及的 yyyymm。
    """
    months: List[str] = []

    cur = datetime(start_dt.year, start_dt.month, 1)
    end = datetime(end_dt.year, end_dt.month, 1)

    while cur <= end:
        months.append(cur.strftime("%Y%m"))

        if cur.month == 12:
            cur = datetime(cur.year + 1, 1, 1)
        else:
            cur = datetime(cur.year, cur.month + 1, 1)

    return months


def _defect_table_name(cim_cfg: DensityJobConfig, yyyymm: str, aoi: str, line_id: str) -> str:
    return (
        cim_cfg.defect_table_tpl
        .replace("yyyymm", str(yyyymm))
        .replace("aoi", str(aoi))
        .replace("line", str(line_id))
        .lower()
    )


def _ensure_cols(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    """
    Ensure selected columns exist before df[cols].
    Missing columns are filled with empty string.
    """
    out = df.copy()

    for c in cols:
        if c not in out.columns:
            out[c] = ""

    return out


def _normalize_raw_def_code_for_others(df: pd.DataFrame) -> pd.DataFrame:
    """
    raw defect 裡 adc_def_code 空值統一成 others。
    """
    if df is None or df.empty:
        return df

    out = df.copy()

    if "adc_def_code" in out.columns:
        out["adc_def_code"] = (
            out["adc_def_code"]
            .astype("string")
            .fillna("others")
            .astype(str)
            .str.strip()
            .replace({
                "": "others",
                "nan": "others",
                "NaN": "others",
                "None": "others",
                "NULL": "others",
            })
        )

    return out


def _norm_str(v: Any) -> str:
    return str(v or "").strip()


def _filter_df_if_col_exists(df: pd.DataFrame, col: str, expected: str) -> pd.DataFrame:
    """
    只有欄位存在且 expected 非空時才過濾。
    """
    if df is None or df.empty:
      return df

    if not expected:
        return df

    if col not in df.columns:
        return df

    return df[df[col].astype(str).str.strip() == str(expected).strip()].copy()


def _filter_by_def_code(df: pd.DataFrame, def_code: str) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    if not def_code:
        return df

    if "adc_def_code" not in df.columns:
        return df

    want = str(def_code or "").strip()
    return df[df["adc_def_code"].astype(str).str.strip() == want].copy()


def _choose_latest_rows_per_glass(
    df_all: pd.DataFrame,
    glds: Set[str],
    test_time_map: Dict[str, datetime],
    tolerance_sec: int = 2,
) -> pd.DataFrame:
    """
    對每片 glass 挑出應該顯示在 defect_map 上的 raw defect rows。

    優先順序：
      1. 若 glass_size_detail 有該 glass 的 test_time：
         先找 raw defect 表 test_time 與該 test_time 相同的 rows。
      2. 若精準對不到，允許 ± tolerance_sec 秒。
      3. 若仍沒有，退回該 glass 最新 test_time。
    """
    if df_all is None or df_all.empty:
        return pd.DataFrame()

    if "sheet_id_chip_id" not in df_all.columns or "test_time" not in df_all.columns:
        return pd.DataFrame()

    out_parts: List[pd.DataFrame] = []

    df = df_all.copy()
    df["sheet_id_chip_id"] = df["sheet_id_chip_id"].astype(str).str.strip()
    df["test_time"] = pd.to_datetime(df["test_time"], errors="coerce")
    df = df.dropna(subset=["test_time"]).copy()

    if df.empty:
        return pd.DataFrame()

    for gid in sorted(glds):
        dfg = df[df["sheet_id_chip_id"] == str(gid)].copy()

        if dfg.empty:
            continue

        target_dt = test_time_map.get(gid)

        if target_dt:
            target_ts = pd.Timestamp(target_dt)

            exact = dfg[dfg["test_time"].eq(target_ts)].copy()

            if not exact.empty:
                out_parts.append(exact)
                continue

            if tolerance_sec > 0:
                delta = (dfg["test_time"] - target_ts).abs()
                near = dfg[delta <= pd.Timedelta(seconds=tolerance_sec)].copy()

                if not near.empty:
                    out_parts.append(near)
                    continue

        # fallback：取該 glass 最新 test_time
        mx = dfg["test_time"].max()
        latest = dfg[dfg["test_time"].eq(mx)].copy()

        if not latest.empty:
            out_parts.append(latest)

    if not out_parts:
        return pd.DataFrame()

    return pd.concat(out_parts, ignore_index=True)


def _first_existing_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _build_pic_path(row: pd.Series, yyyymm: str) -> str:
    """
    對應 raw defect 撈取程式的圖欄位：
      - 202602 前：image_file_path
      - 202602 後：img_file_url_path

    若欄位已經是 http URL，不重複加 prefix。
    """
    base_url = "http://10.97.139.98:1454/"
    aidi_url = "http://l6apaimg103/dms/CELAIDI_L6A/"

    img_new = str(row.get("img_file_url_path", "") or "").strip()
    img_old = str(row.get("image_file_path", "") or "").strip()

    def with_prefix(prefix: str, value: str) -> str:
        value = str(value or "").strip()
        if not value:
            return ""

        if value.lower().startswith(("http://", "https://")):
            return value

        return prefix.rstrip("/") + "/" + value.lstrip("/")

    try:
        ym_int = int(str(yyyymm))
    except Exception:
        ym_int = 999999

    if ym_int >= 202602:
        if img_new:
            return with_prefix(aidi_url, img_new)
        if img_old:
            return with_prefix(base_url, img_old)
        return ""

    if img_old:
        return with_prefix(base_url, img_old)
    if img_new:
        return with_prefix(aidi_url, img_new)
    return ""


def _format_dt_for_json(v: Any) -> str:
    if v is None:
        return ""

    try:
        ts = pd.to_datetime(v, errors="coerce")
        if pd.isna(ts):
            return ""
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(v)


def _row_to_output_dict(row: pd.Series, yyyymm: str) -> Dict[str, Any]:
    """
    前端 defect_map.js 會吃：
      x, y, defect_size, pic_path, pic_name,
      test_time, recipe_id, adc_def_code, chip_id/chip_name
    """
    x_col = _first_existing_col(
        pd.DataFrame(columns=row.index),
        ["pox_x1", "pox_x", "coord_x", "x"]
    )

    y_col = _first_existing_col(
        pd.DataFrame(columns=row.index),
        ["pox_y1", "pox_y", "coord_y", "y"]
    )

    x_val = row.get(x_col, "") if x_col else ""
    y_val = row.get(y_col, "") if y_col else ""

    chip_val = (
        row.get("chip_id", "")
        or row.get("chip_name", "")
        or row.get("chip", "")
        or ""
    )

    return {
        "sheet_id_chip_id": str(row.get("sheet_id_chip_id", "") or "").strip(),
        "adc_def_code": str(row.get("adc_def_code", "") or "").strip(),
        "defect_size": str(row.get("defect_size", "") or "").strip(),

        "x": x_val,
        "y": y_val,
        "pox_x1": x_val,
        "pox_y1": y_val,

        "test_time": _format_dt_for_json(row.get("test_time", "")),
        "pi_time": _format_dt_for_json(row.get("pi_time", "")),

        "recipe_id": str(row.get("recipe_id", "") or "").strip(),
        "chip_id": str(chip_val or "").strip(),
        "chip_name": str(chip_val or "").strip(),

        "pic_path": _build_pic_path(row, yyyymm),
        "pic_name": str(row.get("image_file_name", "") or "").strip(),
    }


# =============================================================================
# Request model
# =============================================================================
class DefectMapIn(BaseModel):
    rows: List[Dict[str, Any]] = []


# =============================================================================
# Main route
# =============================================================================
@router.post("/defect_map")
async def defect_map(payload: DefectMapIn):
    cim_cfg = DensityJobConfig()
    cim_db = MySQLConnet(cim_cfg.src_db)

    if not payload.rows:
        return {"DefectGroupDict": {}}

    row_in = payload.rows[0]
    logger.info(f"[defect_map] frontend row_in={row_in}")

    # -------------------------------------------------------------------------
    # 1) Parse front-end row
    # -------------------------------------------------------------------------
    pi_hour = _norm_str(row_in.get("pi_hour", ""))
    aoi = _norm_str(row_in.get("aoi", ""))
    line_id = _norm_str(row_in.get("line_id", ""))
    def_code = _norm_str(row_in.get("adc_def_code", ""))
    recipe_id = _norm_str(row_in.get("recipe_id", ""))
    model = _norm_str(row_in.get("model", ""))

    """
    if not pi_hour:
        raise HTTPException(status_code=400, detail="pi_hour is required")

    if not aoi:
        raise HTTPException(status_code=400, detail="aoi is required")

    if not line_id:
        raise HTTPException(status_code=400, detail="line_id is required")

    if not def_code:
        raise HTTPException(status_code=400, detail="adc_def_code is required")
    """
    try:
        pi_dt = parse_pi_hour_to_dt(pi_hour)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"pi_hour format error: {pi_hour} ({e})",
        )

    # -------------------------------------------------------------------------
    # 2) Parse glass_size_detail and collect only T > 0 glasses
    # -------------------------------------------------------------------------
    gld_details_raw = row_in.get("glass_size_detail", "")
    gld_details = _safe_json_loads(gld_details_raw)
    glds, test_time_map = _extract_defect_glasses_and_test_times(gld_details)

    """
    if not glds:
        logger.info(
            "[defect_map] no glass with T > 0; return empty. "
            f"pi_hour={pi_hour}, aoi={aoi}, line_id={line_id}, "
            f"def_code={def_code}, recipe_id={recipe_id}, model={model}"
        )
        return {"DefectGroupDict": {}}
    """

    # -------------------------------------------------------------------------
    # 3) Determine query months
    #
    # 新版優先使用 glass_size_detail 裡每片 glass 的 test_time。
    # 若沒有 test_time，才退回 pi_hour ±3 days。
    # -------------------------------------------------------------------------
    if test_time_map:
        min_dt = min(test_time_map.values()) - timedelta(minutes=5)
        max_dt = max(test_time_map.values()) + timedelta(minutes=5)
    else:
        min_dt = pi_dt - timedelta(days=3)
        max_dt = pi_dt + timedelta(days=3)

    months = _months_between(min_dt, max_dt)
    base_keys = {
        'recipe_id':recipe_id,
        'pi_hour':pi_dt,
        'pi_type':'API'
    }
    logger.info(
        "[defect_map] query "
        f"pi_hour={pi_hour}, pi_dt={pi_dt}, "
        f"min_dt={min_dt}, max_dt={max_dt}, months={months}, "
        f"aoi={aoi}, line_id={line_id}, def_code={def_code}, "
        f"recipe_id={recipe_id}, model={model}, "
        f"glds={len(glds)}, test_time_map={len(test_time_map)}"
    )

    # -------------------------------------------------------------------------
    # 4) Fetch raw defect rows by month
    #
    # 這裡刻意只用 sheet_id_chip_id IN 先撈。
    # 原因：不同版本 raw defect 表欄位可能不同，
    #       用 base_keys 直接塞 pi_hour / recipe_id / adc_def_code 容易查不到。
    #       撈出後再依欄位是否存在做 DataFrame filter。
    # -------------------------------------------------------------------------
    df_parts: List[pd.DataFrame] = []

    for ym in months:
        yyyymm = str(ym)
        tbn = _defect_table_name(cim_cfg, yyyymm, aoi, line_id)

        logger.info(f"[defect_map] table={tbn}")

        if not cim_db.table_exists(tbn):
            logger.warning(f"[defect_map] missing raw defect table: {tbn}")
            continue

        try:
            def_df = cim_db.get_rows_df_in(
                table_name=tbn,
                base_keys=base_keys,
                in_key="sheet_id_chip_id",
                in_values=list(glds),
            )
        except Exception as e:
            logger.exception(f"[defect_map] query raw defect failed: table={tbn}, error={e}")
            raise HTTPException(
                status_code=500,
                detail=f"query raw defect failed: table={tbn}, error={e}",
            )

        if def_df is None or def_df.empty:
            logger.info(f"[defect_map] no raw rows: table={tbn}, in_values={list(glds)}")
            continue
        
        def_df = def_df.copy()
        def_df["_src_yyyymm"] = yyyymm
        def_df["_src_table"] = tbn

        df_parts.append(def_df)


    # -------------------------------------------------------------------------
    # 5) Build empty output if no raw rows
    # -------------------------------------------------------------------------
    out: Dict[str, Any] = {}

    if not df_parts:
        for gld in sorted(glds):
            out[gld] = {}

        logger.warning(
            "[defect_map] get zero defect after query. "
            f"pi_hour={pi_hour}, aoi={aoi}, line_id={line_id}, "
            f"def_code={def_code}, recipe_id={recipe_id}, glds={len(glds)}"
        )
        return {"DefectGroupDict": out}

    df_all = pd.concat(df_parts, ignore_index=True)
    df_all["test_time"] = pd.to_datetime(df_all["test_time"], errors="coerce")
    df_all = df_all.dropna(subset=["test_time"]).copy()

    if df_all.empty:
        for gld in sorted(glds):
            out[gld] = {}
        return {"DefectGroupDict": out}

    # -------------------------------------------------------------------------
    # 6) Pick latest / matched test_time rows per glass
    # -------------------------------------------------------------------------
    df_latest = _choose_latest_rows_per_glass(
        df_all=df_all,
        glds=glds,
        test_time_map=test_time_map,
        tolerance_sec=2,
    )

    if df_latest.empty:
        for gld in sorted(glds):
            out[gld] = {}

        logger.warning(
            "[defect_map] get zero defect after choose_latest. "
            f"pi_hour={pi_hour}, aoi={aoi}, line_id={line_id}, "
            f"def_code={def_code}, recipe_id={recipe_id}, glds={len(glds)}"
        )
        return {"DefectGroupDict": out}

    # -------------------------------------------------------------------------
    # 7) Build output per glass
    # -------------------------------------------------------------------------
    df_latest["sheet_id_chip_id"] = df_latest["sheet_id_chip_id"].astype(str).str.strip()

    for gld in sorted(glds):
        def_tb = df_latest[df_latest["sheet_id_chip_id"] == str(gld)].copy()

        if def_tb.empty:
            out[gld] = {}
            continue

        rows_dict: Dict[str, Any] = {}

        for idx, row in def_tb.reset_index(drop=True).iterrows():
            yyyymm = str(row.get("_src_yyyymm", "") or "")
            rows_dict[str(idx)] = _row_to_output_dict(row, yyyymm)

        out[gld] = rows_dict

        try:
            logger.info(
                "[defect_map] output glass "
                f"gld={gld}, rows={len(rows_dict)}, "
                f"test_time={def_tb['test_time'].dropna().astype(str).unique().tolist()[:3]}"
            )
        except Exception:
            pass

    all_codes = []

    if not df_latest.empty and "adc_def_code" in df_latest.columns:
        all_codes = sorted(
            df_latest["adc_def_code"]
            .astype(str)
            .str.strip()
            .replace({
                "": "",
                "nan": "",
                "NaN": "",
                "None": "",
                "NULL": "",
            })
            .dropna()
            .unique()
            .tolist()
        )

    # 確保觸發的 defect code 一定在選單裡
    if def_code and def_code not in all_codes:
        all_codes.insert(0, def_code)

    return {
        "TriggerDefCode": def_code,
        "DefectCodeList": all_codes,
        "DefectGroupDict": out,
    }