# routers/common/density_csv.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from models.sql_db_connect import MySQLConnet


router = APIRouter(prefix="/density_csv", tags=["duty_cell_piaoi_density_csv"])


# =============================================================================
# Request
# =============================================================================
class DensityCsvRequest(BaseModel):
    system: str
    start_date: str
    end_date: str
    limit: Optional[int] = None


# =============================================================================
# Export Config
# =============================================================================
@dataclass
class DensityCsvExportConfig:
    system: str
    db_name: str
    main_table_tpl: str
    time_col: str
    export_columns: Optional[List[str]] = None
    preview_limit: int = 5000

    # only for aoi_density join tab summary
    tab_table_tpl: Optional[str] = None
    tab_time_col: str = "pi_hour"


# =============================================================================
# System helpers
# =============================================================================
def _normalize_system(system: str) -> str:
    s = (system or "").strip()

    aliases = {
        "aoi-density": "aoi_density",
        "aoi_density": "aoi_density",

        "aoi-bpi-density": "aoi_bpi_density",
        "aoi_bpi_density": "aoi_bpi_density",
        "bpi_density": "aoi_bpi_density",

        "aoi-inspection-density": "aoi_inspection_density",
        "aoi_inspection_density": "aoi_inspection_density",
        "inspection_density": "aoi_inspection_density",

        "bpi_same_point": "bpi_same_point",
        "bpi-api-same-point": "bpi_same_point",
        "bpi_api_same_point": "bpi_same_point",
        "same_point": "bpi_same_point",
    }

    return aliases.get(s, s)


def _normalize_monthly_tpl(tpl: str, fallback: str) -> str:
    """
    支援：
      1) xxx_yyyymm
      2) xxx_202605 -> xxx_yyyymm
    """
    s = str(tpl or "").strip()
    if not s:
        s = fallback

    if "yyyymm" in s:
        return s

    if re.search(r"_\d{6}$", s):
        return re.sub(r"_\d{6}$", "_yyyymm", s)

    return s


def _csv_columns_from_api_config(api_cfg, tab_key: str = "csv_download") -> Optional[List[str]]:
    """
    從 API_Config.tab_filter_config[tab_key]["table_columns"] 取得 CSV 欄位 key。
    """
    table_cols = (
        getattr(api_cfg, "tab_filter_config", {})
        .get(tab_key, {})
        .get("table_columns", {})
    )

    if isinstance(table_cols, dict) and table_cols:
        return list(table_cols.keys())

    return None


