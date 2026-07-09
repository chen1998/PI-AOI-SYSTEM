#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import datetime as dt
import html
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import requests
from sqlalchemy import text

try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

from sql_db_connect import MySQLConnet


# =============================================================================
# Basic config
# =============================================================================

# 若 AOI_DB 可從 DensityJobConfig 取得，會優先用 DensityJobConfig().out_db。
# 若 import 失敗，才使用這裡的 fallback。
FALLBACK_AOI_DB = "piaoi_aoi_density"
INSPECTION_DB = "piaoi_inspection_density"

ALERT_TABLE = "alert_daily"

AOI_SOURCE_PREFIX = "density_tab_summary_"
INSPECTION_SOURCE_PREFIX = "inspection_api_summary_"

AOI_SYSTEM_NAME = "AOI_DENSITY"
INSPECTION_SYSTEM_NAME = "INSPECTION"

AOI_THRESHOLD = 1000.0
INSPECTION_THRESHOLD = 200.0

# 若只想限定 AOI tab，可填 ["UPI", "PISpot"]。
# 若空 list，代表 density_tab_summary 內所有 tab_name 都檢查。
AOI_ALERT_TAB_NAMES: List[str] = []

PI_AOI_SYSTEM_URL = "http://10.97.142.217:8204/"

# Mail recipients
MAIL_TO = "DL6AN1@auo.com"  # 多人用 ; 分隔，例如 "A@auo.com;B@auo.com"
MAIL_CC = ""#"harry.lin@auo.com;ruby.yc.lin@auo.com"

MAIL_URL = "https://ids.cdn.corpnet.auo.com/IDS_WS/Mail.asmx"
MAIL_CODE = "rJJeeO5U0ZI="

PROXIES = {
    "http": "http://10.97.4.1:8080",
    "https": "http://10.97.4.1:8080",
}


# =============================================================================
# Logging
# =============================================================================
def setup_logger(log_dir: str = "logs", name: str = "mail_alert") -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    today = dt.datetime.now().strftime("%Y%m%d")
    log_path = os.path.join(log_dir, f"{name}_{today}.log")

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s [%(funcName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    sh = logging.StreamHandler()

    fh.setFormatter(fmt)
    sh.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(sh)

    return logger


logger = setup_logger()


# =============================================================================
# Shift day helpers
# =============================================================================
def get_current_shift_date(now: Optional[dt.datetime] = None) -> dt.date:
    """
    當天定義：
      07:30 以前仍算前一天 shift day
      07:30 以後算今天 shift day
    """
    now = now or dt.datetime.now()
    boundary = now.replace(hour=7, minute=30, second=0, microsecond=0)

    if now < boundary:
        return now.date() - dt.timedelta(days=1)

    return now.date()

def get_alert_pi_hour_range(
    target_day: dt.date,
    now: Optional[dt.datetime] = None,
) -> Tuple[dt.datetime, dt.datetime, str]:
    """
    Alert 查詢區間規則：

    1) 00:00 ~ 07:29 執行：
       target_day 通常會是前一天
       查 target_day 07:00 ~ target_day+1 07:00

    2) 07:30 ~ 11:59 執行：
       查 target_day 00:00 ~ target_day+1 07:00
       用來補抓凌晨 ~ 早班前可能晚更新的資料

    3) 12:00 之後執行：
       查 target_day 07:00 ~ target_day+1 07:00
       回到正常 shift day 區間
    """
    now = now or dt.datetime.now()
    t = now.time()

    morning_boundary = dt.time(hour=7, minute=30, second=0)
    noon_boundary = dt.time(hour=12, minute=0, second=0)

    if t < morning_boundary:
        start_dt = dt.datetime.combine(target_day, dt.time(hour=7, minute=0, second=0))
        end_dt = start_dt + dt.timedelta(days=1)
        return start_dt, end_dt, "night-before-shift"

    if t < noon_boundary:
        start_dt = dt.datetime.combine(target_day, dt.time(hour=0, minute=0, second=0))
        end_dt = dt.datetime.combine(
            target_day + dt.timedelta(days=1),
            dt.time(hour=7, minute=0, second=0),
        )
        return start_dt, end_dt, "morning-buffer"

    start_dt = dt.datetime.combine(target_day, dt.time(hour=7, minute=0, second=0))
    end_dt = start_dt + dt.timedelta(days=1)
    return start_dt, end_dt, "normal-shift"


def get_shift_pi_hour_range(target_day: dt.date) -> Tuple[dt.datetime, dt.datetime]:
    """
    對外維持原本 function 名稱，但實際改成動態 alert range。

    00:00 ~ 07:29：target_day 07:00 ~ target_day+1 07:00
    07:30 ~ 11:59：target_day 00:00 ~ target_day+1 07:00
    12:00 之後：target_day 07:00 ~ target_day+1 07:00
    """
    start_dt, end_dt, _mode = get_alert_pi_hour_range(target_day)
    return start_dt, end_dt


def get_shift_scan_time_range(target_day: dt.date) -> Tuple[dt.datetime, dt.datetime]:
    """
    mail 顯示用：
      D 07:30 ~ D+1 07:30
    """
    start_dt = dt.datetime.combine(target_day, dt.time(hour=7, minute=30, second=0))
    end_dt = start_dt + dt.timedelta(days=1)
    return start_dt, end_dt


# =============================================================================
# AOI DB resolve
# =============================================================================
def resolve_aoi_db() -> str:
    try:
        sys.path.insert(0, r"D:/A0_Project")
        from PI_SYSTEM.models.piaoi.density.cim_density_job import Config as DensityJobConfig

        cfg = DensityJobConfig()
        db = getattr(cfg, "out_db", "") or ""
        db = str(db).strip()

        if db:
            return db
    except Exception as e:
        logger.warning(f"DensityJobConfig import failed, use fallback AOI DB. err={e}")

    return FALLBACK_AOI_DB


# =============================================================================
# Mail sender
# =============================================================================
def send_mail(request_body: Dict[str, str]) -> requests.Response:
    import xml.sax.saxutils

    session_requests = requests.session()

    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Content-Type": "application/soap+xml; charset=utf-8",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 6.1; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/62.0.3202.94 Safari/537.36"
        ),
    }

    soap_tpl = """<?xml version="1.0" encoding="utf-8"?>
    <soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                     xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                     xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
      <soap12:Body>
        <ManualSend_07 xmlns="http://tempuri.org/">
          <strMailCode>%s</strMailCode>
          <strRecipients>%s</strRecipients>
          <strCopyRecipients>%s</strCopyRecipients>
          <strSubject>%s</strSubject>
          <strBody>%s</strBody>
        </ManualSend_07>
      </soap12:Body>
    </soap12:Envelope>"""

    body = str(request_body.get("strBody", ""))
    escaped_body = xml.sax.saxutils.escape(body)

    soap_data = soap_tpl % (
        xml.sax.saxutils.escape(MAIL_CODE),
        xml.sax.saxutils.escape(str(request_body.get("strRecipients", ""))),
        xml.sax.saxutils.escape(str(request_body.get("strCopyRecipients", ""))),
        xml.sax.saxutils.escape(str(request_body.get("strSubject", ""))),
        escaped_body,
    )

    result = session_requests.post(
        MAIL_URL,
        data=soap_data.encode("utf-8"),
        headers=headers,
        proxies=PROXIES,
        verify=False,
        timeout=30,
    )

    return result


