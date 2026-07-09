# routers/cell_aoi_to_array/cell_aoi_to_array.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import inspect, text

from models.sql_db_connect import MySQLConnet

from models.cell_aoi_to_array.API_Config import (
    AOI_FEATURE,
    INSPECTION_FEATURE,
    AOI_INSPEC_FEATURE,

    SOURCE_DB_NAME,
    CELL_DB_NAME,
    INSPECTION_SOURCE_DB_NAME,
    INSPECTION_INPUT_DB_NAME,

    API_AOI_SUMMARY_BASE,
    SAME_POINT_DETAIL_BASE,
    GLASS_SUMMARY_BASE,

    API_INSPECTION_SUMMARY_BASE,
    INSPECTION_SAME_POINT_DETAIL_BASE,
    INSPECTION_GLASS_SUMMARY_BASE,

    SOURCE_CF_OC_RAW_BASE,
    SOURCE_CF_PS_RAW_BASE,
    SOURCE_ARRAY_MOR_RAW_BASE,
    SOURCE_ARRAY_TAR_RAW_BASE,
    SOURCE_ARRAY_TOS_RAW_BASE,

    CELL_AOI_TO_ARRAY_CHARTS,
    CELL_AOI_TO_ARRAY_FEATURES,
    CELL_AOI_TO_ARRAY_LINE_OPTIONS,
    CELL_AOI_TO_ARRAY_MATCH_STATUS_OPTIONS,
    CELL_AOI_TO_ARRAY_PI_TYPES,
    CELL_AOI_TO_ARRAY_SHEET_TYPES,
    CELL_AOI_TO_ARRAY_SOURCE_OP_OPTIONS,

    INSPECTION_SOURCE_OP_OPTIONS,
    INSPECTION_MATCH_STATUS_OPTIONS,

    default_date_range,
    get_feature_config,
    get_feature_db_config,
    get_feature_ui_config,
    now_text,
    table_name_by_yyyymm,
)

router = APIRouter(tags=["duty_cell_cell_aoi_to_array"])


# =============================================================================
# Pydantic Models
# =============================================================================

class CellAoiToArrayFilters(BaseModel):
    startDate: Optional[str] = None
    endDate: Optional[str] = None

    # 舊前端欄位：tool 對應 line_id
    tool: Optional[str] = None
    sheetType: Optional[str] = None
    sheetId: Optional[str] = None

    # CSV 多片 sheet 查詢
    sheetIds: Optional[List[str]] = None
    sheet_ids: Optional[List[str]] = None

    # 新版真實資料欄位
    lineId: Optional[str] = None
    aoi: Optional[str] = None
    piType: Optional[str] = None
    sourceOpId: Optional[str] = None
    matchStatus: Optional[str] = None
    modelNo: Optional[str] = None
    recipeId: Optional[str] = None


class CellAoiToArrayCompareRequest(BaseModel):
    category: str = Field(default="PI")
    feature: str = Field(default=AOI_FEATURE)
    filters: CellAoiToArrayFilters = Field(default_factory=CellAoiToArrayFilters)


class CellAoiToArrayCompareResponse(BaseModel):
    feature: str
    title: str
    info: Dict[str, str]
    summary: Dict[str, Any]
    rows: List[Dict[str, Any]]
    chartData: Dict[str, Dict[str, Any]]
    uiConfig: Dict[str, Any]


class CellAoiToArrayDetailRequest(BaseModel):
    feature: str = Field(default=AOI_FEATURE)
    sheet_id_chip_id: str
    test_time: str
    pi_type: Optional[str] = None
    source_op_id: str


class CellAoiToArrayDetailResponse(BaseModel):
    feature: str
    detail: Dict[str, Any]
    defects: List[Dict[str, Any]]
    defectGroups: Dict[str, List[Dict[str, Any]]]
    groupsLoaded: Dict[str, bool]
    uiConfig: Dict[str, Any]


class CellAoiToArrayDefectGroupsRequest(BaseModel):
    feature: str = Field(default=AOI_FEATURE)
    sheet_id_chip_id: str
    test_time: str
    pi_type: Optional[str] = None
    source_op_id: str


class CellAoiToArrayDefectGroupsResponse(BaseModel):
    feature: str
    defectGroups: Dict[str, List[Dict[str, Any]]]
    groupsLoaded: Dict[str, bool]


class CellAoiToArrayUpdateActionRequest(BaseModel):
    feature: str = Field(default=AOI_FEATURE)

    sheet_id_chip_id: str
    test_time: str
    pi_type: Optional[str] = None
    source_op_id: str

    comment: Optional[str] = None
    action: Optional[str] = None
    editor: Optional[str] = None


class CellAoiToArrayUpdateActionResponse(BaseModel):
    ok: bool
    affected: int
    message: str


# =============================================================================
# Routes
# =============================================================================

@router.get("/config")
def get_cell_aoi_to_array_config() -> Dict[str, Any]:
    dr = default_date_range(days=3)

    return {
        "defaultCategory": "PI",
        "defaultFeatureByCategory": {
            "PI": AOI_FEATURE,
        },
        "categoryTabs": [
            {"key": "PI", "label": "PI"},
        ],
        "featureTabsByCategory": {
            "PI": [
                get_feature_ui_config(AOI_FEATURE),
                get_feature_ui_config(INSPECTION_FEATURE),
                # get_feature_ui_config(AOI_INSPEC_FEATURE),
            ],
        },
        "featureConfigByFeature": {
            key: get_feature_ui_config(key)
            for key in CELL_AOI_TO_ARRAY_FEATURES.keys()
        },
        "sheetTypes": CELL_AOI_TO_ARRAY_SHEET_TYPES,
        "piTypes": CELL_AOI_TO_ARRAY_PI_TYPES,
        "lineOptions": CELL_AOI_TO_ARRAY_LINE_OPTIONS,
        "sourceOpOptions": CELL_AOI_TO_ARRAY_SOURCE_OP_OPTIONS,
        "inspectionSourceOpOptions": INSPECTION_SOURCE_OP_OPTIONS,
        "matchStatusOptions": CELL_AOI_TO_ARRAY_MATCH_STATUS_OPTIONS,
        "inspectionMatchStatusOptions": INSPECTION_MATCH_STATUS_OPTIONS,
        "summaryCards": [
            {
                "key": "cell_total",
                "label": "Cell 總抽檢數 (TFT + CF)",
            },
            {
                "key": "array_same_by_station",
                "label": "ARRAY",
            },
            {
                "key": "cf_same_by_station",
                "label": "CF",
            },
        ],
        "defaultFilters": {
            "startDate": dr["startDate"],
            "endDate": dr["endDate"],
            "tool": "",
            "sheetType": "",
            "sheetId": "",

            "sheetIds": [],
            "sheetCsvFileName": "",

            "lineId": "",
            "aoi": "",
            "piType": "",
            "sourceOpId": "",
            "matchStatus": "",
            "modelNo": "",
            "recipeId": "",
        },
        "pageSize": 10,
    }


@router.post("/compare", response_model=CellAoiToArrayCompareResponse)
def compare_cell_aoi_to_array(req: CellAoiToArrayCompareRequest) -> CellAoiToArrayCompareResponse:
    feature_key = req.feature or AOI_FEATURE

    if feature_key not in CELL_AOI_TO_ARRAY_FEATURES:
        raise HTTPException(status_code=400, detail=f"Unsupported feature: {feature_key}")

    feature_cfg = get_feature_config(feature_key)
    ui_config = get_feature_ui_config(feature_key)
    db_cfg = get_feature_db_config(feature_key)

    all_rows = load_real_summary_rows(feature_key=feature_key, filters=req.filters)
    chart_data = build_chart_data(feature_key=feature_key, rows=all_rows)
    summary = build_summary(feature_key=feature_key, rows=all_rows)

    return CellAoiToArrayCompareResponse(
        feature=feature_key,
        title=feature_cfg["title"],
        info={
            "left": f"資料更新：{now_text()} | Source: {db_cfg.get('source_table')}",
            "linkText": "預留連結功能",
            "linkHref": "#",
        },
        summary=summary,
        rows=all_rows,
        chartData=chart_data,
        uiConfig=ui_config,
    )


@router.post("/detail", response_model=CellAoiToArrayDetailResponse)
def get_cell_aoi_to_array_detail(req: CellAoiToArrayDetailRequest) -> CellAoiToArrayDetailResponse:
    feature_key = req.feature or AOI_FEATURE

    if feature_key not in CELL_AOI_TO_ARRAY_FEATURES:
        raise HTTPException(status_code=400, detail=f"Unsupported feature: {feature_key}")

    ui_config = get_feature_ui_config(feature_key)

    detail = load_same_point_detail(
        feature_key=feature_key,
        sheet_id_chip_id=req.sheet_id_chip_id,
        test_time=req.test_time,
        pi_type=req.pi_type,
        source_op_id=req.source_op_id,
    )

    point_rows = parse_point_detail_to_frontend_rows(
        point_detail=detail.get("point_detail"),
        abbr_cat=detail.get("abbr_cat"),
        source_op_id=detail.get("source_op_id"),
    )

    same_point_group = parse_point_detail_to_same_point_group(
        point_detail=detail.get("point_detail"),
        source_op_id=detail.get("source_op_id"),
    )

    return CellAoiToArrayDetailResponse(
        feature=feature_key,
        detail=detail,
        defects=point_rows,
        defectGroups={
            "same_point": same_point_group,
            "cell_aoi": [],
            "source": [],
        },
        groupsLoaded={
            "same_point": True,
            "cell_aoi": False,
            "source": False,
        },
        uiConfig=ui_config,
    )


@router.post("/detail-defect-groups", response_model=CellAoiToArrayDefectGroupsResponse)
def get_cell_aoi_to_array_detail_defect_groups(
    req: CellAoiToArrayDefectGroupsRequest,
) -> CellAoiToArrayDefectGroupsResponse:
    feature_key = req.feature or AOI_FEATURE

    if feature_key not in CELL_AOI_TO_ARRAY_FEATURES:
        raise HTTPException(status_code=400, detail=f"Unsupported feature: {feature_key}")

    detail = load_same_point_detail(
        feature_key=feature_key,
        sheet_id_chip_id=req.sheet_id_chip_id,
        test_time=req.test_time,
        pi_type=req.pi_type,
        source_op_id=req.source_op_id,
    )

    groups = load_full_defect_groups(
        feature_key=feature_key,
        detail=detail,
        sheet_id_chip_id=req.sheet_id_chip_id,
        test_time=req.test_time,
        pi_type=req.pi_type or detail.get("cell_op") or detail.get("pi_type"),
        source_op_id=req.source_op_id or detail.get("source_op_id"),
    )

    return CellAoiToArrayDefectGroupsResponse(
        feature=feature_key,
        defectGroups={
            "cell_aoi": groups.get("cell_aoi", []),
            "source": groups.get("source", []),
        },
        groupsLoaded={
            "cell_aoi": True,
            "source": True,
        },
    )


