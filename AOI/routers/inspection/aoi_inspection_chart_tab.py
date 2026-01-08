
# routers/inspection_trend.py
from fastapi import APIRouter, Body
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy import text
from models.sql_db_connect import MySQLConnet

router = APIRouter()

# ============================================================
# 小工具：時間解析 / default 範圍 / 月份列表
# ============================================================

def _parse_ymd(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")

def _week_str_to_range(this_year: int, w_start: str, w_end: str) -> Tuple[datetime, datetime]:
    """
    w_start, w_end 格式：'W40', 'W49'
    這裡假設週別是「當年」的 ISO week
    回傳: (start_datetime, end_datetime_exclusive)
    """
    def _week_to_mon(y: int, w: int) -> datetime:
        # ISO: 第 w 週的週一
        return datetime.fromisocalendar(y, w, 1)

    ws = int(str(w_start).replace("W", ""))
    we = int(str(w_end).replace("W", ""))

    if we < ws:
        we = ws  # 防呆

    d_start = _week_to_mon(this_year, ws)
    # end 用「下一週的週一」當作 exclusive 上限
    d_end = _week_to_mon(this_year, we) + timedelta(weeks=1)
    return d_start, d_end

def _ym_str_to_range(ym_start: str, ym_end: str) -> Tuple[datetime, datetime]:
    """
    ym_start, ym_end: '202503' 這種字串
    回傳: (start_datetime, end_datetime_exclusive)
    """
    ys = int(str(ym_start)[:4]); ms = int(str(ym_start)[4:6])
    ye = int(str(ym_end)[:4]);   me = int(str(ym_end)[4:6])

    d_start = datetime(ys, ms, 1)

    # 找 end month 的下一個月 1 號
    if me == 12:
        d_end = datetime(ye + 1, 1, 1)
    else:
        d_end = datetime(ye, me + 1, 1)

    return d_start, d_end

def _default_ranges_now() -> Dict[str, Tuple[datetime, datetime]]:
    """
    day/week/month 都沒給 date 時的預設範圍：
      - day: 最近 7 天
      - week: 最近 7 週
      - month: 最近 7 個月
    全部用 datetime 範圍（右側為 exclusive）
    """
    now = datetime.now()
    today = now.date()

    # day: 最近 7 天（含今天）
    d_end = datetime.combine(today + timedelta(days=1), datetime.min.time())
    d_start = d_end - timedelta(days=7)

    # week: 最近 7 週
    w_end = d_end
    w_start = w_end - timedelta(weeks=7)

    # month: 最近 7 個月
    cur_ts = pd.Timestamp(today)
    cur_period = cur_ts.to_period("M")
    start_period = cur_period - 6  # 包含當月在內共 7 個
    m_start = start_period.to_timestamp()  # 該月 1 號 00:00
    m_end = (cur_period + 1).to_timestamp()  # 下個月 1 號 00:00（exclusive）

    return {
        "day": (d_start, d_end),
        "week": (w_start, w_end),
        "month": (m_start, m_end),
    }

def _month_range_between(d_min: datetime, d_max: datetime) -> List[str]:
    """
    依 d_min ~ d_max 範圍產生 YYYYMM 清單
    """
    if d_min > d_max:
        d_min, d_max = d_max, d_min

    start = pd.Timestamp(d_min).to_period("M")
    end = pd.Timestamp(d_max).to_period("M")
    periods = pd.period_range(start, end, freq="M")
    return [p.strftime("%Y%m") for p in periods]

# ============================================================
# 將前端 day/week/month raw config 轉成 datetime 範圍
# ============================================================

def _raw_to_date_range(kind: str, raw_val: Any) -> Optional[Tuple[datetime, datetime]]:
    """
    支援兩種格式：
      - list/tuple: ["start","end"]
      - dict: { "date": ["start","end"] }

    若無法解析或沒給 → 回傳 None，交給預設處理。
    """
    if raw_val is None:
        return None

    # 若是 dict，可能是 { "date": [...] }
    if isinstance(raw_val, dict):
        date_arr = raw_val.get("date")
    else:
        date_arr = raw_val

    if not isinstance(date_arr, (list, tuple)) or len(date_arr) != 2:
        return None

    if kind == "day":
        d_start = _parse_ymd(str(date_arr[0]))
        d_end = _parse_ymd(str(date_arr[1])) + timedelta(days=1)  # inclusive → exclusive
        return d_start, d_end

    elif kind == "week":
        # 假設同一年，使用現在年份
        this_year = datetime.now().year
        return _week_str_to_range(this_year, str(date_arr[0]), str(date_arr[1]))

    elif kind == "month":
        return _ym_str_to_range(str(date_arr[0]), str(date_arr[1]))

    return None

# ============================================================
# DB 撈 inspection_api_summary_YYYYMM（只卡時間）
# ============================================================

def _fetch_inspection_summary(dbhandler, d_min: datetime, d_max: datetime) -> pd.DataFrame:
    """
    根據 d_min ~ d_max（exclusive）決定要撈哪些 inspection_api_summary_YYYYMM，
    合併成一個 df 後再用 pi_hour 做時間篩選。
    """
    ym_list = _month_range_between(d_min, d_max)

    dfs = []
    for ym in ym_list:
        tbn = f"inspection_api_summary_{ym}"

        sql = text(f"""
            SELECT
              pi_hour,
              line_id,
              model,
              glass_type,
              maingroup_glass_count,
              maingroup_defect_count,
              defect_code_glass_count,
              small_defect_count,
              middle_defect_count,
              large_defect_count,
              over_defect_count
            FROM {tbn}
            WHERE pi_hour >= :d_min AND pi_hour < :d_max
        """)

        try:
            with dbhandler.engine.begin() as conn:
                df_part = pd.read_sql(sql, conn, params={"d_min": d_min, "d_max": d_max})
        except Exception as e:
            print(f"[inspection_trend] 讀取 {tbn} 失敗: {e}")
            df_part = pd.DataFrame()

        if not df_part.empty:
            dfs.append(df_part)

    if dfs:
        df = pd.concat(dfs, ignore_index=True)
    else:
        df = pd.DataFrame(columns=[
            "pi_hour", "line_id", "model", "glass_type",
            "maingroup_glass_count", "maingroup_defect_count",
            "defect_code_glass_count",
            "small_defect_count", "middle_defect_count",
            "large_defect_count", "over_defect_count",
        ])

    # 確保 pi_hour 轉 datetime
    if not df.empty and not pd.api.types.is_datetime64_any_dtype(df["pi_hour"]):
        df["pi_hour"] = pd.to_datetime(df["pi_hour"])

    return df

def _derive_defect_size(s: int, m: int, l: int, o: int) -> str:
    out = []
    if s > 0:
        out.append("S")
    if m > 0:
        out.append("M")
    if l > 0:
        out.append("L")
    if o > 0:
        out.append("O")
    return "".join(out)

# ============================================================
# 依粒度 group & 統計（不再接受其他 filter，只看時間）
# ============================================================

def _filter_by_date(df: pd.DataFrame, date_range: Tuple[datetime, datetime]) -> pd.DataFrame:
    if df.empty:
        return df
    d_start, d_end = date_range
    df2 = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df2["pi_hour"]):
        df2["pi_hour"] = pd.to_datetime(df2["pi_hour"])
    return df2[(df2["pi_hour"] >= d_start) & (df2["pi_hour"] < d_end)]

