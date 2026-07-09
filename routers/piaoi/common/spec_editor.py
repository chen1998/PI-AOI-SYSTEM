# routers/common/spec_editor.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Dict, Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from models.sql_db_connect import MySQLConnet


router = APIRouter(tags=["duty_cell_piaoi_common_spec_edit"])


# =============================================================================
# Utils
# =============================================================================
def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clean_none_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in (d or {}).items() if v is not None}


def _clean_empty_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k, v in (d or {}).items():
        if v is None:
            continue
        if isinstance(v, str) and v.strip() == "":
            continue
        out[k] = v
    return out


# =============================================================================
# System Resolver
# =============================================================================
def _resolve_system_config(system: str) -> Dict[str, Any]:
    """
    回傳：
      {
        "table_name": str,
        "dbname": str,
        "dbhandler": MySQLConnet,
        "editor_col": "Editor" | "editor",
        "mode": system,
      }
    """

    # ------------------------------------------------------------
    # AOI Density
    # ------------------------------------------------------------
    if system == "density":
        from models.piaoi.density.cim_density_job import Config as DensityJobConfig
        from models.piaoi.density.API_Config import API_Config as DensityApiConfig

        density_cfg = DensityJobConfig()
        api_cfg = DensityApiConfig(density_cfg)

        dbname = density_cfg.out_db
        table_name = api_cfg.default_spec_table_name
        dbhandler = MySQLConnet(dbname)

        return {
            "table_name": table_name,
            "dbname": dbname,
            "dbhandler": dbhandler,
            "editor_col": "Editor",
            "mode": "density",
        }

    # ------------------------------------------------------------
    # Inspection Density
    # ------------------------------------------------------------
    if system == "aoi_inspection_density":
        from models.inspection_density.API_Config import CFG

        dbname = CFG.db_name
        table_name = CFG.default_spec_table_name
        dbhandler = MySQLConnet(dbname)

        return {
            "table_name": table_name,
            "dbname": dbname,
            "dbhandler": dbhandler,
            "editor_col": "Editor",
            "mode": "aoi_inspection_density",
        }

    # ------------------------------------------------------------
    # BPI Density - 新版 API_Config
    # ------------------------------------------------------------
    if system == "bpi_density":
        from models.piaoi.bpi_density.API_Config import API_Config as BPIApiConfig

        api_cfg = BPIApiConfig()

        dbname = api_cfg.bpi_density_db_name
        table_name = api_cfg.bpi_density_default_spec_tbn
        dbhandler = MySQLConnet(dbname)

        return {
            "table_name": table_name,
            "dbname": dbname,
            "dbhandler": dbhandler,
            "editor_col": "Editor",
            "mode": "bpi_density",
        }

    # ------------------------------------------------------------
    # BPI/API Same Point
    # ------------------------------------------------------------
    if system == "bpi_same_point":
        from models.piaoi.bpi_density.API_Config import API_Config as BPIApiConfig

        api_cfg = BPIApiConfig()

        dbname = api_cfg.bpi_same_point_db_name
        table_name = api_cfg.bpi_same_point_default_spec_tbn
        dbhandler = MySQLConnet(dbname)

        return {
            "table_name": table_name,
            "dbname": dbname,
            "dbhandler": dbhandler,
            "editor_col": "editor",
            "mode": "bpi_same_point",
        }

    raise HTTPException(status_code=400, detail=f"Unknown system: {system}")

def _normalize_spec_row_fields(system: str, row: Dict[str, Any]) -> Dict[str, Any]:
    """
    將前端 display label 欄位轉成 DB 真實欄位。
    例如：
      MODEL_ID   -> model
      GLASS_TYPE -> glass_type / glass_side
      SIZE_TYPE  -> defect_size
    """
    row = dict(row or {})

    if system == "bpi_density":
        alias = {
            "MODEL_ID": "model",
            "GLASS_TYPE": "glass_type",
            "SIZE_TYPE": "defect_size",
        }
    elif system == "bpi_same_point":
        alias = {
            "MODEL_ID": "model",
            "GLASS_TYPE": "glass_side",
            "SIZE_TYPE": "defect_size",
        }
    else:
        alias = {
            "MODEL_ID": "model",
            "GLASS_TYPE": "glass_type",
            "SIZE_TYPE": "defect_size",
        }

    for old_key, new_key in alias.items():
        if old_key in row and new_key not in row:
            row[new_key] = row.get(old_key)

    for old_key in alias.keys():
        row.pop(old_key, None)

    return row


def _build_spec_identity(system: str, row: Dict[str, Any]) -> Dict[str, Any]:
    """
    delete 用 identity。
    edit 模式通常前端會傳 changes[].identity，因此不走這裡。
    """
    row = _normalize_spec_row_fields(system, row or {})


    if system == "density":
        return {
            "line_id": row.get("line_id", ""),
            "model": row.get("model", ""),
            "glass_type": row.get("glass_type", ""),
            "adc_def_code": row.get("adc_def_code", ""),
            "defect_size": row.get("defect_size", ""),
        }

    if system == "aoi_inspection_density":
        return {
            "line_id": row.get("line_id", ""),
            "model": row.get("model", ""),
            "glass_type": row.get("glass_type", ""),
            "defect_size": row.get("defect_size", ""),
        }

    if system == "bpi_density":
        return {
            "model": row.get("model", ""),
            "glass_type": row.get("glass_type", ""),
            "defect_size": row.get("defect_size", ""),
        }

    if system == "bpi_same_point":
        return {
            "model": row.get("model", ""),
            "glass_side": row.get("glass_side", ""),
            "defect_size": row.get("defect_size", ""),
        }

    return {}


