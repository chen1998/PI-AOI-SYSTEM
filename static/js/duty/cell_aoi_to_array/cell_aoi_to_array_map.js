// static/js/duty/cell_aoi_to_array/cell_aoi_to_array_map.js
(function () {
  "use strict";

  window.CELL_AOI_TO_ARRAY = window.CELL_AOI_TO_ARRAY || {};
  const MOD = window.CELL_AOI_TO_ARRAY;

  const CANVAS_ID = "cell-aoi-to-array-defect-map-canvas";
  const LEGEND_ID = "cell-aoi-to-array-defect-map-legend";
  const TOOLTIP_ID = "cell-aoi-to-array-defect-map-tooltip";

  const GROUPS = [
    { key: "same_point", label: "同點", shape: "star", icon: "★" },
    { key: "cell_aoi", label: "CELL AOI", shape: "circle", icon: "●" },
    { key: "source", label: "前站站點", shape: "square", icon: "■" }
  ];

  const SIZES = ["S", "M", "L", "O"];

  const SIZE_COLORS = {
    S: "#7FDBFF",
    M: "#FF851B",
    L: "#2ECC40",
    O: "#FF4136"
  };

  const GROUP_ICON_COLOR = "#dce8f5";

  const SIZE_RADIUS = {
    S: 3,
    M: 5,
    L: 7,
    O: 9
  };

  const SIZE_STAR_FONT = {
    S: 14,
    M: 17,
    L: 20,
    O: 23
  };

  const DEFAULT_AXIS = {
    min_x: 0,
    max_x: 1850000,
    min_y: 0,
    max_y: 1500000
  };

  const view = {
    canvas: null,
    ctx: null,
    legend: null,
    tooltip: null,
  
    row: null,
    points: [],
  
    axis: Object.assign({}, DEFAULT_AXIS),
    zoom: Object.assign({}, DEFAULT_AXIS),
  
    boxMode: false,
    dragging: false,
    dragStart: null,
    dragEnd: null,
  
    hoverPoint: null,
    selectedPoint: null,
    lastPlot: null,
  
    // 不用 boolean，改記住目前綁定的是哪一個 canvas
    boundCanvas: null
  };

  MOD.Map = {
    render,
    redraw,
    resetView,
    toggleBoxMode,
    clearSelectedPoint,
    clear,
    refreshLegend,
  };

  function clear() {
    view.row = null;
    view.points = [];
    view.hoverPoint = null;
    view.selectedPoint = null;
    view.dragging = false;
    view.dragStart = null;
    view.dragEnd = null;
    view.boxMode = false;
    view.lastPlot = null;
  
    hideTooltip();
  
    const canvas = document.getElementById(CANVAS_ID);
    const legend = document.getElementById(LEGEND_ID);
    const tooltip = document.getElementById(TOOLTIP_ID);
  
    if (canvas) {
      const ctx = canvas.getContext("2d");
      if (ctx) {
        ctx.clearRect(0, 0, canvas.width || canvas.clientWidth || 0, canvas.height || canvas.clientHeight || 0);
      }
    }
  
    if (legend) {
      legend.innerHTML = "";
    }
  
    if (tooltip) {
      tooltip.style.display = "none";
      tooltip.innerHTML = "";
    }
  }

  function refreshLegend() {
    renderLegend();
  }
  

  function render(row) {
    view.canvas = document.getElementById(CANVAS_ID);
    view.legend = document.getElementById(LEGEND_ID);
    view.tooltip = document.getElementById(TOOLTIP_ID);
    view.ctx = view.canvas ? view.canvas.getContext("2d") : null;

    view.row = row || null;
    view.points = [];
    view.hoverPoint = null;
    view.selectedPoint = null;
    view.dragging = false;
    view.dragStart = null;
    view.dragEnd = null;
    view.boxMode = false;

    const axis = MOD.State.getAxisConfig ? MOD.State.getAxisConfig() : DEFAULT_AXIS;
    view.axis = normalizeAxis(axis);
    view.zoom = Object.assign({}, view.axis);

    if (!view.canvas || !view.ctx) return;

    bindCanvasEvents();
    renderLegend();
    updateCursor();
    resizeCanvas();
    redraw();
  }

  function redraw() {
    if (!view.canvas || !view.ctx) return;

    resizeCanvas();

    const ctx = view.ctx;
    const canvas = view.canvas;
    const plot = getPlotRect(canvas);

    view.lastPlot = plot;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    drawBackground(ctx, canvas, plot);
    drawAxes(ctx, plot);

    view.points = buildVisiblePoints(plot);
    drawPoints(ctx, view.points);

    if (view.dragging && view.dragStart && view.dragEnd) {
      drawSelectionBox(ctx, view.dragStart, view.dragEnd);
    }

    updateCursor();
  }

  function resetView() {
    view.zoom = Object.assign({}, view.axis);
    view.hoverPoint = null;
    view.dragging = false;
    view.dragStart = null;
    view.dragEnd = null;
    hideTooltip();
    redraw();
  }

  function toggleBoxMode() {
    view.boxMode = !view.boxMode;
    view.dragging = false;
    view.dragStart = null;
    view.dragEnd = null;
    hideTooltip();
    updateCursor();
    redraw();
  }

  function clearSelectedPoint() {
    view.selectedPoint = null;
    redraw();
  }

  function bindCanvasEvents() {
    if (!view.canvas) return;
  
    /*
     * 每次 Sheet.render(row) 都會建立新的 canvas。
     * 不能用單一 boolean 擋掉第二次綁定。
     * 只要 canvas DOM 換了，就要重新綁事件。
     */
    if (view.boundCanvas === view.canvas) return;
  
    view.boundCanvas = view.canvas;
  
    view.canvas.addEventListener("mousemove", function (evt) {
      const pos = getMousePos(evt);
  
      if (view.boxMode && view.dragging) {
        view.dragEnd = pos;
        redraw();
        return;
      }
  
      const hit = hitTest(pos.x, pos.y);
      view.hoverPoint = hit;
  
      if (hit) {
        showTooltip(hit, evt);
      } else {
        hideTooltip();
      }
  
      updateCursor();
      redraw();
    });
  
    view.canvas.addEventListener("mouseleave", function () {
      view.hoverPoint = null;
      view.dragging = false;
      view.dragStart = null;
      view.dragEnd = null;
      hideTooltip();
      updateCursor();
      redraw();
    });
  
    view.canvas.addEventListener("mousedown", function (evt) {
      if (!view.boxMode) return;
  
      const pos = getMousePos(evt);
      view.dragging = true;
      view.dragStart = pos;
      view.dragEnd = pos;
      hideTooltip();
      updateCursor();
      redraw();
    });
  
    window.addEventListener("mouseup", function () {
      if (!view.boxMode || !view.dragging) return;
  
      view.dragging = false;
  
      if (view.dragStart && view.dragEnd) {
        applySelectionZoom(view.dragStart, view.dragEnd);
      }
  
      view.dragStart = null;
      view.dragEnd = null;
      updateCursor();
      redraw();
    });
  
    view.canvas.addEventListener("click", function (evt) {
      if (view.boxMode) return;
  
      const pos = getMousePos(evt);
      const hit = hitTest(pos.x, pos.y);
  
      if (!hit) return;
  
      view.selectedPoint = hit;
  
      if (MOD.DefectTable && MOD.DefectTable.focusByMapPoint) {
        MOD.DefectTable.focusByMapPoint(hit);
      }
  
      redraw();
    });
  }
  

  function renderLegend() {
    if (!view.legend) return;

    const filters = getMapFilters();

    view.legend.innerHTML = "";

    const groupBlock = document.createElement("div");
    groupBlock.className = "cell-aoi-to-array-map-legend-block";

    const groupTitle = document.createElement("div");
    groupTitle.className = "cell-aoi-to-array-map-legend-title";
    groupTitle.textContent = "Defect Group";
    groupBlock.appendChild(groupTitle);

    GROUPS.forEach(function (group) {
      const item = createLegendCheckbox({
        type: "group",
        value: group.key,
        label: group.label,
        checked: filters.groups.has(group.key),
        color: GROUP_ICON_COLOR,
        shape: group.shape,
        icon: group.icon
      });

      groupBlock.appendChild(item);
    });

    const sizeBlock = document.createElement("div");
    sizeBlock.className = "cell-aoi-to-array-map-legend-block";

    const sizeTitle = document.createElement("div");
    sizeTitle.className = "cell-aoi-to-array-map-legend-title";
    sizeTitle.textContent = "Defect Size";
    sizeBlock.appendChild(sizeTitle);

    SIZES.forEach(function (size) {
      const item = createLegendCheckbox({
        type: "size",
        value: size,
        label: size,
        checked: filters.sizes.has(size),
        color: SIZE_COLORS[size] || SIZE_COLORS.O,
        shape: "circle",
        icon: "●"
      });

      sizeBlock.appendChild(item);
    });

    const hint = document.createElement("div");
    hint.className = "cell-aoi-to-array-map-legend-hint";
    hint.textContent = buildLegendHint();

    view.legend.appendChild(groupBlock);
    view.legend.appendChild(sizeBlock);
    view.legend.appendChild(hint);
  }

  function createLegendCheckbox(options) {
    const label = document.createElement("label");
    label.className = "cell-aoi-to-array-map-legend-item";

    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = Boolean(options.checked);

    input.addEventListener("change", async function () {
      await handleLegendChange(options.type, options.value, input.checked);
    });

    const swatch = document.createElement("span");
    swatch.className = [
      "cell-aoi-to-array-map-legend-swatch",
      options.shape ? `shape-${options.shape}` : "",
      options.type ? `type-${options.type}` : ""
    ].filter(Boolean).join(" ");

    swatch.style.backgroundColor = "transparent";
    swatch.style.border = "none";
    swatch.style.boxShadow = "none";
    swatch.style.borderRadius = "0";
    swatch.style.color = options.color || "#cfd7df";
    swatch.textContent = options.icon || "";

    const text = document.createElement("span");
    text.className = "cell-aoi-to-array-map-legend-text";
    text.textContent = options.label || options.value;

    label.appendChild(input);
    label.appendChild(swatch);
    label.appendChild(text);

    return label;
  }

  async function handleLegendChange(type, value, checked) {
    const filters = getMapFilters();

    if (type === "group") {
      if (checked) {
        filters.groups.add(value);
      } else {
        filters.groups.delete(value);
      }

      /*
       * 新邏輯：
       * - 點 table 詳情後，Sheet.preloadFullDefectGroups() 會預先把 cell/source group 存到 row。
       * - 這裡仍保留 ensureGroupLoaded 保護，避免預載失敗時使用者勾選還是能補打後端。
       */
      if ((value === "source" || value === "cell_aoi") && checked) {
        await ensureGroupLoaded(value);
      }

      if (!checked && view.selectedPoint && view.selectedPoint.group === value) {
        view.selectedPoint = null;

        if (MOD.DefectTable && MOD.DefectTable.clearFocus) {
          MOD.DefectTable.clearFocus();
        }
      }
    }

    if (type === "size") {
      if (checked) {
        filters.sizes.add(value);
      } else {
        filters.sizes.delete(value);
      }

      if (
        !checked &&
        view.selectedPoint &&
        normalizeSize(view.selectedPoint.defect_size) === normalizeSize(value)
      ) {
        view.selectedPoint = null;

        if (MOD.DefectTable && MOD.DefectTable.clearFocus) {
          MOD.DefectTable.clearFocus();
        }
      }
    }

    renderLegend();
    redraw();
  }

  async function ensureGroupLoaded(groupKey) {
    const row = view.row || MOD.State.state.selectedRow;
    if (!row) return;

    MOD.State.ensureRowDefectContainers(row);

    if (groupKey && row.groupsLoaded && row.groupsLoaded[groupKey]) {
      return;
    }

    const filters = getMapFilters();

    if (filters.fullGroupsLoading) {
      return;
    }

    filters.fullGroupsLoading = true;
    renderLegend();

    try {
      const result = await MOD.API.fetchDefectGroups(row);

      const groups = result.defectGroups || {};
      const loaded = result.groupsLoaded || {};

      if (Array.isArray(groups.cell_aoi)) {
        row.defectGroups.cell_aoi = groups.cell_aoi;
      }

      if (Array.isArray(groups.source)) {
        row.defectGroups.source = groups.source;
      }

      row.groupsLoaded.cell_aoi = Boolean(
        loaded.cell_aoi ||
        row.defectGroups.cell_aoi.length
      );

      row.groupsLoaded.source = Boolean(
        loaded.source ||
        row.defectGroups.source.length
      );

      filters.fullGroupsLoaded = Boolean(
        row.groupsLoaded.cell_aoi &&
        row.groupsLoaded.source
      );
    } catch (err) {
      console.error("[cell-aoi-to-array-map] fetchDefectGroups failed:", err);

      if (MOD.UI && MOD.UI.toast) {
        MOD.UI.toast(`載入 defect group 失敗：${err.message || err}`);
      } else {
        alert(`載入 defect group 失敗：${err.message || err}`);
      }

      if (groupKey) {
        filters.groups.delete(groupKey);
      }
    } finally {
      filters.fullGroupsLoading = false;
      renderLegend();
      redraw();
    }
  }

  function buildLegendHint() {
    const row = view.row || MOD.State.state.selectedRow;

    if (!row) return "";

    const loaded = row.groupsLoaded || {};
    const filters = getMapFilters();

    if (filters.fullGroupsLoading) {
      return "完整 defect group 載入中...";
    }

    const sameCnt = countGroup(row, "same_point");
    const cellCnt = countGroup(row, "cell_aoi");
    const sourceCnt = countGroup(row, "source");

    const cellText = loaded.cell_aoi ? cellCnt : "未載入";
    const sourceText = loaded.source ? sourceCnt : "未載入";

    const focusText = view.selectedPoint
      ? ` / 已選 ${getGroupShapeLabel(view.selectedPoint.group)} ${getGroupLabel(view.selectedPoint.group)} #${view.selectedPoint.index || "-"}`
      : "";

    return `同點 ${sameCnt} / CELL ${cellText} / 前站 ${sourceText}${focusText}`;
  }

  function countGroup(row, key) {
    return Array.isArray(row?.defectGroups?.[key])
      ? row.defectGroups[key].length
      : 0;
  }

  function buildVisiblePoints(plot) {
    const row = view.row || MOD.State.state.selectedRow;
    if (!row) return [];

    MOD.State.ensureRowDefectContainers(row);

    const filters = getMapFilters();
    const out = [];

    GROUPS.forEach(function (groupInfo) {
      const groupKey = groupInfo.key;

      if (!filters.groups.has(groupKey)) return;

      const items = Array.isArray(row.defectGroups[groupKey])
        ? row.defectGroups[groupKey]
        : [];

      items.forEach(function (d, idx) {
        const point = normalizeMapPoint(d, groupKey, idx + 1);

        if (!point) return;

        if (!filters.sizes.has(point.defect_size)) return;

        const projected = project(point.x, point.y, plot);

        if (!Number.isFinite(projected.x) || !Number.isFinite(projected.y)) return;

        out.push(Object.assign({}, point, {
          px: projected.x,
          py: projected.y,

          shape: groupInfo.shape,
          color: SIZE_COLORS[point.defect_size] || SIZE_COLORS.O,

          radius: getPointRadius(point.defect_size),
          starFont: getStarFontSize(point.defect_size)
        }));
      });
    });

    return out;
  }

  function normalizeMapPoint(d, groupKey, fallbackIndex) {
    if (!d || typeof d !== "object") return null;

    let x = null;
    let y = null;

    if (groupKey === "same_point") {
      x = toNumber(d.x ?? d.cell_x ?? d.cell?.trans_x);
      y = toNumber(d.y ?? d.cell_y ?? d.cell?.trans_y);
    } else if (groupKey === "cell_aoi") {
      x = toNumber(d.x ?? d.cell_x ?? d.cell?.trans_x);
      y = toNumber(d.y ?? d.cell_y ?? d.cell?.trans_y);
    } else if (groupKey === "source") {
      x = toNumber(d.x ?? d.source_x ?? d.source?.trans_x ?? d.source?.display?.trans_x);
      y = toNumber(d.y ?? d.source_y ?? d.source?.trans_y ?? d.source?.display?.trans_y);
    }

    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;

    const size = normalizeSize(
      d.defect_size ||
      d.cell_defect_size ||
      d.source_defect_size ||
      d.cell?.defect_size ||
      d.source?.defect_size ||
      d.source?.display?.defect_size
    );

    return {
      raw: d,
      group: groupKey,
      index: d.index || fallbackIndex,

      x,
      y,
      defect_size: size,

      defect_code:
        d.defect_code ||
        d.cell_defect_code ||
        d.source_defect_code ||
        d.cell?.defect_code ||
        d.source?.defect_code ||
        d.source?.display?.defect_code ||
        "",

      img: d.img || d.cell_img || d.source_img || "",
      cell_img: d.cell_img || d.cell?.img_url_path || "",
      source_img: d.source_img || d.source?.img_url_path || "",

      cell_defect_uid:
        d.cell_defect_uid ||
        d.cell?.cell_defect_uid ||
        "",

      source_defect_uid:
        d.source_defect_uid ||
        d.source?.source_defect_uid ||
        "",

      source_op_id:
        d.source_op_id ||
        d.source?.source_op_id ||
        d.source?.display?.source_op_id ||
        "",

      cell_x: d.cell_x ?? d.cell?.trans_x ?? "",
      cell_y: d.cell_y ?? d.cell?.trans_y ?? "",

      source_x: d.source_x ?? d.source?.trans_x ?? d.source?.display?.trans_x ?? "",
      source_y: d.source_y ?? d.source?.trans_y ?? d.source?.display?.trans_y ?? "",

      distance: d.distance ?? d.match?.distance ?? "",
      dx: d.dx ?? d.match?.dx ?? "",
      dy: d.dy ?? d.match?.dy ?? "",

      match: Boolean(d.match || groupKey === "same_point")
    };
  }

  function drawBackground(ctx, canvas, plot) {
    ctx.save();

    ctx.fillStyle = "#10131a";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.fillStyle = "#151a22";
    ctx.fillRect(plot.left, plot.top, plot.width, plot.height);

    ctx.strokeStyle = "#303746";
    ctx.lineWidth = 1;
    ctx.strokeRect(plot.left, plot.top, plot.width, plot.height);

    ctx.restore();
  }

  function drawAxes(ctx, plot) {
    const z = view.zoom;

    ctx.save();

    ctx.strokeStyle = "rgba(255,255,255,.08)";
    ctx.lineWidth = 1;
    ctx.fillStyle = "#8e99a8";
    ctx.font = "11px sans-serif";

    const gridCount = 5;

    for (let i = 0; i <= gridCount; i += 1) {
      const gx = plot.left + (plot.width / gridCount) * i;
      const gy = plot.top + (plot.height / gridCount) * i;

      ctx.beginPath();
      ctx.moveTo(gx, plot.top);
      ctx.lineTo(gx, plot.bottom);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(plot.left, gy);
      ctx.lineTo(plot.right, gy);
      ctx.stroke();

      const xValue = z.min_x + ((z.max_x - z.min_x) / gridCount) * i;
      const yValue = z.min_y + ((z.max_y - z.min_y) / gridCount) * i;

      ctx.fillText(formatCoord(xValue), gx + 3, plot.bottom + 16);
      ctx.fillText(formatCoord(yValue), 6, gy + 4);
    }

    ctx.fillStyle = "#cfd7df";
    ctx.fillText("Origin: left-top", plot.left, plot.top - 10);

    ctx.restore();
  }

  function drawPoints(ctx, points) {
    const nonStarPoints = points.filter(function (p) {
      return p.shape !== "star";
    });

    const starPoints = points.filter(function (p) {
      return p.shape === "star";
    });

    nonStarPoints.forEach(function (p) {
      if (p.shape === "square") {
        drawSquare(ctx, p);
      } else {
        drawCircle(ctx, p);
      }
    });

    starPoints.forEach(function (p) {
      drawStar(ctx, p);
    });
  }

  function drawCircle(ctx, p) {
    ctx.save();

    ctx.beginPath();
    ctx.arc(p.px, p.py, p.radius, 0, Math.PI * 2);
    ctx.fillStyle = p.color;
    ctx.globalAlpha = getPointAlpha(p);
    ctx.fill();

    ctx.lineWidth = getPointStrokeWidth(p);
    ctx.strokeStyle = getPointStrokeColor(p);
    ctx.stroke();

    ctx.restore();
  }

  function drawSquare(ctx, p) {
    const size = Math.max(6, p.radius * 2);
    const half = size / 2;

    ctx.save();

    ctx.beginPath();
    ctx.rect(p.px - half, p.py - half, size, size);

    ctx.fillStyle = p.color;
    ctx.globalAlpha = getPointAlpha(p);
    ctx.fill();

    ctx.lineWidth = getPointStrokeWidth(p);
    ctx.strokeStyle = getPointStrokeColor(p);
    ctx.stroke();

    ctx.restore();
  }

  function drawStar(ctx, p) {
    ctx.save();

    ctx.font = `${p.starFont}px sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = p.color;
    ctx.globalAlpha = getPointAlpha(p);

    ctx.shadowColor = "rgba(0,0,0,.85)";
    ctx.shadowBlur = isSelectedPoint(p) ? 8 : 5;

    ctx.fillText("★", p.px, p.py);

    ctx.shadowBlur = 0;
    ctx.strokeStyle = getPointStrokeColor(p);
    ctx.lineWidth = isSelectedPoint(p) ? 1.8 : 0.9;
    ctx.strokeText("★", p.px, p.py);

    ctx.restore();
  }

  function getPointAlpha(p) {
    if (isSelectedPoint(p)) return 1;
    if (view.hoverPoint === p) return 1;
    return 0.78;
  }

  function getPointStrokeWidth(p) {
    if (isSelectedPoint(p)) return 2.6;
    if (view.hoverPoint === p) return 2;
    return 1;
  }

  function getPointStrokeColor(p) {
    if (isSelectedPoint(p)) return "#ffffff";
    if (view.hoverPoint === p) return "#ffffff";
    return "rgba(255,255,255,.78)";
  }

  function isSelectedPoint(p) {
    if (!view.selectedPoint || !p) return false;

    if (
      view.selectedPoint.cell_defect_uid &&
      p.cell_defect_uid &&
      String(view.selectedPoint.cell_defect_uid) === String(p.cell_defect_uid)
    ) {
      return true;
    }

    if (
      view.selectedPoint.source_defect_uid &&
      p.source_defect_uid &&
      String(view.selectedPoint.source_defect_uid) === String(p.source_defect_uid)
    ) {
      return true;
    }

    return (
      view.selectedPoint.group === p.group &&
      Number(view.selectedPoint.x) === Number(p.x) &&
      Number(view.selectedPoint.y) === Number(p.y)
    );
  }

  function drawSelectionBox(ctx, start, end) {
    const x = Math.min(start.x, end.x);
    const y = Math.min(start.y, end.y);
    const w = Math.abs(end.x - start.x);
    const h = Math.abs(end.y - start.y);

    ctx.save();

    ctx.fillStyle = "rgba(92,193,255,.12)";
    ctx.strokeStyle = "#5cc1ff";
    ctx.lineWidth = 1.5;
    ctx.setLineDash([5, 3]);

    ctx.fillRect(x, y, w, h);
    ctx.strokeRect(x, y, w, h);

    ctx.restore();
  }

  function applySelectionZoom(start, end) {
    const plot = view.lastPlot;
    if (!plot) return;

    const x1 = Math.min(start.x, end.x);
    const x2 = Math.max(start.x, end.x);
    const y1 = Math.min(start.y, end.y);
    const y2 = Math.max(start.y, end.y);

    if (Math.abs(x2 - x1) < 8 || Math.abs(y2 - y1) < 8) {
      return;
    }

    const p1 = unproject(x1, y1, plot);
    const p2 = unproject(x2, y2, plot);

    view.zoom = {
      min_x: Math.min(p1.x, p2.x),
      max_x: Math.max(p1.x, p2.x),
      min_y: Math.min(p1.y, p2.y),
      max_y: Math.max(p1.y, p2.y)
    };
  }

  function project(x, y, plot) {
    const z = view.zoom;

    const xSpan = z.max_x - z.min_x;
    const ySpan = z.max_y - z.min_y;

    if (!xSpan || !ySpan) return { x: NaN, y: NaN };

    const px = plot.left + ((x - z.min_x) / xSpan) * plot.width;
    const py = plot.top + ((y - z.min_y) / ySpan) * plot.height;

    return { x: px, y: py };
  }

  function unproject(px, py, plot) {
    const z = view.zoom;

    const x = z.min_x + ((px - plot.left) / plot.width) * (z.max_x - z.min_x);
    const y = z.min_y + ((py - plot.top) / plot.height) * (z.max_y - z.min_y);

    return { x, y };
  }

  function hitTest(px, py) {
    let best = null;
    let bestDist = Infinity;

    view.points.forEach(function (p) {
      const dx = px - p.px;
      const dy = py - p.py;
      const dist = Math.sqrt(dx * dx + dy * dy);

      let hitRadius = Math.max(10, p.radius + 5);

      if (p.shape === "square") {
        hitRadius = Math.max(12, p.radius + 7);
      }

      if (p.shape === "star") {
        hitRadius = Math.max(13, p.radius + 8);
      }

      if (dist <= hitRadius && dist < bestDist) {
        best = p;
        bestDist = dist;
      }
    });

    return best;
  }

  function showTooltip(point, evt) {
    if (!view.tooltip || !point) return;

    const groupLabel = getGroupLabel(point.group);
    const shapeLabel = getGroupShapeLabel(point.group);

    const html = [
      `<b>${escapeHtml(shapeLabel)} ${escapeHtml(groupLabel)}</b>`,
      `Size: ${escapeHtml(point.defect_size || "-")}`,
      `Code: ${escapeHtml(point.defect_code || "-")}`,
      `X: ${escapeHtml(formatCoord(point.x))}`,
      `Y: ${escapeHtml(formatCoord(point.y))}`,
      point.group === "same_point" ? `dx: ${escapeHtml(point.dx ?? "-")}` : "",
      point.group === "same_point" ? `dy: ${escapeHtml(point.dy ?? "-")}` : "",
      point.group === "same_point" ? `distance: ${escapeHtml(point.distance ?? "-")}` : "",
      `<span style="opacity:.75">點擊後只顯示此 defect row</span>`
    ].filter(Boolean).join("<br/>");

    view.tooltip.innerHTML = html;
    view.tooltip.style.display = "block";

    const rect = view.canvas.getBoundingClientRect();
    const x = evt.clientX - rect.left + 14;
    const y = evt.clientY - rect.top + 14;

    view.tooltip.style.left = `${x}px`;
    view.tooltip.style.top = `${y}px`;
  }

  function hideTooltip() {
    if (!view.tooltip) return;
    view.tooltip.style.display = "none";
  }

  function getPlotRect(canvas) {
    const width = canvas.widthCss || canvas._cssWidth || canvas.clientWidth || 640;
    const height = canvas.heightCss || canvas._cssHeight || canvas.clientHeight || 420;

    const left = 54;
    const top = 32;
    const rightPad = 18;
    const bottomPad = 34;

    return {
      left,
      top,
      right: width - rightPad,
      bottom: height - bottomPad,
      width: width - left - rightPad,
      height: height - top - bottomPad
    };
  }

  function resizeCanvas() {
    if (!view.canvas) return;

    const parent = view.canvas.parentElement;
    if (!parent) return;

    const rect = parent.getBoundingClientRect();

    const width = Math.max(640, Math.floor(rect.width));
    const height = Math.max(420, Math.floor(rect.height || 520));

    const dpr = window.devicePixelRatio || 1;

    const targetWidth = Math.floor(width * dpr);
    const targetHeight = Math.floor(height * dpr);

    if (view.canvas.width !== targetWidth || view.canvas.height !== targetHeight) {
      view.canvas.width = targetWidth;
      view.canvas.height = targetHeight;
      view.canvas.style.width = `${width}px`;
      view.canvas.style.height = `${height}px`;

      if (view.ctx) {
        view.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        view.canvas._cssWidth = width;
        view.canvas._cssHeight = height;
      }
    }

    view.canvas.widthCss = width;
    view.canvas.heightCss = height;
  }

  function getMousePos(evt) {
    const rect = view.canvas.getBoundingClientRect();

    return {
      x: evt.clientX - rect.left,
      y: evt.clientY - rect.top
    };
  }

  function updateCursor() {
    if (!view.canvas) return;

    if (view.boxMode) {
      view.canvas.style.cursor = "crosshair";
      return;
    }

    if (view.hoverPoint) {
      view.canvas.style.cursor = "pointer";
      return;
    }

    view.canvas.style.cursor = "default";
  }

  function getMapFilters() {
    const state = MOD.State.state;

    if (!state.mapFilters) {
      MOD.State.resetMapFilters();
    }

    if (!(state.mapFilters.groups instanceof Set)) {
      state.mapFilters.groups = new Set(state.mapFilters.groups || ["same_point"]);
    }

    if (!(state.mapFilters.sizes instanceof Set)) {
      state.mapFilters.sizes = new Set(state.mapFilters.sizes || ["S", "M", "L", "O"]);
    }

    return state.mapFilters;
  }

  function normalizeAxis(axis) {
    const a = axis || {};

    return {
      min_x: toNumber(a.min_x ?? a.minX ?? DEFAULT_AXIS.min_x),
      max_x: toNumber(a.max_x ?? a.maxX ?? DEFAULT_AXIS.max_x),
      min_y: toNumber(a.min_y ?? a.minY ?? DEFAULT_AXIS.min_y),
      max_y: toNumber(a.max_y ?? a.maxY ?? DEFAULT_AXIS.max_y)
    };
  }

  function getPointRadius(size) {
    return SIZE_RADIUS[normalizeSize(size)] || SIZE_RADIUS.O;
  }

  function getStarFontSize(size) {
    return SIZE_STAR_FONT[normalizeSize(size)] || SIZE_STAR_FONT.O;
  }

  function normalizeSize(size) {
    const s = String(size || "").trim().toUpperCase();
    return SIZES.includes(s) ? s : "O";
  }

  function getGroupLabel(groupKey) {
    const found = GROUPS.find(g => g.key === groupKey);
    return found ? found.label : groupKey;
  }

  function getGroupShapeLabel(groupKey) {
    const found = GROUPS.find(g => g.key === groupKey);
    if (!found) return "";

    if (found.shape === "star") return "★";
    if (found.shape === "circle") return "●";
    if (found.shape === "square") return "■";

    return "";
  }

  function toNumber(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : NaN;
  }

  function formatCoord(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "-";

    if (Math.abs(n) >= 1000) {
      return Math.round(n).toLocaleString();
    }

    return String(Math.round(n * 100) / 100);
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