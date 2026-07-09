// static/js/bpi_area/bpi_density/service1.js
// BPI Density 功能服務
//
// 職責：
// - 拉 /bpi_density/reset_summary_filter
// - 設定 AOI_BPI_DENSITY.state.rows / paramDict / ProSpecDict
// - 提供 AOI_BPI_DENSITY.getFiltered()
// - 提供 AOI_BPI_DENSITY.fetchCstDefectGroupsForRows()
// - 處理 BPI Density chart 點擊後 table/map 資料流
//
// 注意：
// - 不再負責 system section 切換
// - 不再負責右上 subtabs 建立
// - 這些由 static/js/bpi_area/common/service.js 的 BPI_AREA 負責

var bpi_density_sub_activeTabKey;

(function () {
  const AOI = (window.AOI_BPI_DENSITY = window.AOI_BPI_DENSITY || {});
  const API = window.AOI_BPI_DENSITY_API;
  const SH = AOI.Shared || {};

  // ============================================================
  // Legacy bridge：舊呼叫委派給 BPI_AREA
  // ============================================================
  AOI.hideAllSections = function () {
    return window.BPI_AREA?.hideAllSections?.();
  };

  AOI.showSection = function (sectionId) {
    return window.BPI_AREA?.showSection?.(sectionId);
  };

  AOI.syncSectionVisibility = function () {
    return window.BPI_AREA?.syncSectionVisibility?.();
  };

  AOI.buildRightSubTabs = function (containerEl) {
    return window.BPI_AREA?.buildRightSubTabs?.(containerEl);
  };

  AOI.applySubTab = function (tabKey) {
    return window.BPI_AREA?.applySubTab?.(tabKey);
  };

  // ============================================================
  // State
  // ============================================================
  AOI.state = AOI.state || {
    payload: null,
    DictData: {},
    rows: [],
    uniques: {},
    timeRange: null,
    paramDict: null,
    activeSubTab: null,
    ProSpecDict: {},
    defectGroups: {},

    chartInited: false,
    tableInitedMap: {},
    tableStateCache: {},
    trendStateCache: null
  };

  // ============================================================
  // ParamDict helpers
  // ============================================================
  function getParamDict() {
    return AOI.state?.paramDict || {};
  }

  function getBpiDensityConfig() {
    const pd = getParamDict();
    return pd.bpiDensity || pd || {};
  }

  function getFilterItemDict() {
    const cfg = getBpiDensityConfig();
    return cfg.filtetItemKeyDict || cfg.filterItemKeyDict || {};
  }

  function getFilterOptionDict() {
    const cfg = getBpiDensityConfig();
    return cfg.filterOptionDict || {};
  }

  // ============================================================
  // Defect map payload
  // ============================================================
  AOI.handleSelection = async function (rows, paramDict) {
    AOI.Table?.showRows?.(rows, paramDict, { noPost: true });

    const resp = await AOI.fetchCstDefectGroupsForRows(rows);

    document.dispatchEvent(new CustomEvent("aoi-bpi-density:defect-map-ready", {
      detail: {
        requestRows: rows,
        response: resp
      }
    }));
  };

  function buildCstDefectMapPayloadFromRows(rows) {
    const seen = new Map();
    const payloadRows = [];

    const keys = (SH && Array.isArray(SH.RAW_KEYS) && SH.RAW_KEYS.length)
      ? SH.RAW_KEYS.slice()
      : [
          "aoi",
          "model",
          "scan_hour",
          "cassette_id",
          "glass_side",
          "recipe_id",
          "glass_list",
          "glass_size_detail"
        ];

    for (const r of rows || []) {
      const key = (SH.makeDefectGroupKey)
        ? SH.makeDefectGroupKey(r, keys)
        : JSON.stringify(keys.map(k => r?.[k] ?? ""));

      if (seen.has(key)) continue;
      seen.set(key, true);

      const obj = (SH.pickRowFields)
        ? SH.pickRowFields(r, keys)
        : (() => {
            const x = {};
            keys.forEach(k => {
              x[k] = r?.[k] ?? "";
            });
            return x;
          })();

      payloadRows.push(obj);
    }

    return payloadRows;
  }

  async function fetchCstDefectGroupsForRows(rows) {
    const payloadRows = buildCstDefectMapPayloadFromRows(rows);

    if (!payloadRows.length) {
      AOI.state.defectGroups = {};
      return { DefectGroupDict: {} };
    }

    try {
      if (!API?.postCstDefectMap) {
        AOI.state.defectGroups = {};
        return { DefectGroupDict: {} };
      }

      const respJson = await API.postCstDefectMap(payloadRows);
      const dict = respJson?.DefectGroupDict;

      AOI.state.defectGroups = (dict && typeof dict === "object") ? dict : {};
      return respJson;
    } catch (err) {
      console.error("[AOI_BPI_DENSITY.fetchCstDefectGroupsForRows] API error:", err);
      AOI.state.defectGroups = {};
      return { DefectGroupDict: {} };
    }
  }

  AOI.buildCstDefectMapPayloadFromRows = buildCstDefectMapPayloadFromRows;
  AOI.fetchCstDefectGroupsForRows = fetchCstDefectGroupsForRows;

  // 舊名稱相容
  AOI.buildDefectMapPayloadFromRows = buildCstDefectMapPayloadFromRows;
  AOI.fetchDefectGroupsForRows = fetchCstDefectGroupsForRows;

  // ============================================================
  // Time helpers
  // ============================================================
  function pad2(n) {
    return String(n).padStart(2, "0");
  }
  
  function fmtDateYYYYMMDD(d) {
    return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
  }
  
  function defaultBpiDensityRange() {
    const end = new Date();
    const start = new Date(end.getTime() - 3 * 24 * 3600 * 1000);
    return [fmtDateYYYYMMDD(start), fmtDateYYYYMMDD(end)];
  }
  
  function ensureBpiDensityDefaultDates(force = false) {
    const s = document.querySelector("#aoi-bpi-density-start");
    const e = document.querySelector("#aoi-bpi-density-end");
    if (!s || !e) return;
  
    const [ds, de] = defaultBpiDensityRange();
  
    if (force || !s.value) s.value = ds;
    if (force || !e.value) e.value = de;
  }

  function parseScanHourToDate(v) {
    if (SH.parseScanHourToDate) return SH.parseScanHourToDate(v);

    if (!v) return null;

    const raw = String(v).trim();
    if (!raw) return null;

    const d = new Date(raw.replace(" ", "T"));
    return isNaN(d.getTime()) ? null : d;
  }

  function calcTimeRange(rows) {
    if (!rows?.length) return null;

    let min = Infinity;
    let max = -Infinity;

    rows.forEach(r => {
      const d = parseScanHourToDate(r.scan_hour_raw || r.scan_hour);
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

  function toDatesParam(dates) {
    return (dates && dates.length === 2) ? dates : undefined;
  }

  // ============================================================
  // Data fetch
  // ============================================================
  AOI.fetchBpiDensityData = async function (opts) {
    ensureBpiDensityDefaultDates(false);

    const dates = (opts?.dates && Array.isArray(opts.dates)) ? opts.dates : undefined;
    const params = {};


    const datesParam = toDatesParam(dates);
    if (datesParam) params.dates = datesParam;

    if (!API?.resetSummaryFilter) {
      throw new Error("AOI_BPI_DENSITY_API.resetSummaryFilter 不存在");
    }

    const payload = await API.resetSummaryFilter(params);

    if (!payload) {
      console.debug("[aoi-bpi-density] duplicated fetch suppressed; keep previous state.");
      return AOI.state.payload;
    }

    AOI.state.payload = payload;
    AOI.state.paramDict = payload?.ParamDict || null;
    AOI.state.ProSpecDict = payload?.ProSpecDict || {};

    const src = Array.isArray(payload?.DictData) ? payload.DictData : [];

    console.log("[BPI Density payload]", payload);

    const rows = src.map(r => {
      const scanRaw = String(r.scan_hour || "");

      const gList = SH.U?.glassList
        ? SH.U.glassList(r)
        : String(r.glass_list || "")
            .split(",")
            .map(s => String(s || "").trim())
            .filter(Boolean);

      const gsdObj = SH.U?.gsdObj
        ? SH.U.gsdObj(r)
        : (() => {
            try {
              return r.glass_size_detail ? JSON.parse(r.glass_size_detail) : {};
            } catch (_e) {
              return {};
            }
          })();

      return {
        aoi: String(r.aoi || ""),
        model: String(r.model || ""),
        cassette_id: String(r.cassette_id || ""),
        glass_side: String(r.glass_side || ""),
        recipe_id: String(r.recipe_id || ""),
        pi_type: String(r.pi_type || ""),

        scan_hour: scanRaw,
        scan_hour_raw: scanRaw,
        run_day: String(r.run_day || ""),

        glass_count: Number(r.glass_count || 0),

        base_total_defect_count: Number(r.total_defect_count || 0),
        base_density: Number(r.density || 0),

        total_defect_count: Number(r.total_defect_count || 0),
        density: Number(r.density || 0),

        small_defect_count: Number(r.small_defect_count || 0),
        middle_defect_count: Number(r.middle_defect_count || 0),
        large_defect_count: Number(r.large_defect_count || 0),
        over_defect_count: Number(r.over_defect_count || 0),
        size_mask: Number(r.size_mask || 0),

        glass_list: String(r.glass_list || ""),
        glass_list_arr: gList,
        glass_size_detail: String(r.glass_size_detail || ""),
        glass_size_detail_obj: gsdObj,

        comment: String(r.comment || ""),
        action: String(r.action || ""),
        editor: String(r.editor || r.Editor || ""),
        Editor: String(r.Editor || r.editor || ""),
        modify_time: String(r.modify_time || "")
      };
    });

    const fo = payload?.ParamDict?.bpiDensity?.filterOptionDict || {};

    AOI.state.uniques = { ...fo };
    AOI.state.rows = rows;
    AOI.state.timeRange = calcTimeRange(rows);

    document.dispatchEvent(new CustomEvent("aoi-bpi-density:data-ready", {
      detail: {
        rows,
        uniques: AOI.state.uniques,
        timeRange: AOI.state.timeRange,
        paramDict: AOI.state.paramDict
      }
    }));

    return payload;
  };

  // ============================================================
  // Filter read
  // ============================================================
  function readDatesFromUI() {
    const b = document.querySelector("#aoi-bpi-density-start");
    const e = document.querySelector("#aoi-bpi-density-end");

    const begin = b?.value;
    const end = e?.value;

    return (begin && end) ? [begin, end] : undefined;
  }

  function getFilterKeys() {
    const dict = getFilterItemDict();
    return Object.keys(dict);
  }

  function selectIdOf(key) {
    return `bpi-f-${key}`;
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

  // ============================================================
  // Filtering
  // ============================================================
  AOI.getFiltered = function (opts) {
    const rows = AOI.state.rows || [];
    if (!rows.length) return [];
  
    const filters = (opts && opts.filters) || readFiltersFromUI();
    const dates = (opts && opts.dates) || readDatesFromUI();
  
    let out = rows.slice();
    const sizeKey = "defect_size";
  
    // 任何篩選器存在但沒有勾選任何值 => 直接無資料
    for (const k of getFilterKeys()) {
      const arr = filters?.[k];
  
      if (Array.isArray(arr) && arr.length === 0) {
        return [];
      }
  
      if (k === sizeKey) continue;
  
      if (Array.isArray(arr) && arr.length) {
        out = out.filter(r => arr.includes(String(r[k] ?? "")));
      }
    }
  
    // defect_size mask
    const bits = SH.DEFECT_SIZE_BITS || { S: 1, M: 2, L: 4, O: 8 };
    const maskKey = SH.DEFECT_SIZE_MASK_KEY || "size_mask";
  
    const sizeArr = Array.isArray(filters?.[sizeKey]) ? filters[sizeKey] : null;
    const selectedSizes = (sizeArr && sizeArr.length) ? new Set(sizeArr) : null;
  
    if (selectedSizes && selectedSizes.size) {
      const wantMask = Array.from(selectedSizes).reduce((m, s) => m | (bits[s] || 0), 0);
  
      if (wantMask > 0) {
        out = out.filter(r => ((Number(r[maskKey] || 0) & wantMask) !== 0));
      }
    }
  
    // 日期
    if (dates && dates.length === 2) {
      const b = new Date(dates[0] + "T00:00:00");
      const e = new Date(dates[1] + "T23:59:59");
  
      const tb = b.getTime();
      const te = e.getTime();
  
      out = out.filter(r => {
        const d = parseScanHourToDate(r.scan_hour_raw || r.scan_hour);
        if (!d) return false;
  
        const t = d.getTime();
        return t >= tb && t <= te;
      });
    }
  
    // 尺寸投影
    if (selectedSizes && selectedSizes.size) {
      out = out.map(r => {
        const nG = Number(r.glass_count || 0);
  
        const baseS = Number(r.small_defect_count || 0);
        const baseM = Number(r.middle_defect_count || 0);
        const baseL = Number(r.large_defect_count || 0);
        const baseO = Number(r.over_defect_count || 0);
  
        const s = selectedSizes.has("S") ? baseS : 0;
        const m = selectedSizes.has("M") ? baseM : 0;
        const l = selectedSizes.has("L") ? baseL : 0;
        const o = selectedSizes.has("O") ? baseO : 0;
  
        const newDef = s + m + l + o;
        const newDensity = nG > 0 ? (newDef / nG) : 0;
  
        return {
          ...r,
          small_defect_count: s,
          middle_defect_count: m,
          large_defect_count: l,
          over_defect_count: o,
          total_defect_count: newDef,
          density: newDensity
        };
      });
    }
  
    return out;
  };

  AOI.readFiltersFromUI = readFiltersFromUI;
  AOI.getFilterKeys = getFilterKeys;
  AOI.selectIdOf = selectIdOf;

  // ============================================================
  // Apply hourly tab default filter
  // ============================================================
  AOI.applyDensitySubTabFilters = function (tabKey) {
    const pd = AOI.state.paramDict || {};
    const defs = pd.SubTabsFilterDefaultDict?.[tabKey];

    if (!defs) return;

    const MDD = AOI.mdd || {};
    const opts = getFilterOptionDict();

    Object.entries(defs).forEach(([_label, conf]) => {
      if (!conf || typeof conf !== "object") return;

      const key = conf.key;
      if (!key) return;

      const all = Array.isArray(opts[key]) ? opts[key] : [];
      let picked = Array.isArray(conf.values) ? conf.values.slice() : [];

      if (!picked.length) {
        picked = all.slice();
      } else {
        picked = picked.filter(v => all.includes(v));
      }

      const mdd = MDD[key];
      if (mdd && typeof mdd.setSelected === "function") {
        mdd.setSelected(picked);

        const selEl = document.getElementById(selectIdOf(key));
        selEl?.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });

    AOI.state.activeSubTab = tabKey;
  };

  // ============================================================
  // Trend compatibility
  // ============================================================
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

    console.debug("[AOI_BPI_DENSITY.fetchTrend] payload =", JSON.parse(JSON.stringify(body)));

    try {
      if (!API?.postTrend) return null;

      const resp = await API.postTrend(body);

      const td = resp?.TrendDict || {};
      const meta = resp?.Meta || {};
      const summaryN = td?.summary?.points?.length || 0;
      const monthN = td?.month?.points?.length || 0;
      const weekN = td?.week?.points?.length || 0;
      const dayN = td?.day?.points?.length || 0;

      console.debug("[AOI_BPI_DENSITY.fetchTrend] response meta =", meta);
      console.debug("[AOI_BPI_DENSITY.fetchTrend] response points =", {
        summary: summaryN,
        month: monthN,
        week: weekN,
        day: dayN
      });

      if (extra?.debug_full_response) {
        console.debug("[AOI_BPI_DENSITY.fetchTrend] response FULL =", resp);
      }

      return resp;
    } catch (e) {
      console.error("[AOI_BPI_DENSITY.fetchTrend] trend fetch failed:", e);
      return null;
    }
  };

  // ============================================================
  // BPI Area common table-tab helper
  // ============================================================
  AOI.getProSpecRowsForTab = function (system, tabKey, config) {
    const pro = AOI.state?.ProSpecDict || {};

    const base = [
      tabKey,
      config?.data_key,
      config?.table_name,
    ].filter(Boolean);

    const candidates = system === "bpi_same_point"
      ? [
          ...base,
          "bpi_same_point_default_spec",
          "bpi_same_point_default_spec_table",
        ]
      : [
          ...base,
          "bpi_density_default_spec",
          "default_spec_table",
        ];

    for (const key of candidates) {
      if (pro[key] !== undefined && pro[key] !== null) {
        return pro[key];
      }
    }

    return {};
  };
})();