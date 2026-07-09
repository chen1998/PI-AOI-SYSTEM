// static/js/duty/cell_aoi_to_array/cell_aoi_to_array_state.js
(function () {
  "use strict";

  window.CELL_AOI_TO_ARRAY = window.CELL_AOI_TO_ARRAY || {};
  const MOD = window.CELL_AOI_TO_ARRAY;

  const root = document.getElementById("cell-aoi-to-array");

  const dom = {
    root,

    activeBadge: document.getElementById("cell-aoi-to-array-active-badge"),

    categoryTabs: document.getElementById("cell-aoi-to-array-category-tabs"),
    featureTabs: document.getElementById("cell-aoi-to-array-feature-tabs"),

    compareSection: document.getElementById("cell-aoi-to-array-compare-section"),
    emptySection: document.getElementById("cell-aoi-to-array-empty-section"),
    emptyText: document.getElementById("cell-aoi-to-array-empty-text"),

    infoLeft: document.getElementById("cell-aoi-to-array-info-left"),
    infoRight: document.getElementById("cell-aoi-to-array-info-right"),

    startDate: document.getElementById("cell-aoi-to-array-start-date"),
    endDate: document.getElementById("cell-aoi-to-array-end-date"),
    toolSelect: document.getElementById("cell-aoi-to-array-tool-select"),
    sheetRadios: document.getElementById("cell-aoi-to-array-sheet-type-radios"),
    sheetInput: document.getElementById("cell-aoi-to-array-sheet-input"),

    sheetCsvInput: document.getElementById("cell-aoi-to-array-sheet-csv-input"),
    sheetCsvBtn: document.getElementById("cell-aoi-to-array-sheet-csv-btn"),
    sheetCsvSampleBtn: document.querySelector("#cell-aoi-to-array-sheet-csv-sample-btn"),
    sheetCsvClearBtn: document.getElementById("cell-aoi-to-array-sheet-csv-clear-btn"),
    sheetCsvInfo: document.getElementById("cell-aoi-to-array-sheet-csv-info"),

    applyBtn: document.getElementById("cell-aoi-to-array-apply-btn"),

    summaryCards: document.getElementById("cell-aoi-to-array-summary-cards"),

    chartTitle: document.getElementById("cell-aoi-to-array-chart-title"),
    chartSubtitle: document.getElementById("cell-aoi-to-array-chart-subtitle"),
    chartGrid: document.getElementById("cell-aoi-to-array-chart-grid"),

    returnBtn: document.getElementById("cell-aoi-to-array-return-btn"),
    tableMode: document.getElementById("cell-aoi-to-array-table-mode"),
    tableHead: document.querySelector("#cell-aoi-to-array-table thead"),
    tableBody: document.querySelector("#cell-aoi-to-array-table tbody"),
    totalCount: document.getElementById("cell-aoi-to-array-total-count"),
    pager: document.getElementById("cell-aoi-to-array-pager"),

    sheetDesc: document.getElementById("cell-aoi-to-array-sheet-desc"),
    sheetDetail: document.getElementById("cell-aoi-to-array-sheet-detail"),

    defectListWrap: document.getElementById("cell-aoi-to-array-defect-list-wrap"),
    defectListCount: document.getElementById("cell-aoi-to-array-defect-list-count"),
    defectTableHead: document.querySelector("#cell-aoi-to-array-defect-table thead"),
    defectTableBody: document.querySelector("#cell-aoi-to-array-defect-table tbody")
  };

  const state = {
    category: "",
    feature: "",

    filters: {
      startDate: "",
      endDate: "",
    
      // tool 現在對應 api_aoi_summary.line_id
      tool: "",
      lineId: "",
    
      sheetType: "",
      sheetId: "",
    
      // CSV 多片 sheet 查詢
      sheetIds: [],
      sheetCsvFileName: "",
    
      aoi: "",
      piType: "",
      sourceOpId: "",
      matchStatus: "",
      modelNo: "",
      recipeId: ""
    },

    summary: {},
    rows: [],
    tableRows: [],
    selectedRow: null,
    currentSheetDefects: [],

    tableMode: "all",
    page: 1,
    pageSize: 10,

    charts: {},

    mapFilters: {
      // 預設只顯示同點星號
      groups: new Set(["same_point"]),

      // defect size 預設全開
      sizes: new Set(["S", "M", "L", "O"]),

      // lazy load 狀態
      fullGroupsLoaded: false,
      fullGroupsLoading: false
    }
  };

  let CONFIG = MOD.CONFIG || {};

  MOD.State = {
    dom,
    state,

    getConfig,
    setConfig,
    loadConfig,
    resetStateByConfig,
    applyResult,

    getFeatureConfig,
    getCurrentFeature,
    getTableColumns,
    getSheetDetailFields,
    getSheetSideConfig,
    getSheetDetailFieldsByRow,
    getDefectTableColumnsByRow,
    getChartList,
    getToolOptions,
    getAxisConfig,
    getRowKey,

    ensureRowDefectContainers,
    resetMapFilters
  };

  function getConfig() {
    return CONFIG || {};
  }

  function setConfig(nextConfig) {
    CONFIG = Object.assign({}, CONFIG || {}, nextConfig || {});
    MOD.CONFIG = CONFIG;
  }

  async function loadConfig() {
    if (!MOD.API || !MOD.API.fetchConfig) {
      resetStateByConfig();
      return CONFIG;
    }

    try {
      const backendConfig = await MOD.API.fetchConfig();
      setConfig(backendConfig);
    } catch (err) {
      console.error("[cell-aoi-to-array] fetchConfig failed, fallback local config:", err);
      setConfig(MOD.CONFIG || {});
    }

    resetStateByConfig();
    return CONFIG;
  }

  function resetStateByConfig() {
    const cfg = getConfig();

    const defaultCategory = cfg.defaultCategory || "PI";
    const defaultFeature =
      (cfg.defaultFeatureByCategory && cfg.defaultFeatureByCategory[defaultCategory]) ||
      "";

    const defaultFilters = cfg.defaultFilters || {};

    state.category = defaultCategory;
    state.feature = defaultFeature;

    state.filters = {
      startDate: defaultFilters.startDate || "",
      endDate: defaultFilters.endDate || "",

      tool: defaultFilters.tool || "",
      lineId: defaultFilters.lineId || "",

      sheetType: defaultFilters.sheetType || "",
      sheetId: defaultFilters.sheetId || "",

      // CSV 多片 sheet 查詢
      sheetIds: Array.isArray(defaultFilters.sheetIds)
      ? defaultFilters.sheetIds
      : [],
      sheetCsvFileName: defaultFilters.sheetCsvFileName || "",

      aoi: defaultFilters.aoi || "",
      piType: defaultFilters.piType || "",
      sourceOpId: defaultFilters.sourceOpId || "",
      matchStatus: defaultFilters.matchStatus || "",
      modelNo: defaultFilters.modelNo || "",
      recipeId: defaultFilters.recipeId || ""
    };

    state.pageSize = cfg.pageSize || 10;
    state.summary = {};
    state.rows = [];
    state.tableRows = [];
    state.selectedRow = null;
    state.currentSheetDefects = [];
    state.tableMode = "all";
    state.page = 1;

    resetMapFilters();
  }

  function applyResult(result) {
    if (result && result.uiConfig) {
      CONFIG.featureConfigByFeature = CONFIG.featureConfigByFeature || {};
      CONFIG.featureConfigByFeature[state.feature] = Object.assign(
        {},
        CONFIG.featureConfigByFeature[state.feature] || {},
        result.uiConfig
      );
      MOD.CONFIG = CONFIG;
    }

    state.summary = result?.summary || {};
    state.rows = Array.isArray(result?.rows) ? result.rows : [];

    state.rows.forEach(function (row) {
      ensureRowDefectContainers(row);
    });

    state.tableRows = state.rows.slice();
    state.selectedRow = null;
    state.currentSheetDefects = [];
    state.tableMode = "all";
    state.page = 1;

    resetMapFilters();
  }

  function getFeatureConfig(featureKey) {
    const key = featureKey || state.feature;
    const cfg = getConfig();
    const map = cfg.featureConfigByFeature || {};
    return map[key] || {};
  }

  function getCurrentFeature() {
    const cfg = getConfig();
    const features = cfg.featureTabsByCategory?.[state.category] || [];
    return features.find(item => item.key === state.feature) || getFeatureConfig(state.feature);
  }

  function getTableColumns() {
    const cfg = getConfig();
    return getFeatureConfig().tableColumns || cfg.tableColumns || [];
  }

  function getSheetDetailFields() {
    return getFeatureConfig().sheetDetailFields || getTableColumns().filter(col => col.key);
  }

  function getChartList() {
    const cfg = getConfig();
    return getFeatureConfig().chartList || cfg.chartListByFeature?.[state.feature] || [];
  }

  function getToolOptions() {
    const cfg = getConfig();
    const featureCfg = getFeatureConfig();

    return (
      featureCfg.toolOptions ||
      cfg.lineOptions ||
      cfg.toolOptions ||
      defaultLineOptions()
    );
  }

  function defaultLineOptions() {
    const out = [];
    for (let i = 1; i <= 7; i += 1) {
      out.push(`CAPIC${i}`);
    }
    return out;
  }

  function getAxisConfig() {
    return getFeatureConfig().axis || {
      min_x: 0,
      max_x: 1850000,
      min_y: 0,
      max_y: 1500000
    };
  }

  function getSheetSideConfig(row) {
    const cfg = getFeatureConfig();
    const side = String(row?.glass_side || row?.abbr_cat || "").toUpperCase();

    return (
      cfg.sheetSideConfig?.[side] ||
      cfg.sheetSideConfig?.TFT ||
      {
        compareTargetLabel: "Source",
        compareTargetCountLabel: "Source點數",
        mapTargetLegendLabel: "Source",
        compareTitleTemplate: "照片比對 (CELL {system_label} Vs. Source)",
        compareLineTemplate: "CELL {system_label} 共 {cell_count} 點，比對 Source 同點 {match_count} 點",
        noticeIcon: "提示",
        noticeText: "點擊 map 點位可只顯示該 defect，按 RETURN 回復全部。"
      }
    );
  }

  function getSheetDetailFieldsByRow(row) {
    const cfg = getFeatureConfig();
    const side = String(row?.glass_side || row?.abbr_cat || "").toUpperCase();

    return (
      cfg.sheetDetailFieldsBySide?.[side] ||
      cfg.sheetDetailFields ||
      getTableColumns().filter(col => col.key)
    );
  }

  function getDefectTableColumnsByRow(row) {
    const cfg = getFeatureConfig();
    const side = String(row?.glass_side || row?.abbr_cat || "").toUpperCase();

    return (
      cfg.defectTableColumnsBySide?.[side] ||
      [
        { type: "text", key: "index", label: "索引" },
        { type: "match", key: "match", label: "Match" },
        { type: "image", key: "cell_img", label: "CELL AOI" },
        { type: "image", key: "source_img", label: "Source" },
        { type: "text", key: "cell_defect_code", label: "CELL Code" },
        { type: "text", key: "source_defect_code", label: "Source Code" },
        { type: "text", key: "cell_defect_size", label: "CELL Size" },
        { type: "text", key: "source_defect_size", label: "Source Size" },
        { type: "text", key: "distance", label: "Distance" },
        { type: "text", key: "dx", label: "dx" },
        { type: "text", key: "dy", label: "dy" }
      ]
    );
  }

  function getRowKey(row) {
    if (!row) return "";

    return [
      row.sheet_id_chip_id || row.sheet_id || "",
      row.test_time || row.scan_time || "",
      row.pi_type || "",
      row.source_op_id || ""
    ].join("|");
  }

  function ensureRowDefectContainers(row) {
    if (!row) return row;

    if (!Array.isArray(row.defects)) {
      row.defects = [];
    }

    if (!row.defectGroups || typeof row.defectGroups !== "object") {
      row.defectGroups = {};
    }

    if (!Array.isArray(row.defectGroups.same_point)) {
      row.defectGroups.same_point = [];
    }

    if (!Array.isArray(row.defectGroups.cell_aoi)) {
      row.defectGroups.cell_aoi = [];
    }

    if (!Array.isArray(row.defectGroups.source)) {
      row.defectGroups.source = [];
    }

    if (!row.groupsLoaded || typeof row.groupsLoaded !== "object") {
      row.groupsLoaded = {};
    }

    row.groupsLoaded.same_point = Boolean(row.groupsLoaded.same_point);
    row.groupsLoaded.cell_aoi = Boolean(row.groupsLoaded.cell_aoi);
    row.groupsLoaded.source = Boolean(row.groupsLoaded.source);

    return row;
  }

  function resetMapFilters() {
    state.mapFilters = {
      groups: new Set(["same_point"]),
      sizes: new Set(["S", "M", "L", "O"]),
      fullGroupsLoaded: false,
      fullGroupsLoading: false
    };
  }
})();
