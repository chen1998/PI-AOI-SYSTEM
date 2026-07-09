// static/js/bpi_area/common/tabs/table_tab.js
// BPI Area Common Table Tab
//
// 支援：
// - bpi_density_default_spec
// - bpi_density_action_history
// - bpi_same_point_default_spec
// - bpi_same_point_action_history
//
// 監聽事件：
// - bpi-area:table-tab-show
//
// 後端 API：
// - /common/spec_editor       via AOI_BPI_DENSITY_API.FrontSpecEditor
// - /common/editor_summary    via AOI_BPI_DENSITY_API.ActionHisEditor

(function () {
    const AREA = (window.BPI_AREA = window.BPI_AREA || {});
    const BPI = (window.AOI_BPI_DENSITY = window.AOI_BPI_DENSITY || {});
    const API = window.AOI_BPI_DENSITY_API;
  
    const $ = (sel, root = document) => root.querySelector(sel);
  
    const editor = window.USER || window.editor || "預設";
  
    const DOM = {
      root: "bpi-area-table-tab-root",
      title: "bpi-area-table-tab-title",
      headerActions: "bpi-area-table-tab-header-actions",
      charTabs: "bpi-area-table-tab-char-tabs",
      table: "bpi-area-table-tab-main",
      pager: "bpi-area-table-tab-pager",
      addPanel: "bpi-area-table-tab-add-panel",
      filterCount: "bpi-area-table-tab-filter-count",
      start: "bpi-area-table-tab-start",
      end: "bpi-area-table-tab-end",
      apply: "bpi-area-table-tab-apply",
      clear: "bpi-area-table-tab-clear",
      filterHost: "bpi-area-table-tab-dynhosts",
      bottomActions: "bpi-area-table-tab-bottom-actions",
      dateBlockClass: "bpi-area-table-tab-filter-item",
    };
  
    const TableTab = {
      kind: "table",
      system: "bpi_density",
      tabGroup: "",
      tabKey: null,
      config: null,
  
      allRows: [],
      filteredRows: [],
  
      mdd: {},
      colKeys: [],
      colLabels: {},
      filterConfig: {},
      filterOrder: [],
  
      pageSize: 200,
      currentPage: 1,
      totalPages: 1,
  
      isEditMode: false,
      isAddMode: false,
      isDeleteMode: false,
  
      editBtn: null,
      addBtn: null,
      deleteBtn: null,
      cancelBtn: null,
  
      lastTabClass: null,
      initialized: false,
    };
  
    // ============================================================
    // constants
    // ============================================================
    const LONG_TEXT_FIELDS = new Set(["comment", "action"]);
  
    const ACTION_EDITABLE_FIELDS = new Set(["comment", "action"]);
  
    const DEFAULT_SPEC_EDIT_TEXT_FIELDS = new Set([
      "model",
      "OOC",
      "OOS",
    ]);
  
    const DEFAULT_SPEC_EDIT_SELECT_FIELDS = new Set([
      "glass_type",
      "glass_side",
      "defect_size",
    ]);
  
    const DEFAULT_SPEC_RESERVED_FIELDS = new Set([
      "Editor",
      "editor",
      "modify_time",
      "drop",
    ]);
  
    // ============================================================
    // basic helpers
    // ============================================================
    function byId(id) {
      return document.getElementById(id);
    }
  
    function safeStr(v) {
      return v == null ? "" : String(v);
    }
  
    function cleanStr(v) {
      return v == null ? "" : String(v).trim();
    }
  
    function pad2(n) {
      return String(n).padStart(2, "0");
    }
  
    function getNowStr() {
      const d = new Date();
      return (
        `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ` +
        `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`
      );
    }
  
    function fmtDateYYYYMMDD(d) {
      return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
    }
  
    function default3DaysRange() {
      const end = new Date();
      const start = new Date(end.getTime() - 3 * 24 * 3600 * 1000);
      return [fmtDateYYYYMMDD(start), fmtDateYYYYMMDD(end)];
    }
  
    function resolveRowsFromAny(raw) {
      if (!raw) return [];
      if (Array.isArray(raw)) return raw;
      if (raw && typeof raw === "object") return Object.values(raw);
      return [];
    }
  
    function normalizeRows(rawRows) {
      const rows = resolveRowsFromAny(rawRows);
  
      return rows.map(r => {
        const o = { ...(r || {}) };
  
        if (o.editor == null && o.Editor != null) o.editor = o.Editor;
        if (o.Editor == null && o.editor != null) o.Editor = o.editor;
        if (o.modify_time == null) o.modify_time = "";
  
        return o;
      });
    }
  
    function normalizeRespRows(resp) {
      if (!resp) return [];
      if (Array.isArray(resp)) return normalizeRows(resp);
      if (resp.DictData !== undefined) return normalizeRows(resp.DictData);
      if (resp.data !== undefined) return normalizeRows(resp.data);
      if (resp.rows !== undefined) return normalizeRows(resp.rows);
      return [];
    }
  
    function formatCellValue(v) {
      if (v == null) return "";
  
      const s = String(v).trim();
      if (!s) return "";
  
      const n = Number(s.replace(/,/g, ""));
      if (!Number.isNaN(n) && Number.isFinite(n) && /^-?\d+(\.\d+)?$/.test(s.replace(/,/g, ""))) {
        const fixed = n.toFixed(2);
        if (fixed.endsWith(".00")) return String(Math.round(n));
        return fixed;
      }
  
      return s;
    }
  
    function getMultiDDCtor() {
      return (
        BPI.MultiDD ||
        window.AOI_DENSITY?.MultiDD ||
        window.MultiDD ||
        null
      );
    }
  
    function isDefaultSpec() {
      return TableTab.kind === "default_spec";
    }
  
    function isActionHistory() {
      return TableTab.kind === "action_history";
    }
  
    function getCacheKey() {
      return `${TableTab.system}::${TableTab.tabKey}::${TableTab.kind}`;
    }
  
    function getCacheRoot() {
      AREA.state = AREA.state || {};
      AREA.state.tableTabCache = AREA.state.tableTabCache || {};
      return AREA.state.tableTabCache;
    }
  
    function tableSelectIdOf(key) {
      return `bpi-area-table-tab-f-${TableTab.system}-${TableTab.tabKey}-${key}`.replace(/[^A-Za-z0-9_-]/g, "_");
    }
  
    function tableHostIdOf(key) {
      return `bpi-area-table-tab-host-${TableTab.system}-${TableTab.tabKey}-${key}`.replace(/[^A-Za-z0-9_-]/g, "_");
    }
  
    // ============================================================
    // DOM helpers
    // ============================================================
    function ensureThead(table) {
      let thead = table.querySelector("thead");
      if (!thead) {
        thead = document.createElement("thead");
        table.appendChild(thead);
      }
      return thead;
    }
  
    function ensureTbody(table) {
      let tbody = table.querySelector("tbody");
      if (!tbody) {
        tbody = document.createElement("tbody");
        table.appendChild(tbody);
      }
      return tbody;
    }
  
    function ensureBottomClearButton() {
      const box = byId(DOM.bottomActions);
      if (!box) return null;
  
      let btn = box.querySelector("#bpi-area-table-tab-clear-bottom");
      if (!btn) {
        btn = document.createElement("button");
        btn.id = "bpi-area-table-tab-clear-bottom";
        btn.type = "button";
        btn.className = "btn btn-xs btn-secondary";
        btn.textContent = "清空篩選";
        box.appendChild(btn);
      }
  
      return btn;
    }
  
    function clearDomForNewTab() {
      const actions = byId(DOM.headerActions);
      if (actions) actions.innerHTML = "";
  
      const charTabs = byId(DOM.charTabs);
      if (charTabs) charTabs.innerHTML = "";
  
      const addPanel = byId(DOM.addPanel);
      if (addPanel) {
        addPanel.innerHTML = "";
        addPanel.style.display = "none";
      }
  
      const table = byId(DOM.table);
      if (table) {
        const thead = ensureThead(table);
        const tbody = ensureTbody(table);
        thead.innerHTML = "";
        tbody.innerHTML = "";
  
        if (TableTab.lastTabClass) {
          table.classList.remove(TableTab.lastTabClass);
          TableTab.lastTabClass = null;
        }
      }
  
      const pager = byId(DOM.pager);
      if (pager) pager.innerHTML = "";
  
      const host = byId(DOM.filterHost);
      if (host) host.innerHTML = "";
  
      const count = byId(DOM.filterCount);
      if (count) count.textContent = "";
    }
  
    function setDateBlockVisible(flag) {
      const root = byId(DOM.root);
      if (!root) return;
  
      const block = root.querySelector(`.${DOM.dateBlockClass}`);
      if (block) block.style.display = flag ? "" : "none";
    }
  
    function setDateInputsDefault() {
      const s = byId(DOM.start);
      const e = byId(DOM.end);
      if (!s || !e) return;
  
      if (!s.value || !e.value) {
        const [ds, de] = default3DaysRange();
        s.value = ds;
        e.value = de;
      }
    }
  
    function readDates() {
      const s = byId(DOM.start)?.value || "";
      const e = byId(DOM.end)?.value || "";
      return s && e ? [s, e] : null;
    }
  
    function setHeaderTitle() {
      const h2 = byId(DOM.title);
      if (!h2) return;
  
      h2.textContent =
        TableTab.config?.tab_name ||
        TableTab.tabKey ||
        "";
    }
  
    // ============================================================
    // cache
    // ============================================================
    function collectSelections() {
      const out = {};
      Object.entries(TableTab.mdd || {}).forEach(([dataKey, wrap]) => {
        const selected = wrap?.mdd?.getSelected?.() || [];
        out[dataKey] = new Set((selected || []).map(String));
      });
      return out;
    }
  
    function cloneSelections(src) {
      const out = {};
      Object.entries(src || {}).forEach(([k, v]) => {
        out[k] = new Set(Array.from(v || []).map(String));
      });
      return out;
    }
  
    function saveCurrentStateToCache() {
      if (!TableTab.tabKey) return;
  
      const cacheRoot = getCacheRoot();
  
      cacheRoot[getCacheKey()] = {
        kind: TableTab.kind,
        system: TableTab.system,
        tabGroup: TableTab.tabGroup,
        tabKey: TableTab.tabKey,
        config: TableTab.config,
  
        allRows: Array.isArray(TableTab.allRows) ? TableTab.allRows.slice() : [],
        filteredRows: Array.isArray(TableTab.filteredRows) ? TableTab.filteredRows.slice() : [],
  
        colKeys: Array.isArray(TableTab.colKeys) ? TableTab.colKeys.slice() : [],
        colLabels: { ...(TableTab.colLabels || {}) },
        filterConfig: TableTab.filterConfig || {},
        filterOrder: Array.isArray(TableTab.filterOrder) ? TableTab.filterOrder.slice() : [],
  
        pageSize: TableTab.pageSize || 200,
        currentPage: TableTab.currentPage || 1,
        totalPages: TableTab.totalPages || 1,
  
        isEditMode: !!TableTab.isEditMode,
        isAddMode: !!TableTab.isAddMode,
        isDeleteMode: !!TableTab.isDeleteMode,
  
        dates: readDates(),
        selections: cloneSelections(collectSelections()),
      };
    }
  
    function restoreStateFromCache(kind, system, tabKey) {
      const cacheRoot = getCacheRoot();
      const key = `${system}::${tabKey}::${kind}`;
      const cache = cacheRoot[key];
  
      if (!cache) return false;
  
      TableTab.kind = cache.kind || kind;
      TableTab.system = cache.system || system;
      TableTab.tabGroup = cache.tabGroup || "";
      TableTab.tabKey = cache.tabKey || tabKey;
      TableTab.config = cache.config || {};
  
      TableTab.allRows = Array.isArray(cache.allRows) ? cache.allRows.slice() : [];
      TableTab.filteredRows = Array.isArray(cache.filteredRows) ? cache.filteredRows.slice() : [];
  
      TableTab.colKeys = Array.isArray(cache.colKeys) ? cache.colKeys.slice() : [];
      TableTab.colLabels = { ...(cache.colLabels || {}) };
      TableTab.filterConfig = cache.filterConfig || {};
      TableTab.filterOrder = Array.isArray(cache.filterOrder) ? cache.filterOrder.slice() : [];
  
      TableTab.pageSize = cache.pageSize || 200;
      TableTab.currentPage = cache.currentPage || 1;
      TableTab.totalPages = cache.totalPages || 1;
  
      TableTab.isEditMode = !!cache.isEditMode;
      TableTab.isAddMode = !!cache.isAddMode;
      TableTab.isDeleteMode = !!cache.isDeleteMode;
  
      const s = byId(DOM.start);
      const e = byId(DOM.end);
      if (s && cache.dates?.[0]) s.value = cache.dates[0];
      if (e && cache.dates?.[1]) e.value = cache.dates[1];
  
      setupHeader();
      renderHeader();
      buildFilters(cache.selections || null);
      applyLocalFilter({ skipSave: true });
      syncHeaderButtonState();
  
      saveCurrentStateToCache();
  
      return true;
    }
  
    // ============================================================
    // columns
    // ============================================================
    function buildColConfig(config, rows) {
      const tc = config?.table_columns;
      const sample = Array.isArray(rows) && rows.length ? rows[0] : {};
      const colKeys = [];
      const colLabels = {};
    
      if (Array.isArray(tc)) {
        tc.forEach((dataKey) => {
          if (!dataKey) return;
          colKeys.push(dataKey);
          colLabels[dataKey] = dataKey;
        });
      } else if (tc && typeof tc === "object") {
        Object.entries(tc).forEach(([k, v]) => {
          let dataKey;
          let header;
    
          if (isDefaultSpec()) {
            // default spec config 採用：
            //   display label -> real data key
            // 例如：
            //   MODEL_ID -> model
            //   GLASS_TYPE -> glass_side
            //   SIZE_TYPE -> defect_size
            header = k;
            dataKey = typeof v === "string" && v ? v : k;
          } else {
            const sampleHasK = sample && Object.prototype.hasOwnProperty.call(sample, k);
            const sampleHasV =
              sample &&
              typeof v === "string" &&
              Object.prototype.hasOwnProperty.call(sample, v);
    
            if (sampleHasV && !sampleHasK) {
              header = k;
              dataKey = v;
            } else {
              dataKey = k;
              header = (typeof v === "string" && v) ? v : k;
            }
          }
    
          if (!dataKey) return;
          colKeys.push(dataKey);
          colLabels[dataKey] = header;
        });
      } else {
        Object.keys(sample || {}).forEach((k) => {
          colKeys.push(k);
          colLabels[k] = k;
        });
      }
    
      TableTab.colKeys = colKeys;
      TableTab.colLabels = colLabels;
    }
    
  
    // ============================================================
    // filter
    // ============================================================
    function findFilterLabelByKey(dataKey) {
      const cfg = TableTab.filterConfig || {};
      for (const [label, conf] of Object.entries(cfg)) {
        if ((conf?.key || label) === dataKey) return label;
      }
      return dataKey;
    }
  
    function getOptionsForDataKey(dataKey) {
      const cfg = TableTab.filterConfig || {};
  
      for (const [label, conf] of Object.entries(cfg)) {
        const k = conf?.key || label;
        if (k !== dataKey) continue;
        if (Array.isArray(conf?.values) && conf.values.length) {
          return conf.values.slice().map(String);
        }
      }
  
      const set = new Set();
      (TableTab.allRows || []).forEach(r => {
        const v = r?.[dataKey];
        if (v == null || v === "") return;
        set.add(String(v));
      });
  
      return Array.from(set).sort();
    }
  
    function getFilterLabels() {
      const cfg = TableTab.filterConfig || {};
      const labels = [];
  
      Object.entries(cfg).forEach(([label, conf]) => {
        if (!conf || typeof conf !== "object") return;
  
        if (conf.hidden === true || conf.visible === false || conf.display === false) return;
  
        const key = conf.key || label;
        if (!key || key === "date" || key === "offset_um") return;
  
        labels.push(label);
      });
  
      if (TableTab.filterOrder && TableTab.filterOrder.length) {
        const orderKeys = TableTab.filterOrder.slice();
        labels.sort((a, b) => {
          const ak = cfg[a]?.key || a;
          const bk = cfg[b]?.key || b;
          const ai = orderKeys.indexOf(ak);
          const bi = orderKeys.indexOf(bk);
          if (ai === -1 && bi === -1) return a.localeCompare(b);
          if (ai === -1) return 1;
          if (bi === -1) return -1;
          return ai - bi;
        });
      }
  
      return labels;
    }
  
    function wireSearchForHost(hostEl) {
      if (!hostEl) return;
  
      const ddRoot = hostEl.querySelector(".multi-dd");
      if (!ddRoot) return;
  
      const input = ddRoot.querySelector(".multi-dd-search");
      if (!input) return;
  
      input.addEventListener("input", () => {
        const q = input.value.trim().toLowerCase();
        const items = Array.from(ddRoot.querySelectorAll(".multi-dd-item"));
  
        items.forEach((item) => {
          const text = item.textContent.toLowerCase();
          item.style.display = (!q || text.includes(q)) ? "" : "none";
        });
      });
    }
  
    function buildFilters(prevSelections) {
      const host = byId(DOM.filterHost);
      if (!host) return;
  
      host.innerHTML = "";
      TableTab.mdd = {};
  
      const MultiDD = getMultiDDCtor();
      if (!MultiDD) {
        host.innerHTML = "<div class='muted'>MultiDD 未載入</div>";
        return;
      }
  
      const labels = getFilterLabels();
  
      labels.forEach(label => {
        const conf = TableTab.filterConfig[label] || {};
        const dataKey = conf.key || label;
  
        let opts = [];
  
        if (Array.isArray(conf.values) && conf.values.length) {
          const rowSet = new Set();
          (TableTab.allRows || []).forEach(r => {
            const v = r?.[dataKey];
            if (v == null || v === "") return;
            rowSet.add(String(v));
          });
  
          const fixed = conf.values.slice().map(String);
          const inter = fixed.filter(v => rowSet.has(String(v)));
          opts = inter.length ? inter : fixed;
        } else {
          opts = getOptionsForDataKey(dataKey);
        }
  
        if (!opts.length) return;
  
        const div = document.createElement("div");
        div.className = "multi-dd-host";
        div.id = tableHostIdOf(dataKey);
        host.appendChild(div);
  
        const mdd = new MultiDD({
          hostId: div.id,
          selectId: tableSelectIdOf(dataKey),
          options: opts,
          title: label,
          onChange: () => {
            TableTab.currentPage = 1;
            applyLocalFilter();
          }
        });
  
        const prevSet = prevSelections?.[dataKey];
        let selected = opts.slice();
  
        if (prevSet && prevSet.size) {
          const keep = opts.filter(o => prevSet.has(String(o)));
          selected = keep.length ? keep : opts.slice();
        }
  
        mdd.setSelected?.(selected);
  
        TableTab.mdd[dataKey] = {
          mdd,
          options: opts,
          config: conf,
        };
  
        wireSearchForHost(div);
      });
    }
  
    function getActiveFilters() {
      const out = {};
  
      Object.entries(TableTab.mdd || {}).forEach(([dataKey, wrap]) => {
        const sel = wrap?.mdd?.getSelected?.() || [];
        const options = wrap?.options || [];
  
        if (!sel.length) {
          out[dataKey] = new Set();
          return;
        }
  
        const isAll =
          options.length &&
          sel.length === options.length &&
          sel.every(v => options.includes(v));
  
        if (isAll) return;
  
        out[dataKey] = new Set(sel.map(String));
      });
  
      return out;
    }
  
    function updateFilterCount() {
      const span = byId(DOM.filterCount);
      if (!span) return;
  
      span.textContent = `( ${TableTab.filteredRows.length || 0} 筆 )`;
    }
  
    function applyLocalFilter(opts) {
      opts = opts || {};
  
      const filters = getActiveFilters();
      const rows = TableTab.allRows || [];
      const keys = Object.keys(filters);
  
      if (!keys.length) {
        TableTab.filteredRows = rows.slice();
      } else {
        TableTab.filteredRows = rows.filter(r => {
          if (!r) return false;
  
          for (const k of keys) {
            const set = filters[k];
  
            // 空選代表該 filter 無符合資料
            if (!set || set.size === 0) return false;
  
            const v = r[k] != null ? String(r[k]) : "";
            if (!set.has(v)) return false;
          }
  
          return true;
        });
      }
  
      updatePagination();
      renderBody();
      renderPager();
      updateFilterCount();
  
      if (!opts.skipSave) saveCurrentStateToCache();
    }
  
    function clearAllLocalFilters() {
      const s = byId(DOM.start);
      const e = byId(DOM.end);
  
      if (s) s.value = "";
      if (e) e.value = "";
  
      buildFilters(null);
      TableTab.currentPage = 1;
      applyLocalFilter();
    }
  
    // ============================================================
    // pagination
    // ============================================================
    function updatePagination() {
      const total = TableTab.filteredRows.length || 0;
      const size = TableTab.pageSize || 200;
  
      TableTab.totalPages = total ? Math.ceil(total / size) : 1;
  
      if (!TableTab.currentPage || TableTab.currentPage > TableTab.totalPages) {
        TableTab.currentPage = 1;
      }
    }
  
    function renderPager() {
      const pager = byId(DOM.pager);
      if (!pager) return;
  
      const total = TableTab.filteredRows.length || 0;
      const pages = TableTab.totalPages || 1;
  
      pager.innerHTML = "";
      pager.style.display = "flex";
  
      const info = document.createElement("div");
      info.className = "bpi-area-table-tab-pager-info";
      info.textContent = `第 ${TableTab.currentPage} / ${pages} 頁（共 ${total} 筆）`;
      pager.appendChild(info);
  
      const btnPrev = document.createElement("button");
      btnPrev.type = "button";
      btnPrev.textContent = "上一頁";
      btnPrev.disabled = pages <= 1 || TableTab.currentPage <= 1;
      btnPrev.addEventListener("click", () => {
        if (TableTab.currentPage <= 1) return;
        TableTab.currentPage -= 1;
        renderBody();
        renderPager();
        updateFilterCount();
        saveCurrentStateToCache();
      });
      pager.appendChild(btnPrev);
  
      const maxPageButtons = 7;
      let start = Math.max(1, TableTab.currentPage - 3);
      let end = Math.min(pages, start + maxPageButtons - 1);
  
      if (end - start + 1 < maxPageButtons) {
        start = Math.max(1, end - maxPageButtons + 1);
      }
  
      for (let p = start; p <= end; p++) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = String(p);
        btn.className = "page-btn" + (p === TableTab.currentPage ? " active" : "");
        btn.disabled = pages <= 1;
  
        btn.addEventListener("click", () => {
          if (p === TableTab.currentPage || pages <= 1) return;
  
          TableTab.currentPage = p;
          renderBody();
          renderPager();
          updateFilterCount();
          saveCurrentStateToCache();
        });
  
        pager.appendChild(btn);
      }
  
      const btnNext = document.createElement("button");
      btnNext.type = "button";
      btnNext.textContent = "下一頁";
      btnNext.disabled = pages <= 1 || TableTab.currentPage >= pages;
  
      btnNext.addEventListener("click", () => {
        if (TableTab.currentPage >= pages) return;
  
        TableTab.currentPage += 1;
        renderBody();
        renderPager();
        updateFilterCount();
        saveCurrentStateToCache();
      });
  
      pager.appendChild(btnNext);
    }
  
    // ============================================================
    // identity / editable config
    // ============================================================
    function getDefaultSpecIdentityKeys() {
      if (TableTab.system === "bpi_same_point") {
        return ["model", "glass_side", "defect_size"];
      }
  
      return ["model", "glass_type", "defect_size"];
    }
  
    function getActionIdentityKeys() {
      const cfgKeys = TableTab.config?.manual_key_cols || TableTab.config?.editor_match_keys;
  
      if (Array.isArray(cfgKeys) && cfgKeys.length) {
        return cfgKeys.slice();
      }
  
      if (TableTab.system === "bpi_same_point") {
        return [
          "model",
          "glass_side",
          "glass_id",
          "tab",
          "api_aoi",
          "api_recipe_id",
        ];
      }
  
      return [
        "scan_hour",
        "aoi",
        "model",
        "cassette_id",
        "glass_side",
        "recipe_id",
      ];
    }
  
    function isEditorField(dataKey) {
      return dataKey === "editor" || dataKey === "Editor";
    }
  
    function getEditorFieldName() {
      return TableTab.system === "bpi_same_point" ? "editor" : "Editor";
    }
  
    function canEditDefaultField(dataKey) {
      if (DEFAULT_SPEC_RESERVED_FIELDS.has(dataKey)) return false;
      return true;
    }
  
    function isDefaultSelectField(dataKey) {
      return (
        dataKey === "glass_type" ||
        dataKey === "glass_side" ||
        dataKey === "defect_size"
      );
    }
  
    function isDefaultTextField(dataKey) {
      if (dataKey === "model") return true;
      if (dataKey === "OOC") return true;
      if (dataKey === "OOS") return true;
      if (isDefaultSelectField(dataKey)) return false;
      if (DEFAULT_SPEC_RESERVED_FIELDS.has(dataKey)) return false;
      return true;
    }
  
    // ============================================================
    // header buttons
    // ============================================================
    function setupHeader() {
      setHeaderTitle();
  
      const actions = byId(DOM.headerActions);
      if (!actions) return;
  
      actions.innerHTML = "";
  
      TableTab.editBtn = null;
      TableTab.addBtn = null;
      TableTab.deleteBtn = null;
      TableTab.cancelBtn = null;
  
      if (isDefaultSpec()) {
        setDateBlockVisible(false);
  
        const editBtn = document.createElement("button");
        editBtn.type = "button";
        editBtn.className = "btn-table-tab-action btn-spec-action";
        editBtn.textContent = "編輯";
  
        const addBtn = document.createElement("button");
        addBtn.type = "button";
        addBtn.className = "btn-table-tab-action btn-spec-action";
        addBtn.textContent = "新增";
  
        const deleteBtn = document.createElement("button");
        deleteBtn.type = "button";
        deleteBtn.className = "btn-table-tab-action btn-spec-action";
        deleteBtn.textContent = "刪除";
  
        editBtn.addEventListener("click", onClickDefaultEdit);
        addBtn.addEventListener("click", onClickDefaultAdd);
        deleteBtn.addEventListener("click", onClickDefaultDelete);
  
        actions.appendChild(editBtn);
        actions.appendChild(addBtn);
        actions.appendChild(deleteBtn);
  
        TableTab.editBtn = editBtn;
        TableTab.addBtn = addBtn;
        TableTab.deleteBtn = deleteBtn;
  
        syncHeaderButtonState();
        return;
      }
  
      if (isActionHistory()) {
        setDateBlockVisible(true);
        setDateInputsDefault();
  
        const editBtn = document.createElement("button");
        editBtn.type = "button";
        editBtn.className = "btn-table-tab-action btn-spec-action";
        editBtn.textContent = "編輯";
  
        const cancelBtn = document.createElement("button");
        cancelBtn.type = "button";
        cancelBtn.className = "btn-table-tab-action btn-spec-action";
        cancelBtn.textContent = "取消";
        cancelBtn.style.display = "none";
  
        editBtn.addEventListener("click", onClickActionEdit);
        cancelBtn.addEventListener("click", onClickActionCancel);
  
        actions.appendChild(editBtn);
        actions.appendChild(cancelBtn);
  
        TableTab.editBtn = editBtn;
        TableTab.cancelBtn = cancelBtn;
  
        syncHeaderButtonState();
        return;
      }
  
      setDateBlockVisible(false);
    }
  
    function syncHeaderButtonState() {
      if (isDefaultSpec()) {
        if (TableTab.isEditMode) {
          if (TableTab.editBtn) {
            TableTab.editBtn.style.display = "";
            TableTab.editBtn.textContent = "儲存";
          }
  
          if (TableTab.addBtn) {
            TableTab.addBtn.style.display = "";
            TableTab.addBtn.textContent = "取消";
          }
  
          if (TableTab.deleteBtn) {
            TableTab.deleteBtn.style.display = "";
            TableTab.deleteBtn.textContent = "刪除";
          }
  
          return;
        }
  
        if (TableTab.isDeleteMode) {
          if (TableTab.editBtn) TableTab.editBtn.style.display = "none";
          if (TableTab.addBtn) TableTab.addBtn.style.display = "none";
  
          if (TableTab.deleteBtn) {
            TableTab.deleteBtn.style.display = "";
            TableTab.deleteBtn.textContent = "取消";
          }
  
          return;
        }
  
        if (TableTab.editBtn) {
          TableTab.editBtn.style.display = "";
          TableTab.editBtn.textContent = "編輯";
        }
  
        if (TableTab.addBtn) {
          TableTab.addBtn.style.display = "";
          TableTab.addBtn.textContent = "新增";
        }
  
        if (TableTab.deleteBtn) {
          TableTab.deleteBtn.style.display = "";
          TableTab.deleteBtn.textContent = "刪除";
        }
  
        return;
      }
  
      if (isActionHistory()) {
        if (TableTab.isEditMode) {
          if (TableTab.editBtn) TableTab.editBtn.textContent = "儲存";
          if (TableTab.cancelBtn) TableTab.cancelBtn.style.display = "";
        } else {
          if (TableTab.editBtn) TableTab.editBtn.textContent = "編輯";
          if (TableTab.cancelBtn) TableTab.cancelBtn.style.display = "none";
        }
      }
    }
  
    // ============================================================
    // render table
    // ============================================================
    function renderHeader() {
      const table = byId(DOM.table);
      if (!table) return;
  
      if (TableTab.lastTabClass) {
        table.classList.remove(TableTab.lastTabClass);
        TableTab.lastTabClass = null;
      }
  
      if (TableTab.tabKey) {
        const cls = String(TableTab.tabKey).replace(/[^A-Za-z0-9_-]/g, "_");
        table.classList.add(cls);
        TableTab.lastTabClass = cls;
      }
  
      const thead = ensureThead(table);
      thead.innerHTML = "";
  
      const tr = document.createElement("tr");
  
      if (isDefaultSpec() && TableTab.isDeleteMode) {
        const thDel = document.createElement("th");
        thDel.className = "table-tab-del-th";
        thDel.textContent = "";
        tr.appendChild(thDel);
      }
  
      (TableTab.colKeys || []).forEach(dataKey => {
        if (isActionHistory() && dataKey === "modify_time") {
          // modify_time 併到 editor 欄顯示
          return;
        }
  
        const th = document.createElement("th");
        th.textContent = TableTab.colLabels[dataKey] || dataKey;
        tr.appendChild(th);
      });
  
      thead.appendChild(tr);
    }
  
    function renderBody() {
      const table = byId(DOM.table);
      if (!table) return;
  
      const tbody = ensureTbody(table);
      const rows = TableTab.filteredRows || [];
  
      tbody.innerHTML = "";
  
      if (!rows.length) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
  
        let colSpan = Math.max(1, TableTab.colKeys.length);
        if (isDefaultSpec() && TableTab.isDeleteMode) colSpan += 1;
  
        td.colSpan = colSpan;
        td.className = "muted";
        td.textContent = "（無資料）";
  
        tr.appendChild(td);
        tbody.appendChild(tr);
  
        return;
      }
  
      const size = TableTab.pageSize || 200;
      const start = (TableTab.currentPage - 1) * size;
      const end = start + size;
      const pageRows = rows.slice(start, end);
  
      pageRows.forEach((r, idxInPage) => {
        const tr = document.createElement("tr");
        const globalIndex = start + idxInPage;
        tr.dataset.rowIndex = String(globalIndex);
  
        if (isDefaultSpec() && TableTab.isDeleteMode) {
          const tdDel = document.createElement("td");
          tdDel.className = "table-tab-del-td";
  
          const btnDel = document.createElement("button");
          btnDel.type = "button";
          btnDel.className = "table-tab-del-btn";
          btnDel.textContent = "✕";
          btnDel.title = "刪除此列";
          btnDel.addEventListener("click", () => deleteDefaultSpecRow(r));
  
          tdDel.appendChild(btnDel);
          tr.appendChild(tdDel);
        }
  
        (TableTab.colKeys || []).forEach(dataKey => {
          if (isActionHistory() && dataKey === "modify_time") {
            return;
          }
  
          const td = document.createElement("td");
          const v = r?.[dataKey];
  
          if (isDefaultSpec()) {
            renderDefaultSpecCell(td, r, dataKey, v);
          } else if (isActionHistory()) {
            renderActionHistoryCell(td, r, dataKey, v);
          } else {
            renderPlainCell(td, dataKey, v);
          }
  
          tr.appendChild(td);
        });
  
        tbody.appendChild(tr);
      });
    }
  
    function renderPlainCell(td, dataKey, value) {
      if (LONG_TEXT_FIELDS.has(dataKey)) {
        td.classList.add("table-tab-longtext-cell");
  
        const box = document.createElement("div");
        box.className = "table-tab-longtext-box";
        box.textContent = safeStr(value);
  
        td.appendChild(box);
        return;
      }
  
      td.textContent = formatCellValue(value);
    }
  
    function renderEditorCell(td, row) {
      td.classList.add("editor-cell");
  
      const e = row?.editor || row?.Editor || "";
      const mt = row?.modify_time || "";
  
      td.innerHTML = `${e || ""}${(e && mt) ? "<br>" : ""}${mt || ""}`;
    }
  
    function renderDefaultSpecCell(td, row, dataKey, value) {
      if (isEditorField(dataKey)) {
        renderEditorCell(td, row);
        return;
      }
  
      if (dataKey === "modify_time") {
        td.textContent = safeStr(value);
        return;
      }
  
      if (TableTab.isEditMode && canEditDefaultField(dataKey)) {
        if (isDefaultSelectField(dataKey)) {
          const select = document.createElement("select");
          select.className = "table-tab-edit-select spec-edit-select";
          select.dataset.field = dataKey;
  
          const opts = getOptionsForDataKey(dataKey);
          const cur = value == null ? "" : String(value);
  
          opts.forEach(optVal => {
            const opt = document.createElement("option");
            opt.value = optVal;
            opt.textContent = optVal;
            if (String(optVal) === cur) opt.selected = true;
            select.appendChild(opt);
          });
  
          if (cur && !opts.includes(cur)) {
            const opt = document.createElement("option");
            opt.value = cur;
            opt.textContent = cur;
            opt.selected = true;
            select.appendChild(opt);
          }
  
          td.appendChild(select);
          return;
        }
  
        if (isDefaultTextField(dataKey)) {
          const input = document.createElement("input");
          input.type = "text";
          input.className = "table-tab-edit-input spec-edit-input";
          input.value = value == null ? "" : String(value);
          input.dataset.field = dataKey;
  
          td.appendChild(input);
          return;
        }
      }
  
      td.textContent = formatCellValue(value);
    }
  
    function renderActionHistoryCell(td, row, dataKey, value) {
      if (TableTab.isEditMode && ACTION_EDITABLE_FIELDS.has(dataKey)) {
        td.classList.add("es-editable-cell");
  
        const textarea = document.createElement("textarea");
        textarea.className = "table-tab-edit-input table-tab-edit-textarea spec-edit-textarea es-edit-input";
        textarea.dataset.field = dataKey;
        textarea.value = value == null ? "" : String(value);
        textarea.rows = 3;
        textarea.spellcheck = false;
  
        td.appendChild(textarea);
        return;
      }
  
      if (isEditorField(dataKey)) {
        renderEditorCell(td, row);
        return;
      }
  
      if (LONG_TEXT_FIELDS.has(dataKey)) {
        td.classList.add("table-tab-longtext-cell", "bpi-action-history-longtext-cell");
  
        const box = document.createElement("div");
        box.className = "table-tab-longtext-box bpi-action-history-longtext-box";
        box.textContent = value == null ? "" : String(value);
  
        td.appendChild(box);
        return;
      }
  
      td.textContent = formatCellValue(value);
    }
  
    // ============================================================
    // default spec edit / add / delete
    // ============================================================
    function onClickDefaultEdit() {
      if (!isDefaultSpec()) return;
  
      if (TableTab.isAddMode) {
        closeAddPanel();
      }
  
      if (!TableTab.isEditMode) {
        TableTab.isEditMode = true;
        TableTab.isDeleteMode = false;
  
        syncHeaderButtonState();
        renderHeader();
        renderBody();
        saveCurrentStateToCache();
  
        return;
      }
  
      saveDefaultSpecEdits();
    }
  
    function onClickDefaultAdd() {
      if (!isDefaultSpec()) return;
  
      if (TableTab.isEditMode) {
        TableTab.isEditMode = false;
        syncHeaderButtonState();
        renderBody();
        saveCurrentStateToCache();
        return;
      }
  
      if (!TableTab.isAddMode) {
        TableTab.isAddMode = true;
        TableTab.isDeleteMode = false;
        TableTab.isEditMode = false;
  
        syncHeaderButtonState();
        showAddPanel();
        saveCurrentStateToCache();
        return;
      }
  
      closeAddPanel();
    }
  
    function onClickDefaultDelete() {
      if (!isDefaultSpec()) return;
  
      if (!TableTab.isDeleteMode) {
        TableTab.isDeleteMode = true;
        TableTab.isEditMode = false;
        TableTab.isAddMode = false;
  
        closeAddPanel({ silent: true });
      } else {
        TableTab.isDeleteMode = false;
      }
  
      syncHeaderButtonState();
      renderHeader();
      renderBody();
      renderPager();
      saveCurrentStateToCache();
    }
  
    async function saveDefaultSpecEdits() {
      const table = byId(DOM.table);
      if (!table) return;
  
      const tbody = ensureTbody(table);
      const rows = TableTab.filteredRows || [];
      const trs = Array.from(tbody.querySelectorAll("tr"));
      const identityKeys = getDefaultSpecIdentityKeys();
  
      const pending = new Map();
  
      trs.forEach(tr => {
        const idx = Number(tr.dataset.rowIndex);
        if (Number.isNaN(idx)) return;
  
        const row = rows[idx];
        if (!row) return;
  
        const inputs = tr.querySelectorAll(
          "input.table-tab-edit-input[data-field], select.table-tab-edit-select[data-field], input.spec-edit-input[data-field], select.spec-edit-select[data-field]"
        );
  
        inputs.forEach(inp => {
          const field = inp.dataset.field;
          const newVal = inp.value ?? "";
          const oldVal = row[field] == null ? "" : String(row[field]);
  
          if (String(newVal) === oldVal) return;
  
          if (!pending.has(idx)) {
            pending.set(idx, {
              rowIndex: idx,
              identity: {},
              patch: {},
              old: {},
            });
          }
  
          const item = pending.get(idx);
          item.patch[field] = newVal;
          item.old[field] = row[field];
  
          row[field] = newVal;
        });
  
        if (pending.has(idx)) {
          const item = pending.get(idx);
  
          identityKeys.forEach(k => {
            if (Object.prototype.hasOwnProperty.call(item.old, k)) {
              item.identity[k] = item.old[k];
            } else {
              item.identity[k] = row[k] ?? "";
            }
          });
        }
      });
  
      const changes = Array.from(pending.values());
  
      if (!changes.length) {
        TableTab.isEditMode = false;
        syncHeaderButtonState();
        renderBody();
        saveCurrentStateToCache();
        return;
      }
  
      const mt = getNowStr();
      const editorCol = getEditorFieldName();
  
      changes.forEach(ch => {
        const row = rows[ch.rowIndex];
        if (row) {
          row[editorCol] = editor;
          row.editor = editor;
          row.Editor = editor;
          row.modify_time = mt;
        }
      });
  
      const payload = {
        system: TableTab.system,
        mode: "edit",
        tabKey: TableTab.tabKey,
        Editor: editor,
        modify_time: mt,
        changes,
      };
  
      try {
        if (!API?.FrontSpecEditor) {
          throw new Error("AOI_BPI_DENSITY_API.FrontSpecEditor 不存在");
        }
  
        console.log("[BPI_AREA_TABLE_TAB][spec edit] payload =", payload);
  
        const res = await API.FrontSpecEditor(payload);
        console.log("[BPI_AREA_TABLE_TAB][spec edit] result =", res);
  
        if (!res || res.ok !== true) {
          alert("儲存完成，但後端回應不是 ok=true");
        }
      } catch (err) {
        console.error("[BPI_AREA_TABLE_TAB][spec edit] failed", err);
        alert("儲存失敗：" + (err?.message || String(err)));
      }
  
      TableTab.isEditMode = false;
      syncHeaderButtonState();
      renderBody();
      saveCurrentStateToCache();
    }
  
    function showAddPanel() {
      const panel = byId(DOM.addPanel);
      if (!panel) return;
    
      // 新增區塊固定顯示在原本 table 上方
      const left = byId("bpi-area-table-tab-left");
      const wrap = left ? left.querySelector(".table-wrap") : null;
    
      if (left && wrap && panel.parentElement === left) {
        left.insertBefore(panel, wrap);
      }
    
      panel.innerHTML = "";
  
      const addTable = document.createElement("table");
      addTable.className = "table-tab-add-table spec-add-table";
  
      const thead = document.createElement("thead");
      const headTr = document.createElement("tr");
  
      const tbody = document.createElement("tbody");
      const bodyTr = document.createElement("tr");
  
      (TableTab.colKeys || []).forEach(dataKey => {
        if (DEFAULT_SPEC_RESERVED_FIELDS.has(dataKey)) return;
  
        const header = TableTab.colLabels[dataKey] || dataKey;
  
        const th = document.createElement("th");
        th.textContent = header;
        headTr.appendChild(th);
  
        const td = document.createElement("td");
        let inputEl;
  
        if (isDefaultSelectField(dataKey)) {
          inputEl = document.createElement("select");
  
          const ph = document.createElement("option");
          ph.value = "";
          ph.textContent = "-- 請選擇 --";
          inputEl.appendChild(ph);
  
          const opts = getOptionsForDataKey(dataKey);
          opts.forEach(v => {
            const opt = document.createElement("option");
            opt.value = v;
            opt.textContent = v;
            inputEl.appendChild(opt);
          });
        } else {
          inputEl = document.createElement("input");
          inputEl.type = "text";
        }
  
        inputEl.className = "table-tab-add-input spec-add-input";
        inputEl.dataset.field = dataKey;
        inputEl.dataset.label = header;
  
        td.appendChild(inputEl);
        bodyTr.appendChild(td);
      });
  
      thead.appendChild(headTr);
      tbody.appendChild(bodyTr);
      addTable.appendChild(thead);
      addTable.appendChild(tbody);
  
      const footer = document.createElement("div");
      footer.className = "table-tab-add-footer spec-add-footer";
  
      const btnCancel = document.createElement("button");
      btnCancel.type = "button";
      btnCancel.className = "btn btn-xs btn-secondary";
      btnCancel.textContent = "取消";
      btnCancel.addEventListener("click", () => closeAddPanel());
  
      const btnSave = document.createElement("button");
      btnSave.type = "button";
      btnSave.className = "btn btn-xs";
      btnSave.textContent = "儲存";
      btnSave.addEventListener("click", saveAddDefaultSpecRow);
  
      footer.appendChild(btnCancel);
      footer.appendChild(btnSave);
  
      panel.appendChild(addTable);
      panel.appendChild(footer);
  
      panel.style.display = "";
    }
  
    function closeAddPanel(opts) {
      opts = opts || {};
  
      const panel = byId(DOM.addPanel);
      if (panel) {
        panel.innerHTML = "";
        panel.style.display = "none";
      }
  
      TableTab.isAddMode = false;
  
      if (!opts.silent) {
        syncHeaderButtonState();
        saveCurrentStateToCache();
      }
    }
  
    async function saveAddDefaultSpecRow() {
      const panel = byId(DOM.addPanel);
      if (!panel) return;
  
      const inputs = panel.querySelectorAll("[data-field]");
      const newRow = {};
      const emptyLabels = [];
  
      inputs.forEach(inp => {
        const field = inp.dataset.field;
        const label = inp.dataset.label || field;
        const val = cleanStr(inp.value);
  
        if (!val) emptyLabels.push(label);
  
        newRow[field] = val;
      });
  
      if (emptyLabels.length) {
        alert("以下欄位不得為空：\n" + emptyLabels.join("、"));
        return;
      }

      const requiredFields = isDefaultSpec()
      ? (TableTab.system === "bpi_same_point"
          ? ["model", "glass_side", "defect_size", "OOC", "OOS"]
          : ["model", "glass_type", "defect_size", "OOC", "OOS"])
      : [];

      const missing = requiredFields.filter(k => !cleanStr(newRow[k]));

      if (missing.length) {
        const labelMap = {};
        Object.entries(TableTab.colLabels || {}).forEach(([k, label]) => {
          labelMap[k] = label || k;
        });

        alert("以下欄位不得為空：\n" + missing.map(k => labelMap[k] || k).join("、"));
        return;
      }
  
      const mt = getNowStr();
      const editorCol = getEditorFieldName();
  
      newRow[editorCol] = editor;
      newRow.editor = editor;
      newRow.Editor = editor;
      newRow.modify_time = mt;
  
      const payload = {
        system: TableTab.system,
        mode: "add",
        tabKey: TableTab.tabKey,
        Editor: editor,
        modify_time: mt,
        row: newRow,
      };
  
      try {
        if (!API?.FrontSpecEditor) {
          throw new Error("AOI_BPI_DENSITY_API.FrontSpecEditor 不存在");
        }
  
        console.log("[BPI_AREA_TABLE_TAB][spec add] payload =", payload);
  
        const res = await API.FrontSpecEditor(payload);
        console.log("[BPI_AREA_TABLE_TAB][spec add] result =", res);
  
        if (!res || res.ok !== true) {
          alert("新增完成，但後端回應不是 ok=true");
        }
  
        TableTab.allRows.unshift(newRow);
        closeAddPanel({ silent: true });
        TableTab.isAddMode = false;
  
        buildFilters(collectSelections());
        applyLocalFilter();
        syncHeaderButtonState();
        saveCurrentStateToCache();
      } catch (err) {
        console.error("[BPI_AREA_TABLE_TAB][spec add] failed", err);
        alert("新增失敗：" + (err?.message || String(err)));
      }
    }
  
    async function deleteDefaultSpecRow(row) {
      if (!row) return;
  
      const ok = confirm("確認刪除此列？");
      if (!ok) return;
  
      const mt = getNowStr();
  
      const payload = {
        system: TableTab.system,
        mode: "delete",
        tabKey: TableTab.tabKey,
        Editor: editor,
        modify_time: mt,
        row,
      };
  
      try {
        if (!API?.FrontSpecEditor) {
          throw new Error("AOI_BPI_DENSITY_API.FrontSpecEditor 不存在");
        }
  
        console.log("[BPI_AREA_TABLE_TAB][spec delete] payload =", payload);
  
        const res = await API.FrontSpecEditor(payload);
        console.log("[BPI_AREA_TABLE_TAB][spec delete] result =", res);
  
        if (!res || res.ok !== true) {
          alert("刪除完成，但後端回應不是 ok=true");
        }
  
        TableTab.allRows = TableTab.allRows.filter(x => x !== row);
        TableTab.filteredRows = TableTab.filteredRows.filter(x => x !== row);
  
        updatePagination();
        renderHeader();
        renderBody();
        renderPager();
        updateFilterCount();
        saveCurrentStateToCache();
      } catch (err) {
        console.error("[BPI_AREA_TABLE_TAB][spec delete] failed", err);
        alert("刪除失敗：" + (err?.message || String(err)));
      }
    }
  
    // ============================================================
    // action history edit
    // ============================================================
    function onClickActionEdit() {
      if (!isActionHistory()) return;
  
      if (!TableTab.isEditMode) {
        TableTab.isEditMode = true;
        syncHeaderButtonState();
        renderBody();
        saveCurrentStateToCache();
        return;
      }
  
      saveActionHistoryEdits();
    }
  
    function onClickActionCancel() {
      if (!isActionHistory()) return;
  
      TableTab.isEditMode = false;
      syncHeaderButtonState();
      renderBody();
      saveCurrentStateToCache();
    }
  
    async function saveActionHistoryEdits() {
      const table = byId(DOM.table);
      if (!table) return;
  
      const tbody = ensureTbody(table);
      const rows = TableTab.filteredRows || [];
      const trs = Array.from(tbody.querySelectorAll("tr"));
  
      const idKeys = getActionIdentityKeys();
      const mt = getNowStr();
      const jobs = [];
  
      trs.forEach(tr => {
        const idx = Number(tr.dataset.rowIndex);
        if (Number.isNaN(idx)) return;
  
        const row = rows[idx];
        if (!row) return;
  
        const inputs = tr.querySelectorAll(".es-edit-input[data-field], .table-tab-edit-textarea[data-field]");
        const patch = {};
  
        inputs.forEach(inp => {
          const field = inp.dataset.field;
          const newVal = inp.value ?? "";
          const oldVal = row[field] == null ? "" : String(row[field]);
  
          if (newVal !== oldVal) {
            patch[field] = newVal;
          }
        });
  
        if (!Object.keys(patch).length) return;
  
        const idRow = {};
  
        idKeys.forEach(k => {
          idRow[k] = row[k] ?? "";
        });
  
        // 如果後端仍需要時間欄位，保底帶上。若後端 match_keys 不用，不影響。
        ["scan_hour", "run_day", "api_scan_time", "bpi_scan_time"].forEach(k => {
          if (row[k] != null && idRow[k] == null) idRow[k] = row[k];
        });
  
        const payloadBase = {
          system: TableTab.system,
          mode: "edit",
          row: idRow,
          editor,
          modify_time: mt,
        };
  
        if (Object.prototype.hasOwnProperty.call(patch, "comment")) {
          payloadBase.comment = patch.comment;
          row.comment = patch.comment;
        }
  
        if (Object.prototype.hasOwnProperty.call(patch, "action")) {
          payloadBase.action = patch.action;
          row.action = patch.action;
        }
  
        row.editor = editor;
        row.Editor = editor;
        row.modify_time = mt;
  
        jobs.push(payloadBase);
      });
  
      if (!jobs.length) {
        TableTab.isEditMode = false;
        syncHeaderButtonState();
        renderBody();
        saveCurrentStateToCache();
        return;
      }
  
      let allOk = true;
  
      for (const payload of jobs) {
        try {
          if (!API?.ActionHisEditor) {
            throw new Error("AOI_BPI_DENSITY_API.ActionHisEditor 不存在");
          }
  
          console.log("[BPI_AREA_TABLE_TAB][action edit] payload =", payload);
  
          const res = await API.ActionHisEditor(payload);
          console.log("[BPI_AREA_TABLE_TAB][action edit] result =", res);
  
          if (!res || res.ok !== true) {
            allOk = false;
          }
        } catch (err) {
          console.error("[BPI_AREA_TABLE_TAB][action edit] failed", payload, err);
          alert("儲存失敗：" + (err?.message || String(err)));
          allOk = false;
          break;
        }
      }
  
      TableTab.isEditMode = false;
      syncHeaderButtonState();
      renderBody();
      saveCurrentStateToCache();
  
      if (allOk) {
        alert("儲存成功");
      } else {
        alert("儲存完成，但部分後端回應不是 ok=true");
      }
    }
  
    async function fetchActionHistoryByDate(opts) {
      opts = opts || {};
  
      if (!API?.ActionHisEditor) {
        console.error("[BPI_AREA_TABLE_TAB] ActionHisEditor 不存在");
        return null;
      }
  
      const dates = readDates();
  
      const payload = {
        system: TableTab.system,
        mode: "date",
        dates: dates && dates.length === 2 ? dates : null,
      };
  
      const resp = await API.ActionHisEditor(payload);
  
      if (!resp) return null;
  
      renderActionHistoryResp(resp, {
        keepSelections: !!opts.keepSelections,
      });
  
      return resp;
    }
  
    async function fetchActionHistoryDefaultRange() {
      const [ds, de] = default3DaysRange();
  
      const s = byId(DOM.start);
      const e = byId(DOM.end);
  
      if (s) s.value = ds;
      if (e) e.value = de;
  
      if (!API?.ActionHisEditor) {
        console.error("[BPI_AREA_TABLE_TAB] ActionHisEditor 不存在");
        return null;
      }
  
      const payload = {
        system: TableTab.system,
        mode: "date",
        dates: [ds, de],
      };
  
      const resp = await API.ActionHisEditor(payload);
  
      if (!resp) return null;
  
      renderActionHistoryResp(resp, {
        keepSelections: false,
      });
  
      return resp;
    }
  
    function renderActionHistoryResp(resp, opts) {
      opts = opts || {};
  
      const prev = opts.keepSelections ? collectSelections() : null;
      const rows = normalizeRespRows(resp);
  
      TableTab.allRows = rows.slice();
      TableTab.filteredRows = rows.slice();
      TableTab.currentPage = 1;
      TableTab.isEditMode = false;
      TableTab.isAddMode = false;
      TableTab.isDeleteMode = false;
  
      buildColConfig(TableTab.config, TableTab.allRows);
      renderHeader();
      buildFilters(prev);
      applyLocalFilter();
      syncHeaderButtonState();
      saveCurrentStateToCache();
    }
  
    // ============================================================
    // buttons
    // ============================================================
    let buttonsBound = false;
  
    function bindButtons() {
      if (buttonsBound) return;
      buttonsBound = true;
  
      const btnApply = byId(DOM.apply);
      const btnClear = byId(DOM.clear);
      const btnBottomClear = ensureBottomClearButton();
  
      if (btnApply) {
        btnApply.addEventListener("click", async () => {
          if (isActionHistory()) {
            await fetchActionHistoryByDate({ keepSelections: true });
          } else {
            TableTab.currentPage = 1;
            applyLocalFilter();
          }
        });
      }
  
      async function clearAll() {
        if (isActionHistory()) {
          const s = byId(DOM.start);
          const e = byId(DOM.end);
          if (s) s.value = "";
          if (e) e.value = "";
  
          await fetchActionHistoryDefaultRange();
          return;
        }
  
        clearAllLocalFilters();
      }
  
      if (btnClear) {
        btnClear.addEventListener("click", clearAll);
      }
  
      if (btnBottomClear) {
        btnBottomClear.addEventListener("click", clearAll);
      }
    }
  
    // ============================================================
    // main render
    // ============================================================
    function resetStateForDetail(detail) {
      TableTab.kind = detail.kind || "table";
      TableTab.system = detail.system || "bpi_density";
      TableTab.tabGroup = detail.tabGroup || "";
      TableTab.tabKey = detail.tabKey || "";
      TableTab.config = detail.config || {};
  
      TableTab.allRows = [];
      TableTab.filteredRows = [];
  
      TableTab.mdd = {};
      TableTab.colKeys = [];
      TableTab.colLabels = {};
      TableTab.filterConfig = TableTab.config?.filter_item_coldict || {};
      TableTab.filterOrder = Array.isArray(TableTab.config?.cascade_order)
        ? TableTab.config.cascade_order.slice()
        : Object.keys(TableTab.filterConfig || {}).map(label => TableTab.filterConfig[label]?.key || label);
  
      TableTab.pageSize = Number(TableTab.config?.page_size || 200);
      if (!Number.isFinite(TableTab.pageSize) || TableTab.pageSize <= 0) TableTab.pageSize = 200;
  
      TableTab.currentPage = 1;
      TableTab.totalPages = 1;
  
      TableTab.isEditMode = false;
      TableTab.isAddMode = false;
      TableTab.isDeleteMode = false;
  
      TableTab.editBtn = null;
      TableTab.addBtn = null;
      TableTab.deleteBtn = null;
      TableTab.cancelBtn = null;
    }
  
    function renderDefaultSpecData(data) {
      const rows = normalizeRows(data);
  
      TableTab.allRows = rows.slice();
      TableTab.filteredRows = rows.slice();
  
      buildColConfig(TableTab.config, TableTab.allRows);
  
      setupHeader();
      renderHeader();
      buildFilters(null);
      applyLocalFilter();
      syncHeaderButtonState();
      saveCurrentStateToCache();
    }
  
    function renderGenericTableData(data) {
      const rows = normalizeRows(data);
  
      TableTab.allRows = rows.slice();
      TableTab.filteredRows = rows.slice();
  
      buildColConfig(TableTab.config, TableTab.allRows);
  
      setupHeader();
      renderHeader();
      buildFilters(null);
      applyLocalFilter();
      syncHeaderButtonState();
      saveCurrentStateToCache();
    }
  
    function renderActionHistoryInitial(resp) {
      const rows = normalizeRespRows(resp);
  
      TableTab.allRows = rows.slice();
      TableTab.filteredRows = rows.slice();
  
      buildColConfig(TableTab.config, TableTab.allRows);
  
      setupHeader();
      renderHeader();
      buildFilters(null);
      applyLocalFilter();
      syncHeaderButtonState();
      saveCurrentStateToCache();
    }
  
    // ============================================================
    // event
    // ============================================================
    document.addEventListener("bpi-area:table-tab-show", async (ev) => {
      bindButtons();
  
      const detail = ev.detail || {};
      const kind = detail.kind || "table";
      const system = detail.system || "bpi_density";
      const tabKey = detail.tabKey || "";
  
      if (detail.restoreOnly) {
        const ok = restoreStateFromCache(kind, system, tabKey);
        if (ok) return;
      }
  
      clearDomForNewTab();
      resetStateForDetail(detail);
  
      if (isDefaultSpec()) {
        renderDefaultSpecData(detail.data || {});
        return;
      }
  
      if (isActionHistory()) {
        if (detail.resp) {
          renderActionHistoryInitial(detail.resp);
          return;
        }
  
        setDateInputsDefault();
        await fetchActionHistoryDefaultRange();
        return;
      }
  
      renderGenericTableData(detail.data || detail.rows || {});
    });
  
    AREA.TableTab = {
      state: TableTab,
      applyLocalFilter,
      fetchActionHistoryByDate,
      fetchActionHistoryDefaultRange,
      renderDefaultSpecData,
      renderActionHistoryResp,
    };
  })();