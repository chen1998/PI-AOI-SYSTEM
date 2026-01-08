// static/js/aoi_density/chart.js
(function () {
  const MOD = (window.AOI_DENSITY = window.AOI_DENSITY || {});
  MOD.Charts = MOD.Charts || {};

  const $ = (sel, root = document) => root.querySelector(sel);
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

  // 所有圖上顏色都集中在這裡
  const CHART_COLOR = {
    glassTotalBar:   "#9aa3b2", // 總片數（灰色柱狀）
    defectGlassBar:  "#FF851B", // 有缺陷片數（橘色柱狀）
    densityPoint:    "#FF4136", // 密度（紅色圓點）

    // Default SPEC 線
    defaultSpecOOC:  "#FFDC00", // 預設 OOC
    defaultSpecOOS:  "#CE0000", // 預設 OOS

    // FIXED SPEC 線
    fixedSpecOOC:    "#FFDC00", // FIXED OOC
    fixedSpecOOS:    "#CE0000"  // FIXED OOS
  };

  // ===================== 時間處理 =====================

  function fmtYYMMDDHH(d) {
    if (!(d instanceof Date) || isNaN(d)) return "";
    const yy = String(d.getFullYear()).slice(-2);
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    const hh = String(d.getHours()).padStart(2, "0");
    return `${yy}-${mm}-${dd} ${hh}`;
  }

  function parsePiHourKeyToDate(key) {
    const d = new Date(String(key).replace(" ", "T"));
    return isNaN(d) ? null : d;
  }

  // ===================== defect size + SPEC 工具 =====================

  function getSelectedSizes() {
    try {
      const ui = window.AOI_DENSITY?.readFiltersFromUI?.();
      const ds = ui?.defect_size;
      if (Array.isArray(ds) && ds.length) return ds;
    } catch (e) {}
    return ["S","M","L","O"];
  }

  // 把 ['L','O'] → "LO"，'OL' → "LO"
  function canonicalSizeKeyFromList(list) {
    if (!Array.isArray(list) || !list.length) return "";
    const chars = list
      .map(s => String(s).trim().toUpperCase()[0])
      .filter(ch => "SMLO".includes(ch));
    const uniq = Array.from(new Set(chars)).sort();  // S,L,M,O 會排序成 L,M,O,S，但我們兩邊都用 canonical 就沒差
    return uniq.join("");
  }

  function canonicalSizeKeyFromString(s) {
    if (!s) return "";
    const chars = String(s)
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

  // 解析 "S:1 M:0 L:0 O:0 T:1" 或 {S:1,M:0,L:0,O:0,T:1}
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

  // === Default SPEC 索引：model + ai_code_1 + SIZE_TYPE ===
  function buildDefaultSpecIndex(rows) {
    const idx = {}; // idx[model][code][sizeKey] = { ooc, oos }
    if (!Array.isArray(rows)) return idx;
    rows.forEach(r => {
      if (!r) return;
      const model = String(r.model || r.MODEL_ID || "").trim();
      const code  = String(r.ai_code_1 || r.DEFECT_CODE || "").trim();
      const sizeKey = canonicalSizeKeyFromString(r.SIZE_TYPE || r.size_type || "");
      if (!model || !code || !sizeKey) return;

      const ooc = toNum(r.OOC);
      const oos = toNum(r.OOS);
      if (ooc == null && oos == null) return;

      (((idx[model] = idx[model] || {})[code] = idx[model][code] || {})[sizeKey] = {
        ooc, oos
      });
    });
    //console.log("[Charts] buildDefaultSpecIndex rows:", rows.length, "index models:", Object.keys(idx).length);
    return idx;
  }

  function pickDefaultSpec(defaultIdx, model, code, sizeKey) {
    const byModel = defaultIdx?.[model];
    if (!byModel) return null;
    const byCode = byModel[code];
    if (!byCode) return null;
    if (sizeKey && byCode[sizeKey]) return byCode[sizeKey];
    // 若沒有完全匹配的 sizeKey，就拿第一個
    const anyKey = Object.keys(byCode)[0];
    return anyKey ? byCode[anyKey] : null;
  }

  // === FIXED SPEC 索引：
  // key = line_id|aoi|model|ai_code_1|recipe_id|glass_type|sizeKey
  function buildFixedSpecIndex(rows) {
    const idx = {};
    if (!Array.isArray(rows)) return idx;
    rows.forEach(r => {
      if (!r) return;
      const line   = String(r.line_id || "").trim();
      const aoi    = String(r.aoi || "").trim();
      const model  = String(r.model || "").trim();
      const code   = String(r.ai_code_1 || "").trim();
      const recipe = String(r.recipe_id || "").trim();
      const side   = String(r.glass_type || "").trim();
      const sizeKey = canonicalSizeKeyFromString(r.size_key || r.SIZE_KEY || "");
      if (!line || !aoi || !model || !code || !recipe || !side || !sizeKey) return;

      const ooc = toNum(r.OOC);
      const oos = toNum(r.OOS);
      if (ooc == null && oos == null) return;

      const key = [line, aoi, model, code, recipe, side, sizeKey].join("|");
      idx[key] = { ooc, oos };
    });
    //console.log("[Charts] buildFixedSpecIndex rows:", rows.length, "index keys:", Object.keys(idx).length);
    return idx;
  }

  function pickFixedSpec(fixedIdx, line, aoi, model, code, recipe, side, sizeKey) {
    if (!fixedIdx) return null;
    const exactKey = [line, aoi, model, code, recipe, side, sizeKey].join("|");
    if (fixedIdx[exactKey]) return fixedIdx[exactKey];

    // 沒有完全匹配 sizeKey：退而求其次，只要 line+aoi+model+code+recipe+side 相同就拿第一筆
    const prefix = [line, aoi, model, code, recipe, side].join("|") + "|";
    const keys = Object.keys(fixedIdx).filter(k => k.startsWith(prefix));
    if (!keys.length) return null;
    return fixedIdx[keys[0]];
  }

  // === Chart 友善欄位讀取（相容舊欄位） ===
  const U = {
    aoi:   r => String(r.aoi_tool ?? r.aoi ?? ""),
    code:  r => String(r.defect_code ?? r.ai_code_1 ?? ""),
    line:  r => String(r.line ?? r.line_id ?? ""),
    model: r => String(r.model_id ?? r.model ?? ""),
    tick:  r => String(r.tick_str ?? r.pi_hour ?? ""),
    g:     r => Number(r.glass_num ?? r.n_glasses ?? 0),
    r:     r => Number(r.defect_num ?? r.n_rows ?? 0),
    s:     r => Number(r.s_count ?? r.small_defect_count ?? 0),
    m:     r => Number(r.m_count ?? r.middle_defect_count ?? 0),
    l:     r => Number(r.l_count ?? r.large_defect_count ?? 0),
    o:     r => Number(r.o_count ?? r.over_defect_count ?? 0),
    codeG: r => Number(r.code_glass_num ?? r.defect_code_glass_count ?? 0),
    side:  r => String(r.glass_type ?? "all")
  };

  // ===================== 全局排序 =====================

  function buildGlobalRowOrder(rows){
    const byLine = new Map();
    (rows||[]).forEach(r=>{
      const line = U.line(r), model = U.model(r);
      if(!line || !model) return;
      if(!byLine.has(line)) byLine.set(line, new Set());
      byLine.get(line).add(model);
    });
    const lines = Array.from(byLine.keys()).sort();
    const order = [];
    lines.forEach(line=>{
      const models = Array.from(byLine.get(line)).sort();
      models.forEach(m=> order.push({ line_id: line, model: m }));
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

  // ===================== 聚合 + SPEC 填入 =====================

  function buildColumnsByAoiCode(rows, globalOrder, defaultSpecIndex, fixedSpecIndex, selectedSizesArr){
    const selected = new Set(
      selectedSizesArr && selectedSizesArr.length ? selectedSizesArr : ["S","M","L","O"]
    );
    const selectedSizeKey = canonicalSizeKeyFromList(Array.from(selected));
    //console.log("[Charts] selectedSizes:", Array.from(selected), "sizeKey:", selectedSizeKey);

    const agg = {};
    const ticksByAoiCode = {};

    (rows || []).forEach((r) => {
      const aoi = U.aoi(r), code = U.code(r), line = U.line(r), model = U.model(r), tickRaw = U.tick(r);
      if (!aoi || !code || !line || !model || !tickRaw) return;

      const d = parsePiHourKeyToDate("20" + tickRaw);
      const tick = d ? fmtYYMMDDHH(d) : tickRaw;

      const key = `${aoi}|${code}`;
      (ticksByAoiCode[key] = ticksByAoiCode[key] || new Set()).add(tick);

      const A = (agg[aoi] = agg[aoi] || {});
      const C = (A[code] = A[code] || {});
      const L = (C[line] = C[line] || {});
      const M = (L[model] = L[model] || {});
      const T = (M[tick] = M[tick] || { g: 0, r: 0, cg: 0, rows: [] });

      T.g  += U.g(r);
      T.r  += U.r(r);
      T.cg += U.codeG(r);
      T.rows.push(r);
    });

    function calcSelectedBySize(bucketRows){
      const perGlass = new Map();
      let totalS = 0, totalM = 0, totalL = 0, totalO = 0;

      bucketRows.forEach(rec => {
        const s = Number(rec.s_count ?? rec.small_defect_count ?? 0);
        const m = Number(rec.m_count ?? rec.middle_defect_count ?? 0);
        const l = Number(rec.l_count ?? rec.large_defect_count  ?? 0);
        const o = Number(rec.o_count ?? rec.over_defect_count   ?? 0);
        totalS += s;
        totalM += m;
        totalL += l;
        totalO += o;

        const gdc = rec.glass_defect_count;
        if (gdc && typeof gdc === "object" && !Array.isArray(gdc)) {
          Object.entries(gdc).forEach(([gid, stat]) => {
            const st = parseSizeStats(stat);
            const cur = perGlass.get(gid) || { S:0, M:0, L:0, O:0 };
            cur.S += st.S;
            cur.M += st.M;
            cur.L += st.L;
            cur.O += st.O;
            perGlass.set(gid, cur);
          });
        }
      });

      const defectSel =
        (selected.has("S") ? totalS : 0) +
        (selected.has("M") ? totalM : 0) +
        (selected.has("L") ? totalL : 0) +
        (selected.has("O") ? totalO : 0);

      let glassSel = 0;
      if (perGlass.size > 0) {
        perGlass.forEach(v => {
          const hit =
            (selected.has("S") && v.S > 0) ||
            (selected.has("M") && v.M > 0) ||
            (selected.has("L") && v.L > 0) ||
            (selected.has("O") && v.O > 0);
          if (hit) glassSel += 1;
        });
      } else {
        bucketRows.forEach(rec => {
          const v = Number(
            rec.defect_code_glass_count ??
            rec.code_glass_num ??
            0
          );
          if (v > glassSel) glassSel = v;
        });
      }

      return { glassSel, defectSel, s: totalS, m: totalM, l: totalL, o: totalO };
    }

    const columns = [];
    const loggedNoFixedSpec = new Set();
    const loggedNoDefaultSpec = new Set();

    Object.keys(agg).sort().forEach((aoi) => {
      const perCode = agg[aoi];
      Object.keys(perCode).sort().forEach((code) => {
        const xTicks = Array.from(ticksByAoiCode[`${aoi}|${code}`] || [])
          .sort((a,b)=> new Date("20"+a.replace(" ","T")) - new Date("20"+b.replace(" ","T")));

        const rowsOut = globalOrder.map(({line_id, model})=>{
          const bucket = (((agg[aoi]||{})[code]||{})[line_id]||{})[model] || {};
          const glasses      = [];
          const codeGlasses  = [];
          const density      = [];
          const sArr = [], mArr = [], lArr = [], oArr = [], defSelArr = [];

          let repRecipe = "";
          let repGlassType = "";

          xTicks.forEach(tk=>{
            const T = bucket[tk] || { g:0, rows:[] };
            const g = Number(T.g || 0);
            glasses.push(g);

            const { glassSel, defectSel, s, m, l, o } = calcSelectedBySize(T.rows || []);
            codeGlasses.push(glassSel);
            defSelArr.push(defectSel);
            sArr.push(s); mArr.push(m); lArr.push(l); oArr.push(o);

            density.push(g > 0 ? (defectSel / g) : null);

            if ((!repRecipe || !repGlassType) && Array.isArray(T.rows) && T.rows.length) {
              const found = T.rows.find(rr => rr.recipe_id || rr.recipe || rr.recipeId || rr.glass_type);
              if (found) {
                repRecipe = String(found.recipe_id ?? found.recipe ?? found.recipeId ?? "").trim();
                repGlassType = String(found.glass_type ?? found.glass_side ?? "").trim();
              }
            }
          });

          const specDefault = pickDefaultSpec(defaultSpecIndex, model, code, selectedSizeKey);
          const specFixed   = pickFixedSpec(
            fixedSpecIndex,
            line_id,
            aoi,
            model,
            code,
            repRecipe,
            repGlassType || "all",
            selectedSizeKey
          );

          const keyBase = `${line_id}|${aoi}|${model}|${code}|${repRecipe}|${repGlassType}|${selectedSizeKey}`;
          if (!specDefault) {
            if (!loggedNoDefaultSpec.has(keyBase)) {
              //console.log("[Charts] no DEFAULT SPEC hit for:", keyBase);
              loggedNoDefaultSpec.add(keyBase);
            }
          }
          if (!specFixed) {
            if (!loggedNoFixedSpec.has(keyBase)) {
              //console.log("[Charts] no FIXED SPEC hit for:", keyBase);
              loggedNoFixedSpec.add(keyBase);
            }
          }

          return {
            aoi, code, line_id, model,
            glasses,
            codeGlasses,
            density,
            sArr, mArr, lArr, oArr, defSelArr,
            maxG: Math.max(0, ...glasses, ...codeGlasses),
            maxD: Math.max(0, ...density.filter(x=>x!=null)),
            specDefault: specDefault || null,
            specFixed:   specFixed   || null
          };
        });

        columns.push({ aoi, code, xTicks, rows: rowsOut });
      });
    });

    return columns;
  }

  // ===================== 畫布/互動狀態 =====================

  function ensureHost() {
    const host = document.querySelector("#aoi_density-facet");
    if (!host) return null;
    host.innerHTML = "";
    host.style.overflow = "visible";
    const chartDiv = document.createElement("div");
    chartDiv.className = "aoi-bigchart";
    chartDiv.style.height = "320px";
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

  function rowsByCriteria(allRows, criteria) {
    return (allRows || []).filter(r => {
      if (criteria.aoi && U.aoi(r) !== criteria.aoi) return false;
      if (criteria.code && U.code(r) !== criteria.code) return false;
      if (criteria.line && U.line(r) !== criteria.line) return false;
      if (criteria.line_id && U.line(r) !== criteria.line_id) return false;
      if (criteria.model && U.model(r) !== criteria.model) return false;
      if (criteria.tick && (U.tick(r) !== criteria.tick && (("20"+U.tick(r)) !== criteria.tick))) return false;
      return true;
    });
  }

  function formatTooltipValue(v) {
    if (v == null) return "";
    if (Array.isArray(v)) return v.map(x => String(x).trim()).join("<br/>");
    if (typeof v === "object") {
      try { return Object.entries(v).map(([k, val]) => `${k}: ${val}`).join("<br/>"); }
      catch { return String(v); }
    }
    const s = String(v);
    return s.includes(",")
      ? s.split(",").map(x => x.trim()).filter(Boolean).join("<br/>")
      : s;
  }

  // ===================== 主繪圖 =====================

  function renderBigChart(dom, columns, global, rawRows) {
    const ec = window.echarts;
    if (!ec) return;

    const LEGEND_TOP = -50, LEGEND_RIGHT = 10, LEGEND_ITEM_GAP = 18, LEGEND_BLOCK_H = 42;
    const TITLE_GAP = 12, HEADER_TEXT_H = 32;
    const padTop = LEGEND_BLOCK_H + TITLE_GAP + HEADER_TEXT_H;
    const padBottom = 44;

    const baseLeft = 16, gutterLineW = 26, gutterGap = 8, gutterModelW = 26;
    const leftMargin = baseLeft + gutterLineW + gutterGap + gutterModelW + 25;
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

    const groups = [];
    let curAoi = null, start = 0;
    columns.forEach((c, idx) => {
      if (c.aoi !== curAoi) {
        if (curAoi != null) groups.push({ aoi: curAoi, startCol: start, count: idx - start });
        curAoi = c.aoi; start = idx;
      }
      if (idx === columns.length - 1) {
        groups.push({ aoi: c.aoi, startCol: start, count: idx - start + 1 });
      }
    });

    const yAxisMetaMap = {};

    function buildOption() {
      const grids = [], xAxes = [], yAxes = [], series = [], graphics = [], dataZoom = [];

      let xAxisCountSoFar = 0;
      const colAxisIndexRange = [];

      columns.forEach((col, colIdx) => {
        const { aoi, code, xTicks, rows } = col;
        const colLeft = leftMargin + colIdx * (colWidth + colGap);
        const hasRows = rows.length > 0;

        graphics.push({
          type: "text",
          left: colLeft + colWidth / 2,
          top: LEGEND_BLOCK_H + 22,
          style: { text: code, fill: "#d4e0ff", fontWeight: 700, fontSize: 12, textAlign: "center" }
        });

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
          const mlMax = Math.max(
            0,
            row?.specDefault?.ooc || 0,
            row?.specDefault?.oos || 0,
            row?.specFixed?.ooc   || 0,
            row?.specFixed?.oos   || 0
          );
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

          yAxisMetaMap[yLeftIndex] = { aoi, code, local: rIdx };

          const rowKey = `${aoi}|${code}|${rIdx}`;
          const barIdG  = `barG:${aoi}:${code}:${rIdx}`;
          const barIdCG = `barCG:${aoi}:${code}:${rIdx}`;
          const scId    = `sc:${aoi}:${code}:${rIdx}`;

          // ① 灰色底柱：主群片數
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
            /*label: {
              show: true,
              position: "top",
              formatter: (p) => {
                const v = (Array.isArray(p.value) ? p.value[1] : p.value);
                return (typeof v === 'number' && isFinite(v) && v > 0) ? String(v) : "";
              },
              fontSize: 10,
              color: CHART_THEME.labelText,
              backgroundColor: CHART_THEME.labelBg,
              padding: CHART_THEME.labelPad,
              borderRadius: CHART_THEME.labelRadius
            },*/
            data: row.glasses.map((v, i) => ({
              value: v,
              itemStyle: {
                opacity: calcOpacity(aoi, code, rowKey, i)
              }
            })),
            universalTransition: true
          });

          // ② 橘色柱：代碼片數（已依尺寸過濾）
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
                opacity: calcOpacity(aoi, code, rowKey, i)
              }
            })),
            universalTransition: true
          });

          // ③ 密度
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
              offset: [3, 0],
              align: "left",
              formatter: (p) => {
                const vv = Array.isArray(p.value) ? p.value[1] : p.value;
                return (typeof vv === "number" && isFinite(vv)) ? vv.toFixed(1) : "";
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
                opacity: v == null ? 0 : calcOpacity(aoi, code, rowKey, i)
              }
            })),
            connectNulls: false,
            universalTransition: true
          });

          // ---- Default SPEC 線 ----
          const dSpec = row.specDefault;
          if (dSpec && (dSpec.ooc != null || dSpec.oos != null)) {
            if (dSpec.ooc != null && isFinite(dSpec.ooc)) {
              series.push({
                name: "預設SPEC",
                type: "line",
                xAxisIndex,
                yAxisIndex: yRightIndex,
                data: xTicks.map(() => dSpec.ooc),
                symbol: "none",
                z: 30,
                zlevel: 1,
                lineStyle: {
                  type: "dashed",
                  width: 1.3,
                  color: CHART_COLOR.defaultSpecOOC
                }
              });
            }
            if (dSpec.oos != null && isFinite(dSpec.oos)) {
              series.push({
                name: "預設SPEC",
                type: "line",
                xAxisIndex,
                yAxisIndex: yRightIndex,
                data: xTicks.map(() => dSpec.oos),
                symbol: "none",
                z: 30,
                zlevel: 1,
                lineStyle: {
                  type: "dashed",
                  width: 1.3,
                  color: CHART_COLOR.defaultSpecOOS
                }
              });
            }
          }

          // ---- FIXED SPEC 線 ----
          const fSpec = row.specFixed;
          if (fSpec && (fSpec.ooc != null || fSpec.oos != null)) {
            if (fSpec.ooc != null && isFinite(fSpec.ooc)) {
              series.push({
                name: "動態SPEC",
                type: "line",
                xAxisIndex,
                yAxisIndex: yRightIndex,
                data: xTicks.map(() => fSpec.ooc),
                symbol: "none",
                z: 31,
                zlevel: 1,
                lineStyle: {
                  type: "dashed",
                  width: 1.3,
                  color: CHART_COLOR.fixedSpecOOC
                }
              });
            }
            if (fSpec.oos != null && isFinite(fSpec.oos)) {
              series.push({
                
                name: "動態SPEC",
                type: "line",
                xAxisIndex,
                yAxisIndex: yRightIndex,
                data: xTicks.map(() => fSpec.oos),
                symbol: "none",
                z: 31,
                zlevel: 1,
                lineStyle: {
                  type: "dashed",
                  width: 1.3,
                  color: CHART_COLOR.fixedSpecOOS
                }
              });
            }
          }

          curTop += rowH + (isBottom ? 0 : rowGap);
        });

        const xStart = xAxisCountSoFar;
        const xEnd = xStart + rows.length;
        colAxisIndexRange.push({ colIndex: colIdx, aoi, code, xStart, xEnd });
        xAxisCountSoFar = xEnd;

        if (hasRows) {
          const xIdxs = Array.from({ length: rows.length }, (_, i) => xStart + i);
          dataZoom.push(
            { type: "inside", xAxisIndex: xIdxs, filterMode: "filter" },
            { type: "slider", xAxisIndex: xIdxs, left: colLeft, bottom: 8, width: colWidth, height: 16, brushSelect: false }
          );
        }
      });

      groups.forEach(g => {
        const left = leftMargin + g.startCol * (colWidth + colGap);
        const right = left + g.count * colWidth + (g.count - 1) * colGap;
        graphics.push({
          type: "text",
          left: (left + right) / 2,
          top: LEGEND_BLOCK_H + 4,
          style: { text: g.aoi, fill: "#89a6ff", fontWeight: 800, fontSize: 13, textAlign: "center" }
        });
      });

      const lineX = 16 + Math.floor(26 / 2);
      const modelX = 16 + 26 + 8 + Math.floor(26 / 2);

      (global.lineGroups || []).forEach(gp=>{
        const top = padTop + gp.start * (rowH + rowGap);
        const bottom = padTop + gp.end * (rowH + rowGap) + rowH;
        graphics.push({
          type: "text",
          left: lineX-15,
          top: top-20,//(top + bottom) / 2,
          //rotation: -Math.PI/2,
          style: { text: gp.line_id, fill: "#f38aff", fontWeight: 700, fontSize: 12, textAlign: "center" }
        });
      });

      (global.order || []).forEach((rm, idx)=>{
        const top = padTop + idx * (rowH + rowGap);
        const centerY = top + rowH / 2;
        graphics.push({
          type: "text",
          left: modelX-60,
          top: centerY,
          //rotation: -Math.PI/2,
          style: { text: rm.model, fill: "#b1ffea", fontWeight: 600, fontSize: 11, textAlign: "center" }
        });
      });

      return {
        animation: true,
        legend: {
          top: 0,
          right: 10,
          itemGap: 18,
          data: ["glass (total)", "defect glass", "density", "預設SPEC", "動態SPEC"],
          selected: {                
            "glass (total)": true,
            "defect glass": true,
            "density": true,
            "預設SPEC": true,
            "動態SPEC": false       // 預設不顯示 FIXED SPEC
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
            const [ , aoi="", code="", rIdxStr="0" ] = String(p0.seriesId||"").split(":");
            const rIdx = Number(rIdxStr) || 0;

            const col = (columns || []).find(c => c.aoi === aoi && c.code === code);
            const tickStr = (p0.axisValue != null)
              ? String(p0.axisValue)
              : (col ? col.xTicks[p0.dataIndex] : "");
            const row = col ? col.rows[rIdx] : null;
            if (!row || !tickStr) return "";

            const pick = rowsByCriteria(rawRows, { aoi, code, line: row.line_id, model: row.model, tick: tickStr });
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
        brush: { toolbox: [], brushMode: "single", brushType: "lineX", xAxisIndex: Array.from({length: xAxisCountSoFar}, (_,i)=>i) },
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
      if (window.AOI_DENSITY?.Table?.showRows) {
        window.AOI_DENSITY.Table.showRows(rows, window.AOI_DENSITY?.state?.paramDict);
      }
    }

    let lastClickAt = 0;
    function buildDefectQueryRow(aoi, code, lineId, model, tickStr, sampleRow) {
      return {
        aoi: aoi,
        pi_hour: tickStr,
        line_id: lineId,
        model: model,
        glass_type: sampleRow?.glass_type ?? "",
        recipe_id: sampleRow?.recipe_id ?? "",
        recipe_comment: sampleRow?.recipe_comment ?? "",
        ai_code_1: code
      };
    }

    inst.off("click");
    inst.on("click", async function (ev) {
      if (ev?.componentType === "xAxis") {
        const xAxisIndex = ev?.xAxisIndex ?? ev?.axisIndex ?? 0;
        const ranges = inst.getOption().__colAxisIndexRange || [];
        let found = null;
        for (const r of ranges) {
          if (xAxisIndex >= r.xStart && xAxisIndex < r.xEnd) { found = r; break; }
        }
        if (!found) return;
        const { aoi, code } = found;
        const tickStr = String(ev.value);
        const pick = rowsByCriteria(rawRows, { aoi, code, tick: tickStr });
        showRowsInTable(pick);

      } else if (ev?.componentType === "yAxis") {
        const yIdx = ev?.yAxisIndex;
        const metaMap = inst.getOption().__yAxisMetaMap || {};
        const hit = metaMap[yIdx];
        if (!hit) return;
        const col = columns.find(c => c.aoi === hit.aoi && c.code === hit.code);
        if (!col) return;
        const row = col.rows[hit.local];
        if (!row) return;
        const pick = rowsByCriteria(rawRows, { line: row.line_id, model: row.model });
        showRowsInTable(pick);

      } else if (ev?.componentType === "series") {
        const now = Date.now();
        if (now - lastClickAt < 300) return;
        lastClickAt = now;

        const sId = ev.seriesId || "";
        const parts = sId.split(":");
        const aoi = parts[1], code = parts[2], rIdx = Number(parts[3] || 0);
        const colIndex = columns.findIndex(c => c.aoi===aoi && c.code===code);
        if (colIndex < 0) return;
        const col = columns[colIndex];
        const dataIdx = ev.dataIndex;
        const tickStr = col.xTicks[dataIdx];
        const row = col.rows[rIdx];
        if (!tickStr || !row) return;

        const pick = rowsByCriteria(rawRows, { aoi, code, line: row.line_id, model: row.model, tick: tickStr });
        showRowsInTable(pick);

        try {
          if (Array.isArray(pick) && pick.length > 0 && API?.postDefectMap) {
            const sample = pick[0] || {};
            const filters = buildDefectQueryRow(aoi, code, row.line_id, row.model, tickStr, sample);
            // const res = await API.postDefectMap([filters]);
            // if (res && res.DefectGroupDict && MOD.DefectMap && typeof MOD.DefectMap.render === "function") {
            //   MOD.DefectMap.render(res.DefectGroupDict);
            // }
          }
        } catch (err) {
          console.error("[charts] postDefectMap error:", err);
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

        const { aoi, code } = found;
        const [sidx, eidx] = idxRange;
        const lo = Math.min(sidx, eidx), hi = Math.max(sidx, eidx);
        for (let i = lo; i <= hi; i++) {
          interopState.selectedTicks.add(`${i}|${aoi}|${code}`);
        }
      });

      refreshOpacity(inst, columns);
    });

    function rebuild() {
      const op = buildOption();
      inst.setOption(op, true, true);
      refreshOpacity(inst, columns);
    }

    window.addEventListener("resize", () => {
      inst.resize();
      rebuild();
    });
  }

  function refreshOpacity(inst, columns) {
    const updates = [];
    columns.forEach((col) => {
      const { aoi, code, rows } = col;
      rows.forEach((row, rIdx) => {
        const rowKey = `${aoi}|${code}|${rIdx}`;

        const barIdG  = `barG:${aoi}:${code}:${rIdx}`;
        const newBarDataG = (row.glasses || []).map((v, i) => ({
          value: v,
          itemStyle: {
            opacity: calcOpacity(aoi, code, rowKey, i)
          }
        }));
        updates.push({ id: barIdG, data: newBarDataG });

        const barIdCG = `barCG:${aoi}:${code}:${rIdx}`;
        const newBarDataCG = (row.codeGlasses || []).map((v, i) => ({
          value: v,
          itemStyle: {
            opacity: calcOpacity(aoi, code, rowKey, i)
          }
        }));
        updates.push({ id: barIdCG, data: newBarDataCG });

        const scId = `sc:${aoi}:${code}:${rIdx}`;
        const newScData = (row.density || []).map((v, i) => ({
          value: v,
          itemStyle: {
            opacity: v == null ? 0 : calcOpacity(aoi, code, rowKey, i)
          }
        }));
        updates.push({ id: scId, data: newScData });
      });
    });
    if (updates.length) inst.setOption({ series: updates }, false, false);
  }

  // ===================== 對外介面 =====================

  MOD.Charts.render = function (rows, _paramDict) {
    const dom = ensureHost();
    if (!dom) return;

    // 從 state 抓 ProSpecDict
    let proSpecDict = (window.AOI_DENSITY?.state?.ProSpecDict) || null;
    if (!proSpecDict && _paramDict && _paramDict.ProSpecDict) {
      proSpecDict = _paramDict.ProSpecDict;
    }
    //console.log("[Charts] ProSpecDict:", proSpecDict);

    const defaultRows = proSpecDict && proSpecDict.default_spec_table
      ? Object.values(proSpecDict.default_spec_table)
      : [];
    const fixedRows = proSpecDict && proSpecDict.fixed_spec_table
      ? Object.values(proSpecDict.fixed_spec_table)
      : [];

    //console.log("[Charts] default_spec_table rows:", defaultRows.length);
    //console.log("[Charts] fixed_spec_table rows:", fixedRows.length);

    const defaultSpecIndex = buildDefaultSpecIndex(defaultRows);
    const fixedSpecIndex   = buildFixedSpecIndex(fixedRows);

    const global = buildGlobalRowOrder(rows || []);
    const columns = (function build(){
      const sizes = getSelectedSizes();
      return buildColumnsByAoiCode(rows || [], global.order, defaultSpecIndex, fixedSpecIndex, sizes);
    })();
    if (!columns.length) {
      dom.innerHTML = "<div class='muted'>沒有資料</div>";
      return;
    }
    renderBigChart(dom, columns, global, rows);
  };
})();