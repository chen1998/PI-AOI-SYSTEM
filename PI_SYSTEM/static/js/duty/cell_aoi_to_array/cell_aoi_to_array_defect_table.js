// static/js/duty/cell_aoi_to_array/cell_aoi_to_array_defect_table.js
(function () {
  "use strict";

  window.CELL_AOI_TO_ARRAY = window.CELL_AOI_TO_ARRAY || {};
  const MOD = window.CELL_AOI_TO_ARRAY;

  const tableState = {
    focusPoint: null,

    // 每次點新的 sheet detail 後會被 reset 成 matched。
    // 頁面初始保留 all，避免初始化時沒有資料造成誤判。
    matchFilter: "all"
  };

  MOD.DefectTable = {
    render,
    renderToolbar,
    renderHead,
    renderBody,
    getRows,
    focusByMapPoint,
    clearFocus,
    setMatchFilter,
    resetForNewSheet,
    setDefaultMatchedOnly,
    getState
  };

  function getState() {
    return tableState;
  }

  function resetForNewSheet() {
    tableState.focusPoint = null;
    tableState.matchFilter = "matched";

    const { dom } = MOD.State || {};

    if (dom) {
      if (dom.defectTableHead) dom.defectTableHead.innerHTML = "";
      if (dom.defectTableBody) dom.defectTableBody.innerHTML = "";
      if (dom.defectListCount) dom.defectListCount.textContent = "Total 0 defects";
      if (dom.defectListWrap) dom.defectListWrap.style.display = "none";
    }

    updateReturnButtonState();
  }

  function setDefaultMatchedOnly() {
    tableState.focusPoint = null;
    tableState.matchFilter = "matched";
    updateReturnButtonState();
  }

  function render(row) {
    renderToolbar(row);
    renderHead(row);
    renderBody(row);
    updateCount(row);
  }

  function renderToolbar(row) {
    const { dom } = MOD.State || {};
    if (!dom || !dom.defectListWrap) return;

    const head = dom.defectListWrap.querySelector(".cell-aoi-to-array-defect-list-head");
    if (!head) return;

    let tools = head.querySelector(".cell-aoi-to-array-defect-list-tools");

    if (!tools) {
      tools = document.createElement("div");
      tools.className = "cell-aoi-to-array-defect-list-tools";
      head.appendChild(tools);
    }

    let btn = tools.querySelector("#cell-aoi-to-array-defect-table-return-btn");

    if (!btn) {
      btn = document.createElement("button");
      btn.type = "button";
      btn.id = "cell-aoi-to-array-defect-table-return-btn";
      btn.className = "cell-aoi-to-array-return-btn cell-aoi-to-array-defect-table-return-btn";
      btn.textContent = "RETURN";
      btn.title = "回復顯示全部 DEFECT 資料";

      btn.addEventListener("click", function () {
        clearFocus();

        if (MOD.Map && MOD.Map.clearSelectedPoint) {
          MOD.Map.clearSelectedPoint();
        }
      });

      tools.appendChild(btn);
    }

    const hasFocus = Boolean(tableState.focusPoint);
    btn.disabled = !hasFocus;
    btn.style.display = hasFocus ? "" : "none";
  }

  function renderHead(row) {
    const { dom } = MOD.State || {};
    if (!dom || !dom.defectTableHead) return;

    dom.defectTableHead.innerHTML = "";

    const columns = getColumns(row);
    const tr = document.createElement("tr");

    columns.forEach(function (col) {
      const th = document.createElement("th");

      if ((col.type || "") === "match" || col.key === "match") {
        th.appendChild(createMatchFilterHeader(col));
      } else {
        th.textContent = col.label || col.key || "";
      }

      tr.appendChild(th);
    });

    dom.defectTableHead.appendChild(tr);
  }

  function renderBody(row) {
    const { dom } = MOD.State || {};
    if (!dom || !dom.defectTableBody) return;

    dom.defectTableBody.innerHTML = "";

    const columns = getColumns(row);
    const rows = getRows(row);

    if (!rows.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");

      td.colSpan = Math.max(columns.length, 1);
      td.className = "cell-aoi-to-array-empty-td";

      const msg = tableState.focusPoint
        ? "目前沒有符合該 map 點位的 defect row"
        : "目前沒有 defect 明細";

      if (MOD.UI && MOD.UI.createEmptyState) {
        td.appendChild(MOD.UI.createEmptyState("∅", msg));
      } else {
        td.textContent = msg;
      }

      tr.appendChild(td);
      dom.defectTableBody.appendChild(tr);
      return;
    }

    rows.forEach(function (defect, idx) {
      const tr = document.createElement("tr");

      if (Boolean(defect.match)) {
        tr.classList.add("cell-aoi-to-array-defect-row-matched");
      } else {
        tr.classList.add("cell-aoi-to-array-defect-row-unmatched");
      }

      if (isFocusedDefect(defect, tableState.focusPoint)) {
        tr.classList.add("cell-aoi-to-array-defect-row-focused");
      }

      columns.forEach(function (col) {
        const td = document.createElement("td");
        td.appendChild(createCell(defect, col, idx));
        tr.appendChild(td);
      });

      dom.defectTableBody.appendChild(tr);
    });
  }

  function createMatchFilterHeader(col) {
    const wrap = document.createElement("div");
    wrap.className = "cell-aoi-to-array-defect-match-filter-head";
  
    const label = document.createElement("div");
    label.className = "cell-aoi-to-array-defect-match-filter-label";
    label.textContent = col.label || "Match";
  
    const select = document.createElement("select");
    select.className = "cell-aoi-to-array-defect-match-filter";
  
    [
      { value: "all", label: "全部" },
      { value: "matched", label: "同點" },
      { value: "unmatched", label: "未同點" }
    ].forEach(function (opt) {
      const option = document.createElement("option");
      option.value = opt.value;
      option.textContent = opt.label;
      select.appendChild(option);
    });
  
    // 重點：option append 完後再設定 value
    select.value = tableState.matchFilter || "matched";
  
    select.addEventListener("change", function () {
      setMatchFilter(select.value);
    });
  
    wrap.appendChild(label);
    wrap.appendChild(select);
  
    return wrap;
  }

  function setMatchFilter(value) {
    const v = String(value || "all").trim().toLowerCase();
    tableState.matchFilter = ["all", "matched", "unmatched"].includes(v) ? v : "all";

    const row = MOD.State?.state?.selectedRow || null;
    render(row);
  }

  function focusByMapPoint(point) {
    tableState.focusPoint = point || null;
  
    if (point) {
      tableState.matchFilter = inferMatchFilterByMapPoint(point);
    }
  
    const row = MOD.State?.state?.selectedRow || null;
    render(row);
  
    updateReturnButtonState();
  }
  
  function inferMatchFilterByMapPoint(point) {
    if (!point) return tableState.matchFilter || "all";
  
    if (point.group === "same_point") {
      return "matched";
    }
  
    if (point.match) {
      return "matched";
    }
  
    return "unmatched";
  }

  function clearFocus() {
    tableState.focusPoint = null;

    const row = MOD.State?.state?.selectedRow || null;
    render(row);

    updateReturnButtonState();
  }

  function updateReturnButtonState() {
    const hasFocus = Boolean(tableState.focusPoint);

    const mapBtn = document.getElementById("cell-aoi-to-array-map-return-btn");
    if (mapBtn) {
      mapBtn.disabled = !hasFocus;
      mapBtn.style.display = hasFocus ? "" : "none";
    }

    const tableBtn = document.getElementById("cell-aoi-to-array-defect-table-return-btn");
    if (tableBtn) {
      tableBtn.disabled = !hasFocus;
      tableBtn.style.display = hasFocus ? "" : "none";
    }
  }

  function getRows(row) {
    if (!row) return [];
  
    if (MOD.State && MOD.State.ensureRowDefectContainers) {
      MOD.State.ensureRowDefectContainers(row);
    }
  
    const mergedRows = buildMergedDefectRows(row);
    let rows = mergedRows.slice();
  
    /*
     * 如果是 map 點擊 focus，優先依 map point 決定要顯示哪一筆。
     * 不再先用 matchFilter 過濾，避免 source-only row 被過濾掉。
     */
    if (tableState.focusPoint) {
      return buildFocusedRows(mergedRows, tableState.focusPoint);
    }
  
    if (tableState.matchFilter === "matched") {
      rows = rows.filter(function (d) {
        return Boolean(d.match);
      });
    } else if (tableState.matchFilter === "unmatched") {
      rows = rows.filter(function (d) {
        return !Boolean(d.match);
      });
    }
  
    return rows;
  }

  function buildFocusedRows(mergedRows, point) {
    if (!point) return [];
  
    const exactRows = mergedRows.filter(function (d) {
      return isFocusedDefect(d, point);
    });
  
    if (exactRows.length) {
      return exactRows;
    }
  
    /*
     * 點 source 方形點：
     * 如果它沒有對應 CELL 同點 row，不可以 fallback 到最近 CELL row。
     * 要建立 source-only row，讓前站 td 顯示前站圖片與 sub table。
     */
    if (point.group === "source") {
      return [normalizeSourcePointAsTableRow(point)];
    }
  
    /*
     * 點 CELL AOI 圓點：
     * 如果完整 CELL group row 沒被 exact match 到，就建立 cell-only row。
     */
    if (point.group === "cell_aoi") {
      return [normalizeCellPointAsTableRow(point)];
    }
  
    /*
     * 點 same_point 星號理論上應該會找到 exactRows。
     * 找不到就建立 same-point row fallback。
     */
    if (point.group === "same_point") {
      return [normalizeSamePointGroupAsTableRow(point.raw || point, point.index || 1)];
    }
  
    return [];
  }
  
  function normalizeSourcePointAsTableRow(point) {
    const raw = point?.raw || point || {};
    const source = raw.source || raw.source_info || raw.display || {};
  
    const sourceInfo = hasObjectData(raw.source_info)
      ? raw.source_info
      : hasObjectData(source)
        ? source
        : {
            source_defect_uid: point.source_defect_uid || raw.source_defect_uid || "",
            source_op_id: point.source_op_id || raw.source_op_id || source.source_op_id || source.display?.source_op_id || "",
            defect_code: point.defect_code || raw.source_defect_code || raw.defect_code || source.defect_code || source.display?.defect_code || "",
            defect_size: point.defect_size || raw.source_defect_size || raw.defect_size || source.defect_size || source.display?.defect_size || "",
            trans_x: point.source_x || point.x || raw.source_x || raw.x || "",
            trans_y: point.source_y || point.y || raw.source_y || raw.y || "",
            img_url_path: point.source_img || raw.source_img || raw.img || source.img_url_path || ""
          };
  
    const sourceImg =
      point.source_img ||
      raw.source_img ||
      raw.img ||
      source.img_url_path ||
      raw.source_info?.img_url_path ||
      "";
  
    return normalizeDefectRow({
      index: point.index || raw.index || 1,
      group: "source",
      match: false,
  
      cell_img: "",
      cell_info: {},
      cell_defect_uid: "",
      cell_defect_code: "",
      cell_defect_size: "",
      cell_x: "",
      cell_y: "",
  
      source_img: sourceImg,
      source_info: sourceInfo,
      source_defect_uid:
        point.source_defect_uid ||
        raw.source_defect_uid ||
        source.source_defect_uid ||
        "",
      source_op_id:
        point.source_op_id ||
        raw.source_op_id ||
        source.source_op_id ||
        source.display?.source_op_id ||
        "",
      source_defect_code:
        point.defect_code ||
        raw.source_defect_code ||
        raw.defect_code ||
        source.defect_code ||
        source.display?.defect_code ||
        "",
      source_defect_size:
        point.defect_size ||
        raw.source_defect_size ||
        raw.defect_size ||
        source.defect_size ||
        source.display?.defect_size ||
        "",
      source_x: point.source_x || point.x || raw.source_x || raw.x || "",
      source_y: point.source_y || point.y || raw.source_y || raw.y || "",
  
      distance: "",
      dx: "",
      dy: ""
    });
  }
  
  function normalizeCellPointAsTableRow(point) {
  const raw = point?.raw || point || {};
  const cell = raw.cell || raw.cell_info || {};

  const cellInfo = hasObjectData(raw.cell_info)
    ? raw.cell_info
    : hasObjectData(cell)
      ? cell
      : {
          cell_defect_uid: point.cell_defect_uid || raw.cell_defect_uid || "",
          defect_code: point.defect_code || raw.cell_defect_code || raw.defect_code || "",
          defect_size: point.defect_size || raw.cell_defect_size || raw.defect_size || "",
          trans_x: point.cell_x || point.x || raw.cell_x || raw.x || "",
          trans_y: point.cell_y || point.y || raw.cell_y || raw.y || "",
          img_url_path: point.cell_img || raw.cell_img || raw.img || ""
        };

  return normalizeDefectRow({
    index: point.index || raw.index || 1,
    group: "cell_aoi",
    match: false,

    cell_img: point.cell_img || raw.cell_img || raw.img || cell.img_url_path || "",
    cell_info: cellInfo,
    cell_defect_uid: point.cell_defect_uid || raw.cell_defect_uid || cell.cell_defect_uid || "",
    cell_defect_code: point.defect_code || raw.cell_defect_code || raw.defect_code || cell.defect_code || "",
    cell_defect_size: point.defect_size || raw.cell_defect_size || raw.defect_size || cell.defect_size || "",
    cell_x: point.cell_x || point.x || raw.cell_x || raw.x || cell.trans_x || "",
    cell_y: point.cell_y || point.y || raw.cell_y || raw.y || cell.trans_y || "",

    source_img: "",
    source_info: {},
    source_defect_uid: "",
    source_defect_code: "",
    source_defect_size: "",
    source_x: "",
    source_y: "",

    distance: "",
    dx: "",
    dy: ""
  });
}


  function buildMergedDefectRows(row) {
    if (!row) return [];
  
    MOD.State.ensureRowDefectContainers(row);
  
    const cellGroupRows = Array.isArray(row.defectGroups?.cell_aoi)
      ? row.defectGroups.cell_aoi
      : [];
  
    const samePointRows = Array.isArray(row.defectGroups?.same_point)
      ? row.defectGroups.same_point
      : [];
  
    let baseRows = [];
  
    /*
     * 完整 CELL defect group 已載入時：
     * defect table 的母體就是完整 CELL defect。
     */
    if (cellGroupRows.length) {
      baseRows = cellGroupRows.map(function (d, idx) {
        const normalized = normalizeDefectRow(d, idx + 1);
  
        // 預設先當未同點，後面再用 samePointRows merge source 資訊。
        normalized.match = false;
        normalized.source_img = "";
        normalized.source_info = {};
        normalized.source_defect_uid = "";
        normalized.source_defect_code = "";
        normalized.source_defect_size = "";
        normalized.source_x = "";
        normalized.source_y = "";
        normalized.distance = "";
        normalized.dx = "";
        normalized.dy = "";
  
        return normalized;
      });
    } else if (Array.isArray(row.defects) && row.defects.length) {
      /*
       * 完整 CELL group 還沒回來時：
       * 先用 /detail 回傳的 point_detail rows。
       */
      baseRows = row.defects.map(function (d, idx) {
        return normalizeDefectRow(d, idx + 1);
      });
    } else if (samePointRows.length) {
      baseRows = samePointRows.map(function (d, idx) {
        return normalizeSamePointGroupAsTableRow(d, idx + 1);
      });
    }
  
    if (!baseRows.length) return [];
  
    if (!samePointRows.length) {
      return baseRows;
    }
  
    const sameIndex = buildSamePointIndex(samePointRows);
  
    return baseRows.map(function (defect, idx) {
      const d = normalizeDefectRow(defect, idx + 1);
      const same = findMatchedSamePoint(d, sameIndex);
  
      if (!same) {
        /*
         * 未同點 CELL defect：
         * CELL 欄位完整顯示，
         * Source 欄位保持空，前端會顯示 dash。
         */
        d.match = false;
        d.source_img = "";
        d.source_info = {};
        d.source_defect_uid = "";
        d.source_defect_code = "";
        d.source_defect_size = "";
        d.source_x = "";
        d.source_y = "";
        d.distance = "";
        d.dx = "";
        d.dy = "";
        return d;
      }
  
      const sourceInfo = getInfoObject(same, "source_info");
      const cellInfo = getInfoObject(same, "cell_info");
  
      d.match = true;
  
      d.source_img =
        same.source_img ||
        same.source?.img_url_path ||
        same.source_info?.img_url_path ||
        d.source_img ||
        "";
  
      d.source_info = hasObjectData(sourceInfo)
        ? sourceInfo
        : d.source_info || {};
  
      d.source_defect_uid =
        same.source_defect_uid ||
        same.source?.source_defect_uid ||
        same.source_info?.source_defect_uid ||
        d.source_defect_uid ||
        "";
  
      d.source_op_id =
        same.source_op_id ||
        same.source?.source_op_id ||
        same.source_info?.source_op_id ||
        same.source_info?.display?.source_op_id ||
        d.source_op_id ||
        "";
  
      d.source_defect_code =
        same.source_defect_code ||
        same.source?.defect_code ||
        same.source_info?.defect_code ||
        same.source_info?.display?.defect_code ||
        d.source_defect_code ||
        "";
  
      d.source_defect_size =
        same.source_defect_size ||
        same.source?.defect_size ||
        same.source_info?.defect_size ||
        same.source_info?.display?.defect_size ||
        d.source_defect_size ||
        "";
  
      d.source_x =
        same.source_x ??
        same.source_info?.trans_x ??
        same.source_info?.display?.trans_x ??
        d.source_x ??
        "";
  
      d.source_y =
        same.source_y ??
        same.source_info?.trans_y ??
        same.source_info?.display?.trans_y ??
        d.source_y ??
        "";
  
      d.dx = same.dx ?? same.match?.dx ?? d.dx ?? "";
      d.dy = same.dy ?? same.match?.dy ?? d.dy ?? "";
      d.distance = same.distance ?? same.match?.distance ?? d.distance ?? "";
  
      if (!hasObjectData(d.cell_info) && hasObjectData(cellInfo)) {
        d.cell_info = cellInfo;
      }
  
      return d;
    });
  }

  function normalizeDefectRow(d, index) {
    const out = Object.assign({}, d || {});
  
    out.index = out.index || index;
  
    out.cell_info = getInfoObject(out, "cell_info");
    out.source_info = getInfoObject(out, "source_info");
  
    out.cell_defect_uid =
      out.cell_defect_uid ||
      out.uid ||
      out.defect_uid ||
      out.cell_info?.cell_defect_uid ||
      "";
  
    out.cell_x = out.cell_x ?? out.x ?? out.cell_info?.trans_x ?? "";
    out.cell_y = out.cell_y ?? out.y ?? out.cell_info?.trans_y ?? "";
  
    out.cell_defect_code =
      out.cell_defect_code ||
      out.defect_code ||
      out.cell_info?.defect_code ||
      "";
  
    out.cell_defect_size =
      out.cell_defect_size ||
      out.defect_size ||
      out.cell_info?.defect_size ||
      "";
  
    out.cell_img =
      out.cell_img ||
      out.aoi_img ||
      out.img ||
      out.cell_info?.img_url_path ||
      out.cell_info?.cell_img_url_path ||
      "";
  
    if (!hasObjectData(out.cell_info)) {
      out.cell_info = {
        cell_defect_uid: out.cell_defect_uid || "",
        chip_id: out.chip_id || "",
        defect_code: out.cell_defect_code || "",
        retype_def_code: out.retype_def_code || "",
        defect_size: out.cell_defect_size || "",
        ori_x: out.ori_x ?? "",
        ori_y: out.ori_y ?? "",
        trans_x: out.cell_x ?? "",
        trans_y: out.cell_y ?? "",
        image_name: out.image_name || "",
        img_url_path: out.cell_img || ""
      };
    }
  
    out.source_img =
      out.source_img ||
      out.array_img ||
      out.cf_img ||
      out.source_info?.img_url_path ||
      "";
  
    out.source_defect_uid =
      out.source_defect_uid ||
      out.source_info?.source_defect_uid ||
      "";
  
    out.source_op_id =
      out.source_op_id ||
      out.source_info?.source_op_id ||
      out.source_info?.display?.source_op_id ||
      "";
  
    out.source_defect_code =
      out.source_defect_code ||
      out.source_info?.defect_code ||
      out.source_info?.display?.defect_code ||
      "";
  
    out.source_defect_size =
      out.source_defect_size ||
      out.source_info?.defect_size ||
      out.source_info?.display?.defect_size ||
      "";
  
    out.source_x =
      out.source_x ??
      out.source_info?.trans_x ??
      out.source_info?.display?.trans_x ??
      "";
  
    out.source_y =
      out.source_y ??
      out.source_info?.trans_y ??
      out.source_info?.display?.trans_y ??
      "";
  
    out.defect_size = out.defect_size || out.cell_defect_size || out.source_defect_size || "";
    out.group = out.group || "";
  
    out.defect_size = out.defect_size || out.cell_defect_size || out.source_defect_size || "";
    out.group = out.group || "";

    out.match = Boolean(
      out.match ||
      out.is_same_point ||
      out.same_point ||
      out.matched
    );

    return out;
  }

  function normalizeSamePointGroupAsTableRow(d, index) {
    const raw = d || {};
    const cell = raw.cell || {};
    const source = raw.source || {};
    const match = raw.match || {};

    const cellInfo = raw.cell_info && typeof raw.cell_info === "object"
      ? raw.cell_info
      : cell;

    const sourceInfo = raw.source_info && typeof raw.source_info === "object"
      ? raw.source_info
      : source;

    return normalizeDefectRow({
      index: raw.index || index,
      match: true,
      cell_defect_uid: raw.cell_defect_uid || cell.cell_defect_uid || "",
      source_defect_uid: raw.source_defect_uid || source.source_defect_uid || "",
      source_op_id: raw.source_op_id || source.source_op_id || source.display?.source_op_id || "",
      cell_img: raw.cell_img || cell.img_url_path || "",
      source_img: raw.source_img || source.img_url_path || "",
      cell_info: cellInfo,
      source_info: sourceInfo,
      cell_defect_code: raw.cell_defect_code || cell.defect_code || raw.defect_code || "",
      source_defect_code: raw.source_defect_code || source.defect_code || source.display?.defect_code || "",
      cell_defect_size: raw.cell_defect_size || cell.defect_size || raw.defect_size || "",
      source_defect_size: raw.source_defect_size || source.defect_size || source.display?.defect_size || "",
      cell_x: raw.cell_x ?? raw.x ?? cell.trans_x ?? "",
      cell_y: raw.cell_y ?? raw.y ?? cell.trans_y ?? "",
      source_x: raw.source_x ?? source.trans_x ?? source.display?.trans_x ?? "",
      source_y: raw.source_y ?? source.trans_y ?? source.display?.trans_y ?? "",
      distance: raw.distance ?? match.distance ?? "",
      dx: raw.dx ?? match.dx ?? "",
      dy: raw.dy ?? match.dy ?? "",
      defect_size: raw.defect_size || raw.cell_defect_size || cell.defect_size || source.defect_size || "",
      group: raw.group || "same_point"
    }, index);
  }

  function buildSamePointIndex(samePointRows) {
    const index = {
      byCellUid: new Map(),
      byCellSignature: new Map()
    };

    samePointRows.forEach(function (row, idx) {
      const same = normalizeSamePointGroupAsTableRow(row, idx + 1);

      if (same.cell_defect_uid) {
        index.byCellUid.set(String(same.cell_defect_uid), same);
      }

      const sig = buildCellSignature(same);
      if (sig) {
        index.byCellSignature.set(sig, same);
      }
    });

    return index;
  }

  function findMatchedSamePoint(defect, sameIndex) {
    if (!defect || !sameIndex) return null;

    if (defect.cell_defect_uid) {
      const byUid = sameIndex.byCellUid.get(String(defect.cell_defect_uid));
      if (byUid) return byUid;
    }

    const sig = buildCellSignature(defect);
    if (sig) {
      const bySig = sameIndex.byCellSignature.get(sig);
      if (bySig) return bySig;
    }

    return null;
  }

  function buildCellSignature(d) {
    if (!d) return "";

    const x = normalizeNumberForKey(d.cell_x ?? d.x ?? d.cell_info?.trans_x);
    const y = normalizeNumberForKey(d.cell_y ?? d.y ?? d.cell_info?.trans_y);
    const code = String(d.cell_defect_code || d.defect_code || "").trim().toUpperCase();
    const size = String(d.cell_defect_size || d.defect_size || "").trim().toUpperCase();

    if (!x && !y && !code && !size) return "";

    return [x, y, code, size].join("|");
  }

  function normalizeNumberForKey(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "";
    return String(Math.round(n * 1000) / 1000);
  }

  function findBestRowByMapPoint(rows, point) {
    if (!rows || !rows.length || !point) return null;

    const px = Number(point.x);
    const py = Number(point.y);

    if (!Number.isFinite(px) || !Number.isFinite(py)) return null;

    let best = null;
    let bestDist = Infinity;

    rows.forEach(function (r) {
      const x = Number(r.cell_x ?? r.x);
      const y = Number(r.cell_y ?? r.y);

      if (!Number.isFinite(x) || !Number.isFinite(y)) return;

      const dx = x - px;
      const dy = y - py;
      const dist = Math.sqrt(dx * dx + dy * dy);

      if (dist < bestDist) {
        bestDist = dist;
        best = r;
      }
    });

    return best;
  }

  function isFocusedDefect(defect, point) {
    if (!defect || !point) return false;
  
    const pRaw = point.raw || point;
    const pointGroup = point.group || pRaw.group || "";
  
    if (pointGroup === "source") {
      const pointSourceUid =
        pRaw.source_defect_uid ||
        pRaw.source?.source_defect_uid ||
        pRaw.source_info?.source_defect_uid ||
        point.source_defect_uid ||
        "";
  
      if (pointSourceUid && defect.source_defect_uid) {
        return String(defect.source_defect_uid) === String(pointSourceUid);
      }
  
      const px = Number(point.source_x ?? point.x ?? pRaw.source_x ?? pRaw.x);
      const py = Number(point.source_y ?? point.y ?? pRaw.source_y ?? pRaw.y);
      const dx = Number(defect.source_x);
      const dy = Number(defect.source_y);
  
      if (
        Number.isFinite(px) &&
        Number.isFinite(py) &&
        Number.isFinite(dx) &&
        Number.isFinite(dy)
      ) {
        return Math.abs(px - dx) <= 0.001 && Math.abs(py - dy) <= 0.001;
      }
  
      return false;
    }
  
    const pointCellUid =
      pRaw.cell_defect_uid ||
      pRaw.cell?.cell_defect_uid ||
      pRaw.cell_info?.cell_defect_uid ||
      point.cell_defect_uid ||
      "";
  
    if (pointCellUid && defect.cell_defect_uid) {
      return String(defect.cell_defect_uid) === String(pointCellUid);
    }
  
    const pointSig = buildCellSignature(normalizeSamePointGroupAsTableRow(pRaw, point.index || 1));
    const defectSig = buildCellSignature(defect);
  
    if (pointSig && defectSig && pointSig === defectSig) {
      return true;
    }
  
    const px = Number(point.cell_x ?? point.x ?? pRaw.cell_x ?? pRaw.x);
    const py = Number(point.cell_y ?? point.y ?? pRaw.cell_y ?? pRaw.y);
    const dx = Number(defect.cell_x ?? defect.x);
    const dy = Number(defect.cell_y ?? defect.y);
  
    if (
      Number.isFinite(px) &&
      Number.isFinite(py) &&
      Number.isFinite(dx) &&
      Number.isFinite(dy)
    ) {
      return Math.abs(px - dx) <= 0.001 && Math.abs(py - dy) <= 0.001;
    }
  
    return false;
  }

  function getColumns(row) {
    if (MOD.State && MOD.State.getDefectTableColumnsByRow) {
      return MOD.State.getDefectTableColumnsByRow(row) || fallbackColumns();
    }

    return fallbackColumns();
  }

  function fallbackColumns() {
    return [
      { type: "text", key: "index", label: "索引" },
      { type: "match", key: "match", label: "Match" },
      {
        type: "image_info",
        key: "cell_img",
        label: "CELL AOI",
        imageKey: "cell_img",
        infoKey: "cell_info",
        subColumnsKey: "cell_aoi"
      },
      {
        type: "image_info",
        key: "source_img",
        label: "Source",
        imageKey: "source_img",
        infoKey: "source_info",
        subColumnsBySourceOpKey: "source",
        sourceOpKey: "source_op_id"
      },
      { type: "text", key: "cell_defect_code", label: "CELL Code" },
      { type: "text", key: "source_defect_code", label: "Source Code" },
      { type: "text", key: "cell_defect_size", label: "CELL Size" },
      { type: "text", key: "source_defect_size", label: "Source Size" },
      { type: "text", key: "distance", label: "Distance" },
      { type: "text", key: "dx", label: "dx" },
      { type: "text", key: "dy", label: "dy" }
    ];
  }

  function createCell(defect, col, index) {
    const type = col.type || "text";

    if (type === "image_info") return createImageInfoCell(defect, col);
    if (type === "image") return createImageCell(defect, col);
    if (type === "match") return createMatchCell(defect, col);

    return createTextCell(defect, col, index);
  }

  function createTextCell(defect, col, index) {
    const span = document.createElement("span");
    span.className = "cell-aoi-to-array-defect-text";

    let value = getValue(defect, col.key);

    if (col.key === "index" && (value == null || value === "")) {
      value = index + 1;
    }

    if (isCoordKey(col.key)) {
      value = formatCoord(value);
      span.classList.add("cell-aoi-to-array-mono");
    }

    if (isDistanceKey(col.key)) {
      value = formatDistance(value);
      span.classList.add("cell-aoi-to-array-mono");
    }

    if (isSizeKey(col.key)) {
      span.classList.add(`cell-aoi-to-array-defect-size-${String(value || "O").toUpperCase()}`);
    }

    span.textContent = value == null || value === "" ? "-" : String(value);
    span.title = span.textContent;

    return span;
  }

  function createImageInfoCell(defect, col) {
    const wrap = document.createElement("div");
    wrap.className = "cell-aoi-to-array-image-info-cell";

    const imageKey = col.imageKey || col.key;
    const infoKey = col.infoKey || "";

    const info = getInfoObject(defect, infoKey);
    const imgUrl = getImageUrl(defect, imageKey);

    const isSourceCell = infoKey === "source_info";

    if (isSourceCell && !imgUrl && !hasObjectData(info)) {
      const empty = document.createElement("span");
      empty.className = "cell-aoi-to-array-defect-img-empty";
      empty.textContent = "-";
      wrap.appendChild(empty);
      return wrap;
    }

    const imgBox = document.createElement("div");
    imgBox.className = "cell-aoi-to-array-image-info-imgbox";

    if (imgUrl) {
      const img = document.createElement("img");
      img.className = "cell-aoi-to-array-defect-img";
      img.src = imgUrl;
      img.alt = col.label || imageKey || "image";
      img.loading = "lazy";
      img.title = imgUrl;

      img.onerror = function () {
        img.style.display = "none";

        if (!imgBox.querySelector(".cell-aoi-to-array-defect-img-empty")) {
          const fallback = document.createElement("span");
          fallback.className = "cell-aoi-to-array-defect-img-empty";
          fallback.textContent = "IMG ERR";
          imgBox.appendChild(fallback);
        }
      };

      img.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        showImagePreview(imgUrl);
      });

      imgBox.appendChild(img);
    } else {
      const emptyImg = document.createElement("span");
      emptyImg.className = "cell-aoi-to-array-defect-img-empty";
      emptyImg.textContent = "-";
      imgBox.appendChild(emptyImg);
    }

    const tableBox = document.createElement("div");
    tableBox.className = "cell-aoi-to-array-image-info-tablebox";

    const subColumns = getSubColumns(defect, col);

    if (subColumns.length && hasObjectData(info)) {
      tableBox.appendChild(createSubTablePairGrid(info, subColumns));
    } else {
      const emptyInfo = document.createElement("div");
      emptyInfo.className = "cell-aoi-to-array-image-info-empty";
      emptyInfo.textContent = "-";
      tableBox.appendChild(emptyInfo);
    }

    wrap.appendChild(imgBox);
    wrap.appendChild(tableBox);

    return wrap;
  }

  function getInfoObject(defect, infoKey) {
    if (!defect || !infoKey) return {};

    const value = defect[infoKey];

    if (value && typeof value === "object" && !Array.isArray(value)) {
      return value;
    }

    return {};
  }

  function getSubColumns(defect, col) {
    const featureCfg =
      MOD.State && MOD.State.getFeatureConfig
        ? MOD.State.getFeatureConfig()
        : {};

    const subMap = featureCfg.defectDetailSubColumns || {};

    if (col.subColumnsKey) {
      const cols = subMap[col.subColumnsKey];
      return Array.isArray(cols) ? cols : [];
    }

    if (col.subColumnsBySourceOpKey) {
      const sourceMap = subMap[col.subColumnsBySourceOpKey] || {};
      const sourceOpKey = col.sourceOpKey || "source_op_id";
      const sourceOp = String(defect?.[sourceOpKey] || "").trim().toUpperCase();

      if (Array.isArray(sourceMap[sourceOp])) {
        return sourceMap[sourceOp];
      }

      const foundKey = Object.keys(sourceMap).find(function (k) {
        return String(k).trim().toUpperCase() === sourceOp;
      });

      return foundKey && Array.isArray(sourceMap[foundKey])
        ? sourceMap[foundKey]
        : [];
    }

    return [];
  }

  function createSubTablePairGrid(info, columns) {
    const wrap = document.createElement("div");
    wrap.className = "cell-aoi-to-array-image-info-pairgrid";

    const validCols = (columns || []).filter(function (col) {
      return col && col.key;
    });

    for (let i = 0; i < validCols.length; i += 2) {
      const col1 = validCols[i];
      const col2 = validCols[i + 1];

      const labelRow = document.createElement("div");
      labelRow.className = "cell-aoi-to-array-image-info-pairgrid-row label-row";

      const valueRow = document.createElement("div");
      valueRow.className = "cell-aoi-to-array-image-info-pairgrid-row value-row";

      const label1 = document.createElement("div");
      label1.className = "cell-aoi-to-array-image-info-pairgrid-label";
      label1.textContent = col1.label || col1.key;

      const value1 = document.createElement("div");
      value1.className = "cell-aoi-to-array-image-info-pairgrid-value";
      value1.textContent = formatSubTableValue(info, col1.key);
      value1.title = value1.textContent;

      labelRow.appendChild(label1);
      valueRow.appendChild(value1);

      const label2 = document.createElement("div");
      label2.className = "cell-aoi-to-array-image-info-pairgrid-label";
      label2.textContent = col2 ? (col2.label || col2.key) : "";

      const value2 = document.createElement("div");
      value2.className = "cell-aoi-to-array-image-info-pairgrid-value";
      value2.textContent = col2 ? formatSubTableValue(info, col2.key) : "";
      value2.title = value2.textContent;

      labelRow.appendChild(label2);
      valueRow.appendChild(value2);

      wrap.appendChild(labelRow);
      wrap.appendChild(valueRow);
    }

    return wrap;
  }

  function formatSubTableValue(info, key) {
    let value = getNestedValue(info, key);

    if (isCoordKey(key)) return formatCoord(value);
    if (isDistanceKey(key)) return formatDistance(value);

    return formatInfoValue(value);
  }

  function getNestedValue(obj, key) {
    if (!obj || !key) return "";

    if (Object.prototype.hasOwnProperty.call(obj, key)) return obj[key];
    if (obj.display && Object.prototype.hasOwnProperty.call(obj.display, key)) return obj.display[key];
    if (obj.raw && Object.prototype.hasOwnProperty.call(obj.raw, key)) return obj.raw[key];

    return "";
  }

  function formatInfoValue(value) {
    if (value == null || value === "") return "-";

    const s = String(value).trim();

    if (!s || ["none", "nan", "nat", "<na>", "null"].includes(s.toLowerCase())) {
      return "-";
    }

    return s;
  }

  function hasObjectData(obj) {
    if (!obj || typeof obj !== "object") return false;

    return Object.keys(obj).some(function (key) {
      const v = obj[key];

      if (v == null) return false;

      if (typeof v === "object") {
        return hasObjectData(v);
      }

      const s = String(v).trim();
      return s && !["none", "nan", "nat", "<na>", "null"].includes(s.toLowerCase());
    });
  }

  function createImageCell(defect, col) {
    const wrap = document.createElement("div");
    wrap.className = "cell-aoi-to-array-defect-img-cell";

    const url = getImageUrl(defect, col.key);

    if (!url) {
      const empty = document.createElement("span");
      empty.className = "cell-aoi-to-array-defect-img-empty";
      empty.textContent = "-";
      wrap.appendChild(empty);
      return wrap;
    }

    const img = document.createElement("img");
    img.className = "cell-aoi-to-array-defect-img";
    img.src = url;
    img.alt = col.label || col.key || "image";
    img.loading = "lazy";
    img.title = url;

    img.onerror = function () {
      img.style.display = "none";

      if (!wrap.querySelector(".cell-aoi-to-array-defect-img-empty")) {
        const fallback = document.createElement("span");
        fallback.className = "cell-aoi-to-array-defect-img-empty";
        fallback.textContent = "IMG ERR";
        wrap.appendChild(fallback);
      }
    };

    img.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      showImagePreview(url);
    });


    wrap.appendChild(img);

    return wrap;
  }

  function createMatchCell(defect, col) {
    const span = document.createElement("span");
    const matched = Boolean(getValue(defect, col.key));

    span.className = matched
      ? "cell-aoi-to-array-match-badge matched"
      : "cell-aoi-to-array-match-badge unmatched";

    span.textContent = matched ? "同點" : "未同點";

    return span;
  }

  function getValue(defect, key) {
    if (!defect || !key) return "";

    if (Object.prototype.hasOwnProperty.call(defect, key)) {
      return defect[key];
    }

    const alias = {
      aoi_img: "cell_img",
      array_img: "source_img",
      cf_img: "source_img",
      array_x: "source_x",
      array_y: "source_y",
      cf_x: "source_x",
      cf_y: "source_y",
      defect_code: "cell_defect_code",
      defect_size: "cell_defect_size"
    };

    if (alias[key] && Object.prototype.hasOwnProperty.call(defect, alias[key])) {
      return defect[alias[key]];
    }

    return "";
  }

  function getImageUrl(defect, key) {
    const direct = getValue(defect, key);
    if (direct) return normalizeUrl(direct);

    if (key === "cell_img" || key === "aoi_img") {
      return normalizeUrl(defect.cell_img || defect.aoi_img || defect.img || defect.cell_info?.img_url_path || "");
    }

    if (key === "source_img" || key === "array_img" || key === "cf_img") {
      return normalizeUrl(defect.source_img || defect.array_img || defect.cf_img || defect.source_info?.img_url_path || "");
    }

    if (key === "img") {
      return normalizeUrl(defect.img || defect.cell_img || defect.source_img || "");
    }

    return "";
  }

  function normalizeUrl(value) {
    const url = String(value || "").trim();

    if (!url || ["none", "nan", "nat", "<na>", "null"].includes(url.toLowerCase())) {
      return "";
    }

    return url;
  }

  function showImagePreview(url) {
    const imgUrl = normalizeUrl(url);
    if (!imgUrl) return;

    let overlay = document.getElementById("cell-aoi-to-array-image-preview-overlay");

    if (!overlay) {
      overlay = document.createElement("div");
      overlay.id = "cell-aoi-to-array-image-preview-overlay";
      overlay.className = "cell-aoi-to-array-image-preview-overlay";

      const box = document.createElement("div");
      box.className = "cell-aoi-to-array-image-preview-box";

      const img = document.createElement("img");
      img.className = "cell-aoi-to-array-image-preview-img";
      img.alt = "defect preview";

      const caption = document.createElement("div");
      caption.className = "cell-aoi-to-array-image-preview-caption";

      box.appendChild(img);
      box.appendChild(caption);
      overlay.appendChild(box);

      // 點空白背景關閉
      overlay.addEventListener("click", function () {
        hideImagePreview();
      });

      // 點圖片本身不要關閉
      box.addEventListener("click", function (ev) {
        ev.stopPropagation();
      });

      document.addEventListener("keydown", function (ev) {
        if (ev.key === "Escape") {
          hideImagePreview();
        }
      });

      document.body.appendChild(overlay);
    }

    const img = overlay.querySelector(".cell-aoi-to-array-image-preview-img");
    const caption = overlay.querySelector(".cell-aoi-to-array-image-preview-caption");

    if (img) {
      img.src = imgUrl;
    }

    if (caption) {
      caption.textContent = imgUrl;
      caption.title = imgUrl;
    }

    overlay.style.display = "flex";
    document.body.classList.add("cell-aoi-to-array-image-preview-open");
  }

  function hideImagePreview() {
    const overlay = document.getElementById("cell-aoi-to-array-image-preview-overlay");
    if (!overlay) return;

    const img = overlay.querySelector(".cell-aoi-to-array-image-preview-img");
    if (img) {
      img.removeAttribute("src");
    }

    overlay.style.display = "none";
    document.body.classList.remove("cell-aoi-to-array-image-preview-open");
  }

  function isCoordKey(key) {
    return [
      "x",
      "y",
      "ori_x",
      "ori_y",
      "trans_x",
      "trans_y",
      "cell_x",
      "cell_y",
      "source_x",
      "source_y",
      "array_x",
      "array_y",
      "cf_x",
      "cf_y"
    ].includes(key);
  }

  function isDistanceKey(key) {
    return ["distance", "dx", "dy", "offset"].includes(key);
  }

  function isSizeKey(key) {
    return [
      "defect_size",
      "cell_defect_size",
      "source_defect_size",
      "array_defect_size",
      "cf_defect_size"
    ].includes(key);
  }

  function formatCoord(value) {
    const n = Number(value);

    if (!Number.isFinite(n)) {
      return value == null || value === "" ? "-" : String(value);
    }

    return Math.round(n).toLocaleString();
  }

  function formatDistance(value) {
    const n = Number(value);

    if (!Number.isFinite(n)) {
      return value == null || value === "" ? "-" : String(value);
    }

    return String(Math.round(n * 1000) / 1000);
  }

  function updateCount(row) {
    const { dom } = MOD.State || {};
    const rows = getRows(row);

    if (dom && dom.defectListCount) {
      dom.defectListCount.textContent = `Total ${rows.length} defects`;
    }

    if (dom && dom.defectListWrap) {
      dom.defectListWrap.style.display = row ? "" : "none";
    }

    updateReturnButtonState();
  }
})();
