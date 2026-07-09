#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import sys
import time
import argparse
import logging
from logging.handlers import TimedRotatingFileHandler
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import create_engine, text, inspect

from sql_db_connect import MySQLConnet


# =============================================================================
# Logging
# =============================================================================
def setup_logging(
    log_dir: str = "logs",
    log_name: str = "repair_cim_pi_glass_trans_job.txt",
):
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, log_name)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    if logger.handlers:
        for h in list(logger.handlers):
            logger.removeHandler(h)

    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    fh = TimedRotatingFileHandler(
        filename=log_path,
        when="midnight",
        interval=1,
        backupCount=92,
        encoding="utf-8",
        utc=False,
    )
    fh.suffix = "%Y-%m-%d"
    fh.setFormatter(fmt)
    fh.setLevel(logging.INFO)

    sh = logging.StreamHandler(stream=sys.stdout)
    sh.setFormatter(fmt)
    sh.setLevel(logging.INFO)

    logger.addHandler(fh)
    logger.addHandler(sh)


# =============================================================================
# Config
# =============================================================================
@dataclass
class Config:
    user_name: str = "L6AINT_AP"
    passwd: str = "L6AINT$AP"
    port: str = "1549"
    host: str = "TCPPA104"
    service_name: str = "L6AHSHA"

    SQL_DBNAME: str = "cim_piaoi"
    SUMMARY_PREFIX: str = "cim_pi_glass"
    DEFECT_PREFIX: str = "cim_defect"

    TRANS_TBN: str = "celods.h_chip_trans_ods"
    OP_LIKE: str = "PI PRINT_%"
    TRANS_ID: str = "LOGF"

    ORACLE_IN_BATCH: int = 900

    @property
    def ORACLE_URL(self) -> str:
        return (
            f"oracle+cx_oracle://{self.user_name}:{self.passwd}"
            f"@{self.host}:{self.port}/?service_name={self.service_name}"
        )


AOI_MAP = {
    "CAPIT203": "aoi100",
    "CAAOI202": "aoi200",
    "CAAOI300": "aoi300",
    "aoi100": "aoi100",
    "aoi200": "aoi200",
    "aoi300": "aoi300",
}

EMPTY_STRINGS = {
    "",
    "nan",
    "nat",
    "none",
    "null",
    "NaN",
    "NaT",
    "None",
    "NULL",
}


# =============================================================================
# Helpers
# =============================================================================
def q(name: str) -> str:
    return f"`{name}`"


def table_exists(db: MySQLConnet, table_name: str) -> bool:
    return inspect(db.engine).has_table(table_name)


def get_columns(db: MySQLConnet, table_name: str) -> set[str]:
    if not table_exists(db, table_name):
        return set()
    return {c["name"] for c in inspect(db.engine).get_columns(table_name)}


def normalize_aoi(aoi: Any) -> str:
    s = "" if aoi is None else str(aoi).strip()
    return AOI_MAP.get(s, "aoi000")


def normalize_line_id(v: Any) -> str:
    if v is None:
        return "pi000"

    s = str(v).strip()

    if s in EMPTY_STRINGS:
        return "pi000"

    return s


def calc_pi_hour(pi_time: Any) -> Optional[pd.Timestamp]:
    dt = pd.to_datetime(pi_time, errors="coerce")

    if pd.isna(dt):
        return None

    return (dt - pd.Timedelta(minutes=30)).floor("h")


def is_bad_pi_time_value(v: Any) -> bool:
    dt = pd.to_datetime(v, errors="coerce")

    if pd.isna(dt):
        return True

    if dt < pd.Timestamp("2000-01-01"):
        return True

    if dt > pd.Timestamp.now() + pd.Timedelta(days=1):
        return True

    return False


def is_bad_pi_time_expr(col: str = "pi_time") -> str:
    return f"""
    (
        {q(col)} IS NULL
        OR CAST({q(col)} AS CHAR) IN ('0000-00-00 00:00:00', '0000-00-00')
        OR {q(col)} < '2000-01-01'
        OR {q(col)} > DATE_ADD(NOW(), INTERVAL 1 DAY)
    )
    """


def is_bad_line_expr(col: str = "line_id") -> str:
    return f"""
    (
        {q(col)} IS NULL
        OR TRIM(CAST({q(col)} AS CHAR)) IN ('', 'nan', 'NaN', 'nat', 'NaT', 'none', 'None', 'null', 'NULL')
        OR TRIM(CAST({q(col)} AS CHAR)) = 'pi000'
    )
    """


