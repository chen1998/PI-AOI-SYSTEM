# models/cell_aoi_to_array/API_Config.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List


# =============================================================================
# Feature keys
# =============================================================================

AOI_FEATURE = "aoi-sampling-compare"
INSPECTION_FEATURE = "inspection-sampling-compare"
AOI_INSPEC_FEATURE = "aoi-inspec-compare"


# =============================================================================
# DB / Table config
# =============================================================================

# AOI 來料檢結果 DB
SOURCE_DB_NAME = "cim_cell_aoi_to_array"

# CELL AOI 原始 DB
CELL_DB_NAME = "cim_piaoi"

# Inspection 來料檢結果 DB
INSPECTION_SOURCE_DB_NAME = "cim_cell_inspec_to_array"

# Inspection 原始 DB，這個目前主要給 ETL 用，API 一般不直接讀
INSPECTION_INPUT_DB_NAME = "piaoi_inspection_density"


# -----------------------------------------------------------------------------
# AOI 來料檢 tables: cim_cell_aoi_to_array
# -----------------------------------------------------------------------------

API_AOI_SUMMARY_BASE = "api_aoi_summary_yyyymm"
SAME_POINT_DETAIL_BASE = "incoming_same_point_detail_yyyymm"
GLASS_SUMMARY_BASE = "incoming_glass_summary_yyyymm"


# -----------------------------------------------------------------------------
# Inspection 來料檢 tables: cim_cell_inspec_to_array
# -----------------------------------------------------------------------------

API_INSPECTION_SUMMARY_BASE = "api_inspection_summary_yyyymm"
INSPECTION_SAME_POINT_DETAIL_BASE = "incoming_inspection_same_point_detail_yyyymm"
INSPECTION_GLASS_SUMMARY_BASE = "incoming_inspection_glass_summary_yyyymm"


# -----------------------------------------------------------------------------
# 共用 source raw cache tables: cim_cell_aoi_to_array
# Inspection ETL 會讀這些，但 API 主查詢不直接查這些
# -----------------------------------------------------------------------------

SOURCE_CF_OC_RAW_BASE = "incoming_source_cf_oc_defect_raw_yyyymm"
SOURCE_CF_PS_RAW_BASE = "incoming_source_cf_ps_defect_raw_yyyymm"
SOURCE_ARRAY_MOR_RAW_BASE = "incoming_source_array_mor_defect_raw_yyyymm"
SOURCE_ARRAY_TAR_RAW_BASE = "incoming_source_array_tar_defect_raw_yyyymm"
SOURCE_ARRAY_TOS_RAW_BASE = "incoming_source_array_tos_defect_raw_yyyymm"

SOURCE_GROUP_STATE_TABLE = "incoming_source_group_state"


def table_name_by_yyyymm(base: str, yyyymm: str) -> str:
    return base.replace("yyyymm", yyyymm).lower()


# =============================================================================
# Common options
# =============================================================================

CELL_AOI_TO_ARRAY_SHEET_TYPES: List[str] = ["TFT", "CF"]

CELL_AOI_TO_ARRAY_PI_TYPES: List[str] = ["BPI", "API"]

CELL_AOI_TO_ARRAY_DEFECT_SIZES: List[str] = ["S", "M", "L", "O"]

# AOI 來料檢前端「機台別」select 使用，對應 api_aoi_summary.line_id
CELL_AOI_TO_ARRAY_LINE_OPTIONS: List[str] = [
    f"CAPIC{i}00" for i in range(1, 8)
]

# Inspection line_id 來自 inspection_summary_table.TOOL_ID，先不寫死選項，讓前端或 API 動態查 distinct 比較合理
INSPECTION_LINE_OPTIONS: List[str] = []


# -----------------------------------------------------------------------------
# AOI 來料檢 source_op_id
# 對應目前 AOI 結果表：
#   OC / PS / PX1=MOR / TAR / TOS
# -----------------------------------------------------------------------------

CELL_AOI_TO_ARRAY_SOURCE_OP_OPTIONS: List[str] = [
    "OC",
    "PS",
    "PX1=MOR",
    "TAR",
    "TOS",
]

CELL_AOI_TO_ARRAY_CF_SOURCE_OP_OPTIONS: List[str] = [
    "OC",
    "PS",
]

CELL_AOI_TO_ARRAY_ARRAY_SOURCE_OP_OPTIONS: List[str] = [
    "PX1=MOR",
    "TAR",
    "TOS",
]


# -----------------------------------------------------------------------------
# Inspection 來料檢 source_op_id
# 對應 RUN_CELL_INSPECTION_INCOMING_GOVERNANCE.py 產出的結果：
#   AOI_BPI / AOI_API / CF_OC / CF_PS / ARRAY_MOR / ARRAY_TAR / ARRAY_TOS
# -----------------------------------------------------------------------------

INSPECTION_SOURCE_OP_OPTIONS: List[str] = [
    "AOI_BPI",
    "AOI_API",
    "CF_OC",
    "CF_PS",
    "ARRAY_MOR",
    "ARRAY_TAR",
    "ARRAY_TOS",
]

INSPECTION_CF_SOURCE_OP_OPTIONS: List[str] = [
    "AOI_BPI",
    "AOI_API",
    "CF_OC",
    "CF_PS",
]

INSPECTION_ARRAY_SOURCE_OP_OPTIONS: List[str] = [
    "AOI_BPI",
    "AOI_API",
    "ARRAY_MOR",
    "ARRAY_TAR",
    "ARRAY_TOS",
]


# -----------------------------------------------------------------------------
# Match status
# -----------------------------------------------------------------------------

CELL_AOI_TO_ARRAY_MATCH_STATUS_OPTIONS: List[str] = [
    "MATCHED",
    "NO_SAME_POINT",
    "NO_SOURCE_DEFECT",
    "SOURCE_NOT_FOUND",
    "SOURCE_QUERY_FAILED",
    "NO_CELL_DEFECT",
    "CELL_COORD_INVALID",
    "SOURCE_COORD_INVALID",
    "INVALID_ABBR_CAT",
]

