#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AOI CAPA 日/時彙總批次程式

功能：
- 從 aoi_summary_{aoi} 讀取原始 glass run 資料
- 依 AOI / run_day / pi_type 建出：
    1) 日彙總表：f"{aoi}_capa_summary"
    2) 每小時彙總原始表：f"{aoi}_capa_hourly_rawdata"

- 支援 3 種模式：
    python aoi_capa.py --mode today                 : 只跑「今天」
    python aoi_capa.py --mode date  --date YYYY-MM-DD : 只跑指定日期
    python aoi_capa.py --mode range --start YYYY-MM-DD [--end YYYY-MM-DD]
        若未給 --end，預設跑到「今天」

日彙總欄位：
    aoi, run_day, pi_type, total_glass, target_count, spec,
    real_day_capa, comment, editor

Hourly 彙總欄位：
    aoi, run_day, hour_int, pi_type,
    hour, cumu, real_hour_capa, real_cumu_capa

- target_count / spec 會依照：
    1) 若 summary 表該日已有資料 → 直接沿用（保留使用者修改）
    2) 否則若有「前一日」資料 → 沿用前一日 target_count / spec
    3) 否則 → 使用程式內建預設值（capa_glassnum_cfg / capa_spec_cfg）
- comment 預設為空字串 ""
- editor：
    - 若沿用舊資料 → 保留原值
    - 若由程式建立新資料 → "default\\n{當次執行時間}"
