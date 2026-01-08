// 系統上方分頁切換（defect-map / aoi_density / report）— 首次顯示 aoi_density 才初始化取數
(function () {
  function $(sel, root = document) { return root.querySelector(sel); }
  function $all(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }

  // 對應每個 view 的容器（不存在的就忽略）
  function getSections() {
    return {
      "defect-map": $("#defect-map-root"),
      "aoi_density": $("#aoi_density-root"),
      "report": $("#report-root"),
    };
  }

  // 只在第一次顯示 AOI Density 時初始化（lazy init）
  function ensureAoiDensityInit() {
    if (window.__aoi_density_inited) return;
    window.__aoi_density_inited = true;
    // 這裡才真正去打 API、建 filter、畫圖
    window.AOI_DENSITY_Router?.ensureInit();
  }

  // 右上區域切換：日期 <-> AOI Density 子分頁（保留 DOM，不銷毀）
  function swapTopRight(view) {
    const dateBox = $("#global-filter");           // 右上的全域日期區塊
    const subtabs = $("#aoi_density-subtabs");     // 右上的 AOI Density 子分頁容器
    if (!dateBox || !subtabs) return;

    if (view === "aoi_density") {
      // 顯示子分頁、隱藏日期
      dateBox.style.display = "none";
      subtabs.style.display = "";
      window.AOI_DENSITY?.buildRightSubTabs?.(subtabs);
    } else {
      // 其餘視圖切回日期（特別是 defect-map）
      subtabs.style.display = "none";
      dateBox.style.display = "";
    }
  }

  function showView(view) {
    const sections = getSections();
    Object.entries(sections).forEach(([key, el]) => {
      if (!el) return;
      el.style.display = (key === view) ? "" : "none";
    });

    // 右上區域切換
    swapTopRight(view);

    if (view === "aoi_density") ensureAoiDensityInit();
  }

  function initTabs() {
    const tabButtons = $all("#system-tabs .sys-tab");
    if (!tabButtons.length) return;

    tabButtons.forEach(btn => {
      btn.addEventListener("click", () => {
        const view = btn.dataset.view; // e.g. "aoi_density"
        // 切換 active 樣式
        tabButtons.forEach(b => b.classList.toggle("active", b === btn));
        // 顯示對應區塊（若是 aoi_density，這裡會做 lazy init）
        showView(view);
      });
    });

    // 初始顯示：依當前 active 指向；若沒有就顯示 defect-map（不觸發 aoi_density 取數）
    const activeBtn = $("#system-tabs .sys-tab.active");
    const fallback = "aoi_density"; //"defect-map";
    const defaultView = activeBtn?.dataset.view || fallback;

    // 若 active 指向不存在的區塊，退回 fallback
    const sections = getSections();
    const initialView = sections[defaultView] ? defaultView : fallback;

    tabButtons.forEach(b => b.classList.toggle("active", b.dataset.view === initialView));
    showView(initialView); // 若 initialView 是 aoi_density，會觸發一次 lazy init
  }

  document.addEventListener("DOMContentLoaded", initTabs);
})();