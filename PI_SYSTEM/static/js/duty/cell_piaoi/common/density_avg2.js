// static/js/common/density_avg.js
// 共用 Density Average Preview / Download
//
// 用途：
//   AOI Density / BPI Density(AOI) / Inspection Density / BPI Same Point 共用 density 平均值分析頁。
//
// 需要 HTML：
//   section#density-avg-download-root
//   div#density-avg-system-badge
//   input#density-avg-start
//   input#density-avg-end
//   button#density-avg-preview-btn
//   button#density-avg-download-btn
//   button#density-avg-clear-btn
//   button#density-avg-filter-apply-btn
//   div#density-avg-status
//   div#density-avg-summary-cards
//   div#density-avg-dynhosts
//   span#density-avg-filter-count
//   table#density-avg-preview-table
//   div#density-avg-pager
//
// service.js 切到 type="density_avg" 時 dispatch：
//   document.dispatchEvent(new CustomEvent("density-avg-download:show", {
//     detail: {
//       system: "aoi_density" | "aoi_bpi_density" | "aoi_inspection_density" | "bpi_same_point",
//       tabKey,
//       config
//     }
//   }));
//
// 操作流程：
//   1. 初始進入：自動查預設 30 天 options + preview。
//   2. 勾選/取消 filter：立即打 /options 更新階層式選項，但不更新 table。
//   3. 按「套用篩選」或「查詢預覽」：才打 /preview 更新 table / summary。
//   4. 清空：清空所有選項，不打後端、不查全量。

