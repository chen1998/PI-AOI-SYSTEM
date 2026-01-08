from __future__ import annotations

import logging
from datetime import datetime, date
from typing import Dict, Any, Optional, List

from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from models.sql_db_connect import MySQLConnet

router = APIRouter()

# ----- Logging -----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(funcName)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("AOI_CAPA_CONFIG")

# ----- DB -----
dbhandler = MySQLConnet("l6a01_project")


# ========================
# 共用小工具
# ========================
def parse_run_day(run_day_str: str) -> date:
    """將 'YYYY-MM-DD' 轉成 date 型態。"""
    return datetime.strptime(run_day_str, "%Y-%m-%d").date()


# ========================
# comment / editor 更新用
# ========================
def update_comment_and_editor_for_day(
    aoi: str,
    run_day_date: date,
    comment: str,
    editor_prefix: str = "",
) -> None:
    """
    將 {aoi}_capa_summary 中「特定 run_day 的所有列」的
    - comment 欄位改為 comment
    - editor 欄位改為 editor_prefix + '\\n' + now

    並印出更新筆數與每筆內容。
    """
    table_name = f"{aoi}_capa_summary"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    editor_full = f"{editor_prefix}\n{now_str}" if editor_prefix else f"\n{now_str}"

    params = {
        "run_day": run_day_date,
        "comment": comment,
        "editor": editor_full,
    }

    update_sql = text(
        f"""
        UPDATE `{table_name}`
        SET comment = :comment,
            editor  = :editor
        WHERE run_day = :run_day
        """
    )

    # (1) UPDATE
    with dbhandler.engine.begin() as conn:
        result = conn.execute(update_sql, params)
        affected = result.rowcount or 0

    logger.info(
        "[save_capa_config] 更新 comment/editor：table=%s, run_day=%s, affected=%d",
        table_name,
        run_day_date,
        affected,
    )

    # (2) SELECT 出來列印
    try:
        select_sql = text(
            f"""
            SELECT *
            FROM `{table_name}`
            WHERE run_day = :run_day
            """
        )
        with dbhandler.engine.connect() as conn:
            rows = conn.execute(select_sql, {"run_day": run_day_date}).fetchall()

        logger.info(
            "[save_capa_config] '%s' run_day=%s 符合的資料共 %d 筆：",
            table_name,
            run_day_date,
            len(rows),
        )
        for r in rows:
            logger.info("  %s", dict(r._mapping))

    except SQLAlchemyError as e:
        logger.error(
            "[save_capa_config] 查詢 '%s' run_day=%s 發生錯誤：%s",
            table_name,
            run_day_date,
            e,
        )


