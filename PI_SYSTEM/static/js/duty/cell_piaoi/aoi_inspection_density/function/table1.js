// static/js/aoi_inspection_density/function/table1.js
// 功能：
// - 預設顯示：依 Filter（UI）後的 rows
// - 由 chart 互動（柱/點/xAxis/yAxis）丟進來的 rows 覆寫顯示
// - 表頭依 ParamDict['hourlyTable']；rowspan 合併同 group
// - 支援新資料結構的 glass_size_detail JSON 字串
// - 在「Analysis Table」右側自動插入 Return + checkbox（Only glass with defect）
(function () {
  const MOD = (window.AOI_INSPECTION = window.AOI_INSPECTION || {});
  const API = window.AOI_INSPECTION_API;
  MOD.Table = MOD.Table || {};

  const $ = (sel, root = document) => root.querySelector(sel);
  const isObj = (o) => o && typeof o === "object" && !Array.isArray(o);
  const toArr = (x) => (Array.isArray(x) ? x : []);

  // ===== 狀態 =====
  let onlyDefectGlass = false;
  let lastExpanded = null;
  let lastColDict = null;
  let lastFromChart = false;

  // ======================================================
  // EditSummary state sync
  // ======================================================
  function upsertEditSummaryFromRow(row) {
    const AOI = window.AOI_INSPECTION || {};
    const state = AOI.state || {};
    if (!state.ProSpecDict) state.ProSpecDict = {};

    let hist = state.ProSpecDict["EditSummary"];

    if (Array.isArray(hist)) {
      // ok
    } else if (hist && typeof hist === "object") {
      hist = Object.values(hist);
    } else {
      hist = [];
    }

    const keyFields = ["pi_hour", "line_id", "model", "glass_type"];
    const keyStr = keyFields.map((k) => String(row[k] ?? "")).join("||");

    let found = false;
    for (const item of hist) {
      const itemKey = keyFields.map((k) => String(item[k] ?? "")).join("||");
      if (itemKey === keyStr) {
        item.comment = row.comment ?? "";
        item.action = row.action ?? "";
        item.Editor = row.Editor ?? row.editor ?? "";
        item.modify_time = row.modify_time ?? row.modifyTime ?? "";
        found = true;
        break;
      }
    }

    if (!found && ((row.comment && row.comment !== "") || (row.action && row.action !== ""))) {
      hist.push({
        pi_hour: row.pi_hour,
        line_id: row.line_id,
        model: row.model,
        glass_type: row.glass_type,
        comment: row.comment ?? "",
        action: row.action ?? "",
        Editor: row.Editor ?? row.editor ?? "",
        modify_time: row.modify_time ?? row.modifyTime ?? ""
      });
    }

    state.ProSpecDict["EditSummary"] = hist;

    try {
      if (
        AOI.currentSectionId === "aoi-inspection-density-spec-table" &&
        AOI.state.activeSubTab === "EditSummary"
      ) {
        const cfg = AOI.state.paramDict?.SubTabsFilterDefaultDict?.EditSummary || {};

        document.dispatchEvent(new CustomEvent("aoi_inspection:subtab-table", {
          detail: {
            tabKey: "EditSummary",
            config: cfg,
            data: hist
          }
        }));
      }
    } catch (e) {
      console.warn("[Inspection] upsertEditSummaryFromRow refresh table error:", e);
    }
  }

  function getNowStr() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    const yyyy = d.getFullYear();
    const mm = pad(d.getMonth() + 1);
    const dd = pad(d.getDate());
    const hh = pad(d.getHours());
    const mi = pad(d.getMinutes());
    const ss = pad(d.getSeconds());
    return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}`;
  }

  // ======================================================
  // glass / group helpers
  // ======================================================
  function parseGlassList(val) {
    if (val == null) return [];
    if (Array.isArray(val)) {
      return val.map(String).map((s) => s.trim()).filter(Boolean);
    }
    return String(val)
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  }

  function getGroupConf(paramDict) {
    const tg = (paramDict && paramDict.hourlyTable_key_group) || {};
    const mainKeys = Array.isArray(tg.main_group) ? tg.main_group.slice() : [];
    const uniSet = new Set([...(tg.uni_col || []), "glass"]);
    const down = (paramDict && paramDict.chartKeyDict && paramDict.chartKeyDict.down) || [];
    const timeKeys = new Set(["pi_hour", ...down]);
    return { mainKeys, uniSet, timeKeys };
  }

  function toNum(v) {
    const x = Number(v);
    return Number.isFinite(x) ? x : 0;
  }

  // 支援：
  // 1. 新格式 JSON string / object:
  //    {"G1":{"S":1,"M":0,"L":2,"O":0},"G2":{"S":0,"M":0,"L":0,"O":0}}
  // 2. 舊格式 string:
  //    G1:S=1;M=0;L=2;O=0,G2:S=0;M=0;L=0;O=0
  function parseGlassSizeDetailToMap(detailVal) {
    if (!Array.isArray(detailVal)) return {};
  
    const out = {};
    detailVal.forEach((one) => {
      if (!one || typeof one !== "object") return;
  
      const gid = String(one.glass_id || "").trim();
      if (!gid) return;
  
      out[gid] = {
        S: toNum(one.S),
        M: toNum(one.M),
        L: toNum(one.L),
        O: toNum(one.O),
        def_count: toNum(one.def_count),
      };
    });
  
    return out;
  }

  function getPerGlassSizeRaw(row) {
    return row && row.__sizeRaw != null ? String(row.__sizeRaw) : "";
  }

  function getPerGlassDefCount(row) {
    const v = row && row.__defCount != null ? Number(row.__defCount) : NaN;
    return Number.isFinite(v) ? v : null;
  }

  // ======================================================
  // head right actions
  // ======================================================
  function ensureHeadRightBox() {
    const head = $("#aoi-inspection-density-table-wrap .table-head");
    if (!head) return null;

    head.style.display = "flex";
    head.style.alignItems = "center";

    let right = head.querySelector(".aoi-inspection-density-head-right");
    if (!right) {
      right = document.createElement("div");
      right.className = "aoi-inspection-density-head-right";
      right.style.marginLeft = "auto";
      right.style.display = "flex";
      right.style.alignItems = "center";
      right.style.gap = "8px";
      head.appendChild(right);
    }
    return right;
  }

  function ensureDefectOnlyCheckbox() {
    const right = ensureHeadRightBox();
    if (!right) return null;

    let wrap = right.querySelector("#aoi-inspection-density-defect-only-wrap");
    let ck;

    if (!wrap) {
      wrap = document.createElement("label");
      wrap.id = "aoi-inspection-density-defect-only-wrap";
      wrap.style.display = "inline-flex";
      wrap.style.alignItems = "center";
      wrap.style.fontSize = "12px";
      wrap.style.cursor = "pointer";

      ck = document.createElement("input");
      ck.type = "checkbox";
      ck.id = "aoi-inspection-density-defect-only";
      ck.style.marginRight = "4px";

      const span = document.createElement("span");
      span.textContent = "Only glass with defect";

      wrap.appendChild(ck);
      wrap.appendChild(span);
      right.appendChild(wrap);

      ck.addEventListener("change", () => {
        onlyDefectGlass = ck.checked;
        if (lastExpanded && lastColDict) {
          renderBody(lastExpanded, lastColDict);
        }
      });
    } else {
      ck = wrap.querySelector("#aoi-inspection-density-defect-only");
    }

    if (ck) {
      ck.checked = !!onlyDefectGlass;
      ck.disabled = false;
    }
    return wrap;
  }

  function ensureReturnButton() {
    const right = ensureHeadRightBox();
    if (!right) return null;

    let btn = right.querySelector("#aoi-inspection-density-table-return");
    if (!btn) {
      btn = document.createElement("button");
      btn.id = "aoi-inspection-density-table-return";
      btn.className = "btn btn-xs btn-secondary";
      btn.textContent = "Return";
      right.appendChild(btn);

      btn.addEventListener("click", () => {
        const rows = window.AOI_INSPECTION?.getFiltered?.() || [];
        const pd = window.AOI_INSPECTION?.state?.paramDict || {};
        lastFromChart = false;
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

  // ======================================================
  // expand rows
  // ======================================================
  function expandRowsByGlass(rows, paramDict) {
    const { mainKeys, uniSet, timeKeys } = getGroupConf(paramDict);
    const out = [];
  
    (rows || []).forEach((r) => {
      const gList = parseGlassList(r.glass);
      const detailMap = parseGlassSizeDetailToMap(r.glass_size_detail);
  
      const sig = mainKeys.map((k) => `${k}:${r[k] ?? ""}`).join("|");
  
      (gList.length ? gList : [""]).forEach((gid, idx) => {
        const gidStr = String(gid || "").trim();
        const one = detailMap[gidStr] || { S: 0, M: 0, L: 0, O: 0, def_count: 0 };
  
        const s = toNum(one.S);
        const m = toNum(one.M);
        const l = toNum(one.L);
        const o = toNum(one.O);
        const defCount = toNum(one.def_count || (s + m + l + o));
  
        out.push({
          ...r,
          __groupKey: sig,
          __groupIndex: idx,
          __glassId: gidStr,
          __defCount: defCount,
  
          glass: gidStr,
  
          // 單片 glass 顯示值
          small_defect_count: s,
          middle_defect_count: m,
          large_defect_count: l,
          over_defect_count: o,
        });
      });
    });
  
    out.sort((a, b) => {
      for (const k of mainKeys) {
        const av = a[k] ?? "";
        const bv = b[k] ?? "";
        if (timeKeys.has(k)) {
          const da = new Date(String(av).replace(" ", "T"));
          const db = new Date(String(bv).replace(" ", "T"));
          const cmp = (isNaN(da) - isNaN(db)) || (da - db);
          if (cmp) return cmp;
        } else {
          if (av < bv) return -1;
          if (av > bv) return 1;
        }
      }
      return String(a.glass || "").localeCompare(String(b.glass || ""));
    });
  
    return { rows: out, mainKeys, uniSet, timeKeys };
  }
  

  function buildColKeys(colDict) {
    const base = Object.keys(colDict || {});
    const cols = base.slice();

    const gi = cols.indexOf("glass");
    if (gi >= 0) {
      cols.splice(gi + 1, 0, "__glassDefTotal");
    } else {
      cols.unshift("__glassDefTotal");
    }

    return cols;
  }

  function renderHeader(colDict) {
    const thead = $("#aoi-inspection-density-table thead");
    if (!thead) return;

    thead.innerHTML = "";
    const tr = document.createElement("tr");
    const cols = buildColKeys(colDict);

    const thAct = document.createElement("th");
    thAct.className = "col-group-actions";
    thAct.textContent = "";
    thAct.style.width = "70px";
    tr.appendChild(thAct);

    cols.forEach((key) => {
      const th = document.createElement("th");
      th.className = `col-${key}`;

      if (key === "__glassDefTotal") {
        th.textContent = "def count";
      } else {
        th.textContent = String(colDict[key] || key);
      }

      th.style.whiteSpace = "nowrap";
      th.style.overflow = "hidden";
      th.style.textOverflow = "ellipsis";
      tr.appendChild(th);
    });

    thead.appendChild(tr);
  }

  // ======================================================
  // modal helpers
  // ======================================================
  function createModalBase(titleText) {
    const overlay = document.createElement("div");
    overlay.className = "aoi-inspection-density-modal-backdrop";
    overlay.style.position = "fixed";
    overlay.style.inset = "0";
    overlay.style.background = "rgba(0,0,0,0.45)";
    overlay.style.display = "flex";
    overlay.style.alignItems = "center";
    overlay.style.justifyContent = "center";
    overlay.style.zIndex = "9999";

    const box = document.createElement("div");
    box.className = "aoi-inspection-density-modal";
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
    body.className = "aoi-inspection-density-modal-body";
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

    function getEditor() {
      const wEditor =
        (window.editor != null && String(window.editor).trim() !== "")
          ? String(window.editor)
          : ((row.Editor || row.editor) || "");
      return wEditor;
    }

    function buildApiRow() {
      const api_row = {};
      ["pi_hour", "line_id", "model", "glass_type"].forEach((k) => {
        api_row[k] = row[k] || "";
      });
      return api_row;
    }

    const lblC = document.createElement("div");
    lblC.textContent = "Comment";
    lblC.style.fontWeight = "600";

    let commentOriginal = (row.comment ?? "") + "";
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

    let actionOriginal = (row.action ?? "") + "";
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

    footerActions.appendChild(btnSave);
    footerActions.appendChild(btnCancel);
    body.appendChild(footerActions);

    btnCancel.addEventListener("click", (ev) => {
      ev.stopPropagation();
      taC.value = commentOriginal;
      taA.value = actionOriginal;
    });

    btnSave.addEventListener("click", async (ev) => {
      ev.stopPropagation();

      const newComment = (taC.value ?? "") + "";
      const newAction = (taA.value ?? "") + "";

      const commentChanged = newComment !== commentOriginal;
      const actionChanged = newAction !== actionOriginal;

      if (!commentChanged && !actionChanged) {
        alert("沒有變更內容，無需儲存。");
        return;
      }

      const newModifyTime = getNowStr();
      const newEditor = getEditor();
      const api_row = buildApiRow();

      if (commentChanged) row.comment = newComment;
      if (actionChanged) row.action = newAction;
      row.Editor = newEditor;
      row.modify_time = newModifyTime;

      if (lastExpanded && lastColDict) {
        renderBody(lastExpanded, lastColDict);
      }
      upsertEditSummaryFromRow(row);

      try {
        if (!API?.CommentEditor) {
          alert("儲存失敗：API.CommentEditor 不存在");
          return;
        }

        const results = [];

        if (commentChanged) {
          const payloadC = {
            system: "aoi_inspection_density",
            mode: "comment",
            row: api_row,
            comment: newComment,
            editor: newEditor,
            modify_time: newModifyTime,
          };
          const respC = await API.CommentEditor(payloadC);
          results.push({ mode: "comment", resp: respC });
        }

        if (actionChanged) {
          const payloadA = {
            system: "aoi_inspection_density",
            mode: "action",
            row: api_row,
            action: newAction,
            editor: newEditor,
            modify_time: newModifyTime,
          };
          const respA = await API.CommentEditor(payloadA);
          results.push({ mode: "action", resp: respA });
        }

        const allOk = results.every((x) => x?.resp?.ok === true);
        if (allOk) {
          if (commentChanged) commentOriginal = newComment;
          if (actionChanged) actionOriginal = newAction;
          alert("儲存成功");
        } else {
          alert("儲存完成，但後端回應不是 ok=true（請看 console）");
          console.warn("[Inspection] save results:", results);
        }
      } catch (err) {
        console.error("[Inspection] save error:", err);
        alert("儲存失敗：" + (err?.message || String(err)));
      }
    });
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
    boxC.textContent = (row.comment ?? "") + "";
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
    boxA.textContent = (row.action ?? "") + "";
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
    footer.className = "aoi-inspection-density-modal-footer";

    const e = (row.Editor || row.editor) || "";
    const mt = (row.modify_time || row.modifyTime) || "";
    footer.textContent = e && mt ? `編輯: ${e}  時間: ${mt}` : `編輯: 預設  時間: ${mt}`;

    footer.style.marginTop = "12px";
    footer.style.textAlign = "center";
    footer.style.fontSize = "11px";
    footer.style.whiteSpace = "pre-line";

    box.appendChild(footer);
  }

  // ======================================================
  // render body
  // ======================================================
  function renderBody(expanded, colDict) {
    const tbody = document.querySelector("#aoi-inspection-density-table tbody");
    if (!tbody) return;
    tbody.innerHTML = "";

    const { rows: rowsExRaw, mainKeys } = expanded || {};
    const colKeys = buildColKeys(colDict);


    const rowsEx = (rowsExRaw || []).filter((row) => {
      if (!onlyDefectGlass) return true;
      const t = getPerGlassDefCount(row);
      return t != null && t > 0;
    });

    if (!rowsEx.length) {
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

        const td = document.createElement("td");
        td.className = `col-${key}`;
        td.style.whiteSpace = "nowrap";
        td.style.overflow = "hidden";
        td.style.textOverflow = "ellipsis";

        if (isGroupable && isHead) {
          td.classList.add("merged");
          td.rowSpan = groupRowspanAtIndex[i];
        }

        let val = "";

        if (key === "pi_hour") {
          val = row.pi_hour_label || row.pi_hour || "";
        }
        if (key === "__glassDefTotal") {
          const t = getPerGlassDefCount(row);
          val = t != null ? String(t) : "";
        } else if (key === "glass") {
          val = row.glass || "";
        } else {
          val = row[key] != null ? row[key] : "";
        }

        if (
          [
            "defect_code_count",
            "n_rows",
            "defect_num",
            "Def Count",
            "def_count",
            "defect_count",
          ].includes(key)
        ) {
          const t2 = getPerGlassDefCount(row);
          if (t2 != null) val = String(t2);
        }

        if (
          key === "__glassDefTotal" ||
          /count$/.test(key) ||
          key === "n_glasses" ||
          key === "density"
        ) {
          td.style.textAlign = "right";
        }

        td.textContent = val == null ? "" : String(val);
        tr.appendChild(td);
      }

      tbody.appendChild(tr);
    }
  }

  // ======================================================
  // public
  // ======================================================
  MOD.Table.render = function (rows, paramDict) {
    const colDict = isObj(paramDict?.hourlyTable) ? paramDict.hourlyTable : null;

    let useColDict;
    if (colDict && Object.keys(colDict).length) {
      useColDict = colDict;
    } else {
      const sample = toArr(rows)[0] || {};
      const dyn = {};
      Object.keys(sample).forEach((k) => { dyn[k] = k; });
      useColDict = dyn;
    }

    lastFromChart = false;

    renderHeader(useColDict);
    lastExpanded = expandRowsByGlass(rows || [], paramDict || {});
    lastColDict = useColDict;
    renderBody(lastExpanded, lastColDict);
    ensureDefectOnlyCheckbox();
    showReturn(false);
  };

  MOD.Table.showRows = function (rows, paramDict, opts) {
    const colDict = isObj(paramDict?.hourlyTable) ? paramDict.hourlyTable : null;

    let useColDict;
    if (colDict && Object.keys(colDict).length) {
      useColDict = colDict;
    } else {
      const sample = toArr(rows)[0] || {};
      const dyn = {};
      Object.keys(sample).forEach((k) => { dyn[k] = k; });
      useColDict = dyn;
    }

    lastFromChart = true;

    renderHeader(useColDict);
    lastExpanded = expandRowsByGlass(rows || [], paramDict || {});
    lastColDict = useColDict;
    renderBody(lastExpanded, lastColDict);
    ensureDefectOnlyCheckbox();
    showReturn(true);
  };
})();