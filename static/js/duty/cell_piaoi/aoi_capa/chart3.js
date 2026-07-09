// static/js/aoi_capa/chart3.js
(function () {
  const AOI = (window.AOI_CAPA = window.AOI_CAPA || {});
  AOI.Chart = AOI.Chart || {};

  const $ = (sel, root = document) => root.querySelector(sel);

  let chart = null;

  const PI_COLORS = {
    API: "#7373B9",
    BPI: "#DAB1D5",
    ITO: "#6C3365",
    OTHER: "#6FA8DC",
  };

  const SCATTER_COLOR = "#FF4136";

  const CHART_THEME = {
    axisLabel: "#aeb6c7",
    axisLine: "#2b3240",
    axisTick: "#3a4354",
    splitLine: "rgba(255,255,255,0.09)",
  };

  function getCurrentSubTab() {
    return AOI.state?.currentSubTab || "Day_Hourly";
  }

  function ensureChartInstance() {
    const dom = $("#aoi-capa-facet");
    if (!dom) return null;

    const style = window.getComputedStyle(dom);
    const h = parseFloat(style.height || "0");
    if (!h) dom.style.height = "360px";

    if (!chart) {
      chart = echarts.init(dom);
      window.addEventListener("resize", () => {
        if (chart) chart.resize();
      });
    }
    return chart;
  }

  function getFilteredSummaryRows() {
    const rows = AOI.state?.rows || [];
    if (!rows.length) return [];
  
    // 任一下拉選單完全沒勾選 → chart 不顯示資料
    if (typeof AOI.hasEmptyFilterSelection === "function" && AOI.hasEmptyFilterSelection()) {
      return [];
    }
  
    const filters =
      typeof AOI.readFiltersFromUI === "function"
        ? AOI.readFiltersFromUI()
        : {};
  
    const aoiSel = filters.aoi || null;
  
    return rows.filter((r) => {
      const aoi = (r.aoi || "").toString();
      if (aoiSel && aoiSel.length && !aoiSel.includes(aoi)) return false;
      return true;
    });
  }

  function buildAoiDayMap(rows) {
    const byAoi = {};
    const piTypeSetByAoi = {};
    const allDays = new Set();

    rows.forEach((r) => {
      const aoi = String(r.aoi || "");
      const day = String(r.run_day || "");
      const pt = String(r.pi_type || "").toUpperCase();

      if (!aoi || !day || !pt) return;

      allDays.add(day);

      if (!byAoi[aoi]) byAoi[aoi] = {};
      if (!byAoi[aoi][day]) byAoi[aoi][day] = { rowsByPi: {}, target: null };

      byAoi[aoi][day].rowsByPi[pt] = r;

      const t = Number(r.target_count);
      if (Number.isFinite(t)) byAoi[aoi][day].target = t;

      if (pt !== "ALL") {
        if (!piTypeSetByAoi[aoi]) piTypeSetByAoi[aoi] = new Set();
        piTypeSetByAoi[aoi].add(pt);
      }
    });

    return {
      byAoi,
      piTypeSetByAoi,
      days: Array.from(allDays).sort(),
    };
  }

  function aggregateDayForAoi(dayInfo, piFilterArr, fullSetArr) {
    const rowsByPi = dayInfo.rowsByPi || {};
    const target = Number(dayInfo.target ?? null);

    const map = {};
    Object.keys(rowsByPi).forEach((k) => {
      map[k.toUpperCase()] = rowsByPi[k];
    });

    const hasALL = !!map.ALL;
    const fullSet = (fullSetArr || []).map((v) => String(v).toUpperCase());

    let selected = [];
    if (Array.isArray(piFilterArr) && piFilterArr.length) {
      const upper = piFilterArr.map((v) => String(v).toUpperCase());
      selected = fullSet.filter((pt) => upper.includes(pt));
    } else {
      selected = fullSet.slice();
    }

    const isFull = selected.length === fullSet.length && fullSet.length > 0;

    let total_glass = 0;
    let capa = null;
    let usedPi = [];

    if (isFull && hasALL) {
      const rowAll = map.ALL;
      total_glass = Number(rowAll.total_glass ?? 0) || 0;
      const v = Number(rowAll.real_day_capa);
      capa = Number.isFinite(v) ? v : null;
      usedPi = ["ALL"];
    } else if (selected.length === 1) {
      const key = selected[0];
      const row = map[key];
      if (row) {
        total_glass = Number(row.total_glass ?? 0) || 0;
        const v = Number(row.real_day_capa);
        capa = Number.isFinite(v) ? v : null;
        usedPi = [key];
      }
    } else if (selected.length > 1) {
      total_glass = selected.reduce((acc, pt) => {
        const row = map[pt];
        return acc + (Number(row?.total_glass ?? 0) || 0);
      }, 0);
      capa = Number.isFinite(target) && target > 0 ? total_glass / target : null;
      usedPi = selected.slice();
    } else {
      if (hasALL) {
        const rowAll = map.ALL;
        total_glass = Number(rowAll.total_glass ?? 0) || 0;
        const v = Number(rowAll.real_day_capa);
        capa = Number.isFinite(v) ? v : null;
        usedPi = ["ALL"];
      }
    }

    return {
      total_glass,
      capa,
      usedPi,
      target: Number.isFinite(target) ? target : null,
    };
  }

  AOI.Chart.update = function () {
    const subTab = getCurrentSubTab();
    const inst = ensureChartInstance();
    if (!inst) return;

    if (subTab !== "Day_Hourly") {
      inst.clear();
      return;
    }

    const data = getFilteredSummaryRows();
    if (!data.length) {
      inst.clear();
      return;
    }

    const { byAoi, piTypeSetByAoi, days } = buildAoiDayMap(data);
    const aoiList = Object.keys(byAoi).sort();
    if (!aoiList.length || !days.length) {
      inst.clear();
      return;
    }

    const uiFilters =
      typeof AOI.readFiltersFromUI === "function"
        ? AOI.readFiltersFromUI()
        : {};
    const piFilterArr = Array.isArray(uiFilters.pi_type) ? uiFilters.pi_type.slice() : [];
    const piFilterUpper = piFilterArr.map((v) => String(v).toUpperCase());

    const dom = $("#aoi-capa-facet");
    let totalHeight = 360;
    if (dom) {
      const cs = window.getComputedStyle(dom);
      totalHeight = dom.clientHeight || parseFloat(cs.height || "0") || totalHeight;
    }

    const n = aoiList.length;
    const topPadding = 40;
    const bottomPadding = 20;
    const gridGap = 20;
    const usable = Math.max(
      totalHeight - topPadding - bottomPadding - gridGap * (n - 1),
      60 * n
    );
    const gridH = usable / n;

    const grids = [];
    const xAxes = [];
    const yAxes = [];
    const series = [];
    const graphics = [];

    const leftMargin = 80;
    const rightMargin = 40;

    aoiList.forEach((aoi, idx) => {
      const top = topPadding + idx * (gridH + gridGap);
      const gridIndex = idx;
      const xAxisIndex = idx;
      const yLeftIndex = idx * 2;
      const yRightIndex = idx * 2 + 1;

      grids.push({
        left: leftMargin,
        right: rightMargin,
        top,
        height: gridH,
      });

      xAxes.push({
        type: "category",
        gridIndex,
        data: days,
        axisTick: {
          alignWithLabel: true,
          lineStyle: { color: CHART_THEME.axisTick, width: 1 },
        },
        axisLabel: {
          show: idx === aoiList.length - 1,
          margin: 10,
          color: CHART_THEME.axisLabel,
        },
        axisLine: {
          lineStyle: { color: CHART_THEME.axisLine, width: 1 },
        },
      });

      yAxes.push({
        type: "value",
        gridIndex,
        position: "left",
        axisLabel: { color: CHART_THEME.axisLabel },
        axisLine: { lineStyle: { color: CHART_THEME.axisLine, width: 1 } },
        axisTick: { lineStyle: { color: CHART_THEME.axisTick, width: 1 } },
        splitLine: {
          show: true,
          lineStyle: { color: CHART_THEME.splitLine, width: 1, type: "dashed" },
        },
      });

      yAxes.push({
        type: "value",
        gridIndex,
        position: "right",
        axisLabel: {
          color: CHART_THEME.axisLabel,
          formatter: (val) => `${Math.round(val)}%`,
        },
        axisLine: { lineStyle: { color: CHART_THEME.axisLine, width: 1 } },
        axisTick: { lineStyle: { color: CHART_THEME.axisTick, width: 1 } },
        splitLine: { show: false },
      });

      graphics.push({
        type: "text",
        left: 18,
        top: top + gridH / 2,
        rotation: -Math.PI / 2,
        style: {
          text: aoi,
          fill: "#f3bfff",
          fontSize: 12,
          fontWeight: 700,
          textAlign: "center",
        },
      });

      const dayMap = byAoi[aoi] || {};
      const fullSet = Array.from(piTypeSetByAoi[aoi] || []).sort();

      const stackDataByPi = {};
      fullSet.forEach((pi) => {
        stackDataByPi[pi.toUpperCase()] = [];
      });

      const allBarData = [];
      const scatterData = [];
      const specLine = [];
      const spec08Line = [];

      let maxGlass = 0;
      let maxCapaPct = 0;

      days.forEach((day) => {
        const info = dayMap[day];

        if (!info) {
          fullSet.forEach((pi) => stackDataByPi[pi.toUpperCase()].push(0));
          allBarData.push(0);
          scatterData.push(null);
          specLine.push(null);
          spec08Line.push(null);
          return;
        }

        const rowsByPi = info.rowsByPi || {};

        let specVal = null;
        {
          const allRow = rowsByPi.ALL;
          let srcRow = allRow;
          if (!srcRow) {
            const anyKey = Object.keys(rowsByPi)[0];
            if (anyKey) srcRow = rowsByPi[anyKey];
          }
          if (srcRow && srcRow.spec != null) {
            const sv = Number(srcRow.spec);
            if (Number.isFinite(sv)) specVal = sv;
          }
        }

        if (specVal != null) {
          specLine.push(specVal);
          spec08Line.push(specVal * 0.8);
          maxCapaPct = Math.max(maxCapaPct, specVal, specVal * 0.8);
        } else {
          specLine.push(null);
          spec08Line.push(null);
        }

        const perPiGlass = {};
        let sumPi = 0;

        fullSet.forEach((pi) => {
          const key = pi.toUpperCase();
          const row = rowsByPi[key];
          const v = row ? (Number(row.total_glass ?? 0) || 0) : 0;
          const isSelected = !piFilterUpper.length || piFilterUpper.includes(key);
          const valForStack = isSelected ? v : 0;

          stackDataByPi[key].push({
            value: valForStack,
            meta: { aoi, day, pi_type: key },
          });

          perPiGlass[key] = v;
          sumPi += v;
        });

        const allRow = rowsByPi.ALL;
        const allVal = allRow ? (Number(allRow.total_glass ?? 0) || 0) : sumPi;
        allBarData.push({
          value: allVal,
          meta: { aoi, day, pi_type: "ALL" },
        });
        maxGlass = Math.max(maxGlass, allVal);

        const agg = aggregateDayForAoi(info, piFilterArr, fullSet);
        const tg = agg.total_glass || 0;
        const cp = agg.capa;

        let cpPct = null;
        if (cp != null && isFinite(cp)) {
          cpPct = Math.round(cp * 100);
          maxCapaPct = Math.max(maxCapaPct, cpPct);
        }

        scatterData.push(
          cpPct != null
            ? {
                value: cpPct,
                meta: {
                  aoi,
                  day,
                  total_glass: tg,
                  capa: cp,
                  capa_percent: cpPct,
                  target_count: agg.target,
                  selected_pi: agg.usedPi,
                  all_pi: fullSet,
                  per_pi_glass: perPiGlass,
                },
              }
            : null
        );
      });

      yAxes[yLeftIndex].max = maxGlass > 0 ? Math.ceil(maxGlass * 1.2) : 10;
      yAxes[yLeftIndex].min = 0;

      yAxes[yRightIndex].max = maxCapaPct > 0 ? Math.ceil(maxCapaPct * 1.2) : 100;
      yAxes[yRightIndex].min = 0;

      series.push({
        name: "total_glass(ALL)",
        type: "bar",
        xAxisIndex,
        yAxisIndex: yLeftIndex,
        barMaxWidth: 18,
        itemStyle: { color: "#9aa3b2", opacity: 0.8 },
        data: allBarData,
        barGap: "-100%",
      });

      fullSet.forEach((pi) => {
        const key = pi.toUpperCase();
        series.push({
          name: `${key} total_glass`,
          type: "bar",
          xAxisIndex,
          yAxisIndex: yLeftIndex,
          stack: `${aoi}-stack`,
          barMaxWidth: 18,
          itemStyle: {
            color: PI_COLORS[key] || "#cccccc",
          },
          data: stackDataByPi[key] || [],
          barGap: "-100%",
        });
      });

      series.push({
        name: "OOS",
        type: "line",
        xAxisIndex,
        yAxisIndex: yRightIndex,
        symbol: "none",
        step: "middle",
        lineStyle: {
          width: 2,
          type: "dashed",
          opacity: 0.8,
          color: "#82D900",
        },
        data: specLine,
        z: 40,
      });

      series.push({
        name: "OOC",
        type: "line",
        xAxisIndex,
        yAxisIndex: yRightIndex,
        symbol: "none",
        step: "middle",
        lineStyle: {
          width: 2,
          type: "dashed",
          opacity: 0.8,
          color: "#0000E3",
        },
        data: spec08Line,
        z: 39,
      });

      series.push({
        name: "Capa",
        type: "scatter",
        xAxisIndex,
        yAxisIndex: yRightIndex,
        symbolSize: 8,
        itemStyle: { color: SCATTER_COLOR },
        label: {
          show: true,
          position: "top",
          formatter: (p) => {
            const m = p.data && p.data.meta;
            if (!m || m.capa_percent == null) return "";
            return `${m.capa_percent}%`;
          },
          color: "#ffffff",
        },
        data: scatterData,
        connectNulls: false,
        z: 50,
      });
    });

    inst.setOption(
      {
        animation: true,
        grid: grids,
        xAxis: xAxes,
        yAxis: yAxes,
        series,
        graphic: graphics,
        legend: {
          top: 6,
          right: 10,
          textStyle: { color: "#e6e9ef" },
          data: [
            "total_glass(ALL)",
            "API total_glass",
            "BPI total_glass",
            "ITO total_glass",
            "OTHER total_glass",
            "Capa",
            "OOS",
            "OOC",
          ],
        },
        tooltip: {
          trigger: "axis",
          triggerOn: "mousemove|click",
          axisPointer: { type: "cross" },
          formatter: (params) => {
            const list = Array.isArray(params) ? params : [params];
            const sc = list.find(
              (p) => p.seriesType === "scatter" && p.data && p.data.meta
            );
            if (!sc) return "";

            const m = sc.data.meta;
            const capaPct = m.capa_percent != null ? m.capa_percent : null;
            const capaVal = m.capa != null ? m.capa.toFixed(3) : null;
            const tg = m.target_count != null ? m.target_count : "-";
            const gl = m.total_glass != null ? m.total_glass : "-";
            const selPi = Array.isArray(m.selected_pi) && m.selected_pi.length
              ? m.selected_pi.join(", ")
              : "-";

            const perPi = m.per_pi_glass || {};
            const perPiStr = Object.keys(perPi)
              .sort()
              .map((k) => `${k}:${perPi[k] ?? 0}`)
              .join(" / ");

            return [
              `<b>${m.day} / ${m.aoi}</b>`,
              capaPct != null ? `Capa: ${capaPct}% (${capaVal})` : "Capa: -",
              `total_glass(by filter): ${gl}`,
              `target_count: ${tg}`,
              `pi_type: ${selPi}`,
              perPiStr ? `pi_type glass: ${perPiStr}` : "",
            ]
              .filter(Boolean)
              .join("<br>");
          },
        },
      },
      true
    );

    inst.resize();

    inst.off("click");
    inst.on("click", (p) => {
      if (getCurrentSubTab() !== "Day_Hourly") return;
      if (!p || p.seriesType !== "bar" || !p.data || !p.data.meta) return;

      const m = p.data.meta;
      if (!AOI.Table || typeof AOI.Table.showHourly !== "function") return;

      AOI.Table.showHourly({
        aoi: m.aoi,
        day: m.day,
        pi_type: m.pi_type,
      });
    });
  };
})();