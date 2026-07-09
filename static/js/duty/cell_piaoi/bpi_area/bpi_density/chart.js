// static/js/bpi_area/bpi_density/chart.js
(function () {
  const MOD = (window.AOI_BPI_DENSITY = window.AOI_BPI_DENSITY || {});
  MOD.Charts = MOD.Charts || {};

  const $ = (sel, root = document) => root.querySelector(sel);
  const Shared = window.AOI_BPI_DENSITY?.Shared || {};
  const U = Shared?.U || {};

  const SLIDER_DEBUG = true;
  const SPEC_LEGEND_NAME = "預設SPEC";

  const CHART_THEME = {
    axisLabel: "#aeb6c7",
    axisLine: "#2b3240",
    axisTick: "#3a4354",
    splitLine: "rgba(255,255,255,0.09)",
    labelText: "#e8edf7",
    labelBg: "rgba(15,18,27,0.85)",
    labelPad: [2, 4],
    labelRadius: 3,
    mlText: "#eaefff",
    mlBg: "rgba(13,18,27,0.9)"
  };

  const CHART_COLOR = {
    glassBar: "#9aa3b2",
    defectGlassBar: "#FF851B",
    totalDensityPoint: "#4da3ff",
    densityPoint: "#FF4136",
    defaultSpecOOC: "#FFB066",
    defaultSpecOOS: "#FF3333"
  };

  const SINGLE_COL_KEY = "__FILTERED__";

  function s(v) {
    return v == null ? "" : String(v);
  }

  function n(v) {
    const x = Number(v);
    return Number.isFinite(x) ? x : 0;
  }

  function toNum(v) {
    const x = Number(v);
    return Number.isFinite(x) ? x : null;
  }

  function parseGlassSizeDetailObj(v) {
    if (!v) return {};
    if (typeof v === "object" && !Array.isArray(v)) return v;

    if (typeof v === "string") {
      const text = v.trim();
      if (!text) return {};
      try {
        const obj = JSON.parse(text);
        return (obj && typeof obj === "object" && !Array.isArray(obj)) ? obj : {};
      } catch (_e) {
        return {};
      }
    }

    return {};
  }

  function getDefectGlassCount(row) {
    const obj = parseGlassSizeDetailObj(row?.glass_size_detail_obj || row?.glass_size_detail);
    if (!obj || typeof obj !== "object") return 0;

    let cnt = 0;
    Object.values(obj).forEach((stat) => {
      if (!stat || typeof stat !== "object") return;

      const ss = n(stat.S);
      const mm = n(stat.M);
      const ll = n(stat.L);
      const oo = n(stat.O);
      const tt = stat.T != null ? n(stat.T) : (ss + mm + ll + oo);

      if (tt > 0) cnt += 1;
    });

    return cnt;
  }

  const A = {
    aoi: (r) => U?.aoi ? U.aoi(r) : s(r?.aoi),
    model: (r) => U?.model ? U.model(r) : s(r?.model),
    side: (r) => U?.side ? U.side(r) : s(r?.glass_side),
    tick: (r) => U?.tick ? U.tick(r) : s(r?.scan_hour),
    cst: (r) => U?.cst ? U.cst(r) : s(r?.cassette_id),
    recipe: (r) => U?.recipe ? U.recipe(r) : s(r?.recipe_id),

    glass: (r) => U?.gTotal ? n(U.gTotal(r)) : n(r?.glass_count),
    defect: (r) => U?.dTotal ? n(U.dTotal(r)) : n(r?.total_defect_count),
    dens: (r) => U?.dens ? Number(U.dens(r)) : Number(r?.density),
    baseDens: (r) => Number(r?.base_density),

    defGlass: (r) => getDefectGlassCount(r),
    sCnt: (r) => n(r?.small_defect_count),
    mCnt: (r) => n(r?.middle_defect_count),
    lCnt: (r) => n(r?.large_defect_count),
    oCnt: (r) => n(r?.over_defect_count)
  };

  function parseTickToDate(tick) {
    const raw = String(tick || "").trim();
    if (!raw) return null;

    const d = new Date(raw.replace(" ", "T"));
    return isNaN(d) ? null : d;
  }

  function fmtHourLabel(tick) {
    const d = parseTickToDate(tick);
    if (!d) return s(tick);

    const yy = String(d.getFullYear()).slice(-2);
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    const hh = String(d.getHours()).padStart(2, "0");

    return `${yy}-${mm}-${dd} ${hh}`;
  }

  // ============================================================
  // BPI Density spec helpers
  // ============================================================
  function normalizeRows(raw) {
    if (!raw) return [];
    if (Array.isArray(raw)) return raw;
    if (typeof raw === "object") return Object.values(raw);
    return [];
  }

  function resolveBpiDensityDefaultSpecRows() {
    const st = window.AOI_BPI_DENSITY?.state || {};
    const payload = st.payload || {};
    const pro =
      st.ProSpecDict ||
      payload.ProSpecDict ||
      {};

    const raw =
      pro.bpi_density_default_spec ||
      pro.default_spec_table ||
      pro.bpi_density_default_spec_table ||
      [];

    return normalizeRows(raw);
  }

  function getSelectedSizes() {
    try {
      const ui = window.AOI_BPI_DENSITY?.readFiltersFromUI?.();
      const ds = ui?.defect_size;
      if (Array.isArray(ds) && ds.length) {
        return ds.map(x => String(x).trim().toUpperCase()).filter(Boolean);
      }
    } catch (_e) {}

    try {
      const st = window.AOI_BPI_DENSITY?.state || {};
      const mdd = st.mdd || st.multiDD || {};
      const wrap = mdd.defect_size;

      const selected = wrap?.mdd?.getSelected?.() || wrap?.getSelected?.() || [];
      if (Array.isArray(selected) && selected.length) {
        return selected.map(x => String(x).trim().toUpperCase()).filter(Boolean);
      }
    } catch (_e) {}

    return ["S", "M", "L", "O"];
  }

  function canonicalBpiSizeKey(list) {
    const set = new Set(
      (list || [])
        .map(v => String(v || "").trim().toUpperCase())
        .filter(Boolean)
    );

    const hasS = set.has("S");
    const hasM = set.has("M");
    const hasL = set.has("L");
    const hasO = set.has("O");

    if (!hasS && !hasM && !hasL && !hasO) return "OLMS";

    if (hasO) {
      if (hasL && hasM && hasS) return "OLMS";
      if (hasL && hasM) return "OLM";
      if (hasL) return "OL";
      return "O";
    }

    if (hasL) return "LMS";
    if (hasM) return "MS";
    if (hasS) return "S";

    return "OLMS";
  }

  function buildBpiSpecIndex(rows) {
    const idx = {};

    (rows || []).forEach((r) => {
      if (!r) return;

      const model = String(
        r.model ??
        r.MODEL_ID ??
        ""
      ).trim();

      const side = String(
        r.glass_type ??
        r.GLASS_TYPE ??
        r.glass_side ??
        ""
      ).trim();

      const sizeKey = String(
        r.defect_size ??
        r.SIZE_TYPE ??
        ""
      ).trim().toUpperCase();

      const ooc = toNum(r.OOC);
      const oos = toNum(r.OOS);

      if (!model || !side || !sizeKey) return;
      if (ooc == null && oos == null) return;

      idx[`${model}|${side}|${sizeKey}`] = {
        ooc,
        oos,
        raw: r,
      };
    });

    return idx;
  }

  function pickBpiSpec(specIdx, model, glassSide, sizeKey) {
    if (!specIdx || !model || !glassSide || !sizeKey) return null;

    return (
      specIdx[`${model}|${glassSide}|${sizeKey}`] ||
      specIdx[`${String(model).trim()}|${String(glassSide).trim()}|${String(sizeKey).trim().toUpperCase()}`] ||
      null
    );
  }

  function pushSpecMarkLine({
    series,
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

      // dummy data：確保 legend 能控制此 series。
      data: [null],

      showSymbol: false,
      symbol: "none",
      silent: true,
      tooltip: { show: false },
      lineStyle: { opacity: 0 },
      emphasis: { disabled: true },

      z,
      zlevel: 1,
      clip: false,

      markLine: {
        silent: true,
        symbol: ["none", "none"],
        animation: false,
        lineStyle: {
          type: "dashed",
          width: 2,
          color,
        },
        label: {
          show: true,
          position: "insideEndTop",
          formatter: typeof labelText === "function" ? labelText : String(labelText || value),
          color,
          backgroundColor: CHART_THEME.mlBg,
          padding: [2, 4],
          borderRadius: 3,
          fontSize: 10,
        },
        data: [
          {
            yAxis: Number(value),
          },
        ],
      },
    });
  }

  function buildHost() {
    const host = $("#aoi-bpi-density-facet");
    if (!host) return null;

    host.innerHTML = "";
    host.style.overflow = "auto";
    host.style.paddingTop = "14px";

    const chartDiv = document.createElement("div");
    chartDiv.className = "aoi-bpi-density-bigchart";
    chartDiv.style.height = "320px";
    chartDiv.style.position = "relative";
    chartDiv.style.marginTop = "6px";

    host.appendChild(chartDiv);
    return chartDiv;
  }

  function getDensityScaleStore() {
    if (!MOD.Charts.__densScaleByKey) {
      MOD.Charts.__densScaleByKey = Object.create(null);
    }
    return MOD.Charts.__densScaleByKey;
  }

  function ensureOverlay(dom) {
    let overlay = dom.querySelector(".aoi-bpi-density-slider-overlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.className = "aoi-bpi-density-slider-overlay";
      overlay.style.position = "absolute";
      overlay.style.left = "0";
      overlay.style.top = "-30px";
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
      { yAxis: [{ id: yId, min: 0, max: newMax }] },
      { notMerge: false, lazyUpdate: true, silent: true }
    );
  }

  function mountPerGridSliders(dom, inst, densMetaList) {
    if (!inst || !Array.isArray(densMetaList) || !densMetaList.length) {
      return;
    }

    ensureOverlay(dom);
    dom.querySelectorAll(".aoi-bpi-density-slider-wrap").forEach(el => el.remove());

    const store = getDensityScaleStore();
    const model = inst.getModel?.();
    if (!model) return;

    let mounted = 0;

    densMetaList.forEach((m) => {
      const gridModel = model.getComponent("grid", m.gridIndex);
      const rect = gridModel?.coordinateSystem?.getRect?.();
      if (!rect || !(rect.width > 0) || !(rect.height > 0)) return;

      const wrap = document.createElement("div");
      wrap.className = "aoi-bpi-density-slider-wrap";
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

      const apply = () => {
        const scale = Number(range.value) / 100;
        store[m.key] = scale;
        tag.textContent = range.value + "%";

        const baseMax = Number(m.baseMax);
        const newMax = Math.max(1e-6, (Number.isFinite(baseMax) ? baseMax : 1) * scale);

        applyOneRightAxisMaxById(inst, m.yId, newMax);
      };

      const stopBubble = (e) => {
        try { e.stopPropagation?.(); } catch (_e) {}
        try { e.stopImmediatePropagation?.(); } catch (_e) {}
      };

      range.addEventListener("pointerdown", stopBubble, true);
      range.addEventListener("mousedown", stopBubble, true);
      range.addEventListener("touchstart", stopBubble, { capture: true, passive: true });
      range.addEventListener("touchmove", stopBubble, { capture: true, passive: true });
      range.addEventListener("click", stopBubble, true);

      range.addEventListener("wheel", (e) => {
        stopBubble(e);
        try { e.preventDefault?.(); } catch (_e) {}
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
      console.warn("[bpi-density slider] mounted=0");
    }
  }

  function buildGlobalRowOrder(rows) {
    const byModel = new Map();

    (rows || []).forEach(r => {
      const model = A.model(r);
      const side = A.side(r);
      if (!model || !side) return;

      if (!byModel.has(model)) byModel.set(model, new Set());
      byModel.get(model).add(side);
    });

    const order = [];

    Array.from(byModel.keys()).sort().forEach(model => {
      Array.from(byModel.get(model)).sort().forEach(side => {
        order.push({
          model,
          glass_side: side
        });
      });
    });

    return {
      order,
      aoiGroups: []
    };
  }

  function buildColumnsByAoi(rows, globalOrder) {
    const byModelSide = {};
    const rawTickList = [];

    (rows || []).forEach(r => {
      const aoi = A.aoi(r);
      const model = A.model(r);
      const side = A.side(r);
      const tick = A.tick(r);
      const cst = A.cst(r);
      const recipe = A.recipe(r);

      if (!model || !side || !tick) return;

      rawTickList.push({
        aoi,
        tick,
        cst,
        recipe_id: recipe,
        row: r
      });

      const M = (byModelSide[model] = byModelSide[model] || {});
      const S = (M[side] = M[side] || []);
      S.push(r);
    });

    rawTickList.sort((x, y) => {
      const tx = parseTickToDate(x.tick)?.getTime?.() ?? 0;
      const ty = parseTickToDate(y.tick)?.getTime?.() ?? 0;
      if (tx !== ty) return tx - ty;

      const aoiCmp = s(x.aoi).localeCompare(s(y.aoi));
      if (aoiCmp !== 0) return aoiCmp;

      const cstCmp = s(x.cst).localeCompare(s(y.cst));
      if (cstCmp !== 0) return cstCmp;

      return s(x.recipe_id).localeCompare(s(y.recipe_id));
    });

    const uniqMap = new Map();

    rawTickList.forEach((it) => {
      const uniqKey = `${it.aoi}||${it.tick}||${it.cst}||${it.recipe_id}`;

      if (!uniqMap.has(uniqKey)) {
        uniqMap.set(uniqKey, {
          aoi: it.aoi,
          tick: it.tick,
          tickLabel: "",
          cst: it.cst,
          recipe_id: it.recipe_id,
          uniqKey,
          raw: it.row
        });
      }
    });

    const xItems = Array.from(uniqMap.values()).map((it, idx, arr) => {
      const prevTick = idx > 0 ? arr[idx - 1].tick : "";
      return {
        ...it,
        tickLabel: prevTick === it.tick ? "" : fmtHourLabel(it.tick)
      };
    });

    const rowsOut = (globalOrder || []).map((rowMeta) => {
      const bucket = (((byModelSide || {})[rowMeta.model] || {})[rowMeta.glass_side] || []);
      const idxMap = new Map();

      bucket.forEach(rr => {
        const aoi = A.aoi(rr);
        const tick = A.tick(rr);
        const cst = A.cst(rr);
        const recipe = A.recipe(rr);
        const key = `${aoi}||${tick}||${cst}||${recipe}`;
        idxMap.set(key, rr);
      });

      const glassArr = [];
      const defectArr = [];
      const defectGlassArr = [];
      const baseDensityArr = [];
      const densityArr = [];
      const rowRawArr = [];

      xItems.forEach((x) => {
        const key = `${x.aoi}||${x.tick}||${x.cst}||${x.recipe_id}`;
        const rr = idxMap.get(key);

        if (rr) {
          glassArr.push(A.glass(rr));
          defectArr.push(A.defect(rr));
          defectGlassArr.push(A.defGlass(rr));
          baseDensityArr.push(Number.isFinite(A.baseDens(rr)) ? A.baseDens(rr) : null);
          densityArr.push(Number.isFinite(A.dens(rr)) ? A.dens(rr) : null);
          rowRawArr.push(rr);
        } else {
          glassArr.push(0);
          defectArr.push(0);
          defectGlassArr.push(0);
          baseDensityArr.push(null);
          densityArr.push(null);
          rowRawArr.push(null);
        }
      });

      const maxGlass = Math.max(1, ...glassArr, ...defectGlassArr);
      const maxDensity = Math.max(
        1,
        ...baseDensityArr.filter(v => v != null).map(v => Number(v)),
        ...densityArr.filter(v => v != null).map(v => Number(v))
      );

      return {
        aoi: SINGLE_COL_KEY,
        model: rowMeta.model,
        glass_side: rowMeta.glass_side,
        xItems,
        glassArr,
        defectArr,
        defectGlassArr,
        baseDensityArr,
        densityArr,
        rowRawArr,
        maxGlass,
        maxDensity
      };
    });

    if (!rowsOut.length) return [];

    return [{
      aoi: SINGLE_COL_KEY,
      xItems,
      rows: rowsOut
    }];
  }

  function buildRowKey(_aoi, model, side) {
    return `${model}|${side}`;
  }

  function renderBigChart(dom, columns, global, rawRows, specIndex, sizeKey) {
    const ec = window.echarts;
    if (!ec) return;

    const LEGEND_TOP = 8;
    const padTop = 88;
    const padBottom = 44;

    const baseLeft = 18;
    const gutterModelW = 110;
    const leftMargin = baseLeft + gutterModelW + 18;

    const rightMargin = 80;
    const colGap = 60;
    const rowH = 118;
    const rowGap = 50;

    const maxRows = Math.max(1, global.order.length);
    const totalH = padTop + maxRows * rowH + (maxRows - 1) * rowGap + padBottom + 60;
    dom.style.height = totalH + "px";

    const width = dom.clientWidth || 1200;
    const nCols = Math.max(1, columns.length);
    const colWidth = Math.max(
      520,
      Math.floor((width - leftMargin - rightMargin - (nCols - 1) * colGap) / nCols)
    );
    const totalChartWidth = leftMargin + nCols * (colWidth + colGap) - colGap + rightMargin;
    dom.style.width = totalChartWidth + "px";

    const oldInst = ec.getInstanceByDom(dom);
    if (oldInst) {
      try { oldInst.dispose(); } catch (_e) {}
    }

    const inst = ec.init(dom);

    const interopState = {
      selectedTicks: new Set(),
      focusRowKey: null
    };

    function calcOpacity(aoi, rowKey, xIdx) {
      let passTick = true;
      if (interopState.selectedTicks.size > 0) {
        passTick = interopState.selectedTicks.has(`${aoi}|${xIdx}`);
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

    function buildOption() {
      const grids = [];
      const xAxes = [];
      const yAxes = [];
      const series = [];
      const graphics = [];
      const dataZoom = [];
      const densRightAxisMeta = [];
      const yAxisMetaMap = {};
      const colAxisIndexRange = [];

      let xAxisCountSoFar = 0;
      let hasDefaultSpecSeries = false;

      columns.forEach((col, colIdx) => {
        const { aoi, xItems, rows } = col;
        const colLeft = leftMargin + colIdx * (colWidth + colGap);

        graphics.push({
          type: "text",
          left: colLeft + colWidth / 2,
          top: 48,
          style: {
            text: "BPI Density",
            fill: "#89a6ff",
            fontWeight: 800,
            fontSize: 13,
            textAlign: "center"
          }
        });

        let curTop = padTop;

        rows.forEach((row, rIdx) => {
          const isBottom = rIdx === rows.length - 1;
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
            data: xItems.map(x => x.uniqKey),
            axisTick: {
              alignWithLabel: true,
              lineStyle: { color: CHART_THEME.axisTick, width: 1 }
            },
            axisLabel: {
              show: isBottom,
              interval: 0,
              rotate: 90,
              margin: 12,
              color: CHART_THEME.axisLabel,
              formatter: function (_val, idx) {
                return xItems[idx]?.tickLabel || "";
              }
            },
            axisLine: {
              onZero: false,
              lineStyle: { color: CHART_THEME.axisLine, width: 1 }
            },
            triggerEvent: true
          });

          const yLeftIndex = yAxes.length;
          const yLeftId = `yL:${aoi}:${rIdx}`;

          yAxes.push({
            id: yLeftId,
            type: "value",
            gridIndex,
            min: 0,
            max: Math.max(1, Math.ceil(row.maxGlass * 1.2)),
            splitLine: {
              show: true,
              lineStyle: { color: CHART_THEME.splitLine, width: 1, type: "dashed" }
            },
            axisLabel: { show: true, color: CHART_THEME.axisLabel },
            axisLine: { lineStyle: { color: CHART_THEME.axisLine, width: 1 } },
            axisTick: { lineStyle: { color: CHART_THEME.axisTick, width: 1 } },
            triggerEvent: true
          });

          const yRightIndex = yAxes.length;
          const yRightId = `yR:${aoi}:${rIdx}`;

          const spec = pickBpiSpec(specIndex, row.model, row.glass_side, sizeKey);
          const specMax = Math.max(
            0,
            spec?.ooc || 0,
            spec?.oos || 0
          );

          const yRightMax = Math.max(
            1,
            row.maxDensity * 1.4,
            specMax ? specMax * 1.15 : 0
          );

          yAxes.push({
            id: yRightId,
            type: "value",
            gridIndex,
            min: 0,
            max: yRightMax,
            splitLine: { show: false },
            axisLabel: { show: false, color: CHART_THEME.axisLabel },
            axisLine: { lineStyle: { color: CHART_THEME.axisLine, width: 1 } },
            axisTick: { lineStyle: { color: CHART_THEME.axisTick, width: 1 } }
          });

          const rowKey = buildRowKey(aoi, row.model, row.glass_side);

          const barId = `barG:${aoi}:${rIdx}`;
          const barDefId = `barDG:${aoi}:${rIdx}`;
          const scBaseId = `scBase:${aoi}:${rIdx}`;
          const scId = `sc:${aoi}:${rIdx}`;

          series.push({
            id: barId,
            name: "glass count",
            type: "bar",
            xAxisIndex,
            yAxisIndex: yLeftIndex,
            barMaxWidth: 18,
            z: 2,
            zlevel: 0,
            itemStyle: { color: CHART_COLOR.glassBar },
            data: row.glassArr.map((v, i) => ({
              value: v,
              itemStyle: { opacity: calcOpacity(aoi, rowKey, i) }
            })),
            universalTransition: true
          });

          series.push({
            id: barDefId,
            name: "defect glass count",
            type: "bar",
            xAxisIndex,
            yAxisIndex: yLeftIndex,
            barMaxWidth: 18,
            barGap: "-100%",
            z: 3,
            zlevel: 0,
            itemStyle: { color: CHART_COLOR.defectGlassBar },
            data: row.defectGlassArr.map((v, i) => ({
              value: v,
              itemStyle: { opacity: calcOpacity(aoi, rowKey, i) }
            })),
            universalTransition: true
          });

          series.push({
            id: scBaseId,
            name: "total density",
            type: "scatter",
            xAxisIndex,
            yAxisIndex: yRightIndex,
            symbolSize: 7,
            z: 45,
            zlevel: 1,
            itemStyle: { color: CHART_COLOR.totalDensityPoint },
            label: {
              show: true,
              position: "top",
              distance: 10,
              align: "center",
              verticalAlign: "bottom",
              formatter: (p) => {
                const vv = Array.isArray(p.value) ? p.value[1] : p.value;
                return (typeof vv === "number" && isFinite(vv)) ? vv.toFixed(2) : "";
              },
              fontSize: 10,
              color: CHART_THEME.labelText,
              backgroundColor: CHART_THEME.labelBg,
              padding: CHART_THEME.labelPad,
              borderRadius: CHART_THEME.labelRadius
            },
            data: row.baseDensityArr.map((v, i) => ({
              value: v,
              itemStyle: { opacity: v == null ? 0 : calcOpacity(aoi, rowKey, i) }
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
              align: "center",
              verticalAlign: "bottom",
              formatter: (p) => {
                const vv = Array.isArray(p.value) ? p.value[1] : p.value;
                return (typeof vv === "number" && isFinite(vv)) ? vv.toFixed(2) : "";
              },
              fontSize: 10,
              color: CHART_THEME.labelText,
              backgroundColor: CHART_THEME.labelBg,
              padding: CHART_THEME.labelPad,
              borderRadius: CHART_THEME.labelRadius
            },
            data: row.densityArr.map((v, i) => ({
              value: v,
              itemStyle: { opacity: v == null ? 0 : calcOpacity(aoi, rowKey, i) }
            })),
            universalTransition: true
          });

          if (spec) {
            if (spec.ooc != null && isFinite(spec.ooc)) {
              hasDefaultSpecSeries = true;

              pushSpecMarkLine({
                series,
                name: SPEC_LEGEND_NAME,
                xAxisIndex,
                yAxisIndex: yRightIndex,
                value: Number(spec.ooc),
                color: CHART_COLOR.defaultSpecOOC,
                labelText: () => `OOC ${Number(spec.ooc).toFixed(1)}`,
                z: 30
              });
            }

            if (spec.oos != null && isFinite(spec.oos)) {
              hasDefaultSpecSeries = true;

              pushSpecMarkLine({
                series,
                name: SPEC_LEGEND_NAME,
                xAxisIndex,
                yAxisIndex: yRightIndex,
                value: Number(spec.oos),
                color: CHART_COLOR.defaultSpecOOS,
                labelText: () => `OOS ${Number(spec.oos).toFixed(1)}`,
                z: 31
              });
            }
          }

          densRightAxisMeta.push({
            key: `${rIdx}|${row.model}|${row.glass_side}`,
            gridIndex,
            yId: yRightId,
            baseMax: yRightMax
          });

          yAxisMetaMap[yLeftIndex] = {
            aoi,
            model: row.model,
            glass_side: row.glass_side,
            local: rIdx
          };

          curTop += rowH + (isBottom ? 0 : rowGap);
        });

        const xStart = xAxisCountSoFar;
        const xEnd = xStart + rows.length;

        colAxisIndexRange.push({
          colIndex: colIdx,
          aoi,
          xStart,
          xEnd
        });

        xAxisCountSoFar = xEnd;

        if (rows.length > 0) {
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

      if (!hasDefaultSpecSeries && xAxes.length > 0 && yAxes.length > 1) {
        series.push({
          name: SPEC_LEGEND_NAME,
          type: "line",
          xAxisIndex: 0,
          yAxisIndex: 1,
          data: [null],
          showSymbol: false,
          silent: true,
          tooltip: { show: false },
          lineStyle: { opacity: 0 }
        });
      }

      (global.order || []).forEach((rm, idx) => {
        const top = padTop + idx * (rowH + rowGap);
        const centerY = top + rowH / 2;

        const t1 = String(rm.model || "").trim();
        const t2 = String(rm.glass_side || "").trim();

        graphics.push({
          type: "text",
          left: baseLeft,
          top: centerY - 12,
          style: {
            text: t2 ? `${t1}\n(${t2})` : t1,
            fill: "#b1ffea",
            fontWeight: 600,
            fontSize: 11,
            lineHeight: 14,
            textAlign: "left"
          }
        });
      });

      return {
        animation: true,
        legend: {
          top: LEGEND_TOP,
          right: 10,
          itemGap: 18,
          data: [
            "glass count",
            "defect glass count",
            "total density",
            "density",
            SPEC_LEGEND_NAME
          ],
          selected: {
            "glass count": true,
            "defect glass count": false,
            "total density": false,
            "density": true,
            [SPEC_LEGEND_NAME]: true
          },
          textStyle: {
            color: CHART_THEME.labelText
          }
        },
        tooltip: {
          trigger: "item",
          renderMode: "html",
          extraCssText: "max-width:560px; white-space:normal; line-height:1.35;",
          formatter: (p) => {
            const sId = String(p.seriesId || "");
            const parts = sId.split(":");
            const aoiKey = parts[1] || "";
            const rIdx = Number(parts[2] || 0);

            const col = columns.find(c => c.aoi === aoiKey);
            if (!col) return "";

            const row = col.rows[rIdx];
            if (!row) return "";

            const dataIdx = Number(p.dataIndex || 0);
            const x = row.xItems[dataIdx];
            const raw = row.rowRawArr[dataIdx];
            if (!x) return "";

            const glassCount = row.glassArr[dataIdx];
            const defectCount = row.defectArr[dataIdx];
            const defectGlassCount = row.defectGlassArr[dataIdx];
            const baseDensity = row.baseDensityArr[dataIdx];
            const density = row.densityArr[dataIdx];

            const size = raw ? {
              S: A.sCnt(raw),
              M: A.mCnt(raw),
              L: A.lCnt(raw),
              O: A.oCnt(raw)
            } : { S: 0, M: 0, L: 0, O: 0 };

            const spec = pickBpiSpec(specIndex, row.model, row.glass_side, sizeKey);

            const kv = [
              ["AOI", raw ? A.aoi(raw) : (x.aoi || "")],
              ["Model", row.model],
              ["glass_side", row.glass_side],
              ["Spec size group", sizeKey],
              ["Hourly", fmtHourLabel(x.tick)],
              ["CST", x.cst],
              ["recipe", x.recipe_id],
              ["glass count", String(Math.trunc(glassCount || 0))],
              ["defect glass count", String(Math.trunc(defectGlassCount || 0))],
              ["filtered defect count", String(Math.trunc(defectCount || 0))],
              ["total density", baseDensity == null ? "" : Number(baseDensity).toFixed(2)],
              ["filtered density", density == null ? "" : Number(density).toFixed(2)],
              ["OOC", spec?.ooc == null ? "" : String(spec.ooc)],
              ["OOS", spec?.oos == null ? "" : String(spec.oos)],
              ["S", String(Math.trunc(size.S || 0))],
              ["M", String(Math.trunc(size.M || 0))],
              ["L", String(Math.trunc(size.L || 0))],
              ["O", String(Math.trunc(size.O || 0))]
            ].filter(([, v]) => v !== "" && v != null);

            return kv.map(([k, v]) => `<div><b>${k}</b>: ${v}</div>`).join("");
          }
        },
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
          console.error("[bpi-density slider] mount error:", e);
        }
      });
    };

    const mountOnce = () => {
      mountNow(option.__densRightAxisMeta);
      inst.off("finished", mountOnce);
    };

    inst.off("finished", mountOnce);
    inst.on("finished", mountOnce);

    inst.setOption(option, true);
    setTimeout(() => mountNow(option.__densRightAxisMeta), 0);
    setTimeout(() => mountNow(option.__densRightAxisMeta), 60);

    function pickOneRow(aoiKey, model, side, dataIdx) {
      const col = columns.find(c => c.aoi === aoiKey);
      if (!col) return [];

      const row = col.rows.find(r => r.model === model && r.glass_side === side);
      if (!row) return [];

      const raw = row.rowRawArr[dataIdx];
      return raw ? [raw] : [];
    }

    inst.off("click");
    inst.on("click", function (ev) {
      if (ev?.componentType === "series") {
        const sId = String(ev.seriesId || "");
        const parts = sId.split(":");
        const aoiKey = parts[1] || "";
        const rIdx = Number(parts[2] || 0);

        const col = columns.find(c => c.aoi === aoiKey);
        if (!col) return;

        const row = col.rows[rIdx];
        if (!row) return;

        const pick = pickOneRow(aoiKey, row.model, row.glass_side, ev.dataIndex);

        if (pick.length) {
          window.AOI_BPI_DENSITY?.handleSelection?.(
            pick,
            window.AOI_BPI_DENSITY?.state?.paramDict || {}
          );
        }
      } else if (ev?.componentType === "yAxis") {
        const yIdx = ev?.yAxisIndex;
        const metaMap = inst.getOption().__yAxisMetaMap || {};
        const hit = metaMap[yIdx];
        if (!hit) return;

        const pick = (rawRows || []).filter(r =>
          A.model(r) === hit.model &&
          A.side(r) === hit.glass_side
        );

        if (pick.length) {
          window.AOI_BPI_DENSITY?.handleSelection?.(
            pick,
            window.AOI_BPI_DENSITY?.state?.paramDict || {}
          );
        }
      }
    });

    inst.off("brushselected");
    inst.on("brushselected", function (params) {
      interopState.selectedTicks.clear();

      const sel = params.batch?.[0]?.selected || [];
      const ranges = inst.getOption().__colAxisIndexRange || [];

      sel.forEach((ss) => {
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

        const [sidx, eidx] = idxRange;
        const lo = Math.min(sidx, eidx);
        const hi = Math.max(sidx, eidx);

        for (let i = lo; i <= hi; i++) {
          interopState.selectedTicks.add(`${found.aoi}|${i}`);
        }
      });

      refreshOpacity(inst, columns, calcOpacity);
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
      setTimeout(() => mountNow(op.__densRightAxisMeta), 0);
      setTimeout(() => mountNow(op.__densRightAxisMeta), 60);

      refreshOpacity(inst, columns, calcOpacity);
    }

    if (MOD.Charts.__resizeHandler) {
      window.removeEventListener("resize", MOD.Charts.__resizeHandler);
    }

    MOD.Charts.__resizeHandler = () => {
      inst.resize();
      rebuild();
    };

    window.addEventListener("resize", MOD.Charts.__resizeHandler);
  }

  function refreshOpacity(inst, columns, calcOpacity) {
    const updates = [];

    columns.forEach((col) => {
      const { aoi, rows } = col;

      rows.forEach((row, rIdx) => {
        const rowKey = buildRowKey(aoi, row.model, row.glass_side);

        const barId = `barG:${aoi}:${rIdx}`;
        const newBarData = (row.glassArr || []).map((v, i) => ({
          value: v,
          itemStyle: { opacity: calcOpacity(aoi, rowKey, i) }
        }));
        updates.push({ id: barId, data: newBarData });

        const barDefId = `barDG:${aoi}:${rIdx}`;
        const newBarDefData = (row.defectGlassArr || []).map((v, i) => ({
          value: v,
          itemStyle: { opacity: calcOpacity(aoi, rowKey, i) }
        }));
        updates.push({ id: barDefId, data: newBarDefData });

        const scBaseId = `scBase:${aoi}:${rIdx}`;
        const newScBaseData = (row.baseDensityArr || []).map((v, i) => ({
          value: v,
          itemStyle: { opacity: v == null ? 0 : calcOpacity(aoi, rowKey, i) }
        }));
        updates.push({ id: scBaseId, data: newScBaseData });

        const scId = `sc:${aoi}:${rIdx}`;
        const newScData = (row.densityArr || []).map((v, i) => ({
          value: v,
          itemStyle: { opacity: v == null ? 0 : calcOpacity(aoi, rowKey, i) }
        }));
        updates.push({ id: scId, data: newScData });
      });
    });

    if (updates.length) {
      inst.setOption({ series: updates }, false, false);
    }
  }

  MOD.Charts.render = function (rows, _paramDict) {
    const dom = buildHost();
    if (!dom) return;

    const safeRows = Array.isArray(rows) ? rows : [];

    const defaultSpecRows = resolveBpiDensityDefaultSpecRows();
    const specIndex = buildBpiSpecIndex(defaultSpecRows);

    const selectedSizes = getSelectedSizes();
    const sizeKey = canonicalBpiSizeKey(selectedSizes);

    console.log("[BPI Density Chart] spec debug", {
      rows: safeRows.length,
      defaultSpecRows: defaultSpecRows.length,
      selectedSizes,
      sizeKey,
      specIndexKeys: Object.keys(specIndex).slice(0, 20),
    });

    const global = buildGlobalRowOrder(safeRows);
    const columns = buildColumnsByAoi(safeRows, global.order);

    if (!columns.length) {
      dom.innerHTML = "<div class='muted'>沒有資料</div>";
      return;
    }

    renderBigChart(dom, columns, global, safeRows, specIndex, sizeKey);
  };
})();