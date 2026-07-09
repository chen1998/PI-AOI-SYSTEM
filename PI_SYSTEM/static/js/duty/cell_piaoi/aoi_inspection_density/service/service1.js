// static/js/aoi_inspection_density/service/service.js
var inspection_sub_activeTabKey;

(function () {
  const AOI = (window.AOI_INSPECTION = window.AOI_INSPECTION || {});
  const API = window.AOI_INSPECTION_API;

  // -------------------------
  // 管理 inspection density 底下 section
  // -------------------------
  const INSP_SECTION_IDS = [
    "aoi-inspection-density-root",
    "aoi-inspection-density-spec-table",
    "aoi-inspection-density-chart-root",
    "density-csv-download-root",
    "density-avg-download-root",
  ];

  AOI.currentSectionId = AOI.currentSectionId || "aoi-inspection-density-root";

  AOI.hideAllSections = function () {
    INSP_SECTION_IDS.forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.style.display = "none";
    });
  };

  AOI.showSection = function (sectionId) {
    AOI.currentSectionId = sectionId || "aoi-inspection-density-root";

    INSP_SECTION_IDS.forEach((id) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.style.display = (id === AOI.currentSectionId) ? "" : "none";
    });
  };

  AOI.syncSectionVisibility = function () {
    AOI.showSection(AOI.currentSectionId || "aoi-inspection-density-root");
  };

  // -------------------------
  // state
  // -------------------------
  AOI.state = AOI.state || {
    payload: null,
    DictData: {},
    rows: [],
    uniques: {},
    timeRange: null,
    paramDict: null,
    activeSubTab: null,
    ProSpecDict: null,
    defectGroups: {},
    chartInited: false,
    tableTabInited: {},
    tableTabSnapshot: {}
  };

  // -------------------------
  // defect_map payload keys（inspection density 用）
  // -------------------------
  const RAW_KEYS = ["pi_hour", "line_id", "model", "glass_type", "glass"];

  function buildDefectMapPayloadFromRows(rows) {
    const seen = new Set();
    const payloadRows = [];

    for (const r of rows || []) {
      const key = RAW_KEYS.map((k) => (r[k] ?? "")).join("||");
      if (seen.has(key)) continue;
      seen.add(key);

      const one = {};
      RAW_KEYS.forEach((k) => {
        if (k in r) one[k] = r[k];
      });
      payloadRows.push(one);
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
      const raw = respJson?.DefectGroupDict || {};
      AOI.state.defectGroups = raw;
      return respJson || { DefectGroupDict: {} };
    } catch (err) {
      console.error("[AOI_INSPECTION.fetchDefectGroupsForRows] API error:", err);
      AOI.state.defectGroups = {};
      return { DefectGroupDict: {} };
    }
  }

  AOI.buildDefectMapPayloadFromRows = buildDefectMapPayloadFromRows;
  AOI.fetchDefectGroupsForRows = fetchDefectGroupsForRows;

  // -------------------------
  // 時間工具
  // -------------------------
  function fmtPiHourToShort(s) {
    const d = new Date(String(s).replace(" ", "T"));
    if (isNaN(d.getTime())) return String(s || "");

    const yy = String(d.getFullYear()).slice(-2);
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    const hh = String(d.getHours()).padStart(2, "0");

    return `${yy}-${mm}-${dd} ${hh}`;
  }

  function parsePiHourToDate(s) {
    if (!s) return null;

    const raw = String(s).trim();

    if (/^\d{2}-\d{2}-\d{2}\s+\d{2}$/.test(raw)) {
      const [datePart, hh] = raw.split(/\s+/);
      const [yy, mm, dd] = datePart.split("-").map(Number);
      return new Date(2000 + yy, mm - 1, dd, Number(hh), 0, 0);
    }

    const d = new Date(raw.replace(" ", "T"));
    return isNaN(d.getTime()) ? null : d;
  }

  function calcTimeRange(rows) {
    if (!rows?.length) return null;

    let min = Infinity;
    let max = -Infinity;

    rows.forEach((r) => {
      const d = parsePiHourToDate(r.pi_hour || r.tick_str);
      if (!d) return;

      const t = d.getTime();
      if (t < min) min = t;
      if (t > max) max = t;
    });

    return min === Infinity ? null : { min: new Date(min), max: new Date(max) };
  }

  function toNum(v) {
    const x = Number(v);
    return Number.isFinite(x) ? x : 0;
  }

  function parseJSONSafe(v, fallback) {
    if (v == null || v === "") return fallback;
    if (typeof v === "object") return v;

    try {
      return JSON.parse(v);
    } catch (_) {
      return fallback;
    }
  }

  function buildFilterJSON(filters) {
    return (filters && typeof filters === "object") ? JSON.stringify(filters) : "{}";
  }

  function toDatesParam(dates) {
    return (dates && dates.length === 2) ? dates : undefined;
  }

  // -------------------------
  // 抓 inspection density summary
  // -------------------------
  AOI.fetchInspectionData = async function (opts = {}) {
    const dates = (opts?.dates && Array.isArray(opts.dates)) ? opts.dates : undefined;
    const filters = opts?.filters || {};

    const params = {
      filter_ask_keys: buildFilterJSON(filters)
    };

    const datesParam = toDatesParam(dates);
    if (datesParam) params.dates = datesParam;

    const payload = await API.resetSummaryFilter(params);
    console.log("[Inspection Density payload]", payload);

    if (!payload) return null;

    AOI.state.payload = payload;
    AOI.state.DictData = payload.DictData || {};

    const rr = payload.ParamDict?.ResolvedQueryRange || {};
    const startEl = document.getElementById("aoi-inspection-density-start");
    const endEl = document.getElementById("aoi-inspection-density-end");

    if (startEl && !startEl.value && rr.start) {
      startEl.value = String(rr.start).slice(0, 10);
    }

    if (endEl && !endEl.value && rr.end) {
      endEl.value = String(rr.end).slice(0, 10);
    }

    AOI.state.paramDict = payload.ParamDict || null;
    AOI.state.ProSpecDict = payload.ProSpecDict || null;

    const src = Array.isArray(payload.DictData) ? payload.DictData : [];

    const rows = src.map((r) => {
      const mgGlass = toNum(r.maingroup_glass_count);
      const dcCount = toNum(r.maingroup_defect_count);

      // display density fallback
      const density = mgGlass > 0 ? dcCount / mgGlass : 0;

      // alert 判斷用：優先後端 maingroup_density，沒有才 fallback 計算值
      const totalDensity = toNum(r.maingroup_density || density);

      const sizeMask = toNum(r.size_mask || 0);
      const availableSizes = Array.isArray(r.available_sizes) ? r.available_sizes.slice() : [];
      const glassSizeDetailList = parseJSONSafe(r.glass_size_detail, []);

      return {
        pi_hour: String(r.pi_hour || ""),
        line_id: String(r.line_id || ""),
        model: String(r.model || ""),
        glass_type: String(r.glass_type || ""),

        maingroup_glass_count: mgGlass,
        maingroup_defect_count: dcCount,

        // 保留兩個 key，chart / table / tabs 都可讀
        maingroup_density: totalDensity,
        total_density: totalDensity,

        defect_code_glass_count: toNum(r.defect_code_glass_count),

        small_defect_count: toNum(r.small_defect_count),
        middle_defect_count: toNum(r.middle_defect_count),
        large_defect_count: toNum(r.large_defect_count),
        over_defect_count: toNum(r.over_defect_count),

        // scatter 顯示用，仍可被 filter size 投影覆蓋
        density,
        size_mask: sizeMask,
        available_sizes: availableSizes,

        glass: Array.isArray(r.glass)
          ? r.glass
          : String(r.glass || "").split(",").map(s => s.trim()).filter(Boolean),

        glass_size_detail: Array.isArray(glassSizeDetailList) ? glassSizeDetailList : [],

        tick_str: fmtPiHourToShort(r.pi_hour),
        n_glasses: mgGlass,
        defect_num: dcCount,

        comment: r.comment ?? "",
        action: r.action ?? "",
        Editor: r.Editor ?? "",
        modify_time: r.modify_time ?? ""
      };
    });

    AOI.state.rows = rows;
    AOI.state.timeRange = calcTimeRange(rows);
    AOI.state.uniques = payload.ParamDict?.filterOptionDict || {};

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

  // -------------------------
  // getFiltered
  // -------------------------
  if (typeof AOI.getFiltered !== "function") {
    AOI.getFiltered = function () {
      return AOI.state.rows || [];
    };
  }

  // -------------------------
  // Trend API
  // -------------------------
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

    console.debug(
      "[AOI_INSPECTION.fetchTrend] POST /trend payload =",
      JSON.parse(JSON.stringify(body))
    );

    try {
      const resp = await API.getInspectionTrend(body);

      const td = resp?.TrendDict || {};
      const meta = resp?.Meta || {};
      const summaryN = td?.summary?.points?.length || 0;
      const monthN = td?.month?.points?.length || 0;
      const weekN = td?.week?.points?.length || 0;
      const dayN = td?.day?.points?.length || 0;

      console.debug("[AOI_INSPECTION.fetchTrend] response meta =", meta);
      console.debug("[AOI_INSPECTION.fetchTrend] response points =", {
        summary: summaryN,
        month: monthN,
        week: weekN,
        day: dayN
      });

      if (extra?.debug_full_response) {
        console.debug("[AOI_INSPECTION.fetchTrend] response FULL =", resp);
      }

      return resp;
    } catch (e) {
      console.error("[AOI_INSPECTION.fetchTrend] trend fetch failed:", e);
      return null;
    }
  };

  // ===================== SubTabs：建立與套用 =====================

  function ensureAfterDataReady(fn) {
    if (AOI.state.paramDict) {
      fn();
      return;
    }

    const handler = () => {
      document.removeEventListener("aoi_inspection:data-ready", handler);
      fn();
    };

    document.addEventListener("aoi_inspection:data-ready", handler);
  }

  function getFilterKeys() {
    const dict = AOI.state.paramDict?.filtetItemKeyDict || {};
    return Object.keys(dict);
  }

  function selectIdOf(key) {
    return `insp-f-${key}`;
  }

  AOI.getFilterKeys = getFilterKeys;
  AOI.selectIdOf = selectIdOf;

  function readFiltersFromUI() {
    const out = {};

    getFilterKeys().forEach((k) => {
      const el = document.getElementById(selectIdOf(k));

      if (!el) {
        out[k] = [];
        return;
      }

      if (el.tagName === "SELECT" && el.multiple) {
        out[k] = Array.from(el.selectedOptions)
          .map((o) => o.value)
          .filter((v) => v !== "" && v != null);
      } else {
        out[k] = [];
      }
    });

    return out;
  }

  AOI.readFiltersFromUI = AOI.readFiltersFromUI || readFiltersFromUI;

  function applyInspectionSubTabFilters(tabKey) {
    const pd = AOI.state.paramDict || {};
    const map = pd.SubTabsFilterDefaultDict || {};
    const defs = map[tabKey];

    if (!defs) return;

    const MDD = AOI.mdd || {};

    // 若 defs 內是 { type, tab_name, filter_item_coldict }，不能直接 Object.entries(defs) 套選。
    // Hourly 目前 filter_item_coldict 是實際預設值來源。
    const filterDefs = defs.filter_item_coldict || defs;

    Object.entries(filterDefs).forEach(([k, wantList]) => {
      if (!Array.isArray(wantList) || !wantList.length) return;

      const mdd = MDD[k];
      if (!mdd) return;

      mdd.setSelected(wantList.slice());

      const selEl = document.getElementById(selectIdOf(k));
      selEl?.dispatchEvent(new Event("change", { bubbles: true }));
    });

    AOI.state.activeSubTab = tabKey;
    inspection_sub_activeTabKey = tabKey;
  }

  AOI.applySubTab = async function (tabKey) {
    const pd = AOI.state.paramDict || {};
    const defs = pd.SubTabsFilterDefaultDict?.[tabKey] || {};
    const rows = AOI.state.ProSpecDict?.[tabKey] || {};
    const type = defs.type || "";

    // 切 tab 前先保存目前 table 狀態
    const tableEntry = AOI.TableTab || null;
    if (tableEntry && typeof tableEntry.snapshotCurrentTableState === "function") {
      const snap = tableEntry.snapshotCurrentTableState();
      if (snap && snap.tabKey) {
        AOI.state.tableTabSnapshot[snap.tabKey] = snap;
      }
    }

    AOI.state.activeSubTab = tabKey;
    inspection_sub_activeTabKey = tabKey;

    AOI.hideAllSections();

    if (!type) {
      AOI.showSection("aoi-inspection-density-root");
      applyInspectionSubTabFilters(tabKey);
      return;
    }

    if (type === "csv") {
      AOI.showSection("density-csv-download-root");

      window.DENSITY_CSV_DOWNLOAD?.setSystem?.({
        system: "aoi_inspection_density",
        tabKey,
        config: defs
      });

      document.dispatchEvent(new CustomEvent("density-csv-download:show", {
        detail: {
          system: "aoi_inspection_density",
          tabKey,
          config: defs
        }
      }));

      return;
    }

    if (type === "density_avg") {
      AOI.showSection("density-avg-download-root");

      document.dispatchEvent(new CustomEvent("density-avg-download:show", {
        detail: {
          system: "aoi_inspection_density",
          tabKey,
          config: defs
        }
      }));

      return;
    }

    if (type === "table") {
      AOI.showSection("aoi-inspection-density-spec-table");

      const inited = !!AOI.state.tableTabInited[tabKey];

      if (inited) {
        document.dispatchEvent(new CustomEvent("aoi_inspection:subtab-table-restore", {
          detail: {
            tabKey,
            config: defs,
            snapshot: AOI.state.tableTabSnapshot?.[tabKey] || null
          }
        }));
        return;
      }

      AOI.state.tableTabInited[tabKey] = true;

      if (tabKey === "EditSummary") {
        const payload = {
          mode: "date",
          system: "aoi_inspection_density",
          dates: null
        };

        const resp = await API.ActionHisEditor(payload);
        if (!resp) return;

        document.dispatchEvent(new CustomEvent("aoi_inspection:subtab-table", {
          detail: {
            tabKey,
            config: defs,
            data: resp?.DictData || {}
          }
        }));

        return;
      }

      document.dispatchEvent(new CustomEvent("aoi_inspection:subtab-table", {
        detail: {
          tabKey,
          config: defs,
          data: rows
        }
      }));

      return;
    }

    if (type === "Chart") {
      AOI.showSection("aoi-inspection-density-chart-root");

      if (!AOI.state.chartInited) {
        AOI.state.chartInited = true;

        document.dispatchEvent(new CustomEvent("aoi_inspection:subtab-chart", {
          detail: {
            tabKey,
            config: defs,
            trend: null,
            filter: {},
            restoreOnly: false
          }
        }));
      } else {
        document.dispatchEvent(new CustomEvent("aoi_inspection:subtab-chart", {
          detail: {
            tabKey,
            config: defs,
            trend: null,
            filter: {},
            restoreOnly: true
          }
        }));
      }

      return;
    }

    AOI.showSection("aoi-inspection-density-root");
    applyInspectionSubTabFilters(tabKey);
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

      keys.forEach((k) => {
        const conf = map[k] || {};
        const type = conf.type || "";
        const label = conf.tab_name || k;

        const btn = document.createElement("button");
        btn.className = "sys-tab";
        btn.textContent = label;
        btn.dataset.subkey = k;

        if (type) btn.dataset.type = type;

        if (AOI.state.activeSubTab === k) {
          btn.classList.add("active");
        }

        btn.addEventListener("click", () => {
          Array.from(containerEl.querySelectorAll(".sys-tab"))
            .forEach((b) => b.classList.remove("active"));

          btn.classList.add("active");
          AOI.applySubTab(k);
        });

        containerEl.appendChild(btn);
      });

      if (!AOI.state.activeSubTab && keys.length) {
        const firstKey = keys[0];
        AOI.state.activeSubTab = firstKey;
        inspection_sub_activeTabKey = firstKey;

        const firstBtn = containerEl.querySelector(".sys-tab");
        if (firstBtn) firstBtn.classList.add("active");

        AOI.applySubTab(firstKey);
      } else if (AOI.state.activeSubTab) {
        const activeBtn = containerEl.querySelector(`[data-subkey="${AOI.state.activeSubTab}"]`);
        if (activeBtn) activeBtn.classList.add("active");
      }
    });
  };
})();