def compute_pi_type(
    aoi: Any,
    recipe_id: Any,
    test_time: Any,
    pi_time: Any,
) -> str:
    """
    對齊 RUN_CIM_PULL_10MIN.py 的 add_pi_type 規則。

    aoi100 / CAPIT203:
        test_time < pi_time  -> BPI
        test_time >= pi_time -> API

    aoi200 / CAAOI202:
        recipe_id 第一碼 0/1/2/3 -> API
        recipe_id 第一碼 4/5     -> BPI

    aoi300 / CAAOI300:
        test_time < pi_time  -> BPI
        test_time >= pi_time -> API
    """
    aoi_s = "" if aoi is None else str(aoi).strip()
    recipe = "" if recipe_id is None else str(recipe_id).strip()

    test_dt = pd.to_datetime(test_time, errors="coerce")
    pi_dt = pd.to_datetime(pi_time, errors="coerce")

    if aoi_s in ("CAPIT203", "aoi100"):
        if pd.isna(test_dt) or pd.isna(pi_dt):
            return "OTHER"
        return "BPI" if test_dt < pi_dt else "API"

    if aoi_s in ("CAAOI202", "aoi200"):
        first = recipe[:1]

        if first in ("0", "1", "2", "3"):
            return "API"

        if first in ("4", "5"):
            return "BPI"

        return "OTHER"

    if aoi_s in ("CAAOI300", "aoi300"):
        if pd.isna(test_dt) or pd.isna(pi_dt):
            return "OTHER"
        return "BPI" if test_dt < pi_dt else "API"

    return "OTHER"


def target_summary_table(pi_time: Any) -> str:
    dt = pd.to_datetime(pi_time, errors="coerce")

    if pd.isna(dt):
        yyyymm = datetime.now().strftime("%Y") + "00"
    else:
        yyyymm = dt.strftime("%Y%m")

    return f"cim_pi_glass_{yyyymm}".lower()


def target_defect_table(
    base_prefix: str,
    test_time: Any,
    aoi: Any,
    line_id: Any,
) -> str:
    dt = pd.to_datetime(test_time, errors="coerce")

    if pd.isna(dt):
        yyyymm = datetime.now().strftime("%Y") + "00"
    else:
        yyyymm = dt.strftime("%Y%m")

    return (
        f"{base_prefix}_{yyyymm}_{normalize_aoi(aoi)}_{normalize_line_id(line_id)}"
    ).lower()


def parse_month_to_yyyymm(month: str) -> str:
    s = str(month).strip()

    if "-" in s:
        return pd.to_datetime(s + "-01", errors="raise").strftime("%Y%m")

    if len(s) == 6 and s.isdigit():
        return s

    raise ValueError(f"Invalid --month: {month}, expected 2026-05 or 202605")


def resolve_date_range(args) -> Tuple[Optional[pd.Timestamp], Optional[pd.Timestamp]]:
    if args.recent_days is not None:
        end_dt = pd.Timestamp.now().normalize() + pd.Timedelta(days=1)
        start_dt = end_dt - pd.Timedelta(days=int(args.recent_days))
        return start_dt, end_dt

    if args.start_date and args.end_date:
        start_dt = pd.to_datetime(args.start_date, errors="raise")
        end_dt = pd.to_datetime(args.end_date, errors="raise") + pd.Timedelta(days=1)
        return start_dt, end_dt

    if args.month:
        yyyymm = parse_month_to_yyyymm(args.month)
        start_dt = pd.to_datetime(yyyymm + "01", format="%Y%m%d")
        end_dt = start_dt + pd.offsets.MonthBegin(1)
        return start_dt, end_dt

    if args.year:
        start_dt = pd.Timestamp(year=int(args.year), month=1, day=1)
        end_dt = pd.Timestamp(year=int(args.year) + 1, month=1, day=1)
        return start_dt, end_dt

    return None, None


def build_summary_tables_by_range(
    db: MySQLConnet,
    *,
    start_dt: Optional[pd.Timestamp],
    end_dt: Optional[pd.Timestamp],
) -> List[str]:
    insp = inspect(db.engine)

    if start_dt is None or end_dt is None:
        y = datetime.now().year
        candidates = [f"cim_pi_glass_{y}{m:02d}" for m in range(1, 13)]
        candidates.append(f"cim_pi_glass_{y}00")
    else:
        months = pd.period_range(
            start=start_dt.to_period("M"),
            end=(end_dt - pd.Timedelta(days=1)).to_period("M"),
            freq="M",
        )

        candidates = [f"cim_pi_glass_{p.strftime('%Y%m')}" for p in months]

        for y in sorted({p.year for p in months}):
            candidates.append(f"cim_pi_glass_{y}00")

    out = []

    for t in sorted(set([v.lower() for v in candidates])):
        if insp.has_table(t):
            out.append(t)

    return out


