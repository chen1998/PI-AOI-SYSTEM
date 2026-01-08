
# routers/aoi_density_defect_map.py
from __future__ import annotations

import re
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text, bindparam
from sqlalchemy.exc import SQLAlchemyError

from models.sql_db_connect import MySQLConnet

router = APIRouter()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(funcName)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ========= 工具 =========
def normalize_pi_hour_to_hour_str(pi_hour: str) -> Optional[str]:
    """
    標準化為 'YYYY-MM-DD HH'（只保留到小時）
    - 'YY-MM-DD HH'  → '20YY-MM-DD HH'
    - 'YYYY-MM-DD HH' → 原樣
    其他格式回 None
    """
    if not pi_hour:
        return None
    s = str(pi_hour).strip()
    if re.fullmatch(r"\d{2}-\d{2}-\d{2}\s+\d{2}", s):
        return "20" + s
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}\s+\d{2}", s):
        return s
    return None

def hour_str_to_range(hour_str: str) -> Optional[tuple[datetime, datetime]]:
    """
    'YYYY-MM-DD HH' → (start_dt, end_dt)
    半開區間：[HH:00:00, HH+1:00:00)
    """
    if not hour_str:
        return None
    try:
        start = datetime.strptime(hour_str, "%Y-%m-%d %H")
    except ValueError:
        return None
    end = start + timedelta(hours=1)
    return start, end

def ym_from_pi_hour_hourstr(pi_hour_hour: str) -> str:
    """從 'YYYY-MM-DD HH' 取出 yymm（例：'2025-11-07 08' → '2511'）"""
    yy = int(pi_hour_hour[2:4])
    mm = pi_hour_hour[5:7]
    return f"{yy:02d}{mm}"

def extract_pi_suffix(line_id: str, default: str = "100") -> str:
    """line_id 末尾 2-3 位數字（CAPIC500 → '500'）"""
    if not line_id:
        return default
    m = re.search(r"(\d{2,3})$", str(line_id))
    return m.group(1) if m else default

def to_bucket(size_val) -> Optional[str]:
    """數值轉 S/M/L/O"""
    if size_val is None:
        return None
    if isinstance(size_val, str):
        up = size_val.strip().upper()
        if up in ("S", "M", "L", "O"):
            return up
        try:
            num = int(float(up))
        except Exception:
            return None
    else:
        try:
            num = int(float(size_val))
        except Exception:
            return None
    if num <= 20: return "S"
    if num <= 100: return "M"
    if num <= 400: return "L"
    return "O"

def group_defects_by_glass(rows: List[Dict]) -> Dict[str, Dict]:
    out: Dict[str, Dict] = {}
    img_flds = []
    for r in rows or []:
        gid = str(r.get("glass_id", "") or "")
        g = out.setdefault(gid, {"defect_map": [], "S": 0, "M": 0, "L": 0, "O": 0, "total": 0})
        img_flds.append(r.get("pic_path"))
        item = {
            "x": r.get("x"),
            "y": r.get("y"),
            "size": r.get("defect_size") if r.get("defect_size") is not None else r.get("size"),
            "img": (
                (r.get("pic_path") or "") + f'{r.get("pic_name")}.jpg'
                if (r.get("pic_name") is not None and r.get("pic_path") is not None) else ""
            ),
            "chip": r.get("chip_name") or r.get("chip"),
            "recipe_id": r.get("recipe_id"),
            "ai_code_1": r.get("ai_code_1"),
        }
        g["defect_map"].append(item)
        b = to_bucket(item.get("size"))
        if b in ("S", "M", "L", "O"):
            g[b] += 1
            g["total"] += 1
    print("影像資料夾:", set(img_flds))
    return out

# ========= DB 偵錯小工具 =========
def _run_scalar(conn, sql: str, params: Dict) -> int:
    return (conn.execute(text(sql), params).scalar() or 0)

def _distinct_preview(conn, table: str, col: str, limit: int = 10):
    sql = f"""
        SELECT TRIM(`{col}`) AS v, COUNT(*) c
        FROM `{table}`
        GROUP BY TRIM(`{col}`)
        ORDER BY c DESC
        LIMIT {limit}
    """
    return [dict(r) for r in conn.execute(text(sql)).mappings().all()]

