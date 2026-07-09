// static/js/aoi_density/chart/chart_config.js
// AOI Density Chart - config / constants
(function () {
  'use strict';

  const MOD = (window.AOI_DENSITY = window.AOI_DENSITY || {});
  const C = (MOD.ChartCore = MOD.ChartCore || {});

  C.SLIDER_DEBUG = false;

  C.CHART_THEME = {
    axisLabel: '#aeb6c7',
    axisLine: '#2b3240',
    axisTick: '#3a4354',
    splitLine: 'rgba(255,255,255,0.09)',
    splitLineStrong: 'rgba(255,255,255,0.14)',
    labelText: '#e8edf7',
    labelBg: 'rgba(15,18,27,0.85)',
    labelPad: [2, 4],
    labelRadius: 3,
    mlText: '#eaefff',
    mlBg: 'rgba(13,18,27,0.9)'
  };

  C.CHART_COLOR = {
    glassTotalBar: '#9aa3b2',
    defectGlassBar: '#FF851B',
    densityPoint: '#FF4136',
    totalDensityPoint: '#7FDBFF',
    defaultSpecOOC: '#FFDC00',
    defaultSpecOOS: '#CE0000',
    fixedSpecOOC: '#FFDC00',
    fixedSpecOOS: '#CE0000'
  };

  C.ALERT_CONFIG = {
    totalDensityThreshold: 1000,
    blinkMs: 650,
    blinkColorA: '#ff0000',
    blinkColorB: '#0066ff'
  };

  C.LAYOUT = {
    legendBlockH: 42,
    titleGap: 12,
    headerTextH: 32,
    
    baseLeft: 16,
    gutterLineW: 26,
    gutterGap: 8,
    gutterModelW: 26,
    rightMargin: 80,
    colGap: 80,
    minColWidth: 260,
    rowH: 145,
    rowGap: 75,
    padBottom: 70,
    bottomExtra: 90,
    minChartWidth: 1200
  };

  // 不阻擋繪製，只用來切換降載模式與提示。
  C.PERF_CONFIG = {
    heavyGridCount: Number.POSITIVE_INFINITY,
    heavyPointCount: Number.POSITIVE_INFINITY,
    extremeGridCount: Number.POSITIVE_INFINITY,
    extremePointCount: Number.POSITIVE_INFINITY,
    heavyAnimation: false,
    normalAnimation: true
  };

  C.SERIES_NAMES = {
    glassTotal: 'glass (total)',
    defectGlass: 'defect glass',
    density: 'density',
    totalDensity: 'Total defect density',
  
    // 同點文字獨立 legend 名稱
    samePoint: '同點',
  
    defaultSpec: '預設SPEC',
    fixedSpec: '動態SPEC'
  };
})();