# =============================================================================
# DB helpers
# =============================================================================
def table_exists(db: MySQLConnet, table_name: str) -> bool:
    sql = text("""
        SELECT COUNT(*)
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = :db
          AND TABLE_NAME = :t
    """)

    with db.engine.begin() as conn:
        cnt = conn.execute(sql, {"db": db.db, "t": table_name}).scalar()

    return bool(cnt)


def column_exists(db: MySQLConnet, table_name: str, column_name: str) -> bool:
    sql = text("""
        SELECT COUNT(*)
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = :db
          AND TABLE_NAME = :t
          AND COLUMN_NAME = :c
    """)

    with db.engine.begin() as conn:
        cnt = conn.execute(sql, {
            "db": db.db,
            "t": table_name,
            "c": column_name,
        }).scalar()

    return bool(cnt)


def ensure_column(db: MySQLConnet, table_name: str, col: str, ddl: str) -> None:
    if column_exists(db, table_name, col):
        return

    with db.engine.begin() as conn:
        conn.execute(text(f"""
            ALTER TABLE `{db.db}`.`{table_name}`
            ADD COLUMN `{col}` {ddl}
        """))

    logger.info(f"[{db.db}.{table_name}] ADD COLUMN {col} {ddl}")


def ensure_alert_daily_table(db: MySQLConnet) -> None:
    if not table_exists(db, ALERT_TABLE):
        ddl = f"""
        CREATE TABLE `{db.db}`.`{ALERT_TABLE}` (
          `alert_key` VARCHAR(512) NOT NULL,
          `system_name` VARCHAR(64) NOT NULL,
          `alert_date` DATE NOT NULL,

          `pi_hour` DATETIME NOT NULL,
          `scan_start` DATETIME NULL,
          `scan_end` DATETIME NULL,

          `line_id` VARCHAR(32) NOT NULL,
          `aoi` VARCHAR(32) NULL,
          `model` VARCHAR(64) NOT NULL,
          `glass_type` VARCHAR(32) NOT NULL,
          `tab_name` VARCHAR(64) NULL,

          `total_glass_count` INT DEFAULT 0,
          `total_defect_count` INT DEFAULT 0,
          `density` DOUBLE DEFAULT 0,
          `threshold` DOUBLE DEFAULT 0,

          `defect_glass_count` INT DEFAULT 0,
          `small_defect_count` INT DEFAULT 0,
          `middle_defect_count` INT DEFAULT 0,
          `large_defect_count` INT DEFAULT 0,
          `over_defect_count` INT DEFAULT 0,

          `recipe_list` LONGTEXT NULL,

          `source_db` VARCHAR(128) NULL,
          `source_table` VARCHAR(128) NOT NULL,

          `alert_status` VARCHAR(32) DEFAULT 'ACTIVE',
          `first_seen_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
          `last_seen_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
          `last_mail_sent_time` DATETIME NULL,
          `mail_send_count` INT DEFAULT 0,

          `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
          `modify_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

          PRIMARY KEY (`alert_key`),
          KEY `idx_alert_date` (`alert_date`),
          KEY `idx_pi_hour` (`pi_hour`),
          KEY `idx_system_name` (`system_name`),
          KEY `idx_line_aoi_model_side` (`line_id`,`aoi`,`model`,`glass_type`),
          KEY `idx_density` (`density`),
          KEY `idx_alert_status` (`alert_status`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """

        with db.engine.begin() as conn:
            conn.execute(text(ddl))

        logger.info(f"[{db.db}.{ALERT_TABLE}] create table done")
        return

    # 保險：若既有表缺欄位，補欄位。
    ensure_column(db, ALERT_TABLE, "alert_key", "VARCHAR(512) NOT NULL")
    ensure_column(db, ALERT_TABLE, "system_name", "VARCHAR(64) NOT NULL")
    ensure_column(db, ALERT_TABLE, "alert_date", "DATE NOT NULL")
    ensure_column(db, ALERT_TABLE, "pi_hour", "DATETIME NOT NULL")
    ensure_column(db, ALERT_TABLE, "scan_start", "DATETIME NULL")
    ensure_column(db, ALERT_TABLE, "scan_end", "DATETIME NULL")
    ensure_column(db, ALERT_TABLE, "line_id", "VARCHAR(32) NOT NULL")
    ensure_column(db, ALERT_TABLE, "aoi", "VARCHAR(32) NULL")
    ensure_column(db, ALERT_TABLE, "model", "VARCHAR(64) NOT NULL")
    ensure_column(db, ALERT_TABLE, "glass_type", "VARCHAR(32) NOT NULL")
    ensure_column(db, ALERT_TABLE, "tab_name", "VARCHAR(64) NULL")
    ensure_column(db, ALERT_TABLE, "total_glass_count", "INT DEFAULT 0")
    ensure_column(db, ALERT_TABLE, "total_defect_count", "INT DEFAULT 0")
    ensure_column(db, ALERT_TABLE, "density", "DOUBLE DEFAULT 0")
    ensure_column(db, ALERT_TABLE, "threshold", "DOUBLE DEFAULT 0")
    ensure_column(db, ALERT_TABLE, "defect_glass_count", "INT DEFAULT 0")
    ensure_column(db, ALERT_TABLE, "small_defect_count", "INT DEFAULT 0")
    ensure_column(db, ALERT_TABLE, "middle_defect_count", "INT DEFAULT 0")
    ensure_column(db, ALERT_TABLE, "large_defect_count", "INT DEFAULT 0")
    ensure_column(db, ALERT_TABLE, "over_defect_count", "INT DEFAULT 0")
    ensure_column(db, ALERT_TABLE, "recipe_list", "LONGTEXT NULL")
    ensure_column(db, ALERT_TABLE, "source_db", "VARCHAR(128) NULL")
    ensure_column(db, ALERT_TABLE, "source_table", "VARCHAR(128) NOT NULL")
    ensure_column(db, ALERT_TABLE, "alert_status", "VARCHAR(32) DEFAULT 'ACTIVE'")
    ensure_column(db, ALERT_TABLE, "first_seen_time", "DATETIME DEFAULT CURRENT_TIMESTAMP")
    ensure_column(db, ALERT_TABLE, "last_seen_time", "DATETIME DEFAULT CURRENT_TIMESTAMP")
    ensure_column(db, ALERT_TABLE, "last_mail_sent_time", "DATETIME NULL")
    ensure_column(db, ALERT_TABLE, "mail_send_count", "INT DEFAULT 0")
    ensure_column(db, ALERT_TABLE, "created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP")
    ensure_column(db, ALERT_TABLE, "modify_time", "DATETIME DEFAULT CURRENT_TIMESTAMP")


