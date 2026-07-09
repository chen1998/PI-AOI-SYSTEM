// static/js/duty/cell_aoi_to_array/cell_aoi_to_array_main.js
(function () {
  "use strict";

  window.CELL_AOI_TO_ARRAY = window.CELL_AOI_TO_ARRAY || {};

  const MOD = window.CELL_AOI_TO_ARRAY;

  MOD.Main = {
    init,
    reload,
    renderInfo
  };

  function isReadyModule(name, fnName) {
    const mod = MOD[name];

    if (!mod) {
      console.warn(`[cell-aoi-to-array-main] MOD.${name} not loaded`);
      return false;
    }

    if (fnName && typeof mod[fnName] !== "function") {
      console.warn(`[cell-aoi-to-array-main] MOD.${name}.${fnName} not ready`, mod);
      return false;
    }

    return true;
  }

  function requireCoreModules() {
    const missing = [];

    [
      ["API", null],
      ["UI", null],
      ["State", null]
    ].forEach(function (item) {
      const name = item[0];

      if (!MOD[name]) {
        missing.push(name);
      }
    });

    if (missing.length) {
      console.error("[cell-aoi-to-array-main] core modules missing:", missing);
      return false;
    }

    return true;
  }

  async function init() {
    try {
      if (!requireCoreModules()) {
        return;
      }

      if (!MOD.State || typeof MOD.State.loadConfig !== "function") {
        console.error("[cell-aoi-to-array-main] MOD.State.loadConfig not ready:", MOD.State);
        return;
      }

      await MOD.State.loadConfig();

      /*
       * 以下模組如果沒有載入，不直接 throw。
       * 會 warning，讓頁面至少能繼續初始化其他區塊。
       */
      if (isReadyModule("Tabs", "init")) {
        MOD.Tabs.init();
      }

      if (isReadyModule("Filters", "init")) {
        MOD.Filters.init();
      }

      if (isReadyModule("Charts", "init")) {
        MOD.Charts.init();
      }

      if (isReadyModule("Table", "init")) {
        MOD.Table.init();
      }

      if (isReadyModule("Tabs", "render")) {
        MOD.Tabs.render();
      }

      if (isReadyModule("Filters", "render")) {
        MOD.Filters.render();
      }

      if (
        MOD.Tabs &&
        typeof MOD.Tabs.activateFeature === "function" &&
        MOD.State &&
        MOD.State.state
      ) {
        MOD.Tabs.activateFeature(MOD.State.state.feature);
      }

      await reload();
    } catch (err) {
      console.error("[cell-aoi-to-array] init failed:", err);
    }
  }

  async function reload() {
    if (!requireCoreModules()) {
      return;
    }

    const { state, dom } = MOD.State;

    if (MOD.Filters && typeof MOD.Filters.collect === "function") {
      MOD.Filters.collect();
    } else {
      console.warn("[cell-aoi-to-array-main] MOD.Filters.collect not ready:", MOD.Filters);
    }

    if (dom.applyBtn) {
      dom.applyBtn.classList.add("is-loading");
      dom.applyBtn.textContent = "載入中";
    }

    try {
      const payload = buildComparePayload();

      console.log("[cell-aoi-to-array-main] compare payload =", payload);

      const result = await MOD.API.fetchCompareData(payload)

      if (MOD.State && typeof MOD.State.applyResult === "function") {
        MOD.State.applyResult(result);
      } else {
        console.warn("[cell-aoi-to-array-main] MOD.State.applyResult not ready:", MOD.State);
      }

      renderInfo(result.info || {});

      if (MOD.Summary && typeof MOD.Summary.render === "function") {
        MOD.Summary.render();
      } else {
        console.warn("[cell-aoi-to-array-main] MOD.Summary.render not ready:", MOD.Summary);
      }

      if (MOD.Charts && typeof MOD.Charts.render === "function") {
        MOD.Charts.render(result.chartData || {});
      } else {
        console.warn("[cell-aoi-to-array-main] MOD.Charts.render not ready:", MOD.Charts);
      }

      if (MOD.Table && typeof MOD.Table.render === "function") {
        MOD.Table.render();
      } else {
        console.warn("[cell-aoi-to-array-main] MOD.Table.render not ready:", MOD.Table);
      }

      if (MOD.Sheet && typeof MOD.Sheet.renderEmpty === "function") {
        MOD.Sheet.renderEmpty();
      } else {
        console.warn("[cell-aoi-to-array-main] MOD.Sheet.renderEmpty not ready:", MOD.Sheet);
      }

      if (MOD.Table && typeof MOD.Table.setModeText === "function") {
        MOD.Table.setModeText("All Data");
      }
    } catch (err) {
      console.error("[cell-aoi-to-array] reload failed:", err);
    } finally {
      if (dom.applyBtn) {
        dom.applyBtn.classList.remove("is-loading");
        dom.applyBtn.textContent = "套用";
      }
    }
  }

  function buildComparePayload() {
    const { state } = MOD.State;
    const filters = state.filters || {};
  
    const sheetIds = Array.isArray(filters.sheetIds)
      ? filters.sheetIds
          .map(function (v) {
            return String(v || "").trim().toUpperCase();
          })
          .filter(function (v, idx, arr) {
            return (
              v &&
              !["NAN", "NONE", "NULL", "<NA>", "NAT"].includes(v) &&
              arr.indexOf(v) === idx
            );
          })
      : [];
  
    return {
      category: state.category || "PI",
      feature: state.feature || "aoi-sampling-compare",
      filters: {
        startDate: filters.startDate || "",
        endDate: filters.endDate || "",
  
        tool: filters.tool || "",
        lineId: filters.lineId || "",
  
        sheetType: filters.sheetType || "",
        sheetId: filters.sheetId || "",
  
        // CSV 多片 sheet 查詢，後端 CellAoiToArrayFilters.sheetIds 會接這個
        sheetIds: sheetIds,
  
        aoi: filters.aoi || "",
        piType: filters.piType || "",
        sourceOpId: filters.sourceOpId || "",
        matchStatus: filters.matchStatus || "",
        modelNo: filters.modelNo || "",
        recipeId: filters.recipeId || ""
      }
    };
  }

  function renderInfo(info) {
    if (!MOD.State || !MOD.State.dom || !MOD.State.state) {
      return;
    }

    const { dom, state } = MOD.State;
    const cfg = MOD.State.getConfig ? MOD.State.getConfig() : {};

    const fallback = cfg.infoTextByFeature?.[state.feature] || {
      left: "",
      linkText: "預留連結功能",
      linkHref: "#"
    };

    const safeInfo = info || fallback;

    if (dom.infoLeft) {
      dom.infoLeft.textContent = safeInfo.left || "";
    }

    if (dom.infoRight) {
      dom.infoRight.innerHTML = "";

      const a = document.createElement("a");
      a.className = "cell-aoi-to-array-reserved-link";
      a.href = safeInfo.linkHref || "#";
      a.textContent = safeInfo.linkText || "預留連結功能";

      a.addEventListener("click", function (event) {
        event.preventDefault();
      });

      dom.infoRight.appendChild(a);
    }
  }

  /*
   * defer 載入時通常 DOM 已 ready。
   * 這裡仍加一層保護，避免 script 被改成非 defer 時初始化過早。
   */
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();