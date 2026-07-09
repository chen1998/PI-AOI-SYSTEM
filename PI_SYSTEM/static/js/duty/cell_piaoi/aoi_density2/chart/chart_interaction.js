// static/js/aoi_density/chart/chart_interaction.js
// AOI Density Chart - click / brush / resize / opacity refresh
(function () {
  'use strict';

  const MOD = (window.AOI_DENSITY = window.AOI_DENSITY || {});
  const C = (MOD.ChartCore = MOD.ChartCore || {});

  function rowKeyOf(aoi, code, rIdx, row) {
    return `${aoi}|${code}|${rIdx}|${row.glass_type || ''}`;
  }

  C.refreshOpacity = function refreshOpacity(inst, columns, ctx) {
    if (!inst || !Array.isArray(columns)) return;

    const updates = [];

    columns.forEach(col => {
      const { aoi, code, rows } = col;

      rows.forEach((row, rIdx) => {
        const rowKey = rowKeyOf(aoi, code, rIdx, row);

        const barIdG = `barG:${aoi}:${code}:${rIdx}`;
        updates.push({
          id: barIdG,
          data: C.makeSeriesData(row, col, aoi, code, rowKey, ctx.interopState, ctx, 'glassTotal')
        });

        const barIdCG = `barCG:${aoi}:${code}:${rIdx}`;
        updates.push({
          id: barIdCG,
          data: C.makeSeriesData(row, col, aoi, code, rowKey, ctx.interopState, ctx, 'defectGlass')
        });

        const scId = `sc:${aoi}:${code}:${rIdx}`;
        updates.push({
          id: scId,
          data: C.makeSeriesData(row, col, aoi, code, rowKey, ctx.interopState, ctx, 'density')
        });

        const totalScId = `scTotal:${aoi}:${code}:${rIdx}`;
        updates.push({
          id: totalScId,
          data: C.makeSeriesData(row, col, aoi, code, rowKey, ctx.interopState, ctx, 'totalDensity')
        });
      });
    });

    if (updates.length) {
      inst.setOption({ series: updates }, false, false);
    }
  };

  C.bindChartEvents = function bindChartEvents(inst, ctx, rebuild) {
    if (!inst) return;

    let lastClickAt = 0;

    inst.off('click');
    inst.on('click', function onClick(ev) {
      if (ev?.componentType === 'xAxis') {
        const xAxisIndex = ev?.xAxisIndex ?? ev?.axisIndex ?? 0;
        const ranges = inst.getOption().__colAxisIndexRange || [];
        let found = null;

        for (const r of ranges) {
          if (xAxisIndex >= r.xStart && xAxisIndex < r.xEnd) {
            found = r;
            break;
          }
        }

        if (!found) return;

        const { aoi, code } = found;
        const tickStr = String(ev.value);
        const pick = C.rowsByCriteriaFromIndex(ctx.rowIndex, ctx.rawRows, {
          aoi,
          code,
          tick: tickStr
        });

        MOD?.handleSelection?.(pick, MOD?.state?.paramDict);
        return;
      }

      if (ev?.componentType === 'yAxis') {
        const yIdx = ev?.yAxisIndex;
        const metaMap = inst.getOption().__yAxisMetaMap || {};
        const hit = metaMap[yIdx];
        if (!hit) return;

        const col = ctx.columns.find(c => c.aoi === hit.aoi && c.code === hit.code);
        if (!col) return;

        const row = col.rows[hit.local];
        if (!row) return;

        const pick = C.rowsByCriteriaFromIndex(ctx.rowIndex, ctx.rawRows, {
          line: row.line_id,
          model: row.model,
          side: row.glass_type
        });

        MOD?.handleSelection?.(pick, MOD?.state?.paramDict);
        return;
      }

      if (ev?.componentType === 'series') {
        const now = Date.now();
        if (now - lastClickAt < 300) return;
        lastClickAt = now;

        const sId = ev.seriesId || '';
        const parts = sId.split(':');
        const aoi = parts[1];
        const code = parts[2];
        const rIdx = Number(parts[3] || 0);

        const col = ctx.columns.find(c => c.aoi === aoi && c.code === code);
        if (!col) return;

        const dataIdx = ev.dataIndex;
        const tickStr = col.xTicks[dataIdx];
        const row = col.rows[rIdx];
        if (!tickStr || !row) return;

        const isBar = sId.startsWith('barG:') || sId.startsWith('barCG:');
        if (isBar) {
          const tabTD = Number(row.tabTotalDefArr?.[dataIdx] ?? 0);
          const tabTG = Number(row.tabTotalGlassArr?.[dataIdx] ?? 0);
          const tabTotalDensity = Number(row.tabTotalDensity?.[dataIdx] ?? 0);
          console.log(
            `[TabTotal] tick=${tickStr} aoi=${aoi} line=${row.line_id} model=${row.model} side=${row.glass_type} ` +
            `tab=${C.activeTabKey()} rawTab=${C.rawActiveTabKey()} tabTD=${tabTD} tabTG=${tabTG} tabDensity=${tabTotalDensity.toFixed(4)}`
          );
        }

        const pick = C.rowsByCriteriaFromIndex(ctx.rowIndex, ctx.rawRows, {
          aoi,
          code,
          line: row.line_id,
          model: row.model,
          side: row.glass_type,
          tick: tickStr
        });

        MOD?.handleSelection?.(pick, MOD?.state?.paramDict);
      }
    });

    inst.off('brushselected');
    inst.on('brushselected', function onBrushSelected(params) {
      if (ctx.extreme) return;

      ctx.interopState.selectedTicks.clear();

      const sel = params.batch?.[0]?.selected || [];
      const ranges = inst.getOption().__colAxisIndexRange || [];

      sel.forEach(ss => {
        const axisIndex = ss.xAxisIndex;
        const idxRange = ss.dataIndex;
        if (!Array.isArray(idxRange) || idxRange.length < 2) return;

        let found = null;
        for (const r of ranges) {
          if (axisIndex >= r.xStart && axisIndex < r.xEnd) {
            found = r;
            break;
          }
        }
        if (!found) return;

        const { aoi, code } = found;
        const [sidx, eidx] = idxRange;
        const lo = Math.min(sidx, eidx);
        const hi = Math.max(sidx, eidx);

        for (let i = lo; i <= hi; i += 1) {
          ctx.interopState.selectedTicks.add(`${i}|${aoi}|${code}`);
        }
      });

      C.refreshOpacity(inst, ctx.columns, ctx);
      C.startTotalDensityBlink(inst);
    });

    inst.off('legendselectchanged');
    inst.on('legendselectchanged', function onLegendSelectChanged(ev) {
      ctx.legendSelectedState = {
        ...ctx.legendSelectedState,
        ...(ev?.selected || {})
      };
      rebuild();
    });
  };

  C.bindResize = function bindResize(dom, inst, rebuild) {
    if (dom.__aoiDensityResizeHandler) {
      window.removeEventListener('resize', dom.__aoiDensityResizeHandler);
    }

    let timer = 0;
    dom.__aoiDensityResizeHandler = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        try {
          inst.resize();
          rebuild();
        } catch (_) {}
      }, 150);
    };

    window.addEventListener('resize', dom.__aoiDensityResizeHandler);
  };
})();
