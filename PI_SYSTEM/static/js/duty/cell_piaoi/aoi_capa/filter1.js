// static/js/aoi_capa/filter1.js
(function () {
  const AOI = (window.AOI_CAPA = window.AOI_CAPA || {});
  AOI.Filter = AOI.Filter || {};

  const $ = (sel, root = document) => root.querySelector(sel);

  function selectIdOf(key) { return `aoi-capa-f-${key}`; }
  function hostIdOf(key) { return `aoi-capa-host-${key}`; }

  function getCurrentSubTab() {
    return AOI.state?.currentSubTab || "Day_Hourly";
  }

  function ensureDynHostsContainer() {
    const aside = $("#aoi-capa-right");
    if (!aside) return null;

    let dyn = $("#aoi-capa-dynhosts");
    if (!dyn) {
      dyn = document.createElement("div");
      dyn.id = "aoi-capa-dynhosts";
      aside.appendChild(dyn);
    }

    return dyn;
  }

  function getDisplayName(cfgKey) {
    const map = AOI.state?.paramDict?.filtetItemKeyDict || {};
    return map?.[cfgKey] || cfgKey;
  }

  function getOptionsOf(key) {
    const subTab = getCurrentSubTab();
    const subCfg = AOI.state?.paramDict?.SubTabsFilterDefaultDict?.[subTab];

    if (subCfg?.filter_item_coldict?.[key]?.values) {
      return Array.isArray(subCfg.filter_item_coldict[key].values)
        ? subCfg.filter_item_coldict[key].values.slice()
        : [];
    }

    const dict = AOI.state?.paramDict?.FilterDefaultDict || {};
    const arr = dict?.[key];

    if (Array.isArray(arr)) return arr.slice();
    if (arr != null) return [arr];

    return [];
  }

  function getFilterKeys() {
    const subTab = getCurrentSubTab();
    const subCfg = AOI.state?.paramDict?.SubTabsFilterDefaultDict?.[subTab];

    if (subCfg?.filter_item_coldict) {
      return Object.keys(subCfg.filter_item_coldict);
    }

    const cfgMap = AOI.state?.paramDict?.filtetItemKeyDict || {};
    return Object.keys(cfgMap);
  }

  function getDefaultSelected(key, opts) {
    const defMap = AOI.state?.paramDict?.FilterDefaultDict || {};
    const preset = defMap?.[key];

    if (!opts || !opts.length) return [];
    if (preset == null) return opts.slice();
    if (Array.isArray(preset) && preset.length === 0) return opts.slice();

    const list = Array.isArray(preset) ? preset : [preset];
    const inter = opts.filter(v => list.includes(v));

    return inter.length ? inter : opts.slice();
  }

  function triggerFilterChange(key) {
    const sel = document.getElementById(selectIdOf(key));
    sel?.dispatchEvent(new Event("change", { bubbles: true }));

    document.dispatchEvent(new CustomEvent("aoi-capa:filter-changed", {
      detail: {
        key,
        filters: AOI.readFiltersFromUI()
      }
    }));
  }

  AOI.Filter.ensureWidgets = function () {
    const subTab = getCurrentSubTab();

    if (subTab !== "Day_Hourly") return;

    const keys = getFilterKeys();
    if (!keys.length) return;

    const dynHosts = ensureDynHostsContainer();
    if (!dynHosts) return;

    AOI.mdd = AOI.mdd || {};
    dynHosts.innerHTML = "";

    keys.forEach((key) => {
      const title = getDisplayName(key);
      const opts = getOptionsOf(key);
      const host = document.createElement("div");

      host.className = "multi-dd-host";
      host.id = hostIdOf(key);
      dynHosts.appendChild(host);

      const selectId = selectIdOf(key);

      const oldWidget = AOI.mdd[key];
      const oldSelected = oldWidget && typeof oldWidget.getSelected === "function"
        ? oldWidget.getSelected()
        : null;

      AOI.mdd[key] = new AOI.MultiDD({
        hostId: host.id,
        selectId,
        options: opts,
        title,
        onChange: () => {
          triggerFilterChange(key);
        },
      });

      let selected;

      if (Array.isArray(oldSelected)) {
        // 重點：若使用者已經清空，保留空選，不自動全選
        selected = oldSelected.filter(v => opts.includes(v));
      } else {
        selected = getDefaultSelected(key, opts);
      }

      if (typeof AOI.mdd[key].setSelected === "function") {
        AOI.mdd[key].setSelected(selected);
      }
    });
  };

  AOI.readFiltersFromUI = function () {
    const out = {};
    const keys = getFilterKeys();

    keys.forEach((key) => {
      const widget = AOI.mdd?.[key];

      if (widget && typeof widget.getSelected === "function") {
        // 重點：一定要回傳 key，即使是 []
        const vals = widget.getSelected() || [];
        out[key] = vals.slice();
        return;
      }

      const sel = document.getElementById(selectIdOf(key));

      if (sel) {
        out[key] = Array.from(sel.options)
          .filter(o => o.selected)
          .map(o => o.value);
      } else {
        out[key] = [];
      }
    });

    return out;
  };

  AOI.hasEmptyFilterSelection = function () {
    const filters = AOI.readFiltersFromUI();
    const keys = getFilterKeys();

    return keys.some((key) => {
      return Array.isArray(filters[key]) && filters[key].length === 0;
    });
  };

  document.addEventListener("aoi-capa:data-ready", (ev) => {
    if (ev?.detail) AOI.state = ev.detail;
    AOI.Filter.ensureWidgets();
  });

  document.addEventListener("aoi-capa:subtab-changed", (ev) => {
    if (ev?.detail?.state) AOI.state = ev.detail.state;
    AOI.Filter.ensureWidgets();
  });

  AOI.selectIdOf = selectIdOf;
  AOI.hostIdOf = hostIdOf;
})();