def build_test_time_filter_sql(
    start_dt: Optional[pd.Timestamp],
    end_dt: Optional[pd.Timestamp],
) -> Tuple[str, Dict[str, Any]]:
    if start_dt is None or end_dt is None:
        return "", {}

    return """
      AND test_time >= :range_start_dt
      AND test_time <  :range_end_dt
    """, {
        "range_start_dt": start_dt.to_pydatetime(),
        "range_end_dt": end_dt.to_pydatetime(),
    }


def to_pydt_or_none(v: Any):
    dt = pd.to_datetime(v, errors="coerce")

    if pd.isna(dt):
        return None

    return dt.to_pydatetime()


def pi_time_changed(old_value: Any, new_value: Any) -> bool:
    old_dt = pd.to_datetime(old_value, errors="coerce")
    new_dt = pd.to_datetime(new_value, errors="coerce")

    if pd.isna(old_dt) and pd.isna(new_dt):
        return False

    if pd.isna(old_dt) != pd.isna(new_dt):
        return True

    return old_dt != new_dt


# =============================================================================
# Oracle
# =============================================================================
class OracleTransClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.engine = create_engine(cfg.ORACLE_URL)

    def fetch_latest_trans(self, glass_ids: List[str]) -> pd.DataFrame:
        """
        對齊 RUN_CIM_PULL_10MIN.py 的 fetch_trans_ods_for_glass_ids 邏輯。

        來源：
            celods.h_chip_trans_ods

        條件：
            sheet_id_chip_id IN (...)
            op_id LIKE 'PI PRINT_%'
            trans_id = 'LOGF'

        規則：
            每片取最新 trans_timestamp。
            line_id 空值補 pi000。
        """
        if not glass_ids:
            return pd.DataFrame(columns=["sheet_id_chip_id", "line_id", "pi_time"])

        clean_ids = (
            pd.Series(glass_ids)
            .dropna()
            .astype(str)
            .str.strip()
        )
        clean_ids = clean_ids[clean_ids.ne("")]
        clean_ids = clean_ids.drop_duplicates().tolist()

        if not clean_ids:
            return pd.DataFrame(columns=["sheet_id_chip_id", "line_id", "pi_time"])

        out_chunks: List[pd.DataFrame] = []

        with self.engine.connect() as conn:
            for i in range(0, len(clean_ids), self.cfg.ORACLE_IN_BATCH):
                batch = clean_ids[i:i + self.cfg.ORACLE_IN_BATCH]

                bind = {f"g{j}": v for j, v in enumerate(batch)}
                in_clause = ", ".join([f":g{j}" for j in range(len(batch))])

                sql = f"""
                SELECT
                    sheet_id_chip_id AS sheet_id_chip_id,
                    eqp_id AS line_id,
                    trans_timestamp AS pi_time,
                    op_id,
                    trans_id
                FROM {self.cfg.TRANS_TBN}
                WHERE sheet_id_chip_id IN ({in_clause})
                  AND op_id LIKE :op_like
                  AND trans_id = :trans_id
                """

                params = dict(bind)
                params.update({
                    "op_like": self.cfg.OP_LIKE,
                    "trans_id": self.cfg.TRANS_ID,
                })

                df = pd.read_sql(text(sql), conn, params=params)
                out_chunks.append(df)

        if not out_chunks:
            return pd.DataFrame(columns=["sheet_id_chip_id", "line_id", "pi_time"])

        df = pd.concat(out_chunks, ignore_index=True)

        if df.empty:
            logging.info(
                f"[oracle_trans] input_glass={len(clean_ids)} found_glass=0 rows=0"
            )
            return pd.DataFrame(columns=["sheet_id_chip_id", "line_id", "pi_time"])

        df.columns = [str(c).lower() for c in df.columns]

        required_cols = {"sheet_id_chip_id", "line_id", "pi_time"}
        missing_cols = required_cols - set(df.columns)

        if missing_cols:
            logging.warning(
                f"[oracle_trans] missing columns={missing_cols}, columns={list(df.columns)}"
            )
            return pd.DataFrame(columns=["sheet_id_chip_id", "line_id", "pi_time"])

        df["sheet_id_chip_id"] = df["sheet_id_chip_id"].astype(str).str.strip()
        df["pi_time"] = pd.to_datetime(df["pi_time"], errors="coerce")

        df["line_id"] = df["line_id"].astype("string").fillna("pi000").str.strip()
        df.loc[df["line_id"].eq(""), "line_id"] = "pi000"

        df = df.dropna(subset=["sheet_id_chip_id"])
        df = df[df["sheet_id_chip_id"].ne("")]

        # 與 RUN_CIM_PULL_10MIN.py 一致：每片取最新 PI PRINT LOGF。
        df = (
            df.sort_values(["sheet_id_chip_id", "pi_time"])
              .drop_duplicates(["sheet_id_chip_id"], keep="last")
        )

        logging.info(
            f"[oracle_trans] input_glass={len(clean_ids)} "
            f"found_glass={df['sheet_id_chip_id'].nunique()} rows={len(df)}"
        )

        return df[["sheet_id_chip_id", "line_id", "pi_time"]]


