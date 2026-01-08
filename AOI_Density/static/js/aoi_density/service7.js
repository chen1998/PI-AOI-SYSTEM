// static/js/aoi_density/service.js
var density_sub_activeTabKey;
(function () {
  const AOI = (window.AOI_DENSITY = window.AOI_DENSITY || {});
  const API = window.API;

  AOI.state = {
    payload: null,
    rows: [],
    uniques: {},
    timeRange: null,
    paramDict: null,
    activeSubTab: null,
    ProSpecDict: null,
    
    defectGroups: {}  // key: "pi_hour||line_id||aoi||model||glass_type||recipe_id||ai_code_1"
  };

  // ===== defect_map 相關：建立 payload + 呼叫後端 /defect_map =====

  const RAW_KEYS = ['pi_hour','line_id','aoi','model','glass_type','recipe_id','ai_code_1'];

  function buildDefectMapPayloadFromRows(rows) {
    const seen = new Map();
    const payloadRows = [];

    for (const r of rows || []) {
      // 注意：這裡的 pi_hour 是「畫面上的字串」（yy-mm-dd HH），
      // 後端會再 normalize 成 'YYYY-MM-DD HH'。
      const key = RAW_KEYS.map(k => (r[k] ?? "")).join("||");
      if (seen.has(key)) continue;
      seen.set(key, true);

      const one = {};
      RAW_KEYS.forEach(k => {
        if (k in r) {
          one[k] = r[k];
        }
      });
      payloadRows.push(one);
    }
    return payloadRows;
  }

  /**
   * 呼叫 /api/defect_map，取得每個分群底下「每片 glass 的 S/M/L/O/total + defect_map」。
   * 呼叫成功後會把結果存進 AOI.state.defectGroups，
   * key 為同樣的 RAW_KEYS 串接字串。
   *
   * 使用方式（例如在別的檔案）：
   *   const rows = AOI.getFiltered();
   *   AOI.fetchDefectGroupsForRows(rows);  // 非同步更新 AOI.state.defectGroups
   */
  async function fetchDefectGroupsForRows(rows) {
    const payloadRows = buildDefectMapPayloadFromRows(rows);
    if (!payloadRows.length) {
      AOI.state.defectGroups = {};
      return;
    }

    let respJson;
    try {
      if (API && typeof API.post === "function") {
        // 與 reset_summary_filter 一樣走 /aoi_density 前綴
        respJson = await API.post(
          `${window.API_BASE}/aoi_density/api/defect_map`,
          { rows: payloadRows }
        );
      } else {
        // fallback：原生 fetch（你平常應該用不到）
        const resp = await fetch(`${window.API_BASE}/aoi_density/api/defect_map`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rows: payloadRows })
        });
        respJson = await resp.json();
      }
    } catch (err) {
      console.error("[AOI.fetchDefectGroupsForRows] API error:", err);
      return;
    }

    const arr = respJson && respJson.DefectGroupDict ? respJson.DefectGroupDict : [];
    const dict = {};

    for (const row of arr) {
      const key = RAW_KEYS.map(k => (row[k] ?? "")).join("||");
      // row.defect_group 是後端 group_defects_by_glass 的結果：
      // { glass_id: { S,M,L,O,total, defect_map:[...] }, ... }
      dict[key] = row.defect_group || {};
    }

    AOI.state.defectGroups = dict;
    console.log("[AOI] 更新 defectGroups：", dict);
  }

  // 暴露給其他檔（table.js / chart.js 等）用
  AOI.buildDefectMapPayloadFromRows = buildDefectMapPayloadFromRows;
  AOI.fetchDefectGroupsForRows      = fetchDefectGroupsForRows;

  // ==== 時間/轉換工具 ====
  function fmtPiHourToShort(s){
    const d=new Date(String(s).replace(" ","T"));
    if(isNaN(d)) return String(s||"");
    const yy=String(d.getFullYear()).slice(-2), mm=String(d.getMonth()+1).padStart(2,"0"),
          dd=String(d.getDate()).padStart(2,"0"), hh=String(d.getHours()).padStart(2,"0");
    return `${yy}-${mm}-${dd} ${hh}`;
  }
  function parsePiHourToDate(s){
    if(!s) return null;
    if(/^\d{2}-\d{2}-\d{2}\s+\d{2}$/.test(s)){
      const [datePart,hh]=s.split(/\s+/);
      const [yy,mm,dd]=datePart.split("-").map(Number);
      return new Date(2000+yy,mm-1,dd,Number(hh),0,0);
    }
    const d=new Date(String(s).replace(" ","T"));
    return isNaN(d.getTime())?null:d;
  }
  function calcTimeRange(rows){
    if(!rows?.length) return null;
    let min=Infinity,max=-Infinity;
    rows.forEach(r=>{
      const d=parsePiHourToDate(r.pi_hour || r.tick_str);
      if(!d) return;
      const t=d.getTime();
      if(t<min) min=t; if(t>max) max=t;
    });
    if(min===Infinity) return null;
    return {min:new Date(min), max:new Date(max)};
  }
  function buildFilterJSON(filters){ return (filters && typeof filters==="object") ? JSON.stringify(filters) : "{}"; }
  function toDatesParam(dates){ return (dates && dates.length===2) ? dates : undefined; }
  
  // ====== 抓資料 ======
  AOI.fetchAoiDensityData = async function (opts) {
    const dates   = (opts?.dates && Array.isArray(opts.dates)) ? opts.dates : undefined;
    const filters = opts?.filters || {};

    const params = { filter_ask_keys: buildFilterJSON(filters) };
    const datesParam = toDatesParam(dates);
    if (datesParam) params.dates = datesParam;

    const payload = await window.API.get(`${window.API_BASE}/aoi_density/api/reset_summary_filter`, params);
    console.log('fetchData', payload);
    // 被 API 鎖判定為重複時會回傳 null；此時不要覆蓋現有狀態
    if (!payload) {
      console.debug('[aoi_density] duplicated fetch suppressed; keep previous state.');
      return AOI.state.payload; // 保留舊資料
    }
    
    AOI.state.payload   = payload;
    AOI.state.paramDict = payload?.ParamDict || null;
    AOI.state.ProSpecDict = payload?.ProSpecDict || null;

    const src = Array.isArray(payload?.DictData) ? payload.DictData : [];
    const toNum = (v) => { const n = Number(v); return Number.isFinite(n) ? n : 0; };

    // ---- 產出 rows（包含 Table 用欄位 + Chart 友善別名）----
    const rows = src.map(r => {
      if (r.model === 'M215HAN01' && r.pi_hour ==='2025-11-09T21:00:00' && r.aoi === 'aoi200' && r.line_id === 'CAPIC200' && r.ai_code_1 === 'Polymer'){
        console.log(r);
      }
      
      const mgGlass = toNum(r.maingroup_glass_count ?? r.total_glass_count ?? r.n_glasses);
      const dcCount = toNum(r.defect_code_count ?? r.maingroup_defect_count ?? r.Total_defect_count ?? r.n_rows);
      const density = mgGlass > 0 ? (dcCount / mgGlass) : 0;

      const sizeMask = toNum(r.size_mask || 0);
      const availableSizes = Array.isArray(r.available_sizes) ? r.available_sizes.slice() : [];

      return {
        // ===== 維度 & 基本欄 =====
        pi_hour: fmtPiHourToShort(r.pi_hour),
        aoi: String(r.aoi || ""),
        line_id: String(r.line_id || ""),
        model: String(r.model || ""),
        glass_type: String(r.glass_type || ""),
        recipe_id: String(r.recipe_id || ""),
        ai_code_1: String(r.ai_code_1 || ""),

        // ===== Table 用 =====
        maingroup_glass_count: mgGlass,
        defect_code_count:     dcCount,
        maingroup_defect_count: toNum(r.maingroup_defect_count ?? r.Total_defect_count),
        small_defect_count:  toNum(r.small_defect_count),
        middle_defect_count: toNum(r.middle_defect_count),
        large_defect_count:  toNum(r.large_defect_count),
        over_defect_count:   toNum(r.over_defect_count),
        defect_code_glass_count: toNum(r.defect_code_glass_count),

        // ===== Chart 舊邏輯相容 =====
        n_glasses: mgGlass,
        n_rows: dcCount,
        density: density,

        // ===== 尺寸篩選（後端前置）=====
        size_mask: sizeMask,
        available_sizes: availableSizes,

        // ===== glass（保留原型別）=====
        glass: Array.isArray(r.glass) ? r.glass : (r.glass ?? ""),
        glass_defect_count: r.glass_defect_count ?? {},

        // ===== Chart 友善別名（之後圖表只吃這組）=====
        aoi_tool: String(r.aoi || ""),
        defect_code: String(r.ai_code_1 || ""),
        line: String(r.line_id || ""),
        model_id: String(r.model || ""),
        tick_str: fmtPiHourToShort(r.pi_hour),
        glass_num: mgGlass,
        defect_num: dcCount,
        code_glass_num: toNum(r.defect_code_glass_count),
        s_count: toNum(r.small_defect_count),
        m_count: toNum(r.middle_defect_count),
        l_count: toNum(r.large_defect_count),
        o_count: toNum(r.over_defect_count)
      };
    });

    // uniques 下拉
    const fo = payload?.ParamDict?.filterOptionDict || {};
    AOI.state.uniques   = { ...fo };
    AOI.state.rows      = rows;
    AOI.state.timeRange = calcTimeRange(rows);

    document.dispatchEvent(new CustomEvent("aoi_density:data-ready", {
      detail: { rows, uniques: AOI.state.uniques, timeRange: AOI.state.timeRange, paramDict: AOI.state.paramDict }
    }));

    return payload;
  };

  // ==== 讀 UI ====
  function readDatesFromUI(){
    const b=document.querySelector("#aoi_densityStart"), e=document.querySelector("#aoi_densityEnd");
    const begin=b?.value, end=e?.value;
    return (begin && end) ? [begin,end] : undefined;
  }
  function getFilterKeys(){ const dict=AOI.state.paramDict?.filtetItemKeyDict || {}; return Object.keys(dict); }
  function selectIdOf(key){ return `f-${key}`; }
  function readMultiSelectValuesByKey(key){
    const el=document.getElementById(selectIdOf(key));
    if(!el) return [];
    if(el.tagName==="SELECT" && el.multiple){ return Array.from(el.selectedOptions).map(o=>o.value).filter(v=>v!=="" && v!=null); }
    return [];
  }
  function readFiltersFromUI(){
    const out={}; getFilterKeys().forEach(k=>{ out[k]=readMultiSelectValuesByKey(k); }); return out;
  }

  // ====== 過濾（含 defect size 位元遮罩）======
  AOI.getFiltered = function(opts){
    const rows = AOI.state.rows || [];
    if(!rows.length) return [];
    const filters = (opts && opts.filters) || readFiltersFromUI();
    const dates   = (opts && opts.dates)   || readDatesFromUI();

    let out = rows.slice();
    const sizeKey="defect_size";

    // 先套一般多選（除 defect_size）
    getFilterKeys().forEach((k)=>{
      if(k===sizeKey) return;
      const arr=filters?.[k];
      if(Array.isArray(arr) && arr.length){
        out = out.filter(r=>arr.includes(String(r[k] ?? "")));
      }
    });

    // defect size：優先使用 ParamDict.DefectSize 的 mask 定義
    const dsMeta = AOI.state.paramDict?.DefectSize || {};
    const maskKey = dsMeta.maskKey || "size_mask";
    const bits = dsMeta.maskBits || {S:1, M:2, L:4, O:8};

    if(Array.isArray(filters?.[sizeKey]) && filters[sizeKey].length){
      const wantMask = filters[sizeKey].reduce((m,s)=> m | (bits[s]||0), 0);
      if (wantMask > 0) {
        out = out.filter(r => ((Number(r[maskKey]||0) & wantMask) !== 0));
      } else {
        // fallback：沒有 mask 時，用四大 count > 0 的 OR
        const sizeMap={S:"small_defect_count", M:"middle_defect_count", L:"large_defect_count", O:"over_defect_count"};
        const cols = filters[sizeKey].map(s=>sizeMap[s]).filter(Boolean);
        if(cols.length) out = out.filter(r=>cols.some(c=>Number(r[c]||0)>0));
      }
    }

    if(dates && dates.length===2){
      const b=new Date(dates[0]+"T00:00:00"), e=new Date(dates[1]+"T23:59:59");
      const tb=b.getTime(), te=e.getTime();
      out = out.filter(r=>{
        const t=parsePiHourToDate(r.tick_str || r.pi_hour)?.getTime();
        return typeof t==="number" && t>=tb && t<=te;
      });
    }

    // ===== 尺寸投影：把未勾選的尺寸歸零，並重算 defect_num / density / defect_code_glass_count =====
    const sizeFilterArr  = Array.isArray(filters?.[sizeKey]) ? filters[sizeKey] : null;
    const selectedSizes  = sizeFilterArr && sizeFilterArr.length ? new Set(sizeFilterArr) : null;
 
    // 解析 "S:1 M:0 L:0 O:0 T:1" 或 {S:1,M:0,L:0,O:0,T:1}
    function parseSizeStats(stat) {
      const out = { S: 0, M: 0, L: 0, O: 0, T: 0 };
      if (!stat) return out;
 
      if (typeof stat === "string") {
        const rx = /\b([SMLOT])\s*:\s*(\d+)/g;
        let m;
        while ((m = rx.exec(stat)) !== null) {
          const k = m[1].toUpperCase();
          const v = Number(m[2] || 0);
          if (k in out && Number.isFinite(v)) out[k] = v;
        }
        if (!/\bT\s*:/.test(stat)) {
          out.T = out.S + out.M + out.L + out.O;
        }
        return out;
      }
 
      if (typeof stat === "object") {
        out.S = Number(stat.S || 0);
        out.M = Number(stat.M || 0);
        out.L = Number(stat.L || 0);
        out.O = Number(stat.O || 0);
        out.T = Number(stat.T || (out.S + out.M + out.L + out.O));
        return out;
      }
 
      return out;
    }
 
    if (selectedSizes && selectedSizes.size > 0) {
      out = out.map((r) => {
        const nG = Number(
          r.n_glasses ??
          r.maingroup_glass_count ??
          r.total_glass_count ??
          0
        );
 
        // 原始尺寸數量（以 AOI.state.rows 為 base，不會被上一輪 getFiltered 汙染）
        const baseS = Number(r.s_count ?? r.small_defect_count ?? 0);
        const baseM = Number(r.m_count ?? r.middle_defect_count ?? 0);
        const baseL = Number(r.l_count ?? r.large_defect_count  ?? 0);
        const baseO = Number(r.o_count ?? r.over_defect_count   ?? 0);
 
        // 依目前勾選的尺寸保留 / 歸零
        const s = selectedSizes.has("S") ? baseS : 0;
        const m = selectedSizes.has("M") ? baseM : 0;
        const l = selectedSizes.has("L") ? baseL : 0;
        const o = selectedSizes.has("O") ? baseO : 0;
 
        const newDef     = s + m + l + o;
        const newDensity = nG > 0 ? newDef / nG : 0;
 
        // === 重新計算「defect glass count」 ===
        let newCodeGlass = Number(
          r.defect_code_glass_count ??
          r.code_glass_num ??
          0
        );
        const gdc = r.glass_defect_count;
 
        if (
          gdc &&
          typeof gdc === "object" &&
          !Array.isArray(gdc) &&
          Object.keys(gdc).length
        ) {
          let cnt = 0;
          Object.values(gdc).forEach((stat) => {
            const st = parseSizeStats(stat);
            const hit =
              (selectedSizes.has("S") && st.S > 0) ||
              (selectedSizes.has("M") && st.M > 0) ||
              (selectedSizes.has("L") && st.L > 0) ||
              (selectedSizes.has("O") && st.O > 0);
            if (hit) cnt += 1;
          });
          newCodeGlass = cnt;
        }
        // 若沒有逐片資訊，就維持原本 defect_code_glass_count（沒辦法精確扣）
 
        return {
          ...r,
 
          // 表格欄位（保持一致）
          small_defect_count:  s,
          middle_defect_count: m,
          large_defect_count:  l,
          over_defect_count:   o,
 
          // Chart 友善欄位（舊欄位相容）
          s_count: s,
          m_count: m,
          l_count: l,
          o_count: o,
 
          // 「該碼」的缺陷數以投影後重算
          defect_code_count: newDef,
          n_rows:            newDef,
          defect_num:        newDef,
 
          // 密度
          density: newDensity,
 
          // ★ 新增：投影後的「有碰到選中尺寸的片數」
          defect_code_glass_count: newCodeGlass,
          code_glass_num:         newCodeGlass,
        };
      });
    }

    return out;
  };

  // 導出工具
  AOI.readFiltersFromUI = readFiltersFromUI;
  AOI.getFilterKeys     = getFilterKeys;
  AOI.selectIdOf        = selectIdOf;

  // ===================== SubTabs：建立與套用 =====================
  function ensureAfterDataReady(fn){
    if (AOI.state.paramDict) { fn(); return; }
    const handler = ()=>{ document.removeEventListener("aoi_density:data-ready", handler); fn(); };
    document.addEventListener("aoi_density:data-ready", handler);
  }

  function getRecipeOptions(tabKey){
    const pd = AOI.state.paramDict || {};
    const subTabsMap = pd.SubTabsFilterDefaultDict || {};
    const defs = subTabsMap?.[tabKey];
    const want = Array.isArray(defs?.recipe_id) ? defs.recipe_id : null;
    return want;
  }

  AOI.applySubTab = function(tabKey){
    const pd   = AOI.state.paramDict || {};
    const defs = pd.SubTabsFilterDefaultDict?.[tabKey];
    const opts = pd.filterOptionDict || {};
    if(!defs) return;

    const MDD = AOI.mdd || (window.AOI_DENSITY && window.AOI_DENSITY.mdd) || {};

    // (A) recipe_id：替換 options 並預設全選
    const recipeWant = getRecipeOptions(tabKey);
    if (Array.isArray(recipeWant) && recipeWant.length){
      const rKey = 'recipe_id';
      const rMdd = MDD[rKey];
      if (rMdd){
        rMdd.updateOptions(recipeWant);
        rMdd.setSelected(recipeWant.slice());
        const selEl = document.getElementById(selectIdOf(rKey));
        selEl?.dispatchEvent(new Event('change', {bubbles:true}));
      } else {
        if (pd.filterOptionDict){
          pd.filterOptionDict[rKey] = recipeWant.slice();
        }
      }
    }

    // (B) 其餘 key：交集預選
    Object.entries(defs).forEach(([k, wantList])=>{
      if (k === 'recipe_id') return;
      const mdd = MDD[k];
      const all = Array.isArray(opts[k]) ? opts[k] : [];
      const want = Array.isArray(wantList) ? wantList : [];
      const picked = want.filter(v => all.includes(v));
      if (mdd && picked.length) {
        mdd.setSelected(picked);
        const selEl = document.getElementById(selectIdOf(k));
        selEl?.dispatchEvent(new Event('change', {bubbles:true}));
      }
    });

    AOI.state.activeSubTab = tabKey;
  };

  AOI.buildRightSubTabs = function(containerEl){
    ensureAfterDataReady(()=>{
      const pd = AOI.state.paramDict || {};
      const map = pd.SubTabsFilterDefaultDict || {};
      const keys = Object.keys(map);
      if (!containerEl || !keys.length) { if(containerEl) containerEl.innerHTML=""; return; }

      containerEl.innerHTML = "";
      keys.forEach(k=>{
        const btn = document.createElement("button");
        btn.className = "sys-tab";
        btn.textContent = k;
        if (AOI.state.activeSubTab === k) btn.classList.add("active");
        btn.addEventListener("click", ()=>{
          Array.from(containerEl.querySelectorAll(".sys-tab")).forEach(b=>b.classList.remove("active"));
          btn.classList.add("active");
          AOI.applySubTab(k);
          density_sub_activeTabKey = k;
        });
        containerEl.appendChild(btn);
      });
      if (!AOI.state.activeSubTab && keys.length) {
        AOI.state.activeSubTab = keys[0];
        const firstBtn = containerEl.querySelector(".sys-tab");
        if (firstBtn) firstBtn.classList.add("active");
        AOI.applySubTab(keys[0]);
      }
    });
  };
})();
