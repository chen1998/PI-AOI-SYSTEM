// static/js/duty/cell_piaoi/aoi_density2/table.js
// 功能：
// - 預設顯示：依 Filter（UI）後的 rows
// - 由 chart 互動（柱/點/xAxis/yAxis）丟進來的 rows 覆寫顯示
// - 表頭依 ParamDict['hourlyTable']
// - rowSpan 合併同 group
// - 逐片展開 glass
// - glass_size_detail 顯示該 glass 對應的 {S,M,L,O,T}
// - 新版：glass_size_detail 內的 test_time 不新增欄位，改為滑鼠移到 glass_id 時顯示 tooltip
// - comment/action/editor/modify_time 群組編輯與顯示
//
// 注意：
// 新版後端已經在 glass_size_detail 裡帶 test_time。
// 因此本檔不再使用 defect_map 回傳去 merge / 覆蓋 glass_size_detail，避免 test_time 被蓋掉。


// ============================================================
// 重要：
// 舊版曾在 defect-map-ready 後用 defect_map response 回填 glass_size_detail。
// 新版 density job 已經在 glass_size_detail 內帶 test_time，
// 不應再用 defect_map response 覆蓋 table 的 glass_size_detail。
// 因此此處不再監聽 aoi-density:defect-map-ready 去重畫 table。
// defect_map-ready 只給 defect_map.js 使用。
// ============================================================
(function () {
  const MOD = (window.AOI_DENSITY = window.AOI_DENSITY || {});
  MOD.Table = MOD.Table || {};

  const API = window.AOI_DENSITY_API;
  const SH = window.AOI_DENSITY?.Shared || null;

  const $ = (sel, root = document) => root.querySelector(sel);

  // ---------- 小工具 ----------
  const isObj = (o) => o && typeof o === "object" && !Array.isArray(o);
  const toArr = (x) => (Array.isArray(x) ? x : []);

  function safeStr(v) {
    return v == null ? "" : String(v);
  }

  function safeNum(v) {
    const x = Number(v);
    return Number.isFinite(x) ? x : 0;
  }

  function uniqueStringList(arr) {
    const seen = new Set();
    const out = [];

    (arr || []).forEach(v => {
      const s = safeStr(v).trim();
      if (!s) return;
      if (seen.has(s)) return;

      seen.add(s);
      out.push(s);
    });

    return out;
  }

  function normalizePiHourForCompare(v) {
    if (SH?.fmtPiHourToBackend) {
      return SH.fmtPiHourToBackend(v);
    }

    const s = safeStr(v).trim();
    if (!s) return "";

    if (/^\d{2}-\d{2}-\d{2}\s+\d{2}$/.test(s)) {
      const [datePart, hh] = s.split(/\s+/);
      const [yy, mm, dd] = datePart.split("-");
      return `20${yy}-${mm}-${dd} ${hh}:00:00`;
    }

    if (/^\d{4}-\d{2}-\d{2}\s+\d{2}$/.test(s)) {
      return `${s}:00:00`;
    }

    if (/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}$/.test(s)) {
      return `${s}:00`;
    }

    return s.replace("T", " ").replace(".000", "");
  }

  // tick: "YY-MM-DD HH"
  function parseYYMMDDHHToTime(tick) {
    const s = safeStr(tick).trim();
    if (!s) return NaN;

    if (/^\d{2}-\d{2}-\d{2}\s+\d{2}$/.test(s)) {
      const d = new Date(`20${s.replace(" ", "T")}:00:00`);
      return d instanceof Date && !isNaN(d) ? d.getTime() : NaN;
    }

    const d2 = new Date(s.replace(" ", "T"));
    return d2 instanceof Date && !isNaN(d2) ? d2.getTime() : NaN;
  }

  function parseGlassList(val) {
    let arr = [];

    if (SH?.parseGlassList) {
      arr = SH.parseGlassList(val);
    } else if (val == null) {
      arr = [];
    } else if (Array.isArray(val)) {
      arr = val
        .map(safeStr)
        .map((s) => s.trim())
        .filter(Boolean);
    } else {
      arr = String(val)
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
    }

    return uniqueStringList(arr);
  }

  function parseGlassSizeDetail(val) {
    if (SH?.parseGlassSizeDetail) {
      return SH.parseGlassSizeDetail(val);
    }

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

  function normalizeSizeStat(detail) {
    if (SH?.parseSizeStats) {
      return SH.parseSizeStats(detail);
    }

    const d = isObj(detail) ? detail : {};

    const S = safeNum(d.S);
    const M = safeNum(d.M);
    const L = safeNum(d.L);
    const O = safeNum(d.O);
    const T = d.T != null ? safeNum(d.T) : S + M + L + O;

    return {
      test_time: safeStr(
        d.test_time ||
        d.scan_time ||
        d.TEST_TIME ||
        d.SCAN_TIME ||
        ""
      ).trim(),
      S,
      M,
      L,
      O,
      T
    };
  }

  // 將 {S,M,L,O,T} 轉為顯示字串
  function formatSizeDetail(detail) {
    const d = normalizeSizeStat(detail);

    return `S:${safeNum(d.S)} M:${safeNum(d.M)} L:${safeNum(d.L)} O:${safeNum(d.O)} T:${safeNum(d.T)}`;
  }

  // 取該片 glass 的 detail
  function getPerGlassDetail(row) {
    const gid = row?.__glassId;
    if (!gid) return null;

    const gsd = row?.__glassSizeDetailObj || parseGlassSizeDetail(row?.glass_size_detail);
    if (!gsd || !isObj(gsd)) return null;

    const hit = gsd[gid];
    return isObj(hit) ? hit : null;
  }

  // 取該片 glass 的總缺陷 T
  function getPerGlassTotalT(row) {
    const detail = getPerGlassDetail(row);
    if (!detail) return null;

    const d = normalizeSizeStat(detail);
    return Number.isFinite(d.T) ? d.T : null;
  }

  // 新版：取該片 glass 的 test_time
  function getPerGlassTestTime(row) {
    const detail = getPerGlassDetail(row);
    if (!detail || !isObj(detail)) return "";

    const d = normalizeSizeStat(detail);

    return safeStr(
      d.test_time ||
      detail.test_time ||
      detail.scan_time ||
      detail.TEST_TIME ||
      detail.SCAN_TIME ||
      ""
    ).trim();
  }

  // 新版：glass_id hover tooltip
  function buildGlassTooltip(row) {
    const gid = safeStr(row?.__glassId || row?.glass || "").trim();
    const testTime = getPerGlassTestTime(row);
    const detail = getPerGlassDetail(row);

    if (!gid && !testTime && !detail) return "";

    const lines = [];

    if (gid) {
      lines.push(`glass_id: ${gid}`);
    }

    if (testTime) {
      lines.push(`test_time: ${testTime}`);
    }

    if (detail) {
      const d = normalizeSizeStat(detail);
      lines.push(
        `S:${safeNum(d.S)} M:${safeNum(d.M)} L:${safeNum(d.L)} O:${safeNum(d.O)} T:${safeNum(d.T)}`
      );
    }

    return lines.join("\n");
  }

  // ==============================
  // table expanded row dedupe
  // ==============================
  function normalizePiHourForDedupe(row) {
    return normalizePiHourForCompare(row?.pi_hour_raw || row?.pi_hour || "");
  }

  function normalizeGlassSizeDetailForDedupe(row) {
    const d = getPerGlassDetail(row);

    if (!d || !isObj(d)) return "";

    const st = normalizeSizeStat(d);

    return [
      `S:${safeNum(st.S)}`,
      `M:${safeNum(st.M)}`,
      `L:${safeNum(st.L)}`,
      `O:${safeNum(st.O)}`,
      `T:${safeNum(st.T)}`,
      `test_time:${safeStr(st.test_time).trim()}`
    ].join("|");
  }

  function makeExpandedGlassDedupKey(row) {
    return [
      normalizePiHourForDedupe(row),
      safeStr(row?.line_id).trim(),
      safeStr(row?.aoi).trim(),
      safeStr(row?.model).trim(),
      safeStr(row?.glass_type).trim(),
      safeStr(row?.recipe_id).trim(),
      safeStr(row?.adc_def_code).trim(),
      safeStr(row?.tab_name).trim(),
      safeStr(row?.__glassId || row?.glass).trim(),
      normalizeGlassSizeDetailForDedupe(row)
    ].join("||");
  }

  function dedupeExpandedGlassRows(rows) {
    const seen = new Set();
    const out = [];

    (rows || []).forEach(row => {
      const key = makeExpandedGlassDedupKey(row);

      if (seen.has(key)) return;

      seen.add(key);
      out.push(row);
    });

    return out;
  }

  // ==============================
  // comment/action/editor/modify_time
  // ==============================
  const editor = window.editor || "";

  let lastExpanded = null;
  let lastColDict = null;
  let lastParamDict = null;

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

  function getEditor(row) {
    const wEditor =
      window.editor != null && String(window.editor).trim() !== ""
        ? String(window.editor)
        : ((row?.Editor || row?.editor) || "");

    return wEditor;
  }

  // density_code_summary 的唯一鍵
  const DENSITY_KEY_FIELDS = [
    "pi_hour",
    "line_id",
    "aoi",
    "model",
    "glass_type",
    "recipe_id",
    "adc_def_code"
  ];

  function buildApiRowForDensity(row) {
    const out = {};

    DENSITY_KEY_FIELDS.forEach((k) => {
      if (k === "pi_hour") {
        out.pi_hour = row?.pi_hour_raw || row?.pi_hour || "";
      } else {
        out[k] = row?.[k] || "";
      }
    });

    return out;
  }

  function matchByKey(a, b) {
    const aPi = normalizePiHourForCompare(a?.pi_hour_raw || a?.pi_hour || "");
    const bPi = normalizePiHourForCompare(b?.pi_hour_raw || b?.pi_hour || "");

    if (String(aPi) !== String(bPi)) return false;

    for (const k of DENSITY_KEY_FIELDS) {
      if (k === "pi_hour") continue;

      if (String(a?.[k] ?? "") !== String(b?.[k] ?? "")) {
        return false;
      }
    }

    return true;
  }

  function patchStateRowsDensity(sampleRow, patch) {
    const AOI = window.AOI_DENSITY || {};
    const stateRows = AOI?.state?.rows;

    if (!Array.isArray(stateRows) || !stateRows.length) return;

    for (const r of stateRows) {
      if (matchByKey(r, sampleRow)) {
        Object.assign(r, patch);
        break;
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

  // ==============================
  // samePoint
  // ==============================
  function isSamePointActive() {
    return window.AOI_DENSITY?.isSamePointTab?.(
      window.AOI_DENSITY?.state?.activeSubTab || window.density_sub_activeTabKey
    );
  }
  
  function buildUseColDict(rows, paramDict) {
    const colDict = isObj(paramDict?.hourlyTable) ? paramDict.hourlyTable : null;
  
    let baseColDict;
  
    if (colDict && Object.keys(colDict).length) {
      baseColDict = { ...colDict };
    } else {
      const sample = toArr(rows)[0] || {};
      baseColDict = {};
      Object.keys(sample).forEach((k) => {
        baseColDict[k] = k;
      });
    }
  
    const samePointCols = isSamePointActive()
      ? {
          //offset: "offset",
          common_cnt: "common cnt",
          common_glass_cnt: "common gld",
        }
      : {};
  
    const out = {};
    const sourceKeys = Object.keys(baseColDict || {});
  
    sourceKeys.forEach((key) => {
      // 同點欄位要插在 glass / glass_size_detail 左側
      if (isSamePointActive() && key === "glass") {
        Object.entries(samePointCols).forEach(([spKey, spLabel]) => {
          if (!out[spKey]) out[spKey] = spLabel;
        });
      }
  
      // 避免原本被加在最後的同點欄位重複出現
      if (["common_cnt", "common_glass_cnt", "common_points_details"].includes(key)) { //"offset", 
        return;
      }
  
      out[key] = baseColDict[key];
    });
  
    // 如果原本 colDict 沒有 glass，才補在最後
    if (isSamePointActive()) {
      Object.entries(samePointCols).forEach(([spKey, spLabel]) => {
        if (!out[spKey]) out[spKey] = spLabel;
      });
    }
  
    return out;
  }
  
  // ==============================
  // Modal 基礎
  // ==============================
  function createModalBase(titleText) {
    const overlay = document.createElement("div");
    overlay.className = "density-modal-backdrop";
    overlay.style.position = "fixed";
    overlay.style.inset = "0";
    overlay.style.background = "rgba(0,0,0,0.45)";
    overlay.style.display = "flex";
    overlay.style.alignItems = "center";
    overlay.style.justifyContent = "center";
    overlay.style.zIndex = "9999";

    const box = document.createElement("div");
    box.className = "density-modal";
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
    body.className = "density-modal-body";
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
    footer.className = "density-modal-footer";

    const e = (row.Editor || row.editor) || "";
    const mt = (row.modify_time || row.modifyTime) || "";

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
      const newEditor = getEditor(row);
      const api_row = buildApiRowForDensity(row);

      const patch = {
        ...(commentChanged ? { comment: newComment } : {}),
        ...(actionChanged ? { action: newAction } : {}),
        Editor: newEditor,
        modify_time: newModifyTime
      };

      if (lastExpanded && row.__groupKey) {
        patchExpandedGroup(lastExpanded, row.__groupKey, patch);
        renderBody(lastExpanded, lastColDict);
      }

      patchStateRowsDensity(row, patch);

      try {
        if (!API?.CommentEditor) {
          alert("儲存失敗: API.CommentEditor 不存在");
          return;
        }

        const results = [];

        if (commentChanged) {
          const payloadC = {
            system: "density",
            mode: "comment",
            row: api_row,
            comment: newComment,
            editor: newEditor,
            modify_time: newModifyTime,
          };

          console.log("[Density] group save(comment):", payloadC);

          const respC = await API.CommentEditor(payloadC);
          results.push({ mode: "comment", resp: respC });
        }

        if (actionChanged) {
          const payloadA = {
            system: "density",
            mode: "action",
            row: api_row,
            action: newAction,
            editor: newEditor,
            modify_time: newModifyTime,
          };

          console.log("[Density] group save(action):", payloadA);

          const respA = await API.CommentEditor(payloadA);
          results.push({ mode: "action", resp: respA });
        }

        const allOk = results.every(x => x?.resp?.ok === true);

        if (allOk) {
          if (commentChanged) commentOriginal = newComment;
          if (actionChanged) actionOriginal = newAction;
          alert("儲存成功");
        } else {
          alert("儲存完成，但後端回應不是 ok=true（請看 console）");
          console.warn("[Density] save results:", results);
        }
      } catch (err) {
        console.error("[Density] save error:", err);
        alert("儲存失敗：" + (err?.message || String(err)));
      }
    });
  }

  // ---------- Return 按鈕 ----------
  function ensureReturnButton() {
    const head = $("#aoi-density-table-wrap .table-head");
    if (!head) return null;

    let btn = head.querySelector("#aoi_tableReturn");

    if (!btn) {
      btn = document.createElement("button");
      btn.id = "aoi_tableReturn";
      btn.className = "btn btn-xs btn-secondary";
      btn.textContent = "Return";
      btn.style.float = "right";
      btn.style.marginLeft = "auto";

      head.appendChild(btn);

      btn.addEventListener("click", () => {
        const rows = window.AOI_DENSITY?.getFiltered?.() || [];
        const pd = window.AOI_DENSITY?.state?.paramDict || {};

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

  // ---------- 分群設定 ----------
  function getGroupConf(paramDict) {
    const tg = (paramDict && paramDict.hourlyTable_key_group) || {};
    let mainKeys = Array.isArray(tg.main_group) ? tg.main_group.slice() : [];
  
    if (isSamePointActive()) {
      [ "common_cnt", "common_glass_cnt"].forEach(k => {
        if (!mainKeys.includes(k)) mainKeys.push(k);
      });
    }
  
    const uniCols = Array.isArray(tg.uni_col) ? tg.uni_col.slice() : [];
    const uniSet = new Set([...uniCols, "glass", "glass_size_detail"]);
  
    const ckd = (paramDict && paramDict.chartKeyDict) || {};
    const down = Array.isArray(ckd.down) ? ckd.down : [];
    const timeKeys = new Set(["pi_hour", ...down]);
  
    return { mainKeys, uniSet, timeKeys };
  }

  // ---------- rows 正規化 ----------
  function normalizeRowsForTable(rows) {
    return (rows || []).map(r => {
      if (!r || typeof r !== "object") return r;

      const out = { ...r };

      const gl =
        Array.isArray(out.__glassList) && out.__glassList.length
          ? out.__glassList
          : Array.isArray(out.glass_list) && out.glass_list.length
            ? out.glass_list
            : parseGlassList(out.glass);

      out.__glassList = uniqueStringList(gl);

      const gsd = isObj(out.__glassSizeDetailObj)
        ? out.__glassSizeDetailObj
        : isObj(out.glass_size_detail_obj)
          ? out.glass_size_detail_obj
          : parseGlassSizeDetail(out.glass_size_detail);

      out.__glassSizeDetailObj = gsd;

      return out;
    });
  }

  // ---------- 逐片展開 ----------
  function expandRowsByGlass(rows, paramDict) {
    const { mainKeys, uniSet, timeKeys } = getGroupConf(paramDict);
    const out = [];

    const normRows = normalizeRowsForTable(rows || []);

    normRows.forEach((r) => {
      const gList = Array.isArray(r.__glassList)
        ? uniqueStringList(r.__glassList)
        : parseGlassList(r.glass);

      const gsdObj = r.__glassSizeDetailObj || parseGlassSizeDetail(r.glass_size_detail);

      const sig = mainKeys
        .map(k => {
          if (k === "pi_hour") {
            return k + ":" + safeStr(r.pi_hour_raw || r.pi_hour);
          }
          return k + ":" + safeStr(r[k]);
        })
        .join("|");

      (gList.length ? gList : [""]).forEach((gid, idx) => {
        // 注意：...r 要放前面，避免 r.__glassId 覆蓋目前展開的 gid。
        out.push({
          ...r,
          __groupKey: sig,
          __groupIndex: idx,
          __glassId: gid,
          __glassSizeDetailObj: gsdObj,
          glass: gid
        });
      });
    });

    const deduped = dedupeExpandedGlassRows(out);

    deduped.sort((a, b) => {
      for (const k of mainKeys) {
        const av = a[k] ?? "";
        const bv = b[k] ?? "";

        if (timeKeys.has(k)) {
          const ta = parseYYMMDDHHToTime(av);
          const tb = parseYYMMDDHHToTime(bv);

          if (!isNaN(ta) && !isNaN(tb) && ta !== tb) {
            return ta - tb;
          }

          if (safeStr(av) < safeStr(bv)) return -1;
          if (safeStr(av) > safeStr(bv)) return 1;
        } else {
          if (safeStr(av) < safeStr(bv)) return -1;
          if (safeStr(av) > safeStr(bv)) return 1;
        }
      }

      return safeStr(a.glass).localeCompare(safeStr(b.glass));
    });

    return { rows: deduped, mainKeys, uniSet, timeKeys };
  }

  // ---------- 表頭 ----------
  function renderHeader(colDict) {
    const thead = $("#aoi-density-table thead");
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

  // ---------- 表身 ----------
  function renderBody(expanded, colDict) {
    const tbody = document.querySelector("#aoi-density-table tbody");
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

    // 計算每組 rowSpan
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

      // group action
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

        if (key === "glass") {
          val = safeStr(row.__glassId || row.glass);
        } else if (key === "glass_size_detail") {
          const detail = getPerGlassDetail(row);
          val = detail ? formatSizeDetail(detail) : "";
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

        if (
          /count$/.test(key) ||
          [
            "glass_cnt",
            "def_glass_cnt",
            "defect_cnt",
            "density",
            "tab_total_glass_cnt",
            "tab_total_defect_cnt",
            "tab_total_density",
            "recipe_total_glass_cnt",
            "recipe_total_defect_cnt",
            "recipe_total_density"
          ].includes(key)
        ) {
          td.style.textAlign = "right";
        }

        td.textContent = val == null ? "" : String(val);

        // 新版：滑鼠移到 glass_id 顯示該片 test_time + size detail
        if (key === "glass") {
          const tooltip = buildGlassTooltip(row);

          if (tooltip) {
            td.title = tooltip;
            td.style.cursor = "help";
            td.classList.add("glass-has-tooltip");
          }
        }

        tr.appendChild(td);
      }

      tbody.appendChild(tr);
    }
  }

  // ---------- 對外：預設渲染 ----------
  MOD.Table.render = function (rows, paramDict) {
    const useColDict = buildUseColDict(rows, paramDict);
  
    renderHeader(useColDict);
  
    const expanded = expandRowsByGlass(rows || [], paramDict || {});
  
    lastExpanded = expanded;
    lastColDict = useColDict;
    lastParamDict = paramDict || {};
  
    renderBody(expanded, useColDict);
    showReturn(false);
  };
  
  MOD.Table.showRows = function (rows, paramDict, opts) {
    const useColDict = buildUseColDict(rows, paramDict);
  
    renderHeader(useColDict);
  
    const expanded = expandRowsByGlass(rows || [], paramDict || {});
  
    lastExpanded = expanded;
    lastColDict = useColDict;
    lastParamDict = paramDict || {};
  
    renderBody(expanded, useColDict);
    showReturn(true);
  };

})();