def _build_trend_kind(df: pd.DataFrame, kind: str) -> Dict[str, Any]:
    """
    依粒度（day/week/month）計算 trend_points
    只卡時間，其他欄位 line_id/model/glass_type 保留給前端自行 filter。
    """
    if df.empty:
        return {"points": []}

    df2 = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df2["pi_hour"]):
        df2["pi_hour"] = pd.to_datetime(df2["pi_hour"])

    # 時間 key & group keys
    if kind == "day":
        df2["pi_date"] = df2["pi_hour"].dt.date
        time_key = "pi_date"
        group_keys = [time_key, "line_id", "model", "glass_type"]

    elif kind == "week":
        iso = df2["pi_hour"].dt.isocalendar()
        df2["week_year"] = iso["year"]
        df2["week_num"]  = iso["week"]
        df2["week_start"] = df2["pi_hour"] - pd.to_timedelta(df2["pi_hour"].dt.weekday, unit="D")
        df2["week_start"] = df2["week_start"].dt.normalize()
        df2["week_label"] = (
            df2["week_year"].astype(str)
            + "-W"
            + df2["week_num"].astype(str).str.zfill(2)
        )
        time_key = "week_start"
        group_keys = [time_key, "week_label", "line_id", "model", "glass_type"]

    elif kind == "month":
        df2["month"] = df2["pi_hour"].dt.to_period("M").dt.to_timestamp()
        time_key = "month"
        group_keys = [time_key, "line_id", "model", "glass_type"]

    else:
        raise ValueError(f"Unknown kind={kind}")

    agg_cols = [
        "maingroup_glass_count",
        "maingroup_defect_count",
        "defect_code_glass_count",
        "small_defect_count",
        "middle_defect_count",
        "large_defect_count",
        "over_defect_count",
    ]
    agg_dict = {c: "sum" for c in agg_cols}

    g = df2.groupby(group_keys, as_index=False).agg(agg_dict)

    # === 原本就有的 selected_defect_count / density_selected（不動） ===
    g["selected_defect_count"] = (
        g["small_defect_count"]
        + g["middle_defect_count"]
        + g["large_defect_count"]
        + g["over_defect_count"]
    )

    g["density_selected"] = (
        g["selected_defect_count"] /
        g["maingroup_glass_count"].replace(0, pd.NA)
    )

    # === 🔹 新增 defect_size（只新增） ===
    g["defect_size"] = g.apply(
        lambda r: _derive_defect_size(
            int(r["small_defect_count"]),
            int(r["middle_defect_count"]),
            int(r["large_defect_count"]),
            int(r["over_defect_count"]),
        ),
        axis=1
    )

    points: List[Dict[str, Any]] = []
    for _, row in g.iterrows():
        item: Dict[str, Any] = {
            "x": row[time_key],
            "line_id": row["line_id"],
            "model": row["model"],
            "glass_type": row["glass_type"],

            # === 新增欄位 ===
            "defect_size": row["defect_size"],

            # === 原有欄位（完全不動） ===
            "maingroup_glass_count": int(row["maingroup_glass_count"]),
            "maingroup_defect_count": int(row["maingroup_defect_count"]),
            "defect_code_glass_count": int(row["defect_code_glass_count"]),
            "small_defect_count": int(row["small_defect_count"]),
            "middle_defect_count": int(row["middle_defect_count"]),
            "large_defect_count": int(row["large_defect_count"]),
            "over_defect_count": int(row["over_defect_count"]),
            "selected_defect_count": int(row["selected_defect_count"]),
            "density_selected": float(row["density_selected"])
                if pd.notna(row["density_selected"]) else None,
        }

        if kind == "week":
            item["week_label"] = row["week_label"]

        points.append(item)

    return {"points": points}