"""

import argparse
import logging
import logging.handlers
import os
from datetime import datetime, date, timedelta
from typing import List, Tuple, Dict, Optional

import numpy as np
import pandas as pd
from sqlalchemy import text, inspect


from sql_db_func import MySQLConnetFunc  # 確認路徑與你的專案一致

# =========================
# Logging 設定（每週輪替，保留 8 份）
# =========================

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "aoi_capa_job.log")

logger = logging.getLogger("aoi_capa_job")
logger.setLevel(logging.INFO)
logger.handlers.clear()

fmt = logging.Formatter(
    "%(asctime)s %(levelname)s [%(funcName)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

file_handler = logging.handlers.TimedRotatingFileHandler(
    LOG_FILE, when="W0", interval=1, backupCount=8, encoding="utf-8"
)
file_handler.setFormatter(fmt)

console_handler = logging.StreamHandler()
console_handler.setFormatter(fmt)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

# =========================
# 參數設定
# =========================

# 要處理的 AOI 名稱（可以依需求調整）
AOI_NAMES = ["aoi100", "aoi200", "aoi300"]

# 每台 AOI 預設的 daily target_count
capa_glassnum_cfg: Dict[str, int] = {
    "aoi100": 168,
    "aoi200": 238,
    "aoi300": 203,
}

# 每台 AOI 預設的 spec（原本的 offset）
capa_spec_cfg: Dict[str, int] = {
    "aoi100": 90,
    "aoi200": 90,
    "aoi300": 90,
}

# 原始表中一定會撈出來的欄位
ORI_FIX_COLUMNS = ["run_day", "scantime", "glass_id", "recipe_id"]


# =========================
# 小工具
# =========================

def parse_yyyymmdd(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def get_pi_types_for_aoi(aoi: str) -> List[str]:
    """
    回傳該 AOI 需要在 summary 表中出現的 pi_type 列表（含 ALL）
    aoi100 / aoi200: API, BPI, ALL
    aoi300: API, BPI, ITO, ALL
    """
    if aoi in ("aoi100", "aoi200"):
        return ["API", "BPI", "ALL"]
    elif aoi == "aoi300":
        return ["API", "BPI", "ITO", "ALL"]
    else:
        # 預設至少有 ALL
        return ["ALL"]


def classify_pi_type(aoi: str, df: pd.DataFrame) -> pd.DataFrame:
    """
    依 AOI / recipe_id 建立 pi_type 欄位，並移除不在範圍內的資料。
    """
    df = df.copy()
    rec = df["recipe_id"].astype(str)
    print(aoi, len(df))
    if aoi in ("aoi100"):
        df["pi_type"] = 'API'
    elif aoi in ("aoi200"):
        # 取第一碼
        first = rec.str[0]
        charts = ["2", "3", "4", "5"]
        df = df[first.isin(charts)].copy()
        df["pi_type"] = first.map({
            "2": "API",
            "4": "BPI",
            "3": "API",
            "5": "BPI",
        }).fillna("")

    elif aoi == "aoi300":
        charts = ["CELL-ITO", "API", "BPI", "ITO"]
        mask = rec.apply(lambda x: (x == charts[0]) or any(c in x for c in charts[1:]))
        df = df[mask].copy()

        conditions = [
            rec.str.contains("API", na=False),
            rec.str.contains("BPI", na=False),
            rec.str.contains("CELL-ITO", na=False),
            rec.str.contains("ITO", na=False),
        ]
        choices = ["API", "BPI", "ITO", "ITO"]
        df["pi_type"] = np.select(conditions, choices, default=None)

    else:
        # 若未定義，全部歸類成 ALL
        df["pi_type"] = "ALL"

    return df


def get_date_range(mode: str,
                   date_str: Optional[str],
                   start_str: Optional[str],
                   end_str: Optional[str]) -> Tuple[date, date]:
    """
    依 CLI 參數回傳要處理的日期區間 (start_date, end_date)
    """
    today = datetime.now().date()

    if mode == "today":
        return today, today

    if mode == "date":
        if not date_str:
            raise ValueError("--mode date 時必須指定 --date YYYY-MM-DD")
        d = parse_yyyymmdd(date_str)
        return d, d

    if mode == "range":
        if not start_str:
            raise ValueError("--mode range 時必須指定 --start YYYY-MM-DD")
        start = parse_yyyymmdd(start_str)
        end = parse_yyyymmdd(end_str) if end_str else today
        if end < start:
            start, end = end, start
        return start, end

    raise ValueError(f"未知 mode: {mode}")


def load_raw_for_aoi(
    db: MySQLConnetFunc,
    aoi: str,
    start_day: date,
    end_day: date,
) -> pd.DataFrame:

    # === 正確來源表邏輯 ===
    if aoi == "aoi300":
        table_name = "aoi_summary_aoi300_capa"   # aoi300 特例
    else:
        table_name = f"aoi_summary_{aoi}"         # aoi100/aoi200 共用

    logger.info(f"[{aoi}] 讀取原始表 {table_name}，日期區間 {start_day} ~ {end_day}")

    sql = text(f"""
        SELECT run_day, scantime, glass_id, recipe_id
        FROM `{table_name}`
        WHERE run_day BETWEEN :start_day AND :end_day
    """)

    params = {"start_day": start_day, "end_day": end_day}

    with db.engine.connect() as conn:
        df = pd.read_sql(sql, conn, params=params)

    logger.info(f"[{aoi}] 原始資料筆數：{len(df)}")
    if df.empty:
        return df

    # 時間欄位處理
    df["scantime"] = pd.to_datetime(df["scantime"], errors="coerce")
    df["run_day"] = pd.to_datetime(df["run_day"]).dt.date
    df = df.dropna(subset=["scantime"])

    # hour_int 0~23
    df["hour_int"] = df["scantime"].dt.hour

    # pi_type 分類
    df = classify_pi_type(aoi, df)
    logger.info(f"[{aoi}] pi_type 分布：{dict(df.groupby('pi_type')['glass_id'].size())}")
    return df


def load_existing_summary_cfg(
    db: MySQLConnetFunc,
    aoi: str,
    start_day: date,
    end_day: date,
) -> pd.DataFrame:

    # === 正確 summary 表名 ===
    table_name = f"{aoi}_capa_summary"

    prev_day = start_day - timedelta(days=1)

    sql = text(f"""
        SELECT aoi, run_day, pi_type,
               total_glass, target_count, spec,
               real_day_capa, comment, editor
        FROM `{table_name}`
        WHERE aoi = :aoi
          AND run_day BETWEEN :start_day AND :end_day
    """)

    params = {
        "aoi": aoi,
        "start_day": prev_day,
        "end_day": end_day
    }

    try:
        with db.engine.connect() as conn:
            df = pd.read_sql(sql, conn, params=params)
        df["run_day"] = pd.to_datetime(df["run_day"]).dt.date
        return df
    except Exception as e:
        logger.warning(f"[{aoi}] 讀取 summary 表 {table_name} 失敗：{e}")
        return pd.DataFrame(columns=[
            "aoi","run_day","pi_type",
            "total_glass","target_count","spec",
            "real_day_capa","comment","editor"
        ])


def decide_target_and_spec_for_day(
    aoi: str,
    day: date,
    existing_summary: pd.DataFrame,
    last_target: Optional[float],
    last_spec: Optional[float],
    now_str: str,
) -> Tuple[float, float, bool]:
    """
    決定當天的 target_count / spec。

    回傳:
        (target_count, spec, is_from_existing_today)

    is_from_existing_today = True 代表今天的設定來自 summary 表既有資料，
    後續會保留 comment / editor。
    """
    # 先找「當天」是否已有 summary（使用者可能修改過）
    today_rows = existing_summary[existing_summary["run_day"] == day]
    if not today_rows.empty:
        # 以第一列為準（通常全日 pi_type 相同 target/spec）
        row0 = today_rows.iloc[0]
        t = float(row0.get("target_count", np.nan))
        s = float(row0.get("spec", np.nan))
        logger.info(
            f"[{aoi}][{day}] 沿用 summary 表當天設定 target={t}, spec={s}"
        )
        return t, s, True

    # 若沒有當天資料，但 last_target/spec 已有 → 沿用前一日
    if last_target is not None and last_spec is not None:
        logger.info(
            f"[{aoi}][{day}] 沿用前一日設定 target={last_target}, spec={last_spec}"
        )
        return last_target, last_spec, False

    # 再嘗試從「更早之前的某天」在 existing_summary 中找（若有）
    older = existing_summary[existing_summary["run_day"] < day]
    if not older.empty:
        older = older.sort_values("run_day")
        row_last = older.iloc[-1]
        t = float(row_last.get("target_count", np.nan))
        s = float(row_last.get("spec", np.nan))
        logger.info(
            f"[{aoi}][{day}] 沿用 summary 表中最近一次設定 target={t}, spec={s}"
        )
        return t, s, False

    # 最後才用程式內建預設
    t = float(capa_glassnum_cfg.get(aoi, np.nan))
    s = float(capa_spec_cfg.get(aoi, np.nan))
    logger.info(
        f"[{aoi}][{day}] 使用預設設定 target={t}, spec={s}"
    )
    return t, s, False


def build_hourly_and_summary_for_day(
    aoi: str,
    day: date,
    raw_day: pd.DataFrame,
    target_count: float,
    spec: float,
    existing_summary: pd.DataFrame,
    now_str: str,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    給定單一 AOI + 單一天的資料，建立：
      - hourly_df : 每小時彙總（pi_type & ALL）
      - summary_df: 當天日彙總（各 pi_type + ALL）

    會處理：
      - 24 小時填滿 (0~23)
      - 沿用 / 預設 comment / editor
      - real_hour_capa / real_cumu_capa / real_day_capa
    """
    pi_types_for_summary = get_pi_types_for_aoi(aoi)
    hours = pd.DataFrame({"hour_int": range(24)})

    # =========================
    # 1) Hourly: 計算各 pi_type & ALL
    # =========================
    hourly_rows = []

    if raw_day.empty:
        # 完全沒資料：只建立 ALL = 0 的 24 筆
        logger.info(f"[{aoi}][{day}] 此日無原始資料，建立 24 小時 ALL=0。")
        df_all = hours.copy()
        df_all["hour"] = 0
        df_all["cumu"] = 0
        df_all["real_hour_capa"] = 0.0
        df_all["real_cumu_capa"] = 0.0
        df_all["aoi"] = aoi
        df_all["run_day"] = day
        df_all["pi_type"] = "ALL"
        hourly_rows.append(df_all)
    else:
        # 有資料：先各 pi_type，再 ALL
        # 先算原始 glass count (含重複 glass)
        cnt_all = (
            raw_day
            .groupby("hour_int")["glass_id"]
            .size()
            .rename("hour")
        )

        cnt_by_pi = (
            raw_day
            .groupby(["pi_type", "hour_int"])["glass_id"]
            .size()
            .rename("hour")
            .reset_index()
        )

        # ALL
        df_all = hours.merge(cnt_all, on="hour_int", how="left").fillna(0)
        df_all["hour"] = df_all["hour"].astype(int)
        df_all["cumu"] = df_all["hour"].cumsum()
        df_all["real_hour_capa"] = (df_all["hour"] / target_count)
        df_all["real_cumu_capa"] = (df_all["cumu"] / target_count)
        df_all["aoi"] = aoi
        df_all["run_day"] = day
        df_all["pi_type"] = "ALL"
        hourly_rows.append(df_all)

        # 各 pi_type
        for pi in sorted(raw_day["pi_type"].dropna().unique()):
            sub = cnt_by_pi[cnt_by_pi["pi_type"] == pi]
            sub_cnt = sub.set_index("hour_int")["hour"]
            df_pi = hours.merge(sub_cnt, how="left", left_on="hour_int", right_index=True).fillna(0)
            df_pi["hour"] = df_pi["hour"].astype(int)
            df_pi["cumu"] = df_pi["hour"].cumsum()
            df_pi["real_hour_capa"] = (df_pi["hour"] / target_count)
            df_pi["real_cumu_capa"] = (df_pi["cumu"] / target_count)
            df_pi["aoi"] = aoi
            df_pi["run_day"] = day
            df_pi["pi_type"] = pi
            hourly_rows.append(df_pi)

    hourly_df = pd.concat(hourly_rows, ignore_index=True)

    # =========================
    # 2) Summary: 各 pi_type & ALL 的 total_glass / real_day_capa
    # =========================
    summary_rows = []
    # 先把 hourly 中最後一筆 (hour_int=23) 當作 total_glass
    end_hour = 23
    hourly_end = hourly_df[hourly_df["hour_int"] == end_hour].copy()

    # 當天既有 summary（用來沿用 comment / editor 或當天設定）
    existing_today = existing_summary[
        (existing_summary["run_day"] == day) &
        (existing_summary["aoi"] == aoi)
    ]

    # 建 editor / comment 預設
    default_editor = f"default\n{now_str}"

    for pi in pi_types_for_summary:
        # 該 pi_type 在 hourly 是否有資料
        row_he = hourly_end[hourly_end["pi_type"] == pi]
        total_glass = int(row_he["cumu"].iloc[0]) if not row_he.empty else 0
        real_day_capa = total_glass / target_count if target_count else 0.0

        # 先嘗試取「當天既有 summary 的該 pi_type 列」以沿用 comment / editor
        exist_pi = existing_today[existing_today["pi_type"] == pi]

        if not exist_pi.empty:
            # 沿用 comment / editor / target_count / spec
            r0 = exist_pi.iloc[0]
            t = float(r0.get("target_count", target_count))
            s = float(r0.get("spec", spec))
            comment = r0.get("comment", "")
            editor = r0.get("editor", default_editor)
        else:
            # 此 pi_type 是程式新建的列：使用目前 target/spec、comment 空白、editor default
            t = target_count
            s = spec
            comment = ""
            editor = default_editor

        summary_rows.append({
            "aoi": aoi,
            "run_day": day,
            "pi_type": pi,
            "total_glass": total_glass,
            "target_count": t,
            "spec": s,
            "real_day_capa": real_day_capa,
            "comment": comment,
            "editor": editor,
        })

    summary_df = pd.DataFrame(summary_rows)
    return hourly_df, summary_df


