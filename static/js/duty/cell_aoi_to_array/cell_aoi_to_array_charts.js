
// static/js/duty/cell_aoi_to_array/cell_aoi_to_array_charts.js
(function () {
  "use strict";

  window.CELL_AOI_TO_ARRAY = window.CELL_AOI_TO_ARRAY || {};
  const MOD = window.CELL_AOI_TO_ARRAY;

  MOD.Charts = {
    init,
    renderSkeleton,
    render,
    resize,
    destroy
  };

  function init() {
    window.addEventListener(
      "resize",
      MOD.UI.debounce(function () {
        resize();

        if (MOD.State.state.selectedRow && MOD.Map && MOD.Map.redraw) {
          MOD.Map.redraw();
        }
      }, 120)
    );
  }

  function renderSkeleton() {
    const { dom } = MOD.State;
    const chartList = MOD.State.getChartList();
  
    if (!dom.chartGrid) return;
  
    applyChartGridLayout();
  
    dom.chartGrid.innerHTML = "";
    destroy();
  
    chartList.forEach(function (chart) {
      const box = document.createElement("div");
      box.className = "cell-aoi-to-array-chart-box";

      const head = document.createElement("div");
      head.className = "cell-aoi-to-array-chart-box-head";

      const titleWrap = document.createElement("div");

      const title = document.createElement("div");
      title.className = "cell-aoi-to-array-chart-box-title";
      title.textContent = chart.title || chart.key;
      titleWrap.appendChild(title);

      if (chart.sub) {
        const sub = document.createElement("div");
        sub.className = "cell-aoi-to-array-chart-box-sub";
        sub.textContent = chart.sub;
        titleWrap.appendChild(sub);
      }

      head.appendChild(titleWrap);

      const canvas = document.createElement("div");
      canvas.className = "cell-aoi-to-array-chart-canvas";
      canvas.id = `cell-aoi-to-array-chart-${chart.key}`;

      box.appendChild(head);
      box.appendChild(canvas);

      dom.chartGrid.appendChild(box);
    });
  }

  function applyChartGridLayout() {
    const { dom, state } = MOD.State;

    if (!dom.chartGrid) return;

    const currentFeature = state.feature || "";

    dom.chartGrid.classList.toggle(
      "is-inspection-chart-grid",
      currentFeature === "inspection-sampling-compare"
    );
  }
  
  function render(chartData) {
    if (!window.echarts) {
      renderFallback();
      return;
    }

    const chartList = MOD.State.getChartList();
    const { state } = MOD.State;

    chartList.forEach(function (chartConfig) {
      const el = document.getElementById(`cell-aoi-to-array-chart-${chartConfig.key}`);
      if (!el) return;

      let chart = state.charts[chartConfig.key];

      if (!chart) {
        chart = window.echarts.init(el);
        state.charts[chartConfig.key] = chart;
      }

      const data = chartData?.[chartConfig.key] || {
        xMin: null,
        xMax: null,
        xDayStartMs: [],
        series: []
      };

      const dayStartSet = buildDayStartSet(data.xDayStartMs);

      const rawSeries = Array.isArray(data.series) ? data.series : [];
      const yWindow = buildYAxisWindow(rawSeries);

      const series = rawSeries.map(function (item) {
        return {
          name: item.name || "-",
          type: "line",
          smooth: false,
          symbol: "circle",
          symbolSize: 7,
          showSymbol: true,
          connectNulls: false,
          data: Array.isArray(item.data) ? item.data : []
        };
      });

      chart.setOption({
        backgroundColor: "transparent",

        legend: {
          type: "scroll",
          orient: "vertical",
          right: 6,
          top: 46,
          bottom: 88,
          textStyle: { color: "#cfd7df" },
          pageTextStyle: { color: "#cfd7df" }
        },

        grid: {
          left: 58,
          right: 162,
          top: 56,
          bottom: 126
        },

        tooltip: {
          trigger: "item",
          confine: true,
          formatter: function (params) {
            return formatTooltip(params, chartConfig);
          }
        },

        dataZoom: [
          {
            type: "slider",
            xAxisIndex: 0,
            bottom: 38,
            height: 24,
            start: 0,
            end: 100,
            textStyle: { color: "#9aa3ad" },
            borderColor: "#333a46",
            fillerColor: "rgba(92,193,255,.18)",
            handleStyle: { color: "#5cc1ff" }
          },
          {
            type: "inside",
            xAxisIndex: 0,
            start: 0,
            end: 100
          },
          {
            type: "slider",
            yAxisIndex: 0,
            right: 116,
            top: 62,
            bottom: 126,
            width: 18,
            startValue: yWindow.min,
            endValue: yWindow.max,
            textStyle: { color: "#9aa3ad" },
            borderColor: "#333a46",
            fillerColor: "rgba(255,213,107,.16)",
            handleStyle: { color: "#ffd56b" },
            labelFormatter: function (value) {
              return formatYAxisPercentLabel(value);
            }
          },
          {
            type: "inside",
            yAxisIndex: 0,
            startValue: yWindow.min,
            endValue: yWindow.max
          }
        ],

        xAxis: {
          type: "time",
          min: data.xMin || null,
          max: data.xMax || null,
          minInterval: 3600 * 1000,
          axisLabel: {
            color: "#9aa3ad",
            hideOverlap: false,
            margin: 18,
            formatter: function (value) {
              return formatTimeAxisLabel(value, dayStartSet);
            }
          },
          axisTick: { alignWithLabel: true },
          axisLine: { lineStyle: { color: "#333a46" } }
        },

        yAxis: {
          type: "value",
          min: 0,
          max: 100,
          splitNumber: yWindow.splitNumber,
          name: "比對率",
          nameTextStyle: { color: "#cfd7df" },
          axisLabel: {
            color: "#9aa3ad",
            showMinLabel: true,
            showMaxLabel: true,
            formatter: function (value) {
              return formatYAxisPercentLabel(value);
            }
          },
          splitLine: { lineStyle: { color: "#262a33" } }
        },

        series
      }, true);

      chart.off("click");
      chart.on("click", function (params) {
        handleChartClick(chartConfig, params);
      });
    });

    resize();
  }

  function buildDayStartSet(values) {
    const set = new Set();

    (values || []).forEach(function (v) {
      const n = Number(v);
      if (!Number.isFinite(n)) return;
      set.add(floorHourMs(n));
    });

    return set;
  }

  function floorHourMs(ms) {
    const d = new Date(Number(ms));
    d.setMinutes(0, 0, 0);
    return d.getTime();
  }

  function formatTimeAxisLabel(value, dayStartSet) {
    const ms = Number(value);
    if (!Number.isFinite(ms)) return "";

    const d = new Date(ms);
    const hourMs = floorHourMs(ms);

    const hh = String(d.getHours()).padStart(2, "0");
    const hourText = `${hh}:00`;

    if (dayStartSet.has(hourMs)) {
      const m = String(d.getMonth() + 1).padStart(2, "0");
      const day = String(d.getDate()).padStart(2, "0");
      return `${hourText}\n${m}-${day}`;
    }

    return `${hourText}\n`;
  }

  function formatTooltip(params, chartConfig) {
    const data = params?.data || {};
    const value = getDataValue(data, params?.value);
    const rateText = Number.isFinite(Number(value))
      ? `${Number(value).toFixed(2)}%`
      : "-";

    const lines = [];

    lines.push(`<b>${escapeHtml(chartConfig.title || "")}</b>`);
    lines.push(`${params.marker || ""}${escapeHtml(params.seriesName || "-")}: ${rateText}`);
    lines.push(`CELL時間: ${escapeHtml(data.__test_time || formatMsTime(params.value?.[0]) || "-")}`);
    lines.push(`SheetID: ${escapeHtml(data.__sheet_id_chip_id || "-")}`);
    lines.push(`CELL PI: ${escapeHtml(data.__pi_type || "-")}`);
    lines.push(`ABBR: ${escapeHtml(data.__abbr_cat || "-")}`);
    lines.push(`站點: ${escapeHtml(data.__source_op_id || "-")}`);
    lines.push(`Line: ${escapeHtml(data.__line_id || "-")}`);
    lines.push(`CELL AOI: ${escapeHtml(data.__aoi || "-")}`);
    lines.push(`同點點數: ${escapeHtml(data.__same_point_defect_cnt ?? "-")}`);
    lines.push(`CELL點數: ${escapeHtml(data.__total_defect_qty ?? "-")}`);
    lines.push(`狀態: ${escapeHtml(data.__match_status || "-")}`);

    return lines.join("<br/>");
  }

  function getDataValue(data, fallback) {
    if (
      data &&
      typeof data === "object" &&
      Array.isArray(data.value) &&
      data.value.length >= 2
    ) {
      return data.value[1];
    }

    if (
      data &&
      typeof data === "object" &&
      Object.prototype.hasOwnProperty.call(data, "value")
    ) {
      return data.value;
    }

    if (Array.isArray(fallback) && fallback.length >= 2) {
      return fallback[1];
    }

    return fallback;
  }

  function formatMsTime(ms) {
    const n = Number(ms);
    if (!Number.isFinite(n)) return "";

    const d = new Date(n);

    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    const ss = String(d.getSeconds()).padStart(2, "0");

    return `${y}-${m}-${day} ${hh}:${mm}:${ss}`;
  }

  function buildYAxisWindow(rawSeries) {
    const values = [];

    (rawSeries || []).forEach(function (series) {
      const data = Array.isArray(series.data) ? series.data : [];

      data.forEach(function (point) {
        const y = extractYValue(point);

        if (Number.isFinite(y)) {
          values.push(y);
        }
      });
    });

    if (!values.length) {
      return { min: 0, max: 100, splitNumber: 5 };
    }

    const dataMin = Math.min.apply(null, values);
    const dataMax = Math.max.apply(null, values);

    let yMin = Math.floor(dataMin);
    let yMax = Math.ceil(dataMax * 1.25);

    yMin = Math.max(0, yMin);
    yMax = Math.max(10, yMax);
    yMax = Math.min(100, yMax);

    if (yMax <= yMin) {
      yMax = Math.min(100, yMin + 1);
    }

    return {
      min: yMin,
      max: yMax,
      splitNumber: calcYAxisSplitNumber(yMin, yMax)
    };
  }

  function extractYValue(point) {
    if (
      point &&
      typeof point === "object" &&
      Array.isArray(point.value) &&
      point.value.length >= 2
    ) {
      const y = Number(point.value[1]);
      return Number.isFinite(y) ? y : NaN;
    }

    if (Array.isArray(point) && point.length >= 2) {
      const y = Number(point[1]);
      return Number.isFinite(y) ? y : NaN;
    }

    const y = Number(point);
    return Number.isFinite(y) ? y : NaN;
  }

  function calcYAxisSplitNumber(min, max) {
    const span = Number(max) - Number(min);

    if (!Number.isFinite(span) || span <= 0) return 5;
    if (min === 0 && max <= 10) return 5;
    if (span <= 5) return 5;

    return 5;
  }

  function formatYAxisPercentLabel(value) {
    const n = Number(value);

    if (!Number.isFinite(n)) return "";

    if (Math.abs(n - Math.round(n)) < 0.0001) {
      return `${Math.round(n)}%`;
    }

    return `${Number(n.toFixed(1))}%`;
  }

  function handleChartClick(chartConfig, params) {
    const data = params?.data || {};
    const rowKey = data.__row_key || "";

    if (!rowKey) {
      MOD.Table.setModeText(`Chart: ${chartConfig.title || ""}`);
      return;
    }

    const { state } = MOD.State;

    state.tableMode = "chart";
    state.tableRows = state.rows.filter(function (row) {
      return MOD.State.getRowKey(row) === rowKey || row.row_key === rowKey;
    });

    state.page = 1;
    state.selectedRow = state.tableRows[0] || null;

    MOD.Table.render();

    if (MOD.Sheet && typeof MOD.Sheet.renderEmpty === "function") {
      MOD.Sheet.renderEmpty();
    } else {
      console.warn("[cell-aoi-to-array-charts] MOD.Sheet.renderEmpty not ready:", MOD.Sheet);
    }

    MOD.Table.setModeText(
      `Chart: ${chartConfig.title || ""} / ${data.__test_time || ""}`
    );
  }

  function renderFallback() {
    const { dom } = MOD.State;

    if (!dom.chartGrid) return;

    dom.chartGrid
      .querySelectorAll(".cell-aoi-to-array-chart-canvas")
      .forEach(function (el) {
        el.innerHTML = "";

        el.appendChild(
          MOD.UI.createEmptyState("⌁", "echarts 尚未載入")
        );
      });
  }

  function resize() {
    const charts = MOD.State.state.charts || {};

    Object.keys(charts).forEach(function (key) {
      try {
        charts[key].resize();
      } catch (err) {
        // ignore
      }
    });
  }

  function destroy() {
    const charts = MOD.State.state.charts || {};

    Object.keys(charts).forEach(function (key) {
      try {
        charts[key].dispose();
      } catch (err) {
        // ignore
      }
    });

    MOD.State.state.charts = {};
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }
})();