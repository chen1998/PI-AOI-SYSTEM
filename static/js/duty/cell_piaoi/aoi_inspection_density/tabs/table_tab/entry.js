// static/js/aoi_inspection_density/tabs/table_tab/entry.js
(function () {
  const AOI = (window.AOI_INSPECTION = window.AOI_INSPECTION || {});
  const MOD = (AOI.TableTab = AOI.TableTab || {});
  const NS = MOD;

  const STATE = AOI.TableTab && AOI.TableTab.State;
  const DOM = AOI.TableTab && AOI.TableTab.DOM;
  const FILTERS = AOI.TableTab && AOI.TableTab.Filters;
  const RENDER = AOI.TableTab && AOI.TableTab.Render;
  const DEFAULT_EDITOR = AOI.TableTab && AOI.TableTab.DefaultSpecEditor;
  const EDIT_SUMMARY_EDITOR = AOI.TableTab && AOI.TableTab.EditSummaryEditor;

  if (!STATE || !DOM || !FILTERS || !RENDER || !DEFAULT_EDITOR || !EDIT_SUMMARY_EDITOR) {
    console.error("[AOI_INSPECTION.TableTab] missing dependency");
    return;
  }

  const {
    SpecState,
    normalizeRows,
    resetSpecStateForTab,
    deepClone,
    setTableTabSnapshot,
    getTableTabSnapshot
  } = STATE;

  const {
    getSpecApplyBtn,
    getSpecClearBtn,
    ensureBottomClearButton,
    hideAddPanel,
    removeEditSummaryCancelBtn
  } = DOM;

  const {
    buildSpecFilters,
    applySpecFilters,
    clearSpecFilters,
    collectSelectionsFromState,
    updateFilterCount,
    ensureFilterExtras
  } = FILTERS;

  const {
    setupHeaderTitle,
    buildColConfig,
    renderAll
  } = RENDER;

  // =========================
  // helpers
  // =========================
  function isDefaultSpecTab() {
    return SpecState.tabKey === "default_spec_table";
  }

  function isEditSummaryTab() {
    return SpecState.tabKey === "EditSummary";
  }

  function cleanupTransientUIState() {
    hideAddPanel();
    removeEditSummaryCancelBtn();

    SpecState.isEditMode = false;
    SpecState.isAddMode = false;
    SpecState.isDeleteMode = false;
    SpecState.editSummaryCancelBtn = null;
    SpecState.editSummaryBackupRows = null;
  }

  function rebuildCurrentTableUI() {
    ensureFilterExtras();
    buildSpecFilters(null);
    applySpecFilters();
    renderAll();
  }

  function rebuildCurrentTableUIWithSelections() {
    ensureFilterExtras();
    const selections = collectSelectionsFromState();
    buildSpecFilters(selections);
    applySpecFilters();
    renderAll();
  }

  // =========================
  // snapshot / restore
  // =========================
  function snapshotCurrentTableState() {
    if (!SpecState.tabKey) return null;

    return {
      tabKey: SpecState.tabKey,
      config: deepClone(SpecState.config || {}),
      allRows: deepClone(SpecState.allRows || []),
      filteredRows: deepClone(SpecState.filteredRows || []),
      colKeys: deepClone(SpecState.colKeys || []),
      colLabels: deepClone(SpecState.colLabels || {}),
      filterConfig: deepClone(SpecState.filterConfig || {}),
      filterOrder: deepClone(SpecState.filterOrder || []),
      pageSize: SpecState.pageSize || 15,
      currentPage: SpecState.currentPage || 1,
      totalPages: SpecState.totalPages || 1,
      isEditMode: !!SpecState.isEditMode,
      isAddMode: !!SpecState.isAddMode,
      isDeleteMode: !!SpecState.isDeleteMode,
      editSummaryBackupRows: deepClone(SpecState.editSummaryBackupRows || null),
      dateRange: {
        start: DOM.getSpecStartInput ? (DOM.getSpecStartInput()?.value || "") : "",
        end: DOM.getSpecEndInput ? (DOM.getSpecEndInput()?.value || "") : ""
      },
      selections: collectSelectionsFromState()
    };
  }

  function restoreTableState(snapshot) {
    if (!snapshot) return;

    SpecState.tabKey = snapshot.tabKey || null;
    SpecState.config = snapshot.config || {};
    SpecState.allRows = deepClone(snapshot.allRows || []);
    SpecState.filteredRows = deepClone(snapshot.filteredRows || []);
    SpecState.colKeys = deepClone(snapshot.colKeys || []);
    SpecState.colLabels = deepClone(snapshot.colLabels || {});
    SpecState.filterConfig = deepClone(snapshot.filterConfig || {});
    SpecState.filterOrder = deepClone(snapshot.filterOrder || []);
    SpecState.pageSize = snapshot.pageSize || 15;
    SpecState.currentPage = snapshot.currentPage || 1;
    SpecState.totalPages = snapshot.totalPages || 1;
    SpecState.isEditMode = !!snapshot.isEditMode;
    SpecState.isAddMode = !!snapshot.isAddMode;
    SpecState.isDeleteMode = !!snapshot.isDeleteMode;
    SpecState.editSummaryBackupRows = deepClone(snapshot.editSummaryBackupRows || null);

    setupHeaderTitle(SpecState.tabKey, SpecState.config);

    if (isEditSummaryTab()) {
      const s = DOM.getSpecStartInput ? DOM.getSpecStartInput() : null;
      const e = DOM.getSpecEndInput ? DOM.getSpecEndInput() : null;
      if (s) s.value = snapshot.dateRange?.start || "";
      if (e) e.value = snapshot.dateRange?.end || "";
    }

    ensureFilterExtras();
    buildSpecFilters(snapshot.selections || null);
    applySpecFilters();

    SpecState.currentPage = snapshot.currentPage || 1;
    renderAll();
    bindSpecButtons();
    bindHeaderButtons();
    updateFilterCount();

    console.log("[AOI_INSPECTION.TableTab] restored:", {
      tabKey: SpecState.tabKey,
      rows: (SpecState.filteredRows || []).length
    });
  }

  function saveCurrentSnapshot() {
    const snap = snapshotCurrentTableState();
    if (!snap || !snap.tabKey) return;
    setTableTabSnapshot(snap.tabKey, snap);
  }

  // =========================
  // apply / clear
  // =========================
  async function handleApplyClick() {
    if (isEditSummaryTab()) {
      await EDIT_SUMMARY_EDITOR.reloadEditSummaryByDateRange();
      saveCurrentSnapshot();
      return;
    }

    rebuildCurrentTableUIWithSelections();
    saveCurrentSnapshot();
  }

  function handleClearClick() {
    cleanupTransientUIState();
    clearSpecFilters({ clearDates: true, rebuild: true });
    renderAll();
    saveCurrentSnapshot();
  }

  function bindSpecButtons() {
    const btnApply = getSpecApplyBtn();
    const btnClear = getSpecClearBtn();
    const btnBottomClear = ensureBottomClearButton();

    if (btnApply && btnApply.dataset.boundTableTab !== "1") {
      btnApply.dataset.boundTableTab = "1";
      btnApply.addEventListener("click", async () => {
        try {
          await handleApplyClick();
        } catch (err) {
          console.error("[AOI_INSPECTION.TableTab] apply click error:", err);
          alert("套用失敗：" + (err && err.message ? err.message : err));
        }
      });
    }

    if (btnClear && btnClear.dataset.boundTableTab !== "1") {
      btnClear.dataset.boundTableTab = "1";
      btnClear.addEventListener("click", () => {
        try {
          handleClearClick();
        } catch (err) {
          console.error("[AOI_INSPECTION.TableTab] clear click error:", err);
          alert("清空失敗：" + (err && err.message ? err.message : err));
        }
      });
    }

    if (btnBottomClear && btnBottomClear.dataset.boundTableTab !== "1") {
      btnBottomClear.dataset.boundTableTab = "1";
      btnBottomClear.addEventListener("click", () => {
        try {
          handleClearClick();
        } catch (err) {
          console.error("[AOI_INSPECTION.TableTab] bottom clear click error:", err);
          alert("清空失敗：" + (err && err.message ? err.message : err));
        }
      });
    }
  }

  // =========================
  // header buttons
  // =========================
  function bindHeaderButtons() {
    if (SpecState.editBtn && SpecState.editBtn.dataset.boundTableTab !== "1") {
      SpecState.editBtn.dataset.boundTableTab = "1";
      SpecState.editBtn.addEventListener("click", async () => {
        try {
          if (isDefaultSpecTab()) {
            await DEFAULT_EDITOR.handleEditButtonClick();
            saveCurrentSnapshot();
            return;
          }

          if (isEditSummaryTab()) {
            await EDIT_SUMMARY_EDITOR.handleEditButtonClick();
            saveCurrentSnapshot();
          }
        } catch (err) {
          console.error("[AOI_INSPECTION.TableTab] edit button click error:", err);
          alert("操作失敗：" + (err && err.message ? err.message : err));
        }
      });
    }

    if (SpecState.addBtn && SpecState.addBtn.dataset.boundTableTab !== "1") {
      SpecState.addBtn.dataset.boundTableTab = "1";
      SpecState.addBtn.addEventListener("click", () => {
        try {
          if (isDefaultSpecTab()) {
            DEFAULT_EDITOR.handleAuxButtonClick();
            saveCurrentSnapshot();
          }
        } catch (err) {
          console.error("[AOI_INSPECTION.TableTab] add/aux button click error:", err);
          alert("操作失敗：" + (err && err.message ? err.message : err));
        }
      });
    }

    if (SpecState.deleteBtn && SpecState.deleteBtn.dataset.boundTableTab !== "1") {
      SpecState.deleteBtn.dataset.boundTableTab = "1";
      SpecState.deleteBtn.addEventListener("click", () => {
        try {
          if (isDefaultSpecTab()) {
            DEFAULT_EDITOR.onClickDefaultSpecDelete();
            saveCurrentSnapshot();
          }
        } catch (err) {
          console.error("[AOI_INSPECTION.TableTab] delete button click error:", err);
          alert("操作失敗：" + (err && err.message ? err.message : err));
        }
      });
    }

    if (SpecState.editSummaryCancelBtn && SpecState.editSummaryCancelBtn.dataset.boundTableTab !== "1") {
      SpecState.editSummaryCancelBtn.dataset.boundTableTab = "1";
      SpecState.editSummaryCancelBtn.addEventListener("click", () => {
        try {
          if (isEditSummaryTab()) {
            EDIT_SUMMARY_EDITOR.handleCancelButtonClick();
            saveCurrentSnapshot();
          }
        } catch (err) {
          console.error("[AOI_INSPECTION.TableTab] edit summary cancel click error:", err);
          alert("取消失敗：" + (err && err.message ? err.message : err));
        }
      });
    }
  }

  // =========================
  // event entry
  // =========================
  async function handleSubtabTableEvent(ev) {
    const detail = ev && ev.detail ? ev.detail : {};
    const tabKey = detail.tabKey || detail.key || detail.subKey || null;
    const config = detail.config || detail.cfg || {};

    let raw = null;
    if (detail.data !== undefined) {
      raw = detail.data;
    } else if (detail.rows !== undefined) {
      raw = detail.rows;
    } else if (detail.data && Array.isArray(detail.data.rows)) {
      raw = detail.data.rows;
    } else if (detail.payload && Array.isArray(detail.payload.rows)) {
      raw = detail.payload.rows;
    }

    const rows = normalizeRows(raw);

    resetSpecStateForTab(tabKey, config, rows);
    cleanupTransientUIState();

    setupHeaderTitle(tabKey, SpecState.config);

    if (isEditSummaryTab()) {
      EDIT_SUMMARY_EDITOR.initEditSummaryDefaultDateRange();
    } else {
      const s = DOM.getSpecStartInput ? DOM.getSpecStartInput() : null;
      const e = DOM.getSpecEndInput ? DOM.getSpecEndInput() : null;
      if (s) s.value = "";
      if (e) e.value = "";
    }

    buildColConfig(SpecState.config, SpecState.allRows);

    ensureFilterExtras();
    buildSpecFilters(null);
    applySpecFilters();
    renderAll();
    bindSpecButtons();
    bindHeaderButtons();
    updateFilterCount();

    if (isEditSummaryTab()) {
      await EDIT_SUMMARY_EDITOR.reloadEditSummaryByDateRange();
      bindHeaderButtons();
    }

    saveCurrentSnapshot();

    console.log("[AOI_INSPECTION.TableTab] subtab-table loaded:", {
      tabKey,
      rows: rows.length,
      config
    });
  }

  function handleSubtabTableRestoreEvent(ev) {
    const detail = ev?.detail || {};
    const tabKey = detail.tabKey || null;
    const snapshot = detail.snapshot || getTableTabSnapshot(tabKey);

    if (!snapshot) {
      console.warn("[AOI_INSPECTION.TableTab] no snapshot to restore:", tabKey);
      return;
    }

    restoreTableState(snapshot);
  }

  // =========================
  // init
  // =========================
  function init() {
    if (document.__aoiInspectionTableTabInited) return;
    document.__aoiInspectionTableTabInited = true;

    bindSpecButtons();

    document.addEventListener("aoi_inspection:subtab-table", handleSubtabTableEvent);
    document.addEventListener("aoi_inspection:subtab-table-restore", handleSubtabTableRestoreEvent);
  }

  init();

  // =========================
  // export
  // =========================
  NS.init = init;
  NS.bindSpecButtons = bindSpecButtons;
  NS.bindHeaderButtons = bindHeaderButtons;
  NS.handleApplyClick = handleApplyClick;
  NS.handleClearClick = handleClearClick;
  NS.handleSubtabTableEvent = handleSubtabTableEvent;
  NS.snapshotCurrentTableState = snapshotCurrentTableState;
  NS.restoreTableState = restoreTableState;
  NS.saveCurrentSnapshot = saveCurrentSnapshot;
})();