INSPECTION_MATCH_STATUS_OPTIONS: List[str] = [
    "MATCHED",
    "NO_SAME_POINT",
    "NO_SOURCE_DEFECT",
    "SOURCE_NOT_FOUND",
    "SOURCE_QUERY_FAILED",
    "NO_INSPECTION_DEFECT",
    "INSPECTION_COORD_INVALID",
    "SOURCE_COORD_INVALID",
    "INVALID_TYPE",
]


# -----------------------------------------------------------------------------
# Axis
# -----------------------------------------------------------------------------

CELL_AOI_TO_ARRAY_AXIS = {
    "min_x": 0,
    "max_x": 1850000,
    "min_y": 0,
    "max_y": 1500000,
}


# =============================================================================
# Summary cards
# =============================================================================

CELL_AOI_TO_ARRAY_SUMMARY_CARDS = [
    {
        "key": "cell_total",
        "label": "CELL 總抽檢數",
    },
    {
        "key": "array_same_by_station",
        "label": "ARRAY 同點片數",
    },
    {
        "key": "cf_same_by_station",
        "label": "CF 同點片數",
    },
]

INSPECTION_SUMMARY_CARDS = [
    {
        "key": "inspection_total",
        "label": "Inspection 總抽檢數",
    },
    {
        "key": "aoi_same_by_station",
        "label": "AOI 同點片數",
    },
    {
        "key": "source_same_by_station",
        "label": "前站同點片數",
    },
]


# =============================================================================
# Main table columns
# =============================================================================

AOI_TABLE_COLUMNS = [
    {"key": "", "label": "詳情"},
    {"key": "test_time", "label": "量測時間"},
    {"key": "line_id", "label": "Line"},
    {"key": "cassette_id", "label": "Cassette"},
    {"key": "sheet_id_chip_id", "label": "SheetID"},
    {"key": "abbr_cat", "label": "ABBR"},
    {"key": "pi_type", "label": "CELL PI"},
    {"key": "recipe_id", "label": "Recipe"},
    {"key": "model_no", "label": "Model"},
    {"key": "aoi", "label": "CELL AOI"},
    {"key": "total_defect_qty", "label": "CELL點數"},
    {"key": "source_op_id", "label": "站點"},
    {"key": "same_point_defect_cnt", "label": "可追溯CELL點數"},
    {"key": "same_point_rate", "label": "比對率"},
    {"key": "match_status", "label": "狀態"},
]

INSPECTION_TABLE_COLUMNS = [
    {"key": "", "label": "詳情"},
    {"key": "test_time", "label": "Inspection時間"},
    {"key": "line_id", "label": "Tool"},
    {"key": "sheet_id_chip_id", "label": "SheetID"},
    {"key": "abbr_cat", "label": "TYPE"},
    {"key": "model_no", "label": "Model"},
    {"key": "total_defect_qty", "label": "Inspection點數"},
    {"key": "source_op_id", "label": "比對站點"},
    {"key": "source_scan_time", "label": "前站時間"},
    {"key": "source_defect_cnt", "label": "前站點數"},
    {"key": "same_point_defect_cnt", "label": "可追溯Inspection點數"},
    {"key": "same_point_rate", "label": "比對率"},
    {"key": "match_status", "label": "狀態"},
]

AOI_INSPEC_TABLE_COLUMNS = AOI_TABLE_COLUMNS


# =============================================================================
# Detail fields
# =============================================================================

COMMON_AOI_SHEET_DETAIL_FIELDS = [
    {"key": "test_time", "label": "量測時間"},
    {"key": "line_id", "label": "Line"},
    {"key": "cassette_id", "label": "Cassette"},
    {"key": "sheet_id_chip_id", "label": "SheetID"},
    {"key": "abbr_cat", "label": "ABBR"},
    {"key": "pi_type", "label": "CELL PI"},
    {"key": "recipe_id", "label": "Recipe"},
    {"key": "model_no", "label": "Model"},
    {"key": "aoi", "label": "CELL AOI"},
    {"key": "total_defect_qty", "label": "CELL點數"},
    {"key": "source_op_id", "label": "站點"},
    {"key": "source_scan_time", "label": "前站時間"},
    {"key": "source_defect_cnt", "label": "前站點數"},
    {"key": "same_point_offset", "label": "Offset"},
    {"key": "same_point_defect_cnt", "label": "可追溯CELL點數"},
    {"key": "same_point_rate", "label": "比對率"},
    {"key": "match_status", "label": "狀態"},
    {"key": "match_status_detail", "label": "狀態說明"},
]

COMMON_INSPECTION_SHEET_DETAIL_FIELDS = [
    {"key": "test_time", "label": "Inspection時間"},
    {"key": "line_id", "label": "Tool"},
    {"key": "sheet_id_chip_id", "label": "SheetID"},
    {"key": "abbr_cat", "label": "TYPE"},
    {"key": "model_no", "label": "Model"},
    {"key": "total_defect_qty", "label": "Inspection點數"},
    {"key": "source_op_id", "label": "比對站點"},
    {"key": "source_scan_time", "label": "前站時間"},
    {"key": "source_defect_cnt", "label": "前站點數"},
    {"key": "same_point_offset", "label": "Offset"},
    {"key": "same_point_defect_cnt", "label": "可追溯Inspection點數"},
    {"key": "same_point_rate", "label": "比對率"},
    {"key": "match_status", "label": "狀態"},
    {"key": "match_status_detail", "label": "狀態說明"},
]

AOI_SHEET_DETAIL_FIELDS_BY_SIDE = {
    "TFT": COMMON_AOI_SHEET_DETAIL_FIELDS,
    "CF": COMMON_AOI_SHEET_DETAIL_FIELDS,
}

INSPECTION_SHEET_DETAIL_FIELDS_BY_SIDE = {
    "TFT": COMMON_INSPECTION_SHEET_DETAIL_FIELDS,
    "CF": COMMON_INSPECTION_SHEET_DETAIL_FIELDS,
}

