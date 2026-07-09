// static/js/aoi_inspection_density/function1/chart1.js
(function () {
  const MOD = (window.AOI_INSPECTION = window.AOI_INSPECTION || {});
  MOD.Charts = MOD.Charts || {};

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
    glassTotalBar: "#9aa3b2",
    defectGlassBar: "#FF851B",
    densityPoint: "#FF4136",
    specOOC: "#FFDC00",
    specOOS: "#CE0000"
  };

  // ============================================================
  // Alert scatter flash config
  //
  // scatter 顯示值仍是目前 filter size 後的 density。
  // scatter 是否閃爍則看後端 maingroup_density / total_density 是否 > 200。
  // ============================================================
  const ALERT_DENSITY_THRESHOLD = 200;

  const ALERT_FLASH = {
    red: "#FF4136",
    blue: "#0074D9",
    normal: CHART_COLOR.densityPoint,
    symbolSize: 11,
    normalSymbolSize: 7,
    intervalMs: 650
  };

  const runtime = {
    inst: null,
    resizeBound: false,
    flashTimer: null,
    flashOn: false
  };

  const interopState = {
    selectedTicks: new Set(),
    focusRowKey: null
  };

  function getDensityScaleStore() {
    if (!MOD.Charts.__densScaleByKey) {
      MOD.Charts.__densScaleByKey = Object.create(null);
    }
    return MOD.Charts.__densScaleByKey;
  }

  function ensureOverlay(dom) {
    let overlay = dom.querySelector(".aoi-inspection-density-slider-overlay");

    if (!overlay) {
      overlay = document.createElement("div");
      overlay.className = "aoi-inspection-density-slider-overlay";
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
      { yAxis: [{ id: yId, min: 0, max: newMax }] },
      { notMerge: false, lazyUpdate: true, silent: true }
    );
  }

  function mountPerGridSliders(dom, inst, densMetaList) {
    if (!inst || !Array.isArray(densMetaList) || !densMetaList.length) return;

    ensureOverlay(dom);
    dom.querySelectorAll(".aoi-inspection-density-slider-wrap").forEach((el) => el.remove());

    const store = getDensityScaleStore();
    const model = inst.getModel?.();

    if (!model) return;

    densMetaList.forEach((m) => {
      const gridModel = model.getComponent("grid", m.gridIndex);
      const rect = gridModel?.coordinateSystem?.getRect?.();

      if (!rect || !(rect.width > 0) || !(rect.height > 0)) return;

      const wrap = document.createElement("div");
      wrap.className = "aoi-inspection-density-slider-wrap";
      wrap.style.position = "absolute";
      wrap.style.pointerEvents = "auto";
      wrap.style.left = `${rect.x + rect.width + 2}px`;
      wrap.style.top = `${rect.y}px`;
      wrap.style.width = "20px";
      wrap.style.height = `${rect.height}px`;
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
      range.style.height = `${rect.height}px`;
      range.style.writingMode = "vertical-lr";
      range.style.direction = "rtl";
      range.style.opacity = "0.92";
      range.style.margin = "0";

      const tag = document.createElement("div");
      tag.textContent = `${range.value}%`;
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
        tag.textContent = `${range.value}%`;

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

      const baseMax = Number(m.baseMax);
      const newMax = Math.max(1e-6, (Number.isFinite(baseMax) ? baseMax : 1) * initScale);
      applyOneRightAxisMaxById(inst, m.yId, newMax);
    });
  }

  function s(v) {
    return v == null ? "" : String(v);
  }

  function n(v) {
    const x = Number(v);
    return Number.isFinite(x) ? x : 0;
  }

  const A = {
    line: (r) => s(r?.line_id),
    model: (r) => s(r?.model),
    side: (r) => s(r?.glass_type),
    tick: (r) => s(r?.tick_str ?? r?.pi_hour),

    g: (r) => n(r?.maingroup_glass_count ?? r?.n_glasses ?? r?.glass_num),
    d: (r) => n(r?.maingroup_defect_count ?? r?.defect_num ?? r?.n_rows),

    // alert 判斷用：優先 maingroup_density
    tD: (r) => n(r?.maingroup_density ?? r?.total_density ?? r?.totalDensity),

    cg: (r) => n(r?.defect_code_glass_count ?? r?.code_glass_num),

    sCnt: (r) => n(r?.small_defect_count ?? r?.s_count),
    mCnt: (r) => n(r?.middle_defect_count ?? r?.m_count),
    lCnt: (r) => n(r?.large_defect_count ?? r?.l_count),
    oCnt: (r) => n(r?.over_defect_count ?? r?.o_count),

    dens: (r) => {
      const g = n(r?.maingroup_glass_count ?? r?.n_glasses ?? r?.glass_num);
      const d = n(r?.maingroup_defect_count ?? r?.defect_num ?? r?.n_rows);
      return g > 0 ? d / g : 0;
    }
  };

  function parseTickToDate(tick) {
    const raw = String(tick || "").trim();
    if (!raw) return null;

    if (/^\d{2}-\d{2}-\d{2}\s+\d{2}$/.test(raw)) {
      const [datePart, hh] = raw.split(/\s+/);
      const [yy, mm, dd] = datePart.split("-").map(Number);
      return new Date(2000 + yy, mm - 1, dd, Number(hh), 0, 0);
    }

    const d2 = new Date(raw.replace(" ", "T"));
    return isNaN(d2.getTime()) ? null : d2;
  }

  function getSelectedSizes() {
    try {
      const ui = window.AOI_INSPECTION?.readFiltersFromUI?.();
      const ds = ui?.defect_size;

      if (Array.isArray(ds) && ds.length) return ds;
    } catch (_) {}

    return ["S", "M", "L", "O"];
  }

  function buildSpecIndex(rows) {
    const idx = {};
    if (!Array.isArray(rows)) return idx;

    rows.forEach((r) => {
      if (!r) return;

      const line = s(r.line_id).trim();
      const model = s(r.model).trim();
      const side = s(r.glass_type || "all").trim();

      if (!line || !model) return;

      idx[line] = idx[line] || {};
      idx[line][model] = idx[line][model] || {};
      idx[line][model][side] = {
        ooc: Number.isFinite(Number(r.OOC)) ? Number(r.OOC) : null,
        oos: Number.isFinite(Number(r.OOS)) ? Number(r.OOS) : null
      };
    });

    return idx;
  }

  function pickSpec(specIdx, line, model, side) {
    if (!specIdx?.[line]?.[model]) return null;

    const obj = specIdx[line][model];

    if (obj[side]) return obj[side];
    if (obj.all) return obj.all;

    const anyKey = Object.keys(obj)[0];
    return anyKey ? obj[anyKey] : null;
  }

  function buildGlobalRowOrder(rows) {
    const byLine = new Map();

    (rows || []).forEach((r) => {
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

    lines.forEach((line) => {
      const byModel = byLine.get(line);
      const models = Array.from(byModel.keys()).sort();

      models.forEach((model) => {
        const sides = Array.from(byModel.get(model)).sort();

        sides.forEach((side) => {
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

  function buildColumns(rows, globalOrder, specIndex, selectedSizesArr) {
    const selected = new Set(
      selectedSizesArr && selectedSizesArr.length ? selectedSizesArr : ["S", "M", "L", "O"]
    );

    const agg = {};
    const ticksSet = new Set();

    (rows || []).forEach((r) => {
      const line = A.line(r);
      const model = A.model(r);
      const side = A.side(r);
      const tick = A.tick(r);

      if (!line || !model || !side || !tick) return;

      ticksSet.add(tick);

      const L = (agg[line] = agg[line] || {});
      const M = (L[model] = L[model] || {});
      const S = (M[side] = M[side] || {});

      const T = (S[tick] = S[tick] || {
        g: 0,
        cg: 0,
        d: 0,
        s: 0,
        m: 0,
        l: 0,
        o: 0,
        mainDensitySum: 0,
        mainDensityWeight: 0,
        rows: []
      });

      T.g += A.g(r);
      T.cg += A.cg(r);
      T.d += A.d(r);
      T.s += A.sCnt(r);
      T.m += A.mCnt(r);
      T.l += A.lCnt(r);
      T.o += A.oCnt(r);

      // ========================================================
      // Alert 判斷用 maingroup_density。
      // 若同 bucket 有多筆聚合，採 glass count 加權平均。
      // ========================================================
      const mainDensity = A.tD(r);
      const mainGlass = A.g(r);

      if (Number.isFinite(mainDensity) && mainDensity > 0) {
        const w = Math.max(1, mainGlass);
        T.mainDensitySum += mainDensity * w;
        T.mainDensityWeight += w;
      }

      T.rows.push(r);
    });

    const xTicks = Array.from(ticksSet).sort((a, b) => {
      const da = parseTickToDate(a);
      const db = parseTickToDate(b);
      return (da?.getTime() ?? 0) - (db?.getTime() ?? 0);
    });

    const rowsOut = globalOrder.map(({ line_id, model, glass_type }) => {
      const bucket = ((((agg[line_id] || {})[model] || {})[glass_type]) || {});

      const glasses = [];
      const codeGlasses = [];
      const density = [];
      const mainDensityArr = [];
      const alertFlags = [];

      const sArr = [];
      const mArr = [];
      const lArr = [];
      const oArr = [];
      const defSelArr = [];

      xTicks.forEach((tk) => {
        const T = bucket[tk] || {
          g: 0,
          cg: 0,
          d: 0,
          s: 0,
          m: 0,
          l: 0,
          o: 0,
          mainDensitySum: 0,
          mainDensityWeight: 0,
          rows: []
        };

        const sCnt = selected.has("S") ? Number(T.s || 0) : 0;
        const mCnt = selected.has("M") ? Number(T.m || 0) : 0;
        const lCnt = selected.has("L") ? Number(T.l || 0) : 0;
        const oCnt = selected.has("O") ? Number(T.o || 0) : 0;
        const dSel = sCnt + mCnt + lCnt + oCnt;

        let cg = Number(T.cg || 0);
        if (dSel === 0) cg = 0;

        const g = Number(T.g || 0);

        const displayDensity = g > 0 ? dSel / g : null;

        let mainDensity = null;
        if (T.mainDensityWeight > 0) {
          mainDensity = T.mainDensitySum / T.mainDensityWeight;
        } else {
          mainDensity = g > 0 ? Number(T.d || 0) / g : null;
        }

        glasses.push(g);
        codeGlasses.push(cg);

        // scatter value：維持目前 filter size 後的 density
        density.push(displayDensity);

        // alert 判斷：用後端 maingroup_density，不新增另一顆 scatter
        mainDensityArr.push(mainDensity);
        alertFlags.push(mainDensity != null && mainDensity > ALERT_DENSITY_THRESHOLD);

        sArr.push(sCnt);
        mArr.push(mCnt);
        lArr.push(lCnt);
        oArr.push(oCnt);
        defSelArr.push(dSel);
      });

      const spec = pickSpec(specIndex, line_id, model, glass_type);

      return {
        line_id,
        model,
        glass_type,

        glasses,
        codeGlasses,
        density,

        // alert meta
        mainDensityArr,
        alertFlags,

        sArr,
        mArr,
        lArr,
        oArr,
        defSelArr,

        maxG: Math.max(0, ...glasses, ...codeGlasses),

        // 右軸仍只看目前顯示的 scatter density，不用 maingroup_density 撐高。
        maxD: Math.max(0, ...density.filter((v) => v != null)),

        spec: spec || null
      };
    });

    return [{ xTicks, rows: rowsOut }];
  }

  function calcOpacity(rowKey, xIdx) {
    let passTick = true;

    if (interopState.selectedTicks.size > 0) {
      passTick = interopState.selectedTicks.has(`${xIdx}|main`);
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

  // ============================================================
  // Alert scatter flash helpers
  // ============================================================
  function hasAnyAlertPoint(columns) {
    return (columns || []).some((col) =>
      (col.rows || []).some((row) =>
        (row.alertFlags || []).some(Boolean)
      )
    );
  }

  
  function buildScatterData(row, rowKey) {
    return (row.density || []).map((v, i) => {
      const isAlert = !!row.alertFlags?.[i];

      return {
        value: v,

        // 給 label.formatter 判斷是否要顯示「爆點」
        needAlert: isAlert,

        // tooltip 也可讀到 maingroup_density
        mainDensity: row.mainDensityArr?.[i],

        symbolSize: isAlert ? ALERT_FLASH.symbolSize : ALERT_FLASH.normalSymbolSize,

        itemStyle: {
          opacity: v == null ? 0 : calcOpacity(rowKey, i),
          color: isAlert
            ? (runtime.flashOn ? ALERT_FLASH.red : ALERT_FLASH.blue)
            : ALERT_FLASH.normal
        }
      };
    });
  }

  function stopAlertFlashTimer() {
    if (runtime.flashTimer) {
      clearInterval(runtime.flashTimer);
      runtime.flashTimer = null;
    }

    runtime.flashOn = false;
  }

  function startAlertFlashTimer(inst, columns) {
    stopAlertFlashTimer();

    if (!inst || !hasAnyAlertPoint(columns)) return;

    runtime.flashTimer = setInterval(() => {
      runtime.flashOn = !runtime.flashOn;
      refreshAlertScatterStyle(inst, columns);
    }, ALERT_FLASH.intervalMs);
  }

  function refreshAlertScatterStyle(inst, columns) {
    if (!inst || !Array.isArray(columns)) return;

    const updates = [];

    columns.forEach((col) => {
      (col.rows || []).forEach((row, rIdx) => {
        const rowKey = `main|${rIdx}|${row.line_id}|${row.model}|${row.glass_type}`;

        updates.push({
          id: `sc:main:${rIdx}`,
          data: buildScatterData(row, rowKey)
        });
      });
    });

    if (updates.length) {
      inst.setOption({ series: updates }, false, false);
    }
  }

  function rowsByCriteria(allRows, criteria) {
    return (allRows || []).filter((r) => {
      if (criteria.line && A.line(r) !== criteria.line) return false;
      if (criteria.line_id && A.line(r) !== criteria.line_id) return false;
      if (criteria.model && A.model(r) !== criteria.model) return false;
      if (criteria.side && A.side(r) !== criteria.side) return false;
      if (criteria.glass_type && A.side(r) !== criteria.glass_type) return false;
      if (criteria.tick && A.tick(r) !== criteria.tick) return false;
      return true;
    });
  }

  function ensureHost() {
    const host = document.querySelector("#aoi-inspection-density-facet");
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

  function showRowsInTable(rows) {
    window.AOI_INSPECTION?.Table?.showRows?.(
      rows,
      window.AOI_INSPECTION?.state?.paramDict
    );
  }

  function fetchMapForRows(rows, tickStr) {
    try {
      if (!Array.isArray(rows) || !rows.length) return;
      if (!window.AOI_INSPECTION?.Map?.fetchAndRender) return;

      const defectRows = rows.map((r) => ({
        glass_type: r.glass_type,
        line_id: r.line_id,
        glass: r.glass,
        model: r.model,
        pi_hour: r.pi_hour || tickStr || ""
      }));

      window.AOI_INSPECTION.Map.fetchAndRender(defectRows);
    } catch (err) {
      console.error("[inspection charts] defect_map fetch error:", err);
    }
  }

  function bindResize(inst, rebuild) {
    if (runtime.resizeBound) return;

    runtime.resizeBound = true;

    window.addEventListener("resize", () => {
      if (!runtime.inst) return;
      runtime.inst.resize();
      rebuild();
    });
  }

  function renderBigChart(dom, columns, global, rawRows) {
    const ec = window.echarts;
    if (!ec) return;

    stopAlertFlashTimer();

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
    const rightMargin = 40;

    const colGap = 24;
    const rowH = 118;
    const rowGap = 50;

    const maxRows = Math.max(1, global.order.length);
    const totalH = padTop + maxRows * rowH + (maxRows - 1) * rowGap + padBottom + 60;
    dom.style.height = `${totalH}px`;

    const width = dom.clientWidth || 1200;
    const nCols = Math.max(1, columns.length);
    const colWidth = Math.max(
      260,
      Math.floor((width - leftMargin - rightMargin - (nCols - 1) * colGap) / nCols)
    );

    const totalChartWidth = leftMargin + nCols * (colWidth + colGap) - colGap + rightMargin;
    dom.style.width = `${totalChartWidth}px`;

    const old = ec.getInstanceByDom(dom);
    if (old) {
      try { old.dispose(); } catch (_) {}
    }

    const inst = ec.init(dom);
    runtime.inst = inst;

    const yAxisMetaMap = {};

    function buildOption() {
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
        const { xTicks, rows } = col;
        const colLeft = leftMargin + colIdx * (colWidth + colGap);
        const hasRows = rows.length > 0;

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
            data: xTicks,
            axisTick: {
              alignWithLabel: true,
              lineStyle: { color: CHART_THEME.axisTick, width: 1 }
            },
            axisLabel: {
              show: isBottom,
              rotate: 90,
              margin: 12,
              color: CHART_THEME.axisLabel
            },
            axisLine: {
              onZero: false,
              lineStyle: { color: CHART_THEME.axisLine, width: 1 }
            },
            triggerEvent: true
          });

          const gMax = Math.max(1, Math.ceil((row.maxG || 1) * 1.2));

          const yLeftIndex = yAxes.length;

          yAxes.push({
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
            axisLabel: { show: true, color: CHART_THEME.axisLabel },
            axisLine: { lineStyle: { color: CHART_THEME.axisLine, width: 1 } },
            axisTick: { lineStyle: { color: CHART_THEME.axisTick, width: 1 } },
            triggerEvent: true
          });

          const dBaseMax = Math.max(1, (row.maxD || 0) * 1.4);

          const mlMax = Math.max(
            0,
            row?.spec?.ooc || 0,
            row?.spec?.oos || 0
          );

          const yRightMax = Math.max(dBaseMax, mlMax ? mlMax * 1.05 : 0);
          const yRightId = `yR:main:${rIdx}`;
          const yRightIndex = yAxes.length;

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

          yAxisMetaMap[yLeftIndex] = { local: rIdx };

          const rowKey = `main|${rIdx}|${row.line_id}|${row.model}|${row.glass_type}`;
          const densKey = rowKey;

          densRightAxisMeta.push({
            key: densKey,
            gridIndex,
            yId: yRightId,
            baseMax: yRightMax,
            debug: {
              line_id: row.line_id,
              model: row.model,
              glass_type: row.glass_type,
              rIdx
            }
          });

          const barIdG = `barG:main:${rIdx}`;
          const barIdCG = `barCG:main:${rIdx}`;
          const scId = `sc:main:${rIdx}`;

          series.push({
            id: barIdG,
            name: "glass (total)",
            type: "bar",
            xAxisIndex,
            yAxisIndex: yLeftIndex,
            barMaxWidth: 14,
            barGap: "0%",
            z: 1,
            itemStyle: { color: CHART_COLOR.glassTotalBar },
            data: row.glasses.map((v, i) => ({
              value: v,
              itemStyle: { opacity: calcOpacity(rowKey, i) }
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
            itemStyle: { color: CHART_COLOR.defectGlassBar },
            label: { show: false },
            data: row.codeGlasses.map((v, i) => ({
              value: v,
              itemStyle: { opacity: calcOpacity(rowKey, i) }
            })),
            universalTransition: true
          });

          series.push({
            id: scId,
            name: "density",
            type: "scatter",
            xAxisIndex,
            yAxisIndex: yRightIndex,
            symbolSize: ALERT_FLASH.normalSymbolSize,
            z: 50,
            itemStyle: { color: CHART_COLOR.densityPoint },
            label: {
              show: true,
              position: "top",
              distance: 10,
              align: "center",
              verticalAlign: "bottom",
            
              formatter: (p) => {
                const vv = Array.isArray(p.value) ? p.value[1] : p.value;
                const hasValue = typeof vv === "number" && isFinite(vv);
            
                if (!hasValue) return "";
            
                if (p?.data?.needAlert) {
                  return `{alert|爆點}\n{gap| }\n{val|${vv.toFixed(2)}}`;
                }
            
                return `{val|${vv.toFixed(2)}}`;
              },
            
              // 外層透明，避免整個 label 黑底被撐大
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
                  backgroundColor: "transparent",
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
            data: buildScatterData(row, rowKey),
            connectNulls: false,
            universalTransition: true
          });

          if (row.spec) {
            if (row.spec.ooc != null && isFinite(row.spec.ooc)) {
              pushSpecMarkLine({
                name: "SPEC",
                xAxisIndex,
                yAxisIndex: yRightIndex,
                value: Number(row.spec.ooc),
                color: CHART_COLOR.specOOC,
                labelText: () => `${Number(row.spec.ooc).toFixed(1)}`,
                z: 30
              });
            }

            if (row.spec.oos != null && isFinite(row.spec.oos)) {
              pushSpecMarkLine({
                name: "SPEC",
                xAxisIndex,
                yAxisIndex: yRightIndex,
                value: Number(row.spec.oos),
                color: CHART_COLOR.specOOS,
                labelText: () => `${Number(row.spec.oos).toFixed(1)}`,
                z: 30
              });
            }
          }

          curTop += rowH + (isBottom ? 0 : rowGap);
        });

        const xStart = xAxisCountSoFar;
        const xEnd = xStart + rows.length;

        colAxisIndexRange.push({
          colIndex: colIdx,
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

      const hasSpecSeries = series.some((ss) => ss && ss.name === "SPEC");

      if (!hasSpecSeries && xAxes.length > 0 && yAxes.length > 1) {
        series.push({
          name: "SPEC",
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

      const lineX = 16 + Math.floor(26 / 2);
      const modelX = 16 + 26 + 8 + Math.floor(26 / 2);

      (global.lineGroups || []).forEach((gp) => {
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
          data: ["glass (total)", "defect glass", "density", "SPEC"],
          selected: {
            "glass (total)": true,
            "defect glass": false,
            "density": true,
            "SPEC": true
          }
        },
        tooltip: {
          trigger: "axis",
          axisPointer: { type: "cross", snap: true },
          renderMode: "html",
          extraCssText: "max-width:560px; white-space:normal; line-height:1.35;",
          formatter: (params) => {
            const list = Array.isArray(params) ? params : [params];
            const p0 = list[0] || {};
            const [, , rIdxStr = "0"] = String(p0.seriesId || "").split(":");
            const rIdx = Number(rIdxStr) || 0;

            const col = columns[0];

            const tickStr = (p0.axisValue != null)
              ? String(p0.axisValue)
              : (col ? col.xTicks[p0.dataIndex] : "");

            const row = col ? col.rows[rIdx] : null;

            if (!row || !tickStr) return "";

            const pick = rowsByCriteria(rawRows, {
              line: row.line_id,
              model: row.model,
              side: row.glass_type,
              tick: tickStr
            });

            if (!pick?.length) return "";

            const idx = col.xTicks.indexOf(tickStr);
            const gTotal = (idx >= 0) ? row.glasses[idx] : null;
            const gCode = (idx >= 0) ? row.codeGlasses[idx] : null;

            const dens = (idx >= 0 && row.density[idx] != null)
              ? Number(row.density[idx]).toFixed(2)
              : "";

            const mainDens = (idx >= 0 && row.mainDensityArr?.[idx] != null)
              ? Number(row.mainDensityArr[idx]).toFixed(2)
              : "";

            const isAlert = idx >= 0 && row.alertFlags?.[idx];

            let dCode = 0;
            let S = 0;
            let M = 0;
            let L = 0;
            let O = 0;

            pick.forEach((rec) => {
              S += n(rec.small_defect_count);
              M += n(rec.middle_defect_count);
              L += n(rec.large_defect_count);
              O += n(rec.over_defect_count);
            });

            dCode = S + M + L + O;

            const sizeLine = [["S", S], ["M", M], ["L", L], ["O", O]]
              .filter(([, v]) => v > 0)
              .map(([k, v]) => `${k}${Math.trunc(v)}`)
              .join(", ");

            const kv = [
              ["density(filter size)", dens],
              ["maingroup_density", mainDens],
              ["alert", isAlert ? `YES > ${ALERT_DENSITY_THRESHOLD}` : ""],
              ["total glass count(hourly)", gTotal == null ? "" : String(Math.trunc(gTotal))],
              ["defect glass count", gCode == null ? "" : String(Math.trunc(gCode))],
              ["defect count(filter size)", String(Math.trunc(dCode))],
              ["S/M/L/O", sizeLine]
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

    const option = buildOption();

    const mountNow = (meta) => {
      requestAnimationFrame(() => {
        try {
          mountPerGridSliders(dom, inst, meta);
        } catch (e) {
          console.error("[inspection-slider] mount error:", e);
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
    startAlertFlashTimer(inst, columns);

    setTimeout(() => mountNow(option.__densRightAxisMeta), 0);
    setTimeout(() => mountNow(option.__densRightAxisMeta), 60);

    let lastClickAt = 0;

    inst.off("click");
    inst.on("click", function (ev) {
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

        const tickStr = String(ev.value);
        const pick = rowsByCriteria(rawRows, { tick: tickStr });
        showRowsInTable(pick);

      } else if (ev?.componentType === "yAxis") {
        const yIdx = ev?.yAxisIndex;
        const metaMap = inst.getOption().__yAxisMetaMap || {};
        const hit = metaMap[yIdx];

        if (!hit) return;

        const col = columns[0];
        if (!col) return;

        const row = col.rows[hit.local];
        if (!row) return;

        const pick = rowsByCriteria(rawRows, {
          line: row.line_id,
          model: row.model,
          side: row.glass_type
        });

        showRowsInTable(pick);

      } else if (ev?.componentType === "series") {
        const now = Date.now();

        if (now - lastClickAt < 300) return;
        lastClickAt = now;

        const sId = ev.seriesId || "";
        const parts = sId.split(":");
        const rIdx = Number(parts[2] || 0);

        const col = columns[0];
        if (!col) return;

        const dataIdx = ev.dataIndex;
        const tickStr = col.xTicks[dataIdx];
        const row = col.rows[rIdx];

        if (!tickStr || !row) return;

        const pick = rowsByCriteria(rawRows, {
          line: row.line_id,
          model: row.model,
          side: row.glass_type,
          tick: tickStr
        });

        showRowsInTable(pick);
        fetchMapForRows(pick, tickStr);
      }
    });

    inst.off("brushselected");
    inst.on("brushselected", function (params) {
      interopState.selectedTicks.clear();

      const sel = params.batch?.[0]?.selected || [];
      const ranges = inst.getOption().__colAxisIndexRange || [];

      sel.forEach((s) => {
        const axisIndex = s.xAxisIndex;
        const idxRange = s.dataIndex;

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
          interopState.selectedTicks.add(`${i}|main`);
        }
      });

      refreshOpacity(inst, columns);
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
      startAlertFlashTimer(inst, columns);

      setTimeout(() => mountNow(op.__densRightAxisMeta), 0);
      setTimeout(() => mountNow(op.__densRightAxisMeta), 60);

      refreshOpacity(inst, columns);
    }

    bindResize(inst, rebuild);
  }

  function refreshOpacity(inst, columns) {
    const updates = [];

    columns.forEach((col) => {
      const { rows } = col;

      rows.forEach((row, rIdx) => {
        const rowKey = `main|${rIdx}|${row.line_id}|${row.model}|${row.glass_type}`;

        updates.push({
          id: `barG:main:${rIdx}`,
          data: (row.glasses || []).map((v, i) => ({
            value: v,
            itemStyle: { opacity: calcOpacity(rowKey, i) }
          }))
        });

        updates.push({
          id: `barCG:main:${rIdx}`,
          data: (row.codeGlasses || []).map((v, i) => ({
            value: v,
            itemStyle: { opacity: calcOpacity(rowKey, i) }
          }))
        });

        updates.push({
          id: `sc:main:${rIdx}`,
          data: buildScatterData(row, rowKey)
        });
      });
    });

    if (updates.length) {
      inst.setOption({ series: updates }, false, false);
    }
  }

  MOD.Charts.render = function (rows, _paramDict) {
    const dom = ensureHost();
    if (!dom) return;

    const currentRows = Array.isArray(rows) ? rows : [];

    if (!currentRows.length) {
      stopAlertFlashTimer();
      dom.innerHTML = "<div class='muted'>沒有資料</div>";
      return;
    }

    let proSpecDict = window.AOI_INSPECTION?.state?.ProSpecDict || null;

    if (!proSpecDict && _paramDict && _paramDict.ProSpecDict) {
      proSpecDict = _paramDict.ProSpecDict;
    }

    const defaultRows = proSpecDict && proSpecDict.default_spec_table
      ? Object.values(proSpecDict.default_spec_table)
      : [];

    const specIndex = buildSpecIndex(defaultRows);
    const global = buildGlobalRowOrder(currentRows);
    const columns = buildColumns(currentRows, global.order, specIndex, getSelectedSizes());

    if (!columns.length) {
      stopAlertFlashTimer();
      dom.innerHTML = "<div class='muted'>沒有資料</div>";
      return;
    }

    renderBigChart(dom, columns, global, currentRows);
  };
})();