#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每次執行：
1. 登入 KLA YMS 取得 token
2. 抓取 CAAOI300 在「最近 WINDOW_MINUTES 分鐘」內的 glass 資料
3. 轉成台灣時間欄位 run_day / scantime
4. 存進 MySQL: aoi_summary_aoi300_capa
   - 若表不存在則新建
   - 若已存在則 append，並用 key_cols 去除重複列
建議交由 Windows Task Scheduler / crontab 每 10 分鐘呼叫一次本檔。
"""

import requests
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
import logging
from sqlalchemy.exc import SQLAlchemyError

from sql_db_func import MySQLConnetFunc

# =========================
# 基本設定
# =========================

# 抓取時間窗（分鐘）→ 跑排程就設 10；若要 backfill 可暫時改大
WINDOW_MINUTES = 15

# 代理
PROXY_DICT = {
    "http": "http://10.97.4.1:8080",
    "https": "http://10.97.4.1:8080",
}

# API 設定
LOGIN_URL = "http://10.97.140.46/api/authority/login"
BASE_URL = "http://10.97.140.46/api/search/glasses"

LOGIN_PAYLOAD = {
    "_id": "",
    "name": "fpd",
    "password": "fpd",
    "resources": [],
    "isORM": False,
}

MACHINE_ID = "CAAOI300"

# DB 設定
DB_NAME = "l6a01_project"
TARGET_TABLE = "aoi_summary_aoi300_capa"
# 用這幾個欄位當作唯一鍵避免重複寫入
KEY_COLS = ["run_day", "scantime", "glass_id", "recipe_id"]

# Logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("yms_aoi300_capa_job.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)


# =========================
# 工具函式
# =========================

def taiwan_to_utc_iso(dt_tw: datetime) -> str:
    """
    將「台灣時間的 datetime」轉成 UTC ISO8601 (尾巴 Z)
    """
    tz_tw = pytz.timezone("Asia/Taipei")
    if dt_tw.tzinfo is None:
        dt_tw = tz_tw.localize(dt_tw)
    else:
        dt_tw = dt_tw.astimezone(tz_tw)
    dt_utc = dt_tw.astimezone(pytz.utc)
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def login_get_token() -> str:
    """
    登入 YMS 取得 access token
    """
    headers = {"Content-Type": "application/json"}
    try:
        res = requests.put(
            LOGIN_URL,
            json=LOGIN_PAYLOAD,
            proxies=PROXY_DICT,
            headers=headers,
            timeout=30,
        )
        if res.status_code == 200:
            data = res.json()
            token = data["token_set"]["access_token"]
            logger.info("成功登入 YMS，取得 token")
            return token
        else:
            logger.error(f"登入失敗，狀態碼: {res.status_code}, 內容: {res.text}")
            return ""
    except Exception as e:
        logger.exception(f"登入 YMS 發生例外: {e}")
        return ""


def fetch_glasses(token: str, start_utc: str, end_utc: str) -> pd.DataFrame:
    """
    依指定 UTC 時間區間抓取 CAAOI300 glasses 資料，回傳 DataFrame。
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "user-agent": "Mozilla/5.0",
    }

    page_items = 100
    params_common = [
        ("pastDays", 0),
        ("pastfromto", 1),
        ("machineId", MACHINE_ID),
        ("startTime", start_utc),
        ("endTime", end_utc),
        ("dataType", 1),
        ("pageItems", page_items),
        ("authority", MACHINE_ID),
        ("isInit", "false"),
    ]

    all_data = []
    page = 1

    while True:
        logger.info(f"抓取資料：第 {page} 頁...")
        params_page = params_common + [("currentPage", page)]
        try:
            res = requests.get(
                BASE_URL,
                headers=headers,
                proxies=PROXY_DICT,
                params=params_page,
                timeout=60,
            )
            if res.status_code != 200:
                logger.error(f"抓取失敗，第 {page} 頁，狀態碼: {res.status_code}, 內容: {res.text}")
                break

            json_data = res.json()
            data_list = json_data.get("data", [])
        except Exception as e:
            logger.exception(f"抓取第 {page} 頁發生例外: {e}")
            break

        if not data_list:
            logger.info("本頁無資料，判定抓取完畢。")
            break

        all_data.extend(data_list)

        if len(data_list) < page_items:
            logger.info("最後一頁抓完。")
            break

        page += 1
        # 避免太快打爆對方 API
        time.sleep(0.2)

    logger.info(f"全部抓取完成，總筆數: {len(all_data)}")

    if not all_data:
        return pd.DataFrame()

    return pd.DataFrame(all_data)


