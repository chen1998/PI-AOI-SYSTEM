from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from typing import Optional, Dict, List
from datetime import datetime, timedelta, date
import pandas as pd

from models.sql_db_connect import MySQLConnet

import logging
router = APIRouter(tags=["duty_cell_piaoi_same_point"])
logger = logging.getLogger()

class Config:
    def __init__(self):
        now = datetime.now()
        logging.info(f"新版 defect map router 連線時間: {now}")

        self.summary_db = "piaoi_ol_defect_map"
        self.raw_db_cim = "cim_piaoi"
        self.raw_db_rtms = "rtms_piaoi_other"

        self.aoi_names = [f"aoi{i}00" for i in range(1, 4)]
        self.all_aoi_tabs = self.aoi_names[:]

        self.run_info_keys = [
            "run_day", "test_time", "sheet_id_chip_id",
            "recipe_id", "line_id", "aoi", "pi_time", "pi_type"
        ]
        self.defect_summary_keys = [
            "defect_count", "over_defect_count", "large_defect_count",
            "middle_defect_count", "small_defect_count"
        ]
        self.run_info_table_cols = self.run_info_keys + ["defect_summary"]

    @staticmethod
    def normalize_aoi(v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        s = str(v).strip().lower()
        return s if s in {"aoi100", "aoi200", "aoi300"} else None

    @staticmethod
    def normalize_line_id(v: Optional[str]) -> Optional[str]:
        """
        aoi100/aoi200: CAPICxxx
        aoi300: 允許 'Null'
        """
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None

        su = s.upper()
        if su.startswith("CAPIC"):
            return su
        if su == "NULL":
            return "Null"
        return s

    @staticmethod
    def parse_dt(v: Optional[str]) -> Optional[datetime]:
        if not v:
            return None

        v = str(v).strip()

        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M",
        ):
            try:
                return datetime.strptime(v, fmt)
            except ValueError:
                continue

        return None

    @staticmethod
    def month_range(start_dt: datetime, end_dt: datetime) -> List[str]:
        if start_dt > end_dt:
            start_dt, end_dt = end_dt, start_dt

        out = []
        cur = datetime(start_dt.year, start_dt.month, 1)
        end_m = datetime(end_dt.year, end_dt.month, 1)

        while cur <= end_m:
            out.append(cur.strftime("%Y%m"))
            if cur.month == 12:
                cur = datetime(cur.year + 1, 1, 1)
            else:
                cur = datetime(cur.year, cur.month + 1, 1)
        return out

    @staticmethod
    def build_summary_table_name(aoi: str, yyyymm: str) -> str:
        return f"{aoi}_{yyyymm}_api_summary_table"

    @staticmethod
    def build_cim_raw_defect_table_name(aoi: str, line_id: str, yyyymm: str) -> str:
        return f"cim_defect_{yyyymm}_{aoi}_{line_id.lower()}"

    @staticmethod
    def build_rtms_raw_defect_table_name(yyyymm: str) -> str:
        return f"rtms_aoi300_raw_{yyyymm}"

    def summary_table_clean_process(self, tb: pd.DataFrame) -> pd.DataFrame:
        if tb.empty:
            return pd.DataFrame(columns=self.run_info_table_cols)

        tb = tb.copy()
        for c in ["run_day", "test_time", "pi_time", "update_time"]:
            if c in tb.columns:
                tb[c] = pd.to_datetime(tb[c], errors="coerce")

        tb["defect_summary"] = [
            {
                key: int(row[key]) if pd.notna(row[key]) else 0
                for key in self.defect_summary_keys
            }
            for _, row in tb.iterrows()
        ]

        return tb[self.run_info_table_cols]

    def get_one_aoi_summary_data(
        self,
        dbhandler: MySQLConnet,
        aoi: str,
        start_dt: datetime,
        end_dt: datetime,
    ) -> pd.DataFrame:
        months = self.month_range(start_dt, end_dt)
        frames = []

        for yyyymm in months:
            tbn = self.build_summary_table_name(aoi, yyyymm)
            if not dbhandler.table_exists(tbn):
                continue

            tb = dbhandler.get_table_between(
                tbn,
                start_dt,
                end_dt,
                time_col="test_time"
            )
            if not tb.empty:
                frames.append(tb)

        if not frames:
            return pd.DataFrame(columns=self.run_info_table_cols)

        tb = pd.concat(frames, ignore_index=True)
        tb = tb.sort_values(["test_time", "sheet_id_chip_id"], ascending=[False, True])
        return self.summary_table_clean_process(tb)

    def get_all_run_info_data(
        self,
        dbhandler: MySQLConnet,
        start_dt: datetime,
        end_dt: datetime,
    ) -> Dict[str, Dict]:
        out = {}
        for aoi in self.all_aoi_tabs:
            tb = self.get_one_aoi_summary_data(dbhandler, aoi, start_dt, end_dt)
            out[aoi] = tb.to_dict(orient="index")
        return out

    def parse_defect_key(
        self,
        key: Optional[str],
        test_time: Optional[str],
        sheet_id_chip_id: Optional[str],
        recipe_id: Optional[str],
        line_id: Optional[str],
        aoi: Optional[str],
    ):
        """
        支援：
        1. test_time|sheet_id_chip_id|recipe_id|line_id|aoi
        2. test_time|sheet_id_chip_id|line_id|aoi
        3. test_time|sheet_id_chip_id|recipe_id
        4. test_time|sheet_id_chip_id
        """
        _test_time = test_time
        _sheet_id_chip_id = sheet_id_chip_id
        _recipe_id = recipe_id
        _line_id = line_id
        _aoi = aoi

        if key:
            parts = [p.strip() for p in str(key).split("|")]
            if len(parts) == 5:
                _test_time, _sheet_id_chip_id, _recipe_id, _line_id, _aoi = parts
            elif len(parts) == 4:
                _test_time, _sheet_id_chip_id, _line_id, _aoi = parts
            elif len(parts) == 3:
                _test_time, _sheet_id_chip_id, _recipe_id = parts
            elif len(parts) == 2:
                _test_time, _sheet_id_chip_id = parts

        _aoi = self.normalize_aoi(_aoi)
        _line_id = self.normalize_line_id(_line_id)

        return _test_time, _sheet_id_chip_id, _recipe_id, _line_id, _aoi

