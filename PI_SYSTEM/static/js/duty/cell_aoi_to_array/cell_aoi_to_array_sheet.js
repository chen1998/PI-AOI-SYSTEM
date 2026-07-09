// static/js/duty/cell_aoi_to_array/cell_aoi_to_array_sheet.js
(function () {
  "use strict";

  window.CELL_AOI_TO_ARRAY = window.CELL_AOI_TO_ARRAY || {};
  const MOD = window.CELL_AOI_TO_ARRAY;

  MOD.Sheet = {
    render,
    renderEmpty,
    applyDetailResult,
    clearDetailView,
    preloadFullDefectGroups
  };

  function clearDetailView() {
    if (!MOD.State || !MOD.State.dom || !MOD.State.state) return;

    const { dom, state } = MOD.State;

    state.selectedRow = null;
    state.currentSheetDefects = [];

    if (MOD.State.resetMapFilters) {
      MOD.State.resetMapFilters();
    }

    if (MOD.DefectTable && typeof MOD.DefectTable.resetForNewSheet === "function") {
      MOD.DefectTable.resetForNewSheet();
    }

    if (MOD.Map && typeof MOD.Map.clear === "function") {
      MOD.Map.clear();
    }

    if (dom.sheetDetail) {
      dom.sheetDetail.innerHTML = "";

      const loading = document.createElement("div");
      loading.className = "cell-aoi-to-array-sheet-empty";

      if (MOD.UI && MOD.UI.createEmptyState) {
        loading.appendChild(
          MOD.UI.createEmptyState("⌛", "Sheet detail 載入中...")
        );
      } else {
        loading.textContent = "Sheet detail 載入中...";
      }

      dom.sheetDetail.appendChild(loading);
    }

    if (dom.defectTableHead) dom.defectTableHead.innerHTML = "";
    if (dom.defectTableBody) dom.defectTableBody.innerHTML = "";
    if (dom.defectListCount) dom.defectListCount.textContent = "Total 0 defects";
    if (dom.defectListWrap) dom.defectListWrap.style.display = "none";
  }

  function render(row) {
    const { dom, state } = MOD.State;

    if (!dom.sheetDetail) return;

    dom.sheetDetail.innerHTML = "";

    if (!row) {
      renderEmpty();
      return;
    }

    MOD.State.ensureRowDefectContainers(row);

    state.selectedRow = row;
    state.currentSheetDefects = Array.isArray(row.defects) ? row.defects : [];

    const layout = document.createElement("div");
    layout.className = "cell-aoi-to-array-sheet-detail-layout";

    const infoPanel = createInfoPanel(row);
    const mapPanel = createMapPanel(row);

    layout.appendChild(infoPanel);
    layout.appendChild(mapPanel);

    dom.sheetDetail.appendChild(layout);

    if (MOD.Map && MOD.Map.render) {
      MOD.Map.render(row);
    }

    if (MOD.DefectTable && MOD.DefectTable.render) {
      MOD.DefectTable.render(row);
    }

    updateReturnButtonState();
  }

  function renderEmpty() {
    const { dom, state } = MOD.State;
  
    if (!dom.sheetDetail) return;
  
    dom.sheetDetail.innerHTML = "";
  
    const selectedRow = state.selectedRow || null;
  
    const empty = document.createElement("div");
    empty.className = "cell-aoi-to-array-sheet-empty";
  
    const box = document.createElement("div");
    box.className = "cell-aoi-to-array-empty-state";
  
    const icon = document.createElement("button");
    icon.type = "button";
    icon.className = "cell-aoi-to-array-empty-icon cell-aoi-to-array-detail-empty-btn";
    icon.textContent = "🖼";
  
    const text = document.createElement("div");
  
    if (selectedRow) {
      const sheet =
        selectedRow.sheet_id_chip_id ||
        selectedRow.sheet_id ||
        selectedRow.detail?.sheet_id ||
        "-";
  
      const time =
        selectedRow.test_time ||
        selectedRow.scan_time ||
        selectedRow.detail?.scan_time ||
        "";
  
      text.innerHTML = "";
  
      const line1 = document.createElement("div");
      line1.textContent = "Chart 已選取一筆資料";
  
      const line2 = document.createElement("div");
      line2.className = "cell-aoi-to-array-empty-sub";
      line2.textContent = `${sheet}${time ? " / " + time : ""}`;
  
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "cell-aoi-to-array-btn cell-aoi-to-array-btn-soft cell-aoi-to-array-open-detail-btn";
      btn.textContent = "查看 Sheet 詳情";
      btn.title = "等同點擊 table row 的詳情圖示";
  
      const openSelectedDetail = async function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
  
        if (MOD.Table && typeof MOD.Table.openDetail === "function") {
          await MOD.Table.openDetail(selectedRow);
        } else {
          console.error("[cell-aoi-to-array-sheet] MOD.Table.openDetail not ready");
        }
      };
  
      icon.addEventListener("click", openSelectedDetail);
      btn.addEventListener("click", openSelectedDetail);
  
      box.appendChild(icon);
      box.appendChild(line1);
      box.appendChild(line2);
      box.appendChild(btn);
    } else {
      icon.disabled = true;
      text.textContent = "請點擊 table 詳情查看 sheet defect map";
  
      box.appendChild(icon);
      box.appendChild(text);
    }
  
    empty.appendChild(box);
    dom.sheetDetail.appendChild(empty);
  
    if (dom.defectListWrap) {
      dom.defectListWrap.style.display = "none";
    }
  }
  

  function applyDetailResult(row, result) {
    if (!row || !result) return row;

    const detail = result.detail || {};
    const defects = Array.isArray(result.defects) ? result.defects : [];

    row.detail = detail;

    mergeDetailToRow(row, detail);

    // 這裡 defects 預期主要是 point_detail 解析出的同點 rows。
    row.defects = defects;

    MOD.State.ensureRowDefectContainers(row);

    const groups = result.defectGroups || {};
    const loaded = result.groupsLoaded || {};

    row.defectGroups.same_point = Array.isArray(groups.same_point)
      ? groups.same_point
      : row.defectGroups.same_point || [];

    row.defectGroups.cell_aoi = Array.isArray(groups.cell_aoi)
      ? groups.cell_aoi
      : row.defectGroups.cell_aoi || [];

    row.defectGroups.source = Array.isArray(groups.source)
      ? groups.source
      : row.defectGroups.source || [];

    row.groupsLoaded.same_point = Boolean(
      loaded.same_point ||
      row.groupsLoaded.same_point ||
      row.defectGroups.same_point.length
    );

    row.groupsLoaded.cell_aoi = Boolean(
      loaded.cell_aoi ||
      row.groupsLoaded.cell_aoi ||
      row.defectGroups.cell_aoi.length
    );

    row.groupsLoaded.source = Boolean(
      loaded.source ||
      row.groupsLoaded.source ||
      row.defectGroups.source.length
    );

    return row;
  }

  async function preloadFullDefectGroups(row) {
    if (!row || !MOD.API || typeof MOD.API.fetchDefectGroups !== "function") {
      return;
    }

    MOD.State.ensureRowDefectContainers(row);

    if (row.groupsLoaded.cell_aoi && row.groupsLoaded.source) {
      return;
    }

    const filters = MOD.State.state.mapFilters || {};

    if (filters.fullGroupsLoading) {
      return;
    }

    filters.fullGroupsLoading = true;

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

      const shouldRedraw =
        filters.groups instanceof Set &&
        (
          filters.groups.has("cell_aoi") ||
          filters.groups.has("source")
        );

      if (shouldRedraw && MOD.Map && typeof MOD.Map.redraw === "function") {
        MOD.Map.redraw();
      }
    } catch (err) {
      console.error("[cell-aoi-to-array-sheet] preloadFullDefectGroups failed:", err);
    } finally {
      filters.fullGroupsLoading = false;
    
      /*
       * 預載完成後要刷新 legend，
       * 不然 legend hint 可能一直停在「完整 defect group 載入中...」
       */
      if (MOD.Map && typeof MOD.Map.refreshLegend === "function") {
        MOD.Map.refreshLegend();
      }
    
      if (MOD.Map && typeof MOD.Map.redraw === "function") {
        MOD.Map.redraw();
      }
    
      /*
       * 預載完成後重新 render defect table。
       * 原因：
       * /detail 初始只有 point_detail rows，
       * /detail-defect-groups 回來後才有完整 cell_aoi 母體。
       */
      if (
        MOD.State &&
        MOD.State.state &&
        MOD.State.state.selectedRow === row &&
        MOD.DefectTable &&
        typeof MOD.DefectTable.render === "function"
      ) {
        MOD.DefectTable.render(row);
      }
    }
  }

  function createInfoPanel(row) {
    const panel = document.createElement("section");
    panel.className = "cell-aoi-to-array-sheet-info-panel card-sub";

    const head = document.createElement("div");
    head.className = "cell-aoi-to-array-sheet-info-head";

    const title = document.createElement("h3");
    title.className = "cell-aoi-to-array-sheet-info-title";
    title.textContent = "Sheet Detail";

    const sub = document.createElement("div");
    sub.className = "cell-aoi-to-array-sheet-info-sub";
    sub.textContent = buildSheetSubTitle(row);

    head.appendChild(title);
    head.appendChild(sub);

    const kv = document.createElement("div");
    kv.className = "cell-aoi-to-array-sheet-kv-list";

    const fields = getSheetDetailFields(row);

    fields.forEach(function (field) {
      kv.appendChild(createKvItem(row, field));
    });

    panel.appendChild(head);
    panel.appendChild(kv);

    return panel;
  }

  function createMapPanel(row) {
    const panel = document.createElement("section");
    panel.className = "cell-aoi-to-array-map-panel card-sub";

    const head = document.createElement("div");
    head.className = "cell-aoi-to-array-map-head";

    const titleWrap = document.createElement("div");
    titleWrap.className = "cell-aoi-to-array-map-title-wrap";

    const title = document.createElement("h3");
    title.className = "cell-aoi-to-array-map-title";
    title.textContent = "Defect Map";

    const sub = document.createElement("div");
    sub.className = "cell-aoi-to-array-map-sub";
    sub.textContent = buildMapSubTitle(row);

    titleWrap.appendChild(title);
    titleWrap.appendChild(sub);

    const actions = document.createElement("div");
    actions.className = "cell-aoi-to-array-map-actions";

    const returnBtn = document.createElement("button");
    returnBtn.type = "button";
    returnBtn.id = "cell-aoi-to-array-map-return-btn";
    returnBtn.className = "cell-aoi-to-array-btn cell-aoi-to-array-btn-soft cell-aoi-to-array-map-return-btn";
    returnBtn.textContent = "RETURN";
    returnBtn.title = "回復 defect table 顯示全部 defect rows";
    returnBtn.disabled = true;
    returnBtn.style.display = "none";

    returnBtn.addEventListener("click", function () {
      if (MOD.DefectTable && MOD.DefectTable.clearFocus) {
        MOD.DefectTable.clearFocus();
      }

      if (MOD.Map && MOD.Map.clearSelectedPoint) {
        MOD.Map.clearSelectedPoint();
      }

      updateReturnButtonState();
    });

    const resetBtn = document.createElement("button");
    resetBtn.type = "button";
    resetBtn.className = "cell-aoi-to-array-btn cell-aoi-to-array-btn-soft";
    resetBtn.textContent = "RESET";
    resetBtn.title = "重設 defect map zoom";

    resetBtn.addEventListener("click", function () {
      if (MOD.Map && MOD.Map.resetView) {
        MOD.Map.resetView();
      }
    });

    const boxBtn = document.createElement("button");
    boxBtn.type = "button";
    boxBtn.className = "cell-aoi-to-array-btn cell-aoi-to-array-btn-soft";
    boxBtn.textContent = "BOX";
    boxBtn.title = "切換框選 zoom 模式";

    boxBtn.addEventListener("click", function () {
      if (MOD.Map && MOD.Map.toggleBoxMode) {
        MOD.Map.toggleBoxMode();
      }
    });

    actions.appendChild(returnBtn);
    actions.appendChild(resetBtn);
    actions.appendChild(boxBtn);

    head.appendChild(titleWrap);
    head.appendChild(actions);

    const body = document.createElement("div");
    body.className = "cell-aoi-to-array-map-body";

    const canvasWrap = document.createElement("div");
    canvasWrap.className = "cell-aoi-to-array-map-canvas-wrap";

    const canvas = document.createElement("canvas");
    canvas.id = "cell-aoi-to-array-defect-map-canvas";
    canvas.className = "cell-aoi-to-array-defect-map-canvas";

    const tooltip = document.createElement("div");
    tooltip.id = "cell-aoi-to-array-defect-map-tooltip";
    tooltip.className = "cell-aoi-to-array-defect-map-tooltip";
    tooltip.style.display = "none";

    canvasWrap.appendChild(canvas);
    canvasWrap.appendChild(tooltip);

    const legend = document.createElement("div");
    legend.id = "cell-aoi-to-array-defect-map-legend";
    legend.className = "cell-aoi-to-array-defect-map-legend";

    body.appendChild(canvasWrap);
    body.appendChild(legend);

    panel.appendChild(head);
    panel.appendChild(body);

    return panel;
  }

  function createKvItem(row, field) {
    const item = document.createElement("div");
    item.className = "cell-aoi-to-array-sheet-kv-item";

    const label = document.createElement("div");
    label.className = "cell-aoi-to-array-sheet-kv-label";
    label.textContent = field.label || field.key || "";

    const value = document.createElement("div");
    value.className = "cell-aoi-to-array-sheet-kv-value";

    const raw = getRowValue(row, field.key);
    const formatted = formatFieldValue(raw, field);

    value.textContent = formatted;
    value.title = formatted;

    item.appendChild(label);
    item.appendChild(value);

    return item;
  }

  function getSheetDetailFields(row) {
    if (MOD.State && MOD.State.getSheetDetailFieldsByRow) {
      const fields = MOD.State.getSheetDetailFieldsByRow(row);
      if (Array.isArray(fields) && fields.length) {
        return fields;
      }
    }

    if (MOD.State && MOD.State.getSheetDetailFields) {
      const fields = MOD.State.getSheetDetailFields();
      if (Array.isArray(fields) && fields.length) {
        return fields;
      }
    }

    return fallbackSheetDetailFields();
  }

  function fallbackSheetDetailFields() {
    return [
      { key: "sheet_id_chip_id", label: "Sheet ID" },
      { key: "test_time", label: "CELL Scan Time" },
      { key: "pi_type", label: "CELL PI" },
      { key: "abbr_cat", label: "ABBR" },
      { key: "model_no", label: "Model" },
      { key: "recipe_id", label: "Recipe" },
      { key: "aoi", label: "CELL AOI" },
      { key: "line_id", label: "Line" },
      { key: "total_defect_qty", label: "CELL Defect" },
      { key: "source_op_id", label: "Source OP" },
      { key: "source_defect_cnt", label: "Source Defect" },
      { key: "same_point_defect_cnt", label: "Same Point" },
      { key: "same_point_rate", label: "Same Rate" },
      { key: "match_status", label: "Status" }
    ];
  }

  function mergeDetailToRow(row, detail) {
    if (!row || !detail || typeof detail !== "object") return;

    Object.keys(detail).forEach(function (key) {
      const value = detail[key];

      if (value !== undefined && value !== null && value !== "") {
        row[key] = value;
      }
    });

    const aliasMap = {
      sheet_id: "sheet_id_chip_id",
      scan_time: "test_time",
      cell_op: "pi_type",
      cell_aoi: "aoi",
      cell_line_id: "line_id",
      cell_defect_cnt: "total_defect_qty"
    };

    Object.keys(aliasMap).forEach(function (srcKey) {
      const dstKey = aliasMap[srcKey];

      if (
        detail[srcKey] !== undefined &&
        detail[srcKey] !== null &&
        detail[srcKey] !== ""
      ) {
        row[dstKey] = detail[srcKey];
      }
    });
  }

  function buildSheetSubTitle(row) {
    const sheet = getRowValue(row, "sheet_id_chip_id") || getRowValue(row, "sheet_id") || "-";
    const time = getRowValue(row, "test_time") || getRowValue(row, "scan_time") || "-";
    const op = getRowValue(row, "pi_type") || getRowValue(row, "cell_op") || "-";
    const src = getRowValue(row, "source_op_id") || "-";

    return `${sheet} | ${op} | ${src} | ${formatDateTime(time)}`;
  }

  function buildMapSubTitle(row) {
    const sameCnt = countGroup(row, "same_point");
    const cellCnt = countGroup(row, "cell_aoi");
    const sourceCnt = countGroup(row, "source");

    const loaded = row?.groupsLoaded || {};
    const sourceText = loaded.source ? sourceCnt : "未顯示";
    const cellText = loaded.cell_aoi ? cellCnt : "未顯示";

    return `Same ${sameCnt} / CELL ${cellText} / Source ${sourceText}`;
  }

  function countGroup(row, key) {
    return Array.isArray(row?.defectGroups?.[key])
      ? row.defectGroups[key].length
      : 0;
  }

  function updateReturnButtonState() {
    const btn = document.getElementById("cell-aoi-to-array-map-return-btn");
    if (!btn) return;

    let hasFocus = false;

    if (MOD.DefectTable && MOD.DefectTable.getState) {
      const state = MOD.DefectTable.getState();
      hasFocus = Boolean(state && state.focusPoint);
    }

    btn.disabled = !hasFocus;
    btn.style.display = hasFocus ? "" : "none";
  }

  function getRowValue(row, key) {
    if (!row || !key) return "";

    if (Object.prototype.hasOwnProperty.call(row, key)) {
      return row[key];
    }

    if (row.detail && Object.prototype.hasOwnProperty.call(row.detail, key)) {
      return row.detail[key];
    }

    const alias = {
      sheet_id: "sheet_id_chip_id",
      sheet_id_chip_id: "sheet_id",
      scan_time: "test_time",
      test_time: "scan_time",
      cell_op: "pi_type",
      pi_type: "cell_op",
      cell_aoi: "aoi",
      aoi: "cell_aoi",
      cell_line_id: "line_id",
      line_id: "cell_line_id",
      cell_defect_cnt: "total_defect_qty",
      total_defect_qty: "cell_defect_cnt"
    };

    if (alias[key] && Object.prototype.hasOwnProperty.call(row, alias[key])) {
      return row[alias[key]];
    }

    if (
      row.detail &&
      alias[key] &&
      Object.prototype.hasOwnProperty.call(row.detail, alias[key])
    ) {
      return row.detail[alias[key]];
    }

    return "";
  }

  function formatFieldValue(value, field) {
    const key = field?.key || "";

    if (value == null || value === "") return "-";

    if (isDateTimeKey(key)) {
      return formatDateTime(value);
    }

    if (isRateKey(key)) {
      return formatRate(value);
    }

    if (isNumberKey(key)) {
      return formatNumber(value);
    }

    const s = String(value).trim();

    if (!s || ["none", "nan", "nat", "<na>", "null"].includes(s.toLowerCase())) {
      return "-";
    }

    return s;
  }

  function isDateTimeKey(key) {
    return [
      "test_time",
      "scan_time",
      "pi_time",
      "source_scan_time",
      "modify_time",
      "create_time",
      "update_time"
    ].includes(key);
  }

  function isRateKey(key) {
    return String(key || "").toLowerCase().includes("rate");
  }

  function isNumberKey(key) {
    return [
      "total_defect_qty",
      "cell_defect_cnt",
      "source_defect_cnt",
      "same_point_defect_cnt",
      "same_point_offset",
      "distance",
      "dx",
      "dy"
    ].includes(key);
  }

  function formatDateTime(value) {
    if (value == null || value === "") return "-";

    const d = new Date(value);

    if (Number.isNaN(d.getTime())) {
      return String(value);
    }

    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    const hh = String(d.getHours()).padStart(2, "0");
    const mi = String(d.getMinutes()).padStart(2, "0");
    const ss = String(d.getSeconds()).padStart(2, "0");

    return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}`;
  }

  function formatRate(value) {
    const n = Number(value);

    if (!Number.isFinite(n)) {
      return value == null || value === "" ? "-" : String(value);
    }

    if (Math.abs(n) <= 1) {
      return `${Math.round(n * 10000) / 100}%`;
    }

    return `${Math.round(n * 100) / 100}%`;
  }

  function formatNumber(value) {
    const n = Number(value);

    if (!Number.isFinite(n)) {
      return value == null || value === "" ? "-" : String(value);
    }

    if (Math.abs(n) >= 1000) {
      return Math.round(n).toLocaleString();
    }

    return String(Math.round(n * 1000) / 1000);
  }
})();