def parse_date(s: Optional[str]) -> dt.date:
    """
    不帶 --date 時，依 07:30 shift day 判斷：
      07:30 前 -> 前一天
      07:30 後 -> 今天
    """
    if not s:
        return get_current_shift_date()

    raw = str(s).strip()

    for fmt in ["%Y-%m-%d", "%Y/%m/%d"]:
        try:
            return dt.datetime.strptime(raw, fmt).date()
        except ValueError:
            pass

    raise ValueError(f"Bad date: {s}")


def month_span(start_day: dt.date, end_day: dt.date) -> List[str]:
    if end_day < start_day:
        start_day, end_day = end_day, start_day

    cur = dt.datetime(start_day.year, start_day.month, 1)
    last = dt.datetime(end_day.year, end_day.month, 1)

    out = []

    while cur <= last:
        out.append(cur.strftime("%Y%m"))
        cur = (cur.replace(day=28) + dt.timedelta(days=4)).replace(day=1)

    return out


def build_aoi_source_table(yyyymm: str) -> str:
    return f"{AOI_SOURCE_PREFIX}{yyyymm}"


def build_inspection_source_table(yyyymm: str) -> str:
    return f"{INSPECTION_SOURCE_PREFIX}{yyyymm}"


def ensure_inspection_density_column(db: MySQLConnet, table_name: str) -> None:
    if not table_exists(db, table_name):
        return

    if not column_exists(db, table_name, "maingroup_density"):
        with db.engine.begin() as conn:
            conn.execute(text(f"""
                ALTER TABLE `{db.db}`.`{table_name}`
                ADD COLUMN `maingroup_density` DOUBLE DEFAULT 0
            """))
        logger.info(f"[{db.db}.{table_name}] ADD COLUMN maingroup_density")

    with db.engine.begin() as conn:
        conn.execute(text(f"""
            UPDATE `{db.db}`.`{table_name}`
            SET `maingroup_density` =
                CASE
                    WHEN `maingroup_glass_count` IS NULL OR `maingroup_glass_count` = 0 THEN 0
                    ELSE COALESCE(`maingroup_defect_count`, 0) / `maingroup_glass_count`
                END
            WHERE `maingroup_density` IS NULL
               OR `maingroup_density` = 0
        """))


# =============================================================================
# Sync AOI_DENSITY
# =============================================================================
def mark_system_day_resolved(db: MySQLConnet, system_name: str, target_day: dt.date) -> int:
    sql = text(f"""
        UPDATE `{db.db}`.`{ALERT_TABLE}`
        SET `alert_status` = 'RESOLVED',
            `last_seen_time` = CURRENT_TIMESTAMP,
            `modify_time` = CURRENT_TIMESTAMP
        WHERE `system_name` = :system_name
          AND `alert_date` = :alert_date
          AND `alert_status` = 'ACTIVE'
    """)

    with db.engine.begin() as conn:
        result = conn.execute(sql, {
            "system_name": system_name,
            "alert_date": target_day,
        })

    return int(result.rowcount or 0)