# ========================
# target/spec 更新 + 重算 CAPA
# ========================
def recalc_hourly_and_summary_for_day(
    aoi: str,
    run_day_date: date,
    new_target: Optional[float],
    new_spec: Optional[float],
) -> None:
    """
    對單一 AOI + 一天：
      1) 以 new_target 重算 hourly_tbn:
         - real_hour_capa = hour / new_target
         - real_cumu_capa = cumu / new_target
      2) 以 hourly 的 ALL 最後一筆 cumu 當 total_glass，
         更新 summary_tbn:
         - target_count = new_target
         - spec         = new_spec
         - real_day_capa = total_glass / new_target
         - editor       = 'manual\\n<now>'
    並列印更新筆數 & row 內容。
    """
    table_hourly = f"{aoi}_capa_hourly_rawdata"
    table_summary = f"{aoi}_capa_summary"

    if not new_target or float(new_target) == 0.0:
        logger.warning(
            "[recalc] aoi=%s run_day=%s new_target 無效(%s)，略過重算",
            aoi,
            run_day_date,
            new_target,
        )
        return

    new_target_f = float(new_target)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    editor_full = f" \n{now_str}"

    # ---------- ① 重算 hourly ----------
    try:
        update_hourly_sql = text(
            f"""
            UPDATE `{table_hourly}`
            SET real_hour_capa = ROUND(hour / :target, 2),
                real_cumu_capa = ROUND(cumu / :target, 2)
            WHERE run_day = :run_day
            """
        )
        params_hourly = {
            "target": new_target_f,
            "run_day": run_day_date,
        }

        with dbhandler.engine.begin() as conn:
            result = conn.execute(update_hourly_sql, params_hourly)
            affected_hourly = result.rowcount or 0

        logger.info(
            "[recalc] hourly updated: table=%s, aoi=%s, run_day=%s, target=%.2f, rows=%d",
            table_hourly,
            aoi,
            run_day_date,
            new_target_f,
            affected_hourly,
        )

        # 查詢並列印
        select_hourly_sql = text(
            f"""
            SELECT *
            FROM `{table_hourly}`
            WHERE run_day = :run_day
            ORDER BY hour_int
            """
        )
        with dbhandler.engine.connect() as conn:
            rows_h = conn.execute(
                select_hourly_sql, {"run_day": run_day_date}
            ).fetchall()

        logger.info(
            "[recalc] '%s' run_day=%s 符合 hourly 資料共 %d 筆：",
            table_hourly,
            run_day_date,
            len(rows_h),
        )
        for r in rows_h:
            logger.info("  %s", dict(r._mapping))

    except SQLAlchemyError as e:
        logger.error(
            "[recalc] 更新 hourly '%s' run_day=%s 發生錯誤：%s",
            table_hourly,
            run_day_date,
            e,
        )
        return

    # ---------- ② 計算 total_glass ----------
    try:
        select_cumu_sql = text(
            f"""
            SELECT cumu
            FROM `{table_hourly}`
            WHERE run_day = :run_day AND pi_type = 'ALL'
            ORDER BY hour_int DESC
            LIMIT 1
            """
        )
        with dbhandler.engine.connect() as conn:
            row = conn.execute(
                select_cumu_sql, {"run_day": run_day_date}
            ).fetchone()

        if row:
            total_glass = float(row._mapping["cumu"])
        else:
            total_glass = 0.0

        new_real_day_capa = round(total_glass / new_target_f, 2) if new_target_f else 0.0

        logger.info(
            "[recalc] summary basis: table=%s, aoi=%s, run_day=%s, "
            "total_glass=%.2f, new_target=%.2f, new_real_day_capa=%.2f",
            table_summary,
            aoi,
            run_day_date,
            total_glass,
            new_target_f,
            new_real_day_capa,
        )

    except SQLAlchemyError as e:
        logger.error(
            "[recalc] 讀取 hourly '%s' 計算 total_glass 時發生錯誤：%s",
            table_hourly,
            e,
        )
        return

    # ---------- ③ 更新 summary ----------
    try:
        update_summary_sql = text(
            f"""
            UPDATE `{table_summary}`
            SET target_count = :target,
                spec         = :spec,
                real_day_capa = :real_day_capa,
                editor       = :editor
            WHERE run_day = :run_day
            """
        )
        params_summary = {
            "target": new_target_f,
            "spec": new_spec,
            "real_day_capa": new_real_day_capa,
            "editor": editor_full,
            "run_day": run_day_date,
        }

        with dbhandler.engine.begin() as conn:
            result = conn.execute(update_summary_sql, params_summary)
            affected_summary = result.rowcount or 0

        logger.info(
            "[recalc] summary updated: table=%s, aoi=%s, run_day=%s, rows=%d",
            table_summary,
            aoi,
            run_day_date,
            affected_summary,
        )

        select_summary_sql = text(
            f"""
            SELECT *
            FROM `{table_summary}`
            WHERE run_day = :run_day
            ORDER BY pi_type
            """
        )
        with dbhandler.engine.connect() as conn:
            rows_s = conn.execute(
                select_summary_sql, {"run_day": run_day_date}
            ).fetchall()

        logger.info(
            "[recalc] '%s' run_day=%s 符合 summary 資料共 %d 筆：",
            table_summary,
            run_day_date,
            len(rows_s),
        )
        for r in rows_s:
            logger.info("  %s", dict(r._mapping))

    except SQLAlchemyError as e:
        logger.error(
            "[recalc] 更新 summary '%s' run_day=%s 發生錯誤：%s",
            table_summary,
            run_day_date,
            e,
        )


