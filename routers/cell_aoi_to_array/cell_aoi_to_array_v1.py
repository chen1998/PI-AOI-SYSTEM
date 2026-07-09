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
    API_AOI_SUMMARY_BASE,
    SAME_POINT_DETAIL_BASE,
    SOURCE_DB_NAME,
    CELL_DB_NAME,
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

    # 舊前端欄位：tool 現在對應 api_aoi_summary.line_id
    tool: Optional[str] = None
    sheetType: Optional[str] = None
    sheetId: Optional[str] = None

    # CSV 多片 sheet 查詢
    # 前端使用 sheetIds；sheet_ids 給後續若有 snake_case payload 時相容。
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
            #{"key": "Dashboard", "label": "Dashboard"},
            {"key": "PI", "label": "PI"},
            #{"key": "RUB", "label": "RUB"},
        ],
        "featureTabsByCategory": {
            "PI": [
                get_feature_ui_config("aoi-sampling-compare"),
                get_feature_ui_config("inspection-sampling-compare"),
                #get_feature_ui_config("aoi-inspec-compare"),
            ]
        },
        "featureConfigByFeature": {
            key: get_feature_ui_config(key)
            for key in CELL_AOI_TO_ARRAY_FEATURES.keys()
        },
        "sheetTypes": CELL_AOI_TO_ARRAY_SHEET_TYPES,
        "piTypes": CELL_AOI_TO_ARRAY_PI_TYPES,
        "lineOptions": CELL_AOI_TO_ARRAY_LINE_OPTIONS,
        "sourceOpOptions": CELL_AOI_TO_ARRAY_SOURCE_OP_OPTIONS,
        "matchStatusOptions": CELL_AOI_TO_ARRAY_MATCH_STATUS_OPTIONS,
        "summaryCards": [
            {
                "key": "cell_total",
                "label": "Cell 總抽檢數 (TFT +CF)",
            },
            {
                "key": "array_same_by_station",
                "label": "ARRAY ",
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

            # CSV 多片 sheet 查詢
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

    all_rows = load_real_summary_rows(feature_key=feature_key, filters=req.filters)
    chart_data = build_chart_data(feature_key=feature_key, rows=all_rows)
    summary = build_summary(all_rows)

    return CellAoiToArrayCompareResponse(
        feature=feature_key,
        title=feature_cfg["title"],
        info={
            "left": f"資料更新：{now_text()} | Source: {API_AOI_SUMMARY_BASE}",
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
    """
    點擊 table 詳情時使用。

    新流程：
        1. /detail 只讀 incoming_same_point_detail_yyyymm
        2. 只解析 point_detail
        3. 立即回傳：
            - detail 基本資訊
            - defects = point_detail 解析後的同點 rows
            - defectGroups.same_point = 同點 map group
            - defectGroups.cell_aoi = []
            - defectGroups.source = []
        4. 不在 /detail 查完整 CELL defect group
        5. 不在 /detail 查完整 source defect group

    原因：
        點 table row 後要先快速 render：
            - Sheet 左側資訊
            - same_point 星號 map
            - defect table 同點資料

        完整 cell_aoi/source defect group 由 /detail-defect-groups 另外取得，
        前端會預載，但不主動顯示，等 legend 勾選後才繪製。
    """
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

        # 這裡只放同點 rows。
        # 完整 CELL AOI defect rows 不在 /detail 查。
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
    """
    點擊 table 詳情後，前端會另外呼叫這支 API 預載完整 defect group。

    新流程：
        1. 先讀 same_point detail，取得：
            - abbr_cat
            - source_op_id
            - source_scan_time
            - cell_aoi
            - cell_op
        2. 查完整 CELL AOI defect group：
            cim_piaoi.cim_defect_yyyymm_*
        3. 查完整前站 source defect group：
            cim_cell_aoi_to_array.incoming_source_*_defect_raw_yyyymm
        4. 回傳給前端存到 row.defectGroups
        5. 前端不會立即顯示 cell/source group，只有 legend 勾選後才畫出來。
    """
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
        detail=detail,
        sheet_id_chip_id=req.sheet_id_chip_id,
        test_time=req.test_time,
        pi_type=req.pi_type or detail.get("cell_op"),
        source_op_id=req.source_op_id or detail.get("source_op_id"),
    )

    cell_group = groups.get("cell_aoi", [])
    source_group = groups.get("source", [])

    return CellAoiToArrayDefectGroupsResponse(
        feature=feature_key,
        defectGroups={
            "cell_aoi": cell_group,
            "source": source_group,
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

def get_output_engine():
    return MySQLConnet(SOURCE_DB_NAME).engine


def get_cell_engine():
    return MySQLConnet(CELL_DB_NAME).engine


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

    engine = get_output_engine()
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
        where_sql, params = build_main_where(filters, start_dt, end_dt_exclusive)

        sql = text(f"""
        SELECT {select_cols}
        FROM `{table_name}`
        WHERE {where_sql}
        ORDER BY test_time ASC, sheet_id_chip_id ASC, pi_type ASC, source_op_id ASC
        """)

        with engine.connect() as conn:
            result = conn.execute(sql, params)
            for row in result:
                rows.append(format_main_row(dict(row._mapping)))

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

    table_name = table_name_by_yyyymm(detail_base, ym)
    engine = get_output_engine()

    if not table_exists(engine, table_name):
        raise HTTPException(status_code=404, detail=f"detail table not found: {table_name}")

    sql = text(f"""
    SELECT
        sheet_id,
        scan_time,
        model_no,
        abbr_cat,
        process,
        recipe_id,
        cassette_id,
        cell_aoi,
        cell_line_id,
        pi_time,
        cell_op,
        cell_defect_cnt,
        source_op_id,
        source_scan_time,
        source_defect_cnt,
        same_point_offset,
        same_point_defect_cnt,
        same_point_rate,
        point_detail,
        match_status,
        match_status_detail
    FROM `{table_name}`
    WHERE sheet_id = :sheet_id
      AND scan_time = :scan_time
      AND source_op_id = :source_op_id
      AND (:pi_type = '' OR cell_op = :pi_type)
    LIMIT 1
    """)

    params = {
        "sheet_id": normalize_str(sheet_id_chip_id),
        "scan_time": dt,
        "pi_type": normalize_str(pi_type).upper(),
        "source_op_id": normalize_str(source_op_id),
    }

    with engine.connect() as conn:
        row = conn.execute(sql, params).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="找不到同點詳情資料")

    return format_detail_row(dict(row))


# =============================================================================
# Full Defect Group Query
# =============================================================================

def load_full_defect_groups(
    detail: Dict[str, Any],
    sheet_id_chip_id: str,
    test_time: str,
    pi_type: Optional[str],
    source_op_id: str,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    查完整 defect group。

    回傳：
        cell_aoi：
            完整 CELL AOI defect group。
            來源：cim_piaoi.cim_defect_yyyymm_*

        source：
            完整前站 defect group。
            來源：
                CF OC  -> incoming_source_cf_oc_defect_raw_yyyymm
                CF PS  -> incoming_source_cf_ps_defect_raw_yyyymm
                TFT MOR -> incoming_source_array_mor_defect_raw_yyyymm
                TFT TAR -> incoming_source_array_tar_defect_raw_yyyymm
                TFT TOS -> incoming_source_array_tos_defect_raw_yyyymm
    """
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
    """
    將 cim_defect 的 img_file_url_path + image_file_name
    組成前端可直接使用的完整 CELL AOI 圖片 URL。

    Example:
        img_file_url_path = "PIT/2606/11/CAAOI202/5H6A5704A/2355/"
        image_file_name   = "RV1_1553299_1208129_0.jpg"

        return:
        "http://l6apaimg103/dms/CELAIDI_L6A/PIT/2606/11/CAAOI202/5H6A5704A/2355/RV1_1553299_1208129_0.jpg"
    """
    path = clean_url(path_value)
    name = clean_url(name_value)

    if not path and not name:
        return ""

    # name 本身如果已經是完整 URL，直接回傳
    if name.startswith("http://") or name.startswith("https://"):
        return name

    # path 本身如果已經是完整圖片 URL，直接回傳
    if (path.startswith("http://") or path.startswith("https://")) and is_image_file_path(path):
        return path

    # path 是完整 URL 的資料夾
    if path.startswith("http://") or path.startswith("https://"):
        if name:
            return path.rstrip("/") + "/" + name.lstrip("/")
        return path

    # path 是相對路徑且已經包含圖片檔名
    if is_image_file_path(path):
        return CELL_AOI_IMG_BASE_URL.rstrip("/") + "/" + path.lstrip("/")

    # 正常情境：相對資料夾 + 檔名
    if path and name:
        return (
            CELL_AOI_IMG_BASE_URL.rstrip("/")
            + "/"
            + path.strip("/")
            + "/"
            + name.lstrip("/")
        )

    # 只有檔名但沒有 path，無法確定完整路徑
    return ""


def load_cell_defect_group(
    detail: Dict[str, Any],
    sheet_id_chip_id: str,
    test_time: str,
    pi_type: Optional[str],
) -> List[Dict[str, Any]]:
    """
    從 cim_piaoi.cim_defect_yyyymm_* 即時查完整 CELL AOI defect group。

    回傳同時支援：
        1. defect map：
            - group
            - x / y
            - cell_x / cell_y
            - defect_size
            - defect_code
            - img

        2. defect table：
            - cell_img
            - cell_info
            - source_img
            - source_info

    影像 URL 規則：
        使用 cim_defect：
            img_file_url_path + image_file_name

        組成：
            http://l6apaimg103/dms/CELAIDI_L6A/{img_file_url_path}/{image_file_name}

        Example:
            img_file_url_path = PIT/2606/11/CAAOI202/5H6A5704A/2355/
            image_file_name   = RV1_1553299_1208129_0.jpg

            cell_img =
            http://l6apaimg103/dms/CELAIDI_L6A/PIT/2606/11/CAAOI202/5H6A5704A/2355/RV1_1553299_1208129_0.jpg

    注意：
        CELL AOI 座標不做 Y 軸反轉。
        x = raw_x
        y = raw_y
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

        sheet_col = first_existing(
            colset,
            ["sheet_id_chip_id", "sheet_id", "glass_id", "glass"],
        )
        time_col = first_existing(
            colset,
            ["test_time", "scan_time", "detect_time"],
        )
        pi_col = first_existing(
            colset,
            ["pi_type", "cell_op"],
        )
        chip_col = first_existing(
            colset,
            ["chip_id", "chip", "tft_chip_id", "cf_chip_id"],
        )

        # CELL AOI 座標：依你目前 cim_defect 欄位，優先 pox_x1 / pox_y1
        x_col = first_existing(
            colset,
            ["pox_x1", "trans_x", "x", "ori_x", "coord_x"],
        )
        y_col = first_existing(
            colset,
            ["pox_y1", "trans_y", "y", "ori_y", "coord_y"],
        )

        ori_x_col = first_existing(
            colset,
            ["pox_x1", "ori_x", "coord_x", "x", "trans_x"],
        )
        ori_y_col = first_existing(
            colset,
            ["pox_y1", "ori_y", "coord_y", "y", "trans_y"],
        )

        size_col = first_existing(
            colset,
            ["defect_size", "defect_size_type", "size"],
        )
        code_col = first_existing(
            colset,
            ["adc_def_code", "defect_code", "code"],
        )
        retype_col = first_existing(
            colset,
            ["retype_def_code", "retype_code", "retype"],
        )

        # 注意：
        # img_file_url_path 是「資料夾路徑」，不是完整 URL。
        # 不要把它當 img_url_col 直接塞給前端。
        img_url_col = first_existing(
            colset,
            ["img_url_path", "image_url", "url"],
        )
        img_path_col = first_existing(
            colset,
            ["img_file_url_path", "image_file_path", "pic_path", "image_path"],
        )
        img_name_col = first_existing(
            colset,
            ["image_file_name", "image_name", "img_file_name", "pic_name"],
        )

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

            # CELL AOI 座標不做 Y 軸反轉
            x = raw_x
            y = raw_y

            defect_size = normalize_size(d.get(size_col)) if size_col else "O"
            defect_code = d.get(code_col) if code_col else None
            retype_code = d.get(retype_col) if retype_col else None

            img_path = d.get(img_path_col) if img_path_col else ""
            img_name = d.get(img_name_col) if img_name_col else ""

            # 優先使用 img_file_url_path + image_file_name 組完整 URL
            img_url = join_cell_img_url(img_path, img_name)

            # 若資料表另有完整 URL 欄位，再作 fallback
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

                # 給前端 image_info cell 使用
                "img_file_url_path": normalize_str(img_path),
                "img_url_path": img_url,
            }

            idx = len(out) + 1

            out.append({
                "group": "cell_aoi",
                "index": idx,

                "cell_defect_uid": cell_defect_uid,

                # map 使用欄位
                "x": round_float(x, 3),
                "y": round_float(y, 3),
                "cell_x": round_float(x, 3),
                "cell_y": round_float(y, 3),

                "defect_size": defect_size,
                "defect_code": defect_code,

                "cell_defect_size": defect_size,
                "cell_defect_code": defect_code,

                # 圖片欄位：前端會優先吃 cell_img
                "img": img_url,
                "cell_img": img_url,
                "aoi_img": img_url,

                # defect table 主欄位
                "match": False,
                "source_op_id": detail.get("source_op_id"),
                "cell_info": cell_info,

                # 未同點時 source 欄位保持空，前端顯示 dash
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


def load_source_defect_group(
    detail: Dict[str, Any],
    sheet_id_chip_id: str,
    source_op_id: str,
) -> List[Dict[str, Any]]:
    """
    從 cim_cell_aoi_to_array.incoming_source_*_defect_raw_yyyymm 查完整前站 group。

    修正版：
        SELECT *，並將完整 raw row 放入 source_info，
        讓 source sub table 可以依 API_Config.py 的欄位直接顯示。
    """
    source_scan_time = detail.get("source_scan_time")
    if not source_scan_time:
        return []

    source_dt = parse_datetime_text(source_scan_time)
    ym = source_dt.strftime("%Y%m")

    abbr_cat = normalize_str(detail.get("abbr_cat")).upper()
    op = normalize_str(source_op_id).upper()

    base = resolve_source_raw_base(abbr_cat=abbr_cat, source_op_id=op)
    if not base:
        return []

    table_name = table_name_by_yyyymm(base, ym)
    engine = get_output_engine()

    if not table_exists(engine, table_name):
        return []

    cols = get_table_columns(engine, table_name)
    colset = set(cols)

    sheet_col = first_existing(colset, ["sheet_id", "glass_id", "board_id", "sheet_id_chip_id"])

    if op in {"TAR", "TOS"}:
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

    if op_col:
        where_parts.append(f"`{op_col}` = :op_id")
        params["op_id"] = source_op_id

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
        source_info.setdefault("op_id", source_op_id)
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

    if side == "CF":
        if op == "OC":
            return SOURCE_CF_OC_RAW_BASE
        if op == "PS":
            return SOURCE_CF_PS_RAW_BASE
        return None

    if side == "TFT":
        if op == "PX1=MOR":
            return SOURCE_ARRAY_MOR_RAW_BASE
        if op == "TAR":
            return SOURCE_ARRAY_TAR_RAW_BASE
        if op == "TOS":
            return SOURCE_ARRAY_TOS_RAW_BASE
        return None

    return None


# =============================================================================
# Merge Detail Defect Rows
# =============================================================================

def merge_cell_group_with_point_rows(
    cell_group: List[Dict[str, Any]],
    point_rows: List[Dict[str, Any]],
    abbr_cat: Optional[str],
    source_op_id: Optional[str],
) -> List[Dict[str, Any]]:
    """
    將完整 CELL AOI defect rows 與 point_detail 解析出的同點 rows 合併。

    合併 key 優先使用 cell_defect_uid；
    若沒有 uid，fallback 使用 trans_x/trans_y/defect_size/defect_code。
    """
    if not cell_group:
        return []

    match_map: Dict[str, Dict[str, Any]] = {}

    for p in point_rows:
        key = build_match_key_from_defect_row(p)
        if key:
            match_map[key] = p

    out: List[Dict[str, Any]] = []

    for idx, c in enumerate(cell_group, start=1):
        row = dict(c)
        row["index"] = idx

        key = build_match_key_from_defect_row(row)
        matched = match_map.get(key)

        if matched:
            row["match"] = True
            row["source_op_id"] = matched.get("source_op_id") or source_op_id
            row["source_img"] = matched.get("source_img") or ""
            row["source_info"] = matched.get("source_info") or {}
            row["source_x"] = matched.get("source_x")
            row["source_y"] = matched.get("source_y")
            row["source_defect_code"] = matched.get("source_defect_code")
            row["source_defect_size"] = matched.get("source_defect_size")
            row["distance"] = matched.get("distance")
            row["dx"] = matched.get("dx")
            row["dy"] = matched.get("dy")
            row["offset"] = matched.get("offset")

            side = normalize_str(abbr_cat).upper()
            if side == "TFT":
                row["array_x"] = matched.get("source_x")
                row["array_y"] = matched.get("source_y")
                row["array_img"] = matched.get("source_img") or ""
                row["cf_x"] = 0
                row["cf_y"] = 0
                row["cf_img"] = ""
            elif side == "CF":
                row["cf_x"] = matched.get("source_x")
                row["cf_y"] = matched.get("source_y")
                row["cf_img"] = matched.get("source_img") or ""
                row["array_x"] = 0
                row["array_y"] = 0
                row["array_img"] = ""

        else:
            row["match"] = False
            row.setdefault("source_op_id", source_op_id)
            row.setdefault("source_img", "")
            row.setdefault("source_info", {})
            row.setdefault("source_x", 0)
            row.setdefault("source_y", 0)
            row.setdefault("source_defect_code", None)
            row.setdefault("source_defect_size", "O")
            row.setdefault("distance", None)
            row.setdefault("dx", None)
            row.setdefault("dy", None)
            row.setdefault("offset", None)

        out.append(row)

    return out


def build_match_key_from_defect_row(row: Dict[str, Any]) -> str:
    cell_info = row.get("cell_info") if isinstance(row.get("cell_info"), dict) else {}

    uid = normalize_str(cell_info.get("cell_defect_uid") or row.get("cell_defect_uid"))
    if uid:
        return f"uid:{uid}"

    x = round_float(cell_info.get("trans_x") or row.get("cell_x"), 3)
    y = round_float(cell_info.get("trans_y") or row.get("cell_y"), 3)
    code = normalize_str(cell_info.get("defect_code") or row.get("cell_defect_code"))
    size = normalize_size(cell_info.get("defect_size") or row.get("cell_defect_size") or row.get("defect_size"))

    return f"xy:{x}|{y}|{code}|{size}"


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
    engine = get_output_engine()

    if not table_exists(engine, table_name):
        raise HTTPException(status_code=404, detail=f"summary table not found: {table_name}")

    sql = text(f"""
    UPDATE `{table_name}`
    SET
        comment = :comment,
        action = :action,
        editor = :editor,
        modify_time = NOW()
    WHERE sheet_id_chip_id = :sheet_id_chip_id
      AND test_time = :test_time
      AND source_op_id = :source_op_id
      AND (:pi_type = '' OR pi_type = :pi_type)
    """)

    params = {
        "sheet_id_chip_id": normalize_str(sheet_id_chip_id),
        "test_time": dt,
        "pi_type": normalize_str(pi_type).upper(),
        "source_op_id": normalize_str(source_op_id),
        "comment": none_if_blank(comment),
        "action": none_if_blank(action),
        "editor": none_if_blank(editor),
    }

    with engine.begin() as conn:
        result = conn.execute(sql, params)

    return int(result.rowcount or 0)


# =============================================================================
# SQL Builders
# =============================================================================
def normalize_sheet_ids_from_filters(filters: CellAoiToArrayFilters) -> List[str]:
    """
    整理前端 CSV 上傳解析出的多筆 sheet_id。

    支援：
        filters.sheetIds
        filters.sheet_ids

    回傳：
        去空值、去 nan/null、轉大寫、去重後的 sheet_id list
    """
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
    filters: CellAoiToArrayFilters,
    start_dt: datetime,
    end_dt_exclusive: datetime,
) -> Tuple[str, Dict[str, Any]]:
    where_parts = [
        "test_time >= :start_dt",
        "test_time < :end_dt",
    ]

    params: Dict[str, Any] = {
        "start_dt": start_dt,
        "end_dt": end_dt_exclusive,
    }

    # tool 現在對應 line_id，不是 source_op_id
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

    if line_id:
        where_parts.append("line_id = :line_id")
        params["line_id"] = line_id

    if source_op:
        where_parts.append("source_op_id = :source_op_id")
        params["source_op_id"] = source_op

    if sheet_type:
        where_parts.append("abbr_cat = :abbr_cat")
        params["abbr_cat"] = sheet_type

    # -------------------------------------------------------------
    # CSV 多片 sheet 查詢
    # 有 sheetIds 時，優先使用 IN。
    # 沒有 sheetIds 時，才使用單筆 SHEET查詢 LIKE。
    # -------------------------------------------------------------
    if sheet_ids:
        bind_names = []

        for i, sid in enumerate(sheet_ids):
            key = f"sheet_id_{i}"
            bind_names.append(f":{key}")
            params[key] = sid

        where_parts.append(
            f"UPPER(sheet_id_chip_id) IN ({', '.join(bind_names)})"
        )

    elif sheet_id:
        where_parts.append("UPPER(sheet_id_chip_id) LIKE :sheet_id")
        params["sheet_id"] = f"%{sheet_id}%"

    if pi_type:
        where_parts.append("pi_type = :pi_type")
        params["pi_type"] = pi_type

    if match_status:
        where_parts.append("match_status = :match_status")
        params["match_status"] = match_status

    if aoi:
        where_parts.append("aoi = :aoi")
        params["aoi"] = aoi

    if model_no:
        where_parts.append("model_no = :model_no")
        params["model_no"] = model_no

    if recipe_id:
        where_parts.append("recipe_id = :recipe_id")
        params["recipe_id"] = recipe_id

    return " AND ".join(where_parts), params

# =============================================================================
# Formatters
# =============================================================================

def format_main_row(row: Dict[str, Any]) -> Dict[str, Any]:
    d = clean_dict(row)

    same_rate = to_float(d.get("same_point_rate"))
    total_defect_qty = to_int(d.get("total_defect_qty"))
    same_point_cnt = to_int(d.get("same_point_defect_cnt"))
    source_defect_cnt = to_int(d.get("source_defect_cnt"))

    out = {
        "test_time": fmt_dt(d.get("test_time")),
        "line_id": d.get("line_id"),
        "cassette_id": d.get("cassette_id"),
        "sheet_id_chip_id": d.get("sheet_id_chip_id"),
        "model_no": d.get("model_no"),
        "abbr_cat": d.get("abbr_cat"),
        "recipe_id": d.get("recipe_id"),
        "aoi": d.get("aoi"),
        "total_defect_qty": total_defect_qty,
        "pi_time": fmt_dt(d.get("pi_time")),
        "pi_type": d.get("pi_type"),
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

        # 舊欄位 alias
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
            pi_type=d.get("pi_type"),
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


def format_detail_row(row: Dict[str, Any]) -> Dict[str, Any]:
    d = clean_dict(row)

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

def parse_point_detail_to_frontend_rows(
    point_detail: Any,
    abbr_cat: Optional[str],
    source_op_id: Optional[str],
) -> List[Dict[str, Any]]:
    """
    將 incoming_same_point_detail.point_detail 轉成前端 defect table rows。

    每一列：
        - cell_img + cell_info
        - source_img + source_info
        - source_op_id 用來決定 source 子表格欄位

    重點：
        source_info 會攤平 source top-level / source.raw / source.display，
        讓 API_Config.py 的 source sub table 欄位可以直接讀到。
    """
    raw_items = parse_json_list(point_detail)
    rows: List[Dict[str, Any]] = []

    side = normalize_str(abbr_cat).upper()

    for idx, item in enumerate(raw_items, start=1):
        cell = item.get("cell") if isinstance(item.get("cell"), dict) else {}
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        match = item.get("match") if isinstance(item.get("match"), dict) else {}

        source_display = source.get("display") if isinstance(source.get("display"), dict) else {}
        source_raw = source.get("raw") if isinstance(source.get("raw"), dict) else {}

        src_op = (
            normalize_str(source.get("source_op_id"))
            or normalize_str(source_display.get("source_op_id"))
            or normalize_str(source_raw.get("source_op_id"))
            or normalize_str(source_raw.get("op_id"))
            or normalize_str(source_op_id)
        )

        cell_x = source_or_zero(cell.get("trans_x"))
        cell_y = source_or_zero(cell.get("trans_y"))

        source_x = source_or_zero(
            source.get("trans_x")
            or source_display.get("trans_x")
            or source_raw.get("trans_x")
        )

        source_y = source_or_zero(
            source.get("trans_y")
            or source_display.get("trans_y")
            or source_raw.get("trans_y")
        )

        cell_img = clean_url(cell.get("img_url_path"))

        source_img = clean_url(
            source.get("img_url_path")
            or source_display.get("img_url_path")
            or source_raw.get("img_url_path")
        )

        cell_info = {
            "cell_defect_uid": cell.get("cell_defect_uid"),
            "chip_id": cell.get("chip_id"),
            "defect_code": cell.get("defect_code"),
            "retype_def_code": cell.get("retype_def_code"),
            "defect_size": normalize_size(cell.get("defect_size")),
            "ori_x": round_float(cell.get("ori_x"), 3),
            "ori_y": round_float(cell.get("ori_y"), 3),
            "trans_x": round_float(cell.get("trans_x"), 3),
            "trans_y": round_float(cell.get("trans_y"), 3),
            "image_name": cell.get("image_name"),
            "img_url_path": cell_img,
        }

        # -------------------------------------------------------------
        # source_info 攤平策略：
        #   1. 先放 source top-level
        #   2. 再補 raw
        #   3. 再補 display
        #   4. 最後補標準欄位
        #
        # 前端 sub table 是直接用 key 取值：
        #   source_info[key]
        #   source_info.display[key]
        #   source_info.raw[key]
        # 所以這邊盡量攤平，避免前端讀不到。
        # -------------------------------------------------------------
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
        source_info.setdefault("op_id", src_op)

        source_info.setdefault("source_defect_uid", (
            source.get("source_defect_uid")
            or source_display.get("source_defect_uid")
            or source_raw.get("source_defect_uid")
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
        )

        source_size = (
            source.get("defect_size")
            or source.get("defect_size_type")
            or source_display.get("defect_size")
            or source_display.get("defect_size_type")
            or source_raw.get("defect_size")
            or source_raw.get("defect_size_type")
            or source_raw.get("tar_judge")
        )

        source_info.setdefault("defect_code", source_code)
        source_info.setdefault("defect_size", normalize_size(source_size))
        source_info.setdefault("defect_size_type", normalize_size(source_size))

        row = {
            "index": idx,
            "match": True,
            "source_op_id": src_op,
            "defect_size": normalize_size(cell.get("defect_size") or source_size),

            # image_info 主欄位
            "cell_img": cell_img,
            "cell_info": cell_info,
            "source_img": source_img,
            "source_info": source_info,

            # map / 舊前端相容欄位
            "cell_x": cell_x,
            "cell_y": cell_y,
            "source_x": source_x,
            "source_y": source_y,

            "cell_defect_code": cell.get("defect_code"),
            "source_defect_code": source_code,
            "cell_defect_size": normalize_size(cell.get("defect_size")),
            "source_defect_size": normalize_size(source_size),

            "distance": round_float(match.get("distance"), 3),
            "dx": round_float(match.get("dx"), 3),
            "dy": round_float(match.get("dy"), 3),
            "offset": match.get("offset"),

            # 舊欄位 alias
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
        cell = item.get("cell") if isinstance(item.get("cell"), dict) else {}
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        match = item.get("match") if isinstance(item.get("match"), dict) else {}

        source_display = source.get("display") if isinstance(source.get("display"), dict) else {}
        source_raw = source.get("raw") if isinstance(source.get("raw"), dict) else {}

        x = source_or_zero(cell.get("trans_x"))
        y = source_or_zero(cell.get("trans_y"))

        source_x = source_or_zero(
            source.get("trans_x")
            or source_display.get("trans_x")
            or source_raw.get("trans_x")
        )

        source_y = source_or_zero(
            source.get("trans_y")
            or source_display.get("trans_y")
            or source_raw.get("trans_y")
        )

        cell_img = clean_url(cell.get("img_url_path"))

        source_img = clean_url(
            source.get("img_url_path")
            or source_display.get("img_url_path")
            or source_raw.get("img_url_path")
        )

        src_op = (
            source.get("source_op_id")
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
        )

        source_size = (
            source.get("defect_size")
            or source.get("defect_size_type")
            or source_display.get("defect_size")
            or source_display.get("defect_size_type")
            or source_raw.get("defect_size")
            or source_raw.get("defect_size_type")
            or source_raw.get("tar_judge")
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
        source_info.setdefault("op_id", src_op)
        source_info.setdefault("img_url_path", source_img)
        source_info.setdefault("trans_x", round_float(source_x, 3))
        source_info.setdefault("trans_y", round_float(source_y, 3))
        source_info.setdefault("defect_code", source_code)
        source_info.setdefault("defect_size", normalize_size(source_size))
        source_info.setdefault("defect_size_type", normalize_size(source_size))

        size = normalize_size(cell.get("defect_size") or source_size)

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
            "cell_defect_code": cell.get("defect_code"),
            "cell_defect_size": normalize_size(cell.get("defect_size")),
            "cell_defect_uid": cell.get("cell_defect_uid"),

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

def build_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Summary cards 計算邏輯。

    CELL AOI RUN片數：
        sheet_id_chip_id + pi_type + test_time 唯一值總數。
        同片 BPI/API 算兩片。
        同片不同前站站點只算一片。

    ARRAY 同點同片：
        分母 = CELL AOI 有 run 過的 TFT 唯一 glass-run 數，顯示一次。
        分子 = 各 ARRAY 站點 match_status = MATCHED 的唯一 TFT glass-run 數。

    CF 同點同片：
        分母 = CELL AOI 有 run 過的 CF 唯一 glass-run 數，顯示一次。
        分子 = 各 CF 站點 match_status = MATCHED 的唯一 CF glass-run 數。
    """

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

    def station_same_count(
        source_rows: List[Dict[str, Any]],
        station: str,
    ) -> int:
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

    tft_rows = [
        r for r in rows
        if side_of(r) == "TFT"
    ]

    cf_rows = [
        r for r in rows
        if side_of(r) == "CF"
    ]

    # 分母：CELL 有 run 過的 TFT / CF 母體片數，不看前站站點
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

    # 顯示用文字：分母只顯示一次

    array_same_by_station = f"Total(Cell AOI TFT片數)：{len(tft_cell_run_keys)}" + " \n" + "\n".join(
        [
            f"{display_station_label(station)}(有同點的片數)：{array_station_same_detail[station]}"
            for station in array_station_order
        ]
    )

    cf_same_by_station = f"Total(Cell AOI CF片數){len(cf_cell_run_keys)}" + " \n" + "\n".join(
        [
           f"{display_station_label(station)}(有同點的片數)：{cf_station_same_detail[station]}"
            for station in cf_station_order
        ]
    )
    return {
        # summary cards 使用
        "cell_total": len(all_cell_keys),
        "array_same_by_station": array_same_by_station,
        "cf_same_by_station": cf_same_by_station,

        # 明細數值，後續若前端要改成表格/進度條可直接用
        "array_cell_run_total": len(tft_cell_run_keys),
        "cf_cell_run_total": len(cf_cell_run_keys),
        "array_station_same_detail": array_station_same_detail,
        "cf_station_same_detail": cf_station_same_detail,

        # 保留舊 key，避免前端 config 尚未改完時空白
        "tft_match": array_same_by_station,
        "cf_match": cf_same_by_station,

        # 其他統計保留
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
            result[chart_key] = {
                "xMin": None,
                "xMax": None,
                "xDayStartMs": [],
                "series": [],
            }

    return result


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


def clean_url(value: Any) -> str:
    s = normalize_str(value)
    if s.lower() in {"none", "nan", "nat", "<na>", "null"}:
        return ""
    return s


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

    if s == "PX1=MOR":
        return "MOR"

    return s