def sync_aoi_density_alerts(db_name: str, target_day: dt.date, threshold: float) -> Dict[str, Any]:
    db = MySQLConnet(db_name)
    ensure_alert_daily_table(db)

    # shift day: D 07:30 ~ D+1 07:30
    # pi_hour query: D 07:00 <= pi_hour < D+1 07:00
    start_dt, end_dt = get_shift_pi_hour_range(target_day)

    marked_resolved = mark_system_day_resolved(db, AOI_SYSTEM_NAME, target_day)

    total_source_rows = 0
    total_affected = 0

    # 若跨月，需要撈兩張月表
    yms = month_span(start_dt.date(), (end_dt - dt.timedelta(seconds=1)).date())

    for ym in yms:
        source_tbn = build_aoi_source_table(ym)

        if not table_exists(db, source_tbn):
            logger.warning(f"[{db.db}.{source_tbn}] missing source table, skip")
            continue

        tab_filter_sql = ""
        params: Dict[str, Any] = {
            "system_name": AOI_SYSTEM_NAME,
            "alert_date": target_day,
            "start_dt": start_dt,
            "end_dt": end_dt,
            "threshold": float(threshold),
            "source_db": db.db,
            "source_table": source_tbn,
        }

        if AOI_ALERT_TAB_NAMES:
            in_keys = []
            for i, tab in enumerate(AOI_ALERT_TAB_NAMES):
                k = f"tab_{i}"
                in_keys.append(f":{k}")
                params[k] = tab
            tab_filter_sql = f" AND `tab_name` IN ({','.join(in_keys)}) "

        count_sql = text(f"""
            SELECT COUNT(*)
            FROM `{db.db}`.`{source_tbn}`
            WHERE `pi_hour` >= :start_dt
              AND `pi_hour` < :end_dt
              AND COALESCE(`tab_total_density`, 0) > :threshold
              {tab_filter_sql}
        """)

        insert_sql = text(f"""
            INSERT INTO `{db.db}`.`{ALERT_TABLE}` (
                alert_key,
                system_name,
                alert_date,

                pi_hour,
                scan_start,
                scan_end,

                line_id,
                aoi,
                model,
                glass_type,
                tab_name,

                total_glass_count,
                total_defect_count,
                density,
                threshold,

                defect_glass_count,
                small_defect_count,
                middle_defect_count,
                large_defect_count,
                over_defect_count,

                recipe_list,

                source_db,
                source_table,

                alert_status,
                first_seen_time,
                last_seen_time
            )
            SELECT
                CONCAT(
                    :system_name, '||',
                    DATE_FORMAT(`pi_hour`, '%Y-%m-%d %H:%i:%s'), '||',
                    COALESCE(`line_id`, ''), '||',
                    COALESCE(`aoi`, ''), '||',
                    COALESCE(`model`, ''), '||',
                    COALESCE(`glass_type`, ''), '||',
                    COALESCE(`tab_name`, '')
                ) AS alert_key,

                :system_name AS system_name,
                :alert_date AS alert_date,

                `pi_hour`,
                DATE_ADD(`pi_hour`, INTERVAL 30 MINUTE) AS scan_start,
                DATE_ADD(`pi_hour`, INTERVAL 90 MINUTE) AS scan_end,

                COALESCE(`line_id`, '') AS line_id,
                COALESCE(`aoi`, '') AS aoi,
                COALESCE(`model`, '') AS model,
                COALESCE(`glass_type`, '') AS glass_type,
                COALESCE(`tab_name`, '') AS tab_name,

                COALESCE(`tab_total_glass_cnt`, 0) AS total_glass_count,
                COALESCE(`tab_total_defect_cnt`, 0) AS total_defect_count,
                COALESCE(`tab_total_density`, 0) AS density,
                :threshold AS threshold,

                0 AS defect_glass_count,
                0 AS small_defect_count,
                0 AS middle_defect_count,
                0 AS large_defect_count,
                0 AS over_defect_count,

                COALESCE(`recipe_list`, '') AS recipe_list,

                :source_db AS source_db,
                :source_table AS source_table,

                'ACTIVE' AS alert_status,
                CURRENT_TIMESTAMP AS first_seen_time,
                CURRENT_TIMESTAMP AS last_seen_time

            FROM `{db.db}`.`{source_tbn}`
            WHERE `pi_hour` >= :start_dt
              AND `pi_hour` < :end_dt
              AND COALESCE(`tab_total_density`, 0) > :threshold
              {tab_filter_sql}

            ON DUPLICATE KEY UPDATE
                system_name = VALUES(system_name),
                alert_date = VALUES(alert_date),

                scan_start = VALUES(scan_start),
                scan_end = VALUES(scan_end),

                total_glass_count = VALUES(total_glass_count),
                total_defect_count = VALUES(total_defect_count),
                density = VALUES(density),
                threshold = VALUES(threshold),

                recipe_list = VALUES(recipe_list),

                source_db = VALUES(source_db),
                source_table = VALUES(source_table),

                alert_status = 'ACTIVE',
                last_seen_time = CURRENT_TIMESTAMP,
                modify_time = CURRENT_TIMESTAMP
        """)

        with db.engine.begin() as conn:
            source_rows = int(conn.execute(count_sql, params).scalar() or 0)
            result = conn.execute(insert_sql, params)
            affected = int(result.rowcount or 0)

        total_source_rows += source_rows
        total_affected += affected

        logger.info(
            f"[sync_aoi_density_alerts] table={source_tbn}, "
            f"range=[{start_dt} ~ {end_dt}), "
            f"source_rows={source_rows}, affected={affected}, threshold={threshold}"
        )

    return {
        "system_name": AOI_SYSTEM_NAME,
        "db": db_name,
        "target_day": str(target_day),
        "query_start": str(start_dt),
        "query_end": str(end_dt),
        "threshold": threshold,
        "marked_resolved": marked_resolved,
        "source_rows": total_source_rows,
        "affected_rows": total_affected,
    }


