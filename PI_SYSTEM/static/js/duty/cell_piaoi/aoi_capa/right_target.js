// static/js/aoi_capa/right_target.js
(function () {
  const AOI_CAPA = (window.AOI_CAPA = window.AOI_CAPA || {});
  const $ = (sel, root = document) => root.querySelector(sel);

  const TargetMod = (AOI_CAPA.TargetTable = AOI_CAPA.TargetTable || {});

  let currentDay = null;
  let cacheRows = [];
  let isEditMode = false;

  function getCurrentSubTab() {
    return AOI_CAPA.state?.currentSubTab || "Day_Hourly";
  }

  function normalizeDay(v) {
    if (!v) return "";
    if (v instanceof Date) {
      const yyyy = v.getFullYear();
      const mm = String(v.getMonth() + 1).padStart(2, "0");
      const dd = String(v.getDate()).padStart(2, "0");
      return `${yyyy}-${mm}-${dd}`;
    }
    return String(v).slice(0, 10);
  }

  function getRoot() {
    return $("#aoi-capa-right");
  }

  function getPanel() {
    return $("#aoi-capa-right .aoi-capa-target-panel");
  }

  function getTable() {
    return $("#aoi-capa-right .aoi-capa-target-table");
  }

  function getButtons() {
    return {
      editBtn: $("#aoi-capa-target-edit"),
      applyBtn: $("#aoi-capa-target-apply"),
      cancelBtn: $("#aoi-capa-target-cancel"),
    };
  }

  function ensureTableStructure() {
    const table = getTable();
    if (!table) return null;
    if (table.dataset.inited === "1") return table;

    table.dataset.inited = "1";
    table.innerHTML = `
      <thead>
        <tr>
          <th>AOI</th>
          <th>Target_glass</th>
          <th>SPEC(%)</th>
        </tr>
      </thead>
      <tbody></tbody>
    `;
    return table;
  }

  function setPanelVisible(show) {
    const panel = getPanel();
    if (!panel) return;
    panel.style.display = show ? "" : "none";
  }

  function getAoiList() {
    const state = AOI_CAPA.state || {};
    const rows = state.rows || [];
    const set = new Set();
    rows.forEach((r) => {
      if (r?.aoi) set.add(String(r.aoi));
    });
    return Array.from(set).sort();
  }

  function findDayAoiRow(dayStr, aoi) {
    const rows = AOI_CAPA.state?.rows || [];
    const ds = normalizeDay(dayStr);

    let best = null;
    rows.forEach((r) => {
      if (String(r.aoi || "") !== String(aoi || "")) return;
      if (normalizeDay(r.run_day || "") !== ds) return;

      const pi = String(r.pi_type || "").toUpperCase();
      if (pi === "ALL") best = r;
      else if (!best) best = r;
    });

    return best;
  }

  function buildCacheRows(dayStr) {
    const aoiList = getAoiList();
    const dayNorm = normalizeDay(dayStr);

    cacheRows = aoiList.map((aoi) => {
      const row = dayNorm ? findDayAoiRow(dayNorm, aoi) : null;
      return {
        aoi,
        target_glass: row?.target_count != null ? String(row.target_count) : "",
        spec: row?.spec != null ? String(row.spec) : "",
      };
    });
  }

  function updateDateLabel() {
    const panel = getPanel();
    if (!panel) return;

    let dateEl = panel.querySelector(".aoi-capa-target-date");
    const head = panel.querySelector(".aoi-capa-target-panel-head");

    if (!dateEl) {
      dateEl = document.createElement("div");
      dateEl.className = "aoi-capa-target-date";
      if (head) head.insertAdjacentElement("afterend", dateEl);
      else panel.prepend(dateEl);
    }

    dateEl.textContent = currentDay ? `日期：${currentDay}` : "日期：--";
  }

  function renderTableView() {
    ensureTableStructure();
    const tbody = $("#aoi-capa-right .aoi-capa-target-table tbody");
    if (!tbody) return;

    tbody.innerHTML = "";
    updateDateLabel();

    if (!cacheRows.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 3;
      td.textContent = "尚無 AOI Target/SPEC 資料";
      td.style.textAlign = "center";
      tbody.appendChild(tr).appendChild(td);
      return;
    }

    cacheRows.forEach((r) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${r.aoi ?? ""}</td>
        <td>${r.target_glass ?? ""}</td>
        <td>${r.spec ?? ""}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  function renderTableEdit() {
    ensureTableStructure();
    const tbody = $("#aoi-capa-right .aoi-capa-target-table tbody");
    if (!tbody) return;

    tbody.innerHTML = "";
    updateDateLabel();

    cacheRows.forEach((r, idx) => {
      const tr = document.createElement("tr");

      tr.innerHTML = `
        <td>${r.aoi ?? ""}</td>
        <td>
          <input
            type="text"
            class="aoi-capa-rtarget-input"
            value="${r.target_glass ?? ""}"
            data-index="${idx}"
            data-field="target_glass"
          />
        </td>
        <td>
          <input
            type="text"
            class="aoi-capa-rtarget-input"
            value="${r.spec ?? ""}"
            data-index="${idx}"
            data-field="spec"
          />
        </td>
      `;

      tbody.appendChild(tr);
    });
  }

  function setButtonsMode(mode) {
    const { editBtn, applyBtn, cancelBtn } = getButtons();
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
    if (getCurrentSubTab() !== "Day_Hourly") return;
    if (!cacheRows.length) return;
    renderTableEdit();
    setButtonsMode("edit");
  }

  function cancelEdit() {
    renderTableView();
    setButtonsMode("view");
  }

  async function persistTargetTableToBackend() {
    if (!currentDay) return;
    if (!AOI_CAPA.API?.saveCapaConfig) {
      throw new Error("AOI_CAPA.API.saveCapaConfig not found");
    }
  
    const payload = {
      run_day: normalizeDay(currentDay),
      editor: "manual",
      target_table: cacheRows.map((r) => ({
        aoi: r.aoi,
        target_glass: r.target_glass === "" ? null : Number(r.target_glass),
        spec: r.spec === "" ? null : Number(r.spec),
      })),
    };
  
    console.log("payload", payload);
    await AOI_CAPA.API.saveCapaConfig(payload);
  }
  
  async function applyChanges() {
    const tbody = $("#aoi-capa-right .aoi-capa-target-table tbody");
    if (!tbody) return;
  
    const newRows = cacheRows.map((r) => ({ ...r }));
    const inputs = tbody.querySelectorAll(".aoi-capa-rtarget-input");
  
    let hasError = false;
    let errMsg = "";
  
    inputs.forEach((inp) => {
      const idx = Number(inp.dataset.index || "0");
      const field = inp.dataset.field;
      const raw = String(inp.value || "").trim();
  
      if (!field || Number.isNaN(idx) || !newRows[idx]) return;
  
      if (raw !== "" && Number.isNaN(Number(raw))) {
        hasError = true;
        errMsg = `AOI「${newRows[idx].aoi}」的 ${
          field === "target_glass" ? "Target_glass" : "SPEC(%)"
        } 必須是數值`;
        return;
      }
  
      newRows[idx][field] = raw;
    });
  
    if (hasError) {
      alert(errMsg || "請確認輸入內容皆為數值");
      return;
    }
  
    // 關鍵：先把新值寫回 cacheRows
    cacheRows = newRows;
  
    try {
      await persistTargetTableToBackend();
  
      renderTableView();
      setButtonsMode("view");
  
      await AOI_CAPA.Router?.refreshSummary?.();
  
    } catch (err) {
      console.error(err);
      alert(`儲存失敗：${err.message || err}`);
    }
  }
  function bindButtons() {
    const root = getRoot();
    if (!root || root.dataset.rtargetBound === "1") return;
    root.dataset.rtargetBound = "1";

    const { editBtn, applyBtn, cancelBtn } = getButtons();

    editBtn?.addEventListener("click", enterEditMode);
    applyBtn?.addEventListener("click", applyChanges);
    cancelBtn?.addEventListener("click", cancelEdit);
  }

  TargetMod.updateForDay = function (dayStr) {
    bindButtons();
    currentDay = dayStr ? normalizeDay(dayStr) : null;
    buildCacheRows(currentDay);
    renderTableView();
    setButtonsMode("view");
  };

  TargetMod.updateForCurrentFilter = function () {
    bindButtons();
    const today = normalizeDay(new Date());
    currentDay = today;
    buildCacheRows(currentDay);
    renderTableView();
    setButtonsMode("view");
  };

  function hookTable() {
    const TableMod = AOI_CAPA.Table;
    if (!TableMod || TableMod.__rtargetHooked) return;
    if (!TableMod.showDay || !TableMod.showHourly) return;

    const origShowDay = TableMod.showDay.bind(TableMod);
    const origShowHourly = TableMod.showHourly.bind(TableMod);

    TableMod.showDay = function () {
      const ret = origShowDay();
      if (getCurrentSubTab() === "Day_Hourly") {
        setPanelVisible(true);
        TargetMod.updateForCurrentFilter();
      } else {
        setPanelVisible(false);
      }
      return ret;
    };

    TableMod.showHourly = async function (meta) {
      const ret = await origShowHourly(meta);
      if (getCurrentSubTab() === "Day_Hourly") {
        setPanelVisible(true);
        if (meta?.day != null) {
          TargetMod.updateForDay(meta.day);
        }
      } else {
        setPanelVisible(false);
      }
      return ret;
    };

    TableMod.__rtargetHooked = true;
  }

  function syncBySubTab() {
    if (getCurrentSubTab() === "Day_Hourly") {
      setPanelVisible(true);
      if (!isEditMode) TargetMod.updateForCurrentFilter();
    } else {
      setPanelVisible(false);
    }
  }

  document.addEventListener("aoi-capa:data-ready", () => {
    hookTable();
    syncBySubTab();
  });

  document.addEventListener("aoi-capa:subtab-changed", () => {
    hookTable();
    syncBySubTab();
  });

  document.addEventListener("DOMContentLoaded", () => {
    hookTable();
    syncBySubTab();
  });
})();