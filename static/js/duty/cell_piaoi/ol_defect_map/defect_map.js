// static/js/ol_defect_map/defect_map.js
(function () {
  const Bus = window.OLDefectMapBus;
  const State = window.OLDefectMapState;
  const Utils = window.OLDefectMapUtils;
  const ColorKit = window.OLDefectMapColorKit;

  const canvas = document.getElementById("ol-defect-map-canvas");
  if (!canvas) {
    console.warn("[ol-defect-map][map] canvas not found");
    return;
  }

  const ctx = canvas.getContext("2d");

  const View = {
    pad: 20,
    scale: 1,
    tx: 0,
    ty: 0,
    boxZoom: false,
    box: null,
    hoveringDot: false,
  };

  const UM_PER_MM = 1000;
  const DEFAULT_BOUNDS = {
    minX: 0,
    minY: 0,
    maxX: 1850000,
    maxY: 1500000,
  };

  const FIXED_POINT_RADIUS_PX = 2.2;
  const HOVER_GAP_X = 38;
  const HOVER_GAP_Y = 28;
  const CLICK_GAP_X = 34;
  const CLICK_GAP_Y = 20;
  const VIEWPORT_PAD = 12;

  const POINT_RADIUS_BY_SIZE = {
    S: 2.2,
    M: 3.4,
    L: 4.8,
    O: 6.5,
  };
  
  function getPointRadiusPx(size) {
    const s = String(size ?? "").trim().toUpperCase();
    return POINT_RADIUS_BY_SIZE[s] || FIXED_POINT_RADIUS_PX;
  }

  const SIZE_EMPTY_VALUES = new Set(["", "NAN", "NONE", "<NA>", "NAT", "NULL"]);

  function normalizeDefectSize(v, raw, key) {
    let s = String(v ?? "").trim().toUpperCase();

    if (SIZE_EMPTY_VALUES.has(s)) {
      const rawAoi = String(raw?.aoi ?? raw?.aoi_id ?? "").trim().toLowerCase();
      const keyAoi = (() => {
        try {
          return String(Utils.parseKey(key)?.aoi ?? "").trim().toLowerCase();
        } catch (e) {
          return "";
        }
      })();

      const aoi = rawAoi || keyAoi;

      // 只針對 aoi200：空 defect_size 視為 O
      if (aoi === "aoi200") return "O";

      // 非 aoi200 先保留空值，不強制歸 O
      return "";
    }

    return s;
  }


  function ensureLightbox() {
    let lb = document.getElementById("ol-defect-map-img-lightbox");
    if (!lb) {
      lb = document.createElement("div");
      lb.id = "ol-defect-map-img-lightbox";
      lb.innerHTML = `
        <div class="lb-inner">
          <img alt="">
          <div class="lb-caption"></div>
        </div>
      `;
      document.body.appendChild(lb);
    }

    Object.assign(lb.style, {
      display: "none",
      position: "fixed",
      inset: "0",
      zIndex: "99999",
      background: "rgba(0,0,0,.72)",
      alignItems: "center",
      justifyContent: "center",
      padding: "24px"
    });

    const inner = lb.querySelector(".lb-inner");
    if (inner) {
      Object.assign(inner.style, {
        maxWidth: "92vw",
        maxHeight: "92vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: "10px"
      });
    }

    const img = lb.querySelector("img");
    if (img) {
      Object.assign(img.style, {
        maxWidth: "92vw",
        maxHeight: "82vh",
        objectFit: "contain",
        borderRadius: "8px",
        boxShadow: "0 8px 28px rgba(0,0,0,.45)",
        background: "#111"
      });
    }

    const cap = lb.querySelector(".lb-caption");
    if (cap) {
      Object.assign(cap.style, {
        color: "#fff",
        fontSize: "13px",
        textAlign: "center"
      });
    }

    lb.addEventListener("click", (e) => {
      if (e.target.id === "ol-defect-map-img-lightbox") {
        lb.style.display = "none";
      }
    });

    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape") lb.style.display = "none";
    });

    document.addEventListener("click", (e) => {
      const t = e.target;
      if (!(t && t.tagName === "IMG" && t.classList.contains("zoomable"))) return;
      const src = t.getAttribute("src");
      const caption = t.getAttribute("alt") || "";
      lb.querySelector("img").setAttribute("src", src);
      lb.querySelector(".lb-caption").textContent = caption;
      lb.style.display = "flex";
    });
  }
  ensureLightbox();

  const FALLBACK_CYCLE = [
    "#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00",
    "#ffff33", "#a65628", "#f781bf", "#999999"
  ];

  function mapKeysFallback(keys) {
    const map = {};
    keys.forEach((k, i) => {
      map[k] = FALLBACK_CYCLE[i % FALLBACK_CYCLE.length];
    });
    return map;
  }

  function ensureKeyColors(keys) {
    try {
      if (ColorKit && typeof ColorKit.mapKeys === "function") {
        State.keyColors = ColorKit.mapKeys(keys || []);
      } else {
        State.keyColors = mapKeysFallback(keys || []);
      }
    } catch (e) {
      State.keyColors = mapKeysFallback(keys || []);
    }
  }

  function renderLegend() {
    const host = document.getElementById("ol-defect-map-legend");
    if (!host) return;

    host.innerHTML = "";
    const keys = State.selectedKeys || [];
    const palette = State.keyColors || {};

    keys.forEach((k) => {
      const color = palette[k] || "#ccc";
      const item = document.createElement("div");
      item.className = "ol-defect-map-legend-item";

      const sw = document.createElement("span");
      sw.className = "ol-defect-map-legend-color";
      sw.style.background = color;

      const tt = document.createElement("span");
      tt.className = "ol-defect-map-legend-text";
      tt.textContent = k;

      item.appendChild(sw);
      item.appendChild(tt);
      host.appendChild(item);
    });
  }

  function updateOverlapSummary(overlapCount, selectedTotal, overlapHitTotal) {
    const overlapEl = document.getElementById("ol-defect-map-overlap-count");
    const totalEl = document.getElementById("ol-defect-map-selected-total");
    //const hitTotalEl = document.getElementById("ol-defect-map-overlap-hit-total");

    if (overlapEl) overlapEl.textContent = String(overlapCount || 0);
    if (totalEl) totalEl.textContent = String(selectedTotal || 0);
    //if (hitTotalEl) hitTotalEl.textContent = String(overlapHitTotal || 0);
  }

  function getAllowedSizes() {
    const s = State.filters?.sizeSet;
    if (!(s instanceof Set) || s.size === 0) return ["S", "M", "L", "O"];
    return [...s];
  }

  function getAllowedTypes() {
    const s = State.filters?.typeSetSelected;
    if (!(s instanceof Set) || s.size === 0) return null;
    return [...s];
  }

  function allPoints(keys) {
    const pts = [];
    const palette = State.keyColors || {};

    keys.forEach((k) => {
      const lst = State.DefectCache[k] || [];
      const col = palette[k] || "#bbb";

      lst.forEach((d) => {
        const rawSize = d.size ?? d.defect_size ?? "";
        const size = normalizeDefectSize(rawSize, d, k);
        const type = d.type ?? d.adc_def_code ?? d.retype_def_code ?? "";
      
        pts.push({
          k,
          x: +d.x,
          y: +d.y,
          size,
          type,
          color: col,
          raw: d,
        });
      });
      
    });

    return pts;
  }

  function computeBounds(points) {
    if (!points.length) return { ...DEFAULT_BOUNDS };

    let minX = +points[0].x;
    let minY = +points[0].y;
    let maxX = minX;
    let maxY = minY;

    points.forEach((p) => {
      if (p.x < minX) minX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.x > maxX) maxX = p.x;
      if (p.y > maxY) maxY = p.y;
    });

    const w = Math.max(1, maxX - minX);
    const h = Math.max(1, maxY - minY);
    const padX = w * 0.01;
    const padY = h * 0.01;

    return {
      minX: minX - padX,
      minY: minY - padY,
      maxX: maxX + padX,
      maxY: maxY + padY,
    };
  }

  const offsetInputEl = document.getElementById("ol-defect-map-offset-input");
  const applyOffsetBtn = document.getElementById("ol-defect-map-apply-offset");

  if (typeof State.mapOffsetUm !== "number") {
    State.mapOffsetUm = typeof State.offsetUm === "number" ? State.offsetUm : 5;
  }

  function parseOffsetInputUm() {
    return parseFloat(offsetInputEl?.value || "5") || 5;
  }

  function getOffsetUm() {
    return Math.max(0, State.mapOffsetUm || 0);
  }

  if (applyOffsetBtn) {
    applyOffsetBtn.addEventListener("click", () => {
      State.mapOffsetUm = parseOffsetInputUm();
      State.offsetUm = State.mapOffsetUm;
      Bus.emit("map-refresh");
    });
  }

  function worldToScreen(x, y, bbox) {
    const W = canvas.clientWidth || canvas.parentElement?.clientWidth || 1;
    const H = canvas.clientHeight || canvas.parentElement?.clientHeight || 1;
    const w = (bbox.maxX - bbox.minX) || 1;
    const h = (bbox.maxY - bbox.minY) || 1;

    const sx = ((x - bbox.minX) / w) * (W - 2 * View.pad) + View.pad;
    const sy = ((y - bbox.minY) / h) * (H - 2 * View.pad) + View.pad;

    return {
      x: sx * View.scale + View.tx,
      y: sy * View.scale + View.ty,
    };
  }

  function screenToWorld(px, py, bbox) {
    const W = canvas.clientWidth || canvas.parentElement?.clientWidth || 1;
    const H = canvas.clientHeight || canvas.parentElement?.clientHeight || 1;

    const x0 = (px - View.tx) / View.scale;
    const y0 = (py - View.ty) / View.scale;

    const w = (bbox.maxX - bbox.minX) || 1;
    const h = (bbox.maxY - bbox.minY) || 1;

    const wx = ((x0 - View.pad) / (W - 2 * View.pad)) * w + bbox.minX;
    const wy = ((y0 - View.pad) / (H - 2 * View.pad)) * h + bbox.minY;

    return { x: wx, y: wy };
  }

  function drawAxes() {
    const W = canvas.clientWidth;
    const H = canvas.clientHeight;

    ctx.save();
    ctx.strokeStyle = "#6b7280";
    ctx.lineWidth = 1;

    ctx.beginPath();
    ctx.moveTo(8, 12);
    ctx.lineTo(W - 8, 12);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(12, 8);
    ctx.lineTo(12, H - 8);
    ctx.stroke();

    ctx.restore();
  }

  function niceStep(rangeMm, pxSpan) {
    const targetPx = 80;
    const n = Math.max(1, pxSpan / targetPx);
    const rough = rangeMm / n;
    const pow10 = Math.pow(10, Math.floor(Math.log10(Math.max(rough, 1e-9))));
    const cand = [1, 2, 5, 10];

    let best = pow10;
    for (const c of cand) {
      const step = c * pow10;
      best = step;
      if (rough <= step) break;
    }
    return best;
  }

  function drawAxisTicks(bbox) {
    const W = canvas.clientWidth;
    const H = canvas.clientHeight;

    const leftScr = View.tx + View.scale * View.pad;
    const rightScr = View.tx + View.scale * (W - View.pad);
    const topScr = View.ty + View.scale * View.pad;
    const botScr = View.ty + View.scale * (H - View.pad);

    const xWorldL = screenToWorld(leftScr, topScr, bbox).x;
    const xWorldR = screenToWorld(rightScr, topScr, bbox).x;
    const yWorldT = screenToWorld(leftScr, topScr, bbox).y;
    const yWorldB = screenToWorld(leftScr, botScr, bbox).y;

    const xMinMm = xWorldL / UM_PER_MM;
    const xMaxMm = xWorldR / UM_PER_MM;
    const yMinMm = yWorldT / UM_PER_MM;
    const yMaxMm = yWorldB / UM_PER_MM;

    const xStep = niceStep(Math.max(1e-9, xMaxMm - xMinMm), (W - 2 * View.pad));
    const yStep = niceStep(Math.max(1e-9, yMaxMm - yMinMm), (H - 2 * View.pad));
    const xStart = Math.ceil(xMinMm / xStep) * xStep;
    const yStart = Math.ceil(yMinMm / yStep) * yStep;

    ctx.save();
    ctx.fillStyle = "#9aa3ad";
    ctx.strokeStyle = "#808695";
    ctx.lineWidth = 1;
    ctx.font = "10px system-ui";

    for (let mm = xStart; mm <= xMaxMm + 1e-9; mm += xStep) {
      const um = mm * UM_PER_MM;
      const s = worldToScreen(um, yWorldT, bbox);
      ctx.beginPath();
      ctx.moveTo(s.x, 12);
      ctx.lineTo(s.x, 16);
      ctx.stroke();

      const txt = String(Math.round(mm * 1000) / 1000);
      ctx.fillText(txt, s.x - ctx.measureText(txt).width / 2, 26);
    }

    for (let mm = yStart; mm <= yMaxMm + 1e-9; mm += yStep) {
      const um = mm * UM_PER_MM;
      const s = worldToScreen(xWorldL, um, bbox);
      ctx.beginPath();
      ctx.moveTo(12, s.y);
      ctx.lineTo(16, s.y);
      ctx.stroke();

      const txt = String(Math.round(mm * 1000) / 1000);
      if (mm !== 0) ctx.fillText(txt, 18, s.y + 3);
    }

    ctx.fillStyle = "#cfd7df";
    ctx.fillText("mm", W - 28, 22);
    ctx.restore();
  }

  function pxToUm(px, bbox) {
    const W = canvas.clientWidth;
    const H = canvas.clientHeight;
    const worldW = Math.max(1, bbox.maxX - bbox.minX);
    const worldH = Math.max(1, bbox.maxY - bbox.minY);
    const scrW = Math.max(1, (W - 2 * View.pad) * (View.scale || 1));
    const scrH = Math.max(1, (H - 2 * View.pad) * (View.scale || 1));

    return Math.max(worldW / scrW, worldH / scrH) * px;
  }

  const CLICK_HIT_PX = 8;
  const HOVER_HIT_PX = 6;
  const MIN_CLICK_HIT_UM = 80;
  const MIN_HOVER_HIT_UM = 60;

  function getClickHitUm(bbox) {
    return Math.max(pxToUm(CLICK_HIT_PX, bbox), MIN_CLICK_HIT_UM);
  }

  function getHoverHitUm(bbox) {
    return Math.max(pxToUm(HOVER_HIT_PX, bbox), MIN_HOVER_HIT_UM);
  }

  function isNearAnyDotPx(px, py, drawPts, bbox) {
    const FACTOR = 1.35;
  
    for (let i = 0; i < drawPts.length; i++) {
      const p = drawPts[i];
      const s = worldToScreen(p.x, p.y, bbox);
      const r = getPointRadiusPx(p.size) * FACTOR;
  
      const dx = px - s.x;
      const dy = py - s.y;
  
      if (dx * dx + dy * dy <= r * r) return true;
    }
  
    return false;
  }

  function getStarOuterRadius(group) {
    const n = group?.keyCount || 0;
    if (n <= 2) return 5;
    if (n === 3) return 7;
    if (n === 4) return 9;
    if (n === 5) return 11;
    return 13;
  }

  function getStarInnerRadius(group) {
    return Math.max(2.5, getStarOuterRadius(group) * 0.48);
  }

  function drawStar(x, y, outerR = 5, innerR = 2.5, spikes = 5) {
    ctx.save();
    ctx.beginPath();

    let rot = Math.PI / 2 * 3;
    ctx.moveTo(x, y - outerR);

    const step = Math.PI / spikes;
    for (let i = 0; i < spikes; i++) {
      ctx.lineTo(x + Math.cos(rot) * outerR, y + Math.sin(rot) * outerR);
      rot += step;
      ctx.lineTo(x + Math.cos(rot) * innerR, y + Math.sin(rot) * innerR);
      rot += step;
    }

    ctx.lineTo(x, y - outerR);
    ctx.closePath();

    ctx.fillStyle = "#FF1744";
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 1;
    ctx.fill();
    ctx.stroke();
    ctx.restore();
  }

  function buildOverlapGroups(filteredPoints, selectedKeys, offsetUm) {
    if (!filteredPoints || filteredPoints.length === 0) return [];

    const parent = new Array(filteredPoints.length).fill(0).map((_, i) => i);

    function find(x) {
      while (parent[x] !== x) {
        parent[x] = parent[parent[x]];
        x = parent[x];
      }
      return x;
    }

    function union(a, b) {
      const ra = find(a);
      const rb = find(b);
      if (ra !== rb) parent[rb] = ra;
    }

    for (let i = 0; i < filteredPoints.length; i++) {
      for (let j = i + 1; j < filteredPoints.length; j++) {
        const a = filteredPoints[i];
        const b = filteredPoints[j];

        if (a.k === b.k) continue;

        const d = Utils.dist(a.x, a.y, b.x, b.y);
        if (d <= offsetUm) {
          union(i, j);
        }
      }
    }

    const groupsMap = new Map();

    filteredPoints.forEach((p, idx) => {
      const root = find(idx);
      if (!groupsMap.has(root)) groupsMap.set(root, []);
      groupsMap.get(root).push(p);
    });

    const groups = [];

    groupsMap.forEach((pts) => {
      const keySet = new Set(pts.map((p) => p.k));
      if (keySet.size < 2) return;

      const centerX = pts.reduce((s, p) => s + p.x, 0) / pts.length;
      const centerY = pts.reduce((s, p) => s + p.y, 0) / pts.length;

      groups.push({
        id: `${Math.round(centerX)}_${Math.round(centerY)}_${pts.length}`,
        x: centerX,
        y: centerY,
        points: pts,
        keySet,
        keyCount: keySet.size,
        pointCount: pts.length,
        selectedTotal: selectedKeys.length
      });
    });

    return groups;
  }

  function drawOverlapStars(overlapGroups, bbox) {
    if (!overlapGroups || !overlapGroups.length) return;

    overlapGroups.forEach((group) => {
      const s = worldToScreen(group.x, group.y, bbox);
      drawStar(
        s.x,
        s.y,
        getStarOuterRadius(group),
        getStarInnerRadius(group),
        5
      );
    });
  }

  function drawAll() {
    ensureKeyColors(State.selectedKeys || []);
    renderLegend();

    const rect = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.floor(rect.width || canvas.parentElement?.clientWidth || 300));
    canvas.height = Math.max(1, Math.floor(rect.height || canvas.parentElement?.clientHeight || 300));

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    drawAxes();

    const keys = State.selectedKeys || [];
    const pts = allPoints(keys);
    const bbox = computeBounds(pts);

    const sizes = getAllowedSizes();
    const types = getAllowedTypes();

    const drawPts = pts.filter((p) => {
      if (sizes && !sizes.includes(p.size)) return false;
      if (types && !types.includes(p.type)) return false;
      return true;
    });

    drawPts.forEach((p) => {
      const s = worldToScreen(p.x, p.y, bbox);
      ctx.fillStyle = p.color;
      ctx.beginPath();
      ctx.arc(s.x, s.y, getPointRadiusPx(p.size), 0, Math.PI * 2);
      ctx.fill();
    });

    const overlapGroups = buildOverlapGroups(drawPts, keys, getOffsetUm());

    State.overlapGroups = overlapGroups;
    State._lastDrawPoints = drawPts;
    State._lastBBox = bbox;

    const overlapHitTotal = overlapGroups.reduce((s, g) => s + (g.keyCount || 0), 0);

    updateOverlapSummary(
      overlapGroups.length,
      keys.length,
      //overlapHitTotal
    );

    drawAxisTicks(bbox);
    drawOverlapStars(overlapGroups, bbox);

    if (View.boxZoom && View.box) {
      const b = View.box;
      ctx.save();
      ctx.strokeStyle = "#10b981";
      ctx.setLineDash([5, 4]);
      ctx.strokeRect(
        Math.min(b.x1, b.x2),
        Math.min(b.y1, b.y2),
        Math.abs(b.x2 - b.x1),
        Math.abs(b.y2 - b.y1)
      );
      ctx.restore();
    }
  }

  const tip = document.createElement("div");
  tip.className = "ol-defect-map-tooltip";
  tip.style.display = "none";
  document.body.appendChild(tip);

  function updateTooltip(clientX, clientY, contentHtml, options = {}) {
    if (!contentHtml) {
      tip.innerHTML = "";
      tip.style.display = "none";
      return;
    }

    const mode = options.mode || "hover";
    const gapX = mode === "click" ? CLICK_GAP_X : HOVER_GAP_X;
    const gapY = mode === "click" ? CLICK_GAP_Y : HOVER_GAP_Y;

    tip.innerHTML = contentHtml;
    tip.style.display = "block";

    const tipRect = tip.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    let left = clientX + gapX;
    let top = clientY + gapY;

    if (left + tipRect.width > vw - VIEWPORT_PAD) {
      left = clientX - tipRect.width - gapX;
    }

    if (top + tipRect.height > vh - VIEWPORT_PAD) {
      top = clientY - tipRect.height - gapY;
    }

    left = Math.max(VIEWPORT_PAD, left);
    top = Math.max(VIEWPORT_PAD, top);

    tip.style.left = `${left}px`;
    tip.style.top = `${top}px`;
  }

  function renderStarSummary(group) {
    const wrap = document.getElementById("ol-defect-map-star-summary");
    const title = document.getElementById("ol-defect-map-star-summary-title");
    const body = document.getElementById("ol-defect-map-star-summary-body");
    if (!wrap || !body) return;

    if (!group) {
      wrap.style.display = "none";
      body.innerHTML = "";
      return;
    }

    const glassList = [...group.keySet]
      .map((k) => Utils.parseKey(k).sheet_id_chip_id)
      .filter(Boolean);

    const uniqueGlassList = [...new Set(glassList)];

    title.innerHTML = `同點統計 (中心座標：<b>${Math.round(group.x)}</b>, <b>${Math.round(group.y)})</b>`
    body.innerHTML = `
      <div>有 defect 的片數 / 總片數：<b>${group.keyCount}</b> / <b>${group.selectedTotal}</b> ; 同點內 defect 點數：<b>${group.pointCount}</div>
      <div>Glass：${uniqueGlassList.join("、")}</div>
    `;

    /*body.innerHTML = `
      <div>有 defect 的片數 / 總片數：<b>${group.keyCount}</b> / <b>${group.selectedTotal}</b></div>
      <div>同點內 defect 點數：<b>${group.pointCount}</b></div>
      <div>中心座標：<b>${Math.round(group.x)}</b>, <b>${Math.round(group.y)}</b></div>
      <div>Glass：${uniqueGlassList.join("、")}</div>
    `;*/

    wrap.style.display = "block";
  }

  function clearStarSummary() {
    renderStarSummary(null);
  }

  function findWithinByKeyAtWorld(keys, world, hitUm) {
    const result = [];

    keys.forEach((k) => {
      const list = State.DefectCache[k] || [];
      let within = list.filter((d) => Utils.dist(world.x, world.y, +d.x, +d.y) <= hitUm);

      if (!within.length && list.length) {
        let best = null;
        let bestDist = Infinity;

        list.forEach((d) => {
          const dd = Utils.dist(world.x, world.y, +d.x, +d.y);
          if (dd < bestDist) {
            bestDist = dd;
            best = d;
          }
        });

        if (best && bestDist <= hitUm * 1.25) {
          within = [best];
        }
      }

      result.push({ key: k, list: within });
    });

    return result;
  }

  function buildClickDetailHtml(keys, world, hitUm) {
    const rows = findWithinByKeyAtWorld(keys, world, hitUm);

    let html = `
      <div class="ol-defect-map-tooltip-click-block">
        <div><b>Click</b>：${(world.x / UM_PER_MM).toFixed(3)} mm, ${(world.y / UM_PER_MM).toFixed(3)} mm</div>
      </div>
    `;

    rows.forEach(({ key: k, list: within }) => {
      const color = (State.keyColors && State.keyColors[k]) || "#ccc";

      html += `<div class="key"><span class="sw" style="background:${color}"></span><b>${k}</b></div>`;

      if (within.length) {
        html += `<table>`;
        within.forEach((d) => {
          const chip = d.chip ?? "";
          const sz = d.size ?? "";
          html += `<tr><td>x=${Math.round(d.x)} µm, y=${Math.round(d.y)} µm</td><td>${chip}</td><td>${sz}</td></tr>`;
        });
        html += `</table>`;
      } else {
        html += `<div class="muted">（無符合）</div>`;
      }
    });

    return html;
  }

  function handleHover(ev) {
    const rect = canvas.getBoundingClientRect();
    const px = ev.clientX - rect.left;
    const py = ev.clientY - rect.top;

    const keys = State.selectedKeys;
    if (!keys || !keys.length) {
      updateTooltip(0, 0, "");
      View.hoveringDot = false;
      refreshCursor();
      return;
    }

    const pts = allPoints(keys);
    const bbox = computeBounds(pts);
    const world = screenToWorld(px, py, bbox);

    const sizes = getAllowedSizes();
    const types = getAllowedTypes();

    const drawPts = pts.filter((p) => {
      if (sizes && !sizes.includes(p.size)) return false;
      if (types && !types.includes(p.type)) return false;
      return true;
    });

    View.hoveringDot = isNearAnyDotPx(px, py, drawPts, bbox);
    refreshCursor();

    const hitUm = getHoverHitUm(bbox);

    let html = `<div class="row"><b>Cursor</b>：${(world.x / UM_PER_MM).toFixed(3)} mm, ${(world.y / UM_PER_MM).toFixed(3)} mm</div>`;

    keys.forEach((k) => {
      const color = (State.keyColors && State.keyColors[k]) || "#ccc";
      const list = State.DefectCache[k] || [];
      const within = list.filter((d) => Utils.dist(world.x, world.y, +d.x, +d.y) <= hitUm);

      html += `<div class="key"><span class="sw" style="background:${color}"></span><b>${k}</b></div>`;

      if (within.length) {
        html += `<table>`;
        within.forEach((d) => {
          const chip = d.chip ?? "";
          const sz = d.size ?? "";
          html += `<tr><td>x=${Math.round(d.x)} µm, y=${Math.round(d.y)} µm</td><td>${chip}</td><td>${sz}</td></tr>`;
        });
        html += `</table>`;
      } else {
        html += `<div class="muted">（無符合）</div>`;
      }
    });

    updateTooltip(ev.clientX, ev.clientY, html, { mode: "hover" });
  }

  canvas.addEventListener("mousemove", handleHover);
  canvas.addEventListener("mouseleave", () => {
    updateTooltip(0, 0, "");
    View.hoveringDot = false;
    refreshCursor();
  });

  function findClickedOverlapGroup(px, py, bbox) {
    const groups = State.overlapGroups || [];
    if (!groups.length) return null;

    let best = null;
    let bestDist = Infinity;

    groups.forEach((group) => {
      const s = worldToScreen(group.x, group.y, bbox);
      const r = getStarOuterRadius(group) + 4;
      const dx = px - s.x;
      const dy = py - s.y;
      const dist = Math.sqrt(dx * dx + dy * dy);

      if (dist <= r && dist < bestDist) {
        best = group;
        bestDist = dist;
      }
    });

    return best;
  }

  function renderClickImages(keys, world, hitUm) {
    const container = document.getElementById("ol-defect-map-info-container");
    if (!container) return;
    container.innerHTML = "";
  
    const rows = findWithinByKeyAtWorld(keys, world, hitUm);
  
    rows.forEach(({ key: k, list: within }) => {
      const block = document.createElement("div");
      block.className = "ol-defect-map-offset-img-group";
  
      const title = document.createElement("div");
      title.className = "ol-defect-map-offset-title";
      title.textContent = `${k} (${within.length})`;
      block.appendChild(title);
  
      const grid = document.createElement("div");
      grid.className = "ol-defect-map-offset-img-grid";
  
      let imageCount = 0;
  
      if (within.length) {
        within.forEach((d, idx) => {
          const src = Utils.buildImageUrl(d);
          if (!src) return;
  
          imageCount += 1;
  
          const fig = document.createElement("figure");
          fig.className = "ol-defect-map-img-card";
          fig.innerHTML = `<img loading="lazy" class="zoomable" src="${src}" alt="${k} #${idx + 1}">`;
          grid.appendChild(fig);
        });
      }
  
      if (imageCount > 0) {
        block.classList.add("has-images");
        block.appendChild(grid);
      } else {
        block.classList.add("no-images");
  
        const empty = document.createElement("div");
        empty.className = "ol-defect-map-offset-empty";
        empty.textContent = "無對應影像";
        block.appendChild(empty);
      }
  
      container.appendChild(block);
    });
  }
  function handleClick(ev) {
    const rect = canvas.getBoundingClientRect();
    const px = ev.clientX - rect.left;
    const py = ev.clientY - rect.top;

    const keys = State.selectedKeys || [];
    if (!keys.length) return;

    const pts = allPoints(keys);
    const bbox = computeBounds(pts);
    const world = screenToWorld(px, py, bbox);
    const hitUm = getClickHitUm(bbox);

    const hitGroup = findClickedOverlapGroup(px, py, bbox);

    if (hitGroup) {
      renderStarSummary(hitGroup);
    } else {
      clearStarSummary();
    }

    const html = buildClickDetailHtml(keys, world, hitUm);
    updateTooltip(ev.clientX, ev.clientY, html, { mode: "click" });
    renderClickImages(keys, world, hitUm);
  }

  const btnReset = document.getElementById("ol-defect-map-btn-reset");
  const btnIn = document.getElementById("ol-defect-map-btn-zoom-in");
  const btnOut = document.getElementById("ol-defect-map-btn-zoom-out");
  const btnBox = document.getElementById("ol-defect-map-btn-box-zoom");
  const btnClr = document.getElementById("ol-defect-map-btn-clear-box");

  let dragging = false;

  function refreshCursor() {
    if (dragging) canvas.style.cursor = "grabbing";
    else if (View.boxZoom) canvas.style.cursor = "crosshair";
    else if (View.hoveringDot) canvas.style.cursor = "pointer";
    else canvas.style.cursor = "default";
  }
  refreshCursor();

  if (btnReset) btnReset.addEventListener("click", () => {
    View.scale = 1;
    View.tx = 0;
    View.ty = 0;
    updateTooltip(0, 0, "");
    drawAll();
    refreshCursor();
  });

  if (btnIn) btnIn.addEventListener("click", () => {
    View.scale *= 1.25;
    drawAll();
    refreshCursor();
  });

  if (btnOut) btnOut.addEventListener("click", () => {
    View.scale /= 1.25;
    drawAll();
    refreshCursor();
  });

  if (btnBox) btnBox.addEventListener("click", () => {
    View.boxZoom = !View.boxZoom;
    View.box = null;
    drawAll();
    refreshCursor();
  });

  if (btnClr) btnClr.addEventListener("click", () => {
    View.box = null;
    drawAll();
    refreshCursor();
  });

  canvas.addEventListener("mousedown", (ev) => {
    if (View.boxZoom) {
      const r = canvas.getBoundingClientRect();
      View.box = {
        x1: ev.clientX - r.left,
        y1: ev.clientY - r.top,
        x2: ev.clientX - r.left,
        y2: ev.clientY - r.top,
      };
    } else {
      dragging = true;
      View._lastX = ev.clientX;
      View._lastY = ev.clientY;
      updateTooltip(0, 0, "");
    }
    refreshCursor();
  });

  window.addEventListener("mousemove", (ev) => {
    if (View.boxZoom && View.box) {
      const r = canvas.getBoundingClientRect();
      View.box.x2 = ev.clientX - r.left;
      View.box.y2 = ev.clientY - r.top;
      drawAll();
      return;
    }

    if (dragging) {
      View.tx += (ev.clientX - View._lastX);
      View.ty += (ev.clientY - View._lastY);
      View._lastX = ev.clientX;
      View._lastY = ev.clientY;
      drawAll();
    }
  });

  window.addEventListener("mouseup", () => {
    if (View.boxZoom && View.box) {
      const b = View.box;
      if (b && Math.abs(b.x2 - b.x1) > 10 && Math.abs(b.y2 - b.y1) > 10) {
        View.scale *= 1.4;
        View.tx -= (Math.min(b.x1, b.x2) + Math.abs(b.x2 - b.x1) / 2 - canvas.clientWidth / 2);
        View.ty -= (Math.min(b.y1, b.y2) + Math.abs(b.y2 - b.y1) / 2 - canvas.clientHeight / 2);
      }
      View.box = null;
      drawAll();
    }

    dragging = false;
    refreshCursor();
  });

  canvas.addEventListener("click", handleClick);

  Bus.on("defect-refresh", () => {
    updateTooltip(0, 0, "");
    drawAll();
  });
  Bus.on("selection-changed", () => {
    clearStarSummary();
    updateTooltip(0, 0, "");
    drawAll();
  });
  Bus.on("map-refresh", () => {
    updateTooltip(0, 0, "");
    drawAll();
  });

  Bus.on("selection-changed", renderLegend);
  Bus.on("defect-refresh", renderLegend);
  Bus.on("map-refresh", renderLegend);

  Bus.on("clear-offset-images", () => {
    const container = document.getElementById("ol-defect-map-info-container");
    if (container) container.innerHTML = "";
    clearStarSummary();
    updateTooltip(0, 0, "");
  });

  drawAll();
})();
