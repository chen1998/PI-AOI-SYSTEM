from __future__ import annotations

import logging
from datetime import datetime, date
from typing import Dict, Any, Optional, List

from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from models.sql_db_connect import MySQLConnet

router = APIRouter(tags=["duty_cell_piaoi_aoi_capa"])

# =========================================================
# Logging
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(funcName)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("AOI_CAPA_SAVE")


# =========================================================
# DB / Const
# =========================================================
DB_NAME = "piaoi_capa"
VALID_AOI = {"aoi100", "aoi200", "aoi300"}

dbhandler = MySQLConnet(DB_NAME)


# =========================================================
# Helpers
# =========================================================
def parse_run_day(run_day_str: str) -> date:
    return datetime.strptime(str(run_day_str).strip(), "%Y-%m-%d").date()


def month_str_from_day(run_day_date: date) -> str:
    return run_day_date.strftime("%Y%m")


def summary_table_name(aoi: str, yyyymm: str) -> str:
    return f"{aoi}_{yyyymm}_capa_summary"


def hourly_table_name(aoi: str, yyyymm: str) -> str:
    return f"{aoi}_{yyyymm}_capa_hourly_rawdata"


def normalize_aoi(aoi: Any) -> str:
    s = str(aoi or "").strip().lower()
    if s not in VALID_AOI:
        raise HTTPException(status_code=400, detail=f"未知 AOI: {aoi}")
    return s


def safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip()
    if s == "":
        return None
    try:
        return float(s)
    except Exception:
        raise HTTPException(status_code=400, detail=f"數值格式錯誤: {v}")


def safe_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v)


def ensure_table_exists(table_name: str):
    if not dbhandler.table_exists(table_name):
        raise HTTPException(status_code=404, detail=f"資料表不存在: {DB_NAME}.{table_name}")