AOI_INSPEC_SHEET_DETAIL_FIELDS_BY_SIDE = {
    "TFT": COMMON_AOI_SHEET_DETAIL_FIELDS,
    "CF": COMMON_AOI_SHEET_DETAIL_FIELDS,
}


# =============================================================================
# Chart config
# =============================================================================

CELL_AOI_TO_ARRAY_CHARTS = {
    AOI_FEATURE: [
        {"key": "array_aoi_same_point_rate", "title": "ARRAY - BY CELL AOI 每片比對率"},
        {"key": "cf_aoi_same_point_rate", "title": "CF - BY CELL AOI 每片比對率"},

        {"key": "array_op_same_point_rate", "title": "ARRAY - BY 站點每片比對率"},
        {"key": "cf_op_same_point_rate", "title": "CF - BY 站點每片比對率"},

        {"key": "array_line_same_point_rate", "title": "ARRAY - BY Line 每片比對率"},
        {"key": "cf_line_same_point_rate", "title": "CF - BY Line 每片比對率"},
    ],

    INSPECTION_FEATURE: [
        # 第 1 排：站點每片比對率
        {
            "key": "inspection_array_op_same_point_rate",
            "title": "ARRAY - BY 站點每片比對率",
        },
        {
            "key": "inspection_cf_op_same_point_rate",
            "title": "CF - BY 站點每片比對率",
        },
        {
            "key": "inspection_cell_aoi_op_same_point_rate",
            "title": "CELL AOI - BY 站點每片比對率",
        },

        # 第 2 排：Inspection Line 每片比對率
        {
            "key": "inspection_array_line_same_point_rate",
            "title": "ARRAY - BY Inspection Line 每片比對率",
        },
        {
            "key": "inspection_cf_line_same_point_rate",
            "title": "CF - BY Inspection Line 每片比對率",
        },
        {
            "key": "inspection_cell_aoi_line_same_point_rate",
            "title": "CELL AOI - BY Inspection Line 每片比對率",
        },
    ],
}


# =============================================================================
# Side config
# =============================================================================

SHEET_SIDE_CONFIG = {
    "TFT": {
        "compareTargetLabel": "ARRAY",
        "compareTargetCountLabel": "ARRAY點數",
        "mapTargetLegendLabel": "ARRAY",
        "compareTitleTemplate": "照片比對 (CELL {system_label} Vs. ARRAY 前站)",
        "compareLineTemplate": "CELL {system_label} 共 {cell_count} 點，可追溯 ARRAY {match_count} 點",
        "noticeIcon": "提示",
        "noticeText": "TFT 會依 PX1=MOR / TAR / TOS 分站點呈現。",
    },
    "CF": {
        "compareTargetLabel": "CF",
        "compareTargetCountLabel": "CF點數",
        "mapTargetLegendLabel": "CF",
        "compareTitleTemplate": "照片比對 (CELL {system_label} Vs. CF 前站)",
        "compareLineTemplate": "CELL {system_label} 共 {cell_count} 點，可追溯 CF {match_count} 點",
        "noticeIcon": "提示",
        "noticeText": "CF 會依 OC / PS 分站點呈現。",
    },
}

INSPECTION_SHEET_SIDE_CONFIG = {
    "TFT": {
        "compareTargetLabel": "AOI / ARRAY",
        "compareTargetCountLabel": "前站點數",
        "mapTargetLegendLabel": "AOI / ARRAY",
        "compareTitleTemplate": "照片比對 (Inspection Vs. AOI / ARRAY 前站)",
        "compareLineTemplate": "Inspection 共 {cell_count} 點，可追溯前站 {match_count} 點",
        "noticeIcon": "提示",
        "noticeText": "TFT 會依 AOI_BPI / AOI_API / ARRAY_MOR / ARRAY_TAR / ARRAY_TOS 分站點呈現。",
    },
    "CF": {
        "compareTargetLabel": "AOI / CF",
        "compareTargetCountLabel": "前站點數",
        "mapTargetLegendLabel": "AOI / CF",
        "compareTitleTemplate": "照片比對 (Inspection Vs. AOI / CF 前站)",
        "compareLineTemplate": "Inspection 共 {cell_count} 點，可追溯前站 {match_count} 點",
        "noticeIcon": "提示",
        "noticeText": "CF 會依 AOI_BPI / AOI_API / CF_OC / CF_PS 分站點呈現。",
    },
}


# =============================================================================
# Defect detail table columns
# =============================================================================

# -----------------------------------------------------------------------------
# AOI feature 主表欄位：CF
# -----------------------------------------------------------------------------

DEFECT_DETAIL_MAIN_COLUMNS_CF = [
    {
        "type": "text",
        "key": "index",
        "label": "索引",
    },
    {
        "type": "match",
        "key": "match",
        "label": "Match",
    },
    {
        "type": "image_info",
        "key": "cell_img",
        "label": "CELL AOI",
        "imageKey": "cell_img",
        "infoKey": "cell_info",
        "subColumnsKey": "cell_aoi",
    },
    {
        "type": "image_info",
        "key": "source_img",
        "label": "CF AOI/Repair前",
        "imageKey": "source_img",
        "infoKey": "source_info",
        "sourceOpKey": "source_op_id",
        "subColumnsBySourceOpKey": "source",
    },
]


# -----------------------------------------------------------------------------
# AOI feature 主表欄位：TFT / ARRAY
# -----------------------------------------------------------------------------

DEFECT_DETAIL_MAIN_COLUMNS_TFT = [
    {
        "type": "text",
        "key": "index",
        "label": "索引",
    },
    {
        "type": "match",
        "key": "match",
        "label": "Match",
    },
    {
        "type": "image_info",
        "key": "cell_img",
        "label": "CELL AOI",
        "imageKey": "cell_img",
        "infoKey": "cell_info",
        "subColumnsKey": "cell_aoi",
    },
    {
        "type": "image_info",
        "key": "source_img",
        "label": "ARRAY",
        "imageKey": "source_img",
        "infoKey": "source_info",
        "sourceOpKey": "source_op_id",
        "subColumnsBySourceOpKey": "source",
    },
]


