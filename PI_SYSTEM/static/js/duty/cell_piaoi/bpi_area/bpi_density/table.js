// static/js/bpi_area/bpi_density/table.js
// BPI Density Table
//
// 功能：
// - 預設顯示：依 Filter UI 過濾後的 rows
// - 可由 chart 互動 rows 覆寫顯示
// - 表頭依 ParamDict.bpiDensity.hourlyTable
// - 依 ParamDict.bpiDensity.hourlyTable_key_group.main_group 做 rowspan 合併
// - 支援 group 級別 comment/action/editor/modify_time 顯示與編輯
// - 逐片展開 glass_list + glass_size_detail

(function () {
  const MOD = (window.AOI_BPI_DENSITY = window.AOI_BPI_DENSITY || {});
  MOD.Table = MOD.Table || {};

  const API = window.AOI_BPI_DENSITY_API;
  const SH = MOD.Shared || {};
  const $ = (sel, root = document) => root.querySelector(sel);

  // =============================================================================
  // Helpers
  // =============================================================================
  const isObj = (o) => o && typeof o === "object" && !Array.isArray(o);
  const toArr = (x) => (Array.isArray(x) ? x : []);

  function safeStr(v) {
    return v == null ? "" : String(v);
  }

  function safeNum(v) {
    const x = Number(v);
    return Number.isFinite(x) ? x : 0;
  }

  function parseDateTimeToTime(v) {
    const s = safeStr(v).trim();
    if (!s) return NaN;

    const d = new Date(s.replace(" ", "T"));
    return d instanceof Date && !isNaN(d) ? d.getTime() : NaN;
  }

  function parseGlassList(val) {
    if (SH.parseGlassList) return SH.parseGlassList(val);

    if (val == null) return [];
    if (Array.isArray(val)) return val.map(safeStr).map(s => s.trim()).filter(Boolean);

    return String(val).split(",").map(s => s.trim()).filter(Boolean);
  }

  function parseGlassSizeDetail(val) {
    if (SH.parseGlassSizeDetail) return SH.parseGlassSizeDetail(val);

    if (!val) return {};
    if (isObj(val)) return val;

    if (typeof val === "string") {
      try {
        const o = JSON.parse(val);
        return isObj(o) ? o : {};
      } catch {
        return {};
      }
    }

    return {};
  }

  function formatSizeDetail(detail) {
    const d = isObj(detail) ? detail : {};
    const S = safeNum(d.S);
    const M = safeNum(d.M);
    const L = safeNum(d.L);
    const O = safeNum(d.O);
    const T = d.T != null ? safeNum(d.T) : (S + M + L + O);

    return `S:${S} M:${M} L:${L} O:${O} T:${T}`;
  }

  function getPerGlassDetail(row) {
    const gid = row?.__glassId;
    if (!gid) return null;

    const gsd = row?.__glassSizeDetailObj || parseGlassSizeDetail(row?.glass_size_detail);
    if (!gsd || !isObj(gsd)) return null;

    const hit = gsd[gid];
    return isObj(hit) ? hit : null;
  }

  function getPerGlassTotalT(row) {
    const detail = getPerGlassDetail(row);
    if (!detail) return null;

    const S = safeNum(detail.S);
    const M = safeNum(detail.M);
    const L = safeNum(detail.L);
    const O = safeNum(detail.O);

    return detail.T != null ? safeNum(detail.T) : (S + M + L + O);
  }

  function getBpiDensityConfig(paramDict) {
    const pd = paramDict || MOD.state?.paramDict || {};
    return pd.bpiDensity || pd || {};
  }

  function getHourlyTable(paramDict) {
    const cfg = getBpiDensityConfig(paramDict);
    return cfg.hourlyTable || {};
  }

  function getHourlyKeyGroup(paramDict) {
    const cfg = getBpiDensityConfig(paramDict);
    return cfg.hourlyTable_key_group || {};
  }

  // =============================================================================
  // 編輯欄位
  // =============================================================================
  let lastExpanded = null;
  let lastColDict = null;
  let lastParamDict = null;

  function getNowStr() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");

    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }

  function getEditor(row) {
    return (window.editor != null && String(window.editor).trim() !== "")
      ? String(window.editor)
      : ((row?.editor || row?.Editor) || "");
  }

  const BPI_KEY_FIELDS = [
    "scan_hour",
    "aoi",
    "model",
    "cassette_id",
    "glass_side",
    "recipe_id"
  ];

  function buildApiRowForBPI(row) {
    const out = {};
    BPI_KEY_FIELDS.forEach((k) => {
      out[k] = row?.[k] || "";
    });
    return out;
  }

  function matchByKey(a, b) {
    for (const k of BPI_KEY_FIELDS) {
      if (String(a?.[k] ?? "") !== String(b?.[k] ?? "")) return false;
    }
    return true;
  }

  function patchStateRowsBPI(sampleRow, patch) {
    const stateRows = MOD?.state?.rows;
    if (!Array.isArray(stateRows) || !stateRows.length) return;

    for (const r of stateRows) {
      if (matchByKey(r, sampleRow)) {
        Object.assign(r, patch);
      }
    }
  }

  function patchExpandedGroup(expanded, groupKey, patch) {
    if (!expanded || !Array.isArray(expanded.rows)) return;

    expanded.rows.forEach((rr) => {
      if (String(rr.__groupKey || "") === String(groupKey || "")) {
        Object.assign(rr, patch);
      }
    });
  }

  // =============================================================================
  // Modal
  // =============================================================================
  function createModalBase(titleText) {
    const overlay = document.createElement("div");
    overlay.className = "bpi-density-modal-backdrop";
    overlay.style.position = "fixed";
    overlay.style.inset = "0";
    overlay.style.background = "rgba(0,0,0,0.45)";
    overlay.style.display = "flex";
    overlay.style.alignItems = "center";
    overlay.style.justifyContent = "center";
    overlay.style.zIndex = "9999";

    const box = document.createElement("div");
    box.className = "bpi-density-modal";
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
    body.className = "bpi-density-modal-body";
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

  function openViewModalForGroup(row) {
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
    boxC.textContent = safeStr(row.comment);
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
    boxA.textContent = safeStr(row.action);
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
    const e = row.editor || row.Editor || "";
    const mt = row.modify_time || "";
    footer.textContent = e && mt
      ? `編輯: ${e}  時間: ${mt}`
      : `編輯: 預設  時間: ${mt}`;
    footer.style.marginTop = "12px";
    footer.style.textAlign = "center";
    footer.style.fontSize = "11px";
    footer.style.whiteSpace = "pre-line";

    box.appendChild(footer);
  }

  function openEditModalForGroup(row) {
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

    let commentOriginal = safeStr(row.comment);

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

    let actionOriginal = safeStr(row.action);

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
      const apiRow = buildApiRowForBPI(row);

      const patch = {
        ...(commentChanged ? { comment: newComment } : {}),
        ...(actionChanged ? { action: newAction } : {}),
        editor: newEditor,
        modify_time: newModifyTime
      };

      if (lastExpanded && row.__groupKey) {
        patchExpandedGroup(lastExpanded, row.__groupKey, patch);
        renderBody(lastExpanded, lastColDict);
      }

      patchStateRowsBPI(row, patch);

      try {
        if (!API?.CommentEditor) {
          alert("儲存失敗: API.CommentEditor 不存在");
          return;
        }

        const results = [];

        if (commentChanged) {
          const payloadC = {
            system: "bpi_density",
            mode: "comment",
            row: apiRow,
            comment: newComment,
            editor: newEditor,
            modify_time: newModifyTime
          };

          console.log("[BPI Density] group save(comment):", payloadC);
          const respC = await API.CommentEditor(payloadC);
          results.push({ mode: "comment", resp: respC });
        }

        if (actionChanged) {
          const payloadA = {
            system: "bpi_density",
            mode: "action",
            row: apiRow,
            action: newAction,
            editor: newEditor,
            modify_time: newModifyTime
          };

          console.log("[BPI Density] group save(action):", payloadA);
          const respA = await API.CommentEditor(payloadA);
          results.push({ mode: "action", resp: respA });
        }

        const allOk = results.every(x => x?.resp?.ok === true);

        if (allOk) {
          if (commentChanged) commentOriginal = newComment;
          if (actionChanged) actionOriginal = newAction;
          alert("儲存成功");
        } else {
          alert("儲存完成，但後端回應不是 ok=true");
          console.warn("[BPI Density] save results:", results);
        }
      } catch (err) {
        console.error("[BPI Density] save error:", err);
        alert("儲存失敗：" + (err?.message || String(err)));
      }
    });
  }

  // =============================================================================
  // Return button
  // =============================================================================
  function ensureReturnButton() {
    const head = $("#aoi-bpi-density-table-wrap .aoi-bpi-density-table-head");
    if (!head) return null;

    let btn = head.querySelector("#aoi_bpi_density_tableReturn");

    if (!btn) {
      btn = document.createElement("button");
      btn.id = "aoi_bpi_density_tableReturn";
      btn.className = "btn btn-xs btn-secondary";
      btn.textContent = "Return";
      btn.style.float = "right";
      btn.style.marginLeft = "auto";

      head.appendChild(btn);

      btn.addEventListener("click", () => {
        const rows = window.AOI_BPI_DENSITY?.getFiltered?.() || [];
        const pd = window.AOI_BPI_DENSITY?.state?.paramDict || {};
        MOD.Table.render(rows, pd);
        showReturn(false);
      });
    }

    return btn;
  }

  function showReturn(show) {
    const btn = ensureReturnButton();
    if (!btn) return;

    btn.style.display = show ? "" : "none";
    btn.disabled = !show;
  }

  // =============================================================================
  // Group config
  // =============================================================================
  function getGroupConf(paramDict) {
    const tg = getHourlyKeyGroup(paramDict);

    const mainKeys = Array.isArray(tg.main_group)
      ? tg.main_group.slice()
      : [];

    const uniCols = Array.isArray(tg.uni_col)
      ? tg.uni_col.slice()
      : [];

    const uniSet = new Set([
      ...uniCols,
      "glass_list",
      "glass_size_detail"
    ]);

    const ckd = getBpiDensityConfig(paramDict).chartKeyDict || {};
    const down = Array.isArray(ckd.down) ? ckd.down : [];
    const timeKeys = new Set(["scan_hour", ...down]);

    return { mainKeys, uniSet, timeKeys };
  }

  // =============================================================================
  // Normalize rows
  // =============================================================================
  function normalizeRowsForTable(rows) {
    return (rows || []).map(r => {
      if (!r || typeof r !== "object") return r;

      const out = { ...r };

      const gl = (Array.isArray(out.__glassList) && out.__glassList.length)
        ? out.__glassList
        : (Array.isArray(out.glass_list) && out.glass_list.length)
          ? out.glass_list
          : parseGlassList(out.glass_list);

      out.__glassList = gl;

      const gsd = isObj(out.__glassSizeDetailObj)
        ? out.__glassSizeDetailObj
        : isObj(out.glass_size_detail_obj)
          ? out.glass_size_detail_obj
          : parseGlassSizeDetail(out.glass_size_detail);

      out.__glassSizeDetailObj = gsd;

      return out;
    });
  }

  // =============================================================================
  // Expand rows by glass
  // =============================================================================
  function expandRowsByGlass(rows, paramDict) {
    const { mainKeys, uniSet, timeKeys } = getGroupConf(paramDict);
    const out = [];
    const normRows = normalizeRowsForTable(rows || []);

    normRows.forEach((r) => {
      const gList = Array.isArray(r.__glassList)
        ? r.__glassList
        : parseGlassList(r.glass_list);

      const gsdObj = r.__glassSizeDetailObj || parseGlassSizeDetail(r.glass_size_detail);

      const sig = mainKeys.map(k => k + ":" + safeStr(r[k])).join("|");

      (gList.length ? gList : [""]).forEach((gid, idx) => {
        out.push({
          __groupKey: sig,
          __groupIndex: idx,
          __glassId: gid,
          __glassSizeDetailObj: gsdObj,
          ...r,
          glass_list: gid
        });
      });
    });

    out.sort((a, b) => {
      for (const k of mainKeys) {
        const av = a[k] ?? "";
        const bv = b[k] ?? "";

        if (timeKeys.has(k)) {
          const ta = parseDateTimeToTime(av);
          const tb = parseDateTimeToTime(bv);

          if (!isNaN(ta) && !isNaN(tb) && ta !== tb) return ta - tb;
          if (safeStr(av) < safeStr(bv)) return -1;
          if (safeStr(av) > safeStr(bv)) return 1;
        } else {
          if (safeStr(av) < safeStr(bv)) return -1;
          if (safeStr(av) > safeStr(bv)) return 1;
        }
      }

      return safeStr(a.glass_list).localeCompare(safeStr(b.glass_list));
    });

    return { rows: out, mainKeys, uniSet, timeKeys };
  }

  // =============================================================================
  // Header
  // =============================================================================
  function renderHeader(colDict) {
    const thead = $("#aoi-bpi-density-table thead");
    if (!thead) return;

    thead.innerHTML = "";

    const tr = document.createElement("tr");

    const thAct = document.createElement("th");
    thAct.className = "col-group-actions";
    thAct.textContent = "";
    thAct.style.width = "70px";
    tr.appendChild(thAct);

    const cols = Object.keys(colDict || {});
    cols.forEach((key) => {
      const th = document.createElement("th");
      th.className = `col-${key}`;
      th.textContent = String(colDict[key] || key);
      th.style.whiteSpace = "nowrap";
      th.style.overflow = "hidden";
      th.style.textOverflow = "ellipsis";
      tr.appendChild(th);
    });

    thead.appendChild(tr);
  }

  // =============================================================================
  // Body
  // =============================================================================
  function renderBody(expanded, colDict) {
    const tbody = $("#aoi-bpi-density-table tbody");
    if (!tbody) return;

    tbody.innerHTML = "";

    const { rows: rowsEx, mainKeys, uniSet } = expanded || {};
    const colKeys = Object.keys(colDict || {});

    if (!rowsEx || !rowsEx.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = Math.max(1, colKeys.length + 1);
      td.className = "muted";
      td.textContent = "（無資料）";
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    const groupRowspanAtIndex = new Array(rowsEx.length).fill(0);

    let last = "";
    let start = 0;

    rowsEx.forEach((r, i) => {
      const sig = String(r.__groupKey || "");

      if (i === 0) {
        last = sig;
        start = 0;
      } else if (sig !== last) {
        groupRowspanAtIndex[start] = i - start;
        start = i;
        last = sig;
      }

      if (i === rowsEx.length - 1) {
        groupRowspanAtIndex[start] = rowsEx.length - start;
      }
    });

    for (let i = 0; i < rowsEx.length; i++) {
      const row = rowsEx[i];
      const isHead = groupRowspanAtIndex[i] > 0;

      const tr = document.createElement("tr");
      tr.className = "main-row";

      if (isHead) {
        const tdAct = document.createElement("td");
        tdAct.className = "col-group-actions";
        tdAct.rowSpan = groupRowspanAtIndex[i];
        tdAct.style.verticalAlign = "top";
        tdAct.style.whiteSpace = "nowrap";

        const wrap = document.createElement("div");
        wrap.style.display = "flex";
        wrap.style.flexDirection = "column";
        wrap.style.gap = "4px";

        const btnEdit = document.createElement("button");
        btnEdit.type = "button";
        btnEdit.className = "btn btn-xs";
        btnEdit.textContent = "編輯";
        btnEdit.addEventListener("click", (ev) => {
          ev.stopPropagation();
          openEditModalForGroup(row);
        });

        const btnShow = document.createElement("button");
        btnShow.type = "button";
        btnShow.className = "btn btn-xs btn-secondary";
        btnShow.textContent = "顯示";
        btnShow.addEventListener("click", (ev) => {
          ev.stopPropagation();
          openViewModalForGroup(row);
        });

        wrap.appendChild(btnEdit);
        wrap.appendChild(btnShow);
        tdAct.appendChild(wrap);
        tr.appendChild(tdAct);
      }

      for (const key of colKeys) {
        const isGroupable = mainKeys.includes(key);
        if (isGroupable && !isHead) continue;

        let val = "";

        if (key === "glass_list") {
          val = safeStr(row.__glassId || row.glass_list);
        } else if (key === "glass_size_detail") {
          const detail = getPerGlassDetail(row);
          val = detail ? formatSizeDetail(detail) : "";
        } else if (key === "total_defect_count") {
          const t = getPerGlassTotalT(row);
          val = t != null ? String(t) : safeStr(row[key]);
        } else {
          val = row[key] != null ? row[key] : "";
        }

        const td = document.createElement("td");
        td.className = `col-${key}`;
        td.style.whiteSpace = "nowrap";
        td.style.overflow = "hidden";
        td.style.textOverflow = "ellipsis";

        if (isGroupable && isHead) {
          td.classList.add("merged");
          td.rowSpan = groupRowspanAtIndex[i];
        }

        if (/count$/.test(key) || ["glass_count", "total_defect_count", "density"].includes(key)) {
          td.style.textAlign = "right";
        }

        td.textContent = val == null ? "" : String(val);
        tr.appendChild(td);
      }

      tbody.appendChild(tr);
    }
  }

  // =============================================================================
  // Public render
  // =============================================================================
  MOD.Table.render = function (rows, paramDict) {
    const colDict = getHourlyTable(paramDict);

    let useColDict;

    if (isObj(colDict) && Object.keys(colDict).length) {
      useColDict = colDict;
    } else {
      const sample = toArr(rows)[0] || {};
      const dyn = {};
      Object.keys(sample).forEach((k) => {
        dyn[k] = k;
      });
      useColDict = dyn;
    }

    renderHeader(useColDict);

    const expanded = expandRowsByGlass(rows || [], paramDict || {});
    lastExpanded = expanded;
    lastColDict = useColDict;
    lastParamDict = paramDict || {};

    renderBody(expanded, useColDict);
    showReturn(false);
  };

  MOD.Table.showRows = function (rows, paramDict) {
    const colDict = getHourlyTable(paramDict);

    let useColDict;

    if (isObj(colDict) && Object.keys(colDict).length) {
      useColDict = colDict;
    } else {
      const sample = toArr(rows)[0] || {};
      const dyn = {};
      Object.keys(sample).forEach((k) => {
        dyn[k] = k;
      });
      useColDict = dyn;
    }

    renderHeader(useColDict);

    const expanded = expandRowsByGlass(rows || [], paramDict || {});
    lastExpanded = expanded;
    lastColDict = useColDict;
    lastParamDict = paramDict || {};

    renderBody(expanded, useColDict);
    showReturn(true);
  };
})();