// static/js/aoi_inspection_density/tabs/table_tab/filters.js
(function () {
  const AOI = (window.AOI_INSPECTION = window.AOI_INSPECTION || {});
  const MOD = (AOI.TableTab = AOI.TableTab || {});
  const NS = (MOD.Filters = MOD.Filters || {});

  const STATE = AOI.TableTab && AOI.TableTab.State;
  const DOM = AOI.TableTab && AOI.TableTab.DOM;

  if (!STATE || !DOM) {
    console.error("[AOI_INSPECTION.TableTab.Filters] missing dependency: State or DOM");
    return;
  }

  const { SpecState } = STATE;
  const {
    createEl,
    ensureSpecDynHosts,
    ensureFilterCountSpan,
    ensureBottomClearButton
  } = DOM;

  function getRender() {
    return AOI.TableTab && AOI.TableTab.Render;
  }

  function refreshTable() {
    const RENDER = getRender();

    if (RENDER && typeof RENDER.renderAll === "function") {
      RENDER.renderAll();
      return;
    }

    updateFilterCount();
  }

  function getSharedMultiDDClass() {
    if (window.AOI_SHARED && window.AOI_SHARED.MultiDD) return window.AOI_SHARED.MultiDD;
    if (window.AOI_INSPECTION && window.AOI_INSPECTION.MultiDD) return window.AOI_INSPECTION.MultiDD;
    if (window.AOI_DENSITY && window.AOI_DENSITY.MultiDD) return window.AOI_DENSITY.MultiDD;
    return null;
  }

  function toStringSafe(v) {
    if (v == null) return "";
    return String(v);
  }

  function uniqueSortedStrings(list) {
    return Array.from(new Set((list || []).map(toStringSafe).filter(Boolean))).sort();
  }

  function getFilterConfigByLabel(label) {
    return (SpecState.filterConfig && SpecState.filterConfig[label]) || {};
  }

  function getFilterDataKeyByLabel(label) {
    const cfg = getFilterConfigByLabel(label);
    return cfg.key || label;
  }

  function getDateInputValues() {
    const s = DOM.getSpecStartInput();
    const e = DOM.getSpecEndInput();

    return {
      start: s ? s.value : "",
      end: e ? e.value : ""
    };
  }

  function getOptionsForLabel(label) {
    const cfg = getFilterConfigByLabel(label);
    const dataKey = cfg.key || label;
    const wrap = SpecState.mdd[dataKey];

    if (!wrap || !Array.isArray(wrap.options)) return [];
    return wrap.options.slice();
  }

  function getOptionsFromFilterConfigValues(label) {
    const cfg = getFilterConfigByLabel(label);
    if (!cfg) return [];

    const vals = cfg.values;
    if (!Array.isArray(vals)) return [];

    return vals.map(v => String(v));
  }

  function collectSelectionsFromState() {
    const out = {};

    Object.entries(SpecState.mdd || {}).forEach(([dataKey, wrap]) => {
      if (!wrap || !wrap.mdd) return;

      const mdd = wrap.mdd;
      const selected = (typeof mdd.getSelected === "function" ? mdd.getSelected() : []) || [];

      out[dataKey] = new Set(selected.map(String));
    });

    return out;
  }

  function getActiveFilters() {
    const out = {};

    Object.entries(SpecState.mdd || {}).forEach(([dataKey, wrap]) => {
      if (!wrap || !wrap.mdd) return;

      const mdd = wrap.mdd;
      const selected = (typeof mdd.getSelected === "function" ? mdd.getSelected() : []) || [];

      out[dataKey] = new Set(selected.map(String));
    });

    return out;
  }

  function wireSearchForHost(hostEl) {
    if (!hostEl) return;

    const ddRoot = hostEl.querySelector(".multi-dd");
    if (!ddRoot) return;

    const input = ddRoot.querySelector(".multi-dd-search");
    if (!input) return;

    if (input.dataset.searchBound === "1") return;
    input.dataset.searchBound = "1";

    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      const items = Array.from(ddRoot.querySelectorAll(".multi-dd-item"));

      items.forEach(item => {
        const txt = (item.textContent || "").toLowerCase();
        item.style.display = (!q || txt.includes(q)) ? "" : "none";
      });
    });
  }

  function getBaseRowsForFilterIndex(labels, idx, prevSelections) {
    let baseRows = SpecState.allRows || [];

    if (!prevSelections || idx <= 0) return baseRows;

    labels.slice(0, idx).forEach(prevLabel => {
      const prevKey = getFilterDataKeyByLabel(prevLabel);

      if (!Object.prototype.hasOwnProperty.call(prevSelections, prevKey)) {
        return;
      }

      const selectedSet = prevSelections[prevKey];

      if (!selectedSet || selectedSet.size === 0) {
        baseRows = [];
        return;
      }

      baseRows = baseRows.filter(row => {
        if (!row) return false;

        const v = toStringSafe(row[prevKey]);
        return selectedSet.has(v);
      });
    });

    return baseRows;
  }

  function resolveOptionsForLabel(label, baseRows) {
    const cfg = getFilterConfigByLabel(label);
    const dataKey = cfg.key || label;

    const uniqSet = new Set();

    (baseRows || []).forEach(row => {
      if (!row) return;

      const v = row[dataKey];
      if (v == null || v === "") return;

      uniqSet.add(String(v));
    });

    const uniqArr = Array.from(uniqSet).sort();
    const cfgValues = Array.isArray(cfg.values)
      ? cfg.values.map(v => String(v))
      : [];

    if (cfgValues.length) {
      return cfgValues.filter(v => uniqSet.has(String(v)));
    }

    return uniqArr;
  }

  function buildSpecFilters(prevSelections) {
    const dynHosts = ensureSpecDynHosts();
    if (!dynHosts) return;

    dynHosts.innerHTML = "";
    SpecState.mdd = {};

    const labels = SpecState.filterOrder && SpecState.filterOrder.length
      ? SpecState.filterOrder.slice()
      : Object.keys(SpecState.filterConfig || {});

    if (!labels.length) {
      SpecState.filteredRows = (SpecState.allRows || []).slice();
      return;
    }

    const MultiDD = getSharedMultiDDClass();

    if (!MultiDD) {
      console.error("[AOI_INSPECTION.TableTab.Filters] MultiDD not found");
      SpecState.filteredRows = (SpecState.allRows || []).slice();
      return;
    }

    labels.forEach((label, idx) => {
      const cfg = getFilterConfigByLabel(label);
      const dataKey = cfg.key || label;

      const baseRows = getBaseRowsForFilterIndex(labels, idx, prevSelections);
      const options = resolveOptionsForLabel(label, baseRows);

      if (!options.length) return;

      const host = createEl("div", {
        className: "multi-dd-host",
        id: STATE.specHostIdOf(dataKey)
      });

      dynHosts.appendChild(host);

      const selectId = STATE.specSelectIdOf(dataKey);

      const mdd = new MultiDD({
        hostId: host.id,
        selectId,
        options,
        title: label,
        onChange: () => {
          SpecState.currentPage = 1;
          applySpecFilters();
          refreshTable();
        }
      });

      let selected = options.slice();

      if (
        prevSelections &&
        Object.prototype.hasOwnProperty.call(prevSelections, dataKey)
      ) {
        const prevSet = prevSelections[dataKey];

        if (!prevSet || prevSet.size === 0) {
          selected = [];
        } else {
          const intersect = options.filter(opt => prevSet.has(String(opt)));
          selected = intersect.length ? intersect : [];
        }
      }

      if (typeof mdd.setSelected === "function") {
        mdd.setSelected(selected);
      }

      SpecState.mdd[dataKey] = {
        mdd,
        options: options.slice()
      };

      wireSearchForHost(host);
    });
  }

  function applySpecFilters() {
    const filters = getActiveFilters();
    const rows = SpecState.allRows || [];
    const filterKeys = Object.keys(filters);

    if (!filterKeys.length) {
      SpecState.filteredRows = rows.slice();
      return SpecState.filteredRows.slice();
    }

    const hasEmptySelection = filterKeys.some(dataKey => {
      const selectedSet = filters[dataKey];
      return selectedSet instanceof Set && selectedSet.size === 0;
    });

    if (hasEmptySelection) {
      SpecState.filteredRows = [];
      return [];
    }

    SpecState.filteredRows = rows.filter(row => {
      for (const dataKey of filterKeys) {
        const selectedSet = filters[dataKey];
        const cellVal = row && row[dataKey] != null ? String(row[dataKey]) : "";

        if (!selectedSet.has(cellVal)) return false;
      }

      return true;
    });

    return SpecState.filteredRows.slice();
  }

  function clearSpecFilters(options = {}) {
    const { clearDates = true } = options || {};

    if (clearDates) {
      const startInput = DOM.getSpecStartInput();
      const endInput = DOM.getSpecEndInput();

      if (startInput) startInput.value = "";
      if (endInput) endInput.value = "";
    }

    Object.values(SpecState.mdd || {}).forEach(wrap => {
      const mdd = wrap && wrap.mdd;

      if (mdd && typeof mdd.setSelected === "function") {
        mdd.setSelected([]);
      }
    });

    SpecState.currentPage = 1;
    applySpecFilters();
    refreshTable();
  }

  function updateFilterCount() {
    const span = ensureFilterCountSpan();
    if (!span) return null;

    const total = (SpecState.filteredRows || []).length;
    span.textContent = `（${total} 筆）`;

    return span;
  }

  function getCurrentFilterSnapshot() {
    return {
      dates: getDateInputValues(),
      selections: collectSelectionsFromState()
    };
  }

  function rebuildFiltersWithCurrentSelections() {
    const selections = collectSelectionsFromState();

    buildSpecFilters(selections);

    SpecState.currentPage = 1;
    applySpecFilters();
    refreshTable();
  }

  function rebuildFiltersFromScratch() {
    buildSpecFilters(null);

    SpecState.currentPage = 1;
    applySpecFilters();
    refreshTable();
  }

  function ensureFilterExtras() {
    ensureFilterCountSpan();
    ensureBottomClearButton();
  }

  NS.toStringSafe = toStringSafe;
  NS.uniqueSortedStrings = uniqueSortedStrings;

  NS.getOptionsForLabel = getOptionsForLabel;
  NS.getOptionsFromFilterConfigValues = getOptionsFromFilterConfigValues;

  NS.collectSelectionsFromState = collectSelectionsFromState;
  NS.getActiveFilters = getActiveFilters;
  NS.wireSearchForHost = wireSearchForHost;

  NS.getBaseRowsForFilterIndex = getBaseRowsForFilterIndex;
  NS.resolveOptionsForLabel = resolveOptionsForLabel;

  NS.buildSpecFilters = buildSpecFilters;
  NS.applySpecFilters = applySpecFilters;
  NS.clearSpecFilters = clearSpecFilters;
  NS.updateFilterCount = updateFilterCount;

  NS.getCurrentFilterSnapshot = getCurrentFilterSnapshot;
  NS.rebuildFiltersWithCurrentSelections = rebuildFiltersWithCurrentSelections;
  NS.rebuildFiltersFromScratch = rebuildFiltersFromScratch;
  NS.ensureFilterExtras = ensureFilterExtras;
})();