// static/js/aoi_density/router.js
(function () {
  const ns = {};
  window.AOI_DENSITY_Router = ns;

  let isFetching = false;
  ns.cachedSpan = null;
  ns.userAppliedDate = false;
  ns.justFetchedUsingDefault = false;
  ns.lastQueryKey = null;
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
      alert("初始化失敗：" + err.message);
    }
  };

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
    const beginEl = document.querySelector("#aoi_densityStart");
    const endEl   = document.querySelector("#aoi_densityEnd");
    if (beginEl) beginEl.value = b;
    if (endEl)   endEl.value   = e;
  }
  function expandDatesToFullDays(dates) {
    if (!dates || dates.length !== 2) return dates;
    return [`${dates[0]} 00:00:00`, `${dates[1]} 23:59:59`];
  }
  function normalizeDaySpan(minDate, maxDate) {
    if (!minDate || !maxDate) return null;
    const b = new Date(minDate); b.setHours(0,0,0,0);
    const e = new Date(maxDate); e.setHours(23,59,59,999);
    return { begin: b, end: e };
  }
  function readDates() {
    const b = document.querySelector("#aoi_densityStart")?.value;
    const e = document.querySelector("#aoi_densityEnd")?.value;
    return (b && e) ? [b, e] : undefined;
  }

  // ---- 動態讀取 Filter（交由 service 的工具）----
  function readFilters() {
    return window.AOI_DENSITY.readFiltersFromUI
      ? window.AOI_DENSITY.readFiltersFromUI()
      : {};
  }
  function buildQueryKey(datesWithTimes, filters) {
    const d = Array.isArray(datesWithTimes) ? datesWithTimes.join('~') : 'no-dates';
    const f = filters ? JSON.stringify(filters) : '{}';
    return d + '||' + f;
  }
  async function fetchData(datesWithTimes, filters, reason) {
    if (isFetching) return;
    // 若與上一次完全同參數，就不必再打
    const key = buildQueryKey(datesWithTimes, filters);
    if (ns.lastQueryKey && ns.lastQueryKey === key) {
        console.debug('[router] skip fetch: same query as last time ->', reason);
        return;
    }
    isFetching = true;
    try {
      await window.AOI_DENSITY.fetchAoiDensityData({ dates: datesWithTimes, filters: filters || {} });
      const tr = window.AOI_DENSITY.state.timeRange;
      if (tr) ns.cachedSpan = normalizeDaySpan(tr.min, tr.max);
      ns.lastQueryKey = key; // 只要 fetch 成功（沒被 service 擋掉），更新請求鍵
    } finally { isFetching = false; }
  }

  function isWithinCachedSpan(datesYMD) {
    if (!ns.cachedSpan || !datesYMD || datesYMD.length !== 2) return false;
    const wantBegin = new Date(datesYMD[0] + "T00:00:00");
    const wantEnd   = new Date(datesYMD[1] + "T23:59:59");
    return (wantBegin >= ns.cachedSpan.begin) && (wantEnd <= ns.cachedSpan.end);
  }

  async function redraw() {
    const dates = readDates();

    if (!ns.justFetchedUsingDefault) {
      if (dates && !isWithinCachedSpan(dates) && ns.userAppliedDate) {
        await fetchData(expandDatesToFullDays(dates), readFilters(), 'redraw-out-of-cache');
      }
    } else {
      ns.justFetchedUsingDefault = false;
    }

    const rows = window.AOI_DENSITY.getFiltered({ dates });
    //console.log('routers rows',rows);
    render(rows); // 用過濾後 rows 畫
  }

  function bindUI() {
    // 動態代理：監聽所有動態建立的 <select id="f-*"> 變化
    const right = document.getElementById("aoi_density-right");
    if (right) {
      right.addEventListener("change", (ev)=>{
        const t = ev.target;
        if (t && t.tagName === "SELECT" && /^f-/.test(t.id)) {
          redraw();
        }
      });
      right.addEventListener("input", (ev)=>{
        const t = ev.target;
        if (t && t.tagName === "SELECT" && /^f-/.test(t.id)) {
          redraw();
        }
      });
    }

    document.getElementById("aoi_densityApply")?.addEventListener("click", async ()=>{
      const dates = readDates();
      console.log('dates',dates);
      if (!dates) return;
      ns.userAppliedDate = true;
      if (!isWithinCachedSpan(dates)) {
        await fetchData(expandDatesToFullDays(dates), readFilters(), 'apply-out-of-cache');
      }
      await redraw();
    });

    document.getElementById("aoi_densityClear")?.addEventListener("click", async ()=>{
      const b = document.getElementById("aoi_densityStart");
      const e = document.getElementById("aoi_densityEnd");
      if (b) b.value = ""; if (e) e.value = "";
      ns.userAppliedDate = false;
      await fetchData(undefined, readFilters(), 'clear-to-default');
      const def = computeDefaultLast3Days();
      setUIDates(def);
      ns.justFetchedUsingDefault = true;
      await redraw();
    });
  }

  function render(rows){
    // 圖
    if (window.AOI_DENSITY?.Charts?.render) {
      window.AOI_DENSITY.Charts.render(rows, window.AOI_DENSITY?.state?.paramDict);
    }
    // 表
    if (window.AOI_DENSITY?.Table?.render) {
      window.AOI_DENSITY.Table.render(rows, window.AOI_DENSITY?.state?.paramDict);
    }
  }
})();