# ========= 主查詢：pi_hour→pi_time 範圍 + 其它鍵 =========
def get_defects_by_key(self: MySQLConnet, table: str, key_dict: Dict) -> List[Dict]:
    """
    查詢規則：
      - 若 key_dict 含 'pi_hour'（hour 字串），改成對該表 `pi_time` 做半開區間
        [HH:00:00, HH+1:00:00) 過濾。
        * 若 `pi_time` 不是日期型別，使用 STR_TO_DATE(TRIM(`pi_time`), '%Y-%m-%d %H:%i:%s') 明確轉型。
        * 若表內沒有 `pi_time`，而有 `pi_hour`，則退回用 `pi_hour` 等值（字串欄位則 TRIM 比對）。
      - 其它鍵：
        * 單值：字串用 TRIM 等值；數值直接等值
        * list/tuple/set：IN (:k_list) with expanding
        * None：IS NULL
    並提供偵錯資訊：每鍵單獨匹配數、AND 疊加的 count/SQL/params（寫入 log）。
    """
    if not key_dict:
        return []

    if not re.fullmatch(r"[A-Za-z0-9_]+", table or ""):
        logging.error(f"[get_defects_by_key] illegal table name: {table!r}")
        return []

    # 取得欄位與型別
    try:
        with self.engine.begin() as conn:
            rows = conn.execute(
                text("""
                    SELECT COLUMN_NAME, DATA_TYPE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA=:db AND TABLE_NAME=:tbl
                """),
                {"db": getattr(self, "db", None), "tbl": table},
            ).mappings().all()
        col_types = {r["COLUMN_NAME"]: (r["DATA_TYPE"] or "").lower() for r in rows}
        cols = list(col_types.keys())
    except Exception:
        try:
            with self.engine.begin() as conn:
                rows = conn.execute(text(f"SHOW COLUMNS FROM `{table}`")).all()
            cols = [r[0] for r in rows]
            col_types = {c: "" for c in cols}
        except Exception as e:
            logging.error(f"[get_defects_by_key] fetch columns failed: {e}")
            return []

    colset = set(cols)
    if not colset:
        logging.warning(f"[get_defects_by_key] no columns in table {table}")
        return []

    # --- 組 WHERE ---
    where, params, expanding = [], {}, []
    debug_info = {"table": table, "by_single": {}, "cumulative": []}

    # 先處理 pi_hour（轉成 pi_time 區間或 pi_hour 等值）
    extra_hour_guard = True  # 額外保險：同時要求表內 pi_hour 與目標 hour_str 一致
    if "pi_hour" in key_dict:
        hour_str = normalize_pi_hour_to_hour_str(key_dict.get("pi_hour"))
        if hour_str:
            rng = hour_str_to_range(hour_str)  # (start_dt, end_dt)
            if rng:
                start_dt, end_dt = rng
                if "pi_time" in colset:
                    pi_time_type = col_types.get("pi_time", "")
                    if pi_time_type in ("datetime", "timestamp", "date"):
                        where.append("`pi_time` >= :pi_s AND `pi_time` < :pi_e")
                    else:
                        # VARCHAR/TEXT → 明確轉型
                        where.append(
                            "STR_TO_DATE(TRIM(`pi_time`), '%Y-%m-%d %H:%i:%s') >= :pi_s "
                            "AND STR_TO_DATE(TRIM(`pi_time`), '%Y-%m-%d %H:%i:%s') < :pi_e"
                        )
                    params["pi_s"] = start_dt
                    params["pi_e"] = end_dt
                elif "pi_hour" in colset:
                    pi_hour_type = col_types.get("pi_hour", "")
                    if pi_hour_type in ("datetime", "timestamp", "date"):
                        where.append("`pi_hour` = :pi_hour_eq")
                        params["pi_hour_eq"] = start_dt  # 取 HH:00:00 為值
                    else:
                        where.append("TRIM(`pi_hour`) = :pi_hour_str")
                        params["pi_hour_str"] = hour_str
                else:
                    logging.warning(f"[get_defects_by_key] table {table} has neither pi_time nor pi_hour; skip time filter.")

                # 額外保險（避免資料不一致）：若表裡也有 pi_hour，就要求它與 hour_str 對齊
                if extra_hour_guard and "pi_hour" in colset:
                    pi_hour_type = col_types.get("pi_hour", "")
                    if pi_hour_type in ("datetime", "timestamp", "date"):
                        where.append("DATE_FORMAT(`pi_hour`, '%Y-%m-%d %H') = :_hour_str")
                    else:
                        where.append("TRIM(`pi_hour`) = :_hour_str")
                    params["_hour_str"] = hour_str

    # 其它鍵
    for k, v in key_dict.items():
        if k == "pi_hour":
            continue
        if k not in colset:
            continue
        col = f"`{k}`"
        if v is None:
            where.append(f"{col} IS NULL")
        elif isinstance(v, (list, tuple, set)):
            lst = [str(x).strip() if isinstance(x, str) else x for x in list(v)]
            if not lst:
                continue
            pname = f"{k}_list"
            where.append(f"{col} IN (:{pname})")
            params[pname] = lst
            expanding.append(bindparam(pname, expanding=True))
        else:
            if isinstance(v, str):
                where.append(f"TRIM({col}) = TRIM(:{k})")
                params[k] = v.strip()
            else:
                where.append(f"{col} = :{k}")
                params[k] = v

    if not where:
        return []

    sql = f"SELECT * FROM `{table}` WHERE " + " AND ".join(where)

    # === 主查詢 ===
    try:
        with self.engine.begin() as conn:
            stmt = text(sql)
            if expanding:
                stmt = stmt.bindparams(*expanding)

            # 記 debug
            def _fmt(v):
                return v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v
            safe_params = {k: _fmt(v) for k, v in params.items()}

            #logging.info(f"[get_defects_by_key] SQL={sql}")
            #logging.info(f"[get_defects_by_key] PARAMS={safe_params}")

            rows = conn.execute(stmt, params).mappings().all()

            # 若 0 筆，做更細的診斷（每鍵單獨匹配、AND 疊加）
            if not rows:
                # 1) 單鍵匹配
                for k, v in key_dict.items():
                    if k == "pi_hour":
                        cnt = 0
                        # 單鍵時間診斷
                        if "pi_time" in colset and ("pi_s" in params and "pi_e" in params):
                            cnt = _run_scalar(conn,
                                              f"SELECT COUNT(*) FROM `{table}` "
                                              f"WHERE "
                                              + ( "STR_TO_DATE(TRIM(`pi_time`), '%Y-%m-%d %H:%i:%s')"
                                                  if col_types.get("pi_time","") not in ("datetime","timestamp","date")
                                                  else "`pi_time`"
                                                )
                                              + " >= :pi_s AND "
                                              + ( "STR_TO_DATE(TRIM(`pi_time`), '%Y-%m-%d %H:%i:%s')"
                                                  if col_types.get("pi_time","") not in ("datetime","timestamp","date")
                                                  else "`pi_time`"
                                                )
                                              + " < :pi_e",
                                              {"pi_s": params.get("pi_s"), "pi_e": params.get("pi_e")})
                        elif "pi_hour" in colset:
                            if "pi_hour_eq" in params:
                                cnt = _run_scalar(conn,
                                                  f"SELECT COUNT(*) FROM `{table}` WHERE `pi_hour` = :v",
                                                  {"v": params.get("pi_hour_eq")})
                            elif "pi_hour_str" in params:
                                cnt = _run_scalar(conn,
                                                  f"SELECT COUNT(*) FROM `{table}` WHERE TRIM(`pi_hour`) = :v",
                                                  {"v": params.get("pi_hour_str")})
                        debug_info["by_single"][k] = cnt
                    else:
                        if k not in colset:
                            debug_info["by_single"][k] = 0
                            continue
                        if v is None:
                            cnt = _run_scalar(conn, f"SELECT COUNT(*) FROM `{table}` WHERE `{k}` IS NULL", {})
                        elif isinstance(v, (list, tuple, set)):
                            lst = list(v)
                            if lst:
                                stmt1 = text(f"SELECT COUNT(*) FROM `{table}` WHERE TRIM(`{k}`) IN :vals") \
                                    .bindparams(bindparam("vals", expanding=True))
                                cnt = conn.execute(stmt1, {"vals": lst}).scalar() or 0
                            else:
                                cnt = 0
                        else:
                            if isinstance(v, str):
                                cnt = _run_scalar(conn,
                                                  f"SELECT COUNT(*) FROM `{table}` WHERE TRIM(`{k}`)=TRIM(:v)",
                                                  {"v": v})
                            else:
                                cnt = _run_scalar(conn,
                                                  f"SELECT COUNT(*) FROM `{table}` WHERE `{k}`=:v",
                                                  {"v": v})
                        debug_info["by_single"][k] = cnt

                # 2) 依序 AND 疊加
                order = ["pi_hour", "line_id", "aoi", "model", "glass_type", "recipe_id", "ai_code_1"]
                cur_where, cur_params = [], {}

                def _bind_exp(stmt_, ps: Dict[str, Any]):
                    bps = []
                    for pk in list(ps.keys()):
                        if pk.endswith("_list"):
                            bps.append(bindparam(pk, expanding=True))
                    return stmt_.bindparams(*bps) if bps else stmt_

                # 時間條件子句（與上方一致）
                def _append_time_clause():
                    if "pi_time" in colset and ("pi_s" in params and "pi_e" in params):
                        if col_types.get("pi_time","") in ("datetime","timestamp","date"):
                            cur_where.append("`pi_time` >= :pi_s AND `pi_time` < :pi_e")
                        else:
                            cur_where.append(
                                "STR_TO_DATE(TRIM(`pi_time`), '%Y-%m-%d %H:%i:%s') >= :pi_s "
                                "AND STR_TO_DATE(TRIM(`pi_time`), '%Y-%m-%d %H:%i:%s') < :pi_e"
                            )
                        cur_params["pi_s"] = params["pi_s"]
                        cur_params["pi_e"] = params["pi_e"]
                    elif "pi_hour" in colset:
                        if "pi_hour_eq" in params:
                            cur_where.append("`pi_hour` = :pi_hour_eq")
                            cur_params["pi_hour_eq"] = params["pi_hour_eq"]
                        elif "pi_hour_str" in params:
                            cur_where.append("TRIM(`pi_hour`) = :pi_hour_str")
                            cur_params["pi_hour_str"] = params["pi_hour_str"]
                    # 額外保險
                    if extra_hour_guard and " _hour_str" in params:
                        if col_types.get("pi_hour","") in ("datetime","timestamp","date"):
                            cur_where.append("DATE_FORMAT(`pi_hour`, '%Y-%m-%d %H') = :_hour_str")
                        else:
                            cur_where.append("TRIM(`pi_hour`) = :_hour_str")
                        cur_params["_hour_str"] = params["_hour_str"]

                for k in order:
                    if k not in key_dict:
                        continue
                    v = key_dict[k]
                    if k == "pi_hour":
                        _append_time_clause()
                    else:
                        if v is None:
                            cur_where.append(f"`{k}` IS NULL")
                        elif isinstance(v, (list, tuple, set)):
                            cur_where.append(f"TRIM(`{k}`) IN :{k}_list")
                            cur_params[f"{k}_list"] = list(v)
                        else:
                            if isinstance(v, str):
                                cur_where.append(f"TRIM(`{k}`) = TRIM(:{k})")
                                cur_params[k] = v
                            else:
                                cur_where.append(f"`{k}` = :{k}")
                                cur_params[k] = v

                    if not cur_where:
                        continue
                    sql_c = f"SELECT COUNT(*) FROM `{table}` WHERE " + " AND ".join(cur_where)
                    stmt_c = _bind_exp(text(sql_c), cur_params)
                    cnt_c = (conn.execute(stmt_c, cur_params).scalar() or 0)
                    debug_info["cumulative"].append({
                        "add": k,
                        "sql": sql_c,
                        "params": {kk: (vv.strftime('%Y-%m-%d %H:%M:%S') if isinstance(vv, datetime) else vv)
                                   for kk, vv in cur_params.items()},
                        "count": cnt_c
                    })

                #logging.info(f"[diagnose][{table}] by_single={debug_info['by_single']}")
                #for step in debug_info["cumulative"]:
                #    logging.info(f"[diagnose][{table}] add={step['add']} count={step['count']} SQL={step['sql']} PARAMS={step['params']}")

            return [dict(r) for r in rows]

    except SQLAlchemyError as e:
        logging.error(f"[get_defects_by_key] {e}")
        return []

