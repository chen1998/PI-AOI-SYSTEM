// static/js/bpi_area/common/service.js
// BPI Area 總控：
// - 管理「來料檢(BPI/同點)」system tab 底下的 section 切換
// - 建立右上兩排 subtabs
// - 分流 BPI Density 與 BPI/API Same Point
// - Table / Action_History / Default Spec 統一走 bpi-area-table-tab-root
//
// Namespace：
// - window.BPI_AREA
// - window.BPI_AREA.Router.ensureInit()

(function () {
  const AREA = (window.BPI_AREA = window.BPI_AREA || {});
  const BPI = (window.AOI_BPI_DENSITY = window.AOI_BPI_DENSITY || {});

  const $ = (sel, root = document) => root.querySelector(sel);
  const $all = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  // ============================================================
  // Section 管理
  // ============================================================
  const BPI_AREA_SECTION_IDS = [
    "aoi-bpi-density-root",
    "bpi-area-table-tab-root",
    "bpi-same-point-root",
    "density-csv-download-root",
    "density-avg-download-root",
  ];

  AREA.state = AREA.state || {
    inited: false,
    loading: false,
    payload: null,
    paramDict: null,
    activeSubTab: null,
    currentSectionId: "aoi-bpi-density-root",
  };

  AREA.hideAllSections = function () {
    BPI_AREA_SECTION_IDS.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = "none";
    });
  };

  AREA.showSection = function (sectionId) {
    AREA.state.currentSectionId = sectionId || "aoi-bpi-density-root";

    BPI_AREA_SECTION_IDS.forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.style.display = (id === AREA.state.currentSectionId) ? "" : "none";
    });
  };

  AREA.syncSectionVisibility = function () {
    AREA.showSection(AREA.state.currentSectionId || "aoi-bpi-density-root");
  };

  // ============================================================
  // ParamDict helpers
  // ============================================================
  function normalizeParamDict(paramDict) {
    const pd = paramDict || {};
    const bpiDensity = pd.bpiDensity || {};
    const bpiSamePoint = pd.bpiSamePoint || {};

    // 舊版 BPI Density 元件相容
    if (!pd.chartKeyDict && bpiDensity.chartKeyDict) {
      pd.chartKeyDict = bpiDensity.chartKeyDict;
    }

    if (!pd.filtetItemKeyDict && bpiDensity.filtetItemKeyDict) {
      pd.filtetItemKeyDict = bpiDensity.filtetItemKeyDict;
    }

    if (!pd.filterItemKeyDict && bpiDensity.filterItemKeyDict) {
      pd.filterItemKeyDict = bpiDensity.filterItemKeyDict;
    }

    if (!pd.hourlyTable && bpiDensity.hourlyTable) {
      pd.hourlyTable = bpiDensity.hourlyTable;
    }

    if (!pd.hourlyTable_key_group && bpiDensity.hourlyTable_key_group) {
      pd.hourlyTable_key_group = bpiDensity.hourlyTable_key_group;
    }

    if (!pd.uniGlassInfo && bpiDensity.uniGlassInfo) {
      pd.uniGlassInfo = bpiDensity.uniGlassInfo;
    }

    if (!pd.filterOptionDict && bpiDensity.filterOptionDict) {
      pd.filterOptionDict = bpiDensity.filterOptionDict;
    }

    if (!pd.SubTabsFilterDefaultDict) {
      pd.SubTabsFilterDefaultDict = {};
    }

    if (!pd.SubTabGroups) {
      pd.SubTabGroups = {
        bpi_density: {
          label: "BPI",
          order: 1,
        },
        bpi_same_point: {
          label: "同點",
          order: 2,
        },
      };
    }

    if (!pd.bpiDensity) pd.bpiDensity = bpiDensity;
    if (!pd.bpiSamePoint) pd.bpiSamePoint = bpiSamePoint;

    return pd;
  }

  function getParamDict() {
    const pd =
      AREA.state.paramDict ||
      BPI.state?.paramDict ||
      AREA.state.payload?.ParamDict ||
      null;

    return normalizeParamDict(pd || {});
  }

  function getSubTabsMap() {
    return getParamDict().SubTabsFilterDefaultDict || {};
  }

  function getGroupsConfig() {
    return getParamDict().SubTabGroups || {
      bpi_density: {
        label: "BPI",
        order: 1,
      },
      bpi_same_point: {
        label: "同點",
        order: 2,
      },
    };
  }

  function getTabGroup(tabKey, conf) {
    const g = String(conf?.tab_group || "").trim();
    if (g) return g;

    if (
      tabKey === "Hourly" ||
      tabKey === "bpi_density_main" ||
      tabKey === "bpi_density_action_history" ||
      tabKey === "bpi_density_default_spec" ||
      tabKey === "bpi_density_csv_download" ||
      tabKey === "bpi_density_average"
    ) {
      return "bpi_density";
    }

    if (
      tabKey === "bpi_same_point_main" ||
      tabKey === "bpi_same_point_pispot" ||
      tabKey === "bpi_same_point_upi" ||
      tabKey === "bpi_same_point_action_history" ||
      tabKey === "bpi_same_point_default_spec" ||
      tabKey === "bpi_same_point_csv_download" ||
      tabKey === "bpi_same_point_average"
    ) {
      return "bpi_same_point";
    }

    const label = String(conf?.tab_name || tabKey || "");
    if (label.includes("同點")) return "bpi_same_point";

    return "bpi_density";
  }

  function getSystemByGroup(group) {
    return group === "bpi_same_point" ? "bpi_same_point" : "bpi_density";
  }

  function getTabOrder(tabKey, conf) {
    const n = Number(conf?.tab_order);
    if (Number.isFinite(n)) return n;

    const fallback = {
      Hourly: 10,

      bpi_density_main: 10,
      bpi_density_action_history: 20,
      bpi_density_default_spec: 30,
      bpi_density_csv_download: 40,
      bpi_density_average: 50,

      bpi_same_point_pispot: 10,
      bpi_same_point_upi: 20,
      bpi_same_point_action_history: 30,
      bpi_same_point_default_spec: 40,
      bpi_same_point_csv_download: 50,
      bpi_same_point_average: 60,
    };

    return fallback[tabKey] || 999;
  }

  function getTabType(conf) {
    return String(conf?.type || "").trim();
  }

  function isBpiDensityHourly(tabKey, conf) {
    const group = getTabGroup(tabKey, conf);
    const type = getTabType(conf);

    return group === "bpi_density" && (type === "" || type === "hourly");
  }

  function isSamePointHourly(tabKey, conf) {
    const group = getTabGroup(tabKey, conf);
    const type = getTabType(conf);

    return group === "bpi_same_point" && (
      type === "hourly" ||
      type === "bpi_same_point"
    );
  }

  function isActionHistoryTab(tabKey, conf) {
    const name = String(conf?.tab_name || tabKey || "").toLowerCase();
    return (
      String(tabKey || "").includes("action_history") ||
      name === "action_history" ||
      name.includes("action")
    );
  }

  function isDefaultSpecTab(tabKey, conf) {
    const name = String(conf?.tab_name || tabKey || "").toLowerCase();
    return (
      String(tabKey || "").includes("default_spec") ||
      name.includes("預設spec") ||
      name.includes("default")
    );
  }

  // ============================================================
  // 初始化 BPI payload
  // ============================================================
  async function loadInitialBpiPayload() {
    if (!BPI.fetchBpiDensityData) {
      throw new Error("AOI_BPI_DENSITY.fetchBpiDensityData 不存在");
    }

    console.log("[BPI_AREA] loadInitialBpiPayload start");

    const payload = await BPI.fetchBpiDensityData();

    AREA.state.payload = payload || BPI.state?.payload || null;
    AREA.state.paramDict = normalizeParamDict(
      payload?.ParamDict || BPI.state?.paramDict || {}
    );

    if (BPI.state) {
      BPI.state.paramDict = AREA.state.paramDict;

      if (!BPI.state.uniques || !Object.keys(BPI.state.uniques || {}).length) {
        BPI.state.uniques =
          AREA.state.paramDict.bpiDensity?.filterOptionDict ||
          AREA.state.paramDict.filterOptionDict ||
          {};
      }
    }

    console.log("[BPI_AREA] loadInitialBpiPayload done", {
      hasPayload: !!AREA.state.payload,
      rows: BPI.state?.rows?.length || 0,
      paramDict: AREA.state.paramDict,
      proSpecDict: BPI.state?.ProSpecDict || {},
    });

    return AREA.state.payload;
  }

  // ============================================================
  // BPI Density redraw
  // ============================================================
  function readBpiDensityDatesFromUI() {
    const s = document.getElementById("aoi-bpi-density-start");
    const e = document.getElementById("aoi-bpi-density-end");
  
    const start = s?.value || "";
    const end = e?.value || "";
  
    return (start && end) ? [start, end] : undefined;
  }
  
  async function refreshBpiDensityByDates(dates) {
    if (!BPI.fetchBpiDensityData) {
      throw new Error("AOI_BPI_DENSITY.fetchBpiDensityData 不存在");
    }
  
    const payload = await BPI.fetchBpiDensityData({
      dates,
      filters: BPI.readFiltersFromUI ? BPI.readFiltersFromUI() : {}
    });
  
    AREA.state.payload = payload || BPI.state?.payload || null;
    AREA.state.paramDict = normalizeParamDict(
      payload?.ParamDict || BPI.state?.paramDict || {}
    );
  
    if (BPI.state) {
      BPI.state.paramDict = AREA.state.paramDict;
    }
  
    const subtabs = document.getElementById("aoi-bpi-density-subtabs");
    if (subtabs) {
      AREA.buildRightSubTabs(subtabs);
    }
  
    redrawBpiDensity();
  }
  
  function bindBpiDensityDateButtons() {
    const applyBtn = document.getElementById("aoi-bpi-density-apply");
    const clearBtn = document.getElementById("aoi-bpi-density-clear");
  
    if (applyBtn && applyBtn.dataset.bpiAreaDateBound !== "1") {
      applyBtn.dataset.bpiAreaDateBound = "1";
  
      applyBtn.addEventListener("click", async () => {
        const dates = readBpiDensityDatesFromUI();
        console.log("[BPI_AREA] date apply", dates);
  
        if (!dates) return;
  
        try {
          await refreshBpiDensityByDates(dates);
        } catch (err) {
          console.error("[BPI_AREA] BPI Density date apply failed:", err);
          alert("BPI Density 日期套用失敗：" + (err.message || err));
        }
      });
    }
  
    if (clearBtn && clearBtn.dataset.bpiAreaDateBound !== "1") {
      clearBtn.dataset.bpiAreaDateBound = "1";
  
      clearBtn.addEventListener("click", async () => {
        const s = document.getElementById("aoi-bpi-density-start");
        const e = document.getElementById("aoi-bpi-density-end");
  
        if (s) s.value = "";
        if (e) e.value = "";
  
        console.log("[BPI_AREA] date clear");
  
        try {
          await refreshBpiDensityByDates(undefined);
        } catch (err) {
          console.error("[BPI_AREA] BPI Density date clear failed:", err);
          alert("BPI Density 日期清空失敗：" + (err.message || err));
        }
      });
    }
  }

  function redrawBpiDensity() {
    const rows = BPI.getFiltered ? BPI.getFiltered() : (BPI.state?.rows || []);

    console.log("[BPI_AREA] redrawBpiDensity rows=", rows.length);

    if (BPI.Charts?.render) {
      BPI.Charts.render(rows, BPI.state?.paramDict);
    }

    if (BPI.Table?.render) {
      BPI.Table.render(rows, BPI.state?.paramDict);
    }
  }

  AREA.redrawBpiDensity = redrawBpiDensity;

  // ============================================================
  // Common table-tab helpers
  // ============================================================
  function resolveSpecRows(system, tabKey, conf) {
    const same = window.BPI_SAME_POINT;
  
    let pro = {};
  
    if (system === "bpi_same_point") {
      pro =
        same?.state?.ProSpecDict ||
        same?.state?.payload?.ProSpecDict ||
        {};
    } else {
      pro =
        BPI.state?.ProSpecDict ||
        BPI.state?.payload?.ProSpecDict ||
        {};
    }
  
    const base = [
      tabKey,
      conf?.data_key,
      conf?.table_name,
    ].filter(Boolean);
  
    const candidates = system === "bpi_same_point"
      ? [
          ...base,
          "bpi_same_point_default_spec",
          "bpi_same_point_default_spec_table",
        ]
      : [
          ...base,
          "bpi_density_default_spec",
          "default_spec_table",
        ];
  
    for (const key of candidates) {
      if (pro[key] !== undefined && pro[key] !== null) {
        return pro[key];
      }
    }
  
    return {};
  }
  async function fetchActionHistory(system, dates) {
    const api = window.AOI_BPI_DENSITY_API;
    if (!api?.ActionHisEditor) {
      throw new Error("AOI_BPI_DENSITY_API.ActionHisEditor 不存在");
    }

    return api.ActionHisEditor({
      system,
      mode: "date",
      dates: dates || null,
    });
  }

  async function showCommonTableTab(tabKey, conf, group, opts) {
    opts = opts || {};

    AREA.showSection("bpi-area-table-tab-root");

    const system = conf.system_key || getSystemByGroup(group);
    const actionHistory = isActionHistoryTab(tabKey, conf);
    const defaultSpec = isDefaultSpecTab(tabKey, conf);

    if (actionHistory) {
      let resp = null;

      if (opts.restoreOnly) {
        document.dispatchEvent(new CustomEvent("bpi-area:table-tab-show", {
          detail: {
            kind: "action_history",
            system,
            tabKey,
            tabGroup: group,
            config: conf,
            resp: null,
            restoreOnly: true,
          },
        }));
        return;
      }

      try {
        resp = await fetchActionHistory(system, null);
      } catch (err) {
        console.error("[BPI_AREA] fetchActionHistory failed", err);
        resp = {
          DictData: {},
          status: "error",
          error: String(err?.message || err),
        };
      }

      document.dispatchEvent(new CustomEvent("bpi-area:table-tab-show", {
        detail: {
          kind: "action_history",
          system,
          tabKey,
          tabGroup: group,
          config: conf,
          resp,
          restoreOnly: false,
        },
      }));

      return;
    }
    
    if (defaultSpec) {
      let rows = resolveSpecRows(system, tabKey, conf);
    
      if (
        system === "bpi_same_point" &&
        (!rows || (typeof rows === "object" && !Object.keys(rows).length))
      ) {
        const same = window.BPI_SAME_POINT;
    
        if (same?.ensureProSpecLoaded) {
          await same.ensureProSpecLoaded();
          rows = resolveSpecRows(system, tabKey, conf);
        } else if (same?.loadData) {
          await same.loadData({
            refreshFilter: false,
            source: "default_spec_lazy_load",
          });
    
          rows = resolveSpecRows(system, tabKey, conf);
        }
      }
    
      document.dispatchEvent(new CustomEvent("bpi-area:table-tab-show", {
        detail: {
          kind: "default_spec",
          system,
          tabKey,
          tabGroup: group,
          config: conf,
          data: rows,
          restoreOnly: !!opts.restoreOnly,
        },
      }));
    
      return;
    }
    
    document.dispatchEvent(new CustomEvent("bpi-area:table-tab-show", {
      detail: {
        kind: "table",
        system,
        tabKey,
        tabGroup: group,
        config: conf,
        data: {},
        restoreOnly: !!opts.restoreOnly,
      },
    }));
  }

  AREA.showCommonTableTab = showCommonTableTab;

  // ============================================================
  // Right subtabs
  // ============================================================
  AREA.buildRightSubTabs = function (containerEl) {
    const map = getSubTabsMap();
    const keys = Object.keys(map);

    if (!containerEl || !keys.length) {
      if (containerEl) containerEl.innerHTML = "";
      return;
    }

    containerEl.innerHTML = "";
    containerEl.classList.add("bpi-area-subtabs-two-rows");

    const groupCfg = getGroupsConfig();
    const groups = {};

    keys.forEach(key => {
      const conf = map[key] || {};
      const groupKey = getTabGroup(key, conf);

      if (!groups[groupKey]) {
        groups[groupKey] = {
          key: groupKey,
          label: groupCfg[groupKey]?.label || groupKey,
          order: Number(groupCfg[groupKey]?.order || 999),
          items: [],
        };
      }

      groups[groupKey].items.push({ key, conf });
    });

    const groupList = Object.values(groups).sort((a, b) => a.order - b.order);

    groupList.forEach(group => {
      group.items.sort((a, b) => {
        const oa = getTabOrder(a.key, a.conf);
        const ob = getTabOrder(b.key, b.conf);

        if (oa !== ob) return oa - ob;
        return String(a.key).localeCompare(String(b.key));
      });

      const row = document.createElement("div");
      row.className = `bpi-area-subtabs-row bpi-area-subtabs-row-${group.key}`;

      const title = document.createElement("span");
      title.className = "bpi-area-subtabs-row-title";
      title.textContent = group.label;
      row.appendChild(title);

      group.items.forEach(({ key, conf }) => {
        const btn = document.createElement("button");
        btn.className = "sys-tab";
        btn.textContent = conf.tab_name || key;
        btn.dataset.subkey = key;

        const type = getTabType(conf);
        if (type) btn.dataset.type = type;

        if (AREA.state.activeSubTab === key) {
          btn.classList.add("active");
        }

        btn.addEventListener("click", () => {
          $all(".sys-tab", containerEl).forEach(b => b.classList.remove("active"));
          btn.classList.add("active");
          AREA.applySubTab(key);
        });

        row.appendChild(btn);
      });

      containerEl.appendChild(row);
    });

    if (!AREA.state.activeSubTab) {
      const firstGroup = groupList[0];
      const firstKey = firstGroup?.items?.[0]?.key || keys[0];

      if (firstKey) {
        AREA.state.activeSubTab = firstKey;

        if (BPI.state) {
          BPI.state.activeSubTab = firstKey;
        }

        window.bpi_density_sub_activeTabKey = firstKey;

        const firstBtn = containerEl.querySelector(`[data-subkey="${firstKey}"]`);
        if (firstBtn) firstBtn.classList.add("active");

        AREA.applySubTab(firstKey);
      }

      return;
    }

    const activeBtn = containerEl.querySelector(`[data-subkey="${AREA.state.activeSubTab}"]`);
    if (activeBtn) activeBtn.classList.add("active");
  };

  // ============================================================
  // Dispatcher
  // ============================================================
  AREA.applySubTab = async function (tabKey) {
    const map = getSubTabsMap();
    const conf = map[tabKey] || {};
    const type = getTabType(conf);
    const group = getTabGroup(tabKey, conf);

    AREA.state.activeSubTab = tabKey;

    if (BPI.state) {
      BPI.state.activeSubTab = tabKey;
    }

    window.bpi_density_sub_activeTabKey = tabKey;

    AREA.hideAllSections();

    console.log("[BPI_AREA] applySubTab", { tabKey, group, type, conf });

    // ------------------------------------------------------------
    // BPI Density hourly
    // ------------------------------------------------------------
    if (isBpiDensityHourly(tabKey, conf)) {
      AREA.showSection("aoi-bpi-density-root");

      if (BPI.applyDensitySubTabFilters) {
        BPI.applyDensitySubTabFilters(tabKey);
      }

      document.dispatchEvent(new CustomEvent("aoi-bpi-density:subtab-density", {
        detail: {
          tabKey,
          config: conf,
          restoreOnly: true,
        },
      }));

      redrawBpiDensity();
      return;
    }

    // ------------------------------------------------------------
    // Same Point hourly
    // ------------------------------------------------------------
    if (isSamePointHourly(tabKey, conf)) {
      AREA.showSection("bpi-same-point-root");

      document.dispatchEvent(new CustomEvent("bpi-same-point:show", {
        detail: {
          system: "bpi_same_point",
          tabKey,
          config: conf,
        },
      }));

      return;
    }

    // ------------------------------------------------------------
    // CSV
    // ------------------------------------------------------------
    if (type === "csv") {
      AREA.showSection("density-csv-download-root");

      const targetSystem = conf.system_key || getSystemByGroup(group);

      document.dispatchEvent(new CustomEvent("density-csv-download:show", {
        detail: {
          system: targetSystem,
          tabKey,
          config: conf,
        },
      }));

      return;
    }

    // ------------------------------------------------------------
    // Density Avg
    // ------------------------------------------------------------
    if (type === "density_avg") {
      AREA.showSection("density-avg-download-root");
    
      const targetSystem = conf.system_key || getSystemByGroup(group);
    
      console.log("[BPI_AREA][density_avg dispatch]", {
        tabKey,
        group,
        type,
        conf,
        targetSystem,
      });
    
      document.dispatchEvent(new CustomEvent("density-avg-download:show", {
        detail: {
          system: targetSystem,
          tabKey,
          config: conf,
        },
      }));
    
      return;
    }
    

    // ------------------------------------------------------------
    // Common Table / Default Spec / Action History
    // ------------------------------------------------------------
    if (type === "table" || type === "bpi_same_point_table") {
      await showCommonTableTab(tabKey, conf, group);
      return;
    }

    // ------------------------------------------------------------
    // fallback
    // ------------------------------------------------------------
    AREA.showSection("aoi-bpi-density-root");
    redrawBpiDensity();
  };

  // ============================================================
  // Router
  // ============================================================
  AREA.Router = AREA.Router || {};

  AREA.Router.ensureInit = async function () {
    if (AREA.state.inited || AREA.state.loading) return;

    AREA.state.loading = true;

    try {
      console.log("[BPI_AREA] ensureInit");

      await loadInitialBpiPayload();

      bindBpiDensityDateButtons();
      
      AREA.state.inited = true;

      const subtabs = document.getElementById("aoi-bpi-density-subtabs");
      if (subtabs) {
        AREA.buildRightSubTabs(subtabs);
      }

      AREA.syncSectionVisibility();
    } catch (err) {
      console.error("[BPI_AREA] ensureInit failed:", err);
      throw err;
    } finally {
      AREA.state.loading = false;
    }
  };
})();