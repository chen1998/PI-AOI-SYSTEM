// static/js/aoi_inspection/service.js
var inspection_sub_activeTabKey;

(function () {
  const AOI = (window.AOI_INSPECTION = window.AOI_INSPECTION || {});
  const API = window.API;

  // -------------------------
  // 管理 inspection 底下 3 個 section
  // -------------------------
  const INSP_SECTION_IDS = [
    "inspection-root",        // 主畫面（Hourly）
    "inspection-spec-table",  // Spec Table
    "inspection-Chart"        // Trend Chart
  ];

  AOI.currentSectionId = "inspection-root";   // 預設顯示哪一個 section

  AOI.hideAllSections = function () {
    INSP_SECTION_IDS.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = "none";
    });
  };

  AOI.showSection = function (sectionId) {
    AOI.currentSectionId = sectionId || "inspection-root";
    INSP_SECTION_IDS.forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.style.display = (id === AOI.currentSectionId) ? "" : "none";
    });
  };

  // 給 system_tab 在切回 inspection 時呼叫用
  AOI.syncSectionVisibility = function () {
    AOI.showSection(AOI.currentSectionId || "inspection-root");
  };

  AOI.state = {
    payload: null,
    DictData:{},
    rows: [],
    uniques: {},
    timeRange: null,
    paramDict: null,
    activeSubTab: null,
    ProSpecDict: null,

    defectGroups: {}  // key: "pi_hour||line_id||model||glass_type"
  };

  // -------------------------
  // defect_map payload keys（inspection 用）
  // -------------------------
  const RAW_KEYS = ['pi_hour','line_id','model','glass_type'];

  function buildDefectMapPayloadFromRows(rows) {
    const seen = new Map();
    const payloadRows = [];

    for (const r of rows || []) {
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

  // -------------------------
  // 呼叫 /aoi_inspection/api/defect_map
  // -------------------------
  async function fetchDefectGroupsForRows(rows) {
    const payloadRows = buildDefectMapPayloadFromRows(rows);
    if (!payloadRows.length) {
      AOI.state.defectGroups = {};
      return;
    }

    let respJson;
    try {
      if (API && typeof API.post === "function") {
        respJson = await API.post(
          `${window.API_BASE}/aoi_inspection/api/defect_map`,
          { rows: payloadRows }
        );
      } else {
        const resp = await fetch(
          `${window.API_BASE}/aoi_inspection/api/defect_map`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ rows: payloadRows })
          }
        );
        respJson = await resp.json();
      }
    } catch (err) {
      console.error("[AOI_INSPECTION.fetchDefectGroupsForRows] API error:", err);
      return;
    }

    const arr = respJson?.DefectGroupDict || [];
    const dict = {};
    for (const row of arr) {
      const key = RAW_KEYS.map(k => (row[k] ?? "")).join("||");
      dict[key] = row.defect_group || {};
    }

    AOI.state.defectGroups = dict;
    console.log("[AOI_INSPECTION] 更新 defectGroups：", dict);
  }

  AOI.buildDefectMapPayloadFromRows = buildDefectMapPayloadFromRows;
  AOI.fetchDefectGroupsForRows      = fetchDefectGroupsForRows;

  // -------------------------
  // 時間工具
  // -------------------------
  function fmtPiHourToShort(s){
    const d=new Date(String(s).replace(" ","T"));
    if(isNaN(d)) return String(s||"");
    const yy=String(d.getFullYear()).slice(-2),
          mm=String(d.getMonth()+1).padStart(2,"0"),
          dd=String(d.getDate()).padStart(2,"0"),
          hh=String(d.getHours()).padStart(2,"0");
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
    return isNaN(d.getTime()) ? null : d;
  }
  function calcTimeRange(rows){
    if(!rows?.length) return null;
    let min=Infinity,max=-Infinity;
    rows.forEach(r=>{
      const d=parsePiHourToDate(r.pi_hour || r.tick_str);
      if(!d) return;
      const t=d.getTime();
      if(t<min) min=t;
      if(t>max) max=t;
    });
    return min===Infinity ? null : {min:new Date(min),max:new Date(max)};
  }

  // -------------------------
  // 抓 inspection summary
  // -------------------------
  AOI.fetchInspectionData = async function (opts) {
    const dates   = (opts?.dates && Array.isArray(opts.dates)) ? opts.dates : undefined;
    const filters = opts?.filters || {};

    const params = { filter_ask_keys: JSON.stringify(filters || {}) };
    if (dates) params.dates = dates;

    const payload = await window.API.get(
      `${window.API_BASE}/aoi_inspection/api/reset_summary_filter`,
      params
    );
    console.log('payload',payload);
    if (!payload) return;

    AOI.state.payload   = payload;
    AOI.state.DictData = payload.DictData || {};
    AOI.state.paramDict = payload.ParamDict || null;
    AOI.state.ProSpecDict = payload.ProSpecDict || null;
    //console.log('ProSpecDict', AOI.state.ProSpecDict)

    const src = Array.isArray(payload.DictData) ? payload.DictData : [];
    const toNum = v => Number(v) || 0;

    const rows = src.map(r => {
      const mgGlass = toNum(r.maingroup_glass_count);
      const dcCount = toNum(r.maingroup_defect_count);
      const density = mgGlass > 0 ? dcCount / mgGlass : 0;
      const sizeMask = toNum(r.size_mask || 0);
      const availableSizes = Array.isArray(r.available_sizes) ? r.available_sizes.slice() : [];

      return {
        // 主鍵
        pi_hour: fmtPiHourToShort(r.pi_hour),
        line_id: String(r.line_id || ""),
        model: String(r.model || ""),
        glass_type: String(r.glass_type || ""),

        // 計算欄位
        maingroup_glass_count: mgGlass,
        maingroup_defect_count: dcCount,
        defect_code_glass_count: toNum(r.defect_code_glass_count),

        small_defect_count:  toNum(r.small_defect_count),
        middle_defect_count: toNum(r.middle_defect_count),
        large_defect_count:  toNum(r.large_defect_count),
        over_defect_count:   toNum(r.over_defect_count),

        density,
  
        size_mask: sizeMask,
        available_sizes: availableSizes,

        glass: Array.isArray(r.glass) ? r.glass : (r.glass ?? ""),
        glass_defect_count: r.glass_defect_count ?? {},
        glass_size_detail: r.glass_size_detail?? (r.glass_size_detail ?? ""),
        tick_str: fmtPiHourToShort(r.pi_hour),
        n_glasses: mgGlass,
        defect_num: dcCount,
        comment:r.comment?? (r.comment ?? ""),
        action: r.action?? (r.action ?? ""),
        Editor:r.Editor?? (r.Editor ?? ""),
        modify_time: r.modify_time?? (r.modify_time ?? ""),
      };
    });

    AOI.state.rows      = rows;
    AOI.state.timeRange = calcTimeRange(rows);
    AOI.state.uniques   = payload.ParamDict?.filterOptionDict || {};

    document.dispatchEvent(new CustomEvent("aoi_inspection:data-ready", {
      detail: {
        rows,
        uniques: AOI.state.uniques,
        timeRange: AOI.state.timeRange,
        paramDict: AOI.state.paramDict
      }
    }));

    return payload;
  };

  // ===================== SubTabs：建立與套用 =====================

  function ensureAfterDataReady(fn){
    if (AOI.state.paramDict) { fn(); return; }
    const handler = ()=>{ document.removeEventListener("aoi_inspection:data-ready", handler); fn(); };
    document.addEventListener("aoi_inspection:data-ready", handler);
  }

  function getFilterKeys(){
    const dict = AOI.state.paramDict?.filtetItemKeyDict || {};
    return Object.keys(dict);
  }
  function selectIdOf(key){
    // inspection 的 filter select id 命名規則：insp-f-*
    return `insp-f-${key}`;
  }

  AOI.getFilterKeys = getFilterKeys;
  AOI.selectIdOf    = selectIdOf;

  function readFiltersFromUI(){
    // 這裡只是提供給 applySubTab 做「預設勾選」，實際 redraw 還是交給 filter7.js + router1.js
    const out = {};
    getFilterKeys().forEach(k=>{
      const el = document.getElementById(selectIdOf(k));
      if (!el) { out[k] = []; return; }
      if (el.tagName === "SELECT" && el.multiple) {
        out[k] = Array.from(el.selectedOptions).map(o=>o.value).filter(v=>v!=="" && v!=null);
      } else {
        out[k] = [];
      }
    });
    return out;
  }
  AOI.readFiltersFromUI = AOI.readFiltersFromUI || readFiltersFromUI;

  function applyInspectionSubTabFilters(tabKey){
    const pd   = AOI.state.paramDict || {};
    const map  = pd.SubTabsFilterDefaultDict || {};
    const defs = map[tabKey];
    if (!defs) return;

    const MDD  = AOI.mdd || (window.AOI_INSPECTION && window.AOI_INSPECTION.mdd) || {};

    Object.entries(defs).forEach(([k, wantList])=>{
      if (!Array.isArray(wantList) || !wantList.length) return;
      const mdd = MDD[k];
      if (mdd) {
        // 多選元件存在時，用其 API 設定
        mdd.setSelected(wantList.slice());
        const selEl = document.getElementById(selectIdOf(k));
        selEl?.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });

    AOI.state.activeSubTab = tabKey;
    inspection_sub_activeTabKey = tabKey;
  }

  // === 根據 SubTab 的 type 決定要切到哪個 section ===
  AOI.applySubTab = function(tabKey){
    //console.log(tabKey);
    const pd   = AOI.state.paramDict || {};
    const defs = pd.SubTabsFilterDefaultDict?.[tabKey] || {};
    const type = defs.type || "";   // "", "table", "Chart"
    const rows = AOI.state.ProSpecDict?.[tabKey] || {};
    console.log(tabKey, rows);
    
    AOI.state.activeSubTab = tabKey;
    inspection_sub_activeTabKey = tabKey;

    // 先把所有 inspection section 關掉
    AOI.hideAllSections();

    if (!type) {
      // === 沒 type：hourly → 顯示主 Inspection 畫面 ===
      AOI.showSection("inspection-root");
      applyInspectionSubTabFilters(tabKey);
      // filter7.js 中的 change 事件會觸發 router redraw

    } else if (type === "table") {
      // === type: "table" → Spec Table 頁 ===
      AOI.showSection("inspection-spec-table");

      document.dispatchEvent(new CustomEvent("aoi_inspection:subtab-table", {
        detail: { tabKey, config: defs, data: rows }
      }));
    } else if (type === "Chart") {
      // === type: "Chart" → Trend Chart 頁 ===
      AOI.showSection("inspection-Chart");

      document.dispatchEvent(new CustomEvent("aoi_inspection:subtab-chart", {
        detail: { tabKey, config: defs }
      }));
    } else {
      // 未知 type：當成主畫面
      AOI.showSection("inspection-root");
      applyInspectionSubTabFilters(tabKey);
    }
  };

  /*


  */

  AOI.buildRightSubTabs = function(containerEl){
    ensureAfterDataReady(()=>{
      const pd   = AOI.state.paramDict || {};
      const map  = pd.SubTabsFilterDefaultDict || {};
      const keys = Object.keys(map);

      if (!containerEl || !keys.length) {
        if (containerEl) containerEl.innerHTML = "";
        return;
      }

      containerEl.innerHTML = "";

      keys.forEach(k=>{
        const conf  = map[k] || {};
        const type  = conf.type || "";          // "", "table", "Chart"
        const label = conf.tab_name || k;       // 顯示名稱

        const btn = document.createElement("button");
        btn.className = "sys-tab";              // 跟上排一樣風格
        btn.textContent = label;
        btn.dataset.subkey = k;
        if (type) btn.dataset.type = type;

        if (AOI.state.activeSubTab === k) {
          btn.classList.add("active");
        }

        btn.addEventListener("click", ()=>{
          Array.from(containerEl.querySelectorAll(".sys-tab"))
            .forEach(b=>b.classList.remove("active"));
          btn.classList.add("active");

          AOI.applySubTab(k);
        });

        containerEl.appendChild(btn);
      });

      // 若還沒有 activeSubTab，預設選第一顆（hourly）
      if (!AOI.state.activeSubTab && keys.length) {
        const firstKey = keys[0];
        AOI.state.activeSubTab = firstKey;

        const firstBtn = containerEl.querySelector(".sys-tab");
        if (firstBtn) firstBtn.classList.add("active");

        AOI.applySubTab(firstKey);
      } else if (AOI.state.activeSubTab) {
        // 若已經有 activeSubTab（例如切 view 再切回來），也同步 section 顯示
        AOI.applySubTab(AOI.state.activeSubTab);
      }
    });
  };

})();