def defect_size_helper(x):
    if x in ["S", "M", "L", "O"]:
        return x
    else :
        return "O"

def json_safe(obj):
    if isinstance(obj, dict):
        return {k: json_safe(v) if k != "defect_size" else defect_size_helper(json_safe(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_safe(v) for v in obj]
    if isinstance(obj, tuple):
        return [json_safe(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(obj, date):
        return obj.strftime("%Y-%m-%d")
    if pd.isna(obj):
        return None
    return obj


@router.get("/run_info")
async def api_run_info(
    aoi: Optional[str] = Query(default=None, description="aoi100 / aoi200 / aoi300"),
    start: Optional[str] = Query(default=None, description="YYYY-MM-DD or YYYY-MM-DD HH:MM:SS"),
    end: Optional[str] = Query(default=None, description="YYYY-MM-DD or YYYY-MM-DD HH:MM:SS"),
):
    cfg = Config()
    dbhandler = MySQLConnet(cfg.summary_db)

    now = datetime.now()
    end_dt = cfg.parse_dt(end) if end else now
    start_dt = cfg.parse_dt(start) if start else (end_dt - timedelta(days=3))
    print(start_dt, end_dt)
    end_dt  = end_dt  + timedelta(days=1)
    if start_dt is None or end_dt is None:
        return JSONResponse(
            {
                "error": "invalid datetime format",
                "AllAoiTabs": cfg.all_aoi_tabs
            },
            status_code=400
        )

    if not aoi:
        all_run_info_dict = cfg.get_all_run_info_data(dbhandler, start_dt, end_dt)
        return {
            "AllRunInfoTableData": all_run_info_dict,
            "AllAoiTabs": cfg.all_aoi_tabs
        }

    aoi = cfg.normalize_aoi(aoi)
    if not aoi:
        return JSONResponse(
            {
                "error": "invalid aoi",
                "AllAoiTabs": cfg.all_aoi_tabs
            },
            status_code=400
        )

    try:
        tb = cfg.get_one_aoi_summary_data(dbhandler, aoi, start_dt, end_dt)
        return {
            "UniRunInfoTableData": tb.to_dict(orient="index"),
            "AllAoiTabs": cfg.all_aoi_tabs
        }
    except Exception as e:
        logging.info(f"[ERROR] {aoi} 查詢 api summary table 失敗: {e}")
        return {
            "UniRunInfoTableData": {},
            "AllAoiTabs": cfg.all_aoi_tabs
        }


@router.get("/gld_defect_map")
async def api_defect_data(
    key: Optional[str] = Query(default=None),
    test_time: Optional[str] = Query(default=None),
    sheet_id_chip_id: Optional[str] = Query(default=None),
    recipe_id: Optional[str] = Query(default=None),
    line_id: Optional[str] = Query(default=None, description="CAPIC100 / Null"),
    aoi: Optional[str] = Query(default=None, description="aoi100 / aoi200 / aoi300"),
):
    cfg = Config()

    _test_time, _sheet_id_chip_id, _recipe_id, _line_id, _aoi = cfg.parse_defect_key(
        key=key,
        test_time=test_time,
        sheet_id_chip_id=sheet_id_chip_id,
        recipe_id=recipe_id,
        line_id=line_id,
        aoi=aoi,
    )

    logging.info(f"[DEBUG] parsed key -> test_time={_test_time}, sheet_id_chip_id={_sheet_id_chip_id}, line_id={_line_id}, aoi={_aoi}")

    if not (_test_time and _sheet_id_chip_id and _aoi):
        return JSONResponse({
            "defects": [],
            "key": key
        })

    dt_obj = cfg.parse_dt(_test_time)
    if dt_obj is None:
        logging.info(f"[ERROR] invalid test_time: {_test_time}")
        return JSONResponse({
            "defects": [],
            "key": key,
            "error": "invalid test_time"
        })

    yyyymm = dt_obj.strftime("%Y%m")

    # ==========================================
    # raw source switch by aoi
    # ==========================================
    if _aoi == "aoi300":
        dbhandler = MySQLConnet(cfg.raw_db_rtms)
        raw_tbn = cfg.build_rtms_raw_defect_table_name(yyyymm)

        need_cols = [
            "sheet_id_chip_id",
            "chip_id",
            "test_time",
            "defect_size",
            "pox_x1",
            "pox_y1",
            "pic_path",
            "img_file_url_path",
            "image_file_name",
            "adc_def_code",
        ]
    else:
        if not _line_id:
            return JSONResponse({
                "defects": [],
                "key": key,
                "error": "missing line_id"
            })

        dbhandler = MySQLConnet(cfg.raw_db_cim)
        raw_tbn = cfg.build_cim_raw_defect_table_name(_aoi, _line_id, yyyymm)

        need_cols = [
            "sheet_id_chip_id",
            "chip_id",
            "test_time",
            "defect_size",
            "pox_x1",
            "pox_y1",
            "img_file_url_path",
            "image_file_name",
            "adc_def_code",
        ]

    if not dbhandler.table_exists(raw_tbn):
        return JSONResponse({
            "defects": [],
            "key": key,
            "raw_table": raw_tbn
        })

    key_dict = {
        "gid": _sheet_id_chip_id,
        "t": dt_obj.strftime("%Y-%m-%d %H:%M:%S")
    }

    logging.info(f"[查詢] {raw_tbn} - {key_dict}")

    rows = dbhandler.get_cim_defects_by_key(raw_tbn, key_dict, cols=need_cols)
    logging.info(f"[查詢結果] Defect 筆數: {len(rows)}")
    if rows:
        logging.info(rows[0])
        key_rows = []
        for r in rows:
            r['defect_size'] = r['defect_size'] if r['defect_size'] in ["S", "M", "L", "O"] else 'O'
            key_rows.append(r)
    
    safe_rows = json_safe(key_rows if key_rows else [])
    
    return JSONResponse({
        "defects": safe_rows,
        "key": key,
        "context": json_safe({
            "test_time": _test_time,
            "sheet_id_chip_id": _sheet_id_chip_id,
            "recipe_id": _recipe_id,
            "line_id": _line_id,
            "aoi": _aoi,
            "raw_table": raw_tbn
        })
    })