@router.post("/update-action", response_model=CellAoiToArrayUpdateActionResponse)
def update_cell_aoi_to_array_action(
    req: CellAoiToArrayUpdateActionRequest,
) -> CellAoiToArrayUpdateActionResponse:
    feature_key = req.feature or AOI_FEATURE

    if feature_key not in CELL_AOI_TO_ARRAY_FEATURES:
        raise HTTPException(status_code=400, detail=f"Unsupported feature: {feature_key}")

    affected = update_api_aoi_action(
        feature_key=feature_key,
        sheet_id_chip_id=req.sheet_id_chip_id,
        test_time=req.test_time,
        pi_type=req.pi_type,
        source_op_id=req.source_op_id,
        comment=req.comment,
        action=req.action,
        editor=req.editor,
    )

    return CellAoiToArrayUpdateActionResponse(
        ok=True,
        affected=affected,
        message="更新完成" if affected else "沒有更新到資料，請確認 key 是否正確",
    )


# =============================================================================
# DB Helpers
# =============================================================================

def get_engine_by_db_name(db_name: str):
    return MySQLConnet(db_name).engine


def get_output_engine(feature_key: str = AOI_FEATURE):
    db_cfg = get_feature_db_config(feature_key)
    db_name = db_cfg.get("source_db") or SOURCE_DB_NAME
    return get_engine_by_db_name(db_name)


def get_source_cache_engine():
    return get_engine_by_db_name(SOURCE_DB_NAME)


def get_cell_engine():
    return get_engine_by_db_name(CELL_DB_NAME)


def get_inspection_input_engine():
    return get_engine_by_db_name(INSPECTION_INPUT_DB_NAME)


def table_exists(engine, table_name: str) -> bool:
    insp = inspect(engine)
    tables = {t.lower() for t in insp.get_table_names()}
    return table_name.lower() in tables


def get_table_columns(engine, table_name: str) -> List[str]:
    try:
        insp = inspect(engine)
        return [c["name"] for c in insp.get_columns(table_name)]
    except Exception:
        return []


def list_tables_like(engine, prefix: str) -> List[str]:
    insp = inspect(engine)
    prefix_l = prefix.lower()
    return [
        t for t in insp.get_table_names()
        if t.lower().startswith(prefix_l)
    ]


def yyyymm_range(start_dt: datetime, end_dt_exclusive: datetime) -> List[str]:
    cur = datetime(start_dt.year, start_dt.month, 1)
    end_month = datetime(end_dt_exclusive.year, end_dt_exclusive.month, 1)

    if (
        end_dt_exclusive.day == 1
        and end_dt_exclusive.hour == 0
        and end_dt_exclusive.minute == 0
        and end_dt_exclusive.second == 0
    ):
        if end_month.month == 1:
            end_month = datetime(end_month.year - 1, 12, 1)
        else:
            end_month = datetime(end_month.year, end_month.month - 1, 1)

    out = []
    while cur <= end_month:
        out.append(cur.strftime("%Y%m"))
        if cur.month == 12:
            cur = datetime(cur.year + 1, 1, 1)
        else:
            cur = datetime(cur.year, cur.month + 1, 1)

    return out


# =============================================================================
# Summary Query
# =============================================================================

def load_real_summary_rows(
    feature_key: str,
    filters: CellAoiToArrayFilters,
) -> List[Dict[str, Any]]:
    start_dt, end_dt_exclusive = normalize_date_range(filters.startDate, filters.endDate)
    months = yyyymm_range(start_dt, end_dt_exclusive)

    db_cfg = get_feature_db_config(feature_key)
    source_base = db_cfg.get("source_table", API_AOI_SUMMARY_BASE)
    query_fields = db_cfg.get("queryFields") or []

    engine = get_output_engine(feature_key)
    rows: List[Dict[str, Any]] = []

    for ym in months:
        table_name = table_name_by_yyyymm(source_base, ym)

        if not table_exists(engine, table_name):
            continue

        table_cols = set(get_table_columns(engine, table_name))
        real_fields = [c for c in query_fields if c in table_cols]

        if not real_fields:
            continue

        select_cols = ", ".join([f"`{c}`" for c in real_fields])
        where_sql, params = build_main_where(
            feature_key=feature_key,
            filters=filters,
            start_dt=start_dt,
            end_dt_exclusive=end_dt_exclusive,
            table_cols=table_cols,
        )

        order_cols = [
            c for c in ["test_time", "sheet_id_chip_id", "pi_type", "source_op_id"]
            if c in table_cols
        ]

        order_sql = ", ".join([f"`{c}` ASC" for c in order_cols]) or "1"

        sql = text(f"""
        SELECT {select_cols}
        FROM `{table_name}`
        WHERE {where_sql}
        ORDER BY {order_sql}
        """)

        with engine.connect() as conn:
            result = conn.execute(sql, params)
            for row in result:
                rows.append(format_main_row(feature_key, dict(row._mapping)))

    return rows


# =============================================================================
# Detail Query
# =============================================================================

def load_same_point_detail(
    feature_key: str,
    sheet_id_chip_id: str,
    test_time: str,
    pi_type: Optional[str],
    source_op_id: str,
) -> Dict[str, Any]:
    dt = parse_datetime_text(test_time)
    ym = dt.strftime("%Y%m")

    db_cfg = get_feature_db_config(feature_key)
    detail_base = db_cfg.get("detail_table", SAME_POINT_DETAIL_BASE)
    detail_fields = db_cfg.get("detailQueryFields") or []

    table_name = table_name_by_yyyymm(detail_base, ym)
    engine = get_output_engine(feature_key)

    if not table_exists(engine, table_name):
        raise HTTPException(status_code=404, detail=f"detail table not found: {table_name}")

    table_cols = set(get_table_columns(engine, table_name))
    real_fields = [c for c in detail_fields if c in table_cols]

    if not real_fields:
        raise HTTPException(status_code=404, detail=f"detail table has no query fields: {table_name}")

    select_cols = ", ".join([f"`{c}`" for c in real_fields])

    where_parts = [
        "`sheet_id` = :sheet_id",
        "`scan_time` = :scan_time",
        "`source_op_id` = :source_op_id",
    ]

    params: Dict[str, Any] = {
        "sheet_id": normalize_str(sheet_id_chip_id),
        "scan_time": dt,
        "source_op_id": normalize_str(source_op_id),
    }

    # AOI detail table 有 cell_op；Inspection detail table 沒有 cell_op
    if "cell_op" in table_cols:
        where_parts.append("(:pi_type = '' OR `cell_op` = :pi_type)")
        params["pi_type"] = normalize_str(pi_type).upper()

    sql = text(f"""
    SELECT {select_cols}
    FROM `{table_name}`
    WHERE {" AND ".join(where_parts)}
    LIMIT 1
    """)

    with engine.connect() as conn:
        row = conn.execute(sql, params).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="找不到同點詳情資料")

    return format_detail_row(feature_key, dict(row))


# =============================================================================
# Full Defect Group Query
# =============================================================================

def load_full_defect_groups(
    feature_key: str,
    detail: Dict[str, Any],
    sheet_id_chip_id: str,
    test_time: str,
    pi_type: Optional[str],
    source_op_id: str,
) -> Dict[str, List[Dict[str, Any]]]:
    if feature_key == INSPECTION_FEATURE:
        target_group = load_inspection_defect_group(
            detail=detail,
            sheet_id_chip_id=sheet_id_chip_id,
            test_time=test_time,
        )

        source_group = load_inspection_source_defect_group(
            detail=detail,
            sheet_id_chip_id=sheet_id_chip_id,
            source_op_id=source_op_id,
        )

        return {
            "cell_aoi": target_group,
            "source": source_group,
        }

    resolved_pi_type = (
        pi_type
        or detail.get("cell_op")
        or detail.get("pi_type")
        or ""
    )

    resolved_source_op_id = (
        source_op_id
        or detail.get("source_op_id")
        or ""
    )

    cell_group = load_cell_defect_group(
        detail=detail,
        sheet_id_chip_id=sheet_id_chip_id,
        test_time=test_time,
        pi_type=resolved_pi_type,
    )

    source_group = load_source_defect_group(
        detail=detail,
        sheet_id_chip_id=sheet_id_chip_id,
        source_op_id=resolved_source_op_id,
    )

    return {
        "cell_aoi": cell_group,
        "source": source_group,
    }


# =============================================================================
# Inspection target defect group
# =============================================================================

INSPECTION_PANEL_HEIGHT_UM = 1500000.0