# =============================================================================
# Repair Job
# =============================================================================
class RepairJob:
    def __init__(self, cfg: Config, dry_run: bool = True):
        self.cfg = cfg
        self.dry_run = dry_run
        self.db = MySQLConnet(cfg.SQL_DBNAME)
        self.oracle = OracleTransClient(cfg)

    def fetch_bad_summary_rows(
        self,
        table_name: str,
        *,
        older_than_min: int,
        limit: int,
        start_dt: Optional[pd.Timestamp] = None,
        end_dt: Optional[pd.Timestamp] = None,
    ) -> pd.DataFrame:
        cols = get_columns(self.db, table_name)

        required = {
            "sheet_id_chip_id",
            "test_time",
            "aoi",
            "recipe_id",
            "line_id",
            "pi_time",
        }

        if not required.issubset(cols):
            logging.warning(
                f"[skip] {table_name} missing required columns: {required - cols}"
            )
            return pd.DataFrame()

        range_sql, range_params = build_test_time_filter_sql(start_dt, end_dt)

        sql = text(f"""
            SELECT *
            FROM {q(table_name)}
            WHERE (
                {is_bad_line_expr('line_id')}
                OR {is_bad_pi_time_expr('pi_time')}
            )
            AND {q('test_time')} < DATE_SUB(NOW(), INTERVAL :older_than_min MINUTE)
            {range_sql}
            ORDER BY test_time ASC
            LIMIT :limit
        """)

        params = {
            "older_than_min": older_than_min,
            "limit": limit,
        }
        params.update(range_params)

        with self.db.engine.begin() as conn:
            return pd.read_sql(sql, conn, params=params)

    def update_summary_row(
        self,
        table_name: str,
        row: pd.Series,
        new_line_id: Optional[str],
        new_pi_time: Optional[pd.Timestamp],
    ):
        sheet_id = str(row["sheet_id_chip_id"]).strip()
        test_time = pd.to_datetime(row["test_time"], errors="coerce")

        old_line_id = normalize_line_id(row.get("line_id"))
        old_pi_time = pd.to_datetime(row.get("pi_time"), errors="coerce")

        final_line_id = old_line_id
        final_pi_time = old_pi_time

        update_fields: Dict[str, Any] = {}

        # 只有原本 line_id 壞掉時才更新 line_id。
        if old_line_id == "pi000" and new_line_id is not None:
            new_line = normalize_line_id(new_line_id)

            if new_line != "pi000":
                final_line_id = new_line
                update_fields["line_id"] = final_line_id

        # 只有原本 pi_time 壞掉時才更新 pi_time。
        if is_bad_pi_time_value(old_pi_time) and new_pi_time is not None:
            new_pi_time_dt = pd.to_datetime(new_pi_time, errors="coerce")

            if not pd.isna(new_pi_time_dt):
                final_pi_time = new_pi_time_dt
                update_fields["pi_time"] = final_pi_time.to_pydatetime()

                ph = calc_pi_hour(final_pi_time)
                update_fields["pi_hour"] = None if ph is None else ph.to_pydatetime()

        final_pi_type = compute_pi_type(
            row.get("aoi"),
            row.get("recipe_id"),
            test_time,
            final_pi_time,
        )
        update_fields["pi_type"] = final_pi_type

        if not update_fields:
            return old_line_id, old_pi_time, final_line_id, final_pi_time, final_pi_type

        set_sql = ", ".join([f"{q(k)} = :{k}" for k in update_fields.keys()])

        sql = text(f"""
            UPDATE {q(table_name)}
            SET {set_sql}
            WHERE sheet_id_chip_id = :sheet_id_chip_id
              AND test_time = :test_time
        """)

        params = dict(update_fields)
        params.update({
            "sheet_id_chip_id": sheet_id,
            "test_time": None if pd.isna(test_time) else test_time.to_pydatetime(),
        })

        logging.info(
            f"[summary_update] {table_name} glass={sheet_id} test_time={test_time} "
            f"old_line_id={old_line_id} final_line_id={final_line_id} "
            f"old_pi_time={old_pi_time} final_pi_time={final_pi_time} "
            f"final_pi_type={final_pi_type} fields={update_fields}"
        )

        if not self.dry_run:
            with self.db.engine.begin() as conn:
                conn.execute(sql, params)

        return old_line_id, old_pi_time, final_line_id, final_pi_time, final_pi_type

    def delete_summary_key(
        self,
        table_name: str,
        sheet_id: Any,
        test_time: Any,
    ) -> int:
        if not table_exists(self.db, table_name):
            return 0

        test_dt = pd.to_datetime(test_time, errors="coerce")
        if pd.isna(test_dt):
            logging.warning(
                f"[summary_delete_skip] invalid test_time table={table_name} "
                f"glass={sheet_id} test_time={test_time}"
            )
            return 0

        sql = text(f"""
            DELETE FROM {q(table_name)}
            WHERE sheet_id_chip_id = :sheet_id_chip_id
              AND test_time = :test_time
        """)

        logging.info(
            f"[summary_delete_target_key] {table_name} glass={sheet_id} test_time={test_dt}"
        )

        with self.db.engine.begin() as conn:
            res = conn.execute(sql, {
                "sheet_id_chip_id": str(sheet_id).strip(),
                "test_time": test_dt.to_pydatetime(),
            })

        return int(res.rowcount or 0)

    def move_summary_if_needed(
        self,
        src_table: str,
        original_row: pd.Series,
        final_line_id: str,
        final_pi_time: Any,
        final_pi_type: Optional[str],
    ):
        final_pi_time_dt = pd.to_datetime(final_pi_time, errors="coerce")

        if pd.isna(final_pi_time_dt):
            return src_table

        target_tbn = target_summary_table(final_pi_time_dt)

        if target_tbn == src_table:
            return src_table

        row_df = pd.DataFrame([original_row.to_dict()])

        row_df["line_id"] = final_line_id
        row_df["pi_time"] = final_pi_time_dt
        row_df["pi_hour"] = calc_pi_hour(final_pi_time_dt)
        row_df["pi_type"] = final_pi_type or row_df.apply(
            lambda r: compute_pi_type(
                r.get("aoi"),
                r.get("recipe_id"),
                r.get("test_time"),
                r.get("pi_time"),
            ),
            axis=1,
        )

        logging.info(
            f"[summary_move] {src_table} -> {target_tbn} "
            f"glass={original_row.get('sheet_id_chip_id')} "
            f"test_time={original_row.get('test_time')} "
            f"line_id={final_line_id} pi_time={final_pi_time_dt} pi_type={row_df['pi_type'].iloc[0]}"
        )

        if not self.dry_run:
            # append_or_create_dedup 是 append-only，不會覆蓋。
            # repair 需要以修復後資料為準，因此 target 若已有同 key，要先刪除再插入。
            self.delete_summary_key(
                target_tbn,
                original_row.get("sheet_id_chip_id"),
                original_row.get("test_time"),
            )

            self.db.append_or_create_dedup(
                table_name=target_tbn,
                df=row_df,
                dedup_keys=["sheet_id_chip_id", "test_time"],
            )

            delete_sql = text(f"""
                DELETE FROM {q(src_table)}
                WHERE sheet_id_chip_id = :sheet_id_chip_id
                  AND test_time = :test_time
            """)

            with self.db.engine.begin() as conn:
                conn.execute(delete_sql, {
                    "sheet_id_chip_id": original_row.get("sheet_id_chip_id"),
                    "test_time": pd.to_datetime(
                        original_row.get("test_time")
                    ).to_pydatetime(),
                })

        return target_tbn

    def find_source_defect_tables(
        self,
        row: pd.Series,
        final_line_id: Optional[str] = None,
    ) -> List[str]:
        """
        defect 表命名規則：
            cim_defect_yyyymm_aoiXXX_piYYY

        新版 RUN_CIM_PULL_10MIN.py 會將 aoi / line_id 從 defect df drop 掉，
        所以 repair 搬 defect 時，主要依靠 table name，而不是欄位內容。
        """
        test_time = pd.to_datetime(row.get("test_time"), errors="coerce")

        if pd.isna(test_time):
            yyyymm = datetime.now().strftime("%Y") + "00"
        else:
            yyyymm = test_time.strftime("%Y%m")

        aoi_norm = normalize_aoi(row.get("aoi"))
        old_line = normalize_line_id(row.get("line_id"))
        final_line = normalize_line_id(final_line_id) if final_line_id else None

        candidate_lines: List[str] = []

        for line in [old_line, "pi000", final_line]:
            if line and line not in candidate_lines:
                candidate_lines.append(line)

        candidates = [
            f"{self.cfg.DEFECT_PREFIX}_{yyyymm}_{aoi_norm}_{line}".lower()
            for line in candidate_lines
        ]

        out: List[str] = []

        for t in candidates:
            if t not in out and table_exists(self.db, t):
                out.append(t)

        return out

    def move_defects_for_row(
        self,
        row: pd.Series,
        final_line_id: str,
        final_pi_time: Any,
        final_pi_type: Optional[str],
    ):
        sheet_id = str(row["sheet_id_chip_id"]).strip()
        test_time = pd.to_datetime(row["test_time"], errors="coerce")

        if pd.isna(test_time):
            logging.warning(f"[defect_skip] invalid test_time glass={sheet_id}")
            return

        target_tbn = target_defect_table(
            self.cfg.DEFECT_PREFIX,
            test_time,
            row.get("aoi"),
            final_line_id,
        )

        source_tbns = self.find_source_defect_tables(
            row,
            final_line_id=final_line_id,
        )

        if not source_tbns:
            logging.info(
                f"[defect] no source tables found glass={sheet_id} test_time={test_time} "
                f"target_tbn={target_tbn}"
            )
            return

        final_pi_hour = calc_pi_hour(final_pi_time)

        if final_pi_type is None:
            final_pi_type = compute_pi_type(
                row.get("aoi"),
                row.get("recipe_id"),
                test_time,
                final_pi_time,
            )

        for src_tbn in source_tbns:
            if src_tbn == target_tbn:
                self.update_defect_in_place(
                    table_name=src_tbn,
                    sheet_id=sheet_id,
                    test_time=test_time,
                    aoi=row.get("aoi"),
                    line_id=final_line_id,
                    pi_time=final_pi_time,
                    pi_hour=final_pi_hour,
                    pi_type=final_pi_type,
                )
                continue

            df = self.read_defects(src_tbn, sheet_id, test_time)

            if df.empty:
                continue

            logging.info(
                f"[defect_move] glass={sheet_id} test_time={test_time} "
                f"{src_tbn} -> {target_tbn} rows={len(df)} "
                f"line_id={final_line_id} pi_time={final_pi_time} pi_type={final_pi_type}"
            )

            df = self.patch_defect_df(
                df=df,
                aoi=row.get("aoi"),
                line_id=final_line_id,
                pi_time=final_pi_time,
                pi_hour=final_pi_hour,
                pi_type=final_pi_type,
            )

            if not self.dry_run:
                # repair 搬 defect 時，以修正後資料為準。
                # target 若已有相同 glass + test_time 的舊資料，先刪除，避免 append-only 無法覆蓋。
                self.delete_defects_if_table_exists(target_tbn, sheet_id, test_time)

                self.db.append_or_create_dedup(
                    table_name=target_tbn,
                    df=df,
                    dedup_keys=self.get_defect_dedup_keys(df),
                )

                self.delete_defects(src_tbn, sheet_id, test_time)

    def read_defects(
        self,
        table_name: str,
        sheet_id: str,
        test_time: pd.Timestamp,
    ) -> pd.DataFrame:
        sql = text(f"""
            SELECT *
            FROM {q(table_name)}
            WHERE sheet_id_chip_id = :sheet_id
              AND test_time = :test_time
        """)

        with self.db.engine.begin() as conn:
            return pd.read_sql(sql, conn, params={
                "sheet_id": sheet_id,
                "test_time": test_time.to_pydatetime(),
            })

    def patch_defect_df(
        self,
        df: pd.DataFrame,
        aoi: Any,
        line_id: str,
        pi_time: Any,
        pi_hour: Any,
        pi_type: Optional[str],
    ) -> pd.DataFrame:
        """
        新版 defect table 可能不含 aoi / line_id 欄位。
        因此只在欄位存在時 patch。
        """
        out = df.copy()

        if "aoi" in out.columns:
            out["aoi"] = aoi

        if "line_id" in out.columns:
            out["line_id"] = line_id

        if "pi_time" in out.columns:
            out["pi_time"] = pd.to_datetime(pi_time, errors="coerce")

        if "pi_hour" in out.columns:
            out["pi_hour"] = pd.to_datetime(pi_hour, errors="coerce")

        if "pi_type" in out.columns:
            out["pi_type"] = pi_type

        return out

    def update_defect_in_place(
        self,
        table_name: str,
        sheet_id: str,
        test_time: pd.Timestamp,
        aoi: Any,
        line_id: str,
        pi_time: Any,
        pi_hour: Any,
        pi_type: Optional[str],
    ):
        cols = get_columns(self.db, table_name)

        update_fields: Dict[str, Any] = {}

        if "aoi" in cols:
            update_fields["aoi"] = aoi

        if "line_id" in cols:
            update_fields["line_id"] = line_id

        if "pi_time" in cols:
            update_fields["pi_time"] = to_pydt_or_none(pi_time)

        if "pi_hour" in cols:
            update_fields["pi_hour"] = to_pydt_or_none(pi_hour)

        if "pi_type" in cols:
            update_fields["pi_type"] = pi_type

        if not update_fields:
            logging.info(
                f"[defect_update_in_place] {table_name} no patchable columns "
                f"glass={sheet_id} test_time={test_time}"
            )
            return

        set_sql = ", ".join([f"{q(k)} = :{k}" for k in update_fields.keys()])

        sql = text(f"""
            UPDATE {q(table_name)}
            SET {set_sql}
            WHERE sheet_id_chip_id = :sheet_id
              AND test_time = :test_time
        """)

        params = dict(update_fields)
        params.update({
            "sheet_id": sheet_id,
            "test_time": test_time.to_pydatetime(),
        })

        logging.info(
            f"[defect_update_in_place] {table_name} glass={sheet_id} "
            f"test_time={test_time} fields={update_fields}"
        )

        if not self.dry_run:
            with self.db.engine.begin() as conn:
                conn.execute(sql, params)

    def delete_defects_if_table_exists(
        self,
        table_name: str,
        sheet_id: str,
        test_time: pd.Timestamp,
    ) -> int:
        if not table_exists(self.db, table_name):
            return 0

        return self.delete_defects(table_name, sheet_id, test_time)

    def delete_defects(
        self,
        table_name: str,
        sheet_id: str,
        test_time: pd.Timestamp,
    ) -> int:
        sql = text(f"""
            DELETE FROM {q(table_name)}
            WHERE sheet_id_chip_id = :sheet_id
              AND test_time = :test_time
        """)

        logging.info(
            f"[defect_delete] {table_name} glass={sheet_id} test_time={test_time}"
        )

        with self.db.engine.begin() as conn:
            res = conn.execute(sql, {
                "sheet_id": sheet_id,
                "test_time": test_time.to_pydatetime(),
            })

        return int(res.rowcount or 0)

    def get_defect_dedup_keys(self, df: pd.DataFrame) -> List[str]:
        """
        與 RUN_CIM_PULL_10MIN.py 新版 defect dedup 邏輯一致。

        若有 defect_seq_no：
            sheet_id_chip_id + test_time + chip_id + defect_seq_no

        若沒有 defect_seq_no：
            sheet_id_chip_id + test_time + chip_id + pox_x1 + pox_y1 + image_file_name
        """
        if df is None or df.empty:
            return []

        if "defect_seq_no" in df.columns:
            return [
                c for c in [
                    "sheet_id_chip_id",
                    "test_time",
                    "chip_id",
                    "defect_seq_no",
                ]
                if c in df.columns
            ]

        return [
            c for c in [
                "sheet_id_chip_id",
                "test_time",
                "chip_id",
                "pox_x1",
                "pox_y1",
                "image_file_name",
            ]
            if c in df.columns
        ]

    def run_once(
        self,
        *,
        older_than_min: int,
        limit_per_table: int,
        start_dt: Optional[pd.Timestamp] = None,
        end_dt: Optional[pd.Timestamp] = None,
    ):
        summary_tbns = build_summary_tables_by_range(
            self.db,
            start_dt=start_dt,
            end_dt=end_dt,
        )

        logging.info(
            f"[run_once] summary_tables={summary_tbns} "
            f"dry_run={self.dry_run} start_dt={start_dt} end_dt={end_dt}"
        )

        if not summary_tbns:
            logging.info("[run_once] no summary tables found")
            return

        for tbn in summary_tbns:
            bad_df = self.fetch_bad_summary_rows(
                tbn,
                older_than_min=older_than_min,
                limit=limit_per_table,
                start_dt=start_dt,
                end_dt=end_dt,
            )

            if bad_df.empty:
                logging.info(f"[scan] {tbn} no bad rows")
                continue

            logging.info(f"[scan] {tbn} bad_rows={len(bad_df)}")

            glass_ids = (
                bad_df["sheet_id_chip_id"]
                .dropna()
                .astype(str)
                .str.strip()
                .drop_duplicates()
                .tolist()
            )

            trans_df = self.oracle.fetch_latest_trans(glass_ids)

            if trans_df.empty:
                logging.info(
                    f"[oracle] {tbn} no trans found for glass_count={len(glass_ids)}"
                )
                logging.info(
                    f"[oracle] {tbn} sample_missing_glass={glass_ids[:20]}"
                )
                continue

            found_ids = set(trans_df["sheet_id_chip_id"].astype(str))
            missing_ids = [g for g in glass_ids if str(g) not in found_ids]

            if missing_ids:
                logging.info(
                    f"[oracle] {tbn} missing_trans_count={len(missing_ids)} "
                    f"sample={missing_ids[:20]}"
                )

            trans_map = {
                str(r["sheet_id_chip_id"]): r
                for _, r in trans_df.iterrows()
            }

            for _, row in bad_df.iterrows():
                sheet_id = str(row["sheet_id_chip_id"]).strip()
                trans = trans_map.get(sheet_id)

                if trans is None:
                    continue

                new_line_id = trans.get("line_id")
                new_pi_time = trans.get("pi_time")

                has_line = (
                    new_line_id is not None
                    and normalize_line_id(new_line_id) != "pi000"
                )

                has_pi_time = (
                    new_pi_time is not None
                    and not pd.isna(pd.to_datetime(new_pi_time, errors="coerce"))
                )

                if not has_line and not has_pi_time:
                    logging.info(
                        f"[skip] glass={sheet_id} oracle line_id/pi_time still invalid "
                        f"new_line_id={new_line_id} new_pi_time={new_pi_time}"
                    )
                    continue

                old_line_id, old_pi_time, final_line_id, final_pi_time, final_pi_type = (
                    self.update_summary_row(
                        tbn,
                        row,
                        new_line_id=new_line_id if has_line else None,
                        new_pi_time=new_pi_time if has_pi_time else None,
                    )
                )

                self.move_summary_if_needed(
                    src_table=tbn,
                    original_row=row,
                    final_line_id=final_line_id,
                    final_pi_time=final_pi_time,
                    final_pi_type=final_pi_type,
                )

                should_move_or_patch_defect = (
                    normalize_line_id(old_line_id) != normalize_line_id(final_line_id)
                    or pi_time_changed(old_pi_time, final_pi_time)
                )

                if should_move_or_patch_defect:
                    self.move_defects_for_row(
                        row,
                        final_line_id=final_line_id,
                        final_pi_time=final_pi_time,
                        final_pi_type=final_pi_type,
                    )


