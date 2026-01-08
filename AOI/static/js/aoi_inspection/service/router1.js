(function () {
  const ns = {};
  window.AOI_INSPECTION_Router = ns;

  let isFetching = false;
  ns.cachedSpan = null;
  ns.userAppliedDate = false;
  ns.justFetchedUsingDefault = false;
  ns.lastQueryKey = null;

  // --- 初始化 ---
  ns.ensureInit = async function () {
    try {
      let dates = readDates();
      if (!dates) {
        const def = computeDefaultLast3Days();
        setUIDates(def);
        ns.userAppliedDate = false;
        await fetchData(undefined, {}, 'init-default');
        ns.justFetchedUsingDefault = true;
      } else {
        await fetchData(expandDatesToFullDays(dates), {}, 'init-with-ui-dates');
        ns.userAppliedDate = true;
      }

      await redraw();
      bindUI();
    } catch (err) {
      alert("Inspection 初始化失敗：" + err.message);
    }
  };

  // --- 日期工具 ---
  function toYMD(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }
  function computeDefaultLast3Days() {
    const now = new Date();
    const end = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const start = new Date(end); start.setDate(start.getDate() - 3);
    return [toYMD(start), toYMD(end)];
  }
  function setUIDates([b, e]) {
    document.querySelector("#inspectionStart").value = b;
    document.querySelector("#inspectionEnd").value   = e;
  }
  function expandDatesToFullDays(dates) {
    return [`${dates[0]} 00:00:00`, `${dates[1]} 23:59:59`];
  }
  function readDates() {
    const b = document.querySelector("#inspectionStart").value;
    const e = document.querySelector("#inspectionEnd").value;
    return (b && e) ? [b, e] : undefined;
  }
  function normalizeDaySpan(minDate, maxDate) {
    if (!minDate || !maxDate) return null;
    const b = new Date(minDate); b.setHours(0,0,0,0);
    const e = new Date(maxDate); e.setHours(23,59,59,999);
    return { begin: b, end: e };
  }

  // --- Filter（對應 inspection 的 filter.js）---
  function readFilters() {
    return window.AOI_INSPECTION.readFiltersFromUI
      ? window.AOI_INSPECTION.readFiltersFromUI()
      : {};
  }

  function buildQueryKey(datesWithTimes, filters) {
    const d = Array.isArray(datesWithTimes) ? datesWithTimes.join("~") : "no-date";
    const f = filters ? JSON.stringify(filters) : "{}";
    return d + "||" + f;
  }

  async function fetchData(datesWithTimes, filters, reason) {
    if (isFetching) return;

    const key = buildQueryKey(datesWithTimes, filters);
    if (ns.lastQueryKey === key) return;

    isFetching = true;
    try {
      await window.AOI_INSPECTION.fetchInspectionData({
        dates: datesWithTimes,
        filters: filters || {}
      });

      const tr = window.AOI_INSPECTION.state.timeRange;
      if (tr) ns.cachedSpan = normalizeDaySpan(tr.min, tr.max);

      ns.lastQueryKey = key;
    } finally { isFetching = false; }
  }

  function isWithinCachedSpan(datesYMD) {
    if (!ns.cachedSpan || !datesYMD) return false;
    const begin = new Date(datesYMD[0] + "T00:00:00");
    const end   = new Date(datesYMD[1] + "T23:59:59");
    return begin >= ns.cachedSpan.begin && end <= ns.cachedSpan.end;
  }

  // --- 重繪 ---
  async function redraw() {
    const dates = readDates();

    if (!ns.justFetchedUsingDefault) {
      if (dates && !isWithinCachedSpan(dates) && ns.userAppliedDate) {
        await fetchData(expandDatesToFullDays(dates), readFilters(), "redraw-out-of-cache");
      }
    } else {
      ns.justFetchedUsingDefault = false;
    }

    const rows = window.AOI_INSPECTION.getFiltered({ dates });

    render(rows);
  }

  // --- 綁定 UI ---
  function bindUI() {
    const right = document.getElementById("inspection-right");

    if (right) {
      right.addEventListener("change", ev => {
        if (ev.target.tagName === "SELECT" && /^insp-f-/.test(ev.target.id)) redraw();
      });
    }

    document.getElementById("inspectionApply")?.addEventListener("click", async () => {
      const dates = readDates();
      ns.userAppliedDate = true;
      if (!isWithinCachedSpan(dates)) {
        await fetchData(expandDatesToFullDays(dates), readFilters(), "apply");
      }
      await redraw();
    });

    document.getElementById("inspectionClear")?.addEventListener("click", async () => {
      document.querySelector("#inspectionStart").value = "";
      document.querySelector("#inspectionEnd").value = "";
      ns.userAppliedDate = false;

      await fetchData(undefined, readFilters(), "clear");
      const def = computeDefaultLast3Days();
      setUIDates(def);
      ns.justFetchedUsingDefault = true;

      await redraw();
    });
  }

  // --- render() ---
  function render(rows) {
    window.AOI_INSPECTION.Charts?.render?.(
      rows,
      window.AOI_INSPECTION.state.paramDict
    );

    window.AOI_INSPECTION.Table?.render?.(
      rows,
      window.AOI_INSPECTION.state.paramDict
    );
  }

})();