def load_inspection_defect_group(
    detail: Dict[str, Any],
    sheet_id_chip_id: str,
    test_time: str,
) -> List[Dict[str, Any]]:
    """
    Inspection 來料檢 target defect group。

    來源：
        piaoi_inspection_density.inspection_raw_table_yyyymm

    條件：
        SHEET_ID = detail.sheet_id
        SCAN_ENDTIME = detail.scan_time

    座標：
        ori_x = COORD_X
        ori_y = COORD_Y
        trans_x = COORD_Y
        trans_y = panel_height_um - COORD_X
    """
    dt = parse_datetime_text(test_time)
    ym = dt.strftime("%Y%m")

    table_name = table_name_by_yyyymm("inspection_raw_table_yyyymm", ym)
    engine = get_inspection_input_engine()

    if not table_exists(engine, table_name):
        return []

    cols = get_table_columns(engine, table_name)
    colset = set(cols)

    select_candidates = [
        "COORD_X",
        "COORD_Y",
        "DEFECT_SIZE_TYPE",
        "IMG_URL",
        "RECIPE_NAME",
        "RUN_ID",
        "SCAN_ENDTIME",
        "SHEET_ID",
        "SP",
        "STAGE",
        "TOOL_ID",
        "TOTAL_DEFECT_COUNT",
    ]

    real_select = [c for c in select_candidates if c in colset]
    if not real_select:
        return []

    select_sql = ", ".join([f"`{c}`" for c in real_select])

    sql = text(f"""
    SELECT {select_sql}
    FROM `{table_name}`
    WHERE `SHEET_ID` = :sheet_id
      AND `SCAN_ENDTIME` = :scan_time
    """)

    params = {
        "sheet_id": normalize_str(sheet_id_chip_id),
        "scan_time": dt,
    }

    try:
        with engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
    except Exception:
        return []

    out: List[Dict[str, Any]] = []

    for idx, r in enumerate(rows, start=1):
        d = clean_dict(dict(r))

        ori_x = to_float(d.get("COORD_X"))
        ori_y = to_float(d.get("COORD_Y"))

        if ori_x is None or ori_y is None:
            continue

        trans_x = ori_y
        trans_y = INSPECTION_PANEL_HEIGHT_UM - ori_x

        defect_size = normalize_size(d.get("DEFECT_SIZE_TYPE"))
        img_url = clean_url(d.get("IMG_URL"))
        image_name = image_name_from_url(img_url)

        uid = build_inspection_uid(
            sheet_id=sheet_id_chip_id,
            scan_time=fmt_dt(test_time),
            line_id=d.get("TOOL_ID"),
            defect_size=defect_size,
            ori_x=ori_x,
            ori_y=ori_y,
            image_name=image_name,
        )

        info = {
            "inspection_defect_uid": uid,
            "sheet_id": sheet_id_chip_id,
            "scan_time": fmt_dt(test_time),
            "line_id": d.get("TOOL_ID"),
            "defect_size": defect_size,
            "defect_size_raw": d.get("DEFECT_SIZE_TYPE"),
            "recipe_name": d.get("RECIPE_NAME"),
            "run_id": d.get("RUN_ID"),
            "sp": d.get("SP"),
            "stage": d.get("STAGE"),
            "ori_x": round_float(ori_x, 3),
            "ori_y": round_float(ori_y, 3),
            "trans_x": round_float(trans_x, 3),
            "trans_y": round_float(trans_y, 3),
            "image_name": image_name,
            "img_url_path": img_url,
            "total_defect_count": to_int(d.get("TOTAL_DEFECT_COUNT")),
        }

        out.append({
            "group": "cell_aoi",
            "index": idx,

            "cell_defect_uid": uid,
            "inspection_defect_uid": uid,

            "x": round_float(trans_x, 3),
            "y": round_float(trans_y, 3),
            "cell_x": round_float(trans_x, 3),
            "cell_y": round_float(trans_y, 3),

            "defect_size": defect_size,
            "cell_defect_size": defect_size,
            "defect_code": "",
            "cell_defect_code": "",

            "img": img_url,
            "cell_img": img_url,
            "aoi_img": img_url,

            "match": False,
            "source_op_id": detail.get("source_op_id"),
            "cell_info": info,

            "source_img": "",
            "source_info": {},
            "source_defect_uid": "",
            "source_x": "",
            "source_y": "",
            "source_defect_size": "",
            "source_defect_code": "",

            "distance": None,
            "dx": None,
            "dy": None,
            "offset": None,
        })

    return out


# =============================================================================
# CELL AOI image url helper
# =============================================================================

CELL_AOI_IMG_BASE_URL = "http://l6apaimg103/dms/CELAIDI_L6A"


def is_null_like(value: Any) -> bool:
    s = str(value or "").strip()
    return (not s) or s.lower() in {"none", "nan", "nat", "<na>", "null"}


def is_image_file_path(value: Any) -> bool:
    s = str(value or "").strip().lower()
    return any(ext in s for ext in [".jpg", ".jpeg", ".png", ".bmp", ".webp"])


def clean_url(value: Any) -> str:
    s = str(value or "").strip()

    if is_null_like(s):
        return ""

    return s.replace("\\", "/")


def join_cell_img_url(path_value: Any, name_value: Any) -> str:
    path = clean_url(path_value)
    name = clean_url(name_value)

    if not path and not name:
        return ""

    if name.startswith("http://") or name.startswith("https://"):
        return name

    if (path.startswith("http://") or path.startswith("https://")) and is_image_file_path(path):
        return path

    if path.startswith("http://") or path.startswith("https://"):
        if name:
            return path.rstrip("/") + "/" + name.lstrip("/")
        return path

    if is_image_file_path(path):
        return CELL_AOI_IMG_BASE_URL.rstrip("/") + "/" + path.lstrip("/")

    if path and name:
        return (
            CELL_AOI_IMG_BASE_URL.rstrip("/")
            + "/"
            + path.strip("/")
            + "/"
            + name.lstrip("/")
        )

    return ""


def load_cell_defect_group(
    detail: Dict[str, Any],
    sheet_id_chip_id: str,
    test_time: str,
    pi_type: Optional[str],
) -> List[Dict[str, Any]]:
    """
    AOI feature target defect group。
    來源：
        cim_piaoi.cim_defect_yyyymm_*
    """
    dt = parse_datetime_text(test_time)
    ym = dt.strftime("%Y%m")

    engine = get_cell_engine()
    prefix = f"cim_defect_{ym}_"
    candidate_tables = list_tables_like(engine, prefix)

    out: List[Dict[str, Any]] = []

    for tb in candidate_tables:
        cols = get_table_columns(engine, tb)
        colset = set(cols)

        sheet_col = first_existing(colset, ["sheet_id_chip_id", "sheet_id", "glass_id", "glass"])
        time_col = first_existing(colset, ["test_time", "scan_time", "detect_time"])
        pi_col = first_existing(colset, ["pi_type", "cell_op"])
        chip_col = first_existing(colset, ["chip_id", "chip", "tft_chip_id", "cf_chip_id"])

        x_col = first_existing(colset, ["pox_x1", "trans_x", "x", "ori_x", "coord_x"])
        y_col = first_existing(colset, ["pox_y1", "trans_y", "y", "ori_y", "coord_y"])

        ori_x_col = first_existing(colset, ["pox_x1", "ori_x", "coord_x", "x", "trans_x"])
        ori_y_col = first_existing(colset, ["pox_y1", "ori_y", "coord_y", "y", "trans_y"])

        size_col = first_existing(colset, ["defect_size", "defect_size_type", "size"])
        code_col = first_existing(colset, ["adc_def_code", "defect_code", "code"])
        retype_col = first_existing(colset, ["retype_def_code", "retype_code", "retype"])

        img_url_col = first_existing(colset, ["img_url_path", "image_url", "url"])
        img_path_col = first_existing(colset, ["img_file_url_path", "image_file_path", "pic_path", "image_path"])
        img_name_col = first_existing(colset, ["image_file_name", "image_name", "img_file_name", "pic_name"])

        if not sheet_col or not time_col:
            continue

        select_cols = unique_keep_order([
            sheet_col,
            time_col,
            pi_col,
            chip_col,
            x_col,
            y_col,
            ori_x_col,
            ori_y_col,
            size_col,
            code_col,
            retype_col,
            img_url_col,
            img_path_col,
            img_name_col,
        ])

        select_sql = ", ".join([f"`{c}`" for c in select_cols])

        where_parts = [
            f"`{sheet_col}` = :sheet_id",
            f"`{time_col}` = :test_time",
        ]

        params: Dict[str, Any] = {
            "sheet_id": normalize_str(sheet_id_chip_id),
            "test_time": dt,
        }

        pi_text = normalize_str(pi_type).upper()
        if pi_col and pi_text:
            where_parts.append(f"`{pi_col}` = :pi_type")
            params["pi_type"] = pi_text

        sql = text(f"""
        SELECT {select_sql}
        FROM `{tb}`
        WHERE {" AND ".join(where_parts)}
        """)

        try:
            with engine.connect() as conn:
                rows = conn.execute(sql, params).mappings().all()
        except Exception:
            continue

        for r in rows:
            d = clean_dict(dict(r))

            raw_x = to_float(d.get(x_col)) if x_col else None
            raw_y = to_float(d.get(y_col)) if y_col else None

            if raw_x is None or raw_y is None:
                continue

            ori_x = to_float(d.get(ori_x_col)) if ori_x_col else raw_x
            ori_y = to_float(d.get(ori_y_col)) if ori_y_col else raw_y

            x = raw_x
            y = raw_y

            defect_size = normalize_size(d.get(size_col)) if size_col else "O"
            defect_code = d.get(code_col) if code_col else None
            retype_code = d.get(retype_col) if retype_col else None

            img_path = d.get(img_path_col) if img_path_col else ""
            img_name = d.get(img_name_col) if img_name_col else ""

            img_url = join_cell_img_url(img_path, img_name)

            if not img_url and img_url_col:
                img_url = clean_url(d.get(img_url_col))

            image_name = normalize_str(img_name)
            if not image_name:
                image_name = image_name_from_url(img_url)

            cell_defect_uid = build_cell_uid(
                sheet_id=sheet_id_chip_id,
                test_time=fmt_dt(test_time),
                defect_code=defect_code,
                defect_size=defect_size,
                ori_x=ori_x,
                ori_y=ori_y,
                image_name=image_name,
            )

            chip_id = d.get(chip_col) if chip_col else None

            cell_info = {
                "cell_defect_uid": cell_defect_uid,
                "sheet_id_chip_id": sheet_id_chip_id,
                "chip_id": chip_id,

                "defect_code": defect_code,
                "cell_defect_code": defect_code,
                "adc_def_code": defect_code,

                "retype_def_code": retype_code,

                "defect_size": defect_size,
                "cell_defect_size": defect_size,

                "ori_x": round_float(ori_x, 3),
                "ori_y": round_float(ori_y, 3),

                "trans_x": round_float(x, 3),
                "trans_y": round_float(y, 3),

                "image_name": image_name,
                "image_file_name": image_name,

                "img_file_url_path": normalize_str(img_path),
                "img_url_path": img_url,
            }

            idx = len(out) + 1

            out.append({
                "group": "cell_aoi",
                "index": idx,

                "cell_defect_uid": cell_defect_uid,

                "x": round_float(x, 3),
                "y": round_float(y, 3),
                "cell_x": round_float(x, 3),
                "cell_y": round_float(y, 3),

                "defect_size": defect_size,
                "defect_code": defect_code,

                "cell_defect_size": defect_size,
                "cell_defect_code": defect_code,

                "img": img_url,
                "cell_img": img_url,
                "aoi_img": img_url,

                "match": False,
                "source_op_id": detail.get("source_op_id"),
                "cell_info": cell_info,

                "source_img": "",
                "source_info": {},
                "source_defect_uid": "",
                "source_x": "",
                "source_y": "",
                "source_defect_size": "",
                "source_defect_code": "",

                "distance": None,
                "dx": None,
                "dy": None,
                "offset": None,
            })

    return out


def load_inspection_source_defect_group(
    detail: Dict[str, Any],
    sheet_id_chip_id: str,
    source_op_id: str,
) -> List[Dict[str, Any]]:
    op = normalize_str(source_op_id).upper()

    if op in {"AOI_BPI", "AOI_API"}:
        pi_type = op.replace("AOI_", "")
        return load_aoi_source_defect_group(
            detail=detail,
            sheet_id_chip_id=sheet_id_chip_id,
            source_scan_time=detail.get("source_scan_time"),
            pi_type=pi_type,
            source_op_id=op,
        )

    return load_source_defect_group(
        detail=detail,
        sheet_id_chip_id=sheet_id_chip_id,
        source_op_id=source_op_id,
    )


