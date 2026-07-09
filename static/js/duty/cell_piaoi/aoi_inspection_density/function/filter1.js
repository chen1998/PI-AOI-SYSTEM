// static/js/aoi_inspection_density/function/filter.js
(function () {
  const AOI = (window.AOI_INSPECTION = window.AOI_INSPECTION || {});
  AOI.Filter = AOI.Filter || {};

  const $ = (sel, root = document) => root.querySelector(sel);

  function selectIdOf(key) { return `insp-f-${key}`; }
  function hostIdOf(key) { return `insp-host-${key}`; }

  function ensureDynHostsContainer() {
    const aside = $("#aoi-inspection-density-right");
    if (!aside) return null;

    let dyn = $("#aoi-inspection-density-dynhosts");
    if (!dyn) {
      dyn = document.createElement("div");
      dyn.id = "aoi-inspection-density-dynhosts";

      const actions = $("#aoi-inspection-density-right .filter-actions");
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

  function getDefaultSelected(key, opts) {
    const defMap = AOI.state.paramDict?.FilterDefaultDict || {};
    const preset = defMap[key];

    if (!opts || !opts.length) return [];
    if (preset == null) return opts.slice();
    if (Array.isArray(preset) && preset.length === 0) return opts.slice();

    const list = Array.isArray(preset) ? preset : [preset];
    const inter = opts.filter((v) => list.includes(v));
    return inter.length ? inter : opts.slice();
  }

  AOI.Filter.ensureWidgets = function () {
    const cfgMap = AOI.state.paramDict?.filtetItemKeyDict || {};
    const keys = Object.keys(cfgMap);
    if (!keys.length) return;
  
    const dynHosts = ensureDynHostsContainer();
    if (!dynHosts) return;
  
    AOI.mdd = AOI.mdd || {};
    let didDefaultAny = false;
  
    keys.forEach((key) => {
      const title = getDisplayName(key);
      const opts = getOptionsOf(key);
      const host = ensureOneHost(dynHosts, key);
      const selectId = selectIdOf(key);
      const defSel = getDefaultSelected(key, opts);
  
      if (AOI.mdd[key]) {
        const mdd = AOI.mdd[key];
        const cur = mdd.getSelected ? mdd.getSelected() : [];
        const wasAllSelected =
          Array.isArray(cur) &&
          Array.isArray(mdd.options) &&
          cur.length === mdd.options.length;
  
        mdd.title = title;
        mdd.updateOptions(opts);
  
        // 原本是全選，資料刷新後才維持全選
        if (wasAllSelected && opts.length) {
          mdd.setSelected(opts);
          document.getElementById(selectId)?.dispatchEvent(new Event("change", { bubbles: true }));
        }
  
        // 原本是空選，保持空選，不自動補回預設
        return;
      }
  
      AOI.mdd[key] = new AOI.MultiDD({
        hostId: host.id,
        selectId,
        options: opts,
        title,
        onChange: () => {}
      });
  
      if (defSel?.length) {
        AOI.mdd[key].setSelected(defSel);
        document.getElementById(selectId)?.dispatchEvent(new Event("change", { bubbles: true }));
        didDefaultAny = true;
      }
    });
  
    if (didDefaultAny) {
      const dynFirstSelect = dynHosts.querySelector('select[id^="insp-f-"]');
      dynFirstSelect?.dispatchEvent(new Event("change", { bubbles: true }));
    }
  };
  

  function parsePiHourToDate(s) {
    if (!s) return null;

    if (/^\d{2}-\d{2}-\d{2}\s+\d{2}$/.test(s)) {
      const [datePart, hh] = s.split(/\s+/);
      const [yy, mm, dd] = datePart.split("-").map(Number);
      return new Date(2000 + yy, mm - 1, dd, Number(hh), 0, 0);
    }

    const d = new Date(String(s).replace(" ", "T"));
    return isNaN(d.getTime()) ? null : d;
  }

  AOI.readFiltersFromUI = function () {
    const out = {};
    const cfgMap = AOI.state.paramDict?.filtetItemKeyDict || {};
    const keys = Object.keys(cfgMap);
  
    keys.forEach((key) => {
      const widget = AOI.mdd?.[key];
  
      if (widget && typeof widget.getSelected === "function") {
        out[key] = widget.getSelected().map(String);
        return;
      }
  
      const sel = document.getElementById(selectIdOf(key));
      if (sel && sel.tagName === "SELECT" && sel.multiple) {
        out[key] = Array.from(sel.selectedOptions)
          .map((o) => String(o.value))
          .filter((v) => v !== "" && v != null);
        return;
      }
  
      out[key] = [];
    });
  
    return out;
  };
  

  function parseSizeStats(stat) {
    const out = { S: 0, M: 0, L: 0, O: 0, T: 0 };
    if (!stat) return out;

    if (typeof stat === "string") {
      const rx = /\b([SMLOT])\s*:\s*(\d+)/g;
      let m;
      while ((m = rx.exec(stat)) !== null) {
        const k = m[1].toUpperCase();
        const v = Number(m[2] || 0);
        if (k in out && Number.isFinite(v)) out[k] = v;
      }
      if (!/\bT\s*:/.test(stat)) {
        out.T = out.S + out.M + out.L + out.O;
      }
      return out;
    }

    if (typeof stat === "object") {
      out.S = Number(stat.S || 0);
      out.M = Number(stat.M || 0);
      out.L = Number(stat.L || 0);
      out.O = Number(stat.O || 0);
      out.T = Number(stat.T != null ? stat.T : (out.S + out.M + out.L + out.O));
      return out;
    }

    return out;
  }

  function getLoadedPiHourRange() {
    const rr = AOI.state.paramDict?.ResolvedQueryRange || {};
    const piStart = rr.pi_start || "";
    const piEnd = rr.pi_end || "";
  
    const begin = parsePiHourToDate(piStart);
    const end = parsePiHourToDate(piEnd);
  
    return { begin, end };
  }

  AOI.getFiltered = function (opts) {
    const filters = AOI.readFiltersFromUI();
    const rows = AOI.state.rows || [];
    if (!rows.length) return [];
  
    const { begin, end } = getLoadedPiHourRange();
  
    const outFiltered = rows.filter((r) => {
      if (begin && end) {
        const d = parsePiHourToDate(r.pi_hour || r.tick_str);
        if (!d || d < begin || d > end) return false;
      }
  
      for (const [k, valsRaw] of Object.entries(filters)) {
        const vals = Array.isArray(valsRaw) ? valsRaw.map(String) : [String(valsRaw)];
      
        if (!vals.length) return false;
        if (k === "defect_size") continue;
      
        const v = (r[k] ?? "").toString();
        if (!vals.includes(v)) return false;
      }
  
      return true;
    });
  
    const sizeFilterArr = filters.defect_size;

    if (Array.isArray(sizeFilterArr) && sizeFilterArr.length === 0) {
      return [];
    }

    const selectedSizes =
      Array.isArray(sizeFilterArr) && sizeFilterArr.length
        ? new Set(sizeFilterArr)
        : null;
  
    if (!selectedSizes || !selectedSizes.size) {
      return outFiltered.slice();
    }
  
    return outFiltered.map((r) => {
      const nG = Number(
        r.n_glasses ??
        r.maingroup_glass_count ??
        r.total_glass_count ??
        r.glass_num ??
        0
      );
  
      const baseS = Number(r.s_count ?? r.small_defect_count ?? 0);
      const baseM = Number(r.m_count ?? r.middle_defect_count ?? 0);
      const baseL = Number(r.l_count ?? r.large_defect_count ?? 0);
      const baseO = Number(r.o_count ?? r.over_defect_count ?? 0);
  
      const s = selectedSizes.has("S") ? baseS : 0;
      const m = selectedSizes.has("M") ? baseM : 0;
      const l = selectedSizes.has("L") ? baseL : 0;
      const o = selectedSizes.has("O") ? baseO : 0;
  
      const newDef = s + m + l + o;
      const newDensity = nG > 0 ? (newDef / nG) : 0;
  
      let newCodeGlass = Number(
        r.defect_code_glass_count ??
        r.code_glass_num ??
        0
      );
  
      const gdc = r.glass_defect_count;
      if (gdc && typeof gdc === "object" && !Array.isArray(gdc) && Object.keys(gdc).length) {
        let cnt = 0;
        Object.values(gdc).forEach((stat) => {
          const st = parseSizeStats(stat);
          const hit =
            (selectedSizes.has("S") && st.S > 0) ||
            (selectedSizes.has("M") && st.M > 0) ||
            (selectedSizes.has("L") && st.L > 0) ||
            (selectedSizes.has("O") && st.O > 0);
          if (hit) cnt += 1;
        });
        newCodeGlass = cnt;
      }
  
      return {
        ...r,
        small_defect_count: s,
        middle_defect_count: m,
        large_defect_count: l,
        over_defect_count: o,
  
        s_count: s,
        m_count: m,
        l_count: l,
        o_count: o,
  
        defect_code_count: newDef,
        n_rows: newDef,
        defect_num: newDef,
  
        density: newDensity,
  
        defect_code_glass_count: newCodeGlass,
        code_glass_num: newCodeGlass
      };
    });
  };
  document.addEventListener("aoi_inspection:data-ready", () => {
    AOI.Filter.ensureWidgets();
  });

  AOI.selectIdOf = selectIdOf;
  AOI.hostIdOf = hostIdOf;
})();