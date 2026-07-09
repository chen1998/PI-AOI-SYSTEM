// static/js/bpi_area/bpi_density/router.js
// BPI Density router compatibility layer.

(function () {
  const ns = {};
  window.AOI_BPI_DENSITY_Router = ns;

  let isFetching = false;

  ns.cachedSpan = null;
  ns.userAppliedDate = false;
  ns.justFetchedUsingDefault = false;
  ns.lastQueryKey = null;
  ns._bound = false;

  // ============================================================
  // Public init
  // ============================================================
  ns.ensureInit = async function () {
    try {
      let dates = readDates();

      if (!dates) {
        const def = computeDefaultLast3Days();
        setUIDates(def);

        ns.userAppliedDate = false;

        await fetchData(undefined, {}, "init-default", true);
        ns.justFetchedUsingDefault = true;
      } else {
        await fetchData(dates, {}, "init-with-ui-dates", true);
        ns.userAppliedDate = true;
      }

      await redraw();

      ns._bound = false;
      bindUI();
    } catch (err) {
      console.error("[bpi density router] ensureInit failed:", err);
      alert("初始化失敗：" + (err.message || err));
    }
  };

  // ============================================================
  // Date helpers
  // ============================================================
  function toYMD(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function computeDefaultLast3Days() {
    const now = new Date();
    const end = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const start = new Date(end);
    start.setDate(start.getDate() - 3);
    return [toYMD(start), toYMD(end)];
  }

  function setUIDates([b, e]) {
    const beginEl = document.querySelector("#aoi-bpi-density-start");
    const endEl = document.querySelector("#aoi-bpi-density-end");

    if (beginEl) beginEl.value = b;
    if (endEl) endEl.value = e;
  }

  function clearUIDates() {
    const beginEl = document.querySelector("#aoi-bpi-density-start");
    const endEl = document.querySelector("#aoi-bpi-density-end");

    if (beginEl) beginEl.value = "";
    if (endEl) endEl.value = "";
  }

  function normalizeDaySpan(minDate, maxDate) {
    if (!minDate || !maxDate) return null;

    const b = new Date(minDate);
    const e = new Date(maxDate);

    b.setHours(0, 0, 0, 0);
    e.setHours(23, 59, 59, 999);

    return { begin: b, end: e };
  }

  function readDates() {
    const b = document.querySelector("#aoi-bpi-density-start")?.value;
    const e = document.querySelector("#aoi-bpi-density-end")?.value;

    return (b && e) ? [b, e] : undefined;
  }

  function readFilters() {
    return window.AOI_BPI_DENSITY?.readFiltersFromUI
      ? window.AOI_BPI_DENSITY.readFiltersFromUI()
      : {};
  }

  function buildQueryKey(datesWithTimes, filters) {
    const d = Array.isArray(datesWithTimes)
      ? datesWithTimes.join("~")
      : "no-dates";

    const f = filters ? JSON.stringify(filters) : "{}";
    return d + "||" + f;
  }

  // ============================================================
  // Data fetch
  // force=true 時一定打後端，不受 lastQueryKey / cache 影響
  // ============================================================
  async function fetchData(datesWithTimes, filters, reason, force = false) {
    if (isFetching) {
      console.debug("[bpi density router] skip fetch: already fetching ->", reason);
      return;
    }

    const key = buildQueryKey(datesWithTimes, filters);

    if (!force && ns.lastQueryKey && ns.lastQueryKey === key) {
      console.debug("[bpi density router] skip fetch: same query ->", reason);
      return;
    }

    isFetching = true;

    try {
      if (!window.AOI_BPI_DENSITY?.fetchBpiDensityData) {
        throw new Error("AOI_BPI_DENSITY.fetchBpiDensityData 不存在");
      }

      console.log("[bpi density router] fetchData", {
        reason,
        force,
        dates: datesWithTimes,
        filters: filters || {}
      });

      await window.AOI_BPI_DENSITY.fetchBpiDensityData({
        dates: datesWithTimes,
        filters: filters || {}
      });

      const tr = window.AOI_BPI_DENSITY?.state?.timeRange;
      if (tr) {
        ns.cachedSpan = normalizeDaySpan(tr.min, tr.max);
      } else {
        ns.cachedSpan = null;
      }

      ns.lastQueryKey = key;

      if (window.BPI_AREA?.buildRightSubTabs) {
        const container = document.getElementById("aoi-bpi-density-subtabs");
        if (container) window.BPI_AREA.buildRightSubTabs(container);
      }
    } finally {
      isFetching = false;
    }
  }

  function isWithinCachedSpan(datesYMD) {
    if (!ns.cachedSpan || !datesYMD || datesYMD.length !== 2) return false;

    const wantBegin = new Date(datesYMD[0] + "T00:00:00");
    const wantEnd = new Date(datesYMD[1] + "T23:59:59");

    return (wantBegin >= ns.cachedSpan.begin) && (wantEnd <= ns.cachedSpan.end);
  }

  // ============================================================
  // Redraw
  // ============================================================
  async function redraw() {
    const dates = readDates();

    if (!ns.justFetchedUsingDefault) {
      if (dates && !isWithinCachedSpan(dates) && ns.userAppliedDate) {
        await fetchData(dates, readFilters(), "redraw-out-of-cache", true);
      }
    } else {
      ns.justFetchedUsingDefault = false;
    }

    const AOI = window.AOI_BPI_DENSITY;
    if (!AOI) return;

    const rows = AOI.getFiltered ? AOI.getFiltered({ dates }) : [];
    render(rows);
  }

  ns.redraw = redraw;

  function render(rows) {
    const root = document.getElementById("aoi-bpi-density-root");
    if (!root) return;

    const isMainVisible = root.style.display !== "none";
    if (!isMainVisible) return;

    if (window.AOI_BPI_DENSITY?.Charts?.render) {
      window.AOI_BPI_DENSITY.Charts.render(
        rows,
        window.AOI_BPI_DENSITY?.state?.paramDict
      );
    }

    if (window.AOI_BPI_DENSITY?.Table?.render) {
      window.AOI_BPI_DENSITY.Table.render(
        rows,
        window.AOI_BPI_DENSITY?.state?.paramDict
      );
    }
  }

  // ============================================================
  // UI binding
  // ============================================================
  function bindUI() {
    if (ns._bound) return;
    ns._bound = true;

    const right = document.getElementById("aoi-bpi-density-right");

    if (right) {
      right.addEventListener("change", (ev) => {
        const t = ev.target;

        if (t && t.tagName === "SELECT" && /^bpi-f-/.test(t.id)) {
          console.log("[BPI Density Filter Change]", readFilters());
          redraw();
        }
      });

      right.addEventListener("input", (ev) => {
        const t = ev.target;

        if (t && t.tagName === "SELECT" && /^bpi-f-/.test(t.id)) {
          redraw();
        }
      });
    }

    const applyBtn = document.getElementById("aoi-bpi-density-apply");
    if (applyBtn && applyBtn.dataset.bpiDensityBound !== "1") {
      applyBtn.dataset.bpiDensityBound = "1";

      applyBtn.addEventListener("click", async () => {
        const dates = readDates();
        const filters = readFilters();

        console.log("[BPI Density Apply] dates =", dates, "filters =", filters);

        if (!dates) return;

        ns.userAppliedDate = true;
        ns.justFetchedUsingDefault = false;

        await fetchData(dates, filters, "apply-date-force", true);
        await redraw();
      });
    }

    const clearBtn = document.getElementById("aoi-bpi-density-clear");
    if (clearBtn && clearBtn.dataset.bpiDensityBound !== "1") {
      clearBtn.dataset.bpiDensityBound = "1";

      clearBtn.addEventListener("click", async () => {
        const filters = readFilters();

        console.log("[BPI Density Clear] filters =", filters);

        clearUIDates();

        ns.userAppliedDate = false;
        ns.justFetchedUsingDefault = true;

        await fetchData(undefined, filters, "clear-date-force", true);

        const def = computeDefaultLast3Days();
        setUIDates(def);

        await redraw();
      });
    }

    document.addEventListener("aoi-bpi-density:data-ready", () => {
      if (window.BPI_AREA?.buildRightSubTabs) {
        const container = document.getElementById("aoi-bpi-density-subtabs");
        if (container) window.BPI_AREA.buildRightSubTabs(container);
      }
    });
  }

  // ============================================================
  // Expose
  // ============================================================
  ns.fetchData = fetchData;
  ns.readDates = readDates;
  ns.readFilters = readFilters;
  ns.computeDefaultLast3Days = computeDefaultLast3Days;
  ns.setUIDates = setUIDates;
})();