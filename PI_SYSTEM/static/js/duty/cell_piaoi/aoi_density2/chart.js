// static/js/aoi_density/chart.js
(function () {
  const MOD = (window.AOI_DENSITY = window.AOI_DENSITY || {});
  MOD.Charts = MOD.Charts || {};

  const Shared = window.AOI_DENSITY?.Shared;
  const U = Shared?.U;

  const SLIDER_DEBUG = true;

  const CHART_THEME = {
    axisLabel: "#aeb6c7",
    axisLine: "#2b3240",
    axisTick: "#3a4354",
    splitLine: "rgba(255,255,255,0.09)",
    splitLineStrong: "rgba(255,255,255,0.14)",
    labelText: "#e8edf7",
    labelBg: "rgba(15,18,27,0.85)",
    labelPad: [2, 4],
    labelRadius: 3,
    mlText: "#eaefff",
    mlBg: "rgba(13,18,27,0.9)"
  };

  const CHART_COLOR = {
    glassTotalBar: "#9aa3b2",
    defectGlassBar: "#FF851B",
    densityPoint: "#FF4136",
    totalDensityPoint: "#7FDBFF",
    defaultSpecOOC: "#FFDC00",
    defaultSpecOOS: "#CE0000",
    fixedSpecOOC: "#FFDC00",
    fixedSpecOOS: "#CE0000"
  };

  const ALERT_CONFIG = {
    totalDensityThreshold: 1000,
    blinkMs: 650,
    blinkColorA: "#ff0000",
    blinkColorB: "#0066ff"
  };

  // =====================
  // Accessor
  // =====================
  function s(v) {
    return v == null ? "" : String(v);
  }

  function n(v) {
    const x = Number(v);
    return Number.isFinite(x) ? x : 0;
  }

  const A = {
    line: r => U?.line ? U.line(r) : s(r?.line_id),
    aoi: r => U?.aoi ? U.aoi(r) : s(r?.aoi),
    model: r => U?.model ? U.model(r) : s(r?.model),
    side: r => U?.side ? U.side(r) : s(r?.glass_type),
    tick: r => U?.tick ? U.tick(r) : s(r?.pi_hour),
    tickRaw: r => U?.tickRaw ? U.tickRaw(r) : s(r?.pi_hour_raw || r?.pi_hour),
    recipe: r => U?.recipe ? U.recipe(r) : s(r?.recipe_id),
    code: r => U?.code ? U.code(r) : s(r?.adc_def_code),

    tabG: r => U?.tabGlass ? n(U.tabGlass(r)) : n(r?.tab_total_glass_cnt ?? r?.total_glass_cnt),
    tabD: r => U?.tabDefect ? n(U.tabDefect(r)) : n(r?.tab_total_defect_cnt ?? r?.total_defect_cnt),
    tabDensity: r => U?.tabDensity ? n(U.tabDensity(r)) : n(r?.tab_total_density ?? r?.total_density),

    recipeG: r => U?.recipeGlass ? n(U.recipeGlass(r)) : n(r?.recipe_total_glass_cnt ?? r?.glass_cnt),
    recipeD: r => U?.recipeDefect ? n(U.recipeDefect(r)) : n(r?.recipe_total_defect_cnt),
    recipeDensity: r => U?.recipeDensity ? n(U.recipeDensity(r)) : n(r?.recipe_total_density),

    d: r => U?.dTotal ? n(U.dTotal(r)) : n(r?.defect_cnt),
    cg: r => U?.gCode ? n(U.gCode(r)) : n(r?.def_glass_cnt),
    dens: r => U?.dens ? n(U.dens(r)) : n(r?.density),

    sCnt: r => n(r?.small_defect_count),
    mCnt: r => n(r?.middle_defect_count),
    lCnt: r => n(r?.large_defect_count),
    oCnt: r => n(r?.over_defect_count)
  };

  // =====================
  // 時間工具
  // =====================
  function parseTickToDate(tick) {
    if (Shared?.parsePiHourToDate) return Shared.parsePiHourToDate(tick);
    const raw = String(tick || "").trim();
    if (!raw) return null;
    const d = new Date(raw.replace(" ", "T"));
    return isNaN(d.getTime()) ? null : d;
  }

  function tickToShort(tick) {
    if (Shared?.fmtPiHourToShort) return Shared.fmtPiHourToShort(tick);
    return String(tick || "");
  }

  function tickSort(a, b) {
    const da = parseTickToDate(a);
    const db = parseTickToDate(b);
    return (da?.getTime() ?? 0) - (db?.getTime() ?? 0);
  }

  function rawActiveTabKey() {
    return window.AOI_DENSITY?.state?.activeSubTab || window.density_sub_activeTabKey || "";
  }

  function normalizeDensityTabKey(tabKey) {
    if (window.AOI_DENSITY?.normalizeDensityTabKey) {
      return window.AOI_DENSITY.normalizeDensityTabKey(tabKey);
    }
  
    const x = String(tabKey || "").trim();
    if (!x) return "";
  
    const defs = window.AOI_DENSITY?.state?.paramDict?.SubTabsFilterDefaultDict?.[x] || {};
    const backend = String(defs.backend_tab_name || "").trim();
  
    if (backend) return backend;
  
    if (x === "UPI(Total)") return "UPI_Total";
    if (x === "PISpot(Total)") return "PISpot_Total";
  
    return x;
  }

  function activeTabKey() {
    return normalizeDensityTabKey(rawActiveTabKey());
  }

  function activeTabDefs() {
    const raw = rawActiveTabKey();
    const backend = activeTabKey();
    const map = window.AOI_DENSITY?.state?.paramDict?.SubTabsFilterDefaultDict || {};
  
    return map[raw] || map[backend] || {};
  }


  function isSamePointTabActive() {
    return window.AOI_DENSITY?.isSamePointTab?.(
      window.AOI_DENSITY?.state?.activeSubTab || window.density_sub_activeTabKey
    );
  }
  
  function makeSamePointKeyByValues(tick, line, aoi, model, side, recipe) {
    let pi = String(tick || "").trim();
  
    if (window.AOI_DENSITY?.Shared?.fmtPiHourToBackend) {
      pi = window.AOI_DENSITY.Shared.fmtPiHourToBackend(pi);
    } else if (/^\d{2}-\d{2}-\d{2}\s+\d{2}$/.test(pi)) {
      const [d, h] = pi.split(/\s+/);
      const [yy, mm, dd] = d.split("-");
      pi = `20${yy}-${mm}-${dd} ${h}:00:00`;
    } else if (/^\d{4}-\d{2}-\d{2}\s+\d{2}$/.test(pi)) {
      pi = `${pi}:00:00`;
    } else if (/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}$/.test(pi)) {
      pi = `${pi}:00`;
    }
  
    return [
      pi,
      String(line || ""),
      String(aoi || ""),
      String(model || ""),
      String(side || ""),
      String(recipe || "")
    ].join("||");
  }
  
  function hasSamePointForChartCell(tick, row, aoi) {
    if (!isSamePointTabActive()) return false;
  
    const idx = window.AOI_DENSITY?.state?.SamePointIndex || {};
    if (!idx || typeof idx !== "object") return false;
  
    const recipeList = String(row?.recipe_list || row?.recipe_id || "")
      .split(",")
      .map(x => x.trim())
      .filter(Boolean);
  
    const recipes = recipeList.length ? recipeList : [String(row?.recipe_id || "")];
  
    return recipes.some(recipe => {
      const key = makeSamePointKeyByValues(
        tick,
        row?.line_id,
        aoi,
        row?.model,
        row?.glass_type,
        recipe
      );
  
      const sp = idx[key];
      /*if (!sp && isSamePointTabActive()) {
        console.debug("[same-point-miss]", {
          tick,
          line: row?.line_id,
          aoi,
          model: row?.model,
          side: row?.glass_type,
          recipe,
          key,
          idxSample: Object.keys(idx).slice(0, 3)
        });
      }*/
      
      return sp && Number(sp.common_cnt || 0) > 0;
    });
  }


  function isTotalDensityTab() {
    const x = String(rawActiveTabKey() || "").trim();
    return x === "UPI(Total)" || x === "PISpot(Total)";
  }

  function buildDefaultLegendSelectedState() {
    const isTotal = isTotalDensityTab();

    return {
      "glass (total)": true,
      "defect glass": false,
      "density": !isTotal,
      "Total defect density": isTotal,
      "預設SPEC": true,
      "動態SPEC": false
    };
  }

  // =====================
  // Alert helpers
  // =====================
  function getAlertDatesFromUI() {
    try {
      const b = document.querySelector("#aoi-density-start")?.value;
      const e = document.querySelector("#aoi-density-end")?.value;
      return (b && e) ? [b, e] : null;
    } catch (_) {
      return null;
    }
  }

  function shouldTotalDensityPointAlert(v) {
    const x = Number(v);
    return Number.isFinite(x) && x > ALERT_CONFIG.totalDensityThreshold;
  }

  function buildAlertRowFromChartPoint(row, tickStr, aoi, code, totalDensity, tabTG, tabTD) {
    return {
      pi_hour: tickStr,
      pi_hour_raw: tickStr,

      line_id: String(row?.line_id || ""),
      aoi: String(aoi || row?.aoi || ""),
      model: String(row?.model || ""),
      glass_type: String(row?.glass_type || ""),

      adc_def_code: String(code || row?.code || ""),
      recipe_id: String(row?.recipe_id || ""),

      tab_total_glass_cnt: Number(tabTG || 0),
      tab_total_defect_cnt: Number(tabTD || 0),
      tab_total_density: Number(totalDensity || 0),

      total_glass_cnt: Number(tabTG || 0),
      total_defect_cnt: Number(tabTD || 0),
      total_density: Number(totalDensity || 0),

      alert_source: "aoi_density_chart_total_scatter"
    };
  }

  function fireAlertRowsOnce(alertRows) {
    if (!Array.isArray(alertRows) || !alertRows.length) return;

    const tabKey = rawActiveTabKey();
    const dates = getAlertDatesFromUI();

    /*alertRows.forEach(r => {
      window.AOI_DENSITY?.sendDensityMailAlert?.(r, {
        tabKey,
        threshold: ALERT_CONFIG.totalDensityThreshold,
        dates
      });
    });*/
  }

  function stopTotalDensityBlink(inst) {
    if (!inst) return;

    if (inst.__aoiDensityBlinkTimer) {
      clearInterval(inst.__aoiDensityBlinkTimer);
      inst.__aoiDensityBlinkTimer = null;
    }
  }

  function startTotalDensityBlink(inst) {
    if (!inst) {
      stopTotalDensityBlink(inst);
      return;
    }
  
    stopTotalDensityBlink(inst);
  
    let flag = false;
  
    inst.__aoiDensityBlinkTimer = setInterval(() => {
      flag = !flag;
  
      let op;
      try {
        op = inst.getOption();
      } catch (_) {
        return;
      }
  
      const updates = [];
  
      (op?.series || []).forEach(ss => {
        const sid = String(ss.id || "");
  
        // 改成閃爍預設 density scatter：sc:...
        // 注意不要用 startsWith("sc")，避免 scTotal 也被打到。
        if (!sid.startsWith("sc:")) return;
        if (!Array.isArray(ss.data)) return;
  
        const newData = ss.data.map(p => {
          if (!p || !p.needAlert) return p;
  
          return {
            ...p,
            itemStyle: {
              ...(p.itemStyle || {}),
              color: flag ? ALERT_CONFIG.blinkColorA : ALERT_CONFIG.blinkColorB
            }
          };
        });
  
        updates.push({
          id: sid,
          data: newData
        });
      });
  
      if (updates.length) {
        inst.setOption({ series: updates }, false, true);
      }
    }, ALERT_CONFIG.blinkMs);
  }
  

  // =====================
  // Filter helpers
  // =====================
  function getSelectedSizes() {
    try {
      const ui = window.AOI_DENSITY?.readFiltersFromUI?.();
      const ds = ui?.defect_size;
      if (Array.isArray(ds) && ds.length) return ds;
    } catch (_) {}
    return ["S", "M", "L", "O"];
  }

  function getSelectedCodes(rows) {
    try {
      const ui = window.AOI_DENSITY?.readFiltersFromUI?.();
      const arr = ui?.adc_def_code;
  
      // 使用者有操作 defect code 時，一律以 UI 為準
      if (Array.isArray(arr) && arr.length) {
        return arr.map(x => String(x).trim()).filter(Boolean);
      }
    } catch (_) {}
  
    const codes = new Set();
  
    (rows || []).forEach(r => {
      const c = A.code(r);
      if (c) codes.add(c);
    });
  
    const fromRows = Array.from(codes).sort();
    if (fromRows.length) return fromRows;
  
    const defs = activeTabDefs();
    const defArr = defs?.adc_def_code;
  
    if (Array.isArray(defArr) && defArr.length) {
      return defArr.map(x => String(x).trim()).filter(Boolean);
    }
  
    return [
      "Polymer",
      "SSIU_Polymer",
      "PI_Spot_NP",
      "PIS With Particle",
      "SPS",
      "NPI_TFT",
      "others"
    ];
  }
  function getChartDateRange() {
    try {
      const b = document.querySelector("#aoi-density-start")?.value;
      const e = document.querySelector("#aoi-density-end")?.value;

      if (!b || !e) return null;

      return {
        start: new Date(b + "T00:00:00").getTime(),
        end: new Date(e + "T23:59:59").getTime()
      };
    } catch (_) {
      return null;
    }
  }

  function passesChartDateFilter(piHour, dateRange) {
    if (!dateRange) return true;

    const d = Shared?.parsePiHourToDate?.(piHour);
    if (!d) return false;

    const t = d.getTime();
    return t >= dateRange.start && t <= dateRange.end;
  }

  function getChartBaseFilters() {
    let filters = {};

    try {
      filters = window.AOI_DENSITY?.readFiltersFromUI?.() || {};
    } catch (_) {
      filters = {};
    }

    return {
      line_id: Array.isArray(filters.line_id) ? filters.line_id.map(String) : [],
      aoi: Array.isArray(filters.aoi) ? filters.aoi.map(String) : [],
      model: Array.isArray(filters.model) ? filters.model.map(String) : [],
      glass_type: Array.isArray(filters.glass_type) ? filters.glass_type.map(String) : []
    };
  }

  function passesChartBaseFilters(row, baseFilters) {
    const checks = ["line_id", "aoi", "model", "glass_type"];

    for (const k of checks) {
      const arr = baseFilters?.[k];

      if (Array.isArray(arr) && arr.length) {
        if (!arr.includes(String(row?.[k] ?? ""))) {
          return false;
        }
      }
    }

    return true;
  }

  // =====================
  // Defect size + SPEC 工具
  // =====================
  function canonicalSizeKeyFromList(list) {
    if (!Array.isArray(list) || !list.length) return "";

    const chars = list
      .map(x => String(x).trim().toUpperCase()[0])
      .filter(ch => "SMLO".includes(ch));

    const uniq = Array.from(new Set(chars)).sort();
    return uniq.join("");
  }

  function canonicalSizeKeyFromString(v) {
    if (!v) return "";

    const chars = String(v)
      .toUpperCase()
      .split("")
      .filter(ch => "SMLO".includes(ch));

    const uniq = Array.from(new Set(chars)).sort();
    return uniq.join("");
  }

  function toNum(v) {
    const x = Number(v);
    return Number.isFinite(x) ? x : null;
  }

  // =====================
  // Default SPEC index
  // =====================
  function buildDefaultSpecIndex(rows) {
    const idx = {};
    if (!Array.isArray(rows)) return idx;

    rows.forEach(r => {
      if (!r) return;

      const model = String(r.MODEL_ID ?? r.model ?? "").trim();
      const code = String(r.DEFECT_CODE ?? r.adc_def_code ?? r.ai_code_1 ?? "").trim();
      const sizeKey = canonicalSizeKeyFromString(r.SIZE_TYPE ?? r.defect_size ?? "");

      if (!model || !code || !sizeKey) return;

      const ooc = toNum(r.OOC);
      const oos = toNum(r.OOS);

      if (ooc == null && oos == null) return;

      (((idx[model] = idx[model] || {})[code] = idx[model][code] || {})[sizeKey] = {
        ooc,
        oos
      });
    });

    return idx;
  }

  function pickDefaultSpec(defaultIdx, model, code, sizeKey) {
    const byModel = defaultIdx?.[model];
    if (!byModel) return null;

    const byCode = byModel[code];
    if (!byCode) return null;

    if (sizeKey && byCode[sizeKey]) return byCode[sizeKey];

    const anyKey = Object.keys(byCode)[0];
    return anyKey ? byCode[anyKey] : null;
  }

  // =====================
  // Fixed SPEC index
  // =====================
  function buildFixedSpecIndex(rows) {
    const idx = {};
    if (!Array.isArray(rows)) return idx;

    rows.forEach(r => {
      if (!r) return;

      const line = String(r.line_id || "").trim();
      const aoi = String(r.aoi || "").trim();
      const model = String(r.model || "").trim();
      const code = String(r.adc_def_code ?? r.DEFECT_CODE ?? r.ai_code_1 ?? "").trim();
      const recipe = String(r.recipe_id || "").trim();
      const side = String(r.glass_type || "").trim();
      const sizeKey = canonicalSizeKeyFromString(r.size_key ?? r.SIZE_KEY ?? r.defect_size ?? r.DEFECT_SIZE ?? "");

      if (!line || !aoi || !model || !code || !recipe || !side || !sizeKey) return;

      const ooc = toNum(r.OOC);
      const oos = toNum(r.OOS);

      if (ooc == null && oos == null) return;

      const key = [line, aoi, model, code, recipe, side, sizeKey].join("|");
      idx[key] = { ooc, oos };
    });

    return idx;
  }

  function pickFixedSpec(fixedIdx, line, aoi, model, code, recipe, side, sizeKey) {
    if (!fixedIdx) return null;

    const exactKey = [line, aoi, model, code, recipe, side, sizeKey].join("|");
    if (fixedIdx[exactKey]) return fixedIdx[exactKey];

    const prefix = [line, aoi, model, code, recipe, side].join("|") + "|";
    const keys = Object.keys(fixedIdx).filter(k => k.startsWith(prefix));

    return keys.length ? fixedIdx[keys[0]] : null;
  }

  // =====================
  // 全局 row order: line -> model -> side
  // =====================
  function buildGlobalRowOrder(rows) {
    const byLine = new Map();

    (rows || []).forEach(r => {
      const line = A.line(r);
      const model = A.model(r);
      const side = A.side(r);

      if (!line || !model || !side) return;

      if (!byLine.has(line)) byLine.set(line, new Map());
      const byModel = byLine.get(line);

      if (!byModel.has(model)) byModel.set(model, new Set());
      byModel.get(model).add(side);
    });

    const lines = Array.from(byLine.keys()).sort();
    const order = [];

    lines.forEach(line => {
      const byModel = byLine.get(line);
      const models = Array.from(byModel.keys()).sort();

      models.forEach(model => {
        const sides = Array.from(byModel.get(model)).sort();

        sides.forEach(side => {
          order.push({
            line_id: line,
            model,
            glass_type: side
          });
        });
      });
    });

    const lineGroups = [];
    let i = 0;

    while (i < order.length) {
      const line = order[i].line_id;
      const start = i;

      while (i < order.length && order[i].line_id === line) i++;

      lineGroups.push({
        line_id: line,
        start,
        end: i - 1
      });
    }

    return { order, lineGroups };
  }

  // =====================
  // TabSummaryData helpers
  // =====================
  function getTabRowsForChart(tabRows) {
    const tab = activeTabKey();
    const baseFilters = getChartBaseFilters();
    const dateRange = getChartDateRange();
  
    return (tabRows || []).filter(r => {
      const rowTab = String(r.tab_name || "").trim();
  
      if (tab && rowTab && rowTab !== String(tab)) return false;
  
      if (!passesChartBaseFilters(r, baseFilters)) return false;
      if (!passesChartDateFilter(r.pi_hour, dateRange)) return false;
  
      return true;
    });
  }

  function buildTabTotalAgg(tabRows, tabName) {
    const out = Object.create(null);
    const active = tabName || activeTabKey();
    const baseFilters = getChartBaseFilters();
    const dateRange = getChartDateRange();

    (tabRows || []).forEach(r => {
      const tn = String(r?.tab_name || "").trim();
      if (active && tn !== active) return;

      if (!passesChartBaseFilters(r, baseFilters)) return;
      if (!passesChartDateFilter(r.pi_hour, dateRange)) return;

      const tick = tickToShort(r?.pi_hour);
      const aoi = String(r?.aoi || "").trim();
      const line = String(r?.line_id || "").trim();
      const model = String(r?.model || "").trim();
      const side = String(r?.glass_type || "").trim();

      if (!tick || !aoi || !line || !model || !side) return;

      const key = `${tick}|${aoi}|${line}|${model}|${side}`;

      out[key] = {
        tab_name: tn,
        TG: n(r?.tab_total_glass_cnt),
        TD: n(r?.tab_total_defect_cnt),
        TotalDensity: Number.isFinite(Number(r?.tab_total_density))
          ? Number(r?.tab_total_density)
          : null,
        recipe_list: String(r?.recipe_list || "")
      };
    });

    const dict = window.AOI_DENSITY?.state?.TabTotalDict || {};
    const dtab = active ? (dict?.[active] || {}) : {};

    Object.entries(dtab).forEach(([backendKey, v]) => {
      const parts = String(backendKey).split("||");
      if (parts.length < 5) return;

      const [rawPiHour, line, aoi, model, side] = parts;

      const rowLike = {
        line_id: line,
        aoi,
        model,
        glass_type: side
      };

      if (!passesChartBaseFilters(rowLike, baseFilters)) return;
      if (!passesChartDateFilter(rawPiHour, dateRange)) return;

      const tick = tickToShort(rawPiHour);

      if (!tick || !aoi || !line || !model || !side) return;

      const key = `${tick}|${aoi}|${line}|${model}|${side}`;

      if (out[key]) return;

      out[key] = {
        tab_name: active,
        TG: n(v?.tab_total_glass_cnt),
        TD: n(v?.tab_total_defect_cnt),
        TotalDensity: Number.isFinite(Number(v?.tab_total_density))
          ? Number(v?.tab_total_density)
          : null,
        recipe_list: ""
      };
    });

    if (!Object.keys(out).length) {
      console.warn("[chart] tabAgg empty", {
        activeTab: active,
        rawActiveTab: rawActiveTabKey(),
        baseFilters,
        dateRange,
        tabRowsLen: Array.isArray(tabRows) ? tabRows.length : 0,
        tabTotalDictKeys: Object.keys(dict || {}),
        sampleTabRows: Array.isArray(tabRows) ? tabRows.slice(0, 3) : [],
        sampleDict: active && dict?.[active]
          ? Object.entries(dict[active]).slice(0, 3)
          : null
      });
    }

    return out;
  }

  function tabAggToSeedRows(tabAgg) {
    const out = [];

    Object.keys(tabAgg || {}).forEach(key => {
      const parts = String(key).split("|");
      if (parts.length < 5) return;

      const [tick, aoi, line_id, model, glass_type] = parts;

      out.push({
        pi_hour: tick,
        line_id,
        aoi,
        model,
        glass_type
      });
    });

    return out;
  }

  function getTabAggValue(tabAgg, tick, aoi, line, model, side, fallbackRow) {
    const key = `${tick}|${aoi}|${line}|${model}|${side}`;

    if (tabAgg && tabAgg[key]) {
      return tabAgg[key];
    }

    if (fallbackRow) {
      const TG = n(fallbackRow?.tab_total_glass_cnt ?? fallbackRow?.total_glass_cnt);
      const TD = n(fallbackRow?.tab_total_defect_cnt ?? fallbackRow?.total_defect_cnt);
      const D = Number(fallbackRow?.tab_total_density ?? fallbackRow?.total_density);

      if (TG > 0 || TD > 0) {
        return {
          TG,
          TD,
          TotalDensity: Number.isFinite(D) ? D : (TG > 0 ? TD / TG : null),
          recipe_list: ""
        };
      }
    }

    return {
      TG: 0,
      TD: 0,
      TotalDensity: null,
      recipe_list: ""
    };
  }

  // =====================
  // 聚合：TabSummaryData skeleton + filtered code rows
  // =====================

  function safeParseJsonObject(v) {
    if (!v) return {};
  
    if (typeof v === "object" && !Array.isArray(v)) {
      return v;
    }
  
    if (typeof v === "string") {
      const s = v.trim();
      if (!s) return {};
  
      try {
        const obj = JSON.parse(s);
        return obj && typeof obj === "object" && !Array.isArray(obj) ? obj : {};
      } catch (_) {
        return {};
      }
    }
  
    return {};
  }
  
  function getRowGlassSizeDetailObj(row) {
    return (
      row?.glass_size_detail_obj ||
      safeParseJsonObject(row?.glass_size_detail) ||
      {}
    );
  }
  
  function addDefectGlassesFromRow(targetSet, row) {
    if (!targetSet || !row) return 0;
  
    const detail = getRowGlassSizeDetailObj(row);
    let added = 0;
  
    if (detail && typeof detail === "object" && Object.keys(detail).length) {
      Object.entries(detail).forEach(([glassId, stat]) => {
        const gid = String(glassId || "").trim();
        if (!gid || !stat || typeof stat !== "object") return;
  
        const t = Number(stat.T || 0);
  
        if (t > 0 && !targetSet.has(gid)) {
          targetSet.add(gid);
          added += 1;
        }
      });
  
      return added;
    }
  
    // fallback：如果沒有 glass_size_detail，就退回 glass 欄位。
    // 但這種 fallback 可能偏鬆，正常新版資料應該會有 glass_size_detail。
    const glassRaw = String(row.glass || "").trim();
  
    if (glassRaw) {
      glassRaw
        .split(",")
        .map(x => x.trim())
        .filter(Boolean)
        .forEach(gid => {
          if (!targetSet.has(gid)) {
            targetSet.add(gid);
            added += 1;
          }
        });
    }
  
    return added;
  }

  function calcTooltipCountsFromRows(pick) {
    const seenRows = new Set();
  
    let dCode = 0;
    let S = 0;
    let M = 0;
    let L = 0;
    let O = 0;
  
    (pick || []).forEach(rec => {
      const rowUid = String(
        rec?.row_uid ||
        [
          A.tickRaw(rec),
          A.line(rec),
          A.aoi(rec),
          A.model(rec),
          A.side(rec),
          String(rec?.tab_name || ""),
          A.recipe(rec),
          A.code(rec)
        ].join("||")
      );
  
      if (seenRows.has(rowUid)) return;
      seenRows.add(rowUid);
  
      dCode += n(rec.defect_cnt);
      S += n(rec.small_defect_count);
      M += n(rec.middle_defect_count);
      L += n(rec.large_defect_count);
      O += n(rec.over_defect_count);
    });
  
    return {
      dCode,
      S,
      M,
      L,
      O
    };
  }

  
  function buildColumnsByAoiCode(rows, globalOrder, defaultSpecIndex, fixedSpecIndex, selectedSizesArr, tabAgg, seedCodes) {
    const selected = new Set(
      selectedSizesArr && selectedSizesArr.length ? selectedSizesArr : ["S", "M", "L", "O"]
    );
  
    const selectedSizeKey = canonicalSizeKeyFromList(Array.from(selected));
  
    const agg = {};
    const ticksByAoiCode = {};
    const codesToSeed = Array.isArray(seedCodes) && seedCodes.length ? seedCodes : [];
  
    Object.keys(tabAgg || {}).forEach(key => {
      const parts = String(key).split("|");
      if (parts.length < 5) return;
  
      const [tick, aoi, line, model, side] = parts;
  
      codesToSeed.forEach(code => {
        if (!aoi || !code || !line || !model || !tick || !side) return;
  
        const acKey = `${aoi}|${code}`;
        (ticksByAoiCode[acKey] = ticksByAoiCode[acKey] || new Set()).add(tick);
  
        const Aoi = (agg[aoi] = agg[aoi] || {});
        const C = (Aoi[code] = Aoi[code] || {});
        const L = (C[line] = C[line] || {});
        const M = (L[model] = L[model] || {});
        const S = (M[side] = M[side] || {});
  
        if (!S[tick]) {
          S[tick] = {
            d: 0,
            cg: 0,
            glassSet: new Set(),
            s: 0,
            m: 0,
            l: 0,
            o: 0,
            rows: [],
            seenRows: new Set()
          };
        }
      });
    });
  
    (rows || []).forEach(r => {
      const aoi = A.aoi(r);
      const code = A.code(r);
      const line = A.line(r);
      const model = A.model(r);
      const tick = A.tick(r);
      const side = A.side(r);
  
      if (!aoi || !code || !line || !model || !tick || !side) return;
  
      const key = `${aoi}|${code}`;
      (ticksByAoiCode[key] = ticksByAoiCode[key] || new Set()).add(tick);
  
      const Aoi = (agg[aoi] = agg[aoi] || {});
      const C = (Aoi[code] = Aoi[code] || {});
      const L = (C[line] = C[line] || {});
      const M = (L[model] = L[model] || {});
      const S = (M[side] = M[side] || {});
      const T = (S[tick] = S[tick] || {
        d: 0,
        cg: 0,
        glassSet: new Set(),
        s: 0,
        m: 0,
        l: 0,
        o: 0,
        rows: [],
        seenRows: new Set()
      });
  
      const rowUid = String(
        r?.row_uid ||
        [
          A.tickRaw(r),
          A.line(r),
          A.aoi(r),
          A.model(r),
          A.side(r),
          String(r?.tab_name || ""),
          A.recipe(r),
          A.code(r)
        ].join("||")
      );
  
      if (T.seenRows.has(rowUid)) return;
      T.seenRows.add(rowUid);
  
      T.d += A.d(r);
  
      if (!(T.glassSet instanceof Set)) {
        T.glassSet = new Set();
      }
  
      const beforeGlassSetSize = T.glassSet.size;
      addDefectGlassesFromRow(T.glassSet, r);
  
      if (T.glassSet.size > beforeGlassSetSize || beforeGlassSetSize > 0) {
        T.cg = T.glassSet.size;
      } else {
        T.cg += A.cg(r);
      }
  
      T.s += A.sCnt(r);
      T.m += A.mCnt(r);
      T.l += A.lCnt(r);
      T.o += A.oCnt(r);
  
      T.rows.push(r);
    });
  
    const columns = [];
  
    Object.keys(agg).sort().forEach(aoi => {
      const perCode = agg[aoi];
  
      Object.keys(perCode).sort().forEach(code => {
        const xTicks = Array.from(ticksByAoiCode[`${aoi}|${code}`] || []).sort(tickSort);
  
        const rowsOut = globalOrder.map(({ line_id, model, glass_type }) => {
          const bucket =
            ((((agg[aoi] || {})[code] || {})[line_id] || {})[model] || {})[glass_type] || {};
  
          const totalDefArr = [];
          const totalGlassArr = [];
          const totalDensity = [];
  
          const tabTotalDefArr = [];
          const tabTotalGlassArr = [];
          const tabTotalDensity = [];
  
          const codeGlasses = [];
          const density = [];
  
          const sArr = [];
          const mArr = [];
          const lArr = [];
          const oArr = [];
          const defSelArr = [];
          const samePointArr = [];
  
          let repRecipe = "";
          let repGlassType = glass_type || "";
  
          xTicks.forEach(tk => {
            const T = bucket[tk] || {
              d: 0,
              cg: 0,
              glassSet: new Set(),
              s: 0,
              m: 0,
              l: 0,
              o: 0,
              rows: []
            };
  
            const fallbackRow = Array.isArray(T.rows) && T.rows.length ? T.rows[0] : null;
            const tab = getTabAggValue(tabAgg, tk, aoi, line_id, model, glass_type, fallbackRow);
  
            const TG = Number(tab.TG || 0);
            const TD = Number(tab.TD || 0);
  
            const totalD = Number.isFinite(Number(tab.TotalDensity))
              ? Number(tab.TotalDensity)
              : (TG > 0 ? TD / TG : null);
  
            const dSel = Number(T.d || 0);
            const cg = Number(T.cg || 0);
  
            totalGlassArr.push(TG);
            totalDefArr.push(TD);
            totalDensity.push(totalD);
  
            tabTotalGlassArr.push(TG);
            tabTotalDefArr.push(TD);
            tabTotalDensity.push(totalD);
  
            codeGlasses.push(cg);
            defSelArr.push(dSel);
  
            sArr.push(Number(T.s || 0));
            mArr.push(Number(T.m || 0));
            lArr.push(Number(T.l || 0));
            oArr.push(Number(T.o || 0));
  
            density.push(TG > 0 ? dSel / TG : null);

            let currentRecipe = repRecipe;
            let currentGlassType = repGlassType || glass_type || "";

            if (Array.isArray(T.rows) && T.rows.length) {
              const found = T.rows.find(rr =>
                String(rr.glass_type ?? "").trim() === String(glass_type ?? "").trim() &&
                String(rr.recipe_id ?? "").trim()
              ) || T.rows.find(rr => String(rr.recipe_id ?? "").trim()) || T.rows[0];

              if (found) {
                currentRecipe = String(found.recipe_id ?? "").trim() || currentRecipe;
                currentGlassType = String(found.glass_type ?? "").trim() || currentGlassType;

                if (!repRecipe) repRecipe = currentRecipe;
                if (!repGlassType) repGlassType = currentGlassType;
              }
            }

            samePointArr.push(hasSamePointForChartCell(tk, {
              ...T,
              line_id,
              model,
              glass_type: currentGlassType,
              recipe_id: currentRecipe,
              recipe_list: tab.recipe_list || ""
            }, aoi));




          });
  
          const specDefault = pickDefaultSpec(defaultSpecIndex, model, code, selectedSizeKey);
          const specFixed = pickFixedSpec(
            fixedSpecIndex,
            line_id,
            aoi,
            model,
            code,
            repRecipe,
            repGlassType || "TFT",
            selectedSizeKey
          );
  
          return {
            aoi,
            code,
            line_id,
            model,
            glass_type,
  
            totalDefArr,
            totalGlassArr,
            totalDensity,
  
            tabTotalDefArr,
            tabTotalGlassArr,
            tabTotalDensity,
  
            codeGlasses,
            density,
  
            sArr,
            mArr,
            lArr,
            oArr,
            defSelArr,
            samePointArr,
  
            maxG: Math.max(0, ...tabTotalGlassArr, ...codeGlasses),
            maxDensity: Math.max(0, ...density.filter(x => x != null)),
            maxTotalDensity: Math.max(0, ...tabTotalDensity.filter(x => x != null)),
  
            specDefault: specDefault || null,
            specFixed: specFixed || null
          };
        });
  
        columns.push({
          aoi,
          code,
          xTicks,
          rows: rowsOut
        });
      });
    });
  
    return columns;
  }
  

  // =====================
  // 畫布/互動狀態
  // =====================
  function ensureHost() {
    const host = document.querySelector("#aoi-density-facet");
    if (!host) return null;

    host.innerHTML = "";
    host.style.overflow = "visible";

    const chartDiv = document.createElement("div");
    chartDiv.className = "aoi-bigchart";
    chartDiv.style.height = "320px";
    chartDiv.style.position = "relative";
    host.appendChild(chartDiv);

    return chartDiv;
  }

  const interopState = {
    selectedTicks: new Set(),
    focusRowKey: null
  };

  function calcOpacity(aoi, code, rowKey, xIdx) {
    let passTick = true;

    if (interopState.selectedTicks.size > 0) {
      passTick = interopState.selectedTicks.has(`${xIdx}|${aoi}|${code}`);
    }

    let passRow = true;

    if (interopState.focusRowKey && interopState.focusRowKey !== rowKey) {
      passRow = false;
    }

    if (passTick && passRow) return 1;
    if (!passTick) return 0.18;
    if (!passRow) return 0.28;

    return 1;
  }

  function rowsByCriteria(rawRows, criteria) {
    const activeBackendTab = activeTabKey();
  
    return (rawRows || []).filter(r => {
      const rowTab = String(r.tab_name || "").trim();
  
      if (activeBackendTab && rowTab && rowTab !== activeBackendTab) return false;
  
      if (criteria.aoi && A.aoi(r) !== criteria.aoi) return false;
      if (criteria.code && A.code(r) !== criteria.code) return false;
      if (criteria.line && A.line(r) !== criteria.line) return false;
      if (criteria.line_id && A.line(r) !== criteria.line_id) return false;
      if (criteria.model && A.model(r) !== criteria.model) return false;
      if (criteria.side && A.side(r) !== criteria.side) return false;
  
      if (criteria.tick) {
        const tk = A.tick(r);
        if (tk !== criteria.tick) return false;
      }
  
      return true;
    });
  }
  

  // =====================
  // Density 右軸滑軌
  // =====================
  function getDensityScaleStore() {
    if (!MOD.Charts.__densScaleByKey) MOD.Charts.__densScaleByKey = Object.create(null);
    return MOD.Charts.__densScaleByKey;
  }

  function ensureOverlay(dom) {
    let overlay = dom.querySelector(".aoi-density-slider-overlay");

    if (!overlay) {
      overlay = document.createElement("div");
      overlay.className = "aoi-density-slider-overlay";
      overlay.style.position = "absolute";
      overlay.style.left = "0";
      overlay.style.top = "0";
      overlay.style.right = "0";
      overlay.style.bottom = "0";
      overlay.style.zIndex = "999";
      overlay.style.pointerEvents = "none";
      dom.appendChild(overlay);
    }

    overlay.innerHTML = "";
    return overlay;
  }

  function applyOneRightAxisMaxById(inst, yId, newMax) {
    inst.setOption(
      {
        yAxis: [
          {
            id: yId,
            min: 0,
            max: newMax
          }
        ]
      },
      {
        notMerge: false,
        lazyUpdate: true,
        silent: true
      }
    );
  }

  function mountPerGridSliders(dom, inst, densMetaList) {
    if (!inst || !Array.isArray(densMetaList) || !densMetaList.length) {
      if (SLIDER_DEBUG) console.warn("[dens-slider] skip mount: inst/metaList invalid", !!inst, densMetaList?.length);
      return;
    }

    ensureOverlay(dom);
    dom.querySelectorAll(".aoi-density-slider-wrap").forEach(el => el.remove());

    const store = getDensityScaleStore();
    const model = inst.getModel?.();

    if (!model) {
      if (SLIDER_DEBUG) console.warn("[dens-slider] skip mount: inst.getModel() missing");
      return;
    }

    let mounted = 0;

    densMetaList.forEach((m) => {
      const gridModel = model.getComponent("grid", m.gridIndex);
      const rect = gridModel?.coordinateSystem?.getRect?.();

      if (!rect || !(rect.width > 0) || !(rect.height > 0)) {
        if (SLIDER_DEBUG) console.warn("[dens-slider] bad rect:", m.gridIndex, rect);
        return;
      }

      const wrap = document.createElement("div");
      wrap.className = "aoi-density-slider-wrap";
      wrap.style.position = "absolute";
      wrap.style.pointerEvents = "auto";
      wrap.style.left = (rect.x + rect.width + 2) + "px";
      wrap.style.top = rect.y + "px";
      wrap.style.width = "20px";
      wrap.style.height = rect.height + "px";
      wrap.style.display = "flex";
      wrap.style.alignItems = "center";
      wrap.style.justifyContent = "center";
      wrap.style.zIndex = "1000";
      wrap.style.background = "rgba(255,255,255,0.02)";
      wrap.style.border = "1px solid rgba(255,255,255,0.08)";
      wrap.style.borderRadius = "6px";

      const range = document.createElement("input");
      range.type = "range";
      range.min = "5";
      range.max = "200";
      range.step = "5";

      const initScale = (typeof store[m.key] === "number") ? store[m.key] : 1;
      range.value = String(Math.round(initScale * 100));

      range.style.width = "18px";
      range.style.height = rect.height + "px";
      range.style.writingMode = "vertical-lr";
      range.style.direction = "rtl";
      range.style.opacity = "0.92";
      range.style.margin = "0";

      const tag = document.createElement("div");
      tag.textContent = range.value + "%";
      tag.style.position = "absolute";
      tag.style.left = "50%";
      tag.style.top = "-6px";
      tag.style.transform = "translate(-50%, -100%)";
      tag.style.fontSize = "10px";
      tag.style.color = "#aeb6c7";
      tag.style.padding = "2px 4px";
      tag.style.borderRadius = "4px";
      tag.style.background = "rgba(15,18,27,0.75)";
      tag.style.border = "1px solid rgba(255,255,255,0.10)";
      tag.style.whiteSpace = "nowrap";
      tag.style.pointerEvents = "none";

      wrap.title = "拖拉調整 Density 右軸上限（雙擊重置 100%）";

      const apply = () => {
        const scale = Number(range.value) / 100;
        store[m.key] = scale;
        tag.textContent = range.value + "%";

        const baseMax = Number(m.baseMax);
        const newMax = Math.max(1e-6, (Number.isFinite(baseMax) ? baseMax : 1) * scale);

        applyOneRightAxisMaxById(inst, m.yId, newMax);
      };

      const stopBubble = (e) => {
        try { e.stopPropagation?.(); } catch (_) {}
        try { e.stopImmediatePropagation?.(); } catch (_) {}
      };

      range.addEventListener("pointerdown", stopBubble, true);
      range.addEventListener("mousedown", stopBubble, true);
      range.addEventListener("touchstart", stopBubble, { capture: true, passive: true });
      range.addEventListener("touchmove", stopBubble, { capture: true, passive: true });
      range.addEventListener("click", stopBubble, true);

      range.addEventListener("wheel", (e) => {
        stopBubble(e);
        try { e.preventDefault?.(); } catch (_) {}
      }, { capture: true, passive: false });

      let rafPending = 0;

      const scheduleApply = () => {
        if (rafPending) return;

        rafPending = requestAnimationFrame(() => {
          rafPending = 0;
          apply();
        });
      };

      range.addEventListener("input", scheduleApply);
      range.addEventListener("change", apply);

      range.addEventListener("dblclick", (e) => {
        stopBubble(e);
        range.value = "100";
        apply();
      });

      wrap.appendChild(range);
      wrap.appendChild(tag);
      dom.appendChild(wrap);

      mounted++;

      const baseMax = Number(m.baseMax);
      const newMax = Math.max(1e-6, (Number.isFinite(baseMax) ? baseMax : 1) * initScale);

      applyOneRightAxisMaxById(inst, m.yId, newMax);
    });

    if (SLIDER_DEBUG && mounted === 0) {
      console.warn("[dens-slider] mounted=0, check grid rect & dom size");
    }
  }

  // =====================
  // 主繪圖
  // =====================
  function renderBigChart(dom, columns, global, rawRows) {
    const ec = window.echarts;
    if (!ec) return;

    const LEGEND_BLOCK_H = 42;
    const TITLE_GAP = 12;
    const HEADER_TEXT_H = 32;
    const padTop = LEGEND_BLOCK_H + TITLE_GAP + HEADER_TEXT_H;
    const padBottom = 44;

    const baseLeft = 16;
    const gutterLineW = 26;
    const gutterGap = 8;
    const gutterModelW = 26;
    const leftMargin = baseLeft + gutterLineW + gutterGap + gutterModelW + 25;

    const rightMargin = 80;
    const colGap = 80;
    const rowH = 118;
    const rowGap = 50;

    const maxRows = Math.max(1, global.order.length);
    const totalH = padTop + maxRows * rowH + (maxRows - 1) * rowGap + padBottom + 60;
    dom.style.height = totalH + "px";

    const width = dom.clientWidth || 1200;
    const nCols = Math.max(1, columns.length);
    const colWidth = Math.max(260, Math.floor((width - leftMargin - rightMargin - (nCols - 1) * colGap) / nCols));
    const totalChartWidth = leftMargin + nCols * (colWidth + colGap) - colGap + rightMargin;
    dom.style.width = totalChartWidth + "px";

    if (dom.__aoiDensityChartInst) {
      try {
        stopTotalDensityBlink(dom.__aoiDensityChartInst);
        dom.__aoiDensityChartInst.dispose();
      } catch (_) {}
      dom.__aoiDensityChartInst = null;
    }

    const inst = ec.init(dom);
    dom.__aoiDensityChartInst = inst;

    const totalDensityAlertRows = [];

    const groups = [];
    let curAoi = null;
    let start = 0;

    columns.forEach((c, idx) => {
      if (c.aoi !== curAoi) {
        if (curAoi != null) {
          groups.push({
            aoi: curAoi,
            startCol: start,
            count: idx - start
          });
        }

        curAoi = c.aoi;
        start = idx;
      }

      if (idx === columns.length - 1) {
        groups.push({
          aoi: c.aoi,
          startCol: start,
          count: idx - start + 1
        });
      }
    });

    const yAxisMetaMap = {};
    let legendSelectedState = buildDefaultLegendSelectedState();

    function buildOption() {
      totalDensityAlertRows.length = 0;

      const grids = [];
      const xAxes = [];
      const yAxes = [];
      const series = [];
      const graphics = [];
      const dataZoom = [];
      const densRightAxisMeta = [];

      let xAxisCountSoFar = 0;
      const colAxisIndexRange = [];

      function pushSpecMarkLine({
        name,
        xAxisIndex,
        yAxisIndex,
        value,
        color,
        labelText,
        z = 30
      }) {
        if (value == null || !isFinite(value)) return;

        series.push({
          name,
          type: "line",
          xAxisIndex,
          yAxisIndex,
          data: [],
          showSymbol: false,
          silent: true,
          tooltip: { show: false },
          lineStyle: { opacity: 0 },
          z,
          zlevel: 1,
          clip: false,
          markLine: {
            silent: true,
            symbol: ["none", "none"],
            lineStyle: {
              type: "dashed",
              width: 1.3,
              color
            },
            label: {
              show: true,
              position: "end",
              formatter: labelText,
              color: CHART_THEME.mlText,
              backgroundColor: CHART_THEME.mlBg,
              padding: [2, 2],
              borderRadius: 3,
              fontSize: 10,
              offset: [10, 0]
            },
            data: [{ yAxis: value }]
          }
        });
      }

      columns.forEach((col, colIdx) => {
        const { aoi, code, xTicks, rows } = col;
        const colLeft = leftMargin + colIdx * (colWidth + colGap);
        const hasRows = rows.length > 0;

        graphics.push({
          type: "text",
          left: colLeft + colWidth / 2,
          top: LEGEND_BLOCK_H + 22,
          style: {
            text: code,
            fill: "#d4e0ff",
            fontWeight: 700,
            fontSize: 12,
            textAlign: "center"
          }
        });

        let curTop = padTop;

        rows.forEach((row, rIdx) => {
          const isBottom = (rIdx === rows.length - 1);
          const gridIndex = grids.length;

          grids.push({
            left: colLeft,
            top: curTop,
            width: colWidth,
            height: rowH
          });

          const xAxisIndex = xAxes.length;

          xAxes.push({
            type: "category",
            gridIndex,
            data: xTicks,
            axisTick: {
              alignWithLabel: true,
              lineStyle: {
                color: CHART_THEME.axisTick,
                width: 1
              }
            },
            axisLabel: {
              show: isBottom,
              rotate: 90,
              margin: 12,
              color: CHART_THEME.axisLabel
            },
            axisLine: {
              onZero: false,
              lineStyle: {
                color: CHART_THEME.axisLine,
                width: 1
              }
            },
            triggerEvent: true
          });

          const gMax = Math.max(1, Math.ceil((row.maxG || 1) * 1.2));

          const yLeftIndex = yAxes.length;
          const yLeftId = `yL:${aoi}:${code}:${rIdx}`;

          yAxes.push({
            id: yLeftId,
            type: "value",
            gridIndex,
            min: 0,
            max: gMax,
            splitLine: {
              show: true,
              lineStyle: {
                color: CHART_THEME.splitLine,
                width: 1,
                type: "dashed"
              }
            },
            axisLabel: {
              show: true,
              color: CHART_THEME.axisLabel
            },
            axisLine: {
              lineStyle: {
                color: CHART_THEME.axisLine,
                width: 1
              }
            },
            axisTick: {
              lineStyle: {
                color: CHART_THEME.axisTick,
                width: 1
              }
            },
            triggerEvent: true
          });

          const showTotalDensity = legendSelectedState["Total defect density"] === true;
          const densityMax = Number(row.maxDensity || 0);
          const totalDensityMax = Number(row.maxTotalDensity || 0);
          const usedDensityMax = showTotalDensity
            ? Math.max(densityMax, totalDensityMax)
            : densityMax;

          const dBaseMax = Math.max(1, usedDensityMax * 1.4);

          const mlMax = Math.max(
            0,
            row?.specDefault?.ooc || 0,
            row?.specDefault?.oos || 0,
            row?.specFixed?.ooc || 0,
            row?.specFixed?.oos || 0
          );

          const yRightMax = Math.max(dBaseMax, mlMax ? mlMax * 1.05 : 0);

          const yRightId = `yR:${aoi}:${code}:${rIdx}`;
          const yRightIndex = yAxes.length;

          yAxes.push({
            id: yRightId,
            type: "value",
            gridIndex,
            min: 0,
            max: yRightMax,
            splitLine: { show: false },
            axisLabel: {
              show: false,
              color: CHART_THEME.axisLabel
            },
            axisLine: {
              lineStyle: {
                color: CHART_THEME.axisLine,
                width: 1
              }
            },
            axisTick: {
              lineStyle: {
                color: CHART_THEME.axisTick,
                width: 1
              }
            }
          });

          const densKey = `${aoi}|${code}|${rIdx}|${row.glass_type || ""}`;

          densRightAxisMeta.push({
            key: densKey,
            gridIndex,
            yId: yRightId,
            baseMax: yRightMax,
            debug: {
              aoi,
              code,
              rIdx,
              glass_type: row.glass_type
            }
          });

          yAxisMetaMap[yLeftIndex] = {
            aoi,
            code,
            local: rIdx
          };

          const rowKey = densKey;
          const barIdG = `barG:${aoi}:${code}:${rIdx}`;
          const barIdCG = `barCG:${aoi}:${code}:${rIdx}`;
          const scId = `sc:${aoi}:${code}:${rIdx}`;
          const totalScId = `scTotal:${aoi}:${code}:${rIdx}`;

          series.push({
            id: barIdG,
            name: "glass (total)",
            type: "bar",
            xAxisIndex,
            yAxisIndex: yLeftIndex,
            barMaxWidth: 14,
            barGap: "0%",
            z: 1,
            zlevel: 0,
            itemStyle: { color: CHART_COLOR.glassTotalBar },
            data: (row.tabTotalGlassArr || []).map((v, i) => ({
              value: Math.trunc(Number(v || 0)),
              itemStyle: {
                opacity: calcOpacity(aoi, code, rowKey, i)
              }
            })),
            universalTransition: true
          });

          series.push({
            id: barIdCG,
            name: "defect glass",
            type: "bar",
            xAxisIndex,
            yAxisIndex: yLeftIndex,
            barMaxWidth: 14,
            barGap: "-100%",
            z: 2,
            zlevel: 0,
            itemStyle: { color: CHART_COLOR.defectGlassBar },
            label: { show: false },
            data: (row.codeGlasses || []).map((v, i) => ({
              value: v,
              itemStyle: {
                opacity: calcOpacity(aoi, code, rowKey, i)
              }
            })),
            universalTransition: true
          });

          series.push({
            id: scId,
            name: "density",
            type: "scatter",
            xAxisIndex,
            yAxisIndex: yRightIndex,
            symbolSize: 7,
            z: 50,
            zlevel: 1,
            itemStyle: { color: CHART_COLOR.densityPoint },
            label: {
              show: true,
              position: "top",
              distance: 10,
              formatter: (p) => {
                const vv = Array.isArray(p.value) ? p.value[1] : p.value;
                const hasValue = typeof vv === "number" && isFinite(vv);
            
                if (!hasValue) return "";
            
                if (p?.data?.needAlert) {
                  return `{alert|爆點}\n{gap| }\n{val|${vv.toFixed(2)}}`;
                }
            
                return `{val|${vv.toFixed(2)}}`;
              },
            
              // 外層一定要透明，不然 \n 會讓整個黑底變大
              backgroundColor: "transparent",
              padding: [0, 0],
              borderRadius: 0,
            
              rich: {
                alert: {
                  color: "#FF0000",
                  fontSize: 12,
                  fontWeight: 800,
                  lineHeight: 14,
                  align: "center",
                  backgroundColor: CHART_THEME.labelBg,//backgroundColor: "transparent",
                  padding: [0, 0, 0, 0]
                },
                gap: {
                  fontSize: 1,
                  lineHeight: 3,
                  backgroundColor: "transparent"
                },
                val: {
                  color: CHART_THEME.labelText,
                  fontSize: 10,
                  lineHeight: 14,
                  align: "center",
                  backgroundColor: CHART_THEME.labelBg,
                  padding: CHART_THEME.labelPad,
                  borderRadius: CHART_THEME.labelRadius
                }
              }
            },
            data: (row.density || []).map((v, i) => {
              const totalDensity = Number(row.tabTotalDensity?.[i]);
              const needAlert = shouldTotalDensityPointAlert(totalDensity);
          
              const tabTG = Number(row.tabTotalGlassArr?.[i] ?? 0);
              const tabTD = Number(row.tabTotalDefArr?.[i] ?? 0);
              const tickStr = xTicks?.[i] || "";
          
              const alertRow = needAlert
                ? buildAlertRowFromChartPoint(
                    row,
                    tickStr,
                    aoi,
                    code,
                    totalDensity,
                    tabTG,
                    tabTD
                  )
                : null;
          
              if (alertRow) {
                totalDensityAlertRows.push(alertRow);
              }
          
              return {
                value: v,
                needAlert,
                alertRow,
                itemStyle: {
                  opacity: v == null ? 0 : calcOpacity(aoi, code, rowKey, i),
                  color: needAlert
                    ? ALERT_CONFIG.blinkColorA
                    : CHART_COLOR.densityPoint
                }
              };
            }),
            connectNulls: false,
            universalTransition: true
          });

          series.push({
            id: totalScId,
            name: "Total defect density",
            type: "scatter",
            xAxisIndex,
            yAxisIndex: yRightIndex,
            symbolSize: 8,
            z: 60,
            zlevel: 1,
            itemStyle: { color: CHART_COLOR.totalDensityPoint },
            label: {
              show: true,
              position: "top",
              distance: 10,
              formatter: (p) => {
                const vv = Array.isArray(p.value) ? p.value[1] : p.value;
                const valText = (typeof vv === "number" && isFinite(vv)) ? vv.toFixed(2) : "";
          
                if (p?.data?.hasSamePoint && legendSelectedState["Total defect density"] === true) {
                  return valText ? `{sp|同點}\n{val|${valText}}` : `{sp|同點}`;
                }
          
                return valText ? `{val|${valText}}` : "";
              },
              backgroundColor: "transparent",
              padding: [0, 0],
              rich: {
                sp: {
                  color: "#FFDC00",
                  fontSize: 12,
                  fontWeight: 800,
                  lineHeight: 15,
                  align: "center",
                  backgroundColor: CHART_THEME.labelBg,
                  padding: [1, 4],
                  borderRadius: 3
                },
                val: {
                  color: CHART_THEME.labelText,
                  fontSize: 10,
                  lineHeight: 14,
                  align: "center",
                  backgroundColor: CHART_THEME.labelBg,
                  padding: CHART_THEME.labelPad,
                  borderRadius: CHART_THEME.labelRadius
                }
              }
            },
            data: (row.tabTotalDensity || []).map((v, i) => {
              const totalDensity = Number(v);
              const needAlert = shouldTotalDensityPointAlert(totalDensity);
          
              const tabTG = Number(row.tabTotalGlassArr?.[i] ?? 0);
              const tabTD = Number(row.tabTotalDefArr?.[i] ?? 0);
              const tickStr = xTicks?.[i] || "";
          
              const alertRow = needAlert
                ? buildAlertRowFromChartPoint(
                    row,
                    tickStr,
                    aoi,
                    code,
                    totalDensity,
                    tabTG,
                    tabTD
                  )
                : null;
          
              if (alertRow) {
                totalDensityAlertRows.push(alertRow);
              }
          
              return {
                value: Number.isFinite(totalDensity) ? totalDensity : null,
                needAlert,
                alertRow,
                hasSamePoint: row.samePointArr?.[i] === true,
                itemStyle: {
                  opacity: v == null ? 0 : calcOpacity(aoi, code, rowKey, i),
                  color: needAlert
                    ? ALERT_CONFIG.blinkColorA
                    : CHART_COLOR.totalDensityPoint
                }
              };
            }),
            connectNulls: false,
            universalTransition: true
          });
          

          const dSpec = row.specDefault;

          if (dSpec) {
            if (dSpec.ooc != null && isFinite(dSpec.ooc)) {
              pushSpecMarkLine({
                name: "預設SPEC",
                xAxisIndex,
                yAxisIndex: yRightIndex,
                value: Number(dSpec.ooc),
                color: CHART_COLOR.defaultSpecOOC,
                labelText: () => `${Number(dSpec.ooc).toFixed(1)}`,
                z: 30
              });
            }

            if (dSpec.oos != null && isFinite(dSpec.oos)) {
              pushSpecMarkLine({
                name: "預設SPEC",
                xAxisIndex,
                yAxisIndex: yRightIndex,
                value: Number(dSpec.oos),
                color: CHART_COLOR.defaultSpecOOS,
                labelText: () => `${Number(dSpec.oos).toFixed(1)}`,
                z: 30
              });
            }
          }

          const fSpec = row.specFixed;

          if (fSpec) {
            if (fSpec.ooc != null && isFinite(fSpec.ooc)) {
              pushSpecMarkLine({
                name: "動態SPEC",
                xAxisIndex,
                yAxisIndex: yRightIndex,
                value: Number(fSpec.ooc),
                color: CHART_COLOR.fixedSpecOOC,
                labelText: () => `${Number(fSpec.ooc).toFixed(1)}`,
                z: 31
              });
            }

            if (fSpec.oos != null && isFinite(fSpec.oos)) {
              pushSpecMarkLine({
                name: "動態SPEC",
                xAxisIndex,
                yAxisIndex: yRightIndex,
                value: Number(fSpec.oos),
                color: CHART_COLOR.fixedSpecOOS,
                labelText: () => `${Number(fSpec.oos).toFixed(1)}`,
                z: 31
              });
            }
          }

          curTop += rowH + (isBottom ? 0 : rowGap);
        });

        const xStart = xAxisCountSoFar;
        const xEnd = xStart + rows.length;

        colAxisIndexRange.push({
          colIndex: colIdx,
          aoi,
          code,
          xStart,
          xEnd
        });

        xAxisCountSoFar = xEnd;

        if (hasRows) {
          const xIdxs = Array.from({ length: rows.length }, (_, i) => xStart + i);

          dataZoom.push(
            {
              type: "inside",
              xAxisIndex: xIdxs,
              filterMode: "filter"
            },
            {
              type: "slider",
              xAxisIndex: xIdxs,
              left: colLeft,
              bottom: 8,
              width: colWidth,
              height: 16,
              brushSelect: false
            }
          );
        }
      });

      const hasDefaultSpecSeries = series.some(ss => ss && ss.name === "預設SPEC");
      const hasFixedSpecSeries = series.some(ss => ss && ss.name === "動態SPEC");

      if (!hasDefaultSpecSeries && xAxes.length > 0 && yAxes.length > 1) {
        series.push({
          name: "預設SPEC",
          type: "line",
          xAxisIndex: 0,
          yAxisIndex: 1,
          data: [],
          showSymbol: false,
          silent: true,
          tooltip: { show: false },
          lineStyle: { opacity: 0 }
        });
      }

      if (!hasFixedSpecSeries && xAxes.length > 0 && yAxes.length > 1) {
        series.push({
          name: "動態SPEC",
          type: "line",
          xAxisIndex: 0,
          yAxisIndex: 1,
          data: [],
          showSymbol: false,
          silent: true,
          tooltip: { show: false },
          lineStyle: { opacity: 0 }
        });
      }

      groups.forEach(g => {
        const left = leftMargin + g.startCol * (colWidth + colGap);
        const right = left + g.count * colWidth + (g.count - 1) * colGap;

        graphics.push({
          type: "text",
          left: (left + right) / 2,
          top: LEGEND_BLOCK_H + 4,
          style: {
            text: g.aoi,
            fill: "#89a6ff",
            fontWeight: 800,
            fontSize: 13,
            textAlign: "center"
          }
        });
      });

      const lineX = 16 + Math.floor(26 / 2);
      const modelX = 16 + 26 + 8 + Math.floor(26 / 2);

      (global.lineGroups || []).forEach(gp => {
        const top = padTop + gp.start * (rowH + rowGap);

        graphics.push({
          type: "text",
          left: lineX - 15,
          top: top - 20,
          style: {
            text: gp.line_id,
            fill: "#f38aff",
            fontWeight: 700,
            fontSize: 12,
            textAlign: "center"
          }
        });
      });

      (global.order || []).forEach((rm, idx) => {
        const top = padTop + idx * (rowH + rowGap);
        const centerY = top + rowH / 2;

        const t1 = String(rm.model || "").trim();
        const t2 = String(rm.glass_type || "").trim();

        graphics.push({
          type: "text",
          left: modelX - 60,
          top: centerY - 12,
          style: {
            text: t2 ? `${t1}\n(${t2})` : t1,
            fill: "#b1ffea",
            fontWeight: 600,
            fontSize: 11,
            lineHeight: 14,
            textAlign: "center"
          }
        });
      });

      return {
        animation: true,
        legend: {
          top: 0,
          right: 10,
          itemGap: 18,
          data: [
            "glass (total)",
            "defect glass",
            "density",
            "Total defect density",
            "預設SPEC",
            "動態SPEC"
          ],
          selected: legendSelectedState
        },
        tooltip: {
          trigger: "axis",
          axisPointer: {
            type: "cross",
            snap: true
          },
          renderMode: "html",
          extraCssText: "max-width:560px; white-space:normal; line-height:1.35;",
          formatter: (params) => {
            const list = Array.isArray(params) ? params : [params];
            const p0 = list[0] || {};
            const [, aoi = "", code = "", rIdxStr = "0"] = String(p0.seriesId || "").split(":");
            const rIdx = Number(rIdxStr) || 0;

            const col = (columns || []).find(c => c.aoi === aoi && c.code === code);
            const tickStr = (p0.axisValue != null)
              ? String(p0.axisValue)
              : (col ? col.xTicks[p0.dataIndex] : "");

            const row = col ? col.rows[rIdx] : null;

            if (!row || !tickStr) return "";

            const pick = rowsByCriteria(rawRows, {
              aoi,
              code,
              line: row.line_id,
              model: row.model,
              side: row.glass_type,
              tick: tickStr
            });

            const idx = col.xTicks.indexOf(tickStr);

            const tabTG = idx >= 0 ? Number(row.tabTotalGlassArr?.[idx] ?? 0) : 0;
            const tabTD = idx >= 0 ? Number(row.tabTotalDefArr?.[idx] ?? 0) : 0;
            const tabD = idx >= 0 ? row.tabTotalDensity?.[idx] : null;

            const dens = (idx >= 0 && row.density[idx] != null)
              ? Number(row.density[idx]).toFixed(2)
              : "";

            const gCode = (idx >= 0) ? row.codeGlasses[idx] : null;

            const tooltipCnt = calcTooltipCountsFromRows(pick);

            const dCode = tooltipCnt.dCode;
            const S = tooltipCnt.S;
            const M = tooltipCnt.M;
            const L = tooltipCnt.L;
            const O = tooltipCnt.O;

            const sizeLine = [["S", S], ["M", M], ["L", L], ["O", O]]
              .filter(([, v]) => v > 0)
              .map(([k, v]) => `${k}${Math.trunc(v)}`)
              .join(", ");

            const kv = [
              ["density", dens],
              ["Total density (tab)", tabD == null ? "" : Number(tabD).toFixed(2)],
              ["Total defect count (tab)", String(Math.trunc(tabTD))],
              ["Total glass count (tab)", String(Math.trunc(tabTG))],
              ["defect glass count", gCode == null ? "" : String(Math.trunc(gCode))],
              ["defect count", String(Math.trunc(dCode))],
              ["S/M/L/O", sizeLine]
            ].filter(([, v]) => v !== "" && v != null);

            return kv.map(([k, v]) => `<div><b>${k}</b>: ${v}</div>`).join("");
          }
        },
        axisPointer: { link: [] },
        brush: {
          toolbox: [],
          brushMode: "single",
          brushType: "lineX",
          xAxisIndex: Array.from({ length: xAxisCountSoFar }, (_, i) => i)
        },
        grid: grids,
        xAxis: xAxes,
        yAxis: yAxes,
        series,
        graphic: graphics,
        dataZoom,
        __colAxisIndexRange: colAxisIndexRange,
        __yAxisMetaMap: yAxisMetaMap,
        __densRightAxisMeta: densRightAxisMeta
      };
    }

    let option = buildOption();

    const mountNow = (meta) => {
      requestAnimationFrame(() => {
        try {
          mountPerGridSliders(dom, inst, meta);
        } catch (e) {
          console.error("[dens-slider] mount error:", e);
        }
      });
    };

    const mountOnce = () => {
      mountNow(option.__densRightAxisMeta);
      inst.off("finished", mountOnce);
    };

    inst.off("finished", mountOnce);
    inst.on("finished", mountOnce);

    inst.setOption(option);

    fireAlertRowsOnce(totalDensityAlertRows);
    startTotalDensityBlink(inst);

    setTimeout(() => mountNow(option.__densRightAxisMeta), 0);
    setTimeout(() => mountNow(option.__densRightAxisMeta), 60);

    let lastClickAt = 0;

    inst.off("click");
    inst.on("click", async function (ev) {
      if (ev?.componentType === "xAxis") {
        const xAxisIndex = ev?.xAxisIndex ?? ev?.axisIndex ?? 0;
        const ranges = inst.getOption().__colAxisIndexRange || [];
        let found = null;

        for (const r of ranges) {
          if (xAxisIndex >= r.xStart && xAxisIndex < r.xEnd) {
            found = r;
            break;
          }
        }

        if (!found) return;

        const { aoi, code } = found;
        const tickStr = String(ev.value);
        const pick = rowsByCriteria(rawRows, {
          aoi,
          code,
          tick: tickStr
        });

        window.AOI_DENSITY?.handleSelection?.(pick, window.AOI_DENSITY?.state?.paramDict);
      } else if (ev?.componentType === "yAxis") {
        const yIdx = ev?.yAxisIndex;
        const metaMap = inst.getOption().__yAxisMetaMap || {};
        const hit = metaMap[yIdx];

        if (!hit) return;

        const col = columns.find(c => c.aoi === hit.aoi && c.code === hit.code);
        if (!col) return;

        const row = col.rows[hit.local];
        if (!row) return;

        const pick = rowsByCriteria(rawRows, {
          line: row.line_id,
          model: row.model,
          side: row.glass_type
        });

        window.AOI_DENSITY?.handleSelection?.(pick, window.AOI_DENSITY?.state?.paramDict);
      } else if (ev?.componentType === "series") {
        const now = Date.now();

        if (now - lastClickAt < 300) return;
        lastClickAt = now;

        const sId = ev.seriesId || "";
        const parts = sId.split(":");

        const aoi = parts[1];
        const code = parts[2];
        const rIdx = Number(parts[3] || 0);

        const col = columns.find(c => c.aoi === aoi && c.code === code);
        if (!col) return;

        const dataIdx = ev.dataIndex;
        const tickStr = col.xTicks[dataIdx];
        const row = col.rows[rIdx];
        if (!tickStr || !row) return;

        const isBar = (sId.startsWith("barG:") || sId.startsWith("barCG:"));

        if (isBar) {
          const tabTD = Number(row.tabTotalDefArr?.[dataIdx] ?? 0);
          const tabTG = Number(row.tabTotalGlassArr?.[dataIdx] ?? 0);
          const tabTotalDensity = Number(row.tabTotalDensity?.[dataIdx] ?? 0);

          console.log(
            `[TabTotal] tick=${tickStr} aoi=${aoi} line=${row.line_id} model=${row.model} side=${row.glass_type} ` +
            `tab=${activeTabKey()} rawTab=${rawActiveTabKey()} tabTD=${tabTD} tabTG=${tabTG} tabDensity=${tabTotalDensity.toFixed(4)}`
          );
        }

        const pick = rowsByCriteria(rawRows, {
          aoi,
          code,
          line: row.line_id,
          model: row.model,
          side: row.glass_type,
          tick: tickStr
        });

        window.AOI_DENSITY?.handleSelection?.(pick, window.AOI_DENSITY?.state?.paramDict);
      }
    });

    inst.off("brushselected");
    inst.on("brushselected", function (params) {
      interopState.selectedTicks.clear();

      const sel = params.batch?.[0]?.selected || [];
      const ranges = inst.getOption().__colAxisIndexRange || [];

      sel.forEach(ss => {
        const axisIndex = ss.xAxisIndex;
        const idxRange = ss.dataIndex;

        if (!Array.isArray(idxRange) || idxRange.length < 2) return;

        let found = null;

        for (const r of ranges) {
          if (axisIndex >= r.xStart && axisIndex < r.xEnd) {
            found = r;
            break;
          }
        }

        if (!found) return;

        const { aoi, code } = found;
        const [sidx, eidx] = idxRange;
        const lo = Math.min(sidx, eidx);
        const hi = Math.max(sidx, eidx);

        for (let i = lo; i <= hi; i++) {
          interopState.selectedTicks.add(`${i}|${aoi}|${code}`);
        }
      });

      refreshOpacity(inst, columns);
      startTotalDensityBlink(inst);
    });

    inst.off("legendselectchanged");
    inst.on("legendselectchanged", function (ev) {
      legendSelectedState = {
        ...legendSelectedState,
        ...(ev?.selected || {})
      };

      rebuild();
    });

    function rebuild() {
      const op = buildOption();

      const mountOnce2 = () => {
        mountNow(op.__densRightAxisMeta);
        inst.off("finished", mountOnce2);
      };

      inst.off("finished", mountOnce2);
      inst.on("finished", mountOnce2);

      inst.setOption(op, true, true);

      fireAlertRowsOnce(totalDensityAlertRows);
      startTotalDensityBlink(inst);

      setTimeout(() => mountNow(op.__densRightAxisMeta), 0);
      setTimeout(() => mountNow(op.__densRightAxisMeta), 60);

      refreshOpacity(inst, columns);
    }

    if (dom.__aoiDensityResizeHandler) {
      window.removeEventListener("resize", dom.__aoiDensityResizeHandler);
    }

    dom.__aoiDensityResizeHandler = () => {
      inst.resize();
      rebuild();
    };

    window.addEventListener("resize", dom.__aoiDensityResizeHandler);
  }

  function refreshOpacity(inst, columns) {
    const updates = [];

    columns.forEach(col => {
      const { aoi, code, rows } = col;

      rows.forEach((row, rIdx) => {
        const rowKey = `${aoi}|${code}|${rIdx}|${row.glass_type || ""}`;

        const barIdG = `barG:${aoi}:${code}:${rIdx}`;
        const newBarDataG = (row.tabTotalGlassArr || []).map((v, i) => ({
          value: Math.trunc(Number(v || 0)),
          itemStyle: {
            opacity: calcOpacity(aoi, code, rowKey, i)
          }
        }));

        updates.push({
          id: barIdG,
          data: newBarDataG
        });

        const barIdCG = `barCG:${aoi}:${code}:${rIdx}`;
        const newBarDataCG = (row.codeGlasses || []).map((v, i) => ({
          value: v,
          itemStyle: {
            opacity: calcOpacity(aoi, code, rowKey, i)
          }
        }));

        updates.push({
          id: barIdCG,
          data: newBarDataCG
        });

        const scId = `sc:${aoi}:${code}:${rIdx}`;
        const newScData = (row.density || []).map((v, i) => {
          const totalDensity = Number(row.tabTotalDensity?.[i]);
          const needAlert = shouldTotalDensityPointAlert(totalDensity);

          const tabTG = Number(row.tabTotalGlassArr?.[i] ?? 0);
          const tabTD = Number(row.tabTotalDefArr?.[i] ?? 0);
          const tickStr = col.xTicks?.[i] || "";

          const alertRow = needAlert
            ? buildAlertRowFromChartPoint(
                row,
                tickStr,
                aoi,
                code,
                totalDensity,
                tabTG,
                tabTD
              )
            : null;

          return {
            value: v,
            needAlert,
            alertRow,
            itemStyle: {
              opacity: v == null ? 0 : calcOpacity(aoi, code, rowKey, i),
              color: needAlert
                ? ALERT_CONFIG.blinkColorA
                : CHART_COLOR.densityPoint
            }
          };
        });

        updates.push({
          id: scId,
          data: newScData
        });

        /*const alertLabelId = `scAlertLabel:${aoi}:${code}:${rIdx}`;
        const newAlertLabelData = (row.density || []).map((v, i) => {
          const totalDensity = Number(row.tabTotalDensity?.[i]);
          const needAlert = shouldTotalDensityPointAlert(totalDensity);

          return {
            value: v,
            needAlert,
            itemStyle: {
              opacity: 0
            },
            label: {
              show: needAlert
            }
          };
        });

        updates.push({
          id: alertLabelId,
          data: newAlertLabelData
        });*/

        const totalScId = `scTotal:${aoi}:${code}:${rIdx}`;
        const newTotalScData = (row.tabTotalDensity || []).map((v, i) => {
          const totalDensity = Number(v);
          const needAlert = shouldTotalDensityPointAlert(totalDensity);
        
          const tabTG = Number(row.tabTotalGlassArr?.[i] ?? 0);
          const tabTD = Number(row.tabTotalDefArr?.[i] ?? 0);
          const tickStr = col.xTicks?.[i] || "";
        
          const alertRow = needAlert
            ? buildAlertRowFromChartPoint(
                row,
                tickStr,
                aoi,
                code,
                totalDensity,
                tabTG,
                tabTD
              )
            : null;
        
          return {
            value: Number.isFinite(totalDensity) ? totalDensity : null,
            needAlert,
            alertRow,
            hasSamePoint: row.samePointArr?.[i] === true,
            itemStyle: {
              opacity: v == null ? 0 : calcOpacity(aoi, code, rowKey, i),
              color: needAlert
                ? ALERT_CONFIG.blinkColorA
                : CHART_COLOR.totalDensityPoint
            }
          };
        });

        updates.push({
          id: totalScId,
          data: newTotalScData
        });
      });
    });

    if (updates.length) {
      inst.setOption({ series: updates }, false, false);
    }
  }

  // =====================
  // 對外介面
  // =====================
  MOD.Charts.render = function (rows, _paramDict) {
    const dom = ensureHost();
    if (!dom) return;
  
    const activeBackendTab = activeTabKey();
    const rawRows0 = Array.isArray(rows) ? rows : [];
  
    const currentRows = rawRows0.filter(r => {
      const rowTab = String(r?.tab_name || "").trim();
  
      // 新版資料有 tab_name 時，chart 一律只吃目前分頁資料
      if (activeBackendTab && rowTab && rowTab !== activeBackendTab) {
        return false;
      }
  
      return true;
    });
  
    if (!currentRows.length || window.AOI_DENSITY?.state?.forceEmptyFilter) {
      dom.innerHTML = "<div class='muted'>沒有資料</div>";
      return;
    }
  
    let proSpecDict = (window.AOI_DENSITY?.state?.ProSpecDict) || null;
  
    if (!proSpecDict && _paramDict && _paramDict.ProSpecDict) {
      proSpecDict = _paramDict.ProSpecDict;
    }
  
    const defaultRows = proSpecDict && proSpecDict.default_spec_table
      ? Object.values(proSpecDict.default_spec_table)
      : [];
  
    const fixedRows = proSpecDict && proSpecDict.fixed_spec_table
      ? Object.values(proSpecDict.fixed_spec_table)
      : [];
  
    const defaultSpecIndex = buildDefaultSpecIndex(defaultRows);
    const fixedSpecIndex = buildFixedSpecIndex(fixedRows);
  
    const tabRowsAll = window.AOI_DENSITY?.state?.TabSummaryData || [];
    const tabRowsForChart = getTabRowsForChart(tabRowsAll);
    const tabAgg = buildTabTotalAgg(tabRowsForChart, activeBackendTab);
  
    const seedRowsFromTabSummary = tabRowsForChart.map(r => ({
      line_id: r.line_id,
      aoi: r.aoi,
      model: r.model,
      glass_type: r.glass_type,
      pi_hour: tickToShort(r.pi_hour)
    }));
  
    const seedRowsFromTabAgg = tabAggToSeedRows(tabAgg);
  
    const seedOrderRows = currentRows.concat(seedRowsFromTabSummary, seedRowsFromTabAgg);
    const global = buildGlobalRowOrder(seedOrderRows);
  
    const columns = (() => {
      const sizes = getSelectedSizes();
      const seedCodes = getSelectedCodes(currentRows);
  
      return buildColumnsByAoiCode(
        currentRows,
        global.order,
        defaultSpecIndex,
        fixedSpecIndex,
        sizes,
        tabAgg,
        seedCodes
      );
    })();
  
    if (!columns.length) {
      dom.innerHTML = "<div class='muted'>沒有資料</div>";
      return;
    }
  
    renderBigChart(dom, columns, global, currentRows);
  };
  
})();