# =============================================================================
# Sync INSPECTION
# =============================================================================
def sync_inspection_alerts(db_name: str, target_day: dt.date, threshold: float) -> Dict[str, Any]:
    db = MySQLConnet(db_name)
    ensure_alert_daily_table(db)

    # shift day: D 07:30 ~ D+1 07:30
    # pi_hour query: D 07:00 <= pi_hour < D+1 07:00
    start_dt, end_dt = get_shift_pi_hour_range(target_day)

    marked_resolved = mark_system_day_resolved(db, INSPECTION_SYSTEM_NAME, target_day)

    total_source_rows = 0
    total_affected = 0

    # 若跨月，需要撈兩張月表
    yms = month_span(start_dt.date(), (end_dt - dt.timedelta(seconds=1)).date())

    for ym in yms:
        source_tbn = build_inspection_source_table(ym)

        if not table_exists(db, source_tbn):
            logger.warning(f"[{db.db}.{source_tbn}] missing source table, skip")
            continue

        ensure_inspection_density_column(db, source_tbn)

        params: Dict[str, Any] = {
            "system_name": INSPECTION_SYSTEM_NAME,
            "alert_date": target_day,
            "start_dt": start_dt,
            "end_dt": end_dt,
            "threshold": float(threshold),
            "source_db": db.db,
            "source_table": source_tbn,
        }

        count_sql = text(f"""
            SELECT COUNT(*)
            FROM `{db.db}`.`{source_tbn}`
            WHERE `pi_hour` >= :start_dt
              AND `pi_hour` < :end_dt
              AND COALESCE(`maingroup_density`, 0) > :threshold
        """)

        insert_sql = text(f"""
            INSERT INTO `{db.db}`.`{ALERT_TABLE}` (
                alert_key,
                system_name,
                alert_date,

                pi_hour,
                scan_start,
                scan_end,

                line_id,
                aoi,
                model,
                glass_type,
                tab_name,

                total_glass_count,
                total_defect_count,
                density,
                threshold,

                defect_glass_count,
                small_defect_count,
                middle_defect_count,
                large_defect_count,
                over_defect_count,

                recipe_list,

                source_db,
                source_table,

                alert_status,
                first_seen_time,
                last_seen_time
            )
            SELECT
                CONCAT(
                    :system_name, '||',
                    DATE_FORMAT(`pi_hour`, '%Y-%m-%d %H:%i:%s'), '||',
                    COALESCE(`line_id`, ''), '||',
                    COALESCE(`model`, ''), '||',
                    COALESCE(`glass_type`, '')
                ) AS alert_key,

                :system_name AS system_name,
                :alert_date AS alert_date,

                `pi_hour`,
                COALESCE(`shift_start`, DATE_ADD(`pi_hour`, INTERVAL 30 MINUTE)) AS scan_start,
                COALESCE(`shift_end`, DATE_ADD(`pi_hour`, INTERVAL 90 MINUTE)) AS scan_end,

                COALESCE(`line_id`, '') AS line_id,
                '' AS aoi,
                COALESCE(`model`, '') AS model,
                COALESCE(`glass_type`, '') AS glass_type,
                '' AS tab_name,

                COALESCE(`maingroup_glass_count`, 0) AS total_glass_count,
                COALESCE(`maingroup_defect_count`, 0) AS total_defect_count,
                COALESCE(`maingroup_density`, 0) AS density,
                :threshold AS threshold,

                COALESCE(`defect_code_glass_count`, 0) AS defect_glass_count,
                COALESCE(`small_defect_count`, 0) AS small_defect_count,
                COALESCE(`middle_defect_count`, 0) AS middle_defect_count,
                COALESCE(`large_defect_count`, 0) AS large_defect_count,
                COALESCE(`over_defect_count`, 0) AS over_defect_count,

                '' AS recipe_list,

                :source_db AS source_db,
                :source_table AS source_table,

                'ACTIVE' AS alert_status,
                CURRENT_TIMESTAMP AS first_seen_time,
                CURRENT_TIMESTAMP AS last_seen_time

            FROM `{db.db}`.`{source_tbn}`
            WHERE `pi_hour` >= :start_dt
              AND `pi_hour` < :end_dt
              AND COALESCE(`maingroup_density`, 0) > :threshold

            ON DUPLICATE KEY UPDATE
                system_name = VALUES(system_name),
                alert_date = VALUES(alert_date),

                scan_start = VALUES(scan_start),
                scan_end = VALUES(scan_end),

                total_glass_count = VALUES(total_glass_count),
                total_defect_count = VALUES(total_defect_count),
                density = VALUES(density),
                threshold = VALUES(threshold),

                defect_glass_count = VALUES(defect_glass_count),
                small_defect_count = VALUES(small_defect_count),
                middle_defect_count = VALUES(middle_defect_count),
                large_defect_count = VALUES(large_defect_count),
                over_defect_count = VALUES(over_defect_count),

                source_db = VALUES(source_db),
                source_table = VALUES(source_table),

                alert_status = 'ACTIVE',
                last_seen_time = CURRENT_TIMESTAMP,
                modify_time = CURRENT_TIMESTAMP
        """)

        with db.engine.begin() as conn:
            source_rows = int(conn.execute(count_sql, params).scalar() or 0)
            result = conn.execute(insert_sql, params)
            affected = int(result.rowcount or 0)

        total_source_rows += source_rows
        total_affected += affected

        logger.info(
            f"[sync_inspection_alerts] table={source_tbn}, "
            f"range=[{start_dt} ~ {end_dt}), "
            f"source_rows={source_rows}, affected={affected}, threshold={threshold}"
        )

    return {
        "system_name": INSPECTION_SYSTEM_NAME,
        "db": db_name,
        "target_day": str(target_day),
        "query_start": str(start_dt),
        "query_end": str(end_dt),
        "threshold": threshold,
        "marked_resolved": marked_resolved,
        "source_rows": total_source_rows,
        "affected_rows": total_affected,
    }


# =============================================================================
# Query alert_daily
# =============================================================================
def fetch_active_alert_rows(
    db_name: str,
    system_name: str,
    target_day: dt.date,
) -> List[Dict[str, Any]]:
    db = MySQLConnet(db_name)
    ensure_alert_daily_table(db)

    sql = text(f"""
        SELECT
            alert_key,
            system_name,
            alert_date,
            pi_hour,
            scan_start,
            scan_end,
            line_id,
            aoi,
            model,
            glass_type,
            tab_name,
            total_glass_count,
            total_defect_count,
            density,
            threshold,
            defect_glass_count,
            small_defect_count,
            middle_defect_count,
            large_defect_count,
            over_defect_count,
            recipe_list,
            source_db,
            source_table,
            alert_status,
            first_seen_time,
            last_seen_time,
            last_mail_sent_time,
            mail_send_count
        FROM `{db.db}`.`{ALERT_TABLE}`
        WHERE `system_name` = :system_name
          AND `alert_date` = :alert_date
          AND `alert_status` = 'ACTIVE'
          AND COALESCE(`density`, 0) > COALESCE(`threshold`, 0)
        ORDER BY
            `density` DESC,
            `pi_hour` DESC,
            `line_id`,
            `aoi`,
            `model`,
            `glass_type`
    """)

    with db.engine.begin() as conn:
        rows = conn.execute(sql, {
            "system_name": system_name,
            "alert_date": target_day,
        }).mappings().all()

    return [dict(r) for r in rows]


def update_mail_sent_rows(db_name: str, alert_keys: List[str]) -> int:
    if not alert_keys:
        return 0

    db = MySQLConnet(db_name)
    ensure_alert_daily_table(db)

    params = {}
    holders = []

    for i, k in enumerate(alert_keys):
        pk = f"k{i}"
        holders.append(f":{pk}")
        params[pk] = k

    sql = text(f"""
        UPDATE `{db.db}`.`{ALERT_TABLE}`
        SET `last_mail_sent_time` = CURRENT_TIMESTAMP,
            `mail_send_count` = COALESCE(`mail_send_count`, 0) + 1,
            `modify_time` = CURRENT_TIMESTAMP
        WHERE `alert_key` IN ({",".join(holders)})
    """)

    with db.engine.begin() as conn:
        result = conn.execute(sql, params)

    return int(result.rowcount or 0)


# =============================================================================
# HTML mail body
# =============================================================================
def fmt_dt(v: Any) -> str:
    if v is None:
        return ""

    if isinstance(v, (dt.datetime, dt.date)):
        if isinstance(v, dt.datetime):
            return v.strftime("%Y-%m-%d %H:%M:%S")
        return v.strftime("%Y-%m-%d")

    s = str(v)
    if s == "None" or s == "NaT":
        return ""

    return s


def fmt_num(v: Any, ndigits: int = 2) -> str:
    try:
        x = float(v)
        return f"{x:.{ndigits}f}"
    except Exception:
        return "0.00"


