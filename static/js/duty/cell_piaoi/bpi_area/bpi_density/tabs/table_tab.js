// static/js/bpi_density/tabs/table_tab.js
(function () {
  const AOI = (window.AOI_BPI_DENSITY = window.AOI_BPI_DENSITY || {});
  const API = window.AOI_BPI_DENSITY_API;
  const $ = (sel, root = document) => root.querySelector(sel);

  const editor = window.USER || window.editor || "預設";

  const Spec = {
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
    lastTabClass: null,
    isEditMode: false,
    isAddMode: false,
    isDeleteMode: false,
    editBtn: null,
    addBtn: null,
    deleteBtn: null
  };

  const EDIT_TEXT_LABELS = new Set(["MODEL_ID", "OOC", "OOS"]);
  const EDIT_SELECT_LABELS = new Set([
    "GLASS_TYPE",
    "SIZE_TYPE"
  ]);

  // =========================
  // cache
  // =========================
  function getTableCacheRoot() {
    const st = AOI.state || (AOI.state = {});
    if (!st.tableStateCache) st.tableStateCache = {};
    return st.tableStateCache;
  }

  function cloneSetMap(src) {
    const out = {};
    Object.entries(src || {}).forEach(([k, v]) => {
      out[k] = new Set(Array.from(v || []).map(String));
    });
    return out;
  }

  function saveCurrentTableState() {
    if (!Spec.tabKey) return;

    const cacheRoot = getTableCacheRoot();
    cacheRoot[Spec.tabKey] = {
      tabKey: Spec.tabKey,
      config: Spec.config,
      allRows: Array.isArray(Spec.allRows) ? Spec.allRows.slice() : [],
      filteredRows: Array.isArray(Spec.filteredRows) ? Spec.filteredRows.slice() : [],
      colKeys: Array.isArray(Spec.colKeys) ? Spec.colKeys.slice() : [],
      colLabels: { ...(Spec.colLabels || {}) },
      filterConfig: Spec.filterConfig || {},
      filterOrder: Array.isArray(Spec.filterOrder) ? Spec.filterOrder.slice() : [],
      currentPage: Spec.currentPage || 1,
      totalPages: Spec.totalPages || 1,
      pageSize: Spec.pageSize || 200,
      lastTabClass: Spec.lastTabClass || null,
      isEditMode: !!Spec.isEditMode,
      isAddMode: !!Spec.isAddMode,
      isDeleteMode: !!Spec.isDeleteMode,
      selections: cloneSetMap(collectSelectionsFromState())
    };
  }

  function restoreTableState(tabKey) {
    const cacheRoot = getTableCacheRoot();
    const cache = cacheRoot[tabKey];
    if (!cache) return false;

    Spec.tabKey = cache.tabKey || tabKey;
    Spec.config = cache.config || {};
    Spec.allRows = Array.isArray(cache.allRows) ? cache.allRows.slice() : [];
    Spec.filteredRows = Array.isArray(cache.filteredRows) ? cache.filteredRows.slice() : [];
    Spec.colKeys = Array.isArray(cache.colKeys) ? cache.colKeys.slice() : [];
    Spec.colLabels = { ...(cache.colLabels || {}) };
    Spec.filterConfig = cache.filterConfig || {};
    Spec.filterOrder = Array.isArray(cache.filterOrder) ? cache.filterOrder.slice() : [];
    Spec.currentPage = cache.currentPage || 1;
    Spec.totalPages = cache.totalPages || 1;
    Spec.pageSize = cache.pageSize || 200;
    Spec.lastTabClass = cache.lastTabClass || null;
    Spec.isEditMode = !!cache.isEditMode;
    Spec.isAddMode = !!cache.isAddMode;
    Spec.isDeleteMode = !!cache.isDeleteMode;

    setupHeaderTitle(Spec.tabKey, Spec.config);
    renderHeader();
    buildSpecFilters(cache.selections || null);
    applySpecFilter();

    const panel = $("#aoi-bpi-density-spec-add-panel");
    if (panel && !Spec.isAddMode) panel.style.display = "none";

    if (Spec.tabKey === "default_spec_table") {
      if (Spec.isEditMode) {
        if (Spec.editBtn) Spec.editBtn.textContent = "儲存";
        if (Spec.addBtn) Spec.addBtn.textContent = "取消";
        if (Spec.deleteBtn) Spec.deleteBtn.textContent = "刪除";
      } else if (Spec.isDeleteMode) {
        if (Spec.editBtn) Spec.editBtn.style.display = "none";
        if (Spec.addBtn) Spec.addBtn.style.display = "none";
        if (Spec.deleteBtn) Spec.deleteBtn.textContent = "取消";
      } else {
        restoreHeaderButtonsDefault();
      }
    }

    return true;
  }

  // =========================
  // ids / helpers
  // =========================
  function specSelectIdOf(key) {
    return `aoi-bpi-density-spec-f-${key}`;
  }

  function specHostIdOf(key) {
    return `aoi-bpi-density-spec-host-${key}`;
  }

  function getNowStr() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }

  function formatCellValue(v) {
    if (v == null) return "";
    const s = String(v).trim();
    if (!s) return "";

    const num = Number(s.replace(/,/g, ""));
    if (!Number.isNaN(num) && Number.isFinite(num)) {
      const fixed = num.toFixed(2);
      if (fixed.endsWith(".00")) return String(Math.round(num));
      return fixed;
    }
    return s;
  }

  function resolveRowsFromAny(raw) {
    if (!raw) return [];
    if (Array.isArray(raw)) return raw;
    if (raw && typeof raw === "object") return Object.values(raw);
    return [];
  }

  // =========================
  // DOM ensure
  // =========================
  function ensureSpecDynHosts() {
    const aside = $("#aoi-bpi-density-spec-right");
    if (!aside) return null;

    let dyn = $("#aoi-bpi-density-spec-dynhosts");
    if (!dyn) {
      dyn = document.createElement("div");
      dyn.id = "aoi-bpi-density-spec-dynhosts";
      aside.appendChild(dyn);
    }
    return dyn;
  }

  function ensurePager() {
    const wrap = $("#aoi-bpi-density-spec-left .table-wrap");
    if (!wrap) return null;

    let pager = $("#aoi-bpi-density-spec-pager");
    if (!pager) {
      pager = document.createElement("div");
      pager.id = "aoi-bpi-density-spec-pager";
      pager.className = "aoi_spec-pager";
      wrap.appendChild(pager);
    }
    return pager;
  }

  function ensureFilterCountSpan() {
    const title = $("#aoi-bpi-density-spec-right .spec-filter-panel-title")
      || $("#aoi-bpi-density-spec-right .aoi-bpi-density-spec-filter-panel-title");
    if (!title) return null;

    let span = $("#aoi-bpi-density-spec-count");
    if (!span) {
      span = document.createElement("span");
      span.id = "aoi-bpi-density-spec-count";
      span.className = "spec-filter-count";
      title.appendChild(span);
    }
    return span;
  }

  function ensureBottomClearButton() {
    const aside = $("#aoi-bpi-density-spec-right");
    if (!aside) return null;

    let box = aside.querySelector(".spec-filter-bottom-actions");
    if (!box) {
      box = document.createElement("div");
      box.className = "spec-filter-bottom-actions";

      const btn = document.createElement("button");
      btn.id = "aoi-bpi-density-spec-clear-bottom";
      btn.className = "btn btn-xs btn-secondary";
      btn.textContent = "清空篩選";

      box.appendChild(btn);
      aside.appendChild(box);
    }

    return $("#aoi-bpi-density-spec-clear-bottom");
  }

  function ensureAddPanel() {
    let panel = $("#aoi-bpi-density-spec-add-panel");
    if (panel) return panel;

    const left = $("#aoi-bpi-density-spec-left");
    if (!left) return null;

    panel = document.createElement("section");
    panel.id = "aoi-bpi-density-spec-add-panel";
    panel.className = "card-sub spec-add-panel";
    panel.style.display = "none";

    const tableWrap = left.querySelector(".table-wrap");
    if (tableWrap) {
      left.insertBefore(panel, tableWrap);
    } else {
      left.appendChild(panel);
    }

    return panel;
  }

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

  // =========================
  // header buttons
  // =========================
  function restoreHeaderButtonsDefault() {
    Spec.isEditMode = false;
    Spec.isAddMode = false;
    Spec.isDeleteMode = false;

    if (Spec.editBtn) {
      Spec.editBtn.style.display = "";
      Spec.editBtn.textContent = "編輯";
    }
    if (Spec.addBtn) {
      Spec.addBtn.style.display = "";
      Spec.addBtn.textContent = "新增";
    }
    if (Spec.deleteBtn) {
      Spec.deleteBtn.style.display = "";
      Spec.deleteBtn.textContent = "刪除";
    }
  }

  function bindHeaderButtons() {
    if (Spec.editBtn) Spec.editBtn.onclick = onClickEdit;
    if (Spec.addBtn) Spec.addBtn.onclick = onClickAdd;
    if (Spec.deleteBtn) Spec.deleteBtn.onclick = onClickDelete;
  }

  function setupHeaderTitle(tabKey, config) {
    const h2 = $("#aoi-bpi-density-spec-info .aoi-bpi-density-spec-info-head .t");
    if (h2) {
      const name = (config && config.tab_name) || tabKey || "";
      h2.textContent = name;
    }

    const dateBlock = $("#aoi-bpi-density-spec-right .spec-filter-item");
    if (dateBlock) {
      if (tabKey === "default_spec_table") {
        dateBlock.style.display = "none";
      } else {
        dateBlock.style.display = "";
      }
    }

    const head = $("#aoi-bpi-density-spec-info .aoi-bpi-density-spec-info-head");
    if (!head) return;

    let actions = head.querySelector(".spec-header-actions");
    if (!actions) {
      actions = document.createElement("div");
      actions.className = "spec-header-actions";
      head.appendChild(actions);
    }

    actions.innerHTML = "";

    if (tabKey === "default_spec_table") {
      const editBtn = document.createElement("button");
      editBtn.id = "aoi-bpi-density-spec-edit";
      editBtn.className = "btn-spec-action";
      editBtn.textContent = "編輯";

      const addBtn = document.createElement("button");
      addBtn.id = "aoi-bpi-density-spec-add";
      addBtn.className = "btn-spec-action";
      addBtn.textContent = "新增";

      const deleteBtn = document.createElement("button");
      deleteBtn.id = "aoi-bpi-density-spec-delete";
      deleteBtn.className = "btn-spec-action";
      deleteBtn.textContent = "刪除";

      actions.appendChild(editBtn);
      actions.appendChild(addBtn);
      actions.appendChild(deleteBtn);
      actions.style.display = "";

      Spec.editBtn = editBtn;
      Spec.addBtn = addBtn;
      Spec.deleteBtn = deleteBtn;

      bindHeaderButtons();
    } else {
      actions.style.display = "none";
      Spec.editBtn = null;
      Spec.addBtn = null;
      Spec.deleteBtn = null;
      Spec.isEditMode = false;
      Spec.isAddMode = false;
      Spec.isDeleteMode = false;

      const panel = $("#aoi-bpi-density-spec-add-panel");
      if (panel) panel.style.display = "none";
    }
  }

  // =========================
  // columns
  // =========================
  function buildColConfig(config, rows) {
    const tc = config && config.table_columns;
    const sample = Array.isArray(rows) && rows.length ? rows[0] : {};
    const colKeys = [];
    const colLabels = {};

    if (Array.isArray(tc)) {
      tc.forEach((dataKey) => {
        colKeys.push(dataKey);
        colLabels[dataKey] = dataKey;
      });
    } else if (tc && typeof tc === "object") {
      Object.entries(tc).forEach(([k, v]) => {
        let dataKey;
        let header;

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

    Spec.colKeys = colKeys;
    Spec.colLabels = colLabels;
  }

  // =========================
  // filters
  // =========================
  function getOptionsForLabel(label) {
    const cfg = Spec.filterConfig && Spec.filterConfig[label];
    if (!cfg) return [];

    if (Array.isArray(cfg.values) && cfg.values.length) {
      return cfg.values.slice();
    }

    const dataKey = cfg.key || label;
    const wrap = Spec.mdd[dataKey];
    if (!wrap || !Array.isArray(wrap.options)) return [];
    return wrap.options.slice();
  }

  function collectSelectionsFromState() {
    const out = {};
    Object.entries(Spec.mdd || {}).forEach(([dataKey, wrap]) => {
      if (!wrap || !wrap.mdd) return;
      const sel = wrap.mdd.getSelected ? wrap.mdd.getSelected() : [];
      out[dataKey] = new Set((sel || []).map(String));
    });
    return out;
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

  function buildSpecFilters(prevSelections) {
    const colDict = Spec.filterConfig || {};
    const labels = Spec.filterOrder.length ? Spec.filterOrder : Object.keys(colDict || {});
    const dynHosts = ensureSpecDynHosts();
    if (!dynHosts) return;

    dynHosts.innerHTML = "";
    Spec.mdd = {};

    if (!labels.length) {
      Spec.filteredRows = (Spec.allRows || []).slice();
      applySpecFilter();
      return;
    }

    if (!AOI.MultiDD) {
      console.error("[bpi_spec] AOI.MultiDD 未載入");
      Spec.filteredRows = (Spec.allRows || []).slice();
      applySpecFilter();
      return;
    }

    labels.forEach((label, idx) => {
      const cfg = colDict[label] || {};
      const dataKey = cfg.key || label;

      let baseRows = Spec.allRows || [];
      if (prevSelections && idx > 0) {
        labels.slice(0, idx).forEach((prevLabel) => {
          const pcfg = colDict[prevLabel] || {};
          const pKey = pcfg.key || prevLabel;
          const set = prevSelections[pKey];
          if (!set || !set.size) return;

          baseRows = baseRows.filter((r) => {
            if (!r) return false;
            const v = r[pKey];
            const s = v == null ? "" : String(v);
            return set.has(s);
          });
        });
      }

      const uniqSet = new Set();
      (baseRows || []).forEach((r) => {
        if (!r) return;
        const v = r[dataKey];
        if (v === undefined || v === null || v === "") return;
        uniqSet.add(String(v));
      });

      const uniqArr = Array.from(uniqSet).sort();

      let opts;
      const cfgVals = Array.isArray(cfg.values) ? cfg.values.slice() : [];
      if (cfgVals.length) {
        opts = cfgVals.filter((v) => uniqSet.has(String(v)));
      } else {
        opts = uniqArr;
      }

      if (!opts.length) return;

      const host = document.createElement("div");
      host.className = "multi-dd-host";
      host.id = specHostIdOf(dataKey);
      dynHosts.appendChild(host);

      const mdd = new AOI.MultiDD({
        hostId: host.id,
        selectId: specSelectIdOf(dataKey),
        options: opts,
        title: label,
        onChange: () => {
          Spec.currentPage = 1;
          applySpecFilter();
        }
      });

      const prevSet = prevSelections && prevSelections[dataKey];
      let selected;
      if (prevSet && prevSet.size) {
        const intersect = opts.filter((o) => prevSet.has(String(o)));
        selected = intersect.length ? intersect : opts.slice();
      } else {
        selected = opts.slice();
      }

      if (selected.length && mdd.setSelected) {
        mdd.setSelected(selected);
      }

      Spec.mdd[dataKey] = { mdd, options: opts };
      wireSearchForHost(host);
    });
  }

  function getActiveFilters() {
    const out = {};
    Object.entries(Spec.mdd || {}).forEach(([dataKey, wrap]) => {
      if (!wrap || !wrap.mdd) return;
      const sel = wrap.mdd.getSelected ? wrap.mdd.getSelected() : [];
      if (sel.length) out[dataKey] = new Set(sel.map(String));
    });
    return out;
  }

  function updateFilterCount() {
    const span = ensureFilterCountSpan();
    if (!span) return;
    const total = Spec.filteredRows.length || 0;
    span.textContent = `( ${total} 筆 )`;
  }

  // =========================
  // pager
  // =========================
  function updatePagination() {
    const total = Spec.filteredRows.length || 0;
    const size = Spec.pageSize || 200;
    Spec.totalPages = total ? Math.ceil(total / size) : 1;
    if (!Spec.currentPage || Spec.currentPage > Spec.totalPages) {
      Spec.currentPage = 1;
    }
  }

  function renderPager() {
    const pager = ensurePager();
    if (!pager) return;

    const total = Spec.filteredRows.length || 0;
    const pages = Spec.totalPages || 1;

    pager.innerHTML = "";
    pager.style.display = "flex";

    const info = document.createElement("div");
    info.className = "aoi_spec-pager-info";
    info.textContent = `第 ${Spec.currentPage} / ${pages} 頁（共 ${total} 筆）`;
    pager.appendChild(info);

    const btnPrev = document.createElement("button");
    btnPrev.textContent = "上一頁";
    btnPrev.disabled = (pages <= 1) || (Spec.currentPage <= 1);
    btnPrev.addEventListener("click", () => {
      if (Spec.currentPage > 1) {
        Spec.currentPage -= 1;
        renderBody();
        renderPager();
        updateFilterCount();
        saveCurrentTableState();
      }
    });
    pager.appendChild(btnPrev);

    const maxPageButtons = 7;
    let start = Math.max(1, Spec.currentPage - 3);
    let end = Math.min(pages, start + maxPageButtons - 1);
    if (end - start + 1 < maxPageButtons) {
      start = Math.max(1, end - maxPageButtons + 1);
    }

    for (let p = start; p <= end; p++) {
      const btn = document.createElement("button");
      btn.textContent = String(p);
      btn.className = "page-btn" + (p === Spec.currentPage ? " active" : "");
      btn.disabled = (pages <= 1);
      btn.addEventListener("click", () => {
        if (p === Spec.currentPage || pages <= 1) return;
        Spec.currentPage = p;
        renderBody();
        renderPager();
        updateFilterCount();
        saveCurrentTableState();
      });
      pager.appendChild(btn);
    }

    const btnNext = document.createElement("button");
    btnNext.textContent = "下一頁";
    btnNext.disabled = (pages <= 1) || (Spec.currentPage >= pages);
    btnNext.addEventListener("click", () => {
      if (Spec.currentPage < pages) {
        Spec.currentPage += 1;
        renderBody();
        renderPager();
        updateFilterCount();
        saveCurrentTableState();
      }
    });
    pager.appendChild(btnNext);
  }

  // =========================
  // render
  // =========================
  function renderHeader() {
    const table = $("#aoi-bpi-density-spec-table-main");
    if (!table) return;

    const thead = ensureThead(table);

    if (Spec.lastTabClass) table.classList.remove(Spec.lastTabClass);
    if (Spec.tabKey) {
      table.classList.add(Spec.tabKey);
      Spec.lastTabClass = Spec.tabKey;
    }

    thead.innerHTML = "";
    const tr = document.createElement("tr");

    const isDefault = Spec.tabKey === "default_spec_table";
    if (isDefault && Spec.isDeleteMode) {
      const thDel = document.createElement("th");
      thDel.className = "spec-col-del";
      thDel.textContent = "";
      tr.appendChild(thDel);
    }

    (Spec.colKeys || []).forEach((dataKey) => {
      const th = document.createElement("th");
      th.textContent = Spec.colLabels[dataKey] || dataKey;
      tr.appendChild(th);
    });

    thead.appendChild(tr);
  }

  function renderBody() {
    const table = $("#aoi-bpi-density-spec-table-main");
    if (!table) return;

    const tbody = ensureTbody(table);
    const rows = Spec.filteredRows || [];
    tbody.innerHTML = "";

    const isDefault = Spec.tabKey === "default_spec_table";

    if (!rows.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      let colSpan = Math.max(1, Spec.colKeys.length);
      if (isDefault && Spec.isDeleteMode) colSpan += 1;
      td.colSpan = colSpan;
      td.className = "muted";
      td.textContent = "（無資料）";
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    const size = Spec.pageSize || 200;
    const start = (Spec.currentPage - 1) * size;
    const end = start + size;
    const pageRows = rows.slice(start, end);

    pageRows.forEach((r, idxInPage) => {
      const tr = document.createElement("tr");
      const globalIndex = start + idxInPage;
      tr.dataset.rowIndex = String(globalIndex);

      if (isDefault && Spec.isDeleteMode) {
        const tdDel = document.createElement("td");
        tdDel.className = "spec-cell-del";

        const btnDel = document.createElement("button");
        btnDel.type = "button";
        btnDel.className = "spec-del-btn";
        btnDel.textContent = "✕";
        btnDel.title = "刪除此列";

        btnDel.addEventListener("click", async () => {
          const row = rows[globalIndex];
          if (!row) return;

          const payload = {
            system: "bpi_density",
            mode: "delete",
            tabKey: Spec.tabKey,
            row
          };

          try {
            if (API?.FrontSpecEditor) {
              console.log('del', payload);
              const res = await API.FrontSpecEditor(payload);
              console.log("[bpi_spec] delete result", res);
            }

            Spec.allRows = Spec.allRows.filter((x) => x !== row);
            Spec.filteredRows = Spec.filteredRows.filter((x) => x !== row);
            updatePagination();
            renderHeader();
            renderBody();
            renderPager();
            updateFilterCount();
            saveCurrentTableState();
          } catch (err) {
            console.error("[bpi_spec] delete error", err);
            alert("刪除失敗：" + (err && err.message ? err.message : err));
          }
        });

        tdDel.appendChild(btnDel);
        tr.appendChild(tdDel);
      }

      (Spec.colKeys || []).forEach((dataKey) => {
        const td = document.createElement("td");
        const header = Spec.colLabels[dataKey] || dataKey;
        const v = r && r[dataKey];

        if (isDefault && header === "Editor") {
          td.classList.add("editor-cell");
          const e = (r && (r.Editor || r.editor)) || "";
          const mtime = (r && (r.modify_time || r.modifyTime)) || "";
          td.innerHTML = `${e || ""}${(e && mtime) ? "<br>" : ""}${mtime || ""}`;
        } else if (isDefault && Spec.isEditMode && EDIT_TEXT_LABELS.has(header)) {
          const input = document.createElement("input");
          input.type = "text";
          input.className = "spec-edit-input";
          input.value = v == null ? "" : String(v);
          input.dataset.field = dataKey;
          td.appendChild(input);
        } else if (isDefault && Spec.isEditMode && EDIT_SELECT_LABELS.has(header)) {
          const select = document.createElement("select");
          select.className = "spec-edit-select";
          select.dataset.field = dataKey;

          const opts = getOptionsForLabel(header);
          const cur = v == null ? "" : String(v);

          opts.forEach((optVal) => {
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
        } else {
          const isActionHistoryLongText =
            Spec.tabKey === "EditSummary" &&
            (dataKey === "comment" || dataKey === "action");
        
          if (isActionHistoryLongText) {
            td.classList.add("bpi-action-history-longtext-cell");
        
            const box = document.createElement("div");
            box.className = "bpi-action-history-longtext-box";
            box.textContent = v == null ? "" : String(v);
        
            td.appendChild(box);
          } else {
            td.textContent = formatCellValue(v);
          }
        }
        

        tr.appendChild(td);
      });

      tbody.appendChild(tr);
    });
  }

  // =========================
  // filter apply
  // =========================
  function applySpecFilter() {
    const filters = getActiveFilters();
    const rows = Spec.allRows || [];
    const fKeys = Object.keys(filters);

    if (!fKeys.length) {
      Spec.filteredRows = rows.slice();
    } else {
      Spec.filteredRows = rows.filter((r) => {
        for (const dataKey of fKeys) {
          const set = filters[dataKey];
          const v = (r && r[dataKey] != null) ? String(r[dataKey]) : "";
          if (!set.has(v)) return false;
        }
        return true;
      });
    }

    updatePagination();
    renderBody();
    renderPager();
    updateFilterCount();
    saveCurrentTableState();
  }

  // =========================
  // edit / add / delete
  // =========================
  function saveEditChanges() {
    if (!Spec.isEditMode) return;

    const table = $("#aoi-bpi-density-spec-table-main");
    if (!table) return;

    const tbody = ensureTbody(table);

    const ROW_ID_KEYS = [
      "model",
      "glass_type",
      "defect_size"
    ];

    const pending = new Map();
    const rows = Spec.filteredRows || [];
    const trs = Array.from(tbody.querySelectorAll("tr"));

    trs.forEach((tr) => {
      const idxStr = tr.dataset.rowIndex;
      const rowIndex = Number(idxStr);
      if (Number.isNaN(rowIndex)) return;

      const row = rows[rowIndex];
      if (!row) return;

      const inputs = tr.querySelectorAll(
        "input.spec-edit-input[data-field], select.spec-edit-select[data-field]"
      );

      inputs.forEach((inp) => {
        const field = inp.dataset.field;
        const newVal = inp.value ?? "";
        const oldValRaw = row[field];
        const oldVal = oldValRaw == null ? "" : String(oldValRaw);

        if (String(newVal) !== oldVal) {
          if (!pending.has(rowIndex)) {
            pending.set(rowIndex, {
              rowIndex,
              identity: {},
              patch: {},
              old: {}
            });
          }

          const item = pending.get(rowIndex);
          item.patch[field] = newVal;
          item.old[field] = oldValRaw;

          row[field] = newVal;
        }
      });

      if (pending.has(rowIndex)) {
        const item = pending.get(rowIndex);
        const identity = {};
        ROW_ID_KEYS.forEach((k) => {
          if (Object.prototype.hasOwnProperty.call(item.old, k)) {
            identity[k] = item.old[k];
          } else {
            identity[k] = (row && row[k] != null) ? row[k] : "";
          }
        });
        item.identity = identity;
      }
    });

    const changes = Array.from(pending.values());
    if (changes.length) {
      const modifyTime = getNowStr();

      changes.forEach((ch) => {
        const r = rows[ch.rowIndex];
        if (r) {
          r.Editor = editor;
          r.modify_time = modifyTime;
        }
      });

      const payload = {
        system: "bpi_density",
        mode: "edit",
        tabKey: Spec.tabKey,
        Editor: editor,
        modify_time: modifyTime,
        changes
      };

      if (API?.FrontSpecEditor) {
        console.log('edit', payload);
        API.FrontSpecEditor(payload)
          .then((res) => {
            console.log("[bpi_spec] edit result", res);
          })
          .catch((err) => {
            console.error("[bpi_spec] edit error", err);
            alert("儲存失敗：" + (err && err.message ? err.message : err));
          });
      }
    }

    Spec.isEditMode = false;
    if (Spec.editBtn) Spec.editBtn.textContent = "編輯";
    if (Spec.addBtn) Spec.addBtn.textContent = "新增";

    renderBody();
    saveCurrentTableState();
  }

  function cancelEditMode() {
    if (!Spec.isEditMode) return;
    Spec.isEditMode = false;
    if (Spec.editBtn) Spec.editBtn.textContent = "編輯";
    if (Spec.addBtn) Spec.addBtn.textContent = "新增";
    renderBody();
    saveCurrentTableState();
  }

  function showAddPanel() {
    const panel = ensureAddPanel();
    if (!panel) return;

    panel.innerHTML = "";

    const addTable = document.createElement("table");
    addTable.className = "spec-add-table";

    const thead = document.createElement("thead");
    const headTr = document.createElement("tr");
    const tbody = document.createElement("tbody");
    const bodyTr = document.createElement("tr");

    (Spec.colKeys || []).forEach((dataKey) => {
      const header = Spec.colLabels[dataKey] || dataKey;
      if (header === "Editor") return;

      const th = document.createElement("th");
      th.textContent = header;
      headTr.appendChild(th);

      const td = document.createElement("td");
      let inputEl;

      if (EDIT_TEXT_LABELS.has(header)) {
        inputEl = document.createElement("input");
        inputEl.type = "text";
      } else if (EDIT_SELECT_LABELS.has(header)) {
        inputEl = document.createElement("select");

        const ph = document.createElement("option");
        ph.value = "";
        ph.textContent = "-- 請選擇 --";
        inputEl.appendChild(ph);

        const opts = getOptionsForLabel(header);
        (opts || []).forEach((v) => {
          const opt = document.createElement("option");
          opt.value = v;
          opt.textContent = v;
          inputEl.appendChild(opt);
        });

        inputEl.value = "";
      } else {
        inputEl = document.createElement("input");
        inputEl.type = "text";
      }

      inputEl.dataset.field = dataKey;
      inputEl.dataset.label = header;
      inputEl.className = "spec-add-input";

      td.appendChild(inputEl);
      bodyTr.appendChild(td);
    });

    thead.appendChild(headTr);
    tbody.appendChild(bodyTr);
    addTable.appendChild(thead);
    addTable.appendChild(tbody);

    const footer = document.createElement("div");
    footer.className = "spec-add-footer";

    const btnSave = document.createElement("button");
    btnSave.type = "button";
    btnSave.className = "btn btn-xs";
    btnSave.textContent = "儲存";

    const btnCancel = document.createElement("button");
    btnCancel.type = "button";
    btnCancel.className = "btn btn-xs btn-secondary";
    btnCancel.textContent = "取消";

    footer.appendChild(btnCancel);
    footer.appendChild(btnSave);

    panel.appendChild(addTable);
    panel.appendChild(footer);

    function closeAddMode() {
      Spec.isAddMode = false;
      panel.style.display = "none";
      restoreHeaderButtonsDefault();
    }

    btnCancel.addEventListener("click", closeAddMode);

    btnSave.addEventListener("click", async () => {
      const inputs = panel.querySelectorAll("[data-field]");
      const newRow = {};
      const emptyLabels = [];

      inputs.forEach((inp) => {
        const field = inp.dataset.field;
        const label = inp.dataset.label || field;
        const val = (inp.value || "").trim();
        if (!val) emptyLabels.push(label);
        newRow[field] = val;
      });

      if (emptyLabels.length) {
        alert("以下欄位不得為空：\n" + emptyLabels.join("、"));
        return;
      }

      const modifyTime = getNowStr();
      newRow.Editor = editor;
      newRow.modify_time = modifyTime;

      const payload = {
        system: "bpi_density",
        mode: "add",
        tabKey: Spec.tabKey,
        Editor: editor,
        modify_time: modifyTime,
        row: newRow
      };

      try {
        if (API?.FrontSpecEditor) {
          console.log('add', payload);
          const res = await API.FrontSpecEditor(payload);
          console.log("[bpi_spec] add result", res);
        }

        Spec.allRows.push(newRow);
        applySpecFilter();
        closeAddMode();
        saveCurrentTableState();
      } catch (err) {
        console.error("[bpi_spec] add error", err);
        alert("新增失敗：" + (err && err.message ? err.message : err));
      }
    });

    panel.style.display = "";
  }

  function onClickEdit() {
    if (Spec.tabKey !== "default_spec_table") return;

    if (Spec.isAddMode) {
      const panel = $("#aoi-bpi-density-spec-add-panel");
      if (panel) panel.style.display = "none";
      Spec.isAddMode = false;
    }

    if (!Spec.isEditMode) {
      Spec.isEditMode = true;
      Spec.isDeleteMode = false;

      if (Spec.editBtn) {
        Spec.editBtn.textContent = "儲存";
        Spec.editBtn.style.display = "";
      }
      if (Spec.addBtn) {
        Spec.addBtn.textContent = "取消";
        Spec.addBtn.style.display = "";
      }
      if (Spec.deleteBtn) {
        Spec.deleteBtn.textContent = "刪除";
        Spec.deleteBtn.style.display = "";
      }

      renderHeader();
      renderBody();
      saveCurrentTableState();
      return;
    }

    saveEditChanges();
  }

  function onClickAdd() {
    if (Spec.tabKey !== "default_spec_table") return;

    if (Spec.isEditMode) {
      cancelEditMode();
      return;
    }

    if (!Spec.isAddMode) {
      Spec.isAddMode = true;
      Spec.isEditMode = false;
      Spec.isDeleteMode = false;

      if (Spec.editBtn) Spec.editBtn.style.display = "none";
      if (Spec.addBtn) Spec.addBtn.style.display = "none";
      if (Spec.deleteBtn) Spec.deleteBtn.style.display = "none";

      showAddPanel();
    } else {
      Spec.isAddMode = false;
      const panel = $("#aoi-bpi-density-spec-add-panel");
      if (panel) panel.style.display = "none";
      restoreHeaderButtonsDefault();
    }
    saveCurrentTableState();
  }

  function onClickDelete() {
    if (Spec.tabKey !== "default_spec_table") return;

    if (!Spec.isDeleteMode) {
      Spec.isDeleteMode = true;
      Spec.isEditMode = false;
      Spec.isAddMode = false;

      const panel = $("#aoi-bpi-density-spec-add-panel");
      if (panel) panel.style.display = "none";

      if (Spec.editBtn) Spec.editBtn.style.display = "none";
      if (Spec.addBtn) Spec.addBtn.style.display = "none";
      if (Spec.deleteBtn) {
        Spec.deleteBtn.textContent = "取消";
        Spec.deleteBtn.style.display = "";
      }
    } else {
      Spec.isDeleteMode = false;

      if (Spec.editBtn) {
        Spec.editBtn.style.display = "";
        Spec.editBtn.textContent = "編輯";
      }
      if (Spec.addBtn) {
        Spec.addBtn.style.display = "";
        Spec.addBtn.textContent = "新增";
      }
      if (Spec.deleteBtn) {
        Spec.deleteBtn.textContent = "刪除";
      }
    }

    renderHeader();
    renderBody();
    renderPager();
    saveCurrentTableState();
  }

  // =========================
  // buttons
  // =========================
  let btnBound = false;

  function clearAllFilters() {
    const s = $("#aoi-bpi-density-spec-start");
    const e = $("#aoi-bpi-density-spec-end");
    if (s) s.value = "";
    if (e) e.value = "";

    buildSpecFilters(null);
    Spec.currentPage = 1;
    applySpecFilter();
    saveCurrentTableState();
  }

  function bindSpecButtons() {
    if (btnBound) return;
    btnBound = true;

    const btnApply = $("#aoi-bpi-density-spec-apply");
    const btnClear = $("#aoi-bpi-density-spec-clear");
    const btnBottomClear = ensureBottomClearButton();

    if (btnApply) {
      btnApply.addEventListener("click", () => {
        const curSel = collectSelectionsFromState();
        buildSpecFilters(curSel);
        Spec.currentPage = 1;
        applySpecFilter();
      });
    }

    if (btnClear) btnClear.addEventListener("click", clearAllFilters);
    if (btnBottomClear) btnBottomClear.addEventListener("click", clearAllFilters);
  }

  // =========================
  // event: normal spec table
  // =========================
  document.addEventListener("aoi-bpi-density:subtab-table", (ev) => {
    const detail = ev.detail || {};

    const tabKey = detail.tabKey || detail.key || detail.subKey || null;
    const config = detail.config || detail.cfg || {};
    const restoreOnly = !!detail.restoreOnly;

    bindSpecButtons();

    if (restoreOnly && tabKey) {
      const ok = restoreTableState(tabKey);
      if (ok) return;
    }

    let raw = null;
    if (detail.data !== undefined) raw = detail.data;
    else if (detail.rows !== undefined) raw = detail.rows;
    else if (detail.payload && detail.payload.rows !== undefined) raw = detail.payload.rows;

    const rows = resolveRowsFromAny(raw);

    Spec.tabKey = tabKey;
    Spec.config = config;
    Spec.allRows = rows.slice();
    Spec.filteredRows = rows.slice();
    Spec.filterConfig = (config && config.filter_item_coldict) || {};
    Spec.filterOrder = Object.keys(Spec.filterConfig || {});
    Spec.currentPage = 1;
    Spec.totalPages = 1;
    Spec.isEditMode = false;
    Spec.isAddMode = false;
    Spec.isDeleteMode = false;

    setupHeaderTitle(tabKey, Spec.config);
    buildColConfig(Spec.config, Spec.allRows);
    renderHeader();
    buildSpecFilters(null);
    applySpecFilter();
    saveCurrentTableState();
  });

  // =========================
  // event: EditSummary
  // =========================
  document.addEventListener("aoi-bpi-density:subtab-action-history", (ev) => {
    const detail = ev.detail || {};

    const tabKey = detail.tabKey || "EditSummary";
    const config = detail.config || {};
    const restoreOnly = !!detail.restoreOnly;

    bindSpecButtons();

    if (restoreOnly && tabKey) {
      const ok = restoreTableState(tabKey);
      if (ok) return;
    }

    const resp = detail.resp || {};
    let raw = null;

    if (Array.isArray(resp)) raw = resp;
    else if (resp?.DictData) raw = resp.DictData;
    else if (resp?.data) raw = resp.data;
    else if (resp?.rows) raw = resp.rows;
    else raw = [];

    const rows = resolveRowsFromAny(raw);

    Spec.tabKey = tabKey;
    Spec.config = config;
    Spec.allRows = rows.slice();
    Spec.filteredRows = rows.slice();
    Spec.filterConfig = (config && config.filter_item_coldict) || {};
    Spec.filterOrder = Object.keys(Spec.filterConfig || {});
    Spec.currentPage = 1;
    Spec.totalPages = 1;
    Spec.isEditMode = false;
    Spec.isAddMode = false;
    Spec.isDeleteMode = false;

    setupHeaderTitle(tabKey, Spec.config);
    buildColConfig(Spec.config, Spec.allRows);
    renderHeader();
    buildSpecFilters(null);
    applySpecFilter();
    saveCurrentTableState();
  });
})();