def write_to_db(
    db: MySQLConnetFunc,
    aoi: str,
    start_day: date,
    end_day: date,
    hourly_df: pd.DataFrame,
    summary_df: pd.DataFrame,
):
    """
    將某 AOI 在指定日期區間的 hourly / summary 結果寫回 DB：
      - 若目標表存在：先 DELETE 當區間 (aoi, run_day) 的資料
      - 若目標表不存在：略過 DELETE，直接用 to_sql 建表 + 寫入
    """
    hourly_table = f"{aoi}_capa_hourly_rawdata"
    summary_table = f"{aoi}_capa_summary"

    logger.info(
        f"[{aoi}] 寫回 DB：run_day {start_day} ~ {end_day}，"
        f"summary {len(summary_df)} rows, hourly {len(hourly_df)} rows"
    )

    # 檢查資料表是否存在（第一次執行時會是 False）
    insp = inspect(db.engine)
    has_summary = insp.has_table(summary_table)
    has_hourly = insp.has_table(hourly_table)

    with db.engine.begin() as conn:
        del_params = {
            "aoi": aoi,
            "start_day": start_day,
            "end_day": end_day,
        }

        # 只有「表已存在」才執行 DELETE，避免 1146 錯誤
        if has_summary:
            logger.info(f"[{aoi}] 刪除舊 summary 資料：{summary_table}")
            conn.execute(
                text(
                    f"""
                    DELETE FROM `{summary_table}`
                    WHERE aoi = :aoi
                      AND run_day BETWEEN :start_day AND :end_day
                    """
                ),
                del_params,
            )
        else:
            logger.info(f"[{aoi}] summary 表 {summary_table} 尚未建立，略過 DELETE。")

        if has_hourly:
            logger.info(f"[{aoi}] 刪除舊 hourly 資料：{hourly_table}")
            conn.execute(
                text(
                    f"""
                    DELETE FROM `{hourly_table}`
                    WHERE aoi = :aoi
                      AND run_day BETWEEN :start_day AND :end_day
                    """
                ),
                del_params,
            )
        else:
            logger.info(f"[{aoi}] hourly 表 {hourly_table} 尚未建立，略過 DELETE。")

        # 寫入新的 summary / hourly
        if not summary_df.empty:
            logger.info(f"[{aoi}] 寫入 summary：{len(summary_df)} rows → {summary_table}")
            summary_df.to_sql(
                summary_table,
                conn,
                if_exists="append",   # 若表不存在會自動建立
                index=False,
                method="multi",
            )
        else:
            logger.info(f"[{aoi}] 本次 summary 無資料可寫入。")

        if not hourly_df.empty:
            logger.info(f"[{aoi}] 寫入 hourly：{len(hourly_df)} rows → {hourly_table}")
            hourly_df.to_sql(
                hourly_table,
                conn,
                if_exists="append",   # 若表不存在會自動建立
                index=False,
                method="multi",
            )
        else:
            logger.info(f"[{aoi}] 本次 hourly 無資料可寫入。")



