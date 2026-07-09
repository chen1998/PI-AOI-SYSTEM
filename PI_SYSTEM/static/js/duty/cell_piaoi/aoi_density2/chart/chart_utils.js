// static/js/aoi_density/chart/chart_utils.js
// AOI Density Chart - shared utilities / accessors / spec / alert / slider
(function () {
  'use strict';

  const MOD = (window.AOI_DENSITY = window.AOI_DENSITY || {});
  const C = (MOD.ChartCore = MOD.ChartCore || {});
  const Shared = MOD.Shared || null;
  const U = Shared?.U || null;

  function s(v) {
    return v == null ? '' : String(v);
  }

  function n(v) {
    const x = Number(v);
    return Number.isFinite(x) ? x : 0;
  }

  function toNum(v) {
    const x = Number(v);
    return Number.isFinite(x) ? x : null;
  }

  C.s = s;
  C.n = n;
  C.toNum = toNum;

  C.A = {
    line: r => U?.line ? U.line(r) : s(r?.line_id),
    aoi: r => U?.aoi ? U.aoi(r) : s(r?.aoi),
    model: r => U?.model ? U.model(r) : s(r?.model),
    side: r => U?.side ? U.side(r) : s(r?.glass_type),
    tick: r => U?.tick ? U.tick(r) : s(r?.pi_hour),
    tickRaw: r => U?.tickRaw ? U.tickRaw(r) : s(r?.pi_hour_raw || r?.pi_hour),
    recipe: r => U?.recipe ? U.recipe(r) : s(r?.recipe_id),
    code: r => U?.code ? U.code(r) : s(r?.adc_def_code),

    tabG: r => U?.tabGlass ? n(U.tabGlass(r)) : n(r?.tab_total_glass_cnt ?? r?.total_glass_cnt),
    tabD: r => U?.tabDefect ? n(U.tabDefect(r)) : n(r?.tab_total_defect_cnt ?? r?.total_defect_cnt),
    tabDensity: r => U?.tabDensity ? n(U.tabDensity(r)) : n(r?.tab_total_density ?? r?.total_density),

    d: r => U?.dTotal ? n(U.dTotal(r)) : n(r?.defect_cnt),
    cg: r => U?.gCode ? n(U.gCode(r)) : n(r?.def_glass_cnt),
    dens: r => U?.dens ? n(U.dens(r)) : n(r?.density),

    sCnt: r => n(r?.small_defect_count),
    mCnt: r => n(r?.middle_defect_count),
    lCnt: r => n(r?.large_defect_count),
    oCnt: r => n(r?.over_defect_count)
  };

  C.parseTickToDate = function parseTickToDate(tick) {
    if (Shared?.parsePiHourToDate) return Shared.parsePiHourToDate(tick);
    const raw = s(tick).trim();
    if (!raw) return null;
    const d = new Date(raw.replace(' ', 'T'));
    return Number.isNaN(d.getTime()) ? null : d;
  };

  C.tickToShort = function tickToShort(tick) {
    if (Shared?.fmtPiHourToShort) return Shared.fmtPiHourToShort(tick);
    return s(tick);
  };

  C.tickSort = function tickSort(a, b) {
    const da = C.parseTickToDate(a);
    const db = C.parseTickToDate(b);
    return (da?.getTime() ?? 0) - (db?.getTime() ?? 0);
  };

  C.rawActiveTabKey = function rawActiveTabKey() {
    return MOD?.state?.activeSubTab || window.density_sub_activeTabKey || '';
  };

  C.normalizeDensityTabKey = function normalizeDensityTabKey(tabKey) {
    if (MOD?.normalizeDensityTabKey) return MOD.normalizeDensityTabKey(tabKey);

    const x = s(tabKey).trim();
    if (!x) return '';

    const defs = MOD?.state?.paramDict?.SubTabsFilterDefaultDict?.[x] || {};
    const backend = s(defs.backend_tab_name).trim();
    if (backend) return backend;

    if (x === 'UPI(Total)') return 'UPI_Total';
    if (x === 'PISpot(Total)') return 'PISpot_Total';
    return x;
  };

  C.activeTabKey = function activeTabKey() {
    return C.normalizeDensityTabKey(C.rawActiveTabKey());
  };

  C.activeTabDefs = function activeTabDefs() {
    const raw = C.rawActiveTabKey();
    const backend = C.activeTabKey();
    const map = MOD?.state?.paramDict?.SubTabsFilterDefaultDict || {};
    return map[raw] || map[backend] || {};
  };

  C.isSamePointTabActive = function isSamePointTabActive() {
    return MOD?.isSamePointTab?.(MOD?.state?.activeSubTab || window.density_sub_activeTabKey) === true;
  };

  C.isTotalDensityTab = function isTotalDensityTab() {
    const x = s(C.rawActiveTabKey()).trim();
    return x === 'UPI(Total)' || x === 'PISpot(Total)';
  };

  C.buildDefaultLegendSelectedState = function buildDefaultLegendSelectedState() {
    const isTotal = C.isTotalDensityTab();
  
    return {
      [C.SERIES_NAMES.glassTotal]: true,
      [C.SERIES_NAMES.defectGlass]: false,
      [C.SERIES_NAMES.density]: !isTotal,
      [C.SERIES_NAMES.totalDensity]: isTotal,
  
      // 同點獨立 legend，預設關閉
      [C.SERIES_NAMES.samePoint]: false,
  
      [C.SERIES_NAMES.defaultSpec]: true,
      [C.SERIES_NAMES.fixedSpec]: false
    };
  };

  C.makeSamePointKeyByValues = function makeSamePointKeyByValues(tick, line, aoi, model, side, recipe) {
    let pi = s(tick).trim();

    if (Shared?.fmtPiHourToBackend) {
      pi = Shared.fmtPiHourToBackend(pi);
    } else if (/^\d{2}-\d{2}-\d{2}\s+\d{2}$/.test(pi)) {
      const [d, h] = pi.split(/\s+/);
      const [yy, mm, dd] = d.split('-');
      pi = `20${yy}-${mm}-${dd} ${h}:00:00`;
    } else if (/^\d{4}-\d{2}-\d{2}\s+\d{2}$/.test(pi)) {
      pi = `${pi}:00:00`;
    } else if (/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}$/.test(pi)) {
      pi = `${pi}:00`;
    }

    return [pi, s(line), s(aoi), s(model), s(side), s(recipe)].join('||');
  };

  C.hasSamePointForChartCell = function hasSamePointForChartCell(tick, row, aoi) {
    if (!C.isSamePointTabActive()) return false;

    const idx = MOD?.state?.SamePointIndex || {};
    if (!idx || typeof idx !== 'object') return false;

    const recipeList = s(row?.recipe_list || row?.recipe_id)
      .split(',')
      .map(x => x.trim())
      .filter(Boolean);

    const recipes = recipeList.length ? recipeList : [s(row?.recipe_id)];

    return recipes.some(recipe => {
      const key = C.makeSamePointKeyByValues(
        tick,
        row?.line_id,
        aoi,
        row?.model,
        row?.glass_type,
        recipe
      );
      const sp = idx[key];
      return sp && n(sp.common_cnt) > 0;
    });
  };

  C.getSelectedSizes = function getSelectedSizes() {
    try {
      const ui = MOD?.readFiltersFromUI?.();
      const ds = ui?.defect_size;
      if (Array.isArray(ds) && ds.length) return ds;
    } catch (_) {}
    return ['S', 'M', 'L', 'O'];
  };

  C.getSelectedCodes = function getSelectedCodes(rows) {
    try {
      const ui = MOD?.readFiltersFromUI?.();
      const arr = ui?.adc_def_code;
      if (Array.isArray(arr) && arr.length) {
        return arr.map(x => s(x).trim()).filter(Boolean);
      }
    } catch (_) {}

    const codes = new Set();
    (rows || []).forEach(r => {
      const c = C.A.code(r);
      if (c) codes.add(c);
    });

    const fromRows = Array.from(codes).sort();
    if (fromRows.length) return fromRows;

    const defArr = C.activeTabDefs()?.adc_def_code;
    if (Array.isArray(defArr) && defArr.length) {
      return defArr.map(x => s(x).trim()).filter(Boolean);
    }

    return ['Polymer', 'SSIU_Polymer', 'PI_Spot_NP', 'PIS With Particle', 'SPS', 'NPI_TFT', 'others'];
  };

  C.getChartDateRange = function getChartDateRange() {
    try {
      const b = document.querySelector('#aoi-density-start')?.value;
      const e = document.querySelector('#aoi-density-end')?.value;
      if (!b || !e) return null;
      return {
        start: new Date(`${b}T00:00:00`).getTime(),
        end: new Date(`${e}T23:59:59`).getTime()
      };
    } catch (_) {
      return null;
    }
  };

  C.passesChartDateFilter = function passesChartDateFilter(piHour, dateRange) {
    if (!dateRange) return true;
    const d = C.parseTickToDate(piHour);
    if (!d) return false;
    const t = d.getTime();
    return t >= dateRange.start && t <= dateRange.end;
  };

  C.getChartBaseFilters = function getChartBaseFilters() {
    let filters = {};
    try {
      filters = MOD?.readFiltersFromUI?.() || {};
    } catch (_) {}

    return {
      line_id: Array.isArray(filters.line_id) ? filters.line_id.map(String) : [],
      aoi: Array.isArray(filters.aoi) ? filters.aoi.map(String) : [],
      model: Array.isArray(filters.model) ? filters.model.map(String) : [],
      glass_type: Array.isArray(filters.glass_type) ? filters.glass_type.map(String) : []
    };
  };

  C.passesChartBaseFilters = function passesChartBaseFilters(row, baseFilters) {
    const checks = ['line_id', 'aoi', 'model', 'glass_type'];
    for (const k of checks) {
      const arr = baseFilters?.[k];
      if (Array.isArray(arr) && arr.length && !arr.includes(s(row?.[k]))) {
        return false;
      }
    }
    return true;
  };

  C.canonicalSizeKeyFromList = function canonicalSizeKeyFromList(list) {
    if (!Array.isArray(list) || !list.length) return '';
    const chars = list.map(x => s(x).trim().toUpperCase()[0]).filter(ch => 'SMLO'.includes(ch));
    return Array.from(new Set(chars)).sort().join('');
  };

  C.canonicalSizeKeyFromString = function canonicalSizeKeyFromString(v) {
    if (!v) return '';
    const chars = s(v).toUpperCase().split('').filter(ch => 'SMLO'.includes(ch));
    return Array.from(new Set(chars)).sort().join('');
  };

  C.buildDefaultSpecIndex = function buildDefaultSpecIndex(rows) {
    const idx = {};
    if (!Array.isArray(rows)) return idx;

    rows.forEach(r => {
      if (!r) return;
      const model = s(r.MODEL_ID ?? r.model).trim();
      const code = s(r.DEFECT_CODE ?? r.adc_def_code ?? r.ai_code_1).trim();
      const sizeKey = C.canonicalSizeKeyFromString(r.SIZE_TYPE ?? r.defect_size);
      if (!model || !code || !sizeKey) return;

      const ooc = toNum(r.OOC);
      const oos = toNum(r.OOS);
      if (ooc == null && oos == null) return;

      idx[model] = idx[model] || {};
      idx[model][code] = idx[model][code] || {};
      idx[model][code][sizeKey] = { ooc, oos };
    });

    return idx;
  };

  C.pickDefaultSpec = function pickDefaultSpec(defaultIdx, model, code, sizeKey) {
    const byModel = defaultIdx?.[model];
    if (!byModel) return null;
    const byCode = byModel[code];
    if (!byCode) return null;
    if (sizeKey && byCode[sizeKey]) return byCode[sizeKey];
    const anyKey = Object.keys(byCode)[0];
    return anyKey ? byCode[anyKey] : null;
  };

  C.buildFixedSpecIndex = function buildFixedSpecIndex(rows) {
    const idx = {};
    if (!Array.isArray(rows)) return idx;

    rows.forEach(r => {
      if (!r) return;
      const line = s(r.line_id).trim();
      const aoi = s(r.aoi).trim();
      const model = s(r.model).trim();
      const code = s(r.adc_def_code ?? r.DEFECT_CODE ?? r.ai_code_1).trim();
      const recipe = s(r.recipe_id).trim();
      const side = s(r.glass_type).trim();
      const sizeKey = C.canonicalSizeKeyFromString(r.size_key ?? r.SIZE_KEY ?? r.defect_size ?? r.DEFECT_SIZE);
      if (!line || !aoi || !model || !code || !recipe || !side || !sizeKey) return;

      const ooc = toNum(r.OOC);
      const oos = toNum(r.OOS);
      if (ooc == null && oos == null) return;

      idx[[line, aoi, model, code, recipe, side, sizeKey].join('|')] = { ooc, oos };
    });

    return idx;
  };

  C.pickFixedSpec = function pickFixedSpec(fixedIdx, line, aoi, model, code, recipe, side, sizeKey) {
    if (!fixedIdx) return null;
    const exactKey = [line, aoi, model, code, recipe, side, sizeKey].join('|');
    if (fixedIdx[exactKey]) return fixedIdx[exactKey];
    const prefix = [line, aoi, model, code, recipe, side].join('|') + '|';
    const keys = Object.keys(fixedIdx).filter(k => k.startsWith(prefix));
    return keys.length ? fixedIdx[keys[0]] : null;
  };

  C.safeParseJsonObject = function safeParseJsonObject(v) {
    if (!v) return {};
    if (typeof v === 'object' && !Array.isArray(v)) return v;
    if (typeof v === 'string') {
      const text = v.trim();
      if (!text) return {};
      try {
        const obj = JSON.parse(text);
        return obj && typeof obj === 'object' && !Array.isArray(obj) ? obj : {};
      } catch (_) {
        return {};
      }
    }
    return {};
  };

  C.getRowGlassSizeDetailObj = function getRowGlassSizeDetailObj(row) {
    return row?.glass_size_detail_obj || C.safeParseJsonObject(row?.glass_size_detail) || {};
  };

  C.addDefectGlassesFromRow = function addDefectGlassesFromRow(targetSet, row) {
    if (!targetSet || !row) return 0;

    const detail = C.getRowGlassSizeDetailObj(row);
    let added = 0;

    if (detail && typeof detail === 'object' && Object.keys(detail).length) {
      Object.entries(detail).forEach(([glassId, stat]) => {
        const gid = s(glassId).trim();
        if (!gid || !stat || typeof stat !== 'object') return;
        if (n(stat.T) > 0 && !targetSet.has(gid)) {
          targetSet.add(gid);
          added += 1;
        }
      });
      return added;
    }

    s(row.glass).split(',').map(x => x.trim()).filter(Boolean).forEach(gid => {
      if (!targetSet.has(gid)) {
        targetSet.add(gid);
        added += 1;
      }
    });

    return added;
  };

  C.calcTooltipCountsFromRows = function calcTooltipCountsFromRows(pick) {
    const A = C.A;
    const seenRows = new Set();
    let dCode = 0;
    let S = 0;
    let M = 0;
    let L = 0;
    let O = 0;

    (pick || []).forEach(rec => {
      const rowUid = s(rec?.row_uid || [
        A.tickRaw(rec), A.line(rec), A.aoi(rec), A.model(rec), A.side(rec), s(rec?.tab_name), A.recipe(rec), A.code(rec)
      ].join('||'));

      if (seenRows.has(rowUid)) return;
      seenRows.add(rowUid);

      dCode += n(rec.defect_cnt);
      S += n(rec.small_defect_count);
      M += n(rec.middle_defect_count);
      L += n(rec.large_defect_count);
      O += n(rec.over_defect_count);
    });

    return { dCode, S, M, L, O };
  };

  C.shouldTotalDensityPointAlert = function shouldTotalDensityPointAlert(v) {
    const x = Number(v);
    return Number.isFinite(x) && x > C.ALERT_CONFIG.totalDensityThreshold;
  };

  C.buildAlertRowFromChartPoint = function buildAlertRowFromChartPoint(row, tickStr, aoi, code, totalDensity, tabTG, tabTD) {
    return {
      pi_hour: tickStr,
      pi_hour_raw: tickStr,
      line_id: s(row?.line_id),
      aoi: s(aoi || row?.aoi),
      model: s(row?.model),
      glass_type: s(row?.glass_type),
      adc_def_code: s(code || row?.code),
      recipe_id: s(row?.recipe_id),
      tab_total_glass_cnt: n(tabTG),
      tab_total_defect_cnt: n(tabTD),
      tab_total_density: n(totalDensity),
      total_glass_cnt: n(tabTG),
      total_defect_cnt: n(tabTD),
      total_density: n(totalDensity),
      alert_source: 'aoi_density_chart_total_scatter'
    };
  };

  C.fireAlertRowsOnce = function fireAlertRowsOnce(alertRows) {
    if (!Array.isArray(alertRows) || !alertRows.length) return;
    // 保留接口；目前原始程式也是註解掉寄信。
  };

  C.stopTotalDensityBlink = function stopTotalDensityBlink(inst) {
    if (!inst) return;
    if (inst.__aoiDensityBlinkTimer) {
      clearInterval(inst.__aoiDensityBlinkTimer);
      inst.__aoiDensityBlinkTimer = null;
    }
  };

  C.startTotalDensityBlink = function startTotalDensityBlink(inst) {
    if (!inst) return;
    C.stopTotalDensityBlink(inst);

    let flag = false;
    inst.__aoiDensityBlinkTimer = setInterval(() => {
      flag = !flag;
      let op;
      try {
        op = inst.getOption();
      } catch (_) {
        return;
      }

      const updates = [];
      (op?.series || []).forEach(ss => {
        const sid = s(ss.id);
        if (!sid.startsWith('sc:')) return;
        if (!Array.isArray(ss.data)) return;

        const newData = ss.data.map(p => {
          if (!p || !p.needAlert) return p;
          return {
            ...p,
            itemStyle: {
              ...(p.itemStyle || {}),
              color: flag ? C.ALERT_CONFIG.blinkColorA : C.ALERT_CONFIG.blinkColorB
            }
          };
        });

        updates.push({ id: sid, data: newData });
      });

      if (updates.length) {
        inst.setOption({ series: updates }, false, true);
      }
    }, C.ALERT_CONFIG.blinkMs);
  };

  C.getDensityScaleStore = function getDensityScaleStore() {
    if (!MOD.Charts.__densScaleByKey) MOD.Charts.__densScaleByKey = Object.create(null);
    return MOD.Charts.__densScaleByKey;
  };

  C.applyOneRightAxisMaxById = function applyOneRightAxisMaxById(inst, yId, newMax) {
    inst.setOption({ yAxis: [{ id: yId, min: 0, max: newMax }] }, {
      notMerge: false,
      lazyUpdate: true,
      silent: true
    });
  };

  C.ensureSliderOverlay = function ensureSliderOverlay(dom) {
    let overlay = dom.querySelector('.aoi-density-slider-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.className = 'aoi-density-slider-overlay';
      Object.assign(overlay.style, {
        position: 'absolute',
        left: '0',
        top: '0',
        right: '0',
        bottom: '0',
        zIndex: '999',
        pointerEvents: 'none'
      });
      dom.appendChild(overlay);
    }
    overlay.innerHTML = '';
    return overlay;
  };

  C.mountPerGridSliders = function mountPerGridSliders(dom, inst, densMetaList) {
    // Heavy/extreme mode 不掛每格 slider，避免幾百個 DOM input 拖垮瀏覽器。
    if (dom.__aoiDensityHeavy || dom.__aoiDensityExtreme) {
      dom.querySelectorAll('.aoi-density-slider-wrap').forEach(el => el.remove());
      return;
    }

    if (!inst || !Array.isArray(densMetaList) || !densMetaList.length) return;

    C.ensureSliderOverlay(dom);
    dom.querySelectorAll('.aoi-density-slider-wrap').forEach(el => el.remove());

    const store = C.getDensityScaleStore();
    const model = inst.getModel?.();
    if (!model) return;

    densMetaList.forEach(m => {
      const gridModel = model.getComponent('grid', m.gridIndex);
      const rect = gridModel?.coordinateSystem?.getRect?.();
      if (!rect || !(rect.width > 0) || !(rect.height > 0)) return;

      const wrap = document.createElement('div');
      wrap.className = 'aoi-density-slider-wrap';
      Object.assign(wrap.style, {
        position: 'absolute',
        pointerEvents: 'auto',
        left: `${rect.x + rect.width + 2}px`,
        top: `${rect.y}px`,
        width: '20px',
        height: `${rect.height}px`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: '1000',
        background: 'rgba(255,255,255,0.02)',
        border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: '6px'
      });

      const range = document.createElement('input');
      range.type = 'range';
      range.min = '5';
      range.max = '200';
      range.step = '5';

      const initScale = typeof store[m.key] === 'number' ? store[m.key] : 1;
      range.value = String(Math.round(initScale * 100));
      Object.assign(range.style, {
        width: '18px',
        height: `${rect.height}px`,
        writingMode: 'vertical-lr',
        direction: 'rtl',
        opacity: '0.92',
        margin: '0'
      });

      const tag = document.createElement('div');
      tag.textContent = `${range.value}%`;
      Object.assign(tag.style, {
        position: 'absolute',
        left: '50%',
        top: '-6px',
        transform: 'translate(-50%, -100%)',
        fontSize: '10px',
        color: '#aeb6c7',
        padding: '2px 4px',
        borderRadius: '4px',
        background: 'rgba(15,18,27,0.75)',
        border: '1px solid rgba(255,255,255,0.10)',
        whiteSpace: 'nowrap',
        pointerEvents: 'none'
      });

      const apply = () => {
        const scale = Number(range.value) / 100;
        store[m.key] = scale;
        tag.textContent = `${range.value}%`;
        const baseMax = Number(m.baseMax);
        const newMax = Math.max(1e-6, (Number.isFinite(baseMax) ? baseMax : 1) * scale);
        C.applyOneRightAxisMaxById(inst, m.yId, newMax);
      };

      const stopBubble = e => {
        try { e.stopPropagation?.(); } catch (_) {}
        try { e.stopImmediatePropagation?.(); } catch (_) {}
      };

      ['pointerdown', 'mousedown', 'click'].forEach(evt => range.addEventListener(evt, stopBubble, true));
      range.addEventListener('touchstart', stopBubble, { capture: true, passive: true });
      range.addEventListener('touchmove', stopBubble, { capture: true, passive: true });
      range.addEventListener('wheel', e => {
        stopBubble(e);
        try { e.preventDefault?.(); } catch (_) {}
      }, { capture: true, passive: false });

      let rafPending = 0;
      range.addEventListener('input', () => {
        if (rafPending) return;
        rafPending = requestAnimationFrame(() => {
          rafPending = 0;
          apply();
        });
      });
      range.addEventListener('change', apply);
      range.addEventListener('dblclick', e => {
        stopBubble(e);
        range.value = '100';
        apply();
      });

      wrap.title = '拖拉調整 Density 右軸上限（雙擊重置 100%）';
      wrap.appendChild(range);
      wrap.appendChild(tag);
      dom.appendChild(wrap);

      const baseMax = Number(m.baseMax);
      const newMax = Math.max(1e-6, (Number.isFinite(baseMax) ? baseMax : 1) * initScale);
      C.applyOneRightAxisMaxById(inst, m.yId, newMax);
    });
  };
})();
