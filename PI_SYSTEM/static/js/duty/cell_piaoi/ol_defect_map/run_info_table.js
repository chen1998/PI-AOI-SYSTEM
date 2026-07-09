// static/js/ol_defect_map/run_info_table.js
(function () {
  const Bus = window.OLDefectMapBus;
  const State = window.OLDefectMapState;
  const Utils = window.OLDefectMapUtils;

  const theadCols = [
    { text: "選" },
    { text: "時間", key: "time", sortable: true },
    { text: "Recipe", key: "recipe_id" },
    { text: "Glass", key: "sheet_id_chip_id" },
    { text: "S", key: "s", sortable: true },
    { text: "M", key: "m", sortable: true },
    { text: "L", key: "l", sortable: true },
    { text: "O", key: "o", sortable: true },
    { text: "總", key: "total", sortable: true }
  ];

  let currentRows = [];
  let sortKey = "time";
  let sortDir = "desc";

  State.filters = State.filters || {};
  if (!(State.filters.recipes instanceof Set)) {
    State.filters.recipes = new Set();
  }
  if (typeof State.filters.glassQuery !== "string") {
    State.filters.glassQuery = "";
  }

  function enrich(r) {
    const ds = r.defect_summary || {};
    const s = +(r.small_defect_count ?? ds.small_defect_count ?? 0);
    const m = +(r.middle_defect_count ?? ds.middle_defect_count ?? 0);
    const l = +(r.large_defect_count ?? ds.large_defect_count ?? 0);
    const o = +(r.over_defect_count ?? ds.over_defect_count ?? 0);
    const total = +(r.defect_count ?? ds.defect_count ?? (s + m + l + o));

    return { ...r, s, m, l, o, total };
  }

  function toDate(s) {
    return s ? new Date(String(s).replace(" ", "T")) : new Date(0);
  }

  function initRecipeDD(hostId, items, placeholder, onChange) {
    const oldHost = document.getElementById(hostId);
    if (!oldHost) return;

    const values = (items || []).map(v => String(v || "").trim()).filter(Boolean);

    const wrap = document.createElement("div");
    wrap.className = "ol-defect-map-multi-dd";
    wrap.id = hostId;

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ol-defect-map-multi-dd-btn";

    const list = document.createElement("div");
    list.className = "ol-defect-map-multi-dd-list";

    const head = document.createElement("div");
    head.className = "ol-defect-map-multi-dd-head";

    const title = document.createElement("div");
    title.className = "ol-defect-map-multi-dd-title";
    title.textContent = "Recipe";

    const actions = document.createElement("div");
    actions.className = "ol-defect-map-multi-dd-actions";

    const btnToggleAll = document.createElement("button");
    btnToggleAll.type = "button";
    btnToggleAll.className = "ol-defect-map-multi-dd-action";
    btnToggleAll.textContent = "全選";

    const btnClear = document.createElement("button");
    btnClear.type = "button";
    btnClear.className = "ol-defect-map-multi-dd-action";
    btnClear.textContent = "清空";

    actions.append(btnToggleAll, btnClear);
    head.append(title, actions);

    const body = document.createElement("div");
    body.className = "ol-defect-map-multi-dd-body";

    values.forEach((vv) => {
      const lab = document.createElement("label");
      lab.className = "ol-defect-map-multi-dd-option";

      const chk = document.createElement("input");
      chk.type = "checkbox";
      chk.value = vv;
      chk.checked = State.filters.recipes.has(vv);

      const span = document.createElement("span");
      span.textContent = vv;

      lab.append(chk, span);
      body.appendChild(lab);
    });

    function getCheckedValues() {
      return [...body.querySelectorAll('input[type="checkbox"]:checked')].map(c => c.value);
    }

    function syncToggleAllText() {
      const boxes = [...body.querySelectorAll('input[type="checkbox"]')];
      const allChecked = boxes.length > 0 && boxes.every(b => b.checked);
      btnToggleAll.textContent = allChecked ? "取消全選" : "全選";
    }

    function updateButtonText(vals) {
      if (!vals || vals.length === 0) {
        btn.textContent = placeholder || "Recipe（未選）";
        return;
      }
      if (vals.length <= 3) {
        btn.textContent = `Recipe：${vals.join(", ")}`;
        return;
      }
      btn.textContent = `Recipe：已選 ${vals.length} 項`;
    }

    btn.addEventListener("click", () => {
      document.querySelectorAll(".ol-defect-map-multi-dd.open").forEach((el) => {
        if (el !== wrap) el.classList.remove("open");
      });
      wrap.classList.toggle("open");
    });

    document.addEventListener("click", (e) => {
      if (!wrap.contains(e.target)) wrap.classList.remove("open");
    });

    btnToggleAll.addEventListener("click", () => {
      const boxes = [...body.querySelectorAll('input[type="checkbox"]')];
      const allChecked = boxes.length > 0 && boxes.every(b => b.checked);
      boxes.forEach((b) => {
        b.checked = !allChecked;
      });

      const vals = getCheckedValues();
      State.filters.recipes = new Set(vals);
      updateButtonText(vals);
      syncToggleAllText();
      if (typeof onChange === "function") onChange(vals);
    });

    btnClear.addEventListener("click", () => {
      body.querySelectorAll('input[type="checkbox"]').forEach((b) => {
        b.checked = false;
      });

      const vals = [];
      State.filters.recipes = new Set(vals);
      updateButtonText(vals);
      syncToggleAllText();
      if (typeof onChange === "function") onChange(vals);
    });

    body.addEventListener("change", () => {
      const vals = getCheckedValues();
      State.filters.recipes = new Set(vals);
      updateButtonText(vals);
      syncToggleAllText();
      if (typeof onChange === "function") onChange(vals);
    });

    list.append(head, body);
    wrap.append(btn, list);

    oldHost.replaceWith(wrap);

    const initial = [...State.filters.recipes];
    updateButtonText(initial);
    syncToggleAllText();
  }

  function ensureRecipeDropdown(rows) {
    const recipes = Array.from(
      new Set((rows || []).map((r) => String(r.recipe_id || "").trim()).filter(Boolean))
    ).sort();

    initRecipeDD(
      "ol-defect-map-multi-select-recipe",
      recipes,
      "Recipe（未選）",
      () => {
        Bus.emit("filters-changed");
      }
    );
  }

  function passFilters(rows) {
    let r = rows.slice();
  
    const q = String(State.filters.glassQuery || "").toLowerCase().trim();
    if (q) {
      r = r.filter((x) =>
        String(x.sheet_id_chip_id || "").toLowerCase().includes(q)
      );
    }
  
    if (State.filters.recipes instanceof Set && State.filters.recipes.size > 0) {
      r = r.filter((x) => State.filters.recipes.has(String(x.recipe_id || "").trim()));
    }
  
    // 同 glass 自動篩選：保留目前已勾選 glass 的聯集
    if (State.flags.matchSameGlass && State.selectedKeys.length >= 1) {
      const selectedGlassSet = new Set(
        State.selectedKeys
          .map((k) => Utils.parseKey(k).sheet_id_chip_id)
          .map((g) => String(g || "").trim())
          .filter(Boolean)
      );
  
      if (selectedGlassSet.size > 0) {
        r = r.filter((x) =>
          selectedGlassSet.has(String(x.sheet_id_chip_id || "").trim())
        );
      }
    }
  
    // 僅顯示多次量測 glass
    if (State.flags.onlyMultiMeasuredGlass) {
      const glassCountMap = new Map();
  
      r.forEach((row) => {
        const gid = String(row.sheet_id_chip_id || "").trim();
        if (!gid) return;
        glassCountMap.set(gid, (glassCountMap.get(gid) || 0) + 1);
      });
  
      r = r.filter((row) => {
        const gid = String(row.sheet_id_chip_id || "").trim();
        return gid && (glassCountMap.get(gid) || 0) > 1;
      });
    }
  
    return r;
  }

  function sortRows(rows) {
    const arr = rows.slice();

    if (sortKey === "time") {
      arr.sort((a, b) => toDate(a.test_time) - toDate(b.test_time));
    }

    if (["s", "m", "l", "o", "total"].includes(sortKey)) {
      arr.sort((a, b) => (a[sortKey] || 0) - (b[sortKey] || 0));
    }

    if (sortDir === "desc") arr.reverse();
    return arr;
  }

  function renderHead(thead) {
    if (!thead) return;
    thead.innerHTML = "";

    const tr = document.createElement("tr");

    theadCols.forEach((c) => {
      const th = document.createElement("th");
      th.textContent = c.text;

      if (c.sortable) {
        th.classList.add("sortable");
        th.dataset.key = c.key;

        const arrow = document.createElement("span");
        arrow.className = "sort-arrow";
        arrow.textContent = (sortKey === c.key)
          ? (sortDir === "asc" ? " ▲" : " ▼")
          : " ↕";

        th.appendChild(arrow);

        th.addEventListener("click", () => {
          if (sortKey === c.key) {
            sortDir = (sortDir === "asc" ? "desc" : "asc");
          } else {
            sortKey = c.key;
            sortDir = "desc";
          }
          render(currentRows);
        });
      }

      tr.appendChild(th);
    });

    thead.appendChild(tr);
  }

  function renderBody(tbody, rows) {
    if (!tbody) return;
    tbody.innerHTML = "";

    rows.forEach((r) => {
      const rr = enrich(r);
      const key = Utils.keyFromRow(rr);
      State.rowByKey[key] = rr;

      const tr = document.createElement("tr");
      tr.dataset.key = key;

      if (State.selectedKeys.includes(key)) {
        tr.classList.add("selected");
      }

      const tdSel = document.createElement("td");
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.className = "sel";
      cb.checked = State.selectedKeys.includes(key);
      tdSel.appendChild(cb);
      tr.appendChild(tdSel);

      [
        rr.test_time,
        rr.recipe_id,
        rr.sheet_id_chip_id,
        rr.s,
        rr.m,
        rr.l,
        rr.o,
        rr.total
      ].forEach((val) => {
        const td = document.createElement("td");
        td.textContent = (val ?? "");
        tr.appendChild(td);
      });

      function toggle(checked) {
        const exists = State.selectedKeys.includes(key);

        if (checked && !exists) {
          State.selectedKeys.push(key);
        } else if (!checked && exists) {
          State.selectedKeys = State.selectedKeys.filter((k) => k !== key);
        }

        const selCountEl = document.getElementById("ol-defect-map-selected-count");
        if (selCountEl) {
          selCountEl.textContent = String(State.selectedKeys.length || 0);
        }

        tr.classList.toggle("selected", checked);

        Bus.emit("selection-changed", State.selectedKeys.slice());

        if (State.flags.matchSameGlass) {
          render(currentRows);
        }
      }

      cb.addEventListener("change", () => toggle(cb.checked));
      tbody.appendChild(tr);
    });

    const totalEl = document.getElementById("ol-defect-map-total-count");
    if (totalEl) {
      totalEl.textContent = String(rows.length || 0);
    }
  }

  function render(rows) {
    currentRows = rows.slice();

    ensureRecipeDropdown(currentRows);

    const thead = document.getElementById("ol-defect-map-run-info-thead");
    const tbody = document.getElementById("ol-defect-map-run-info-tbody");
    if (!thead || !tbody) return;

    renderHead(thead);

    let filtered = passFilters(currentRows);
    let sorted = sortRows(filtered);

    let didAutoSelect = false;

    if ((!State.selectedKeys || State.selectedKeys.length === 0) && sorted.length > 0) {
      const first = enrich(sorted[0]);
      const firstKey = Utils.keyFromRow(first);

      State.selectedKeys = [firstKey];

      const c = document.getElementById("ol-defect-map-selected-count");
      if (c) c.textContent = "1";

      didAutoSelect = true;
    }

    filtered = passFilters(currentRows);
    sorted = sortRows(filtered);

    renderBody(tbody, sorted);

    if (didAutoSelect) {
      queueMicrotask(() => Bus.emit("selection-changed", State.selectedKeys.slice()));
    }
  }

  Bus.on("render-run-info", (rows) => render(rows || []));
  Bus.on("filters-changed", () => render(currentRows));

  const btnClearSel = document.getElementById("ol-defect-map-btn-clear-selection");
  if (btnClearSel) {
    btnClearSel.addEventListener("click", () => {
      State.selectedKeys = [];

      const selectedCountEl = document.getElementById("ol-defect-map-selected-count");
      if (selectedCountEl) selectedCountEl.textContent = "0";

      document.querySelectorAll('#ol-defect-map-run-info-tbody input.sel').forEach((cb) => {
        cb.checked = false;
      });

      document.querySelectorAll('#ol-defect-map-run-info-tbody tr').forEach((tr) => {
        tr.classList.remove("selected");
      });

      const mapInfo = document.getElementById("ol-defect-map-info-container");
      if (mapInfo) mapInfo.innerHTML = "";

      Bus.emit("selection-changed", []);
    });
  }

  const chkOnlyMultiMeasured = document.getElementById("ol-defect-map-only-multi-measured-glass");
  if (chkOnlyMultiMeasured) {
    chkOnlyMultiMeasured.checked = !!State.flags.onlyMultiMeasuredGlass;

    chkOnlyMultiMeasured.addEventListener("change", () => {
      State.flags.onlyMultiMeasuredGlass = !!chkOnlyMultiMeasured.checked;
      Bus.emit("filters-changed");
    });
  }

})();