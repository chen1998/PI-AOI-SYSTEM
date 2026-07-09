// static/js/aoi_density/chart/chart_aggregate.js
// AOI Density Chart - data aggregation / render model builder
(function () {
  'use strict';

  const MOD = (window.AOI_DENSITY = window.AOI_DENSITY || {});
  const C = (MOD.ChartCore = MOD.ChartCore || {});

  function buildGlobalRowOrder(rows) {
    const A = C.A;
    const byLine = new Map();

    (rows || []).forEach(r => {
      const line = A.line(r);
      const model = A.model(r);
      const side = A.side(r);
      if (!line || !model || !side) return;

      if (!byLine.has(line)) byLine.set(line, new Map());
      const byModel = byLine.get(line);

      if (!byModel.has(model)) byModel.set(model, new Set());
      byModel.get(model).add(side);
    });

    const order = [];
    Array.from(byLine.keys()).sort().forEach(line => {
      const byModel = byLine.get(line);
      Array.from(byModel.keys()).sort().forEach(model => {
        Array.from(byModel.get(model)).sort().forEach(side => {
          order.push({ line_id: line, model, glass_type: side });
        });
      });
    });

    const lineGroups = [];
    let i = 0;
    while (i < order.length) {
      const line = order[i].line_id;
      const start = i;
      while (i < order.length && order[i].line_id === line) i += 1;
      lineGroups.push({ line_id: line, start, end: i - 1 });
    }

    return { order, lineGroups };
  }

  function getTabRowsForChart(tabRows) {
    const tab = C.activeTabKey();
    const baseFilters = C.getChartBaseFilters();
    const dateRange = C.getChartDateRange();

    return (tabRows || []).filter(r => {
      const rowTab = String(r.tab_name || '').trim();
      if (tab && rowTab && rowTab !== String(tab)) return false;
      if (!C.passesChartBaseFilters(r, baseFilters)) return false;
      if (!C.passesChartDateFilter(r.pi_hour, dateRange)) return false;
      return true;
    });
  }

  function buildTabTotalAgg(tabRows, tabName) {
    const out = Object.create(null);
    const active = tabName || C.activeTabKey();
    const baseFilters = C.getChartBaseFilters();
    const dateRange = C.getChartDateRange();

    (tabRows || []).forEach(r => {
      const tn = String(r?.tab_name || '').trim();
      if (active && tn !== active) return;
      if (!C.passesChartBaseFilters(r, baseFilters)) return;
      if (!C.passesChartDateFilter(r.pi_hour, dateRange)) return;

      const tick = C.tickToShort(r?.pi_hour);
      const aoi = String(r?.aoi || '').trim();
      const line = String(r?.line_id || '').trim();
      const model = String(r?.model || '').trim();
      const side = String(r?.glass_type || '').trim();
      if (!tick || !aoi || !line || !model || !side) return;

      const key = `${tick}|${aoi}|${line}|${model}|${side}`;
      out[key] = {
        tab_name: tn,
        TG: C.n(r?.tab_total_glass_cnt),
        TD: C.n(r?.tab_total_defect_cnt),
        TotalDensity: Number.isFinite(Number(r?.tab_total_density)) ? Number(r?.tab_total_density) : null,
        recipe_list: String(r?.recipe_list || '')
      };
    });

    const dict = MOD?.state?.TabTotalDict || {};
    const dtab = active ? (dict?.[active] || {}) : {};

    Object.entries(dtab).forEach(([backendKey, v]) => {
      const parts = String(backendKey).split('||');
      if (parts.length < 5) return;

      const [rawPiHour, line, aoi, model, side] = parts;
      const rowLike = { line_id: line, aoi, model, glass_type: side };

      if (!C.passesChartBaseFilters(rowLike, baseFilters)) return;
      if (!C.passesChartDateFilter(rawPiHour, dateRange)) return;

      const tick = C.tickToShort(rawPiHour);
      if (!tick || !aoi || !line || !model || !side) return;

      const key = `${tick}|${aoi}|${line}|${model}|${side}`;
      if (out[key]) return;

      out[key] = {
        tab_name: active,
        TG: C.n(v?.tab_total_glass_cnt),
        TD: C.n(v?.tab_total_defect_cnt),
        TotalDensity: Number.isFinite(Number(v?.tab_total_density)) ? Number(v?.tab_total_density) : null,
        recipe_list: String(v?.recipe_list || '')
      };
    });

    return out;
  }

  function tabAggToSeedRows(tabAgg) {
    const out = [];

    Object.keys(tabAgg || {}).forEach(key => {
      const parts = String(key).split('|');
      if (parts.length < 5) return;

      const [tick, aoi, line_id, model, glass_type] = parts;
      out.push({ pi_hour: tick, line_id, aoi, model, glass_type });
    });

    return out;
  }

  function getTabAggValue(tabAgg, tick, aoi, line, model, side, fallbackRow) {
    const key = `${tick}|${aoi}|${line}|${model}|${side}`;
    if (tabAgg && tabAgg[key]) return tabAgg[key];

    if (fallbackRow) {
      const TG = C.n(fallbackRow?.tab_total_glass_cnt ?? fallbackRow?.total_glass_cnt);
      const TD = C.n(fallbackRow?.tab_total_defect_cnt ?? fallbackRow?.total_defect_cnt);
      const D = Number(fallbackRow?.tab_total_density ?? fallbackRow?.total_density);
      if (TG > 0 || TD > 0) {
        return {
          TG,
          TD,
          TotalDensity: Number.isFinite(D) ? D : (TG > 0 ? TD / TG : null),
          recipe_list: ''
        };
      }
    }

    return { TG: 0, TD: 0, TotalDensity: null, recipe_list: '' };
  }

  function buildRowIndex(rows) {
    const A = C.A;
    const byCriteria = new Map();

    (rows || []).forEach(r => {
      const keys = [
        [A.aoi(r), A.code(r), A.line(r), A.model(r), A.side(r), A.tick(r)].join('|'),
        [A.aoi(r), A.code(r), '', '', '', A.tick(r)].join('|'),
        ['', '', A.line(r), A.model(r), A.side(r), ''].join('|')
      ];

      keys.forEach(key => {
        if (!byCriteria.has(key)) byCriteria.set(key, []);
        byCriteria.get(key).push(r);
      });
    });

    return { byCriteria };
  }

  function rowsByCriteriaFromIndex(rowIndex, rawRows, criteria) {
    const A = C.A;
    const activeBackendTab = C.activeTabKey();

    if (criteria.aoi && criteria.code && criteria.line && criteria.model && criteria.side && criteria.tick) {
      return rowIndex.byCriteria.get([
        criteria.aoi,
        criteria.code,
        criteria.line,
        criteria.model,
        criteria.side,
        criteria.tick
      ].join('|')) || [];
    }

    if (criteria.aoi && criteria.code && criteria.tick && !criteria.line && !criteria.model && !criteria.side) {
      return rowIndex.byCriteria.get([criteria.aoi, criteria.code, '', '', '', criteria.tick].join('|')) || [];
    }

    if (criteria.line && criteria.model && criteria.side && !criteria.aoi && !criteria.code && !criteria.tick) {
      return rowIndex.byCriteria.get(['', '', criteria.line, criteria.model, criteria.side, ''].join('|')) || [];
    }

    return (rawRows || []).filter(r => {
      const rowTab = String(r.tab_name || '').trim();
      if (activeBackendTab && rowTab && rowTab !== activeBackendTab) return false;
      if (criteria.aoi && A.aoi(r) !== criteria.aoi) return false;
      if (criteria.code && A.code(r) !== criteria.code) return false;
      if (criteria.line && A.line(r) !== criteria.line) return false;
      if (criteria.line_id && A.line(r) !== criteria.line_id) return false;
      if (criteria.model && A.model(r) !== criteria.model) return false;
      if (criteria.side && A.side(r) !== criteria.side) return false;
      if (criteria.tick && A.tick(r) !== criteria.tick) return false;
      return true;
    });
  }

  function buildColumnsByAoiCode(rows, globalOrder, defaultSpecIndex, fixedSpecIndex, selectedSizesArr, tabAgg, seedCodes) {
    const A = C.A;
    const selected = new Set(selectedSizesArr && selectedSizesArr.length ? selectedSizesArr : ['S', 'M', 'L', 'O']);
    const selectedSizeKey = C.canonicalSizeKeyFromList(Array.from(selected));

    const agg = Object.create(null);
    const ticksByAoiCode = Object.create(null);
    const codesToSeed = Array.isArray(seedCodes) && seedCodes.length ? seedCodes : [];

    Object.keys(tabAgg || {}).forEach(key => {
      const parts = String(key).split('|');
      if (parts.length < 5) return;

      const [tick, aoi, line, model, side] = parts;
      codesToSeed.forEach(code => {
        if (!aoi || !code || !line || !model || !tick || !side) return;

        const acKey = `${aoi}|${code}`;
        (ticksByAoiCode[acKey] = ticksByAoiCode[acKey] || new Set()).add(tick);

        const Aoi = (agg[aoi] = agg[aoi] || Object.create(null));
        const Code = (Aoi[code] = Aoi[code] || Object.create(null));
        const Line = (Code[line] = Code[line] || Object.create(null));
        const Model = (Line[model] = Line[model] || Object.create(null));
        const Side = (Model[side] = Model[side] || Object.create(null));

        if (!Side[tick]) {
          Side[tick] = {
            d: 0,
            cg: 0,
            glassSet: new Set(),
            s: 0,
            m: 0,
            l: 0,
            o: 0,
            rows: [],
            seenRows: new Set()
          };
        }
      });
    });

    (rows || []).forEach(r => {
      const aoi = A.aoi(r);
      const code = A.code(r);
      const line = A.line(r);
      const model = A.model(r);
      const tick = A.tick(r);
      const side = A.side(r);
      if (!aoi || !code || !line || !model || !tick || !side) return;

      const acKey = `${aoi}|${code}`;
      (ticksByAoiCode[acKey] = ticksByAoiCode[acKey] || new Set()).add(tick);

      const Aoi = (agg[aoi] = agg[aoi] || Object.create(null));
      const Code = (Aoi[code] = Aoi[code] || Object.create(null));
      const Line = (Code[line] = Code[line] || Object.create(null));
      const Model = (Line[model] = Line[model] || Object.create(null));
      const Side = (Model[side] = Model[side] || Object.create(null));
      const T = (Side[tick] = Side[tick] || {
        d: 0,
        cg: 0,
        glassSet: new Set(),
        s: 0,
        m: 0,
        l: 0,
        o: 0,
        rows: [],
        seenRows: new Set()
      });

      const rowUid = String(r?.row_uid || [
        A.tickRaw(r), A.line(r), A.aoi(r), A.model(r), A.side(r), String(r?.tab_name || ''), A.recipe(r), A.code(r)
      ].join('||'));

      if (T.seenRows.has(rowUid)) return;
      T.seenRows.add(rowUid);

      T.d += A.d(r);

      if (!(T.glassSet instanceof Set)) {
        T.glassSet = new Set();
      }
      
      const beforeGlassSetSize = T.glassSet.size;
      
      C.addDefectGlassesFromRow(T.glassSet, r);
      
      if (T.glassSet.size > beforeGlassSetSize || beforeGlassSetSize > 0) {
        T.cg = T.glassSet.size;
      } else {
        T.cg += A.cg(r);
      }

      T.s += A.sCnt(r);
      T.m += A.mCnt(r);
      T.l += A.lCnt(r);
      T.o += A.oCnt(r);
      T.rows.push(r);
    });

    const columns = [];

    Object.keys(agg).sort().forEach(aoi => {
      const perCode = agg[aoi];

      Object.keys(perCode).sort().forEach(code => {
        const xTicks = Array.from(ticksByAoiCode[`${aoi}|${code}`] || []).sort(C.tickSort);

        const rowsOut = globalOrder.map(({ line_id, model, glass_type }) => {
          const bucket = (((perCode[code] || {})[line_id] || {})[model] || {})[glass_type] || {};

          const totalDefArr = [];
          const totalGlassArr = [];
          const totalDensity = [];
          const tabTotalDefArr = [];
          const tabTotalGlassArr = [];
          const tabTotalDensity = [];
          const codeGlasses = [];
          const density = [];
          const sArr = [];
          const mArr = [];
          const lArr = [];
          const oArr = [];
          const defSelArr = [];
          const samePointArr = [];

          let repRecipe = '';
          let repGlassType = glass_type || '';

          xTicks.forEach(tk => {
            const T = bucket[tk] || {
              d: 0,
              cg: 0,
              glassSet: new Set(),
              s: 0,
              m: 0,
              l: 0,
              o: 0,
              rows: []
            };

            const fallbackRow = Array.isArray(T.rows) && T.rows.length ? T.rows[0] : null;
            const tab = getTabAggValue(tabAgg, tk, aoi, line_id, model, glass_type, fallbackRow);

            const TG = Number(tab.TG || 0);
            const TD = Number(tab.TD || 0);
            const totalD = Number.isFinite(Number(tab.TotalDensity)) ? Number(tab.TotalDensity) : (TG > 0 ? TD / TG : null);

            const dSel = Number(T.d || 0);
            const cg = Number(T.cg || 0);

            totalGlassArr.push(TG);
            totalDefArr.push(TD);
            totalDensity.push(totalD);
            tabTotalGlassArr.push(TG);
            tabTotalDefArr.push(TD);
            tabTotalDensity.push(totalD);
            codeGlasses.push(cg);
            defSelArr.push(dSel);
            sArr.push(Number(T.s || 0));
            mArr.push(Number(T.m || 0));
            lArr.push(Number(T.l || 0));
            oArr.push(Number(T.o || 0));
            density.push(TG > 0 ? dSel / TG : null);

            let currentRecipe = repRecipe;
            let currentGlassType = repGlassType || glass_type || '';

            if (Array.isArray(T.rows) && T.rows.length) {
              const found = T.rows.find(rr =>
                String(rr.glass_type ?? '').trim() === String(glass_type ?? '').trim() &&
                String(rr.recipe_id ?? '').trim()
              ) || T.rows.find(rr => String(rr.recipe_id ?? '').trim()) || T.rows[0];

              if (found) {
                currentRecipe = String(found.recipe_id ?? '').trim() || currentRecipe;
                currentGlassType = String(found.glass_type ?? '').trim() || currentGlassType;
                if (!repRecipe) repRecipe = currentRecipe;
                if (!repGlassType) repGlassType = currentGlassType;
              }
            }

            samePointArr.push(C.hasSamePointForChartCell(tk, {
              ...T,
              line_id,
              model,
              glass_type: currentGlassType,
              recipe_id: currentRecipe,
              recipe_list: tab.recipe_list || ''
            }, aoi));
          });

          const specDefault = C.pickDefaultSpec(defaultSpecIndex, model, code, selectedSizeKey);
          const specFixed = C.pickFixedSpec(
            fixedSpecIndex,
            line_id,
            aoi,
            model,
            code,
            repRecipe,
            repGlassType || 'TFT',
            selectedSizeKey
          );

          return {
            aoi,
            code,
            line_id,
            model,
            glass_type,
            totalDefArr,
            totalGlassArr,
            totalDensity,
            tabTotalDefArr,
            tabTotalGlassArr,
            tabTotalDensity,
            codeGlasses,
            density,
            sArr,
            mArr,
            lArr,
            oArr,
            defSelArr,
            samePointArr,
            maxG: Math.max(0, ...tabTotalGlassArr, ...codeGlasses),
            maxDensity: Math.max(0, ...density.filter(x => x != null)),
            maxTotalDensity: Math.max(0, ...tabTotalDensity.filter(x => x != null)),
            specDefault: specDefault || null,
            specFixed: specFixed || null
          };
        });

        columns.push({ aoi, code, xTicks, rows: rowsOut });
      });
    });

    return columns;
  }

  function calcPointCount(columns) {
    let points = 0;
    (columns || []).forEach(col => {
      const tickCount = Array.isArray(col.xTicks) ? col.xTicks.length : 0;
      const rowCount = Array.isArray(col.rows) ? col.rows.length : 0;
      points += tickCount * rowCount * 4;
    });
    return points;
  }

  function calcGridCount(columns) {
    return (columns || []).reduce((acc, col) => acc + (Array.isArray(col.rows) ? col.rows.length : 0), 0);
  }

  C.buildGlobalRowOrder = buildGlobalRowOrder;
  C.getTabRowsForChart = getTabRowsForChart;
  C.buildTabTotalAgg = buildTabTotalAgg;
  C.tabAggToSeedRows = tabAggToSeedRows;
  C.getTabAggValue = getTabAggValue;
  C.buildColumnsByAoiCode = buildColumnsByAoiCode;
  C.buildRowIndex = buildRowIndex;
  C.rowsByCriteriaFromIndex = rowsByCriteriaFromIndex;

  C.buildRenderModel = function buildRenderModel(rows, paramDict) {
    const activeBackendTab = C.activeTabKey();
    const rawRows0 = Array.isArray(rows) ? rows : [];

    const currentRows = rawRows0.filter(r => {
      const rowTab = String(r?.tab_name || '').trim();
      if (activeBackendTab && rowTab && rowTab !== activeBackendTab) return false;
      return true;
    });

    if (!currentRows.length || MOD?.state?.forceEmptyFilter) {
      return { ok: false, message: '沒有資料' };
    }

    let proSpecDict = MOD?.state?.ProSpecDict || null;
    if (!proSpecDict && paramDict && paramDict.ProSpecDict) {
      proSpecDict = paramDict.ProSpecDict;
    }

    const defaultRows = proSpecDict?.default_spec_table ? Object.values(proSpecDict.default_spec_table) : [];
    const fixedRows = proSpecDict?.fixed_spec_table ? Object.values(proSpecDict.fixed_spec_table) : [];

    const defaultSpecIndex = C.buildDefaultSpecIndex(defaultRows);
    const fixedSpecIndex = C.buildFixedSpecIndex(fixedRows);

    const tabRowsAll = MOD?.state?.TabSummaryData || [];
    const tabRowsForChart = getTabRowsForChart(tabRowsAll);
    const tabAgg = buildTabTotalAgg(tabRowsForChart, activeBackendTab);

    const seedRowsFromTabSummary = tabRowsForChart.map(r => ({
      line_id: r.line_id,
      aoi: r.aoi,
      model: r.model,
      glass_type: r.glass_type,
      pi_hour: C.tickToShort(r.pi_hour)
    }));

    const seedRowsFromTabAgg = tabAggToSeedRows(tabAgg);
    const seedOrderRows = currentRows.concat(seedRowsFromTabSummary, seedRowsFromTabAgg);
    const global = buildGlobalRowOrder(seedOrderRows);

    const columns = buildColumnsByAoiCode(
      currentRows,
      global.order,
      defaultSpecIndex,
      fixedSpecIndex,
      C.getSelectedSizes(),
      tabAgg,
      C.getSelectedCodes(currentRows)
    );

    if (!columns.length) {
      return { ok: false, message: '沒有資料' };
    }

    const gridCount = calcGridCount(columns);
    const pointCount = calcPointCount(columns);
    const perf = C.PERF_CONFIG || {
      heavyGridCount: 80,
      heavyPointCount: 8000,
      extremeGridCount: 999999,
      extremePointCount: 999999
    };
    
    const heavy = false;
    const extreme = false;

    return {
      ok: true,
      columns,
      global,
      rawRows: currentRows,
      rowIndex: buildRowIndex(currentRows),
      gridCount,
      pointCount,
      heavy,
      extreme
    };
  };
})();
