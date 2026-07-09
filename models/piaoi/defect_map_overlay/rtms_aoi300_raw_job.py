
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import xmltodict
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine


# =========================================================
# Logging
# =========================================================
def setup_logger(log_dir: str = "logs", name: str = "rtms_aoi300_raw_job") -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(funcName)s] %(message)s")

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    fh = logging.FileHandler(os.path.join(log_dir, f"{name}.log"), encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


logger = setup_logger()


# =========================================================
# DB
# =========================================================
@dataclass
class DBConfig:
    host: str = "127.0.0.1"
    port: int = 3306
    user: str = "l6a01_user"
    pwd: str = "l6a01$user"
    raw_db: str = "rtms_piaoi_other"

    def make_url(self, dbname: str) -> str:
        return f"mysql+pymysql://{self.user}:{self.pwd}@{self.host}:{self.port}/{dbname}?charset=utf8mb4"


class MySQLDB:
    def __init__(self, dbname: str, cfg: DBConfig):
        self.dbname = dbname
        self.engine: Engine = create_engine(
            cfg.make_url(dbname),
            pool_pre_ping=True,
            pool_recycle=3600,
        )

    def execute(self, sql: str, params: Optional[dict] = None):
        with self.engine.begin() as conn:
            return conn.execute(text(sql), params or {})

    def table_exists(self, table_name: str) -> bool:
        insp = inspect(self.engine)
        return insp.has_table(table_name)

    def upsert_rows(self, table_name: str, rows: List[dict]):
        if not rows:
            return

        sql = f"""
        INSERT INTO `{self.dbname}`.`{table_name}` (
            sheet_id_chip_id,
            chip_id,
            test_time,
            defect_size,
            size_class,
            pox_x1,
            pox_y1,
            adc_def_code,
            retype_def_code,
            image_file_name,
            img_file_url_path,
            pic_path,
            recipe_id,
            line_id,
            aoi,
            model,
            glass_type,
            pi_time,
            pi_type,
            cst_id,
            defect_count,
            defect_id,
            source_file,
            source_mtime
        ) VALUES (
            :sheet_id_chip_id,
            :chip_id,
            :test_time,
            :defect_size,
            :size_class,
            :pox_x1,
            :pox_y1,
            :adc_def_code,
            :retype_def_code,
            :image_file_name,
            :img_file_url_path,
            :pic_path,
            :recipe_id,
            :line_id,
            :aoi,
            :model,
            :glass_type,
            :pi_time,
            :pi_type,
            :cst_id,
            :defect_count,
            :defect_id,
            :source_file,
            :source_mtime
        )
        ON DUPLICATE KEY UPDATE
            defect_size       = VALUES(defect_size),
            size_class        = VALUES(size_class),
            pox_x1            = VALUES(pox_x1),
            pox_y1            = VALUES(pox_y1),
            adc_def_code      = VALUES(adc_def_code),
            retype_def_code   = VALUES(retype_def_code),
            image_file_name   = VALUES(image_file_name),
            img_file_url_path = VALUES(img_file_url_path),
            pic_path          = VALUES(pic_path),
            recipe_id         = VALUES(recipe_id),
            line_id           = VALUES(line_id),
            aoi               = VALUES(aoi),
            model             = VALUES(model),
            glass_type        = VALUES(glass_type),
            pi_time           = VALUES(pi_time),
            pi_type           = VALUES(pi_type),
            cst_id            = VALUES(cst_id),
            defect_count      = VALUES(defect_count),
            source_file       = VALUES(source_file),
            source_mtime      = VALUES(source_mtime)
        """
        with self.engine.begin() as conn:
            conn.execute(text(sql), rows)


def ensure_raw_table(db: MySQLDB, table_name: str):
    ddl = f"""
    CREATE TABLE IF NOT EXISTS `{db.dbname}`.`{table_name}` (
        id BIGINT NOT NULL AUTO_INCREMENT,
        sheet_id_chip_id VARCHAR(64) NOT NULL,
        chip_id VARCHAR(64) NULL,
        test_time DATETIME NOT NULL,
        defect_size VARCHAR(32) NULL,
        size_class VARCHAR(32) NULL,
        pox_x1 BIGINT NULL,
        pox_y1 BIGINT NULL,
        adc_def_code VARCHAR(128) NULL,
        retype_def_code VARCHAR(128) NULL,
        image_file_name VARCHAR(255) NULL,
        img_file_url_path VARCHAR(512) NULL,
        pic_path VARCHAR(1024) NULL,
        recipe_id VARCHAR(255) NULL,
        line_id VARCHAR(32) NULL,
        aoi VARCHAR(32) NULL,
        model VARCHAR(255) NULL,
        glass_type VARCHAR(64) NULL,
        pi_time DATETIME NULL,
        pi_type VARCHAR(16) NULL,
        cst_id VARCHAR(128) NULL,
        defect_count INT NULL,
        defect_id VARCHAR(64) NOT NULL,
        source_file VARCHAR(512) NULL,
        source_mtime DATETIME NULL,
        update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY uk_rtms_raw (
            sheet_id_chip_id,
            test_time,
            chip_id,
            defect_id
        ),
        KEY idx_test_time (test_time),
        KEY idx_glass (sheet_id_chip_id),
        KEY idx_aoi (aoi),
        KEY idx_line (line_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    db.execute(ddl)


# =========================================================
# Helpers
# =========================================================
AOI_MAP = {
    "CAAOI300": "aoi300",
    "AOI300": "aoi300",
    "aoi300": "aoi300",
}


def normalize_aoi(v: str) -> str:
    s = str(v or "").strip()
    return AOI_MAP.get(s.upper(), "aoi300")

def parse_dt(v: Optional[str]) -> Optional[datetime]:
    if not v:
        return None

    v = str(v).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue

    raise ValueError(f"無法解析日期時間格式: {v}")

def infer_glass_type(recipe: str) -> str:
    recipe = str(recipe or "").strip()
    if recipe in {"CELL-ITO", "CELL-ITO_20230823"}:
        return "ITO"
    if recipe in {"C-API", "T-API"}:
        return "PASS"

    parts = recipe.split("-")
    if len(parts) <= 1:
        return "Unknown"

    gt = parts[1]
    if gt == "T":
        gt = "TFT"
    elif gt == "C":
        gt = "CF"
    elif gt == "TD":
        gt = "ITO"

    if len(parts) > 2 and parts[1] == "T" and parts[2] == "ITO":
        gt = "ITO"
    return gt


def infer_pi_type(recipe: str, default_pi_type: str = "OTHER") -> str:
    s = str(recipe or "").strip().upper()

    if "CELL-ITO" in s:
        return "CELL-ITO"
    if "-BPI" in s:
        return "BPI"
    if "-API" in s:
        return "API"

    return default_pi_type



def resolve_window(
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
    date_str: Optional[str],
    lookback_min: int,
    lag_min: int,
) -> Tuple[datetime, datetime]:
    if start_dt or end_dt:
        if start_dt is None and end_dt is not None:
            start_dt = end_dt - timedelta(minutes=lookback_min)
        if end_dt is None and start_dt is not None:
            end_dt = start_dt + timedelta(minutes=lookback_min)
        return start_dt, end_dt

    if date_str:
        d = parse_dt(date_str)
        d0 = datetime(d.year, d.month, d.day)
        return d0, d0 + timedelta(days=1)

    now = datetime.now()
    end_dt = now - timedelta(minutes=lag_min)
    start_dt = end_dt - timedelta(minutes=lookback_min)
    return start_dt, end_dt


def file_mtime_in_range(file_path: str, start_dt: datetime, end_dt: datetime) -> bool:
    try:
        mt = datetime.fromtimestamp(os.path.getmtime(file_path))
        return start_dt <= mt < end_dt
    except Exception:
        return False


def build_month_table_name(ts: datetime) -> str:
    return f"rtms_aoi300_raw_{ts.strftime('%Y%m')}"


def read_xml_file(file_path: str) -> Optional[dict]:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return xmltodict.parse(f.read())
    except Exception as e:
        logger.warning(f"[read_xml_file] failed: {file_path}, err={e}")
        return None


def extract_cst_flowindex_from_filename(filename: str) -> Tuple[str, str]:
    try:
        parts = filename.split(".")
        cst = parts[3]
        flowindex = parts[5]
        return cst, flowindex
    except Exception:
        return "N/A", "N/A"


def to_dt_from_unix_str(v: str) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(int(v))
    except Exception:
        return None


def safe_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def extract_macro_image_paths(source_dir: str, defect_filename: str) -> List[str]:
    """
    由 .defect 檔名找到同名 .macro / .marco，
    讀取 MacroInspection.Images.GlassImage 的 ImgName。
    最多回傳 4 張 macro image。
    """
    fn = str(defect_filename or "").strip()

    candidate_macro_names: List[str] = []

    lower_fn = fn.lower()
    if lower_fn.endswith(".defect"):
        base = fn[: -len(".defect")]
        candidate_macro_names.append(base + ".macro")
        candidate_macro_names.append(base + ".marco")
    else:
        candidate_macro_names.append(fn + ".macro")
        candidate_macro_names.append(fn + ".marco")

    macro_path = ""
    for macro_filename in candidate_macro_names:
        p = os.path.join(source_dir, macro_filename)
        if os.path.exists(p):
            macro_path = p
            break

    if not macro_path:
        logger.warning(
            f"[extract_macro_image_paths] macro file not found for defect={defect_filename}, "
            f"candidates={candidate_macro_names}"
        )
        return []

    macro_obj = read_xml_file(macro_path)
    if not macro_obj:
        return []

    try:
        images_section = (
            macro_obj.get("Body", {})
            .get("MacroInspection", {})
            .get("Images", {})
        )

        glass_images = images_section.get("GlassImage", [])

        if isinstance(glass_images, dict):
            glass_images = [glass_images]

        img_names: List[str] = []
        for glass_image in glass_images[:4]:
            if not isinstance(glass_image, dict):
                continue

            img_name = str(glass_image.get("ImgName", "")).strip()
            if img_name:
                img_names.append(img_name)

        return img_names

    except Exception as e:
        logger.warning(f"[extract_macro_image_paths] failed: {macro_path}, err={e}")
        return []

# =========================================================
# Extract
# =========================================================
def extract_records_from_defect_file(
    file_path: str,
    source_dir: str,
    default_line_id: str = "Null",
    default_pi_type: str = "OTHER",
) -> List[dict]:
    fn = os.path.basename(file_path)
    xml_obj = read_xml_file(file_path)
    if not xml_obj:
        return []

    body = xml_obj.get("Body", {}) or {}
    inspection = body.get("InspectionInfo", {}) or {}
    defects_node = body.get("Defects", {}) or {}

    start_date = inspection.get("StartDate", "")
    machine_id = inspection.get("MachineID", "")
    device = inspection.get("Device", "")
    lot_id = inspection.get("LotID", "")
    glass_id = inspection.get("GlassID", "")
    max_defs_estimate = inspection.get("MaxDefsEstimate", 0)
    layer = inspection.get("Layer", "")

    scan_dt = to_dt_from_unix_str(start_date)
    if scan_dt is None:
        logger.warning(f"[extract_records_from_defect_file] invalid StartDate: {file_path}")
        return []

    if not glass_id:
        logger.warning(f"[extract_records_from_defect_file] empty GlassID: {file_path}")
        return []

    cst, flowindex = extract_cst_flowindex_from_filename(fn)
    glass_type = infer_glass_type(device)
    pi_type = infer_pi_type(device, default_pi_type=default_pi_type)
    aoi = normalize_aoi(machine_id)

    try:
        source_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
    except Exception:
        source_mtime = datetime.now()

    try:
        defect_count_int = int(float(max_defs_estimate or 0))
    except Exception:
        defect_count_int = 0

    base = {
        "sheet_id_chip_id": glass_id,
        "test_time": scan_dt,
        "adc_def_code": "",
        "retype_def_code": "",
        "recipe_id": device,
        "line_id": str(default_line_id),
        "aoi": aoi,
        "model": layer,
        "glass_type": glass_type,
        "pi_time": None,
        "pi_type": pi_type,
        "cst_id": lot_id,
        "defect_count": defect_count_int,
        "source_file": fn,
        "source_mtime": source_mtime,
    }

    rows: List[dict] = []

    # =====================================================
    # 1. 正常 defect records
    # =====================================================
    defect_list = safe_list(defects_node.get("Defect") if isinstance(defects_node, dict) else None)

    if defect_list:
        for d in defect_list:
            if not isinstance(d, dict):
                continue

            coord = d.get("Coordinate", {}) or {}
            img_node = d.get("Images", {}) or {}
            img_data = img_node.get("Image") if isinstance(img_node, dict) else None
            img_list = safe_list(img_data)

            image_file = ""
            if img_list and isinstance(img_list[0], dict):
                image_file = str((img_list[0] or {}).get("file", "")).strip()

            rep_id = d.get("RepID", "")
            chip_id = f"{glass_id}{rep_id}" if rep_id not in ("", None, "N/A") else glass_id

            area_size = d.get("AreaSize", 0)
            defect_id = str(d.get("DefectID", "")).strip() or "0"

            judge_defect = d.get("JudgeDefect", {}) or {}
            if not isinstance(judge_defect, dict):
                judge_defect = {}

            size_class = str(judge_defect.get("SizeClass", "")).strip()

            try:
                pox_x1 = round(float(coord.get("X", 0)) * 1000)
                pox_y1 = round(1500000 - float(coord.get("Y", 0)) * 1000)
            except Exception:
                pox_x1, pox_y1 = 0, 0

            try:
                area_size_str = str(round(float(area_size)))
            except Exception:
                area_size_str = "0"

            img_rel_path = (
                f"PIT/{scan_dt.strftime('%y%m/%d')}/"
                f"{machine_id}/{glass_id}/{scan_dt.strftime('%H%M')}/"
            )

            pic_path = (
                f"http://10.97.139.98:1454/"
                f"{machine_id}/{cst}/{glass_id}/PCS1/{flowindex}/CaptureImage/small/{image_file}"
                if image_file else ""
            )

            row = dict(base)
            row.update({
                "chip_id": chip_id,
                "defect_size": size_class,
                "size_class": area_size_str,
                "pox_x1": int(pox_x1),
                "pox_y1": int(pox_y1),
                "image_file_name": image_file,
                "img_file_url_path": img_rel_path,
                "pic_path": pic_path,
                "defect_id": defect_id,
            })
            rows.append(row)

    # =====================================================
    # 2. 不論有沒有 defect，都 append .macro / .marco 原點影像 records
    # =====================================================
    macro_img_names = extract_macro_image_paths(source_dir, fn)
    for idx, img_name in enumerate(macro_img_names, start=1):
        pic_path = (
            f"http://10.97.139.98:1454/"
            f"{machine_id}/{lot_id}/{glass_id}/PCS1/{flowindex}/Map/{img_name}"
        )
        row = dict(base)
        row.update({
            "chip_id": f"{glass_id}_macro_{idx}",
            "defect_size": "OK",
            "size_class": "0",
            "pox_x1": 0,
            "pox_y1": 0,
            "image_file_name": img_name,
            "img_file_url_path": (
                f"PIT/{scan_dt.strftime('%y%m/%d')}/"
                f"{machine_id}/{glass_id}/{scan_dt.strftime('%H%M')}/Map/"
            ),
            "pic_path": pic_path,
            "defect_id": f"MACRO_{idx}",
        })
        rows.append(row)

    # =====================================================
    # 3. 沒有 defect，也沒有 macro 時，仍寫一筆 placeholder
    # =====================================================
    if not rows:
        row = dict(base)
        row.update({
            "chip_id": f"{glass_id}0",
            "defect_size": "OK",
            "size_class": "0",
            "pox_x1": 0,
            "pox_y1": 0,
            "image_file_name": "",
            "img_file_url_path": "",
            "pic_path": "",
            "defect_id": "NO_DEFECT",
        })
        rows.append(row)

    return rows

    
# =========================================================
# Main run
# =========================================================
def one_run(
    cfg: DBConfig,
    source_dir: str,
    start_dt: datetime,
    end_dt: datetime,
    default_line_id: str,
    default_pi_type: str,
):
    logger.info(f"[one_run] source_dir={source_dir}")
    logger.info(f"[one_run] start_dt={start_dt}, end_dt={end_dt}")

    if not os.path.exists(source_dir):
        logger.warning(f"[one_run] source dir not exists: {source_dir}")
        return

    db = MySQLDB(cfg.raw_db, cfg)

    all_files = []
    for name in os.listdir(source_dir):
        if name.lower().endswith(".defect"):
            fp = os.path.join(source_dir, name)
            if file_mtime_in_range(fp, start_dt, end_dt):
                all_files.append(fp)

    all_files.sort()
    logger.info(f"[one_run] matched defect files: {len(all_files)}")

    month_rows: Dict[str, List[dict]] = {}

    for fp in all_files:
        try:
            rows = extract_records_from_defect_file(
                fp,
                source_dir=source_dir,
                default_line_id=default_line_id,
                default_pi_type=default_pi_type,
            )

            if not rows:
                continue

            for r in rows:
                tbn = build_month_table_name(r["test_time"])
                month_rows.setdefault(tbn, []).append(r)

            logger.info(f"[one_run] file={os.path.basename(fp)} extracted_rows={len(rows)}")
        except Exception:
            logger.exception(f"[one_run] failed file: {fp}")

    if not month_rows:
        logger.info("[one_run] no rows extracted")
        return

    for tbn, rows in month_rows.items():
        ensure_raw_table(db, tbn)
        db.upsert_rows(tbn, rows)
        logger.info(f"[one_run] upsert {tbn}: {len(rows)} rows")

    logger.info("[one_run] done")


# =========================================================
# CLI
# =========================================================
def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="RTMS AOI300 raw defect job")

    p.add_argument("--host", type=str, default="127.0.0.1")
    p.add_argument("--port", type=int, default=3306)
    p.add_argument("--user", type=str, default="l6a01_user")
    p.add_argument("--pwd", type=str, default="l6a01$user")
    p.add_argument("--raw-db", type=str, default="rtms_piaoi_other")

    p.add_argument("--source-dir", type=str, default=r"\\10.97.136.13\\rtms")
    p.add_argument("--line-id", type=str, default="Null")
    p.add_argument("--pi-type", type=str, default="Null")

    p.add_argument("--once", action="store_true")
    p.add_argument("--every-min", type=int, default=10)
    p.add_argument("--lookback-min", type=int, default=180)
    p.add_argument("--lag-min", type=int, default=2)

    p.add_argument("--start-dt", type=str, default=None)
    p.add_argument("--end-dt", type=str, default=None)
    p.add_argument("--date", type=str, default=None)

    return p


def main():
    args = build_arg_parser().parse_args()

    cfg = DBConfig(
        host=args.host,
        port=args.port,
        user=args.user,
        pwd=args.pwd,
        raw_db=args.raw_db,
    )

    start_dt = parse_dt(args.start_dt)
    end_dt = parse_dt(args.end_dt)

    if args.once:
        sdt, edt = resolve_window(
            start_dt=start_dt,
            end_dt=end_dt,
            date_str=args.date,
            lookback_min=args.lookback_min,
            lag_min=args.lag_min,
        )
        one_run(
            cfg=cfg,
            source_dir=args.source_dir,
            start_dt=sdt,
            end_dt=edt,
            default_line_id=args.line_id,
            default_pi_type=args.pi_type,
        )
        return

    every_sec = max(1, args.every_min * 60)
    while True:
        t0 = time.time()
        try:
            sdt, edt = resolve_window(
                start_dt=start_dt,
                end_dt=end_dt,
                date_str=args.date,
                lookback_min=args.lookback_min,
                lag_min=args.lag_min,
            )
            one_run(
                cfg=cfg,
                source_dir=args.source_dir,
                start_dt=sdt,
                end_dt=edt,
                default_line_id=args.line_id,
                default_pi_type=args.pi_type,
            )
        except Exception:
            logger.exception("[main] run failed")

        sleep_sec = max(0.0, every_sec - (time.time() - t0))
        time.sleep(sleep_sec)


if __name__ == "__main__":
    main()


"""
# 單次執行：最近 3 小時
python rtms_aoi300_raw_job.py --once

# 單次執行：指定區間
python rtms_aoi300_raw_job.py --once --start-dt "2026-05-01 07:30:00" --end-dt "2026-05-07 17:00:00"

# 常駐，每 10 分鐘跑一次
python rtms_aoi300_raw_job.py
"""