def fmt_int(v: Any) -> str:
    try:
        return str(int(float(v or 0)))
    except Exception:
        return "0"


def esc(v: Any) -> str:
    return html.escape("" if v is None else str(v))


def build_scan_time_text(row: Dict[str, Any]) -> str:
    return f"{fmt_dt(row.get('scan_start'))} ~ {fmt_dt(row.get('scan_end'))}"


def build_html_table(system_name: str, rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "<p>目前無 Alert。</p>"

    if system_name == AOI_SYSTEM_NAME:
        headers = [
            "No.",
            "PI Hour",
            "PI Line",
            "AOI",
            "Model",
            "Side",
            "Total Glass",
            "Total Defect",
            "Density",
        ]

        body_rows = []

        for i, r in enumerate(rows, start=1):
            body_rows.append([
                str(i),
                fmt_dt(r.get("pi_hour")),
                r.get("line_id", ""),
                r.get("aoi", ""),
                r.get("model", ""),
                r.get("glass_type", ""),
                fmt_int(r.get("total_glass_count")),
                fmt_int(r.get("total_defect_count")),
                fmt_num(r.get("density"), 2),
            ])

    else:
        headers = [
            "No.",
            "Scan Hour",
            "Line",
            "Model",
            "Side",
            "Total Glass",
            "Total Defect",
            "Density",
            "Defect Glass",
            "S",
            "M",
            "L",
            "O",
        ]

        body_rows = []

        for i, r in enumerate(rows, start=1):
            body_rows.append([
                str(i),
                fmt_dt(r.get("pi_hour")),
                r.get("line_id", ""),
                r.get("model", ""),
                r.get("glass_type", ""),
                fmt_int(r.get("total_glass_count")),
                fmt_int(r.get("total_defect_count")),
                fmt_num(r.get("density"), 2),
                fmt_int(r.get("defect_glass_count")),
                fmt_int(r.get("small_defect_count")),
                fmt_int(r.get("middle_defect_count")),
                fmt_int(r.get("large_defect_count")),
                fmt_int(r.get("over_defect_count")),
            ])

    th_html = "".join(
        f"<th style='border:1px solid #999;padding:6px;background:#e8eef7;text-align:center;'>{esc(h)}</th>"
        for h in headers
    )

    tr_html_list = []

    for tr in body_rows:
        td_html = "".join(
            f"<td style='border:1px solid #999;padding:5px;text-align:center;white-space:nowrap;'>{esc(v)}</td>"
            for v in tr
        )
        tr_html_list.append(f"<tr>{td_html}</tr>")

    table_html = f"""
    <table style="border-collapse:collapse;font-family:Arial,'Microsoft JhengHei',sans-serif;font-size:13px;">
      <thead>
        <tr>{th_html}</tr>
      </thead>
      <tbody>
        {''.join(tr_html_list)}
      </tbody>
    </table>
    """

    return table_html


def build_mail_body(system_name: str, target_day: dt.date, rows: List[Dict[str, Any]]) -> str:
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    threshold = AOI_THRESHOLD if system_name == AOI_SYSTEM_NAME else INSPECTION_THRESHOLD

    shift_start, shift_end = get_shift_scan_time_range(target_day)
    pi_start, pi_end, range_mode = get_alert_pi_hour_range(target_day)

    print(f"range_mode={range_mode}")
    print(f"shift_range={shift_start} ~ {shift_end}")
    print(f"pi_hour_query_range=[{pi_start} ~ {pi_end})")

    body = ""
    body += f"<a href='{PI_AOI_SYSTEM_URL}'>PI AOI System 連結</a><br><br>"
    body += f"<b>{esc(system_name)} Density Alert</b><br>"
    body += f"Alert Shift Day: {esc(target_day)}<br>"
    body += f"Alert Range Mode: {esc(range_mode)}<br>"
    body += f"Shift Range: {esc(shift_start.strftime('%Y-%m-%d %H:%M:%S'))} ~ {esc(shift_end.strftime('%Y-%m-%d %H:%M:%S'))}<br>"
    body += f"PI Hour Query Range: {esc(pi_start.strftime('%Y-%m-%d %H:%M:%S'))} ~ {esc(pi_end.strftime('%Y-%m-%d %H:%M:%S'))}<br>"
    body += f"Mail Time: {esc(now)}<br>"
    body += f"Threshold: density &gt; {esc(threshold)}<br>"
    body += f"Alert Count: {len(rows)}<br><br>"
    body += build_html_table(system_name, rows)
    body += "<br><br>"
    body += "<span style='color:#777;'>此信件由 PI AOI mail_alert.py 每小時自動產生。</span>"

    return body

def build_combined_mail_body(
    target_day: dt.date,
    aoi_rows: List[Dict[str, Any]],
    inspection_rows: List[Dict[str, Any]],
) -> str:
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    shift_start, shift_end = get_shift_scan_time_range(target_day)
    pi_start, pi_end, range_mode = get_alert_pi_hour_range(target_day)

    print(f"range_mode={range_mode}")
    print(f"shift_range={shift_start} ~ {shift_end}")
    print(f"pi_hour_query_range=[{pi_start} ~ {pi_end})")

    aoi_count = len(aoi_rows or [])
    inspection_count = len(inspection_rows or [])
    total_count = aoi_count + inspection_count

    body = ""
    body += f"<a href='{PI_AOI_SYSTEM_URL}'>PI AOI System 連結</a><br><br>"
    body += "<b>PI AOI Density Combined Alert</b><br>"
    body += f"Alert Shift Day: {esc(target_day)}<br>"
    body += f"Alert Range Mode: {esc(range_mode)}<br>"
    body += f"Shift Range: {esc(shift_start.strftime('%Y-%m-%d %H:%M:%S'))} ~ {esc(shift_end.strftime('%Y-%m-%d %H:%M:%S'))}<br>"
    body += f"PI Hour Query Range: {esc(pi_start.strftime('%Y-%m-%d %H:%M:%S'))} ~ {esc(pi_end.strftime('%Y-%m-%d %H:%M:%S'))}<br>"
    body += f"Mail Time: {esc(now)}<br>"
    body += f"Total Alert Count: {total_count}<br>"
    body += f"AOI_DENSITY Threshold: density &gt; {esc(AOI_THRESHOLD)}，Alert Count: {aoi_count}<br>"
    body += f"INSPECTION Threshold: density &gt; {esc(INSPECTION_THRESHOLD)}，Alert Count: {inspection_count}<br>"
    body += "<br>"

    if aoi_count > 0:
        body += f"<h3 style='margin-bottom:6px;'>AOI_DENSITY Alert ({aoi_count})</h3>"
        body += build_html_table(AOI_SYSTEM_NAME, aoi_rows)
        body += "<br><br>"

    if inspection_count > 0:
        body += f"<h3 style='margin-bottom:6px;'>INSPECTION Alert ({inspection_count})</h3>"
        body += build_html_table(INSPECTION_SYSTEM_NAME, inspection_rows)
        body += "<br><br>"

    body += "<span style='color:#777;'>此信件由 PI AOI mail_alert.py 每小時自動產生。</span>"

    return body

def send_system_alert_mail(
    db_name: str,
    system_name: str,
    target_day: dt.date,
    rows: List[Dict[str, Any]],
    dry_run: bool = False,
) -> Dict[str, Any]:
    if not rows:
        logger.info(f"[{system_name}] no active alert rows, skip mail")
        return {
            "system_name": system_name,
            "sent": False,
            "row_count": 0,
            "status_code": None,
            "updated_rows": 0,
        }

    subject = f"PI AOI System - {system_name} Alert - {target_day} - {len(rows)} rows"
    body = build_mail_body(system_name, target_day, rows)

    post_data = {
        "strRecipients": MAIL_TO,
        "strCopyRecipients": MAIL_CC,
        "strSubject": subject,
        "strBody": body,
    }

    if dry_run:
        logger.info(f"[DRY RUN][{system_name}] subject={subject}, rows={len(rows)}")
        logger.info(body)
        return {
            "system_name": system_name,
            "sent": False,
            "dry_run": True,
            "row_count": len(rows),
            "status_code": None,
            "updated_rows": 0,
        }

    if not MAIL_TO.strip():
        logger.warning(f"[{system_name}] MAIL_TO empty, skip actual send")
        return {
            "system_name": system_name,
            "sent": False,
            "row_count": len(rows),
            "status_code": None,
            "updated_rows": 0,
            "message": "MAIL_TO empty",
        }

    resp = send_mail(post_data)
    ok = 200 <= int(resp.status_code) < 300

    updated_rows = 0

    if ok:
        alert_keys = [str(r["alert_key"]) for r in rows if r.get("alert_key")]
        updated_rows = update_mail_sent_rows(db_name, alert_keys)

    logger.info(
        f"[{system_name}] mail sent={ok}, status_code={resp.status_code}, "
        f"rows={len(rows)}, updated_rows={updated_rows}"
    )

    return {
        "system_name": system_name,
        "sent": ok,
        "row_count": len(rows),
        "status_code": resp.status_code,
        "updated_rows": updated_rows,
        "response_text": resp.text[:1000] if resp.text else "",
    }

def send_combined_alert_mail(
    aoi_db: str,
    inspection_db: str,
    target_day: dt.date,
    aoi_rows: List[Dict[str, Any]],
    inspection_rows: List[Dict[str, Any]],
    dry_run: bool = False,
) -> Dict[str, Any]:
    aoi_rows = aoi_rows or []
    inspection_rows = inspection_rows or []

    total_count = len(aoi_rows) + len(inspection_rows)

    if total_count <= 0:
        logger.info("[COMBINED] no active alert rows, skip mail")
        return {
            "system_name": "COMBINED",
            "sent": False,
            "row_count": 0,
            "aoi_count": 0,
            "inspection_count": 0,
            "status_code": None,
            "updated_aoi_rows": 0,
            "updated_inspection_rows": 0,
        }

    subject = (
        f"PI AOI System - Combined Density Alert - {target_day} - "
        f"AOI:{len(aoi_rows)} / INSPECTION:{len(inspection_rows)}"
    )
    body = build_combined_mail_body(target_day, aoi_rows, inspection_rows)

    post_data = {
        "strRecipients": MAIL_TO,
        "strCopyRecipients": MAIL_CC,
        "strSubject": subject,
        "strBody": body,
    }

    if dry_run:
        logger.info(
            f"[DRY RUN][COMBINED] subject={subject}, "
            f"aoi_rows={len(aoi_rows)}, inspection_rows={len(inspection_rows)}"
        )
        logger.info(body)
        return {
            "system_name": "COMBINED",
            "sent": False,
            "dry_run": True,
            "row_count": total_count,
            "aoi_count": len(aoi_rows),
            "inspection_count": len(inspection_rows),
            "status_code": None,
            "updated_aoi_rows": 0,
            "updated_inspection_rows": 0,
        }

    if not MAIL_TO.strip():
        logger.warning("[COMBINED] MAIL_TO empty, skip actual send")
        return {
            "system_name": "COMBINED",
            "sent": False,
            "row_count": total_count,
            "aoi_count": len(aoi_rows),
            "inspection_count": len(inspection_rows),
            "status_code": None,
            "updated_aoi_rows": 0,
            "updated_inspection_rows": 0,
            "message": "MAIL_TO empty",
        }

    resp = send_mail(post_data)
    ok = 200 <= int(resp.status_code) < 300

    updated_aoi_rows = 0
    updated_inspection_rows = 0

    if ok:
        aoi_keys = [str(r["alert_key"]) for r in aoi_rows if r.get("alert_key")]
        inspection_keys = [str(r["alert_key"]) for r in inspection_rows if r.get("alert_key")]

        updated_aoi_rows = update_mail_sent_rows(aoi_db, aoi_keys)
        updated_inspection_rows = update_mail_sent_rows(inspection_db, inspection_keys)

    logger.info(
        f"[COMBINED] mail sent={ok}, status_code={resp.status_code}, "
        f"aoi_rows={len(aoi_rows)}, inspection_rows={len(inspection_rows)}, "
        f"updated_aoi_rows={updated_aoi_rows}, updated_inspection_rows={updated_inspection_rows}"
    )

    return {
        "system_name": "COMBINED",
        "sent": ok,
        "row_count": total_count,
        "aoi_count": len(aoi_rows),
        "inspection_count": len(inspection_rows),
        "status_code": resp.status_code,
        "updated_aoi_rows": updated_aoi_rows,
        "updated_inspection_rows": updated_inspection_rows,
        "response_text": resp.text[:1000] if resp.text else "",
    }


# =============================================================================
# Main flow
# =============================================================================
def run_mail_alert(
    target_day: dt.date,
    aoi_db: str,
    inspection_db: str,
    aoi_threshold: float,
    inspection_threshold: float,
    dry_run: bool = False,
    sync_only: bool = False,
    send_aoi: bool = True,
    send_inspection: bool = True,
    combined_mail: bool = False,
) -> Dict[str, Any]:
    logger.info(
        f"[run_mail_alert] target_day={target_day}, "
        f"aoi_db={aoi_db}, inspection_db={inspection_db}, "
        f"aoi_threshold={aoi_threshold}, inspection_threshold={inspection_threshold}, "
        f"dry_run={dry_run}, sync_only={sync_only}, combined_mail={combined_mail}"
    )

    result: Dict[str, Any] = {
        "target_day": str(target_day),
        "sync": {},
        "mail": {},
    }

    if send_aoi:
        result["sync"][AOI_SYSTEM_NAME] = sync_aoi_density_alerts(
            db_name=aoi_db,
            target_day=target_day,
            threshold=float(aoi_threshold),
        )

    if send_inspection:
        result["sync"][INSPECTION_SYSTEM_NAME] = sync_inspection_alerts(
            db_name=inspection_db,
            target_day=target_day,
            threshold=float(inspection_threshold),
        )

    if sync_only:
        return result

    aoi_rows: List[Dict[str, Any]] = []
    inspection_rows: List[Dict[str, Any]] = []

    if send_aoi:
        aoi_rows = fetch_active_alert_rows(
            db_name=aoi_db,
            system_name=AOI_SYSTEM_NAME,
            target_day=target_day,
        )

    if send_inspection:
        inspection_rows = fetch_active_alert_rows(
            db_name=inspection_db,
            system_name=INSPECTION_SYSTEM_NAME,
            target_day=target_day,
        )

    if combined_mail:
        result["mail"]["COMBINED"] = send_combined_alert_mail(
            aoi_db=aoi_db,
            inspection_db=inspection_db,
            target_day=target_day,
            aoi_rows=aoi_rows,
            inspection_rows=inspection_rows,
            dry_run=dry_run,
        )
        return result

    if send_aoi:
        result["mail"][AOI_SYSTEM_NAME] = send_system_alert_mail(
            db_name=aoi_db,
            system_name=AOI_SYSTEM_NAME,
            target_day=target_day,
            rows=aoi_rows,
            dry_run=dry_run,
        )

    if send_inspection:
        result["mail"][INSPECTION_SYSTEM_NAME] = send_system_alert_mail(
            db_name=inspection_db,
            system_name=INSPECTION_SYSTEM_NAME,
            target_day=target_day,
            rows=inspection_rows,
            dry_run=dry_run,
        )

    return result

# =============================================================================
# CLI
# =============================================================================
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="PI AOI hourly mail alert for AOI_DENSITY and INSPECTION.")

    p.add_argument("--date", default=None, help="Alert shift date YYYY-MM-DD, default=current shift day by 07:30")
    p.add_argument("--aoi-db", default=None, help="AOI density DB. Default from DensityJobConfig().out_db or fallback.")
    p.add_argument("--inspection-db", default=INSPECTION_DB)

    p.add_argument("--aoi-threshold", type=float, default=AOI_THRESHOLD)
    p.add_argument("--inspection-threshold", type=float, default=INSPECTION_THRESHOLD)

    p.add_argument("--dry-run", action="store_true", help="Do not send mail, print/log mail body only.")
    p.add_argument("--sync-only", action="store_true", help="Only sync alert_daily, do not send mail.")

    p.add_argument("--only-aoi", action="store_true", help="Only process AOI_DENSITY.")
    p.add_argument("--only-inspection", action="store_true", help="Only process INSPECTION.")

    p.add_argument(
        "--combined-mail",
        action="store_true",
        help="Send AOI_DENSITY and INSPECTION alerts in one combined email.",
    )
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    target_day = parse_date(args.date)

    aoi_db = args.aoi_db or resolve_aoi_db()
    inspection_db = args.inspection_db

    send_aoi = True
    send_inspection = True

    if args.only_aoi:
        send_inspection = False

    if args.only_inspection:
        send_aoi = False

    result = run_mail_alert(
        target_day=target_day,
        aoi_db=aoi_db,
        inspection_db=inspection_db,
        aoi_threshold=float(args.aoi_threshold),
        inspection_threshold=float(args.inspection_threshold),
        dry_run=bool(args.dry_run),
        sync_only=bool(args.sync_only),
        send_aoi=send_aoi,
        send_inspection=send_inspection,
        combined_mail=bool(args.combined_mail),
    )

    print("=" * 80)
    print("PI AOI Mail Alert Result")
    print("=" * 80)

    print(f"target_day={result['target_day']}")

    shift_start, shift_end = get_shift_scan_time_range(target_day)
    pi_start, pi_end = get_shift_pi_hour_range(target_day)

    print(f"shift_range={shift_start} ~ {shift_end}")
    print(f"pi_hour_query_range=[{pi_start} ~ {pi_end})")

    for k, v in result.get("sync", {}).items():
        print(
            f"[SYNC][{k}] "
            f"db={v.get('db')}, "
            f"threshold={v.get('threshold')}, "
            f"query_start={v.get('query_start')}, "
            f"query_end={v.get('query_end')}, "
            f"source_rows={v.get('source_rows')}, "
            f"affected_rows={v.get('affected_rows')}, "
            f"marked_resolved={v.get('marked_resolved')}"
        )

    for k, v in result.get("mail", {}).items():
        if k == "COMBINED":
            print(
                f"[MAIL][{k}] "
                f"sent={v.get('sent')}, "
                f"rows={v.get('row_count')}, "
                f"aoi_count={v.get('aoi_count')}, "
                f"inspection_count={v.get('inspection_count')}, "
                f"status_code={v.get('status_code')}, "
                f"updated_aoi_rows={v.get('updated_aoi_rows')}, "
                f"updated_inspection_rows={v.get('updated_inspection_rows')}"
            )
        else:
            print(
                f"[MAIL][{k}] "
                f"sent={v.get('sent')}, "
                f"rows={v.get('row_count')}, "
                f"status_code={v.get('status_code')}, "
                f"updated_rows={v.get('updated_rows')}"
            )


if __name__ == "__main__":
    main()

"""
python mail_alert.py --date 2026-06-04 --combined-mail
"""