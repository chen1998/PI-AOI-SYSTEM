// static/js/duty/cell_aoi_to_array/cell_aoi_to_array_tabs.js
(function () {
    "use strict";
  
    window.CELL_AOI_TO_ARRAY = window.CELL_AOI_TO_ARRAY || {};
    const MOD = window.CELL_AOI_TO_ARRAY;
  
    MOD.Tabs = {
      init,
      render,
      activateFeature,
      showEmptyCategory,
      showEmptyFeature
    };
  
    function init() {
      const { dom } = MOD.State;
      if (!dom.categoryTabs || !dom.featureTabs) return;
  
      dom.categoryTabs.addEventListener("click", function (event) {
        const btn = event.target.closest("[data-category]");
        if (!btn) return;
  
        const { state } = MOD.State;
        const cfg = MOD.State.getConfig();
  
        state.category = btn.dataset.category;
        state.feature = cfg.defaultFeatureByCategory?.[state.category] || "";
        state.filters.tool = "";
  
        render();
  
        if (!state.feature) {
          showEmptyCategory();
          return;
        }
  
        MOD.Filters.render();
        activateFeature(state.feature);
        MOD.Main.reload();
      });
  
      dom.featureTabs.addEventListener("click", function (event) {
        const btn = event.target.closest("[data-feature]");
        if (!btn) return;
  
        const { state } = MOD.State;
        state.feature = btn.dataset.feature;
        state.filters.tool = "";
  
        renderFeatureTabs();
        MOD.Filters.render();
        activateFeature(state.feature);
        MOD.Main.reload();
      });
    }
  
    function render() {
      renderCategoryTabs();
      renderFeatureTabs();
    }
  
    function renderCategoryTabs() {
      const { dom, state } = MOD.State;
      const cfg = MOD.State.getConfig();
  
      dom.categoryTabs.innerHTML = "";
  
      (cfg.categoryTabs || []).forEach(function (tab) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "cell-aoi-to-array-category-tab";
        btn.dataset.category = tab.key;
        btn.textContent = tab.label;
        btn.classList.toggle("active", tab.key === state.category);
        dom.categoryTabs.appendChild(btn);
      });
    }

    function renderChartFormulaHint(targetEl) {
      if (!targetEl) return;
    
      targetEl.innerHTML = "";
    
      const wrap = document.createElement("div");
      wrap.className = "cell-aoi-to-array-chart-hint-wrap";
    
      const label = document.createElement("span");
      label.className = "cell-aoi-to-array-chart-hint-label";
      label.textContent = "比對率說明";
    
      const icon = document.createElement("button");
      icon.type = "button";
      icon.className = "cell-aoi-to-array-chart-hint-icon";
      icon.textContent = "ⓘ";
      icon.setAttribute("aria-label", "查看比對率計算公式");
    
      const tooltip = document.createElement("div");
      tooltip.className = "cell-aoi-to-array-chart-hint-tooltip";
      tooltip.innerHTML = [
        "<b>同點比對率計算公式</b>",
        "同點比對率 = 同點 defect 數 ÷ CELL AOI defect 總數 × 100%",
        "",
        "同點 defect 數：以 CELL AOI defect 為主體，在指定 offset 範圍內找到最近前站 defect 的 CELL defect 數。",
        "CELL AOI defect 總數：該片 glass 在 CELL AOI 量測到的 defect 總數。",
        "",
        "規則：單一 CELL defect 若對應多個前站 defect，只計算 1 點，取最近的前站 defect；同一個前站 defect 可對應多個 CELL defect。"
      ].join("<br/>");
    
      icon.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
    
        const isOpen = wrap.classList.contains("is-open");
    
        closeAllChartFormulaHints();
    
        if (!isOpen) {
          wrap.classList.add("is-open");
        }
      });
    
      document.addEventListener("click", function () {
        closeAllChartFormulaHints();
      });
    
      tooltip.addEventListener("click", function (ev) {
        ev.stopPropagation();
      });
    
      wrap.appendChild(label);
      wrap.appendChild(icon);
      wrap.appendChild(tooltip);
    
      targetEl.appendChild(wrap);
    }
    
    function closeAllChartFormulaHints() {
      document
        .querySelectorAll(".cell-aoi-to-array-chart-hint-wrap.is-open")
        .forEach(function (el) {
          el.classList.remove("is-open");
        });
    }
  
    function renderFeatureTabs() {
      const { dom, state } = MOD.State;
      const cfg = MOD.State.getConfig();
      const features = cfg.featureTabsByCategory?.[state.category] || [];
  
      dom.featureTabs.innerHTML = "";
      dom.featureTabs.classList.toggle("is-empty", features.length === 0);
  
      if (!features.length) {
        state.feature = "";
        return;
      }
  
      const exists = features.some(item => item.key === state.feature);
      if (!exists) {
        state.feature = cfg.defaultFeatureByCategory?.[state.category] || features[0].key;
      }
  
      features.forEach(function (tab) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "cell-aoi-to-array-feature-tab";
        btn.dataset.feature = tab.key;
        btn.textContent = tab.label;
        btn.classList.toggle("active", tab.key === state.feature);
        dom.featureTabs.appendChild(btn);
      });
    }
  
    function activateFeature(featureKey) {
      const { dom, state } = MOD.State;
      const feature = MOD.State.getCurrentFeature();
      const featureConfig = MOD.State.getFeatureConfig(featureKey);
  
      if (!feature || feature.type !== "compare") {
        showEmptyFeature(feature);
        return;
      }
  
      dom.compareSection.style.display = "";
      dom.emptySection.style.display = "none";
  
      dom.chartTitle.textContent =
        featureConfig.chartTitle ||
        featureConfig.title ||
        feature.title ||
        feature.label ||
        "";
  
      renderChartFormulaHint(dom.chartSubtitle);
      dom.activeBadge.textContent = `${state.category} / ${feature.label || featureConfig.label || featureKey}`;
  
      MOD.Main.renderInfo(null);
      MOD.Charts.renderSkeleton();
      MOD.Table.renderHead();
    }
  
    function showEmptyCategory() {
      const { dom, state } = MOD.State;
  
      dom.compareSection.style.display = "none";
      dom.emptySection.style.display = "";
      dom.emptyText.textContent = `${state.category} 尚未設定功能分頁。`;
      dom.activeBadge.textContent = state.category;
  
      MOD.Sheet.renderEmpty();
    }
  
    function showEmptyFeature(feature) {
      const { dom, state } = MOD.State;
  
      dom.compareSection.style.display = "none";
      dom.emptySection.style.display = "";
      dom.emptyText.textContent = feature ? `${feature.label} 尚未接入內容。` : "此功能尚未設定。";
      dom.activeBadge.textContent = feature ? `${state.category} / ${feature.label}` : state.category;
  
      MOD.Sheet.renderEmpty();
    }
  })();
  