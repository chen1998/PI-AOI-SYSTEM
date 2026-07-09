from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


ROOT = Path(__file__).resolve().parents[2]
MYSQL_BASE = Path(r"C:\Program Files\MySQL\MySQL Server 8.4")
MYSQLD = MYSQL_BASE / "bin" / "mysqld.exe"
MYSQL = MYSQL_BASE / "bin" / "mysql.exe"
MYSQLADMIN = MYSQL_BASE / "bin" / "mysqladmin.exe"
DATA_DIR = ROOT / "mock_mysql" / "data"
RUN_DIR = ROOT / "mock_mysql" / "run"

HOST = "127.0.0.1"
PORT = 3307
USER = "root"
PASSWORD = os.getenv("PI_MOCK_MYSQL_PASSWORD") or os.getenv("PI_MYSQL_PASSWORD") or ""
YYYYMM = "202607"
RUN_DAY = "2026-07-09"
BASE_TS = "2026-07-09 08:00:00"


def quote_ident(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def column_type(col: str) -> str:
    c = col.lower()
    if c in {"hour_label"}:
        return "varchar(255)"
    if c in {"comment", "action", "editor", "drop"}:
        return "varchar(255)"
    if c in {"hour_int", "hour_sort", "hour", "cumu", "real_hour_capa", "real_cumu_capa"}:
        return "double"
    if any(k in c for k in ["json", "detail", "list", "glass", "img", "pic", "url", "path"]):
        return "longtext"
    if c in {"run_day", "shift_day"}:
        return "date"
    if any(k in c for k in ["time", "hour", "modify", "shift_start", "shift_end", "gen_dt"]):
        return "datetime"
    if c in {"x", "y", "dx", "dy", "bpi_x", "bpi_y", "api_x", "api_y"}:
        return "double"
    if any(
        k in c
        for k in [
            "count",
            "cnt",
            "density",
            "rate",
            "offset",
            "distance",
            "rank",
            "sort",
            "spec",
            "capa",
            "qty",
            "total",
            "target",
            "hour_int",
            "hour",
            "cumu",
        ]
    ):
        return "double"
    return "varchar(255)"


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    text = text.replace("\\", "\\\\").replace("'", "''")
    return f"'{text}'"


def bind_sql(sql: str, params: Sequence[Any] | None = None) -> str:
    if not params:
        return sql
    out = sql
    for value in params:
        out = out.replace("%s", sql_literal(value), 1)
    return out


class ScriptCursor:
    def __init__(self) -> None:
        self.statements: List[str] = []

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> None:
        self.statements.append(bind_sql(sql, params).rstrip().rstrip(";") + ";")

    def executemany(self, sql: str, rows: Iterable[Sequence[Any]]) -> None:
        for row in rows:
            self.execute(sql, row)

    def text(self) -> str:
        return "\n".join(self.statements) + "\n"


def mysql_cli(password: str | None, sql: str, check: bool = True) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if password is not None:
        env["MYSQL_PWD"] = password
    args = [
        str(MYSQL),
        f"--host={HOST}",
        f"--port={PORT}",
        f"--user={USER}",
        "--protocol=TCP",
        "--default-character-set=utf8mb4",
        "--binary-mode",
    ]
    if password is None:
        args.append("--skip-password")
    proc = subprocess.run(
        args,
        input=sql,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        check=False,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    return proc


def wait_for_port(timeout_s: int = 45) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection((HOST, PORT), timeout=1):
                return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"MySQL did not listen on {HOST}:{PORT} within {timeout_s}s")


def datadir_initialized() -> bool:
    return (DATA_DIR / "mysql").exists()


def initialize_datadir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    if datadir_initialized():
        return
    cmd = [
        str(MYSQLD),
        "--no-defaults",
        "--initialize-insecure",
        f"--basedir={MYSQL_BASE}",
        f"--datadir={DATA_DIR}",
        "--log-error-verbosity=3",
        "--console",
    ]
    subprocess.run(cmd, cwd=ROOT, check=True)


def start_server() -> subprocess.Popen:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    log_path = RUN_DIR / "seed_mysqld.log"
    log = log_path.open("a", encoding="utf-8", errors="replace")
    cmd = [
        str(MYSQLD),
        "--no-defaults",
        f"--basedir={MYSQL_BASE}",
        f"--datadir={DATA_DIR}",
        f"--port={PORT}",
        f"--bind-address={HOST}",
        "--mysqlx=0",
        "--console",
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    wait_for_port()
    return proc


def ensure_root_password() -> None:
    if mysql_cli(PASSWORD, "SELECT 1;", check=False).returncode == 0:
        return
    pwd_sql = (
        f"ALTER USER 'root'@'localhost' IDENTIFIED BY {sql_literal(PASSWORD)};\n"
        "FLUSH PRIVILEGES;\n"
    )
    mysql_cli(None, pwd_sql)


def create_database(cur, db: str) -> None:
    cur.execute(
        f"CREATE DATABASE IF NOT EXISTS {quote_ident(db)} "
        "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )


def recreate_table(cur, db: str, table: str, columns: Iterable[str]) -> None:
    cols = list(dict.fromkeys(columns))
    create_database(cur, db)
    cur.execute(f"DROP TABLE IF EXISTS {quote_ident(db)}.{quote_ident(table)}")
    col_sql = ", ".join(f"{quote_ident(c)} {column_type(c)} NULL" for c in cols)
    cur.execute(
        f"CREATE TABLE {quote_ident(db)}.{quote_ident(table)} ("
        "id bigint unsigned NOT NULL AUTO_INCREMENT,"
        f"{col_sql},"
        "PRIMARY KEY (id)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
    )


def insert_rows(cur, db: str, table: str, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    cols = list(rows[0].keys())
    placeholders = ", ".join(["%s"] * len(cols))
    col_sql = ", ".join(quote_ident(c) for c in cols)
    sql = f"INSERT INTO {quote_ident(db)}.{quote_ident(table)} ({col_sql}) VALUES ({placeholders})"
    data = [tuple(row.get(c) for c in cols) for row in rows]
    cur.executemany(sql, data)


def make_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def seed_table(cur, db: str, table: str, columns: List[str], rows: List[Dict[str, Any]]) -> None:
    recreate_table(cur, db, table, columns)
    insert_rows(cur, db, table, rows)


def seed_piaoi_density(cur) -> None:
    db = "piaoi_density"
    tab_cols = [
        "line_id",
        "aoi",
        "model",
        "glass_type",
        "pi_hour",
        "recipe_family",
        "tab_name",
        "tab_total_glass_cnt",
        "tab_total_defect_cnt",
        "tab_total_density",
        "tab_raw_defect_cnt",
        "tab_total_defect_gap",
        "recipe_list",
        "glass",
    ]
    recipe_cols = [
        "line_id",
        "aoi",
        "model",
        "glass_type",
        "pi_hour",
        "recipe_id",
        "recipe_total_glass_cnt",
        "recipe_total_defect_cnt",
        "recipe_total_density",
        "recipe_raw_defect_cnt",
        "recipe_total_defect_gap",
        "glass",
    ]
    code_cols = [
        "line_id",
        "aoi",
        "model",
        "glass_type",
        "pi_hour",
        "recipe_id",
        "adc_def_code",
        "recipe_total_glass_cnt",
        "recipe_total_defect_cnt",
        "recipe_total_density",
        "recipe_raw_defect_cnt",
        "recipe_total_defect_gap",
        "defect_cnt",
        "def_glass_cnt",
        "glass_cnt",
        "recipe_code_density",
        "density",
        "small_defect_count",
        "middle_defect_count",
        "large_defect_count",
        "over_defect_count",
        "glass",
        "glass_size_detail",
        "comment",
        "action",
        "Editor",
        "modify_time",
    ]
    same_cols = [
        "line_id",
        "aoi",
        "model",
        "glass_type",
        "pi_hour",
        "recipe_id",
        "offset",
        "common_cnt",
        "common_glass_cnt",
        "common_points_details",
        "gen_time",
    ]
    seed_table(
        cur,
        db,
        f"density_tab_summary_{YYYYMM}",
        tab_cols,
        [
            {
                "line_id": "pi100",
                "aoi": "aoi100",
                "model": "MDL-A",
                "glass_type": "TFT",
                "pi_hour": BASE_TS,
                "recipe_family": "UPI",
                "tab_name": "UPI(Total)",
                "tab_total_glass_cnt": 120,
                "tab_total_defect_cnt": 36,
                "tab_total_density": 0.3,
                "tab_raw_defect_cnt": 35,
                "tab_total_defect_gap": 1,
                "recipe_list": "RCP-100,RCP-200",
                "glass": "G250709001,G250709002",
            },
            {
                "line_id": "pi200",
                "aoi": "aoi200",
                "model": "MDL-B",
                "glass_type": "CF",
                "pi_hour": "2026-07-09 09:00:00",
                "recipe_family": "PISpot",
                "tab_name": "PISpot(Total)",
                "tab_total_glass_cnt": 95,
                "tab_total_defect_cnt": 44,
                "tab_total_density": 0.463,
                "tab_raw_defect_cnt": 42,
                "tab_total_defect_gap": 2,
                "recipe_list": "RCP-300",
                "glass": "G250709003,G250709004",
            },
        ],
    )
    seed_table(
        cur,
        db,
        f"density_recipe_summary_{YYYYMM}",
        recipe_cols,
        [
            {
                "line_id": "pi100",
                "aoi": "aoi100",
                "model": "MDL-A",
                "glass_type": "TFT",
                "pi_hour": BASE_TS,
                "recipe_id": "RCP-100",
                "recipe_total_glass_cnt": 80,
                "recipe_total_defect_cnt": 24,
                "recipe_total_density": 0.3,
                "recipe_raw_defect_cnt": 23,
                "recipe_total_defect_gap": 1,
                "glass": "G250709001,G250709002",
            }
        ],
    )
    seed_table(
        cur,
        db,
        f"density_code_summary_{YYYYMM}",
        code_cols,
        [
            {
                "line_id": "pi100",
                "aoi": "aoi100",
                "model": "MDL-A",
                "glass_type": "TFT",
                "pi_hour": BASE_TS,
                "recipe_id": "RCP-100",
                "adc_def_code": "Polymer",
                "recipe_total_glass_cnt": 80,
                "recipe_total_defect_cnt": 24,
                "recipe_total_density": 0.3,
                "recipe_raw_defect_cnt": 23,
                "recipe_total_defect_gap": 1,
                "defect_cnt": 16,
                "def_glass_cnt": 10,
                "glass_cnt": 80,
                "recipe_code_density": 0.2,
                "density": 0.2,
                "small_defect_count": 8,
                "middle_defect_count": 5,
                "large_defect_count": 2,
                "over_defect_count": 1,
                "glass": "G250709001,G250709002",
                "glass_size_detail": "S:8,M:5,L:2,O:1",
                "comment": "mock density row",
                "action": "observe",
                "Editor": "mock",
                "modify_time": BASE_TS,
            },
            {
                "line_id": "pi200",
                "aoi": "aoi200",
                "model": "MDL-B",
                "glass_type": "CF",
                "pi_hour": "2026-07-09 09:00:00",
                "recipe_id": "RCP-300",
                "adc_def_code": "PI_Spot_NP",
                "recipe_total_glass_cnt": 95,
                "recipe_total_defect_cnt": 44,
                "recipe_total_density": 0.463,
                "recipe_raw_defect_cnt": 42,
                "recipe_total_defect_gap": 2,
                "defect_cnt": 27,
                "def_glass_cnt": 18,
                "glass_cnt": 95,
                "recipe_code_density": 0.284,
                "density": 0.284,
                "small_defect_count": 11,
                "middle_defect_count": 8,
                "large_defect_count": 5,
                "over_defect_count": 3,
                "glass": "G250709003,G250709004",
                "glass_size_detail": "S:11,M:8,L:5,O:3",
                "comment": "mock high density",
                "action": "check recipe",
                "Editor": "mock",
                "modify_time": BASE_TS,
            },
        ],
    )
    seed_table(
        cur,
        db,
        f"density_recipe_same_point_{YYYYMM}",
        same_cols,
        [
            {
                "line_id": "pi100",
                "aoi": "aoi100",
                "model": "MDL-A",
                "glass_type": "TFT",
                "pi_hour": BASE_TS,
                "recipe_id": "RCP-100",
                "offset": 20,
                "common_cnt": 3,
                "common_glass_cnt": 2,
                "common_points_details": make_json(
                    [
                        {
                            "glass_id": "G250709001",
                            "offset": 20,
                            "distance": 7.2,
                            "defect_a": {"x": 120, "y": 450, "defect_size": "S"},
                            "defect_b": {"x": 126, "y": 454, "defect_size": "M"},
                        }
                    ]
                ),
                "gen_time": BASE_TS,
            }
        ],
    )
    spec_cols = ["model", "glass_type", "defect_size", "OOC", "OOS", "Editor", "modify_time", "drop"]
    seed_table(
        cur,
        db,
        "default_spec_table",
        spec_cols,
        [
            {
                "model": "MDL-A",
                "glass_type": "TFT",
                "defect_size": "S",
                "OOC": 0.25,
                "OOS": 0.45,
                "Editor": "mock",
                "modify_time": BASE_TS,
                "drop": "F",
            }
        ],
    )
    seed_table(cur, db, f"fix_spec_table_{YYYYMM}", spec_cols + ["GEN_DT"], [])


def seed_bpi(cur) -> None:
    density_db = "piaoi_bpi_density"
    same_db = "piaoi_bpi_same_point"
    bpi_cols = [
        "aoi",
        "model",
        "scan_hour",
        "cassette_id",
        "glass_side",
        "recipe_id",
        "pi_type",
        "run_day",
        "glass_count",
        "total_defect_count",
        "small_defect_count",
        "middle_defect_count",
        "large_defect_count",
        "over_defect_count",
        "density",
        "glass_list",
        "glass_size_detail",
        "source_db",
        "source_table",
        "comment",
        "action",
        "editor",
        "modify_time",
    ]
    seed_table(
        cur,
        density_db,
        f"bpi_api_summary_{YYYYMM}",
        bpi_cols,
        [
            {
                "aoi": "aoi300",
                "model": "MDL-A",
                "scan_hour": BASE_TS,
                "cassette_id": "CST001",
                "glass_side": "TFT",
                "recipe_id": "BPI-RCP-1",
                "pi_type": "BPI",
                "run_day": RUN_DAY,
                "glass_count": 64,
                "total_defect_count": 31,
                "small_defect_count": 14,
                "middle_defect_count": 9,
                "large_defect_count": 6,
                "over_defect_count": 2,
                "density": 0.484,
                "glass_list": "G250709001,G250709002",
                "glass_size_detail": "S:14,M:9,L:6,O:2",
                "source_db": "rtms_piaoi_other",
                "source_table": f"rtms_aoi300_raw_{YYYYMM}",
                "comment": "mock bpi row",
                "action": "review",
                "editor": "mock",
                "modify_time": BASE_TS,
            }
        ],
    )
    spec_cols = ["model", "glass_type", "defect_size", "OOC", "OOS", "Editor", "modify_time", "drop"]
    seed_table(
        cur,
        density_db,
        "default_spec_table",
        spec_cols,
        [
            {
                "model": "MDL-A",
                "glass_type": "TFT",
                "defect_size": "M",
                "OOC": 0.35,
                "OOS": 0.55,
                "Editor": "mock",
                "modify_time": BASE_TS,
                "drop": "F",
            }
        ],
    )
    pair_cols = [
        "model",
        "glass_side",
        "glass_id",
        "scan_hour",
        "run_day",
        "tab",
        "bpi_aoi",
        "bpi_line_id",
        "bpi_recipe_id",
        "bpi_cassette_id",
        "bpi_scan_time",
        "bpi_pi_time",
        "bpi_scan_hour",
        "bpi_run_day",
        "bpi_source_db",
        "bpi_source_table",
        "api_aoi",
        "api_line_id",
        "api_recipe_id",
        "api_cassette_id",
        "api_scan_time",
        "api_pi_time",
        "api_scan_hour",
        "api_run_day",
        "api_source_db",
        "api_source_table",
        "bpi_defect_count",
        "api_defect_count",
        "bpi_small_defect_count",
        "bpi_middle_defect_count",
        "bpi_large_defect_count",
        "bpi_over_defect_count",
        "api_small_defect_count",
        "api_middle_defect_count",
        "api_large_defect_count",
        "api_over_defect_count",
        "pair_status",
        "pair_message",
        "default_offset_um",
        "matched_points_json",
        "comment",
        "action",
        "editor",
        "modify_time",
        "gen_time",
    ]
    pair_row = {
        "model": "MDL-A",
        "glass_side": "TFT",
        "glass_id": "G250709001",
        "scan_hour": BASE_TS,
        "run_day": RUN_DAY,
        "tab": "TFT",
        "bpi_aoi": "aoi300",
        "bpi_line_id": "capic300",
        "bpi_recipe_id": "BPI-RCP-1",
        "bpi_cassette_id": "CST001",
        "bpi_scan_time": BASE_TS,
        "bpi_pi_time": BASE_TS,
        "bpi_scan_hour": BASE_TS,
        "bpi_run_day": RUN_DAY,
        "bpi_source_db": "rtms_piaoi_other",
        "bpi_source_table": f"rtms_aoi300_raw_{YYYYMM}",
        "api_aoi": "aoi100",
        "api_line_id": "capic100",
        "api_recipe_id": "RCP-100",
        "api_cassette_id": "CST001",
        "api_scan_time": BASE_TS,
        "api_pi_time": BASE_TS,
        "api_scan_hour": BASE_TS,
        "api_run_day": RUN_DAY,
        "api_source_db": "cim_piaoi",
        "api_source_table": f"cim_defect_{YYYYMM}_aoi100_capic100",
        "bpi_defect_count": 31,
        "api_defect_count": 24,
        "bpi_small_defect_count": 14,
        "bpi_middle_defect_count": 9,
        "bpi_large_defect_count": 6,
        "bpi_over_defect_count": 2,
        "api_small_defect_count": 8,
        "api_middle_defect_count": 5,
        "api_large_defect_count": 2,
        "api_over_defect_count": 1,
        "pair_status": "paired",
        "pair_message": "mock pair",
        "default_offset_um": 20,
        "matched_points_json": make_json([{"bpi_x": 100, "bpi_y": 200, "api_x": 104, "api_y": 203}]),
        "comment": "mock same point",
        "action": "confirm",
        "editor": "mock",
        "modify_time": BASE_TS,
        "gen_time": BASE_TS,
    }
    seed_table(cur, same_db, f"bpi_same_point_{YYYYMM}", pair_cols, [pair_row])
    offset_cols = [
        "model",
        "glass_side",
        "glass_id",
        "scan_hour",
        "run_day",
        "tab",
        "bpi_aoi",
        "bpi_scan_time",
        "bpi_recipe_id",
        "api_aoi",
        "api_scan_time",
        "api_recipe_id",
        "offset_um",
        "bpi_defect_count",
        "api_defect_count",
        "matched_pair_count",
        "matched_bpi_defect_count",
        "matched_api_defect_count",
        "unmatched_bpi_defect_count",
        "unmatched_api_defect_count",
        "matched_bpi_s_count",
        "matched_bpi_m_count",
        "matched_bpi_l_count",
        "matched_bpi_o_count",
        "matched_api_s_count",
        "matched_api_m_count",
        "matched_api_l_count",
        "matched_api_o_count",
        "matched_size_transition_json",
        "gen_time",
    ]
    seed_table(
        cur,
        same_db,
        f"bpi_same_point_offset_summary_{YYYYMM}",
        offset_cols,
        [
            {
                "model": "MDL-A",
                "glass_side": "TFT",
                "glass_id": "G250709001",
                "scan_hour": BASE_TS,
                "run_day": RUN_DAY,
                "tab": "TFT",
                "bpi_aoi": "aoi300",
                "bpi_scan_time": BASE_TS,
                "bpi_recipe_id": "BPI-RCP-1",
                "api_aoi": "aoi100",
                "api_scan_time": BASE_TS,
                "api_recipe_id": "RCP-100",
                "offset_um": 20,
                "bpi_defect_count": 31,
                "api_defect_count": 24,
                "matched_pair_count": 12,
                "matched_bpi_defect_count": 12,
                "matched_api_defect_count": 12,
                "unmatched_bpi_defect_count": 19,
                "unmatched_api_defect_count": 12,
                "matched_bpi_s_count": 5,
                "matched_bpi_m_count": 4,
                "matched_bpi_l_count": 2,
                "matched_bpi_o_count": 1,
                "matched_api_s_count": 4,
                "matched_api_m_count": 5,
                "matched_api_l_count": 2,
                "matched_api_o_count": 1,
                "matched_size_transition_json": make_json({"S->M": 2, "M->M": 4}),
                "gen_time": BASE_TS,
            }
        ],
    )
    match_cols = [
        "model",
        "glass_side",
        "glass_id",
        "scan_hour",
        "run_day",
        "tab",
        "bpi_aoi",
        "bpi_line_id",
        "bpi_recipe_id",
        "bpi_scan_time",
        "api_aoi",
        "api_line_id",
        "api_recipe_id",
        "api_scan_time",
        "offset_um",
        "bpi_defect_uid",
        "bpi_chip_id",
        "bpi_x",
        "bpi_y",
        "bpi_defect_size",
        "bpi_adc_def_code",
        "bpi_retype_code",
        "bpi_pic_path",
        "bpi_pic_name",
        "api_defect_uid",
        "api_chip_id",
        "api_x",
        "api_y",
        "api_defect_size",
        "api_adc_def_code",
        "api_retype_code",
        "api_pic_path",
        "api_pic_name",
        "dx",
        "dy",
        "distance",
        "match_rank",
        "match_method",
        "gen_time",
    ]
    seed_table(
        cur,
        same_db,
        f"bpi_same_point_match_detail_{YYYYMM}",
        match_cols,
        [
            {
                "model": "MDL-A",
                "glass_side": "TFT",
                "glass_id": "G250709001",
                "scan_hour": BASE_TS,
                "run_day": RUN_DAY,
                "tab": "TFT",
                "bpi_aoi": "aoi300",
                "bpi_line_id": "capic300",
                "bpi_recipe_id": "BPI-RCP-1",
                "bpi_scan_time": BASE_TS,
                "api_aoi": "aoi100",
                "api_line_id": "capic100",
                "api_recipe_id": "RCP-100",
                "api_scan_time": BASE_TS,
                "offset_um": 20,
                "bpi_defect_uid": "BPI-1",
                "bpi_chip_id": "CHIP01",
                "bpi_x": 100,
                "bpi_y": 200,
                "bpi_defect_size": "M",
                "bpi_adc_def_code": "BPI_POLY",
                "bpi_retype_code": "NA",
                "bpi_pic_path": "",
                "bpi_pic_name": "",
                "api_defect_uid": "API-1",
                "api_chip_id": "CHIP01",
                "api_x": 104,
                "api_y": 203,
                "api_defect_size": "S",
                "api_adc_def_code": "Polymer",
                "api_retype_code": "NA",
                "api_pic_path": "",
                "api_pic_name": "",
                "dx": 4,
                "dy": 3,
                "distance": 5,
                "match_rank": 1,
                "match_method": "nearest",
                "gen_time": BASE_TS,
            }
        ],
    )
    same_spec_cols = ["model", "glass_side", "defect_size", "OOC", "OOS", "editor", "modify_time", "drop"]
    seed_table(
        cur,
        same_db,
        "default_spec_table",
        same_spec_cols,
        [
            {
                "model": "MDL-A",
                "glass_side": "TFT",
                "defect_size": "M",
                "OOC": 10,
                "OOS": 20,
                "editor": "mock",
                "modify_time": BASE_TS,
                "drop": "F",
            }
        ],
    )


def seed_inspection(cur) -> None:
    db = "piaoi_inspection_density"
    cols = [
        "pi_hour",
        "shift_day",
        "shift_week",
        "shift_month",
        "shift_start",
        "shift_end",
        "line_id",
        "model",
        "glass_type",
        "maingroup_glass_count",
        "maingroup_defect_count",
        "maingroup_density",
        "defect_code_glass_count",
        "small_defect_count",
        "middle_defect_count",
        "large_defect_count",
        "over_defect_count",
        "glass",
        "glass_size_detail",
        "comment",
        "action",
        "Editor",
        "modify_time",
    ]
    seed_table(
        cur,
        db,
        f"inspection_api_summary_{YYYYMM}",
        cols,
        [
            {
                "pi_hour": BASE_TS,
                "shift_day": RUN_DAY,
                "shift_week": "2026-W28",
                "shift_month": "2026-07",
                "shift_start": "2026-07-09 07:00:00",
                "shift_end": "2026-07-09 19:00:00",
                "line_id": "CAPIC107",
                "model": "MDL-A",
                "glass_type": "TFT",
                "maingroup_glass_count": 50,
                "maingroup_defect_count": 18,
                "maingroup_density": 0.36,
                "defect_code_glass_count": 12,
                "small_defect_count": 6,
                "middle_defect_count": 5,
                "large_defect_count": 4,
                "over_defect_count": 3,
                "glass": "G250709001,G250709002",
                "glass_size_detail": "S:6,M:5,L:4,O:3",
                "comment": "mock inspection",
                "action": "track",
                "Editor": "mock",
                "modify_time": BASE_TS,
            }
        ],
    )
    detail_cols = cols + ["sheet_id", "chip_id", "x", "y", "defect_size", "adc_def_code", "img_url"]
    seed_table(
        cur,
        db,
        f"inspection_api_glass_detail_{YYYYMM}",
        detail_cols,
        [
            {
                "pi_hour": BASE_TS,
                "shift_day": RUN_DAY,
                "shift_week": "2026-W28",
                "shift_month": "2026-07",
                "shift_start": "2026-07-09 07:00:00",
                "shift_end": "2026-07-09 19:00:00",
                "line_id": "CAPIC107",
                "model": "MDL-A",
                "glass_type": "TFT",
                "maingroup_glass_count": 50,
                "maingroup_defect_count": 18,
                "maingroup_density": 0.36,
                "defect_code_glass_count": 12,
                "small_defect_count": 6,
                "middle_defect_count": 5,
                "large_defect_count": 4,
                "over_defect_count": 3,
                "glass": "G250709001",
                "glass_size_detail": "S:6",
                "comment": "",
                "action": "",
                "Editor": "mock",
                "modify_time": BASE_TS,
                "sheet_id": "G250709001",
                "chip_id": "CHIP01",
                "x": 110,
                "y": 220,
                "defect_size": "S",
                "adc_def_code": "INSPEC_DEFECT",
                "img_url": "",
            }
        ],
    )
    seed_table(cur, db, f"inspection_raw_table_{YYYYMM}", detail_cols, [])
    spec_cols = ["line_id", "model", "glass_type", "defect_size", "OOC", "OOS", "Editor", "modify_time", "drop"]
    seed_table(
        cur,
        db,
        "default_spec_table",
        spec_cols,
        [
            {
                "line_id": "CAPIC107",
                "model": "MDL-A",
                "glass_type": "TFT",
                "defect_size": "S",
                "OOC": 0.3,
                "OOS": 0.5,
                "Editor": "mock",
                "modify_time": BASE_TS,
                "drop": "F",
            }
        ],
    )


def seed_capa(cur) -> None:
    db = "piaoi_capa"
    day_cols = [
        "aoi",
        "run_day",
        "pi_type",
        "total_glass",
        "target_count",
        "spec",
        "real_day_capa",
        "comment",
        "action",
        "editor",
        "modify_time",
    ]
    hourly_cols = [
        "aoi",
        "run_day",
        "pi_type",
        "pi_hour",
        "hour_int",
        "hour_label",
        "hour_sort",
        "hour",
        "cumu",
        "real_hour_capa",
        "real_cumu_capa",
    ]
    for idx, aoi in enumerate(["aoi100", "aoi200", "aoi300"], start=1):
        seed_table(
            cur,
            db,
            f"{aoi}_{YYYYMM}_capa_summary",
            day_cols,
            [
                {
                    "aoi": aoi,
                    "run_day": RUN_DAY,
                    "pi_type": "API",
                    "total_glass": 100 + idx * 10,
                    "target_count": 120,
                    "spec": 115,
                    "real_day_capa": 0.92,
                    "comment": "mock capa",
                    "action": "monitor",
                    "editor": "mock",
                    "modify_time": BASE_TS,
                }
            ],
        )
        seed_table(
            cur,
            db,
            f"{aoi}_{YYYYMM}_capa_hourly_rawdata",
            hourly_cols,
            [
                {
                    "aoi": aoi,
                    "run_day": RUN_DAY,
                    "pi_type": "API",
                    "pi_hour": BASE_TS,
                    "hour_int": 8,
                    "hour_label": "08",
                    "hour_sort": 1,
                    "hour": 10 + idx,
                    "cumu": 10 + idx,
                    "real_hour_capa": 0.9,
                    "real_cumu_capa": 0.9,
                }
            ],
        )


def seed_ol_defect_map(cur) -> None:
    summary_db = "piaoi_ol_defect_map"
    raw_db = "cim_piaoi"
    rtms_db = "rtms_piaoi_other"
    summary_cols = [
        "test_time",
        "sheet_id_chip_id",
        "recipe_id",
        "line_id",
        "aoi",
        "defect_count",
        "over_defect_count",
        "large_defect_count",
        "middle_defect_count",
        "small_defect_count",
    ]
    raw_cols = [
        "test_time",
        "sheet_id_chip_id",
        "recipe_id",
        "line_id",
        "aoi",
        "x",
        "y",
        "defect_size",
        "adc_def_code",
        "retype_code",
        "img_url",
    ]
    for aoi in ["aoi100", "aoi200", "aoi300"]:
        seed_table(
            cur,
            summary_db,
            f"{aoi}_{YYYYMM}_api_summary_table",
            summary_cols,
            [
                {
                    "test_time": BASE_TS,
                    "sheet_id_chip_id": "G250709001",
                    "recipe_id": "RCP-100",
                    "line_id": "capic100",
                    "aoi": aoi,
                    "defect_count": 8,
                    "over_defect_count": 1,
                    "large_defect_count": 2,
                    "middle_defect_count": 2,
                    "small_defect_count": 3,
                }
            ],
        )
    seed_table(
        cur,
        raw_db,
        f"cim_defect_{YYYYMM}_aoi100_capic100",
        raw_cols,
        [
            {
                "test_time": BASE_TS,
                "sheet_id_chip_id": "G250709001",
                "recipe_id": "RCP-100",
                "line_id": "capic100",
                "aoi": "aoi100",
                "x": 120,
                "y": 450,
                "defect_size": "S",
                "adc_def_code": "Polymer",
                "retype_code": "NA",
                "img_url": "",
            }
        ],
    )
    seed_table(cur, rtms_db, f"rtms_aoi300_raw_{YYYYMM}", raw_cols, [])


def seed_cell_aoi_to_array(cur) -> None:
    aoi_db = "cim_cell_aoi_to_array"
    ins_db = "cim_cell_inspec_to_array"
    summary_cols = [
        "test_time",
        "line_id",
        "cassette_id",
        "sheet_id_chip_id",
        "abbr_cat",
        "pi_type",
        "recipe_id",
        "model_no",
        "aoi",
        "total_defect_qty",
        "source_op_id",
        "source_scan_time",
        "source_defect_cnt",
        "same_point_defect_cnt",
        "same_point_rate",
        "same_point_offset",
        "match_status",
        "match_status_detail",
        "comment",
        "action",
        "editor",
        "modify_time",
    ]
    detail_cols = summary_cols + ["sheet_id", "scan_time", "point_detail"]
    point_detail = make_json(
        [
            {
                "match": True,
                "cell_img": "",
                "source_img": "",
                "cell_info": {"x": 120, "y": 450, "defect_size": "S"},
                "source_info": {"x": 124, "y": 452, "defect_size": "M"},
            }
        ]
    )
    row = {
        "test_time": BASE_TS,
        "line_id": "CAPIC100",
        "cassette_id": "CST001",
        "sheet_id_chip_id": "G250709001",
        "abbr_cat": "TFT",
        "pi_type": "API",
        "recipe_id": "RCP-100",
        "model_no": "MDL-A",
        "aoi": "aoi100",
        "total_defect_qty": 24,
        "source_op_id": "PX1=MOR",
        "source_scan_time": BASE_TS,
        "source_defect_cnt": 18,
        "same_point_defect_cnt": 9,
        "same_point_rate": 0.375,
        "same_point_offset": 20,
        "match_status": "matched",
        "match_status_detail": "mock matched",
        "comment": "mock incoming",
        "action": "track",
        "editor": "mock",
        "modify_time": BASE_TS,
    }
    seed_table(cur, aoi_db, f"api_aoi_summary_{YYYYMM}", summary_cols, [row])
    seed_table(
        cur,
        aoi_db,
        f"incoming_same_point_detail_{YYYYMM}",
        detail_cols,
        [dict(row, sheet_id="G250709001", scan_time=BASE_TS, point_detail=point_detail)],
    )
    seed_table(cur, aoi_db, f"incoming_glass_summary_{YYYYMM}", summary_cols, [row])
    for base in [
        "incoming_source_cf_oc_defect_raw",
        "incoming_source_cf_ps_defect_raw",
        "incoming_source_array_mor_defect_raw",
        "incoming_source_array_tar_defect_raw",
        "incoming_source_array_tos_defect_raw",
    ]:
        seed_table(cur, aoi_db, f"{base}_{YYYYMM}", summary_cols, [])
    ins_row = dict(row)
    ins_row.update({"line_id": "CAPIC107", "source_op_id": "AOI_API"})
    seed_table(cur, ins_db, f"api_inspection_summary_{YYYYMM}", summary_cols, [ins_row])
    seed_table(
        cur,
        ins_db,
        f"incoming_inspection_same_point_detail_{YYYYMM}",
        detail_cols,
        [dict(ins_row, sheet_id="G250709001", scan_time=BASE_TS, point_detail=point_detail)],
    )
    seed_table(cur, ins_db, f"incoming_inspection_glass_summary_{YYYYMM}", summary_cols, [ins_row])


def seed_all() -> None:
    cur = ScriptCursor()
    seed_piaoi_density(cur)
    seed_bpi(cur)
    seed_inspection(cur)
    seed_capa(cur)
    seed_ol_defect_map(cur)
    seed_cell_aoi_to_array(cur)
    mysql_cli(PASSWORD, cur.text())


def verify_counts() -> Dict[str, int]:
    checks = {
        "piaoi_density.density_code_summary_202607": ("piaoi_density", "density_code_summary_202607"),
        "piaoi_bpi_density.bpi_api_summary_202607": ("piaoi_bpi_density", "bpi_api_summary_202607"),
        "piaoi_bpi_same_point.bpi_same_point_202607": ("piaoi_bpi_same_point", "bpi_same_point_202607"),
        "piaoi_inspection_density.inspection_api_summary_202607": (
            "piaoi_inspection_density",
            "inspection_api_summary_202607",
        ),
        "piaoi_capa.aoi100_202607_capa_summary": ("piaoi_capa", "aoi100_202607_capa_summary"),
        "cim_cell_aoi_to_array.api_aoi_summary_202607": (
            "cim_cell_aoi_to_array",
            "api_aoi_summary_202607",
        ),
    }
    out: Dict[str, int] = {}
    for label, (db, table) in checks.items():
        proc = mysql_cli(
            PASSWORD,
            f"SELECT COUNT(*) AS n FROM {quote_ident(db)}.{quote_ident(table)};",
        )
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        out[label] = int(lines[-1]) if lines else 0
    return out


def shutdown_server() -> None:
    env = os.environ.copy()
    env["MYSQL_PWD"] = PASSWORD
    subprocess.run(
        [
            str(MYSQLADMIN),
            f"--host={HOST}",
            f"--port={PORT}",
            f"--user={USER}",
            "shutdown",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def main() -> None:
    global PASSWORD

    parser = argparse.ArgumentParser(description="Initialize and seed local mock MySQL data.")
    parser.add_argument("--leave-running", action="store_true", help="Leave mock MySQL listening on 127.0.0.1:3307")
    parser.add_argument("--password", default=PASSWORD, help="Mock MySQL root password")
    args = parser.parse_args()
    PASSWORD = args.password

    if not PASSWORD:
        raise SystemExit("Set --password or PI_MOCK_MYSQL_PASSWORD before seeding mock MySQL.")

    for exe in [MYSQLD, MYSQL, MYSQLADMIN]:
        if not exe.exists():
            raise SystemExit(f"MySQL executable not found: {exe}")

    initialize_datadir()
    proc = start_server()
    try:
        ensure_root_password()
        seed_all()
        counts = verify_counts()
        print("Mock MySQL seeded.")
        print(f"host={HOST} port={PORT} user={USER}")
        for label, count in counts.items():
            print(f"{label}: {count}")
        if args.leave_running:
            print("Mock MySQL left running.")
            return
    finally:
        if not args.leave_running:
            shutdown_server()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.terminate()


if __name__ == "__main__":
    main()
