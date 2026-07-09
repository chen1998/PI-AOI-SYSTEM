// static/js/bpi_area/bpi_density/filter.js
// BPI Density 右側篩選
// 新版 ParamDict：
//   ParamDict.bpiDensity.filtetItemKeyDict
//   ParamDict.bpiDensity.filterOptionDict
//
// 舊版相容：
//   ParamDict.filtetItemKeyDict
//   ParamDict.filterOptionDict

(function () {
  const AOI = (window.AOI_BPI_DENSITY = window.AOI_BPI_DENSITY || {});
  AOI.Filter = AOI.Filter || {};
  AOI.mdd = AOI.mdd || {};

  const $ = (sel, root = document) => root.querySelector(sel);

  function getParamDict() {
    return AOI.state?.paramDict || {};
  }

  function getBpiDensityConfig() {
    const pd = getParamDict();
    return pd.bpiDensity || pd || {};
  }

  function getFilterItemDict() {
    const cfg = getBpiDensityConfig();
    return cfg.filtetItemKeyDict || cfg.filterItemKeyDict || {};
  }

  function getFilterOptionDict() {
    const cfg = getBpiDensityConfig();
    return cfg.filterOptionDict || {};
  }

  function selectIdOf(key) {
    return `bpi-f-${key}`;
  }

  function hostIdOf(key) {
    return `bpi-host-${key}`;
  }

  function cleanArr(v) {
    if (!Array.isArray(v)) return [];
    return v.map(x => String(x).trim()).filter(Boolean);
  }

  function ensureDynHostsContainer() {
    const aside = $("#aoi-bpi-density-right");
    if (!aside) return null;

    let dyn = $("#aoi-bpi-density-dynhosts");

    if (!dyn) {
      dyn = document.createElement("div");
      dyn.id = "aoi-bpi-density-dynhosts";

      const actions = $("#aoi-bpi-density-right .aoi-bpi-density-filter-actions");
      if (actions && actions.parentElement) {
        actions.parentElement.insertAdjacentElement("afterend", dyn);
      } else {
        aside.appendChild(dyn);
      }
    }

    return dyn;
  }

  function getDisplayName(cfgKey) {
    const map = getFilterItemDict();
    return map?.[cfgKey] || cfgKey;
  }

  function ensureOneHost(dynHostsEl, key) {
    let host = $("#" + hostIdOf(key));

    if (!host) {
      host = document.createElement("div");
      host.className = "multi-dd-host";
      host.id = hostIdOf(key);
      dynHostsEl.appendChild(host);
    }

    return host;
  }

  function getOptionsOf(key) {
    const dict = getFilterOptionDict();
    const arr = dict?.[key];

    if (Array.isArray(arr)) return arr.slice();

    return [];
  }

  function dispatchFilterChange(key) {
    const el = document.getElementById(selectIdOf(key));
    el?.dispatchEvent(new Event("change", { bubbles: true }));
  
    window.BPI_AREA?.redrawBpiDensity?.();
    window.AOI_BPI_DENSITY_Router?.redraw?.();
  }

  AOI.Filter.ensureWidgets = function () {
    const cfgMap = getFilterItemDict();
    const keys = Object.keys(cfgMap || {});

    if (!keys.length) return;

    const dynHosts = ensureDynHostsContainer();
    if (!dynHosts) return;

    AOI.mdd = AOI.mdd || {};

    keys.forEach((key) => {
      const title = getDisplayName(key);
      const opts = cleanArr(getOptionsOf(key));
      const host = ensureOneHost(dynHosts, key);
      const selectId = selectIdOf(key);

      if (!AOI.MultiDD) {
        console.error("[BPI Filter] AOI.MultiDD 未載入");
        return;
      }

      // 第一次建立
      if (!AOI.mdd[key]) {
        AOI.mdd[key] = new AOI.MultiDD({
          hostId: host.id,
          selectId,
          options: opts,
          title,
          onChange: () => {
            dispatchFilterChange(key);
          }
        });

        // 新建時預設全選
        if (opts.length) {
          AOI.mdd[key].setSelected(opts);
          dispatchFilterChange(key);
        }

        return;
      }

      // 已存在：更新 options
      const mdd = AOI.mdd[key];

      const prevOptions = cleanArr(mdd.options || []);
      const prevSelected = cleanArr(mdd.getSelected ? mdd.getSelected() : []);
      const prevAllSelected =
        prevOptions.length > 0 &&
        prevSelected.length === prevOptions.length &&
        prevSelected.every(v => prevOptions.includes(v));

      mdd.title = title;
      mdd.updateOptions(opts);

      const curSelected = cleanArr(mdd.getSelected ? mdd.getSelected() : []);

      // 若更新前是全選，更新後仍維持全選
      if (prevAllSelected && opts.length) {
        mdd.setSelected(opts);
        dispatchFilterChange(selectId);
        return;
      }

      // 如果更新後選項交集為空，預設全選，避免整頁被濾空
      /*if ((!curSelected || curSelected.length === 0) && opts.length) {
        mdd.setSelected(opts);
        dispatchFilterChange(selectId);
        return;
      }*/

      // 若不是全選也不是空，維持交集
      const keep = curSelected.filter(v => opts.includes(v));

      if (keep.length !== curSelected.length) {
        // 重點：交集為空時保留空選，不要自動全選
        mdd.setSelected(keep);
        dispatchFilterChange(key);
      }
    });
  };

  document.addEventListener("aoi-bpi-density:data-ready", () => {
    AOI.Filter.ensureWidgets();

    // 這裡只負責建立 filter，不再主動 apply subtab。
    // 右上分頁切換由 BPI_AREA 統一控制。
  });

  AOI.selectIdOf = selectIdOf;
  AOI.hostIdOf = hostIdOf;

  AOI.getBpiDensityFilterItemDict = getFilterItemDict;
  AOI.getBpiDensityFilterOptionDict = getFilterOptionDict;
})();