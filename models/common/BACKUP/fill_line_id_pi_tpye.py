#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
from sqlalchemy import text, inspect

from sql_db_connect import MySQLConnet


DB_NAME = "cim_piaoi"
DRY_RUN = False   # 先用 True 預覽；確認後改 False 執行更新


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


EMPTY_STRINGS = ("", "NaT", "nat", "nan", "NaN", "None", "none", "NULL", "null")


def q(name: str) -> str:
    return f"`{name}`"


def get_columns(db: MySQLConnet, table_name: str) -> set[str]:
    insp = inspect(db.engine)
    return {c["name"] for c in insp.get_columns(table_name)}


def is_empty_line_sql(col: str = "line_id") -> str:
    vals = ", ".join([f"'{v}'" for v in EMPTY_STRINGS])
    return f"""
    (
        {q(col)} IS NULL
        OR TRIM(CAST({q(col)} AS CHAR)) IN ({vals})
    )
    """


def update_summary_table(db: MySQLConnet, table_name: str):
    cols = get_columns(db, table_name)

    required_for_pi_type = {"aoi", "recipe_id", "test_time", "pi_time", "pi_type"}
    can_update_pi_type = required_for_pi_type.issubset(cols)

    can_update_line_id = "line_id" in cols

    logging.info("=" * 80)
    logging.info(f"[summary] table={table_name}")
    logging.info(f"[summary] can_update_line_id={can_update_line_id}")
    logging.info(f"[summary] can_update_pi_type={can_update_pi_type}")

    with db.engine.begin() as conn:
        if can_update_line_id:
            count_sql = text(f"""
                SELECT COUNT(*) AS cnt
                FROM {q(table_name)}
                WHERE {is_empty_line_sql("line_id")}
            """)
            cnt = conn.execute(count_sql).scalar() or 0
            logging.info(f"[summary] {table_name} line_id empty rows={cnt}")

            if not DRY_RUN and cnt > 0:
                update_sql = text(f"""
                    UPDATE {q(table_name)}
                    SET {q("line_id")} = 'pi000'
                    WHERE {is_empty_line_sql("line_id")}
                """)
                r = conn.execute(update_sql)
                logging.info(f"[summary] {table_name} line_id updated={r.rowcount}")

        if can_update_pi_type:
            count_sql = text(f"""
                SELECT COUNT(*) AS cnt
                FROM {q(table_name)}
            """)
            cnt = conn.execute(count_sql).scalar() or 0
            logging.info(f"[summary] {table_name} pi_type recompute rows={cnt}")

            if not DRY_RUN and cnt > 0:
                update_sql = text(f"""
                    UPDATE {q(table_name)}
                    SET {q("pi_type")} =
                        CASE
                            /* AOI100：pi_time / test_time 任一無法判斷則 OTHER */
                            WHEN {q("aoi")} IN ('CAPIT203', 'aoi100') THEN
                                CASE
                                    WHEN {q("test_time")} IS NULL OR {q("pi_time")} IS NULL THEN 'OTHER'
                                    WHEN {q("test_time")} < {q("pi_time")} THEN 'BPI'
                                    ELSE 'API'
                                END

                            /* AOI200：recipe_id 第一碼判斷 */
                            WHEN {q("aoi")} IN ('CAAOI202', 'aoi200') THEN
                                CASE
                                    WHEN LEFT(TRIM(COALESCE(CAST({q("recipe_id")} AS CHAR), '')), 1) IN ('0', '1', '2', '3') THEN 'API'
                                    WHEN LEFT(TRIM(COALESCE(CAST({q("recipe_id")} AS CHAR), '')), 1) IN ('4', '5') THEN 'BPI'
                                    ELSE 'OTHER'
                                END

                            /* AOI300：recipe_id 包含字串判斷，優先序 API > BPI > ITO 
                            WHEN {q("aoi")} IN ('CAAOI300', 'aoi300') THEN
                                CASE
                                    WHEN UPPER(COALESCE(CAST({q("recipe_id")} AS CHAR), '')) LIKE '%API%' THEN 'API'
                                    WHEN UPPER(COALESCE(CAST({q("recipe_id")} AS CHAR), '')) LIKE '%BPI%' THEN 'BPI'
                                    WHEN UPPER(COALESCE(CAST({q("recipe_id")} AS CHAR), '')) LIKE '%ITO%' THEN 'ITO'
                                    ELSE 'OTHER'
                                END
                            */

                            /* AOI300：pi_time / test_time 任一無法判斷則 OTHER */
                            WHEN {q("aoi")} IN ('CAAOI300', 'aoi300') THEN
                                CASE
                                    WHEN {q("test_time")} IS NULL OR {q("pi_time")} IS NULL THEN 'OTHER'
                                    WHEN {q("test_time")} < {q("pi_time")} THEN 'BPI'
                                    ELSE 'API'
                                END

                            ELSE 'OTHER'
                        END
                """)
                r = conn.execute(update_sql)
                logging.info(f"[summary] {table_name} pi_type updated={r.rowcount}")


def update_raw_table(db: MySQLConnet, table_name: str):
    cols = get_columns(db, table_name)

    can_update_line_id = "line_id" in cols

    logging.info("=" * 80)
    logging.info(f"[raw] table={table_name}")
    logging.info(f"[raw] can_update_line_id={can_update_line_id}")

    with db.engine.begin() as conn:
        if can_update_line_id:
            count_sql = text(f"""
                SELECT COUNT(*) AS cnt
                FROM {q(table_name)}
                WHERE {is_empty_line_sql("line_id")}
            """)
            cnt = conn.execute(count_sql).scalar() or 0
            logging.info(f"[raw] {table_name} line_id empty rows={cnt}")

            if not DRY_RUN and cnt > 0:
                update_sql = text(f"""
                    UPDATE {q(table_name)}
                    SET {q("line_id")} = 'pi000'
                    WHERE {is_empty_line_sql("line_id")}
                """)
                r = conn.execute(update_sql)
                logging.info(f"[raw] {table_name} line_id updated={r.rowcount}")


def main():
    db = MySQLConnet(DB_NAME)

    all_tbns = db.list_tables()

    pi_tbns = sorted([
        v for v in all_tbns
        if v.startswith("cim_pi_glass")
    ])

    raw_tbns = sorted([
        v for v in all_tbns
        if v.startswith("cim_defect")
    ])

    logging.info(f"DRY_RUN={DRY_RUN}")
    logging.info(f"summary tables={len(pi_tbns)}")
    logging.info(f"raw tables={len(raw_tbns)}")

    for tbn in pi_tbns:
        update_summary_table(db, tbn)

    for tbn in raw_tbns:
        update_raw_table(db, tbn)

    logging.info("done")


if __name__ == "__main__":
    main()