# -----------------------------------------------------------------------------
# Inspection feature 主表欄位：CF
# point_detail 裡仍沿用 cell_img / cell_info key，前端可不改。
# 但 label 改成 Inspection。
# -----------------------------------------------------------------------------

DEFECT_DETAIL_MAIN_COLUMNS_INSPECTION_CF = [
    {
        "type": "text",
        "key": "index",
        "label": "索引",
    },
    {
        "type": "match",
        "key": "match",
        "label": "Match",
    },
    {
        "type": "image_info",
        "key": "cell_img",
        "label": "Inspection",
        "imageKey": "cell_img",
        "infoKey": "cell_info",
        "subColumnsKey": "inspection",
    },
    {
        "type": "image_info",
        "key": "source_img",
        "label": "AOI / CF 前站",
        "imageKey": "source_img",
        "infoKey": "source_info",
        "sourceOpKey": "source_op_id",
        "subColumnsBySourceOpKey": "source",
    },
]


# -----------------------------------------------------------------------------
# Inspection feature 主表欄位：TFT
# -----------------------------------------------------------------------------

DEFECT_DETAIL_MAIN_COLUMNS_INSPECTION_TFT = [
    {
        "type": "text",
        "key": "index",
        "label": "索引",
    },
    {
        "type": "match",
        "key": "match",
        "label": "Match",
    },
    {
        "type": "image_info",
        "key": "cell_img",
        "label": "Inspection",
        "imageKey": "cell_img",
        "infoKey": "cell_info",
        "subColumnsKey": "inspection",
    },
    {
        "type": "image_info",
        "key": "source_img",
        "label": "AOI / ARRAY 前站",
        "imageKey": "source_img",
        "infoKey": "source_info",
        "sourceOpKey": "source_op_id",
        "subColumnsBySourceOpKey": "source",
    },
]


# -----------------------------------------------------------------------------
# CELL AOI 子表格欄位
# 來源：AOI feature /detail 回傳 defects[*].cell_info
# -----------------------------------------------------------------------------

DEFECT_DETAIL_COLUMNS_SUB_CELL_AOI = [
    {"type": "text", "key": "chip_id", "label": "Chip"},
    {"type": "text", "key": "defect_code", "label": "Defect Code"},
    {"type": "text", "key": "retype_def_code", "label": "Retype"},
    {"type": "text", "key": "defect_size", "label": "Size"},
    {"type": "text", "key": "ori_x", "label": "ORI X"},
    {"type": "text", "key": "ori_y", "label": "ORI Y"},
    {"type": "text", "key": "trans_x", "label": "Trans X"},
    {"type": "text", "key": "trans_y", "label": "Trans Y"},
    {"type": "text", "key": "image_name", "label": "Image"},
]


# -----------------------------------------------------------------------------
# Inspection target 子表格欄位
# 來源：Inspection feature /detail 回傳 defects[*].cell_info
# -----------------------------------------------------------------------------

DEFECT_DETAIL_COLUMNS_SUB_INSPECTION = [
    {"type": "text", "key": "inspection_defect_uid", "label": "UID"},
    {"type": "text", "key": "sheet_id", "label": "SheetID"},
    {"type": "text", "key": "scan_time", "label": "Inspection時間"},
    {"type": "text", "key": "line_id", "label": "Tool"},
    {"type": "text", "key": "defect_size", "label": "Size"},
    {"type": "text", "key": "defect_size_raw", "label": "Raw Size"},
    {"type": "text", "key": "recipe_name", "label": "Recipe"},
    {"type": "text", "key": "run_id", "label": "Run ID"},
    {"type": "text", "key": "sp", "label": "SP"},
    {"type": "text", "key": "stage", "label": "Stage"},
    {"type": "text", "key": "ori_x", "label": "ORI X"},
    {"type": "text", "key": "ori_y", "label": "ORI Y"},
    {"type": "text", "key": "trans_x", "label": "Trans X"},
    {"type": "text", "key": "trans_y", "label": "Trans Y"},
    {"type": "text", "key": "image_name", "label": "Image"},
]


# -----------------------------------------------------------------------------
# AOI source 子表格欄位：給 Inspection 的 AOI_BPI / AOI_API 使用
# 來源：point_detail.source
# -----------------------------------------------------------------------------

DEFECT_DETAIL_COLUMNS_SUB_AOI_SOURCE = [
    {"type": "text", "key": "source_op_id", "label": "站點"},
    {"type": "text", "key": "sheet_id", "label": "SheetID"},
    {"type": "text", "key": "scan_time", "label": "AOI時間"},
    {"type": "text", "key": "line_id", "label": "Line"},
    {"type": "text", "key": "model_no", "label": "Model"},
    {"type": "text", "key": "chip_id", "label": "Chip"},
    {"type": "text", "key": "defect_code", "label": "Defect Code"},
    {"type": "text", "key": "retype_def_code", "label": "Retype"},
    {"type": "text", "key": "defect_size", "label": "Size"},
    {"type": "text", "key": "defect_size_raw", "label": "Raw Size"},
    {"type": "text", "key": "ori_x", "label": "ORI X"},
    {"type": "text", "key": "ori_y", "label": "ORI Y"},
    {"type": "text", "key": "trans_x", "label": "Trans X"},
    {"type": "text", "key": "trans_y", "label": "Trans Y"},
    {"type": "text", "key": "image_name", "label": "Image"},
    {"type": "text", "key": "source_group_key", "label": "Group Key"},
]


# -----------------------------------------------------------------------------
# CF source 子表格欄位
# AOI feature 舊值：OC / PS
# Inspection feature 新值：CF_OC / CF_PS
# -----------------------------------------------------------------------------

