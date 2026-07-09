// static/js/aoi_density2/tabs/editSummary.js
(function () {
  const AOI = (window.AOI_DENSITY = window.AOI_DENSITY || {});
  const API = window.AOI_DENSITY_API;
  const $ = (sel, root = document) => root.querySelector(sel);

  const editor = window.USER || window.editor || "預設";

  const ES = {
    tabKey: "EditSummary",
    defs: null,
    allRows: [],
    filteredRows: [],
    mdd: {},
    filterConfig: {},
    filterOrder: [],
    colKeys: [],
    colLabels: {},
    pageSize: 200,
    currentPage: 1,
    totalPages: 1,
    isEditMode: false,
    editBtn: null,
    cancelBtn: null,
    isInited: false,
  };


  const EDITABLE_FIELDS = new Set(["comment", "action"]);
  const ROW_ID_KEYS = [
    "pi_hour",
    "line_id",
    "aoi",
    "model",
    "glass_type",
    "recipe_id",
    "adc_def_code",
  ];

  function getCacheRoot() {
    const AOIState = window.AOI_DENSITY?.state || {};
    if (!AOIState.tableStateCache) AOIState.tableStateCache = {};
    return AOIState.tableStateCache;
  }
  
  function saveCurrentStateToCache() {
    const cacheRoot = getCacheRoot();
    cacheRoot[ES.tabKey] = {
      defs: ES.defs,
      allRows: Array.isArray(ES.allRows) ? ES.allRows.slice() : [],
      filteredRows: Array.isArray(ES.filteredRows) ? ES.filteredRows.slice() : [],
      colKeys: Array.isArray(ES.colKeys) ? ES.colKeys.slice() : [],
      colLabels: { ...(ES.colLabels || {}) },
      currentPage: ES.currentPage || 1,
      totalPages: ES.totalPages || 1,
      isEditMode: !!ES.isEditMode,
      dates: readDates(),
      selections: collectSelections()
    };
  }
  
  function restoreStateFromCache() {
    const cacheRoot = getCacheRoot();
    const cache = cacheRoot[ES.tabKey];
    if (!cache) return false;
  
    ES.defs = cache.defs || ES.defs || {};
    ES.allRows = Array.isArray(cache.allRows) ? cache.allRows.slice() : [];
    ES.filteredRows = Array.isArray(cache.filteredRows) ? cache.filteredRows.slice() : [];
    ES.colKeys = Array.isArray(cache.colKeys) ? cache.colKeys.slice() : [];
    ES.colLabels = { ...(cache.colLabels || {}) };
    ES.currentPage = cache.currentPage || 1;
    ES.totalPages = cache.totalPages || 1;
    ES.isEditMode = !!cache.isEditMode;
  
    setHeaderTitle(ES.defs?.tab_name || "Action_History");
    setupHeaderActions();
  
    const sEl = $("#aoi-density-spec-start");
    const eEl = $("#aoi-density-spec-end");
    if (sEl && cache.dates?.[0]) sEl.value = cache.dates[0];
    if (eEl && cache.dates?.[1]) eEl.value = cache.dates[1];
  
    renderHeader();
    buildFiltersFromDefs(ES.defs, cache.selections || null);
    updatePagination();
    applyLocalFilter();
  
    if (ES.isEditMode) {
      if (ES.editBtn) ES.editBtn.textContent = "儲存";
      if (ES.cancelBtn) ES.cancelBtn.style.display = "";
    } else {
      if (ES.editBtn) ES.editBtn.textContent = "編輯";
      if (ES.cancelBtn) ES.cancelBtn.style.display = "none";
    }
  
    return true;
  }

  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  function fmtDateYYYYMMDD(d) {
    return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
  }

  function default3DaysRange() {
    const end = new Date();
    const start = new Date(end.getTime() - 3 * 24 * 3600 * 1000);
    return [fmtDateYYYYMMDD(start), fmtDateYYYYMMDD(end)];
  }

  function getNowStr() {
    const d = new Date();
    return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
  }

  function specSelectIdOf(key) {
    return `aoi-density-spec-es-f-${key}`;
  }

  function specHostIdOf(key) {
    return `aoi-density-spec-es-host-${key}`;
  }

  function ensureDynHosts() {
    const aside = $("#aoi-density-spec-right");
    if (!aside) return null;

    let dyn = $("#aoi-density-spec-dynhosts");
    if (!dyn) {
      dyn = document.createElement("div");
      dyn.id = "aoi-density-spec-dynhosts";
      aside.appendChild(dyn);
    }
    return dyn;
  }

  function ensurePager() {
    const wrap = $("#aoi-density-spec-left .table-wrap");
    if (!wrap) return null;

    let pager = $("#aoi-density-spec-pager");
    if (!pager) {
      pager = document.createElement("div");
      pager.id = "aoi-density-spec-pager";
      pager.className = "aoi_spec-pager";
      wrap.appendChild(pager);
    }
    return pager;
  }

  function ensureFilterCountSpan() {
    const title = $("#aoi-density-spec-right .aoi-inspection-density-spec-filter-panel-title")
      || $("#aoi-density-spec-right .spec-filter-panel-title")
      || $("#aoi-density-spec-right .aoi-density-spec-filter-panel-title");

    if (!title) return null;

    let span = $("#aoi-density-spec-count");
    if (!span) {
      span = document.createElement("span");
      span.id = "aoi-density-spec-count";
      span.className = "spec-filter-count";
      title.appendChild(span);
    }
    return span;
  }

  function ensureBottomClearButton() {
    const aside = $("#aoi-density-spec-right");
    if (!aside) return null;

    let box = aside.querySelector(".spec-filter-bottom-actions");
    if (!box) {
      box = document.createElement("div");
      box.className = "spec-filter-bottom-actions";

      const btn = document.createElement("button");
      btn.id = "aoi-density-spec-clear-bottom";
      btn.className = "btn btn-xs btn-secondary";
      btn.textContent = "清空篩選";

      box.appendChild(btn);
      aside.appendChild(box);
    }

    return $("#aoi-density-spec-clear-bottom");
  }

  function setHeaderTitle(name) {
    const h2 = $("#aoi-density-spec-info .aoi-density-spec-info-head .t");
    if (h2) h2.textContent = name || "Action_History";

    const dateBlock = $("#aoi-density-spec-right .spec-filter-item");
    if (dateBlock) dateBlock.style.display = "";
  }

  function setupHeaderActions() {
    const head = $("#aoi-density-spec-info .aoi-density-spec-info-head");
    if (!head) return;

    let actions = head.querySelector(".spec-header-actions");
    if (!actions) {
      actions = document.createElement("div");
      actions.className = "spec-header-actions";
      head.appendChild(actions);
    }

    actions.innerHTML = "";
    actions.style.display = "";

    const editBtn = document.createElement("button");
    editBtn.id = "aoi-density-es-edit";
    editBtn.className = "btn-spec-action";
    editBtn.textContent = "編輯";

    const cancelBtn = document.createElement("button");
    cancelBtn.id = "aoi-density-es-cancel";
    cancelBtn.className = "btn-spec-action";
    cancelBtn.textContent = "取消";
    cancelBtn.style.display = "none";

    actions.appendChild(editBtn);
    actions.appendChild(cancelBtn);

    ES.editBtn = editBtn;
    ES.cancelBtn = cancelBtn;

    editBtn.onclick = onClickEdit;
    cancelBtn.onclick = onClickCancel;
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

  function buildColConfigFromDefs(defs) {
    const tc = defs?.table_columns;
    const colKeys = [];
    const colLabels = {};

    if (Array.isArray(tc)) {
      tc.forEach((k) => {
        colKeys.push(k);
        colLabels[k] = k;
      });
    } else if (tc && typeof tc === "object") {
      Object.entries(tc).forEach(([k, v]) => {
        colKeys.push(k);
        colLabels[k] = typeof v === "string" && v ? v : k;
      });
    } else {
      const fallback = [
        "line_id",
        "aoi",
        "model",
        "glass_type",
        "recipe_id",
        "pi_hour",
        "adc_def_code",
        "density",
        "comment",
        "action",
        "Editor",
        "modify_time",
      ];
      fallback.forEach((k) => {
        colKeys.push(k);
        colLabels[k] = k;
      });
    }

    ES.colKeys = colKeys;
    ES.colLabels = colLabels;
  }

  function renderHeader() {
    const table = $("#aoi-density-spec-table-main");
    if (!table) return;

    const thead = ensureThead(table);
    thead.innerHTML = "";

    const tr = document.createElement("tr");
    (ES.colKeys || []).forEach((dataKey) => {
      if (dataKey !== 'modify_time'){
        const th = document.createElement("th");
        th.textContent = ES.colLabels[dataKey] || dataKey;
        tr.appendChild(th);
      }
      
    });

    thead.appendChild(tr);
  }

  function formatCellValue(v) {
    if (v == null) return "";
    return String(v);
  }

  function setDateInputsFromDefs(defs) {
    const sEl = $("#aoi-density-spec-start");
    const eEl = $("#aoi-density-spec-end");
    if (!sEl || !eEl) return;

    const tr = defs?.timeRange;
    if (tr?.start && tr?.end) {
      sEl.value = tr.start;
      eEl.value = tr.end;
      return;
    }

    if (!sEl.value || !eEl.value) {
      const [ds, de] = default3DaysRange();
      sEl.value = ds;
      eEl.value = de;
    }
  }

  function readDates() {
    const s = $("#aoi-density-spec-start")?.value;
    const e = $("#aoi-density-spec-end")?.value;
    return s && e ? [s, e] : null;
  }

  function collectSelections() {
    const out = {};
    Object.entries(ES.mdd || {}).forEach(([dataKey, wrap]) => {
      const mdd = wrap?.mdd;
      if (!mdd?.getSelected) return;
      out[dataKey] = new Set((mdd.getSelected() || []).map(String));
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

  function buildFiltersFromDefs(defs, prevSelections) {
    const dynHosts = ensureDynHosts();
    if (!dynHosts) return;

    dynHosts.innerHTML = "";
    ES.mdd = {};

    const colDict = defs?.filter_item_coldict || {};
    const labels = Object.keys(colDict || {});
    ES.filterConfig = colDict;
    ES.filterOrder = labels;

    if (!labels.length) return;

    if (!AOI.MultiDD) {
      console.error("[EditSummary] AOI.MultiDD 未載入");
      return;
    }

    function uniqFromRows(key) {
      const s = new Set();
      (ES.allRows || []).forEach((r) => {
        if (!r) return;
        if (r[key] == null) return;
        const v = String(r[key]);
        if (v !== "") s.add(v);
      });
      return Array.from(s).sort();
    }

    labels.forEach((label) => {
      const cfg = colDict[label] || {};
      const dataKey = cfg.key || label;

      const dataUniques = uniqFromRows(dataKey);

      let opts = Array.isArray(cfg.values) ? cfg.values.slice() : [];
      if (!opts.length) {
        opts = dataUniques.slice();
      } else {
        const inter = opts.filter((v) => dataUniques.includes(String(v)));
        opts = inter.length ? inter : dataUniques.slice();
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
          ES.currentPage = 1;
          applyLocalFilter();
        },
      });

      const prevSet = prevSelections && prevSelections[dataKey];
      let selected = null;

      if (prevSet && prevSet.size) {
        const keep = opts.filter((o) => prevSet.has(String(o)));
        selected = keep.length ? keep : opts.slice();
      } else {
        selected = opts.slice();
      }

      mdd.setSelected?.(selected);
      ES.mdd[dataKey] = { mdd, options: opts };

      wireSearchForHost(host);
    });
  }

  function getActiveFilters() {
    const out = {};
    Object.entries(ES.mdd || {}).forEach(([dataKey, wrap]) => {
      const sel = wrap?.mdd?.getSelected?.() || [];
      if (sel.length) out[dataKey] = new Set(sel.map(String));
    });
    return out;
  }

  function applyLocalFilter() {
    const filters = getActiveFilters();
    const rows = ES.allRows || [];
    const keys = Object.keys(filters);

    if (!keys.length) {
      ES.filteredRows = rows.slice();
    } else {
      ES.filteredRows = rows.filter((r) => {
        if (!r) return false;

        for (const k of keys) {
          const set = filters[k];
          if (!(k in r)) continue;

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
    saveCurrentStateToCache();
  }

  function updatePagination() {
    const total = ES.filteredRows.length || 0;
    const size = ES.pageSize || 200;
    ES.totalPages = total ? Math.ceil(total / size) : 1;
    if (!ES.currentPage || ES.currentPage > ES.totalPages) ES.currentPage = 1;
  }

  function renderPager() {
    const pager = ensurePager();
    if (!pager) return;

    const total = ES.filteredRows.length || 0;
    const pages = ES.totalPages || 1;

    pager.innerHTML = "";
    pager.style.display = "flex";

    const info = document.createElement("div");
    info.className = "aoi_spec-pager-info";
    info.textContent = `第 ${ES.currentPage} / ${pages} 頁（共 ${total} 筆）`;
    pager.appendChild(info);

    const btnPrev = document.createElement("button");
    btnPrev.textContent = "上一頁";
    btnPrev.disabled = pages <= 1 || ES.currentPage <= 1;
    btnPrev.onclick = () => {
      if (ES.currentPage > 1) {
        ES.currentPage -= 1;
        renderBody();
        renderPager();
        updateFilterCount();
      }
    };
    pager.appendChild(btnPrev);

    const maxPageButtons = 7;
    let start = Math.max(1, ES.currentPage - 3);
    let end = Math.min(pages, start + maxPageButtons - 1);
    if (end - start + 1 < maxPageButtons) {
      start = Math.max(1, end - maxPageButtons + 1);
    }

    for (let p = start; p <= end; p++) {
      const btn = document.createElement("button");
      btn.textContent = String(p);
      btn.className = "page-btn" + (p === ES.currentPage ? " active" : "");
      btn.disabled = pages <= 1;
      btn.onclick = () => {
        if (p === ES.currentPage || pages <= 1) return;
        ES.currentPage = p;
        renderBody();
        renderPager();
        updateFilterCount();
      };
      pager.appendChild(btn);
    }

    const btnNext = document.createElement("button");
    btnNext.textContent = "下一頁";
    btnNext.disabled = pages <= 1 || ES.currentPage >= pages;
    btnNext.onclick = () => {
      if (ES.currentPage < pages) {
        ES.currentPage += 1;
        renderBody();
        renderPager();
        updateFilterCount();
      }
    };
    pager.appendChild(btnNext);
  }

  function updateFilterCount() {
    const span = ensureFilterCountSpan();
    if (!span) return;
    span.textContent = `( ${ES.filteredRows.length || 0} 筆）`;
  }

  function renderBody() {
    const table = $("#aoi-density-spec-table-main");
    if (!table) return;

    const tbody = ensureTbody(table);
    const rows = ES.filteredRows || [];
    tbody.innerHTML = "";

    if (!rows.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = Math.max(1, ES.colKeys.length);
      td.className = "muted";
      td.textContent = "（無資料）";
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    const size = ES.pageSize || 200;
    const start = (ES.currentPage - 1) * size;
    const end = start + size;
    const pageRows = rows.slice(start, end);

    pageRows.forEach((r, idxInPage) => {
      const tr = document.createElement("tr");
      const globalIndex = start + idxInPage;
      tr.dataset.rowIndex = String(globalIndex);

      (ES.colKeys || []).forEach((dataKey) => {
        const td = document.createElement("td");
        const v = r ? r[dataKey] : "";
        console.log(dataKey);
        if (ES.isEditMode && EDITABLE_FIELDS.has(dataKey)) {
          const input = document.createElement("input");
          input.type = "text";
          input.className = "es-edit-input spec-edit-input";
          input.dataset.field = dataKey;
          input.value = v == null ? "" : String(v);
          td.appendChild(input);
        } else if (dataKey === "Editor") {
          td.classList.add("editor-cell");
          const e = (r && (r.Editor || r.editor)) || "";
          const mt = (r && (r.modify_time || r.modifyTime)) || "";
          td.innerHTML = `${e || ""}${(e && mt) ? "<br>" : ""}${mt || ""}`;
        } else if (dataKey !== 'modify_time'){
          console.log('dataKey', dataKey);
          td.textContent = formatCellValue(v);
        }

        tr.appendChild(td);
      });

      tbody.appendChild(tr);
    });
  }

  function normalizeRowsFromResp(resp) {
    const raw = resp?.DictData;
    if (!raw) return [];
    if (Array.isArray(raw)) return raw;
    if (typeof raw === "object") return Object.values(raw);
    return [];
  }

  function renderWith(defs, resp, { keepSelections = false } = {}) {
    ES.defs = defs || ES.defs || {};

    const rows = normalizeRowsFromResp(resp);
    ES.allRows = rows.slice();
    ES.filteredRows = rows.slice();
    ES.currentPage = 1;
    ES.isEditMode = false;

    setHeaderTitle(ES.defs?.tab_name || "Action_History");
    setupHeaderActions();
    setDateInputsFromDefs(ES.defs);
    buildColConfigFromDefs(ES.defs);
    renderHeader();

    const prev = keepSelections ? collectSelections() : null;
    buildFiltersFromDefs(ES.defs, prev);

    updatePagination();
    applyLocalFilter();
    saveCurrentStateToCache();
  }


  async function fetchByDateFromBackend({ keepSelections = false } = {}) {
    if (!API?.ActionHisEditor) {
      console.error("[EditSummary] window.AOI_DENSITY_API.ActionHisEditor 不存在");
      return null;
    }

    const dates = readDates();

    const payload = {
      mode: "date",
      dates: dates && dates.length === 2 ? dates : null,
    };

    const resp = await API.ActionHisEditor(payload);
    if (!resp) return null;

    renderWith(ES.defs, resp, { keepSelections });
    return resp;
  }

  async function fetchDefault3Days() {
    if (!API?.ActionHisEditor) {
      console.error("[EditSummary] window.AOI_DENSITY_API.ActionHisEditor 不存在");
      return null;
    }

    const payload = { mode: "date", dates: null };
    const resp = await API.ActionHisEditor(payload);
    if (!resp) return null;

    const [ds, de] = default3DaysRange();
    const sEl = $("#aoi-density-spec-start");
    const eEl = $("#aoi-density-spec-end");
    if (sEl) sEl.value = ds;
    if (eEl) eEl.value = de;

    renderWith(ES.defs, resp, { keepSelections: false });
    return resp;
  }

  function onClickEdit() {
    if (!ES.isEditMode) {
      ES.isEditMode = true;
      if (ES.editBtn) ES.editBtn.textContent = "儲存";
      if (ES.cancelBtn) ES.cancelBtn.style.display = "";
      renderBody();
      return;
    }
    saveEdits();
    saveCurrentStateToCache();
  }

  function onClickCancel() {
    ES.isEditMode = false;
    if (ES.editBtn) ES.editBtn.textContent = "編輯";
    if (ES.cancelBtn) ES.cancelBtn.style.display = "none";
    renderBody();
    saveCurrentStateToCache();
  }

  async function saveEdits() {
    if (!API?.ActionHisEditor) {
      alert("儲存失敗：window.AOI_DENSITY_API.ActionHisEditor 不存在");
      return;
    }

    const table = $("#aoi-density-spec-table-main");
    const tbody = table ? ensureTbody(table) : null;
    if (!tbody) return;

    const rows = ES.filteredRows || [];
    const trs = Array.from(tbody.querySelectorAll("tr"));
    const mt = getNowStr();
    const jobs = [];

    trs.forEach((tr) => {
      const idx = Number(tr.dataset.rowIndex);
      if (Number.isNaN(idx)) return;

      const row = rows[idx];
      if (!row) return;

      const inputs = tr.querySelectorAll("input.es-edit-input[data-field]");
      const patch = {};

      inputs.forEach((inp) => {
        const field = inp.dataset.field;
        const newVal = (inp.value ?? "").trim();
        const oldVal = row[field] == null ? "" : String(row[field]);
        if (newVal !== oldVal) patch[field] = newVal;
      });

      if (!Object.keys(patch).length) return;

      const idRow = {};
      ROW_ID_KEYS.forEach((k) => {
        idRow[k] = row[k];
      });

      const payload = {
        mode: "edit",
        system: "density",
        row: idRow,
        editor,
        modify_time: mt,
      };

      if (Object.prototype.hasOwnProperty.call(patch, "comment")) payload.comment = patch.comment;
      if (Object.prototype.hasOwnProperty.call(patch, "action")) payload.action = patch.action;

      if (payload.comment != null) row.comment = payload.comment;
      if (payload.action != null) row.action = payload.action;
      row.Editor = editor;
      row.modify_time = mt;

      jobs.push(payload);
    });

    if (!jobs.length) {
      ES.isEditMode = false;
      if (ES.editBtn) ES.editBtn.textContent = "編輯";
      if (ES.cancelBtn) ES.cancelBtn.style.display = "none";
      renderBody();
      return;
    }

    for (const payload of jobs) {
      try {
        const res = await API.ActionHisEditor(payload);
        console.log("[EditSummary] saved", res);
      } catch (e) {
        console.error("[EditSummary] save failed", payload, e);
        alert("儲存失敗：" + (e?.message || e));
        break;
      }
    }

    ES.isEditMode = false;
    if (ES.editBtn) ES.editBtn.textContent = "編輯";
    if (ES.cancelBtn) ES.cancelBtn.style.display = "none";
    renderBody();
  
    saveCurrentStateToCache();
  }

  let btnBound = false;
  function bindButtons() {
    if (btnBound) return;
    btnBound = true;

    const btnApply = $("#aoi-density-spec-apply");
    const btnClear = $("#aoi-density-spec-clear");
    const btnBottomClear = ensureBottomClearButton();

    if (btnApply) {
      btnApply.addEventListener("click", async () => {
        await fetchByDateFromBackend({ keepSelections: true });
      });
    }

    async function clearAll() {
      const s = $("#aoi-density-spec-start");
      const e = $("#aoi-density-spec-end");
      if (s) s.value = "";
      if (e) e.value = "";
      await fetchDefault3Days();
    }

    if (btnClear) btnClear.addEventListener("click", clearAll);
    if (btnBottomClear) btnBottomClear.addEventListener("click", clearAll);
  }

  document.addEventListener("aoi-density:subtab-action-history", async (ev) => {
    bindButtons();
  
    const defs = ev?.detail?.config || null;
    const resp = ev?.detail?.resp || null;
    const restoreOnly = !!ev?.detail?.restoreOnly;
  
    if (defs) ES.defs = defs;
  
    if (restoreOnly) {
      const ok = restoreStateFromCache();
      if (ok) return;
    }
  
    if (resp) {
      renderWith(ES.defs, resp, { keepSelections: false });
      ES.isInited = true;
      return;
    }
  
    if (!ES.isInited) {
      setDateInputsFromDefs(ES.defs || {});
      await fetchDefault3Days();
      ES.isInited = true;
      saveCurrentStateToCache();
    }
  });
})();