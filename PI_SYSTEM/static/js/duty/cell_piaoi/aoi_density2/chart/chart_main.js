// static/js/aoi_density/chart/chart_main.js
// AOI Density Chart - public entry
(function () {
  'use strict';

  const MOD = (window.AOI_DENSITY = window.AOI_DENSITY || {});
  MOD.Charts = MOD.Charts || {};

  const C = (MOD.ChartCore = MOD.ChartCore || {});

  function ensureHost() {
    const host = document.querySelector('#aoi-density-facet');
    if (!host) return null;

    host.innerHTML = '';
    host.style.overflow = 'auto';

    const div = document.createElement('div');
    div.className = 'aoi-bigchart';
    div.style.height = '320px';
    div.style.minHeight = '320px';
    div.style.position = 'relative';
    div.style.overflow = 'visible';
    host.appendChild(div);

    return div;
  }

  function showMessage(dom, html) {
    dom.innerHTML = `<div class="muted" style="padding:16px;line-height:1.6;">${html}</div>`;
  }

  function showHeavyNotice(model) {
    const root = document.querySelector('#aoi-density-facet');
    if (!root || !model.heavy) return;

    let note = document.getElementById('aoi-density-chart-heavy-note');
    if (!note) {
      note = document.createElement('div');
      note.id = 'aoi-density-chart-heavy-note';
      root.insertAdjacentElement('beforebegin', note);
    }

    const level = model.extreme ? '極大量資料模式' : '大量資料模式';
    note.textContent = `${level}：grid=${model.gridCount}, points=${model.pointCount}。已自動關閉部分動畫/標籤/滑軌以降低瀏覽器負載，但仍會依照目前篩選完整繪製。`;
    Object.assign(note.style, {
      display: '',
      margin: '6px 0 8px',
      padding: '6px 10px',
      borderRadius: '6px',
      border: '1px solid rgba(255,220,0,0.35)',
      background: 'rgba(255,220,0,0.08)',
      color: '#FFDC00',
      fontSize: '12px',
      lineHeight: '1.4'
    });
  }

  function hideHeavyNotice() {
    const note = document.getElementById('aoi-density-chart-heavy-note');
    if (note) note.style.display = 'none';
  }

  function disposeOld(dom) {
    if (dom.__aoiDensityChartInst) {
      try {
        C.stopTotalDensityBlink(dom.__aoiDensityChartInst);
        dom.__aoiDensityChartInst.dispose();
      } catch (_) {}
      dom.__aoiDensityChartInst = null;
    }
  }

  function renderBigChart(dom, model) {
    const ec = window.echarts;
    if (!ec) {
      showMessage(dom, 'ECharts 未載入');
      return;
    }

    disposeOld(dom);

    dom.__aoiDensityHeavy = !!model.heavy;
    dom.__aoiDensityExtreme = !!model.extreme;

    const inst = ec.init(dom);
    dom.__aoiDensityChartInst = inst;

    const ctx = {
      dom,
      columns: model.columns,
      global: model.global,
      rawRows: model.rawRows,
      rowIndex: model.rowIndex,
      gridCount: model.gridCount,
      pointCount: model.pointCount,
      heavy: model.heavy,
      extreme: model.extreme,
      legendSelectedState: C.buildDefaultLegendSelectedState(),
      totalDensityAlertRows: [],
      interopState: {
        selectedTicks: new Set(),
        focusRowKey: null
      }
    };

    let option = C.buildOption(ctx);

    inst.resize({
      width: dom.clientWidth,
      height: dom.clientHeight
    });

    const mountNow = meta => {
      requestAnimationFrame(() => {
        try {
          C.mountPerGridSliders(dom, inst, meta);
        } catch (e) {
          console.error('[dens-slider] mount error:', e);
        }
      });
    };

    const mountOnce = () => {
      mountNow(option.__densRightAxisMeta);
      inst.off('finished', mountOnce);
    };

    inst.off('finished', mountOnce);
    inst.on('finished', mountOnce);

    inst.setOption(option, true, false);

    C.fireAlertRowsOnce(ctx.totalDensityAlertRows);
    C.startTotalDensityBlink(inst);

    setTimeout(() => mountNow(option.__densRightAxisMeta), 0);
    setTimeout(() => mountNow(option.__densRightAxisMeta), 60);

    
    function rebuild() {
      ctx.totalDensityAlertRows.length = 0;
      option = C.buildOption(ctx);

      inst.resize({
        width: dom.clientWidth,
        height: dom.clientHeight
      });

      const mountOnce2 = () => {
        mountNow(option.__densRightAxisMeta);
        inst.off('finished', mountOnce2);
      };

      inst.off('finished', mountOnce2);
      inst.on('finished', mountOnce2);

      inst.setOption(option, true, true);
      C.fireAlertRowsOnce(ctx.totalDensityAlertRows);
      C.startTotalDensityBlink(inst);

      setTimeout(() => mountNow(option.__densRightAxisMeta), 0);
      setTimeout(() => mountNow(option.__densRightAxisMeta), 60);
      C.refreshOpacity(inst, model.columns, ctx);
    }

    C.bindChartEvents(inst, ctx, rebuild);
    C.bindResize(dom, inst, rebuild);
  }

  MOD.Charts.render = function render(rows, paramDict) {
    const dom = ensureHost();
    if (!dom) return;

    const model = C.buildRenderModel(rows, paramDict);

    if (!model.ok) {
      hideHeavyNotice();
      showMessage(dom, model.message || '沒有資料');
      return;
    }

    hideHeavyNotice();

    renderBigChart(dom, model);
  };
})();
