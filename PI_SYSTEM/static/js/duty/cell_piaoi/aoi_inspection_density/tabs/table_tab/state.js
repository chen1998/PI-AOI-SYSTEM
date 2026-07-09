// static/js/aoi_inspection_density/tabs/table_tab/state.js
(function () {
  const AOI = (window.AOI_INSPECTION = window.AOI_INSPECTION || {});
  const MOD = (AOI.TableTab = AOI.TableTab || {});
  const NS = (MOD.State = MOD.State || {});

  // =========================
  // 常數
  // =========================
  const EDIT_TEXT_LABELS = new Set(["Model", "OOC", "OOS"]);
  const EDIT_SELECT_LABELS = new Set(["PI Line", "Type", "Defect Size"]);
  const EDIT_FILTER_SELECT_LABELS = new Set(["PI Line", "Type", "Defect Size"]);

  // =========================
  // 小工具
  // =========================
  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  function getNowStr() {
    const d = new Date();
    const yyyy = d.getFullYear();
    const mm = pad2(d.getMonth() + 1);
    const dd = pad2(d.getDate());
    const hh = pad2(d.getHours());
    const mi = pad2(d.getMinutes());
    const ss = pad2(d.getSeconds());
    return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}`;
  }

  function formatYMD(date) {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) return "";
    const yyyy = date.getFullYear();
    const mm = pad2(date.getMonth() + 1);
    const dd = pad2(date.getDate());
    return `${yyyy}-${mm}-${dd}`;
  }

  function deepClone(v) {
    try {
      return JSON.parse(JSON.stringify(v));
    } catch (_) {
      return v;
    }
  }

  function isPlainObject(v) {
    return !!v && typeof v === "object" && !Array.isArray(v);
  }

  function normalizeRows(raw) {
    if (Array.isArray(raw)) return raw.slice();
    if (isPlainObject(raw)) return Object.values(raw);
    return [];
  }

  function specSelectIdOf(key) {
    return `aoi-inspection-density-spec--f-${key}`;
  }

  function specHostIdOf(key) {
    return `aoi-inspection-density-spec-host-${key}`;
  }

  // =========================
  // 初始 state
  // =========================
  function createInitialSpecState() {
    return {
      tabKey: null,
      config: null,

      allRows: [],
      filteredRows: [],

      // mdd: { [dataKey]: { mdd, options } }
      mdd: {},

      colKeys: [],
      colLabels: {},

      filterConfig: {},
      filterOrder: [],

      pageSize: 15,
      currentPage: 1,
      totalPages: 1,

      lastTabClass: null,

      isEditMode: false,
      isAddMode: false,
      isDeleteMode: false,

      editBtn: null,
      addBtn: null,
      deleteBtn: null,

      editSummaryCancelBtn: null,
      editSummaryBackupRows: null,

      buttonsBound: {
        spec: false,
        header: false
      },

      // 新增：每個 table 子分頁的狀態快照
      tableTabCache: {}
    };
  }

  const SpecState = createInitialSpecState();

  function resetModeState() {
    SpecState.isEditMode = false;
    SpecState.isAddMode = false;
    SpecState.isDeleteMode = false;
    SpecState.editSummaryCancelBtn = null;
    SpecState.editSummaryBackupRows = null;
  }

  function resetTransientDomRefs() {
    SpecState.editBtn = null;
    SpecState.addBtn = null;
    SpecState.deleteBtn = null;
  }

  function resetSpecStateForTab(tabKey, config, rows) {
    const nextRows = normalizeRows(rows);
    const nextConfig = config || {};
    const nextFilterConfig = (nextConfig && nextConfig.filter_item_coldict) || {};

    const keepPageSize = SpecState.pageSize || 15;
    const keepCache = SpecState.tableTabCache || {};

    Object.assign(SpecState, createInitialSpecState(), {
      tabKey: tabKey || null,
      config: nextConfig,
      allRows: nextRows,
      filteredRows: nextRows.slice(),
      filterConfig: nextFilterConfig,
      filterOrder: Object.keys(nextFilterConfig || {}),
      pageSize: keepPageSize,
      tableTabCache: keepCache
    });
  }

  function setRows(rows) {
    const nextRows = normalizeRows(rows);
    SpecState.allRows = nextRows;
    SpecState.filteredRows = nextRows.slice();
    SpecState.currentPage = 1;
    SpecState.totalPages = 1;
  }

  function replaceAllRows(rows) {
    setRows(rows);
  }

  function setFilteredRows(rows) {
    SpecState.filteredRows = Array.isArray(rows) ? rows.slice() : [];
    if (!SpecState.currentPage || SpecState.currentPage < 1) {
      SpecState.currentPage = 1;
    }
  }

  function setTabConfig(config) {
    SpecState.config = config || {};
    SpecState.filterConfig = (SpecState.config && SpecState.config.filter_item_coldict) || {};
    SpecState.filterOrder = Object.keys(SpecState.filterConfig || {});
  }

  function getEditorName() {
    return window.USER || "預設";
  }

  function getTabName() {
    return (SpecState.config && SpecState.config.tab_name) || SpecState.tabKey || "";
  }

  // =========================
  // table tab cache
  // =========================
  function setTableTabSnapshot(tabKey, snapshot) {
    if (!tabKey) return;
    if (!SpecState.tableTabCache) SpecState.tableTabCache = {};
    SpecState.tableTabCache[tabKey] = snapshot || null;
  }

  function getTableTabSnapshot(tabKey) {
    if (!tabKey) return null;
    return SpecState.tableTabCache?.[tabKey] || null;
  }

  // =========================
  // export
  // =========================
  NS.EDIT_TEXT_LABELS = EDIT_TEXT_LABELS;
  NS.EDIT_SELECT_LABELS = EDIT_SELECT_LABELS;
  NS.EDIT_FILTER_SELECT_LABELS = EDIT_FILTER_SELECT_LABELS;

  NS.SpecState = SpecState;

  NS.pad2 = pad2;
  NS.getNowStr = getNowStr;
  NS.formatYMD = formatYMD;
  NS.deepClone = deepClone;
  NS.isPlainObject = isPlainObject;
  NS.normalizeRows = normalizeRows;

  NS.specSelectIdOf = specSelectIdOf;
  NS.specHostIdOf = specHostIdOf;

  NS.createInitialSpecState = createInitialSpecState;
  NS.resetModeState = resetModeState;
  NS.resetTransientDomRefs = resetTransientDomRefs;
  NS.resetSpecStateForTab = resetSpecStateForTab;

  NS.setRows = setRows;
  NS.replaceAllRows = replaceAllRows;
  NS.setFilteredRows = setFilteredRows;
  NS.setTabConfig = setTabConfig;

  NS.getEditorName = getEditorName;
  NS.getTabName = getTabName;

  NS.setTableTabSnapshot = setTableTabSnapshot;
  NS.getTableTabSnapshot = getTableTabSnapshot;
})();