# =============================================================================
# Main
# =============================================================================
def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once then exit.",
    )
    parser.add_argument(
        "--every-min",
        type=int,
        default=60,
        help="Loop interval minutes.",
    )
    parser.add_argument(
        "--older-than-min",
        type=int,
        default=180,
        help="Only repair rows older than N minutes.",
    )
    parser.add_argument(
        "--limit-per-table",
        type=int,
        default=50000,
        help="Max rows per summary table per run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only, do not update/delete/insert.",
    )

    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Repair specific year, e.g. 2026.",
    )
    parser.add_argument(
        "--month",
        type=str,
        default=None,
        help="Repair specific month, e.g. 2026-05 or 202605.",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Repair start date, e.g. 2026-05-01.",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="Repair end date, e.g. 2026-05-07.",
    )
    parser.add_argument(
        "--recent-days",
        type=int,
        default=None,
        help="Repair recent N days.",
    )

    args = parser.parse_args()

    setup_logging()

    start_dt, end_dt = resolve_date_range(args)

    cfg = Config()
    job = RepairJob(cfg, dry_run=args.dry_run)

    logging.info(
        f"=== repair job start dry_run={args.dry_run} "
        f"older_than_min={args.older_than_min} "
        f"limit_per_table={args.limit_per_table} "
        f"start_dt={start_dt} end_dt={end_dt} ==="
    )

    if args.once:
        job.run_once(
            older_than_min=args.older_than_min,
            limit_per_table=args.limit_per_table,
            start_dt=start_dt,
            end_dt=end_dt,
        )
        logging.info("=== repair job end once ===")
        return

    every_sec = max(1, args.every_min * 60)

    while True:
        t0 = time.time()

        try:
            job.run_once(
                older_than_min=args.older_than_min,
                limit_per_table=args.limit_per_table,
                start_dt=start_dt,
                end_dt=end_dt,
            )
        except Exception:
            logging.exception("[loop] repair failed")

        elapsed = time.time() - t0
        sleep_sec = max(0, every_sec - elapsed)
        time.sleep(sleep_sec)


if __name__ == "__main__":
    main()


"""
建議執行方式：

1) 先 dry-run 看修復內容：
python repair_cim_pi_glass_trans_job.py --once --month 2026-06 --dry-run

2) 確認 log 沒問題後實際修復：
python repair_cim_pi_glass_trans_job.py --once --month 2026-04

3) 指定日期區間：
python repair_cim_pi_glass_trans_job.py --once --start-date 2026-05-01 --end-date 2026-05-07 --dry-run

4) 修近 7 天：
python repair_cim_pi_glass_trans_job.py --once --recent-days 7 --dry-run

5) 週期執行，每 60 分鐘修一次：
python repair_cim_pi_glass_trans_job.py --every-min 60 --recent-days 7

6) 建議正式週期排程：
python repair_cim_pi_glass_trans_job.py --every-min 60 --recent-days 7 --older-than-min 180
"""