def _strip_reserved_patch_fields(patch: Dict[str, Any], editor_col: str) -> Dict[str, Any]:
    """
    避免 patch 裡帶到 editor / modify_time / drop 破壞統一欄位更新。
    同時兼容 Editor/editor 大小寫。
    """
    reserved = {"Editor", "editor", "modify_time", "drop"}

    out = {}
    for k, v in (patch or {}).items():
        if k in reserved:
            continue
        out[k] = v

    return out


# =============================================================================
# Payload Models
# =============================================================================
class EditChangeV2(BaseModel):
    rowIndex: int
    identity: Dict[str, Any] = Field(default_factory=dict)
    patch: Dict[str, Any] = Field(default_factory=dict)
    old: Optional[Dict[str, Any]] = None


class SpecEditorPayload(BaseModel):
    mode: Literal["edit", "add", "delete"]
    tabKey: Optional[str] = None

    system: Literal[
        "density",
        "aoi_inspection_density",
        "bpi_density",
        "bpi_same_point",
    ]

    # edit 用
    changes: Optional[List[EditChangeV2]] = None

    # add/delete 用
    row: Optional[Dict[str, Any]] = None

    # metadata
    Editor: Optional[str] = None
    modify_time: Optional[str] = None


# =============================================================================
# Main API
# =============================================================================
@router.post("/spec_editor")
async def spec_editor(payload: SpecEditorPayload):
    """
    通用 spec editor。

    支援：
      - density
      - aoi_inspection_density
      - bpi_density
      - bpi_same_point

    mode:
      - edit:
          使用 changes[].identity + patch 更新。
      - add:
          使用 row append。
      - delete:
          使用 row identity，將 drop='T'。
    """
    print(f"[spec_editor] system={payload.system}, mode={payload.mode}, tabKey={payload.tabKey}")

    sys_cfg = _resolve_system_config(payload.system)

    table_name = sys_cfg["table_name"]
    dbhandler = sys_cfg["dbhandler"]
    editor_col = sys_cfg.get("editor_col", "Editor")

    editor = payload.Editor or "預設"
    modify_time = payload.modify_time or _now_str()

    try:
        # =========================================================
        # edit
        # =========================================================
        if payload.mode == "edit":
            if not payload.changes:
                raise HTTPException(status_code=400, detail="changes is required for edit")

            updated = 0
            skipped = 0

            for ch in payload.changes:
                cond = _clean_empty_dict(_normalize_spec_row_fields(payload.system, ch.identity or {}))
                patch = _clean_none_dict(_normalize_spec_row_fields(payload.system, ch.patch or {}))

                if not cond:
                    skipped += 1
                    continue

                if not patch:
                    skipped += 1
                    continue

                # 只操作未 drop 的資料
                cond.update({"drop": "F"})

                update_dict = _strip_reserved_patch_fields(patch, editor_col)

                update_dict.update({
                    editor_col: editor,
                    "modify_time": modify_time,
                })

                # 只有 editor/modify_time，沒實際欄位更新就略過
                if len(update_dict) <= 2:
                    skipped += 1
                    continue

                print(f"[spec_editor][edit] table={table_name}")
                print(f"[spec_editor][edit] cond={cond}")
                print(f"[spec_editor][edit] update={update_dict}")

                dbhandler.update_rows(table_name, cond, update_dict)
                updated += 1

            return {
                "ok": True,
                "mode": "edit",
                "updated": updated,
                "skipped": skipped,
            }

        # =========================================================
        # add
        # =========================================================
        if payload.mode == "add":
            if not payload.row:
                raise HTTPException(status_code=400, detail="row is required for add")

            row = _normalize_spec_row_fields(payload.system, dict(payload.row))

            row["drop"] = "F"
            row[editor_col] = row.get(editor_col) or row.get("Editor") or row.get("editor") or editor
            row["modify_time"] = row.get("modify_time") or modify_time

            # 避免同時帶 Editor/editor 雙欄位造成目標表欄位不存在錯誤
            if editor_col == "editor":
                row.pop("Editor", None)
            else:
                row.pop("editor", None)

            print(f"[spec_editor][add] table={table_name}")
            print(f"[spec_editor][add] row={row}")

            dbhandler.append_single_row_with_nan(table_name, row)

            return {
                "ok": True,
                "mode": "add",
                "table": table_name,
            }

        # =========================================================
        # delete
        # =========================================================
        if payload.mode == "delete":
            if not payload.row:
                raise HTTPException(status_code=400, detail="row is required for delete")

            cond = _build_spec_identity(payload.system, payload.row)
            cond = _clean_empty_dict(cond)

            if not cond:
                raise HTTPException(status_code=400, detail="delete cond is empty")

            cond["drop"] = "F"

            update_dict = {
                "modify_time": modify_time,
                "drop": "T",
                editor_col: editor,
            }

            print(f"[spec_editor][delete] table={table_name}")
            print(f"[spec_editor][delete] cond={cond}")
            print(f"[spec_editor][delete] update={update_dict}")

            dbhandler.update_rows(table_name, cond, update_dict)

            return {
                "ok": True,
                "mode": "delete",
                "table": table_name,
            }

        raise HTTPException(status_code=400, detail=f"Unknown mode: {payload.mode}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"spec_editor failed: {repr(e)}")