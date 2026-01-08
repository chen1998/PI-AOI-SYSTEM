
// static/js/aoi_inspection/chart.js
(function () {
  const MOD = (window.AOI_INSPECTION = window.AOI_INSPECTION || {});
  MOD.Charts = MOD.Charts || {};

  const $  = (sel, root = document) => root.querySelector(sel);
  const API = window.API;

  const CHART_THEME = {
    axisLabel: "#aeb6c7",
    axisLine:  "#2b3240",
    axisTick:  "#3a4354",
    splitLine: "rgba(255,255,255,0.09)",
    splitLineStrong: "rgba(255,255,255,0.14)",
    labelText: "#e8edf7",
    labelBg:   "rgba(15,18,27,0.85)",
    labelPad:  [2, 4],
    labelRadius: 3,
    mlText: "#eaefff",
    mlBg:   "rgba(13,18,27,0.9)"
  };

  const CHART_COLOR = {
    glassTotalBar:   "#9aa3b2",
    defectGlassBar:  "#FF851B",
    densityPoint:    "#FF4136",
    oocLine:         "#FFDC00",
    oosLine:         "#CE0000"
  };

  function fmtYYMMDDHH(d) {
    if (!(d instanceof Date) || isNaN(d)) return "";
    const yy = String(d.getFullYear()).slice(-2);
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    const hh = String(d.getHours()).padStart(2, "0");
    return `${yy}-${mm}-${dd} ${hh}`;
  }

  function parsePiHourKeyToDate(key) {
    if (!key) return null;
    // 支援兩種格式：
    // 1) '25-11-17 07'
    // 2) '2025-11-17T07:00:00'
    if (/^\d{2}-\d{2}-\d{2}\s+\d{2}$/.test(key)) {
      // '25-11-17 07' → '2025-11-17T07:00:00'
      const [yy, mm, dd_hh] = key.split("-");
      const [dd, hh] = dd_hh.split(" ");
      const full = `20${yy}-${mm}-${dd}T${hh}:00:00`;
      const d = new Date(full);
      return isNaN(d) ? null : d;
    }
    // 若已經是 ISO
    const d = new Date(String(key));
    return isNaN(d) ? null : d;
  }

  // === SPEC 索引 ===
  function buildSpecIndex(dictObj) {
    const idx = {};
    if (!dictObj || typeof dictObj !== "object") return idx;

    const rows = Object.values(dictObj);

    rows.forEach(r => {
      if (!r) return;

      const line  = String(r.line_id || "").trim();
      const model = String(r.model || "").trim();
      const side  = String(r.glass_type || "all").trim();  // TFT / CF / ALL

      if (!line || !model) return;

      const cell = {
        ooc: (r.OOC != null && isFinite(Number(r.OOC))) ? Number(r.OOC) : null,
        oos: (r.OOS != null && isFinite(Number(r.OOS))) ? Number(r.OOS) : null,
      };

      // 結構：idx[line][model][side] = cell
      idx[line] = idx[line] || {};
      idx[line][model] = idx[line][model] || {};
      idx[line][model][side] = cell;
    });

    return idx;
  }

  function getSelectedSizes() {
    try {
      const ui = window.AOI_INSPECTION?.readFiltersFromUI?.();
      const ds = ui?.defect_size;
      if (Array.isArray(ds) && ds.length) return ds;
    } catch (e) {}
    return ["S","M","L","O"];
  }

  // 解析 size 統計字串或物件（保留跟 aoi_density 同一套）
  function parseSizeStats(stat) {
    const out = { S: 0, M: 0, L: 0, O: 0, T: 0 };
    if (!stat) return out;

    if (typeof stat === "string") {
      const rx = /\b([SMLOT])\s*:\s*(\d+)/g;
      let m;
      while ((m = rx.exec(stat)) !== null) {
        const k = m[1].toUpperCase();
        const v = Number(m[2] || 0);
        if (k in out && Number.isFinite(v)) out[k] = v;
      }
      if (!/\bT\s*:/.test(stat)) {
        out.T = out.S + out.M + out.L + out.O;
      }
      return out;
    }

    if (typeof stat === "object") {
      out.S = Number(stat.S || 0);
      out.M = Number(stat.M || 0);
      out.L = Number(stat.L || 0);
      out.O = Number(stat.O || 0);
      out.T = Number(
        stat.T != null
          ? stat.T
          : (out.S + out.M + out.L + out.O)
      );
      return out;
    }

    return out;
  }

  // specIndex[line][model][side] 取 OOC/OOS
  function pickSpec(specIndex, line, model, side='all'){
    if (!specIndex?.[line]?.[model]) return null;

    const obj = specIndex[line][model];

    // 先找 exact match
    if (obj[side]) return obj[side];

    // 再找 'all'
    if (obj["all"]) return obj["all"];

    // 再取第一筆
    return Object.values(obj)[0] || null;
  }

  // ---- 資料讀取工具：Inspection 只有綜合一碼，不看 defect_code ----
  const U = {
    // aoi / code 已經不需要，保留佔位但不再使用
    aoi:  _ => "",
    code: _ => "",

    line:  r => String(r.line_id ?? r.line ?? ""),
    model: r => String(r.model ?? r.model_id ?? ""),
    side:  r => String(r.glass_type ?? "all"),   // 玻璃面/別：TFT/CF/ALL...

    tick:  r => {
      // 優先 tick_str，其次 pi_hour (ISO)
      return String(r.tick_str ?? r.pi_hour ?? "");
    },

    // 主群片數 / 缺陷數
    g:  r => Number(
      r.glass_num ??
      r.n_glasses ??
      r.maingroup_glass_count ??
      0
    ),
    r:  r => Number(
      r.defect_num ??
      r.maingroup_defect_count ??
      r.n_rows ??
      0
    ),

    // 尺寸數量
    s:  r => Number(r.s_count ?? r.small_defect_count  ?? 0),
    m:  r => Number(r.m_count ?? r.middle_defect_count ?? 0),
    l:  r => Number(r.l_count ?? r.large_defect_count  ?? 0),
    o:  r => Number(r.o_count ?? r.over_defect_count   ?? 0),

    // 「綜合」的 defect 片數
    codeG: r => Number(
      r.defect_code_glass_count ??
      r.code_glass_num ??
      0
    )
  };

  // ========== Row 排列：關鍵是 line + model + glass_type ==========
  function buildGlobalRowOrder(rows){
    const byLine = new Map();

    (rows||[]).forEach(r=>{
      const line  = U.line(r);
      const model = U.model(r);
      const side  = U.side(r);  // glass_type
      if (!line || !model) return;
      if (!byLine.has(line)) byLine.set(line, new Map());
      const mMap = byLine.get(line);
      if (!mMap.has(model)) mMap.set(model, new Set());
      mMap.get(model).add(side);
    });

    const order = [];
    const lines = Array.from(byLine.keys()).sort();
    lines.forEach(line=>{
      const mMap = byLine.get(line);
      const models = Array.from(mMap.keys()).sort();
      models.forEach(m=>{
        const sides = Array.from(mMap.get(m)).sort();
        sides.forEach(side=>{
          order.push({ line_id: line, model: m, glass_type: side });
        });
      });
    });

    const lineGroups = [];
    let i = 0;
    while(i < order.length){
      const line = order[i].line_id;
      const start = i;
      while(i < order.length && order[i].line_id === line) i++;
      lineGroups.push({ line_id: line, start, end: i-1 });
    }
    return { order, lineGroups };
  }

  // ========== 聚合欄位：Inspection 版，按 (line, model, glass_type, tick) 聚合 ==========
  // 不再依 aoi/code 分欄，全部放到同一個 column
  function buildColumnsByAoiCode(rows, globalOrder, specIndex, selectedSizesArr){
    const selected = new Set(selectedSizesArr && selectedSizesArr.length ? selectedSizesArr : ["S","M","L","O"]);

    // bucketsMap[line][model][side][tick] = { g, r, cg, rows[] }
    const bucketsMap = {};
    const ticksSet = new Set();

    (rows || []).forEach((r) => {
      const line  = U.line(r);
      const model = U.model(r);
      const side  = U.side(r) || "all";
      const tickRaw = U.tick(r);

      if (!line || !model || !tickRaw) return;

      const d = parsePiHourKeyToDate(tickRaw);
      const tick = d ? fmtYYMMDDHH(d) : tickRaw;

      ticksSet.add(tick);

      const L = (bucketsMap[line] = bucketsMap[line] || {});
      const M = (L[model] = L[model] || {});
      const G = (M[side] = M[side] || {});
      const T = (G[tick] = G[tick] || { g: 0, r: 0, cg: 0, rows: [] });

      T.g  += U.g(r);
      T.r  += U.r(r);
      T.cg += U.codeG(r);
      T.rows.push(r);
    });

    const xTicks = Array.from(ticksSet).sort((a,b)=>{
      const da = parsePiHourKeyToDate(a);
      const db = parsePiHourKeyToDate(b);
      return (da && db) ? (da - db) : (String(a).localeCompare(String(b)));
    });

    function calcSelectedBySize(bucketRows){
      let totalS = 0, totalM = 0, totalL = 0, totalO = 0;
      bucketRows.forEach(rec => {
        const s = U.s(rec);
        const m = U.m(rec);
        const l = U.l(rec);
        const o = U.o(rec);
        totalS += s;
        totalM += m;
        totalL += l;
        totalO += o;
      });

      const defectSel =
        (selected.has("S") ? totalS : 0) +
        (selected.has("M") ? totalM : 0) +
        (selected.has("L") ? totalL : 0) +
        (selected.has("O") ? totalO : 0);

      // 先抓「綜合」的 defect glass 片數
      let glassSel = 0;
      bucketRows.forEach(rec => {
        const v = U.codeG(rec);
        if (v > glassSel) glassSel = v;
      });

      // 如果在目前選到的尺寸下，完全沒有 defect → 橘色柱 = 0
      if (defectSel === 0) {
        glassSel = 0;
      }

      return { glassSel, defectSel, s: totalS, m: totalM, l: totalL, o: totalO };
    }

    const rowsOut = (globalOrder || []).map(({line_id, model, glass_type})=>{
      const buckets = (((bucketsMap[line_id] || {})[model] || {})[glass_type] || {});

      const glasses      = [];
      const codeGlasses  = [];
      const density      = [];
      const sArr = [], mArr = [], lArr = [], oArr = [], defSelArr = [];

      xTicks.forEach(tk=>{
        const T = buckets[tk] || { g:0, rows:[] };
        const g = Number(T.g || 0);
        glasses.push(g);

        const { glassSel, defectSel, s, m, l, o } = calcSelectedBySize(T.rows || []);
        codeGlasses.push(glassSel);
        defSelArr.push(defectSel);
        sArr.push(s); mArr.push(m); lArr.push(l); oArr.push(o);

        density.push(g > 0 ? (defectSel / g) : null);
      });

      const spec = pickSpec(specIndex, line_id, model, glass_type);

      return {
        line_id,
        model,
        glass_type,
        glasses,
        codeGlasses,
        density,
        sArr, mArr, lArr, oArr, defSelArr,
        maxG: Math.max(0, ...glasses, ...codeGlasses),
        maxD: Math.max(0, ...density.filter(x=>x!=null)),
        spec: spec || null
      };
    });

    if (!rowsOut.length) return [];
    return [{ xTicks, rows: rowsOut }];
  }

  // ===== 互動狀態 =====
  const interopState = {
    selectedTicks: new Set(),
    focusRowKey: null
  };

  // 把 aoi/code 拿掉，改用 colIndex 區分 column
  function calcOpacity(colIndex, rowKey, xIdx) {
    let passTick = true;
    if (interopState.selectedTicks.size > 0) {
      passTick = interopState.selectedTicks.has(`${xIdx}|${colIndex}`);
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

  // 依條件從 rawRows 抓出 summary rows
  function rowsByCriteria(allRows, criteria) {
    return (allRows || []).filter(r => {
      if (criteria.line && U.line(r) !== criteria.line) return false;
      if (criteria.line_id && U.line(r) !== criteria.line_id) return false;
      if (criteria.model && U.model(r) !== criteria.model) return false;
      if (criteria.glass_type && U.side(r) !== criteria.glass_type) return false;
      if (criteria.tick &&
          (U.tick(r) !== criteria.tick && (("20"+U.tick(r)) !== criteria.tick))) return false;
      return true;
    });
  }

  function renderBigChart(dom, columns, global, rawRows) {
    const ec = window.echarts;
    if (!ec) return;

    const LEGEND_TOP = -10, LEGEND_RIGHT = 10, LEGEND_ITEM_GAP = 18, LEGEND_BLOCK_H = 42;
    const TITLE_GAP = 12, HEADER_TEXT_H = 32;
    const padTop = LEGEND_BLOCK_H + TITLE_GAP + HEADER_TEXT_H;
    const padBottom = 44;

    const baseLeft = 16, gutterLineW = 26, gutterGap = 8, gutterModelW = 26;
    const leftMargin = baseLeft + gutterLineW + gutterGap + gutterModelW + 50;
    const rightMargin = 56;

    const colGap = 24;
    const rowH = 118, rowGap = 50;
    const maxRows = Math.max(1, global.order.length);
    const totalH = padTop + maxRows * rowH + (maxRows - 1) * rowGap + padBottom + 60;
    dom.style.height = totalH + "px";

    const width = dom.clientWidth || 1200;
    const nCols = Math.max(1, columns.length);
    const colWidth = Math.max(260, Math.floor((width - leftMargin - rightMargin - (nCols - 1) * colGap) / nCols));
    const totalChartWidth = leftMargin + nCols * (colWidth + colGap) - colGap + rightMargin;
    dom.style.width = totalChartWidth + "px";

    const inst = ec.init(dom);

    const yAxisMetaMap = {};

    function buildOption() {
      const grids = [], xAxes = [], yAxes = [], series = [], graphics = [], dataZoom = [];

      let xAxisCountSoFar = 0;
      const colAxisIndexRange = [];

      columns.forEach((col, colIdx) => {
        const { xTicks, rows } = col;
        const colLeft = leftMargin + colIdx * (colWidth + colGap);
        const hasRows = rows.length > 0;

        let curTop = padTop;
        rows.forEach((row, rIdx) => {
          const isBottom = (rIdx === rows.length - 1);
          const gridIndex = grids.length;
          grids.push({ left: colLeft, top: curTop, width: colWidth, height: rowH });

          const xAxisIndex = xAxes.length;
          xAxes.push({
            type: "category",
            gridIndex,
            data: xTicks,
            axisTick: { alignWithLabel: true, lineStyle: { color: CHART_THEME.axisTick, width: 1 } },
            axisLabel: { show: isBottom, rotate: 90, margin: 12, color: CHART_THEME.axisLabel },
            axisLine: { onZero: false, lineStyle: { color: CHART_THEME.axisLine, width: 1 } },
            triggerEvent: true
          });

          const gMax = Math.max(1, Math.ceil((row.maxG || 1) * 1.2));
          const yLeftIndex = yAxes.length;
          yAxes.push({
            type: "value",
            gridIndex,
            min: 0, max: gMax,
            splitLine: { show: true, lineStyle: { color: CHART_THEME.splitLine, width: 1, type: "dashed" } },
            axisLabel: { show: true, color: CHART_THEME.axisLabel },
            axisLine: { lineStyle: { color: CHART_THEME.axisLine, width: 1 } },
            axisTick: { lineStyle: { color: CHART_THEME.axisTick, width: 1 } },
            triggerEvent: true
          });

          const dBaseMax = Math.max(1, (row.maxD || 0) * 1.4);
          const mlMax = Math.max(0, (row?.spec?.ooc || 0), (row?.spec?.oos || 0));
          const yRightMax = Math.max(dBaseMax, mlMax ? mlMax * 1.05 : 0);
          const yRightIndex = yAxes.length;
          yAxes.push({
            type: "value",
            gridIndex,
            min: 0, max: yRightMax,
            splitLine: { show: false },
            axisLabel: { show: false, color: CHART_THEME.axisLabel },
            axisLine: { lineStyle: { color: CHART_THEME.axisLine, width: 1 } },
            axisTick: { lineStyle: { color: CHART_THEME.axisTick, width: 1 } }
          });

          // 記錄這個 yLeftIndex 對應哪個 column / row
          yAxisMetaMap[yLeftIndex] = { colIndex: colIdx, local: rIdx };

          const rowKey = `${colIdx}|${row.line_id}|${row.model}|${row.glass_type}|${rIdx}`;
          const barIdG  = `barG:${colIdx}:${rIdx}`;
          const barIdCG = `barCG:${colIdx}:${rIdx}`;
          const scId    = `sc:${colIdx}:${rIdx}`;

          // 主群片數
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
            itemStyle: {
              color: CHART_COLOR.glassTotalBar
            },
            data: row.glasses.map((v, i) => ({
              value: v,
              itemStyle: {
                opacity: calcOpacity(colIdx, rowKey, i)
              }
            })),
            universalTransition: true
          });

          // 綜合 defect 片數
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
            itemStyle: {
              color: CHART_COLOR.defectGlassBar
            },
            label: { show: false },
            data: (row.codeGlasses || []).map((v, i) => ({
              value: v,
              itemStyle: {
                opacity: calcOpacity(colIdx, rowKey, i)
              }
            })),
            universalTransition: true
          });

          const mlData = [];
          if (row?.spec?.ooc != null && isFinite(row.spec.ooc)) {
            mlData.push({
              name: "OOC",
              yAxis: row.spec.ooc,
              lineStyle: { type: "dashed", width: 1.5, color: CHART_COLOR.oocLine }
            });
          }
          if (row?.spec?.oos != null && isFinite(row.spec.oos)) {
            mlData.push({
              name: "OOS",
              yAxis: row.spec.oos,
              lineStyle: { type: "dashed", width: 1.5, color: CHART_COLOR.oosLine }
            });
          }

          // density 點
          series.push({
            id: scId,
            name: "density",
            type: "scatter",
            xAxisIndex,
            yAxisIndex: yRightIndex,
            symbolSize: 7,
            z: 50,
            zlevel: 1,
            itemStyle: {
              color: CHART_COLOR.densityPoint
            },
            label: {
              show: true,
              position: "top",
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
            data: row.density.map((v, i) => ({
              value: v,
              itemStyle: {
                opacity: v == null ? 0 : calcOpacity(colIdx, rowKey, i)
              }
            })),
            connectNulls: false,
            universalTransition: true,
            markLine: mlData.length
              ? {
                  symbol: "none",
                  silent: false,
                  data: mlData
                }
              : undefined
          });

          curTop += rowH + (isBottom ? 0 : rowGap);
        });

        const xStart = xAxisCountSoFar;
        const xEnd = xStart + rows.length;
        colAxisIndexRange.push({ colIndex: colIdx, xStart, xEnd });
        xAxisCountSoFar = xEnd;

        if (hasRows) {
          const xIdxs = Array.from({ length: rows.length }, (_, i) => xStart + i);
          dataZoom.push(
            { type: "inside", xAxisIndex: xIdxs, filterMode: "filter" },
            { type: "slider", xAxisIndex: xIdxs, left: colLeft, bottom: 8, width: colWidth, height: 16, brushSelect: false }
          );
        }
      });

      // 左側 line / model 標籤
      const lineX = 16 + Math.floor(26 / 2);
      const modelX = 16 + 26 + 8 + Math.floor(26 / 2);

      (global.lineGroups || []).forEach(gp=>{
        const top = padTop + gp.start * (rowH + rowGap);
        const bottom = padTop + gp.end * (rowH + rowGap) + rowH;
        graphics.push({
          type: "text",
          left: lineX-15,
          top: top,
          style: { text: gp.line_id, fill: "#f38aff", fontWeight: 700, fontSize: 12, textAlign: "center" }
        });
      });

      (global.order || []).forEach((rm, idx)=>{
        const top = padTop + idx * (rowH + rowGap);
        const centerY = top + rowH / 2;
        const label = rm.glass_type
          ? `${rm.model} (${rm.glass_type})`
          : rm.model;
        graphics.push({
          type: "text",
          left: modelX-60,
          top: centerY,
          style: { text: label, fill: "#b1ffea", fontWeight: 600, fontSize: 11, textAlign: "center" }
        });
      });

      return {
        animation: true,
        legend: {
          top: LEGEND_TOP,
          right: LEGEND_RIGHT,
          itemGap: LEGEND_ITEM_GAP,
          data: ["glass (total)", "defect glass", "density"],
          selected: {
            "glass (total)": true,
            "defect glass": false,
            "density": true
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
            const parts = String(p0.seriesId || "").split(":");
            // seriesId: 'barG:<colIdx>:<rIdx>' / 'barCG:<colIdx>:<rIdx>' / 'sc:<colIdx>:<rIdx>'
            const colIdx = Number(parts[1] || 0);
            const rIdx = Number(parts[2] || 0);

            const col = (columns || [])[colIdx] || null;
            const tickStr = (p0.axisValue != null)
              ? String(p0.axisValue)
              : (col ? col.xTicks[p0.dataIndex] : "");
            const row = col ? col.rows[rIdx] : null;
            if (!row || !tickStr) return tickStr;

            const pick = rowsByCriteria(
              rawRows,
              {
                line: row.line_id,
                model: row.model,
                glass_type: row.glass_type,
                tick: tickStr
              }
            );
            const repr = pick?.[0] || null;
            if (!repr) return tickStr;

            const i = (n) => (n == null || !isFinite(n)) ? "" : String(Math.trunc(Number(n)));
            const f = (n) => { const x = Number(n); return Number.isFinite(x) ? x.toFixed(2) : ""; };

            let dens = "";
            const idx = col.xTicks.indexOf(tickStr);
            if (idx >= 0) dens = f(row.density[idx]);

            const gTotal = (idx >= 0) ? row.glasses[idx] : null;
            const dTotal = repr.maingroup_defect_count ?? repr.Total_defect_count ?? repr.n_rows ?? null;

            let gCode = null, dCode = 0, S = 0, M = 0, L = 0, O = 0;

            if (idx >= 0 && Array.isArray(row.codeGlasses)) {
              gCode = row.codeGlasses[idx];
            }

            pick.forEach((rec) => {
              dCode += Number(rec.defect_code_count ?? rec.defect_num ?? rec.n_rows ?? 0);
              S     += Number(rec.small_defect_count  ?? rec.s_count ?? 0);
              M     += Number(rec.middle_defect_count ?? rec.m_count ?? 0);
              L     += Number(rec.large_defect_count  ?? rec.l_count ?? 0);
              O     += Number(rec.over_defect_count   ?? rec.o_count ?? 0);
            });

            const sizeLine = [['S',S],['M',M],['L',L],['O',O]]
              .filter(([,v])=>v>0)
              .map(([k,v])=>`${k}${i(v)}`)
              .join(', ');

            const kv = [
              ['density',                      dens],
              ['total glass count(hourly)',    i(gTotal)],
              ['total defect count(hourly)',   i(dTotal)],
              ['defect glass count',           i(gCode)],
              ['defect count',                 i(dCode)],
              ['S/M/L/O',                      sizeLine]
            ].filter(([,v])=>v!=="" && v!=null);

            return kv.map(([k,v])=>`<div><b>${k}</b>: ${v}</div>`).join("");
          }
        },
        axisPointer: { link: [] },
        brush: {
          toolbox: [],
          brushMode: "single",
          brushType: "lineX",
          xAxisIndex: Array.from({length: xAxisCountSoFar}, (_,i)=>i)
        },
        grid: grids,
        xAxis: xAxes,
        yAxis: yAxes,
        series,
        graphic: graphics,
        dataZoom,
        __colAxisIndexRange: colAxisIndexRange,
        __yAxisMetaMap: yAxisMetaMap
      };
    }

    let option = buildOption();
    inst.setOption(option);

    function showRowsInTable(rows) {
      if (window.AOI_INSPECTION?.Table?.showRows) {
        window.AOI_INSPECTION.Table.showRows(rows, window.AOI_INSPECTION?.state?.paramDict);
      }
    }


    let lastClickAt = 0;

    inst.off("click");
    inst.on("click", async function (ev) {
      // 1) 點 xAxis：只用 tick 過濾 summary rows
      if (ev?.componentType === "xAxis") {
        const xAxisIndex = ev?.xAxisIndex ?? ev?.axisIndex ?? 0;
        const ranges = inst.getOption().__colAxisIndexRange || [];
        let found = null;
        for (const r of ranges) {
          if (xAxisIndex >= r.xStart && xAxisIndex < r.xEnd) { found = r; break; }
        }
        if (!found) return;

        const tickStr = String(ev.value);
        const pick = rowsByCriteria(rawRows, { tick: tickStr });
        console.log("[inspection charts] xAxis click summary rows:", pick);
        showRowsInTable(pick);

      // 2) 點 yAxis：選該行 (line, model, glass_type) 的所有 rows
      } else if (ev?.componentType === "yAxis") {
        const yIdx = ev?.yAxisIndex;
        const metaMap = inst.getOption().__yAxisMetaMap || {};
        const hit = metaMap[yIdx];
        if (!hit) return;
        const col = columns[hit.colIndex];
        if (!col) return;
        const row = col.rows[hit.local];
        if (!row) return;
        const pick = rowsByCriteria(
          rawRows,
          { line: row.line_id, model: row.model, glass_type: row.glass_type }
        );
        console.log("[inspection charts] yAxis click summary rows:", pick);
        showRowsInTable(pick);

      // 3) 點 series (bar / density)：同時更新 table + 呼叫 defect_map，並 console.log summary rows
    } else if (ev?.componentType === "series") {
      const now = Date.now();
      if (now - lastClickAt < 300) return;
      lastClickAt = now;
    
      const sId = ev.seriesId || "";
      console.log('seriesId', sId);
      const parts = sId.split(":");
      const colIdx = Number(parts[1] || 0);
      const rIdx   = Number(parts[2] || 0);
    
      const col = columns[colIdx];
      if (!col) return;
    
      const dataIdx = ev.dataIndex;
      const tickStr = col.xTicks[dataIdx];
      const row = col.rows[rIdx];
      if (!tickStr || !row) return;
    
      // 1) 先抓對應的 summary rows（你現在 console.log 出來的那個陣列）
      const pick = rowsByCriteria(
        rawRows,
        {
          line:       row.line_id,
          model:      row.model,
          glass_type: row.glass_type,
          tick:       tickStr
        }
      );
    
      // ★ 這裡是你現在看到的資料
      //console.log("[inspection charts] series click summary rows:", pick);
    
      // 先照舊丟給 table 用
      showRowsInTable(pick);
    
      // 2) 再把要給 defect_map 的 payload rows 組出來（只留 5 個欄位）
      try {
        if (Array.isArray(pick) && pick.length > 0 &&
            window.AOI_INSPECTION?.Map?.fetchAndRender) {
    
          const defectRows = pick.map(r => ({
            glass_type: r.glass_type,
            line_id:    r.line_id,
            glass:      r.glass,
            model:      r.model,
            pi_hour:    r.pi_hour || tickStr
          }));
    
          console.log("[inspection charts] payload to defect_map:", defectRows);
    
          // 直接把「乾淨 payload」丟給 defect_map.js
          window.AOI_INSPECTION.Map.fetchAndRender(defectRows);
        }
      } catch (err) {
        console.error("[inspection charts] defect_map fetch error:", err);
      }
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
          if (axisIndex >= r.xStart && axisIndex < r.xEnd) { found = r; break; }
        }
        if (!found) return;

        const { colIndex } = found;
        const [sidx, eidx] = idxRange;
        const lo = Math.min(sidx, eidx), hi = Math.max(sidx, eidx);
        for (let i = lo; i <= hi; i++) {
          interopState.selectedTicks.add(`${i}|${colIndex}`);
        }
      });

      refreshOpacity(inst, columns);
    });

    renderBigChart.optionBuilder = ()=>{
      const op = buildOption();
      inst.setOption(op, true, true);
      refreshOpacity(inst, columns);
      return op;
    };

    window.addEventListener("resize", () => {
      inst.resize();
      if (typeof renderBigChart.optionBuilder === "function") {
        renderBigChart.optionBuilder();
      }
    });
  }

  function refreshOpacity(inst, columns) {
    const updates = [];
    columns.forEach((col, colIdx) => {
      const { rows } = col;
      rows.forEach((row, rIdx) => {
        const rowKey = `${colIdx}|${row.line_id}|${row.model}|${row.glass_type}|${rIdx}`;

        const barIdG  = `barG:${colIdx}:${rIdx}`;
        const newBarDataG = (row.glasses || []).map((v, i) => ({
          value: v,
          itemStyle: {
            opacity: calcOpacity(colIdx, rowKey, i)
          }
        }));
        updates.push({ id: barIdG, data: newBarDataG });

        const barIdCG = `barCG:${colIdx}:${rIdx}`;
        const newBarDataCG = (row.codeGlasses || []).map((v, i) => ({
          value: v,
          itemStyle: {
            opacity: calcOpacity(colIdx, rowKey, i)
          }
        }));
        updates.push({ id: barIdCG, data: newBarDataCG });

        const scId = `sc:${colIdx}:${rIdx}`;
        const newScData = (row.density || []).map((v, i) => ({
          value: v,
          itemStyle: {
            opacity: v == null ? 0 : calcOpacity(colIdx, rowKey, i)
          }
        }));
        updates.push({ id: scId, data: newScData });
      });
    });
    if (updates.length) inst.setOption({ series: updates }, false, false);
  }

  MOD.Charts.render = function (rows, _paramDict) {
    const dom = (function ensureHost(){
      const host = document.querySelector("#inspection-facet");
      if (!host) return null;
      host.innerHTML = "";
      host.style.overflow = "visible";
      const chartDiv = document.createElement("div");
      chartDiv.className = "aoi-bigchart";
      chartDiv.style.height = "320px";
      host.appendChild(chartDiv);
      return chartDiv;
    })();
    if (!dom) return;

    const proSpecDict = (window.AOI_INSPECTION?.state?.ProSpecDict?.default_spec_table) || null;
    const specIndex = buildSpecIndex(proSpecDict);
    const global = buildGlobalRowOrder(rows || []);
    const columns = (function build(){
      const sizes = getSelectedSizes();
      return buildColumnsByAoiCode(rows || [], global.order, specIndex, sizes);
    })();
    if (!columns.length) { dom.innerHTML = "<div class='muted'>沒有資料</div>"; return; }
    renderBigChart(dom, columns, global, rows);
  };
})();
