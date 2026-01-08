// static/js/aoi_inspection/defect_map.js
// 單一 canvas 顯示所有 defect；以「尺寸 S/M/L/O」著色；右側圖例含 尺寸多選 + Glass 勾選；點擊點開影像；hover 顯示資訊
(function () {
  const MOD = (window.AOI_INSPECTION = window.AOI_INSPECTION || {});
  MOD.Map = MOD.Map || {};

  const CANVAS_ID = "inspection-mini-map";
  const LEGEND_ID = "inspection-map-legend";
  const TIPS_ID   = "inspection-map-tooltip";

  const DEFECT_INFO_KEYS = ["lotid", "recipe", "x", "y", "defect_size", "ai_code_1"];

  const AXIS = { minX: 0, maxX: 1880000, minY: 0, maxY: 1580000 };

  const SIZE_COLORS = { S: "#7FDBFF", M: "#FF851B", L: "#2ECC40", O: "#FF4136" };

  function ensureLayout() {
    const host = document.getElementById("inspection-map-wrap");
    const vp = host?.querySelector(".map-viewport");
    const cvs = document.getElementById(CANVAS_ID);
    if (!vp || !cvs) return null;

    vp.style.display = "flex";
    vp.style.gap = "10px";
    vp.style.alignItems = "stretch";
    vp.style.overflow = "hidden";

    Object.assign(cvs.style, {
      flex: "8 1 0", width: "100%", height: "100%",
      background: "#0f1115", border: "1px solid rgba(255,255,255,0.08)", borderRadius: "6px"
    });

    let legend = document.getElementById(LEGEND_ID);
    if (!legend) {
      legend = document.createElement("div");
      legend.id = LEGEND_ID;
      vp.appendChild(legend);
    }
    Object.assign(legend.style, {
      flex: "2 1 0", minWidth: "160px", display: "flex", flexDirection: "column", gap: "10px",
      background: "#0f1115", border: "1px solid rgba(255,255,255,0.08)", borderRadius: "6px",
      padding: "8px", overflowY: "auto", overflowX: "hidden",
    });

    let tips = document.getElementById(TIPS_ID);
    if (!tips) {
      tips = document.createElement("div");
      tips.id = TIPS_ID;
      document.body.appendChild(tips);
    }
    Object.assign(tips.style, {
      position: "fixed", zIndex: 9999, pointerEvents: "none",
      background: "rgba(0,0,0,0.85)", border: "1px solid rgba(255,255,255,0.15)",
      borderRadius: "6px", padding: "6px 8px",
      font: "12px/1.35 -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif",
      color: "#fff", boxShadow: "0 6px 18px rgba(0,0,0,0.35)", maxWidth: "320px", display: "none",
    });

    return { vp, cvs, legend, tips };
  }

  function niceStep(range) {
    if (!isFinite(range) || range <= 0) return 1;
    const exp = Math.floor(Math.log10(range));
    const frac = range / Math.pow(10, exp);
    const niceFrac = frac < 1.5 ? 1 : frac < 3 ? 2 : frac < 7 ? 5 : 10;
    return niceFrac * Math.pow(10, exp);
  }

  const state = {
    groups: [],
    sizeFilter: new Set(["S","M","L","O"]),
    glassFilter: new Set(),
    hitCache: [],
  };

  function normalizeResponse(resp) {
    const src = resp && resp.DefectGroupDict;
    const out = [];
  
    if (!src) return out;
  
    // --- 新格式：{ SHEET_ID: [ {x,y,size,img}, ... ] } ---
    if (!Array.isArray(src) && typeof src === "object") {
      Object.entries(src).forEach(([gid, arr]) => {
        if (!Array.isArray(arr)) return;
  
        const group = {
          gid,
          label: String(gid),
          points: []
        };
  
        arr.forEach(it => {
          const raw = (it.size ?? "").toString().trim().toUpperCase();
          let bucket = null;
  
          if (["S","M","L","O"].includes(raw)) {
            bucket = raw;
          } else {
            const num = parseInt(raw, 10);
            if (!isNaN(num)) {
              if (num <= 20) bucket = "S";
              else if (num <= 100) bucket = "M";
              else if (num <= 400) bucket = "L";
              else bucket = "O";
            }
          }
  
          group.points.push({
            x: Number(it.x || 0),
            y: Number(it.y || 0),
            bucket,
            rawSize: it.size,
            img: it.img || "",
            chip: it.chip || "",
            recipe_id: it.recipe_id || "",
            meta: {
              lotid: it.lotid ?? it.lot ?? "",
              lot: it.lot ?? "",
              recipe: it.recipe ?? it.recipe_id ?? "",
              x: it.x ?? "",
              y: it.y ?? "",
              defect_size: it.size ?? "",
              ai_code_1: it.ai_code_1 ?? "",
            }
          });
        });
  
        out.push(group);
      });
  
      return out;
    }
  
    // --- 舊格式相容：list，每個元素內有 defect_group ---
    if (Array.isArray(src)) {
      const outMap = new Map();
  
      src.forEach(oneRow => {
        const dg = oneRow?.defect_group || {};
        Object.entries(dg).forEach(([gid, payload]) => {
          if (!outMap.has(gid)) {
            outMap.set(gid, {
              gid,
              label: `${gid}`,
              points: []
            });
          }
          const g = outMap.get(gid);
          (payload.defect_map || []).forEach(it => {
            const raw = (it.size ?? "").toString().trim().toUpperCase();
            let bucket = null;
            if (["S","M","L","O"].includes(raw)) {
              bucket = raw;
            } else {
              const num = parseInt(raw, 10);
              if (!isNaN(num)) {
                if (num <= 20) bucket = "S";
                else if (num <= 100) bucket = "M";
                else if (num <= 400) bucket = "L";
                else bucket = "O";
              }
            }
            g.points.push({
              x: Number(it.x || 0),
              y: Number(it.y || 0),
              bucket,
              rawSize: it.size,
              img: it.img || "",
              chip: it.chip || "",
              recipe_id: it.recipe_id || "",
              meta: {
                glass_id: gid ?? "",
                x: it.x ?? "",
                y: it.y ?? "",
                defect_size: it.size ?? "",
                ai_code_1: it.ai_code_1 ?? "",
              }
            });
          });
        });
      });
  
      return Array.from(outMap.values());
    }
  
    return out;
  }

  function buildLegend(groups) {
    const legend = document.getElementById(LEGEND_ID);
    if (!legend) return;
    legend.innerHTML = "";

    const sizeBox = document.createElement("div");
    sizeBox.style.borderBottom = "1px dashed rgba(255,255,255,0.14)";
    sizeBox.style.paddingBottom = "8px";

    const sHeader = document.createElement("div");
    Object.assign(sHeader.style, { display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:"6px" });

    const sTitle = document.createElement("div");
    Object.assign(sTitle.style, { fontWeight:"700", fontSize:"12px" });
    sTitle.textContent = "尺寸";

    const allSizeSelected = state.sizeFilter.size === 4;
    const sBtn = document.createElement("button");
    sBtn.className = "btn btn-xs btn-secondary";
    sBtn.textContent = allSizeSelected ? "清空" : "全選";
    sBtn.addEventListener("click", ()=>{
      if (state.sizeFilter.size === 4) {
        state.sizeFilter = new Set();
      } else {
        state.sizeFilter = new Set(["S","M","L","O"]);
      }
      buildLegend(state.groups);
      redraw();
    });
    sHeader.append(sTitle, sBtn);
    sizeBox.appendChild(sHeader);

    const sWrap = document.createElement("div");
    Object.assign(sWrap.style, { display:"flex", flexWrap:"wrap", gap:"8px" });

    ["S","M","L","O"].forEach(k=>{
      const item = document.createElement("div");
      Object.assign(item.style, {
        display: "inline-flex", alignItems: "center", gap: "3px",
        padding: "2px 3px", border: "1px solid rgba(255,255,255,0.15)",
        borderRadius: "4px", cursor: "pointer", userSelect: "none",
        background: state.sizeFilter.has(k) ? "rgba(255,255,255,0.06)" : "transparent",
      });

      const sw = document.createElement("span");
      Object.assign(sw.style, { display: "inline-block", width: "14px", height: "14px", borderRadius: "3px", background: SIZE_COLORS[k] || "#999" });

      const label = document.createElement("span");
      label.textContent = k; label.style.fontSize = "12px";

      item.appendChild(sw); item.appendChild(label);
      item.addEventListener("click", ()=>{
        if (state.sizeFilter.has(k)) state.sizeFilter.delete(k);
        else state.sizeFilter.add(k);
        buildLegend(state.groups);
        redraw();
      });

      sWrap.appendChild(item);
    });
    sizeBox.appendChild(sWrap);
    legend.appendChild(sizeBox);

    const glassBox = document.createElement("div");

    const gHeader = document.createElement("div");
    Object.assign(gHeader.style, { display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:"6px" });

    const gTitle = document.createElement("div");
    Object.assign(gTitle.style, { fontWeight:"700", fontSize:"12px" });
    gTitle.textContent = "Glass 篩選";

    const allGids = (groups || []).map(g=>g.gid);
    const allGlassSelected = allGids.length > 0 && state.glassFilter.size === allGids.length;

    const gBtn = document.createElement("button");
    gBtn.className = "btn btn-xs btn-secondary";
    gBtn.textContent = allGlassSelected ? "清空" : "全選";
    gBtn.addEventListener("click", ()=>{
      if (state.glassFilter.size === allGids.length && allGids.length > 0) {
        state.glassFilter = new Set();
      } else {
        state.glassFilter = new Set(allGids);
      }
      buildLegend(state.groups);
      redraw();
    });

    gHeader.append(gTitle, gBtn);
    glassBox.appendChild(gHeader);

    const list = document.createElement("div");
    Object.assign(list.style, { display: "flex", flexDirection: "column", gap: "6px" });

    (groups || [])
      .slice()
      .sort((a,b)=>String(a.label).localeCompare(String(b.label)))
      .forEach(g=>{
        const row = document.createElement("label");
        Object.assign(row.style, {
          display: "flex", alignItems: "center", gap: "8px", cursor: "pointer",
          padding: "4px 6px", borderRadius: "4px",
          border: "1px solid rgba(255,255,255,0.08)",
          background: state.glassFilter.has(g.gid) ? "rgba(255,255,255,0.04)" : "transparent",
        });

        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = state.glassFilter.has(g.gid);
        cb.addEventListener("change", ()=>{
          if (cb.checked) state.glassFilter.add(g.gid);
          else state.glassFilter.delete(g.gid);
          row.style.background = state.glassFilter.has(g.gid) ? "rgba(255,255,255,0.04)" : "transparent";
          buildLegend(state.groups);
          redraw();
        });

        const label = document.createElement("span");
        label.style.fontSize = "12px";
        label.textContent = g.label || g.gid;

        row.appendChild(cb);
        row.appendChild(label);
        list.appendChild(row);
      });

    glassBox.appendChild(list);
    legend.appendChild(glassBox);
  }

  function drawAxes(ctx, w, h) {
    const padL = 60, padR = 18, padT = 12, padB = 48;
    const plotW = Math.max(10, w - padL - padR);
    const plotH = Math.max(10, h - padT - padB);

    const x0 = AXIS.minX, x1 = AXIS.maxX;
    const y0 = AXIS.minY, y1 = AXIS.maxY;
    const xRange = x1 - x0, yRange = y1 - y0;

    const xScale = plotW / (xRange || 1);
    const yScale = plotH / (yRange || 1);

    ctx.strokeStyle = "rgba(255,255,255,0.5)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padL, padT + plotH);
    ctx.lineTo(padL + plotW, padT + plotH);
    ctx.moveTo(padL, padT);
    ctx.lineTo(padL, padT + plotH);
    ctx.stroke();

    ctx.fillStyle = "rgba(255,255,255,0.7)";
    ctx.font = "12px sans-serif";
    ctx.textAlign = "center";

    const X_TICK_TARGET = 12;
    const xStep = niceStep((x1 - x0) / X_TICK_TARGET);
    for (let xv = x0; xv <= x1 + 1e-9; xv += xStep) {
      const x = padL + (xv - x0) * xScale;
      
      ctx.strokeStyle = "rgba(255,255,255,0.2)";
      ctx.beginPath(); ctx.moveTo(x, padT + plotH); ctx.lineTo(x, padT + plotH + 4); ctx.stroke();
      if (xv !==0){
        ctx.fillText(String(Math.round(xv)), x, padT + plotH + 16);
      }
      
      ctx.strokeStyle = "rgba(255,255,255,0.05)";
      ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, padT + plotH); ctx.stroke();
    }

    ctx.textAlign = "right";
    const yStep = niceStep((y1 - y0) / 6);
    for (let yv = y0; yv <= y1 + 1e-9; yv += yStep) {
      const y = padT + (yv - y0) * yScale;
      ctx.strokeStyle = "rgba(255,255,255,0.2)";
      ctx.beginPath(); ctx.moveTo(padL - 4, y); ctx.lineTo(padL, y); ctx.stroke();
      ctx.fillText(String(Math.round(yv)), padL - 6, y + 4);
      ctx.strokeStyle = "rgba(255,255,255,0.05)";
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(padL + plotW, y); ctx.stroke();
    }

    return { padL, padT, plotW, plotH, x0, y0, x1, y1, xScale, yScale };
  }

  function redraw() {
    const cvs = document.getElementById(CANVAS_ID);
    if (!cvs) return;
    const ctx = cvs.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const cssW = cvs.clientWidth || 600;
    const cssH = cvs.clientHeight || 300;
    cvs.width = Math.floor(cssW * dpr);
    cvs.height = Math.floor(cssH * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);

    const coord = drawAxes(ctx, cssW, cssH);

    const groups = state.groups || [];
    const ptsAll = [];
    groups.forEach(g=>{
      if (!state.glassFilter.has(g.gid)) return;
      g.points.forEach(p=>{
        if (!p.bucket || !state.sizeFilter.has(p.bucket)) return;
        ptsAll.push({ ...p, gid: g.gid });
      });
    });

    if (!ptsAll.length) { state.hitCache = []; return; }

    function toScreen(p) {
      const x = coord.padL + (p.x - coord.x0) * coord.xScale;
      const y = coord.padT + (p.y - coord.y0) * coord.yScale;
      return [x, y];
    }
    function rOf(b) { return b==="S"?3 : b==="M"?5 : b==="L"?7 : 9; }

    const hit = [];
    ["S","M","L","O"].forEach(b=>{
      const pts = ptsAll.filter(p=>p.bucket===b);
      if (!pts.length) return;
      ctx.fillStyle = SIZE_COLORS[b] || "#AAA";
      pts.forEach(p=>{
        const [sx, sy] = toScreen(p);
        const r = rOf(p.bucket);
        ctx.beginPath();
        ctx.arc(sx, sy, r, 0, Math.PI*2);
        ctx.globalAlpha = 0.9;
        ctx.fill();
        ctx.globalAlpha = 1;
        hit.push({ sx, sy, r: r + 4, url: p.img, point: p });
      });
    });

    state.hitCache = hit;
  }

  function findHit(ev) {
    const cvs = document.getElementById(CANVAS_ID);
    if (!cvs || !state.hitCache?.length) return null;
    const rect = cvs.getBoundingClientRect();
    const x = ev.clientX - rect.left;
    const y = ev.clientY - rect.top;

    let best = null, bestD2 = Infinity;
    for (let i=0;i<state.hitCache.length;i++){
      const h = state.hitCache[i];
      const dx = x - h.sx, dy = y - h.sy;
      const d2 = dx*dx + dy*dy;
      if (d2 <= (h.r*h.r) && d2 < bestD2) { best = h; bestD2 = d2; }
    }
    return best;
  }

  function tooltipHtmlFromPoint(p){
    const m = p?.meta || {};
    const kv = {
      lotid: m.lotid ?? m.lot ?? "",
      recipe: m.recipe ?? p?.recipe_id ?? "",
      x: m.x ?? p?.x ?? "",
      y: m.y ?? p?.y ?? "",
      defect_size: m.defect_size ?? p?.rawSize ?? p?.bucket ?? "",
      ai_code_1: m.ai_code_1 ?? "",
    };
    const rows = DEFECT_INFO_KEYS.map(k=>{
      const v = kv[k] ?? "";
      return `<tr><td style="opacity:.65;padding-right:8px;">${k}</td><td>${String(v)}</td></tr>`;
    }).join("");
    return `<table style="border-collapse:collapse;">${rows}</table>`;
  }

  function showTooltip(ev, html){
    const tips = document.getElementById(TIPS_ID);
    if (!tips) return;
    tips.innerHTML = html;
    tips.style.display = "block";
    const pad = 12;
    let x = ev.clientX + pad, y = ev.clientY + pad;
    const vw = window.innerWidth, vh = window.innerHeight;
    const rect = tips.getBoundingClientRect();
    if (x + rect.width > vw - 8) x = vw - rect.width - 8;
    if (y + rect.height > vh - 8) y = vh - rect.height - 8;
    tips.style.left = `${x}px`;
    tips.style.top  = `${y}px`;
  }

  function hideTooltip(){
    const tips = document.getElementById(TIPS_ID);
    if (!tips) return;
    tips.style.display = "none";
  }
  /*
  */
  MOD.Map.setData = function(response) {
    state.groups = normalizeResponse(response);
    state.sizeFilter = new Set(["S","M","L","O"]);
    state.glassFilter = new Set((state.groups || []).map(g=>g.gid));
    buildLegend(state.groups);
    redraw();
  };

  // === 新增：由 chart.js 丟 filters 進來，由這裡打後端 defect_map API ===
  MOD.Map.fetchAndRender = async function(filterRows) {
    const rows = Array.isArray(filterRows) ? filterRows : [];
    if (!rows.length) {
      // 沒有條件就清空圖
      MOD.Map.setData({ DefectGroupDict: [] });
      return;
    }

    try {
      let resp = null;

      if (window.API?.postDefectMap) {
        // 優先使用 aoi_inspection 封裝好的 API
        resp = await window.API.postDefectMap(rows);
      } else if (window.API?.post) {
        // 備援：直接打同一路徑
        const base =
          window.API_BASE_DENSITY ||
          window.API_BASE ||
          "";
        const url = `${base}/aoi_inspection/api/defect_map`;
        resp = await window.API.post(url, { rows });
      }

      resp = resp || { DefectGroupDict: [] };

      // 與舊版 table.js 行為維持一致：把 response 存在 state 方便 debug
      if (window.AOI_INSPECTION?.state) {
        window.AOI_INSPECTION.state.defectMapResponse = resp;
      }

      MOD.Map.setData(resp);
    } catch (err) {
      console.error("[AOI_INSPECTION] Map.fetchAndRender error:", err);
      MOD.Map.setData({ DefectGroupDict: [] });
    }
  };


  /*document.addEventListener("aoi_inspection:defect-map-ready", (ev)=>{
    const resp = ev?.detail?.response || null;
    MOD.Map.setData(resp || {});
  });
  */

  function bindCanvasEvents() {
    const cvs = document.getElementById(CANVAS_ID);
    if (!cvs) return;

    cvs.addEventListener("mousemove", (ev)=>{
      const hit = findHit(ev);
      if (hit && hit.point) {
        cvs.style.cursor = hit.url && hit.url !== "#" ? "pointer" : "default";
        showTooltip(ev, tooltipHtmlFromPoint(hit.point));
      } else {
        cvs.style.cursor = "default";
        hideTooltip();
      }
    });

    cvs.addEventListener("mouseleave", hideTooltip);

    cvs.addEventListener("click", (ev)=>{
      const hit = findHit(ev);
      if (hit && hit.url) {
        window.open(hit.url, "_blank", "noopener");
      }
    });
  }

  window.addEventListener("resize", ()=>{
    hideTooltip();
    redraw();
  });

  document.addEventListener("DOMContentLoaded", ()=>{
    ensureLayout();
    buildLegend([]);
    bindCanvasEvents();
    redraw();
  });
})();
