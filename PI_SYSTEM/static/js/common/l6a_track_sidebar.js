// static/js/common/l6a_track_sidebar.js
(function () {
    "use strict";
  
    const shell = document.getElementById("l6a-track-shell");
    const sidebar = document.getElementById("l6a-track-sidebar");
    const sidebarInner = document.getElementById("l6a-track-sidebar-inner");
  
    if (!shell || !sidebar || !sidebarInner) return;
  
    const STORAGE_KEY = "l6a-track-sidebar-state";

    let cellAoiToArrayScriptsLoading = null;
    let cellAoiToArrayScriptsLoaded = false;

    const CELL_AOI_TO_ARRAY_SCRIPT_LIST = [
      "/static/js/duty/cell_aoi_to_array/cell_aoi_to_array_api.js",
      "/static/js/duty/cell_aoi_to_array/cell_aoi_to_array_state.js",
      "/static/js/duty/cell_aoi_to_array/cell_aoi_to_array_ui.js",
      "/static/js/duty/cell_aoi_to_array/cell_aoi_to_array_summary.js",
      "/static/js/duty/cell_aoi_to_array/cell_aoi_to_array_tabs.js",
      "/static/js/duty/cell_aoi_to_array/cell_aoi_to_array_filters.js",
      "/static/js/duty/cell_aoi_to_array/cell_aoi_to_array_map.js",
      "/static/js/duty/cell_aoi_to_array/cell_aoi_to_array_defect_table.js",
      "/static/js/duty/cell_aoi_to_array/cell_aoi_to_array_sheet.js",
      "/static/js/duty/cell_aoi_to_array/cell_aoi_to_array_table.js",
      "/static/js/duty/cell_aoi_to_array/cell_aoi_to_array_charts.js",
      "/static/js/duty/cell_aoi_to_array/cell_aoi_to_array_main.js"
    ];

    // =========================================================
    // 之後若改 API，只要讓後端回傳類似這個結構即可
    // =========================================================
    const menuTree = {
      title: "L6A AOI",
      defaultView: "pi-aoi-analysis",
      sections: [
        /*{ 
          title: "個人",
          children: [
            {
              label: "專案管理",
              view: "project-management"
            },
            {
              label: "表單中心",
              view: "form-center"
            }
          ]
        },
        {
          title: "總攬",
          children: [
            {
              label: "異常管理平台",
              view: "abnormal-platform"
            },
            {
              label: "AI與智慧製造專案",
              view: "ai-smart-manufacturing-project"
            }
          ]
        },
        */
        {
          title: "流程優化",
          children: [
            /*{
              label: "設備品質管理",
              view: "equipment-quality"
            },
            {
              label: "產品品質管理",
              view: "product-quality"
            },*/
            {
              label: "值班專區",
              children: [
                {
                  label: "Cell值班",
                  children: [
                    {
                      label: "來料檢",
                      view: "incoming-inspection"
                    },
                    {
                      label: "PI AOI量測分析工具",
                      view: "pi-aoi-analysis"
                    }
                  ]
                }
              ]
            }
          ]
        },
        /*
        {
          title: "工具庫",
          children: [
            {
              label: "工具庫",
              view: "tool-library"
            }
          ]
        }
        */
      ]
    };
  
    // =========================================================
    // Render
    // =========================================================
    function renderSidebar(tree) {
      sidebarInner.innerHTML = "";
  
      const header = document.createElement("div");
      header.className = "l6a-track-sidebar-header";
  
      const title = document.createElement("div");
      title.className = "l6a-track-title";
      title.textContent = tree.title || "L6A Track";
  
      header.appendChild(title);
  
      const nav = document.createElement("nav");
      nav.className = "l6a-track-nav";
  
      (tree.sections || []).forEach(function (section) {
        const sectionEl = document.createElement("section");
        sectionEl.className = "l6a-track-nav-section";
  
        const sectionTitle = document.createElement("button");
        sectionTitle.className = "l6a-track-section-title";
        sectionTitle.type = "button";
        sectionTitle.textContent = section.title || "";
  
        const menu = document.createElement("div");
        menu.className = "l6a-track-menu";
  
        renderMenuItems(section.children || [], menu, 0);
  
        sectionEl.appendChild(sectionTitle);
        sectionEl.appendChild(menu);
        nav.appendChild(sectionEl);
      });
  
      const footer = document.createElement("div");
      footer.className = "l6a-track-sidebar-footer";
  
      const toggleBtn = document.createElement("button");
      toggleBtn.id = "l6a-track-toggle-sidebar";
      toggleBtn.className = "l6a-track-toggle-sidebar";
      toggleBtn.type = "button";
      toggleBtn.title = "收合 / 展開";
      toggleBtn.innerHTML = `
        <span class="l6a-track-toggle-icon">‹</span>
        <span class="l6a-track-toggle-text">收合</span>
      `;
  
      footer.appendChild(toggleBtn);
  
      sidebarInner.appendChild(header);
      sidebarInner.appendChild(nav);
      sidebarInner.appendChild(footer);
    }
  
    function renderMenuItems(items, parentEl, level) {
      items.forEach(function (item) {
        const hasChildren = Array.isArray(item.children) && item.children.length > 0;
  
        if (hasChildren) {
          const group = document.createElement("div");
          group.className = "l6a-track-menu-group";
          group.dataset.l6aLevel = String(level);
  
          const btn = document.createElement("button");
          btn.className = "l6a-track-menu-item l6a-track-has-children";
          btn.type = "button";
          btn.textContent = item.label || "";
  
          const submenu = document.createElement("div");
          submenu.className = "l6a-track-submenu";
          submenu.dataset.l6aLevel = String(level + 1);
  
          renderMenuItems(item.children || [], submenu, level + 1);
  
          group.appendChild(btn);
          group.appendChild(submenu);
          parentEl.appendChild(group);
          return;
        }
  
        const btn = document.createElement("button");
        btn.className = level > 0 ? "l6a-track-submenu-item" : "l6a-track-menu-item";
        btn.type = "button";
        btn.textContent = item.label || "";
        btn.dataset.l6aView = item.view || "";
  
        parentEl.appendChild(btn);
      });
    }
  
    // =========================================================
    // Sidebar open / close
    // =========================================================
    function isClosed() {
      return shell.classList.contains("l6a-track-sidebar-closed");
    }
  
    function setSidebarState(nextState, save) {
      const closed = nextState === "closed";
  
      shell.classList.toggle("l6a-track-sidebar-open", !closed);
      shell.classList.toggle("l6a-track-sidebar-closed", closed);
      shell.classList.remove("l6a-track-sidebar-hover-open");
  
      const toggleIcon = document.querySelector(".l6a-track-toggle-icon");
      const toggleText = document.querySelector(".l6a-track-toggle-text");
  
      if (toggleIcon) toggleIcon.textContent = closed ? "›" : "‹";
      if (toggleText) toggleText.textContent = closed ? "展開" : "收合";
  
      if (save) {
        try {
          localStorage.setItem(STORAGE_KEY, closed ? "closed" : "open");
        } catch (err) {
          // ignore
        }
      }
  
      requestResizeCharts();
    }
  
    function bindSidebarEvents() {
      const toggleBtn = document.getElementById("l6a-track-toggle-sidebar");
  
      if (toggleBtn) {
        toggleBtn.addEventListener("click", function () {
          setSidebarState(isClosed() ? "open" : "closed", true);
        });
      }
  
      sidebar.addEventListener("mouseenter", function () {
        if (!isClosed()) return;
        shell.classList.add("l6a-track-sidebar-hover-open");
        requestResizeCharts();
      });
  
      sidebar.addEventListener("mouseleave", function () {
        if (!isClosed()) return;
        shell.classList.remove("l6a-track-sidebar-hover-open");
        requestResizeCharts();
      });
  
      sidebar.addEventListener("click", function (event) {
        const btn = event.target.closest("[data-l6a-view]");
        if (!btn) return;
  
        const view = btn.dataset.l6aView;
        if (!view) return;
  
        activateL6aPage(view);
        setActiveMenu(view);
      });
    }
  
    // =========================================================
    // Page switch
    // =========================================================
    function activateL6aPage(view) {
      const pages = document.querySelectorAll(".l6a-track-page");

      pages.forEach(function (page) {
        const matched = page.dataset.l6aPage === view;

        page.classList.toggle("active", matched);
        page.style.display = matched ? "" : "none";

        if (!matched) return;

        // placeholder 自動補標題，避免空白
        if (
          page.classList.contains("l6a-track-placeholder-page") &&
          !page.dataset.rendered
        ) {
          page.innerHTML = `
            <div class="card">
              <h2>${escapeHtml(getMenuLabelByView(view) || view)}</h2>
              <p class="muted">此功能尚未接入。</p>
            </div>
          `;
          page.dataset.rendered = "1";
        }

        activatePageModule(view, page);
      });

      requestResizeCharts();
    }


    function activatePageModule(view, page) {
      if (view === "incoming-inspection") {
        activateIncomingInspectionPage(page);
        return;
      }

      if (view === "pi-aoi-analysis") {
        requestResizeCharts();
        return;
      }
    }


    function loadScriptOnce(src) {
      return new Promise(function (resolve, reject) {
        if (document.querySelector(`script[data-lazy-src="${src}"]`)) {
          resolve();
          return;
        }
    
        const script = document.createElement("script");
        script.src = src;
        script.async = false;
        script.dataset.lazySrc = src;
    
        script.onload = function () {
          resolve();
        };
    
        script.onerror = function () {
          reject(new Error("Failed to load script: " + src));
        };
    
        document.body.appendChild(script);
      });
    }
    
    
    async function loadCellAoiToArrayScripts() {
      if (cellAoiToArrayScriptsLoaded) {
        return;
      }
    
      if (cellAoiToArrayScriptsLoading) {
        return cellAoiToArrayScriptsLoading;
      }
    
      cellAoiToArrayScriptsLoading = (async function () {
        for (const src of CELL_AOI_TO_ARRAY_SCRIPT_LIST) {
          await loadScriptOnce(src);
        }
    
        cellAoiToArrayScriptsLoaded = true;
      })();
    
      return cellAoiToArrayScriptsLoading;
    }

    
    async function activateIncomingInspectionPage(page) {
      try {
        await loadCellAoiToArrayScripts();
      } catch (err) {
        console.error("[L6A] load CELL_AOI_TO_ARRAY scripts failed", err);
        return;
      }
    
      const mod = window.CELL_AOI_TO_ARRAY;
    
      if (
        !mod ||
        !mod.State ||
        !mod.Tabs ||
        !mod.Filters ||
        !mod.Main ||
        !mod.Charts ||
        !mod.Table
      ) {
        window.setTimeout(function () {
          activateIncomingInspectionPage(page);
        }, 80);
        return;
      }
    
      if (!page.dataset.cellAoiToArrayActivated) {
        page.dataset.cellAoiToArrayActivated = "1";
    
        if (typeof mod.Tabs.render === "function") {
          mod.Tabs.render();
        }
    
        if (typeof mod.Filters.render === "function") {
          mod.Filters.render();
        }
    
        const state = mod.State.state || {};
        const currentFeature = state.feature || "";
    
        if (currentFeature && typeof mod.Tabs.activateFeature === "function") {
          mod.Tabs.activateFeature(currentFeature);
        }
    
        if (typeof mod.Main.reload === "function") {
          mod.Main.reload();
        }
    
        return;
      }
    
      if (mod.Charts && typeof mod.Charts.resize === "function") {
        mod.Charts.resize();
      }
    }


    function setActiveMenu(view) {
      document.querySelectorAll("[data-l6a-view]").forEach(function (btn) {
        btn.classList.toggle("active", btn.dataset.l6aView === view);
      });
    }
  
    function getMenuLabelByView(view) {
      let result = "";
  
      function walk(items) {
        for (const item of items || []) {
          if (item.view === view) {
            result = item.label || "";
            return true;
          }
  
          if (item.children && walk(item.children)) {
            return true;
          }
        }
  
        return false;
      }
  
      for (const section of menuTree.sections || []) {
        if (walk(section.children || [])) break;
      }
  
      return result;
    }
  
    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }
  
    // =========================================================
    // Resize charts
    // =========================================================
    function requestResizeCharts() {
      window.setTimeout(function () {
        window.dispatchEvent(new Event("resize"));
  
        if (!window.echarts) return;
  
        document.querySelectorAll("[_echarts_instance_]").forEach(function (el) {
          try {
            const chart = window.echarts.getInstanceByDom(el);
            if (chart) chart.resize();
          } catch (err) {
            // ignore
          }
        });
      }, 260);
    }
  
    // =========================================================
    // Init
    // =========================================================
    function init() {
      renderSidebar(menuTree);
      bindSidebarEvents();
  
      let saved = "open";
  
      try {
        saved = localStorage.getItem(STORAGE_KEY) || "open";
      } catch (err) {
        saved = "open";
      }
  
      setSidebarState(saved === "closed" ? "closed" : "open", false);
  
      const defaultView = menuTree.defaultView || "pi-aoi-analysis";
      activateL6aPage(defaultView);
      setActiveMenu(defaultView);
    }
  
    init();
  })();
  