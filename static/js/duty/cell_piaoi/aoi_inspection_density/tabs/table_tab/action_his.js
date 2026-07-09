// static/js/aoi_inspection_density/tabs/table_tab/edit_summary_editor.js
(function () {
  const AOI = (window.AOI_INSPECTION = window.AOI_INSPECTION || {});
  const API = window.AOI_INSPECTION_API;
  const MOD = (AOI.TableTab = AOI.TableTab || {});
  const NS = (MOD.EditSummaryEditor = MOD.EditSummaryEditor || {});

  const STATE = AOI.TableTab && AOI.TableTab.State;
  const DOM = AOI.TableTab && AOI.TableTab.DOM;
  const FILTERS = AOI.TableTab && AOI.TableTab.Filters;
  const RENDER = AOI.TableTab && AOI.TableTab.Render;

  if (!STATE || !DOM || !FILTERS || !RENDER) {
    console.error("[AOI_INSPECTION.TableTab.EditSummaryEditor] missing dependency");
    return;
  }

  const {
    SpecState,
    formatYMD,
    deepClone,
    getNowStr,
    getEditorName,
    normalizeRows
  } = STATE;

  const {
    getSpecStartInput,
    getSpecEndInput,
    getSpecTbodyEl,
    ensureEditSummaryCancelBtn,
    removeEditSummaryCancelBtn
  } = DOM;

  const {
    buildSpecFilters,
    applySpecFilters,
    updateFilterCount
  } = FILTERS;

  const {
    buildColConfig,
    renderHeader,
    renderBody,
    renderPager,
    renderAll
  } = RENDER;

  const EDIT_ROW_KEYS = ["pi_hour", "line_id", "model", "glass_type"];

  // =========================
  // helpers
  // =========================
  function isEditSummaryTab() {
    return SpecState.tabKey === "EditSummary";
  }

  function getActionEditSummaryAPI() {
    return API && typeof API.ActionHisEditor === "function"
      ? API.ActionHisEditor
      : null;
  }

  function getFrontEditorAPI() {
    return API && typeof API.ActionHisEditor === "function"
      ? API.ActionHisEditor
      : null;
  }

  function buildEditRowKey(row) {
    const out = {};
    EDIT_ROW_KEYS.forEach((k) => {
      out[k] = row?.[k] ?? "";
    });
    return out;
  }

  function getDateRangeValues() {
    const s = getSpecStartInput();
    const e = getSpecEndInput();
    return {
      startDate: s ? s.value : "",
      endDate: e ? e.value : ""
    };
  }

  function setDateRangeValues(startDate, endDate) {
    const s = getSpecStartInput();
    const e = getSpecEndInput();
    if (s) s.value = startDate || "";
    if (e) e.value = endDate || "";
  }

  function resetEditSummaryButtonsToDefault() {
    if (SpecState.editBtn) {
      SpecState.editBtn.textContent = "編輯";
    }
    removeEditSummaryCancelBtn();
    SpecState.editSummaryCancelBtn = null;
    SpecState.isEditMode = false;
  }
  /*
  function applyRowsAndRefresh(newRows) {
    SpecState.allRows = (newRows || []).slice();
    SpecState.filteredRows = (newRows || []).slice();
    SpecState.currentPage = 1;
    SpecState.editSummaryBackupRows = null;
    SpecState.isEditMode = false;
    console.log("[EditSummary] tabKey =", SpecState.tabKey);
    console.log("[EditSummary] allRows =", SpecState.allRows);
    console.log("[EditSummary] filteredRows =", SpecState.filteredRows);
    console.log("[EditSummary] firstRow keys =", Object.keys(SpecState.filteredRows?.[0] || {}));
    console.log("[EditSummary] columns =", SpecState.columns);
    console.log("[EditSummary] currentColumns =", SpecState.currentColumns);
    console.log("[EditSummary] tableCols =", SpecState.tableCols);
    console.log("[EditSummary] currentConfig =", SpecState.currentConfig);

    if (SpecState.editBtn) {
      SpecState.editBtn.textContent = "編輯";
    }
    removeEditSummaryCancelBtn();
    SpecState.editSummaryCancelBtn = null;

    buildSpecFilters(null);
    applySpecFilters();
    renderAll();
  }
    */

  function applyRowsAndRefresh(newRows) {
    SpecState.allRows = (newRows || []).slice();
    SpecState.filteredRows = (newRows || []).slice();
    SpecState.currentPage = 1;
    SpecState.editSummaryBackupRows = null;
    SpecState.isEditMode = false;
  
    buildColConfig(SpecState.config, SpecState.allRows);
  
    if (SpecState.editBtn) {
      SpecState.editBtn.textContent = "編輯";
    }
    removeEditSummaryCancelBtn();
    SpecState.editSummaryCancelBtn = null;
  
    buildSpecFilters(null);
    applySpecFilters();
    renderAll();
  }

  // =========================
  // default date range
  // =========================
  function initEditSummaryDefaultDateRange() {
    if (!isEditSummaryTab()) return;

    const today = new Date();
    const endDate = formatYMD(today);

    const startDateObj = new Date(today);
    startDateObj.setDate(startDateObj.getDate() - 3);
    const startDate = formatYMD(startDateObj);

    setDateRangeValues(startDate, endDate);
  }

  // =========================
  // edit mode
  // =========================
  function enterEditSummaryMode() {
    if (!isEditSummaryTab()) return;

    SpecState.editSummaryBackupRows = deepClone(SpecState.allRows || []);
    SpecState.isEditMode = true;

    if (SpecState.editBtn) {
      SpecState.editBtn.textContent = "儲存";
    }

    const cancelBtn = ensureEditSummaryCancelBtn();
    if (cancelBtn) {
      SpecState.editSummaryCancelBtn = cancelBtn;
    }

    renderHeader();
    renderBody();
    renderPager();
  }

  function cancelEditSummaryMode() {
    if (!isEditSummaryTab()) return;

    if (SpecState.editSummaryBackupRows) {
      SpecState.allRows = deepClone(SpecState.editSummaryBackupRows) || [];
      SpecState.filteredRows = (SpecState.allRows || []).slice();
      SpecState.editSummaryBackupRows = null;
    }

    resetEditSummaryButtonsToDefault();
    buildSpecFilters(null);
    applySpecFilters();
    renderAll();
  }

  async function saveEditSummaryEdits() {
    if (!isEditSummaryTab()) return;
    if (!SpecState.isEditMode) return;

    const tbody = getSpecTbodyEl();
    if (!tbody) return;

    const rows = SpecState.filteredRows || [];
    const trs = Array.from(tbody.querySelectorAll("tr"));
    const changes = [];

    trs.forEach((tr) => {
      const idxStr = tr.dataset.rowIndex;
      const rowIndex = Number(idxStr);
      if (Number.isNaN(rowIndex)) return;

      const row = rows[rowIndex];
      if (!row) return;

      const commentInput = tr.querySelector('input[data-field="comment"]');
      const actionInput = tr.querySelector('input[data-field="action"]');

      if (commentInput) {
        const newVal = commentInput.value;
        const oldRaw = row.comment;
        const oldVal = oldRaw == null ? "" : String(oldRaw);

        if (newVal !== oldVal) {
          changes.push({
            row,
            key: "comment",
            oldValue: oldRaw,
            newValue: newVal
          });
          row.comment = newVal;
        }
      }

      if (actionInput) {
        const newVal = actionInput.value;
        const oldRaw = row.action;
        const oldVal = oldRaw == null ? "" : String(oldRaw);

        if (newVal !== oldVal) {
          changes.push({
            row,
            key: "action",
            oldValue: oldRaw,
            newValue: newVal
          });
          row.action = newVal;
        }
      }
    });

    if (!changes.length) {
      SpecState.editSummaryBackupRows = null;
      resetEditSummaryButtonsToDefault();
      renderHeader();
      renderBody();
      renderPager();
      updateFilterCount();
      return;
    }

    const api = getFrontEditorAPI();
    if (!api) {
      alert("後端 editor_summary API 未定義，無法儲存");
      return;
    }

    const editor = getEditorName();
    const modifyTime = getNowStr();

    try {
      for (const ch of changes) {
        const payload = {
          system: "aoi_inspection_density",
          mode: "edit",
          row: buildEditRowKey(ch.row),
          editor,
          modify_time: modifyTime
        };

        if (ch.key === "comment") payload.comment = ch.newValue;
        if (ch.key === "action") payload.action = ch.newValue;

        await api(payload);
      }

      SpecState.editSummaryBackupRows = null;
      resetEditSummaryButtonsToDefault();

      renderHeader();
      renderBody();
      renderPager();
      updateFilterCount();
    } catch (err) {
      console.error("[AOI_INSPECTION.TableTab.EditSummaryEditor] save error:", err);
      alert("儲存失敗：" + (err && err.message ? err.message : err));
    }
  }

  // =========================
  // reload by date range
  // =========================
  async function reloadEditSummaryByDateRange() {
    if (!isEditSummaryTab()) return null;

    const { startDate, endDate } = getDateRangeValues();
    if (!startDate || !endDate) {
      alert("請先選擇起訖日期");
      return null;
    }

    const api = getActionEditSummaryAPI();
    if (!api) {
      console.warn("[AOI_INSPECTION.TableTab.EditSummaryEditor] API.ActionHisEditor 未定義");
      buildSpecFilters(null);
      applySpecFilters();
      renderAll();
      return null;
    }

    const btnApply = DOM.getSpecApplyBtn ? DOM.getSpecApplyBtn() : null;
    const oldText = btnApply ? btnApply.textContent : "";

    try {
      if (btnApply) {
        btnApply.disabled = true;
        btnApply.textContent = "載入中...";
      }

      const payload = {
        mode: "date",
        system: "aoi_inspection_density",
        dates: [startDate, endDate]
      };

      const res = await api(payload);

      let newRows = [];
      if (res && res.DictData) {
        newRows = normalizeRows(res.DictData);
      }

      applyRowsAndRefresh(newRows);
      return newRows.slice();
    } catch (err) {
      console.error("[AOI_INSPECTION.TableTab.EditSummaryEditor] reload error:", err);
      alert("重新載入 EditSummary 資料失敗：" + (err && err.message ? err.message : err));
      return null;
    } finally {
      if (btnApply) {
        btnApply.disabled = false;
        btnApply.textContent = oldText || "套用";
      }
    }
  }

  // =========================
  // click dispatcher
  // =========================
  function handleEditButtonClick() {
    if (!isEditSummaryTab()) return;

    if (!SpecState.isEditMode) {
      enterEditSummaryMode();
      return;
    }

    saveEditSummaryEdits();
  }

  function handleCancelButtonClick() {
    if (!isEditSummaryTab()) return;
    cancelEditSummaryMode();
  }

  // =========================
  // export
  // =========================
  NS.isEditSummaryTab = isEditSummaryTab;

  NS.getDateRangeValues = getDateRangeValues;
  NS.setDateRangeValues = setDateRangeValues;

  NS.initEditSummaryDefaultDateRange = initEditSummaryDefaultDateRange;

  NS.enterEditSummaryMode = enterEditSummaryMode;
  NS.cancelEditSummaryMode = cancelEditSummaryMode;
  NS.saveEditSummaryEdits = saveEditSummaryEdits;

  NS.reloadEditSummaryByDateRange = reloadEditSummaryByDateRange;

  NS.handleEditButtonClick = handleEditButtonClick;
  NS.handleCancelButtonClick = handleCancelButtonClick;
})();