# ========================
# 主 API：save_capa_config
# ========================
@router.post("/api/save_config")
async def save_capa_config(payload: Dict[str, Any]):
    """
    接收前端 CAPA 設定：

    1) 若 payload 含有 "aoi"（來自 table.js）：
       - 視為「更新單一 AOI 在某一天的 comment（+ editor）」
       - 不考慮 pi_type，該天所有 row 的 comment 都改掉
       - 印出更新筆數與 row 內容

       範例：
       {
         "aoi": "aoi200",
         "run_day": "2025-11-21"
         "comment": "123",        # 要寫入的 comment
         "editor": "userA"        # (可選) editor prefix
       }

    2) 若 payload 含有 "target_table"（來自 right_target.js）：
       - 視為「更新某一天所有 AOI 的 target/spec」
       - 針對每個 AOI：
           a. 以新 target 重算 hourly_tbn 的 real_hour_capa / real_cumu_capa
           b. 以 ALL 最後一筆 cumu 算 total_glass
           c. 更新 summary_tbn 的 target_count / spec / real_day_capa / editor
       - 印出各表更新筆數與 row 內容

       範例：
       {
         "run_day": "2025-11-25",
         "target_table": [
           {"aoi": "aoi100", "target_glass": 100, "spec": 90},
           {"aoi": "aoi200", "target_glass": 238, "spec": 90},
           {"aoi": "aoi300", "target_glass": 203, "spec": 90}
         ]
       }

    回傳：不寫死 key，直接把 payload 原樣回傳。
    """
    try:
        logger.info("[save_capa_config] 收到 payload: %s", payload)

        # ---- 0) 處理 run_day 轉型（若有）----
        run_day_str: Optional[str] = payload.get("run_day")
        run_day_date: Optional[date] = None

        if run_day_str:
            try:
                run_day_date = parse_run_day(run_day_str)
            except ValueError as ve:
                raise HTTPException(
                    status_code=400,
                    detail=f"run_day 格式錯誤（需 YYYY-MM-DD）：{run_day_str}",
                ) from ve

        # ---- 1) 若有 'aoi' key → 更新 comment / editor ----
        if "aoi" in payload:
            if not run_day_date:
                raise HTTPException(status_code=400, detail="缺少 run_day（更新 comment 需要）")

            aoi = str(payload["aoi"])
            comment = str(payload.get("comment", ""))
            editor_prefix = str(payload.get("editor", ""))

            logger.info(
                "[save_capa_config] comment 更新請求：aoi=%s, run_day=%s, comment=%s, editor_prefix=%s",
                aoi,
                run_day_date,
                comment,
                editor_prefix,
            )

            update_comment_and_editor_for_day(
                aoi=aoi,
                run_day_date=run_day_date,
                comment=comment,
                editor_prefix=editor_prefix,
            )

        # ---- 2) 若有 'target_table' key → 重算 CAPA + 更新 summary ----
        target_table: Optional[List[Dict[str, Any]]] = payload.get("target_table")
        if target_table:
            if not run_day_date:
                raise HTTPException(status_code=400, detail="缺少 run_day（更新 target/spec 需要）")

            logger.info(
                "[save_capa_config] target/spec 更新請求：run_day=%s, entries=%d",
                run_day_date,
                len(target_table),
            )

            for entry in target_table:
                aoi = entry.get("aoi")
                if not aoi:
                    logger.warning("[save_capa_config] target_table entry 缺少 aoi，略過: %s", entry)
                    continue

                target_glass = entry.get("target_glass")
                spec = entry.get("spec")

                logger.info(
                    "[save_capa_config] → recalc aoi=%s, run_day=%s, target_glass=%s, spec=%s",
                    aoi,
                    run_day_date,
                    target_glass,
                    spec,
                )

                recalc_hourly_and_summary_for_day(
                    aoi=str(aoi),
                    run_day_date=run_day_date,
                    new_target=target_glass,
                    new_spec=spec,
                )

        # ---- 3) 回傳原 payload ----
        return payload

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[save_capa_config] 發生未預期錯誤")
        raise HTTPException(status_code=500, detail=f"save_config error: {e}")