DEFECT_DETAIL_COLUMNS_SUB_CF_OC = [
    {"type": "text", "key": "source_op_id", "label": "站點"},
    {"type": "text", "key": "sheet_id", "label": "SheetID"},
    {"type": "text", "key": "chip_id", "label": "Chip"},
    {"type": "text", "key": "model_no", "label": "Model"},
    {"type": "text", "key": "scan_time", "label": "AOI時間"},
    {"type": "text", "key": "defect_no", "label": "Defect No"},
    {"type": "text", "key": "defect_code", "label": "Defect Code"},
    {"type": "text", "key": "defect_size", "label": "Size"},
    {"type": "text", "key": "defect_size_raw", "label": "Raw Size"},
    {"type": "text", "key": "ori_x", "label": "ORI X"},
    {"type": "text", "key": "ori_y", "label": "ORI Y"},
    {"type": "text", "key": "trans_x", "label": "Trans X"},
    {"type": "text", "key": "trans_y", "label": "Trans Y"},
    {"type": "text", "key": "image_name", "label": "Image"},
    {"type": "text", "key": "source_group_key", "label": "Group Key"},
]

DEFECT_DETAIL_COLUMNS_SUB_CF_PS = DEFECT_DETAIL_COLUMNS_SUB_CF_OC


# -----------------------------------------------------------------------------
# ARRAY MOR source 子表格欄位
# AOI feature 舊值：PX1=MOR
# Inspection feature 新值：ARRAY_MOR
# -----------------------------------------------------------------------------

DEFECT_DETAIL_COLUMNS_SUB_TFT_MOR = [
    {"type": "text", "key": "source_op_id", "label": "站點"},
    {"type": "text", "key": "sheet_id", "label": "SheetID"},
    {"type": "text", "key": "lot_id", "label": "Lot"},
    {"type": "text", "key": "scan_time", "label": "Scan Time"},
    {"type": "text", "key": "chip_id", "label": "Chip"},
    {"type": "text", "key": "signal_no", "label": "Signal"},
    {"type": "text", "key": "gate_no", "label": "Gate"},
    {"type": "text", "key": "defect_code", "label": "Defect Code"},
    {"type": "text", "key": "defect_size", "label": "Size"},
    {"type": "text", "key": "defect_size_raw", "label": "Raw Size"},
    {"type": "text", "key": "ori_x", "label": "ORI X"},
    {"type": "text", "key": "ori_y", "label": "ORI Y"},
    {"type": "text", "key": "trans_x", "label": "Trans X"},
    {"type": "text", "key": "trans_y", "label": "Trans Y"},
    {"type": "text", "key": "image_name", "label": "Image"},
    {"type": "text", "key": "source_group_key", "label": "Group Key"},
]


# -----------------------------------------------------------------------------
# ARRAY TAR / TOS source 子表格欄位
# AOI feature 舊值：TAR / TOS
# Inspection feature 新值：ARRAY_TAR / ARRAY_TOS
# -----------------------------------------------------------------------------

DEFECT_DETAIL_COLUMNS_SUB_TFT_TAR = [
    {"type": "text", "key": "source_op_id", "label": "站點"},
    {"type": "text", "key": "sheet_id", "label": "SheetID"},
    {"type": "text", "key": "lot_id", "label": "Lot"},
    {"type": "text", "key": "chip_id", "label": "Chip"},
    {"type": "text", "key": "signal_no", "label": "Signal"},
    {"type": "text", "key": "gate_no", "label": "Gate"},
    {"type": "text", "key": "defect_code", "label": "Defect Code"},
    {"type": "text", "key": "defect_size", "label": "Size"},
    {"type": "text", "key": "defect_size_raw", "label": "Raw Size"},
    {"type": "text", "key": "ori_x", "label": "ORI X"},
    {"type": "text", "key": "ori_y", "label": "ORI Y"},
    {"type": "text", "key": "trans_x", "label": "Trans X"},
    {"type": "text", "key": "trans_y", "label": "Trans Y"},
    {"type": "text", "key": "image_name", "label": "Image"},
    {"type": "text", "key": "source_group_key", "label": "Group Key"},
]

DEFECT_DETAIL_COLUMNS_SUB_TFT_TOS = DEFECT_DETAIL_COLUMNS_SUB_TFT_TAR


# -----------------------------------------------------------------------------
# 子表格 mapping
# -----------------------------------------------------------------------------

DEFECT_DETAIL_SUB_COLUMNS_AOI = {
    "cell_aoi": DEFECT_DETAIL_COLUMNS_SUB_CELL_AOI,
    "source": {
        "OC": DEFECT_DETAIL_COLUMNS_SUB_CF_OC,
        "PS": DEFECT_DETAIL_COLUMNS_SUB_CF_PS,
        "PX1=MOR": DEFECT_DETAIL_COLUMNS_SUB_TFT_MOR,
        "TAR": DEFECT_DETAIL_COLUMNS_SUB_TFT_TAR,
        "TOS": DEFECT_DETAIL_COLUMNS_SUB_TFT_TOS,
    },
}

DEFECT_DETAIL_SUB_COLUMNS_INSPECTION = {
    "inspection": DEFECT_DETAIL_COLUMNS_SUB_INSPECTION,
    "cell_aoi": DEFECT_DETAIL_COLUMNS_SUB_INSPECTION,
    "source": {
        "AOI_BPI": DEFECT_DETAIL_COLUMNS_SUB_AOI_SOURCE,
        "AOI_API": DEFECT_DETAIL_COLUMNS_SUB_AOI_SOURCE,

        "CF_OC": DEFECT_DETAIL_COLUMNS_SUB_CF_OC,
        "CF_PS": DEFECT_DETAIL_COLUMNS_SUB_CF_PS,

        "ARRAY_MOR": DEFECT_DETAIL_COLUMNS_SUB_TFT_MOR,
        "ARRAY_TAR": DEFECT_DETAIL_COLUMNS_SUB_TFT_TAR,
        "ARRAY_TOS": DEFECT_DETAIL_COLUMNS_SUB_TFT_TOS,

        # 相容舊值
        "OC": DEFECT_DETAIL_COLUMNS_SUB_CF_OC,
        "PS": DEFECT_DETAIL_COLUMNS_SUB_CF_PS,
        "PX1=MOR": DEFECT_DETAIL_COLUMNS_SUB_TFT_MOR,
        "TAR": DEFECT_DETAIL_COLUMNS_SUB_TFT_TAR,
        "TOS": DEFECT_DETAIL_COLUMNS_SUB_TFT_TOS,
    },
}


