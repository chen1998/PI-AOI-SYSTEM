// static/js/aoi_inspection_density/tabs/table_tab/render.js
(function () {
    const AOI = (window.AOI_INSPECTION = window.AOI_INSPECTION || {});
    const MOD = (AOI.TableTab = AOI.TableTab || {});
    const NS = (MOD.Render = MOD.Render || {});
  
    const STATE = AOI.TableTab && AOI.TableTab.State;
    const DOM = AOI.TableTab && AOI.TableTab.DOM;
    const FILTERS = AOI.TableTab && AOI.TableTab.Filters;
  
    if (!STATE || !DOM || !FILTERS) {
      console.error("[AOI_INSPECTION.TableTab.Render] missing dependency: State / DOM / Filters");
      return;
    }
  
    const {
      SpecState,
      EDIT_TEXT_LABELS,
      EDIT_SELECT_LABELS,
      EDIT_FILTER_SELECT_LABELS
    } = STATE;
  
    const {
      $,
      createEl,
      getSpecTitleEl,
      getSpecRightEl,
      getSpecTableEl,
      getSpecTheadEl,
      getSpecTbodyEl,
      ensureSpecHeaderActions,
      ensurePager,
      syncTableTabClass
    } = DOM;
  
    const {
      getOptionsForLabel,
      getOptionsFromFilterConfigValues,
      updateFilterCount
    } = FILTERS;
  
    // =========================
    // common utils
    // =========================
    function formatCellValue(v) {
      if (v == null) return "";
      const s = String(v).trim();
      if (!s) return "";
  
      const num = Number(s.replace(/,/g, ""));
      if (!Number.isNaN(num) && Number.isFinite(num)) {
        const fixed = num.toFixed(2);
        if (fixed.endsWith(".00")) {
          return String(Math.round(num));
        }
        return fixed;
      }
  
      return s;
    }
  
    function getHeaderByDataKey(dataKey) {
      return (SpecState.colLabels && SpecState.colLabels[dataKey]) || dataKey;
    }
  
    function isDefaultSpecTab() {
      return SpecState.tabKey === "default_spec_table";
    }
  
    function isEditSummaryTab() {
      return SpecState.tabKey === "EditSummary";
    }
  
    // =========================
    // header / config
    // =========================
    function setupHeaderTitle(tabKey, config) {
      const h2 = getSpecTitleEl();
      if (h2) {
        const name = (config && config.tab_name) || tabKey || "";
        h2.textContent = name;
      }
  
      const dateRow = DOM.getSpecDateRowEl ? DOM.getSpecDateRowEl() : $("#aoi-inspection-density-spec-date-row");
      if (dateRow) {
        dateRow.style.display = (tabKey === "EditSummary") ? "" : "none";
      }
  
      const actions = ensureSpecHeaderActions();
      if (!actions) return;
  
      actions.innerHTML = "";
  
      if (tabKey === "default_spec_table") {
        const editBtn = createEl("button", {
          id: "aoi-inspection-density-spec-edit",
          className: "btn-spec-action",
          text: "編輯"
        });
  
        const addBtn = createEl("button", {
          id: "aoi-inspection-density-spec-add",
          className: "btn-spec-action",
          text: "新增"
        });
  
        const deleteBtn = createEl("button", {
          id: "aoi-inspection-density-spec-delete",
          className: "btn-spec-action",
          text: "刪除"
        });
  
        actions.appendChild(editBtn);
        actions.appendChild(addBtn);
        actions.appendChild(deleteBtn);
        actions.style.display = "";
  
        SpecState.editBtn = editBtn;
        SpecState.addBtn = addBtn;
        SpecState.deleteBtn = deleteBtn;
        return;
      }
  
      if (tabKey === "EditSummary") {
        const editBtn = createEl("button", {
          id: "aoi-inspection-density-spec-edit-summary",
          className: "btn-spec-action",
          text: "編輯"
        });
  
        actions.appendChild(editBtn);
        actions.style.display = "";
  
        SpecState.editBtn = editBtn;
        SpecState.addBtn = null;
        SpecState.deleteBtn = null;
        return;
      }
  
      actions.style.display = "none";
      SpecState.editBtn = null;
      SpecState.addBtn = null;
      SpecState.deleteBtn = null;
    }
  
    function buildColConfig(config, rows) {
      const tc = config && config.table_columns;
      const sample = Array.isArray(rows) && rows.length ? rows[0] : {};
      const colKeys = [];
      const colLabels = {};
  
      if (Array.isArray(tc)) {
        tc.forEach(dataKey => {
          colKeys.push(dataKey);
          colLabels[dataKey] = dataKey;
        });
      } else if (tc && typeof tc === "object") {
        Object.entries(tc).forEach(([k, v]) => {
          let dataKey;
          let header;
  
          const sampleHasK = sample && Object.prototype.hasOwnProperty.call(sample, k);
          const sampleHasV = sample && typeof v === "string" &&
            Object.prototype.hasOwnProperty.call(sample, v);
  
          if (sampleHasV && !sampleHasK) {
            // label -> dataKey
            header = k;
            dataKey = v;
          } else {
            // dataKey -> label
            dataKey = k;
            header = (typeof v === "string" && v) ? v : k;
          }
  
          if (!dataKey) return;
          colKeys.push(dataKey);
          colLabels[dataKey] = header;
        });
      } else {
        Object.keys(sample || {}).forEach(k => {
          colKeys.push(k);
          colLabels[k] = k;
        });
      }
  
      SpecState.colKeys = colKeys;
      SpecState.colLabels = colLabels;
    }
  
    // =========================
    // pagination
    // =========================
    function updatePagination() {
      const total = (SpecState.filteredRows || []).length;
      const size = SpecState.pageSize || 200;
  
      SpecState.totalPages = total ? Math.ceil(total / size) : 1;
  
      if (!SpecState.currentPage || SpecState.currentPage < 1) {
        SpecState.currentPage = 1;
      }
      if (SpecState.currentPage > SpecState.totalPages) {
        SpecState.currentPage = 1;
      }
    }
  
    function getCurrentPageRows() {
      const rows = SpecState.filteredRows || [];
      const size = SpecState.pageSize || 200;
      const start = (SpecState.currentPage - 1) * size;
      const end = start + size;
      return {
        start,
        end,
        rows: rows.slice(start, end)
      };
    }
  
    // =========================
    // cell renderers
    // =========================
    function createEditSummaryInput(dataKey, value) {
      const input = createEl("input", {
        className: "edit-summary-input",
        attrs: {
          type: "text",
          "data-field": dataKey
        }
      });
      input.value = value == null ? "" : String(value);
      return input;
    }
  
    function createDefaultTextInput(dataKey, value) {
      const input = createEl("input", {
        className: "spec-edit-input",
        attrs: {
          type: "text",
          "data-field": dataKey
        }
      });
      input.value = value == null ? "" : String(value);
      return input;
    }
  
    function createDefaultSelectFromFilterValues(header, dataKey, value) {
      const select = createEl("select", {
        className: "spec-edit-select",
        attrs: {
          "data-field": dataKey
        }
      });
  
      const cur = value == null ? "" : String(value);
      const opts = getOptionsFromFilterConfigValues(header);
  
      const ph = createEl("option", {
        text: "-- 請選擇 --",
        attrs: { value: "" }
      });
      select.appendChild(ph);
  
      opts.forEach(optVal => {
        const opt = createEl("option", {
          text: optVal,
          attrs: { value: optVal }
        });
        if (String(optVal) === cur) opt.selected = true;
        select.appendChild(opt);
      });
  
      if (cur && cur !== "" && !opts.includes(cur)) {
        const opt = createEl("option", {
          text: cur,
          attrs: { value: cur }
        });
        opt.selected = true;
        select.appendChild(opt);
      }
  
      if (!cur) select.value = "";
      return select;
    }
  
    function createDefaultSelectFromMDD(header, dataKey, value) {
      const select = createEl("select", {
        className: "spec-edit-select",
        attrs: {
          "data-field": dataKey
        }
      });
  
      const cur = value == null ? "" : String(value);
      const opts = getOptionsForLabel(header);
  
      opts.forEach(optVal => {
        const opt = createEl("option", {
          text: optVal,
          attrs: { value: optVal }
        });
        if (String(optVal) === cur) opt.selected = true;
        select.appendChild(opt);
      });
  
      if (cur && !opts.includes(cur)) {
        const opt = createEl("option", {
          text: cur,
          attrs: { value: cur }
        });
        opt.selected = true;
        select.appendChild(opt);
      }
  
      return select;
    }
  
    function renderEditorCell(td, row) {
      td.classList.add("editor-cell");
      const editorVal = (row && (row.Editor || row.editor)) || "";
      const modifyTime = (row && (row.modify_time || row.modifyTime)) || "";
      td.innerHTML = `${editorVal || ""}${(editorVal && modifyTime) ? "<br>" : ""}${modifyTime || ""}`;
    }
  
    function renderNormalCell(td, value) {
      td.textContent = formatCellValue(value);
    }
  
    function renderDataCell(td, row, dataKey) {
      const header = getHeaderByDataKey(dataKey);
      const value = row && row[dataKey];
  
      if (
        isEditSummaryTab() &&
        SpecState.isEditMode &&
        (dataKey === "comment" || dataKey === "action")
      ) {
        td.appendChild(createEditSummaryInput(dataKey, value));
        return;
      }
  
      if (isDefaultSpecTab() && header === "Editor") {
        renderEditorCell(td, row);
        return;
      }
  
      if (isDefaultSpecTab() && SpecState.isEditMode && EDIT_TEXT_LABELS.has(header)) {
        td.appendChild(createDefaultTextInput(dataKey, value));
        return;
      }
  
      if (isDefaultSpecTab() && SpecState.isEditMode && EDIT_FILTER_SELECT_LABELS.has(header)) {
        td.appendChild(createDefaultSelectFromFilterValues(header, dataKey, value));
        return;
      }
  
      if (isDefaultSpecTab() && SpecState.isEditMode && EDIT_SELECT_LABELS.has(header)) {
        td.appendChild(createDefaultSelectFromMDD(header, dataKey, value));
        return;
      }
  
      renderNormalCell(td, value);
    }
  
    function createDeleteCell(row, globalIndex) {
      const td = createEl("td", { className: "spec-cell-del" });
      const btn = createEl("button", {
        className: "spec-del-btn",
        text: "✕",
        attrs: {
          type: "button",
          title: "刪除此列"
        }
      });
  
      btn.addEventListener("click", async () => {
        const API = window.AOI_INSPECTION_API;
        if (!row) return;
  
        const payload = {
          system: "aoi_inspection_density",
          mode: "delete",
          tabKey: SpecState.tabKey,
          row
        };
  
        try {
          if (API && typeof API.specEditor === "function") {
            await API.specEditor(payload);
          }
  
          SpecState.allRows = (SpecState.allRows || []).filter(x => x !== row);
          SpecState.filteredRows = (SpecState.filteredRows || []).filter(x => x !== row);
  
          updatePagination();
          renderBody();
          renderPager();
          updateFilterCount();
        } catch (err) {
          console.error("[AOI_INSPECTION.TableTab.Render] delete row error:", err);
          alert("刪除失敗：" + (err && err.message ? err.message : err));
        }
      });
  
      td.appendChild(btn);
      return td;
    }
  
    // =========================
    // table render
    // =========================
    function renderHeader() {
      const table = getSpecTableEl();
      const thead = getSpecTheadEl();
      if (!table || !thead) return;
  
      syncTableTabClass(SpecState.tabKey);
  
      thead.innerHTML = "";
      const tr = createEl("tr");
  
      if (isDefaultSpecTab() && SpecState.isDeleteMode) {
        const thDel = createEl("th", {
          className: "spec-col-del",
          text: ""
        });
        tr.appendChild(thDel);
      }
  
      (SpecState.colKeys || []).forEach(dataKey => {
        const th = createEl("th", {
          text: getHeaderByDataKey(dataKey)
        });
        tr.appendChild(th);
      });
  
      thead.appendChild(tr);
    }
  
    function renderBody() {
      const tbody = getSpecTbodyEl();
      if (!tbody) return;
  
      const rows = SpecState.filteredRows || [];
      tbody.innerHTML = "";
  
      if (!rows.length) {
        const tr = createEl("tr");
        let colSpan = Math.max(1, (SpecState.colKeys || []).length);
        if (isDefaultSpecTab() && SpecState.isDeleteMode) {
          colSpan += 1;
        }
  
        const td = createEl("td", {
          className: "muted",
          text: "（無資料）",
          attrs: { colspan: colSpan }
        });
  
        tr.appendChild(td);
        tbody.appendChild(tr);
        return;
      }
  
      const { start, rows: pageRows } = getCurrentPageRows();
  
      pageRows.forEach((row, idxInPage) => {
        const tr = createEl("tr", {
          attrs: {
            "data-row-index": String(start + idxInPage)
          }
        });
  
        const globalIndex = start + idxInPage;
  
        if (isDefaultSpecTab() && SpecState.isDeleteMode) {
          tr.appendChild(createDeleteCell(row, globalIndex));
        }
  
        (SpecState.colKeys || []).forEach(dataKey => {
          const td = createEl("td");
          renderDataCell(td, row, dataKey);
          tr.appendChild(td);
        });
  
        tbody.appendChild(tr);
      });
    }
  
    function renderPager() {
      const pager = ensurePager();
      if (!pager) return;
  
      const total = (SpecState.filteredRows || []).length;
      const pages = SpecState.totalPages || 1;
  
      pager.innerHTML = "";
      pager.style.display = "flex";
  
      const info = createEl("div", {
        className: "aoi-inspection-density-spec-pager-info",
        text: `第 ${SpecState.currentPage} / ${pages} 頁（共 ${total} 筆）`
      });
      pager.appendChild(info);
  
      const btnPrev = createEl("button", {
        text: "上一頁"
      });
      btnPrev.disabled = (pages <= 1) || (SpecState.currentPage <= 1);
      btnPrev.addEventListener("click", () => {
        if (SpecState.currentPage > 1) {
          SpecState.currentPage -= 1;
          renderBody();
          renderPager();
          updateFilterCount();
        }
      });
      pager.appendChild(btnPrev);
  
      const maxPageButtons = 7;
      let start = Math.max(1, SpecState.currentPage - 3);
      let end = Math.min(pages, start + maxPageButtons - 1);
      if ((end - start + 1) < maxPageButtons) {
        start = Math.max(1, end - maxPageButtons + 1);
      }
  
      for (let p = start; p <= end; p++) {
        const btn = createEl("button", {
          className: `page-btn${p === SpecState.currentPage ? " active" : ""}`,
          text: String(p)
        });
  
        btn.disabled = (pages <= 1);
        btn.addEventListener("click", () => {
          if (p === SpecState.currentPage || pages <= 1) return;
          SpecState.currentPage = p;
          renderBody();
          renderPager();
          updateFilterCount();
        });
  
        pager.appendChild(btn);
      }
  
      const btnNext = createEl("button", {
        text: "下一頁"
      });
      btnNext.disabled = (pages <= 1) || (SpecState.currentPage >= pages);
      btnNext.addEventListener("click", () => {
        if (SpecState.currentPage < pages) {
          SpecState.currentPage += 1;
          renderBody();
          renderPager();
          updateFilterCount();
        }
      });
      pager.appendChild(btnNext);
    }
  
    function renderAll() {
      updatePagination();
      renderHeader();
      renderBody();
      renderPager();
      updateFilterCount();
    }
  
    // =========================
    // export
    // =========================
    NS.formatCellValue = formatCellValue;
    NS.getHeaderByDataKey = getHeaderByDataKey;
    NS.isDefaultSpecTab = isDefaultSpecTab;
    NS.isEditSummaryTab = isEditSummaryTab;
  
    NS.setupHeaderTitle = setupHeaderTitle;
    NS.buildColConfig = buildColConfig;
  
    NS.updatePagination = updatePagination;
    NS.getCurrentPageRows = getCurrentPageRows;
  
    NS.renderHeader = renderHeader;
    NS.renderBody = renderBody;
    NS.renderPager = renderPager;
    NS.renderAll = renderAll;
  })();