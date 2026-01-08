// 系統上方分頁切換（defect-map / aoi_density / inspection / aoi_capa）
(function () {
  function $(sel, root = document) { return root.querySelector(sel); }
  function $all(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }

  // 對應每個 view 的容器（不存在的就忽略）
  function getSections() {
    return {
      "defect-map": $("#defect-map-root") || $("#defect-map-section"),
      "aoi_density": $("#aoi_density-root"),
      "inspection": $("#inspection-root"),
      "aoi_capa": $("#aoi_capa-root"),
      "report": $("#report-root"),
    };
  }

  // 只在第一次顯示 AOI Density 時初始化（lazy init）
  function ensureAoiDensityInit() {
    if (window.__aoi_density_inited) return;
    window.__aoi_density_inited = true;
    window.AOI_DENSITY_Router?.ensureInit?.();
  }

  // 只在第一次顯示 Inspection 時初始化
  function ensureInspectionInit() {
    if (window.__aoi_inspection_inited) return;
    window.__aoi_inspection_inited = true;
    window.AOI_INSPECTION_Router?.ensureInit?.();
  }

  // 只在第一次顯示 AOI CAPA 時初始化
  function ensureAoiCapaInit() {
    if (window.__aoi_capa_inited) return;
    window.__aoi_capa_inited = true;
    window.AOI_CAPA_Router?.ensureInit?.();
  }

  // 右上區域 + 中間 line_tabs 的切換
  function swapTopArea(view) {
    const dateBox        = $("#global-filter");        // defect-map 的日期
    const densitySubtabs = $("#aoi_density-subtabs");  // density 的 subtabs
    const inspSubtabs    = $("#inspection-subtabs");   // inspection 的 subtabs
    const lineTabs       = $("#all-tab-container");    // defect-map 的 line tabs

    const isDefect     = (view === "defect-map");
    const isDensity    = (view === "aoi_density");
    const isInspection = (view === "inspection");

    // 日期只在 defect-map 顯示
    if (dateBox) {
      dateBox.style.display = isDefect ? "" : "none";
    }

    // line tabs 只在 defect-map 顯示
    if (lineTabs) {
      lineTabs.style.display = isDefect ? "" : "none";
    }

    // density 的 subtabs
    if (densitySubtabs) {
      if (isDensity) {
        densitySubtabs.style.display = "";
        window.AOI_DENSITY?.buildRightSubTabs?.(densitySubtabs);
      } else {
        densitySubtabs.style.display = "none";
      }
    }

    // inspection 的 subtabs
    if (inspSubtabs) {
      if (isInspection) {
        inspSubtabs.style.display = "";
        window.AOI_INSPECTION?.buildRightSubTabs?.(inspSubtabs);
      } else {
        inspSubtabs.style.display = "none";
      }
    }
  }

  function showView(view) {
    const sections = getSections();

    // 顯示 / 隱藏每個 root 區塊（粗分：defect-map / aoi_density / inspection / aoi_capa）
    Object.entries(sections).forEach(([key, el]) => {
      if (!el) return;
      el.style.display = (key === view) ? "" : "none";
    });

    // ==== 跟 aoi_density 溝通：管理底下三個 section ====
    if (view === "aoi_density") {
      window.AOI_DENSITY?.syncSectionVisibility?.();
    } else {
      window.AOI_DENSITY?.hideAllSections?.();
    }

    // ==== 跟 inspection 溝通：管理底下三個 section ====
    if (view === "inspection") {
      window.AOI_INSPECTION?.syncSectionVisibility?.();
    } else {
      window.AOI_INSPECTION?.hideAllSections?.();
    }

    // 切換上方右邊區塊 (日期 / subtabs)
    swapTopArea(view);

    // 依頁面做初始化
    if (view === "aoi_density") {
      ensureAoiDensityInit();
    } else if (view === "inspection") {
      ensureInspectionInit();
    } else if (view === "aoi_capa") {
      ensureAoiCapaInit();
    }
  }

  function initTabs() {
    const tabButtons = $all("#system-tabs .sys-tab");
    if (!tabButtons.length) return;

    tabButtons.forEach(btn => {
      btn.addEventListener("click", () => {
        const view = btn.dataset.view;
        tabButtons.forEach(b => b.classList.toggle("active", b === btn));
        showView(view);
      });
    });

    // ★★ 預設頁 = aoi_density ★★
    let initialView = "inspection";
    let initialBtn  = tabButtons.find(b => b.dataset.view === "inspection");

    if (!initialBtn) {
      initialBtn = tabButtons[0];
      initialView = initialBtn?.dataset.view;
    }

    tabButtons.forEach(b => b.classList.toggle("active", b === initialBtn));
    showView(initialView);
  }

  document.addEventListener("DOMContentLoaded", initTabs);
})();