def _resolve_export_config(system: str) -> DensityCsvExportConfig:
    """
    Resolve:
      - db_name
      - main_table_tpl
      - time_col
      - export_columns
      - tab_table_tpl for aoi_density
    """
    key = _normalize_system(system)

    # ------------------------------------------------------------
    # AOI Density
    # ------------------------------------------------------------
    if key == "aoi_density":
        from models.piaoi.density.cim_density_job import Config as AoiDensityJobConfig
        from models.piaoi.density.API_Config import API_Config as AoiDensityApiConfig

        job_cfg = AoiDensityJobConfig()
        api_cfg = AoiDensityApiConfig(job_cfg)

        return DensityCsvExportConfig(
            system=key,
            db_name=job_cfg.out_db,
            main_table_tpl=getattr(job_cfg, "code_table_tpl", "density_code_summary_yyyymm"),
            time_col="pi_hour",
            export_columns=_csv_columns_from_api_config(api_cfg, "csv_download"),
            preview_limit=5000,
            tab_table_tpl=getattr(job_cfg, "tab_table_tpl", "density_tab_summary_yyyymm"),
            tab_time_col="pi_hour",
        )

    # ------------------------------------------------------------
    # BPI Density - 新版 API_Config
    # ------------------------------------------------------------
    if key == "aoi_bpi_density":
        from models.piaoi.bpi_density.API_Config import API_Config as BPIApiConfig

        api_cfg = BPIApiConfig()

        return DensityCsvExportConfig(
            system=key,
            db_name=api_cfg.bpi_density_db_name,
            main_table_tpl=_normalize_monthly_tpl(
                api_cfg.bpi_density_summary_table_tpl,
                "bpi_api_summary_yyyymm",
            ),
            time_col="scan_hour",
            export_columns=_csv_columns_from_api_config(api_cfg, "bpi_density_csv_download"),
            preview_limit=5000,
        )

    # ------------------------------------------------------------
    # BPI/API Same Point
    # ------------------------------------------------------------
    if key == "bpi_same_point":
        from models.piaoi.bpi_density.API_Config import API_Config as BPIApiConfig

        api_cfg = BPIApiConfig()

        return DensityCsvExportConfig(
            system=key,
            db_name=api_cfg.bpi_same_point_db_name,
            main_table_tpl=_normalize_monthly_tpl(
                api_cfg.bpi_same_point_offset_table_tpl,
                "bpi_api_same_point_offset_summary_yyyymm",
            ),
            time_col="scan_hour",
            export_columns=_csv_columns_from_api_config(api_cfg, "bpi_same_point_csv_download"),
            preview_limit=5000,
        )

    # ------------------------------------------------------------
    # AOI Inspection Density
    # ------------------------------------------------------------
    if key == "aoi_inspection_density":
        from models.inspection_density.API_Config import InspectionDensityApiConfig

        api_cfg = InspectionDensityApiConfig()

        db_name = (
            getattr(api_cfg, "db_name", None)
            or getattr(api_cfg, "out_db", None)
            or getattr(getattr(api_cfg, "core_cfg", None), "TARGET_DB", None)
            or "piaoi_inspection_density"
        )

        table_tpl = (
            getattr(api_cfg, "api_summary_table_tpl", None)
            or getattr(api_cfg, "summary_table_tpl", None)
            or getattr(api_cfg, "out_table_tpl", None)
            or "inspection_api_summary_yyyymm"
        )

        time_col = (
            getattr(api_cfg, "summary_time_col", None)
            or getattr(api_cfg, "time_col", None)
            or "pi_hour"
        )

        return DensityCsvExportConfig(
            system=key,
            db_name=db_name,
            main_table_tpl=table_tpl,
            time_col=time_col,
            export_columns=_csv_columns_from_api_config(api_cfg, "csv_download"),
            preview_limit=5000,
        )

    raise HTTPException(status_code=400, detail=f"unknown system: {system}")


# =============================================================================
# Time helpers
# =============================================================================
def _parse_date_only(s: str) -> datetime:
    s = str(s).strip().replace("T", " ")

    for fmt in ("%Y-%m-%d", "%y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
        except ValueError:
            continue

    raise ValueError(f"Bad date: {s}")


def _to_query_range(start_date: str, end_date: str) -> tuple[datetime, datetime]:
    """
    Density 頁面日期語意：
      日期 D = [D 07:00, D+1 07:00)

    若 start > end，會自動交換。
    """
    st = _parse_date_only(start_date)
    ed = _parse_date_only(end_date)

    if ed < st:
        st, ed = ed, st

    start = st.replace(hour=7, minute=0, second=0, microsecond=0)
    end_exclusive = (ed + timedelta(days=1)).replace(
        hour=7,
        minute=0,
        second=0,
        microsecond=0,
    )

    return start, end_exclusive


def _iter_yyyymm(start_dt: datetime, end_dt: datetime) -> List[str]:
    if end_dt <= start_dt:
        return []

    end_incl = end_dt - timedelta(seconds=1)

    cur = datetime(start_dt.year, start_dt.month, 1)
    end_m = datetime(end_incl.year, end_incl.month, 1)

    out: List[str] = []

    while cur <= end_m:
        out.append(cur.strftime("%Y%m"))

        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)

    return out


