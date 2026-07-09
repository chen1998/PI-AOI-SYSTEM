// static/js/bpi_area/bpi_same_point/table.js
// BPI/API Same Point Table
//
// 功能：
// - 預設顯示：依 PISpot / UPI + filter + date 查回的 TableRows
// - 點 chart bar 後：顯示 selected row，並出現 return 按鈕
// - return：回到全部 TableRows
// - 表頭依 config.table_columns 動態產生
// - 支援 shared_left / compare / shared_right / size_summary / meta 分組
// - compare 欄位：BPI/API 上下對照顯示
// - comment/action/editor/modify_time 以 group row 的「顯示 / 編輯」modal 操作
// - 儲存 comment/action 後 patch state.tableRows / chartRows / rows / filteredRows / selectedRow
// - Same Point editor key 由後端 Config.manual_key_cols / editor_match_keys 決定，不再寫死在前端

(function () {
  const MOD = (window.BPI_SAME_POINT = window.BPI_SAME_POINT || {});
  const Table = (MOD.Table = MOD.Table || {});
  const API = MOD.API;

  // =============================================================================
  // Basic helpers
  // =============================================================================
  function $(id) {
    return document.getElementById(id);
  }

  function safeStr(v) {
    return v == null ? "" : String(v);
  }

  function safeTrim(v) {
    return safeStr(v).trim();
  }

  function isObj(o) {
    return o && typeof o === "object" && !Array.isArray(o);
  }

  function toArr(x) {
    return Array.isArray(x) ? x : [];
  }

  function firstNonEmpty(...vals) {
    for (const v of vals) {
      const s = safeTrim(v);
      if (s) return s;
    }
    return "";
  }

  function getConfig(opts) {
    return (
      opts?.config ||
      MOD.state?.config ||
      MOD.state?.payload?.ParamDict?.Config ||
      {}
    );
  }

  function getNowStr() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");

    return (
      `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
      `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
    );
  }

  function getEditor(row) {
    return window.editor != null && String(window.editor).trim() !== ""
      ? String(window.editor).trim()
      : safeTrim(row?.editor || row?.Editor || "");
  }

  function formatValue(key, value, col) {
    if (value == null || value === "") return "";

    if (key === "offset_um" || key === "default_offset_um") {
      const suffix = col?.suffix || "";
      return `${safeStr(value)}${suffix}`;
    }

    return safeStr(value);
  }

  // =============================================================================
  // Same Point key fields - from backend config
  // =============================================================================
  function getSamePointManualKeyFields(opts) {
    const cfg = getConfig(opts);

    const manualKeyCols = toArr(cfg?.manual_key_cols);
    if (manualKeyCols.length) return manualKeyCols;

    const editorMatchKeys = toArr(cfg?.editor_match_keys);
    if (editorMatchKeys.length) return editorMatchKeys;

    const defectMapManualKeys = toArr(cfg?.defect_map?.manual_key_cols);
    if (defectMapManualKeys.length) return defectMapManualKeys;

    const frontManualKeys = toArr(cfg?.bpiSamePoint?.manual_key_cols);
    if (frontManualKeys.length) return frontManualKeys;

    return ["model", "glass_side", "glass_id", "tab", "api_aoi", "api_recipe_id"];
  }

  function getSamePointPatchKeyFields(opts) {
    // 前端 patch 狀態應該跟 editor manual key 一致。
    return getSamePointManualKeyFields(opts);
  }

  function getCurrentSubPage() {
    return firstNonEmpty(
      MOD.state?.subPage,
      MOD.state?.payload?.ParamDict?.Config?.sub_page,
      MOD.state?.payload?.ParamDict?.Config?.same_point_page,
      getConfig()?.sub_page,
      getConfig()?.same_point_page
    );
  }

  function inferTabFromRow(row) {
    const tab = safeTrim(row?.tab);
    if (tab) return tab;

    const sub = safeTrim(getCurrentSubPage());
    if (sub) return sub;

    const apiAoi = safeTrim(row?.api_aoi);
    const recipe = safeTrim(row?.api_recipe_id);
    const head = recipe.slice(0, 1);

    if (apiAoi === "aoi200") {
      if (head === "0" || head === "1") return "PISpot";
      if (head === "2" || head === "3") return "UPI";
    }

    if (apiAoi === "aoi100" || apiAoi === "aoi300") {
      return apiAoi;
    }

    return "";
  }

  function getRowValueForKey(row, key) {
    if (!row) return "";

    if (key === "tab") {
      return row.tab || inferTabFromRow(row);
    }

    return row[key] ?? "";
  }

  function buildApiRowForSamePoint(row) {
    const out = {};
    const keys = getSamePointManualKeyFields();

    keys.forEach((k) => {
      out[k] = getRowValueForKey(row, k);
    });

    // tab 是 manual key 必要欄位，前端先補一層，後端 editor.py 也會再 fallback。
    out.tab = out.tab || inferTabFromRow(row);

    // table resolve 用；不是 WHERE key。
    out._pair_source_table = row?._pair_source_table ?? "";
    out.scan_hour = row?.scan_hour ?? "";

    // 保留常用欄位，方便後端 fallback / debug。
    out.api_scan_time = row?.api_scan_time ?? "";
    out.bpi_scan_time = row?.bpi_scan_time ?? "";

    out.api_aoi = row?.api_aoi ?? out.api_aoi ?? "";
    out.api_recipe_id = row?.api_recipe_id ?? out.api_recipe_id ?? "";

    out.bpi_aoi = row?.bpi_aoi ?? "";
    out.bpi_recipe_id = row?.bpi_recipe_id ?? "";

    out.model = row?.model ?? out.model ?? "";
    out.glass_side = row?.glass_side ?? out.glass_side ?? "";
    out.glass_id = row?.glass_id ?? out.glass_id ?? "";

    return out;
  }

  function samePointKeyOf(row) {
    const keys = getSamePointPatchKeyFields();

    return keys
      .map((k) => `${k}:${safeStr(getRowValueForKey(row, k))}`)
      .join("|");
  }

  function matchByKey(a, b) {
    const keys = getSamePointPatchKeyFields();

    for (const k of keys) {
      const av = safeStr(getRowValueForKey(a, k));
      const bv = safeStr(getRowValueForKey(b, k));

      if (av !== bv) return false;
    }

    return true;
  }

  function patchArrayRows(rows, sampleRow, patch) {
    if (!Array.isArray(rows)) return;

    rows.forEach((r) => {
      if (matchByKey(r, sampleRow)) {
        Object.assign(r, patch);
      }
    });
  }

  function patchAllStateRows(sampleRow, patch) {
    const st = MOD.state || {};

    patchArrayRows(st.tableRows, sampleRow, patch);
    patchArrayRows(st.chartRows, sampleRow, patch);
    patchArrayRows(st.rows, sampleRow, patch);
    patchArrayRows(st.filteredRows, sampleRow, patch);

    if (st.selectedRow && matchByKey(st.selectedRow, sampleRow)) {
      Object.assign(st.selectedRow, patch);
    }
  }

  // =============================================================================
  // Column config
  // =============================================================================
  const DEFAULT_GROUPED_COLUMNS = {
    shared_left: [
      { key: "scan_hour", label: "Hourly" },
      { key: "model", label: "Model" },
      { key: "glass_side", label: "side" },
      { key: "glass_id", label: "glass" },
    ],

    compare: [
      { label: "AOI", bpi_key: "bpi_aoi", api_key: "api_aoi" },
      { label: "scan time", bpi_key: "bpi_scan_time", api_key: "api_scan_time" },
      { label: "recipe", bpi_key: "bpi_recipe_id", api_key: "api_recipe_id" },
      { label: "defect", bpi_key: "bpi_defect_count", api_key: "api_defect_count" },
    ],

    shared_right: [
      { key: "offset_um", label: "offset", suffix: "um" },
      { key: "matched_pair_count", label: "same point" },
    ],

    size_summary: [],

    meta: [
      { key: "comment", label: "comment" },
      { key: "action", label: "action" },
      { key: "editor", label: "Editor" },
      { key: "modify_time", label: "modify_time" },
    ],
  };

  function isGroupedColumns(cols) {
    return (
      cols &&
      typeof cols === "object" &&
      !Array.isArray(cols) &&
      (
        Array.isArray(cols.shared_left) ||
        Array.isArray(cols.compare) ||
        Array.isArray(cols.shared_right) ||
        Array.isArray(cols.size_summary) ||
        Array.isArray(cols.meta)
      )
    );
  }

  function normalizeGroupedColumns(raw) {
    if (!isGroupedColumns(raw)) {
      return DEFAULT_GROUPED_COLUMNS;
    }

    return {
      shared_left: Array.isArray(raw.shared_left) ? raw.shared_left : [],
      compare: Array.isArray(raw.compare) ? raw.compare : [],
      shared_right: Array.isArray(raw.shared_right) ? raw.shared_right : [],
      size_summary: Array.isArray(raw.size_summary) ? raw.size_summary : [],
      meta: Array.isArray(raw.meta) ? raw.meta : [],
    };
  }

  function getGroupedColumns(opts) {
    const cfg = getConfig(opts);
    return normalizeGroupedColumns(cfg.table_columns);
  }

  function getFlatRenderColumns(grouped) {
    return [
      ...grouped.shared_left.map((c) => ({ ...c, type: "shared" })),
      ...grouped.compare.map((c) => ({ ...c, type: "compare" })),
      ...grouped.shared_right.map((c) => ({ ...c, type: "shared" })),
      ...grouped.size_summary.map((c) => ({ ...c, type: "shared", className: "size-summary" })),
      // meta 不直接顯示為欄位，改成左側顯示/編輯 modal。
    ];
  }

  // =============================================================================
  // Modal
  // =============================================================================
  function createModalBase(titleText) {
    const overlay = document.createElement("div");
    overlay.className = "bpi-same-point-modal-backdrop";
    overlay.style.position = "fixed";
    overlay.style.inset = "0";
    overlay.style.background = "rgba(0,0,0,0.45)";
    overlay.style.display = "flex";
    overlay.style.alignItems = "center";
    overlay.style.justifyContent = "center";
    overlay.style.zIndex = "9999";

    const box = document.createElement("div");
    box.className = "bpi-same-point-modal";
    box.style.minWidth = "640px";
    box.style.maxWidth = "80vw";
    box.style.maxHeight = "80vh";
    box.style.background = "#1f2933";
    box.style.color = "#f9fafb";
    box.style.borderRadius = "8px";
    box.style.boxShadow = "0 12px 30px rgba(0,0,0,0.5)";
    box.style.display = "flex";
    box.style.flexDirection = "column";
    box.style.padding = "16px 20px";
    box.style.fontSize = "13px";

    const header = document.createElement("div");
    header.style.display = "flex";
    header.style.alignItems = "center";
    header.style.justifyContent = "space-between";
    header.style.marginBottom = "8px";

    const title = document.createElement("div");
    title.textContent = titleText || "";
    title.style.fontWeight = "600";

    const btnClose = document.createElement("button");
    btnClose.type = "button";
    btnClose.textContent = "×";
    btnClose.style.border = "none";
    btnClose.style.background = "transparent";
    btnClose.style.color = "inherit";
    btnClose.style.fontSize = "18px";
    btnClose.style.cursor = "pointer";
    btnClose.style.lineHeight = "1";

    header.appendChild(title);
    header.appendChild(btnClose);

    const body = document.createElement("div");
    body.className = "bpi-same-point-modal-body";
    body.style.display = "flex";
    body.style.gap = "16px";
    body.style.marginTop = "8px";
    body.style.overflow = "auto";

    box.appendChild(header);
    box.appendChild(body);
    overlay.appendChild(box);

    function close() {
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    }

    btnClose.addEventListener("click", (ev) => {
      ev.stopPropagation();
      close();
    });

    overlay.addEventListener("click", (ev) => {
      if (ev.target === overlay) close();
    });

    document.body.appendChild(overlay);

    return { overlay, box, body, close };
  }

  function openViewModalForRow(row) {
    const { body, box } = createModalBase("comment / action");

    const left = document.createElement("div");
    const right = document.createElement("div");

    [left, right].forEach((col) => {
      col.style.flex = "1 1 0";
      col.style.display = "flex";
      col.style.flexDirection = "column";
      col.style.gap = "6px";
    });

    const lblC = document.createElement("div");
    lblC.textContent = "Comment";
    lblC.style.fontWeight = "600";

    const boxC = document.createElement("div");
    boxC.textContent = safeStr(row?.comment);
    boxC.style.whiteSpace = "pre-wrap";
    boxC.style.borderRadius = "4px";
    boxC.style.border = "1px solid #4b5563";
    boxC.style.background = "#111827";
    boxC.style.padding = "6px 8px";
    boxC.style.minHeight = "80px";

    left.appendChild(lblC);
    left.appendChild(boxC);

    const lblA = document.createElement("div");
    lblA.textContent = "Action";
    lblA.style.fontWeight = "600";

    const boxA = document.createElement("div");
    boxA.textContent = safeStr(row?.action);
    boxA.style.whiteSpace = "pre-wrap";
    boxA.style.borderRadius = "4px";
    boxA.style.border = "1px solid #4b5563";
    boxA.style.background = "#111827";
    boxA.style.padding = "6px 8px";
    boxA.style.minHeight = "80px";

    right.appendChild(lblA);
    right.appendChild(boxA);

    body.appendChild(left);
    body.appendChild(right);

    const footer = document.createElement("div");
    const e = row?.editor || row?.Editor || "";
    const mt = row?.modify_time || "";

    footer.textContent = e && mt
      ? `編輯: ${e}  時間: ${mt}`
      : `編輯: ${e || "預設"}  時間: ${mt}`;

    footer.style.marginTop = "12px";
    footer.style.textAlign = "center";
    footer.style.fontSize = "11px";
    footer.style.whiteSpace = "pre-line";

    box.appendChild(footer);
  }

  function openEditModalForRow(row) {
    const { body } = createModalBase("comment / action");

    const left = document.createElement("div");
    const right = document.createElement("div");

    [left, right].forEach((col) => {
      col.style.flex = "1 1 0";
      col.style.display = "flex";
      col.style.flexDirection = "column";
      col.style.gap = "6px";
    });

    const lblC = document.createElement("div");
    lblC.textContent = "Comment";
    lblC.style.fontWeight = "600";

    let commentOriginal = safeStr(row?.comment);

    const taC = document.createElement("textarea");
    taC.value = commentOriginal;
    taC.rows = 6;
    taC.style.width = "100%";
    taC.style.resize = "vertical";
    taC.style.minHeight = "80px";
    taC.style.borderRadius = "4px";
    taC.style.border = "1px solid #4b5563";
    taC.style.background = "#111827";
    taC.style.color = "inherit";
    taC.style.padding = "6px 8px";
    taC.style.fontFamily = "inherit";
    taC.style.fontSize = "12px";

    left.appendChild(lblC);
    left.appendChild(taC);

    const lblA = document.createElement("div");
    lblA.textContent = "Action";
    lblA.style.fontWeight = "600";

    let actionOriginal = safeStr(row?.action);

    const taA = document.createElement("textarea");
    taA.value = actionOriginal;
    taA.rows = 6;
    taA.style.width = "100%";
    taA.style.resize = "vertical";
    taA.style.minHeight = "80px";
    taA.style.borderRadius = "4px";
    taA.style.border = "1px solid #4b5563";
    taA.style.background = "#111827";
    taA.style.color = "inherit";
    taA.style.padding = "6px 8px";
    taA.style.fontFamily = "inherit";
    taA.style.fontSize = "12px";

    right.appendChild(lblA);
    right.appendChild(taA);

    body.appendChild(left);
    body.appendChild(right);

    const footerActions = document.createElement("div");
    footerActions.style.display = "flex";
    footerActions.style.justifyContent = "flex-end";
    footerActions.style.gap = "8px";
    footerActions.style.marginTop = "10px";

    const btnSave = document.createElement("button");
    btnSave.type = "button";
    btnSave.className = "btn btn-xs";
    btnSave.textContent = "儲存";

    const btnCancel = document.createElement("button");
    btnCancel.type = "button";
    btnCancel.className = "btn btn-xs btn-secondary";
    btnCancel.textContent = "取消";

    footerActions.appendChild(btnCancel);
    footerActions.appendChild(btnSave);
    body.appendChild(footerActions);

    btnCancel.addEventListener("click", (ev) => {
      ev.stopPropagation();
      taC.value = commentOriginal;
      taA.value = actionOriginal;
    });

    btnSave.addEventListener("click", async (ev) => {
      ev.stopPropagation();

      const newComment = safeStr(taC.value);
      const newAction = safeStr(taA.value);

      const commentChanged = newComment !== commentOriginal;
      const actionChanged = newAction !== actionOriginal;

      if (!commentChanged && !actionChanged) {
        alert("沒有變更內容，無需儲存。");
        return;
      }

      const newModifyTime = getNowStr();
      const newEditor = getEditor(row);
      const apiRow = buildApiRowForSamePoint(row);

      const patch = {
        ...(commentChanged ? { comment: newComment } : {}),
        ...(actionChanged ? { action: newAction } : {}),
        editor: newEditor,
        modify_time: newModifyTime,
      };

      // 先 patch 前端狀態，讓使用者立即看到變更。
      patchAllStateRows(row, patch);

      // 如果目前是 selected mode，更新 selected row table。
      if (MOD.state?.tableMode === "selected" && MOD.state?.selectedRow) {
        Table.render([MOD.state.selectedRow], {
          mode: "selected",
          config: MOD.state.config,
        });
      } else {
        Table.render(MOD.state?.tableRows || [], {
          mode: "all",
          config: MOD.state?.config,
        });
      }

      try {
        if (!API?.CommentEditor) {
          alert("儲存失敗: API.CommentEditor 不存在");
          return;
        }

        const results = [];

        if (commentChanged) {
          const payloadC = {
            system: "bpi_same_point",
            mode: "comment",
            row: apiRow,
            comment: newComment,
            editor: newEditor,
            modify_time: newModifyTime,
          };

          console.log("[BPI Same Point] save(comment):", payloadC);
          const respC = await API.CommentEditor(payloadC);
          results.push({ mode: "comment", resp: respC });
        }

        if (actionChanged) {
          const payloadA = {
            system: "bpi_same_point",
            mode: "action",
            row: apiRow,
            action: newAction,
            editor: newEditor,
            modify_time: newModifyTime,
          };

          console.log("[BPI Same Point] save(action):", payloadA);
          const respA = await API.CommentEditor(payloadA);
          results.push({ mode: "action", resp: respA });
        }

        const allOk = results.every((x) => x?.resp?.ok === true);

        if (allOk) {
          if (commentChanged) commentOriginal = newComment;
          if (actionChanged) actionOriginal = newAction;
          alert("儲存成功");
        } else {
          alert("儲存完成，但後端回應不是 ok=true");
          console.warn("[BPI Same Point] save results:", results);
        }
      } catch (err) {
        console.error("[BPI Same Point] save error:", err);
        alert("儲存失敗：" + (err?.message || String(err)));
      }
    });
  }

  // =============================================================================
  // Table head return button
  // =============================================================================
  function ensureTableHead(mode, rowCount) {
    const wrap = $("bpi-same-point-table-wrap");
    if (!wrap) return;

    const head = wrap.querySelector(".table-head");
    if (!head) return;

    head.classList.add("bpi-same-point-table-head-flex");

    let title = head.querySelector(".bpi-same-point-table-title");
    if (!title) {
      const oldText = (head.textContent || "Same Point Table").trim();
      head.textContent = "";

      title = document.createElement("span");
      title.className = "bpi-same-point-table-title";
      title.textContent = oldText || "Same Point Table";
      head.appendChild(title);
    }

    let meta = head.querySelector("#bpi-same-point-table-meta");
    if (!meta) {
      meta = document.createElement("span");
      meta.id = "bpi-same-point-table-meta";
      meta.className = "muted bpi-same-point-table-meta";
      head.appendChild(meta);
    }

    meta.textContent = mode === "selected"
      ? "Selected row"
      : `All rows: ${rowCount}`;

    let btn = head.querySelector("#bpi-same-point-table-return");
    if (!btn) {
      btn = document.createElement("button");
      btn.id = "bpi-same-point-table-return";
      btn.type = "button";
      btn.className = "btn btn-xs btn-secondary";
      btn.textContent = "Return";

      btn.addEventListener("click", () => {
        if (typeof MOD.returnTable === "function") {
          MOD.returnTable();
          return;
        }

        const rows =
          MOD.state?.tableRows ||
          MOD.state?.filteredRows ||
          MOD.state?.rows ||
          [];

        MOD.state.selectedRow = null;
        MOD.state.tableMode = "all";

        Table.render(rows, {
          mode: "all",
          config: MOD.state?.config,
        });

        MOD.DefectMap?.clear?.();
      });

      head.appendChild(btn);
    }

    btn.style.display = mode === "selected" ? "" : "none";
  }

  // =============================================================================
  // Cell builders
  // =============================================================================
  function makeCompareCell(row, col) {
    const wrap = document.createElement("div");
    wrap.className = "bpi-same-point-compare-cell";

    const bpiLine = document.createElement("div");
    bpiLine.className = "bpi-same-point-compare-line bpi-line";

    const bpiTag = document.createElement("span");
    bpiTag.className = "bpi-same-point-compare-tag";
    bpiTag.textContent = "BPI";

    const bpiVal = document.createElement("span");
    bpiVal.className = "bpi-same-point-compare-value";
    bpiVal.textContent = formatValue(col.bpi_key, row?.[col.bpi_key], col);

    bpiLine.appendChild(bpiTag);
    bpiLine.appendChild(bpiVal);

    const apiLine = document.createElement("div");
    apiLine.className = "bpi-same-point-compare-line api-line";

    const apiTag = document.createElement("span");
    apiTag.className = "bpi-same-point-compare-tag";
    apiTag.textContent = "API";

    const apiVal = document.createElement("span");
    apiVal.className = "bpi-same-point-compare-value";
    apiVal.textContent = formatValue(col.api_key, row?.[col.api_key], col);

    apiLine.appendChild(apiTag);
    apiLine.appendChild(apiVal);

    wrap.appendChild(bpiLine);
    wrap.appendChild(apiLine);

    return wrap;
  }

  function makeSharedCell(row, col) {
    const div = document.createElement("div");
    div.className = "bpi-same-point-shared-cell";

    if (col.className) {
      div.classList.add(String(col.className));
    }

    div.textContent = formatValue(col.key, row?.[col.key], col);
    return div;
  }

  function makeActionCell(row) {
    const wrap = document.createElement("div");
    wrap.className = "bpi-same-point-row-actions";

    const btnEdit = document.createElement("button");
    btnEdit.type = "button";
    btnEdit.className = "btn btn-xs";
    btnEdit.textContent = "編輯";
    btnEdit.addEventListener("click", (ev) => {
      ev.stopPropagation();
      openEditModalForRow(row);
    });

    const btnShow = document.createElement("button");
    btnShow.type = "button";
    btnShow.className = "btn btn-xs btn-secondary";
    btnShow.textContent = "顯示";
    btnShow.addEventListener("click", (ev) => {
      ev.stopPropagation();
      openViewModalForRow(row);
    });

    wrap.appendChild(btnEdit);
    wrap.appendChild(btnShow);

    return wrap;
  }

  // =============================================================================
  // Header / Body render
  // =============================================================================
  function renderHeader(thead, columns) {
    thead.innerHTML = "";

    const trh = document.createElement("tr");

    const thAct = document.createElement("th");
    thAct.className = "bpi-same-point-actions-th";
    thAct.textContent = "";
    thAct.style.width = "72px";
    trh.appendChild(thAct);

    columns.forEach((col) => {
      const th = document.createElement("th");
      const label = col.label || col.key || "";
      th.textContent = label;
      th.dataset.colLabel = label;

      if (col.type === "compare") {
        th.classList.add("bpi-same-point-compare-th");
      }

      if (col.className) {
        th.classList.add(String(col.className));
      }

      trh.appendChild(th);
    });

    thead.appendChild(trh);
  }

  function renderEmpty(tbody, colSpan, mode) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");

    td.colSpan = colSpan;
    td.className = "muted";
    td.textContent = mode === "selected"
      ? "此 chart bar 沒有對應資料"
      : "目前時間區間沒有 Same Point 資料";

    tr.appendChild(td);
    tbody.appendChild(tr);
  }

  function renderBody(tbody, rows, columns, mode) {
    tbody.innerHTML = "";

    const arr = Array.isArray(rows) ? rows : [];

    if (!arr.length) {
      renderEmpty(tbody, columns.length + 1, mode);
      return;
    }

    arr.forEach((row) => {
      const tr = document.createElement("tr");

      if (mode === "selected") {
        tr.classList.add("is-selected");
      }

      tr.dataset.samePointKey = samePointKeyOf(row);

      const tdAct = document.createElement("td");
      tdAct.className = "bpi-same-point-actions-td";
      tdAct.appendChild(makeActionCell(row));
      tr.appendChild(tdAct);

      columns.forEach((col) => {
        const td = document.createElement("td");
        const label = col.label || col.key || "";
        td.dataset.colLabel = label;

        if (col.type === "compare") {
          td.classList.add("bpi-same-point-compare-td");
          td.appendChild(makeCompareCell(row, col));
        } else {
          td.appendChild(makeSharedCell(row, col));
        }

        if (col.className) {
          td.classList.add(String(col.className));
        }

        tr.appendChild(td);
      });

      tbody.appendChild(tr);
    });
  }

  // =============================================================================
  // Public render
  // =============================================================================
  Table.render = function (rows, opts) {
    const table = $("bpi-same-point-table");
    if (!table) return;

    const thead = table.querySelector("thead");
    const tbody = table.querySelector("tbody");
    if (!thead || !tbody) return;

    const options = opts || {};
    const mode = options.mode || MOD.state?.tableMode || "all";
    const arr = Array.isArray(rows) ? rows : [];

    const grouped = getGroupedColumns(options);
    const columns = getFlatRenderColumns(grouped);

    ensureTableHead(mode, arr.length);
    renderHeader(thead, columns);
    renderBody(tbody, arr, columns, mode);
  };

  Table.renderDefault = function () {
    const rows =
      MOD.state?.tableRows ||
      MOD.state?.filteredRows ||
      MOD.state?.rows ||
      [];

    MOD.state.selectedRow = null;
    MOD.state.tableMode = "all";

    Table.render(rows, {
      mode: "all",
      config: MOD.state?.config,
    });
  };

  // Debug helpers
  Table.getSamePointManualKeyFields = getSamePointManualKeyFields;
  Table.buildApiRowForSamePoint = buildApiRowForSamePoint;
})();