# -----------------------------------------------------------------------------
# 主表欄位 by side
# -----------------------------------------------------------------------------

DEFECT_TABLE_COLUMNS_BY_FEATURE_SIDE = {
    AOI_FEATURE: {
        "TFT": DEFECT_DETAIL_MAIN_COLUMNS_TFT,
        "CF": DEFECT_DETAIL_MAIN_COLUMNS_CF,
    },
    INSPECTION_FEATURE: {
        "TFT": DEFECT_DETAIL_MAIN_COLUMNS_INSPECTION_TFT,
        "CF": DEFECT_DETAIL_MAIN_COLUMNS_INSPECTION_CF,
    },
    AOI_INSPEC_FEATURE: {
        "TFT": DEFECT_DETAIL_MAIN_COLUMNS_TFT,
        "CF": DEFECT_DETAIL_MAIN_COLUMNS_CF,
    },
}


# =============================================================================
# API field mapping
# =============================================================================

API_AOI_SUMMARY_QUERY_FIELDS = [
    "test_time",
    "line_id",
    "cassette_id",
    "sheet_id_chip_id",
    "model_no",
    "abbr_cat",
    "recipe_id",
    "aoi",
    "total_defect_qty",
    "pi_time",
    "pi_type",
    "source_scan_time",
    "source_op_id",
    "source_defect_cnt",
    "same_point_offset",
    "same_point_defect_cnt",
    "same_point_rate",
    "match_status",
    "match_status_detail",
    "comment",
    "action",
    "modify_time",
    "editor",
]

API_INSPECTION_SUMMARY_QUERY_FIELDS = [
    "test_time",
    "line_id",
    "sheet_id_chip_id",
    "abbr_cat",
    "model_no",
    "total_defect_qty",
    "source_op_id",
    "source_scan_time",
    "source_defect_cnt",
    "same_point_offset",
    "same_point_defect_cnt",
    "same_point_rate",
    "match_status",
    "match_status_detail",
    "comment",
    "action",
    "modify_time",
    "editor",
]

SAME_POINT_DETAIL_QUERY_FIELDS = [
    "sheet_id",
    "scan_time",
    "model_no",
    "abbr_cat",
    "process",
    "recipe_id",
    "cassette_id",
    "cell_aoi",
    "cell_line_id",
    "pi_time",
    "cell_op",
    "cell_defect_cnt",
    "source_op_id",
    "source_scan_time",
    "source_defect_cnt",
    "same_point_offset",
    "same_point_defect_cnt",
    "same_point_rate",
    "point_detail",
    "match_status",
    "match_status_detail",
]

INSPECTION_SAME_POINT_DETAIL_QUERY_FIELDS = [
    "sheet_id",
    "glass_type",
    "scan_time",
    "line_id",
    "model_no",
    "total_defect_qty",
    "source_op_id",
    "source_scan_time",
    "source_defect_cnt",
    "same_point_offset",
    "same_point_defect_cnt",
    "same_point_rate",
    "point_detail",
    "match_status",
    "match_status_detail",
]

DETAIL_KEY_MAPPING = {
    "sheet_id_chip_id": "sheet_id",
    "test_time": "scan_time",
    "pi_type": "cell_op",
    "source_op_id": "source_op_id",
}

INSPECTION_DETAIL_KEY_MAPPING = {
    "sheet_id_chip_id": "sheet_id",
    "test_time": "scan_time",
    "source_op_id": "source_op_id",
}


# =============================================================================
# Filter config
# =============================================================================

MAIN_FILTER_FIELDS = [
    {
        "key": "test_time",
        "label": "CELL量測時間",
        "type": "datetime_range",
        "db_field": "test_time",
    },
    {
        "key": "line_id",
        "label": "Line",
        "type": "multi_select",
        "db_field": "line_id",
        "options": CELL_AOI_TO_ARRAY_LINE_OPTIONS,
    },
    {
        "key": "aoi",
        "label": "CELL AOI",
        "type": "multi_select",
        "db_field": "aoi",
    },
    {
        "key": "abbr_cat",
        "label": "ABBR",
        "type": "multi_select",
        "db_field": "abbr_cat",
        "options": CELL_AOI_TO_ARRAY_SHEET_TYPES,
    },
    {
        "key": "pi_type",
        "label": "PI Type",
        "type": "multi_select",
        "db_field": "pi_type",
        "options": CELL_AOI_TO_ARRAY_PI_TYPES,
    },
    {
        "key": "source_op_id",
        "label": "站點",
        "type": "multi_select",
        "db_field": "source_op_id",
        "options": CELL_AOI_TO_ARRAY_SOURCE_OP_OPTIONS,
    },
    {
        "key": "match_status",
        "label": "狀態",
        "type": "multi_select",
        "db_field": "match_status",
        "options": CELL_AOI_TO_ARRAY_MATCH_STATUS_OPTIONS,
    },
    {
        "key": "sheet_id_chip_id",
        "label": "SheetID",
        "type": "text",
        "db_field": "sheet_id_chip_id",
    },
    {
        "key": "model_no",
        "label": "Model",
        "type": "multi_select",
        "db_field": "model_no",
    },
    {
        "key": "recipe_id",
        "label": "Recipe",
        "type": "multi_select",
        "db_field": "recipe_id",
    },
]

