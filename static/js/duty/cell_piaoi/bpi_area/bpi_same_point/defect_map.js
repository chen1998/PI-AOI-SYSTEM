// static/js/bpi_area/bpi_same_point/defect_map.js
// BPI/API Same Point defect map
//
// 功能：
// - 單一 canvas 顯示 BPI / API / Same Point defect
// - BPI：圓形
// - API：三角形
// - Same Point：星形
// - 尺寸 S/M/L/O 以顏色區分，可勾選
// - Group filter 可勾選 BPI / API / Same Point 單一或複數顯示
// - 預設只顯示 Same Point
// - Hover tooltip 顯示座標、defect size、code、distance 等
// - 點 scatter 開圖片彈窗；可顯示 >=1 張圖
// - 彈窗圖片上方顯示 BPI/API、defect size、adc_def_code、retype_code
// - 點彈窗內圖片放大；點空白先關閉放大圖，再點空白關閉彈窗

(function () {
  const MOD = (window.BPI_SAME_POINT = window.BPI_SAME_POINT || {});
  const API = MOD.API;
  const DefectMap = (MOD.DefectMap = MOD.DefectMap || {});
  const state = MOD.state || {};

  const CANVAS_ID = "bpi-same-point-mini-map";
  const LEGEND_ID = "bpi-same-point-map-legend";
  const TIPS_ID = "bpi-same-point-map-tooltip";

  const DEFECT_INFO_KEYS = [
    "group",
    "glass",
    "chip_id",
    "x",
    "y",
    "defect_size",
    "adc_def_code",
    "retype_code",
    "distance",
  ];

  // 原始座標單位：um
  const AXIS = {
    minX: 0,
    maxX: 1850000,
    minY: 0,
    maxY: 1500000,
  };

  const SIZE_KEYS = ["S", "M", "L", "O"];
  const GROUP_KEYS = ["BPI", "API", "MATCH"];

  // 預設只顯示 Same Point
  const DEFAULT_GROUP_FILTER = ["MATCH"];

  const SIZE_COLORS = {
    S: "#7FDBFF",
    M: "#FF851B",
    L: "#2ECC40",
    O: "#FF4136",
  };

  const GROUP_LABELS = {
    BPI: "BPI",
    API: "API",
    MATCH: "Same Point",
  };

  const GROUP_SHAPES = {
    BPI: "circle",
    API: "triangle",
    MATCH: "star",
  };

  const mapState = {
    respByMode: {
      BPI: null,
      API: null,
      MATCH: null,
    },

    loadingMode: new Set(),

    sizeFilter: new Set(SIZE_KEYS),
    groupFilter: new Set(DEFAULT_GROUP_FILTER),

    points: [],
    hitCache: [],
    isBound: false,

    imageModal: null,
    zoomOverlay: null,
  };

  function $(id) {
    return document.getElementById(id);
  }

  function cleanStr(v) {
    if (v == null) return "";

    const s = String(v).trim();
    if (!s) return "";

    if (["nan", "none", "null", "nat", "<na>", "undefined"].includes(s.toLowerCase())) {
      return "";
    }

    return s;
  }

  function escapeHtml(v) {
    return cleanStr(v)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function num(v) {
    const n = Number(v);
    return Number.isFinite(n) ? n : 0;
  }

  function normalizeSize(v) {
    const s = cleanStr(v).toUpperCase();

    if (["S", "SMALL"].includes(s)) return "S";
    if (["M", "MID", "MIDDLE"].includes(s)) return "M";
    if (["L", "LARGE"].includes(s)) return "L";
    if (["O", "OVER"].includes(s)) return "O";

    return "";
  }

  function isValidSize(v) {
    return SIZE_KEYS.includes(normalizeSize(v));
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

    return p.endsWith("/") || p.endsWith("\\") ? p + n : p + "/" + n;
  }

  function makeImageItem(url, meta) {
    const u = cleanStr(url);
    if (!u) return null;

    return {
      url: u,
      side: cleanStr(meta?.side),
      defect_size: cleanStr(meta?.defect_size),
      adc_def_code: cleanStr(meta?.adc_def_code),
      retype_code: cleanStr(meta?.retype_code),
      chip_id: cleanStr(meta?.chip_id),
    };
  }

  function normalizeImageItem(item) {
    if (!item) return null;

    if (typeof item === "string") {
      const url = cleanStr(item);
      return url ? { url } : null;
    }

    if (typeof item === "object") {
      const url = cleanStr(item.url || item.src || item.href);
      if (!url) return null;

      return {
        url,
        side: cleanStr(item.side),
        defect_size: cleanStr(item.defect_size),
        adc_def_code: cleanStr(item.adc_def_code),
        retype_code: cleanStr(item.retype_code),
        chip_id: cleanStr(item.chip_id),
      };
    }

    return null;
  }

  function readOffset() {
    return Number($("bpi-same-point-offset")?.value || state.offset || 20) || 20;
  }

  function getAxisFromConfig() {
    const cfg =
      state.config?.defect_map?.map_axis ||
      state.config?.defectMap?.map_axis ||
      state.payload?.ParamDict?.Config?.defect_map?.map_axis ||
      null;

    if (!cfg || typeof cfg !== "object") return AXIS;

    return {
      minX: Number.isFinite(Number(cfg.minX)) ? Number(cfg.minX) : AXIS.minX,
      maxX: Number.isFinite(Number(cfg.maxX)) ? Number(cfg.maxX) : AXIS.maxX,
      minY: Number.isFinite(Number(cfg.minY)) ? Number(cfg.minY) : AXIS.minY,
      maxY: Number.isFinite(Number(cfg.maxY)) ? Number(cfg.maxY) : AXIS.maxY,
    };
  }

  function formatAxisMm(v) {
    const mm = Number(v) / 1000;
    if (!Number.isFinite(mm)) return "";

    if (Math.abs(mm - Math.round(mm)) < 1e-6) {
      return String(Math.round(mm));
    }

    return mm.toFixed(1);
  }

  // =============================================================================
  // Layout
  // =============================================================================
  function ensureLayout() {
    const wrap = $("bpi-same-point-map-wrap");
    const vp = wrap?.querySelector(".map-viewport, .bpi-same-point-map-viewport");
    const canvas = $(CANVAS_ID);

    if (!vp || !canvas) return null;

    Object.assign(wrap.style, {
      position: "relative",
      overflow: "visible",
    });

    Object.assign(vp.style, {
      position: "relative",
      display: "flex",
      flexDirection: "row",
      gap: "10px",
      alignItems: "stretch",
      overflow: "visible",
      width: "100%",
      minHeight: "360px",
    });

    Object.assign(canvas.style, {
      flex: "4 1 0",
      width: "auto",
      minWidth: "0",
      height: "100%",
      minHeight: "360px",
      background: "#0f1115",
      border: "1px solid rgba(255,255,255,0.08)",
      borderRadius: "6px",
      cursor: "default",
      position: "relative",
      zIndex: "1",
      pointerEvents: "auto",
      boxSizing: "border-box",
    });

    let legend = $(LEGEND_ID);
    if (!legend) {
      legend = document.createElement("div");
      legend.id = LEGEND_ID;
      vp.appendChild(legend);
    } else if (legend.parentElement !== vp) {
      vp.appendChild(legend);
    }

    Object.assign(legend.style, {
      flex: "1 1 0",
      width: "auto",
      maxWidth: "260px",
      minWidth: "170px",
      height: "auto",
      minHeight: "360px",
      display: "flex",
      flexDirection: "column",
      gap: "8px",
      background: "#0f1115",
      border: "1px solid rgba(255,255,255,0.08)",
      borderRadius: "6px",
      padding: "8px",
      overflowY: "auto",
      overflowX: "hidden",
      position: "relative",
      zIndex: "20",
      pointerEvents: "auto",
      color: "#fff",
      boxSizing: "border-box",
    });

    let tips = $(TIPS_ID);
    if (!tips) {
      tips = document.createElement("div");
      tips.id = TIPS_ID;
      document.body.appendChild(tips);
    }

    Object.assign(tips.style, {
      position: "fixed",
      zIndex: 9999,
      pointerEvents: "none",
      background: "rgba(0,0,0,0.88)",
      border: "1px solid rgba(255,255,255,0.15)",
      borderRadius: "6px",
      padding: "6px 8px",
      font: "12px/1.35 -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif",
      color: "#fff",
      boxShadow: "0 6px 18px rgba(0,0,0,0.35)",
      maxWidth: "420px",
      display: "none",
    });

    return { wrap, vp, canvas, legend, tips };
  }

  // =============================================================================
  // Legend
  // =============================================================================
  function shapeIcon(group, color) {
    const cvs = document.createElement("canvas");
    cvs.width = 14;
    cvs.height = 14;
    cvs.style.width = "14px";
    cvs.style.height = "14px";
    cvs.style.flex = "0 0 14px";

    const ctx = cvs.getContext("2d");
    if (!ctx) return cvs;

    drawSymbol(ctx, 7, 7, 4.8, GROUP_SHAPES[group], color || "#fff", {
      stroke: "rgba(0,0,0,.55)",
    });

    return cvs;
  }

  function makeSmallButton(text) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-xs btn-secondary";
    btn.textContent = text;

    Object.assign(btn.style, {
      cursor: "pointer",
      pointerEvents: "auto",
      fontSize: "11px",
      lineHeight: "1.2",
      padding: "2px 6px",
      borderRadius: "4px",
      border: "1px solid rgba(255,255,255,0.18)",
      background: "rgba(255,255,255,0.08)",
      color: "#fff",
      whiteSpace: "nowrap",
      userSelect: "none",
    });

    ["pointerdown", "mousedown", "click"].forEach(evt => {
      btn.addEventListener(evt, ev => {
        ev.stopPropagation();
      });
    });

    return btn;
  }

  function buildLegend() {
    ensureLayout();

    const legend = $(LEGEND_ID);
    if (!legend) return;

    Object.assign(legend.style, {
      pointerEvents: "auto",
      zIndex: "20",
      position: "relative",
    });

    legend.innerHTML = "";

    if (!legend.dataset.boundClickShield) {
      legend.dataset.boundClickShield = "1";

      // 不可用 capture:true，否則會在捕獲階段阻止 button / checkbox 自己的 click
      ["pointerdown", "mousedown"].forEach(evt => {
        legend.addEventListener(evt, ev => {
          ev.stopPropagation();
        });
      });
    }
    // ============================================================
    // 1) Defect Size filter
    // ============================================================
    const sizeBox = document.createElement("div");
    Object.assign(sizeBox.style, {
      borderBottom: "1px dashed rgba(255,255,255,0.14)",
      paddingBottom: "8px",
    });

    const sHeader = document.createElement("div");
    Object.assign(sHeader.style, {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      marginBottom: "6px",
      gap: "6px",
    });

    const sTitle = document.createElement("div");
    sTitle.textContent = "Defect Size";
    Object.assign(sTitle.style, {
      fontWeight: "700",
      fontSize: "12px",
      lineHeight: "1.2",
    });

    const sBtn = makeSmallButton(mapState.sizeFilter.size === SIZE_KEYS.length ? "清空" : "全選");

    sBtn.onclick = ev => {
      ev.preventDefault();
      ev.stopPropagation();

      const allSelected = mapState.sizeFilter.size === SIZE_KEYS.length;

      mapState.sizeFilter = allSelected
        ? new Set()
        : new Set(SIZE_KEYS);

      buildLegend();
      redraw();
    };

    sHeader.append(sTitle, sBtn);
    sizeBox.appendChild(sHeader);

    const sWrap = document.createElement("div");
    Object.assign(sWrap.style, {
      display: "grid",
      gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
      gap: "6px",
      overflow: "visible",
    });

    SIZE_KEYS.forEach(k => {
      const item = document.createElement("div");

      Object.assign(item.style, {
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "flex-start",
        gap: "5px",
        padding: "3px 5px",
        border: "1px solid rgba(255,255,255,0.15)",
        borderRadius: "4px",
        cursor: "pointer",
        userSelect: "none",
        background: mapState.sizeFilter.has(k) ? "rgba(255,255,255,0.09)" : "transparent",
        pointerEvents: "auto",
        minWidth: "0",
      });

      const sw = document.createElement("span");
      Object.assign(sw.style, {
        display: "inline-block",
        width: "11px",
        height: "11px",
        borderRadius: "3px",
        background: SIZE_COLORS[k] || "#999",
        flex: "0 0 11px",
      });

      const label = document.createElement("span");
      label.textContent = k;
      Object.assign(label.style, {
        fontSize: "11px",
        whiteSpace: "nowrap",
        lineHeight: "1.2",
      });

      item.append(sw, label);

      item.addEventListener("click", ev => {
        ev.preventDefault();
        ev.stopPropagation();

        if (mapState.sizeFilter.has(k)) mapState.sizeFilter.delete(k);
        else mapState.sizeFilter.add(k);

        buildLegend();
        redraw();
      });

      sWrap.appendChild(item);
    });

    sizeBox.appendChild(sWrap);
    legend.appendChild(sizeBox);

    // ============================================================
    // 2) Defect Group filter
    // ============================================================
    const groupBox = document.createElement("div");
    Object.assign(groupBox.style, {
      borderBottom: "1px dashed rgba(255,255,255,0.14)",
      paddingBottom: "8px",
    });

    const gHeader = document.createElement("div");
    Object.assign(gHeader.style, {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      marginBottom: "6px",
      gap: "6px",
    });

    const gTitle = document.createElement("div");
    gTitle.textContent = "Defect Group";
    Object.assign(gTitle.style, {
      fontWeight: "700",
      fontSize: "12px",
      lineHeight: "1.2",
    });

    const gBtn = makeSmallButton(mapState.groupFilter.size === GROUP_KEYS.length ? "清空" : "全選");

    gBtn.onclick = ev => {
      ev.preventDefault();
      ev.stopPropagation();

      const allSelected = mapState.groupFilter.size === GROUP_KEYS.length;

      mapState.groupFilter = allSelected
        ? new Set()
        : new Set(GROUP_KEYS);

      buildLegend();
      redraw();
    };

    gHeader.append(gTitle, gBtn);
    groupBox.appendChild(gHeader);

    const gList = document.createElement("div");
    Object.assign(gList.style, {
      display: "flex",
      flexDirection: "column",
      gap: "5px",
    });

    [
      ["BPI", "#5B5B5B"],
      ["API", "#5B5B5B"],
      ["MATCH", "#5B5B5B"],
    ].forEach(([group, color]) => {
      const row = document.createElement("label");

      Object.assign(row.style, {
        display: "flex",
        alignItems: "center",
        gap: "5px",
        cursor: "pointer",
        padding: "3px 5px",
        borderRadius: "4px",
        border: "1px solid rgba(255,255,255,0.08)",
        background: mapState.groupFilter.has(group) ? "rgba(255,255,255,0.05)" : "transparent",
        pointerEvents: "auto",
        userSelect: "none",
        minHeight: "22px",
      });

      row.addEventListener("click", ev => {
        ev.stopPropagation();
      });

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = mapState.groupFilter.has(group);

      Object.assign(cb.style, {
        cursor: "pointer",
        pointerEvents: "auto",
        flex: "0 0 auto",
        width: "12px",
        height: "12px",
        margin: "0",
      });

      cb.addEventListener("click", ev => {
        ev.stopPropagation();
      });

      cb.addEventListener("change", ev => {
        ev.stopPropagation();

        if (cb.checked) mapState.groupFilter.add(group);
        else mapState.groupFilter.delete(group);

        buildLegend();
        redraw();
      });

      const icon = shapeIcon(group, color);

      const label = document.createElement("span");
      label.textContent = GROUP_LABELS[group] || group;

      Object.assign(label.style, {
        fontSize: "11px",
        whiteSpace: "nowrap",
        lineHeight: "1.2",
      });

      row.append(cb, icon, label);
      gList.appendChild(row);
    });

    groupBox.appendChild(gList);
    legend.appendChild(groupBox);

    // ============================================================
    // 3) Selected info
    // ============================================================
    const infoBox = document.createElement("div");
    const row = state.selectedRow || {};

    const title = document.createElement("div");
    title.textContent = "Selected";
    Object.assign(title.style, {
      fontWeight: "700",
      fontSize: "12px",
      marginBottom: "5px",
    });

    infoBox.appendChild(title);

    const info = document.createElement("div");
    Object.assign(info.style, {
      fontSize: "11px",
      lineHeight: "1.45",
      opacity: ".9",
      wordBreak: "break-word",
    });

    if (state.selectedRow) {
      info.innerHTML = [
        `glass: ${escapeHtml(row.glass_id)}`,
        `model: ${escapeHtml(row.model)}`,
        `side: ${escapeHtml(row.glass_side)}`,
        `offset: ${escapeHtml(row.offset_um || readOffset())}um`,
      ].join("<br>");
    } else {
      info.textContent = "尚未選取 chart/table row";
    }

    infoBox.appendChild(info);
    legend.appendChild(infoBox);
  }

  // =============================================================================
  // API load all groups
  // =============================================================================
  async function fetchMode(mode) {
    const row = state.selectedRow;

    if (!row || !API?.defectMap) return null;

    const offset = readOffset();

    const payload = {
      mode,
      row,
      offset_um: offset,
      size_filter: Array.from(mapState.sizeFilter || []),
    };

    console.log("[BPI_SAME_POINT] defect_map payload =", JSON.parse(JSON.stringify(payload)));

    const resp = await API.defectMap(payload);

    console.log("[BPI_SAME_POINT] defect_map response =", mode, resp);

    return resp || {};
  }

  async function ensureRespForMode(mode) {
    if (mapState.respByMode[mode]) return mapState.respByMode[mode];
    if (mapState.loadingMode.has(mode)) return null;

    mapState.loadingMode.add(mode);

    try {
      const resp = await fetchMode(mode);
      mapState.respByMode[mode] = resp;
      return resp;
    } catch (err) {
      console.error(`[BPI_SAME_POINT] defect_map ${mode} failed:`, err);
      mapState.respByMode[mode] = null;
      return null;
    } finally {
      mapState.loadingMode.delete(mode);
    }
  }

  async function loadAllModes() {
    if (!state.selectedRow || !API?.defectMap) {
      DefectMap.clear();
      return;
    }

    mapState.respByMode = {
      BPI: null,
      API: null,
      MATCH: null,
    };

    mapState.loadingMode = new Set();

    await Promise.all([
      ensureRespForMode("BPI"),
      ensureRespForMode("API"),
      ensureRespForMode("MATCH"),
    ]);

    rebuildPoints();
    buildLegend();
    redraw();
  }

  // =============================================================================
  // Normalize render points
  // =============================================================================
  function makePointBase(group, x, y, size, raw, images, extra) {
    const sz = normalizeSize(size);

    if (!SIZE_KEYS.includes(sz)) return null;

    const imgItems = Array.isArray(images)
      ? images.map(normalizeImageItem).filter(Boolean)
      : [];

    return {
      group,
      shape: GROUP_SHAPES[group],
      x: num(x),
      y: num(y),
      size: sz,
      color: SIZE_COLORS[sz],
      radius: sz === "S" ? 4 : sz === "M" ? 6 : sz === "L" ? 8 : 10,
      raw: raw || {},
      images: imgItems,
      meta: extra || {},
    };
  }

  function normalizeBpiApiPoints(group, resp) {
    const rows = Array.isArray(resp?.DefectRows) ? resp.DefectRows : [];

    return rows
      .map(r => {
        const size = normalizeSize(r.defect_size);
        if (!isValidSize(size)) return null;

        const img = buildImageUrl(r.pic_path, r.pic_name);

        return makePointBase(
          group,
          r.x,
          r.y,
          size,
          r,
          [
            makeImageItem(img, {
              side: group,
              defect_size: r.defect_size,
              adc_def_code: r.adc_def_code,
              retype_code: r.retype_code,
              chip_id: r.chip_id,
            }),
          ],
          {
            group,
            glass: state.selectedRow?.glass_id || "",
            chip_id: r.chip_id,
            x: r.x,
            y: r.y,
            defect_size: r.defect_size,
            adc_def_code: r.adc_def_code,
            retype_code: r.retype_code,
            source_table: r.source_table,
          }
        );
      })
      .filter(Boolean);
  }

  function normalizeMatchPoints(resp) {
    const rows = Array.isArray(resp?.MatchRows) ? resp.MatchRows : [];

    return rows
      .map(r => {
        const bpiSize = normalizeSize(r.bpi_defect_size);
        const apiSize = normalizeSize(r.api_defect_size);
        const size = bpiSize || apiSize;

        if (!isValidSize(size)) return null;

        const bpiImg = buildImageUrl(r.bpi_pic_path, r.bpi_pic_name);
        const apiImg = buildImageUrl(r.api_pic_path, r.api_pic_name);

        return makePointBase(
          "MATCH",
          r.bpi_x,
          r.bpi_y,
          size,
          r,
          [
            makeImageItem(bpiImg, {
              side: "BPI",
              defect_size: r.bpi_defect_size,
              adc_def_code: r.bpi_adc_def_code,
              retype_code: r.bpi_retype_code,
              chip_id: r.bpi_chip_id,
            }),
            makeImageItem(apiImg, {
              side: "API",
              defect_size: r.api_defect_size,
              adc_def_code: r.api_adc_def_code,
              retype_code: r.api_retype_code,
              chip_id: r.api_chip_id,
            }),
          ].filter(Boolean),
          {
            group: "MATCH",
            glass: r.glass_id || state.selectedRow?.glass_id || "",
            chip_id: `${cleanStr(r.bpi_chip_id)} / ${cleanStr(r.api_chip_id)}`,
            x: r.bpi_x,
            y: r.bpi_y,
            defect_size: `${cleanStr(r.bpi_defect_size)} / ${cleanStr(r.api_defect_size)}`,
            adc_def_code: `${cleanStr(r.bpi_adc_def_code)} / ${cleanStr(r.api_adc_def_code)}`,
            retype_code: `${cleanStr(r.bpi_retype_code)} / ${cleanStr(r.api_retype_code)}`,
            distance: r.distance,
            dx: r.dx,
            dy: r.dy,
            bpi_x: r.bpi_x,
            bpi_y: r.bpi_y,
            api_x: r.api_x,
            api_y: r.api_y,
            match_rank: r.match_rank,
          }
        );
      })
      .filter(Boolean);
  }

  function rebuildPoints() {
    const out = [];

    out.push(...normalizeBpiApiPoints("BPI", mapState.respByMode.BPI));
    out.push(...normalizeBpiApiPoints("API", mapState.respByMode.API));
    out.push(...normalizeMatchPoints(mapState.respByMode.MATCH));

    mapState.points = out;
  }

  function getVisiblePoints() {
    return (mapState.points || []).filter(p => {
      if (!p) return false;
      if (!GROUP_KEYS.includes(p.group)) return false;
      if (!mapState.groupFilter.has(p.group)) return false;
      if (!p.size || !mapState.sizeFilter.has(p.size)) return false;

      const axis = getAxisFromConfig();
      if (p.x < axis.minX || p.x > axis.maxX) return false;
      if (p.y < axis.minY || p.y > axis.maxY) return false;

      return true;
    });
  }

  // =============================================================================
  // Canvas draw
  // =============================================================================
  function niceStep(range) {
    if (!isFinite(range) || range <= 0) return 1;

    const exp = Math.floor(Math.log10(range));
    const frac = range / Math.pow(10, exp);
    const niceFrac = frac < 1.5 ? 1 : frac < 3 ? 2 : frac < 7 ? 5 : 10;

    return niceFrac * Math.pow(10, exp);
  }

  function setupCanvas() {
    const env = ensureLayout();
    if (!env) return null;

    const { canvas } = env;
    const parent = canvas.parentElement;

    const cssW = Math.max(10, canvas.clientWidth || parent?.clientWidth || 640);
    const cssH = Math.max(10, canvas.clientHeight || parent?.clientHeight || 360);
    const dpr = window.devicePixelRatio || 1;

    canvas.width = Math.floor(cssW * dpr);
    canvas.height = Math.floor(cssH * dpr);

    const ctx = canvas.getContext("2d");
    if (!ctx) return null;

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);

    return { canvas, ctx, w: cssW, h: cssH };
  }

  function drawAxes(ctx, w, h) {
    const axis = getAxisFromConfig();

    const padL = 46;
    const padR = 12;
    const padT = 14;
    const padB = 38;

    const plotW = Math.max(10, w - padL - padR);
    const plotH = Math.max(10, h - padT - padB);

    const x0 = axis.minX;
    const x1 = axis.maxX;
    const y0 = axis.minY;
    const y1 = axis.maxY;

    const xScale = plotW / ((x1 - x0) || 1);
    const yScale = plotH / ((y1 - y0) || 1);

    ctx.fillStyle = "#0f1115";
    ctx.fillRect(0, 0, w, h);

    ctx.strokeStyle = "rgba(255,255,255,0.5)";
    ctx.lineWidth = 1;

    ctx.beginPath();
    ctx.moveTo(padL, padT + plotH);
    ctx.lineTo(padL + plotW, padT + plotH);
    ctx.moveTo(padL, padT);
    ctx.lineTo(padL, padT + plotH);
    ctx.stroke();

    ctx.fillStyle = "rgba(255,255,255,0.82)";
    ctx.font = "10px sans-serif";
    ctx.textAlign = "center";

    const xStep = niceStep((x1 - x0) / 10);

    for (let xv = x0; xv <= x1 + 1e-9; xv += xStep) {
      const x = padL + (xv - x0) * xScale;

      ctx.strokeStyle = "rgba(255,255,255,0.18)";
      ctx.beginPath();
      ctx.moveTo(x, padT + plotH);
      ctx.lineTo(x, padT + plotH + 4);
      ctx.stroke();

      ctx.fillStyle = "rgba(255,255,255,0.82)";
      ctx.fillText(formatAxisMm(xv), x, padT + plotH + 16);

      ctx.strokeStyle = "rgba(255,255,255,0.055)";
      ctx.beginPath();
      ctx.moveTo(x, padT);
      ctx.lineTo(x, padT + plotH);
      ctx.stroke();
    }

    ctx.textAlign = "right";

    const yStep = niceStep((y1 - y0) / 6);

    for (let yv = y0; yv <= y1 + 1e-9; yv += yStep) {
      const y = padT + (yv - y0) * yScale;

      ctx.strokeStyle = "rgba(255,255,255,0.18)";
      ctx.beginPath();
      ctx.moveTo(padL - 4, y);
      ctx.lineTo(padL, y);
      ctx.stroke();

      ctx.fillStyle = "rgba(255,255,255,0.82)";
      ctx.fillText(formatAxisMm(yv), padL - 6, y + 4);

      ctx.strokeStyle = "rgba(255,255,255,0.055)";
      ctx.beginPath();
      ctx.moveTo(padL, y);
      ctx.lineTo(padL + plotW, y);
      ctx.stroke();
    }

    ctx.save();
    ctx.fillStyle = "rgba(255,255,255,0.62)";
    ctx.font = "10px sans-serif";
    ctx.textAlign = "right";
    ctx.fillText("X/Y: mm", padL + plotW, padT + plotH + 31);
    ctx.restore();

    function toScreen(x, y) {
      return {
        sx: padL + (num(x) - x0) * xScale,
        sy: padT + (num(y) - y0) * yScale,
      };
    }

    return {
      axis,
      padL,
      padT,
      plotW,
      plotH,
      toScreen,
    };
  }

  function drawSymbol(ctx, x, y, r, shape, color, opts) {
    ctx.save();

    ctx.fillStyle = color || "#fff";
    ctx.strokeStyle = opts?.stroke || "rgba(0,0,0,.55)";
    ctx.lineWidth = opts?.lineWidth || 1;
    ctx.globalAlpha = opts?.alpha ?? 0.92;

    if (shape === "triangle") {
      ctx.beginPath();
      ctx.moveTo(x, y - r);
      ctx.lineTo(x - r * 0.95, y + r * 0.82);
      ctx.lineTo(x + r * 0.95, y + r * 0.82);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    } else if (shape === "star") {
      drawStarPath(ctx, x, y, r, r * 0.45, 5);
      ctx.fill();
      ctx.stroke();
    } else {
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    }

    ctx.restore();
  }

  function drawStarPath(ctx, cx, cy, outerR, innerR, points) {
    let rot = -Math.PI / 2;
    const step = Math.PI / points;

    ctx.beginPath();

    for (let i = 0; i < points * 2; i++) {
      const r = i % 2 === 0 ? outerR : innerR;
      const x = cx + Math.cos(rot) * r;
      const y = cy + Math.sin(rot) * r;

      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);

      rot += step;
    }

    ctx.closePath();
  }

  function redraw() {
    const env = setupCanvas();
    if (!env) return;

    const { ctx, w, h } = env;
    const coord = drawAxes(ctx, w, h);

    mapState.hitCache = [];

    const pts = getVisiblePoints();

    if (!pts.length) {
      drawEmptyText(ctx, w, h);
      return;
    }

    pts.forEach(p => {
      const { sx, sy } = coord.toScreen(p.x, p.y);
      const r = p.group === "MATCH" ? Math.max(8, p.radius + 2) : p.radius;

      drawSymbol(ctx, sx, sy, r, p.shape, p.color);

      mapState.hitCache.push({
        sx,
        sy,
        r: r + 5,
        point: p,
      });
    });
  }

  function drawEmptyText(ctx, w, h) {
    ctx.fillStyle = "rgba(255,255,255,.65)";
    ctx.font = "13px sans-serif";
    ctx.textAlign = "center";

    if (!state.selectedRow) {
      ctx.fillText("請先點選 chart bar 載入 defect map", w / 2, h / 2);
    } else {
      ctx.fillText("無可顯示 defect 點", w / 2, h / 2);
    }
  }

  // =============================================================================
  // Tooltip / hit
  // =============================================================================
  function findHit(ev) {
    const canvas = $(CANVAS_ID);
    if (!canvas || !mapState.hitCache.length) return null;

    const rect = canvas.getBoundingClientRect();
    const x = ev.clientX - rect.left;
    const y = ev.clientY - rect.top;

    let best = null;
    let bestD2 = Infinity;

    for (const h of mapState.hitCache) {
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
    const meta = p.meta || {};

    const kv = {
      group: GROUP_LABELS[p.group] || p.group,
      glass: meta.glass || state.selectedRow?.glass_id || "",
      chip_id: meta.chip_id || "",
      x: meta.x ?? p.x ?? "",
      y: meta.y ?? p.y ?? "",
      defect_size: meta.defect_size || p.size || "",
      adc_def_code: meta.adc_def_code || "",
      retype_code: meta.retype_code || "",
      distance: meta.distance || "",
    };

    const rows = DEFECT_INFO_KEYS.map(k => {
      const v = kv[k] ?? "";
      return `
        <tr>
          <td style="opacity:.65;padding-right:8px;white-space:nowrap;">${escapeHtml(k)}</td>
          <td style="white-space:nowrap;">${escapeHtml(v)}</td>
        </tr>
      `;
    }).join("");

    const extra =
      p.group === "MATCH"
        ? `
          <tr><td style="opacity:.65;padding-right:8px;">bpi_xy</td><td>${escapeHtml(meta.bpi_x)}, ${escapeHtml(meta.bpi_y)}</td></tr>
          <tr><td style="opacity:.65;padding-right:8px;">api_xy</td><td>${escapeHtml(meta.api_x)}, ${escapeHtml(meta.api_y)}</td></tr>
          <tr><td style="opacity:.65;padding-right:8px;">dx/dy</td><td>${escapeHtml(meta.dx)}, ${escapeHtml(meta.dy)}</td></tr>
          <tr><td style="opacity:.65;padding-right:8px;">rank</td><td>${escapeHtml(meta.match_rank)}</td></tr>
        `
        : "";

    return `<table style="border-collapse:collapse;">${rows}${extra}</table>`;
  }

  function showTooltip(ev, html) {
    const tips = $(TIPS_ID);
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
    const tips = $(TIPS_ID);
    if (!tips) return;

    tips.style.display = "none";
  }

  // =============================================================================
  // Image modal
  // =============================================================================
  function openImageModal(point) {
    const imgs = Array.isArray(point?.images)
      ? point.images.map(normalizeImageItem).filter(Boolean)
      : [];

    if (!imgs.length) return;

    closeImageModal();

    const overlay = document.createElement("div");
    overlay.className = "bpi-same-point-image-modal-backdrop";

    Object.assign(overlay.style, {
      position: "fixed",
      inset: "0",
      zIndex: "10000",
      background: "rgba(0,0,0,.52)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: "24px",
    });

    const panel = document.createElement("div");
    panel.className = "bpi-same-point-image-modal-panel";

    Object.assign(panel.style, {
      maxWidth: "86vw",
      maxHeight: "82vh",
      minWidth: "420px",
      background: "#111827",
      color: "#fff",
      border: "1px solid rgba(255,255,255,.16)",
      borderRadius: "10px",
      boxShadow: "0 16px 40px rgba(0,0,0,.55)",
      padding: "14px",
      display: "flex",
      flexDirection: "column",
      gap: "10px",
      overflow: "hidden",
    });

    const head = document.createElement("div");
    Object.assign(head.style, {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      gap: "12px",
    });

    const title = document.createElement("div");
    title.style.fontWeight = "700";
    title.textContent = `${GROUP_LABELS[point.group] || point.group} image - ${cleanStr(state.selectedRow?.glass_id)}`;

    const closeBtn = makeSmallButton("關閉");
    closeBtn.onclick = ev => {
      ev.preventDefault();
      ev.stopPropagation();
      closeImageModal();
    };

    head.append(title, closeBtn);

    const body = document.createElement("div");
    Object.assign(body.style, {
      display: "grid",
      gridTemplateColumns: imgs.length === 1 ? "1fr" : "repeat(auto-fit, minmax(260px, 1fr))",
      gap: "10px",
      overflow: "auto",
      paddingRight: "2px",
    });

    imgs.forEach((imgInfo, idx) => {
      const url = imgInfo.url;

      const card = document.createElement("div");
      Object.assign(card.style, {
        border: "1px solid rgba(255,255,255,.12)",
        borderRadius: "8px",
        padding: "8px",
        background: "rgba(255,255,255,.04)",
        display: "flex",
        flexDirection: "column",
        gap: "6px",
      });

      const label = document.createElement("div");
      Object.assign(label.style, {
        fontSize: "12px",
        lineHeight: "1.45",
        opacity: ".9",
        display: "flex",
        flexDirection: "column",
        gap: "2px",
      });

      const side = cleanStr(imgInfo.side) || (imgs.length === 1 ? "image" : `image ${idx + 1}`);
      const size = cleanStr(imgInfo.defect_size);
      const code = cleanStr(imgInfo.adc_def_code);
      const retype = cleanStr(imgInfo.retype_code);

      label.innerHTML = `
        <div style="font-weight:700;color:#fff;">${escapeHtml(side)}</div>
        <div style="opacity:.78;">
          Size: ${escapeHtml(size || "-")}
          &nbsp;|&nbsp;
          Code: ${escapeHtml(code || "-")}
        </div>
        ${
          retype
            ? `<div style="opacity:.65;">Retype: ${escapeHtml(retype)}</div>`
            : ""
        }
      `;

      const img = document.createElement("img");
      img.src = url;
      img.alt = `defect image ${idx + 1}`;

      Object.assign(img.style, {
        maxWidth: "100%",
        maxHeight: "56vh",
        objectFit: "contain",
        borderRadius: "6px",
        cursor: "zoom-in",
        background: "#000",
      });

      img.addEventListener("click", ev => {
        ev.stopPropagation();
        openZoomImage(url);
      });

      card.append(label, img);
      body.appendChild(card);
    });

    panel.append(head, body);
    overlay.appendChild(panel);
    document.body.appendChild(overlay);

    overlay.addEventListener("click", ev => {
      if (ev.target !== overlay) return;

      if (mapState.zoomOverlay) {
        closeZoomImage();
        return;
      }

      closeImageModal();
    });

    mapState.imageModal = overlay;
  }

  function closeImageModal() {
    closeZoomImage();

    if (mapState.imageModal?.parentNode) {
      mapState.imageModal.parentNode.removeChild(mapState.imageModal);
    }

    mapState.imageModal = null;
  }

  function openZoomImage(url) {
    closeZoomImage();

    const overlay = document.createElement("div");
    overlay.className = "bpi-same-point-image-zoom-backdrop";

    Object.assign(overlay.style, {
      position: "fixed",
      inset: "0",
      zIndex: "10001",
      background: "rgba(0,0,0,.78)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: "20px",
      cursor: "zoom-out",
    });

    const img = document.createElement("img");
    img.src = url;

    Object.assign(img.style, {
      maxWidth: "96vw",
      maxHeight: "94vh",
      objectFit: "contain",
      borderRadius: "8px",
      boxShadow: "0 20px 60px rgba(0,0,0,.7)",
      background: "#000",
    });

    img.addEventListener("click", ev => {
      ev.stopPropagation();
    });

    overlay.appendChild(img);
    document.body.appendChild(overlay);

    overlay.addEventListener("click", () => {
      closeZoomImage();
    });

    mapState.zoomOverlay = overlay;
  }

  function closeZoomImage() {
    if (mapState.zoomOverlay?.parentNode) {
      mapState.zoomOverlay.parentNode.removeChild(mapState.zoomOverlay);
    }

    mapState.zoomOverlay = null;
  }

  // =============================================================================
  // Canvas events
  // =============================================================================
  function bindCanvasEvents() {
    if (mapState.isBound) return;

    const canvas = $(CANVAS_ID);
    if (!canvas) return;

    mapState.isBound = true;

    canvas.addEventListener("mousemove", ev => {
      const hit = findHit(ev);

      if (hit?.point) {
        canvas.style.cursor = hit.point.images?.length ? "pointer" : "default";
        showTooltip(ev, tooltipHtmlFromPoint(hit.point));
      } else {
        canvas.style.cursor = "default";
        hideTooltip();
      }
    });

    canvas.addEventListener("mouseleave", hideTooltip);

    canvas.addEventListener("click", ev => {
      const hit = findHit(ev);

      if (hit?.point) {
        openImageModal(hit.point);
      }
    });
  }

  // =============================================================================
  // Public API
  // =============================================================================
  DefectMap.clear = function () {
    mapState.respByMode = {
      BPI: null,
      API: null,
      MATCH: null,
    };

    mapState.points = [];
    mapState.hitCache = [];
    mapState.sizeFilter = new Set(SIZE_KEYS);
    mapState.groupFilter = new Set(DEFAULT_GROUP_FILTER);

    closeImageModal();
    hideTooltip();

    buildLegend();
    redraw();
  };

  DefectMap.load = async function () {
    await loadAllModes();
  };

  DefectMap.render = function () {
    rebuildPoints();
    buildLegend();
    redraw();
  };

  DefectMap.redraw = function () {
    redraw();
  };

  function init() {
    ensureLayout();
    buildLegend();
    redraw();

    setTimeout(() => {
      bindCanvasEvents();
    }, 0);
  }

  window.addEventListener("resize", () => {
    hideTooltip();
    redraw();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();