(function () {
  const MOD = (window.DENSITY_AVG_DOWNLOAD = window.DENSITY_AVG_DOWNLOAD || {});
  const API_BASE = window.API_BASE || "";

  const state = {
    system: "",
    tabKey: "",
    config: null,

    filterOptionDict: {},
    suggestedFilters: {},
    mdd: {},
    filterKeys: [],
    filterLabels: {},
    cascadeOrder: [],

    lastPreview: null,
    lastRows: [],
    lastColumns: [],

    pageSize: 12,
    currentPage: 1,
    totalPages: 1,
    previewTotalCount: 0,

    bound: false,
    loadingOptions: false,
    loadingPreview: false,
    suppressFilterChange: false,
    optionReqSeq: 0,
    filtersDirty: false
  };

  // ============================================================
  // DOM helpers
  // ============================================================
  function $(id) {
    return document.getElementById(id);
  }

  function setStatus(msg, type) {
    const el = $("density-avg-status");
    if (!el) return;

    el.textContent = msg || "";
    el.classList.remove("density-avg-status-ok", "density-avg-status-warn", "density-avg-status-error");

    if (type === "ok") el.classList.add("density-avg-status-ok");
    if (type === "warn") el.classList.add("density-avg-status-warn");
    if (type === "error") el.classList.add("density-avg-status-error");
  }

  function setBusy(isBusy) {
    const previewBtn = $("density-avg-preview-btn");
    const downloadBtn = $("density-avg-download-btn");
    const clearBtn = $("density-avg-clear-btn");
    const filterApplyBtn = $("density-avg-filter-apply-btn");

    if (previewBtn) previewBtn.disabled = !!isBusy;
    if (downloadBtn) downloadBtn.disabled = !!isBusy;
    if (clearBtn) clearBtn.disabled = !!isBusy;
    if (filterApplyBtn) filterApplyBtn.disabled = !!isBusy;
  }

  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  function toYMD(d) {
    return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
  }

  function getDefaultDateRange() {
    const end = new Date();
    end.setHours(0, 0, 0, 0);

    const start = new Date(end);
    start.setDate(start.getDate() - 30);

    return {
      start_date: toYMD(start),
      end_date: toYMD(end)
    };
  }

  function ensureDefaultDates(force) {
    const startEl = $("density-avg-start");
    const endEl = $("density-avg-end");
    if (!startEl || !endEl) return;

    const def = getDefaultDateRange();

    if (force || !startEl.value) startEl.value = def.start_date;
    if (force || !endEl.value) endEl.value = def.end_date;
  }

  function readDates() {
    return {
      start_date: $("density-avg-start")?.value || "",
      end_date: $("density-avg-end")?.value || ""
    };
  }

  function validatePayload(payload) {
    if (!payload.system) {
      alert("尚未指定系統");
      return false;
    }

    if (!payload.start_date || !payload.end_date) {
      alert("請選擇日期區間");
      return false;
    }

    return true;
  }

  function buildUrl(path) {
    return `${API_BASE}${path}`;
  }

  async function postJson(path, body) {
    const resp = await fetch(buildUrl(path), {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(body || {})
    });

    if (!resp.ok) {
      const txt = await resp.text().catch(() => "");
      throw new Error(txt || `HTTP ${resp.status}`);
    }

    return await resp.json();
  }

  async function postBlobResponse(path, body) {
    const resp = await fetch(buildUrl(path), {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(body || {})
    });

    if (!resp.ok) {
      const txt = await resp.text().catch(() => "");
      throw new Error(txt || `HTTP ${resp.status}`);
    }

    return resp;
  }

  function parseFilenameFromContentDisposition(cd, fallback) {
    if (!cd) return fallback;

    const m1 = cd.match(/filename\*=UTF-8''([^;]+)/i);
    if (m1 && m1[1]) {
      try {
        return decodeURIComponent(m1[1]);
      } catch (_) {
        return m1[1];
      }
    }

    const m2 = cd.match(/filename="?([^"]+)"?/i);
    if (m2 && m2[1]) return m2[1];

    return fallback;
  }

  // ============================================================
  // API
  // ============================================================
  const API = {
    async options(payload) {
      return await postJson("/common/density_avg/options", payload);
    },

    async preview(payload) {
      return await postJson("/common/density_avg/preview", payload);
    },

    async download(payload) {
      const resp = await postBlobResponse("/common/density_avg/download", payload);
      const blob = await resp.blob();

      const cd = resp.headers.get("Content-Disposition") || "";
      const fallback = `${payload?.system || "density"}_density_avg_${payload?.start_date || ""}_${payload?.end_date || ""}.csv`;
      const filename = parseFilenameFromContentDisposition(cd, fallback);

      const a = document.createElement("a");
      const url = URL.createObjectURL(blob);

      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();

      URL.revokeObjectURL(url);
      a.remove();

      return {
        ok: true,
        filename
      };
    }
  };

  window.DENSITY_AVG_API = API;

  // ============================================================
  // Config helpers
  // ============================================================
  function getSystemLabel(system) {
    const labelMap = {
      aoi_density: "AOI Density",
      aoi_bpi_density: "BPI Density(AOI)",
      bpi_density: "BPI Density(AOI)",
      aoi_inspection_density: "Inspection Density",
      bpi_same_point: "BPI/API 同點"
    };

    return labelMap[system] || system || "未指定";
  }

  function getMultiDDCtor() {
    return (
      window.AOI_DENSITY?.MultiDD ||
      window.AOI_BPI_DENSITY?.MultiDD ||
      window.AOI_INSPECTION_DENSITY?.MultiDD ||
      window.AOI_CSV?.MultiDD ||
      window.MultiDD ||
      null
    );
  }

  function normalizeFilterConfig(config) {
    const colDict = config?.filter_item_coldict || {};
    const labelByKey = {};
    const keysFromDict = [];

    Object.entries(colDict).forEach(([label, cfg]) => {
      if (!cfg || typeof cfg !== "object") return;

      const key = String(cfg.key || "").trim();
      if (!key || key === "date") return;

      if (!keysFromDict.includes(key)) keysFromDict.push(key);
      labelByKey[key] = label;
    });

    const order = Array.isArray(config?.cascade_order)
      ? config.cascade_order.map(String).filter(Boolean)
      : [];

    const finalKeys = [];

    order.forEach(k => {
      if (keysFromDict.includes(k) && !finalKeys.includes(k)) {
        finalKeys.push(k);
      }
    });

    keysFromDict.forEach(k => {
      if (!finalKeys.includes(k)) {
        finalKeys.push(k);
      }
    });

    state.filterKeys = finalKeys;
    state.filterLabels = labelByKey;
    state.cascadeOrder = finalKeys.slice();
  }

  function selectIdOf(key) {
    return `density-avg-f-${key}`;
  }

  function hostIdOf(key) {
    return `density-avg-host-${key}`;
  }

  function cleanArr(v) {
    if (!Array.isArray(v)) return [];
    return v.map(x => String(x).trim()).filter(Boolean);
  }

  function getConfigForKey(key) {
    const colDict = state.config?.filter_item_coldict || {};
    for (const cfg of Object.values(colDict)) {
      if (cfg && String(cfg.key || "") === String(key)) return cfg;
    }
    return {};
  }

  function isSingleSelectFilter(key) {
    const cfg = getConfigForKey(key);
    const mode = String(cfg.selection_mode || cfg.select_mode || "").toLowerCase();

    return (
      mode === "single" ||
      cfg.single === true ||
      cfg.multiple === false
    );
  }

  function normalizeSelectionForKey(key, selected, options) {
    const opts = cleanArr(options);
    let sel = cleanArr(selected).filter(v => opts.includes(v));

    if (!isSingleSelectFilter(key)) return sel;
    if (!opts.length) return [];

    const cfg = getConfigForKey(key);
    const rawDefault = cfg.default_value != null ? cfg.default_value : cfg.default;
    const defaults = Array.isArray(cfg.default_values)
      ? cleanArr(cfg.default_values)
      : cleanArr(rawDefault != null ? [rawDefault] : []);
    const defaultValue = defaults.find(v => opts.includes(v));

    if (sel.length > 1) return [sel[sel.length - 1]];
    if (sel.length === 1) return [sel[0]];

    return [defaultValue || opts[0]];
  }

  // ============================================================
  // Filters
  // ============================================================
  function hasBuiltFilters() {
    return Object.keys(state.mdd || {}).length > 0;
  }

  function getAllSelectionState() {
    const out = {};

    Object.entries(state.mdd || {}).forEach(([key, wrap]) => {
      const selected = cleanArr(wrap?.mdd?.getSelected?.() || []);
      out[key] = selected;
    });

    return out;
  }

  function getSelectedFilters() {
    const out = {};

    Object.entries(state.mdd || {}).forEach(([key, wrap]) => {
      const selected = cleanArr(wrap?.mdd?.getSelected?.() || []);
      const options = cleanArr(wrap?.options || []);

      if (!options.length) return;

      // 空選單不送 filter；preview/download 由 hasEmptyFilterSelection() 阻擋。
      if (!selected.length) return;

      // 全選視為沒有篩選。
      if (isSingleSelectFilter(key)) {
        out[key] = normalizeSelectionForKey(key, selected, options);
        return;
      }

      const isAllSelected =
        selected.length === options.length &&
        selected.every(v => options.includes(v));

      if (isAllSelected) return;

      out[key] = selected;
    });

    return out;
  }

  function hasEmptyFilterSelection() {
    return Object.entries(state.mdd || {}).some(([_key, wrap]) => {
      const selected = cleanArr(wrap?.mdd?.getSelected?.() || []);
      const options = cleanArr(wrap?.options || []);

      return options.length > 0 && selected.length === 0;
    });
  }

  function buildPayload(extra) {
    const dates = readDates();

    return {
      system: state.system,
      start_date: dates.start_date,
      end_date: dates.end_date,
      filters: getSelectedFilters(),
      ...(extra || {})
    };
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

      items.forEach(item => {
        const text = item.textContent.toLowerCase();
        item.style.display = (!q || text.includes(q)) ? "" : "none";
      });
    });
  }

  function updateFilterCount() {
    const el = $("density-avg-filter-count");
    if (!el) return;

    if (hasEmptyFilterSelection()) {
      el.textContent = "（有空白篩選）";
      return;
    }

    const filters = getSelectedFilters();
    const n = Object.values(filters).reduce(
      (acc, arr) => acc + (Array.isArray(arr) ? arr.length : 0),
      0
    );

    el.textContent = n ? `(已選 ${n})` : "";
  }

  function clearFilterHosts() {
    const host = $("density-avg-dynhosts");
    if (host) host.innerHTML = "";

    state.mdd = {};
    updateFilterCount();
  }

  function arrSame(a, b) {
    const aa = cleanArr(a);
    const bb = cleanArr(b);
  
    if (aa.length !== bb.length) return false;
  
    const sa = new Set(aa);
    for (const x of bb) {
      if (!sa.has(x)) return false;
    }
  
    return true;
  }
  
  function getOpenFilterKey() {
    const open = document.querySelector("#density-avg-dynhosts .multi-dd.open");
    if (!open) return "";
  
    const host = open.closest(".multi-dd-host");
    if (!host || !host.id) return "";
  
    const prefix = "density-avg-host-";
    if (!host.id.startsWith(prefix)) return "";
  
    return host.id.slice(prefix.length);
  }
  
  function reopenFilterByKey(key) {
    if (!key) return;
  
    const wrap = state.mdd?.[key];
    const nodes = wrap?.mdd?.nodes;
  
    if (!nodes?.list || !nodes?.wrap) return;
  
    nodes.list.style.display = "";
    nodes.wrap.classList.add("open");
  
    try {
      nodes.search?.focus?.();
    } catch (_) {}
  }
  
  function ensureAvgFilterHost(dyn, key) {
    let host = document.getElementById(hostIdOf(key));
  
    if (!host) {
      host = document.createElement("div");
      host.className = "multi-dd-host";
      host.id = hostIdOf(key);
      dyn.appendChild(host);
    }
  
    return host;
  }
  
  function removeUnusedFilterHosts(validKeys) {
    const valid = new Set(validKeys || []);
    const dyn = $("density-avg-dynhosts");
    if (!dyn) return;
  
    Array.from(dyn.querySelectorAll(".multi-dd-host")).forEach(host => {
      const prefix = "density-avg-host-";
      const key = host.id && host.id.startsWith(prefix)
        ? host.id.slice(prefix.length)
        : "";
  
      if (key && !valid.has(key)) {
        host.remove();
        delete state.mdd[key];
      }
    });
  }

  

  function buildFilterControls(optionDict, prevSelections, suggestedFilters) {
    const dyn = $("density-avg-dynhosts");
    if (!dyn) return;
  
    const MultiDD = getMultiDDCtor();
    if (!MultiDD) {
      console.error("[density_avg] MultiDD not found");
      dyn.innerHTML = "<div class='density-avg-filter-hint'>MultiDD 未載入</div>";
      return;
    }
  
    const optionMap = optionDict || {};
    const suggestions = suggestedFilters || {};
    const keys = state.filterKeys || [];
  
    const openKeyBefore = getOpenFilterKey();
  
    state.mdd = state.mdd || {};
  
    removeUnusedFilterHosts(keys);
  
    keys.forEach(key => {
      const cfg = getConfigForKey(key);
      let opts = cleanArr(optionMap[key]);
  
      if (!opts.length && Array.isArray(cfg.values) && cfg.values.length) {
        opts = cleanArr(cfg.values);
      }
  
      if (!opts.length) return;
  
      const host = ensureAvgFilterHost(dyn, key);
      const label = state.filterLabels[key] || key;
      const selectId = selectIdOf(key);
  
      const suggested = cleanArr(suggestions[key]);
  
      const hasPrev = Object.prototype.hasOwnProperty.call(prevSelections || {}, key);
      const prev = cleanArr(prevSelections?.[key]);
  
      const shouldApplySuggestion =
        suggested.length > 0 &&
        (
          !hasPrev ||
          prev.length === opts.length
        );
  
      let selected = [];
  
      if (shouldApplySuggestion) {
        selected = suggested.filter(v => opts.includes(v));
      } else if (hasPrev) {
        // 有舊狀態，即使是空陣列，也要保留空選
        selected = prev.filter(v => opts.includes(v));
      } else {
        // 首次建立才全選
        selected = opts.slice();
      }
  
      selected = normalizeSelectionForKey(key, selected, opts);

      let wrap = state.mdd[key];
  
      // 第一次建立
      if (!wrap?.mdd) {
        const mdd = new MultiDD({
          hostId: host.id,
          selectId,
          options: opts,
          title: label,
          onChange: (selectedValues) => {
            if (state.suppressFilterChange) return;

            const currentOptions = state.mdd?.[key]?.options || opts;
            const normalized = normalizeSelectionForKey(key, selectedValues, currentOptions);
            if (!arrSame(selectedValues, normalized)) {
              state.suppressFilterChange = true;
              try {
                mdd.setSelected?.(normalized);
              } finally {
                state.suppressFilterChange = false;
              }
            }
  
            state.currentPage = 1;
            updateFilterCount();
  
            // 只更新階層式 options，不更新 table / summary
            scheduleOptionsRefresh();
          }
        });
  
        state.suppressFilterChange = true;
        try {
          mdd.setSelected?.(selected);
        } finally {
          state.suppressFilterChange = false;
        }
  
        state.mdd[key] = {
          mdd,
          options: opts
        };
  
        wireSearchForHost(host);
        return;
      }
  
      // 已存在：原地更新，不砍 DOM
      const mdd = wrap.mdd;
      mdd.title = label;
  
      const oldOptions = cleanArr(wrap.options || []);
      const oldSelected = cleanArr(mdd.getSelected?.() || []);
  
      const optionsChanged = !arrSame(oldOptions, opts);
      const selectedChanged = !arrSame(oldSelected, selected);
  
      state.suppressFilterChange = true;
      try {
        if (optionsChanged) {
          mdd.updateOptions?.(opts);
        }
  
        if (selectedChanged || optionsChanged) {
          mdd.setSelected?.(selected);
        }
  
        if (mdd.nodes?.btn && typeof mdd._updateBtnText === "function") {
          mdd._updateBtnText(mdd.nodes.btn);
        }
  
        if (mdd.nodes?.updateFooterButton) {
          mdd.nodes.updateFooterButton();
        }
      } finally {
        state.suppressFilterChange = false;
      }
  
      state.mdd[key] = {
        mdd,
        options: opts
      };
  
      wireSearchForHost(host);
    });
  
    updateFilterCount();
  
    // 如果原本有展開某一個選單，更新後保持展開
    if (openKeyBefore && state.mdd?.[openKeyBefore]) {
      reopenFilterByKey(openKeyBefore);
    }
  }

  let optionsRefreshTimer = null;

  function scheduleOptionsRefresh() {
    if (optionsRefreshTimer) clearTimeout(optionsRefreshTimer);

    optionsRefreshTimer = setTimeout(() => {
      refreshOptions({
        keepSelections: true,
        autoPreview: false
      });
    }, 150);
  }

  async function refreshOptions({ keepSelections = true, autoPreview = false } = {}) {
    ensureDefaultDates(false);

    const payload = buildPayload();
    if (!validatePayload(payload)) return null;

    console.log("[density_avg/options] payload", payload);

    const seq = ++state.optionReqSeq;
    const prevSelections = keepSelections ? getAllSelectionState() : {};
    
    try {
      state.loadingOptions = true;
      const dyn = $("density-avg-dynhosts");
      if (dyn) dyn.classList.add("density-avg-filter-loading");

      setStatus("更新篩選選項中...");

      const resp = await API.options(payload);
      if (seq !== state.optionReqSeq) return null;

      state.filterOptionDict = resp?.filterOptionDict || {};
      state.suggestedFilters = resp?.suggestedFilters || {};

      if (resp?.Config && typeof resp.Config === "object") {
        state.config = {
          ...(state.config || {}),
          ...resp.Config
        };
        normalizeFilterConfig(state.config);
      }

      buildFilterControls(
        state.filterOptionDict,
        prevSelections,
        state.suggestedFilters
      );

      if (autoPreview) {
        await MOD.preview();
      } else {
        setStatus("篩選選項已更新，請按右側「套用篩選」更新結果。", "ok");
      }

      return resp;
    } catch (err) {
      console.error("[density_avg] options failed:", err);
      setStatus("更新篩選選項失敗", "error");
      alert("更新篩選選項失敗：" + (err?.message || String(err)));
      return null;
    } finally {
      state.loadingOptions = false;
      const dyn = $("density-avg-dynhosts");
      if (dyn) dyn.classList.remove("density-avg-filter-loading");
    }
  }

  // ============================================================
  // Summary cards
  // ============================================================
  function fmtNum(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return "0";
    return n.toLocaleString();
  }

  function fmtDensity(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return "0";
    return n.toFixed(6);
  }

  function renderSummaryCards(summary) {
    const host = $("density-avg-summary-cards");
    if (!host) return;

    const s = summary || {};
    const labels = state.config?.summary_labels || {};

    function labelOf(key, fallbackTitle, fallbackSubtitle) {
      const cfg = labels?.[key] || {};

      return {
        title: cfg.title || fallbackTitle,
        subtitle: cfg.subtitle || fallbackSubtitle
      };
    }

    const rowLabel = labelOf("rows", "Rows", "preview result rows");
    const defectLabel = labelOf("defect_cnt", "Defect Count", "sum");
    const glassLabel = labelOf("total_glass_cnt", "Total Glass", "sum");
    const densityLabel = labelOf("density", "Density", "defect / glass");

    const items = [
      { k: rowLabel.title, v: fmtNum(s.rows), u: rowLabel.subtitle },
      { k: defectLabel.title, v: fmtNum(s.defect_cnt), u: defectLabel.subtitle },
      { k: glassLabel.title, v: fmtNum(s.total_glass_cnt), u: glassLabel.subtitle },
      { k: densityLabel.title, v: fmtDensity(s.density), u: densityLabel.subtitle }
    ];

    host.innerHTML = "";

    items.forEach(item => {
      const card = document.createElement("div");
      card.className = "density-avg-summary-card";

      const k = document.createElement("div");
      k.className = "k";
      k.textContent = item.k;

      const v = document.createElement("div");
      v.className = "v";
      v.textContent = item.v;

      const u = document.createElement("div");
      u.className = "u";
      u.textContent = item.u;

      card.appendChild(k);
      card.appendChild(v);
      card.appendChild(u);
      host.appendChild(card);
    });
  }

  // ============================================================
  // Table render
  // ============================================================
  function normalizeCellValue(v) {
    if (v == null) return "";

    if (typeof v === "object") {
      try {
        return JSON.stringify(v);
      } catch (_) {
        return String(v);
      }
    }

    return String(v);
  }

  function isNumericColumn(col) {
    return [
      "defect_cnt",
      "total_glass_cnt",
      "day_count",
      "hour_count",
      "density",
      "avg_hourly_density"
    ].includes(String(col));
  }

  function isDensityColumn(col) {
    return ["density", "avg_hourly_density"].includes(String(col));
  }

  function getCurrentPageShownCount() {
    const total = Array.isArray(state.lastRows) ? state.lastRows.length : 0;
    const size = state.pageSize || 12;
    const start = (state.currentPage - 1) * size;
    const end = Math.min(start + size, total);

    if (total <= 0 || start >= total) return 0;
    return Math.max(0, end - start);
  }

  function updatePreviewStatus(type = "ok") {
    const shown = getCurrentPageShownCount();
    const total = Number(state.previewTotalCount || state.lastRows.length || 0);
    setStatus(`預覽完成：顯示 ${shown} 筆，共 ${total} 筆。`, type);
  }

  function updatePagination() {
    const total = state.lastRows.length || 0;
    const size = state.pageSize || 12;

    state.totalPages = total ? Math.ceil(total / size) : 1;

    if (!state.currentPage || state.currentPage > state.totalPages) {
      state.currentPage = 1;
    }
  }

  function renderPager() {
    const pager = $("density-avg-pager");
    if (!pager) return;

    updatePagination();

    const total = state.lastRows.length || 0;
    const pages = state.totalPages || 1;

    pager.innerHTML = "";

    const info = document.createElement("div");
    info.className = "density-avg-pager-info";
    info.textContent = `第 ${state.currentPage} / ${pages} 頁（共 ${total} 筆）`;
    pager.appendChild(info);

    const prev = document.createElement("button");
    prev.textContent = "上一頁";
    prev.disabled = pages <= 1 || state.currentPage <= 1;
    prev.onclick = () => {
      if (state.currentPage <= 1) return;
      state.currentPage -= 1;
      renderPreviewTable();
      updatePreviewStatus("ok");
    };
    pager.appendChild(prev);

    const maxPageButtons = 7;
    let start = Math.max(1, state.currentPage - 3);
    let end = Math.min(pages, start + maxPageButtons - 1);

    if (end - start + 1 < maxPageButtons) {
      start = Math.max(1, end - maxPageButtons + 1);
    }

    for (let p = start; p <= end; p++) {
      const btn = document.createElement("button");
      btn.textContent = String(p);
      btn.className = "page-btn" + (p === state.currentPage ? " active" : "");
      btn.disabled = pages <= 1;
      btn.onclick = () => {
        if (p === state.currentPage) return;
        state.currentPage = p;
        renderPreviewTable();
        updatePreviewStatus("ok");
      };
      pager.appendChild(btn);
    }

    const next = document.createElement("button");
    next.textContent = "下一頁";
    next.disabled = pages <= 1 || state.currentPage >= pages;
    next.onclick = () => {
      if (state.currentPage >= pages) return;
      state.currentPage += 1;
      renderPreviewTable();
      updatePreviewStatus("ok");
    };
    pager.appendChild(next);
  }

  function renderPreviewTable() {
    const table = $("density-avg-preview-table");
    if (!table) return;

    const thead = table.querySelector("thead");
    const tbody = table.querySelector("tbody");
    if (!thead || !tbody) return;

    const rows = Array.isArray(state.lastRows) ? state.lastRows : [];
    const columns = Array.isArray(state.lastColumns) && state.lastColumns.length
      ? state.lastColumns
      : Object.keys(rows?.[0] || {});

    thead.innerHTML = "";
    tbody.innerHTML = "";

    if (!columns.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.textContent = "（無資料）";
      td.className = "muted";
      tr.appendChild(td);
      tbody.appendChild(tr);
      renderPager();
      return;
    }

    const trh = document.createElement("tr");
    columns.forEach(c => {
      const th = document.createElement("th");
      th.textContent = c;
      if (isNumericColumn(c)) th.classList.add("density-avg-num");
      trh.appendChild(th);
    });
    thead.appendChild(trh);

    const size = state.pageSize || 12;
    const start = (state.currentPage - 1) * size;
    const end = start + size;
    const pageRows = rows.slice(start, end);

    if (!pageRows.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = columns.length;
      td.textContent = "（無資料）";
      td.className = "muted";
      tr.appendChild(td);
      tbody.appendChild(tr);
      renderPager();
      return;
    }

    pageRows.forEach(r => {
      const tr = document.createElement("tr");

      columns.forEach(c => {
        const td = document.createElement("td");
        const val = normalizeCellValue(r?.[c]);

        td.textContent = val;

        if (isNumericColumn(c)) td.classList.add("density-avg-num");
        if (isDensityColumn(c)) td.classList.add("density-avg-density");

        const n = Number(r?.[c]);
        if (isNumericColumn(c) && Number.isFinite(n) && n === 0) {
          td.classList.add("density-avg-zero");
        }

        tr.appendChild(td);
      });

      tbody.appendChild(tr);
    });

    renderPager();
  }

  function clearPreview() {
    state.lastPreview = null;
    state.lastRows = [];
    state.lastColumns = [];
    state.currentPage = 1;
    state.totalPages = 1;
    state.previewTotalCount = 0;
    renderSummaryCards(null);
    renderPreviewTable();
  }

  // ============================================================
  // Actions
  // ============================================================
  MOD.setSystem = async function ({ system, tabKey, config }) {
    console.log("[density_avg] setSystem", { system, tabKey, config });

    state.system = system || "";
    state.tabKey = tabKey || "";
    state.config = config || null;
    state.filtersDirty = false;

    normalizeFilterConfig(state.config);
    ensureDefaultDates(false);

    const badge = $("density-avg-system-badge");
    if (badge) badge.textContent = getSystemLabel(state.system);

    clearPreview();
    setStatus(`目前系統：${getSystemLabel(state.system)}`);

    await refreshOptions({
      keepSelections: false,
      autoPreview: true
    });
  };

  MOD.refreshOptions = refreshOptions;

  MOD.preview = async function () {
    ensureDefaultDates(false);

    const payload = buildPayload();
    if (!validatePayload(payload)) return;

    if (hasBuiltFilters() && hasEmptyFilterSelection()) {
      clearPreview();
      setStatus("有篩選器目前為空，暫不查詢；至少勾選一個選項後才會重新查詢。", "warn");
      return null;
    }

    try {
      state.loadingPreview = true;
      setBusy(true);
      setStatus("計算中...");

      const resp = await API.preview(payload);

      state.lastPreview = resp;
      state.lastRows = Array.isArray(resp?.rows) ? resp.rows : [];
      state.lastColumns = Array.isArray(resp?.columns) ? resp.columns : [];
      state.currentPage = 1;
      state.previewTotalCount = Number(resp?.total_count || state.lastRows.length || 0);

      state.filterOptionDict = resp?.filterOptionDict || state.filterOptionDict || {};
      state.suggestedFilters = resp?.suggestedFilters || {};

      renderSummaryCards(resp?.summary || null);
      renderPreviewTable();
      updatePreviewStatus("ok");

      return resp;
    } catch (err) {
      console.error("[density_avg] preview failed:", err);
      clearPreview();
      setStatus("查詢失敗", "error");
      alert("查詢失敗：" + (err?.message || String(err)));
      return null;
    } finally {
      state.loadingPreview = false;
      setBusy(false);
    }
  };

  MOD.download = async function () {
    ensureDefaultDates(false);

    const payload = buildPayload();
    if (!validatePayload(payload)) return;

    if (hasBuiltFilters() && hasEmptyFilterSelection()) {
      setStatus("有篩選器目前為空，無法下載；至少勾選一個選項。", "warn");
      return null;
    }

    try {
      setBusy(true);
      setStatus("準備下載 Density 平均值 CSV...");

      const result = await API.download(payload);

      setStatus(`下載完成：${result.filename || ""}`, "ok");
      return result;
    } catch (err) {
      console.error("[density_avg] download failed:", err);
      setStatus("下載失敗", "error");
      alert("下載失敗：" + (err?.message || String(err)));
      return null;
    } finally {
      setBusy(false);
    }
  };

  MOD.clearAll = async function () {
    ensureDefaultDates(true);
    clearPreview();

    state.filtersDirty = false;
    state.suppressFilterChange = true;

    try {
      Object.values(state.mdd || {}).forEach(wrap => {
        wrap?.mdd?.setSelected?.([]);
      });
    } finally {
      state.suppressFilterChange = false;
    }

    updateFilterCount();
    setStatus("已清空篩選；目前不查詢資料，請至少勾選一個選項後按「套用篩選」。", "warn");
  };

  MOD.getState = function () {
    return {
      ...state,
      mdd: undefined
    };
  };

  // ============================================================
  // Bind
  // ============================================================
  function bind() {
    if (state.bound) return;
    state.bound = true;

    ensureDefaultDates(false);

    $("density-avg-preview-btn")?.addEventListener("click", async () => {
      await MOD.preview();
    });

    $("density-avg-filter-apply-btn")?.addEventListener("click", async () => {
      await MOD.preview();
    });

    $("density-avg-download-btn")?.addEventListener("click", async () => {
      await MOD.download();
    });

    $("density-avg-clear-btn")?.addEventListener("click", async () => {
      await MOD.clearAll();
    });

    $("density-avg-start")?.addEventListener("change", () => {
      clearPreview();
      refreshOptions({
        keepSelections: true,
        autoPreview: true
      });
    });

    $("density-avg-end")?.addEventListener("change", () => {
      clearPreview();
      refreshOptions({
        keepSelections: true,
        autoPreview: true
      });
    });

    document.addEventListener("density-avg-download:show", (ev) => {
      MOD.setSystem(ev.detail || {});
    });

    clearPreview();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