INSPECTION_FILTER_FIELDS = [
    {
        "key": "test_time",
        "label": "Inspection時間",
        "type": "datetime_range",
        "db_field": "test_time",
    },
    {
        "key": "line_id",
        "label": "Tool",
        "type": "multi_select",
        "db_field": "line_id",
        "options": INSPECTION_LINE_OPTIONS,
    },
    {
        "key": "abbr_cat",
        "label": "TYPE",
        "type": "multi_select",
        "db_field": "abbr_cat",
        "options": CELL_AOI_TO_ARRAY_SHEET_TYPES,
    },
    {
        "key": "source_op_id",
        "label": "比對站點",
        "type": "multi_select",
        "db_field": "source_op_id",
        "options": INSPECTION_SOURCE_OP_OPTIONS,
    },
    {
        "key": "match_status",
        "label": "狀態",
        "type": "multi_select",
        "db_field": "match_status",
        "options": INSPECTION_MATCH_STATUS_OPTIONS,
    },
    {
        "key": "sheet_id_chip_id",
        "label": "SheetID",
        "type": "text",
        "db_field": "sheet_id_chip_id",
    },
    {
        "key": "model_no",
        "label": "Model",
        "type": "multi_select",
        "db_field": "model_no",
    },
]


# =============================================================================
# Editable fields
# =============================================================================

API_AOI_EDITABLE_FIELDS = [
    {
        "key": "comment",
        "label": "備註",
        "type": "textarea",
        "db_field": "comment",
    },
    {
        "key": "action",
        "label": "Action",
        "type": "text",
        "db_field": "action",
    },
    {
        "key": "editor",
        "label": "Editor",
        "type": "text",
        "db_field": "editor",
    },
]

API_AOI_UPDATE_KEYS = [
    "sheet_id_chip_id",
    "pi_type",
    "test_time",
    "source_op_id",
]

API_INSPECTION_UPDATE_KEYS = [
    "sheet_id_chip_id",
    "abbr_cat",
    "test_time",
    "source_op_id",
]


# =============================================================================
# Feature config
# =============================================================================

CELL_AOI_TO_ARRAY_FEATURES: Dict[str, Dict[str, Any]] = {
    AOI_FEATURE: {
        "label": "AOI來料檢",
        "title": "AOI來料檢",
        "chartTitle": "AOI來料檢",
        "type": "compare",

        "summaryCards": CELL_AOI_TO_ARRAY_SUMMARY_CARDS,

        "source_db": SOURCE_DB_NAME,
        "cell_db": CELL_DB_NAME,
        "source_table": API_AOI_SUMMARY_BASE,
        "detail_table": SAME_POINT_DETAIL_BASE,
        "glass_summary_table": GLASS_SUMMARY_BASE,

        "toolOptions": CELL_AOI_TO_ARRAY_LINE_OPTIONS,

        "tableColumns": AOI_TABLE_COLUMNS,
        "sheetDetailFields": COMMON_AOI_SHEET_DETAIL_FIELDS,
        "chartList": CELL_AOI_TO_ARRAY_CHARTS[AOI_FEATURE],

        "sheetDetailFieldsBySide": AOI_SHEET_DETAIL_FIELDS_BY_SIDE,
        "defectTableColumnsBySide": DEFECT_TABLE_COLUMNS_BY_FEATURE_SIDE[AOI_FEATURE],
        "defectDetailSubColumns": DEFECT_DETAIL_SUB_COLUMNS_AOI,
        "sheetSideConfig": SHEET_SIDE_CONFIG,

        "systemField": "aoi",
        "systemLabel": "AOI",

        "queryFields": API_AOI_SUMMARY_QUERY_FIELDS,
        "detailQueryFields": SAME_POINT_DETAIL_QUERY_FIELDS,
        "detailKeyMapping": DETAIL_KEY_MAPPING,
        "filterFields": MAIN_FILTER_FIELDS,
        "editableFields": API_AOI_EDITABLE_FIELDS,
        "updateKeys": API_AOI_UPDATE_KEYS,

        "sourceOpOptions": CELL_AOI_TO_ARRAY_SOURCE_OP_OPTIONS,
        "cfSourceOpOptions": CELL_AOI_TO_ARRAY_CF_SOURCE_OP_OPTIONS,
        "arraySourceOpOptions": CELL_AOI_TO_ARRAY_ARRAY_SOURCE_OP_OPTIONS,
        "matchStatusOptions": CELL_AOI_TO_ARRAY_MATCH_STATUS_OPTIONS,
    },

    INSPECTION_FEATURE: {
        "label": "Inspection來料檢",
        "title": "Inspection來料檢",
        "chartTitle": "Inspection來料檢",
        "type": "compare",

        "summaryCards": INSPECTION_SUMMARY_CARDS,

        "source_db": INSPECTION_SOURCE_DB_NAME,
        "cell_db": CELL_DB_NAME,
        "source_table": API_INSPECTION_SUMMARY_BASE,
        "detail_table": INSPECTION_SAME_POINT_DETAIL_BASE,
        "glass_summary_table": INSPECTION_GLASS_SUMMARY_BASE,

        "toolOptions": INSPECTION_LINE_OPTIONS,

        "tableColumns": INSPECTION_TABLE_COLUMNS,
        "sheetDetailFields": COMMON_INSPECTION_SHEET_DETAIL_FIELDS,
        "chartList": CELL_AOI_TO_ARRAY_CHARTS[INSPECTION_FEATURE],

        "sheetDetailFieldsBySide": INSPECTION_SHEET_DETAIL_FIELDS_BY_SIDE,
        "defectTableColumnsBySide": DEFECT_TABLE_COLUMNS_BY_FEATURE_SIDE[INSPECTION_FEATURE],
        "defectDetailSubColumns": DEFECT_DETAIL_SUB_COLUMNS_INSPECTION,
        "sheetSideConfig": INSPECTION_SHEET_SIDE_CONFIG,

        "systemField": "line_id",
        "systemLabel": "Inspection",

        "queryFields": API_INSPECTION_SUMMARY_QUERY_FIELDS,
        "detailQueryFields": INSPECTION_SAME_POINT_DETAIL_QUERY_FIELDS,
        "detailKeyMapping": INSPECTION_DETAIL_KEY_MAPPING,
        "filterFields": INSPECTION_FILTER_FIELDS,
        "editableFields": API_AOI_EDITABLE_FIELDS,
        "updateKeys": API_INSPECTION_UPDATE_KEYS,

        "sourceOpOptions": INSPECTION_SOURCE_OP_OPTIONS,
        "cfSourceOpOptions": INSPECTION_CF_SOURCE_OP_OPTIONS,
        "arraySourceOpOptions": INSPECTION_ARRAY_SOURCE_OP_OPTIONS,
        "matchStatusOptions": INSPECTION_MATCH_STATUS_OPTIONS,
    },

}




