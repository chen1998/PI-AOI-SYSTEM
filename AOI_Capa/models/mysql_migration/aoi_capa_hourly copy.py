#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AOI 機台每日 CAPA 彙總 & 每小時 Raw 資料產出

功能說明：
- 來源：各 AOI 的 summary 表
    aoi100 → aoi_summary_aoi100
    aoi200 → aoi_summary_aoi200
    aoi300 → aoi_summary_aoi300_capa

- 輸出：
    1) {aoi}_capa_summary
        - 日彙總表(by aoi, run_day, pi_type, ALL)
        - 欄位：
          ['aoi', 'run_day', 'pi_type',
           'total_glass', 'target_count', 'spec', 'real_day_capa',
           'comment', 'editor']

    2) {aoi}_capa_hourly_rawdata
        - 每小時 Raw(by aoi, run_day, hour_int, pi_type, ALL)
        - 欄位：
          ['aoi', 'run_day', 'hour_int', 'pi_type',
           'hour', 'cumu', 'real_hour_capa', 'real_cumu_capa']
        - 不存 target_count / spec(要用時再 join summary)

執行模式：
- --mode today
    → 只處理「今天」的資料

- --mode date --date YYYY-MM-DD
    → 只處理指定某一天

- --mode range --start YYYY-MM-DD [--end YYYY-MM-DD]
    → 回溯區間：
        start ~ end（含），end 預設為「今天」，
        若 end > 今天，會自動截斷到今天。
        區間內每一天都會跑一輪 AOI。

target_count / spec / comment / editor 的決策順序（對每個 AOI + run_day）：
1) 若 {aoi}_capa_summary 中已存在 run_day = 當天 的資料：
   → 完整沿用（包含前端編輯過的 target_count / spec / comment / editor）

2) 若當天沒有資料，但有前一天資料：
   → 延用「前一天的 target_count / spec」，
      comment / editor 改為 "default\\n{本次執行時間}"

3) 若連前一天也沒有資料：
   → 使用程式內建預設：
        capa_glassnum_cfg[aoi] → target_count
        capa_spec_cfg[aoi]     → spec
      並寫入 comment / editor = "default\\n{本次執行時間}"

寫入邏輯：
- 每次執行某一個 (aoi, run_day) 時：
  - 會先 DELETE 該日該 AOI 在 summary / hourly 裡的舊資料
  - 再把該日完整結果寫入