# =========================================================
# Comment / Action / Editor / ModifyTime
# =========================================================
def update_day_text_fields(
    aoi: str,
    run_day_date: date,
    comment: Optional[str] = None,
    action: Optional[str] = None,
    editor: Optional[str] = None,
) -> Dict[str, Any]:
    """
    更新單一 AOI + 單一天 summary 表中的文字欄位：
    - comment
    - action
    - editor
    - modify_time
    """
    yyyymm = month_str_from_day(run_day_date)
    table_name = summary_table_name(aoi, yyyymm)
    ensure_table_exists(table_name)

    modify_time = datetime.now()

    set_parts = ["modify_time = :modify_time"]
    params: Dict[str, Any] = {
        "run_day": run_day_date,
        "modify_time": modify_time,
    }

    if comment is not None:
        set_parts.append("comment = :comment")
        params["comment"] = comment

    if action is not None:
        set_parts.append("action = :action")
        params["action"] = action

    if editor is not None:
        set_parts.append("editor = :editor")
        params["editor"] = editor

    if len(set_parts) == 1:
        logger.info("[update_day_text_fields] 無欄位需更新，略過")
        return {"affected": 0, "table": table_name}

    sql = text(
        f"""
        UPDATE `{table_name}`
        SET {", ".join(set_parts)}
        WHERE run_day = :run_day
        """
    )

    try:
        with dbhandler.engine.begin() as conn:
            res = conn.execute(sql, params)
            affected = res.rowcount or 0

        logger.info(
            "[update_day_text_fields] table=%s, aoi=%s, run_day=%s, affected=%d",
            table_name, aoi, run_day_date, affected
        )

        return {
            "table": table_name,
            "aoi": aoi,
            "run_day": str(run_day_date),
            "affected": affected,
            "modify_time": modify_time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    except SQLAlchemyError as e:
        logger.exception("[update_day_text_fields] SQL error")
        raise HTTPException(status_code=500, detail=f"更新 summary 文字欄位失敗: {e}")


# =========================================================
# Target / Spec recalc
# =========================================================
def recalc_hourly_for_day(
    aoi: str,
    run_day_date: date,
    new_target_count: float,
) -> Dict[str, Any]:
    """
    重算 hourly:
      real_hour_capa = hour / target_count
      real_cumu_capa = cumu / target_count
    """
    yyyymm = month_str_from_day(run_day_date)
    table_hourly = hourly_table_name(aoi, yyyymm)
    ensure_table_exists(table_hourly)

    if new_target_count <= 0:
        raise HTTPException(status_code=400, detail=f"target_count 必須大於 0，目前為 {new_target_count}")

    sql = text(
        f"""
        UPDATE `{table_hourly}`
        SET
            real_hour_capa = (`hour` / :target_count),
            real_cumu_capa = (`cumu` / :target_count)
        WHERE run_day = :run_day
        """
    )

    try:
        with dbhandler.engine.begin() as conn:
            res = conn.execute(sql, {
                "target_count": new_target_count,
                "run_day": run_day_date,
            })
            affected = res.rowcount or 0

        logger.info(
            "[recalc_hourly_for_day] table=%s, aoi=%s, run_day=%s, target_count=%s, affected=%d",
            table_hourly, aoi, run_day_date, new_target_count, affected
        )

        return {
            "table": table_hourly,
            "affected": affected,
        }

    except SQLAlchemyError as e:
        logger.exception("[recalc_hourly_for_day] SQL error")
        raise HTTPException(status_code=500, detail=f"更新 hourly 失敗: {e}")


def recalc_summary_for_day(
    aoi: str,
    run_day_date: date,
    new_target_count: float,
    new_spec: Optional[float],
    editor: Optional[str] = None,
) -> Dict[str, Any]:
    """
    重算 summary:
      target_count = new_target_count
      spec = new_spec
      real_day_capa = total_glass / new_target_count
      editor = editor
      modify_time = now
    """
    yyyymm = month_str_from_day(run_day_date)
    table_summary = summary_table_name(aoi, yyyymm)
    ensure_table_exists(table_summary)

    if new_target_count <= 0:
        raise HTTPException(status_code=400, detail=f"target_count 必須大於 0，目前為 {new_target_count}")

    modify_time = datetime.now()
    use_editor = safe_str(editor)

    sql = text(
        f"""
        UPDATE `{table_summary}`
        SET
            target_count = :target_count,
            spec = :spec,
            real_day_capa = CASE
                WHEN :target_count > 0 THEN (`total_glass` / :target_count)
                ELSE 0
            END,
            editor = :editor,
            modify_time = :modify_time
        WHERE run_day = :run_day
        """
    )

    try:
        with dbhandler.engine.begin() as conn:
            res = conn.execute(sql, {
                "target_count": new_target_count,
                "spec": new_spec,
                "editor": use_editor,
                "modify_time": modify_time,
                "run_day": run_day_date,
            })
            affected = res.rowcount or 0

        logger.info(
            "[recalc_summary_for_day] table=%s, aoi=%s, run_day=%s, target_count=%s, spec=%s, affected=%d",
            table_summary, aoi, run_day_date, new_target_count, new_spec, affected
        )

        return {
            "table": table_summary,
            "affected": affected,
            "modify_time": modify_time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    except SQLAlchemyError as e:
        logger.exception("[recalc_summary_for_day] SQL error")
        raise HTTPException(status_code=500, detail=f"更新 summary 失敗: {e}")


def recalc_target_spec_for_day(
    aoi: str,
    run_day_date: date,
    new_target_count: float,
    new_spec: Optional[float],
    editor: Optional[str] = None,
) -> Dict[str, Any]:
    """
    同步重算 hourly + summary
    """
    hourly_ret = recalc_hourly_for_day(
        aoi=aoi,
        run_day_date=run_day_date,
        new_target_count=new_target_count,
    )

    summary_ret = recalc_summary_for_day(
        aoi=aoi,
        run_day_date=run_day_date,
        new_target_count=new_target_count,
        new_spec=new_spec,
        editor=editor,
    )

    return {
        "aoi": aoi,
        "run_day": str(run_day_date),
        "hourly": hourly_ret,
        "summary": summary_ret,
    }


# =========================================================
# Main API
# =========================================================
@router.post("/api/save_config")
async def save_capa_config(payload: Dict[str, Any]):
    """
    支援兩類 payload:

    1) 更新 Day Info 文字欄位
    {
      "aoi": "aoi200",
      "run_day": "2026-04-20",
      "comment": "...",   # optional
      "action": "...",    # optional
      "editor": "ruby"    # optional
    }

    2) 更新 Target / Spec 並重算
    {
      "run_day": "2026-04-20",
      "editor": "ruby",   # optional
      "target_table": [
        {"aoi": "aoi100", "target_glass": 168, "spec": 90},
        {"aoi": "aoi200", "target_glass": 238, "spec": 90},
        {"aoi": "aoi300", "target_glass": 203, "spec": 90}
      ]
    }
    """
    try:
        logger.info("[save_capa_config] payload=%s", payload)

        run_day_str = payload.get("run_day")
        if not run_day_str:
            raise HTTPException(status_code=400, detail="缺少 run_day")

        run_day_date = parse_run_day(run_day_str)

        result: Dict[str, Any] = {
            "ok": True,
            "run_day": str(run_day_date),
            "mode": None,
            "results": [],
        }

        # =====================================================
        # Mode 1: 單日單 AOI 文字更新
        # =====================================================
        if "aoi" in payload:
            aoi = normalize_aoi(payload.get("aoi"))
            comment = payload["comment"] if "comment" in payload else None
            action = payload["action"] if "action" in payload else None
            editor = payload["editor"] if "editor" in payload else None

            if comment is None and action is None and editor is None:
                raise HTTPException(
                    status_code=400,
                    detail="更新 Day Info 時，comment/action/editor 至少要提供一個"
                )

            ret = update_day_text_fields(
                aoi=aoi,
                run_day_date=run_day_date,
                comment=comment,
                action=action,
                editor=editor,
            )

            result["mode"] = "day_text_update"
            result["results"].append(ret)
            return result

        # =====================================================
        # Mode 2: Target / Spec 批次更新
        # =====================================================
        target_table = payload.get("target_table")
        if target_table:
            if not isinstance(target_table, list):
                raise HTTPException(status_code=400, detail="target_table 必須是 list")

            editor = payload.get("editor", "")

            for entry in target_table:
                aoi = normalize_aoi(entry.get("aoi"))
                new_target_count = safe_float(entry.get("target_glass"))
                new_spec = safe_float(entry.get("spec"))

                if new_target_count is None:
                    raise HTTPException(
                        status_code=400,
                        detail=f"{aoi} 缺少 target_glass"
                    )

                ret = recalc_target_spec_for_day(
                    aoi=aoi,
                    run_day_date=run_day_date,
                    new_target_count=new_target_count,
                    new_spec=new_spec,
                    editor=editor,
                )
                result["results"].append(ret)

            result["mode"] = "target_spec_recalc"
            return result

        raise HTTPException(
            status_code=400,
            detail="payload 不符合格式，需包含 aoi 或 target_table"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[save_capa_config] unexpected error")
        raise HTTPException(status_code=500, detail=f"save_config error: {e}")