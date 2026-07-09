// static/js/bpi_area/bpi_same_point/filter.js
(function () {
  const MOD = (window.BPI_SAME_POINT = window.BPI_SAME_POINT || {});
  const state = MOD.state;

  const Filter = (MOD.Filter = MOD.Filter || {});

  let suppressChange = false;
  let debounceTimer = null;

  // 勾選 filter 後立即查資料。
  // 注意：service.js 的 MOD.loadData 必須支援 refreshFilter:false，
  // 否則 filter 會被重建，選單仍會關閉。
  const AUTO_RELOAD_ON_FILTER_CHANGE = true;
  const FILTER_RELOAD_DEBOUNCE_MS = 250;

  function $(id) {
    return document.getElementById(id);
  }

  function cleanStr(v) {
    return v == null ? "" : String(v).trim();
  }

  function cleanArr(v) {
    if (!Array.isArray(v)) return [];
    return v.map(x => String(x).trim()).filter(Boolean);
  }

  function arrSameSet(a, b) {
    const aa = cleanArr(a).sort();
    const bb = cleanArr(b).sort();

    if (aa.length !== bb.length) return false;

    for (let i = 0; i < aa.length; i += 1) {
      if (aa[i] !== bb[i]) return false;
    }

    return true;
  }

  function getMultiDDCtor() {
    return (
      window.AOI_BPI_DENSITY?.MultiDD ||
      window.AOI_DENSITY?.MultiDD ||
      window.MultiDD ||
      null
    );
  }

  function selectIdOf(key) {
    return `bpi-sp-f-${key}`;
  }

  function hostIdOf(key) {
    return `bpi-sp-host-${key}`;
  }

  function getFilterConfig(config) {
    return config?.filter_item_coldict || {};
  }

  function isHiddenConf(conf) {
    return conf?.hidden === true || conf?.display === false || conf?.visible === false;
  }

  function isExcludedKey(key) {
    return key === "date" || key === "offset_um";
  }

  function findConfigForKey(config, key) {
    const colDict = getFilterConfig(config);

    for (const conf of Object.values(colDict)) {
      if (conf?.key === key) return conf;
    }

    return {};
  }

  function getOrder(config) {
    const order = Array.isArray(config?.cascade_order)
      ? config.cascade_order.slice()
      : [];

    const colDict = getFilterConfig(config);

    Object.values(colDict).forEach(conf => {
      const key = conf?.key;
      if (!key || isExcludedKey(key) || isHiddenConf(conf)) return;
      if (!order.includes(key)) order.push(key);
    });

    return order.filter(key => {
      if (isExcludedKey(key)) return false;

      const conf = findConfigForKey(config, key);
      if (isHiddenConf(conf)) return false;

      return true;
    });
  }

  function labelByKey(config) {
    const out = {};
    const colDict = getFilterConfig(config);

    Object.entries(colDict).forEach(([label, conf]) => {
      const key = conf?.key;
      if (!key || isExcludedKey(key) || isHiddenConf(conf)) return;
      out[key] = label;
    });

    return out;
  }

  function getOptionsForKey(optionDict, conf, key) {
    let options = cleanArr(optionDict?.[key]);

    if (!options.length && Array.isArray(conf?.values)) {
      options = cleanArr(conf.values);
    }

    // defect_size 新版固定用點位原子尺寸 S/M/L/O。
    // 後端用 matched_bpi_* OR matched_api_* 判斷。
    if (key === "defect_size") {
      const preferred = cleanArr(conf?.values);
      if (preferred.length) return preferred;

      if (options.length) return options;

      return ["S", "M", "L", "O"];
    }

    return options;
  }

  function scheduleReload() {
    if (!AUTO_RELOAD_ON_FILTER_CHANGE) return;

    if (debounceTimer) {
      clearTimeout(debounceTimer);
    }

    debounceTimer = setTimeout(() => {
      MOD.loadData?.({
        refreshFilter: false,
        source: "filter",
      });
    }, FILTER_RELOAD_DEBOUNCE_MS);
  }

  function getSelectedForKey(key) {
    const wrap = state.mdd?.[key];
    return cleanArr(wrap?.mdd?.getSelected?.() || []);
  }

  function getOptionsForRenderedKey(key) {
    const wrap = state.mdd?.[key];
    return cleanArr(wrap?.options || []);
  }

  Filter.getSelectedFilters = function () {
    const out = {};
  
    Object.entries(state.mdd || {}).forEach(([key, wrap]) => {
      const selected = cleanArr(wrap?.mdd?.getSelected?.() || []);
      const options = cleanArr(wrap?.options || []);
  
      // 清空選單：代表該欄位無選取，查詢結果應為 0 筆。
      if (options.length > 0 && selected.length === 0) {
        out[key] = ["__NO_SELECTION__"];
        return;
      }
  
      if (!selected.length) return;
  
      const isAllSelected =
        options.length > 0 &&
        selected.length === options.length &&
        selected.every(v => options.includes(v));
  
      // 全選代表不下 filter。
      if (isAllSelected) return;
  
      out[key] = selected;
    });
  
    return out;
  };

  Filter.clear = function () {
    Object.values(state.mdd || {}).forEach(wrap => {
      const options = cleanArr(wrap?.options || []);

      suppressChange = true;
      try {
        wrap?.mdd?.setSelected?.(options);
      } finally {
        suppressChange = false;
      }
    });
  };

  /**
   * 不重建 MultiDD，只同步目前 options cache。
   *
   * 這是為了 filter onChange 即時查詢時，不要把下拉選單重建掉。
   * 因為你的需求是：
   *   - filter options 只受日期/subPage 影響
   *   - 勾 filter 只更新 ChartRows/TableRows
   *
   * 所以 filter onChange 後 response 回來時，不需要重 render filter。
   */
  Filter.syncOptionsOnly = function (optionDict, config) {
    if (!state.mdd) return;

    const order = getOrder(config || state.config || {});

    order.forEach(key => {
      const wrap = state.mdd?.[key];
      if (!wrap) return;

      const conf = findConfigForKey(config || state.config || {}, key);
      const nextOptions = getOptionsForKey(optionDict || {}, conf, key);

      if (!nextOptions.length) return;

      // options 沒變就不動。
      if (arrSameSet(wrap.options, nextOptions)) return;

      // 如果日期沒有變，理論上 options 不應該變。
      // 這裡只更新 cache，不強制重建元件，避免下拉關閉。
      wrap.options = nextOptions;
    });
  };

  Filter.render = function (optionDict, config) {
    const host = $("bpi-same-point-dynhosts");
    if (!host) return;

    const MultiDD = getMultiDDCtor();
    if (!MultiDD) {
      host.innerHTML = "<div class='muted'>MultiDD 未載入</div>";
      return;
    }

    const prevFilters = Filter.getSelectedFilters();

    host.innerHTML = "";
    state.mdd = {};

    const order = getOrder(config);
    const labels = labelByKey(config);

    order.forEach(key => {
      const conf = findConfigForKey(config, key);

      if (isHiddenConf(conf)) return;

      const options = getOptionsForKey(optionDict, conf, key);

      if (!options.length) return;

      const div = document.createElement("div");
      div.className = "multi-dd-host";
      div.id = hostIdOf(key);
      host.appendChild(div);

      const mdd = new MultiDD({
        hostId: div.id,
        selectId: selectIdOf(key),
        options,
        title: labels[key] || conf?.label || key,
        onChange: () => {
          if (suppressChange) return;
          scheduleReload();
        },
      });

      const prev = cleanArr(prevFilters[key]);
      const selected = prev.length
        ? prev.filter(v => options.includes(v))
        : options.slice();

      suppressChange = true;
      try {
        mdd.setSelected?.(selected.length ? selected : options.slice());
      } finally {
        suppressChange = false;
      }

      state.mdd[key] = {
        mdd,
        options,
        config: conf,
      };
    });
  };

  Filter.AUTO_RELOAD_ON_FILTER_CHANGE = AUTO_RELOAD_ON_FILTER_CHANGE;
})();