# ============================================================
# 路由本體
# ============================================================

@router.post("/api/trend")
async def get_inspection_trend(payload: Dict[str, Any] = Body(...)):
    """
    接收：
    {
      "day":   ["YYYY-MM-DD","YYYY-MM-DD"] 或 {} 或省略
      "week":  ["W40","W49"]              或 {} 或省略
      "month": ["YYYYMM","YYYYMM"]        或 {} 或省略
    }

    - 若某個 key 缺席（例如沒有 "week"），則不回傳對應粒度。
    - 若存在但為 {} 或無法解析，則取預設 7 天 / 7 週 / 7 月。
    """
    dbhandler = MySQLConnet("l6a01_project")

    raw_day   = payload.get("day")
    raw_week  = payload.get("week")
    raw_month = payload.get("month")

    default_ranges = _default_ranges_now()

    real_ranges: Dict[str, Tuple[datetime, datetime]] = {}

    # day
    if raw_day is not None:
        r = _raw_to_date_range("day", raw_day)
        real_ranges["day"] = r if r is not None else default_ranges["day"]

    # week
    if raw_week is not None:
        r = _raw_to_date_range("week", raw_week)
        real_ranges["week"] = r if r is not None else default_ranges["week"]

    # month
    if raw_month is not None:
        r = _raw_to_date_range("month", raw_month)
        real_ranges["month"] = r if r is not None else default_ranges["month"]

    if not real_ranges:
        # 三個都沒要算，就回傳空
        return {}

    # 決定全體 d_min / d_max（用來撈 DB）
    d_min = min(r[0] for r in real_ranges.values())
    d_max = max(r[1] for r in real_ranges.values())

    # 撈整體 base df（只卡時間）
    df_base = _fetch_inspection_summary(dbhandler, d_min, d_max)

    result: Dict[str, Any] = {}

    # day trend
    if "day" in real_ranges:
        df_day = _filter_by_date(df_base, real_ranges["day"])
        print('day', len(df_day))
        result["day"] = _build_trend_kind(df_day, "day")

    # week trend
    if "week" in real_ranges:
        df_week = _filter_by_date(df_base, real_ranges["week"])
        print('week', len(df_week))
        result["week"] = _build_trend_kind(df_week, "week")

    # month trend
    if "month" in real_ranges:
        df_month = _filter_by_date(df_base, real_ranges["month"])
        print('month', len(df_month))
        result["month"] = _build_trend_kind(df_month, "month")

    return result


    
