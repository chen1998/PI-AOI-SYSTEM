// static/js/duty/cell_aoi_to_array/cell_aoi_to_array_table.js
(function () {
  "use strict";

  window.CELL_AOI_TO_ARRAY = window.CELL_AOI_TO_ARRAY || {};
  const MOD = window.CELL_AOI_TO_ARRAY;

  const localState = {
    filters: {},
    openKey: null,
    baseMode: null,
    modeBaseRows: [],
    lastRenderedRows: null,
  
    // body-level filter menu
    floatingMenu: null,
  
    // 避免連續點擊不同 row 時，舊 request 回來覆蓋新 row。
    detailRequestSeq: 0
  };

  MOD.Table = {
    init,
    render,
    renderHead,
    renderBody,
    renderPager,
    setModeText,
    showAll,
    renderActiveRow,
    openDetail
  };

  function init() {
    const { dom } = MOD.State;

    if (dom.returnBtn) {
      dom.returnBtn.addEventListener("click", function () {
        showAll();
      });
    }

    document.addEventListener("click", function (event) {
      if (event.target.closest(".cell-aoi-filter-wrap")) return;
      if (event.target.closest(".cell-aoi-filter-menu")) return;
    
      if (localState.openKey !== null) {
        localState.openKey = null;
        closeFloatingFilterMenu();
        renderHead();
      }
    });
    
    window.addEventListener("resize", function () {
      if (localState.openKey !== null) {
        localState.openKey = null;
        closeFloatingFilterMenu();
        renderHead();
      }
    });
    
    window.addEventListener("scroll", function (event) {
      if (localState.openKey === null) return;
    
      // 如果是在下拉選單內部滾動，不要關閉
      if (event.target && event.target.closest && event.target.closest(".cell-aoi-filter-menu")) {
        return;
      }
    
      // 如果 scroll target 本身就是選單，也不要關閉
      if (event.target && event.target.classList && event.target.classList.contains("cell-aoi-filter-menu")) {
        return;
      }
    
      localState.openKey = null;
      closeFloatingFilterMenu();
      renderHead();
    }, true);
    
    
  }

  function render() {
    const { state } = MOD.State;

    syncModeBaseRows();

    state.tableRows = getFilteredRows();
    localState.lastRenderedRows = state.tableRows;

    renderHead();
    renderBody();
    renderPager();
    updateCount();
    updateReturnButton();
  }

  function syncModeBaseRows() {
    const { state } = MOD.State;

    if (state.tableMode === "all") {
      localState.baseMode = "all";
      localState.modeBaseRows = Array.isArray(state.rows) ? state.rows.slice() : [];
      return;
    }

    const externalRowsChanged = state.tableRows !== localState.lastRenderedRows;

    if (
      localState.baseMode !== state.tableMode ||
      externalRowsChanged ||
      !Array.isArray(localState.modeBaseRows)
    ) {
      localState.baseMode = state.tableMode;
      localState.modeBaseRows = Array.isArray(state.tableRows)
        ? state.tableRows.slice()
        : [];
    }
  }

  function getBaseRows() {
    const { state } = MOD.State;

    if (state.tableMode === "all") {
      return Array.isArray(state.rows) ? state.rows : [];
    }

    return Array.isArray(localState.modeBaseRows)
      ? localState.modeBaseRows
      : [];
  }

  function getFilteredRows() {
    const rows = getBaseRows();
    const filters = localState.filters || {};
    const keys = Object.keys(filters);

    if (!keys.length) return rows.slice();

    return rows.filter(function (row) {
      for (const key of keys) {
        const selected = filters[key];

        if (Array.isArray(selected) && selected.length === 0) {
          return false;
        }

        if (Array.isArray(selected) && selected.length) {
          const val = normalizeValue(row[key], key, row);
          if (!selected.includes(val)) return false;
        }
      }

      return true;
    });
  }

  function renderHead() {
    const { dom } = MOD.State;
    const columns = MOD.State.getTableColumns();
  
    if (!dom.tableHead) return;
  
    closeFloatingFilterMenu();
  
    dom.tableHead.innerHTML = "";
  
    const tr = document.createElement("tr");
  
    columns.forEach(function (col) {
      const th = document.createElement("th");
  
      const head = document.createElement("span");
      head.className = "cell-aoi-filter-head";
  
      const label = document.createElement("span");
      label.textContent = col.label || col.key || "";
      head.appendChild(label);
  
      if (isFilterableColumn(col)) {
        head.appendChild(createFilterWrap(col));
      }
  
      th.appendChild(head);
      tr.appendChild(th);
    });
  
    dom.tableHead.appendChild(tr);
  
    mountOpenFilterMenu();
  }
  

  function isFilterableColumn(col) {
    if (!col || !col.key) return false;
    if (col.label === "詳情") return false;
    if (col.label === "量測時間") return false;
    if (col.key === "test_time") return false;
    if (col.key === "scan_time") return false;
    return true;
  }

  function createFilterWrap(col) {
    const key = col.key;
  
    const wrap = document.createElement("span");
    wrap.className = "cell-aoi-filter-wrap";
  
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "cell-aoi-filter-btn";
    btn.textContent = "▾";
    btn.title = "篩選";
    btn.dataset.filterKey = key;
  
    if (Object.prototype.hasOwnProperty.call(localState.filters, key)) {
      btn.classList.add("active");
    }
  
    btn.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
  
      localState.openKey = localState.openKey === key ? null : key;
      renderHead();
    });
  
    wrap.appendChild(btn);
  
    return wrap;
  }

  function closeFloatingFilterMenu() {
    if (localState.floatingMenu) {
      try {
        localState.floatingMenu.remove();
      } catch (_) {}
      localState.floatingMenu = null;
    }
  
    document.querySelectorAll(".cell-aoi-filter-menu").forEach(function (menu) {
      try {
        menu.remove();
      } catch (_) {}
    });
  }
  
  function mountOpenFilterMenu() {
    if (localState.openKey === null) return;
  
    const columns = MOD.State.getTableColumns();
    const col = (columns || []).find(function (c) {
      return c && c.key === localState.openKey;
    });
  
    if (!col) return;
  
    const selector = `.cell-aoi-filter-btn[data-filter-key="${cssEscape(localState.openKey)}"]`;
    const btn = document.querySelector(selector);
  
    if (!btn) return;
  
    const menu = createFilterMenu(col);
    localState.floatingMenu = menu;
  
    document.body.appendChild(menu);
  
    requestAnimationFrame(function () {
      placeFloatingFilterMenu(btn, menu);
    });
  }
  
  function placeFloatingFilterMenu(btn, menu) {
    if (!btn || !menu) return;
  
    const gap = 6;
    const margin = 8;
  
    menu.style.visibility = "hidden";
    menu.style.display = "block";
    menu.style.left = "0px";
    menu.style.top = "0px";
  
    const btnRect = btn.getBoundingClientRect();
    const menuRect = menu.getBoundingClientRect();
  
    let left = btnRect.right - menuRect.width;
    let top = btnRect.bottom + gap;
  
    if (left < margin) {
      left = margin;
    }
  
    if (left + menuRect.width > window.innerWidth - margin) {
      left = window.innerWidth - menuRect.width - margin;
    }
  
    if (top + menuRect.height > window.innerHeight - margin) {
      top = btnRect.top - menuRect.height - gap;
    }
  
    if (top < margin) {
      top = margin;
    }
  
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
    menu.style.visibility = "";
  }

  
  function createFilterMenu(col) {
    const key = col.key;

    const menu = document.createElement("div");
    menu.className = "cell-aoi-filter-menu";

    menu.addEventListener("click", function (ev) {
      ev.stopPropagation();
    });
    
    menu.addEventListener("wheel", function (ev) {
      ev.stopPropagation();
    }, { passive: true });

    const allOptions = getUniqueOptions(key);
    const selected = getSelectedForKey(key, allOptions);
    const selectedSet = new Set(selected);
    const isAllSelected = allOptions.length > 0 && selected.length === allOptions.length;

    const actions = document.createElement("div");
    actions.className = "cell-aoi-filter-actions";

    const okBtn = document.createElement("button");
    okBtn.type = "button";
    okBtn.className = "btn btn-xs";
    okBtn.textContent = "OK";

    const clearBtn = document.createElement("button");
    clearBtn.type = "button";
    clearBtn.className = "btn btn-xs btn-secondary";
    clearBtn.textContent = "Clear";

    okBtn.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();

      const values = getCheckedValues(menu);

      if (values.length === allOptions.length) {
        delete localState.filters[key];
      } else {
        localState.filters[key] = values;
      }

      localState.openKey = null;
      MOD.State.state.page = 1;
      render();
    });

    clearBtn.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();

      menu.querySelectorAll("input[type='checkbox']").forEach(function (inp) {
        inp.checked = false;
      });

      localState.filters[key] = [];
      MOD.State.state.page = 1;

      render();

      localState.openKey = key;
      renderHead();
    });

    actions.appendChild(okBtn);
    actions.appendChild(clearBtn);
    menu.appendChild(actions);

    menu.appendChild(createCheckOption("__ALL__", "全選", isAllSelected, true));

    if (!allOptions.length) {
      const empty = document.createElement("div");
      empty.className = "cell-aoi-filter-empty";
      empty.textContent = "無可篩選項目";
      menu.appendChild(empty);
    } else {
      allOptions.forEach(function (opt) {
        menu.appendChild(createCheckOption(opt, opt, selectedSet.has(opt), false));
      });
    }

    menu.addEventListener("change", function (ev) {
      const target = ev.target;
      if (!target || target.type !== "checkbox") return;

      if (target.value === "__ALL__") {
        menu
          .querySelectorAll("input[type='checkbox']:not([value='__ALL__'])")
          .forEach(function (inp) {
            inp.checked = target.checked;
          });
        return;
      }

      syncAllCheckbox(menu);
    });

    return menu;
  }

  function createCheckOption(value, text, checked, isAll) {
    const label = document.createElement("label");
    label.className = "cell-aoi-filter-option";

    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = value;
    input.checked = checked;

    if (isAll) input.dataset.all = "1";

    const span = document.createElement("span");
    span.textContent = text;

    label.appendChild(input);
    label.appendChild(span);

    return label;
  }

  function syncAllCheckbox(menu) {
    const all = menu.querySelector("input[value='__ALL__']");
    const items = Array.from(
      menu.querySelectorAll("input[type='checkbox']:not([value='__ALL__'])")
    );

    if (all) {
      all.checked = items.length > 0 && items.every(function (inp) {
        return inp.checked;
      });
    }
  }

  function getCheckedValues(menu) {
    return Array.from(
      menu.querySelectorAll("input[type='checkbox']:not([value='__ALL__'])")
    )
      .filter(function (inp) {
        return inp.checked;
      })
      .map(function (inp) {
        return inp.value;
      });
  }

  function getSelectedForKey(key, allOptions) {
    if (Object.prototype.hasOwnProperty.call(localState.filters, key)) {
      return Array.isArray(localState.filters[key])
        ? localState.filters[key].slice()
        : [];
    }

    return allOptions.slice();
  }

  function getUniqueOptions(key) {
    const set = new Set();

    getBaseRows().forEach(function (row) {
      const v = normalizeValue(row[key], key, row);
      if (v !== "") set.add(v);
    });

    return Array.from(set).sort();
  }

  function renderBody() {
    const { dom, state } = MOD.State;
    const columns = MOD.State.getTableColumns();

    if (!dom.tableBody) return;

    dom.tableBody.innerHTML = "";

    const rows = getPagedRows();

    if (!rows.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");

      td.colSpan = Math.max(columns.length, 1);
      td.className = "cell-aoi-to-array-empty-td";

      if (MOD.UI && MOD.UI.createEmptyState) {
        td.appendChild(MOD.UI.createEmptyState("∅", "目前沒有資料"));
      } else {
        td.textContent = "目前沒有資料";
      }

      tr.appendChild(td);
      dom.tableBody.appendChild(tr);
      return;
    }

    rows.forEach(function (row) {
      MOD.State.ensureRowDefectContainers(row);

      const tr = document.createElement("tr");
      const rowKey = MOD.State.getRowKey(row);

      tr.dataset.rowKey = rowKey;

      if (
        state.selectedRow &&
        MOD.State.getRowKey(state.selectedRow) === rowKey
      ) {
        tr.classList.add("active");
      }

      columns.forEach(function (col) {
        const td = document.createElement("td");

        if (!col.key && col.label === "詳情") {
          td.appendChild(createDetailButton(row));
        } else if (!col.key) {
          td.appendChild(createDetailButton(row));
        } else {
          td.appendChild(createCellContent(row, col));
        }

        tr.appendChild(td);
      });

      dom.tableBody.appendChild(tr);
    });
  }

  function createDetailButton(row) {
    const btn = document.createElement("button");

    btn.type = "button";
    btn.className = "cell-aoi-to-array-detail-btn";
    btn.title = "查看 Sheet 詳細資訊";
    btn.textContent = "🖼";

    btn.addEventListener("click", async function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      await handleDetailClick(row);
    });

    return btn;
  }

  function openDetail(row) {
    if (!row) {
      return Promise.resolve();
    }
  
    return handleDetailClick(row);
  }

  async function handleDetailClick(row) {
    const { state } = MOD.State;

    const requestSeq = ++localState.detailRequestSeq;

    try {
      setLoadingRow(row, true);

      /*
       * 每次點新 row：
       * 1. 先清掉舊 Sheet / Map / Defect Table
       * 2. reset defect table filter = matched
       * 3. reset map filter = same_point + all sizes
       */
      if (MOD.Sheet && typeof MOD.Sheet.clearDetailView === "function") {
        MOD.Sheet.clearDetailView();
      } else {
        fallbackClearDetailView();
      }

      if (MOD.State && typeof MOD.State.resetMapFilters === "function") {
        MOD.State.resetMapFilters();
      }

      if (MOD.DefectTable && typeof MOD.DefectTable.setDefaultMatchedOnly === "function") {
        MOD.DefectTable.setDefaultMatchedOnly();
      }

      state.selectedRow = null;
      state.currentSheetDefects = [];

      renderActiveRow("");

      const result = await MOD.API.fetchDetailData(row);

      // 若期間又點了另一列，舊結果直接丟棄。
      if (requestSeq !== localState.detailRequestSeq) {
        return;
      }

      if (!MOD.Sheet || typeof MOD.Sheet.applyDetailResult !== "function") {
        console.error("[cell-aoi-to-array-table] MOD.Sheet not ready:", {
          Sheet: MOD.Sheet,
          MOD
        });

        throw new Error(
          "CELL_AOI_TO_ARRAY.Sheet 尚未載入，請確認 cell_aoi_to_array_sheet.js 有載入，且順序在 table.js / charts.js / main.js 前面"
        );
      }

      MOD.Sheet.applyDetailResult(row, result);

      state.selectedRow = row;
      state.currentSheetDefects = Array.isArray(row.defects) ? row.defects : [];

      renderActiveRow(MOD.State.getRowKey(row));

      if (typeof MOD.Sheet.render === "function") {
        MOD.Sheet.render(row);
      }

      /*
       * 預載完整 defect groups：
       * - /detail 已經有 point_detail，可立即 render same_point 星號與 defect table。
       * - /detail-defect-groups 再拿完整 cell_aoi/source group。
       * - 拿到後不主動勾選、不主動 render 顯示，只存進 row.defectGroups。
       */
      if (MOD.Sheet && typeof MOD.Sheet.preloadFullDefectGroups === "function") {
        MOD.Sheet.preloadFullDefectGroups(row);
      }
    } catch (err) {
      console.error("[cell-aoi-to-array-table] fetch detail failed:", err);

      if (requestSeq === localState.detailRequestSeq) {
        if (MOD.UI && MOD.UI.toast) {
          MOD.UI.toast(`讀取詳情失敗：${err.message || err}`);
        } else {
          alert(`讀取詳情失敗：${err.message || err}`);
        }

        if (MOD.Sheet && typeof MOD.Sheet.renderEmpty === "function") {
          MOD.Sheet.renderEmpty();
        }
      }
    } finally {
      setLoadingRow(row, false);
    }
  }

  function fallbackClearDetailView() {
    const { dom } = MOD.State || {};
    if (!dom) return;

    if (dom.sheetDetail) {
      dom.sheetDetail.innerHTML = "";
    }

    if (dom.defectTableHead) {
      dom.defectTableHead.innerHTML = "";
    }

    if (dom.defectTableBody) {
      dom.defectTableBody.innerHTML = "";
    }

    if (dom.defectListWrap) {
      dom.defectListWrap.style.display = "none";
    }

    if (dom.defectListCount) {
      dom.defectListCount.textContent = "Total 0 defects";
    }
  }

  function setLoadingRow(row, loading) {
    const key = MOD.State.getRowKey(row);
    const { dom } = MOD.State;

    if (!dom.tableBody || !key) return;

    const tr = dom.tableBody.querySelector(`tr[data-row-key="${cssEscape(key)}"]`);
    if (!tr) return;

    const btn = tr.querySelector(".cell-aoi-to-array-detail-btn");
    if (!btn) return;

    btn.disabled = Boolean(loading);
    btn.textContent = loading ? "讀取中" : "🖼";
  }

  function createCellContent(row, col) {
    const span = document.createElement("span");
    const value = getDisplayValue(row, col.key);

    span.textContent = value;

    if (col.key === "same_point_rate" || col.key === "match_rate") {
      span.className = getRateClass(row);
    }

    if (col.key === "match_status") {
      span.className = getStatusClass(value);
    }

    if (
      col.key === "sheet_id_chip_id" ||
      col.key === "sheet_id" ||
      col.key === "cassette_id"
    ) {
      span.classList.add("cell-aoi-to-array-mono");
    }

    if (col.key === "test_time" || col.key === "scan_time" || col.key === "source_scan_time") {
      span.classList.add("cell-aoi-to-array-nowrap");
    }

    span.title = String(value || "");

    return span;
  }

  function getDisplayValue(row, key) {
    let value = row?.[key];

    if ((value == null || value === "") && row?.detail) {
      value = row.detail[key];
    }

    if (key === "same_point_rate" || key === "match_rate") {
      return formatRate(value);
    }

    if (
      key === "total_defect_qty" ||
      key === "same_point_defect_cnt" ||
      key === "source_defect_cnt"
    ) {
      return value == null || value === "" ? "0" : String(value);
    }

    if (value == null || value === "") {
      return "-";
    }

    return String(value);
  }

  function formatRate(value, row) {
    if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
      return "-";
    }
  
    const n = Number(value);
    return `${(n * 100).toFixed(2)}%`;
  }

  function getRateClass(row) {
    const rate = Number(row?.same_point_rate ?? row?.match_rate);

    if (!Number.isFinite(rate)) {
      return "cell-aoi-to-array-rate cell-aoi-to-array-rate-na";
    }

    const pct = rate <= 1 ? rate * 100 : rate;

    if (pct == 0) {
      return "cell-aoi-to-array-rate cell-aoi-to-array-rate-good";
    }

    /*if (pct >= 50) {
      return "cell-aoi-to-array-rate cell-aoi-to-array-rate-mid";
    }*/

    return "cell-aoi-to-array-rate cell-aoi-to-array-rate-low";
  }

  function getStatusClass(value) {
    const s = String(value || "").toUpperCase();

    if (s === "MATCHED") {
      return "cell-aoi-to-array-status cell-aoi-to-array-status-ok";
    }

    if (s === "NO_SAME_POINT") {
      return "cell-aoi-to-array-status cell-aoi-to-array-status-warn";
    }

    if (s === "SOURCE_NOT_FOUND") {
      return "cell-aoi-to-array-status cell-aoi-to-array-status-bad";
    }

    return "cell-aoi-to-array-status";
  }

  function renderPager() {
    const { dom, state } = MOD.State;

    if (!dom.pager) return;

    dom.pager.innerHTML = "";

    const total = state.tableRows.length;
    const pageSize = state.pageSize || 10;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));

    if (state.page > totalPages) {
      state.page = totalPages;
    }

    dom.pager.appendChild(createPageButton("‹", state.page - 1, state.page <= 1));

    getPagerPages(state.page, totalPages).forEach(function (page) {
      if (page === "...") {
        const span = document.createElement("span");
        span.className = "cell-aoi-to-array-page-ellipsis";
        span.textContent = "...";
        dom.pager.appendChild(span);
        return;
      }

      const btn = createPageButton(String(page), page, false);
      btn.classList.toggle("active", page === state.page);
      dom.pager.appendChild(btn);
    });

    dom.pager.appendChild(createPageButton("›", state.page + 1, state.page >= totalPages));
  }

  function getPagerPages(current, total) {
    if (MOD.UI && typeof MOD.UI.getPagerPages === "function") {
      return MOD.UI.getPagerPages(current, total);
    }

    const pages = [];

    if (total <= 7) {
      for (let i = 1; i <= total; i += 1) pages.push(i);
      return pages;
    }

    pages.push(1);

    if (current > 4) pages.push("...");

    const start = Math.max(2, current - 1);
    const end = Math.min(total - 1, current + 1);

    for (let i = start; i <= end; i += 1) {
      pages.push(i);
    }

    if (current < total - 3) pages.push("...");

    pages.push(total);

    return pages;
  }

  function createPageButton(text, page, disabled) {
    const btn = document.createElement("button");

    btn.type = "button";
    btn.className = "cell-aoi-to-array-page-btn";
    btn.textContent = text;
    btn.disabled = disabled;

    btn.addEventListener("click", function () {
      if (disabled) return;

      MOD.State.state.page = page;
      render();
    });

    return btn;
  }

  function getPagedRows() {
    const { state } = MOD.State;
    const pageSize = state.pageSize || 10;
    const start = (state.page - 1) * pageSize;
    const end = start + pageSize;

    return state.tableRows.slice(start, end);
  }

  function updateCount() {
    const { dom, state } = MOD.State;

    if (dom.totalCount) {
      dom.totalCount.textContent = `Total ${state.tableRows.length} items`;
    }
  }

  function updateReturnButton() {
    const { dom, state } = MOD.State;

    if (!dom.returnBtn) return;

    dom.returnBtn.style.display = state.tableMode === "all" ? "none" : "";
  }

  function setModeText(text) {
    const { dom, state } = MOD.State;

    if (dom.tableMode) {
      dom.tableMode.textContent = text || (state.tableMode === "all" ? "All Data" : state.tableMode);
    }
  }

  function showAll() {
    const { state } = MOD.State;

    state.tableMode = "all";
    state.tableRows = Array.isArray(state.rows) ? state.rows.slice() : [];
    state.page = 1;
    state.selectedRow = null;
    state.currentSheetDefects = [];

    localState.filters = {};
    localState.openKey = null;
    closeFloatingFilterMenu();
    localState.baseMode = "all";
    localState.modeBaseRows = state.tableRows.slice();
    localState.lastRenderedRows = null;

    setModeText("All Data");
    render();

    if (MOD.Sheet && typeof MOD.Sheet.renderEmpty === "function") {
      MOD.Sheet.renderEmpty();
    } else {
      console.warn("[cell-aoi-to-array-table] MOD.Sheet.renderEmpty not ready:", MOD.Sheet);
    }
  }

  function renderActiveRow(activeKey) {
    const { dom } = MOD.State;

    if (!dom.tableBody) return;

    dom.tableBody.querySelectorAll("tr[data-row-key]").forEach(function (tr) {
      tr.classList.toggle("active", tr.dataset.rowKey === activeKey);
    });
  }

  function normalizeValue(v, key, row) {
    if (v == null && row?.detail && key) {
      v = row.detail[key];
    }

    if (v == null) return "";

    if (key === "same_point_rate" || key === "match_rate") {
      return formatRate(v);
    }

    return String(v);
  }

  function cssEscape(value) {
    if (window.CSS && window.CSS.escape) {
      return window.CSS.escape(value);
    }

    return String(value).replace(/["\\]/g, "\\$&");
  }
})();