# =============================================================================
# SQL helpers
# =============================================================================
def _read_monthly_table(
    *,
    export_cfg: DensityCsvExportConfig,
    table_tpl: str,
    time_col: str,
    start_dt: datetime,
    end_dt: datetime,
    limit: Optional[int] = None,
) -> pd.DataFrame:
    db = MySQLConnet(export_cfg.db_name)
    months = _iter_yyyymm(start_dt, end_dt)

    frames: List[pd.DataFrame] = []

    for ym in months:
        table_name = table_tpl.replace("yyyymm", ym).lower()

        if not db.table_exists(table_name):
            continue

        sql = f"""
            SELECT *
            FROM `{db.db}`.`{table_name}`
            WHERE `{time_col}` >= :start_dt
              AND `{time_col}` <  :end_dt
        """

        params = {
            "start_dt": start_dt,
            "end_dt": end_dt,
        }

        if limit is not None:
            sql += " LIMIT :limit"
            params["limit"] = int(limit)

        part = db.query_df(sql, params)

        if part is not None and not part.empty:
            if "source_table" in part.columns:
                if "_export_source_table" not in part.columns:
                    part.insert(0, "_export_source_table", table_name)
                else:
                    part["_export_source_table"] = table_name
            else:
                part.insert(0, "source_table", table_name)

            frames.append(part)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


# =============================================================================
# Density / alias helpers
# =============================================================================
def _compute_export_density(df: pd.DataFrame, system: str) -> pd.DataFrame:
    """
    依 system 補/覆寫 CSV 輸出用 density。
    """
    if df is None or df.empty:
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()

    out = df.copy()
    key = _normalize_system(system)

    def div(num_col: str, den_col: str):
        if num_col not in out.columns or den_col not in out.columns:
            return None

        num = pd.to_numeric(out[num_col], errors="coerce").fillna(0)
        den = pd.to_numeric(out[den_col], errors="coerce").replace(0, pd.NA)
        return (num / den).fillna(0).round(6)

    if key == "aoi_density":
        v = div("defect_cnt", "tab_total_glass_cnt")
        if v is not None:
            out["density"] = v
        return out

    if key == "aoi_inspection_density":
        v = div("maingroup_defect_count", "maingroup_glass_count")
        if v is not None:
            out["density"] = v

        if "maingroup_glass_count" in out.columns and "total_glass_cnt" not in out.columns:
            out["total_glass_cnt"] = out["maingroup_glass_count"]

        if "maingroup_defect_count" in out.columns and "defect_cnt" not in out.columns:
            out["defect_cnt"] = out["maingroup_defect_count"]

        return out

    if key == "aoi_bpi_density":
        candidates = [
            ("total_defect_count", "glass_count"),
            ("defect_cnt", "glass_count"),
            ("total_def", "glass_count"),
            ("def_cnt", "glass_count"),
            ("total_defect_count", "glass_cnt"),
            ("defect_cnt", "glass_cnt"),
        ]

        for num_col, den_col in candidates:
            v = div(num_col, den_col)
            if v is not None:
                out["density"] = v

                if den_col in out.columns and "total_glass_cnt" not in out.columns:
                    out["total_glass_cnt"] = out[den_col]

                if num_col in out.columns and "defect_cnt" not in out.columns:
                    out["defect_cnt"] = out[num_col]

                break

        return out

    if key == "bpi_same_point":
        # 同點明細下載不一定需要 density。
        # 若需要同點 density：每 row 是一片 glass pair，所以分母=1。
        if "matched_pair_count" in out.columns and "same_point_density" not in out.columns:
            out["same_point_density"] = pd.to_numeric(
                out["matched_pair_count"],
                errors="coerce",
            ).fillna(0).round(6)

        return out

    return out


def _apply_export_columns(df: pd.DataFrame, columns: Optional[List[str]]) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()

    out = df.copy()

    if not columns:
        return out

    for c in columns:
        if c not in out.columns:
            out[c] = ""

    return out[columns].copy()


