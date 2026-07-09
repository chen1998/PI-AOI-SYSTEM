// static/js/bpi_area/bpi_same_point/service.js
(function () {
  const MOD = (window.BPI_SAME_POINT = window.BPI_SAME_POINT || {});
  const API = MOD.API;

  MOD.state = MOD.state || {
    tabKey: "",
    config: null,
  
    payload: null,
    ProSpecDict: {},
  
    rows: [],
    chartRows: [],
    tableRows: [],
    filteredRows: [],
  
    selectedRow: null,
    tableMode: "all",
  
    filterOptionDict: {},
    mdd: {},
    offset: 20,
    subPage: "PISpot",
  
    lastRequest: null,
    isBound: false,
    isLoading: false,
  };
  

  const state = MOD.state;

  const DEFAULT_OFFSETS = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50];
  const DEFAULT_OFFSET = 20;

  function $(id) {
    return document.getElementById(id);
  }

  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  function toYMD(d) {
    return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
  }

  function cleanStr(v) {
    return v == null ? "" : String(v).trim();
  }

  function num(v) {
    const n = Number(v);
    return Number.isFinite(n) ? n : 0;
  }

  // 目前預設回看 15 天；若要回看 3 天，改成 start.setDate(start.getDate() - 2)
  function default3DaysRange() {
    const end = new Date();
    end.setHours(0, 0, 0, 0);

    const start = new Date(end);
    start.setDate(start.getDate() - 15);

    return [toYMD(start), toYMD(end)];
  }

  function ensureDefaultDates(force = false) {
    const s = $("bpi-same-point-start");
    const e = $("bpi-same-point-end");

    if (!s || !e) return;

    const [ds, de] = default3DaysRange();

    if (force || !s.value) s.value = ds;
    if (force || !e.value) e.value = de;
  }

  function readDates() {
    const s = $("bpi-same-point-start")?.value || "";
    const e = $("bpi-same-point-end")?.value || "";

    return s && e ? [s, e] : null;
  }

  function getConfigOffsets() {
    const cfgOffsets =
      state.config?.offsets ||
      state.config?.defect_map?.offsets ||
      state.config?.defectMap?.offsets ||
      state.payload?.ParamDict?.Config?.offsets ||
      state.payload?.ParamDict?.Config?.defect_map?.offsets ||
      state.payload?.ParamDict?.Config?.defectMap?.offsets ||
      [];

    const raw = Array.isArray(cfgOffsets) && cfgOffsets.length
      ? cfgOffsets
      : DEFAULT_OFFSETS;

    const vals = raw
      .map(v => Number(v))
      .filter(v => Number.isFinite(v));

    const uniq = Array.from(new Set(vals)).sort((a, b) => a - b);

    return uniq.length ? uniq : DEFAULT_OFFSETS.slice();
  }

  function getConfigDefaultOffset() {
    const v = Number(
      state.config?.default_offset ||
      state.config?.defect_map?.default_offset ||
      state.config?.defectMap?.default_offset ||
      state.payload?.ParamDict?.Config?.default_offset ||
      state.payload?.ParamDict?.Config?.defect_map?.default_offset ||
      state.payload?.ParamDict?.Config?.defectMap?.default_offset ||
      DEFAULT_OFFSET
    );

    return Number.isFinite(v) ? v : DEFAULT_OFFSET;
  }

  function normalizeOffset(v, offsets) {
    const n = Number(v);
    const list = Array.isArray(offsets) && offsets.length ? offsets : DEFAULT_OFFSETS;

    if (Number.isFinite(n) && list.includes(n)) return n;
    if (list.includes(DEFAULT_OFFSET)) return DEFAULT_OFFSET;

    return list[0] || DEFAULT_OFFSET;
  }

  /**
   * 動態產生 Offset options。
   *
   * preferredOffset:
   * - 第一次進頁面時可傳 20
   * - 使用者切換 offset 後重新 render 時，要傳目前選到的 offset
   * - 不傳時會優先保留 select 目前值，其次 state.offset，其次 config default
   */
  function renderOffsetOptions(preferredOffset) {
    const el = $("bpi-same-point-offset");
    if (!el) return;

    const offsets = getConfigOffsets();

    let rawValue = preferredOffset;

    if (rawValue === undefined || rawValue === null || rawValue === "") {
      rawValue = el.value;
    }

    if (rawValue === undefined || rawValue === null || rawValue === "") {
      rawValue = state.offset;
    }

    if (rawValue === undefined || rawValue === null || rawValue === "") {
      rawValue = getConfigDefaultOffset();
    }

    if (rawValue === undefined || rawValue === null || rawValue === "") {
      rawValue = DEFAULT_OFFSET;
    }

    const currentValue = Number(rawValue);
    const finalOffset = normalizeOffset(currentValue, offsets);

    el.innerHTML = "";

    offsets.forEach(v => {
      const opt = document.createElement("option");
      opt.value = String(v);
      opt.textContent = String(v);
      if (v === finalOffset) opt.selected = true;
      el.appendChild(opt);
    });

    state.offset = finalOffset;
    el.value = String(finalOffset);
  }

  function readOffset() {
    const offsets = getConfigOffsets();
    const el = $("bpi-same-point-offset");

    if (el && !el.options.length) {
      renderOffsetOptions(state.offset || DEFAULT_OFFSET);
    }

    const v = Number(el?.value || state.offset || DEFAULT_OFFSET);
    const finalOffset = normalizeOffset(v, offsets);

    state.offset = finalOffset;

    if (el && el.value !== String(finalOffset)) {
      el.value = String(finalOffset);
    }

    return finalOffset;
  }

  function setStatus(msg) {
    let el = $("bpi-same-point-status");

    if (!el) {
      const info = $("bpi-same-point-info");
      if (info) {
        el = document.createElement("div");
        el.id = "bpi-same-point-status";
        el.className = "muted";
        el.style.marginTop = "4px";
        info.appendChild(el);
      }
    }

    if (el) el.textContent = msg || "";
  }

  function setBusy(flag) {
    state.isLoading = !!flag;

    const ids = [
      "bpi-same-point-apply",
      "bpi-same-point-clear",
      "bpi-same-point-offset",
      "bpi-same-point-map-mode",
      "bpi-same-point-table-return",
    ];

    ids.forEach(id => {
      const el = $(id);
      if (el) el.disabled = !!flag;
    });
  }

  function normalizeRow(r) {
    r = r || {};

    return {
      ...r,

      // source table / key
      _pair_source_table: cleanStr(r._pair_source_table),
      _offset_source_table: cleanStr(r._offset_source_table),

      scan_hour: cleanStr(r.scan_hour),
      run_day: cleanStr(r.run_day),
      tab: cleanStr(r.tab),

      model: cleanStr(r.model),
      glass_side: cleanStr(r.glass_side),
      glass_id: cleanStr(r.glass_id),

      comment: cleanStr(r.comment),
      action: cleanStr(r.action),
      editor: cleanStr(r.editor || r.Editor),
      Editor: cleanStr(r.Editor || r.editor),
      modify_time: cleanStr(r.modify_time),

      // BPI side
      bpi_aoi: cleanStr(r.bpi_aoi),
      bpi_line_id: cleanStr(r.bpi_line_id),
      bpi_scan_time: cleanStr(r.bpi_scan_time),
      bpi_recipe_id: cleanStr(r.bpi_recipe_id),
      bpi_cassette_id: cleanStr(r.bpi_cassette_id),
      bpi_pi_time: cleanStr(r.bpi_pi_time),
      bpi_scan_hour: cleanStr(r.bpi_scan_hour),
      bpi_run_day: cleanStr(r.bpi_run_day),
      bpi_source_db: cleanStr(r.bpi_source_db),
      bpi_source_table: cleanStr(r.bpi_source_table),
      bpi_defect_count: num(r.bpi_defect_count),

      bpi_small_defect_count: num(r.bpi_small_defect_count),
      bpi_middle_defect_count: num(r.bpi_middle_defect_count),
      bpi_large_defect_count: num(r.bpi_large_defect_count),
      bpi_over_defect_count: num(r.bpi_over_defect_count),

      // API side
      api_aoi: cleanStr(r.api_aoi),
      api_line_id: cleanStr(r.api_line_id),
      api_scan_time: cleanStr(r.api_scan_time),
      api_recipe_id: cleanStr(r.api_recipe_id),
      api_cassette_id: cleanStr(r.api_cassette_id),
      api_pi_time: cleanStr(r.api_pi_time),
      api_scan_hour: cleanStr(r.api_scan_hour),
      api_run_day: cleanStr(r.api_run_day),
      api_source_db: cleanStr(r.api_source_db),
      api_source_table: cleanStr(r.api_source_table),
      api_defect_count: num(r.api_defect_count),

      api_small_defect_count: num(r.api_small_defect_count),
      api_middle_defect_count: num(r.api_middle_defect_count),
      api_large_defect_count: num(r.api_large_defect_count),
      api_over_defect_count: num(r.api_over_defect_count),

      // pair meta
      pair_status: cleanStr(r.pair_status),
      pair_message: cleanStr(r.pair_message),
      default_offset_um: num(r.default_offset_um),
      matched_points_json: cleanStr(r.matched_points_json),

      // offset summary
      offset_um: num(r.offset_um),
      matched_pair_count: num(r.matched_pair_count),
      matched_bpi_defect_count: num(r.matched_bpi_defect_count),
      matched_api_defect_count: num(r.matched_api_defect_count),
      unmatched_bpi_defect_count: num(r.unmatched_bpi_defect_count),
      unmatched_api_defect_count: num(r.unmatched_api_defect_count),

      matched_bpi_s_count: num(r.matched_bpi_s_count),
      matched_bpi_m_count: num(r.matched_bpi_m_count),
      matched_bpi_l_count: num(r.matched_bpi_l_count),
      matched_bpi_o_count: num(r.matched_bpi_o_count),

      matched_api_s_count: num(r.matched_api_s_count),
      matched_api_m_count: num(r.matched_api_m_count),
      matched_api_l_count: num(r.matched_api_l_count),
      matched_api_o_count: num(r.matched_api_o_count),

      matched_size_transition_json: cleanStr(r.matched_size_transition_json),
    };
  }

  function normalizeRows(rows) {
    return Array.isArray(rows) ? rows.map(normalizeRow) : [];
  }

  function buildPayload() {
    return {
      dates: readDates(),
      filters: MOD.Filter?.getSelectedFilters?.() || {},
      offset_um: readOffset(),
      sub_page: state.subPage || "PISpot",
    };
  }

  function getDefaultTableRows() {
    return (
      state.tableRows ||
      state.filteredRows ||
      state.rows ||
      []
    );
  }

  function renderDefaultTable() {
    state.selectedRow = null;
    state.tableMode = "all";

    MOD.Table?.render?.(getDefaultTableRows(), {
      mode: "all",
      config: state.config,
    });
  }

  function buildModeTabs() {
    const host = $("bpi-same-point-mode-tabs");
    if (!host) return;

    const modes = ["PISpot", "UPI"];
    host.innerHTML = "";

    modes.forEach(mode => {
      const btn = document.createElement("button");
      btn.className = "sys-tab" + (state.subPage === mode ? " active" : "");
      btn.textContent = mode;
      btn.dataset.mode = mode;

      btn.addEventListener("click", async () => {
        if (state.subPage === mode) return;

        state.subPage = mode;

        Array.from(host.querySelectorAll(".sys-tab")).forEach(b => b.classList.remove("active"));
        btn.classList.add("active");

        await MOD.loadData({ refreshFilter: true, source: "mode" });
      });

      host.appendChild(btn);
    });
  }

  function hasObjectData(obj) {
    if (!obj) return false;
    if (Array.isArray(obj)) return obj.length > 0;
    if (typeof obj === "object") return Object.keys(obj).length > 0;
    return false;
  }
  
  MOD.ensureProSpecLoaded = async function () {
    const current = state.ProSpecDict || state.payload?.ProSpecDict || {};
  
    if (hasObjectData(current?.bpi_same_point_default_spec)) {
      state.ProSpecDict = current;
      return current;
    }
  
    if (!API?.resetFilter) {
      console.error("[BPI_SAME_POINT] API.resetFilter missing");
      return {};
    }
  
    const payload = {
      dates: null,
      filters: {},
      offset_um: state.offset || DEFAULT_OFFSET,
      sub_page: state.subPage || "PISpot",
    };
  
    console.log("[BPI_SAME_POINT] ensureProSpecLoaded payload =", payload);
  
    try {
      const resp = await API.resetFilter(payload);
      const pro = resp?.ProSpecDict || {};
  
      state.ProSpecDict = pro;
  
      // 只保留 ProSpecDict，不重畫 root chart/table，不覆蓋 rows
      state.payload = {
        ...(state.payload || {}),
        ProSpecDict: pro,
      };
  
      console.log("[BPI_SAME_POINT] ensureProSpecLoaded ProSpecDict =", pro);
  
      return pro;
    } catch (err) {
      console.error("[BPI_SAME_POINT] ensureProSpecLoaded failed:", err);
      return {};
    }
  };
  
  


  MOD.loadData = async function (opts) {
    opts = opts || {};
    const refreshFilter = opts.refreshFilter !== false;

    if (!API?.resetFilter) {
      console.error("[BPI_SAME_POINT] API.resetFilter missing");
      return null;
    }

    ensureDefaultDates(false);

    // 保留目前使用者選到的 offset，不要回 default 20
    const offsetEl = $("bpi-same-point-offset");
    const currentOffset = Number(offsetEl?.value || state.offset || DEFAULT_OFFSET);

    if (offsetEl && !offsetEl.options.length) {
      renderOffsetOptions(currentOffset);
    } else {
      state.offset = normalizeOffset(currentOffset, getConfigOffsets());
      if (offsetEl && offsetEl.value !== String(state.offset)) {
        offsetEl.value = String(state.offset);
      }
    }

    const payload = buildPayload();
    state.lastRequest = payload;

    console.log("[BPI_SAME_POINT] reset_filter payload =", JSON.parse(JSON.stringify(payload)));

    try {
      setBusy(true);
      setStatus("同點來料檢資料查詢中...");

      const resp = await API.resetFilter(payload);

      console.log("[BPI_SAME_POINT] reset_filter response =", resp);

      const respConfig = resp?.ParamDict?.Config || {};

      state.payload = resp;
      state.filterOptionDict = resp?.ParamDict?.filterOptionDict || {};
      state.ProSpecDict = resp?.ProSpecDict || {};

      state.chartRows = normalizeRows(resp?.ChartRows || []);
      state.tableRows = normalizeRows(resp?.TableRows || resp?.ChartRows || []);

      // rows / filteredRows 代表 table 級資料，不再用 chartRows
      state.rows = state.tableRows.slice();
      state.filteredRows = state.tableRows.slice();

      state.selectedRow = null;
      state.tableMode = "all";

      state.offset = normalizeOffset(
        Number(resp?.Debug?.offset_um || payload.offset_um || state.offset || DEFAULT_OFFSET),
        getConfigOffsets()
      );

      state.config = {
        ...(state.config || {}),
        ...(respConfig || {}),
      };

      state.subPage =
        respConfig.same_point_page ||
        respConfig.sub_page ||
        state.subPage ||
        "PISpot";

      // reset_filter 回來後 config 可能更新 offsets/default_offset，因此重建 options。
      // 必須保留本次查詢使用的 payload.offset_um，不能回 default 20。
      renderOffsetOptions(payload.offset_um);

      if (refreshFilter) {
        MOD.Filter?.render?.(state.filterOptionDict, state.config);
      } else {
        MOD.Filter?.syncOptionsOnly?.(state.filterOptionDict, state.config);
      }

      // Chart 使用 ChartRows
      MOD.Chart?.render?.(state.chartRows);

      // Table 使用 TableRows
      MOD.Table?.render?.(state.tableRows, {
        mode: "all",
        config: state.config,
      });

      MOD.DefectMap?.clear?.();

      setStatus(`查詢完成：${state.tableRows.length} 筆，offset=${state.offset}um，${state.subPage}`);

      return resp;
    } catch (err) {
      console.error("[BPI_SAME_POINT] loadData failed:", err);
      setStatus("查詢失敗：" + (err?.message || err));
      return null;
    } finally {
      setBusy(false);
    }
  };

  MOD.selectRow = async function (row) {
    state.selectedRow = row || null;
    state.tableMode = "selected";

    // 點 chart bar 後，Table 顯示該 row
    MOD.Table?.render?.(row ? [row] : [], {
      mode: "selected",
      config: state.config,
    });

    await MOD.DefectMap?.load?.();
  };

  MOD.returnTable = function () {
    renderDefaultTable();
    MOD.DefectMap?.clear?.();
  };

  MOD.refreshMap = async function () {
    await MOD.DefectMap?.load?.();
  };

  function bind() {
    if (state.isBound) return;
    state.isBound = true;

    $("bpi-same-point-apply")?.addEventListener("click", () => {
      MOD.loadData({ refreshFilter: true, source: "apply" });
    });

    $("bpi-same-point-clear")?.addEventListener("click", () => {
      ensureDefaultDates(true);
      state.selectedRow = null;
      state.tableMode = "all";
      MOD.Filter?.clear?.();

      // 清空時 offset 回到 default 20
      renderOffsetOptions(DEFAULT_OFFSET);

      MOD.loadData({ refreshFilter: false, source: "clear" });
    });

    $("bpi-same-point-offset")?.addEventListener("change", ev => {
      const selected = Number(ev.target.value || DEFAULT_OFFSET);
      state.offset = normalizeOffset(selected, getConfigOffsets());

      if (ev.target.value !== String(state.offset)) {
        ev.target.value = String(state.offset);
      }

      // offset 改變不刷新 filter options，避免選項越選越少
      MOD.loadData({ refreshFilter: false, source: "offset" });
    });

    $("bpi-same-point-start")?.addEventListener("change", () => {
      setStatus("日期已變更，請按套用查詢。");
    });

    $("bpi-same-point-end")?.addEventListener("change", () => {
      setStatus("日期已變更，請按套用查詢。");
    });

    $("bpi-same-point-map-mode")?.addEventListener("change", () => {
      MOD.refreshMap();
    });
  }

  MOD.show = async function ({ tabKey, config }) {
    state.tabKey = tabKey || "";
    state.config = config || {};

    // 從右上 PISpot / UPI tab config 取得 subPage
    state.subPage =
      state.config?.same_point_page ||
      state.config?.sub_page ||
      state.subPage ||
      "PISpot";

    // 第一次進頁面：依後端 config 動態建立 offset option，預設 20
    renderOffsetOptions(DEFAULT_OFFSET);

    ensureDefaultDates(false);
    bind();
    buildModeTabs();

    await MOD.loadData({ refreshFilter: true, source: "show" });
  };

  document.addEventListener("bpi-same-point:show", async ev => {
    await MOD.show(ev.detail || {});
  });
})();