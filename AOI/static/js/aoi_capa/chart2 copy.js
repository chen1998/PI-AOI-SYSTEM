// static/js/aoi_capa/chart.js
(function () {
  const AOI = (window.AOI_CAPA = window.AOI_CAPA || {});
  AOI.Chart = AOI.Chart || {};

  const $ = (sel, root = document) => root.querySelector(sel);

  let chart = null;

  // pi_type 專用顏色（堆疊柱）
  const PI_COLORS = {
    API: "#7373B9",
    BPI: "#336666",
    ITO: "#6C3365"
  };

  const SCATTER_COLOR = "#FF4136";  // Capa 統一用綠色

  const CHART_THEME = {
    axisLabel: "#aeb6c7",
    axisLine:  "#2b3240",
    axisTick:  "#3a4354",
    splitLine: "rgba(255,255,255,0.09)",
    splitLineStrong: "rgba(255,255,255,0.14)"
  };

  function ensureChartInstance() {
    const dom = $("#aoi_capa-facet");
    if (!dom) return null;

    // 若一開始沒有高度，給一個預設高度，後續不再因 AOI 數量動態調整高度
    const style = window.getComputedStyle(dom);
    const h = parseFloat(style.height || "0");
    if (!h) {
      dom.style.height = "360px";
    }

    if (!chart) {
      chart = echarts.init(dom);
      window.addEventListener("resize", () => {
        chart && chart.resize();
      });
    }
    return chart;
  }

  // 只用 aoi 做篩選，pi_type 留給後面自己算
  function getFilteredSummaryRows() {
    const rows = AOI.state?.rows || [];
    if (!rows.length) return [];

    const filters =
      typeof AOI.readFiltersFromUI === "function"
        ? AOI.readFiltersFromUI()
        : {};

    const aoiSel = filters.aoi || null;

    return rows.filter((r) => {
      const aoi = (r.aoi || r.AOI || "").toString();
      if (aoiSel && aoiSel.length && !aoiSel.includes(aoi)) return false;
      return true;
    });
  }

  // 依 aoi / run_day / pi_type 整理
  function buildAoiDayMap(rows) {
    const byAoi = {};
    const piTypeSetByAoi = {};
    const allDays = new Set();

    rows.forEach((r) => {
      const aoi = (r.aoi || "").toString();
      const day = (r.run_day || "").toString();
      const ptRaw = (r.pi_type || "").toString();
      if (!aoi || !day || !ptRaw) return;

      const pt = ptRaw.toUpperCase();
      allDays.add(day);

      if (!byAoi[aoi]) byAoi[aoi] = {};
      if (!byAoi[aoi][day]) byAoi[aoi][day] = { rowsByPi: {}, target: null };

      byAoi[aoi][day].rowsByPi[pt] = r;

      const t = Number(r.target_count);
      if (Number.isFinite(t)) {
        byAoi[aoi][day].target = t;
      }

      if (pt !== "ALL") {
        if (!piTypeSetByAoi[aoi]) piTypeSetByAoi[aoi] = new Set();
        piTypeSetByAoi[aoi].add(pt);
      }
    });

    return {
      byAoi,
      piTypeSetByAoi,
      days: Array.from(allDays).sort()
    };
  }

  // 依 pi_type filter 計算「這個 AOI / 這一天」的合計 total_glass & capa
  function aggregateDayForAoi(aoi, dayInfo, piFilterArr, fullSetArr) {
    const rowsByPi = dayInfo.rowsByPi || {};
    const target = Number(dayInfo.target ?? null);

    const map = {};
    Object.keys(rowsByPi).forEach((k) => {
      map[k.toUpperCase()] = rowsByPi[k];
    });

    const hasALL = !!map.ALL;
    const fullSet = (fullSetArr || []).map((v) => v.toUpperCase());

    // 目前對這個 AOI 真正有效的 pi_type（交集）
    let selected = [];
    if (Array.isArray(piFilterArr) && piFilterArr.length) {
      const upper = piFilterArr.map((v) => v.toUpperCase());
      selected = fullSet.filter((pt) => upper.includes(pt));
    } else {
      // 沒勾 pi_type → 視為全選
      selected = fullSet.slice();
    }

    const isFull = selected.length === fullSet.length && fullSet.length > 0;

    let total_glass = 0;
    let capa = null;
    let usedPi = [];

    if (isFull && hasALL) {
      const rowAll = map.ALL;
      total_glass = Number(rowAll.total_glass ?? 0) || 0;
      const v = Number(rowAll.real_day_capa ?? rowAll.real_day_capa_percent);
      capa = Number.isFinite(v) ? v : null;
      usedPi = ["ALL"];
    } else if (selected.length === 1) {
      const key = selected[0];
      const row = map[key];
      if (row) {
        total_glass = Number(row.total_glass ?? 0) || 0;
        const v = Number(row.real_day_capa ?? row.real_day_capa_percent);
        capa = Number.isFinite(v) ? v : null;
        usedPi = [key];
      } else {
        total_glass = 0;
        capa = null;
        usedPi = [];
      }
    } else if (selected.length > 1) {
      total_glass = selected.reduce((acc, pt) => {
        const row = map[pt];
        return acc + (Number(row?.total_glass ?? 0) || 0);
      }, 0);
      if (Number.isFinite(target) && target > 0) {
        capa = total_glass / target;
      } else {
        capa = null;
      }
      usedPi = selected.slice();
    } else {
      if (hasALL) {
        const rowAll = map.ALL;
        total_glass = Number(rowAll.total_glass ?? 0) || 0;
        const v = Number(rowAll.real_day_capa ?? rowAll.real_day_capa_percent);
        capa = Number.isFinite(v) ? v : null;
        usedPi = ["ALL"];
      } else {
        total_glass = 0;
        capa = null;
        usedPi = [];
      }
    }
    return {
      total_glass,
      capa,
      usedPi,
      target: Number.isFinite(target) ? target : null
    };
  }

  AOI.Chart.update = function () {
    const inst = ensureChartInstance();
    if (!inst) return;
  
    const data = getFilteredSummaryRows();
    if (!data.length) {
      inst.clear();
      inst.setOption({
        title: { text: "", left: "center" },
        xAxis: { type: "category", data: [] },
        yAxis: [],
        series: []
      });
      return;
    }
  
    const { byAoi, piTypeSetByAoi, days } = buildAoiDayMap(data);
    const aoiList = Object.keys(byAoi).sort();
    if (!aoiList.length || !days.length) {
      inst.clear();
      inst.setOption({
        title: { text: "", left: "center" },
        xAxis: { type: "category", data: [] },
        yAxis: [],
        series: []
      });
      return;
    }
  
    // 目前 UI 的 pi_type 選取（影響 Capa + 彩色堆疊是否顯示）
    const uiFilters =
      typeof AOI.readFiltersFromUI === "function"
        ? AOI.readFiltersFromUI()
        : {};
    const piFilterArr = Array.isArray(uiFilters.pi_type)
      ? uiFilters.pi_type.slice()
      : [];
    const piFilterUpper = piFilterArr.map((v) => v.toUpperCase());
  
    // ====== ★ 依容器高度平均分配每個 AOI 子圖的高度 ======
    const dom = $("#aoi_capa-facet");
    let totalHeight = 360;
    if (dom) {
      const cs = window.getComputedStyle(dom);
      const h1 = dom.clientHeight;
      const h2 = parseFloat(cs.height || "0");
      totalHeight = h1 || h2 || totalHeight;
    }
  
    const n = aoiList.length;
    const topPadding = 40;    // 整體上方留白
    const bottomPadding = 20; // 整體下方留白
    const gridGap = 20;       // 子圖之間間距
  
    // 可用高度（全部 grid 總和）
    const usable = Math.max(
      totalHeight - topPadding - bottomPadding - gridGap * (n - 1),
      60 * n    // 每格至少 60 高，避免太扁
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
  
      // 每個 AOI 一個 grid，高度平均分配
      grids.push({
        left: leftMargin,
        right: rightMargin,
        top,
        height: gridH
      });
  
      xAxes.push({
        type: "category",
        gridIndex,
        data: days,
        axisTick: {
          alignWithLabel: true,
          lineStyle: { color: CHART_THEME.axisTick, width: 1 }
        },
        axisLabel: {
          show: idx === aoiList.length - 1, // 只有最後一個 AOI 顯示 x label
          rotate: 0,
          margin: 10,
          color: CHART_THEME.axisLabel
        },
        axisLine: {
          lineStyle: { color: CHART_THEME.axisLine, width: 1 }
        }
      });
  
      // 左 y 軸：total_glass
      yAxes.push({
        type: "value",
        gridIndex,
        position: "left",
        axisLabel: { color: CHART_THEME.axisLabel },
        axisLine: { lineStyle: { color: CHART_THEME.axisLine, width: 1 } },
        axisTick: { lineStyle: { color: CHART_THEME.axisTick, width: 1 } },
        splitLine: {
          show: true,
          lineStyle: { color: CHART_THEME.splitLine, width: 1, type: "dashed" }
        }
      });
  
      // 右 y 軸：Capa(%)  ← ★ 改成百分比刻度
      yAxes.push({
        type: "value",
        gridIndex,
        position: "right",
        axisLabel: {
          color: CHART_THEME.axisLabel,
          formatter: (val) => `${Math.round(val)}%`   // 直接顯示百分比
        },
        axisLine: { lineStyle: { color: CHART_THEME.axisLine, width: 1 } },
        axisTick: { lineStyle: { color: CHART_THEME.axisTick, width: 1 } },
        splitLine: { show: false }
      });
  
      // AOI label：畫在左側 y 軸的左邊（直立），位置要用新的 gridH
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
          textAlign: "center"
        }
      });
  
      const dayMap = byAoi[aoi] || {};
      const fullSet = Array.from(piTypeSetByAoi[aoi] || []).sort(); // 這台 AOI 的 pi_type 列表
  
      // 準備堆疊資料：每個 pi_type 一組，另外一組 ALL（灰色背景）
      const stackDataByPi = {};
      fullSet.forEach((pi) => {
        stackDataByPi[pi.toUpperCase()] = [];
      });
      const allBarData = [];
  
      const scatterData = [];
      const specLine = [];   // 每日 spec (百分比)
      const spec08Line = []; // 每日 spec * 0.8 (百分比)
      let maxGlass = 0;
      let maxCapaPct = 0;    // 右軸用百分比最大值
  
      days.forEach((day) => {
        const info = dayMap[day];
  
        if (!info) {
          fullSet.forEach((pi) => {
            stackDataByPi[pi.toUpperCase()].push(0);
          });
          allBarData.push(0);
          scatterData.push(null);
          specLine.push(null);
          spec08Line.push(null);
          return;
        }
  
        const rowsByPi = info.rowsByPi || {};
  
        // 取得當天 spec（已為百分比單位）
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
            if (Number.isFinite(sv)) specVal = sv; // sv 已是百分比，例如 85
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
  
        // 每個 pi_type 的 glass
        const perPiGlass = {};
        let sumPi = 0;
        fullSet.forEach((pi) => {
          const key = pi.toUpperCase();
          const row = rowsByPi[key];
          const v = row ? (Number(row.total_glass ?? 0) || 0) : 0;
          // 若有 pi_type filter，沒被選到就堆疊部分設 0
          const isSelected =
            !piFilterUpper.length || piFilterUpper.includes(key);
          const valForStack = isSelected ? v : 0;
  
          stackDataByPi[key].push({
            value: valForStack,
            meta: {
              aoi,
              day,
              pi_type: key
            }
          });
          perPiGlass[key] = v;
          sumPi += v;
        });
  
        // ALL 的 glass：若有 ALL row，用 ALL；沒有就用 pi_type 加總
        const allRow = rowsByPi.ALL;
        const allVal = allRow
          ? (Number(allRow.total_glass ?? 0) || 0)
          : sumPi;
        allBarData.push({
          value: allVal,
          meta: {
            aoi,
            day,
            pi_type: "ALL"
          }
        });
        maxGlass = Math.max(maxGlass, allVal);
  
        // 計算這一天的 Capa（依 pi_type filter 規則）
        const agg = aggregateDayForAoi(aoi, info, piFilterArr, fullSet);
        const tg = agg.total_glass || 0;
        const cp = agg.capa; // 比例 (0~1 或 >1)
  
        let cpPct = null;
        if (cp != null && isFinite(cp)) {
          // ★ 轉成百分比，四捨五入
          cpPct = Math.round(cp * 100);
          maxCapaPct = Math.max(maxCapaPct, cpPct);
        }
  
        scatterData.push(
          cpPct != null && isFinite(cpPct)
            ? {
                value: cpPct,  // 圖上用百分比值
                meta: {
                  aoi,
                  day,
                  total_glass: tg,
                  capa: cp,          // 原始比例
                  capa_percent: cpPct, // 百分比
                  target_count: agg.target,
                  selected_pi: agg.usedPi,
                  all_pi: fullSet,
                  per_pi_glass: perPiGlass
                }
              }
            : null
        );
      });
  
      const gAxis = yAxes[yLeftIndex];
      const cAxis = yAxes[yRightIndex];
      gAxis.max = maxGlass > 0 ? Math.ceil(maxGlass * 1.2) : 10;
      gAxis.min = 0;
  
      // ★ 右軸使用百分比的最大值
      cAxis.max = maxCapaPct > 0 ? Math.ceil(maxCapaPct * 1.2) : 100;
      cAxis.min = 0;
  
      // 灰色 ALL 背景柱（所有 AOI 都叫同一個 name，legend 一個就可以控全部）
      series.push({
        name: "total_glass(ALL)",
        type: "bar",
        xAxisIndex,
        yAxisIndex: yLeftIndex,
        barMaxWidth: 18,
        itemStyle: {
          color: "#9aa3b2",
          opacity: 0.8
        },
        data: allBarData,
        barGap: "-100%" // 跟堆疊柱重疊
      });
  
      // 彩色堆疊：每個 pi_type 一段（名字不帶 aoi，方便 legend 統一）
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
            color: PI_COLORS[key] || "#cccccc"
          },
          data: stackDataByPi[key] || [],
          barGap: "-100%"
        });
      });
  
      // ★ Spec 線 (每日一個值，step 水平段)
      series.push({
        name: "OOS",
        type: "line",
        xAxisIndex,
        yAxisIndex: yRightIndex,
        symbol: "none",
        step: "middle",
        lineStyle: {
          width: 1.5,
          type: "dashed",
          opacity: 0.8,
          color:'#82D900',
        },
        data: specLine,
        z: 40
      });
      console.log('xAxisIndex',xAxisIndex);
      // Spec*0.8 線
      series.push({
        name: "OOC",
        type: "line",
        xAxisIndex,
        yAxisIndex: yRightIndex,
        symbol: "none",
        step: "middle",
        lineStyle: {
          width: 1.5,
          type: "dashed",
          opacity: 0.8,
          color:'#0000E3',
          
        },
        data: spec08Line,
        z: 39
      });
  
      // Capa Scatter
      series.push({
        name: "Capa",
        type: "scatter",
        xAxisIndex,
        yAxisIndex: yRightIndex,
        symbolSize: 8,
        itemStyle: {
          color: SCATTER_COLOR
        },
        // ★ 在點上顯示百分比標籤
        label: {
          show: true,
          position: "top",
          formatter: (p) => {
            const m = p.data && p.data.meta;
            if (!m || m.capa_percent == null) return "";
            return `${m.capa_percent}%`;
          }
        },
        data: scatterData,
        connectNulls: false,
        z: 50
      });
    });
  
    // 圖例統一一組在右上
    const legend = {
      top: 6,
      right: 10,
      textStyle: { color: "#e6e9ef" },
      data: [
        "total_glass(ALL)",
        "API total_glass",
        "BPI total_glass",
        "ITO total_glass",
        "Capa",
        "OOS",
        "OOC"
      ]
    };
  
    const option = {
      animation: true,
      title: { text: "", left: "center" },
      grid: grids,
      xAxis: xAxes,
      yAxis: yAxes,
      series,
      legend,
      graphic: graphics,
      tooltip: {
        trigger: "axis",
        triggerOn: "mousemove|click",
        axisPointer: { type: "cross" },
        formatter: (params) => {
          const list = Array.isArray(params) ? params : [params];
  
          // 找到 scatter 那一筆（有 meta 的）
          const sc = list.find(
            (p) => p.seriesType === "scatter" && p.data && p.data.meta
          );
          if (!sc) return "";
  
          const m = sc.data.meta;
          const capaPct =
            m.capa_percent != null && isFinite(m.capa_percent)
              ? m.capa_percent
              : null;
          const capaVal =
            m.capa != null && isFinite(m.capa) ? m.capa.toFixed(3) : null;
          const tg =
            m.target_count != null && isFinite(m.target_count)
              ? m.target_count
              : "-";
          const gl = m.total_glass != null ? m.total_glass : "-";
          const selPi =
            Array.isArray(m.selected_pi) && m.selected_pi.length
              ? m.selected_pi.join(", ")
              : "-";
  
          const perPi = m.per_pi_glass || {};
          const perPiStr = Object.keys(perPi)
            .sort()
            .map((k) => `${k}:${perPi[k] ?? 0}`)
            .join(" / ");
  
          const capaLine =
            capaPct != null
              ? `Capa: ${capaPct}%` +
                (capaVal != null ? ` (${capaVal})` : "")
              : "Capa: -";
  
          return [
            `<b>${m.day} / ${m.aoi}</b>`,
            capaLine,
            `total_glass(by filter): ${gl}`,
            `target_count: ${tg}`,
            `pi_type: ${selPi}`,
            perPiStr ? `pi_type glass: ${perPiStr}` : ""
          ]
            .filter(Boolean)
            .join("<br>");
        }
      }
    };
  
    inst.setOption(option, true);
    inst.resize(); // 依目前容器大小再調整一次
  
    // -------- 柱狀點擊 → 顯示 hourly table --------
    inst.off("click");
    inst.on("click", (p) => {
      if (!p || p.seriesType !== "bar" || !p.data || !p.data.meta) return;
      const m = p.data.meta;
      if (!AOI.Table || typeof AOI.Table.showHourly !== "function") return;
      AOI.Table.showHourly({
        aoi: m.aoi,
        day: m.day,
        pi_type: m.pi_type
      });
    });
  };
})();