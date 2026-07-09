// static/js/aoi_inspection_density/tabs/table_tab/default_spec_editor.js
(function () {
  const AOI = (window.AOI_INSPECTION = window.AOI_INSPECTION || {});
  const API = window.AOI_INSPECTION_API;
  const MOD = (AOI.TableTab = AOI.TableTab || {});
  const NS = (MOD.DefaultSpecEditor = MOD.DefaultSpecEditor || {});

  const STATE = AOI.TableTab && AOI.TableTab.State;
  const DOM = AOI.TableTab && AOI.TableTab.DOM;
  const FILTERS = AOI.TableTab && AOI.TableTab.Filters;
  const RENDER = AOI.TableTab && AOI.TableTab.Render;

  if (!STATE || !DOM || !FILTERS || !RENDER) {
    console.error("[AOI_INSPECTION.TableTab.DefaultSpecEditor] missing dependency");
    return;
  }

  const {
    SpecState,
    EDIT_TEXT_LABELS,
    EDIT_SELECT_LABELS,
    EDIT_FILTER_SELECT_LABELS,
    getNowStr,
    getEditorName
  } = STATE;

  const {
    $,
    createEl,
    clearEl,
    ensureAddPanel,
    hideAddPanel
  } = DOM;

  const {
    getOptionsForLabel,
    getOptionsFromFilterConfigValues,
    rebuildFiltersWithCurrentSelections,
    rebuildFiltersFromScratch,
    updateFilterCount
  } = FILTERS;

  const {
    renderHeader,
    renderBody,
    renderPager,
    renderAll
  } = RENDER;

  const SPEC_IDENTITY_KEYS = ["line_id", "model", "glass_type", "defect_size"];

  // =========================
  // helpers
  // =========================
  function isDefaultSpecTab() {
    return SpecState.tabKey === "default_spec_table";
  }

  function getSpecEditor() {
    return API && typeof API.specEditor === "function"
      ? API.specEditor
      : null;
  }

  function buildIdentityFromRow(row) {
    const out = {};
    SPEC_IDENTITY_KEYS.forEach((k) => {
      out[k] = row?.[k] ?? "";
    });
    return out;
  }

  function sameIdentity(a, b) {
    return SPEC_IDENTITY_KEYS.every((k) => String(a?.[k] ?? "") === String(b?.[k] ?? ""));
  }

  function hideHeaderButtons() {
    if (SpecState.editBtn) SpecState.editBtn.style.display = "none";
    if (SpecState.addBtn) SpecState.addBtn.style.display = "none";
    if (SpecState.deleteBtn) SpecState.deleteBtn.style.display = "none";
  }

  function resetHeaderButtonsDefault() {
    if (SpecState.editBtn) {
      SpecState.editBtn.style.display = "";
      SpecState.editBtn.textContent = "編輯";
    }
    if (SpecState.addBtn) {
      SpecState.addBtn.style.display = "";
      SpecState.addBtn.textContent = "新增";
    }
    if (SpecState.deleteBtn) {
      SpecState.deleteBtn.style.display = "";
      SpecState.deleteBtn.textContent = "刪除";
    }
  }

  function exitDeleteMode() {
    SpecState.isDeleteMode = false;

    if (SpecState.editBtn) {
      SpecState.editBtn.style.display = "";
      SpecState.editBtn.textContent = "編輯";
    }
    if (SpecState.addBtn) {
      SpecState.addBtn.style.display = "";
      SpecState.addBtn.textContent = "新增";
    }
    if (SpecState.deleteBtn) {
      SpecState.deleteBtn.style.display = "";
      SpecState.deleteBtn.textContent = "刪除";
    }

    renderHeader();
    renderBody();
    renderPager();
  }

  function hideAndClearAddPanel() {
    hideAddPanel();
  }

  function getRowByTr(tr) {
    if (!tr) return null;
    const idxStr = tr.dataset.rowIndex;
    const rowIndex = Number(idxStr);
    if (Number.isNaN(rowIndex)) return null;
    const rows = SpecState.filteredRows || [];
    return rows[rowIndex] || null;
  }

  // =========================
  // edit mode
  // =========================
  async function saveDefaultSpecEdits() {
    if (!isDefaultSpecTab() || !SpecState.isEditMode) return;

    const tbody = DOM.getSpecTbodyEl();
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

      const identity = buildIdentityFromRow(row);
      const patch = {};
      const old = {};

      const inputs = tr.querySelectorAll(
        'input.spec-edit-input[data-field], select.spec-edit-select[data-field]'
      );

      inputs.forEach((inp) => {
        const field = inp.dataset.field;
        const newVal = inp.value;
        const oldRaw = row[field];
        const oldVal = oldRaw == null ? "" : String(oldRaw);

        if (newVal !== oldVal) {
          patch[field] = newVal;
          old[field] = oldRaw;
        }
      });

      if (Object.keys(patch).length) {
        changes.push({
          rowIndex,
          identity,
          patch,
          old
        });
      }
    });

    if (changes.length) {
      const modifyTime = getNowStr();
      const editor = getEditorName();
      const api = getSpecEditor();

      if (!api) {
        alert("specEditor API 未定義，無法儲存");
        return;
      }

      try {
        await api({
          system: "aoi_inspection_density",
          mode: "edit",
          tabKey: SpecState.tabKey,
          Editor: editor,
          modify_time: modifyTime,
          changes
        });
      } catch (err) {
        console.error("[AOI_INSPECTION.TableTab.DefaultSpecEditor] save edit error:", err);
        alert("儲存失敗：" + (err && err.message ? err.message : err));
        return;
      }

      changes.forEach((ch) => {
        const row = rows[ch.rowIndex];
        if (!row) return;

        Object.entries(ch.patch || {}).forEach(([k, v]) => {
          row[k] = v;
        });

        row.Editor = editor;
        row.modify_time = modifyTime;
      });

      // 同步回 allRows
      SpecState.allRows = (SpecState.allRows || []).map((r) => {
        const hit = changes.find((ch) => sameIdentity(r, ch.identity));
        if (!hit) return r;

        const next = { ...r };
        Object.entries(hit.patch || {}).forEach(([k, v]) => {
          next[k] = v;
        });
        next.Editor = editor;
        next.modify_time = modifyTime;
        return next;
      });
    }

    SpecState.isEditMode = false;

    if (SpecState.editBtn) SpecState.editBtn.textContent = "編輯";
    if (SpecState.addBtn) SpecState.addBtn.textContent = "新增";
    if (SpecState.deleteBtn) SpecState.deleteBtn.textContent = "刪除";

    renderHeader();
    renderBody();
    renderPager();
    updateFilterCount();
  }

  function cancelDefaultSpecEditMode() {
    if (!isDefaultSpecTab() || !SpecState.isEditMode) return;

    SpecState.isEditMode = false;

    if (SpecState.editBtn) SpecState.editBtn.textContent = "編輯";
    if (SpecState.addBtn) SpecState.addBtn.textContent = "新增";
    if (SpecState.deleteBtn) SpecState.deleteBtn.textContent = "刪除";

    renderHeader();
    renderBody();
    renderPager();
  }

  function enterDefaultSpecEditMode() {
    if (!isDefaultSpecTab()) return;

    if (SpecState.isAddMode) {
      SpecState.isAddMode = false;
      hideAndClearAddPanel();
    }

    if (SpecState.isDeleteMode) {
      SpecState.isDeleteMode = false;
    }

    SpecState.isEditMode = true;

    if (SpecState.editBtn) {
      SpecState.editBtn.textContent = "儲存";
      SpecState.editBtn.style.display = "";
    }
    if (SpecState.addBtn) {
      SpecState.addBtn.textContent = "取消";
      SpecState.addBtn.style.display = "";
    }
    if (SpecState.deleteBtn) {
      SpecState.deleteBtn.textContent = "刪除";
      SpecState.deleteBtn.style.display = "";
    }

    renderHeader();
    renderBody();
  }

  // =========================
  // add panel
  // =========================
  function buildAddInputByHeader(header, dataKey) {
    let inputEl;

    if (EDIT_TEXT_LABELS.has(header)) {
      inputEl = createEl("input", {
        className: "spec-add-input",
        attrs: {
          type: "text",
          "data-field": dataKey,
          "data-label": header
        }
      });
      return inputEl;
    }

    if (EDIT_FILTER_SELECT_LABELS.has(header)) {
      inputEl = createEl("select", {
        className: "spec-add-input",
        attrs: {
          "data-field": dataKey,
          "data-label": header
        }
      });

      inputEl.appendChild(createEl("option", {
        text: "-- 請選擇 --",
        attrs: { value: "" }
      }));

      const opts = getOptionsFromFilterConfigValues(header);
      (opts || []).forEach((v) => {
        inputEl.appendChild(createEl("option", {
          text: v,
          attrs: { value: v }
        }));
      });

      inputEl.value = "";
      return inputEl;
    }

    if (EDIT_SELECT_LABELS.has(header)) {
      inputEl = createEl("select", {
        className: "spec-add-input",
        attrs: {
          "data-field": dataKey,
          "data-label": header
        }
      });

      inputEl.appendChild(createEl("option", {
        text: "-- 請選擇 --",
        attrs: { value: "" }
      }));

      const opts = getOptionsForLabel(header);
      (opts || []).forEach((v) => {
        inputEl.appendChild(createEl("option", {
          text: v,
          attrs: { value: v }
        }));
      });

      inputEl.value = "";
      return inputEl;
    }

    inputEl = createEl("input", {
      className: "spec-add-input",
      attrs: {
        type: "text",
        "data-field": dataKey,
        "data-label": header
      }
    });
    return inputEl;
  }

  function showAddPanel() {
    if (!isDefaultSpecTab()) return;

    const panel = ensureAddPanel();
    if (!panel) return;

    SpecState.isAddMode = true;
    SpecState.isEditMode = false;
    SpecState.isDeleteMode = false;

    clearEl(panel);
    hideHeaderButtons();

    const addTable = createEl("table", { className: "spec-add-table" });
    const thead = createEl("thead");
    const headTr = createEl("tr");
    const tbody = createEl("tbody");
    const bodyTr = createEl("tr");

    (SpecState.colKeys || []).forEach((dataKey) => {
      const header = (SpecState.colLabels && SpecState.colLabels[dataKey]) || dataKey;
      if (header === "Editor") return;
      if (header === "modify_time") return;

      const th = createEl("th", { text: header });
      headTr.appendChild(th);

      const td = createEl("td");
      const inputEl = buildAddInputByHeader(header, dataKey);
      td.appendChild(inputEl);
      bodyTr.appendChild(td);
    });

    thead.appendChild(headTr);
    tbody.appendChild(bodyTr);
    addTable.appendChild(thead);
    addTable.appendChild(tbody);

    const footer = createEl("div", { className: "spec-add-footer" });

    const btnCancel = createEl("button", {
      className: "btn btn-xs btn-secondary",
      text: "取消",
      attrs: { type: "button" }
    });

    const btnSave = createEl("button", {
      className: "btn btn-xs",
      text: "儲存",
      attrs: { type: "button" }
    });

    footer.appendChild(btnCancel);
    footer.appendChild(btnSave);

    panel.appendChild(addTable);
    panel.appendChild(footer);
    panel.style.display = "";

    btnCancel.addEventListener("click", () => {
      SpecState.isAddMode = false;
      hideAndClearAddPanel();
      resetHeaderButtonsDefault();
    });

    btnSave.addEventListener("click", async () => {
      const inputs = panel.querySelectorAll("[data-field]");
      const newRow = {};
      const emptyLabels = [];

      inputs.forEach((inp) => {
        const field = inp.dataset.field;
        const label = inp.dataset.label || field;
        const value = (inp.value || "").trim();

        if (!value) emptyLabels.push(label);
        newRow[field] = value;
      });

      if (emptyLabels.length) {
        alert("以下欄位不得為空：\n" + emptyLabels.join("、"));
        return;
      }

      const editor = getEditorName();
      const modifyTime = getNowStr();
      const api = getSpecEditor();

      newRow.Editor = editor;
      newRow.modify_time = modifyTime;

      if (!api) {
        alert("specEditor API 未定義，無法新增");
        return;
      }

      try {
        await api({
          system: "aoi_inspection_density",
          mode: "add",
          tabKey: SpecState.tabKey,
          Editor: editor,
          modify_time: modifyTime,
          row: newRow
        });
      } catch (err) {
        console.error("[AOI_INSPECTION.TableTab.DefaultSpecEditor] add row error:", err);
        alert("新增失敗：" + (err && err.message ? err.message : err));
        return;
      }

      SpecState.allRows.push(newRow);
      SpecState.isAddMode = false;
      hideAndClearAddPanel();
      resetHeaderButtonsDefault();

      rebuildFiltersWithCurrentSelections();
      renderAll();
    });
  }

  // =========================
  // delete
  // =========================
  async function deleteDefaultSpecRow(row) {
    if (!isDefaultSpecTab() || !row) return;

    const api = getSpecEditor();
    if (!api) {
      alert("specEditor API 未定義，無法刪除");
      return;
    }

    const editor = getEditorName();
    const modifyTime = getNowStr();
    const identity = buildIdentityFromRow(row);

    try {
      await api({
        system: "aoi_inspection_density",
        mode: "delete",
        tabKey: SpecState.tabKey,
        Editor: editor,
        modify_time: modifyTime,
        row: identity
      });
    } catch (err) {
      console.error("[AOI_INSPECTION.TableTab.DefaultSpecEditor] delete row error:", err);
      alert("刪除失敗：" + (err && err.message ? err.message : err));
      return;
    }

    SpecState.allRows = (SpecState.allRows || []).filter((r) => !sameIdentity(r, identity));
    SpecState.filteredRows = (SpecState.filteredRows || []).filter((r) => !sameIdentity(r, identity));

    rebuildFiltersFromScratch();
    renderAll();
  }

  function bindDeleteRowClicks() {
    const tbody = DOM.getSpecTbodyEl();
    if (!tbody) return;

    if (tbody.dataset.defaultSpecDeleteBound === "1") return;
    tbody.dataset.defaultSpecDeleteBound = "1";

    tbody.addEventListener("click", async (ev) => {
      if (!SpecState.isDeleteMode) return;

      const btn = ev.target.closest("[data-action='delete-row']");
      if (!btn) return;

      const tr = btn.closest("tr");
      const row = getRowByTr(tr);
      if (!row) return;

      await deleteDefaultSpecRow(row);
    });
  }

  // =========================
  // click handlers
  // =========================
  function onClickDefaultSpecAdd() {
    if (!isDefaultSpecTab()) return;

    if (SpecState.isEditMode) {
      cancelDefaultSpecEditMode();
    }

    if (SpecState.isDeleteMode) {
      exitDeleteMode();
    }

    if (SpecState.isAddMode) return;
    showAddPanel();
  }

  function onClickDefaultSpecDelete() {
    if (!isDefaultSpecTab()) return;

    if (!SpecState.isDeleteMode) {
      SpecState.isDeleteMode = true;
      SpecState.isEditMode = false;
      SpecState.isAddMode = false;

      hideAndClearAddPanel();

      if (SpecState.editBtn) {
        SpecState.editBtn.style.display = "none";
      }
      if (SpecState.addBtn) {
        SpecState.addBtn.style.display = "none";
      }
      if (SpecState.deleteBtn) {
        SpecState.deleteBtn.textContent = "取消";
        SpecState.deleteBtn.style.display = "";
      }
    } else {
      exitDeleteMode();
      return;
    }

    renderHeader();
    renderBody();
    renderPager();
    bindDeleteRowClicks();
  }

  function handleEditButtonClick() {
    if (!isDefaultSpecTab()) return;

    if (!SpecState.isEditMode) {
      enterDefaultSpecEditMode();
      return;
    }

    saveDefaultSpecEdits();
  }

  function handleAuxButtonClick() {
    if (!isDefaultSpecTab()) return;

    if (SpecState.isEditMode) {
      cancelDefaultSpecEditMode();
      return;
    }

    onClickDefaultSpecAdd();
  }

  // =========================
  // export
  // =========================
  NS.buildIdentityFromRow = buildIdentityFromRow;
  NS.sameIdentity = sameIdentity;
  NS.deleteDefaultSpecRow = deleteDefaultSpecRow;
  NS.bindDeleteRowClicks = bindDeleteRowClicks;

  NS.hideHeaderButtons = hideHeaderButtons;
  NS.resetHeaderButtonsDefault = resetHeaderButtonsDefault;

  NS.enterDefaultSpecEditMode = enterDefaultSpecEditMode;
  NS.saveDefaultSpecEdits = saveDefaultSpecEdits;
  NS.cancelDefaultSpecEditMode = cancelDefaultSpecEditMode;

  NS.showAddPanel = showAddPanel;

  NS.onClickDefaultSpecAdd = onClickDefaultSpecAdd;
  NS.onClickDefaultSpecDelete = onClickDefaultSpecDelete;

  NS.handleEditButtonClick = handleEditButtonClick;
  NS.handleAuxButtonClick = handleAuxButtonClick;
})();