# =============================================================================
# AOI Density join logic
# =============================================================================
def _recipe_to_tabs(recipe_id: object) -> List[str]:
    s = "" if recipe_id is None else str(recipe_id).strip()

    if len(s) == 4:
        if s.startswith("2"):
            return ["UPI"]
        if s.startswith("0"):
            return ["PISpot", "SPS"]

    if len(s) == 3:
        return ["UPI", "PISpot", "SPS"]

    return []


def _read_aoi_density_joined(
    *,
    export_cfg: DensityCsvExportConfig,
    start_dt: datetime,
    end_dt: datetime,
    limit: Optional[int] = None,
) -> pd.DataFrame:
    code_df = _read_monthly_table(
        export_cfg=export_cfg,
        table_tpl=export_cfg.main_table_tpl,
        time_col=export_cfg.time_col,
        start_dt=start_dt,
        end_dt=end_dt,
        limit=limit,
    )

    if code_df is None or code_df.empty:
        return pd.DataFrame(columns=export_cfg.export_columns or [])

    if not export_cfg.tab_table_tpl:
        code_df = _compute_export_density(code_df, export_cfg.system)
        return _apply_export_columns(code_df, export_cfg.export_columns)

    tab_df = _read_monthly_table(
        export_cfg=export_cfg,
        table_tpl=export_cfg.tab_table_tpl,
        time_col=export_cfg.tab_time_col,
        start_dt=start_dt,
        end_dt=end_dt,
        limit=None,
    )

    code_df["pi_hour"] = pd.to_datetime(code_df["pi_hour"], errors="coerce")
    code_df = code_df.dropna(subset=["pi_hour"]).copy()

    if "source_table" in code_df.columns:
        code_df.rename(columns={"source_table": "code_source_table"}, inplace=True)

    if tab_df is None or tab_df.empty:
        code_df["tab_name"] = ""
        code_df["tab_total_glass_cnt"] = 0
        code_df["tab_total_defect_cnt"] = 0
        code_df["tab_total_density"] = 0.0
        code_df["recipe_list"] = ""
        code_df["tab_source_table"] = ""

        code_df = _compute_export_density(code_df, export_cfg.system)
        return _apply_export_columns(code_df, export_cfg.export_columns)

    tab_df["pi_hour"] = pd.to_datetime(tab_df["pi_hour"], errors="coerce")
    tab_df = tab_df.dropna(subset=["pi_hour"]).copy()

    if "source_table" in tab_df.columns:
        tab_df.rename(columns={"source_table": "tab_source_table"}, inplace=True)

    code_df["__tabs"] = code_df["recipe_id"].apply(_recipe_to_tabs)
    code_expanded = code_df.explode("__tabs").rename(columns={"__tabs": "tab_name"})
    code_expanded = code_expanded.dropna(subset=["tab_name"]).copy()
    code_expanded = code_expanded[code_expanded["tab_name"].astype(str).str.len() > 0].copy()

    if code_expanded.empty:
        code_df["tab_name"] = ""
        code_df["tab_total_glass_cnt"] = 0
        code_df["tab_total_defect_cnt"] = 0
        code_df["tab_total_density"] = 0.0
        code_df["recipe_list"] = ""
        code_df["tab_source_table"] = ""

        code_df = _compute_export_density(code_df, export_cfg.system)
        return _apply_export_columns(code_df, export_cfg.export_columns)

    join_keys = [
        "line_id",
        "aoi",
        "model",
        "glass_type",
        "pi_hour",
        "tab_name",
    ]

    tab_cols = join_keys + [
        "tab_total_glass_cnt",
        "tab_total_defect_cnt",
        "tab_total_density",
        "recipe_list",
    ]

    if "tab_source_table" in tab_df.columns:
        tab_cols.append("tab_source_table")

    existing_tab_cols = [c for c in tab_cols if c in tab_df.columns]

    out = code_expanded.merge(
        tab_df[existing_tab_cols].drop_duplicates(subset=join_keys),
        on=join_keys,
        how="left",
    )

    for c in ["tab_total_glass_cnt", "tab_total_defect_cnt", "tab_total_density"]:
        if c not in out.columns:
            out[c] = 0
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)

    if "recipe_list" not in out.columns:
        out["recipe_list"] = ""

    if "tab_source_table" not in out.columns:
        out["tab_source_table"] = ""

    out = _compute_export_density(out, export_cfg.system)
    return _apply_export_columns(out, export_cfg.export_columns)


