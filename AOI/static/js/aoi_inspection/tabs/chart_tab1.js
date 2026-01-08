
// static/js/aoi_inspection/chart_tab.js
(function () {
  // ==============================
  // Namespace
  // ==============================
  const ROOT   = (window.AOI_INSPECTION = window.AOI_INSPECTION || {});
  const MOD    = (ROOT.TrendCharts = ROOT.TrendCharts || {});
  const MDD_NS = ROOT;

  const $ = (sel, root = document) => root.querySelector(sel);

  MOD.filterConfig = null;
  MOD.mdd = { 1: {}, 2: {}, 3: {} };
  MOD.rawTrend = { day: null, week: null, month: null };

  // baseline cache（用於 tooltip 比較）
  MOD.baseline = {
    day:   { xTicks: [], glassTotal: [], defectGlass: [], density: [], defectCount: [] },
    week:  { xTicks: [], glassTotal: [], defectGlass: [], density: [], defectCount: [] },
    month: { xTicks: [], glassTotal: [], defectGlass: [], density: [], defectCount: [] }
  };

  let uiBound = false;

  // ==============================
  // Fetch helper
  // ==============================
  async function fetchTrend(payload) {
    const API = window.API || null;
    if (!API?.getInspectionTrend) {
      console.warn("[inspection_trend] API.getInspectionTrend 不存在");
      return null;
    }
    try {
      return await API.getInspectionTrend(payload);
    } catch (e) {
      console.error("[inspection_trend] getInspectionTrend error:", e);
      return null;
    }
  }

  // ==============================
  // MultiDD utilities
  // ==============================
  function collectGroupSelections(groupNo) {
    const out = {};
    const wrap = MOD.mdd[groupNo] || {};
    Object.entries(wrap).forEach(([dataKey, obj]) => {
      if (!obj?.mdd?.getSelected) return;
      const sel = obj.mdd.getSelected() || [];
      if (sel.length) out[dataKey] = sel.map(String);
    });
    return out;
  }

  // 判斷「是否真的有縮小篩選」（子集合）
  // 1) sel.length===0 → 不限制（等於全選）→ 不算
  // 2) sel.length===options.length → 全選 → 不算
  // 3) 其他 → 算 select 模式
  function isSubsetSelection(groupNo) {
    const wrap = MOD.mdd[groupNo] || {};
    for (const obj of Object.values(wrap)) {
      const mdd = obj?.mdd;
      const options = obj?.options || [];
      if (!mdd?.getSelected) continue;

      const sel = (mdd.getSelected() || []).map(String);
      if (!sel.length) continue;
      if (sel.length === options.length) continue;
      return true;
    }
    return false;
  }

  // ==============================
  // filter_item_coldict normalize
  // ==============================
  function normalizeFilterItem(rawKey, rawCfg) {
    if (Array.isArray(rawCfg)) {
      return { labelText: rawKey, dataKey: rawKey, options: rawCfg.map(String) };
    }
    if (rawCfg && typeof rawCfg === "object") {
      const dataKey   = rawCfg.key || rawKey;
      const options   = Array.isArray(rawCfg.values) ? rawCfg.values.map(String) : [];
      const labelText = rawCfg.label || rawKey;
      return { labelText, dataKey, options };
    }
    return null;
  }

  // ==============================
  // Option visibility (per group trend points)
  // ==============================
  function getKindByGroupNo(groupNo) {
    return (groupNo === 1) ? "month" : (groupNo === 2) ? "week" : "day";
  }

  function buildValueSetFromTrendPoints(points, dataKey) {
    const set = new Set();
    (points || []).forEach(p => {
      const v = p?.[dataKey];
      if (v == null) return;
      const s = String(v);
      if (!s) return;
      set.add(s);
    });
    return set;
  }

  // dataKey = "defect_size" 例外：不做隱藏（維持原本固定選項 S/M/L/O）
  function filterOptionsByTrendPresence({ groupNo, dataKey, options }) {
    if (!Array.isArray(options)) return [];
    if (String(dataKey) === "defect_size") return options.map(String);

    const kind = getKindByGroupNo(groupNo);
    const points = MOD.rawTrend?.[kind]?.points || [];
    if (!points.length) return [];

    const set = buildValueSetFromTrendPoints(points, dataKey);
    return options.map(String).filter(v => set.has(String(v)));
  }

  // ==============================
  // Build filters per group
  // ==============================
  function buildChartFiltersForGroup(groupNo, filterCfg) {
    const group = $(`.inspection-chart-group[data-chart-group="${groupNo}"]`);
    if (!group) return;

    const row = group.querySelector(".inspection-chart-filter-row");
    if (!row) return;

    row.querySelector(".inspection-chart-extra-filters")?.remove();

    const extra = document.createElement("div");
    extra.className = "inspection-chart-extra-filters";
    extra.style.display = "flex";
    extra.style.flexWrap = "wrap";
    extra.style.gap = "8px";

    MOD.mdd[groupNo] = {};

    const colDict = filterCfg || {};
    const keys = Object.keys(colDict || {});
    if (!keys.length) return;

    const anchor = row.querySelector(".inspection-filter-group");
    if (anchor && anchor.parentNode === row) row.insertBefore(extra, anchor.nextSibling);
    else row.appendChild(extra);

    const hasMultiDD = typeof MDD_NS.MultiDD === "function";

    const rerender = () => {
      if (groupNo === 1) MOD.renderMonthChart();
      if (groupNo === 2) MOD.renderWeekChart();
      if (groupNo === 3) MOD.renderDayChart();
    };

    keys.forEach((rawKey) => {
      const norm = normalizeFilterItem(rawKey, colDict[rawKey]);
      if (!norm) return;

      const { labelText, dataKey, options } = norm;

      const visibleOptions = filterOptionsByTrendPresence({
        groupNo,
        dataKey,
        options
      });

      if (!visibleOptions.length) return;

      const fg = document.createElement("div");
      fg.className = "inspection-filter-group";

      const lab = document.createElement("label");
      lab.className = "inspection-field-label";
      lab.textContent = labelText;
      fg.appendChild(lab);

      if (hasMultiDD) {
        const host = document.createElement("div");
        host.className = "multi-dd-host";
        host.id = `inspection_chart${groupNo}-host-${dataKey}`;
        fg.appendChild(host);

        extra.appendChild(fg);

        const mdd = new MDD_NS.MultiDD({
          hostId: host.id,
          selectId: `inspection_chart${groupNo}-select-${dataKey}`,
          options: visibleOptions,
          title: "",
          labelText,
          onChange: rerender
        });
        
        // ✅ 預設選取規則
        if (String(dataKey) === "glass_type" && visibleOptions.includes("TFT")) {
          mdd.setSelected(["TFT"]);        // 只選 TFT
        } else {
          mdd.setSelected([]);             // 其他維持「不選=不限制」
        }
        
        MOD.mdd[groupNo][dataKey] = { mdd, options: visibleOptions };
      } else {
        const sel = document.createElement("select");
        sel.className = "inspection-select";
        sel.multiple = true;
        visibleOptions.forEach(v => {
          const opt = document.createElement("option");
          opt.value = v;
          opt.textContent = v;
          sel.appendChild(opt);
        });

        // 預設選取 TFT（fallback）
        if (String(dataKey) === "glass_type") {
          Array.from(sel.options).forEach(o => {
            o.selected = (o.value === "TFT");
          });
        }

        sel.addEventListener("change", rerender);
        fg.appendChild(sel);
        extra.appendChild(fg);

      }
    });
  }

  function buildAllChartFilters(filterCfg) {
    buildChartFiltersForGroup(1, filterCfg);
    buildChartFiltersForGroup(2, filterCfg);
    buildChartFiltersForGroup(3, filterCfg);
  }

  // ==============================
  // rawTrend → init date inputs
  // ==============================
  function getTrendPoints(kind) {
    const trend = MOD.rawTrend[kind];
    if (!trend || !Array.isArray(trend.points)) return [];
    return trend.points;
  }

  function initDateInputsFromTrend(kind) {
    const pts = getTrendPoints(kind);
    if (!pts.length) return;

    if (kind === "day") {
      const dates = pts.map(p => p?.x).filter(Boolean).map(x => String(x).slice(0, 10)).sort();
      if (!dates.length) return;
      const sEl = $("#inspection_chart3-dateStart");
      const eEl = $("#inspection_chart3-dateEnd");
      if (sEl) sEl.value = dates[0];
      if (eEl) eEl.value = dates[dates.length - 1];
    }

    if (kind === "week") {
      const weeks = pts.map(p => p?.week_label).filter(Boolean).sort();
      if (!weeks.length) return;
      const sEl = $("#inspection_chart2-weekStart");
      const eEl = $("#inspection_chart2-weekEnd");
      if (sEl) sEl.value = weeks[0];
      if (eEl) eEl.value = weeks[weeks.length - 1];
    }

    if (kind === "month") {
      const months = pts.map(p => p?.x).filter(Boolean).map(x => String(x).slice(0, 7)).sort();
      if (!months.length) return;
      const sEl = $("#inspection_chart1-monthStart");
      const eEl = $("#inspection_chart1-monthEnd");
      if (sEl) sEl.value = months[0];
      if (eEl) eEl.value = months[months.length - 1];
    }
  }

  function autoSelectOptionsForGroupFromTrend(groupNo) {
    const kind = (groupNo === 1) ? "month" : (groupNo === 2) ? "week" : "day";
    const pts = getTrendPoints(kind);
    if (!pts.length) return;

    const wrap = MOD.mdd[groupNo] || {};
    Object.entries(wrap).forEach(([dataKey, obj]) => {
      if (!obj?.mdd?.setSelected) return;

      // defect_size：不要用 row.defect_size ("SMLO") 去 auto-select
      // 讓它維持「不選=不限制」即可
      if (dataKey === "defect_size") {
        obj.mdd.setSelected([]);
        return;
      }

      if (dataKey === "glass_type") {
        obj.mdd.setSelected(obj.options?.includes("TFT") ? ["TFT"] : []);
        return;
      }

      const valueSet = new Set();
      pts.forEach(p => {
        if (p && p[dataKey] != null) valueSet.add(String(p[dataKey]));
      });

      const options = obj.options || [];
      const selected = options.filter(v => valueSet.has(String(v)));
      obj.mdd.setSelected(selected);
    });
  }

  function refreshUIFromRawTrend(kind) {
    if (kind === "day" || kind === "week" || kind === "month") {
      initDateInputsFromTrend(kind);
      const groupNo = (kind === "month") ? 1 : (kind === "week") ? 2 : 3;
      autoSelectOptionsForGroupFromTrend(groupNo);
    } else if (kind === "all") {
      ["month", "week", "day"].forEach(k => {
        initDateInputsFromTrend(k);
        const g = (k === "month") ? 1 : (k === "week") ? 2 : 3;
        autoSelectOptionsForGroupFromTrend(g);
      });
    }
  }

  // ==============================
  // Frontend filter points (day/week/month)
  // defect_size 規則（TrendChart）：
  // - 選 S/M/L/O 時：用四個 *_defect_count > 0 來判斷 row 是否符合（OR）
  // - density 的計算：會在 aggregateByKey 用勾選到的 size 重新加總 defect_count
  // ==============================
  function passDefectSizeRow(row, arr) {
    const want = new Set((arr || []).map(String));
    if (!want.size) return true; // 不選=不限制

    const hasS = (Number(row.small_defect_count  ?? 0) || 0) > 0;
    const hasM = (Number(row.middle_defect_count ?? 0) || 0) > 0;
    const hasL = (Number(row.large_defect_count  ?? 0) || 0) > 0;
    const hasO = (Number(row.over_defect_count   ?? 0) || 0) > 0;

    return (
      (want.has("S") && hasS) ||
      (want.has("M") && hasM) ||
      (want.has("L") && hasL) ||
      (want.has("O") && hasO)
    );
  }

  function getDayFilteredPointsFromUI() {
    const pts = MOD.rawTrend.day?.points || [];
    const dStart = $("#inspection_chart3-dateStart")?.value || "";
    const dEnd   = $("#inspection_chart3-dateEnd")?.value || "";
    const hasDate = !!(dStart && dEnd);
    const selMap = collectGroupSelections(3);

    return pts.filter(row => {
      if (!row) return false;

      if (hasDate) {
        const x = String(row.x || "").slice(0, 10);
        if (!x) return false;
        if (x < dStart || x > dEnd) return false;
      }

      for (const [key, arr] of Object.entries(selMap)) {
        if (!arr.length) continue;

        if (key === "defect_size") {
          if (!passDefectSizeRow(row, arr)) return false;
          continue;
        }

        const rv = row[key];
        if (rv == null) return false;
        if (!arr.includes(String(rv))) return false;
      }

      return true;
    });
  }

  function getWeekFilteredPointsFromUI() {
    const pts = MOD.rawTrend.week?.points || [];
    const wStart = $("#inspection_chart2-weekStart")?.value || "";
    const wEnd   = $("#inspection_chart2-weekEnd")?.value || "";
    const hasWeek = !!(wStart && wEnd);
    const selMap = collectGroupSelections(2);

    return pts.filter(row => {
      if (!row) return false;

      if (hasWeek) {
        const w = String(row.week_label || "");
        if (!w) return false;
        if (w < wStart || w > wEnd) return false;
      }

      for (const [key, arr] of Object.entries(selMap)) {
        if (!arr.length) continue;

        if (key === "defect_size") {
          if (!passDefectSizeRow(row, arr)) return false;
          continue;
        }

        const rv = row[key];
        if (rv == null) return false;
        if (!arr.includes(String(rv))) return false;
      }

      return true;
    });
  }

  function getMonthFilteredPointsFromUI() {
    const pts = MOD.rawTrend.month?.points || [];
    const mStart = $("#inspection_chart1-monthStart")?.value || "";
    const mEnd   = $("#inspection_chart1-monthEnd")?.value || "";
    const hasMonth = !!(mStart && mEnd);
    const selMap = collectGroupSelections(1);

    return pts.filter(row => {
      if (!row) return false;

      if (hasMonth) {
        const mm = String(row.x || "").slice(0, 7);
        if (!mm) return false;
        if (mm < mStart || mm > mEnd) return false;
      }

      for (const [key, arr] of Object.entries(selMap)) {
        if (!arr.length) continue;

        if (key === "defect_size") {
          if (!passDefectSizeRow(row, arr)) return false;
          continue;
        }

        const rv = row[key];
        if (rv == null) return false;
        if (!arr.includes(String(rv))) return false;
      }

      return true;
    });
  }

  // ==============================
  // Aggregate helpers
  // - density：可依 selSizes 重新計算 defect_count（S/M/L/O）
  // - defect_code_glass_count：後端目前沒有 size 對應 glass_count，所以這裡只能沿用原值（不會因 size 改變）
  // - defectCount：aggregate 後的 defect 總數（baseline = maingroup_defect_count；select = 勾選 S/M/L/O 的總和）
  // ==============================
  function aggregateByKey(rows, keyFn, selSizes = []) {
    const want = new Set((selSizes || []).map(String));
    const useSelected = want.size > 0;

    const pickDefectCount = (r) => {
      if (!useSelected) {
        // 沒選 defect_size：沿用後端的 selected_defect_count（=S+M+L+O）
        const v = (r.selected_defect_count != null) ? r.selected_defect_count : r.maingroup_defect_count;
        return Number(v ?? 0) || 0;
      }
      let sum = 0;
      if (want.has("S")) sum += Number(r.small_defect_count  ?? 0) || 0;
      if (want.has("M")) sum += Number(r.middle_defect_count ?? 0) || 0;
      if (want.has("L")) sum += Number(r.large_defect_count  ?? 0) || 0;
      if (want.has("O")) sum += Number(r.over_defect_count   ?? 0) || 0;
      return sum;
    };

    const byKey = new Map();
    rows.forEach(r => {
      const k = String(keyFn(r) || "").trim();
      if (!k) return;

      const g  = Number(r.maingroup_glass_count ?? 0) || 0;
      const cg = Number(r.defect_code_glass_count ?? 0) || 0;
      const d  = pickDefectCount(r);

      if (!byKey.has(k)) byKey.set(k, { k, g: 0, cg: 0, d: 0 });
      const o = byKey.get(k);
      o.g  += g;
      o.cg += cg;
      o.d  += d;
    });

    const xTicks = Array.from(byKey.keys()).sort((a, b) => String(a).localeCompare(String(b)));
    const glassTotal  = [];
    const defectGlass = [];
    const density     = [];
    const defectCount = [];

    xTicks.forEach(x => {
      const o = byKey.get(x);
      const g  = o?.g || 0;
      const cg = Math.min(o?.cg || 0, g);
      const d  = o?.d || 0;

      glassTotal.push(g);
      defectGlass.push(cg);
      defectCount.push(d);
      density.push(g > 0 ? (d / g) : null);
    });

    return { xTicks, glassTotal, defectGlass, density, defectCount };
  }

  function rebuildBaselineDayCache() {
    MOD.baseline.day = aggregateByKey(MOD.rawTrend.day?.points || [], r => String(r?.x || "").slice(0, 10));
  }
  function rebuildBaselineWeekCache() {
    MOD.baseline.week = aggregateByKey(MOD.rawTrend.week?.points || [], r => String(r?.week_label || ""));
  }
  function rebuildBaselineMonthCache() {
    MOD.baseline.month = aggregateByKey(MOD.rawTrend.month?.points || [], r => String(r?.x || "").slice(0, 7));
  }

  // ==============================
  // Tooltip formatter
  // ==============================
  function makeTooltipFormatter({ xTicks, baseline, showSelect, selSeries, labels }) {
    const i0 = (n) => (n == null || !isFinite(n)) ? "-" : String(Math.trunc(Number(n)));
    const f4 = (n) => (n == null || !isFinite(n)) ? "-" : Number(n).toFixed(1);

    return function (params) {
      const list = Array.isArray(params) ? params : [params];
      const idx = list?.[0]?.dataIndex ?? 0;
      const x = xTicks[idx] ?? "";
      const br = "<br>";

      let s = "";
      s += String(x) + br;

      // baseline glass / defect glass / density
      s += labels.base[0] + ": " + i0(baseline.glassTotal[idx]) + br;
      s += labels.base[1] + ": " + i0(baseline.defectGlass[idx]) + br;
      s += labels.base[2] + ": " + f4(baseline.density[idx]) + br;

      // baseline defectCount = maingroup_defect_count（或 selected_defect_count aggregate）
      if (baseline.defectCount && baseline.defectCount.length > idx) {
        s += "maingroup_defect_count: " + i0(baseline.defectCount[idx]) + br;
      }

      if (showSelect) {
        s += br;
        s += labels.select[0] + ": " + i0(selSeries.glassTotal[idx]) + br;
        s += labels.select[1] + ": " + i0(selSeries.defectGlass[idx]) + br;
        s += labels.select[2] + ": " + f4(selSeries.density[idx]) + br;

        if (selSeries.defectCount && selSeries.defectCount.length > idx) {
          s += "select_defect_count: " + i0(selSeries.defectCount[idx]) + br;
        }
      }
      return s;
    };
  }

  // ==============================
  // Generic renderer
  // ==============================
  function renderTrendChart({
    domId,
    baseline,
    showSelect,
    selectAgg,
    keyLabels
  }) {
    const ec = window.echarts;
    const dom = $(domId);
    if (!ec || !dom) return;

    if (!baseline?.xTicks?.length) {
      dom.textContent = "沒有資料";
      return;
    }

    const xTicks = baseline.xTicks;

    // align select to baseline ticks
    const selMap = {};
    if (selectAgg?.xTicks?.length) {
      selectAgg.xTicks.forEach((x, i) => {
        selMap[x] = {
          g:   selectAgg.glassTotal[i],
          cg:  selectAgg.defectGlass[i],
          den: selectAgg.density[i],
          d:   selectAgg.defectCount ? selectAgg.defectCount[i] : null
        };
      });
    }

    const selSeries = {
      glassTotal:  xTicks.map(x => (selMap[x]?.g   ?? null)),
      defectGlass: xTicks.map(x => (selMap[x]?.cg  ?? null)),
      density:     xTicks.map(x => (selMap[x]?.den ?? null)),
      defectCount: xTicks.map(x => (selMap[x]?.d   ?? null))
    };

    const inst = ec.getInstanceByDom(dom) || ec.init(dom);
    dom.style.height = "320px";

    const baseNames = keyLabels.base;   // ["glass (total)", "defect glass", "density"]
    const selNames  = keyLabels.select; // ["select-glass (total)", "select-defect glass", "select-density"]

    const legendData = showSelect ? [...baseNames, ...selNames] : [...baseNames];

    const legendSelected = {};

    [...baseNames, ...selNames].forEach(n => {
      legendSelected[n] = false;
    });

    if (showSelect) {
      // 只開 select-glass (total) + select-density
      legendSelected["select-glass (total)"] = true;
      legendSelected["select-density"]       = true;
    } else {
      // 只開 baseline 的 glass (total) + density
      legendSelected["glass (total)"] = true;
      legendSelected["density"]       = true;
    }

    const barWidth = 18;  // 統一四個 bar 的寬度

    const option = {
      backgroundColor: "transparent",
      animation: true,
      grid: { left: 56, right: 56, top: 44, bottom: 48, containLabel: true },

      legend: {
        top: 8,
        right: 10,
        itemGap: 18,
        textStyle: { color: "#d7e1ff" },
        data: legendData,
        selected: legendSelected
      },

      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross", snap: true },
        formatter: makeTooltipFormatter({
          xTicks,
          baseline,
          showSelect,
          selSeries,
          labels: { base: baseNames, select: selNames }
        })
      },

      xAxis: {
        type: "category",
        data: xTicks,
        axisTick: { alignWithLabel: true, lineStyle: { color: "rgba(255,255,255,0.18)" } },
        axisLine: { lineStyle: { color: "rgba(255,255,255,0.22)" } },
        axisLabel: { color: "#cfe0ff", rotate: xTicks.length > 10 ? 45 : 0, margin: 12 }
      },

      yAxis: [
        {
          type: "value",
          name: "glass count",
          min: 0,
          axisLabel: { color: "#cfe0ff" },
          axisLine: { lineStyle: { color: "rgba(255,255,255,0.22)" } },
          axisTick: { lineStyle: { color: "rgba(255,255,255,0.18)" } },
          splitLine: { show: true, lineStyle: { color: "rgba(210,210,210,0.28)", type: "dashed", width: 1 } }
        },
        {
          type: "value",
          name: "density",
          min: 0,
          axisLabel: { color: "#cfe0ff", formatter: (v) => (v != null ? Number(v).toFixed(2) : "") },
          axisLine: { lineStyle: { color: "rgba(255,255,255,0.22)" } },
          axisTick: { lineStyle: { color: "rgba(255,255,255,0.18)" } },
          splitLine: { show: false }
        }
      ],

      series: [
        // ---- baseline ----
        {
          id: `${domId}_bar_total`,
          name: baseNames[0],
          type: "bar",
          yAxisIndex: 0,
          barWidth,
          barGap: "0%",       // 第一個在類別中心位置
          z: 1,
          itemStyle: { color: "#9aa3b2", opacity: 0.7 },
          data: baseline.glassTotal
        },
        {
          id: `${domId}_bar_defect`,
          name: baseNames[1],
          type: "bar",
          yAxisIndex: 0,
          barWidth,
          barGap: "-100%",    // 與第一個完全重疊
          z: 2,
          itemStyle: { color: "#FF851B", opacity: 0.9 },
          data: baseline.defectGlass
        },
        {
          id: `${domId}_density`,
          name: baseNames[2],
          type: "line",
          yAxisIndex: 1,
          showSymbol: true,
          symbol: "circle",
          symbolSize: 6,
          connectNulls: false,
          z: 10,
          lineStyle: { width: 2, color: "#FF4136" },
          itemStyle: { color: "#FF4136" },
          // 在柱狀上方顯示 density 數值
          label: {
            show: true,
            position: "top",
            formatter: (p) => {
              const v = p.data;
              if (v == null || !isFinite(v)) return "";
              return Number(v).toFixed(1);
            },
            fontSize: 10,
            padding: [2, 4],
            color: "#e8edf7",
            backgroundColor: "rgba(15,18,27,0.85)",
          },
          data: baseline.density
        },

        // ---- select ----
        ...(showSelect ? [
          {
            id: `${domId}_sel_bar_total`,
            name: selNames[0],
            type: "bar",
            yAxisIndex: 0,
            barWidth,
            barGap: "-100%",  // 與 baseline 一樣位置
            z: 3,
            itemStyle: { color: "#AAAAFF", opacity: 0.9 },
            data: selSeries.glassTotal
          },
          {
            id: `${domId}_sel_bar_defect`,
            name: selNames[1],
            type: "bar",
            yAxisIndex: 0,
            barWidth,
            barGap: "-100%",  // 同位置
            z: 4,
            itemStyle: { color: "#AE00AE", opacity: 0.9 },
            data: selSeries.defectGlass
          },
          {
            id: `${domId}_sel_density`,
            name: selNames[2],
            type: "line",
            yAxisIndex: 1,
            showSymbol: true,
            symbol: "circle",
            symbolSize: 5,
            connectNulls: false,
            z: 12,
            lineStyle: { width: 2, type: "dashed", color: "#ff9f9f" },
            itemStyle: { color: "#ff9f9f" },
            // ★ 新增：在柱狀上方顯示 select-density 數值
            label: {
              show: true,
              position: "top",
              formatter: (p) => {
                const v = p.data;
                if (v == null || !isFinite(v)) return "";
                return Number(v).toFixed(1);
              },
              fontSize: 10,
              padding: [2, 4],
              color: "#e8edf7",
              backgroundColor: "rgba(15,18,27,0.85)",
            },
            data: selSeries.density
          }
        ] : [])
      ]
    };

    inst.setOption(option, true);

    window.removeEventListener("resize", inst.__resizeHandler || (() => {}));
    inst.__resizeHandler = () => inst.resize();
    window.addEventListener("resize", inst.__resizeHandler);
  }

  // ==============================
  // Render Day/Week/Month
  // - 把目前勾選到的 defect_size 傳進 aggregateByKey 做 density 重算
  // ==============================
  MOD.renderDayChart = function renderDayChart() {
    if (!MOD.baseline.day?.xTicks?.length) rebuildBaselineDayCache();
    const showSelect = isSubsetSelection(3);

    const selMap = collectGroupSelections(3);
    const selSizes = selMap.defect_size || [];

    const selAgg = showSelect
      ? aggregateByKey(getDayFilteredPointsFromUI(), r => String(r?.x || "").slice(0, 10), selSizes)
      : null;

    renderTrendChart({
      domId: "#inspection-chart3",
      baseline: MOD.baseline.day,
      showSelect,
      selectAgg: selAgg,
      keyLabels: {
        base: ["glass (total)", "defect glass", "density"],
        select: ["select-glass (total)", "select-defect glass", "select-density"]
      }
    });
  };

  MOD.renderWeekChart = function renderWeekChart() {
    if (!MOD.baseline.week?.xTicks?.length) rebuildBaselineWeekCache();
    const showSelect = isSubsetSelection(2);

    const selMap = collectGroupSelections(2);
    const selSizes = selMap.defect_size || [];

    const selAgg = showSelect
      ? aggregateByKey(getWeekFilteredPointsFromUI(), r => String(r?.week_label || ""), selSizes)
      : null;

    renderTrendChart({
      domId: "#inspection-chart2",
      baseline: MOD.baseline.week,
      showSelect,
      selectAgg: selAgg,
      keyLabels: {
        base: ["glass (total)", "defect glass", "density"],
        select: ["select-glass (total)", "select-defect glass", "select-density"]
      }
    });
  };

  MOD.renderMonthChart = function renderMonthChart() {
    if (!MOD.baseline.month?.xTicks?.length) rebuildBaselineMonthCache();
    const showSelect = isSubsetSelection(1);

    const selMap = collectGroupSelections(1);
    const selSizes = selMap.defect_size || [];

    const selAgg = showSelect
      ? aggregateByKey(getMonthFilteredPointsFromUI(), r => String(r?.x || "").slice(0, 7), selSizes)
      : null;

    renderTrendChart({
      domId: "#inspection-chart1",
      baseline: MOD.baseline.month,
      showSelect,
      selectAgg: selAgg,
      keyLabels: {
        base: ["glass (total)", "defect glass", "density"],
        select: ["select-glass (total)", "select-defect glass", "select-density"]
      }
    });
  };

  // ==============================
  // Read time filters (Apply only)
  // ==============================
  function readMonthRange() {
    const s = $("#inspection_chart1-monthStart")?.value || "";
    const e = $("#inspection_chart1-monthEnd")?.value || "";
    if (!(s && e)) return null;
    return [s.replace("-", ""), e.replace("-", "")];
  }

  function readWeekRange() {
    const s = $("#inspection_chart2-weekStart")?.value || "";
    const e = $("#inspection_chart2-weekEnd")?.value || "";
    if (!(s && e)) return null;
    const sW = (s.split("-W")[1] || "").trim();
    const eW = (e.split("-W")[1] || "").trim();
    if (!(sW && eW)) return null;
    return [`W${sW}`, `W${eW}`];
  }

  function readDayRange() {
    const s = $("#inspection_chart3-dateStart")?.value || "";
    const e = $("#inspection_chart3-dateEnd")?.value || "";
    if (!(s && e)) return null;
    return [s, e];
  }

  // ==============================
  // Bind UI (Apply/Clear)
  // ==============================
  function bindUI() {
    if (uiBound) return;
    uiBound = true;

    $("#inspection_chart1-apply")?.addEventListener("click", async () => {
      const range = readMonthRange();
      if (!range) return;

      const data = await fetchTrend({ day: null, week: null, month: range });
      if (!data) return;

      MOD.rawTrend.month = data.month || null;
      refreshUIFromRawTrend("month");
      rebuildBaselineMonthCache();
      MOD.renderMonthChart();
    });

    $("#inspection_chart1-clear")?.addEventListener("click", async () => {
      const data = await fetchTrend({ day: null, week: null, month: {} });
      if (!data) return;

      MOD.rawTrend.month = data.month || null;
      refreshUIFromRawTrend("month");
      rebuildBaselineMonthCache();
      MOD.renderMonthChart();
    });

    $("#inspection_chart2-apply")?.addEventListener("click", async () => {
      const range = readWeekRange();
      if (!range) return;

      const data = await fetchTrend({ day: null, week: range, month: null });
      if (!data) return;

      MOD.rawTrend.week = data.week || null;
      refreshUIFromRawTrend("week");
      rebuildBaselineWeekCache();
      MOD.renderWeekChart();
    });

    $("#inspection_chart2-clear")?.addEventListener("click", async () => {
      const data = await fetchTrend({ day: null, week: {}, month: null });
      if (!data) return;

      MOD.rawTrend.week = data.week || null;
      refreshUIFromRawTrend("week");
      rebuildBaselineWeekCache();
      MOD.renderWeekChart();
    });

    $("#inspection_chart3-apply")?.addEventListener("click", async () => {
      const range = readDayRange();
      if (!range) return;

      const data = await fetchTrend({ day: range, week: null, month: null });
      if (!data) return;

      MOD.rawTrend.day = data.day || null;
      refreshUIFromRawTrend("day");
      rebuildBaselineDayCache();
      MOD.renderDayChart();
    });

    $("#inspection_chart3-clear")?.addEventListener("click", async () => {
      const data = await fetchTrend({ day: {}, week: null, month: null });
      if (!data) return;

      MOD.rawTrend.day = data.day || null;
      refreshUIFromRawTrend("day");
      rebuildBaselineDayCache();
      MOD.renderDayChart();
    });

    console.log("[inspection_trend] UI bound");
  }

  // ==============================
  // Event: subtab-chart init
  // ==============================
  document.addEventListener("aoi_inspection:subtab-chart", async (ev) => {
    const detail = ev.detail || {};
    const cfg = detail.config || {};
    const filt = cfg.filter_item_coldict || null;

    bindUI();

    const data = await fetchTrend({ day: {}, week: {}, month: {} });
    if (!data) return;

    MOD.rawTrend.day   = data.day   || null;
    MOD.rawTrend.week  = data.week  || null;
    MOD.rawTrend.month = data.month || null;

    //  有了 rawTrend，再建 filters（這時 options 才能正確被過濾）
    if (filt && typeof filt === "object") {
      MOD.filterConfig = filt;
      buildAllChartFilters(filt);
    }

    refreshUIFromRawTrend("all");

    rebuildBaselineDayCache();
    rebuildBaselineWeekCache();
    rebuildBaselineMonthCache();

    MOD.renderMonthChart();
    MOD.renderWeekChart();
    MOD.renderDayChart();
  });

})();
