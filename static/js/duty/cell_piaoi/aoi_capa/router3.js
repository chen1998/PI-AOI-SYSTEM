// static/js/aoi_capa/router3.js
(function () {
  const AOI = (window.AOI_CAPA = window.AOI_CAPA || {});
  AOI.Router = AOI.Router || {};

  const $ = (sel, root = document) => root.querySelector(sel);

  AOI.state = AOI.state || {
    rows: [],
    paramDict: null,
    dateRange: null,
    hourlyCache: {},
    initialized: false,
    currentSubTab: "Day_Hourly",
    editSummaryRows: [],
    editSummaryLoaded: false,
  };

  function showToast(msg) {
    const toast = $(".toast");
    if (!toast) return;
    toast.textContent = String(msg || "");
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), 3000);
  }

  function readDateRangeFromUI() {
    const s = $("#aoi-capa-start")?.value || "";
    const e = $("#aoi-capa-end")?.value || "";
    if (!s || !e) return null;
    return [s, e];
  }

  function clearDateRangeUI() {
    const s = $("#aoi-capa-start");
    const e = $("#aoi-capa-end");
    if (s) s.value = "";
    if (e) e.value = "";
  }

  function applyDateRangeToUI(dateRange) {
    if (!dateRange) return;

    const s = $("#aoi-capa-start");
    const e = $("#aoi-capa-end");

    if (s && dateRange.start) s.value = String(dateRange.start).slice(0, 10);
    if (e && dateRange.end) e.value = String(dateRange.end).slice(0, 10);
  }

  function dispatchDataReady() {
    document.dispatchEvent(
      new CustomEvent("aoi-capa:data-ready", { detail: AOI.state })
    );
  }

  function dispatchSubTabChanged(key) {
    document.dispatchEvent(
      new CustomEvent("aoi-capa:subtab-changed", {
        detail: { key: key || AOI.state.currentSubTab || "Day_Hourly" },
      })
    );
  }

  function dispatchEditSummaryReady() {
    document.dispatchEvent(
      new CustomEvent("aoi-capa:edit-summary-ready", {
        detail: {
          rows: AOI.state.editSummaryRows || [],
          state: AOI.state,
        },
      })
    );
  }

  function resizeChartIfNeeded() {
    const dom = $("#aoi-capa-facet");
    if (!dom || !window.echarts) return;

    const inst = window.echarts.getInstanceByDom(dom);
    if (inst) {
      try {
        inst.resize();
      } catch (err) {
        console.warn("[AOI_CAPA] chart resize failed:", err);
      }
    }
  }

  function syncSubTabSectionVisibility() {
    const subTab = AOI.state.currentSubTab || "Day_Hourly";

    const specWrap = $("#aoi-capa-spec-table");
    const capaRoot = $("#aoi-capa-root");

    if (subTab === "EditSummary") {
      if (specWrap) specWrap.style.display = "";
      if (capaRoot) capaRoot.style.display = "none";
    } else {
      if (capaRoot) capaRoot.style.display = ""
      if (specWrap) specWrap.style.display = "none";
    }
  }

  AOI.buildRightSubTabs = function (host) {
    if (!host) return;
    host.innerHTML = "";

    const subTabsCfg =
      AOI.state?.paramDict?.SubTabsFilterDefaultDict ||
      AOI.state?.paramDict?.subTabsFilterDefaultDict ||
      {};

    const keys = Object.keys(subTabsCfg).length
      ? Object.keys(subTabsCfg)
      : ["Day_Hourly", "EditSummary"];

    const current = AOI.state?.currentSubTab || "Day_Hourly";

    keys.forEach((key) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `tab-btn${key === current ? " active" : ""}`;
      btn.dataset.key = key;
    
      const cfg = subTabsCfg[key] || {};
      btn.textContent = cfg.tab_name || key;   
    
      btn.addEventListener("click", async () => {
        AOI.state.currentSubTab = key;
    
        host.querySelectorAll(".tab-btn").forEach((el) => {
          el.classList.toggle("active", el.dataset.key === key);
        });
    
        syncSubTabSectionVisibility();
        dispatchSubTabChanged(key);
    
        if (key === "EditSummary") {
          try {
            AOI.EditSummary?.initLayout?.();
            await AOI.Router.refreshEditSummary();
          } catch (err) {
            console.error("[AOI_CAPA] refreshEditSummary failed:", err);
            showToast(`EditSummary 讀取失敗：${err.message || err}`);
          }
        }
    
        AOI.Router.redraw();
      });
    
      host.appendChild(btn);
    });
  };

  AOI.Router.redraw = function () {
    syncSubTabSectionVisibility();

    const current = AOI.state.currentSubTab || "Day_Hourly";

    if (current === "EditSummary") {
      try {
        AOI.EditSummary?.build?.();
      } catch (err) {
        console.error("[AOI_CAPA] EditSummary render failed:", err);
      }
      return;
    }

    try {
      AOI.Chart?.update?.();
    } catch (err) {
      console.error("[AOI_CAPA] Chart.update failed:", err);
    }

    try {
      AOI.Table?.build?.();
    } catch (err) {
      console.error("[AOI_CAPA] Table.build failed:", err);
    }

    setTimeout(resizeChartIfNeeded, 0);
  };

  AOI.Router.refreshSummary = async function (dates) {
    try {
      const payload = await AOI.API.fetchSummary(dates || null);

      AOI.state.rows = Array.isArray(payload?.DictData) ? payload.DictData : [];
      AOI.state.paramDict = payload?.ParamDict || {};
      AOI.state.dateRange = payload?.DateRange || null;

      if (!dates && AOI.state.dateRange) {
        applyDateRangeToUI(AOI.state.dateRange);
      }

      const host = $("#aoi-capa-subtabs");
      if (host) {
        AOI.buildRightSubTabs(host);
      }

      dispatchDataReady();
      syncSubTabSectionVisibility();
      AOI.Router.redraw();
    } catch (err) {
      console.error("[AOI_CAPA] refreshSummary failed:", err);
      showToast(`稼動 summary 讀取失敗：${err.message || err}`);
    }
  };

  AOI.Router.refreshHourly = async function (ask) {
    try {
      const res = await AOI.API.fetchHourly(ask || {});
      const rows = Array.isArray(res?.rows) ? res.rows : [];

      const key = [
        ask?.aoi || "",
        ask?.run_day || "",
        ask?.pi_type || "ALL",
      ].join("|");

      AOI.state.hourlyCache[key] = rows;
      return rows;
    } catch (err) {
      console.error("[AOI_CAPA] refreshHourly failed:", err);
      showToast(`稼動 hourly 讀取失敗：${err.message || err}`);
      return [];
    }
  };

  AOI.Router.refreshEditSummary = async function () {
    if (typeof AOI.API?.fetchActionHistoryData !== "function") {
      AOI.state.editSummaryRows = [];
      AOI.state.editSummaryLoaded = true;
      dispatchEditSummaryReady();
      return [];
    }

    try {
      const specStart = $("#aoi-capa-spec-start")?.value || "";
      const specEnd = $("#aoi-capa-spec-end")?.value || "";

      let dates = null;
      if (specStart && specEnd) {
        dates = [specStart, specEnd];
      } else {
        const dr = AOI.state.dateRange || null;
        dates = dr
          ? [String(dr.start).slice(0, 10), String(dr.end).slice(0, 10)]
          : readDateRangeFromUI();
      }

      const payload = await AOI.API.fetchActionHistoryData(dates || null);

      let rows = [];
      if (Array.isArray(payload?.rows)) {
        rows = payload.rows;
      } else if (Array.isArray(payload?.DictData)) {
        rows = payload.DictData;
      } else if (payload?.DictData && typeof payload.DictData === "object") {
        rows = Object.values(payload.DictData);
      }

      AOI.state.editSummaryRows = rows;
      AOI.state.editSummaryLoaded = true;

      dispatchEditSummaryReady();
      return rows;
    } catch (err) {
      console.error("[AOI_CAPA] refreshEditSummary failed:", err);
      showToast(`稼動 EditSummary 讀取失敗：${err.message || err}`);
      return [];
    }
  };

  function bindDateButtons() {
    const btnApply = $("#aoi-capa-apply");
    const btnClear = $("#aoi-capa-clear");

    if (btnApply && !btnApply.dataset.bound) {
      btnApply.dataset.bound = "1";
      btnApply.addEventListener("click", async () => {
        const dr = readDateRangeFromUI();
        AOI.state.editSummaryLoaded = false;
        await AOI.Router.refreshSummary(dr || null);

        if ((AOI.state.currentSubTab || "Day_Hourly") === "EditSummary") {
          AOI.EditSummary?.initLayout?.();
          await AOI.Router.refreshEditSummary();
          AOI.Router.redraw();
        }
      });
    }

    if (btnClear && !btnClear.dataset.bound) {
      btnClear.dataset.bound = "1";
      btnClear.addEventListener("click", async () => {
        clearDateRangeUI();
        AOI.state.editSummaryLoaded = false;
        await AOI.Router.refreshSummary(null);

        if ((AOI.state.currentSubTab || "Day_Hourly") === "EditSummary") {
          AOI.EditSummary?.initLayout?.();
          await AOI.Router.refreshEditSummary();
          AOI.Router.redraw();
        }
      });
    }
  }

  function bindFilterPanelEvents() {
    const right = $("#aoi-capa-right");
    if (!right || right.dataset.bound === "1") return;

    right.dataset.bound = "1";
    right.addEventListener("change", (ev) => {
      const id = ev.target?.id || "";
      if (id.startsWith("aoi-capa-f-")) {
        AOI.Router.redraw();
      }
    });
  }

  function bindSystemTabEvents() {
    const tabBtns = document.querySelectorAll('.sys-tab[data-view="aoi-capa"]');
    tabBtns.forEach((btn) => {
      if (btn.dataset.capaBound === "1") return;
      btn.dataset.capaBound = "1";

      btn.addEventListener("click", () => {
        setTimeout(async () => {
          const host = $("#aoi-capa-subtabs");
          if (host) {
            AOI.buildRightSubTabs(host);
          }

          syncSubTabSectionVisibility();
          dispatchSubTabChanged(AOI.state.currentSubTab || "Day_Hourly");

          if ((AOI.state.currentSubTab || "Day_Hourly") === "EditSummary") {
            AOI.EditSummary?.initLayout?.();
            if (!AOI.state.editSummaryLoaded) {
              await AOI.Router.refreshEditSummary();
            }
          }

          AOI.Router.redraw();
        }, 50);
      });
    });
  }

  AOI.Router.bindUI = function () {
    bindDateButtons();
    bindFilterPanelEvents();
    bindSystemTabEvents();
  };

  AOI.Router.ensureInit = async function () {
    AOI.Router.bindUI();

    if (AOI.state.initialized) {
      const host = $("#aoi-capa-subtabs");
      if (host) {
        AOI.buildRightSubTabs(host);
      }

      syncSubTabSectionVisibility();
      dispatchSubTabChanged(AOI.state.currentSubTab || "Day_Hourly");

      if ((AOI.state.currentSubTab || "Day_Hourly") === "EditSummary") {
        AOI.EditSummary?.initLayout?.();
        if (!AOI.state.editSummaryLoaded) {
          await AOI.Router.refreshEditSummary();
        }
      }

      setTimeout(() => AOI.Router.redraw(), 0);
      return;
    }

    AOI.state.initialized = true;
    await AOI.Router.refreshSummary(null);

    const host = $("#aoi-capa-subtabs");
    if (host) {
      AOI.buildRightSubTabs(host);
    }

    syncSubTabSectionVisibility();
    dispatchSubTabChanged(AOI.state.currentSubTab || "Day_Hourly");

    if ((AOI.state.currentSubTab || "Day_Hourly") === "EditSummary") {
      AOI.EditSummary?.initLayout?.();
      await AOI.Router.refreshEditSummary();
    }
  };

  document.addEventListener("DOMContentLoaded", () => {
    const root = $("#aoi-capa-root");
    if (!root) return;
    AOI.Router.bindUI();
  });
})();