# =============================================================================
# Common read
# =============================================================================
def _read_export_dataframe(
    *,
    export_cfg: DensityCsvExportConfig,
    start_dt: datetime,
    end_dt: datetime,
    limit: Optional[int] = None,
) -> pd.DataFrame:
    if export_cfg.system == "aoi_density":
        return _read_aoi_density_joined(
            export_cfg=export_cfg,
            start_dt=start_dt,
            end_dt=end_dt,
            limit=limit,
        )

    df = _read_monthly_table(
        export_cfg=export_cfg,
        table_tpl=export_cfg.main_table_tpl,
        time_col=export_cfg.time_col,
        start_dt=start_dt,
        end_dt=end_dt,
        limit=limit,
    )

    df = _compute_export_density(df, export_cfg.system)
    return _apply_export_columns(df, export_cfg.export_columns)


def _count_export_rows(
    *,
    export_cfg: DensityCsvExportConfig,
    start_dt: datetime,
    end_dt: datetime,
) -> int:
    df = _read_export_dataframe(
        export_cfg=export_cfg,
        start_dt=start_dt,
        end_dt=end_dt,
        limit=None,
    )

    if df is None or df.empty:
        return 0

    return int(len(df))


def _csv_filename(system: str, start_date: str, end_date: str) -> str:
    clean_system = _normalize_system(system)
    s = start_date.replace("-", "")
    e = end_date.replace("-", "")
    return f"{clean_system}_{s}_{e}.csv"


# =============================================================================
# APIs
# =============================================================================
@router.post("/preview")
async def preview_density_csv(req: DensityCsvRequest):
    try:
        export_cfg = _resolve_export_config(req.system)
        start_dt, end_dt = _to_query_range(req.start_date, req.end_date)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"bad request: {e}")

    try:
        preview_limit = req.limit

        preview_df = _read_export_dataframe(
            export_cfg=export_cfg,
            start_dt=start_dt,
            end_dt=end_dt,
            limit=preview_limit,
        )

        total_count = _count_export_rows(
            export_cfg=export_cfg,
            start_dt=start_dt,
            end_dt=end_dt,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"query failed: {repr(e)}")

    if preview_df is None or preview_df.empty:
        return {
            "ok": True,
            "system": export_cfg.system,
            "columns": export_cfg.export_columns or [],
            "rows": [],
            "preview_count": 0,
            "total_count": total_count,
            "count": 0,
        }

    preview_df = preview_df.fillna("")
    preview_count = int(len(preview_df))

    return {
        "ok": True,
        "system": export_cfg.system,
        "columns": preview_df.columns.tolist(),
        "rows": preview_df.to_dict(orient="records"),
        "preview_count": preview_count,
        "total_count": total_count,
        "count": preview_count,
    }


@router.post("/download")
async def download_density_csv(req: DensityCsvRequest):
    try:
        export_cfg = _resolve_export_config(req.system)
        start_dt, end_dt = _to_query_range(req.start_date, req.end_date)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"bad request: {e}")

    try:
        df = _read_export_dataframe(
            export_cfg=export_cfg,
            start_dt=start_dt,
            end_dt=end_dt,
            limit=None,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"download query failed: {repr(e)}")

    if df is None:
        df = pd.DataFrame()

    df = df.fillna("")

    csv_bytes = df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    mem = io.BytesIO(csv_bytes)
    mem.seek(0)

    filename = _csv_filename(export_cfg.system, req.start_date, req.end_date)

    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{filename}"
    }

    return StreamingResponse(
        mem,
        media_type="text/csv; charset=utf-8",
        headers=headers,
    )