# =============================================================================
# Helper functions
# =============================================================================

def default_date_range(days: int = 3) -> Dict[str, str]:
    end = date.today()
    start = end - timedelta(days=days - 1)
    return {
        "startDate": start.strftime("%Y-%m-%d"),
        "endDate": end.strftime("%Y-%m-%d"),
    }


def get_feature_config(feature_key: str) -> Dict[str, Any]:
    return CELL_AOI_TO_ARRAY_FEATURES.get(
        feature_key,
        CELL_AOI_TO_ARRAY_FEATURES[AOI_FEATURE],
    )


def get_feature_ui_config(feature_key: str) -> Dict[str, Any]:
    cfg = get_feature_config(feature_key)

    return {
        "key": feature_key,
        "label": cfg["label"],
        "type": cfg["type"],
        "title": cfg["title"],
        "chartTitle": cfg["chartTitle"],

        "toolOptions": cfg["toolOptions"],
        "tableColumns": cfg["tableColumns"],
        "sheetDetailFields": cfg["sheetDetailFields"],
        "sheetDetailFieldsBySide": cfg["sheetDetailFieldsBySide"],
        "defectTableColumnsBySide": cfg["defectTableColumnsBySide"],
        "defectDetailSubColumns": cfg.get("defectDetailSubColumns", {}),
        "sheetSideConfig": cfg["sheetSideConfig"],
        "chartList": cfg["chartList"],
        "summaryCards": cfg.get("summaryCards", CELL_AOI_TO_ARRAY_SUMMARY_CARDS),

        "axis": CELL_AOI_TO_ARRAY_AXIS,
        "systemField": cfg["systemField"],
        "systemLabel": cfg["systemLabel"],

        "sheetTypes": CELL_AOI_TO_ARRAY_SHEET_TYPES,
        "piTypes": CELL_AOI_TO_ARRAY_PI_TYPES,
        "lineOptions": cfg.get("toolOptions", CELL_AOI_TO_ARRAY_LINE_OPTIONS),

        "sourceOpOptions": cfg.get("sourceOpOptions", CELL_AOI_TO_ARRAY_SOURCE_OP_OPTIONS),
        "cfSourceOpOptions": cfg.get("cfSourceOpOptions", CELL_AOI_TO_ARRAY_CF_SOURCE_OP_OPTIONS),
        "arraySourceOpOptions": cfg.get("arraySourceOpOptions", CELL_AOI_TO_ARRAY_ARRAY_SOURCE_OP_OPTIONS),

        "defectSizes": CELL_AOI_TO_ARRAY_DEFECT_SIZES,
        "matchStatusOptions": cfg.get("matchStatusOptions", CELL_AOI_TO_ARRAY_MATCH_STATUS_OPTIONS),

        "filterFields": cfg["filterFields"],
        "editableFields": cfg["editableFields"],
        "updateKeys": cfg["updateKeys"],
    }


def get_feature_db_config(feature_key: str) -> Dict[str, Any]:
    cfg = get_feature_config(feature_key)

    return {
        "source_db": cfg["source_db"],
        "cell_db": cfg["cell_db"],
        "source_table": cfg["source_table"],
        "detail_table": cfg["detail_table"],
        "glass_summary_table": cfg["glass_summary_table"],
        "queryFields": cfg["queryFields"],
        "detailQueryFields": cfg["detailQueryFields"],
        "detailKeyMapping": cfg["detailKeyMapping"],
        "updateKeys": cfg["updateKeys"],
    }


def get_source_op_options_by_side(abbr_cat: str) -> List[str]:
    """
    舊版相容：預設回傳 AOI 來料檢的 source_op_id options。
    """
    side = str(abbr_cat or "").strip().upper()

    if side == "CF":
        return CELL_AOI_TO_ARRAY_CF_SOURCE_OP_OPTIONS

    if side == "TFT":
        return CELL_AOI_TO_ARRAY_ARRAY_SOURCE_OP_OPTIONS

    return CELL_AOI_TO_ARRAY_SOURCE_OP_OPTIONS


def get_source_op_options_by_feature_side(feature_key: str, abbr_cat: str) -> List[str]:
    """
    新版使用：依 feature + side 回傳 source_op_id options。
    """
    feature = str(feature_key or "").strip()
    side = str(abbr_cat or "").strip().upper()

    if feature == INSPECTION_FEATURE:
        if side == "CF":
            return INSPECTION_CF_SOURCE_OP_OPTIONS
        if side == "TFT":
            return INSPECTION_ARRAY_SOURCE_OP_OPTIONS
        return INSPECTION_SOURCE_OP_OPTIONS

    if side == "CF":
        return CELL_AOI_TO_ARRAY_CF_SOURCE_OP_OPTIONS

    if side == "TFT":
        return CELL_AOI_TO_ARRAY_ARRAY_SOURCE_OP_OPTIONS

    return CELL_AOI_TO_ARRAY_SOURCE_OP_OPTIONS


def yyyymm_from_date_text(date_text: str) -> str:
    if not date_text:
        return datetime.now().strftime("%Y%m")

    s = str(date_text).strip()
    if len(s) >= 7:
        return s[:7].replace("-", "")

    return datetime.now().strftime("%Y%m")


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")