// static/js/aoi_inspection/table.js
// 功能：
// - 預設顯示：依 Filter（UI）後的 rows
// - 新增：由 chart 互動（柱/點/xAxis/yAxis）丟進來的 rows 覆寫顯示
// - 表頭依 ParamDict['hourlyTable']；rowspan 合併同 group
// - 在「Analysis Table」右側自動插入 Return + checkbox（Only glass with defect）
//
// 本版重點：
// 1) 使用 row.glass_size_detail 解析每片 glass 的 S/M/L/O：
//    "AG0UJC01HR:S=0;M=0;L=0;O=0,AG0UJC01HJ:S=1;M=0;L=2;O=0"
// 2) 表格展開成「逐片 glass 一列」：
//    - 左邊 glass 欄：顯示該片 glass_id（例如 AG0UJC01HR）
//    - "def count" 欄：S+M+L+O 的合計
//    - "size" 欄（glass_detail_size / glass_size_detail）：顯示 "S=..;M=..;L=..;O=.." 整串
// 3) Only glass with defect：以 def count > 0 判斷，初始也可用
(function () {
  const MOD = (window.AOI_INSPECTION = window.AOI_INSPECTION || {});
  MOD.Table = MOD.Table || {};
  const editor = window.editor || '';
  const $ = (sel, root = document) => root.querySelector(sel);

  // ===== 狀態 =====
  let onlyDefectGlass = false;   // checkbox 狀態
  let lastExpanded = null;       // expandRowsByGlass 的結果 { rows, mainKeys, uniSet, timeKeys }
  let lastColDict = null;        // 目前使用的欄位定義（ParamDict.hourlyTable）
  let lastFromChart = false;     // true = 由 chart 互動顯示, false = Filter 預設顯示（保留標記）

  const isObj = (o) => o && typeof o === "object" && !Array.isArray(o);
  const toArr = (x) => (Array.isArray(x) ? x : []);


  function getNowStr(){
    const d = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    const yyyy = d.getFullYear();
    const mm   = pad(d.getMonth() + 1);
    const dd   = pad(d.getDate());
    const hh   = pad(d.getHours());
    const mi   = pad(d.getMinutes());
    const ss   = pad(d.getSeconds());
    return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}`;
  }

  // 將 row.glass 轉成 glass_id 陣列
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

  // 依 ParamDict 決定 group key / uni col / time key
  function getGroupConf(paramDict) {
    const tg =
      (paramDict &&
        (paramDict.hourlyTable_key_group ||
          paramDict.hourlyTable_key_group)) ||
      {};
    const mainKeys = Array.isArray(tg.main_group) ? tg.main_group.slice() : [];
    const uniSet = new Set([...(tg.uni_col || []), "glass"]);
    const down =
      (paramDict && paramDict.chartKeyDict && paramDict.chartKeyDict.down) ||
      [];
    const timeKeys = new Set(["pi_hour", ...down]);
    return { mainKeys, uniSet, timeKeys };
  }


  function parseGlassSizeDetailToMap(detailStr) {
    const out = {};
    if (!detailStr) return out;

    const parts = String(detailStr)
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    for (const one of parts) {
      const idx = one.indexOf(":");
      if (idx < 0) continue;

      const gid = one.slice(0, idx).trim();
      const rhs = one.slice(idx + 1).trim(); // "S=0;M=0;L=0;O=0"
      if (!gid || !rhs) continue;

      const getNum = (k) => {
        const m = rhs.match(new RegExp(`\\b${k}\\s*=\\s*(\\d+)`, "i"));
        return m ? Number(m[1] || 0) : 0;
      };

      const S = getNum("S");
      const M = getNum("M");
      const L = getNum("L");
      const O = getNum("O");

      const sum =
        (Number.isFinite(S) ? S : 0) +
        (Number.isFinite(M) ? M : 0) +
        (Number.isFinite(L) ? L : 0) +
        (Number.isFinite(O) ? O : 0);

      out[gid] = {
        raw: `S=${S};M=${M};L=${L};O=${O}`,
        sum,
      };
    }

    return out;
  }

  // 取得逐片 glass 的 size raw 與 def count
  function getPerGlassSizeRaw(row) {
    return row && row.__sizeRaw != null ? String(row.__sizeRaw) : "";
  }
  function getPerGlassDefCount(row) {
    const v = row && row.__defCount != null ? Number(row.__defCount) : NaN;
    return Number.isFinite(v) ? v : null;
  }

  // ================= Head 右側：Return + checkbox =================

  function ensureHeadRightBox() {
    const head = $("#inspection-table-wrap .table-head");
    if (!head) return null;

    head.style.display = "flex";
    head.style.alignItems = "center";

    let right = head.querySelector(".inspection-head-right");
    if (!right) {
      right = document.createElement("div");
      right.className = "inspection-head-right";
      right.style.marginLeft = "auto";
      right.style.display = "flex";
      right.style.alignItems = "center";
      right.style.gap = "8px";
      head.appendChild(right);
    }
    return right;
  }

  // ★ 勾選框：只顯示有 defect 的 glass（現在 Filter / Chart 都可用）
  function ensureDefectOnlyCheckbox() {
    const right = ensureHeadRightBox();
    if (!right) return null;

    let wrap = right.querySelector("#inspection-defect-only-wrap");
    let ck;

    if (!wrap) {
      wrap = document.createElement("label");
      wrap.id = "inspection-defect-only-wrap";
      wrap.style.display = "inline-flex";
      wrap.style.alignItems = "center";
      wrap.style.fontSize = "12px";
      wrap.style.cursor = "pointer";

      ck = document.createElement("input");
      ck.type = "checkbox";
      ck.id = "inspection-defect-only";
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
      ck = wrap.querySelector("#inspection-defect-only");
    }

    if (ck) {
      ck.checked = !!onlyDefectGlass;
      ck.disabled = false;   // 初始也可用
    }
    return wrap;
  }

  function ensureReturnButton() {
    const right = ensureHeadRightBox();
    if (!right) return null;

    let btn = right.querySelector("#inspection_tableReturn");
    if (!btn) {
      btn = document.createElement("button");
      btn.id = "inspection_tableReturn";
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
  // ★ 展開逐片 glass row（寫入 __sizeRaw / __defCount）
  // ======================================================
  function expandRowsByGlass(rows, paramDict) {
    const { mainKeys, uniSet, timeKeys } = getGroupConf(paramDict);
    const out = [];

    (rows || []).forEach((r) => {
      const gList = parseGlassList(r.glass);

      // ✅ 支援兩種 key 名：glass_size_detail / glass_detail_size
      const detailStr = r.glass_size_detail || r.glass_detail_size || "";
      const detailMap = parseGlassSizeDetailToMap(detailStr);

      const sig = mainKeys
        .map((k) => k + ":" + (r[k] ?? ""))
        .join("|");

      (gList.length ? gList : [""]).forEach((gid, idx) => {
        const info = detailMap[gid] || null;
        out.push({
          __groupKey: sig,
          __groupIndex: idx,
          __glassId: gid,
          __sizeRaw: info ? info.raw : "",     // size 欄顯示用
          __defCount: info ? info.sum : null,  // def count 顯示 / 過濾用
          ...r,
          glass: gid,                          // 一列只顯示單一 glass_id
        });
      });
    });

    // 依 mainKeys 排序，最後依 glass id
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

  // ===== 欄位順序：在 glass 後插入 def count 欄 =====
  function buildColKeys(colDict) {
    const base = Object.keys(colDict || {});
    const cols = base.slice();

    const gi = cols.indexOf("glass");
    if (gi >= 0) {
      // 在 glass 之後插入一個虛擬欄位 __glassDefTotal
      cols.splice(gi + 1, 0, "__glassDefTotal");
    } else {
      cols.unshift("__glassDefTotal");
    }

    return cols;
  }

  function renderHeader(colDict) {
    const thead = $("#inspection-table thead");
    if (!thead) return;
    thead.innerHTML = "";
    const tr = document.createElement("tr");
  
    const cols = buildColKeys(colDict);
  
    // === 新增：最左側 group 操作欄 ===
    const thAct = document.createElement("th");
    thAct.className = "col-group-actions";
    thAct.textContent = "";              // 列名留空就好
    thAct.style.width = "70px";
    tr.appendChild(thAct);
    // =================================
  
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
   // ==============================================
  // comment 欄位客製 UI：上方可編輯 textbox，下方 Editor/modify_time
  // ==============================================
  function buildCommentCell(td, row) {
    const wrapper = document.createElement("div");
    wrapper.className = "comment-wrapper";
    wrapper.style.display = "flex";
    wrapper.style.flexDirection = "column";
    wrapper.style.gap = "6px";
    wrapper.style.width = "100%";
  
    // ====== 工具：現在時間（你要的儲存當下時間） ======
    function nowIso() {
      // 例：2026-01-02T13:05:12+08:00
      const d = new Date();
      const pad = (n) => String(n).padStart(2, "0");
      const y = d.getFullYear();
      const m = pad(d.getMonth() + 1);
      const dd = pad(d.getDate());
      const hh = pad(d.getHours());
      const mm = pad(d.getMinutes());
      const ss = pad(d.getSeconds());
      const tz = -d.getTimezoneOffset(); // minutes
      const sign = tz >= 0 ? "+" : "-";
      const tzh = pad(Math.floor(Math.abs(tz) / 60));
      const tzm = pad(Math.abs(tz) % 60);
      return `${y}-${m}-${dd}T${hh}:${mm}:${ss}${sign}${tzh}:${tzm}`;
    }
  
    // ====== 上方：按鈕列（在 textbox 上方，水平排列） ======
    const actions = document.createElement("div");
    actions.className = "comment-actions";
    actions.style.display = "none";           // 預設不顯示（進入 edit 才顯示）
    actions.style.justifyContent = "flex-end";
    actions.style.gap = "6px";
  
    const btnSave = document.createElement("button");
    btnSave.type = "button";
    btnSave.className = "btn btn-xs";
    btnSave.textContent = "儲存";
  
    const btnCancel = document.createElement("button");
    btnCancel.type = "button";
    btnCancel.className = "btn btn-xs btn-secondary";
    btnCancel.textContent = "取消";
  
    actions.appendChild(btnSave);
    actions.appendChild(btnCancel);
  
    // ====== textbox（textarea） ======
    const orig = (row.comment ?? "") + "";
  
    const ta = document.createElement("textarea");
    ta.className = "comment-textarea";
    ta.value = orig;
    ta.dataset.originalValue = orig;
    ta.readOnly = true;                 // 預設不可編輯
    ta.rows = 2;
    ta.style.width = "100%";
    ta.style.resize = "vertical";
    ta.style.minHeight = "36px";
    ta.style.fontSize = "12px";
    ta.style.lineHeight = "1.3";
    ta.style.padding = "4px 6px";
    ta.style.border = "1px solid #2b3240";
    ta.style.borderRadius = "4px";
    ta.style.background = "transparent";
    ta.style.color = "inherit";
  
    // ====== 下方：Editor + modify_time（純文字顯示） ======
    const bottom = document.createElement("div");
    bottom.className = "comment-meta";
    const e0 = (row.Editor || row.editor) || "";
    const mt0 = (row.modify_time || row.modifyTime) || "";
    bottom.textContent = e0 && mt0 ? `${e0}\n${mt0}` : (e0 || mt0 || "");
    bottom.style.fontSize = "11px";
    bottom.style.color = "#999";
    bottom.style.whiteSpace = "pre-line";
  
    // 組裝
    wrapper.appendChild(actions); // ✅ 按鈕在上方
    wrapper.appendChild(ta);
    wrapper.appendChild(bottom);
    td.appendChild(wrapper);
  
    // ====== 編輯模式 ======
    let editing = false;
  
    function enterEdit() {
      if (editing) return;
      editing = true;
      ta.readOnly = false;
      ta.focus();
      actions.style.display = "flex";
      ta.style.borderColor = "#888";
    }
  
    function exitEdit() {
      editing = false;
      ta.readOnly = true;
      actions.style.display = "none";
      ta.style.borderColor = "#2b3240";
    }
  
    // 雙擊進入編輯
    ta.addEventListener("dblclick", (ev) => {
      ev.stopPropagation();
      enterEdit();
    });
  
    // ====== 儲存：console + 更新 editor/modify_time + 收起 ======
    btnSave.addEventListener("click", async (ev) => {
      ev.stopPropagation();
    
      const newComment = ta.value ?? "";
      const newModifyTime = getNowStr();
    
      // editor：你現在用 window.editor OK（或你要改成 window.USER 也行）
      const newEditor =
        (window.editor != null && String(window.editor).trim() !== "")
          ? String(window.editor)
          : ((row.Editor || row.editor) || "");
      const api_row = {};
      ['pi_hour', 'line_id', 'model', 'glass_type'].forEach(apiKey =>{
        api_row[apiKey] = row[apiKey] || '';
      })
      //  你要丟後端的 payload（同 console 那包）
      const payload = {
        system: "inspection",
        mode: "comment",
        row: api_row,
        // 更新後資料
        comment: newComment,
        editor: newEditor,
        modify_time: newModifyTime,
    
      };
    
      // 1) 先照你需求 console（含時間+editor+key）
      console.log("[Inspection] comment save:", payload);
    
      // 2) 立刻更新 UI（不等後端）
      row.comment = newComment;
      row.Editor = newEditor;
      row.modify_time = newModifyTime;
    
      ta.dataset.originalValue = newComment;
      bottom.textContent = (newEditor && newModifyTime)
        ? `${newEditor}\n${newModifyTime}`
        : (newEditor || newModifyTime || "");
    
      exitEdit();
      /*
      
      */
      // 3) 用 frontEditor 傳後端
      try {
        if (!window.API?.frontEditor) {
          console.warn("[Inspection] window.API.frontEditor not found, skip post", payload);
          return;
        }
        const resp = await window.API.frontEditor(payload);
        console.log("[Inspection] comment frontEditor resp:", resp);
      } catch (err) {
        console.error("[Inspection] comment frontEditor error:", err);
        // 你要的話這裡也可以做 rollback（把 comment 還原），但你目前需求沒要求
      }
    });
  
    // ====== 取消：還原 + 收起 ======
    btnCancel.addEventListener("click", (ev) => {
      ev.stopPropagation();
      ta.value = ta.dataset.originalValue || "";
      exitEdit();
    });
  }

  // ==============================
  // Group 彈跳視窗小工具
  // ==============================

  function createModalBase(titleText) {
    const overlay = document.createElement("div");
    overlay.className = "inspection-modal-backdrop";
    overlay.style.position = "fixed";
    overlay.style.inset = "0";
    overlay.style.background = "rgba(0,0,0,0.45)";
    overlay.style.display = "flex";
    overlay.style.alignItems = "center";
    overlay.style.justifyContent = "center";
    overlay.style.zIndex = "9999";

    const box = document.createElement("div");
    box.className = "inspection-modal";
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
    body.className = "inspection-modal-body";
    body.style.display = "flex";
    body.style.gap = "16px";
    body.style.marginTop = "8px";
    body.style.overflow = "auto";

    box.appendChild(header);
    box.appendChild(body);
    overlay.appendChild(box);

    function close() {
      if (overlay.parentNode) {
        overlay.parentNode.removeChild(overlay);
      }
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

  // ====== Group 編輯視窗（左：comment；右：action） ======
  function openEditModalForGroup(row) {
    const { body } = createModalBase("comment / action");

    // 左右兩區塊
    const left = document.createElement("div");
    const right = document.createElement("div");
    [left, right].forEach((col) => {
      col.style.flex = "1 1 0";
      col.style.display = "flex";
      col.style.flexDirection = "column";
      col.style.gap = "6px";
    });

    // 共用：取 editor & api_row
    function getEditor() {
      const wEditor = (window.editor != null && String(window.editor).trim() !== "")
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

    // === 左側：comment 區 ===
    let commentOriginal = (row.comment ?? "") + "";

    const lblC = document.createElement("div");
    lblC.textContent = "Comment";
    lblC.style.fontWeight = "600";

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

    const btnRowC = document.createElement("div");
    btnRowC.style.display = "flex";
    btnRowC.style.justifyContent = "flex-end";
    btnRowC.style.gap = "6px";

    const btnCSave = document.createElement("button");
    btnCSave.type = "button";
    btnCSave.className = "btn btn-xs";
    btnCSave.textContent = "儲存";

    const btnCCancel = document.createElement("button");
    btnCCancel.type = "button";
    btnCCancel.className = "btn btn-xs btn-secondary";
    btnCCancel.textContent = "取消";

    btnRowC.appendChild(btnCSave);
    btnRowC.appendChild(btnCCancel);

    left.appendChild(lblC);
    left.appendChild(taC);
    left.appendChild(btnRowC);

    // === 右側：action 區 ===
    let actionOriginal = (row.action ?? "") + "";

    const lblA = document.createElement("div");
    lblA.textContent = "Action";
    lblA.style.fontWeight = "600";

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

    const btnRowA = document.createElement("div");
    btnRowA.style.display = "flex";
    btnRowA.style.justifyContent = "flex-end";
    btnRowA.style.gap = "6px";

    const btnASave = document.createElement("button");
    btnASave.type = "button";
    btnASave.className = "btn btn-xs";
    btnASave.textContent = "儲存";

    const btnACancel = document.createElement("button");
    btnACancel.type = "button";
    btnACancel.className = "btn btn-xs btn-secondary";
    btnACancel.textContent = "取消";

    btnRowA.appendChild(btnASave);
    btnRowA.appendChild(btnACancel);

    right.appendChild(lblA);
    right.appendChild(taA);
    right.appendChild(btnRowA);

    body.appendChild(left);
    body.appendChild(right);

    // ====== 按鈕事件：Comment 儲存 / 取消 ======
    btnCSave.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      const newComment = taC.value ?? "";
      const newModifyTime = getNowStr();
      const newEditor = getEditor();
      const api_row = buildApiRow();

      const payload = {
        system: "inspection",
        mode: "comment",          // ★ 編輯 comment 區
        row: api_row,
        comment: newComment,
        editor: newEditor,
        modify_time: newModifyTime,
      };

      console.log("[Inspection] group comment save:", payload);

      // 更新 row & UI
      row.comment = newComment;
      row.Editor = newEditor;
      row.modify_time = newModifyTime;
      commentOriginal = newComment;

      if (lastExpanded && lastColDict) {
        renderBody(lastExpanded, lastColDict);
      }

      try {
        if (window.API?.frontEditor) {
          const resp = await window.API.frontEditor(payload);
          console.log("[Inspection] frontEditor resp (comment):", resp);
        }
      } catch (err) {
        console.error("[Inspection] frontEditor error (comment):", err);
      }
    });

    btnCCancel.addEventListener("click", (ev) => {
      ev.stopPropagation();
      taC.value = commentOriginal;
    });

    // ====== 按鈕事件：Action 儲存 / 取消 ======
    btnASave.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      const newAction = taA.value ?? "";
      const newModifyTime = getNowStr();
      const newEditor = getEditor();
      const api_row = buildApiRow();
    
      const payload = {
        system: "inspection",
        mode: "action",      //  通知後端要更新 action 欄位
        row: api_row,
        action: newAction,   //  這裡改成 action，不再塞在 comment
        editor: newEditor,
        modify_time: newModifyTime,
      };
    
      console.log("[Inspection] group action save:", payload);
    
      row.action = newAction;
      row.Editor = newEditor;
      row.modify_time = newModifyTime;
    
      if (lastExpanded && lastColDict) {
        renderBody(lastExpanded, lastColDict);
      }
    
      try {
        if (window.API?.frontEditor) {
          const resp = await window.API.frontEditor(payload);
          console.log("[Inspection] frontEditor resp (action):", resp);
        }
      } catch (err) {
        console.error("[Inspection] frontEditor error (action):", err);
      }
    });

    btnACancel.addEventListener("click", (ev) => {
      ev.stopPropagation();
      taA.value = actionOriginal;
    });
  }

function openViewModalForGroup(row) {
  // ★ 這裡把 box 一起拿出來，等一下要在最下方塞 Editor / modify_time
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

  // ====== 新增：視窗下方顯示 Editor + modify_time，水平置中 ======
  const footer = document.createElement("div");
  footer.className = "inspection-modal-footer";

  const e = (row.Editor || row.editor) || "";
  const mt = (row.modify_time || row.modifyTime) || "";
  footer.textContent = e && mt ? `編輯: ${e}  時間: ${mt}` : `編輯: 預設  時間: ${mt}`;

  // 如果你要改成全部交給 CSS 控制，可以只留 className，拿掉這幾行 style
  footer.style.marginTop = "12px";
  footer.style.textAlign = "center";
  footer.style.fontSize = "11px";
  footer.style.whiteSpace = "pre-line";

  box.appendChild(footer);
}

/*

*/
  function renderBody(expanded, colDict) {
    const tbody = document.querySelector("#inspection-table tbody");
    if (!tbody) return;
    tbody.innerHTML = "";

    const { rows: rowsExRaw, mainKeys, uniSet } = expanded || {};
    const colKeys = buildColKeys(colDict);
    console.log("[inspection] colKeys =", colKeys);

    const SIZE_KEYS = new Set([
      "size",
      "detail",
      "glass_size_detail"
    ]);

    const rowsEx = (rowsExRaw || []).filter((row) => {
      if (!onlyDefectGlass) return true;
      const t = getPerGlassDefCount(row);
      return t != null && t > 0;
    });

    if (!rowsEx || !rowsEx.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      // ★ header 多一欄，所以這裡要 +1
      td.colSpan = Math.max(1, colKeys.length + 1);
      td.className = "muted";
      td.textContent = "（無資料）";
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    // group rowspan 計算
    const groupRowspanAtIndex = new Array(rowsEx.length).fill(0);
    let last = "",
      start = 0;
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

      // === 新增：每個 group 左側的「編輯 / 顯示」兩顆按鈕 ===
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
      // ======================================================

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

        /*if (key === "comment") {
          td.style.whiteSpace = "normal";
          td.style.overflow = "visible";
          td.style.textOverflow = "clip";
          td.style.verticalAlign = "top";

          buildCommentCell(td, row);
          tr.appendChild(td);
          continue;
        }*/

        // ===== 以下原本邏輯維持 =====
        let val = "";

        if (key === "__glassDefTotal") {
          const t = getPerGlassDefCount(row);
          val = t != null ? String(t) : "";
        } else if (SIZE_KEYS.has(key)) {
          val = getPerGlassSizeRaw(row);
        } else if (key === "glass") {
          val = row.glass || "";
        /*} else if (key === "Editor") {
          const e = (row.Editor || row.editor) || '';
          const mtime  = (row.modify_time || row.modifyTime) || '';
          val = `${e || ''}${(e && mtime) ? ' ' : ''}${mtime || ''}`;*/
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

  // ================== defect_map API：保留原有行為 ==================

  /*async function sendRowsToDefectMap(rows) {
    try {
      if (!window.API?.post) {
        console.warn(
          "[AOI_INSPECTION] window.API.post 未定義，略過送出 defect_map。"
        );
        return null;
      }
      const url = `${window.API_BASE}/aoi_inspection/api/defect_map`;
      const resp = await window.API.post(url, {
        rows: Array.isArray(rows) ? rows : [],
      });

      if (window.AOI_INSPECTION?.state) {
        window.AOI_INSPECTION.state.defectMapResponse = resp;
      }
      document.dispatchEvent(
        new CustomEvent("aoi_inspection:defect-map-ready", {
          detail: { requestRows: rows, response: resp },
        })
      );
      return resp;
    } catch (err) {
      console.error("[AOI_INSPECTION] defect_map API 錯誤：", err);
      document.dispatchEvent(
        new CustomEvent("aoi_inspection:defect-map-error", {
          detail: { error: err },
        })
      );
      return null;
    }
  }
  */
  /*
  function injectGlassCounts(requestRows, response) {
    // 這邊保留原有邏輯，讓 defect_map.js 仍可吃到 glass_defect_count
    const list = (response && response.DefectGroupDict) || [];
    const out = (requestRows || []).map((r, idx) => {
      const src = list[idx] || {};
      const dg = src.defect_group || {};
      const gdc = {};
      Object.entries(dg).forEach(([gid, payload]) => {
        const S = Number((payload && payload.S) || 0);
        const M = Number((payload && payload.M) || 0);
        const L = Number((payload && payload.L) || 0);
        const O = Number((payload && payload.O) || 0);
        const T =
          payload && payload.total != null
            ? Number(payload.total) || 0
            : S + M + L + O;
        gdc[String(gid)] =
          "S:" +
          S +
          " M:" +
          M +
          " L:" +
          L +
          " O:" +
          O +
          " T:" +
          T;
      });
      return { ...r, glass_defect_count: gdc, __no_api: true };
    });
    return out;
  }*/

  // ================= 對外 API：render / showRows =================

  MOD.Table.render = function (rows, paramDict) {
    const colDict = isObj(paramDict?.hourlyTable)
      ? paramDict.hourlyTable
      : null;

    let useColDict;
    if (colDict && Object.keys(colDict).length) {
      useColDict = colDict;
    } else {
      const sample = toArr(rows)[0] || {};
      const dyn = {};
      Object.keys(sample).forEach((k) => (dyn[k] = k));
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
    const noPost = !!(opts && opts.noPost);
    const colDict = isObj(paramDict?.hourlyTable)
      ? paramDict.hourlyTable
      : null;

    let useColDict;
    if (colDict && Object.keys(colDict).length) {
      useColDict = colDict;
    } else {
      const sample = toArr(rows)[0] || {};
      const dyn = {};
      Object.keys(sample).forEach((k) => (dyn[k] = k));
      useColDict = dyn;
    }

    lastFromChart = true;

    renderHeader(useColDict);
    lastExpanded = expandRowsByGlass(rows || [], paramDict || {});
    lastColDict = useColDict;
    renderBody(lastExpanded, lastColDict);
    ensureDefectOnlyCheckbox();
    showReturn(true);

    /*if (!noPost && !rows?.[0]?.__no_api) {
      sendRowsToDefectMap(rows);
    }
    */
  };

  /*document.addEventListener("aoi_inspection:defect-map-ready", (ev) => {
    const req = ev?.detail?.requestRows || [];
    const resp = ev?.detail?.response || {};
    const pd = window.AOI_INSPECTION?.state?.paramDict || {};
    const updated = injectGlassCounts(req, resp);
    MOD.Table.showRows(updated, pd, { noPost: true });
  });*/
})();
