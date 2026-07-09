// static/js/aoi_density/filter.js
// 右側篩選 + SamePoint offset 單選下拉
(function () {
  const AOI = (window.AOI_DENSITY = window.AOI_DENSITY || {});
  AOI.Filter = AOI.Filter || {};

  const $ = (sel, root = document) => root.querySelector(sel);

  function selectIdOf(key) { return `f-${key}`; }
  function hostIdOf(key) { return `host-${key}`; }

  function isSamePointTab(tabKey) {
    return typeof AOI.isSamePointTab === "function"
      ? AOI.isSamePointTab(tabKey)
      : ["UPI(Total)", "PISpot(Total)"].includes(String(tabKey || "").trim());
  }

  function ensureDynHostsContainer() {
    const aside = $("#aoi-density-right");
    if (!aside) return null;

    let dyn = $("#aoi-density-dynhosts");
    if (!dyn) {
      dyn = document.createElement("div");
      dyn.id = "aoi-density-dynhosts";

      const actions = $("#aoi-density-right .filter-actions");
      if (actions && actions.parentElement) {
        actions.parentElement.insertAdjacentElement("afterend", dyn);
      } else {
        aside.appendChild(dyn);
      }
    }

    return dyn;
  }

  function getDisplayName(cfgKey) {
    const map = AOI.state.paramDict?.filtetItemKeyDict || {};
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
    const dict = AOI.state.paramDict?.filterOptionDict || {};
    const arr = dict?.[key];
    return Array.isArray(arr) ? arr.slice() : [];
  }

  function cleanArr(v) {
    return Array.isArray(v)
      ? v.map(x => String(x).trim()).filter(Boolean)
      : [];
  }

  function readDatesFromUI() {
    const b = document.querySelector("#aoi-density-start")?.value;
    const e = document.querySelector("#aoi-density-end")?.value;
    return b && e ? [b, e] : undefined;
  }

  function readFiltersFromUISafe() {
    return typeof AOI.readFiltersFromUI === "function"
      ? AOI.readFiltersFromUI()
      : {};
  }

  function refreshDensityView() {
    const rows = typeof AOI.getFiltered === "function" ? AOI.getFiltered() : [];

    AOI.Charts?.render?.(rows, AOI.state.paramDict || {});
    AOI.Table?.render?.(rows, AOI.state.paramDict || {});
  }

  function getSamePointConfig() {
    return AOI.state.paramDict?.SamePoint || {};
  }

  function getOffsetValues(tabKey) {
    const defs = AOI.state.paramDict?.SubTabsFilterDefaultDict?.[tabKey] || {};
    const fromTab = defs?.same_point?.offset_values || defs?.offset;
    const fromGlobal = getSamePointConfig()?.offset_values;

    const values = cleanArr(fromTab || fromGlobal || [20, 30, 40, 50, 60, 70, 80, 90, 100])
      .map(Number)
      .filter(Number.isFinite);

    return values.length ? values : [20];
  }

  function getDefaultOffset(tabKey) {
    const defs = AOI.state.paramDict?.SubTabsFilterDefaultDict?.[tabKey] || {};
    const v =
      defs?.same_point?.default_offset ??
      getSamePointConfig()?.default_offset ??
      AOI.state.samePointOffset ??
      20;

    const n = Number(v);
    return Number.isFinite(n) ? n : 20;
  }

  function ensureSamePointOffsetHost() {
    const dynHosts = ensureDynHostsContainer();
    if (!dynHosts) return null;

    let host = $("#host-same-point-offset");
    if (!host) {
      host = document.createElement("div");
      host.id = "host-same-point-offset";
      host.className = "multi-dd-host same-point-offset-host";
      dynHosts.insertAdjacentElement("afterbegin", host);
    }

    return host;
  }

  function hideSamePointOffset() {
    const host = $("#host-same-point-offset");
    if (host) host.style.display = "none";
  }

  function renderSamePointOffset(tabKey) {
    const host = ensureSamePointOffsetHost();
    if (!host) return;

    if (!isSamePointTab(tabKey)) {
      hideSamePointOffset();
      return;
    }

    host.style.display = "";

    const values = getOffsetValues(tabKey);
    const current = Number(AOI.state.samePointOffset || getDefaultOffset(tabKey));
    const selected = values.includes(current) ? current : getDefaultOffset(tabKey);

    AOI.state.samePointOffset = selected;

    host.innerHTML = "";

    const wrap = document.createElement("div");
    wrap.className = "same-point-offset-box";
    wrap.style.display = "flex";
    wrap.style.flexDirection = "column";
    wrap.style.gap = "6px";
    wrap.style.marginBottom = "10px";

    const label = document.createElement("label");
    label.textContent = "Same Point Offset";
    label.style.fontWeight = "700";
    label.style.fontSize = "12px";

    const select = document.createElement("select");
    select.id = "f-same-point-offset";
    select.className = "form-select form-select-sm";
    select.style.width = "100%";

    values.forEach(v => {
      const opt = document.createElement("option");
      opt.value = String(v);
      opt.textContent = String(v);
      opt.selected = Number(v) === Number(selected);
      select.appendChild(opt);
    });

    select.addEventListener("change", async () => {
      const offset = Number(select.value || 20);
      AOI.state.samePointOffset = offset;

      try {
        await AOI.fetchSamePointData?.({
          tabKey,
          dates: readDatesFromUI(),
          filters: readFiltersFromUISafe(),
          offset
        });
      } catch (e) {
        console.error("[same-point] offset fetch failed:", e);
      }

      refreshDensityView();
    });

    wrap.appendChild(label);
    wrap.appendChild(select);
    host.appendChild(wrap);
  }

  AOI.Filter.ensureWidgets = function () {
    const cfgMap = AOI.state.paramDict?.filtetItemKeyDict || {};
    const keys = Object.keys(cfgMap);
    if (!keys.length) return;

    const dynHosts = ensureDynHostsContainer();
    if (!dynHosts) return;

    AOI.mdd = AOI.mdd || {};

    keys.forEach((key) => {
      const title = getDisplayName(key);
      const opts = getOptionsOf(key);
      const host = ensureOneHost(dynHosts, key);
      const selectId = selectIdOf(key);

      if (!AOI.mdd[key]) {
        AOI.mdd[key] = new AOI.MultiDD({
          hostId: host.id,
          selectId,
          options: opts,
          title,
          onChange: () => {
            AOI.refreshCascadeFiltersFromUI?.(key);
          }
        });

        if (opts?.length) {
          AOI.mdd[key].setSelected([]);
        }

        return;
      }

      const mdd = AOI.mdd[key];
      const prevAllSelected = (mdd.selected && mdd.options)
        ? (mdd.selected.size === mdd.options.length)
        : false;

        mdd.title = title;
        mdd.updateOptions(opts);
        
        if (prevAllSelected && opts?.length) {
          mdd.setSelected(opts);
        }
    });

    renderSamePointOffset(AOI.state.activeSubTab || window.density_sub_activeTabKey || "");
  };

  AOI.Filter.syncSamePointOffset = function (tabKey) {
    renderSamePointOffset(tabKey);
  };

  document.addEventListener("aoi-density:data-ready", () => {
    AOI.Filter.ensureWidgets();

    const subTabsMap = AOI.state.paramDict?.SubTabsFilterDefaultDict || {};
    const keys = Object.keys(subTabsMap);
    if (!keys.length) return;

    const currentKey = AOI.state.activeSubTab || window.density_sub_activeTabKey || "";

    if (currentKey && subTabsMap[currentKey]) {
      AOI.applyDensitySubTabFilters?.(currentKey);
      renderSamePointOffset(currentKey);
      return;
    }

    const firstKey = keys[0];
    if (firstKey) {
      AOI.state.activeSubTab = firstKey;
      window.density_sub_activeTabKey = firstKey;
      AOI.applySubTab(firstKey);
      renderSamePointOffset(firstKey);
    }
  });

  document.addEventListener("aoi-density:subtab-density", (ev) => {
    const tabKey = ev?.detail?.tabKey || AOI.state.activeSubTab || window.density_sub_activeTabKey || "";
    renderSamePointOffset(tabKey);
  });

  AOI.selectIdOf = selectIdOf;
  AOI.hostIdOf = hostIdOf;
})();