// static/js/duty/cell_piaoi/aoi_density2/service1.js
var density_sub_activeTabKey;

(function () {
  const AOI = (window.AOI_DENSITY = window.AOI_DENSITY || {});
  const API = window.AOI_DENSITY_API;
  const SH = AOI.Shared;

  const DENSITY_SECTION_IDS = [
    "aoi-density-root",
    "aoi-density-spec-table",
    "aoi-density-trend-chart-root",
    "density-csv-download-root",
    "density-avg-download-root",
  ];

  AOI.currentSectionId = "aoi-density-root";

  AOI.hideAllSections = function () {
    DENSITY_SECTION_IDS.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = "none";
    });
  };

  AOI.showSection = function (sectionId) {
    AOI.currentSectionId = sectionId || "aoi-density-root";

    DENSITY_SECTION_IDS.forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.style.display = id === AOI.currentSectionId ? "" : "none";
    });
  };

  AOI.syncSectionVisibility = function () {
    AOI.showSection(AOI.currentSectionId || "aoi-density-root");
  };

  AOI.state = AOI.state || {
    payload: null,
    DictData: {},
    rows: [],
    uniques: {},
    timeRange: null,
    paramDict: null,
    activeSubTab: null,
    ProSpecDict: null,
    TabSummaryData: [],
    TabTotalDict: {},
    defectGroups: {},
    DefaultFilterDict: {},

    chartInited: false,
    tableInitedMap: {},
    tableStateCache: {},
    trendStateCache: null,
    forceEmptyFilter: false,

    samePointPayload: null,
    SamePointData: [],
    SamePointIndex: {},
    samePointOffset: 20,
    samePointEnabled: true,
    

  };

  AOI.handleSelection = async function (rows, paramDict) {
    AOI.Table?.showRows?.(rows, paramDict, { noPost: true });

    const samePointRows = AOI.attachSamePointToRows
      ? AOI.attachSamePointToRows(rows || [])
      : [];

    // 先送一次空 defect response，讓同點星號優先繪製，不等 /defect_map
    document.dispatchEvent(new CustomEvent("aoi-density:defect-map-ready", {
      detail: {
        requestRows: rows || [],
        response: { DefectGroupDict: {}, DefectCodeList: [] },
        samePointRows,
        samePointFirst: true
      }
    }));

    const resp = await AOI.fetchDefectGroupsForRows(rows);

    // defect_map 回來後再補一般 defect 點；同點星號仍會最後繪製，不會被遮住
    document.dispatchEvent(new CustomEvent("aoi-density:defect-map-ready", {
      detail: {
        requestRows: rows || [],
        response: resp,
        samePointRows,
        samePointFirst: false
      }
    }));
  };

  function fallbackMakeDefectGroupKey(row, keys) {
    return (keys || []).map(k => {
      if (k === "pi_hour") return row?.pi_hour_raw || row?.pi_hour || "";
      return row?.[k] ?? "";
    }).join("||");
  }

  function fallbackPickRowFields(row, keys) {
    const out = {};

    (keys || []).forEach(k => {
      if (!row) return;

      if (k === "pi_hour") {
        out.pi_hour = row.pi_hour_raw || row.pi_hour || "";
        return;
      }

      if (k in row) out[k] = row[k];
    });

    return out;
  }

  function buildDefectMapPayloadFromRows(rows) {
    const seen = new Map();
    const payloadRows = [];

    const keys = SH?.RAW_KEYS || [
      "pi_hour",
      "line_id",
      "aoi",
      "model",
      "glass_type",
      "recipe_id",
      "adc_def_code",
      "glass",
      "glass_size_detail"
    ];

    for (const r of rows || []) {
      const key = SH?.makeDefectGroupKey
        ? SH.makeDefectGroupKey(r, keys)
        : fallbackMakeDefectGroupKey(r, keys);

      if (seen.has(key)) continue;
      seen.set(key, true);

      const picked = SH?.pickRowFields
        ? SH.pickRowFields(r, keys)
        : fallbackPickRowFields(r, keys);

      picked.pi_hour = r?.pi_hour_raw || r?.pi_hour || picked.pi_hour || "";

      if (r?.tab_name != null) picked.tab_name = r.tab_name;
      if (r?.recipe_family != null) picked.recipe_family = r.recipe_family;

      payloadRows.push(picked);
    }

    return payloadRows;
  }

  async function fetchDefectGroupsForRows(rows) {
    const payloadRows = buildDefectMapPayloadFromRows(rows);

    if (!payloadRows.length) {
      AOI.state.defectGroups = {};
      return { DefectGroupDict: {} };
    }

    try {
      const respJson = await API.postDefectMap(payloadRows);
      const dict = respJson?.DefectGroupDict;
      AOI.state.defectGroups = dict && typeof dict === "object" ? dict : {};
      return respJson;
    } catch (err) {
      console.error("[AOI.fetchDefectGroupsForRows] API error:", err);
      AOI.state.defectGroups = {};
      return { DefectGroupDict: {} };
    }
  }

  AOI.buildDefectMapPayloadFromRows = buildDefectMapPayloadFromRows;
  AOI.fetchDefectGroupsForRows = fetchDefectGroupsForRows;

  function calcTimeRange(rows) {
    if (!rows?.length) return null;

    let min = Infinity;
    let max = -Infinity;

    rows.forEach(r => {
      const d = SH.parsePiHourToDate(r.pi_hour_raw || r.pi_hour);
      if (!d) return;

      const t = d.getTime();
      if (t < min) min = t;
      if (t > max) max = t;
    });

    if (min === Infinity) return null;

    return {
      min: new Date(min),
      max: new Date(max)
    };
  }

  function buildFilterJSON(filters) {
    return filters && typeof filters === "object" ? JSON.stringify(filters) : "{}";
  }

  function isCurrentDateRangeOver3Days() {
    const dates = readDatesFromUI();
    if (!dates || dates.length !== 2) return false;
  
    const b = new Date(dates[0] + "T00:00:00");
    const e = new Date(dates[1] + "T00:00:00");
  
    if (Number.isNaN(b.getTime()) || Number.isNaN(e.getTime())) return false;
  
    const diffDays = Math.floor((e - b) / 86400000) + 1;
    return diffDays > 3;
  }
  
  function isAllSelected(selected, options) {
    const s = new Set((selected || []).map(String));
    const o = (options || []).map(String).filter(Boolean);
  
    return o.length > 0 && o.every(x => s.has(x));
  }
  
  function pickOneModelPerLine(rows, lineIds) {
    const out = [];
    const seenLine = new Set();
  
    const lineSet = new Set((lineIds || []).map(String));
  
    const sorted = (rows || []).slice().sort((a, b) => {
      const la = String(a.line_id || "");
      const lb = String(b.line_id || "");
      const ma = String(a.model || "");
      const mb = String(b.model || "");
  
      if (la !== lb) return la.localeCompare(lb);
      return ma.localeCompare(mb);
    });
  
    sorted.forEach(r => {
      const line = String(r.line_id || "").trim();
      const model = String(r.model || "").trim();
  
      if (!line || !model) return;
      if (lineSet.size && !lineSet.has(line)) return;
      if (seenLine.has(line)) return;
  
      seenLine.add(line);
      out.push(model);
    });
  
    return Array.from(new Set(out));
  }

  
  AOI.refreshCascadeFiltersFromUI = function (changedKey) {
    const pd = AOI.state.paramDict || {};
    const globalOpts = pd.filterOptionDict || {};
    const MDD = AOI.mdd || {};
  
    const activeTab = AOI.state.activeSubTab || density_sub_activeTabKey || "";
    const staticDefs = pd.SubTabsFilterDefaultDict?.[activeTab] || {};
    const dynamicOpts = AOI.state.DynamicFilterOptionDict?.[activeTab] || {};
    const activeBackendTab = normalizeDensityTabKey(activeTab);
  
    const filterKeys = Object.keys(pd.filtetItemKeyDict || {});
  
    const cascadeOrder = [
      "line_id",
      "aoi",
      "model",
      "glass_type",
      "recipe_id",
      "adc_def_code",
      "defect_size"
    ].filter(k => filterKeys.includes(k));
  
    const changedIdx = cascadeOrder.indexOf(changedKey);
    if (changedIdx < 0) return;
  
    function cleanArr(v) {
      return Array.isArray(v)
        ? v.map(x => String(x).trim()).filter(Boolean)
        : [];
    }
  
    function getSelected(key) {
      if (MDD[key]?.selected) {
        return Array.from(MDD[key].selected).map(String).filter(Boolean);
      }
      return [];
    }
  
    function getRecipeFamily() {
      return String(staticDefs.recipe_family || "").trim();
    }
  
    function recipeMatchFamily(recipeId) {
      const s = String(recipeId || "").trim();
      const fam = getRecipeFamily();
  
      if (!s) return false;
  
      if (s.length === 3) return true;
  
      if (s.length === 4) {
        if (fam === "UPI") return /^[23]/.test(s);
        if (fam === "PISpot" || fam === "SPS") return /^[01]/.test(s);
      }
  
      return false;
    }
  
    function getRows(targetKey, selectedMap) {
      let rows = AOI.state.rows || [];
  
      if (activeBackendTab) {
        rows = rows.filter(r => {
          const rowTab = String(r.tab_name || "").trim();
          return !rowTab || rowTab === activeBackendTab;
        });
      }
  
      if (targetKey === "recipe_id") {
        rows = rows.filter(r => recipeMatchFamily(r.recipe_id));
      }
  
      for (const key of cascadeOrder) {
        if (key === targetKey) break;
        if (key === "adc_def_code") continue;
        if (key === "defect_size") continue;
  
        const vals = cleanArr(selectedMap[key]);
        if (!vals.length) continue;
  
        rows = rows.filter(r => vals.includes(String(r[key] ?? "")));
      }
  
      return rows;
    }
  
    function getValidOptions(targetKey, selectedMap) {
      // 使用者操作後，model/glass/recipe 要依前面選擇重新算
      // 但 adc_def_code / defect_size 用固定規則
      if (targetKey === "adc_def_code") {
        const rows = AOI.state.rows || [];
        return Array.from(new Set(
          rows
            .filter(r => {
              const rowTab = String(r.tab_name || "").trim();
              return !activeBackendTab || !rowTab || rowTab === activeBackendTab;
            })
            .map(r => String(r.adc_def_code || "").trim())
            .filter(Boolean)
        )).sort();
      }
  
      if (targetKey === "defect_size") {
        return cleanArr(globalOpts[targetKey] || ["S", "M", "L", "O"]);
      }
  
      const rows = getRows(targetKey, selectedMap);
  
      let values = rows
        .map(r => String(r[targetKey] ?? "").trim())
        .filter(Boolean);
  
      if (targetKey === "recipe_id") {
        values = values.filter(recipeMatchFamily);
      }
  
      return Array.from(new Set(values)).sort();
    }
  
    const selectedMap = {};
  
    cascadeOrder.forEach((key, idx) => {
      if (idx <= changedIdx) {
        selectedMap[key] = getSelected(key);
        return;
      }
  
      const validOptions = getValidOptions(key, selectedMap);
  
      MDD[key]?.updateOptions?.(validOptions);
  
      let selected = [];

      if (key === "adc_def_code") {
        selected = cleanArr(staticDefs.adc_def_code || [])
          .filter(v => validOptions.includes(v));
      } else if (key === "defect_size") {
        selected = validOptions.slice();
      } else if (key === "model") {
        const lineOptions = MDD.line_id?.options || [];
        const selectedLines = selectedMap.line_id || [];

        const lineAllSelected =
          changedKey === "line_id" &&
          isCurrentDateRangeOver3Days() &&
          isAllSelected(selectedLines, lineOptions);

        if (lineAllSelected) {
          const rowsForModel = getRows("model", {
            line_id: selectedLines,
            aoi: selectedMap.aoi || getSelected("aoi")
          });

          selected = pickOneModelPerLine(rowsForModel, selectedLines)
            .filter(v => validOptions.includes(v));
        } else {
          selected = validOptions.slice();
        }
      } else {
        selected = validOptions.slice();
      }

      MDD[key]?.setSelected?.(selected);
      selectedMap[key] = selected;

    });
  
    const rows = AOI.getFiltered?.() || [];
    AOI.Charts?.render?.(rows, AOI.state.paramDict || {});
    AOI.Table?.render?.(rows, AOI.state.paramDict || {});
  };

  function toDatesParam(dates) {
    return dates && dates.length === 2 ? dates : undefined;
  }

  function normalizeDensityTabKey(tabKey) {
    const x = String(tabKey || "").trim();
    if (!x) return "";

    const defs = AOI.state.paramDict?.SubTabsFilterDefaultDict?.[x];
    const backend = String(defs?.backend_tab_name || "").trim();

    if (backend) return backend;
    if (x === "UPI(Total)") return "UPI_Total";
    if (x === "PISpot(Total)") return "PISpot_Total";

    return x;
  }

  function getRawActiveDensityTabKey() {
    return String(AOI.state.activeSubTab || density_sub_activeTabKey || "").trim();
  }

  function getActiveDensityTabKey() {
    return normalizeDensityTabKey(getRawActiveDensityTabKey());
  }

  function normalizeTabKeyPiHour(x) {
    const raw = String(x || "").trim();
    if (!raw) return "";

    let s = raw.replace("T", " ").replace(".000", "").trim();

    if (/^\d{4}-\d{2}-\d{2}\s+\d{2}$/.test(s)) s += ":00:00";
    if (/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}$/.test(s)) s += ":00";

    const d = SH.parsePiHourToDate(s);

    if (d) {
      const y = d.getFullYear();
      const m = String(d.getMonth() + 1).padStart(2, "0");
      const day = String(d.getDate()).padStart(2, "0");
      const hh = String(d.getHours()).padStart(2, "0");
      return `${y}-${m}-${day} ${hh}:00:00`;
    }

    return s;
  }

  function makeTabTotalKeyFromRow(r) {
    return [
      normalizeTabKeyPiHour(r?.pi_hour_raw || r?.pi_hour),
      String(r?.line_id || ""),
      String(r?.aoi || ""),
      String(r?.model || ""),
      String(r?.glass_type || "")
    ].join("||");
  }

  function getTabTotalForRow(row, tabKey) {
    const tab = normalizeDensityTabKey(tabKey || getRawActiveDensityTabKey());
    const key = makeTabTotalKeyFromRow(row);
    const d = AOI.state.TabTotalDict?.[tab]?.[key];

    if (!d) {
      return {
        tab_total_glass_cnt: 0,
        tab_total_defect_cnt: 0,
        tab_total_density: 0
      };
    }

    return {
      tab_total_glass_cnt: Number(d.tab_total_glass_cnt || 0),
      tab_total_defect_cnt: Number(d.tab_total_defect_cnt || 0),
      tab_total_density: Number(d.tab_total_density || 0)
    };
  }

  function attachTabTotalsToRows(rows, tabKey) {
    const activeBackendTab = normalizeDensityTabKey(tabKey || getRawActiveDensityTabKey());

    return (rows || []).map(r => {
      const rowTG = Number(r.tab_total_glass_cnt || 0);
      const rowTD = Number(r.tab_total_defect_cnt || 0);
      const rowTN = Number(r.tab_total_density || 0);

      const t = rowTG > 0
        ? {
            tab_total_glass_cnt: rowTG,
            tab_total_defect_cnt: rowTD,
            tab_total_density: rowTN
          }
        : getTabTotalForRow(r, activeBackendTab);

      const tg = Number(t.tab_total_glass_cnt || 0);
      const td = Number(t.tab_total_defect_cnt || 0);
      const tn = Number(t.tab_total_density || 0);

      const currentDef = Number(r.defect_cnt || 0);
      const tabCodeDensity = tg > 0 ? currentDef / tg : 0;

      return {
        ...r,

        tab_name: String(r.tab_name || activeBackendTab || ""),
        recipe_family: String(r.recipe_family || ""),

        tab_total_glass_cnt: tg,
        tab_total_defect_cnt: td,
        tab_total_density: tn,

        total_glass_cnt: tg,
        total_defect_cnt: td,
        total_density: tn,

        recipe_code_density: Number(r.recipe_code_density || 0),
        tab_code_density: tabCodeDensity,

        density: tabCodeDensity
      };
    });
  }

  AOI.makeTabTotalKeyFromRow = makeTabTotalKeyFromRow;
  AOI.getTabTotalForRow = getTabTotalForRow;
  AOI.attachTabTotalsToRows = attachTabTotalsToRows;
  AOI.normalizeDensityTabKey = normalizeDensityTabKey;
  AOI.getActiveDensityTabKey = getActiveDensityTabKey;
  AOI.getRawActiveDensityTabKey = getRawActiveDensityTabKey;

  function getSubTabDefsForActiveTab() {
    const pd = AOI.state.paramDict || {};
    const map = pd.SubTabsFilterDefaultDict || {};
    const rawActive = getRawActiveDensityTabKey();
    return map[rawActive] || {};
  }

  function asCleanStringArray(v) {
    return Array.isArray(v)
      ? v.map(x => String(x).trim()).filter(Boolean)
      : [];
  }

  function intersectArray(a, b) {
    const bSet = new Set(b.map(String));
    return a.filter(x => bSet.has(String(x)));
  }

  function hasFilterDom(key) {
    return !!document.getElementById(selectIdOf(key));
  }

  function isUserClearedFilter(filters, key) {
    return hasFilterDom(key) && Array.isArray(filters?.[key]) && filters[key].length === 0;
  }

  function buildEffectiveFilters(uiFilters) {
    const filters = { ...(uiFilters || {}) };
    const defs = getSubTabDefsForActiveTab();

    const allowedRecipes = asCleanStringArray(defs.recipe_id);
    const allowedCodes = asCleanStringArray(defs.adc_def_code);

    if (allowedRecipes.length) {
      const uiRecipe = asCleanStringArray(filters.recipe_id);

      if (isUserClearedFilter(filters, "recipe_id")) {
        filters.recipe_id = [];
      } else if (uiRecipe.length) {
        const inter = intersectArray(uiRecipe, allowedRecipes);
        filters.recipe_id = inter.length ? inter : [];
      } else {
        filters.recipe_id = allowedRecipes.slice();
      }
    }

    if (allowedCodes.length) {
      const uiCodes = asCleanStringArray(filters.adc_def_code);

      if (isUserClearedFilter(filters, "adc_def_code")) {
        filters.adc_def_code = [];
      } else if (uiCodes.length) {
        filters.adc_def_code = uiCodes.slice();
      } else {
        filters.adc_def_code = allowedCodes.slice();
      }
    }

    return filters;
  }

  AOI.reapplyActiveDensitySubTabFilters = function () {
    const active = getRawActiveDensityTabKey();
    if (!active) return;

    const defs = AOI.state.paramDict?.SubTabsFilterDefaultDict?.[active];
    if (!defs) return;

    const type = defs.type || "";
    if (type) return;

    AOI.applyDensitySubTabFilters(active);
  };

  AOI.fetchAoiDensityData = async function (opts) {
    const dates = opts?.dates && Array.isArray(opts.dates) ? opts.dates : undefined;
    const filters = opts?.filters || readFiltersFromUI();

    const params = {
      filter_ask_keys: buildFilterJSON(filters)
    };

    const datesParam = toDatesParam(dates);
    if (datesParam) params.dates = datesParam;

    const payload = await API.resetSummaryFilter(params);

    if (!payload) {
      console.debug("[aoi-density] duplicated fetch suppressed; keep previous state.");
      return AOI.state.payload;
    }

    AOI.state.payload = payload;
    AOI.state.paramDict = payload?.ParamDict || null;
    AOI.state.DefaultFilterDict = payload?.ParamDict?.DefaultFilterDict || {};
    AOI.state.DynamicFilterOptionDict = payload?.ParamDict?.DynamicFilterOptionDict || {};
    
    AOI.state.ProSpecDict = payload?.ProSpecDict || null;
    AOI.state.TabSummaryData = Array.isArray(payload?.TabSummaryData)
      ? payload.TabSummaryData
      : [];

    AOI.state.TabTotalDict = payload?.TabTotalDict || {};

    const src = Array.isArray(payload?.DictData) ? payload.DictData : [];

    const rows = src.map(r => {
      const piRaw = r.pi_hour;
      const piShort = SH.fmtPiHourToShort(piRaw);

      const gList = SH.parseGlassList(r.glass);
      const gsdObj = SH.parseGlassSizeDetail(r.glass_size_detail);

      const tabTG = Number(r.tab_total_glass_cnt || r.total_glass_cnt || 0);
      const tabTD = Number(r.tab_total_defect_cnt || r.total_defect_cnt || 0);
      const tabTN = Number(r.tab_total_density || r.total_density || 0);

      const defectCnt = Number(r.defect_cnt || 0);
      const tabCodeDensity = tabTG > 0 ? defectCnt / tabTG : Number(r.density || 0);

      return {
        line_id: String(r.line_id || ""),
        aoi: String(r.aoi || ""),
        model: String(r.model || ""),
        glass_type: String(r.glass_type || ""),
        recipe_id: String(r.recipe_id || ""),
        adc_def_code: String(r.adc_def_code || ""),

        recipe_family: String(r.recipe_family || ""),
        tab_name: String(r.tab_name || ""),

        pi_hour: piShort,
        pi_hour_raw: piRaw,

        recipe_total_glass_cnt: Number(r.recipe_total_glass_cnt || r.glass_cnt || 0),
        recipe_total_defect_cnt: Number(r.recipe_total_defect_cnt || 0),
        recipe_total_density: Number(r.recipe_total_density || 0),
        recipe_raw_defect_cnt: Number(r.recipe_raw_defect_cnt || 0),
        recipe_total_defect_gap: Number(r.recipe_total_defect_gap || 0),

        tab_total_glass_cnt: tabTG,
        tab_total_defect_cnt: tabTD,
        tab_total_density: tabTN,
        tab_raw_defect_cnt: Number(r.tab_raw_defect_cnt || 0),
        tab_total_defect_gap: Number(r.tab_total_defect_gap || 0),

        glass_cnt: Number(r.glass_cnt || r.recipe_total_glass_cnt || 0),
        defect_cnt: defectCnt,

        density: tabCodeDensity,

        def_glass_cnt: Number(r.def_glass_cnt || 0),

        total_glass_cnt: tabTG,
        total_defect_cnt: tabTD,
        total_density: tabTN,

        recipe_code_density: Number(r.recipe_code_density || 0),
        tab_code_density: tabCodeDensity,

        small_defect_count: Number(r.small_defect_count || 0),
        middle_defect_count: Number(r.middle_defect_count || 0),
        large_defect_count: Number(r.large_defect_count || 0),
        over_defect_count: Number(r.over_defect_count || 0),
        size_mask: Number(r.size_mask || 0),

        glass: r.glass ?? "",
        glass_size_detail: r.glass_size_detail ?? "",

        glass_list: gList,
        glass_size_detail_obj: gsdObj,

        comment: String(r.comment || ""),
        action: String(r.action || ""),
        Editor: String(r.Editor || ""),
        modify_time: String(r.modify_time || "")
      };
    });

    const fo = payload?.ParamDict?.filterOptionDict || {};
    AOI.state.uniques = { ...fo };
    AOI.state.rows = rows;
    AOI.state.timeRange = calcTimeRange(rows);

    // 日期套用後，如果目前在 Total tab，就重拉 same point。
    if (isSamePointTab(AOI.state.activeSubTab || density_sub_activeTabKey)) {
      try {
        await AOI.fetchSamePointData({
          tabKey: AOI.state.activeSubTab || density_sub_activeTabKey,
          dates,
          offset: AOI.state.samePointOffset || 20
        });
      } catch (e) {
        console.error("[aoi-density] fetch same point after reset failed:", e);
      }
    }

    document.dispatchEvent(new CustomEvent("aoi-density:data-ready", {
      detail: {
        rows,
        uniques: AOI.state.uniques,
        timeRange: AOI.state.timeRange,
        paramDict: AOI.state.paramDict,
        TabSummaryData: AOI.state.TabSummaryData,
        TabTotalDict: AOI.state.TabTotalDict
      }
    }));

    requestAnimationFrame(() => {
      if (!AOI.state.skipReapplySubTabOnce) {
        AOI.reapplyActiveDensitySubTabFilters?.();
      }
      AOI.state.skipReapplySubTabOnce = false;
    });

    return payload;
  };

  function readDatesFromUI() {
    const b = document.querySelector("#aoi-density-start");
    const e = document.querySelector("#aoi-density-end");

    const begin = b?.value;
    const end = e?.value;

    return begin && end ? [begin, end] : undefined;
  }

  function getFilterKeys() {
    const dict = AOI.state.paramDict?.filtetItemKeyDict || {};
    return Object.keys(dict);
  }

  function selectIdOf(key) {
    return `f-${key}`;
  }

  function readMultiSelectValuesByKey(key) {
    const el = document.getElementById(selectIdOf(key));
    if (!el) return [];

    if (el.tagName === "SELECT" && el.multiple) {
      return Array.from(el.selectedOptions)
        .map(o => o.value)
        .filter(v => v !== "" && v != null);
    }

    return [];
  }

  function readFiltersFromUI() {
    const out = {};
    getFilterKeys().forEach(k => {
      out[k] = readMultiSelectValuesByKey(k);
    });
    return out;
  }

  AOI.getFiltered = function (opts) {
    const rows = AOI.state.rows || [];
    if (!rows.length) return [];

    const uiFilters = opts?.filters || readFiltersFromUI();
    const filters = buildEffectiveFilters(uiFilters);

    AOI.state.forceEmptyFilter = false;

    const dates = opts?.dates || readDatesFromUI();

    let out = rows.slice();
    const sizeKey = "defect_size";

    const activeBackendTab = getActiveDensityTabKey();

    if (activeBackendTab) {
      out = out.filter(r => {
        const rowTab = String(r.tab_name || "").trim();
        if (!rowTab) return true;
        return rowTab === activeBackendTab;
      });
    }

    for (const k of getFilterKeys()) {
      if (k === sizeKey) continue;

      const arr = filters?.[k];

      if (hasFilterDom(k) && Array.isArray(arr) && arr.length === 0) {
        AOI.state.forceEmptyFilter = true;
        return [];
      }

      if (Array.isArray(arr) && arr.length) {
        out = out.filter(r => arr.includes(String(r[k] ?? "")));
      }
    }

    const bits = SH.DEFECT_SIZE_BITS || { S: 1, M: 2, L: 4, O: 8 };
    const maskKey = SH.DEFECT_SIZE_MASK_KEY || "size_mask";

    const sizeArr = Array.isArray(filters?.[sizeKey]) ? filters[sizeKey] : null;
    const selectedSizes = sizeArr && sizeArr.length ? new Set(sizeArr) : null;

    if (selectedSizes && selectedSizes.size) {
      const wantMask = Array.from(selectedSizes).reduce((m, s) => m | (bits[s] || 0), 0);
      const allMask = (bits.S || 1) | (bits.M || 2) | (bits.L || 4) | (bits.O || 8);

      if (wantMask > 0 && wantMask !== allMask) {
        out = out.filter(r => {
          const rowMask = Number(r[maskKey] || 0);

          if (
            rowMask === 0 &&
            Number(r.glass_cnt || r.recipe_total_glass_cnt || 0) > 0 &&
            Number(r.defect_cnt || 0) === 0
          ) {
            return true;
          }

          return (rowMask & wantMask) !== 0;
        });
      }
    }

    if (dates && dates.length === 2) {
      const b = new Date(dates[0] + "T00:00:00");
      const e = new Date(dates[1] + "T23:59:59");

      const tb = b.getTime();
      const te = e.getTime();

      out = out.filter(r => {
        const d = SH.parsePiHourToDate(r.pi_hour_raw || r.pi_hour);
        if (!d) return false;

        const t = d.getTime();
        return t >= tb && t <= te;
      });
    }

    out = attachTabTotalsToRows(out, activeBackendTab);

    if (selectedSizes && selectedSizes.size) {
      out = out.map(r => {
        const nG = Number(
          r.tab_total_glass_cnt ||
          r.total_glass_cnt ||
          r.recipe_total_glass_cnt ||
          r.glass_cnt ||
          0
        );

        const baseS = Number(r.small_defect_count || 0);
        const baseM = Number(r.middle_defect_count || 0);
        const baseL = Number(r.large_defect_count || 0);
        const baseO = Number(r.over_defect_count || 0);

        const ss = selectedSizes.has("S") ? baseS : 0;
        const mm = selectedSizes.has("M") ? baseM : 0;
        const ll = selectedSizes.has("L") ? baseL : 0;
        const oo = selectedSizes.has("O") ? baseO : 0;

        const newDef = ss + mm + ll + oo;
        const newDensity = nG > 0 ? newDef / nG : 0;

        let newDefGlass = Number(r.def_glass_cnt || 0);
        const gsd = r.glass_size_detail_obj || {};

        if (gsd && typeof gsd === "object" && Object.keys(gsd).length) {
          let cnt = 0;

          Object.values(gsd).forEach(stat => {
            const st = SH.parseSizeStats(stat);

            const hit =
              (selectedSizes.has("S") && st.S > 0) ||
              (selectedSizes.has("M") && st.M > 0) ||
              (selectedSizes.has("L") && st.L > 0) ||
              (selectedSizes.has("O") && st.O > 0);

            if (hit) cnt += 1;
          });

          newDefGlass = cnt;
        }

        return {
          ...r,
          small_defect_count: ss,
          middle_defect_count: mm,
          large_defect_count: ll,
          over_defect_count: oo,
          defect_cnt: newDef,
          density: newDensity,
          tab_code_density: newDensity,
          def_glass_cnt: newDefGlass
        };
      });
    }

    if (isSamePointTab(AOI.state.activeSubTab || density_sub_activeTabKey)) {
      out = attachSamePointToRows(out);
    }

    return out;
  };

  AOI.readFiltersFromUI = readFiltersFromUI;
  AOI.getFilterKeys = getFilterKeys;
  AOI.selectIdOf = selectIdOf;

  function ensureAfterDataReady(fn) {
    if (AOI.state.paramDict) {
      fn();
      return;
    }

    const handler = () => {
      document.removeEventListener("aoi-density:data-ready", handler);
      fn();
    };

    document.addEventListener("aoi-density:data-ready", handler);
  }

  function cleanArr(v) {
    return Array.isArray(v)
      ? v.map(x => String(x).trim()).filter(Boolean)
      : [];
  }

  AOI.applyDensitySubTabFilters = function (tabKey) {
    const pd = AOI.state.paramDict || {};
    const staticDefs = pd.SubTabsFilterDefaultDict?.[tabKey] || {};
    const dynamicDefs = AOI.state.DefaultFilterDict?.[tabKey] || {};
    const dynamicOpts = AOI.state.DynamicFilterOptionDict?.[tabKey] || {};
  
    const defs = {
      ...staticDefs,
      ...dynamicDefs
    };
  
    const globalOpts = pd.filterOptionDict || {};
    const MDD = AOI.mdd || {};
  
    const filterKeys = Object.keys(pd.filtetItemKeyDict || {});
  
    const cascadeOrder = [
      "line_id",
      "aoi",
      "model",
      "glass_type",
      "recipe_id",
      "adc_def_code",
      "defect_size"
    ].filter(k => filterKeys.includes(k));
  
    function cleanArr(v) {
      return Array.isArray(v)
        ? v.map(x => String(x).trim()).filter(Boolean)
        : [];
    }
  
    function setMdd(key, optionValues, selectedValues) {
      const mdd = MDD[key];
      const selEl = document.getElementById(selectIdOf(key));
  
      const options = cleanArr(optionValues);
      const selected = cleanArr(selectedValues).filter(v => {
        return !options.length || options.includes(v);
      });
  
      if (mdd) {
        mdd.updateOptions?.(options);
        mdd.setSelected?.(selected);
        selEl?.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }
  
    function getRecipeFamily() {
      return String(staticDefs.recipe_family || "").trim();
    }
  
    function recipeMatchFamily(recipeId) {
      const s = String(recipeId || "").trim();
      const fam = getRecipeFamily();
  
      if (!s) return false;
  
      if (s.length === 3) return true;
  
      if (s.length === 4) {
        if (fam === "UPI") return /^[23]/.test(s);
        if (fam === "PISpot" || fam === "SPS") return /^[01]/.test(s);
      }
  
      return false;
    }
  
    function getRowsForOptions(targetKey, selectedMap) {
      let rows = AOI.state.rows || [];
      const activeBackendTab = normalizeDensityTabKey(tabKey);
  
      if (activeBackendTab) {
        rows = rows.filter(r => {
          const rowTab = String(r.tab_name || "").trim();
          return !rowTab || rowTab === activeBackendTab;
        });
      }
  
      if (targetKey === "recipe_id") {
        rows = rows.filter(r => recipeMatchFamily(r.recipe_id));
      }
  
      for (const key of cascadeOrder) {
        if (key === targetKey) break;
        if (key === "adc_def_code") continue;
        if (key === "defect_size") continue;
  
        const vals = cleanArr(selectedMap[key]);
        if (!vals.length) continue;
  
        rows = rows.filter(r => vals.includes(String(r[key] ?? "")));
      }
  
      return rows;
    }
  
    function getValidOptions(targetKey, selectedMap) {
      if (dynamicOpts[targetKey]) {
        return cleanArr(dynamicOpts[targetKey]);
      }
  
      if (targetKey === "defect_size") {
        return cleanArr(globalOpts[targetKey] || ["S", "M", "L", "O"]);
      }
  
      let rows = getRowsForOptions(targetKey, selectedMap);
  
      let values = rows
        .map(r => String(r[targetKey] ?? "").trim())
        .filter(Boolean);
  
      if (targetKey === "recipe_id") {
        values = values.filter(recipeMatchFamily);
      }
  
      return Array.from(new Set(values)).sort();
    }
  
    function getSelectedForKey(key, validOptions) {
      // 日期 > 3 天時，由後端 dynamicDefs 指定
      if (Object.prototype.hasOwnProperty.call(dynamicDefs, key)) {
        return cleanArr(dynamicDefs[key]).filter(v => validOptions.includes(v));
      }
  
      // line_id：照 API_Config.py
      if (key === "line_id") {
        return cleanArr(staticDefs.line_id || []).filter(v => validOptions.includes(v));
      }
  
      // aoi：日期 <= 3 天照 API_Config.py；日期 > 3 天 dynamicDefs 已處理
      if (key === "aoi") {
        return cleanArr(staticDefs.aoi || []).filter(v => validOptions.includes(v));
      }
  
      // adc_def_code：永遠照 API_Config.py tab_filter_config
      if (key === "adc_def_code") {
        return cleanArr(staticDefs.adc_def_code || []).filter(v => validOptions.includes(v));
      }
  
      // defect_size：永遠全選
      if (key === "defect_size") {
        return validOptions.slice();
      }
  
      if (key === "model") {
        const selectedLines = selectedMap.line_id || [];
        const lineOptions = dynamicOpts.line_id || globalOpts.line_id || [];

        if (
          isCurrentDateRangeOver3Days() &&
          isAllSelected(selectedLines, lineOptions)
        ) {
          const rowsForModel = getRowsForOptions("model", {
            line_id: selectedLines,
            aoi: selectedMap.aoi || []
          });

          return pickOneModelPerLine(rowsForModel, selectedLines)
            .filter(v => validOptions.includes(v));
        }
      }

      return validOptions.slice();
    }
  
    const selectedMap = {};
  
    cascadeOrder.forEach(key => {
      const validOptions = getValidOptions(key, selectedMap);
      const selected = getSelectedForKey(key, validOptions);
  
      selectedMap[key] = selected;
  
      setMdd(key, validOptions, selected);
    });
  
    AOI.state.activeSubTab = tabKey;
    density_sub_activeTabKey = tabKey;
  };

  AOI.fetchTrend = async function (extra) {
    const target = extra?.target || "";
    const date_dict = extra?.date_dict || {
      summary: { month: [], week: [], day: [] },
      month: [],
      week: [],
      day: []
    };

    const filters = extra?.filters || extra?.filter || {};
    const body = { target, date_dict, filters };

    try {
      return await API.postTrend(body);
    } catch (e) {
      console.error("[AOI.fetchTrend] trend fetch failed:", e);
      return null;
    }
  };

  AOI.applySubTab = async function (tabKey) {
    const pd = AOI.state.paramDict || {};
    const defs = pd.SubTabsFilterDefaultDict?.[tabKey] || {};
    const rows = AOI.state.ProSpecDict?.[tabKey] || {};
    const type = defs.type || "";

    AOI.state.activeSubTab = tabKey;
    density_sub_activeTabKey = tabKey;

    AOI.hideAllSections();

    if (!type) {
      AOI.showSection("aoi-density-root");
      AOI.applyDensitySubTabFilters(tabKey);

      // 初始切到 Total tab 時，打 /recipe_same_point，offset 預設 20
      if (isSamePointTab(tabKey)) {
        try {
          await AOI.fetchSamePointData({
            tabKey,
            dates: readDatesFromUI(),
            offset: AOI.state.samePointOffset || 20
          });
      
          const rows = AOI.getFiltered?.() || [];
      
          AOI.Charts?.render?.(rows, AOI.state.paramDict || {});
          AOI.Table?.render?.(rows, AOI.state.paramDict || {});
        } catch (e) {
          console.error("[aoi-density] fetch same point on tab switch failed:", e);
        }
      } else {
        AOI.state.samePointPayload = null;
        AOI.state.SamePointData = [];
        AOI.state.SamePointIndex = {};
      }

      document.dispatchEvent(new CustomEvent("aoi-density:subtab-density", {
        detail: { tabKey, restoreOnly: true }
      }));

      return;
    }

    if (type === "csv") {
      AOI.showSection("density-csv-download-root");

      window.DENSITY_CSV_DOWNLOAD?.setSystem?.({
        system: "aoi_density",
        tabKey,
        config: defs
      });

      document.dispatchEvent(new CustomEvent("density-csv-download:show", {
        detail: { system: "aoi_density", tabKey, config: defs }
      }));

      return;
    }

    if (type === "density_avg") {
      AOI.showSection("density-avg-download-root");

      document.dispatchEvent(new CustomEvent("density-avg-download:show", {
        detail: { system: "aoi_density", tabKey, config: defs }
      }));

      return;
    }

    if (type === "table") {
      AOI.showSection("aoi-density-spec-table");

      if (tabKey === "EditSummary") {
        const restoreOnly = !!AOI.state.tableInitedMap?.[tabKey];

        if (!restoreOnly) {
          const payload = {
            mode: "date",
            dates: null,
            filter_ask_keys: {}
          };

          const resp = await API.ActionHisEditor(payload);
          if (!resp) return;

          AOI.state.tableInitedMap[tabKey] = true;

          document.dispatchEvent(new CustomEvent("aoi-density:subtab-action-history", {
            detail: { tabKey, config: defs, resp, restoreOnly: false }
          }));

          return;
        }

        document.dispatchEvent(new CustomEvent("aoi-density:subtab-action-history", {
          detail: { tabKey, config: defs, resp: null, restoreOnly: true }
        }));

        return;
      }

      const restoreOnly = !!AOI.state.tableInitedMap?.[tabKey];

      if (!restoreOnly) {
        AOI.state.tableInitedMap[tabKey] = true;
      }

      document.dispatchEvent(new CustomEvent("aoi-density:subtab-table", {
        detail: { tabKey, config: defs, data: rows, restoreOnly }
      }));

      return;
    }

    if (type === "Chart") {
      AOI.showSection("aoi-density-trend-chart-root");

      const restoreOnly = !!AOI.state.chartInited;

      if (!AOI.state.chartInited) {
        AOI.state.chartInited = true;
      }

      document.dispatchEvent(new CustomEvent("aoi-density:subtab-chart", {
        detail: { tabKey, config: defs, trend: null, filter: {}, restoreOnly }
      }));

      return;
    }

    AOI.showSection("aoi-density-root");
    AOI.applyDensitySubTabFilters(tabKey);

    document.dispatchEvent(new CustomEvent("aoi-density:subtab-density", {
      detail: { tabKey, restoreOnly: true }
    }));
  };

  AOI.buildRightSubTabs = function (containerEl) {
    ensureAfterDataReady(() => {
      const pd = AOI.state.paramDict || {};
      const map = pd.SubTabsFilterDefaultDict || {};
      const keys = Object.keys(map);

      if (!containerEl || !keys.length) {
        if (containerEl) containerEl.innerHTML = "";
        return;
      }

      containerEl.innerHTML = "";

      keys.forEach(k => {
        const conf = map[k] || {};
        const type = conf.type || "";
        const label = conf.tab_name || k;

        const btn = document.createElement("button");
        btn.className = "sys-tab";
        btn.textContent = label;
        btn.dataset.subkey = k;

        if (type) btn.dataset.type = type;
        if (AOI.state.activeSubTab === k) btn.classList.add("active");

        btn.addEventListener("click", () => {
          Array.from(containerEl.querySelectorAll(".sys-tab")).forEach(b => b.classList.remove("active"));
          btn.classList.add("active");
          AOI.applySubTab(k);
        });

        containerEl.appendChild(btn);
      });

      if (!AOI.state.activeSubTab && keys.length) {
        const firstKey = keys[0];

        AOI.state.activeSubTab = firstKey;
        density_sub_activeTabKey = firstKey;

        const firstBtn = containerEl.querySelector(".sys-tab");
        if (firstBtn) firstBtn.classList.add("active");

        AOI.applySubTab(firstKey);
      } else if (AOI.state.activeSubTab) {
        const activeBtn = containerEl.querySelector(`[data-subkey="${AOI.state.activeSubTab}"]`);
        if (activeBtn) activeBtn.classList.add("active");
      }
    });
  };

  function isSamePointTab(tabKey) {
    return ["UPI(Total)", "PISpot(Total)"].includes(String(tabKey || "").trim());
  }

  function makeSamePointKeyFromRow(r) {
    return [
      normalizeTabKeyPiHour(r?.pi_hour_raw || r?.pi_hour),
      String(r?.line_id || ""),
      String(r?.aoi || ""),
      String(r?.model || ""),
      String(r?.glass_type || ""),
      String(r?.recipe_id || "")
    ].join("||");
  }

  function attachSamePointToRows(rows) {
    const idx = AOI.state.SamePointIndex || {};

    return (rows || []).map(r => {
      const key = makeSamePointKeyFromRow(r);
      const sp = idx[key] || null;

      return {
        ...r,
        same_point_key: key,
        offset: sp ? Number(sp.offset || 0) : "",
        common_cnt: sp ? Number(sp.common_cnt || 0) : 0,
        common_glass_cnt: sp ? Number(sp.common_glass_cnt || 0) : 0,
        common_points_details: sp ? (sp.common_points_details || "[]") : "[]",
        has_same_point: sp ? Number(sp.common_cnt || 0) > 0 : false
      };
    });
  }

  AOI.fetchSamePointData = async function (opts) {
    const tabKey = opts?.tabKey || AOI.state.activeSubTab || density_sub_activeTabKey || "";
  
    if (!isSamePointTab(tabKey)) {
      AOI.state.samePointPayload = null;
      AOI.state.SamePointData = [];
      AOI.state.SamePointIndex = {};
      return null;
    }
  
    const dates = opts?.dates || readDatesFromUI();
    const offset = Number(opts?.offset || AOI.state.samePointOffset || 20);
  
    const params = {
      tab_name: tabKey,
      offset
    };
  
    if (dates && dates.length === 2) {
      params.dates = dates;
    }
  
    const payload = await API.getRecipeSamePoint(params);
  
    // 防止 API 被防重複機制或其他原因回傳 null 時，把原本 SamePointIndex 清空。
    if (!payload) {
      console.warn("[same-point] empty payload, keep previous SamePointIndex", params);
      return AOI.state.samePointPayload || null;
    }
  
    AOI.state.samePointPayload = payload;
    AOI.state.SamePointData = Array.isArray(payload?.SamePointData)
      ? payload.SamePointData
      : [];
    AOI.state.SamePointIndex = payload?.SamePointIndex || {};
    AOI.state.samePointOffset = offset;
  
    console.debug("[same-point] loaded", {
      tabKey,
      offset,
      rows: AOI.state.SamePointData.length,
      indexKeys: Object.keys(AOI.state.SamePointIndex || {}).length,
      debug: payload.Debug
    });
  
    return payload;
  };
  

  AOI.attachSamePointToRows = attachSamePointToRows;
  AOI.isSamePointTab = isSamePointTab;
  AOI.makeSamePointKeyFromRow = makeSamePointKeyFromRow;
})();