# ====== 請求模型 ======
class DefectMapIn(BaseModel):
    rows: List[Dict[str, Any]] = []

# 注意：aoi 也會被用來組表名，但這裡一起保留，做 debug/cumulative 時會列入
RAW_KEYS = ['pi_hour', 'line_id', 'aoi', 'model', 'glass_type', 'recipe_id', 'ai_code_1']

@router.post("/api/defect_map")
async def defect_map(payload: DefectMapIn):
    """
    前端傳入 rows（圖表/表格所選），
    依 AOI + pi_hour 組出資料表名（yymm 取自 pi_hour），
    查詢時：pi_hour 改以 pi_time 的同一小時範圍做時間過濾，再 AND 其它鍵等值/IN/NULL 比對。
    回傳 DefectGroupDict（每列 filters + defect_group；若 0 筆會在 log 中印診斷）。
    """
    main_group_show = ['glass_id','x','y','defect_size','ai_code_1','pi_time','pi_hour']
    dbhandler = MySQLConnet('l6a01_project')
    out_rows: List[Dict[str, Any]] = []

    #logging.info(f"[defect_map] payload rows = {len(payload.rows)}")

    for filters in payload.rows:
        aoi = str(filters.get('aoi') or '').strip().lower()
        pi_hour_raw = filters.get('pi_hour')
        pi_hour_hour = normalize_pi_hour_to_hour_str(pi_hour_raw)

        if not aoi or not pi_hour_hour:
            filters['defect_group'] = {}
            filters['debug'] = {
                "reason": "missing aoi or invalid pi_hour",
                "aoi": aoi,
                "pi_hour_raw": pi_hour_raw,
                "pi_hour_norm_hour": pi_hour_hour,
            }
            out_rows.append(filters)
            continue

        # 表名：{aoi}_pidensity_20{yymm}_pi{pi}
        yymm = ym_from_pi_hour_hourstr(pi_hour_hour)     # '2511'
        pi_suffix = extract_pi_suffix(filters.get('line_id', ''))  # '100'/'200'/'700'…
        tbname = f'{aoi}_pidensity_20{yymm}_pi{pi_suffix}'.lower()

        # key_dict：僅 RAW_KEYS 中有提供的鍵（字串先 strip）
        key_dict: Dict[str, Any] = {}
        for k in RAW_KEYS:
            if k in filters:
                v = filters[k]
                if isinstance(v, str):
                    v = v.strip()
                key_dict[k] = v
        # 確保 pi_hour 用「時」字串（供 get_defects_by_key 轉 pi_time 範圍）
        key_dict['pi_hour'] = pi_hour_hour

        logging.info(f"[defect_map] tb={tbname} key_dict={key_dict}")

        rows = get_defects_by_key(dbhandler, tbname, key_dict)
        #logging.info(f"[defect_map] table={tbname} matched rows={len(rows)}")

        # 顯示部分欄位 + 直接檢查是否在時間區間（便於肉眼確認）
        """
        try:
            # 從 key_dict/內部推算當前查詢的時間窗，僅供印出檢查
            s_e = hour_str_to_range(pi_hour_hour)
            sdt, edt = (s_e if s_e else (None, None))
            for r in rows[:20]:
                in_range = None
                pt = r.get("pi_time")
                if pt is not None and sdt and edt:
                    try:
                        pdt = datetime.strptime(str(pt).strip(), "%Y-%m-%d %H:%M:%S")
                        in_range = (pdt >= sdt and pdt < edt)
                    except Exception:
                        in_range = "parse_fail"
                print({k: r.get(k) for k in main_group_show if k in r}, "in_range=", in_range)
        except Exception:
            pass
        """
        # 分組輸出
        
        filters['defect_group'] = group_defects_by_glass(rows)
        out_rows.append(filters)

    return {"DefectGroupDict": out_rows}
