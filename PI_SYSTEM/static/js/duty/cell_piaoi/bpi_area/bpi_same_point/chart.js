// static/js/bpi_area/bpi_same_point/chart.js
(function () {
  const MOD = (window.BPI_SAME_POINT = window.BPI_SAME_POINT || {});
  const Chart = (MOD.Chart = MOD.Chart || {});
  const state = MOD.state || {};

  const SPEC_LEGEND_NAME = "預設spec";

  const SPEC_COLORS = {
    OOC: "#FFB066", // 淺橘
    OOS: "#FF3333", // 紅
  };

  function $(id) {
    return document.getElementById(id);
  }

  function num(v) {
    const n = Number(v);
    return Number.isFinite(n) ? n : 0;
  }

  function safeStr(v) {
    return v == null ? "" : String(v);
  }

  function cleanStr(v) {
    return v == null ? "" : String(v).trim();
  }

  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  function parseDate(v) {
    const d = new Date(String(v || "").replace(" ", "T"));
    return isNaN(d.getTime()) ? null : d;
  }

  function hourLabel(v) {
    const d = parseDate(v);
    if (!d) return safeStr(v);

    return (
      `${d.getFullYear()}-` +
      `${pad2(d.getMonth() + 1)}-` +
      `${pad2(d.getDate())} ` +
      `${pad2(d.getHours())}`
    );
  }

  function hourTime(v) {
    const d = parseDate(v);
    return d ? d.getTime() : 0;
  }

  function groupKey(row) {
    return `${safeStr(row.model) || "-"}||${safeStr(row.glass_side) || "-"}`;
  }

  function groupTitle(row) {
    const model = safeStr(row.model) || "-";
    const side = safeStr(row.glass_side) || "-";
    return `${model}(${side})`;
  }

  function xLabel(row) {
    const hour = hourLabel(row.scan_hour);
    const glass = safeStr(row.glass_id);
    const g4 = glass ? glass.slice(-4) : "";

    return g4 ? `${hour}\n${g4}` : hour;
  }

  // ============================================================
  // Spec helpers
  // ============================================================
  function normalizeSpecRows(raw) {
    if (!raw) return [];
    if (Array.isArray(raw)) return raw;
    if (typeof raw === "object") return Object.values(raw);
    return [];
  }

  function getSamePointSpecRows() {
    const sp = window.BPI_SAME_POINT || {};
    const spState = sp.state || {};

    const pro =
      state?.ProSpecDict ||
      state?.payload?.ProSpecDict ||
      spState?.ProSpecDict ||
      spState?.payload?.ProSpecDict ||
      {};

    return normalizeSpecRows(
      pro.bpi_same_point_default_spec ||
      pro.bpi_same_point_default_spec_table ||
      []
    );
  }

  function getSelectedDefectSizes() {
    const wrap = state?.mdd?.defect_size;
    const selected = wrap?.mdd?.getSelected?.() || [];
    const options = wrap?.options || [];

    const sel = Array.isArray(selected)
      ? selected.map(x => String(x).trim().toUpperCase()).filter(Boolean)
      : [];

    const opts = Array.isArray(options)
      ? options.map(x => String(x).trim().toUpperCase()).filter(Boolean)
      : [];

    const atoms = sel.filter(x => ["S", "M", "L", "O"].includes(x));

    if (!atoms.length) return ["S", "M", "L", "O"];

    const atomOpts = opts.filter(x => ["S", "M", "L", "O"].includes(x));

    if (
      atomOpts.length &&
      atoms.length === atomOpts.length &&
      atoms.every(x => atomOpts.includes(x))
    ) {
      return ["S", "M", "L", "O"];
    }

    return atoms;
  }

  function selectedAtomsToSpecGroup(atoms) {
    const set = new Set(
      (atoms || []).map(x => String(x).trim().toUpperCase()).filter(Boolean)
    );

    if (!set.size) return "OLMS";

    const hasS = set.has("S");
    const hasM = set.has("M");
    const hasL = set.has("L");
    const hasO = set.has("O");

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

  function findSpecForGroup(group) {
    const first = group?.rows?.[0] || {};
    const model = cleanStr(first.model);
    const side = cleanStr(first.glass_side);
    const specGroup = selectedAtomsToSpecGroup(getSelectedDefectSizes());

    const rows = getSamePointSpecRows();

    const matched = rows.find(r =>
      cleanStr(r.model) === model &&
      cleanStr(r.glass_side) === side &&
      cleanStr(r.defect_size).toUpperCase() === specGroup
    );

    if (!matched) {
      return {
        specGroup,
        OOC: null,
        OOS: null,
        found: false,
      };
    }

    const ooc = Number(matched.OOC);
    const oos = Number(matched.OOS);

    return {
      specGroup,
      OOC: Number.isFinite(ooc) ? ooc : null,
      OOS: Number.isFinite(oos) ? oos : null,
      found: true,
    };
  }

  function makeSpecLineData(groupRows, value, label) {
    if (!Number.isFinite(value)) return [];

    return (groupRows || []).map(() => ({
      value,
      __isSpec: true,
      __specLabel: label,
      __specValue: value,
    }));
  }

  function pushSpecLineSeries(series, group, gi, specInfo) {
    if (!group || !Array.isArray(group.rows) || !group.rows.length) return;
  
    const hasOOC = Number.isFinite(specInfo?.OOC);
    const hasOOS = Number.isFinite(specInfo?.OOS);
  
    if (!hasOOC && !hasOOS) return;
  
    const markLineData = [];
  
    if (hasOOC) {
      markLineData.push({
        name: "OOC",
        yAxis: specInfo.OOC,
        label: {
          formatter: `OOC ${specInfo.OOC}`,
          color: SPEC_COLORS.OOC,
        },
        lineStyle: {
          color: SPEC_COLORS.OOC,
          type: "dashed",
          width: 2,
        },
      });
    }
  
    if (hasOOS) {
      markLineData.push({
        name: "OOS",
        yAxis: specInfo.OOS,
        label: {
          formatter: `OOS ${specInfo.OOS}`,
          color: SPEC_COLORS.OOS,
        },
        lineStyle: {
          color: SPEC_COLORS.OOS,
          type: "dashed",
          width: 2.2,
        },
      });
    }
  
    series.push({
      name: SPEC_LEGEND_NAME,
      type: "line",
      xAxisIndex: gi,
      yAxisIndex: gi * 2 + 1,
  
      // 用一筆透明 dummy data 讓 legend 可以控制這個 series。
      data: group.rows.map(() => null),
  
      symbol: "none",
      showSymbol: false,
      silent: true,
      tooltip: {
        show: false,
      },
      emphasis: {
        disabled: true,
      },
  
      lineStyle: {
        opacity: 0,
      },
  
      markLine: {
        silent: true,
        symbol: "none",
        animation: false,
        label: {
          show: true,
          position: "insideEndTop",
          fontSize: 10,
        },
        data: markLineData,
      },
  
      z: 20,
    });
  }

  // ============================================================
  // Data grouping
  // ============================================================
  function buildGroups(rows) {
    const map = new Map();

    rows.forEach(row => {
      const key = groupKey(row);

      if (!map.has(key)) {
        map.set(key, {
          key,
          title: groupTitle(row),
          rows: [],
        });
      }

      map.get(key).rows.push(row);
    });

    const groups = Array.from(map.values());

    groups.forEach(g => {
      g.rows.sort((a, b) => {
        const ta = hourTime(a.scan_hour);
        const tb = hourTime(b.scan_hour);
        if (ta !== tb) return ta - tb;

        const ga = safeStr(a.glass_id);
        const gb = safeStr(b.glass_id);
        if (ga !== gb) return ga.localeCompare(gb);

        const apiA = safeStr(a.api_recipe_id);
        const apiB = safeStr(b.api_recipe_id);
        if (apiA !== apiB) return apiA.localeCompare(apiB);

        return safeStr(a.api_scan_time).localeCompare(safeStr(b.api_scan_time));
      });
    });

    groups.sort((a, b) => a.title.localeCompare(b.title));

    return groups;
  }

  function calcMax(rows, cols) {
    let m = 0;

    rows.forEach(r => {
      cols.forEach(c => {
        m = Math.max(m, num(r[c]));
      });
    });

    if (m <= 0) return 1;

    return Math.ceil(m * 1.15);
  }

  function calcGridLayout(groupCount) {
    const topBase = 75;
    const gridGap = 72;
    const gridHeight = 205;
    const bottom = 58;

    const grids = [];
    const titles = [];
    const xAxes = [];
    const yAxes = [];

    for (let i = 0; i < groupCount; i++) {
      const top = topBase + i * (gridHeight + gridGap);

      grids.push({
        left: 92,
        right: 92,
        top,
        height: gridHeight,
        containLabel: true,
      });

      titles.push({
        text: "",
        left: 12,
        top: top - 48,
        textStyle: {
          color: "#ffffff",
          fontSize: 13,
          fontWeight: 600,
        },
      });

      xAxes.push({
        type: "category",
        gridIndex: i,
        data: [],
        triggerEvent: true,
        axisLabel: {
          rotate: 30,
          fontSize: 10,
          margin: 14,
          color: "#ffffff",
        },
        axisLine: {
          lineStyle: {
            color: "rgba(255,255,255,.55)",
          },
        },
        axisTick: {
          alignWithLabel: true,
          lineStyle: {
            color: "rgba(255,255,255,.55)",
          },
        },
      });

      // 左 Y：BPI/API defect count
      yAxes.push({
        type: "value",
        gridIndex: i,
        name: "defect",
        position: "left",
        min: 0,
        max: null,
        nameTextStyle: {
          color: "#ffffff",
        },
        axisLabel: {
          color: "#ffffff",
        },
        axisLine: {
          lineStyle: {
            color: "rgba(255,255,255,.55)",
          },
        },
        axisTick: {
          lineStyle: {
            color: "rgba(255,255,255,.55)",
          },
        },
        splitLine: {
          lineStyle: {
            type: "dashed",
            color: "rgba(255,255,255,.14)",
          },
        },
      });

      // 右 Y：同點數 / OOC / OOS
      yAxes.push({
        type: "value",
        gridIndex: i,
        name: "同點",
        position: "right",
        min: 0,
        max: null,
        nameTextStyle: {
          color: "#ffffff",
        },
        axisLabel: {
          color: "#ffffff",
        },
        axisLine: {
          lineStyle: {
            color: "rgba(255,255,255,.55)",
          },
        },
        axisTick: {
          lineStyle: {
            color: "rgba(255,255,255,.55)",
          },
        },
        splitLine: {
          show: false,
        },
      });
    }

    const totalHeight = topBase + groupCount * (gridHeight + gridGap) + bottom;

    return {
      topBase,
      gridGap,
      gridHeight,
      bottom,
      grids,
      titles,
      xAxes,
      yAxes,
      totalHeight,
    };
  }

  function buildTooltip(dataByGlobalIndex) {
    return function formatter(params) {
      const list = Array.isArray(params) ? params : [params];

      const p =
        list.find(x => x?.data && x.data.__globalIndex != null) ||
        list[0] ||
        {};

      const r = dataByGlobalIndex[p.data?.__globalIndex ?? p.dataIndex];

      if (!r) return "";

      const specGroup = selectedAtomsToSpecGroup(getSelectedDefectSizes());

      return [
        `<b>${safeStr(r.glass_id)}</b>`,
        `Hourly: ${safeStr(r.scan_hour)}`,
        `Tab: ${safeStr(r.tab)}`,
        `Model: ${safeStr(r.model)}`,
        `Side: ${safeStr(r.glass_side)}`,
        `Spec size group: ${specGroup}`,
        `BPI: ${safeStr(r.bpi_aoi)} / ${safeStr(r.bpi_recipe_id)} / defect=${safeStr(r.bpi_defect_count)}`,
        `API: ${safeStr(r.api_aoi)} / ${safeStr(r.api_recipe_id)} / defect=${safeStr(r.api_defect_count)}`,
        `Offset: ${safeStr(r.offset_um)}um`,
        `同點數: ${safeStr(r.matched_pair_count)}`,
        `BPI同點 S/M/L/O: ${safeStr(r.matched_bpi_s_count)} / ${safeStr(r.matched_bpi_m_count)} / ${safeStr(r.matched_bpi_l_count)} / ${safeStr(r.matched_bpi_o_count)}`,
        `API同點 S/M/L/O: ${safeStr(r.matched_api_s_count)} / ${safeStr(r.matched_api_m_count)} / ${safeStr(r.matched_api_l_count)} / ${safeStr(r.matched_api_o_count)}`,
      ].join("<br>");
    };
  }

  function makeXAxisZoom(layout) {
    return [
      {
        type: "inside",
        xAxisIndex: layout.xAxes.map((_, i) => i),
        filterMode: "none",
      },
      {
        type: "slider",
        xAxisIndex: layout.xAxes.map((_, i) => i),
        bottom: 18,
        height: 18,
        brushSelect: false,
        filterMode: "none",
        textStyle: {
          color: "#ffffff",
        },
      },
    ];
  }

  function makeYAxisZooms(layout, groupCount) {
    const dataZoom = [];

    for (let gi = 0; gi < groupCount; gi++) {
      const grid = layout.grids[gi];

      const leftSliderLeft = Math.max(4, grid.left - 30);
      const rightSliderRight = Math.max(4, grid.right - 30);

      const sliderTop = grid.top + 2;
      const sliderHeight = 120;

      dataZoom.push({
        type: "slider",
        yAxisIndex: gi * 2,
        orient: "vertical",
        filterMode: "none",
        left: leftSliderLeft,
        top: sliderTop,
        height: sliderHeight,
        width: 14,
        showDetail: false,
        showDataShadow: false,
        brushSelect: false,
        realtime: true,
        borderColor: "rgba(255,255,255,.35)",
        fillerColor: "rgba(100,160,255,.25)",
        handleSize: "80%",
        textStyle: {
          color: "#ffffff",
        },
      });

      dataZoom.push({
        type: "slider",
        yAxisIndex: gi * 2 + 1,
        orient: "vertical",
        filterMode: "none",
        right: rightSliderRight,
        top: sliderTop,
        height: sliderHeight,
        width: 14,
        showDetail: false,
        showDataShadow: false,
        brushSelect: false,
        realtime: true,
        borderColor: "rgba(255,255,255,.35)",
        fillerColor: "rgba(100,160,255,.25)",
        handleSize: "80%",
        textStyle: {
          color: "#ffffff",
        },
      });

      dataZoom.push({
        type: "inside",
        yAxisIndex: gi * 2,
        filterMode: "none",
        zoomOnMouseWheel: true,
        moveOnMouseMove: false,
        moveOnMouseWheel: false,
      });

      dataZoom.push({
        type: "inside",
        yAxisIndex: gi * 2 + 1,
        filterMode: "none",
        zoomOnMouseWheel: true,
        moveOnMouseMove: false,
        moveOnMouseWheel: false,
      });
    }

    return dataZoom;
  }

  function getRowFromZrPoint(inst, groups, point) {
    if (!inst || !Array.isArray(groups) || !point) return null;

    for (let gi = 0; gi < groups.length; gi++) {
      const inGrid = inst.containPixel({ gridIndex: gi }, point);
      if (!inGrid) continue;

      let idx = null;

      try {
        const converted = inst.convertFromPixel({ xAxisIndex: gi }, point);

        if (Array.isArray(converted)) {
          idx = Math.round(Number(converted[0]));
        } else {
          idx = Math.round(Number(converted));
        }
      } catch (_) {
        idx = null;
      }

      if (!Number.isFinite(idx)) return null;

      const rows = groups[gi]?.rows || [];
      if (!rows.length) return null;

      if (idx < 0) idx = 0;
      if (idx >= rows.length) idx = rows.length - 1;

      return rows[idx] || null;
    }

    return null;
  }

  function bindWideClick(inst, groups) {
    if (!inst || !inst.getZr) return;

    const zr = inst.getZr();

    if (state.samePointZrClickHandler) {
      try {
        zr.off("click", state.samePointZrClickHandler);
      } catch (_) {}
    }

    if (state.samePointUpdateAxisPointerHandler) {
      try {
        inst.off("updateAxisPointer", state.samePointUpdateAxisPointerHandler);
      } catch (_) {}
    }

    state.samePointHoverTarget = null;

    state.samePointUpdateAxisPointerHandler = function (ev) {
      const axesInfo = ev?.axesInfo || [];

      if (!axesInfo.length) {
        state.samePointHoverTarget = null;
        return;
      }

      const info = axesInfo.find(x => x && x.axisDim === "x");

      if (!info) {
        state.samePointHoverTarget = null;
        return;
      }

      const xAxisIndex = Number(info.axisIndex);
      const dataIndex = Number(info.value);

      if (!Number.isFinite(xAxisIndex) || !Number.isFinite(dataIndex)) {
        state.samePointHoverTarget = null;
        return;
      }

      const rows = groups[xAxisIndex]?.rows || [];
      const row = rows[dataIndex];

      if (!row) {
        state.samePointHoverTarget = null;
        return;
      }

      state.samePointHoverTarget = {
        gridIndex: xAxisIndex,
        dataIndex,
        row,
      };
    };

    inst.on("updateAxisPointer", state.samePointUpdateAxisPointerHandler);

    state.samePointZrClickHandler = async function (ev) {
      const point = [ev.offsetX, ev.offsetY];

      let inAnyGrid = false;

      for (let gi = 0; gi < groups.length; gi++) {
        if (inst.containPixel({ gridIndex: gi }, point)) {
          inAnyGrid = true;
          break;
        }
      }

      if (!inAnyGrid) return;

      const hoverRow = state.samePointHoverTarget?.row;
      if (hoverRow) {
        await MOD.selectRow?.(hoverRow);
        return;
      }

      const row = getRowFromZrPoint(inst, groups, point);
      if (!row) return;

      await MOD.selectRow?.(row);
    };

    zr.on("click", state.samePointZrClickHandler);
  }

  Chart.render = function (rows) {
    const host = $("bpi-same-point-facet");
    if (!host || !window.echarts) return;

    const data = Array.isArray(rows) ? rows : [];

    if (state.chart) {
      try {
        if (state.samePointZrClickHandler && state.chart.getZr) {
          state.chart.getZr().off("click", state.samePointZrClickHandler);
        }
      } catch (_) {}

      try {
        if (state.samePointUpdateAxisPointerHandler) {
          state.chart.off("updateAxisPointer", state.samePointUpdateAxisPointerHandler);
        }
      } catch (_) {}

      try {
        state.chart.dispose();
      } catch (_) {}

      state.chart = null;
      state.samePointZrClickHandler = null;
      state.samePointUpdateAxisPointerHandler = null;
      state.samePointHoverTarget = null;
    }

    host.innerHTML = "";

    if (!data.length) {
      host.innerHTML = "<div class='muted' style='padding:16px;'>沒有資料</div>";
      return;
    }

    const groups = buildGroups(data);
    const layout = calcGridLayout(groups.length);

    host.style.height = `${Math.max(380, layout.totalHeight)}px`;

    const inst = echarts.init(host);
    state.chart = inst;

    const dataByGlobalIndex = [];
    const series = [];
    let hasAnySpecLine = false;

    groups.forEach((group, gi) => {
      layout.titles[gi].text = group.title;

      const xData = group.rows.map(r => xLabel(r));
      layout.xAxes[gi].data = xData;

      const specInfo = findSpecForGroup(group);

      console.log("[BPI_SAME_POINT][spec match]", {
        group: group.title,
        model: group.rows?.[0]?.model,
        glass_side: group.rows?.[0]?.glass_side,
        selectedSizes: getSelectedDefectSizes(),
        specInfo,
        specRowsCount: getSamePointSpecRows().length,
      });

      const defectMax = calcMax(group.rows, [
        "bpi_defect_count",
        "api_defect_count",
      ]);

      let sameMax = calcMax(group.rows, [
        "matched_pair_count",
      ]);

      if (Number.isFinite(specInfo.OOC)) {
        sameMax = Math.max(sameMax, Math.ceil(specInfo.OOC * 1.15));
        hasAnySpecLine = true;
      }

      if (Number.isFinite(specInfo.OOS)) {
        sameMax = Math.max(sameMax, Math.ceil(specInfo.OOS * 1.15));
        hasAnySpecLine = true;
      }

      layout.yAxes[gi * 2].max = defectMax;
      layout.yAxes[gi * 2 + 1].max = sameMax;

      const bpiData = group.rows.map(r => {
        const globalIndex = dataByGlobalIndex.push(r) - 1;

        return {
          value: num(r.bpi_defect_count),
          __globalIndex: globalIndex,
        };
      });

      const apiData = group.rows.map(r => {
        const globalIndex = dataByGlobalIndex.push(r) - 1;

        return {
          value: num(r.api_defect_count),
          __globalIndex: globalIndex,
        };
      });

      const samePointData = group.rows.map(r => {
        const globalIndex = dataByGlobalIndex.push(r) - 1;

        return {
          value: num(r.matched_pair_count),
          __globalIndex: globalIndex,
        };
      });

      series.push({
        name: "BPI defect",
        type: "bar",
        xAxisIndex: gi,
        yAxisIndex: gi * 2,
        data: bpiData,
        barMaxWidth: 16,
        emphasis: {
          focus: "series",
        },
      });

      series.push({
        name: "API defect",
        type: "bar",
        xAxisIndex: gi,
        yAxisIndex: gi * 2,
        data: apiData,
        barMaxWidth: 16,
        emphasis: {
          focus: "series",
        },
      });

      series.push({
        name: "同點數",
        type: "scatter",
        xAxisIndex: gi,
        yAxisIndex: gi * 2 + 1,
        symbolSize: 8,
        itemStyle: {
          color: "#F75000",
        },
        data: samePointData,
        z: 10,
        emphasis: {
          focus: "series",
        },
      });

      pushSpecLineSeries(series, group, gi, specInfo);
    });

    const legendData = ["BPI defect", "API defect", "同點數"];

    if (hasAnySpecLine) {
      legendData.push(SPEC_LEGEND_NAME);
    }

    const option = {
      animation: true,

      title: layout.titles,

      legend: {
        top: 0,
        right: 10,
        data: legendData,
        textStyle: {
          color: "#ffffff",
        },
      },

      tooltip: {
        trigger: "axis",
        axisPointer: {
          type: "shadow",
        },
        renderMode: "html",
        extraCssText: "max-width:560px; white-space:normal;",
        formatter: buildTooltip(dataByGlobalIndex),
      },

      grid: layout.grids,
      xAxis: layout.xAxes,
      yAxis: layout.yAxes,

      dataZoom: [
        ...makeXAxisZoom(layout),
        ...makeYAxisZooms(layout, groups.length),
      ],

      series,
    };

    console.log("[BPI_SAME_POINT.Chart] render", {
      rows: data.length,
      groups: groups.length,
      specRows: getSamePointSpecRows().length,
      hasAnySpecLine,
      legendData,
      seriesCount: series.length,
    });

    inst.setOption(option, true);

    inst.off("click");
    inst.on("click", async ev => {
      const globalIndex = ev?.data?.__globalIndex;

      if (
        globalIndex == null ||
        globalIndex < 0 ||
        globalIndex >= dataByGlobalIndex.length
      ) {
        return;
      }

      await MOD.selectRow?.(dataByGlobalIndex[globalIndex]);
    });

    bindWideClick(inst, groups);

    if (state.chartResizeHandler) {
      window.removeEventListener("resize", state.chartResizeHandler);
    }

    state.chartResizeHandler = () => {
      try {
        inst.resize();
      } catch (_) {}
    };

    window.addEventListener("resize", state.chartResizeHandler);
  };
})();