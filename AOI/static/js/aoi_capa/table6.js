// static/js/aoi_capa/table.js
(function () {
  const AOI = (window.AOI_CAPA = window.AOI_CAPA || {});
  AOI.Table = AOI.Table || {};

  const $ = (sel, root = document) => root.querySelector(sel);

  // ---------- 共用：排序 day rows ----------
  function sortDayRows(rows) {
    return (rows || []).slice().sort((a, b) => {
      const da = a.run_day || "";
      const db = b.run_day || "";
      if (da < db) return -1;
      if (da > db) return 1;
      const aa = a.aoi || "";
      const ab = b.aoi || "";
      if (aa < ab) return -1;
      if (aa > ab) return 1;
      const pa = a.pi_type || "";
      const pb = b.pi_type || "";
      if (pa < pb) return -1;
      if (pa > pb) return 1;
      return 0;
    });
  }

  // ---------- AOI 對應固定 pi_type 列表 ----------
  const PI_BY_AOI = {
    aoi100: ["API", "BPI", "ALL"],
    aoi200: ["API", "BPI", "ALL"],
    aoi300: ["API", "BPI", "ITO", "ALL"],
  };

  function getPiListForAoi(aoi) {
    const key = String(aoi || "").toLowerCase();
    const fixed = PI_BY_AOI[key];
    if (fixed) return fixed.slice();

    // fallback：如果未來有其它 AOI，就從資料掃出來
    const rows = AOI.state?.rows || [];
    const set = new Set();
    rows.forEach((r) => {
      if (String(r.aoi || "").toLowerCase() === key && r.pi_type) {
        set.add(String(r.pi_type).toUpperCase());
      }
    });
    return Array.from(set).sort();
  }

  // ---------- Day Detail Panel：顯示 target/spec/comment/editor ----------
  function ensureDetailPanel() {
    const panel = $("#aoi_capa-day-detail");
    if (!panel) return null;

    // 只綁一次事件
    if (panel.dataset.bound === "1") return panel;
    panel.dataset.bound = "1";

    const editBtn   = $("#capa-detail-edit", panel);
    const saveBtn   = $("#capa-detail-save", panel);
    const cancelBtn = $("#capa-detail-cancel", panel);

    const commentCell = panel.querySelector('td[data-field="comment"]');

    function setMode(mode) {
      // mode: "view" | "edit"
      if (mode === "edit") {
        editBtn.style.display   = "none";
        saveBtn.style.display   = "";
        cancelBtn.style.display = "";
      } else {
        editBtn.style.display   = "";
        saveBtn.style.display   = "none";
        cancelBtn.style.display = "none";
      }
    }

    function enterEdit() {
      if (!commentCell) return;
      const currentText = commentCell.dataset.rawValue ?? commentCell.textContent;
      commentCell.innerHTML = "";
      const ta = document.createElement("textarea");
      ta.className = "detail-comment-editor";
      ta.value = currentText || "";
      commentCell.appendChild(ta);
      setMode("edit");
    }

    function backToView(newText, keepRaw) {
      if (!commentCell) return;
      commentCell.innerHTML = "";
      const val = newText != null ? newText : (commentCell.dataset.rawValue || "");
      commentCell.textContent = val;           // 這裡保留 \n，交給 CSS 的 pre-line 顯示
      if (!keepRaw) {
        commentCell.dataset.rawValue = val;
      }
      setMode("view");
    }

    // 編輯
    editBtn?.addEventListener("click", () => {
      enterEdit();
    });

    // 儲存
    saveBtn?.addEventListener("click", async () => {
      if (!commentCell) return;
      const ta = commentCell.querySelector("textarea");
      const newVal = ta ? ta.value : "";

      // 取得當前 row identity
      const aoi     = panel.dataset.aoi || "";
      const run_day = panel.dataset.runDay || "";
      const pi_type = panel.dataset.piType || "";

      console.log("[AOI_CAPA] Save comment:", {
        aoi,
        run_day,
        pi_type,
        comment: newVal
      });

      // 先更新畫面（使用者馬上看到）
      backToView(newVal, false);

      // 丟給後端（這邊後端會把這一天這個 AOI 的所有 row 都改 comment + editor）
      try {
        if (AOI.API && AOI.API.saveCapaConfig) {
          const payload = {
            aoi,
            run_day,
            comment: newVal,
            // editor 前綴看你要不要給，目前由後端自動補時間戳
          };

          console.log("[AOI_CAPA][DayDetail] POST saveCapaConfig", payload);
          const res = await AOI.API.saveCapaConfig(payload);
          console.log("[AOI_CAPA][DayDetail] saveCapaConfig OK:", res);
        }
      } catch (err) {
        console.error("[AOI_CAPA][DayDetail] saveCapaConfig failed:", err);
        alert(`Day Info 儲存失敗：${err.message || err}`);
        return;
      }

      // ★ 後端更新成功後，重新抓 summary，讓 Day Table / Chart / Day Info 都跟 DB 同步
      try {
        if (AOI.Router && typeof AOI.Router.refreshSummary === "function") {
          const st = AOI.state || {};
          const dr = st.dateRange;
          const dates = dr ? [dr.start, dr.end] : null;

          await AOI.Router.refreshSummary(dates);

          // summary 重新載入後，找回對應那一筆，更新右側 Day Info 卡片
          const rows = AOI.state?.rows || [];
          const match =
            rows.find(
              (r) =>
                String(r.aoi || "") === String(aoi) &&
                String(r.run_day || "") === String(run_day) &&
                String(r.pi_type || "") === String(pi_type)
            ) ||
            rows.find(
              (r) =>
                String(r.aoi || "") === String(aoi) &&
                String(r.run_day || "") === String(run_day)
            );

          if (match) {
            updateDayDetailPanel(match);
            setDayDetailVisible(true);
          }
        }
      } catch (e) {
        console.warn("[AOI_CAPA] refreshSummary after comment failed:", e);
      }
    });


    // 取消
    cancelBtn?.addEventListener("click", () => {
      backToView(null, true); // 用原本 rawValue
    });

    // 初始為 view 模式
    setMode("view");

    return panel;
  }

  // 控制 Day Detail 顯示/隱藏
  function setDayDetailVisible(show) {
    const panel = $("#aoi_capa-day-detail");
    if (!panel) return;
    // ⭐ 重要：必須給明確值，才能覆蓋 CSS 中的 display:none
    panel.style.display = show ? "flex" : "none";
  }

  // 寫入 detail panel 的值
  function updateDayDetailPanel(row) {
    const panel = ensureDetailPanel();
    if (!panel || !row) return;

    const aoi     = row.aoi || "";
    const run_day = row.run_day != null ? String(row.run_day) : "";
    const pt      = row.pi_type || "";

    panel.dataset.aoi    = String(aoi);
    panel.dataset.runDay = run_day;
    panel.dataset.piType = String(pt);

    const targetCell  = panel.querySelector('td[data-field="target_count"]');
    const specCell    = panel.querySelector('td[data-field="spec"]');
    const commentCell = panel.querySelector('td[data-field="comment"]');
    const editorCell  = panel.querySelector('td[data-field="editor"]');

    if (targetCell) {
      targetCell.textContent = row.target_count != null ? String(row.target_count) : "";
    }
    if (specCell) {
      specCell.textContent = row.spec != null ? String(row.spec) : "";
    }
    if (commentCell) {
      const txt = row.comment != null ? String(row.comment) : "";
      commentCell.dataset.rawValue = txt;
      commentCell.textContent = txt;  // 同樣保留 \n
    }
    if (editorCell) {
      editorCell.textContent = row.editor != null ? String(row.editor) : "";
    }

    // 回到檢視模式（若剛好在編輯中）
    const editBtn   = $("#capa-detail-edit", panel);
    const saveBtn   = $("#capa-detail-save", panel);
    const cancelBtn = $("#capa-detail-cancel", panel);
    if (editBtn && saveBtn && cancelBtn) {
      editBtn.style.display   = "";
      saveBtn.style.display   = "none";
      cancelBtn.style.display = "none";
    }
  }

  // 初始 day rows：只看 AOI.state.rows，不吃任何 filter
  function getAllDayRows() {
    const rows = AOI.state?.rows || [];
    if (!rows.length) return [];
    return sortDayRows(rows);
  }

  // ---------- Return 按鈕 ----------
  function ensureReturnButton() {
    const head = $("#aoi_capa-table-wrap .table-head");
    if (!head) return null;

    let btn = head.querySelector("#aoi_capa_tableReturn");
    if (!btn) {
      btn = document.createElement("button");
      btn.id = "aoi_capa_tableReturn";
      btn.className = "btn btn-xs btn-secondary";
      btn.textContent = "Return";
      // 放在左邊：插在 title 後面
      const title = head.querySelector(".table-title");
      if (title && title.nextSibling) {
        head.insertBefore(btn, title.nextSibling);
      } else {
        head.appendChild(btn);
      }
      btn.style.marginLeft = "8px";

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
    btn.disabled = !show;
  }

  // ---------- Day Table 表頭 ----------
  function buildDayHead(thead) {
    thead.innerHTML = "";
    const tr = document.createElement("tr");
    const cols = [
      "日期",
      "AOI",
      "PI Type",
      "Total Glass",
      "Target Count",
      "Spec",
      "Day Capa(%)",
      "Comment",
      "Editor"
    ];
    cols.forEach((name) => {
      const th = document.createElement("th");
      th.textContent = name;
      tr.appendChild(th);
    });
    thead.appendChild(tr);
    return cols.length;
  }

  function buildHourlyHead(thead, ctx) {
    thead.innerHTML = "";
    const tr = document.createElement("tr");

    // 第一欄：AOI + 日期
    const titleTh = document.createElement("th");
    const dayStr =
      ctx && ctx.run_day != null ? String(ctx.run_day) : "";
    titleTh.textContent = `${ctx.aoi || ""}  ${dayStr}`;
    tr.appendChild(titleTh);

    // 0 ~ 23 小時欄
    for (let h = 0; h < 24; h++) {
      const th = document.createElement("th");
      th.textContent = `${h}h`; // 要 00/01 可以改 padStart
      tr.appendChild(th);
    }

    // 最右側 Target Count 欄
    const specTh = document.createElement("th");
    const specVal = ctx && ctx.target_count != null ? ctx.target_count : null;
    specTh.textContent = specVal != null ? `${specVal} ` : "null";
    specTh.style.background = "#4b5563";
    specTh.style.color = "#ffffff";
    specTh.style.fontWeight = "700";
    specTh.style.whiteSpace = "nowrap";
    tr.appendChild(specTh);

    thead.appendChild(tr);
    return 1 + 24 + 1; // AOI+日 + 24 小時 + 最右欄
  }

  // ---------- 渲染 Day Table ----------
  function renderDayTable(rows) {
    const table = $("#aoi_capa-table");
    if (!table) return;

    const thead = table.querySelector("thead") || table.createTHead();
    const tbody = table.querySelector("tbody") || table.createTBody();

    const colCount = buildDayHead(thead);
    tbody.innerHTML = "";

    if (!rows || !rows.length) {
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
        r.run_day || "",
        r.aoi || "",
        r.pi_type || "",
        r.total_glass ?? "",
        r.target_count ?? "",
        r.spec ?? "",
        (r.real_day_capa * 100).toFixed(2) ?? "",
        r.comment ?? "",
        r.editor ?? ""
      ];
      cols.forEach((v) => {
        const td = document.createElement("td");
        td.textContent = v == null ? "" : String(v);  // 若字串含 \n，會畫成多行
        tr.appendChild(td);
      });

      tbody.appendChild(tr);
    });
  }

    // ---------- 渲染 Hourly Table（整張表改成 hourly） ----------
    function renderHourlyTable(hourlyRows, ctx) {
      const table = $("#aoi_capa-table");
      if (!table) return;
  
      const thead = table.querySelector("thead") || table.createTHead();
      const tbody = table.querySelector("tbody") || table.createTBody();
  
      const colCount = buildHourlyHead(thead, ctx);
      tbody.innerHTML = "";
  
      if (!hourlyRows || !hourlyRows.length) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = colCount;
        td.className = "muted";
        td.textContent = `此日無 hourly 資料（${ctx.run_day} / ${ctx.aoi} / ${ctx.pi_type || "ALL"}）`;
        tr.appendChild(td);
        tbody.appendChild(tr);
        return;
      }
  
      // 正規化 hour_int / pi_type
      const rows = hourlyRows.map((r) => ({
        ...r,
        hour_int: Number(r.hour_int ?? r.hour ?? 0),
        pi_type: (r.pi_type || "").toString().toUpperCase(),
      }));
  
      // 固定 pi_type 列表：依 AOI
      const piList = getPiListForAoi(ctx.aoi);
  
      // key = `${pi_type}|${hour}` 的彙總
      const hourMap = new Map();
      rows.forEach((r) => {
        const h = Number(r.hour_int ?? 0);
        const pt = r.pi_type || "";
        const key = `${pt}|${h}`;
  
        const prev =
          hourMap.get(key) || {
            hour_glass: 0,
            real_hour_capa: 0,
            real_cumu_capa: 0,
          };
  
        const addHour = Number(r.hour ?? 0) || 0;
        const addHrCapa = Number(r.real_hour_capa ?? 0) || 0;
        const addCumuCapa = Number(r.real_cumu_capa ?? 0) || 0;
  
        hourMap.set(key, {
          hour_glass: prev.hour_glass + addHour,
          real_hour_capa: prev.real_hour_capa + addHrCapa,
          real_cumu_capa: prev.real_cumu_capa + addCumuCapa,
        });
      });
  
      // -------- pi_type row 0~23 & 加總 --------
      const piRowData = {};
      const piRowSum = {};
      piList.forEach((pt) => {
        piRowData[pt] = {};
        piRowSum[pt] = 0;
      });
  
      for (let h = 0; h < 24; h++) {
        piList.forEach((pt) => {
          let rec;
  
          if (pt === "ALL") {
            rec = hourMap.get(`ALL|${h}`);
            if (!rec) {
              let sumHour = 0;
              piList.forEach((p0) => {
                if (p0 === "ALL") return;
                const r0 = hourMap.get(`${p0}|${h}`);
                if (r0) sumHour += r0.hour_glass;
              });
              rec = {
                hour_glass: sumHour,
                real_hour_capa: 0,
                real_cumu_capa: 0,
              };
            }
          } else {
            rec =
              hourMap.get(`${pt}|${h}`) || {
                hour_glass: 0,
                real_hour_capa: 0,
                real_cumu_capa: 0,
              };
          }
  
          const v = rec.hour_glass || 0;
          piRowData[pt][h] = v;
          piRowSum[pt] += v;
        });
      }
  
      // -------- capa / cumu_capa（轉成百分比） --------
      // -------- capa / cumu_capa（轉成百分比，先乘 100 再四捨五入） --------
      const capaRow = {};
      let capaSum = 0;
      const cumuRow = {};
      let cumu = 0;            // 用 capa(%) 顯示值逐步累加
      const primaryPt = (ctx.pi_type || "ALL").toUpperCase();

      for (let h = 0; h < 24; h++) {
        const rec =
          hourMap.get(`ALL|${h}`) || hourMap.get(`${primaryPt}|${h}`);

        if (!rec) {
          capaRow[h] = null;
          cumuRow[h] = null;
          continue;
        }

        // 原始小數（0~1）
        const c = Number(rec.real_hour_capa ?? 0);

        // 先乘 100 再四捨五入到小數 2 位
        let cp = c * 100;                    // 變成百分比
        cp = Math.round(cp * 100) / 100;     // 四捨五入到 2 位小數

        capaRow[h] = cp;
        capaSum += cp;

        // cumu_capa(%) 改為用 capa(%) 的顯示值累加
        cumu += cp;
        const cu = Math.round(cumu * 100) / 100;  // 一樣保留 2 位小數
        cumuRow[h] = cu;
      }

      const lastCumu = cumu;
  
      // -------- cumu_target_capa --------
      const specValRaw = ctx.spec;
      const specValNum = Number(specValRaw);
      const hasSpec = specValRaw != null && !Number.isNaN(specValNum);
      const targetRow = {};
  
      if (hasSpec) {
        const perHour = specValNum / 24;
        for (let h = 0; h < 24; h++) {
          const v = perHour * (h + 1);
          targetRow[h] = v;
        }
      }
  
      // -------- pi_type rows --------
      piList.forEach((pt) => {
        const tr = document.createElement("tr");
  
        const labelTd = document.createElement("td");
        labelTd.textContent = pt;
        labelTd.style.fontWeight = pt === "ALL" ? "600" : "normal";
        tr.appendChild(labelTd);
  
        for (let h = 0; h < 24; h++) {
          const td = document.createElement("td");
          const v = piRowData[pt][h] ?? 0;
          td.textContent = v;
          // 對齊交給 CSS
          tr.appendChild(td);
        }
  
        const sumTd = document.createElement("td");
        sumTd.textContent = piRowSum[pt] || 0;
        sumTd.style.fontWeight = "600";
        tr.appendChild(sumTd);
  
        tbody.appendChild(tr);
      });
  
      // -------- capa row --------
      {
        const tr = document.createElement("tr");
        const labelTd = document.createElement("td");
        labelTd.textContent = "capa(%)";
        labelTd.style.fontWeight = "600";
        tr.appendChild(labelTd);
  
        for (let h = 0; h < 24; h++) {
          const td = document.createElement("td");
          const v = capaRow[h];
          td.textContent = v == null ? "" : Number(v).toFixed(2);
          tr.appendChild(td);
        }
  
        const sumTd = document.createElement("td");
        sumTd.textContent = capaSum ? Number(capaSum).toFixed(2) : "";
        sumTd.style.fontWeight = "600";
        tr.appendChild(sumTd);
  
        tbody.appendChild(tr);
      }
      /*
      
      */
  
      // -------- cumu_capa row --------
      {
        const tr = document.createElement("tr");
        const labelTd = document.createElement("td");
        labelTd.textContent = "cumu_capa(%)";
        labelTd.style.fontWeight = "600";
        tr.appendChild(labelTd);
  
        for (let h = 0; h < 24; h++) {
          const td = document.createElement("td");
          const v = cumuRow[h];
          td.textContent = v == null ? "" : Number(v).toFixed(2);
          tr.appendChild(td);
        }
  
        const sumTd = document.createElement("td");
        sumTd.textContent =
          lastCumu == null ? "" : Number(lastCumu).toFixed(2);
        sumTd.style.fontWeight = "600";
        tr.appendChild(sumTd);
  
        tbody.appendChild(tr);
      }
  
      // -------- cumu_target_capa row --------
      if (hasSpec) {
        const tr = document.createElement("tr");
        const labelTd = document.createElement("td");
        labelTd.textContent = "cumu_target_capa(%)";
        labelTd.style.fontWeight = "600";
        labelTd.style.color = "#facc15";
        tr.appendChild(labelTd);
  
        for (let h = 0; h < 24; h++) {
          const td = document.createElement("td");
          const v = targetRow[h];
          td.textContent = v == null ? "" : Number(v).toFixed(2);
          tr.appendChild(td);
        }
  
        const sumTd = document.createElement("td");
        sumTd.textContent = specValNum.toFixed(2);
        sumTd.style.fontWeight = "700";
        sumTd.style.background = "#4b5563";
        sumTd.style.color = "#fff";
        tr.appendChild(sumTd);
  
        tbody.appendChild(tr);
      }
    }
  // ---------- 對外：顯示 Day Table（初始 + Return） ----------
  AOI.Table.showDay = function () {
    AOI.state = AOI.state || {};
    if (!Array.isArray(AOI.state.baseDayRows) || !AOI.state.baseDayRows.length) {
      AOI.state.baseDayRows = getAllDayRows();
    }
    const rows = AOI.state.baseDayRows || getAllDayRows();
    renderDayTable(rows);
    showReturn(false);

    // 回到日表時，隱藏右側 Day Info
    setDayDetailVisible(false);
  };

  // Router 目前會叫 build()，讓它等同 showDay()
  AOI.Table.build = function () {
    AOI.Table.showDay();
  };

  // ---------- 對外：由 Chart 點擊呼叫，顯示 Hourly Table ----------
  AOI.Table.showHourly = async function (meta) {
      if (!meta || !meta.aoi || !meta.day) return;
  
      const aoi     = meta.aoi;
      const run_day = meta.day;
  
      AOI.state.lastHourlyMeta = {
        aoi,
        run_day,
        // 這邊我們固定用 "ALL"，下面 renderHourlyTable 也是用 "ALL"
        pi_type: "ALL"
      };
  
    const pt = "ALL";
    AOI.state = AOI.state || {};
    AOI.state.hourlyCache = AOI.state.hourlyCache || {};

    // ★ cache key 也固定成 __ALL__，避免被舊的單一 pi_type cache 汙染
    const cacheKey = `${aoi}|${run_day}|__ALL__`;

    let hourlyRows = AOI.state.hourlyCache[cacheKey];
    if (!hourlyRows) {
      try {
        const res = await AOI.API.fetchHourly({
          aoi,
          // ★ 這裡一律給 null → 後端回傳該日所有 pi_type（含 ALL）
          pi_type: null,
          run_day
        });
        hourlyRows = res.rows || [];
        AOI.state.hourlyCache[cacheKey] = hourlyRows;
      } catch (err) {
        console.error("[AOI_CAPA] fetchHourly failed:", err);
        const toast = document.querySelector(".toast");
        if (toast) {
          toast.textContent = `hourly 讀取失敗：${err.message || err}`;
          toast.classList.add("show");
          setTimeout(() => toast.classList.remove("show"), 3000);
        }
        return;
      }
    }

    // 從 day rows 抓對應的 row（為了 spec / target / comment / editor）
    let specVal = null;
    let target_count = null;
    let match = null;

    const dayRows = AOI.state.rows || [];
    if (Array.isArray(dayRows) && dayRows.length) {
      const dayStr = String(run_day);

      // ★ 先找 ALL 這列（整體設定），找不到再退回任意 pi_type（例如 API）
      match =
        dayRows.find(
          (r) =>
            String(r.aoi || "") === String(aoi) &&
            String(r.run_day || "") === dayStr &&
            String(r.pi_type || "").toUpperCase() === "ALL"
        ) ||
        dayRows.find(
          (r) =>
            String(r.aoi || "") === String(aoi) &&
            String(r.run_day || "") === dayStr
        );

      if (match && match.spec != null) {
        const num = Number(match.spec);
        specVal = Number.isFinite(num) ? num : match.spec;
      }

      if (match && match.target_count != null) {
        const num = Number(match.target_count);
        target_count = Number.isFinite(num) ? num : match.target_count;
      }
    }

    //  更新右側 Day Info 卡片 & 顯示/隱藏
    if (match) {
      updateDayDetailPanel(match);
      setDayDetailVisible(true);
    } else {
      setDayDetailVisible(false);
    }

    //  畫 hourly table
    // ★ ctx.pi_type 也固定給 "ALL"，讓 capa/cumu 以 ALL 為主
    renderHourlyTable(hourlyRows, {
      aoi,
      run_day,
      pi_type: "ALL",
      spec: specVal,
      target_count: target_count
    });
    showReturn(true);
  };

})();