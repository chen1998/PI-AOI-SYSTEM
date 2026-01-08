// static/js/aoi_density/table.js
// 功能：
// - 預設顯示：依 Filter（UI）後的 rows
// - 新增：由 chart 互動（柱/點/xAxis/yAxis）丟進來的 rows 覆寫顯示
// - 表頭依 ParamDict['hourlyTable']；rowspan 合併同 group（修正為整群 rowSpan）
// - 在「Analysis Table」右側自動插入一顆 Return 按鈕，按下後恢復顯示 Filter 結果
(function () {
  const MOD = (window.AOI_DENSITY = window.AOI_DENSITY || {});
  MOD.Table = MOD.Table || {};

  const $ = (sel, root = document) => root.querySelector(sel);

  // ---------- 小工具 ----------
  const isObj = (o) => o && typeof o === "object" && !Array.isArray(o);
  const toArr = (x) => (Array.isArray(x) ? x : []);

  function parseGlassList(val) {
    if (val == null) return [];
    if (Array.isArray(val)) return val.map(String).map((s) => s.trim()).filter(Boolean);
    return String(val).split(",").map((s) => s.trim()).filter(Boolean);
  }
  function dateKeySorter(a, b) {
    const da = new Date("20" + String(a).replace(" ", "T"));
    const db = new Date("20" + String(b).replace(" ", "T"));
    return da - db;
  }
  // 直接使用後端 key（不做顯示名對應）
  function getGroupConf(paramDict){
    const tg = (paramDict && (paramDict.hourlyTable_key_group || paramDict.hourlyTable_key_group)) || {};
    const mainKeys = Array.isArray(tg.main_group) ? tg.main_group.slice() : [];
    //console.log('mainKeys',mainKeys);
    const uniSet   = new Set([ ...(tg.uni_col || []), 'glass', 'glass_defect_count' ]);
    // 時間欄位（用於排序時做時間比較）
    const down = (paramDict && paramDict.chartKeyDict && paramDict.chartKeyDict.down) || [];
    const timeKeys = new Set(['pi_hour', ...down]);
    return { mainKeys, uniSet, timeKeys };
  }
  // 針對群組鍵的值做一致化：去空白、時間轉 timestamp、數值/布林/物件正規化
  function normalizeForKey(key, val, timeKeys) {
    if (val == null) return "";
    if (typeof val === "string") {
      const s = val.trim();
      if (timeKeys && timeKeys.has(key)) {
        const d = new Date("20" + s.replace(" ", "T"));
        if (!isNaN(d)) return String(d.getTime());
      }
      return s;
    }
    if (typeof val === "number") return Number.isFinite(val) ? String(val) : "";
    if (val instanceof Date) return String(val.getTime());
    if (typeof val === "boolean") return val ? "1" : "0";
    if (typeof val === "object") return JSON.stringify(val);
    return String(val);
  }

  // 以實際「要顯示的欄位」為準，排除逐片欄後組出分組簽章
  function makeGroupSig(row, colKeys, perGlass, timeKeys) {
    const parts = [];
    for (const k of colKeys) {
      if (perGlass.has(k)) continue; // 排除逐片欄
      parts.push(k + ":" + normalizeForKey(k, row[k], timeKeys));
    }
    return parts.join("|");
  }

  // 解析像 "S:1 M:0 L:0 O:0 T:1" → {S:1,M:0,L:0,O:0,T:1}
  function parseSizeStatsStr(statStr) {
    const out = { S:0, M:0, L:0, O:0, T:0 };
    if (!statStr) return out;
    const rx = /\b([SMLOT])\s*:\s*(\d+)/g;
    let m;
    while ((m = rx.exec(String(statStr))) !== null) {
      const k = m[1].toUpperCase();
      const v = Number(m[2] || 0);
      if (k in out && Number.isFinite(v)) out[k] = v;
    }
    // 若沒有 T，但四個尺寸有值，就補一個 T
    if (!/\bT\s*:/.test(String(statStr))) {
      out.T = out.S + out.M + out.L + out.O;
    }
    return out;
  }
  // 從 row 的 glass_defect_count 取「當前這片 glass 的總數 T」
  function getPerGlassTotalFromRow(row) {
    const gid = row.__glassId;
    const gdc = row.glass_defect_count;
    if (!gid || !gdc) return null;
    const statStr = gdc[gid]; // 例如 "S:1 M:0 L:0 O:0 T:1"
    if (!statStr) return null;
    const stats = parseSizeStatsStr(statStr);
    return Number.isFinite(stats.T) ? stats.T : null;
  }

  // ---------- Return 按鈕 ----------
  function ensureReturnButton() {
    const head = $("#aoi_density-table-wrap .table-head");
    if (!head) return null;
    let btn = head.querySelector("#aoi_tableReturn");
    if (!btn) {
      btn = document.createElement("button");
      btn.id = "aoi_tableReturn";
      btn.className = "btn btn-xs btn-secondary";
      btn.textContent = "Return";
      btn.style.float = "right";
      btn.style.marginLeft = "auto";
      head.appendChild(btn);
      btn.addEventListener("click", () => {
        const rows = window.AOI_DENSITY?.getFiltered?.() || [];
        const pd = window.AOI_DENSITY?.state?.paramDict || {};
        MOD.Table.render(rows, pd);
        showReturn(false);
      });
    }
    return btn;
  }
  function showReturn(show) {
    const btn = ensureReturnButton();
    if (!btn) return;
    btn.style.display = show ? "" : "none";
    btn.disabled = !show;
  }

  // ---------- 依 ParamDict 推導欄位/分組規格 ----------
 

  // ---------- 由 table_group_key_dic 取得分群/逐片欄（自動把顯示名轉資料鍵） ----------
  function getTableGroupingKeys(paramDict, rows){
    const sample = (Array.isArray(rows) && rows[0]) || {};
    const colDict = (paramDict && paramDict.hourlyTable) || {};   // key=資料欄位, value=表頭文字

    // 反向表：顯示名 -> 資料鍵
    const REV = {};
    Object.entries(colDict).forEach(([k, v])=>{
      if (v != null) REV[String(v).trim()] = k;
    });

    // 常見別名對應
    const SYN = {
      "PI Line": "line_id", "pi line": "line_id", "Line": "line_id",
      "Model": "model", "model_id": "model",
      "side": "glass_type", "Side": "glass_type", "glass side": "glass_type",
      "Hourly": "pi_hour", "hourly":"pi_hour", "pi hour":"pi_hour",
      "recipe": "recipe_id", "Recipe":"recipe_id",
      "defect": "ai_code_1", "Defect":"ai_code_1",

      // 你畫面上的統計欄位常見命名
      "total gld":"maingroup_glass_count",
      "total def":"maingroup_defect_count",
      "gld":"defect_code_glass_count",
      "gld def":"defect_code_count"
    };

    const resolveKey = (k)=>{
      if (!k) return "";
      if (k in sample) return k;      // 就是資料鍵
      if (k in colDict) return k;     // 也是資料鍵
      if (REV[k]) return REV[k];      // 顯示名 -> 資料鍵
      if (SYN[k]) return SYN[k];      // 常見別名 -> 資料鍵
      return k;                       // 保底
    };

    const tg = (paramDict && paramDict.table_group_key_dic) || {};
    const mainRaw = Array.isArray(tg.main_group) ? tg.main_group : [];
    console.log('mainRaw',mainRaw);
    const uniRaw  = Array.isArray(tg.uni_col) ? tg.uni_col : [];

    const mainKeys = mainRaw.map(resolveKey).filter(Boolean);
    const uniSet   = new Set(uniRaw.map(resolveKey));
    // 永遠視為逐片欄（避免被合併）
    uniSet.add("glass");
    uniSet.add("glass_defect_count");
    uniSet.add("glass def statis");

    const down = (paramDict && paramDict.chartKeyDict && paramDict.chartKeyDict.down) || [];
    const timeKeys = new Set(["pi_hour", "Hourly", ...down]);

    // 觀察是否未解析成功（可暫留）
    const unresolved = mainRaw.filter(x => !mainKeys.includes(x) && !Object.values(REV).includes(x));
    if (unresolved.length) {
      console.debug("[table] 未解析為資料鍵的 main_group 項目：", unresolved);
    }

    return { mainKeys, uniSet, timeKeys };
  }

  function getGroupingSpec(paramDict, rows) {
    const ckd = paramDict?.chartKeyDict || {};
    const hourlyTable = paramDict?.hourlyTable || {};

    const metric = new Set([...(ckd.right || []), "n_glasses", "density"]);
    const leftDims = toArr(ckd.left).filter((k) => !metric.has(k));
    const upDims = toArr(ckd.up);
    const downDims = toArr(ckd.down);

    const sample = Array.isArray(rows) && rows.length ? rows[0] : {};
    const perGlass = getPerGlassSet(hourlyTable, sample);

    let dims = [...leftDims, ...upDims, ...downDims];

    const allKeys = new Set([
      ...Object.keys(hourlyTable || {}),
      ...Object.keys(sample || {}),
    ]);
    for (const k of allKeys) {
      if (!dims.includes(k) && !metric.has(k) && !perGlass.has(k)) {
        if (downDims.includes(k)) continue;
        dims.splice(leftDims.length, 0, k);
      }
    }
    dims = Array.from(new Set(dims));

    const timeKeys = new Set(downDims);
    return { dims, timeKeys, perGlass };
  }

  function expandRowsByGlass(rows, paramDict) {
    const { mainKeys, uniSet, timeKeys } = getGroupConf(paramDict);
    //console.log(mainKeys, uniSet, timeKeys);
    const out = [];
  
    (rows || []).forEach((r) => {
      // 玻璃清單：字串 "a,b,c" or 陣列
      //console.log('row',r);
      const gList = Array.isArray(r.glass)
        ? r.glass.map(s=>String(s).trim()).filter(Boolean)
        : String(r.glass||'').split(',').map(s=>s.trim()).filter(Boolean);
  
      // 單片統計來源（object / JSON string）
      let gdc = {};
      if (r.glass_defect_count && typeof r.glass_defect_count === 'object') gdc = r.glass_defect_count;
      else if (typeof r.glass_defect_count === 'string') {
        try { const o = JSON.parse(r.glass_defect_count); if (o && typeof o==='object') gdc=o; } catch {}
      }
  
      // main_group 簽章（完全用後端資料鍵）
      const sig = mainKeys.map(k => k + ':' + (r[k] ?? '')).join('|');
  
      (gList.length ? gList : ['']).forEach((gid, idx) => {
        out.push({
          __groupKey: sig,
          __groupIndex: idx,
          __glassId: gid,
          ...r,
          glass: gid,
          glass_defect_count: gdc
        });
      });
    });
  
    // 依 main_group → glass 排序（pi_hour 做時間排序）
    out.sort((a,b)=>{
      for(const k of getGroupConf(paramDict).mainKeys){
        const av = a[k] ?? '', bv = b[k] ?? '';
        if (timeKeys.has(k)) {
          const da = new Date('20'+String(av).replace(' ','T'));
          const db = new Date('20'+String(bv).replace(' ','T'));
          const cmp = (isNaN(da)-isNaN(db)) || (da-db);
          if (cmp) return cmp;
        } else {
          if (av < bv) return -1;
          if (av > bv) return 1;
        }
      }
      return String(a.glass||'').localeCompare(String(b.glass||''));
    });
  
    return { rows: out, mainKeys, uniSet, timeKeys };
  }
  

  // ---------- 表頭 ----------
  function renderHeader(colDict) {
    const thead = $("#aoi_density-table thead");
    if (!thead) return;
    thead.innerHTML = "";
    const tr = document.createElement("tr");

    const cols = Object.keys(colDict || {});
    cols.forEach((key) => {
      const th = document.createElement("th");
      th.className = `col-${key}`;
      th.textContent = String(colDict[key] || key);
      th.style.whiteSpace = "nowrap";
      th.style.overflow = "hidden";
      th.style.textOverflow = "ellipsis";
      tr.appendChild(th);
    });
    thead.appendChild(tr);
  }

  // ---------- 表身（僅 main_group 欄位做 rowspan，其餘逐列；uni_col 一律逐片） ----------
  function renderBody(expanded, colDict) {
    const tbody = document.querySelector("#aoi_density-table tbody");
    if (!tbody) return;
    tbody.innerHTML = "";
  
    const { rows: rowsEx, mainKeys, uniSet, timeKeys } = expanded || {};
    const colKeys = Object.keys(colDict || {});
    if (!rowsEx || !rowsEx.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = Math.max(1, colKeys.length);
      td.className = "muted";
      td.textContent = "（無資料）";
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }
  
    // 計算每組 rowSpan（用 __groupKey）
    const groupRowspanAtIndex = new Array(rowsEx.length).fill(0);
    let last = "", start = 0;
    rowsEx.forEach((r,i)=>{
      const sig = String(r.__groupKey||"");
      if (i===0) { last=sig; start=0; }
      else if (sig!==last){ groupRowspanAtIndex[start]=i-start; start=i; last=sig; }
      if (i===rowsEx.length-1) groupRowspanAtIndex[start]=rowsEx.length-start;
    });
  
    // 逐列輸出
    for (let i=0;i<rowsEx.length;i++){
      const row = rowsEx[i];
      const isHead = groupRowspanAtIndex[i] > 0;
      const tr = document.createElement("tr");
      tr.className = "main-row";
  
      for (const key of colKeys){
        const isUni = uniSet.has(key);
        const isGroupable = mainKeys.includes(key);
      
        if (isGroupable && !isHead) continue; // 同組內只在首列畫
      
        let val = "";
        if (isUni) {
          if (key === "glass") {
            val = row.glass || "";
          } else if (key === "glass_defect_count") {
            const gdc = row.glass_defect_count;
            if (gdc && typeof gdc==='object' && !Array.isArray(gdc)) {
              const v = gdc[row.__glassId];
              if (v!=null) val = String(v);
            }
          } else {
            val = row[key] != null ? row[key] : "";
          }
        } else {
          val = row[key] != null ? row[key] : "";
        }
      
        // === ★★★ 重要覆蓋：當欄位是群組層級的缺陷數（defect_code_count / n_rows / defect_num），
        // 在逐片視圖下優先顯示「該片 glass 的 T 總數」★★★
        // 你可以依你的欄位命名把以下名單調整/增減
        if (["defect_code_count", "n_rows", "defect_num", "Def Count", "def_count", "defect_count"].includes(key)) {
          const t = getPerGlassTotalFromRow(row);
          if (t != null) val = String(t);
        }
      
        const td = document.createElement("td");
        td.className = `col-${key}`;
        td.style.whiteSpace = "nowrap";
        td.style.overflow = "hidden";
        td.style.textOverflow = "ellipsis";
      
        if (isGroupable && isHead) {
          td.classList.add("merged");
          td.rowSpan = groupRowspanAtIndex[i];
        }
        if (/count$/.test(key) || key === "n_glasses" || key === "density") {
          td.style.textAlign = "right";
        }
      
        td.textContent = val == null ? "" : String(val);
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
  }
  

  // ---------- 串 API：把 rows 丟到 defect_map ----------
  async function sendRowsToDefectMap(rows) {
    //console.log(rows);
    try {
      if (!window.API?.post) {
        console.warn("[AOI_DENSITY] window.API.post 未定義，略過送出 defect_map。");
        return null;
      }
      const url = `${window.API_BASE}/aoi_density/api/defect_map`;
      const resp = await window.API.post(url, { rows: Array.isArray(rows) ? rows : [] });

      if (window.AOI_DENSITY?.state) {
        window.AOI_DENSITY.state.defectMapResponse = resp;
      }
      document.dispatchEvent(new CustomEvent("aoi_density:defect-map-ready", {
        detail: { requestRows: rows, response: resp }
      }));
      return resp;
    } catch (err) {
      console.error("[AOI_DENSITY] defect_map API 錯誤：", err);
      document.dispatchEvent(new CustomEvent("aoi_density:defect-map-error", {
        detail: { error: err }
      }));
      return null;
    }
  }
  // ---------- 把 API 回來的 S/M/L/O/Total 填到 rows.glass_defect_count ----------
  function injectGlassCounts(requestRows, response) {
    const list = (response && response.DefectGroupDict) || [];
    const out = (requestRows || []).map((r, idx) => {
      const src = list[idx] || {};
      const dg = src.defect_group || {};
      const gdc = {};
      Object.entries(dg).forEach(([gid, payload]) => {
        const S = Number(payload?.S || 0);
        const M = Number(payload?.M || 0);
        const L = Number(payload?.L || 0);
        const O = Number(payload?.O || 0);
        const T = Number(payload?.total || 0);
        gdc[gid] = `S:${S} M:${M} L:${L} O:${O} T:${T}`;
      });
      return { ...r, glass_defect_count: gdc, __no_api: true };
    });
    return out;
  }

  // ---------- 對外：預設渲染（依 UI Filter） ----------
  MOD.Table.render = function (rows, paramDict) {
    const colDict = isObj(paramDict?.hourlyTable) ? paramDict.hourlyTable : null;
  
    let useColDict;
    if (colDict && Object.keys(colDict).length) {
      useColDict = colDict;
    } else {
      const sample = toArr(rows)[0] || {};
      const dyn = {};
      Object.keys(sample).forEach((k) => (dyn[k] = k));
      useColDict = dyn;
    }
  
    renderHeader(useColDict);
    const expanded = expandRowsByGlass(rows || [], paramDict || {});
    renderBody(expanded, useColDict);
    showReturn(false);
  };
  

  // ---------- 對外：覆寫顯示（由圖表點擊而來） ----------
  MOD.Table.showRows = function (rows, paramDict, opts) {
    const noPost = !!(opts && opts.noPost);
    const colDict = isObj(paramDict?.hourlyTable) ? paramDict.hourlyTable : null;
  
    let useColDict;
    if (colDict && Object.keys(colDict).length) {
      useColDict = colDict;
    } else {
      const sample = toArr(rows)[0] || {};
      const dyn = {};
      Object.keys(sample).forEach((k) => (dyn[k] = k));
      useColDict = dyn;
    }
  
    renderHeader(useColDict);
    const expanded = expandRowsByGlass(rows || [], paramDict || {});
    renderBody(expanded, useColDict);
    showReturn(true);
  
    if (!noPost && !rows?.[0]?.__no_api) {
      sendRowsToDefectMap(rows);
    }
  };

  // ---- 監聽 defect-map 回傳：把 S/M/L/O/T 寫回表格，並觸發地圖渲染 ----
  document.addEventListener("aoi_density:defect-map-ready", (ev) => {
    const req = ev?.detail?.requestRows || [];
    const resp = ev?.detail?.response || {};
    const pd = window.AOI_DENSITY?.state?.paramDict || {};
    const updated = injectGlassCounts(req, resp);
    MOD.Table.showRows(updated, pd, { noPost: true });
  });

})();