def transform_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    將原始 API DataFrame 轉成需要的欄位：
    - 轉換 startTime / endTime 為台灣時間
    - 新增 run_day / scantime / endTime_tw
    - rename 欄位
    - 只保留 [run_day, scantime, glass_id, recipe_id]
    """
    if df.empty:
        return df

    # 轉時區
    start_ts = pd.to_datetime(df["startTime"], utc=True)
    end_ts = pd.to_datetime(df["endTime"], utc=True)

    tw_start = start_ts.dt.tz_convert("Asia/Taipei")
    tw_end = end_ts.dt.tz_convert("Asia/Taipei")

    df["scantime"] = tw_start.dt.strftime("%Y-%m-%d %H:%M:%S")
    df["run_day"] = tw_start.dt.strftime("%Y-%m-%d")
    df["endTime_tw"] = tw_end.dt.strftime("%Y-%m-%d %H:%M:%S")

    # 欄位改名
    df_renamed = df.rename(
        columns={
            "glassId": "glass_id",
            "layer": "model_id",
            "device": "recipe_id",
            "lotId": "lot_id",
            "machineId": "aoi_id",
        }
    )

    columns = ["run_day", "scantime", "glass_id", "recipe_id"]
    missing = [c for c in columns if c not in df_renamed.columns]
    if missing:
        logger.error(f"缺少必要欄位: {missing}，原始欄位: {list(df_renamed.columns)}")
        return pd.DataFrame()

    df_out = df_renamed[columns].copy()

    # 去除欄位內全空或 NaN 的 row（依實際需求調整）
    df_out.dropna(subset=["glass_id", "recipe_id"], how="any", inplace=True)

    # 以 KEY_COLS 在單次抓取內先做一次 drop_duplicates，減少 DB 比對量
    df_out = df_out.drop_duplicates(subset=KEY_COLS)

    logger.info(f"轉換後資料筆數: {len(df_out)}")
    return df_out


def save_to_db(df: pd.DataFrame):
    """
    將 df append 到 MySQL 的 aoi_summary_aoi300_capa，
    若表不存在則新建；已存在則 append_new_rows 並去除重複。
    """
    if df.empty:
        logger.info("本次沒有新資料，略過寫入 DB。")
        return

    dbhandler = MySQLConnetFunc(DB_NAME)

    try:
        dbhandler.append_new_rows(df, TARGET_TABLE, KEY_COLS)
    except SQLAlchemyError as e:
        logger.error(f"寫入 DB 發生 SQLAlchemyError: {e}")
    except Exception as e:
        logger.exception(f"寫入 DB 發生未知錯誤: {e}")


def main():
    logger.info("=== YMS CAAOI300 CAPA 抓取 job 開始 ===")

    # 1) 計算台灣時間的查詢區間（最近 WINDOW_MINUTES 分鐘）
    tz_tw = pytz.timezone("Asia/Taipei")
    now_tw = datetime.now(tz_tw)
    start_tw = now_tw - timedelta(minutes=WINDOW_MINUTES)

    start_utc = taiwan_to_utc_iso(start_tw)
    end_utc = taiwan_to_utc_iso(now_tw)

    logger.info(
        f"查詢時間窗 (TW): {start_tw.strftime('%Y-%m-%d %H:%M:%S')} ~ {now_tw.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    logger.info(f"查詢時間窗 (UTC ISO): {start_utc} ~ {end_utc}")

    # 2) 登入取得 token
    token = login_get_token()
    if not token:
        logger.error("無法取得 token，中止本次 job。")
        return

    # 3) 抓取資料
    raw_df = fetch_glasses(token, start_utc, end_utc)
    if raw_df.empty:
        logger.info("本次時間窗內無 API 資料。")
        return

    # 4) 轉換欄位
    clean_df = transform_df(raw_df)
    
    if clean_df.empty:
        logger.info("轉換後無有效資料，略過寫入 DB。")
        return

    # 5) 寫入 DB
    save_to_db(clean_df)

    logger.info("=== 本次 job 結束 ===")


if __name__ == "__main__":
    main()
