
// static/js/bpi_area/bpi_density/defect_map.js
// BPI Density defect map
//
// 功能：
// - 接收 aoi-bpi-density:defect-map-ready
// - 顯示 BPI Density 點擊 chart/table 後回傳的 defect raw points
// - 保留 size filter / glass filter / tooltip / image open
//
// 注意：
// - 本檔只服務 BPI Density 原功能。
// - BPI/API Same Point map 請使用 static/js/bpi_area/bpi_same_point/defect_map.js。

(function () {
  const MOD = (window.AOI_BPI_DENSITY = window.AOI_BPI_DENSITY || {});
  MOD.Map = MOD.Map || {};

  const CANVAS_ID = "aoi-bpi-density-mini-map";
  const LEGEND_ID = "aoi-bpi-density-map-legend";
  const TIPS_ID = "aoi-bpi-density-map-tooltip";

  const DEFECT_INFO_KEYS = ["lotid", "recipe", "x", "y", "defect_size"];

  const AXIS = {
    minX: 0,
    maxX: 1850000,
    minY: 0,
    maxY: 1500000
  };

  const SIZE_COLORS = {
    S: "#7FDBFF",
    M: "#FF851B",
    L: "#2ECC40",
    O: "#FF4136"
  };

  const state = {
    groups: [],
    sizeFilter: new Set(["S", "M", "L", "O"]),
    glassFilter: new Set(),
    hitCache: []
  };

  // ============================================================
  // Helpers
  // ============================================================
  function cleanStr(v) {
    if (v == null) return "";
    const s = String(v).trim();
    if (!s) return "";
    if (["nan", "none", "null", "nat", "<na>"].includes(s.toLowerCase())) return "";
    return s;
  }

  function num(v) {
    const n = Number(v);
    return Number.isFinite(n) ? n : 0;
  }

  function isJpgPath(s) {
    return String(s || "").toLowerCase().includes(".jpg");
  }

  function buildImageUrl(picPath, picName) {
    const p = cleanStr(picPath);
    const n = cleanStr(picName);

    if (!p) return n;
    if (isJpgPath(p)) return p;
    if (!n) return p;

    return p.endsWith("/") || p.endsWith("\\")
      ? p + n
      : p + "/" + n;
  }

  // ============================================================
  // Layout
  // ============================================================
  function ensureLayout() {
    const host = document.getElementById("aoi-bpi-density-map-wrap");
    const vp = host?.querySelector(".aoi-bpi-density-map-viewport, .map-viewport");
    const cvs = document.getElementById(CANVAS_ID);

    if (!vp || !cvs) return null;

    vp.style.display = "flex";
    vp.style.gap = "10px";
    vp.style.alignItems = "stretch";
    vp.style.overflow = "hidden";

    Object.assign(cvs.style, {
      flex: "8 1 0",
      width: "100%",
      height: "100%",
      background: "#0f1115",
      border: "1px solid rgba(255,255,255,0.08)",
      borderRadius: "6px"
    });

    let legend = document.getElementById(LEGEND_ID);
    if (!legend) {
      legend = document.createElement("div");
      legend.id = LEGEND_ID;
      vp.appendChild(legend);
    }

    Object.assign(legend.style, {
      flex: "2 1 0",
      minWidth: "160px",
      display: "flex",
      flexDirection: "column",
      gap: "10px",
      background: "#0f1115",
      border: "1px solid rgba(255,255,255,0.08)",
      borderRadius: "6px",
      padding: "8px",
      overflowY: "auto",
      overflowX: "hidden"
    });

    let tips = document.getElementById(TIPS_ID);
    if (!tips) {
      tips = document.createElement("div");
      tips.id = TIPS_ID;
      document.body.appendChild(tips);
    }

    Object.assign(tips.style, {
      position: "fixed",
      zIndex: 9999,
      pointerEvents: "none",
      background: "rgba(0,0,0,0.85)",
      border: "1px solid rgba(255,255,255,0.15)",
      borderRadius: "6px",
      padding: "6px 8px",
      font: "12px/1.35 -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif",
      color: "#fff",
      boxShadow: "0 6px 18px rgba(0,0,0,0.35)",
      maxWidth: "320px",
      display: "none"
    });

    return { vp, cvs, legend, tips };
  }

  // ============================================================
  // Normalize response
  // ============================================================
  function normalizeResponse(resp) {
    const dict = resp?.DefectGroupDict;
    if (!dict || typeof dict !== "object") return [];

    const groups = [];

    Object.entries(dict).forEach(([glassId, defectObj]) => {
      const gid = cleanStr(glassId);
      const g = {
        gid,
        label: gid,
        points: []
      };

      if (!defectObj || typeof defectObj !== "object") {
        groups.push(g);
        return;
      }

      Object.values(defectObj).forEach((it) => {
        if (!it || typeof it !== "object") return;

        const rawSize = cleanStr(it.defect_size).toUpperCase();
        const bucket = ["S", "M", "L", "O"].includes(rawSize) ? rawSize : "O";

        if (!bucket) return;

        const x = num(it.x);
        const y = num(it.y);

        const picPath = cleanStr(it.pic_path);
        const picName = cleanStr(it.pic_name);
        const img = buildImageUrl(picPath, picName);

        const jpgMatches = String(img).match(/\.jpg/gi);
        if (jpgMatches && jpgMatches.length >= 2) {
          console.warn("[BPI_DEFECT_MAP][DOUBLE_JPG_URL]", {
            glassId: gid,
            img,
            picPath,
            picName,
            rawItem: it
          });
        }

        g.points.push({
          x,
          y,
          bucket,
          rawSize: it.defect_size,
          img: img || "",
          recipe_id: cleanStr(it.recipe_id),
          meta: {
            lotid: gid,
            recipe: cleanStr(it.recipe_id),
            x,
            y,
            defect_size: it.defect_size ?? ""
          }
        });
      });

      groups.push(g);
    });

    return groups;
  }

  // ============================================================
  // Legend
  // ============================================================
  function buildLegend(groups) {
    const legend = document.getElementById(LEGEND_ID);
    if (!legend) return;

    legend.innerHTML = "";

    // ----------------------------
    // Size filter
    // ----------------------------
    const sizeBox = document.createElement("div");
    sizeBox.style.borderBottom = "1px dashed rgba(255,255,255,0.14)";
    sizeBox.style.paddingBottom = "8px";

    const sHeader = document.createElement("div");
    Object.assign(sHeader.style, {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      marginBottom: "6px"
    });

    const sTitle = document.createElement("div");
    sTitle.style.fontWeight = "700";
    sTitle.style.fontSize = "12px";
    sTitle.textContent = "尺寸";

    const sBtn = document.createElement("button");
    sBtn.className = "btn btn-xs btn-secondary";
    sBtn.textContent = state.sizeFilter.size === 4 ? "清空" : "全選";
    sBtn.addEventListener("click", () => {
      if (state.sizeFilter.size === 4) {
        state.sizeFilter = new Set();
      } else {
        state.sizeFilter = new Set(["S", "M", "L", "O"]);
      }

      buildLegend(state.groups);
      redraw();
    });

    sHeader.append(sTitle, sBtn);
    sizeBox.appendChild(sHeader);

    const sWrap = document.createElement("div");
    Object.assign(sWrap.style, {
      display: "flex",
      flexWrap: "wrap",
      gap: "8px"
    });

    ["S", "M", "L", "O"].forEach(k => {
      const item = document.createElement("div");
      Object.assign(item.style, {
        display: "inline-flex",
        alignItems: "center",
        gap: "3px",
        padding: "2px 3px",
        border: "1px solid rgba(255,255,255,0.15)",
        borderRadius: "4px",
        cursor: "pointer",
        userSelect: "none",
        background: state.sizeFilter.has(k) ? "rgba(255,255,255,0.06)" : "transparent"
      });

      const sw = document.createElement("span");
      Object.assign(sw.style, {
        display: "inline-block",
        width: "14px",
        height: "14px",
        borderRadius: "3px",
        background: SIZE_COLORS[k] || "#999"
      });

      const label = document.createElement("span");
      label.textContent = k;
      label.style.fontSize = "12px";

      item.append(sw, label);

      item.addEventListener("click", () => {
        if (state.sizeFilter.has(k)) state.sizeFilter.delete(k);
        else state.sizeFilter.add(k);

        buildLegend(state.groups);
        redraw();
      });

      sWrap.appendChild(item);
    });

    sizeBox.appendChild(sWrap);
    legend.appendChild(sizeBox);

    // ----------------------------
    // Glass filter
    // ----------------------------
    const glassBox = document.createElement("div");

    const gHeader = document.createElement("div");
    Object.assign(gHeader.style, {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      marginBottom: "6px"
    });

    const gTitle = document.createElement("div");
    gTitle.style.fontWeight = "700";
    gTitle.style.fontSize = "12px";
    gTitle.textContent = "Glass 篩選";

    const allGids = (groups || []).map(g => g.gid);
    const gBtn = document.createElement("button");
    gBtn.className = "btn btn-xs btn-secondary";
    gBtn.textContent = (allGids.length > 0 && state.glassFilter.size === allGids.length) ? "清空" : "全選";

    gBtn.addEventListener("click", () => {
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
    Object.assign(list.style, {
      display: "flex",
      flexDirection: "column",
      gap: "6px"
    });

    (groups || [])
      .slice()
      .sort((a, b) => String(a.label).localeCompare(String(b.label)))
      .forEach(g => {
        const row = document.createElement("label");
        Object.assign(row.style, {
          display: "flex",
          alignItems: "center",
          gap: "8px",
          cursor: "pointer",
          padding: "4px 6px",
          borderRadius: "4px",
          border: "1px solid rgba(255,255,255,0.08)",
          background: state.glassFilter.has(g.gid) ? "rgba(255,255,255,0.04)" : "transparent"
        });

        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = state.glassFilter.has(g.gid);
        cb.addEventListener("change", () => {
          if (cb.checked) state.glassFilter.add(g.gid);
          else state.glassFilter.delete(g.gid);

          buildLegend(state.groups);
          redraw();
        });

        const label = document.createElement("span");
        label.style.fontSize = "12px";
        label.textContent = g.label || g.gid;

        row.append(cb, label);
        list.appendChild(row);
      });

    glassBox.appendChild(list);
    legend.appendChild(glassBox);
  }

  // ============================================================
  // Canvas drawing
  // ============================================================
  function niceStep(range) {
    if (!isFinite(range) || range <= 0) return 1;

    const exp = Math.floor(Math.log10(range));
    const frac = range / Math.pow(10, exp);
    const niceFrac = frac < 1.5 ? 1 : frac < 3 ? 2 : frac < 7 ? 5 : 10;

    return niceFrac * Math.pow(10, exp);
  }

  function drawAxes(ctx, w, h) {
    const padL = 60;
    const padR = 18;
    const padT = 12;
    const padB = 48;

    const plotW = Math.max(10, w - padL - padR);
    const plotH = Math.max(10, h - padT - padB);

    const x0 = AXIS.minX;
    const x1 = AXIS.maxX;
    const y0 = AXIS.minY;
    const y1 = AXIS.maxY;

    const xScale = plotW / ((x1 - x0) || 1);
    const yScale = plotH / ((y1 - y0) || 1);

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

    const xStep = niceStep((x1 - x0) / 12);
    for (let xv = x0; xv <= x1 + 1e-9; xv += xStep) {
      const x = padL + (xv - x0) * xScale;

      ctx.strokeStyle = "rgba(255,255,255,0.2)";
      ctx.beginPath();
      ctx.moveTo(x, padT + plotH);
      ctx.lineTo(x, padT + plotH + 4);
      ctx.stroke();

      if (xv !== 0) {
        ctx.fillText(String(Math.round(xv)), x, padT + plotH + 16);
      }

      ctx.strokeStyle = "rgba(255,255,255,0.05)";
      ctx.beginPath();
      ctx.moveTo(x, padT);
      ctx.lineTo(x, padT + plotH);
      ctx.stroke();
    }

    ctx.textAlign = "right";

    const yStep = niceStep((y1 - y0) / 6);
    for (let yv = y0; yv <= y1 + 1e-9; yv += yStep) {
      const y = padT + (yv - y0) * yScale;

      ctx.strokeStyle = "rgba(255,255,255,0.2)";
      ctx.beginPath();
      ctx.moveTo(padL - 4, y);
      ctx.lineTo(padL, y);
      ctx.stroke();

      ctx.fillText(String(Math.round(yv)), padL - 6, y + 4);

      ctx.strokeStyle = "rgba(255,255,255,0.05)";
      ctx.beginPath();
      ctx.moveTo(padL, y);
      ctx.lineTo(padL + plotW, y);
      ctx.stroke();
    }

    return {
      padL,
      padT,
      plotW,
      plotH,
      x0,
      y0,
      xScale,
      yScale
    };
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

    const ptsAll = [];

    (state.groups || []).forEach(g => {
      if (!state.glassFilter.has(g.gid)) return;

      g.points.forEach(p => {
        if (!p.bucket || !state.sizeFilter.has(p.bucket)) return;
        ptsAll.push({ ...p, gid: g.gid });
      });
    });

    if (!ptsAll.length) {
      state.hitCache = [];
      return;
    }

    function toScreen(p) {
      const x = coord.padL + (p.x - AXIS.minX) * coord.xScale;
      const y = coord.padT + (p.y - AXIS.minY) * coord.yScale;
      return [x, y];
    }

    function rOf(b) {
      return b === "S" ? 3 : b === "M" ? 5 : b === "L" ? 7 : 9;
    }

    const hit = [];

    ["S", "M", "L", "O"].forEach(b => {
      const pts = ptsAll.filter(p => p.bucket === b);
      if (!pts.length) return;

      ctx.fillStyle = SIZE_COLORS[b] || "#AAA";

      pts.forEach(p => {
        const [sx, sy] = toScreen(p);
        const r = rOf(p.bucket);

        ctx.beginPath();
        ctx.arc(sx, sy, r, 0, Math.PI * 2);
        ctx.globalAlpha = 0.9;
        ctx.fill();
        ctx.globalAlpha = 1;

        hit.push({
          sx,
          sy,
          r: r + 4,
          url: p.img,
          point: p
        });
      });
    });

    state.hitCache = hit;
  }

  // ============================================================
  // Tooltip / click
  // ============================================================
  function findHit(ev) {
    const cvs = document.getElementById(CANVAS_ID);
    if (!cvs || !state.hitCache?.length) return null;

    const rect = cvs.getBoundingClientRect();
    const x = ev.clientX - rect.left;
    const y = ev.clientY - rect.top;

    let best = null;
    let bestD2 = Infinity;

    for (const h of state.hitCache) {
      const dx = x - h.sx;
      const dy = y - h.sy;
      const d2 = dx * dx + dy * dy;

      if (d2 <= h.r * h.r && d2 < bestD2) {
        best = h;
        bestD2 = d2;
      }
    }

    return best;
  }

  function tooltipHtmlFromPoint(p) {
    const m = p?.meta || {};
    const kv = {
      lotid: m.lotid ?? "",
      recipe: m.recipe ?? p?.recipe_id ?? "",
      x: m.x ?? p?.x ?? "",
      y: m.y ?? p?.y ?? "",
      defect_size: m.defect_size ?? p?.rawSize ?? p?.bucket ?? ""
    };

    const rows = DEFECT_INFO_KEYS.map(k => {
      const v = kv[k] ?? "";
      return `<tr><td style="opacity:.65;padding-right:8px;">${k}</td><td>${String(v)}</td></tr>`;
    }).join("");

    return `<table style="border-collapse:collapse;">${rows}</table>`;
  }

  function showTooltip(ev, html) {
    const tips = document.getElementById(TIPS_ID);
    if (!tips) return;

    tips.innerHTML = html;
    tips.style.display = "block";

    const pad = 12;
    let x = ev.clientX + pad;
    let y = ev.clientY + pad;

    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const rect = tips.getBoundingClientRect();

    if (x + rect.width > vw - 8) x = vw - rect.width - 8;
    if (y + rect.height > vh - 8) y = vh - rect.height - 8;

    tips.style.left = `${x}px`;
    tips.style.top = `${y}px`;
  }

  function hideTooltip() {
    const tips = document.getElementById(TIPS_ID);
    if (!tips) return;
    tips.style.display = "none";
  }

  function bindCanvasEvents() {
    const cvs = document.getElementById(CANVAS_ID);
    if (!cvs) return;

    cvs.addEventListener("mousemove", (ev) => {
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

    cvs.addEventListener("click", (ev) => {
      const hit = findHit(ev);

      if (hit && hit.url) {
        window.open(hit.url, "_blank", "noopener");
      }
    });
  }

  // ============================================================
  // Public API
  // ============================================================
  MOD.Map.setData = function (response) {
    state.groups = normalizeResponse(response);
    state.sizeFilter = new Set(["S", "M", "L", "O"]);
    state.glassFilter = new Set((state.groups || []).map(g => g.gid));

    buildLegend(state.groups);
    redraw();
  };

  MOD.Map.clear = function () {
    state.groups = [];
    state.sizeFilter = new Set(["S", "M", "L", "O"]);
    state.glassFilter = new Set();
    state.hitCache = [];

    buildLegend([]);
    redraw();
  };

  document.addEventListener("aoi-bpi-density:defect-map-ready", (ev) => {
    const resp = ev?.detail?.response || null;
    MOD.Map.setData(resp || {});
  });

  let _mapUiInited = false;

  function initMapUI() {
    if (_mapUiInited) return;

    _mapUiInited = true;

    ensureLayout();
    buildLegend([]);
    bindCanvasEvents();
    redraw();
  }

  window.addEventListener("resize", () => {
    hideTooltip();
    redraw();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initMapUI, { once: true });
  } else {
    initMapUI();
  }
})();