def load_aoi_source_defect_group(
    detail: Dict[str, Any],
    sheet_id_chip_id: str,
    source_scan_time: Any,
    pi_type: str,
    source_op_id: str,
) -> List[Dict[str, Any]]:
    """
    Inspection feature 的 AOI_BPI / AOI_API source group。
    來源仍是 cim_piaoi.cim_defect_yyyymm_*
    但回傳格式改成 source group。
    """
    if not source_scan_time:
        return []

    rows = load_cell_defect_group(
        detail={"source_op_id": source_op_id},
        sheet_id_chip_id=sheet_id_chip_id,
        test_time=fmt_dt(source_scan_time) or str(source_scan_time),
        pi_type=pi_type,
    )

    out: List[Dict[str, Any]] = []

    for idx, row in enumerate(rows, start=1):
        info = dict(row.get("cell_info") or {})
        img = row.get("cell_img") or row.get("img") or ""

        source_info = dict(info)
        source_info.setdefault("source_op_id", source_op_id)
        source_info.setdefault("op_id", source_op_id)

        out.append({
            "group": "source",
            "index": idx,
            "x": row.get("x"),
            "y": row.get("y"),
            "defect_size": row.get("defect_size"),
            "defect_code": row.get("defect_code"),
            "img": img,
            "image_name": info.get("image_name"),

            "source_op_id": source_op_id,
            "source_x": row.get("cell_x"),
            "source_y": row.get("cell_y"),
            "source_img": img,
            "source_info": source_info,
            "source_defect_size": row.get("cell_defect_size"),
            "source_defect_code": row.get("cell_defect_code"),
            "source_defect_uid": row.get("cell_defect_uid"),

            "cell_x": 0,
            "cell_y": 0,
            "cell_img": "",
            "cell_info": {},
            "match": False,
        })

    return out


def load_source_defect_group(
    detail: Dict[str, Any],
    sheet_id_chip_id: str,
    source_op_id: str,
) -> List[Dict[str, Any]]:
    """
    從 cim_cell_aoi_to_array.incoming_source_*_defect_raw_yyyymm 查完整前站 group。

    支援：
        AOI feature：
            OC / PS / PX1=MOR / TAR / TOS

        Inspection feature：
            CF_OC / CF_PS / ARRAY_MOR / ARRAY_TAR / ARRAY_TOS
    """
    source_scan_time = detail.get("source_scan_time")
    if not source_scan_time:
        return []

    source_dt = parse_datetime_text(source_scan_time)
    ym = source_dt.strftime("%Y%m")

    abbr_cat = normalize_str(detail.get("abbr_cat") or detail.get("glass_type")).upper()
    op = normalize_str(source_op_id).upper()

    base = resolve_source_raw_base(abbr_cat=abbr_cat, source_op_id=op)
    if not base:
        return []

    table_name = table_name_by_yyyymm(base, ym)
    engine = get_source_cache_engine()

    if not table_exists(engine, table_name):
        return []

    cols = get_table_columns(engine, table_name)
    colset = set(cols)

    sheet_col = first_existing(colset, ["sheet_id", "glass_id", "board_id", "sheet_id_chip_id"])

    if op in {"TAR", "TOS", "ARRAY_TAR", "ARRAY_TOS"}:
        time_col = first_existing(colset, ["repair_time", "scan_time", "testing_date", "test_time"])
    else:
        time_col = first_existing(colset, ["scan_time", "repair_time", "testing_date", "test_time"])

    op_col = first_existing(colset, ["op_id", "source_op_id", "op"])

    if not sheet_col or not time_col:
        return []

    where_parts = [
        f"`{sheet_col}` = :sheet_id",
        f"`{time_col}` = :scan_time",
    ]

    params: Dict[str, Any] = {
        "sheet_id": normalize_str(sheet_id_chip_id),
        "scan_time": source_dt,
    }

    raw_op_value = normalize_source_op_for_raw_table(op)

    if op_col and raw_op_value:
        where_parts.append(f"`{op_col}` = :op_id")
        params["op_id"] = raw_op_value

    sql = text(f"""
    SELECT *
    FROM `{table_name}`
    WHERE {" AND ".join(where_parts)}
    """)

    try:
        with engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
    except Exception:
        return []

    out: List[Dict[str, Any]] = []

    for idx, r in enumerate(rows, start=1):
        d = clean_dict(dict(r))

        x = to_float(d.get("trans_x") or d.get("x") or d.get("ori_x") or d.get("coord_x"))
        y = to_float(d.get("trans_y") or d.get("y") or d.get("ori_y") or d.get("coord_y"))

        img_url = clean_url(d.get("img_url_path") or d.get("image_url"))
        image_name = d.get("image_name") or d.get("image_file_name") or image_name_from_url(img_url)

        defect_size = normalize_size(
            d.get("defect_size")
            or d.get("defect_size_type")
            or d.get("tar_judge")
            or d.get("size")
        )

        defect_code = (
            d.get("defect_code")
            or d.get("adc_repair_answers")
            or d.get("retype")
            or d.get("code")
        )

        source_info = dict(d)
        source_info.setdefault("source_op_id", source_op_id)
        source_info.setdefault("op_id", raw_op_value or source_op_id)
        source_info.setdefault("defect_code", defect_code)
        source_info.setdefault("defect_size", defect_size)
        source_info.setdefault("defect_size_type", defect_size)
        source_info.setdefault("trans_x", round_float(x, 3))
        source_info.setdefault("trans_y", round_float(y, 3))
        source_info.setdefault("ori_x", round_float(d.get("ori_x") or x, 3))
        source_info.setdefault("ori_y", round_float(d.get("ori_y") or y, 3))
        source_info.setdefault("image_name", image_name)
        source_info.setdefault("img_url_path", img_url)

        out.append({
            "group": "source",
            "index": idx,
            "x": x,
            "y": y,
            "defect_size": defect_size,
            "defect_code": defect_code,
            "img": img_url,
            "image_name": image_name,

            "source_op_id": source_op_id,
            "source_x": x,
            "source_y": y,
            "source_img": img_url,
            "source_info": source_info,
            "source_defect_size": defect_size,
            "source_defect_code": defect_code,
            "source_defect_uid": d.get("source_defect_uid"),

            "cell_x": 0,
            "cell_y": 0,
            "cell_img": "",
            "cell_info": {},
            "match": False,
        })

    return out


def resolve_source_raw_base(abbr_cat: str, source_op_id: str) -> Optional[str]:
    side = normalize_str(abbr_cat).upper()
    op = normalize_str(source_op_id).upper()

    if op in {"CF_OC", "OC"}:
        return SOURCE_CF_OC_RAW_BASE

    if op in {"CF_PS", "PS"}:
        return SOURCE_CF_PS_RAW_BASE

    if op in {"ARRAY_MOR", "PX1=MOR", "MOR"}:
        return SOURCE_ARRAY_MOR_RAW_BASE

    if op in {"ARRAY_TAR", "TAR"}:
        return SOURCE_ARRAY_TAR_RAW_BASE

    if op in {"ARRAY_TOS", "TOS"}:
        return SOURCE_ARRAY_TOS_RAW_BASE

    # side fallback
    if side == "CF":
        if op == "OC":
            return SOURCE_CF_OC_RAW_BASE
        if op == "PS":
            return SOURCE_CF_PS_RAW_BASE

    if side == "TFT":
        if op == "PX1=MOR":
            return SOURCE_ARRAY_MOR_RAW_BASE
        if op == "TAR":
            return SOURCE_ARRAY_TAR_RAW_BASE
        if op == "TOS":
            return SOURCE_ARRAY_TOS_RAW_BASE

    return None


def normalize_source_op_for_raw_table(source_op_id: str) -> str:
    op = normalize_str(source_op_id).upper()

    mapping = {
        "CF_OC": "OC",
        "CF_PS": "PS",
        "ARRAY_MOR": "PX1=MOR",
        "ARRAY_TAR": "TAR",
        "ARRAY_TOS": "TOS",
    }

    return mapping.get(op, source_op_id)


# =============================================================================
# Update Query
# =============================================================================

def update_api_aoi_action(
    feature_key: str,
    sheet_id_chip_id: str,
    test_time: str,
    pi_type: Optional[str],
    source_op_id: str,
    comment: Optional[str],
    action: Optional[str],
    editor: Optional[str],
) -> int:
    dt = parse_datetime_text(test_time)
    ym = dt.strftime("%Y%m")

    db_cfg = get_feature_db_config(feature_key)
    source_base = db_cfg.get("source_table", API_AOI_SUMMARY_BASE)

    table_name = table_name_by_yyyymm(source_base, ym)
    engine = get_output_engine(feature_key)

    if not table_exists(engine, table_name):
        raise HTTPException(status_code=404, detail=f"summary table not found: {table_name}")

    table_cols = set(get_table_columns(engine, table_name))

    set_parts = []
    params: Dict[str, Any] = {
        "sheet_id_chip_id": normalize_str(sheet_id_chip_id),
        "test_time": dt,
        "source_op_id": normalize_str(source_op_id),
        "comment": none_if_blank(comment),
        "action": none_if_blank(action),
        "editor": none_if_blank(editor),
    }

    if "comment" in table_cols:
        set_parts.append("comment = :comment")
    if "action" in table_cols:
        set_parts.append("action = :action")
    if "editor" in table_cols:
        set_parts.append("editor = :editor")
    if "modify_time" in table_cols:
        set_parts.append("modify_time = NOW()")

    if not set_parts:
        return 0

    where_parts = [
        "sheet_id_chip_id = :sheet_id_chip_id",
        "test_time = :test_time",
        "source_op_id = :source_op_id",
    ]

    if "pi_type" in table_cols:
        where_parts.append("(:pi_type = '' OR pi_type = :pi_type)")
        params["pi_type"] = normalize_str(pi_type).upper()

    sql = text(f"""
    UPDATE `{table_name}`
    SET {", ".join(set_parts)}
    WHERE {" AND ".join(where_parts)}
    """)

    with engine.begin() as conn:
        result = conn.execute(sql, params)

    return int(result.rowcount or 0)


# =============================================================================
# SQL Builders
# =============================================================================

def normalize_sheet_ids_from_filters(filters: CellAoiToArrayFilters) -> List[str]:
    raw_values: List[Any] = []

    if getattr(filters, "sheetIds", None):
        raw_values.extend(filters.sheetIds or [])

    if getattr(filters, "sheet_ids", None):
        raw_values.extend(filters.sheet_ids or [])

    out: List[str] = []
    seen = set()

    for v in raw_values:
        s = normalize_str(v).upper()

        if not s:
            continue

        if s.lower() in {"none", "nan", "nat", "<na>", "null"}:
            continue

        if s in seen:
            continue

        seen.add(s)
        out.append(s)

    return out


