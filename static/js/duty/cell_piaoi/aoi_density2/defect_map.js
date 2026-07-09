// static/js/duty/cell_piaoi/aoi_density2/defect_map.js
// 單一 canvas 顯示所有 defect；以「尺寸 S/M/L/O」著色
// 右側圖例：尺寸多選 + Defect Code 下拉式 checkbox 多選 + Glass 下拉式 checkbox 多選
// 點擊點開影像；hover 顯示資訊

(function () {
  const MOD = (window.AOI_DENSITY = window.AOI_DENSITY || {});
  MOD.Map = MOD.Map || {};

  const CANVAS_ID = "aoi-density-mini-map";
  const LEGEND_ID = "aoi-density-map-legend";
  const TIPS_ID   = "aoi-density-map-tooltip";

  // 懸浮框欄位順序
  const DEFECT_INFO_KEYS = [
    "lotid",
    "recipe",
    "test_time",
    "x",
    "y",
    "defect_size",
    "adc_def_code",
    "chip",
    "common_cnt",
    "common_glass_cnt",
    "cluster_point_cnt",
    "cluster_glass_cnt",
    
  ];

  // 固定座標範圍（µm）
  const AXIS = {
    minX: 0,
    maxX: 1850000,
    minY: 0,
    maxY: 1500000
  };

  // 尺寸顏色
  const SIZE_COLORS = {
    S: "#7FDBFF",
    M: "#FF851B",
    L: "#2ECC40",
    O: "#FF4136"
  };

  // ===== 小工具 =====
  function safeStr(v) {
    return v == null ? "" : String(v);
  }

  function escHtml(v) {
    return safeStr(v)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function normalizeDefectCode(v) {
    const s = safeStr(v).trim();

    if (!s) return "others";

    const lower = s.toLowerCase();

    if (
      lower === "nan" ||
      lower === "none" ||
      lower === "null" ||
      lower === "undefined"
    ) {
      return "others";
    }

    return s;
  }

  function buildImageUrl(it) {
    const direct = safeStr(
      it?.image_url ||
      it?.img_url ||
      it?.url ||
      it?.img_file_url_path ||
      ""
    ).trim();

    if (direct) return direct;

    const picPath = safeStr(it?.pic_path || "").trim();
    const picName = safeStr(it?.pic_name || "").trim();

    if (!picPath) return picName;
    if (!picName) return picPath;

    // pic_path 已經是完整圖片 URL 且看起來包含副檔名，就不要再接 pic_name
    if (
      /^https?:\/\//i.test(picPath) &&
      /\.(jpg|jpeg|png|bmp|gif|webp)(\?|#|$)/i.test(picPath)
    ) {
      return picPath;
    }

    return picPath.replace(/[\\/]+$/, "") + "/" + picName.replace(/^[\\/]+/, "");
  }

  function normalizeBucket(size) {
    const raw = safeStr(size || "O").trim().toUpperCase();
    return ["S", "M", "L", "O"].includes(raw) ? raw : "O";
  }

  function uniqSorted(arr) {
    return Array.from(new Set(
      (arr || [])
        .map(x => safeStr(x).trim())
        .filter(Boolean)
        .map(normalizeDefectCode)
    )).sort((a, b) => String(a).localeCompare(String(b)));
  }

  // ===== 佈局 =====
  function ensureLayout() {
    const host = document.getElementById("aoi-density-map-wrap");
    const vp = host?.querySelector(".map-viewport");
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
      minWidth: "220px",
      display: "flex",
      flexDirection: "column",
      gap: "10px",
      background: "#0f1115",
      border: "1px solid rgba(255,255,255,0.08)",
      borderRadius: "6px",
      padding: "8px",
      overflowY: "auto",
      overflowX: "hidden",
      position: "relative"
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
      maxWidth: "360px",
      display: "none",
    });

    return { vp, cvs, legend, tips };
  }

  // ===== 刻度計算 =====
  function niceStep(range) {
    if (!isFinite(range) || range <= 0) return 1;

    const exp = Math.floor(Math.log10(range));
    const frac = range / Math.pow(10, exp);
    const niceFrac = frac < 1.5 ? 1 : frac < 3 ? 2 : frac < 7 ? 5 : 10;

    return niceFrac * Math.pow(10, exp);
  }

  // ===== 狀態 =====
  const state = {
    groups: [],

    sizeFilter: new Set(["S", "M", "L", "O"]),

    defectCodeList: [],
    triggerDefCode: "",
    defectCodeFilter: new Set(),
    defectCodeDropdownOpen: false,

    glassFilter: new Set(),
    glassDropdownOpen: false,

    hitCache: [],

    samePointRows: [],
    showSamePoint: true,
  };

  // ===== 後端 → 正規化 =====
  function normalizeResponse(resp) {
    const dict = resp?.DefectGroupDict;
    if (!dict || typeof dict !== "object") return [];

    const groups = [];

    // dict: { glass_id: { "0": {...}, "1": {...} } }
    Object.entries(dict).forEach(([glassId, defectObj]) => {
      const gid = safeStr(glassId).trim();

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
        if (!it) return;

        const bucket = normalizeBucket(it.defect_size);
        const img = buildImageUrl(it);

        const recipe = safeStr(
          it.recipe_id ||
          it.recipe ||
          it.RECIPE_ID ||
          ""
        );

        const adcCode = normalizeDefectCode(
          it.adc_def_code ||
          it.ai_code_1 ||
          it.defect_code ||
          it.DEFECT_CODE ||
          ""
        );

        const chip = safeStr(
          it.chip ||
          it.chip_id ||
          it.chip_name ||
          it.CHIP_ID ||
          ""
        );

        const testTime = safeStr(
          it.test_time ||
          it.scan_time ||
          it.TEST_TIME ||
          it.SCAN_TIME ||
          ""
        );

        g.points.push({
          x: Number(it.x ?? it.coord_x ?? it.pox_x ?? 0),
          y: Number(it.y ?? it.coord_y ?? it.pox_y ?? 0),

          bucket,
          rawSize: it.defect_size,
          img: img || "",

          defectCode: adcCode,
          chip,
          recipe_id: recipe,

          meta: {
            lotid: gid,
            recipe,
            test_time: testTime,
            x: it.x ?? it.coord_x ?? it.pox_x ?? "",
            y: it.y ?? it.coord_y ?? it.pox_y ?? "",
            defect_size: it.defect_size ?? "",
            adc_def_code: adcCode,
            chip,
            img: img || ""
          }
        });
      });

      groups.push(g);
    });

    return groups;
  }

  function collectDefectCodesFromGroups(groups) {
    const out = [];

    (groups || []).forEach(g => {
      (g.points || []).forEach(p => {
        out.push(
          p.defectCode ||
          p.meta?.adc_def_code ||
          "others"
        );
      });
    });

    return uniqSorted(out);
  }

  function isSamePointActive() {
    return window.AOI_DENSITY?.isSamePointTab?.(
      window.AOI_DENSITY?.state?.activeSubTab || window.density_sub_activeTabKey
    );
  }
  
  function safeJsonArray(v) {
    if (!v) return [];
    if (Array.isArray(v)) return v;
  
    if (typeof v === "string") {
      try {
        const obj = JSON.parse(v);
        return Array.isArray(obj) ? obj : [];
      } catch (_) {
        return [];
      }
    }
  
    return [];
  }
  
  function collectSamePointPoints(rows) {
    const out = [];
  
    (rows || []).forEach(r => {
      if (!r || Number(r.common_cnt || 0) <= 0) return;
  
      const details = safeJsonArray(r.common_points_details);
  
      details.forEach(cluster => {
        const points = Array.isArray(cluster.points) ? cluster.points : [];
  
        if (!points.length) return;
  
        points.forEach(p => {
          
          const x = Number(p.x ?? p.coord_x ?? p.pox_x ?? p.pox_x1);
          const y = Number(p.y ?? p.coord_y ?? p.pox_y ?? p.pox_y1);
  
          if (!Number.isFinite(x) || !Number.isFinite(y)) return;
  
          out.push({
            type: "same_point",
            x,
            y,
            gid: safeStr(p.glass || p.glass_id || ""),
            recipe_id: safeStr(r.recipe_id || ""),
            cluster,
            cluster_id: cluster.cluster_id,
            center_x: cluster.center_x,
            center_y: cluster.center_y,
            glass_cnt: cluster.glass_cnt,
            point_cnt: cluster.point_cnt,
            all_points: points,
            meta: {
              lotid: safeStr(p.glass || p.glass_id || ""),
              recipe: safeStr(r.recipe_id || ""),
              test_time: safeStr(p.test_time || ""),
              x,
              y,
              defect_size: safeStr(p.defect_size || ""),
              adc_def_code: safeStr(p.defect_code || p.adc_def_code || ""),
              chip: safeStr(p.chip_id || p.chip || ""),
              img: safeStr(p.img_url || p.image_url || ""),
              cluster_id: cluster.cluster_id,
              common_cnt: Number(r.common_cnt || 0),
              common_glass_cnt: Number(r.common_glass_cnt || 0),
              cluster_glass_cnt: Number(cluster.glass_cnt || 0),
              cluster_point_cnt: Number(cluster.point_cnt || 0)
            }
          });
        });
      });
    });
  
    return out;
  }
  
  function drawStar(ctx, x, y, outerR, innerR) {
    ctx.beginPath();
  
    for (let i = 0; i < 10; i++) {
      const angle = -Math.PI / 2 + i * Math.PI / 5;
      const r = i % 2 === 0 ? outerR : innerR;
      const px = x + Math.cos(angle) * r;
      const py = y + Math.sin(angle) * r;
  
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
  
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  }

  function showSamePointModal(hit) {
    const p = hit?.point;
    if (!p || p.type !== "same_point") return false;
  
    let modal = document.getElementById("aoi-density-same-point-modal");
  
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "aoi-density-same-point-modal";
      document.body.appendChild(modal);
    }
  
    function buildFullImageUrl(it) {
      const imgUrl = safeStr(it?.img_url || it?.image_url || "").trim();
      const picName = safeStr(it?.pic_name || it?.image_file_name || "").trim();
  
      if (!imgUrl) return picName;
      if (!picName) return imgUrl;
  
      if (/\.(jpg|jpeg|png|bmp|gif|webp)(\?|#|$)/i.test(imgUrl)) {
        return imgUrl;
      }
  
      return imgUrl.replace(/[\\/]+$/, "") + "/" + picName.replace(/^[\\/]+/, "");
    }
  
    const points = Array.isArray(p.all_points) ? p.all_points : [];
    const cluster = p.cluster || {};
  
    console.log("[same-point modal points]", points);
    console.log("[same-point modal image urls]", points.map(buildFullImageUrl));
  
    modal.innerHTML = "";
  
    const backdrop = document.createElement("div");
    backdrop.id = "aoi-density-same-point-backdrop";
    Object.assign(backdrop.style, {
      position: "fixed",
      inset: "0",
      zIndex: "10000",
      background: "rgba(0,0,0,0.72)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: "24px"
    });
  
    const panel = document.createElement("div");
    Object.assign(panel.style, {
      width: "min(980px, 92vw)",
      height: "720px",
      maxHeight: "86vh",
      display: "flex",
      flexDirection: "column",
      overflow: "hidden",
      background: "#111827",
      border: "1px solid rgba(255,255,255,0.18)",
      borderRadius: "12px",
      boxShadow: "0 20px 60px rgba(0,0,0,0.55)",
      color: "#fff"
    });
  
    const header = document.createElement("div");
    Object.assign(header.style, {
      position: "sticky",
      top: "0",
      zIndex: "1",
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      gap: "12px",
      padding: "14px 16px",
      background: "#111827",
      borderBottom: "1px solid rgba(255,255,255,0.12)"
    });
  
    const titleWrap = document.createElement("div");
  
    const title = document.createElement("div");
    title.textContent = "Same Point Cluster";
    Object.assign(title.style, {
      fontSize: "16px",
      fontWeight: "800",
      color: "#FFDC00"
    });
  
    const subTitle = document.createElement("div");
    subTitle.textContent =
      `cluster_id=${cluster.cluster_id || ""} ｜ recipe=${p.recipe_id || ""} ｜ ` +
      `glass_cnt=${cluster.glass_cnt || ""} ｜ point_cnt=${cluster.point_cnt || ""} ｜ ` +
      `center=(${cluster.center_x || ""}, ${cluster.center_y || ""})`;
    Object.assign(subTitle.style, {
      fontSize: "12px",
      color: "#aeb6c7",
      marginTop: "3px"
    });
  
    titleWrap.appendChild(title);
    titleWrap.appendChild(subTitle);
  
    const closeBtn = document.createElement("button");
    closeBtn.id = "aoi-density-same-point-close";
    closeBtn.textContent = "關閉";
    Object.assign(closeBtn.style, {
      border: "1px solid rgba(255,255,255,0.18)",
      background: "rgba(255,255,255,0.08)",
      color: "#fff",
      borderRadius: "6px",
      padding: "5px 10px",
      cursor: "pointer"
    });
  
    header.appendChild(titleWrap);
    header.appendChild(closeBtn);
  
    const body = document.createElement("div");
    Object.assign(body.style, {
      padding: "14px 16px",
      overflowY: "auto",
      overflowX: "hidden",
      flex: "1 1 auto",
      minHeight: "0"
    });
  
    if (!points.length) {
      const empty = document.createElement("div");
      empty.textContent = "沒有 common point detail";
      empty.style.color = "#aaa";
      body.appendChild(empty);
    }
    console.log(points);
    points.forEach((it, idx) => {
      console.log(it);
      const img = buildFullImageUrl(it);
      const glass = safeStr(it.glass || it.glass_id || "");
      const defectSize = safeStr(it.defect_size || "");
      const defectCode = safeStr(it.defect_code || it.adc_def_code || "");
      const chip = safeStr(it.chip_id || it.chip || "");
      const common_cnt = safeStr(it.common_cnt ||  "");
      const common_glass_cnt = safeStr(it.common_glass_cnt ||  "");
      const testTime = safeStr(it.test_time || "");
      const x = safeStr(it.x || "");
      const y = safeStr(it.y || "");
  
      const card = document.createElement("div");
      Object.assign(card.style, {
        display: "grid",
        gridTemplateColumns: "160px 1fr",
        gap: "10px",
        padding: "10px",
        border: "1px solid rgba(255,255,255,0.12)",
        borderRadius: "8px",
        background: "rgba(255,255,255,0.04)",
        marginBottom: "10px"
      });
  
      const imgBox = document.createElement("div");
  
      if (img) {
        const image = document.createElement("img");
        image.src = img;
        Object.assign(image.style, {
          width: "160px",
          height: "120px",
          objectFit: "contain",
          background: "#000",
          borderRadius: "6px",
          border: "1px solid rgba(255,255,255,0.12)"
        });
        imgBox.appendChild(image);
      } else {
        const noImg = document.createElement("div");
        noImg.textContent = "No Image";
        Object.assign(noImg.style, {
          width: "160px",
          height: "120px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#000",
          borderRadius: "6px",
          color: "#aaa"
        });
        imgBox.appendChild(noImg);
      }
  
      const info = document.createElement("div");
      Object.assign(info.style, {
        fontSize: "12px",
        lineHeight: "1.55",
        color: "#e8edf7"
      });
  
      const rows = [
        [`#${idx + 1}`, ""],
        ["Glass", glass],
        /*["common_cnt", common_cnt],
        ["common_glass_cnt", common_glass_cnt],*/
        ["Test Time", testTime],
        ["X/Y", `${x} / ${y}`],
        ["Defect Size", defectSize],
        ["Defect Code", defectCode],
        ["Chip", chip]
      ];
  
      rows.forEach(([k, v]) => {
        const row = document.createElement("div");
        if (v === "") {
          const b = document.createElement("b");
          b.textContent = k;
          row.appendChild(b);
        } else {
          const b = document.createElement("b");
          b.textContent = k;
          row.appendChild(b);
          row.appendChild(document.createTextNode(`: ${v}`));
        }
        info.appendChild(row);
      });
  
      if (img) {
        const linkWrap = document.createElement("div");
        linkWrap.style.marginTop = "6px";
  
        const a = document.createElement("a");
        a.href = img;
        a.target = "_blank";
        a.rel = "noopener";
        a.textContent = "開啟影像";
        a.style.color = "#7FDBFF";
  
        linkWrap.appendChild(a);
        info.appendChild(linkWrap);
      }
  
      card.appendChild(imgBox);
      card.appendChild(info);
      body.appendChild(card);
    });
  
    panel.appendChild(header);
    panel.appendChild(body);
    backdrop.appendChild(panel);
    modal.appendChild(backdrop);
  
    modal.style.display = "block";
  
    const close = () => {
      modal.style.display = "none";
      modal.innerHTML = "";
    };
  
    closeBtn.addEventListener("click", close);
  
    backdrop.addEventListener("click", (ev) => {
      if (ev.target?.id === "aoi-density-same-point-backdrop") close();
    });
  
    return true;
  }
  
  function buildSamePointLegend(legend) {
    if (!isSamePointActive()) return;
  
    const box = document.createElement("div");
    box.style.borderBottom = "1px dashed rgba(255,255,255,0.14)";
    box.style.paddingBottom = "8px";
  
    const label = document.createElement("label");
    Object.assign(label.style, {
      display: "flex",
      alignItems: "center",
      gap: "8px",
      cursor: "pointer",
      userSelect: "none",
      fontSize: "12px",
      fontWeight: "700"
    });
  
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = state.showSamePoint !== false;
  
    cb.addEventListener("change", () => {
      state.showSamePoint = cb.checked;
      redraw();
    });
  
    const txt = document.createElement("span");
    txt.textContent = "顯示同點星號";
  
    label.append(cb, txt);
    box.appendChild(label);
    legend.appendChild(box);
  }
  

  // ===== Legend：尺寸多選 + Defect Code 下拉 checkbox + Glass 下拉 checkbox =====
  function buildLegend(groups) {
    const legend = document.getElementById(LEGEND_ID);
    if (!legend) return;
  
    legend.innerHTML = "";
  
    buildSizeLegend(legend);
    buildSamePointLegend(legend);
    buildDefectCodeDropdownLegend(legend);
    buildGlassDropdownLegend(legend, groups || []);
  }

  function buildSizeLegend(legend) {
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
    Object.assign(sTitle.style, {
      fontWeight: "700",
      fontSize: "12px"
    });
    sTitle.textContent = "尺寸";

    const allSizeSelected = state.sizeFilter.size === 4;

    const sBtn = document.createElement("button");
    sBtn.className = "btn btn-xs btn-secondary";
    sBtn.textContent = allSizeSelected ? "清空" : "全選";

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
        background: state.sizeFilter.has(k) ? "rgba(255,255,255,0.06)" : "transparent",
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

      item.appendChild(sw);
      item.appendChild(label);

      item.addEventListener("click", () => {
        if (state.sizeFilter.has(k)) {
          state.sizeFilter.delete(k);
        } else {
          state.sizeFilter.add(k);
        }

        buildLegend(state.groups);
        redraw();
      });

      sWrap.appendChild(item);
    });

    sizeBox.appendChild(sWrap);
    legend.appendChild(sizeBox);
  }

  function buildDefectCodeDropdownLegend(legend) {
    const box = document.createElement("div");
    box.className = "aoi-density-map-code-dd-box";
    box.style.borderBottom = "1px dashed rgba(255,255,255,0.14)";
    box.style.paddingBottom = "8px";

    const codes = Array.isArray(state.defectCodeList)
      ? state.defectCodeList.map(normalizeDefectCode).filter(Boolean)
      : [];

    const selectedCount = codes.filter(code => state.defectCodeFilter.has(code)).length;
    const allSelected = codes.length > 0 && selectedCount === codes.length;

    const header = document.createElement("div");
    Object.assign(header.style, {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      marginBottom: "6px"
    });

    const title = document.createElement("div");
    Object.assign(title.style, {
      fontWeight: "700",
      fontSize: "12px"
    });
    title.textContent = "Defect Code 篩選";

    const btnAll = document.createElement("button");
    btnAll.className = "btn btn-xs btn-secondary";
    btnAll.textContent = allSelected ? "清空" : "全選";

    btnAll.addEventListener("click", (ev) => {
      ev.stopPropagation();

      if (allSelected) {
        state.defectCodeFilter = new Set();
      } else {
        state.defectCodeFilter = new Set(codes);
      }

      buildLegend(state.groups);
      redraw();
    });

    header.append(title, btnAll);
    box.appendChild(header);

    const ddWrap = document.createElement("div");
    ddWrap.className = "aoi-density-map-code-dd";
    Object.assign(ddWrap.style, {
      position: "relative",
      width: "100%"
    });

    const ddBtn = document.createElement("button");
    ddBtn.type = "button";
    ddBtn.className = "btn btn-xs btn-secondary";
    ddBtn.style.width = "100%";
    ddBtn.style.display = "flex";
    ddBtn.style.alignItems = "center";
    ddBtn.style.justifyContent = "space-between";
    ddBtn.style.gap = "6px";
    ddBtn.style.textAlign = "left";

    const btnText = document.createElement("span");
    btnText.style.overflow = "hidden";
    btnText.style.whiteSpace = "nowrap";
    btnText.style.textOverflow = "ellipsis";

    if (!codes.length) {
      btnText.textContent = "無 defect code";
    } else if (selectedCount === 0) {
      btnText.textContent = "未選取";
    } else if (selectedCount === 1) {
      btnText.textContent = Array.from(state.defectCodeFilter)[0] || "已選 1";
    } else if (selectedCount === codes.length) {
      btnText.textContent = `全部 defect code (${selectedCount})`;
    } else {
      btnText.textContent = `已選 ${selectedCount} / ${codes.length}`;
    }

    const arrow = document.createElement("span");
    arrow.textContent = state.defectCodeDropdownOpen ? "▲" : "▼";
    arrow.style.fontSize = "10px";
    arrow.style.opacity = "0.8";

    ddBtn.appendChild(btnText);
    ddBtn.appendChild(arrow);

    ddBtn.addEventListener("click", (ev) => {
      ev.stopPropagation();

      state.defectCodeDropdownOpen = !state.defectCodeDropdownOpen;
      state.glassDropdownOpen = false;

      buildLegend(state.groups);
    });

    ddWrap.appendChild(ddBtn);

    const panel = document.createElement("div");
    panel.className = "aoi-density-map-code-dd-panel";
    Object.assign(panel.style, {
      display: state.defectCodeDropdownOpen ? "block" : "none",
      position: "absolute",
      top: "calc(100% + 4px)",
      left: "0",
      right: "0",
      zIndex: "30",
      maxHeight: "260px",
      overflowY: "auto",
      overflowX: "hidden",
      background: "#111827",
      border: "1px solid rgba(255,255,255,0.18)",
      borderRadius: "6px",
      boxShadow: "0 10px 24px rgba(0,0,0,0.35)",
      padding: "6px"
    });

    panel.addEventListener("click", (ev) => {
      ev.stopPropagation();
    });

    const search = document.createElement("input");
    search.type = "text";
    search.placeholder = "搜尋 defect code...";
    Object.assign(search.style, {
      width: "100%",
      boxSizing: "border-box",
      marginBottom: "6px",
      padding: "4px 6px",
      borderRadius: "4px",
      border: "1px solid rgba(255,255,255,0.18)",
      background: "#0f1115",
      color: "#fff",
      fontSize: "12px",
      outline: "none"
    });

    panel.appendChild(search);

    const list = document.createElement("div");
    Object.assign(list.style, {
      display: "flex",
      flexDirection: "column",
      gap: "4px"
    });

    codes.slice().sort((a, b) => String(a).localeCompare(String(b))).forEach(code => {
      const row = document.createElement("label");
      row.className = "aoi-density-map-code-dd-item";
      row.dataset.label = String(code || "").toLowerCase();

      Object.assign(row.style, {
        display: "flex",
        alignItems: "center",
        gap: "8px",
        cursor: "pointer",
        padding: "4px 6px",
        borderRadius: "4px",
        border: "1px solid rgba(255,255,255,0.08)",
        background: state.defectCodeFilter.has(code)
          ? "rgba(255,255,255,0.06)"
          : "transparent",
        userSelect: "none"
      });

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = state.defectCodeFilter.has(code);

      cb.addEventListener("change", () => {
        if (cb.checked) {
          state.defectCodeFilter.add(code);
        } else {
          state.defectCodeFilter.delete(code);
        }

        state.defectCodeDropdownOpen = true;
        state.glassDropdownOpen = false;

        buildLegend(state.groups);
        redraw();
      });

      const label = document.createElement("span");
      label.style.fontSize = "12px";
      label.style.overflow = "hidden";
      label.style.textOverflow = "ellipsis";
      label.style.whiteSpace = "nowrap";
      label.textContent = code;

      row.appendChild(cb);
      row.appendChild(label);

      list.appendChild(row);
    });

    search.addEventListener("input", () => {
      const q = search.value.trim().toLowerCase();

      Array.from(list.querySelectorAll(".aoi-density-map-code-dd-item")).forEach(item => {
        const text = item.dataset.label || "";
        item.style.display = !q || text.includes(q) ? "" : "none";
      });
    });

    panel.appendChild(list);
    ddWrap.appendChild(panel);

    box.appendChild(ddWrap);
    legend.appendChild(box);
  }

  function buildGlassDropdownLegend(legend, groups) {
    const glassBox = document.createElement("div");
    glassBox.className = "aoi-density-map-glass-dd-box";

    const allGids = (groups || []).map(g => g.gid).filter(Boolean);
    const selectedCount = allGids.filter(gid => state.glassFilter.has(gid)).length;
    const allGlassSelected = allGids.length > 0 && selectedCount === allGids.length;

    const gHeader = document.createElement("div");
    Object.assign(gHeader.style, {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      marginBottom: "6px"
    });

    const gTitle = document.createElement("div");
    Object.assign(gTitle.style, {
      fontWeight: "700",
      fontSize: "12px"
    });
    gTitle.textContent = "Glass 篩選";

    const gBtn = document.createElement("button");
    gBtn.className = "btn btn-xs btn-secondary";
    gBtn.textContent = allGlassSelected ? "清空" : "全選";

    gBtn.addEventListener("click", (ev) => {
      ev.stopPropagation();

      if (allGids.length > 0 && state.glassFilter.size === allGids.length) {
        state.glassFilter = new Set();
      } else {
        state.glassFilter = new Set(allGids);
      }

      buildLegend(state.groups);
      redraw();
    });

    gHeader.append(gTitle, gBtn);
    glassBox.appendChild(gHeader);

    const ddWrap = document.createElement("div");
    ddWrap.className = "aoi-density-map-glass-dd";
    Object.assign(ddWrap.style, {
      position: "relative",
      width: "100%"
    });

    const ddBtn = document.createElement("button");
    ddBtn.type = "button";
    ddBtn.className = "btn btn-xs btn-secondary";
    ddBtn.style.width = "100%";
    ddBtn.style.display = "flex";
    ddBtn.style.alignItems = "center";
    ddBtn.style.justifyContent = "space-between";
    ddBtn.style.gap = "6px";
    ddBtn.style.textAlign = "left";

    const btnText = document.createElement("span");
    btnText.style.overflow = "hidden";
    btnText.style.whiteSpace = "nowrap";
    btnText.style.textOverflow = "ellipsis";

    if (!allGids.length) {
      btnText.textContent = "無 Glass";
    } else if (selectedCount === 0) {
      btnText.textContent = "未選取";
    } else if (selectedCount === allGids.length) {
      btnText.textContent = `全部 Glass (${selectedCount})`;
    } else {
      btnText.textContent = `已選 ${selectedCount} / ${allGids.length}`;
    }

    const arrow = document.createElement("span");
    arrow.textContent = state.glassDropdownOpen ? "▲" : "▼";
    arrow.style.fontSize = "10px";
    arrow.style.opacity = "0.8";

    ddBtn.appendChild(btnText);
    ddBtn.appendChild(arrow);

    ddBtn.addEventListener("click", (ev) => {
      ev.stopPropagation();

      state.glassDropdownOpen = !state.glassDropdownOpen;
      state.defectCodeDropdownOpen = false;

      buildLegend(state.groups);
    });

    ddWrap.appendChild(ddBtn);

    const panel = document.createElement("div");
    panel.className = "aoi-density-map-glass-dd-panel";
    Object.assign(panel.style, {
      display: state.glassDropdownOpen ? "block" : "none",
      position: "absolute",
      top: "calc(100% + 4px)",
      left: "0",
      right: "0",
      zIndex: "20",
      maxHeight: "260px",
      overflowY: "auto",
      overflowX: "hidden",
      background: "#111827",
      border: "1px solid rgba(255,255,255,0.18)",
      borderRadius: "6px",
      boxShadow: "0 10px 24px rgba(0,0,0,0.35)",
      padding: "6px"
    });

    panel.addEventListener("click", (ev) => {
      ev.stopPropagation();
    });

    const search = document.createElement("input");
    search.type = "text";
    search.placeholder = "搜尋 glass...";
    Object.assign(search.style, {
      width: "100%",
      boxSizing: "border-box",
      marginBottom: "6px",
      padding: "4px 6px",
      borderRadius: "4px",
      border: "1px solid rgba(255,255,255,0.18)",
      background: "#0f1115",
      color: "#fff",
      fontSize: "12px",
      outline: "none"
    });

    panel.appendChild(search);

    const list = document.createElement("div");
    Object.assign(list.style, {
      display: "flex",
      flexDirection: "column",
      gap: "4px"
    });

    const sortedGroups = (groups || [])
      .slice()
      .sort((a, b) => String(a.label).localeCompare(String(b.label)));

    sortedGroups.forEach(g => {
      const row = document.createElement("label");
      row.className = "aoi-density-map-glass-dd-item";
      row.dataset.label = String(g.label || g.gid || "").toLowerCase();

      Object.assign(row.style, {
        display: "flex",
        alignItems: "center",
        gap: "8px",
        cursor: "pointer",
        padding: "4px 6px",
        borderRadius: "4px",
        border: "1px solid rgba(255,255,255,0.08)",
        background: state.glassFilter.has(g.gid) ? "rgba(255,255,255,0.06)" : "transparent",
        userSelect: "none"
      });

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = state.glassFilter.has(g.gid);

      cb.addEventListener("change", () => {
        if (cb.checked) {
          state.glassFilter.add(g.gid);
        } else {
          state.glassFilter.delete(g.gid);
        }

        state.glassDropdownOpen = true;
        state.defectCodeDropdownOpen = false;

        buildLegend(state.groups);
        redraw();
      });

      const label = document.createElement("span");
      label.style.fontSize = "12px";
      label.style.overflow = "hidden";
      label.style.textOverflow = "ellipsis";
      label.style.whiteSpace = "nowrap";
      label.textContent = g.label || g.gid;

      row.appendChild(cb);
      row.appendChild(label);

      list.appendChild(row);
    });

    search.addEventListener("input", () => {
      const q = search.value.trim().toLowerCase();

      Array.from(list.querySelectorAll(".aoi-density-map-glass-dd-item")).forEach(item => {
        const text = item.dataset.label || "";
        item.style.display = !q || text.includes(q) ? "" : "none";
      });
    });

    panel.appendChild(list);
    ddWrap.appendChild(panel);

    glassBox.appendChild(ddWrap);
    legend.appendChild(glassBox);
  }

  // 點擊外部關閉 dropdown
  document.addEventListener("click", () => {
    if (!state.glassDropdownOpen && !state.defectCodeDropdownOpen) return;

    state.glassDropdownOpen = false;
    state.defectCodeDropdownOpen = false;

    buildLegend(state.groups);
  });

  // ===== 坐標軸與網格（左上原點，y 向下增） =====
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

    const xRange = x1 - x0;
    const yRange = y1 - y0;

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
      x1,
      y1,
      xScale,
      yScale
    };
  }

  // ===== 重畫 =====
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
  
    function toScreen(p) {
      const x = coord.padL + (p.x - coord.x0) * coord.xScale;
      const y = coord.padT + (p.y - coord.y0) * coord.yScale;
      return [x, y];
    }
  
    function rOf(b) {
      return b === "S" ? 3 : b === "M" ? 5 : b === "L" ? 7 : 9;
    }
  
    const groups = state.groups || [];
    const ptsAll = [];
    const hit = [];
  
    groups.forEach(g => {
      if (!state.glassFilter.has(g.gid)) return;
  
      g.points.forEach(p => {
        if (!p.bucket || !state.sizeFilter.has(p.bucket)) return;
  
        const code = normalizeDefectCode(
          p.defectCode ||
          p.meta?.adc_def_code ||
          "others"
        );
  
        if (state.defectCodeFilter.size === 0) return;
        if (!state.defectCodeFilter.has(code)) return;
  
        ptsAll.push({ ...p, gid: g.gid });
      });
    });
  
    // 先畫一般 defect 圓點
    ["S", "M", "L", "O"].forEach(b => {
      const pts = ptsAll.filter(p => p.bucket === b);
      if (!pts.length) return;
  
      ctx.fillStyle = SIZE_COLORS[b] || "#AAA";
  
      pts.forEach(p => {
        const [sx, sy] = toScreen(p);
        const r = rOf(p.bucket);
        //console.log('p',p);
        ctx.beginPath();
        ctx.arc(sx, sy, r, 0, Math.PI * 2);
        ctx.globalAlpha = 0.72;
        ctx.fill();
        ctx.globalAlpha = 1;
  
        hit.push({
          type: "defect",
          priority: 1,
          sx,
          sy,
          r: r + 4,
          url: p.img,
          point: p
        });
      });
    });
  
    // 最後畫 Same Point 星號，確保不被圓點覆蓋
    if (isSamePointActive() && state.showSamePoint !== false) {
      const spPts = collectSamePointPoints(state.samePointRows || []);
  
      spPts.forEach(p => {
        const [sx, sy] = toScreen(p);
  
        ctx.save();
        ctx.shadowColor = "#EA0000";
        ctx.shadowBlur = 3;
        ctx.fillStyle = "#FFDC00";
        ctx.strokeStyle = "#000000";
        ctx.lineWidth = 1.2;
        drawStar(ctx, sx, sy, 7, 3);
        ctx.restore();
  
        hit.push({
          type: "same_point",
          priority: 99,
          sx,
          sy,
          r: 15,
          url: p.meta?.img || "",
          point: {
            ...p,
            bucket: "同點",
            rawSize: "同點",
            defectCode: "same_point",
            img: p.meta?.img || "",
            meta: {
              ...p.meta,
              defect_size: p.meta?.defect_size || "同點",
              adc_def_code: p.meta?.adc_def_code || "same_point"
            }
          }
        });
      });
    }
  
    state.hitCache = hit;
  }
  

  // ===== 命中與 tooltip =====
  function findHit(ev) {
    const cvs = document.getElementById(CANVAS_ID);
    if (!cvs || !state.hitCache?.length) return null;
  
    const rect = cvs.getBoundingClientRect();
    const x = ev.clientX - rect.left;
    const y = ev.clientY - rect.top;
  
    let best = null;
    let bestScore = -Infinity;
  
    for (let i = 0; i < state.hitCache.length; i++) {
      const h = state.hitCache[i];
      const dx = x - h.sx;
      const dy = y - h.sy;
      const d2 = dx * dx + dy * dy;
  
      if (d2 > h.r * h.r) continue;
  
      const priority = Number(h.priority || 0);
      const score = priority * 1000000 - d2;
  
      if (score > bestScore) {
        best = h;
        bestScore = score;
      }
    }
  
    return best;
  }

  function tooltipHtmlFromPoint(p) {
    const m = p?.meta || {};
    const isSamePoint = p?.type === "same_point";
  
    const keys = isSamePoint
      ? [
          "lotid",
          "recipe",
          "test_time",
          "x",
          "y",
          "defect_size",
          "adc_def_code",
          "chip",
          "common_cnt",
          "common_glass_cnt",
          "cluster_point_cnt",
          "cluster_glass_cnt",
          "img"
        ]
      : DEFECT_INFO_KEYS;
  
    const kv = {
      lotid: m.lotid ?? m.lot ?? "",
      recipe: m.recipe ?? p?.recipe_id ?? "",
      test_time: m.test_time ?? "",
      x: m.x ?? p?.x ?? "",
      y: m.y ?? p?.y ?? "",
      defect_size: m.defect_size ?? p?.rawSize ?? p?.bucket ?? "",
      adc_def_code: m.adc_def_code ?? p?.defectCode ?? "",
      chip: m.chip ?? p?.chip ?? "",
      common_cnt: m.common_cnt ?? "",
      common_glass_cnt: m.common_glass_cnt ?? "",
      cluster_point_cnt: m.cluster_point_cnt ?? "",
      cluster_glass_cnt: m.cluster_glass_cnt ?? "",
      img: m.img ?? p?.img ?? ""
    };
  
    const rows = keys.map(k => {
      const v = kv[k] ?? "";
      return `<tr>
        <td style="opacity:.65;padding-right:8px;white-space:nowrap;">${escHtml(k)}</td>
        <td style="word-break:break-all;">${escHtml(v)}</td>
      </tr>`;
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

    if (x + rect.width > vw - 8) {
      x = vw - rect.width - 8;
    }

    if (y + rect.height > vh - 8) {
      y = vh - rect.height - 8;
    }

    tips.style.left = `${x}px`;
    tips.style.top = `${y}px`;
  }

  function hideTooltip() {
    const tips = document.getElementById(TIPS_ID);
    if (!tips) return;

    tips.style.display = "none";
  }

  // ===== 對外 API =====
  MOD.Map.setData = function (response, requestRows, samePointRows) {
    state.groups = normalizeResponse(response);
    state.samePointRows = Array.isArray(samePointRows)
      ? samePointRows
      : (state.samePointRows || []);
  
    state.sizeFilter = new Set(["S", "M", "L", "O"]);
  
    state.triggerDefCode = normalizeDefectCode(
      response?.TriggerDefCode ||
      requestRows?.[0]?.adc_def_code ||
      ""
    );
  
    let codes = Array.isArray(response?.DefectCodeList)
      ? uniqSorted(response.DefectCodeList)
      : [];
  
    if (!codes.length) {
      codes = collectDefectCodesFromGroups(state.groups);
    }
  
    if (state.triggerDefCode && !codes.includes(state.triggerDefCode)) {
      codes.unshift(state.triggerDefCode);
    }
  
    state.defectCodeList = codes;
  
    if (state.triggerDefCode) {
      state.defectCodeFilter = new Set([state.triggerDefCode]);
    } else {
      state.defectCodeFilter = new Set(codes);
    }
  
    state.glassFilter = new Set((state.groups || []).map(g => g.gid));
  
    state.defectCodeDropdownOpen = false;
    state.glassDropdownOpen = false;
  
    buildLegend(state.groups);
    redraw();
  };
  

  MOD.Map.clear = function () {
    state.groups = [];
  
    state.sizeFilter = new Set(["S", "M", "L", "O"]);
  
    state.defectCodeList = [];
    state.triggerDefCode = "";
    state.defectCodeFilter = new Set();
    state.defectCodeDropdownOpen = false;
  
    state.glassFilter = new Set();
    state.glassDropdownOpen = false;
  
    state.samePointRows = [];
    state.showSamePoint = true;
  
    state.hitCache = [];
  
    buildLegend([]);
    redraw();
  };

  // 支援外部事件餵資料
  document.addEventListener("aoi-density:defect-map-ready", (ev) => {
    const resp = ev?.detail?.response || null;
    const requestRows = ev?.detail?.requestRows || [];
    const samePointRows = ev?.detail?.samePointRows || [];
  
    MOD.Map.setData(resp || {}, requestRows, samePointRows);
  });

  document.addEventListener("aoi-density:data-ready", () => {
    MOD.Map.clear?.();
  });

  // ===== 綁定事件 =====
  function bindCanvasEvents() {
    const cvs = document.getElementById(CANVAS_ID);
    if (!cvs) return;
  
    cvs.addEventListener("mousemove", (ev) => {
      const hit = findHit(ev);
  
      if (hit && hit.point) {
        cvs.style.cursor = "pointer";
        showTooltip(ev, tooltipHtmlFromPoint(hit.point));
      } else {
        cvs.style.cursor = "default";
        hideTooltip();
      }
    });
  
    cvs.addEventListener("mouseleave", hideTooltip);
  
    cvs.addEventListener("click", (ev) => {
      const hit = findHit(ev);
      if (!hit || !hit.point) return;
  
      hideTooltip();
  
      if (hit.type === "same_point" || hit.point?.type === "same_point") {
        showSamePointModal(hit);
        return;
      }
  
      if (hit.url) {
        window.open(hit.url, "_blank", "noopener");
      }
    });
  }

  window.addEventListener("resize", () => {
    hideTooltip();
    redraw();
  });

  // 初始化
  let _mapUiInited = false;

  function initMapUI() {
    if (_mapUiInited) return;

    _mapUiInited = true;

    ensureLayout();
    buildLegend([]);
    bindCanvasEvents();
    redraw();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initMapUI, { once: true });
  } else {
    initMapUI();
  }
})();