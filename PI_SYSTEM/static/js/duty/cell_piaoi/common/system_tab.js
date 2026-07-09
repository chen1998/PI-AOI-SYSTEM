// static/js/system_tab.js
(function () {
  const $ = (sel, root = document) => root.querySelector(sel);
  const $all = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  function normalizeView(view) {
    const v = String(view || "").trim();

    const map = {
      "gld_overlay": "ol-defect-map",
      "gld-overlay": "ol-defect-map",
      "defect-map": "ol-defect-map",
      "defect_map": "ol-defect-map",
      "ol-defect-map": "ol-defect-map",
      "ol_defect_map": "ol-defect-map",

      "aoi_bpi_density": "aoi-bpi-density",
      "aoi-bpi-density": "aoi-bpi-density",
      "bpi_density": "aoi-bpi-density",
      "bpi-density": "aoi-bpi-density",
      "bpi": "aoi-bpi-density",

      "aoi_density": "aoi-density",
      "aoi-density": "aoi-density",
      "density": "aoi-density",

      "inspection": "aoi-inspection-density",
      "aoi_inspection_density": "aoi-inspection-density",
      "aoi-inspection-density": "aoi-inspection-density",

      "aoi_capa": "aoi-capa",
      "aoi-capa": "aoi-capa",

      "report": "report",
    };

    return map[v] || v;
  }

  const loadedScripts = new Set();

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      if (!src) {
        reject(new Error("script src is empty"));
        return;
      }

      if (loadedScripts.has(src)) {
        resolve();
        return;
      }

      const existed = document.querySelector(`script[data-dynamic-src="${src}"]`);
      if (existed) {
        if (existed.dataset.loaded === "1") {
          loadedScripts.add(src);
          resolve();
          return;
        }

        existed.addEventListener(
          "load",
          () => {
            existed.dataset.loaded = "1";
            loadedScripts.add(src);
            resolve();
          },
          { once: true }
        );

        existed.addEventListener(
          "error",
          () => reject(new Error(`script load failed: ${src}`)),
          { once: true }
        );
        return;
      }

      const s = document.createElement("script");
      s.src = src;
      s.defer = true;
      s.dataset.dynamicSrc = src;

      s.onload = () => {
        s.dataset.loaded = "1";
        loadedScripts.add(src);
        resolve();
      };

      s.onerror = () => reject(new Error(`script load failed: ${src}`));
      document.head.appendChild(s);
    });
  }

  async function loadScriptsInOrder(srcList) {
    const list = Array.isArray(srcList) ? srcList : [];
    for (const src of list) {
      await loadScript(src);
    }
  }

  const VIEW_ASSET_CONFIG = {
    "ol-defect-map": {
      scripts: [
        "static/js/duty/cell_piaoi/ol_defect_map/colors.js",
        "static/js/duty/cell_piaoi/ol_defect_map/bus1.js",
        "static/js/duty/cell_piaoi/ol_defect_map/filter.js",
        "static/js/duty/cell_piaoi/ol_defect_map/router.js",
        "static/js/duty/cell_piaoi/ol_defect_map/api.js",
        "static/js/duty/cell_piaoi/ol_defect_map/run_info_table.js",
        "static/js/duty/cell_piaoi/ol_defect_map/defect_map.js",
        "static/js/duty/cell_piaoi/ol_defect_map/defect_list.js",
      ],
      init: async () => {
        if (typeof window.OL_DEFECT_MAP_Router?.ensureInit === "function") {
          await window.OL_DEFECT_MAP_Router.ensureInit();
        }
      },
    },

    "aoi-bpi-density": {
      scripts: [
        // BPI Area 共用總控
        "static/js/duty/cell_piaoi/bpi_area/bpi_density/api.js",
        "static/js/duty/cell_piaoi/bpi_area/common/service.js",
        "static/js/duty/cell_piaoi/bpi_area/common/tabs/table_tab.js",
        // BPI Density 原功能
        "static/js/duty/cell_piaoi/bpi_area/bpi_density/shared1.js",
        "static/js/duty/cell_piaoi/bpi_area/bpi_density/api.js",
        "static/js/duty/cell_piaoi/bpi_area/bpi_density/multidd2.js",
        "static/js/duty/cell_piaoi/bpi_area/bpi_density/service1.js",
        "static/js/duty/cell_piaoi/bpi_area/bpi_density/router.js",
        "static/js/duty/cell_piaoi/bpi_area/bpi_density/filter.js",
        "static/js/duty/cell_piaoi/bpi_area/bpi_density/chart.js",
        "static/js/duty/cell_piaoi/bpi_area/bpi_density/table.js",
        "static/js/duty/cell_piaoi/bpi_area/bpi_density/defect_map.js",

        // BPI/API Same Point 同點來料檢
        "static/js/duty/cell_piaoi/bpi_area/bpi_same_point/api.js",
        "static/js/duty/cell_piaoi/bpi_area/bpi_same_point/service.js",
        "static/js/duty/cell_piaoi/bpi_area/bpi_same_point/filter.js",
        "static/js/duty/cell_piaoi/bpi_area/bpi_same_point/chart.js",
        "static/js/duty/cell_piaoi/bpi_area/bpi_same_point/table.js",
        "static/js/duty/cell_piaoi/bpi_area/bpi_same_point/defect_map.js",
      ],
      init: async () => {
        if (typeof window.BPI_AREA?.Router?.ensureInit === "function") {
          await window.BPI_AREA.Router.ensureInit();
        }
      },
    },

    "aoi-density": {
      scripts: [
        "static/js/duty/cell_piaoi/aoi_density2/shared1.js",
        "static/js/duty/cell_piaoi/aoi_density2/api.js",
        "static/js/duty/cell_piaoi/aoi_density2/service1.js",
        "static/js/duty/cell_piaoi/aoi_density2/router.js",
        "static/js/duty/cell_piaoi/aoi_density2/multidd2.js",
        "static/js/duty/cell_piaoi/aoi_density2/filter.js",

        //"static/js/duty/cell_piaoi/aoi_density2/chart.js",
        "static/js/duty/cell_piaoi/aoi_density2/chart/chart_config.js",
        "static/js/duty/cell_piaoi/aoi_density2/chart/chart_utils.js",
        "static/js/duty/cell_piaoi/aoi_density2/chart/chart_aggregate.js",
        "static/js/duty/cell_piaoi/aoi_density2/chart/chart_interaction.js",
        "static/js/duty/cell_piaoi/aoi_density2/chart/chart_option.js",
        "static/js/duty/cell_piaoi/aoi_density2/chart/chart_main.js",


        "static/js/duty/cell_piaoi/aoi_density2/table.js",
        "static/js/duty/cell_piaoi/aoi_density2/defect_map.js",
        "static/js/duty/cell_piaoi/aoi_density2/tabs/trend_chart.js",
        "static/js/duty/cell_piaoi/aoi_density2/tabs/table_tab.js",
        "static/js/duty/cell_piaoi/aoi_density2/tabs/editSummary.js",
      ],
      init: async () => {
        if (typeof window.AOI_DENSITY_Router?.ensureInit === "function") {
          await window.AOI_DENSITY_Router.ensureInit();
        }
      },
    },

    "aoi-inspection-density": {
      scripts: [
        "static/js/duty/cell_piaoi/aoi_inspection_density/service/api.js",
        "static/js/duty/cell_piaoi/aoi_inspection_density/service/service1.js",
        "static/js/duty/cell_piaoi/aoi_inspection_density/service/router.js",
        "static/js/duty/cell_piaoi/aoi_inspection_density/function/multidd1.js",
        "static/js/duty/cell_piaoi/aoi_inspection_density/function/filter1.js",
        "static/js/duty/cell_piaoi/aoi_inspection_density/function/chart1.js",
        "static/js/duty/cell_piaoi/aoi_inspection_density/function/table1.js",
        "static/js/duty/cell_piaoi/aoi_inspection_density/function/defect_map.js",
        "static/js/duty/cell_piaoi/aoi_inspection_density/tabs/table_tab/state.js",
        "static/js/duty/cell_piaoi/aoi_inspection_density/tabs/table_tab/dom.js",
        "static/js/duty/cell_piaoi/aoi_inspection_density/tabs/table_tab/filters.js",
        "static/js/duty/cell_piaoi/aoi_inspection_density/tabs/table_tab/render.js",
        "static/js/duty/cell_piaoi/aoi_inspection_density/tabs/table_tab/default_spec_editor.js",
        "static/js/duty/cell_piaoi/aoi_inspection_density/tabs/table_tab/action_his.js",
        "static/js/duty/cell_piaoi/aoi_inspection_density/tabs/table_tab/entry.js",
        "static/js/duty/cell_piaoi/aoi_inspection_density/tabs/trend_chart.js",
      ],
      init: async () => {
        if (typeof window.AOI_INSPECTION_Router?.ensureInit === "function") {
          await window.AOI_INSPECTION_Router.ensureInit();
        }
      },
    },

    "aoi-capa": {
      scripts: [
        "static/js/duty/cell_piaoi/aoi_capa/multidd.js",
        "static/js/duty/cell_piaoi/aoi_capa/filter1.js",
        "static/js/duty/cell_piaoi/aoi_capa/api.js",
        "static/js/duty/cell_piaoi/aoi_capa/chart3.js",
        "static/js/duty/cell_piaoi/aoi_capa/table6.js",
        "static/js/duty/cell_piaoi/aoi_capa/router3.js",
        "static/js/duty/cell_piaoi/aoi_capa/right_target.js",
        "static/js/duty/cell_piaoi/aoi_capa/editSummary.js",
      ],
      init: async () => {
        if (typeof window.AOI_CAPA?.Router?.ensureInit === "function") {
          await window.AOI_CAPA.Router.ensureInit();
        }
      },
    },

    "report": {
      scripts: [],
      init: async () => {},
    },
  };

  const viewAssetsPromise = Object.create(null);
  const viewInited = Object.create(null);

  async function ensureViewAssetsLoaded(view) {
    const conf = VIEW_ASSET_CONFIG[view];
    if (!conf) return;

    if (!viewAssetsPromise[view]) {
      viewAssetsPromise[view] = loadScriptsInOrder(conf.scripts || []).catch((err) => {
        console.error(`[system_tab] ${view} assets load failed:`, err);
        viewAssetsPromise[view] = null;
        throw err;
      });
    }

    await viewAssetsPromise[view];
  }

  async function ensureViewInit(view) {
    const conf = VIEW_ASSET_CONFIG[view];
    if (!conf) return;

    await ensureViewAssetsLoaded(view);

    if (viewInited[view]) return;
    viewInited[view] = true;

    try {
      await conf.init?.();
    } catch (err) {
      viewInited[view] = false;
      throw err;
    }
  }

  function getSections() {
    return {
      "ol-defect-map":
        $("#ol-defect-map-root") ||
        $("#ol_defect_map-root"),

      "aoi-bpi-density":
        $("#aoi-bpi-density-root") ||
        $("#aoi_bpi_density-root"),

      "aoi-density":
        $("#aoi-density-root") ||
        $("#aoi_density-root"),

      "aoi-inspection-density":
        $("#aoi-inspection-density-root") ||
        $("#aoi_inspection_density-root") ||
        $("#inspection-root"),

      "aoi-capa":
        $("#aoi-capa-root") ||
        $("#aoi_capa-root"),

      "report":
        $("#report-root"),
    };
  }

  function swapTopArea(rawView) {
    const view = normalizeView(rawView);

    const olDefectDateBox = $("#ol-defect-map-global-filter");

    const bpiDensitySubtabs =
      $("#aoi-bpi-density-subtabs") ||
      $("#aoi_bpi_density-subtabs");

    const densitySubtabs =
      $("#aoi-density-subtabs") ||
      $("#aoi_density-subtabs");

    const inspSubtabs =
      $("#aoi-inspection-density-subtabs") ||
      $("#aoi_inspection_density-subtabs") ||
      $("#inspection-subtabs");

    const capaSubtabs =
      $("#aoi-capa-subtabs") ||
      $("#aoi_capa-subtabs");

    const lineTabs = $("#all-tab-container");

    const isOlDefectMap = view === "ol-defect-map";
    const isBPIDensity = view === "aoi-bpi-density";
    const isDensity = view === "aoi-density";
    const isInspection = view === "aoi-inspection-density";
    const isCapa = view === "aoi-capa";

    if (olDefectDateBox) {
      olDefectDateBox.style.display = isOlDefectMap ? "" : "none";
    }

    if (lineTabs) {
      lineTabs.style.display = isOlDefectMap ? "" : "none";
    }

    if (bpiDensitySubtabs) {
      if (isBPIDensity) {
        bpiDensitySubtabs.style.display = "";
    
        if (window.BPI_AREA?.buildRightSubTabs) {
          window.BPI_AREA.buildRightSubTabs(bpiDensitySubtabs);
        } else {
          window.AOI_BPI_DENSITY?.buildRightSubTabs?.(bpiDensitySubtabs);
        }
      } else {
        bpiDensitySubtabs.style.display = "none";
      }
    }

    if (densitySubtabs) {
      if (isDensity) {
        densitySubtabs.style.display = "";
        window.AOI_DENSITY?.buildRightSubTabs?.(densitySubtabs);
      } else {
        densitySubtabs.style.display = "none";
      }
    }

    if (inspSubtabs) {
      if (isInspection) {
        inspSubtabs.style.display = "";
        window.AOI_INSPECTION?.buildRightSubTabs?.(inspSubtabs);
      } else {
        inspSubtabs.style.display = "none";
      }
    }

    if (capaSubtabs) {
      if (isCapa) {
        capaSubtabs.style.display = "";
        window.AOI_CAPA?.buildRightSubTabs?.(capaSubtabs);
      } else {
        capaSubtabs.style.display = "none";
      }
    }
  }

  async function showView(rawView) {
    const view = normalizeView(rawView);
    const sections = getSections();

    Object.entries(sections).forEach(([key, el]) => {
      if (!el) return;
      el.style.display = key === view ? "" : "none";
    });

    swapTopArea(view);

    await ensureViewInit(view);

    swapTopArea(view);

    window.BPI_AREA?.hideAllSections?.();
    window.AOI_BPI_DENSITY?.hideAllSections?.();
    window.AOI_DENSITY?.hideAllSections?.();
    window.AOI_INSPECTION?.hideAllSections?.();

    if (view === "aoi-bpi-density") {
      if (window.BPI_AREA?.syncSectionVisibility) {
        window.BPI_AREA.syncSectionVisibility();
      } else {
        window.AOI_BPI_DENSITY?.syncSectionVisibility?.();
      }
    }

    
    if (view === "aoi-density") {
      window.AOI_DENSITY?.syncSectionVisibility?.();
    }

    if (view === "aoi-inspection-density") {
      window.AOI_INSPECTION?.syncSectionVisibility?.();
    }

    if (view === "aoi-capa") {
      window.AOI_CAPA?.Router?.redraw?.();
    }
  }

  function syncActiveButton(tabButtons, rawView) {
    const target = normalizeView(rawView);
    tabButtons.forEach((btn) => {
      const btnView = normalizeView(btn.dataset.view);
      btn.classList.toggle("active", btnView === target);
    });
  }

  function resolveInitialView(tabButtons) {
    const activeBtn = tabButtons.find((b) => b.classList.contains("active"));
    if (activeBtn?.dataset.view) {
      return normalizeView(activeBtn.dataset.view);
    }

    if (window.DEFAULT_SYSTEM_VIEW) {
      return normalizeView(window.DEFAULT_SYSTEM_VIEW);
    }

    return "aoi-density";
  }

  function initTabs() {
    const tabButtons = $all("#system-tabs .sys-tab");
    if (!tabButtons.length) return;

    tabButtons.forEach((btn) => {
      btn.addEventListener("click", async () => {
        const rawView = btn.dataset.view;
        syncActiveButton(tabButtons, rawView);

        try {
          await showView(rawView);
        } catch (err) {
          console.error("[system_tab] showView failed:", err);
          alert(`切換頁面失敗：${err.message || err}`);
        }
      });
    });

    const initialView = resolveInitialView(tabButtons);
    syncActiveButton(tabButtons, initialView);

    showView(initialView).catch((err) => {
      console.error("[system_tab] initial showView failed:", err);
      alert(`初始化頁面失敗：${err.message || err}`);
    });
  }

  document.addEventListener("DOMContentLoaded", initTabs);
})();