def build_main_where(
    feature_key: str,
    filters: CellAoiToArrayFilters,
    start_dt: datetime,
    end_dt_exclusive: datetime,
    table_cols: set[str],
) -> Tuple[str, Dict[str, Any]]:
    where_parts = [
        "test_time >= :start_dt",
        "test_time < :end_dt",
    ]

    params: Dict[str, Any] = {
        "start_dt": start_dt,
        "end_dt": end_dt_exclusive,
    }

    line_id = normalize_str(filters.lineId or filters.tool)
    source_op = normalize_str(filters.sourceOpId)
    sheet_type = normalize_str(filters.sheetType).upper()
    sheet_id = normalize_str(filters.sheetId).upper()
    sheet_ids = normalize_sheet_ids_from_filters(filters)

    pi_type = normalize_str(filters.piType).upper()
    match_status = normalize_str(filters.matchStatus).upper()
    aoi = normalize_str(filters.aoi)
    model_no = normalize_str(filters.modelNo)
    recipe_id = normalize_str(filters.recipeId)

    if line_id and "line_id" in table_cols:
        where_parts.append("line_id = :line_id")
        params["line_id"] = line_id

    if source_op and "source_op_id" in table_cols:
        where_parts.append("source_op_id = :source_op_id")
        params["source_op_id"] = source_op

    if sheet_type and "abbr_cat" in table_cols:
        where_parts.append("abbr_cat = :abbr_cat")
        params["abbr_cat"] = sheet_type

    if sheet_ids and "sheet_id_chip_id" in table_cols:
        bind_names = []

        for i, sid in enumerate(sheet_ids):
            key = f"sheet_id_{i}"
            bind_names.append(f":{key}")
            params[key] = sid

        where_parts.append(
            f"UPPER(sheet_id_chip_id) IN ({', '.join(bind_names)})"
        )

    elif sheet_id and "sheet_id_chip_id" in table_cols:
        where_parts.append("UPPER(sheet_id_chip_id) LIKE :sheet_id")
        params["sheet_id"] = f"%{sheet_id}%"

    if pi_type and "pi_type" in table_cols:
        where_parts.append("pi_type = :pi_type")
        params["pi_type"] = pi_type

    if match_status and "match_status" in table_cols:
        where_parts.append("match_status = :match_status")
        params["match_status"] = match_status

    if aoi and "aoi" in table_cols:
        where_parts.append("aoi = :aoi")
        params["aoi"] = aoi

    if model_no and "model_no" in table_cols:
        where_parts.append("model_no = :model_no")
        params["model_no"] = model_no

    if recipe_id and "recipe_id" in table_cols:
        where_parts.append("recipe_id = :recipe_id")
        params["recipe_id"] = recipe_id

    return " AND ".join(where_parts), params


# =============================================================================
# Formatters
# =============================================================================

def format_main_row(feature_key: str, row: Dict[str, Any]) -> Dict[str, Any]:
    d = clean_dict(row)

    same_rate = to_float(d.get("same_point_rate"))
    total_defect_qty = to_int(d.get("total_defect_qty"))
    same_point_cnt = to_int(d.get("same_point_defect_cnt"))
    source_defect_cnt = to_int(d.get("source_defect_cnt"))

    pi_type = d.get("pi_type")
    aoi = d.get("aoi")
    recipe_id = d.get("recipe_id")
    cassette_id = d.get("cassette_id")

    if feature_key == INSPECTION_FEATURE:
        pi_type = None
        aoi = None
        recipe_id = None
        cassette_id = None

    out = {
        "test_time": fmt_dt(d.get("test_time")),
        "line_id": d.get("line_id"),
        "cassette_id": cassette_id,
        "sheet_id_chip_id": d.get("sheet_id_chip_id"),
        "model_no": d.get("model_no"),
        "abbr_cat": d.get("abbr_cat"),
        "recipe_id": recipe_id,
        "aoi": aoi,
        "total_defect_qty": total_defect_qty,
        "pi_time": fmt_dt(d.get("pi_time")),
        "pi_type": pi_type,
        "source_scan_time": fmt_dt(d.get("source_scan_time")),
        "source_op_id": d.get("source_op_id"),
        "source_defect_cnt": source_defect_cnt,
        "same_point_offset": to_float(d.get("same_point_offset")),
        "same_point_defect_cnt": same_point_cnt,
        "same_point_rate": same_rate,
        "match_status": d.get("match_status"),
        "match_status_detail": d.get("match_status_detail"),
        "comment": d.get("comment"),
        "action": d.get("action"),
        "modify_time": fmt_dt(d.get("modify_time")),
        "editor": d.get("editor"),

        # alias
        "scan_time": fmt_dt(d.get("test_time")),
        "sheet_id": d.get("sheet_id_chip_id"),
        "glass_side": d.get("abbr_cat"),
        "model": d.get("model_no"),
        "cell_count": total_defect_qty,
        "match_count": same_point_cnt,
        "match_rate": format_rate_percent(same_rate),

        "row_key": build_frontend_row_key(
            sheet_id_chip_id=d.get("sheet_id_chip_id"),
            test_time=fmt_dt(d.get("test_time")),
            pi_type=pi_type,
            source_op_id=d.get("source_op_id"),
        ),

        "defects": [],
        "defectGroups": {
            "same_point": [],
            "cell_aoi": [],
            "source": [],
        },
        "groupsLoaded": {
            "same_point": False,
            "cell_aoi": False,
            "source": False,
        },
    }

    return out


def format_detail_row(feature_key: str, row: Dict[str, Any]) -> Dict[str, Any]:
    d = clean_dict(row)

    if feature_key == INSPECTION_FEATURE:
        return {
            "sheet_id": d.get("sheet_id"),
            "sheet_id_chip_id": d.get("sheet_id"),
            "scan_time": fmt_dt(d.get("scan_time")),
            "test_time": fmt_dt(d.get("scan_time")),
            "model_no": d.get("model_no"),
            "abbr_cat": d.get("glass_type"),
            "glass_type": d.get("glass_type"),
            "process": "INSPECTION",
            "recipe_id": None,
            "cassette_id": None,
            "cell_aoi": None,
            "aoi": None,
            "cell_line_id": d.get("line_id"),
            "line_id": d.get("line_id"),
            "pi_time": None,
            "cell_op": None,
            "pi_type": None,
            "cell_defect_cnt": to_int(d.get("total_defect_qty")),
            "total_defect_qty": to_int(d.get("total_defect_qty")),
            "source_op_id": d.get("source_op_id"),
            "source_scan_time": fmt_dt(d.get("source_scan_time")),
            "source_defect_cnt": to_int(d.get("source_defect_cnt")),
            "same_point_offset": to_float(d.get("same_point_offset")),
            "same_point_defect_cnt": to_int(d.get("same_point_defect_cnt")),
            "same_point_rate": to_float(d.get("same_point_rate")),
            "point_detail": d.get("point_detail"),
            "match_status": d.get("match_status"),
            "match_status_detail": d.get("match_status_detail"),
        }

    return {
        "sheet_id": d.get("sheet_id"),
        "sheet_id_chip_id": d.get("sheet_id"),
        "scan_time": fmt_dt(d.get("scan_time")),
        "test_time": fmt_dt(d.get("scan_time")),
        "model_no": d.get("model_no"),
        "abbr_cat": d.get("abbr_cat"),
        "process": d.get("process"),
        "recipe_id": d.get("recipe_id"),
        "cassette_id": d.get("cassette_id"),
        "cell_aoi": d.get("cell_aoi"),
        "aoi": d.get("cell_aoi"),
        "cell_line_id": d.get("cell_line_id"),
        "line_id": d.get("cell_line_id"),
        "pi_time": fmt_dt(d.get("pi_time")),
        "cell_op": d.get("cell_op"),
        "pi_type": d.get("cell_op"),
        "cell_defect_cnt": to_int(d.get("cell_defect_cnt")),
        "total_defect_qty": to_int(d.get("cell_defect_cnt")),
        "source_op_id": d.get("source_op_id"),
        "source_scan_time": fmt_dt(d.get("source_scan_time")),
        "source_defect_cnt": to_int(d.get("source_defect_cnt")),
        "same_point_offset": to_float(d.get("same_point_offset")),
        "same_point_defect_cnt": to_int(d.get("same_point_defect_cnt")),
        "same_point_rate": to_float(d.get("same_point_rate")),
        "point_detail": d.get("point_detail"),
        "match_status": d.get("match_status"),
        "match_status_detail": d.get("match_status_detail"),
    }


# =============================================================================
# Point Detail Parsers
# =============================================================================

