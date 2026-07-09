// static/js/aoi_capa/table6.js
(function () {
  const AOI = (window.AOI_CAPA = window.AOI_CAPA || {});
  AOI.Table = AOI.Table || {};

  const $ = (sel, root = document) => root.querySelector(sel);

  const PI_BY_AOI = {
    aoi100: ["API", "BPI", "OTHER", "ALL"],
    aoi200: ["API", "BPI", "OTHER", "ALL"],
    aoi300: ["API", "BPI", "ITO", "OTHER", "ALL"],
  };

  function getCurrentSubTab() {
    return AOI.state?.currentSubTab || "Day_Hourly";
  }

  function normalizeDay(v) {
    if (!v) return "";
    return String(v).slice(0, 10);
  }

  function sortDayRows(rows) {
    return (rows || []).slice().sort((a, b) => {
      const da = String(a.run_day || "");
      const db = String(b.run_day || "");
      if (da < db) return -1;
      if (da > db) return 1;

      const aa = String(a.aoi || "");
      const ab = String(b.aoi || "");
      if (aa < ab) return -1;
      if (aa > ab) return 1;

      const pa = String(a.pi_type || "");
      const pb = String(b.pi_type || "");
      if (pa < pb) return -1;
      if (pa > pb) return 1;

      return 0;
    });
  }

  function getPiListForAoi(aoi) {
    const key = String(aoi || "").toLowerCase();
    return (PI_BY_AOI[key] || ["ALL"]).slice();
  }

  function getMainTable() {
    return $("#aoi-capa-table");
  }

  function getTableHeadTitle() {
    return $("#aoi-capa-table-wrap .aoi-capa-table-title");
  }

  function getDayDetailPanel() {
    return $("#aoi-capa-day-detail");
  }

  function showToast(msg) {
    const toast = $(".toast");
    if (!toast) return;
    toast.textContent = String(msg || "");
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), 3000);
  }

  function ensureDetailTableStructure() {
    const panel = getDayDetailPanel();
    if (!panel) return null;

    const table = panel.querySelector(".aoi-capa-detail-table");
    if (!table) return null;

    if (table.dataset.inited === "1") return table;

    table.dataset.inited = "1";
    table.innerHTML = `
      <tbody>
        <tr><th>Target Count</th><td data-field="target_count"></td></tr>
        <tr><th>Spec</th><td data-field="spec"></td></tr>
        <tr><th>Comment</th><td data-field="comment"></td></tr>
        <tr><th>Action</th><td data-field="action"></td></tr>
        <tr><th>Editor</th><td data-field="editor"></td></tr>
        <tr><th>Modify Time</th><td data-field="modify_time"></td></tr>
      </tbody>
    `;
    return table;
  }

  function ensureDetailPanel() {
    const panel = getDayDetailPanel();
    if (!panel) return null;

    ensureDetailTableStructure();

    if (panel.dataset.bound === "1") return panel;
    panel.dataset.bound = "1";

    const editBtn = $("#aoi-capa-detail-edit", panel);
    const saveBtn = $("#aoi-capa-detail-save", panel);
    const cancelBtn = $("#aoi-capa-detail-cancel", panel);

    function setMode(mode) {
      if (!editBtn || !saveBtn || !cancelBtn) return;
      if (mode === "edit") {
        editBtn.style.display = "none";
        saveBtn.style.display = "";
        cancelBtn.style.display = "";
      } else {
        editBtn.style.display = "";
        saveBtn.style.display = "none";
        cancelBtn.style.display = "none";
      }
    }

    function enterEdit() {
      const commentCell = panel.querySelector('td[data-field="comment"]');
      const actionCell = panel.querySelector('td[data-field="action"]');
      if (!commentCell || !actionCell) return;

      const commentRaw = commentCell.dataset.rawValue ?? commentCell.textContent ?? "";
      const actionRaw = actionCell.dataset.rawValue ?? actionCell.textContent ?? "";

      commentCell.innerHTML = "";
      actionCell.innerHTML = "";

      const taComment = document.createElement("textarea");
      taComment.className = "detail-comment-editor";
      taComment.value = commentRaw;

      const taAction = document.createElement("textarea");
      taAction.className = "detail-comment-editor";
      taAction.value = actionRaw;

      commentCell.appendChild(taComment);
      actionCell.appendChild(taAction);

      setMode("edit");
    }

    function backToView(nextComment, nextAction, keepRaw) {
      const commentCell = panel.querySelector('td[data-field="comment"]');
      const actionCell = panel.querySelector('td[data-field="action"]');
      if (!commentCell || !actionCell) return;

      const finalComment =
        nextComment != null ? nextComment : (commentCell.dataset.rawValue || "");
      const finalAction =
        nextAction != null ? nextAction : (actionCell.dataset.rawValue || "");

      commentCell.innerHTML = "";
      actionCell.innerHTML = "";

      commentCell.textContent = finalComment;
      actionCell.textContent = finalAction;

      if (!keepRaw) {
        commentCell.dataset.rawValue = finalComment;
        actionCell.dataset.rawValue = finalAction;
      }

      setMode("view");
    }

    editBtn?.addEventListener("click", () => {
      enterEdit();
    });

    saveBtn?.addEventListener("click", async () => {
      const aoi = panel.dataset.aoi || "";
      const run_day = panel.dataset.runDay || "";

      const commentCell = panel.querySelector('td[data-field="comment"]');
      const actionCell = panel.querySelector('td[data-field="action"]');
      const taComment = commentCell?.querySelector("textarea");
      const taAction = actionCell?.querySelector("textarea");

      const newComment = taComment ? taComment.value : "";
      const newAction = taAction ? taAction.value : "";

      try {
        await AOI.API.saveCapaConfig({
          aoi,
          run_day,
          comment: newComment,
          action: newAction,
          editor: "manual",
        });

        backToView(newComment, newAction, false);
        showToast("Day Info 已儲存");

        if (AOI.Router?.refreshSummary) {
          const dr = AOI.state?.dateRange;
          const dates = dr ? [dr.start, dr.end] : null;
          await AOI.Router.refreshSummary(dates);
        }
      } catch (err) {
        console.error("[AOI_CAPA] save day detail failed:", err);
        showToast(`Day Info 儲存失敗：${err.message || err}`);
      }
    });

    cancelBtn?.addEventListener("click", () => {
      backToView(null, null, true);
    });

    setMode("view");
    return panel;
  }

  function setDayDetailVisible(show) {
    const panel = getDayDetailPanel();
    if (!panel) return;
    panel.style.display = show ? "flex" : "none";
    panel.classList.toggle("show", !!show);
  }

  function updateDayDetailPanel(row) {
    const panel = ensureDetailPanel();
    if (!panel || !row) return;

    panel.dataset.aoi = String(row.aoi || "");
    panel.dataset.runDay = normalizeDay(row.run_day || "");
    panel.dataset.piType = String(row.pi_type || "ALL");

    const mapping = {
      target_count: row.target_count,
      spec: row.spec,
      comment: row.comment,
      action: row.action,
      editor: row.editor,
      modify_time: row.modify_time,
    };

    Object.entries(mapping).forEach(([field, val]) => {
      const td = panel.querySelector(`td[data-field="${field}"]`);
      if (!td) return;
      const txt = val == null ? "" : String(val);
      td.textContent = txt;
      if (field === "comment" || field === "action") {
        td.dataset.rawValue = txt;
      }
    });

    const editBtn = $("#aoi-capa-detail-edit", panel);
    const saveBtn = $("#aoi-capa-detail-save", panel);
    const cancelBtn = $("#aoi-capa-detail-cancel", panel);
    if (editBtn && saveBtn && cancelBtn) {
      editBtn.style.display = "";
      saveBtn.style.display = "none";
      cancelBtn.style.display = "none";
    }
  }

  function ensureReturnButton() {
    const head = $("#aoi-capa-table-wrap .aoi-capa-table-head");
    if (!head) return null;

    let btn = head.querySelector("#aoi-capa-table-return");
    if (!btn) {
      btn = document.createElement("button");
      btn.id = "aoi-capa-table-return";
      btn.className = "btn btn-xs btn-secondary";
      btn.textContent = "Return";
      btn.style.marginLeft = "8px";
      btn.style.display = "none";

      const title = head.querySelector(".aoi-capa-table-title");
      if (title) {
        title.insertAdjacentElement("afterend", btn);
      } else {
        head.appendChild(btn);
      }

      btn.addEventListener("click", () => {
        AOI.Table.showDay();
      });
    }

    return btn;
  }

  function showReturn(show) {
    const btn = ensureReturnButton();
    if (!btn) return;
    btn.style.display = show ? "" : "none";
  }

  function buildDayHead(thead) {
    thead.innerHTML = "";
    const tr = document.createElement("tr");
    [
      "日期",
      "AOI",
      "PI Type",
      "Total Glass",
      "Target Count",
      "Spec",
      "Day Capa(%)",
      "Comment",
      "Action",
      "Editor",
      "Modify Time",
    ].forEach((name) => {
      const th = document.createElement("th");
      th.textContent = name;
      tr.appendChild(th);
    });
    thead.appendChild(tr);
    return 11;
  }

  function buildHourlyHead(thead, ctx) {
    thead.innerHTML = "";
    const tr = document.createElement("tr");

    const titleTh = document.createElement("th");
    titleTh.textContent = `${ctx.aoi || ""}  ${ctx.run_day || ""}`;
    tr.appendChild(titleTh);

    const orderedHours = [
      "07", "08", "09", "10", "11", "12",
      "13", "14", "15", "16", "17", "18",
      "19", "20", "21", "22", "23", "00",
      "01", "02", "03", "04", "05", "06"
    ];

    orderedHours.forEach((h) => {
      const th = document.createElement("th");
      th.textContent = h;
      tr.appendChild(th);
    });

    const tailTh = document.createElement("th");
    tailTh.textContent =
      ctx.target_count != null ? String(ctx.target_count) : "";
    tailTh.style.background = "#4b5563";
    tailTh.style.color = "#fff";
    tailTh.style.fontWeight = "700";
    tr.appendChild(tailTh);

    thead.appendChild(tr);
    return 26;
  }

  function getFilteredDayRows() {
    const rows = AOI.state?.rows || [];
  
    // 任一下拉選單完全沒勾選 → table 不顯示資料
    if (typeof AOI.hasEmptyFilterSelection === "function" && AOI.hasEmptyFilterSelection()) {
      return [];
    }
  
    const filters =
      typeof AOI.readFiltersFromUI === "function"
        ? AOI.readFiltersFromUI()
        : {};
  
    const aoiSel = filters.aoi || [];
    const piSel = (filters.pi_type || []).map((v) => String(v).toUpperCase());
  
    return sortDayRows(
      rows.filter((r) => {
        const aoi = String(r.aoi || "");
        const pi = String(r.pi_type || "").toUpperCase();
  
        if (aoiSel.length && !aoiSel.includes(aoi)) return false;
        if (piSel.length && !piSel.includes(pi)) return false;
        return true;
      })
    );
  }
  function renderDayTable(rows) {
    const table = getMainTable();
    if (!table) return;

    table.classList.remove("hourly");
    table.classList.add("day");

    const thead = table.querySelector("thead") || table.createTHead();
    const tbody = table.querySelector("tbody") || table.createTBody();

    const colCount = buildDayHead(thead);
    tbody.innerHTML = "";

    if (!rows.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = colCount;
      td.className = "muted";
      td.textContent = "目前條件下沒有日彙總資料";
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    rows.forEach((r, idx) => {
      const tr = document.createElement("tr");
      tr.className = "main-row";
      tr.dataset.index = String(idx);

      const cols = [
        normalizeDay(r.run_day || ""),
        r.aoi || "",
        r.pi_type || "",
        r.total_glass ?? "",
        r.target_count ?? "",
        r.spec ?? "",
        r.real_day_capa != null ? (Number(r.real_day_capa) * 100).toFixed(2) : "",
        r.comment ?? "",
        r.action ?? "",
        r.editor ?? "",
        r.modify_time ?? "",
      ];

      cols.forEach((v) => {
        const td = document.createElement("td");
        td.textContent = v == null ? "" : String(v);
        tr.appendChild(td);
      });

      tr.addEventListener("click", () => {
        updateDayDetailPanel(r);
        setDayDetailVisible(true);
      });

      tbody.appendChild(tr);
    });
  }

  function renderEditSummaryPlaceholder() {
    const table = getMainTable();
    if (!table) return;

    table.classList.remove("hourly");
    table.classList.add("day");

    const thead = table.querySelector("thead") || table.createTHead();
    const tbody = table.querySelector("tbody") || table.createTBody();

    thead.innerHTML = `
      <tr>
        <th>Message</th>
      </tr>
    `;

    tbody.innerHTML = `
      <tr>
        <td>🚧 EditSummary 尚未接後端 API</td>
      </tr>
    `;
  }

  function renderHourlyTable(hourlyRows, ctx) {
    const table = getMainTable();
    if (!table) return;

    table.classList.remove("day");
    table.classList.add("hourly");

    const thead = table.querySelector("thead") || table.createTHead();
    const tbody = table.querySelector("tbody") || table.createTBody();

    const colCount = buildHourlyHead(thead, ctx);
    tbody.innerHTML = "";

    if (!hourlyRows || !hourlyRows.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = colCount;
      td.className = "muted";
      td.textContent = `此日無 hourly 資料（${ctx.run_day} / ${ctx.aoi}）`;
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    const rows = hourlyRows.map((r) => ({
      ...r,
      hour_int: Number(r.hour_int ?? 0),
      hour_label: String(r.hour_label || "").padStart(2, "0"),
      pi_type: String(r.pi_type || "").toUpperCase(),
    }));

    const piList = getPiListForAoi(ctx.aoi);

    const orderedHours = [
      "07", "08", "09", "10", "11", "12",
      "13", "14", "15", "16", "17", "18",
      "19", "20", "21", "22", "23", "00",
      "01", "02", "03", "04", "05", "06"
    ];

    const hourMap = new Map();
    rows.forEach((r) => {
      const h = String(r.hour_label || "").padStart(2, "0");
      const pt = r.pi_type;
      const key = `${pt}|${h}`;
      hourMap.set(key, {
        hour: Number(r.hour ?? 0) || 0,
        real_hour_capa: Number(r.real_hour_capa ?? 0) || 0,
        real_cumu_capa: Number(r.real_cumu_capa ?? 0) || 0,
      });
    });

    const piRowData = {};
    const piRowSum = {};

    piList.forEach((pt) => {
      piRowData[pt] = {};
      piRowSum[pt] = 0;
    });

    orderedHours.forEach((h) => {
      piList.forEach((pt) => {
        let rec = hourMap.get(`${pt}|${h}`);

        if (!rec && pt === "ALL") {
          let sumHour = 0;
          piList.forEach((p0) => {
            if (p0 === "ALL") return;
            const r0 = hourMap.get(`${p0}|${h}`);
            if (r0) sumHour += r0.hour;
          });
          rec = { hour: sumHour, real_hour_capa: 0, real_cumu_capa: 0 };
        }

        rec = rec || { hour: 0, real_hour_capa: 0, real_cumu_capa: 0 };

        piRowData[pt][h] = rec.hour;
        piRowSum[pt] += rec.hour;
      });
    });

    const capaRow = {};
    const cumuRow = {};
    let capaSum = 0;
    let cumu = 0;

    orderedHours.forEach((h) => {
      const rec = hourMap.get(`ALL|${h}`) || null;
      if (!rec) {
        capaRow[h] = null;
        cumuRow[h] = null;
        return;
      }

      let cp = Number(rec.real_hour_capa || 0) * 100;
      cp = Math.round(cp * 100) / 100;
      capaRow[h] = cp;
      capaSum += cp;

      cumu += cp;
      cumuRow[h] = Math.round(cumu * 100) / 100;
    });

    const targetRow = {};
    const specValNum = Number(ctx.spec);
    const hasSpec = ctx.spec != null && !Number.isNaN(specValNum);

    if (hasSpec) {
      const perHour = specValNum / 24;
      orderedHours.forEach((h, i) => {
        targetRow[h] = Math.round(perHour * (i + 1) * 100) / 100;
      });
    }

    piList.forEach((pt) => {
      const tr = document.createElement("tr");
      const labelTd = document.createElement("td");
      labelTd.textContent = pt;
      tr.appendChild(labelTd);

      orderedHours.forEach((h) => {
        const td = document.createElement("td");
        td.textContent = piRowData[pt][h] ?? 0;
        tr.appendChild(td);
      });

      const sumTd = document.createElement("td");
      sumTd.textContent = piRowSum[pt] || 0;
      tr.appendChild(sumTd);

      tbody.appendChild(tr);
    });

    {
      const tr = document.createElement("tr");
      const labelTd = document.createElement("td");
      labelTd.textContent = "capa(%)";
      tr.appendChild(labelTd);

      orderedHours.forEach((h) => {
        const td = document.createElement("td");
        td.textContent = capaRow[h] == null ? "" : Number(capaRow[h]).toFixed(2);
        tr.appendChild(td);
      });

      const sumTd = document.createElement("td");
      sumTd.textContent = capaSum ? Number(capaSum).toFixed(2) : "";
      tr.appendChild(sumTd);

      tbody.appendChild(tr);
    }

    {
      const tr = document.createElement("tr");
      const labelTd = document.createElement("td");
      labelTd.textContent = "cumu_capa(%)";
      tr.appendChild(labelTd);

      orderedHours.forEach((h) => {
        const td = document.createElement("td");
        td.textContent = cumuRow[h] == null ? "" : Number(cumuRow[h]).toFixed(2);
        tr.appendChild(td);
      });

      const sumTd = document.createElement("td");
      const lastVal = cumuRow[orderedHours[orderedHours.length - 1]];
      sumTd.textContent = lastVal == null ? "" : Number(lastVal).toFixed(2);
      tr.appendChild(sumTd);

      tbody.appendChild(tr);
    }

    if (hasSpec) {
      const tr = document.createElement("tr");
      const labelTd = document.createElement("td");
      labelTd.textContent = "cumu_target_capa(%)";
      tr.appendChild(labelTd);

      orderedHours.forEach((h) => {
        const td = document.createElement("td");
        td.textContent = Number(targetRow[h]).toFixed(2);
        tr.appendChild(td);
      });

      const sumTd = document.createElement("td");
      sumTd.textContent = specValNum.toFixed(2);
      tr.appendChild(sumTd);

      tbody.appendChild(tr);
    }
  }

  AOI.Table.showDay = function () {
    const rows = getFilteredDayRows();
    AOI.state.baseDayRows = rows.slice();

    const title = getTableHeadTitle();
    if (title) title.textContent = "CAPA Table";

    renderDayTable(rows);
    showReturn(false);

    if (getCurrentSubTab() === "Day_Hourly") {
      setDayDetailVisible(false);
    }
  };

  AOI.Table.showEditSummary = function () {
    const title = getTableHeadTitle();
    if (title) title.textContent = "EditSummary";

    renderEditSummaryPlaceholder();
    showReturn(false);
    setDayDetailVisible(false);
  };

  AOI.Table.showHourly = async function (meta) {
    if (!meta || !meta.aoi || !meta.day) return;

    const aoi = meta.aoi;
    const run_day = normalizeDay(meta.day);

    AOI.state.lastHourlyMeta = {
      aoi,
      run_day,
      pi_type: "ALL",
    };

    const cacheKey = `${aoi}|${run_day}|__ALL__`;

    let hourlyRows = AOI.state.hourlyCache?.[cacheKey];
    if (!hourlyRows) {
      try {
        const res = await AOI.API.fetchHourly({
          aoi,
          pi_type: null,
          run_day,
        });
        hourlyRows = Array.isArray(res?.rows) ? res.rows : [];
        AOI.state.hourlyCache = AOI.state.hourlyCache || {};
        AOI.state.hourlyCache[cacheKey] = hourlyRows;
      } catch (err) {
        console.error("[AOI_CAPA] fetchHourly failed:", err);
        showToast(`hourly 讀取失敗：${err.message || err}`);
        return;
      }
    }

    const dayRows = AOI.state.rows || [];
    const match =
      dayRows.find(
        (r) =>
          String(r.aoi || "") === String(aoi) &&
          normalizeDay(r.run_day || "") === run_day &&
          String(r.pi_type || "").toUpperCase() === "ALL"
      ) ||
      dayRows.find(
        (r) =>
          String(r.aoi || "") === String(aoi) &&
          normalizeDay(r.run_day || "") === run_day
      );

    if (match) {
      updateDayDetailPanel(match);
      setDayDetailVisible(true);
    } else {
      setDayDetailVisible(false);
    }

    const title = getTableHeadTitle();
    if (title) title.textContent = "Hourly Table";

    renderHourlyTable(hourlyRows, {
      aoi,
      run_day,
      pi_type: "ALL",
      spec: match?.spec ?? null,
      target_count: match?.target_count ?? null,
    });

    showReturn(true);
  };

  AOI.Table.build = function () {
    const subTab = getCurrentSubTab();
    if (subTab === "EditSummary") {
      AOI.Table.showEditSummary();
      return;
    }
    AOI.Table.showDay();
  };
})();