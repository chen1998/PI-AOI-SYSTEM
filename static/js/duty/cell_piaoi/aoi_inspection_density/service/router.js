// static/js/aoi_inspection_density/service/router.js
(function () {
  const ns = {};
  window.AOI_INSPECTION_Router = ns;

  let isFetching = false;
  let isBound = false;
  let hasInited = false;
  let dataReadyBound = false;

  // =========================
  // init
  // =========================
  ns.ensureInit = async function () {
    if (hasInited) {
      //render();
      return;
    }

    hasInited = true;

    bindDataReady();
    bindUI();

    await fetchData({
      dates: expandDates(readDates()),
      filters: readFilters()
    });

    // 不再手動 render
    // data-ready 事件已經會 render 一次
  };

  // =========================
  // 日期工具
  // =========================
  function readDates() {
    const b = document.querySelector("#aoi-inspection-density-start")?.value || "";
    const e = document.querySelector("#aoi-inspection-density-end")?.value || "";
    return (b && e) ? [b, e] : undefined;
  }

  function expandDates(dates) {
    if (!Array.isArray(dates) || dates.length !== 2) return undefined;
    const [b, e] = dates;
    if (!b || !e) return undefined;
    return [b, e];
  }

  // =========================
  // filter 讀取
  // =========================
  function readFilters() {
    if (window.AOI_INSPECTION?.readFiltersFromUI) {
      return window.AOI_INSPECTION.readFiltersFromUI() || {};
    }
    return {};
  }

  // =========================
  // fetch
  // =========================
  async function fetchData(opts = {}) {
    if (isFetching) return null;
    isFetching = true;

    try {
      const payload = await window.AOI_INSPECTION.fetchInspectionData({
        dates: opts.dates,
        filters: opts.filters || {}
      });
      return payload || null;
    } catch (err) {
      console.error("[AOI_INSPECTION_Router] fetchData error:", err);
      throw err;
    } finally {
      isFetching = false;
    }
  }

  // =========================
  // render
  // =========================
  function render() {
    const AOI = window.AOI_INSPECTION;
    if (!AOI) return;

    const paramDict = AOI.state?.paramDict || {};
    const dates = readDates();

    let rows = [];
    if (typeof AOI.getFiltered === "function") {
      rows = AOI.getFiltered({ dates }) || [];
    } else {
      rows = AOI.state?.rows || [];
    }

    AOI.Charts?.render?.(rows, paramDict);
    AOI.Table?.render?.(rows, paramDict);
  }

  // =========================
  // data-ready 後重畫
  // =========================
  function bindDataReady() {
    if (dataReadyBound) return;
    dataReadyBound = true;

    document.addEventListener("aoi_inspection:data-ready", () => {
      render();
    });
  }

  // =========================
  // UI 綁定
  // =========================
  function bindUI() {
    if (isBound) return;
    isBound = true;

    // 日期 Apply
    document
      .getElementById("aoi-inspection-density-apply")
      ?.addEventListener("click", async () => {
        try {
          await fetchData({
            dates: expandDates(readDates()),
            filters: readFilters()
          });
          // 不再手動 render，避免重複
        } catch (err) {
          console.error("[AOI_INSPECTION_Router] apply error:", err);
          alert(`Inspection Density 套用失敗：${err.message || err}`);
        }
      });

    // 日期 Clear
    document
      .getElementById("aoi-inspection-density-clear")
      ?.addEventListener("click", async () => {
        try {
          const s = document.getElementById("aoi-inspection-density-start");
          const e = document.getElementById("aoi-inspection-density-end");
          if (s) s.value = "";
          if (e) e.value = "";

          await fetchData({
            dates: undefined,
            filters: readFilters()
          });
          // 不再手動 render，避免重複
        } catch (err) {
          console.error("[AOI_INSPECTION_Router] clear error:", err);
          alert(`Inspection Density 清空失敗：${err.message || err}`);
        }
      });

    // 右側篩選區 change（MultiDD 會 dispatch 到隱藏 select）
    const right = document.getElementById("aoi-inspection-density-right");
    if (right) {
      right.addEventListener("change", (ev) => {
        const t = ev.target;
        if (!t) return;

        // 本地篩選直接重畫，不打 API
        if (t.tagName === "SELECT" && /^insp-f-/.test(t.id || "")) {
          render();
        }
      });
    }
  }
})();