# =========================
# 主流程
# =========================

def run_job(mode: str, date_str: Optional[str], start_str: Optional[str], end_str: Optional[str]):
    start_day, end_day = get_date_range(mode, date_str, start_str, end_str)
    logger.info(f"=== AOI CAPA Job 啟動：mode={mode}, start={start_day}, end={end_day} ===")

    db = MySQLConnetFunc("l6a01_project")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for aoi in AOI_NAMES:
        logger.info(f"----- 處理 AOI = {aoi} -----")

        # 1) 讀原始資料
        raw_df = load_raw_for_aoi(db, aoi, start_day, end_day)

        # 2) 讀 summary 既有設定（含前一日）
        existing_summary = load_existing_summary_cfg(db, aoi, start_day, end_day)

        # 3) 依日期逐日處理
        all_hourly = []
        all_summary = []

        # 以日期遞增順序處理
        day_list = [start_day + timedelta(days=i)
                    for i in range((end_day - start_day).days + 1)]

        last_target = None
        last_spec = None

        for d in day_list:
            raw_day = raw_df[raw_df["run_day"] == d].copy()

            # 決定今日的 target / spec
            target_count, spec, is_from_existing_today = decide_target_and_spec_for_day(
                aoi, d, existing_summary, last_target, last_spec, now_str
            )

            # 更新記憶：讓後面日期可以延用
            last_target = target_count
            last_spec = spec

            # 建立 hourly & summary
            hourly_d, summary_d = build_hourly_and_summary_for_day(
                aoi, d, raw_day, target_count, spec, existing_summary, now_str
            )

            all_hourly.append(hourly_d)
            all_summary.append(summary_d)

        if not all_hourly:
            logger.info(f"[{aoi}] 此區間完全沒有需要寫入的資料，略過 DB 寫入。")
            continue

        hourly_df = pd.concat(all_hourly, ignore_index=True)
        summary_df = pd.concat(all_summary, ignore_index=True)

        # 統一欄位順序
        summary_cols = [
            "aoi", "run_day", "pi_type",
            "total_glass", "target_count", "spec",
            "real_day_capa", "comment", "editor",
        ]
        summary_df = summary_df[summary_cols]

        hourly_cols = [
            "aoi", "run_day", "hour_int", "pi_type",
            "hour", "cumu", "real_hour_capa", "real_cumu_capa",
        ]
        hourly_df = hourly_df[hourly_cols]

        # 4) 寫回 DB
        write_to_db(db, aoi, start_day, end_day, hourly_df, summary_df)

    logger.info("=== AOI CAPA Job 完成 ===")


def main():
    parser = argparse.ArgumentParser(description="AOI CAPA Daily/Hourly Summary Job")
    parser.add_argument(
        "--mode",
        choices=["today", "date", "range"],
        default="today",
        help="today: 今天；date: 指定一天；range: 指定起迄區間",
    )
    parser.add_argument("--date", help="--mode date 時的日期 YYYY-MM-DD")
    parser.add_argument("--start", help="--mode range 的起始日期 YYYY-MM-DD")
    parser.add_argument("--end", help="--mode range 的結束日期 YYYY-MM-DD（可省略，預設今天）")

    args = parser.parse_args()

    try:
        run_job(args.mode, args.date, args.start, args.end)
    except Exception as e:
        logger.exception(f"AOI CAPA Job 執行失敗：{e}")
        raise


if __name__ == "__main__":
    main()