"""

import argparse
import logging
from datetime import datetime, date, timedelta
from typing import List, Dict

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from sql_db_func import MySQLConnetFunc  # 你原本的 DB handler

# ======== Logging 設定 ========

logger = logging.getLogger("aoi_capa_job")
logger.setLevel(logging.INFO)

if not logger.handlers:
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        "%Y-%m-%d %H:%M:%S"
    )

    # 寫檔
    fh = logging.FileHandler("aoi_capa_daily_job.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Console
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

# ======== 可調參數區 ========

DB_NAME = "l6a01_project"

# AOI 清單（若你有 cfg.aoi_names，可直接改掉這一行）
AOI_LIST = ["aoi100", "aoi200", "aoi300"]

# 每台 AOI 預設每日 target 片數
capa_glassnum_cfg: Dict[str, float] = {
    "aoi100": 168,
    "aoi200": 238,
    "aoi300": 203,
}

# 每台 AOI 預設 spec（原本 offset 改名為 spec）
capa_spec_cfg: Dict[str, float] = {
    "aoi100": 90,
    "aoi200": 90,
    "aoi300": 90,
}


# 來源表名稱規則：aoi300 例外用 aoi_summary_aoi300_capa
def get_source_table_name(aoi: str) -> str:
    if aoi == "aoi300":
        return "aoi_summary_aoi300_capa"
    return f"aoi_summary_{aoi}"


# ======== 共用工具 ========

def build_run_days(mode: str,
                   date_str: str = None,
                   start_str: str = None,
                   end_str: str = None) -> List[date]:
    """
    根據模式產出要處理的 run_day 列表。
    - today: [今天]
    - date:  [指定日期]
    - range: [start ~ end]，end 預設今天；若 end > 今天 → 截斷為今天
    """
    today = datetime.now().date()

    if mode == "today":
        return [today]

    if mode == "date":
        if not date_str:
            raise ValueError("--mode date 時必須提供 --date YYYY-MM-DD")
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        return [d]

    if mode == "range":
        if not start_str:
            raise ValueError("--mode range 時必須提供 --start YYYY-MM-DD")
        start = datetime.strptime(start_str, "%Y-%m-%d").date()
        if end_str:
            end = datetime.strptime(end_str, "%Y-%m-%d").date()
        else:
            end = today

        # 若 end 在未來 → 自動截斷到今天
        if end > today:
            logger.warning(f"--end {end} 在未來，自動改為今天 {today}")
            end = today

        if start > end:
            raise ValueError(f"日期區間錯誤：start({start}) > end({end})")

        days: List[date] = []
        cur = start
        while cur <= end:
            days.append(cur)
            cur += timedelta(days=1)
        return days

    raise ValueError(f"不支援的 mode: {mode}")


def load_aoi_source_for_day(db: MySQLConnetFunc, aoi: str, run_day: date) -> pd.DataFrame:
    """
    從 aoi_summary_* 撈出指定 run_day 的 raw 資料（只撈必要欄位）：
        ['scantime', 'glass_id', 'recipe_id', run_day]
    """
    table_name = get_source_table_name(aoi)
    cols = ["scantime", "glass_id", "recipe_id"]

    logger.info(f"[load_aoi_source_for_day] 撈取 {table_name} run_day={run_day}")
    try:
        sql = f"""
            SELECT {", ".join(f"`{c}`" for c in cols)},
                   DATE(`scantime`) AS `run_day`
            FROM `{table_name}`
            WHERE DATE(`scantime`) = :run_day
        """
        with db.engine.connect() as conn:
            df = pd.read_sql(text(sql), conn, params={"run_day": run_day})
        logger.info(f"[load_aoi_source_for_day] {table_name} run_day={run_day} 取回 {len(df)} rows")
        return df
    except SQLAlchemyError as e:
        logger.error(f"[load_aoi_source_for_day] 撈取 {table_name} 失敗: {e}")
        return pd.DataFrame(columns=["scantime", "glass_id", "recipe_id", "run_day"])


def classify_pi_type(aoi: str, df: pd.DataFrame) -> pd.DataFrame:
    """
    依照 AOI 與 recipe_id，把資料分成 pi_type 群（API / BPI / ITO ...）
    傳回多一欄 pi_type 的 DataFrame
    """
    df = df.copy()

    if df.empty:
        df["pi_type"] = np.nan
        return df

    rcp = df["recipe_id"].astype(str)

    if aoi in ["aoi100", "aoi200"]:
        df = df[rcp.str[0].isin(["2", "3", "4", "5"])]
        r1 = df["recipe_id"].astype(str).str[0]
        df["pi_type"] = r1.map({
            "2": "API",
            "4": "API",
            "3": "BPI",
            "5": "BPI",
        }).fillna("")

    elif aoi == "aoi300":
        charts = ["CELL-ITO", "API", "BPI", "ITO"]
        mask = rcp.apply(lambda x: x == charts[0] or any(c in x for c in charts[1:]))
        df = df[mask]

        conditions = [
            df["recipe_id"].astype(str).str.contains("API", na=False),
            df["recipe_id"].astype(str).str.contains("BPI", na=False),
            df["recipe_id"].astype(str).str.contains("CELL-ITO", na=False),
            df["recipe_id"].astype(str).str.contains("ITO", na=False),
        ]
        choices = ["API", "BPI", "ITO", "ITO"]
        df["pi_type"] = np.select(conditions, choices, default=None)

    else:
        df["pi_type"] = "ALL"

    return df


def get_pi_type_list_for_aoi(aoi: str) -> List[str]:
    """依 AOI 給出該 AOI 應有的 pi_type 列表（不含 ALL）"""
    if aoi in ["aoi100", "aoi200"]:
        return ["API", "BPI"]
    elif aoi == "aoi300":
        return ["API", "BPI", "ITO"]
    else:
        return []


def get_prev_or_default_target_spec(
    db: MySQLConnetFunc,
    aoi: str,
    run_day: date,
    pi_types: List[str],
) -> Dict[str, Dict[str, object]]:
    """
    取得某 AOI 某一天各 pi_type 的 target_count / spec / comment / editor 預設值。

    優先順序：
      1) {aoi}_capa_summary 中 run_day = 當天 → 完整沿用
      2) 若無，找 run_day - 1 → 延用 target/spec，comment/editor = default\\n{now}
      3) 若仍無 → 用 cfg 預設，comment/editor = default\\n{now}
    """
    summary_table = f"{aoi}_capa_summary"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    default_target = capa_glassnum_cfg.get(aoi, np.nan)
    default_spec = capa_spec_cfg.get(aoi, np.nan)

    # 1) 當天
    try:
        sql_today = f"""
            SELECT *
            FROM `{summary_table}`
            WHERE `aoi` = :aoi AND `run_day` = :run_day
        """
        with db.engine.connect() as conn:
            df_today = pd.read_sql(
                text(sql_today),
                conn,
                params={"aoi": aoi, "run_day": run_day}
            )
    except SQLAlchemyError:
        df_today = pd.DataFrame()

    mapping: Dict[str, Dict[str, object]] = {}

    if not df_today.empty:
        logger.info(f"[get_prev_or_default_target_spec] 使用 {summary_table} 當天設定 ({aoi}, {run_day})")
        for pt in pi_types + ["ALL"]:
            row = df_today[df_today["pi_type"] == pt]
            if not row.empty:
                r0 = row.iloc[0]
                mapping[pt] = {
                    "target_count": r0.get("target_count", default_target),
                    "spec": r0.get("spec", default_spec),
                    "comment": r0.get("comment", ""),
                    "editor": r0.get("editor", ""),
                }

        all_row = mapping.get("ALL", {
            "target_count": default_target,
            "spec": default_spec,
            "comment": f"default\n{now_str}",
            "editor": f"default\n{now_str}",
        })
        for pt in pi_types + ["ALL"]:
            if pt not in mapping:
                mapping[pt] = dict(all_row)
        return mapping

    # 2) 前一天
    prev_day = run_day - timedelta(days=1)
    try:
        sql_prev = f"""
            SELECT *
            FROM `{summary_table}`
            WHERE `aoi` = :aoi AND `run_day` = :run_day
        """
        with db.engine.connect() as conn:
            df_prev = pd.read_sql(
                text(sql_prev),
                conn,
                params={"aoi": aoi, "run_day": prev_day}
            )
    except SQLAlchemyError:
        df_prev = pd.DataFrame()

    if not df_prev.empty:
        logger.info(f"[get_prev_or_default_target_spec] 沿用 {summary_table} 前一天設定 ({aoi}, {prev_day})")
        for pt in pi_types + ["ALL"]:
            row = df_prev[df_prev["pi_type"] == pt]
            if not row.empty:
                r0 = row.iloc[0]
                mapping[pt] = {
                    "target_count": r0.get("target_count", default_target),
                    "spec": r0.get("spec", default_spec),
                    "comment": f"default\n{now_str}",
                    "editor": f"default\n{now_str}",
                }

    if not mapping:
        logger.info(f"[get_prev_or_default_target_spec] 使用 cfg 預設 target/spec ({aoi}, {run_day})")
        base = {
            "target_count": default_target,
            "spec": default_spec,
            "comment": f"default\n{now_str}",
            "editor": f"default\n{now_str}",
        }
        for pt in pi_types + ["ALL"]:
            mapping[pt] = dict(base)
        return mapping

    all_row = mapping.get("ALL", {
        "target_count": default_target,
        "spec": default_spec,
        "comment": f"default\n{now_str}",
        "editor": f"default\n{now_str}",
    })
    for pt in pi_types + ["ALL"]:
        if pt not in mapping:
            mapping[pt] = dict(all_row)
    return mapping


def delete_existing_day(db: MySQLConnetFunc, table_name: str, aoi: str, run_day: date):
    """刪除指定表中同一天同 AOI 的舊資料"""
    try:
        sql = f"DELETE FROM `{table_name}` WHERE `aoi` = :aoi AND `run_day` = :run_day"
        with db.engine.begin() as conn:
            conn.execute(text(sql), {"aoi": aoi, "run_day": run_day})
        logger.info(f"[delete_existing_day] {table_name} 刪除 ({aoi}, {run_day}) 舊資料")
    except SQLAlchemyError as e:
        logger.error(f"[delete_existing_day] 刪除 {table_name} ({aoi}, {run_day}) 失敗: {e}")


def upsert_day_summary(
    db: MySQLConnetFunc,
    aoi: str,
    run_day: date,
    day_total_glass: Dict[str, int],
    target_spec_map: Dict[str, Dict[str, object]],
    pi_types: List[str],
):
    """
    寫入日彙總表 {aoi}_capa_summary：
    - 先刪除該 aoi + run_day 的舊資料
    - 再寫入新的每 pi_type + ALL row
    """
    summary_table = f"{aoi}_capa_summary"

    records = []
    for pt in pi_types:
        ts = target_spec_map.get(pt, target_spec_map["ALL"])
        total = day_total_glass.get(pt, 0)
        tgt = ts["target_count"]
        spec = ts["spec"]

        if not (tgt and np.isfinite(tgt)):
            real_capa = 0.0
        else:
            real_capa = round(total / tgt, 2)

        records.append({
            "aoi": aoi,
            "run_day": run_day,
            "pi_type": pt,
            "total_glass": total,
            "target_count": tgt,
            "spec": spec,
            "real_day_capa": real_capa,
            "comment": ts["comment"],
            "editor": ts["editor"],
        })

    ts_all = target_spec_map["ALL"]
    total_all = day_total_glass.get("ALL", 0)
    tgt_all = ts_all["target_count"]
    spec_all = ts_all["spec"]

    if not (tgt_all and np.isfinite(tgt_all)):
        real_capa_all = 0.0
    else:
        real_capa_all = round(total_all / tgt_all, 2)

    records.append({
        "aoi": aoi,
        "run_day": run_day,
        "pi_type": "ALL",
        "total_glass": total_all,
        "target_count": tgt_all,
        "spec": spec_all,
        "real_day_capa": real_capa_all,
        "comment": ts_all["comment"],
        "editor": ts_all["editor"],
    })

    df_day = pd.DataFrame.from_records(records)

    delete_existing_day(db, summary_table, aoi, run_day)
    try:
        df_day.to_sql(summary_table, db.engine, index=False, if_exists="append")
        logger.info(f"[upsert_day_summary] {summary_table} 寫入 {len(df_day)} rows ({aoi}, {run_day})")
    except SQLAlchemyError as e:
        logger.error(f"[upsert_day_summary] 寫入 {summary_table} 失敗: {e}")


def upsert_hourly_raw(
    db: MySQLConnetFunc,
    aoi: str,
    run_day: date,
    hourly_usage: pd.DataFrame,
    target_spec_map: Dict[str, Dict[str, object]],
    pi_types: List[str],
):
    """
    寫入 {aoi}_capa_hourly_rawdata：
    - 每個 pi_type + ALL，每小時 0~23 的 hour / cumu / capa
    - 先刪除該日舊資料再寫入
    - 不存 target_count / spec（只存計算結果）
    """
    hourly_table = f"{aoi}_capa_hourly_rawdata"

    if hourly_usage.empty:
        logger.info(f"[upsert_hourly_raw] {aoi}, {run_day} 無 hourly_usage，建立全 0 資料")
        hours = list(range(24))
        records = []
        for pt in pi_types + ["ALL"]:
            ts = target_spec_map.get(pt, target_spec_map["ALL"])
            tgt = ts["target_count"]
            cumu = 0
            for h in hours:
                hour_val = 0
                cumu += hour_val
                if not (tgt and np.isfinite(tgt)):
                    rh = 0.0
                    rc = 0.0
                else:
                    rh = round(hour_val / tgt, 2)
                    rc = round(cumu / tgt, 2)
                records.append({
                    "aoi": aoi,
                    "run_day": run_day,
                    "hour_int": h,
                    "pi_type": pt,
                    "hour": hour_val,
                    "cumu": cumu,
                    "real_hour_capa": rh,
                    "real_cumu_capa": rc,
                })
        df_hour = pd.DataFrame.from_records(records)

    else:
        df = hourly_usage.copy()
        records = []

        # 1) 各 pi_type
        for pt in pi_types:
            sub = df[df["pi_type"] == pt].copy()
            ts = target_spec_map.get(pt, target_spec_map["ALL"])
            tgt = ts["target_count"]

            if sub.empty:
                cumu = 0
                for h in range(24):
                    hour_val = 0
                    cumu += hour_val
                    if not (tgt and np.isfinite(tgt)):
                        rh = 0.0
                        rc = 0.0
                    else:
                        rh = round(hour_val / tgt, 2)
                        rc = round(cumu / tgt, 2)
                    records.append({
                        "aoi": aoi,
                        "run_day": run_day,
                        "hour_int": h,
                        "pi_type": pt,
                        "hour": hour_val,
                        "cumu": cumu,
                        "real_hour_capa": rh,
                        "real_cumu_capa": rc,
                    })
                continue

            sub = sub.sort_values("hour_int")
            hour_series = sub["glass_count_f"].fillna(0)
            cumu_series = sub["glass_pi"].fillna(0)

            for h, hv, cv in zip(sub["hour_int"], hour_series, cumu_series):
                if not (tgt and np.isfinite(tgt)):
                    rh = 0.0
                    rc = 0.0
                else:
                    rh = round(hv / tgt, 2)
                    rc = round(cv / tgt, 2)
                records.append({
                    "aoi": aoi,
                    "run_day": run_day,
                    "hour_int": int(h),
                    "pi_type": pt,
                    "hour": int(hv),
                    "cumu": int(cv),
                    "real_hour_capa": rh,
                    "real_cumu_capa": rc,
                })

        # 2) ALL（全部 pi_type 相加）
        df_all = (
            df.groupby("hour_int", as_index=False)["glass_count_f"]
              .sum()
              .rename(columns={"glass_count_f": "glass_count_all"})
        )
        df_all = df_all.sort_values("hour_int")
        df_all["glass_all_cumu"] = df_all["glass_count_all"].cumsum()

        ts_all = target_spec_map["ALL"]
        tgt_all = ts_all["target_count"]

        for h, hv, cv in zip(
            df_all["hour_int"],
            df_all["glass_count_all"],
            df_all["glass_all_cumu"],
        ):
            if not (tgt_all and np.isfinite(tgt_all)):
                rh = 0.0
                rc = 0.0
            else:
                rh = round(hv / tgt_all, 2)
                rc = round(cv / tgt_all, 2)
            records.append({
                "aoi": aoi,
                "run_day": run_day,
                "hour_int": int(h),
                "pi_type": "ALL",
                "hour": int(hv),
                "cumu": int(cv),
                "real_hour_capa": rh,
                "real_cumu_capa": rc,
            })

        df_hour = pd.DataFrame.from_records(records)

    delete_existing_day(db, hourly_table, aoi, run_day)
    try:
        df_hour.to_sql(hourly_table, db.engine, index=False, if_exists="append")
        logger.info(f"[upsert_hourly_raw] {hourly_table} 寫入 {len(df_hour)} rows ({aoi}, {run_day})")
    except SQLAlchemyError as e:
        logger.error(f"[upsert_hourly_raw] 寫入 {hourly_table} 失敗: {e}")


# ======== 主流程 ========

def process_aoi_for_day(db: MySQLConnetFunc, aoi: str, run_day: date):
    """
    處理單一 AOI + 指定 run_day 的全流程：
      1) 從 source 撈當天 raw
      2) 分類 pi_type
      3) 計算每小時 glass_count & 累積
      4) 產出：
         - 日彙總 {aoi}_capa_summary
         - 每小時 raw {aoi}_capa_hourly_rawdata
    """
    logger.info(f"=== 處理 AOI={aoi}, run_day={run_day} 開始 ===")

    pi_types = get_pi_type_list_for_aoi(aoi)

    # 1) 撈當天 raw
    src = load_aoi_source_for_day(db, aoi, run_day)
    if src.empty:
        logger.warning(f"[{aoi}] {run_day} 無 source raw，建立 0 值日彙總 & hourly")
        target_spec_map = get_prev_or_default_target_spec(db, aoi, run_day, pi_types)
        day_total_glass = {pt: 0 for pt in pi_types + ["ALL"]}
        upsert_day_summary(db, aoi, run_day, day_total_glass, target_spec_map, pi_types)
        empty_hourly = pd.DataFrame()
        upsert_hourly_raw(db, aoi, run_day, empty_hourly, target_spec_map, pi_types)
        logger.info(f"=== 處理 AOI={aoi}, run_day={run_day} 結束 (無資料) ===")
        return

    # 2) 分 pi_type
    src["scantime"] = pd.to_datetime(src["scantime"], errors="coerce")
    src = src.dropna(subset=["scantime"])
    if src.empty:
        logger.warning(f"[{aoi}] {run_day} scantime 全無效，視為無資料")
        target_spec_map = get_prev_or_default_target_spec(db, aoi, run_day, pi_types)
        day_total_glass = {pt: 0 for pt in pi_types + ["ALL"]}
        upsert_day_summary(db, aoi, run_day, day_total_glass, target_spec_map, pi_types)
        empty_hourly = pd.DataFrame()
        upsert_hourly_raw(db, aoi, run_day, empty_hourly, target_spec_map, pi_types)
        logger.info(f"=== 處理 AOI={aoi}, run_day={run_day} 結束 (scantime 無效) ===")
        return

    src = classify_pi_type(aoi, src)

    base_pi_types = get_pi_type_list_for_aoi(aoi)
    actual_pts = sorted({pt for pt in src["pi_type"].dropna().unique() if pt in base_pi_types})
    if actual_pts:
        pi_types = actual_pts
    else:
        pi_types = base_pi_types

    logger.info(f"[{aoi}] {run_day} pi_type = {pi_types}")

    # 3) 計算每小時 glass_count / 累積
    src["hour_int"] = src["scantime"].dt.hour

    cnt = (
        src.groupby(["run_day", "hour_int", "pi_type"], dropna=False)["glass_id"]
           .size()
           .rename("glass_count")
           .reset_index()
    )
    cnt = cnt[cnt["run_day"] == run_day]

    hours = pd.Series(range(24), name="hour_int")
    full_idx = pd.MultiIndex.from_product(
        [[run_day], hours, pi_types],
        names=["run_day", "hour_int", "pi_type"]
    )
    full_frame = pd.DataFrame(index=full_idx).reset_index()

    hourly_usage = (
        full_frame
        .merge(cnt, on=["run_day", "hour_int", "pi_type"], how="left")
        .sort_values(["run_day", "pi_type", "hour_int"])
        .reset_index(drop=True)
    )
    hourly_usage["glass_count_f"] = hourly_usage["glass_count"].fillna(0)

    hourly_usage["glass_pi"] = (
        hourly_usage
        .groupby(["run_day", "pi_type"], dropna=False)["glass_count_f"]
        .cumsum()
    )

    # 4) 取得 target/spec/comment/editor
    target_spec_map = get_prev_or_default_target_spec(db, aoi, run_day, pi_types)

    # 5) 日 total_glass
    day_total_glass: Dict[str, int] = {}
    for pt in pi_types:
        sub = hourly_usage[hourly_usage["pi_type"] == pt]
        if sub.empty:
            day_total_glass[pt] = 0
        else:
            day_total_glass[pt] = int(sub["glass_pi"].iloc[-1])

    day_total_glass["ALL"] = int(sum(day_total_glass.get(pt, 0) for pt in pi_types))
    logger.info(f"[{aoi}] {run_day} day_total_glass = {day_total_glass}")

    # 6) 寫入日彙總
    upsert_day_summary(db, aoi, run_day, day_total_glass, target_spec_map, pi_types)

    # 7) 寫入 hourly raw
    upsert_hourly_raw(db, aoi, run_day, hourly_usage, target_spec_map, pi_types)

    logger.info(f"=== 處理 AOI={aoi}, run_day={run_day} 完成 ===")


def main():
    parser = argparse.ArgumentParser(description="AOI CAPA 日彙總 & Hourly Raw Job")
    parser.add_argument(
        "--mode",
        choices=["today", "date", "range"],
        default="today",
        help=(
            "today: 處理今天; "
            "date: 指定單一天 (--date YYYY-MM-DD); "
            "range: 回溯區間 (--start YYYY-MM-DD [--end YYYY-MM-DD])"
        )
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="當 --mode=date 時，指定要處理的日期 (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="當 --mode=range 時，指定起始日期 (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="當 --mode=range 時，指定結束日期 (YYYY-MM-DD)，預設=今天"
    )

    args = parser.parse_args()

    run_days = build_run_days(args.mode, args.date, args.start, args.end)
    logger.info(f"=== AOI CAPA Job 啟動 mode={args.mode}, run_days={run_days} ===")

    db = MySQLConnetFunc(DB_NAME)

    # range 模式會有多天，這裡確保是由小到大跑，前一天 summary 寫完後 DB 就有資料，
    # 隔一天在 get_prev_or_default_target_spec 就能沿用前一天設定
    for rd in sorted(run_days):
        for aoi in AOI_LIST:
            process_aoi_for_day(db, aoi, rd)

    logger.info("=== AOI CAPA Job 結束 ===")


if __name__ == "__main__":
    main()