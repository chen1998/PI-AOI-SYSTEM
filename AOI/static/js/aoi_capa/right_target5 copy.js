 // static/js/aoi_capa/right_target.js
 (function () {
  const AOI_CAPA = (window.AOI_CAPA = window.AOI_CAPA || {});
  const $ = (sel, root = document) => root.querySelector(sel);

  const TargetMod = (AOI_CAPA.TargetTable = AOI_CAPA.TargetTable || {});

  let currentDay = null; // 目前 AOI Target 表格所對應的日期（字串 YYYY-MM-DD）
  let cacheRows = [];    // [{aoi, target_glass, spec}]
  let isEditMode = false;

  // ===== 小工具：標準化日期成 'YYYY-MM-DD' =====
  function normalizeDay(v) {
    if (!v) return "";
    if (v instanceof Date) {
      const yyyy = v.getFullYear();
      const mm = String(v.getMonth() + 1).padStart(2, "0");
      const dd = String(v.getDate()).padStart(2, "0");
      return `${yyyy}-${mm}-${dd}`;
    }
    const s = String(v);
    // 直接取前 10 碼，處理像 '2025-11-01T00:00:00' 或 '2025-11-01 00:00:00'
    return s.slice(0, 10);
  }

  // ===== 取得 AOI 清單：優先 state.uniques.aoi，否則從 rows 算 unique =====
  function getAoiList() {
    const state = window.AOI_CAPA?.state || window.AOI?.state || {};
    const uniq = state.uniques || {};
    if (Array.isArray(uniq.aoi) && uniq.aoi.length) {
      return uniq.aoi.slice();
    }
    const rows = state.rows || [];
    const set = new Set();
    rows.forEach((r) => {
      if (r && r.aoi) set.add(String(r.aoi));
    });
    return Array.from(set).sort();
  }

  // ===== 在 head 下方插入 / 更新日期文字 =====
  function updateDateLabel() {
    const root = $("#aoi_capa-right");
    if (!root) return;
    const box = root.querySelector(".aoi_capa-rtarget");
    if (!box) return;

    let dateEl = box.querySelector(".aoi_capa-rtarget-date");
    const head = box.querySelector(".aoi_capa-rtarget-head");
    const body = box.querySelector(".aoi_capa-rtarget-body");

    if (!dateEl) {
      dateEl = document.createElement("div");
      dateEl.className = "aoi_capa-rtarget-date";
      // 插在 head 下、body 上
      if (head && head.parentNode) {
        head.insertAdjacentElement("afterend", dateEl);
      } else if (body && body.parentNode) {
        body.parentNode.insertBefore(dateEl, body);
      } else {
        box.appendChild(dateEl);
      }
    }

    dateEl.textContent = currentDay
      ? `日期：${currentDay}`
      : "日期：--";
  }

  // ===== 依「日期 + AOI」找對應 summary row（優先 pi_type = 'ALL'） =====
  function findDayAoiRow(dayStr, aoi) {
    const state = window.AOI_CAPA?.state || window.AOI?.state || {};
    const rows = state.rows || [];
    if (!dayStr) return null;

    const ds = normalizeDay(dayStr);
    let best = null;

    rows.forEach((r) => {
      if (!r) return;
      if (String(r.aoi || "") !== String(aoi || "")) return;

      const rd = normalizeDay(r.run_day || "");
      if (rd !== ds) return;

      const pi = String(r.pi_type || "").toUpperCase();
      if (pi === "ALL") {
        // 優先用 ALL，持續覆蓋沒關係
        best = r;
      } else if (!best) {
        // 退而求其次的其他 pi_type
        best = r;
      }
    });

    return best;
  }

  // ===== 產生目前 day 對應的 cacheRows =====
  function buildCacheRows(dayStr) {
    const aoiList = getAoiList();
    const dayNorm = dayStr ? normalizeDay(dayStr) : "";

    cacheRows = aoiList.map((aoi) => {
      const row = dayNorm ? findDayAoiRow(dayNorm, aoi) : null;
      return {
        aoi,
        // 從 summary row 的 target_count / spec 取值
        target_glass:
          row && row.target_count != null ? String(row.target_count) : "",
        spec: row && row.spec != null ? String(row.spec) : "",
      };
    });
  }

  // ===== view mode：畫表格 =====
  function renderTableView() {
    const tbody = $("#aoi_capa-right .aoi_capa-rtarget-table tbody");
    if (!tbody) return;

    tbody.innerHTML = "";

    updateDateLabel();

    if (!cacheRows.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 3;
      td.textContent = currentDay
        ? `【${currentDay}】沒有對應 AOI Target/SPEC 資料`
        : "尚無 AOI Target/SPEC 資料";
      td.style.textAlign = "center";
      td.style.color = "#9ca3b8";
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    cacheRows.forEach((r) => {
      const tr = document.createElement("tr");

      const tdAoi = document.createElement("td");
      tdAoi.textContent = r.aoi;
      tr.appendChild(tdAoi);

      const tdTarget = document.createElement("td");
      tdTarget.textContent = r.target_glass ?? "";
      tr.appendChild(tdTarget);

      const tdSpec = document.createElement("td");
      tdSpec.textContent = r.spec ?? "";
      tr.appendChild(tdSpec);

      tbody.appendChild(tr);
    });
  }

  // ===== edit mode：畫 input =====
  function renderTableEdit() {
    const tbody = $("#aoi_capa-right .aoi_capa-rtarget-table tbody");
    if (!tbody) return;

    tbody.innerHTML = "";

    updateDateLabel();

    cacheRows.forEach((r, idx) => {
      const tr = document.createElement("tr");

      const tdAoi = document.createElement("td");
      tdAoi.textContent = r.aoi;
      tr.appendChild(tdAoi);

      const tdTarget = document.createElement("td");
      const inTarget = document.createElement("input");
      inTarget.type = "text";
      inTarget.className = "aoi_capa-rtarget-input";
      inTarget.value = r.target_glass ?? "";
      inTarget.dataset.index = String(idx);
      inTarget.dataset.field = "target_glass";
      tdTarget.appendChild(inTarget);
      tr.appendChild(tdTarget);

      const tdSpec = document.createElement("td");
      const inSpec = document.createElement("input");
      inSpec.type = "text";
      inSpec.className = "aoi_capa-rtarget-input";
      inSpec.value = r.spec ?? "";
      inSpec.dataset.index = String(idx);
      inSpec.dataset.field = "spec";
      tdSpec.appendChild(inSpec);
      tr.appendChild(tdSpec);

      tbody.appendChild(tr);
    });
  }

  function setButtonsMode(mode) {
    const editBtn = $("#aoi_capa-rt-edit");
    const applyBtn = $("#aoi_capa-rt-apply");
    const cancelBtn = $("#aoi_capa-rt-cancel");
    if (!editBtn || !applyBtn || !cancelBtn) return;

    if (mode === "edit") {
      editBtn.style.display = "none";
      applyBtn.style.display = "";
      cancelBtn.style.display = "";
      isEditMode = true;
    } else {
      editBtn.style.display = "";
      applyBtn.style.display = "none";
      cancelBtn.style.display = "none";
      isEditMode = false;
    }
  }

  function enterEditMode() {
    if (!cacheRows.length) return;
    renderTableEdit();
    setButtonsMode("edit");
  }

  function cancelEdit() {
    renderTableView();
    setButtonsMode("view");
  }

   // ===== 將目前 AOI Target 表格 + 當日 rows 丟給後端 =====
   async function persistTargetTableToBackend() {
    if (!currentDay) {
      console.warn("[AOI_CAPA][TargetTable] currentDay is empty, skip save");
      return;
    }

    const state = window.AOI_CAPA?.state || window.AOI?.state || {};
    const allRows = state.rows || [];
    const dayStr = normalizeDay(currentDay);

    const payload = {
      run_day: dayStr,
      target_table: cacheRows.map((r) => ({
        aoi: r.aoi,
        // 空字串當 null
        target_glass: r.target_glass === "" ? null : Number(r.target_glass),
        spec: r.spec === "" ? null : Number(r.spec),
      })),
      // day_rows: dayRows,  // 你現在先不用就保留註解
    };

    if (!window.AOI_CAPA?.API || !window.AOI_CAPA.API.saveCapaConfig) {
      console.warn("[AOI_CAPA][TargetTable] saveCapaConfig API not found");
      return;
    }

    try {
      //console.log("[AOI_CAPA][TargetTable] POST saveCapaConfig", payload);
      const res = await window.AOI_CAPA.API.saveCapaConfig(payload);
      //console.log("[AOI_CAPA][TargetTable] saveCapaConfig OK:", res);

      // ===== ★ 儲存成功後，更新前端 state.rows 的 target_count / spec =====
      cacheRows.forEach((rowCfg) => {
        const aoi = rowCfg.aoi;
        if (!aoi) return;

        // 找出這一天、這個 AOI 的 summary row（優先 ALL）
        const summaryRow = findDayAoiRow(dayStr, aoi);
        if (!summaryRow) return;

        // 更新 target_count
        if (rowCfg.target_glass === "") {
          summaryRow.target_count = null;
        } else {
          const tg = Number(rowCfg.target_glass);
          summaryRow.target_count = Number.isFinite(tg) ? tg : null;
        }

        // 更新 spec
        if (rowCfg.spec === "") {
          summaryRow.spec = null;
        } else {
          const sp = Number(rowCfg.spec);
          summaryRow.spec = Number.isFinite(sp) ? sp : null;
        }
      });
      /*
      
      

      */
      // ===== ★ 重新畫圖，讓該日 spec 線即時更新 =====
      if (window.AOI_CAPA?.Chart && typeof window.AOI_CAPA.Chart.update === "function") {
        window.AOI_CAPA.Chart.update();
      }
    } catch (err) {
      console.error("[AOI_CAPA][TargetTable] saveCapaConfig failed:", err);
      alert(`AOI Target/SPEC 儲存失敗：${err.message || err}`);
    }
  }

  function applyChanges() {
    const tbody = $("#aoi_capa-right .aoi_capa-rtarget-table tbody");
    if (!tbody) return;

    const newRows = cacheRows.map((r) => ({ ...r }));

    const inputs = tbody.querySelectorAll(".aoi_capa-rtarget-input");
    let hasError = false;
    let errMsg = "";

    inputs.forEach((inp) => {
      const idx = Number(inp.dataset.index || "0");
      const field = inp.dataset.field;
      const raw = inp.value.trim();

      if (!field || Number.isNaN(idx) || !newRows[idx]) return;

      if (raw !== "" && Number.isNaN(Number(raw))) {
        hasError = true;
        errMsg = `AOI「${newRows[idx].aoi}」的 ${
          field === "target_glass" ? "Target_glass" : "SPEC(%)"
        } 必須是數值`;
      } else {
        newRows[idx][field] = raw;
      }
    });

    if (hasError) {
      alert(errMsg || "請確認輸入內容皆為數值");
      return;
    }

    cacheRows = newRows;

    console.log("[AOI_CAPA] AOI Target/SPEC updated (front)", {
      day: currentDay,
      rows: cacheRows,
    });

    persistTargetTableToBackend();

    renderTableView();
    setButtonsMode("view");
  }

  function bindButtons() {
    const root = $("#aoi_capa-right");
    if (!root) return;
    if (root.dataset.rtargetBound === "1") return;
    root.dataset.rtargetBound = "1";

    const editBtn = $("#aoi_capa-rt-edit");
    const applyBtn = $("#aoi_capa-rt-apply");
    const cancelBtn = $("#aoi_capa-rt-cancel");

    editBtn && editBtn.addEventListener("click", enterEditMode);
    applyBtn && applyBtn.addEventListener("click", applyChanges);
    cancelBtn && cancelBtn.addEventListener("click", cancelEdit);
  }

  // ===== 對外：依指定日期更新 AOI Target 表格 =====
  TargetMod.updateForDay = function (dayStr) {
    bindButtons();
    currentDay = dayStr ? normalizeDay(dayStr) : null;
    buildCacheRows(currentDay);
    renderTableView();
    setButtonsMode("view");
  };

  // ===== 對外：初始 / 回日表時 → 顯示「今天」 =====
  TargetMod.updateForCurrentFilter = function () {
    bindButtons();

    // 需求：初始網頁時顯示「當天資料」，沒有就顯示空值
    const today = new Date();
    const todayStr = normalizeDay(today);

    currentDay = todayStr;
    buildCacheRows(currentDay);
    renderTableView();
    setButtonsMode("view");
  };

  // ===== hook Table.showDay / showHourly =====
  function hookTable() {
    const TableMod = window.AOI_CAPA && window.AOI_CAPA.Table;
    if (!TableMod) return;
    if (TableMod.__rtargetHooked) return;

    const origShowDay = TableMod.showDay && TableMod.showDay.bind(TableMod);
    const origShowHourly =
      TableMod.showHourly && TableMod.showHourly.bind(TableMod);

    if (!origShowDay || !origShowHourly) {
      return; // 還沒定義好，之後再試
    }

    TableMod.showDay = function () {
      const ret = origShowDay();
      // 回到日表 → 顯示今天
      TargetMod.updateForCurrentFilter();
      return ret;
    };

    TableMod.showHourly = async function (meta) {
      const ret = await origShowHourly(meta);
      // 點柱狀後：表格應該顯示該柱狀的日期
      if (meta && meta.day != null) {
        TargetMod.updateForDay(meta.day);
      }
      return ret;
    };

    TableMod.__rtargetHooked = true;
    console.log("[AOI_CAPA][TargetTable] hooked Table.showDay/showHourly");
  }

  // 檔案載入時先試一次
  hookTable();

  // Router.refreshSummary 完成會 dispatch "aoi_capa:data-ready"
  document.addEventListener("aoi_capa:data-ready", () => {
    hookTable();
    // 有資料後，先依「今天」顯示一次
    TargetMod.updateForCurrentFilter();
  });

  // DOMContentLoaded 之後再試一次（確保 table.js 已載入）
  document.addEventListener("DOMContentLoaded", () => {
    hookTable();
  });

})();