def get_point_target_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    相容：
        AOI 舊格式：
            item["cell"]

        Inspection 新格式：
            item["cell_info"] / item["target"] / item["target_info"]
    """
    for key in ["cell", "cell_info", "target", "target_info"]:
        v = item.get(key)
        if isinstance(v, dict):
            return v
    return {}


def get_point_source_item(item: Dict[str, Any]) -> Dict[str, Any]:
    for key in ["source", "source_info"]:
        v = item.get(key)
        if isinstance(v, dict):
            return v
    return {}


def get_point_match_item(item: Dict[str, Any]) -> Dict[str, Any]:
    for key in ["match", "match_detail"]:
        v = item.get(key)
        if isinstance(v, dict):
            return v

    return {
        "distance": item.get("distance"),
        "dx": item.get("dx"),
        "dy": item.get("dy"),
        "offset": item.get("offset") or item.get("same_point_offset"),
    }


def parse_point_detail_to_frontend_rows(
    point_detail: Any,
    abbr_cat: Optional[str],
    source_op_id: Optional[str],
) -> List[Dict[str, Any]]:
    raw_items = parse_json_list(point_detail)
    rows: List[Dict[str, Any]] = []

    side = normalize_str(abbr_cat).upper()

    for idx, item in enumerate(raw_items, start=1):
        cell = get_point_target_item(item)
        source = get_point_source_item(item)
        match = get_point_match_item(item)

        source_display = source.get("display") if isinstance(source.get("display"), dict) else {}
        source_raw = source.get("raw") if isinstance(source.get("raw"), dict) else {}

        src_op = (
            normalize_str(item.get("source_op_id"))
            or normalize_str(source.get("source_op_id"))
            or normalize_str(source_display.get("source_op_id"))
            or normalize_str(source_raw.get("source_op_id"))
            or normalize_str(source_raw.get("op_id"))
            or normalize_str(source_op_id)
        )

        cell_uid = (
            cell.get("cell_defect_uid")
            or cell.get("inspection_defect_uid")
            or item.get("cell_defect_uid")
        )

        cell_x = source_or_zero(cell.get("trans_x") or item.get("cell_x"))
        cell_y = source_or_zero(cell.get("trans_y") or item.get("cell_y"))

        source_x = source_or_zero(
            source.get("trans_x")
            or source_display.get("trans_x")
            or source_raw.get("trans_x")
            or item.get("source_x")
        )

        source_y = source_or_zero(
            source.get("trans_y")
            or source_display.get("trans_y")
            or source_raw.get("trans_y")
            or item.get("source_y")
        )

        cell_img = clean_url(
            cell.get("img_url_path")
            or item.get("cell_img")
            or item.get("img")
        )

        source_img = clean_url(
            source.get("img_url_path")
            or source_display.get("img_url_path")
            or source_raw.get("img_url_path")
            or item.get("source_img")
        )

        cell_info = dict(cell)
        cell_info.setdefault("cell_defect_uid", cell_uid)
        cell_info.setdefault("inspection_defect_uid", cell.get("inspection_defect_uid") or cell_uid)
        cell_info.setdefault("defect_code", cell.get("defect_code"))
        cell_info.setdefault("retype_def_code", cell.get("retype_def_code"))
        cell_info.setdefault("defect_size", normalize_size(cell.get("defect_size")))
        cell_info.setdefault("ori_x", round_float(cell.get("ori_x"), 3))
        cell_info.setdefault("ori_y", round_float(cell.get("ori_y"), 3))
        cell_info.setdefault("trans_x", round_float(cell_x, 3))
        cell_info.setdefault("trans_y", round_float(cell_y, 3))
        cell_info.setdefault("image_name", cell.get("image_name"))
        cell_info.setdefault("img_url_path", cell_img)

        source_info = {}

        for k, v in source.items():
            if k not in {"raw", "display"}:
                source_info[k] = v

        for k, v in source_raw.items():
            source_info.setdefault(k, v)

        for k, v in source_display.items():
            source_info.setdefault(k, v)

        source_info["raw"] = source_raw
        source_info["display"] = source_display

        source_info.setdefault("source_op_id", src_op)
        source_info.setdefault("op_id", normalize_source_op_for_raw_table(src_op))

        source_info.setdefault("source_defect_uid", (
            source.get("source_defect_uid")
            or source_display.get("source_defect_uid")
            or source_raw.get("source_defect_uid")
            or item.get("source_defect_uid")
        ))

        source_info.setdefault("trans_x", round_float(source_x, 3))
        source_info.setdefault("trans_y", round_float(source_y, 3))

        source_info.setdefault("ori_x", round_float(
            source.get("ori_x")
            or source_display.get("ori_x")
            or source_raw.get("ori_x"),
            3,
        ))

        source_info.setdefault("ori_y", round_float(
            source.get("ori_y")
            or source_display.get("ori_y")
            or source_raw.get("ori_y"),
            3,
        ))

        source_info.setdefault("image_name", (
            source.get("image_name")
            or source_display.get("image_name")
            or source_raw.get("image_name")
        ))

        source_info.setdefault("img_url_path", source_img)

        source_code = (
            source.get("defect_code")
            or source.get("retype")
            or source.get("adc_repair_answers")
            or source_display.get("defect_code")
            or source_raw.get("defect_code")
            or source_raw.get("retype")
            or source_raw.get("adc_repair_answers")
            or item.get("source_defect_code")
        )

        source_size = (
            source.get("defect_size")
            or source.get("defect_size_type")
            or source_display.get("defect_size")
            or source_display.get("defect_size_type")
            or source_raw.get("defect_size")
            or source_raw.get("defect_size_type")
            or source_raw.get("tar_judge")
            or item.get("source_defect_size")
        )

        source_info.setdefault("defect_code", source_code)
        source_info.setdefault("defect_size", normalize_size(source_size))
        source_info.setdefault("defect_size_type", normalize_size(source_size))

        cell_size = normalize_size(cell.get("defect_size") or item.get("cell_defect_size"))
        cell_code = cell.get("defect_code") or item.get("cell_defect_code")

        row = {
            "index": idx,
            "match": True,
            "source_op_id": src_op,
            "defect_size": normalize_size(cell_size or source_size),

            "cell_img": cell_img,
            "cell_info": cell_info,
            "source_img": source_img,
            "source_info": source_info,

            "cell_x": cell_x,
            "cell_y": cell_y,
            "source_x": source_x,
            "source_y": source_y,

            "cell_defect_code": cell_code,
            "source_defect_code": source_code,
            "cell_defect_size": cell_size,
            "source_defect_size": normalize_size(source_size),

            "distance": round_float(match.get("distance"), 3),
            "dx": round_float(match.get("dx"), 3),
            "dy": round_float(match.get("dy"), 3),
            "offset": match.get("offset"),

            "aoi_img": cell_img,
            "array_x": source_x if side == "TFT" else 0,
            "array_y": source_y if side == "TFT" else 0,
            "array_img": source_img if side == "TFT" else "",
            "cf_x": source_x if side == "CF" else 0,
            "cf_y": source_y if side == "CF" else 0,
            "cf_img": source_img if side == "CF" else "",
        }

        rows.append(row)

    return rows


def parse_point_detail_to_same_point_group(
    point_detail: Any,
    source_op_id: Optional[str],
) -> List[Dict[str, Any]]:
    raw_items = parse_json_list(point_detail)
    out: List[Dict[str, Any]] = []

    for idx, item in enumerate(raw_items, start=1):
        cell = get_point_target_item(item)
        source = get_point_source_item(item)
        match = get_point_match_item(item)

        source_display = source.get("display") if isinstance(source.get("display"), dict) else {}
        source_raw = source.get("raw") if isinstance(source.get("raw"), dict) else {}

        x = source_or_zero(cell.get("trans_x") or item.get("cell_x"))
        y = source_or_zero(cell.get("trans_y") or item.get("cell_y"))

        source_x = source_or_zero(
            source.get("trans_x")
            or source_display.get("trans_x")
            or source_raw.get("trans_x")
            or item.get("source_x")
        )

        source_y = source_or_zero(
            source.get("trans_y")
            or source_display.get("trans_y")
            or source_raw.get("trans_y")
            or item.get("source_y")
        )

        cell_img = clean_url(
            cell.get("img_url_path")
            or item.get("cell_img")
            or item.get("img")
        )

        source_img = clean_url(
            source.get("img_url_path")
            or source_display.get("img_url_path")
            or source_raw.get("img_url_path")
            or item.get("source_img")
        )

        src_op = (
            item.get("source_op_id")
            or source.get("source_op_id")
            or source_display.get("source_op_id")
            or source_raw.get("source_op_id")
            or source_raw.get("op_id")
            or source_op_id
        )

        source_code = (
            source.get("defect_code")
            or source.get("retype")
            or source.get("adc_repair_answers")
            or source_display.get("defect_code")
            or source_raw.get("defect_code")
            or source_raw.get("retype")
            or source_raw.get("adc_repair_answers")
            or item.get("source_defect_code")
        )

        source_size = (
            source.get("defect_size")
            or source.get("defect_size_type")
            or source_display.get("defect_size")
            or source_display.get("defect_size_type")
            or source_raw.get("defect_size")
            or source_raw.get("defect_size_type")
            or source_raw.get("tar_judge")
            or item.get("source_defect_size")
        )

        cell_info = dict(cell)
        cell_info.setdefault("img_url_path", cell_img)

        source_info = {}

        for k, v in source.items():
            if k not in {"raw", "display"}:
                source_info[k] = v

        for k, v in source_raw.items():
            source_info.setdefault(k, v)

        for k, v in source_display.items():
            source_info.setdefault(k, v)

        source_info["raw"] = source_raw
        source_info["display"] = source_display
        source_info.setdefault("source_op_id", src_op)
        source_info.setdefault("op_id", normalize_source_op_for_raw_table(src_op))
        source_info.setdefault("img_url_path", source_img)
        source_info.setdefault("trans_x", round_float(source_x, 3))
        source_info.setdefault("trans_y", round_float(source_y, 3))
        source_info.setdefault("defect_code", source_code)
        source_info.setdefault("defect_size", normalize_size(source_size))
        source_info.setdefault("defect_size_type", normalize_size(source_size))

        cell_size = normalize_size(cell.get("defect_size") or item.get("cell_defect_size"))
        size = normalize_size(cell_size or source_size)

        out.append({
            "group": "same_point",
            "index": idx,
            "x": x,
            "y": y,
            "defect_size": size,
            "img": cell_img or source_img,

            "cell_x": x,
            "cell_y": y,
            "cell_img": cell_img,
            "cell_info": cell_info,
            "cell_defect_code": cell.get("defect_code") or item.get("cell_defect_code"),
            "cell_defect_size": cell_size,
            "cell_defect_uid": (
                cell.get("cell_defect_uid")
                or cell.get("inspection_defect_uid")
                or item.get("cell_defect_uid")
            ),

            "source_x": source_x,
            "source_y": source_y,
            "source_img": source_img,
            "source_info": source_info,
            "source_defect_code": source_code,
            "source_defect_size": normalize_size(source_size),
            "source_defect_uid": (
                source.get("source_defect_uid")
                or source_display.get("source_defect_uid")
                or source_raw.get("source_defect_uid")
                or item.get("source_defect_uid")
            ),

            "source_op_id": src_op,
            "distance": round_float(match.get("distance"), 3),
            "dx": round_float(match.get("dx"), 3),
            "dy": round_float(match.get("dy"), 3),
            "offset": match.get("offset"),
            "match": True,
        })

    return out


def parse_json_list(value: Any) -> List[Dict[str, Any]]:
    if not value:
        return []

    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]

    if isinstance(value, str):
        try:
            data = json.loads(value)
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
        except Exception:
            return []

    return []


# =============================================================================
# Summary / Chart
# =============================================================================

def build_summary(feature_key: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if feature_key == INSPECTION_FEATURE:
        return build_inspection_summary(rows)

    return build_aoi_summary(rows)


def build_aoi_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    def glass_run_key(r: Dict[str, Any]) -> str:
        return "|".join([
            str(r.get("sheet_id_chip_id") or r.get("sheet_id") or "").strip(),
            str(r.get("pi_type") or r.get("cell_op") or "").strip().upper(),
            fmt_dt(r.get("test_time") or r.get("scan_time")) or "",
        ])

    def valid_key(r: Dict[str, Any]) -> str:
        key = glass_run_key(r)
        parts = key.split("|")

        if len(parts) != 3:
            return ""

        if not parts[0] or not parts[1] or not parts[2]:
            return ""

        return key

    def side_of(r: Dict[str, Any]) -> str:
        return str(r.get("abbr_cat") or r.get("glass_side") or "").strip().upper()

    def station_of(r: Dict[str, Any]) -> str:
        return str(r.get("source_op_id") or "").strip().upper()

    def is_matched(r: Dict[str, Any]) -> bool:
        return str(r.get("match_status") or "").strip().upper() == "MATCHED"

    def station_same_count(source_rows: List[Dict[str, Any]], station: str) -> int:
        station_u = station.upper()

        matched_keys = {
            valid_key(r)
            for r in source_rows
            if valid_key(r)
            and station_of(r) == station_u
            and is_matched(r)
        }

        return len(matched_keys)

    all_cell_keys = {
        valid_key(r)
        for r in rows
        if valid_key(r)
    }

    tft_rows = [r for r in rows if side_of(r) == "TFT"]
    cf_rows = [r for r in rows if side_of(r) == "CF"]

    tft_cell_run_keys = {
        valid_key(r)
        for r in tft_rows
        if valid_key(r)
    }

    cf_cell_run_keys = {
        valid_key(r)
        for r in cf_rows
        if valid_key(r)
    }

    array_station_order = ["PX1=MOR", "TAR", "TOS"]
    cf_station_order = ["OC", "PS"]

    array_station_same_detail = {
        station: station_same_count(tft_rows, station)
        for station in array_station_order
    }

    cf_station_same_detail = {
        station: station_same_count(cf_rows, station)
        for station in cf_station_order
    }

    array_same_by_station = f"Total(Cell AOI TFT片數)：{len(tft_cell_run_keys)}" + " \n" + "\n".join(
        [
            f"{display_station_label(station)}(有同點的片數)：{array_station_same_detail[station]}"
            for station in array_station_order
        ]
    )

    cf_same_by_station = f"Total(Cell AOI CF片數)：{len(cf_cell_run_keys)}" + " \n" + "\n".join(
        [
            f"{display_station_label(station)}(有同點的片數)：{cf_station_same_detail[station]}"
            for station in cf_station_order
        ]
    )

    return {
        "cell_total": len(all_cell_keys),
        "array_same_by_station": array_same_by_station,
        "cf_same_by_station": cf_same_by_station,

        "array_cell_run_total": len(tft_cell_run_keys),
        "cf_cell_run_total": len(cf_cell_run_keys),
        "array_station_same_detail": array_station_same_detail,
        "cf_station_same_detail": cf_station_same_detail,

        "tft_match": array_same_by_station,
        "cf_match": cf_same_by_station,

        "matched_total": len({
            valid_key(r)
            for r in rows
            if valid_key(r) and is_matched(r)
        }),
        "no_same_point_total": sum(
            1 for r in rows
            if str(r.get("match_status") or "").strip().upper() == "NO_SAME_POINT"
        ),
        "source_not_found_total": sum(
            1 for r in rows
            if str(r.get("match_status") or "").strip().upper() == "SOURCE_NOT_FOUND"
        ),
    }


def build_inspection_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    def glass_key(r: Dict[str, Any]) -> str:
        return "|".join([
            str(r.get("sheet_id_chip_id") or r.get("sheet_id") or "").strip(),
            str(r.get("abbr_cat") or "").strip().upper(),
            fmt_dt(r.get("test_time") or r.get("scan_time")) or "",
        ])

    def valid_key(r: Dict[str, Any]) -> str:
        key = glass_key(r)
        parts = key.split("|")
        if len(parts) != 3:
            return ""
        if not parts[0] or not parts[1] or not parts[2]:
            return ""
        return key

    def side_of(r: Dict[str, Any]) -> str:
        return str(r.get("abbr_cat") or "").strip().upper()

    def station_of(r: Dict[str, Any]) -> str:
        return str(r.get("source_op_id") or "").strip().upper()

    def is_matched(r: Dict[str, Any]) -> bool:
        return str(r.get("match_status") or "").strip().upper() == "MATCHED"

    def station_same_count(source_rows: List[Dict[str, Any]], station: str) -> int:
        station_u = station.upper()
        matched_keys = {
            valid_key(r)
            for r in source_rows
            if valid_key(r)
            and station_of(r) == station_u
            and is_matched(r)
        }
        return len(matched_keys)

    all_keys = {
        valid_key(r)
        for r in rows
        if valid_key(r)
    }

    cf_rows = [r for r in rows if side_of(r) == "CF"]
    tft_rows = [r for r in rows if side_of(r) == "TFT"]

    cf_keys = {
        valid_key(r)
        for r in cf_rows
        if valid_key(r)
    }

    tft_keys = {
        valid_key(r)
        for r in tft_rows
        if valid_key(r)
    }

    cf_station_order = ["AOI_BPI", "AOI_API", "CF_OC", "CF_PS"]
    tft_station_order = ["AOI_BPI", "AOI_API", "ARRAY_MOR", "ARRAY_TAR", "ARRAY_TOS"]

    cf_station_same_detail = {
        station: station_same_count(cf_rows, station)
        for station in cf_station_order
    }

    array_station_same_detail = {
        station: station_same_count(tft_rows, station)
        for station in tft_station_order
    }

    cf_same_by_station = f"Total(Inspection CF片數)：{len(cf_keys)}" + " \n" + "\n".join(
        [
            f"{display_station_label(station)}(有同點的片數)：{cf_station_same_detail[station]}"
            for station in cf_station_order
        ]
    )

    array_same_by_station = f"Total(Inspection TFT片數)：{len(tft_keys)}" + " \n" + "\n".join(
        [
            f"{display_station_label(station)}(有同點的片數)：{array_station_same_detail[station]}"
            for station in tft_station_order
        ]
    )

    return {
        "inspection_total": len(all_keys),
        "cell_total": len(all_keys),

        "aoi_same_by_station": (
            f"AOI_BPI(有同點的片數)：{station_same_count(rows, 'AOI_BPI')}\n"
            f"AOI_API(有同點的片數)：{station_same_count(rows, 'AOI_API')}"
        ),
        "source_same_by_station": array_same_by_station + "\n" + cf_same_by_station,

        "array_same_by_station": array_same_by_station,
        "cf_same_by_station": cf_same_by_station,

        "array_cell_run_total": len(tft_keys),
        "cf_cell_run_total": len(cf_keys),
        "array_station_same_detail": array_station_same_detail,
        "cf_station_same_detail": cf_station_same_detail,

        "tft_match": array_same_by_station,
        "cf_match": cf_same_by_station,

        "matched_total": len({
            valid_key(r)
            for r in rows
            if valid_key(r) and is_matched(r)
        }),
        "no_same_point_total": sum(
            1 for r in rows
            if str(r.get("match_status") or "").strip().upper() == "NO_SAME_POINT"
        ),
        "source_not_found_total": sum(
            1 for r in rows
            if str(r.get("match_status") or "").strip().upper() == "SOURCE_NOT_FOUND"
        ),
    }

def build_chart_data(
    feature_key: str,
    rows: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    chart_cfgs = CELL_AOI_TO_ARRAY_CHARTS.get(feature_key, [])
    result: Dict[str, Dict[str, Any]] = {}

    array_rows = [
        r for r in rows
        if str(r.get("abbr_cat", "")).upper() == "TFT"
    ]

    cf_rows = [
        r for r in rows
        if str(r.get("abbr_cat", "")).upper() == "CF"
    ]

    for chart in chart_cfgs:
        chart_key = chart["key"]

        # =========================================================
        # Inspection charts
        # =========================================================
        if feature_key == INSPECTION_FEATURE:
            inspection_array_rows = [
                r for r in rows
                if str(r.get("abbr_cat", "")).upper() == "TFT"
                and str(r.get("source_op_id", "")).upper() in {
                    "ARRAY_MOR",
                    "ARRAY_TAR",
                    "ARRAY_TOS",
                }
            ]

            inspection_cf_rows = [
                r for r in rows
                if str(r.get("abbr_cat", "")).upper() == "CF"
                and str(r.get("source_op_id", "")).upper() in {
                    "CF_OC",
                    "CF_PS",
                }
            ]

            inspection_cell_aoi_rows = [
                r for r in rows
                if str(r.get("source_op_id", "")).upper() in {
                    "AOI_BPI",
                    "AOI_API",
                }
            ]

            # 第 1 排：ARRAY
            if chart_key == "inspection_array_op_same_point_rate":
                result[chart_key] = build_sheet_rate_time_line_chart(
                    rows=inspection_array_rows,
                    group_key="source_op_id",
                    allow_groups=[
                        "ARRAY_MOR",
                        "ARRAY_TAR",
                        "ARRAY_TOS",
                    ],
                )

            elif chart_key == "inspection_array_line_same_point_rate":
                result[chart_key] = build_sheet_rate_time_line_chart(
                    rows=inspection_array_rows,
                    group_key="line_id",
                    allow_groups=None,
                )

            # 第 2 排：CF
            elif chart_key == "inspection_cf_op_same_point_rate":
                result[chart_key] = build_sheet_rate_time_line_chart(
                    rows=inspection_cf_rows,
                    group_key="source_op_id",
                    allow_groups=[
                        "CF_OC",
                        "CF_PS",
                    ],
                )

            elif chart_key == "inspection_cf_line_same_point_rate":
                result[chart_key] = build_sheet_rate_time_line_chart(
                    rows=inspection_cf_rows,
                    group_key="line_id",
                    allow_groups=None,
                )

            # 第 3 排：CELL AOI
            elif chart_key == "inspection_cell_aoi_op_same_point_rate":
                result[chart_key] = build_sheet_rate_time_line_chart(
                    rows=inspection_cell_aoi_rows,
                    group_key="source_op_id",
                    allow_groups=[
                        "AOI_BPI",
                        "AOI_API",
                    ],
                )

            elif chart_key == "inspection_cell_aoi_line_same_point_rate":
                result[chart_key] = build_sheet_rate_time_line_chart(
                    rows=inspection_cell_aoi_rows,
                    group_key="line_id",
                    allow_groups=None,
                )

            else:
                result[chart_key] = empty_chart()

            continue

        # =========================================================
        # AOI charts
        # =========================================================
        if chart_key == "array_op_same_point_rate":
            result[chart_key] = build_sheet_rate_time_line_chart(
                rows=array_rows,
                group_key="source_op_id",
                allow_groups=["PX1=MOR", "TAR", "TOS"],
            )

        elif chart_key == "cf_op_same_point_rate":
            result[chart_key] = build_sheet_rate_time_line_chart(
                rows=cf_rows,
                group_key="source_op_id",
                allow_groups=["OC", "PS"],
            )

        elif chart_key == "array_line_same_point_rate":
            result[chart_key] = build_sheet_rate_time_line_chart(
                rows=array_rows,
                group_key="line_id",
                allow_groups=None,
            )

        elif chart_key == "cf_line_same_point_rate":
            result[chart_key] = build_sheet_rate_time_line_chart(
                rows=cf_rows,
                group_key="line_id",
                allow_groups=None,
            )

        elif chart_key == "array_aoi_same_point_rate":
            result[chart_key] = build_sheet_rate_time_line_chart(
                rows=array_rows,
                group_key="aoi",
                allow_groups=None,
            )

        elif chart_key == "cf_aoi_same_point_rate":
            result[chart_key] = build_sheet_rate_time_line_chart(
                rows=cf_rows,
                group_key="aoi",
                allow_groups=None,
            )

        # 舊 key 相容
        elif chart_key == "array_aoi_line_same_point_rate":
            result[chart_key] = build_sheet_rate_time_line_chart(
                rows=array_rows,
                group_key="aoi",
                allow_groups=None,
            )

        elif chart_key == "cf_aoi_line_same_point_rate":
            result[chart_key] = build_sheet_rate_time_line_chart(
                rows=cf_rows,
                group_key="aoi",
                allow_groups=None,
            )

        else:
            result[chart_key] = empty_chart()

    return result

def empty_chart() -> Dict[str, Any]:
    return {
        "xMin": None,
        "xMax": None,
        "xDayStartMs": [],
        "series": [],
    }


def build_sheet_rate_time_line_chart(
    rows: List[Dict[str, Any]],
    group_key: str,
    allow_groups: Optional[List[str]] = None,
) -> Dict[str, Any]:
    points: List[Dict[str, Any]] = []

    for r in rows:
        rate = to_float(r.get("same_point_rate"))
        if rate is None:
            continue

        test_time_text = fmt_dt(r.get("test_time") or r.get("scan_time"))
        test_dt = parse_chart_datetime(test_time_text)
        if test_dt is None:
            continue

        group = str(r.get(group_key) or "").strip()
        if not group:
            group = "UNKNOWN"

        y_value = round(rate * 100, 2)
        ts_ms = datetime_to_ms(test_dt)

        row_key = build_frontend_row_key(
            sheet_id_chip_id=r.get("sheet_id_chip_id") or r.get("sheet_id"),
            test_time=test_time_text,
            pi_type=r.get("pi_type"),
            source_op_id=r.get("source_op_id"),
        )

        points.append({
            "group": group,
            "dt": test_dt,
            "ts_ms": ts_ms,
            "y": y_value,
            "row": r,
            "row_key": row_key,
        })

    points.sort(
        key=lambda p: (
            p["dt"],
            str(p["row"].get("sheet_id_chip_id") or p["row"].get("sheet_id") or ""),
            str(p["row"].get("pi_type") or ""),
            str(p["row"].get("source_op_id") or ""),
        )
    )

    if allow_groups:
        groups = [
            g for g in allow_groups
            if any(str(p["group"]) == g for p in points)
        ]
    else:
        groups = sorted({
            str(p["group"])
            for p in points
            if str(p["group"]).strip()
        })

    if points:
        min_dt = floor_to_hour(min(p["dt"] for p in points))
        max_dt = ceil_to_hour(max(p["dt"] for p in points))
        x_min = datetime_to_ms(min_dt)
        x_max = datetime_to_ms(max_dt)
    else:
        x_min = None
        x_max = None

    first_hour_by_date: Dict[str, datetime] = {}
    for p in points:
        date_key = p["dt"].strftime("%Y-%m-%d")
        hour_dt = floor_to_hour(p["dt"])
        if date_key not in first_hour_by_date or hour_dt < first_hour_by_date[date_key]:
            first_hour_by_date[date_key] = hour_dt

    x_day_start_ms = [
        datetime_to_ms(v)
        for _, v in sorted(first_hour_by_date.items())
    ]

    series = []

    for group in groups:
        group_points = [
            p for p in points
            if str(p["group"]) == group
        ]

        data = []

        for p in group_points:
            r = p["row"]
            data.append({
                "value": [p["ts_ms"], p["y"]],
                "__row_key": p["row_key"],
                "__test_time": fmt_dt(r.get("test_time") or r.get("scan_time")),
                "__sheet_id_chip_id": r.get("sheet_id_chip_id") or r.get("sheet_id"),
                "__pi_type": r.get("pi_type"),
                "__source_op_id": r.get("source_op_id"),
                "__line_id": r.get("line_id"),
                "__aoi": r.get("aoi"),
                "__abbr_cat": r.get("abbr_cat"),
                "__same_point_defect_cnt": r.get("same_point_defect_cnt"),
                "__total_defect_qty": r.get("total_defect_qty"),
                "__match_status": r.get("match_status"),
            })

        series.append({
            "name": group,
            "data": data,
        })

    return {
        "xMin": x_min,
        "xMax": x_max,
        "xDayStartMs": x_day_start_ms,
        "series": series,
    }


# =============================================================================
# Chart Helpers
# =============================================================================

def parse_chart_datetime(value: Any) -> Optional[datetime]:
    s = str(value or "").strip()
    if not s:
        return None

    try:
        if len(s) >= 19:
            return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
        if len(s) >= 16:
            return datetime.strptime(s[:16], "%Y-%m-%d %H:%M")
        if len(s) == 10:
            return datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        return None

    return None


def floor_to_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def ceil_to_hour(dt: datetime) -> datetime:
    base = floor_to_hour(dt)
    if dt == base:
        return base
    return base + timedelta(hours=1)


def datetime_to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def build_frontend_row_key(
    sheet_id_chip_id: Any,
    test_time: Any,
    pi_type: Any,
    source_op_id: Any,
) -> str:
    return "|".join([
        str(sheet_id_chip_id or "").strip(),
        fmt_dt(test_time) or str(test_time or "").strip(),
        str(pi_type or "").strip(),
        str(source_op_id or "").strip(),
    ])


# =============================================================================
# Normalizers
# =============================================================================

def normalize_date_range(start_date: Optional[str], end_date: Optional[str]) -> Tuple[datetime, datetime]:
    dr = default_date_range(days=3)
    start_text = start_date or dr["startDate"]
    end_text = end_date or dr["endDate"]

    try:
        start_dt = parse_date_or_datetime(start_text)
        end_dt = parse_date_or_datetime(end_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="日期格式需為 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS") from exc

    if len(str(end_text).strip()) == 10:
        end_dt_exclusive = end_dt + timedelta(days=1)
    else:
        end_dt_exclusive = end_dt

    if start_dt >= end_dt_exclusive:
        raise HTTPException(status_code=400, detail="開始時間不可晚於或等於結束時間")

    if (end_dt_exclusive - start_dt).days > 31:
        raise HTTPException(status_code=400, detail="查詢區間不可超過 31 天")

    return start_dt, end_dt_exclusive


def parse_date_or_datetime(value: str) -> datetime:
    s = str(value or "").strip()

    if len(s) == 10:
        return datetime.strptime(s, "%Y-%m-%d")

    return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")


def parse_datetime_text(value: Any) -> datetime:
    s = str(value or "").strip()

    if not s:
        raise HTTPException(status_code=400, detail="時間不可為空")

    try:
        if len(s) == 10:
            return datetime.strptime(s, "%Y-%m-%d")
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"時間格式錯誤: {value}") from exc


def normalize_str(value: Optional[Any]) -> str:
    return str(value or "").strip()


def none_if_blank(value: Optional[str]) -> Optional[str]:
    s = normalize_str(value)
    return s if s else None


def fmt_dt(value: Any) -> Optional[str]:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")

    s = str(value).strip()
    if not s or s.lower() in {"none", "nan", "nat", "<na>", "null"}:
        return None

    return s[:19]


def clean_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    out = {}

    for k, v in row.items():
        if v is None:
            out[k] = None
            continue

        if isinstance(v, float) and math.isnan(v):
            out[k] = None
            continue

        if str(v).strip().lower() in {"none", "nan", "nat", "<na>", "null"}:
            out[k] = None
            continue

        out[k] = v

    return out


def to_int(value: Any) -> Optional[int]:
    if value is None:
        return None

    try:
        if isinstance(value, float) and math.isnan(value):
            return None

        s = str(value).strip()
        if not s or s.lower() in {"none", "nan", "nat", "<na>", "null"}:
            return None

        return int(float(s))
    except Exception:
        return None


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None

    try:
        if isinstance(value, float) and math.isnan(value):
            return None

        s = str(value).strip()
        if not s or s.lower() in {"none", "nan", "nat", "<na>", "null"}:
            return None

        return float(s)
    except Exception:
        return None


def round_float(value: Any, digits: int = 3) -> Optional[float]:
    v = to_float(value)
    if v is None:
        return None
    return round(v, digits)


def source_or_zero(value: Any) -> float:
    v = to_float(value)
    return float(v) if v is not None else 0.0


def format_rate_percent(value: Any) -> str:
    v = to_float(value)
    if v is None:
        return ""

    return f"{round(v * 100, 1)}%"


def normalize_size(value: Any) -> str:
    s = normalize_str(value).upper()
    if s in {"S", "M", "L", "O"}:
        return s
    return "O"


def first_existing(colset: set[str], candidates: List[str]) -> Optional[str]:
    for c in candidates:
        if c in colset:
            return c
    return None


def unique_keep_order(values: List[Optional[str]]) -> List[str]:
    seen = set()
    out = []

    for v in values:
        if not v:
            continue
        if v in seen:
            continue
        seen.add(v)
        out.append(v)

    return out


def image_name_from_url(value: Any) -> str:
    s = clean_url(value)
    if not s:
        return ""

    s = s.replace("\\", "/")
    s = s.split("?")[0].split("#")[0]
    return s.rstrip("/").split("/")[-1]


def display_station_label(station: Any) -> str:
    s = str(station or "").strip().upper()

    mapping = {
        "PX1=MOR": "MOR",
        "ARRAY_MOR": "MOR",
        "ARRAY_TAR": "TAR",
        "ARRAY_TOS": "TOS",
        "CF_OC": "OC",
        "CF_PS": "PS",
        "AOI_BPI": "AOI BPI",
        "AOI_API": "AOI API",
    }

    return mapping.get(s, s)


def build_cell_uid(
    sheet_id: Any,
    test_time: Any,
    defect_code: Any,
    defect_size: Any,
    ori_x: Any,
    ori_y: Any,
    image_name: Any,
) -> str:
    return "|".join([
        normalize_str(sheet_id),
        normalize_str(test_time),
        normalize_str(defect_code),
        normalize_str(defect_size),
        normalize_str(ori_x),
        normalize_str(ori_y),
        normalize_str(image_name),
    ])


def build_inspection_uid(
    sheet_id: Any,
    scan_time: Any,
    line_id: Any,
    defect_size: Any,
    ori_x: Any,
    ori_y: Any,
    image_name: Any,
) -> str:
    return "|".join([
        "INSPECTION",
        normalize_str(sheet_id),
        normalize_str(scan_time),
        normalize_str(line_id),
        normalize_str(defect_size),
        normalize_str(ori_x),
        normalize_str(ori_y),
        normalize_str(image_name),
    ])