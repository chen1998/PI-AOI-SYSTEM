// static/js/aoi_inspection_density/tabs/trend_chart.js
(function () {
  const AOI = (window.AOI_INSPECTION = window.AOI_INSPECTION || {});
  const API = window.AOI_INSPECTION_API;

  const $ = (sel, root = document) => root.querySelector(sel);

  const _hasFilterSelectedByTarget = {
    summary: false,
    month: false,
    week: false,
    day: false
  };

  const _charts = {};

  function resizeAllChartsSoon() {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        adjustChartHeights();
      });
    });
  }

  const _trendState = {
    inited: false,
    lastInitResp: null
  };

  const GROUP_TO_TARGET = { g0: "summary", g1: "month", g2: "week", g3: "day" };
  const TARGET_TO_CANVAS = {
    summary: "aoi-inspection-density-trend-chart-canvas-0",
    month:   "aoi-inspection-density-trend-chart-canvas-1",
    week:    "aoi-inspection-density-trend-chart-canvas-2",
    day:     "aoi-inspection-density-trend-chart-canvas-3"
  };
  const TARGET_TO_TITLE = {
    summary: "Summary",
    month: "Month",
    week: "Week",
    day: "Day"
  };

  
  function pad2(n) { return String(n).padStart(2, "0"); }
  function ymd(d){ return `${d.getFullYear()}-${pad2(d.getMonth()+1)}-${pad2(d.getDate())}`; }

  const SHIFT_HOUR = 7;
  const SHIFT_MIN  = 30;

  function nowFloorHour(){
    const d = new Date();
    d.setMinutes(0,0,0);
    return d;
  }

  function workdayLabelToday(){
    const d = nowFloorHour();
    d.setHours(d.getHours() - SHIFT_HOUR);
    d.setMinutes(d.getMinutes() - SHIFT_MIN);
    d.setHours(0,0,0,0);
    return d;
  }

  function ymStr(d) {
    return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}`;
  }

  function isoWeekString(dateObj) {
    const d = new Date(Date.UTC(dateObj.getFullYear(), dateObj.getMonth(), dateObj.getDate()));
    const dayNum = d.getUTCDay() || 7;
    d.setUTCDate(d.getUTCDate() + 4 - dayNum);
    const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    const weekNo = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
    return `${d.getUTCFullYear()}-W${pad2(weekNo)}`;
  }

  function setDateMaxToWorkdayToday(){
    const max = ymd(workdayLabelToday());
    [
      "aoi-inspection-density-trend-chart-g0-dayStart",
      "aoi-inspection-density-trend-chart-g0-dayEnd",
      "aoi-inspection-density-trend-chart-g3-dayStart",
      "aoi-inspection-density-trend-chart-g3-dayEnd"
    ].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.max = max;
    });
  }

  function setMonthWeekMaxToWorkdayToday() {
    const endLabel = workdayLabelToday();
    const maxMonth = ymStr(endLabel);
    const maxWeek  = isoWeekString(endLabel);

    [
      "aoi-inspection-density-trend-chart-g0-monthStart",
      "aoi-inspection-density-trend-chart-g0-monthEnd",
      "aoi-inspection-density-trend-chart-g1-monthStart",
      "aoi-inspection-density-trend-chart-g1-monthEnd"
    ].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.max = maxMonth;
    });

    [
      "aoi-inspection-density-trend-chart-g0-weekStart",
      "aoi-inspection-density-trend-chart-g0-weekEnd",
      "aoi-inspection-density-trend-chart-g2-weekStart",
      "aoi-inspection-density-trend-chart-g2-weekEnd"
    ].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.max = maxWeek;
    });
  }

  function toMonthInput(d){ return `${d.getFullYear()}-${pad2(d.getMonth()+1)}`; }
  function startOfMonth(d){ return new Date(d.getFullYear(), d.getMonth(), 1); }
  function addMonths(d, n){ return new Date(d.getFullYear(), d.getMonth()+n, 1); }

  function startOfISOWeek(d){
    const x = new Date(d);
    const day = x.getDay() || 7;
    x.setDate(x.getDate() - (day - 1));
    x.setHours(0,0,0,0);
    return x;
  }

  function addDays(d, n){
    const x = new Date(d);
    x.setDate(x.getDate()+n);
    return x;
  }

  function computeDefaultRanges(){
    const endLabel = workdayLabelToday();

    const g0mEnd   = startOfMonth(endLabel);
    const g0mStart = addMonths(g0mEnd, -(6-1));

    const g0wEnd   = startOfISOWeek(endLabel);
    const g0wStart = addDays(g0wEnd, -7*(9-1));

    const g0dEnd   = new Date(endLabel);
    const g0dStart = addDays(g0dEnd, -(6-1));

    const g1mEnd   = startOfMonth(endLabel);
    const g1mStart = addMonths(g1mEnd, -(7-1));

    const g2wEnd   = startOfISOWeek(endLabel);
    const g2wStart = addDays(g2wEnd, -7*(7-1));

    const g3dEnd   = new Date(endLabel);
    const g3dStart = addDays(g3dEnd, -(7-1));

    return {
      g0: {
        monthStart: toMonthInput(g0mStart), monthEnd: toMonthInput(g0mEnd),
        weekStart: isoWeekString(g0wStart), weekEnd: isoWeekString(g0wEnd),
        dayStart: ymd(g0dStart), dayEnd: ymd(g0dEnd)
      },
      g1: { monthStart: toMonthInput(g1mStart), monthEnd: toMonthInput(g1mEnd) },
      g2: { weekStart: isoWeekString(g2wStart), weekEnd: isoWeekString(g2wEnd) },
      g3: { dayStart: ymd(g3dStart), dayEnd: ymd(g3dEnd) }
    };
  }

  function setDefaultRangesOnInputs(){
    const d = computeDefaultRanges();

    $("#aoi-inspection-density-trend-chart-g0-monthStart").value = d.g0.monthStart;
    $("#aoi-inspection-density-trend-chart-g0-monthEnd").value   = d.g0.monthEnd;
    $("#aoi-inspection-density-trend-chart-g0-weekStart").value  = d.g0.weekStart;
    $("#aoi-inspection-density-trend-chart-g0-weekEnd").value    = d.g0.weekEnd;
    $("#aoi-inspection-density-trend-chart-g0-dayStart").value   = d.g0.dayStart;
    $("#aoi-inspection-density-trend-chart-g0-dayEnd").value     = d.g0.dayEnd;

    $("#aoi-inspection-density-trend-chart-g1-monthStart").value = d.g1.monthStart;
    $("#aoi-inspection-density-trend-chart-g1-monthEnd").value   = d.g1.monthEnd;

    $("#aoi-inspection-density-trend-chart-g2-weekStart").value  = d.g2.weekStart;
    $("#aoi-inspection-density-trend-chart-g2-weekEnd").value    = d.g2.weekEnd;

    $("#aoi-inspection-density-trend-chart-g3-dayStart").value   = d.g3.dayStart;
    $("#aoi-inspection-density-trend-chart-g3-dayEnd").value     = d.g3.dayEnd;
  }

  function setDefaultRangesForGroup(groupKey){
    const d = computeDefaultRanges()[groupKey];
    if (!d) return;

    if (groupKey === "g0") {
      $("#aoi-inspection-density-trend-chart-g0-monthStart").value = d.monthStart;
      $("#aoi-inspection-density-trend-chart-g0-monthEnd").value   = d.monthEnd;
      $("#aoi-inspection-density-trend-chart-g0-weekStart").value  = d.weekStart;
      $("#aoi-inspection-density-trend-chart-g0-weekEnd").value    = d.weekEnd;
      $("#aoi-inspection-density-trend-chart-g0-dayStart").value   = d.dayStart;
      $("#aoi-inspection-density-trend-chart-g0-dayEnd").value     = d.dayEnd;
    }
    if (groupKey === "g1") {
      $("#aoi-inspection-density-trend-chart-g1-monthStart").value = d.monthStart;
      $("#aoi-inspection-density-trend-chart-g1-monthEnd").value   = d.monthEnd;
    }
    if (groupKey === "g2") {
      $("#aoi-inspection-density-trend-chart-g2-weekStart").value  = d.weekStart;
      $("#aoi-inspection-density-trend-chart-g2-weekEnd").value    = d.weekEnd;
    }
    if (groupKey === "g3") {
      $("#aoi-inspection-density-trend-chart-g3-dayStart").value   = d.dayStart;
      $("#aoi-inspection-density-trend-chart-g3-dayEnd").value     = d.dayEnd;
    }
  }

  function monthInputToYYYYMM(v) {
    if (!v || typeof v !== "string") return "";
    const s = v.replace("-", "").trim();
    return /^\d{6}$/.test(s) ? s : "";
  }

  function weekInputToWYYWW(v) {
    if (!v || typeof v !== "string") return "";
    const m = v.match(/^(\d{4})-W(\d{2})$/i);
    if (!m) return "";
    const year = Number(m[1]);
    const week = Number(m[2]);
    const yy = pad2(year % 100);
    const ww = pad2(week);
    return `W${yy}${ww}`;
  }

  const _mdd = { g0:{}, g1:{}, g2:{}, g3:{} };
  const _mddAllOptions = { g0:{}, g1:{}, g2:{}, g3:{} };

  function _selectAllOnInst(inst, options) {
    if (!inst) return;
    const opts = Array.isArray(options) ? options : [];
    if (typeof inst.selectAll === "function") { inst.selectAll(); return; }
    if (typeof inst.setSelected === "function") { inst.setSelected(opts); return; }
    if (typeof inst.setValue === "function") { inst.setValue(opts); return; }
    if (typeof inst.updateSelected === "function") { inst.updateSelected(opts); return; }
  }

  function ensureMultiDD(groupKey, key, options, onChange) {
    const hostId = `aoi-inspection-density-trend-chart-${groupKey}-mddhost-${key}`;
    const selectId = `aoi-inspection-density-trend-chart-${groupKey}-mddsel-${key}`;
    const host = document.getElementById(hostId);
    if (!host) return null;

    const opts = Array.isArray(options) ? options : [];
    _mddAllOptions[groupKey][key] = opts;

    if (_mdd[groupKey] && _mdd[groupKey][key]) {
      _mdd[groupKey][key].updateOptions(opts);
      return _mdd[groupKey][key];
    }

    const MultiDD = AOI.MultiDD;
    if (!MultiDD) {
      console.error("[AOI_INSPECTION Trend] MultiDD not found");
      return null;
    }

    const inst = new MultiDD({
      hostId,
      selectId,
      options: opts,
      title: key,
      onChange
    });

    _mdd[groupKey][key] = inst;
    return inst;
  }

  function wireSearchForHost(hostEl) {
    if (!hostEl) return;
  
    const ddRoot = hostEl.querySelector(".multi-dd");
    if (!ddRoot) return;
  
    const input = ddRoot.querySelector(".multi-dd-search");
    if (!input) return;
  
    if (input.dataset.searchBound === "1") return;
    input.dataset.searchBound = "1";
  
    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      const items = Array.from(ddRoot.querySelectorAll(".multi-dd-item"));
  
      items.forEach(item => {
        const txt = (item.textContent || "").toLowerCase();
        item.style.display = (!q || txt.includes(q)) ? "" : "none";
      });
    });
  }

  function buildDynFiltersAsMultiDD(groupKey, hostEl, filterOptionDict, onAnyChange) {
  if (!hostEl) return;

  const keys = Object.keys(filterOptionDict || {});

  if (hostEl.dataset.inited === "1") {
    keys.forEach((k) => {
      ensureMultiDD(groupKey, k, filterOptionDict[k] || [], onAnyChange);

      const slot = document.getElementById(
        `aoi-inspection-density-trend-chart-${groupKey}-mddhost-${k}`
      );
      wireSearchForHost(slot);
    });
    return;
  }

  hostEl.dataset.inited = "1";
  hostEl.innerHTML = "";

  keys.forEach((k) => {
    const slot = document.createElement("div");
    slot.className = "aoi-mdd-host";
    slot.id = `aoi-inspection-density-trend-chart-${groupKey}-mddhost-${k}`;
    hostEl.appendChild(slot);

    ensureMultiDD(groupKey, k, filterOptionDict[k] || [], onAnyChange);
    wireSearchForHost(slot);
  });
}

  function readGroupFilters(groupKey) {
    const dict = {};
    const bucket = _mdd[groupKey] || {};
    Object.keys(bucket).forEach(k => {
      dict[k] = bucket[k].getSelected();
    });
    return dict;
  }

  function clearGroupFilters(groupKey) {
    const bucket = _mdd[groupKey] || {};
    Object.values(bucket).forEach(inst => inst.clear());
  }

  function setGroupFiltersSelectAll(groupKey) {
    const bucket = _mdd[groupKey] || {};
    Object.keys(bucket).forEach(k => {
      const inst = bucket[k];
      const opts = _mddAllOptions?.[groupKey]?.[k] || [];
      _selectAllOnInst(inst, opts);
    });
  }

  function normalizeGroupFilters(groupKey, rawFilters) {
    const out = {};
    const f = rawFilters || {};
    const allOpt = _mddAllOptions?.[groupKey] || {};

    Object.keys(f).forEach(k => {
      const arr = Array.isArray(f[k]) ? f[k] : [];
      if (!arr.length) return;

      const allLen = Array.isArray(allOpt[k]) ? allOpt[k].length : 0;
      if (allLen > 0 && arr.length >= allLen) return;

      out[k] = arr;
    });

    return out;
  }

  function v(id) { return document.getElementById(id)?.value || ""; }

  function buildDateDictForTarget(target) {
    if (target === "summary") {
      const out = { summary: { month: [], week: [], day: [] } };

      const ms = monthInputToYYYYMM(v("aoi-inspection-density-trend-chart-g0-monthStart"));
      const me = monthInputToYYYYMM(v("aoi-inspection-density-trend-chart-g0-monthEnd"));
      if (ms && me) out.summary.month = [ms, me];

      const ws = weekInputToWYYWW(v("aoi-inspection-density-trend-chart-g0-weekStart"));
      const we = weekInputToWYYWW(v("aoi-inspection-density-trend-chart-g0-weekEnd"));
      if (ws && we) out.summary.week = [ws, we];

      const ds = v("aoi-inspection-density-trend-chart-g0-dayStart");
      const de = v("aoi-inspection-density-trend-chart-g0-dayEnd");
      if (ds && de) out.summary.day = [ds, de];

      return out;
    }

    if (target === "month") {
      const out = { month: [] };
      const ms = monthInputToYYYYMM(v("aoi-inspection-density-trend-chart-g1-monthStart"));
      const me = monthInputToYYYYMM(v("aoi-inspection-density-trend-chart-g1-monthEnd"));
      if (ms && me) out.month = [ms, me];
      return out;
    }

    if (target === "week") {
      const out = { week: [] };
      const ws = weekInputToWYYWW(v("aoi-inspection-density-trend-chart-g2-weekStart"));
      const we = weekInputToWYYWW(v("aoi-inspection-density-trend-chart-g2-weekEnd"));
      if (ws && we) out.week = [ws, we];
      return out;
    }

    if (target === "day") {
      const out = { day: [] };
      const ds = v("aoi-inspection-density-trend-chart-g3-dayStart");
      const de = v("aoi-inspection-density-trend-chart-g3-dayEnd");
      if (ds && de) out.day = [ds, de];
      return out;
    }

    return {
      summary: { month: [], week: [], day: [] },
      month: [],
      week: [],
      day: []
    };
  }

  function clearTimeInputsForGroup(groupKey) {
    if (groupKey === "g0") {
      [
        "aoi-inspection-density-trend-chart-g0-monthStart",
        "aoi-inspection-density-trend-chart-g0-monthEnd",
        "aoi-inspection-density-trend-chart-g0-weekStart",
        "aoi-inspection-density-trend-chart-g0-weekEnd",
        "aoi-inspection-density-trend-chart-g0-dayStart",
        "aoi-inspection-density-trend-chart-g0-dayEnd"
      ].forEach(id => { const el = document.getElementById(id); if (el) el.value = ""; });
    }
    if (groupKey === "g1") {
      [
        "aoi-inspection-density-trend-chart-g1-monthStart",
        "aoi-inspection-density-trend-chart-g1-monthEnd"
      ].forEach(id => { const el = document.getElementById(id); if (el) el.value = ""; });
    }
    if (groupKey === "g2") {
      [
        "aoi-inspection-density-trend-chart-g2-weekStart",
        "aoi-inspection-density-trend-chart-g2-weekEnd"
      ].forEach(id => { const el = document.getElementById(id); if (el) el.value = ""; });
    }
    if (groupKey === "g3") {
      [
        "aoi-inspection-density-trend-chart-g3-dayStart",
        "aoi-inspection-density-trend-chart-g3-dayEnd"
      ].forEach(id => { const el = document.getElementById(id); if (el) el.value = ""; });
    }
  }

  function buildFiltersPayloadForTarget(target, groupKey) {
    const base = { summary: {}, month: {}, week: {}, day: {} };
    const raw = readGroupFilters(groupKey);
    const norm = normalizeGroupFilters(groupKey, raw);
    base[target] = norm;
    return base;
  }

  async function postTrend({ reason = "", groupKey = "", target = "" } = {}) {
    const isInit = !target;

    const date_dict = isInit
      ? {
          summary: { month: [], week: [], day: [] },
          month: [],
          week: [],
          day: []
        }
      : buildDateDictForTarget(target);

    const filters = isInit
      ? { summary: {}, month: {}, week: {}, day: {} }
      : buildFiltersPayloadForTarget(target, groupKey);

    if (!isInit) {
      const has = Object.keys(filters?.[target] || {}).length > 0;
      _hasFilterSelectedByTarget[target] = has;
    }

    const payload = isInit ? { date_dict, filters } : { target, date_dict, filters };

    console.debug("[AOI_INSPECTION_TREND] request reason=", reason, "target=", target || "(init)", payload);

    const resp = await API.getInspectionTrend(payload);

    try {
      const td = resp?.TrendDict || {};
      const meta = resp?.Meta || {};
      console.debug("[AOI_INSPECTION_TREND] response meta=", meta, {
        summary_points: td?.summary?.points?.length || 0,
        month_points:   td?.month?.points?.length || 0,
        week_points:    td?.week?.points?.length || 0,
        day_points:     td?.day?.points?.length || 0,
      });
    } catch (e) {
      console.debug("[AOI_INSPECTION_TREND] response parse error", e);
    }

    return resp;
  }

  function adjustChartHeights() {
    [
      "aoi-inspection-density-trend-chart-canvas-0",
      "aoi-inspection-density-trend-chart-canvas-1",
      "aoi-inspection-density-trend-chart-canvas-2",
      "aoi-inspection-density-trend-chart-canvas-3"
    ].forEach(id => {
      const ins = _charts[id];
      if (ins && typeof ins.resize === "function") ins.resize();
    });
  }

  function ensureChart(domId) {
    const el = document.getElementById(domId);
    if (!el || !window.echarts) return null;
    if (_charts[domId]) return _charts[domId];
    _charts[domId] = window.echarts.init(el);
    return _charts[domId];
  }

  function renderChart(domId, points, title) {
    const el = document.getElementById(domId);
    if (!el) return;

    const pts = Array.isArray(points) ? points : [];
    const xs  = pts.map(p => p.x_label || p.x || "");

    const n = (v) => (v === null || v === undefined || v === "" ? null : Number(v));
    const totalGlass = pts.map(p => n(p.glass_cnt));
    const totalDef   = pts.map(p => n(p.defect_cnt));
    const totalDen   = pts.map(p => n(p.density));

    const selTotalGlass = pts.map(p => n(p.select_total_glass_cnt));
    const selDefGlass   = pts.map(p => n(p.select_def_glass_cnt));
    const selDefCnt     = pts.map(p => n(p.select_def_cnt));
    const selGlass      = selDefGlass;
    const selDen        = pts.map(p => n(p.select_density));

    const ins = ensureChart(domId);
    if (!ins) {
      el.innerHTML = `<div style="padding:10px;font-size:12px;opacity:.85;">
        <div style="font-weight:600;margin-bottom:6px;">${title || domId}</div>
        <div>points=${pts.length} (ECharts not found)</div>
      </div>`;
      return;
    }

    const fmtInt = (v) => {
      const x = Number(v);
      if (!Number.isFinite(x)) return "-";
      return Math.round(x).toLocaleString();
    };
    const fmtPct = (v) => {
      const x = Number(v);
      if (!Number.isFinite(x)) return "-";
      return x.toFixed(2);
    };
    const fmtPctLabel = (v) => {
      const x = Number(v);
      if (!Number.isFinite(x)) return "";
      return x.toFixed(2);
    };

    const tooltipFormatter = (params) => {
      const idx = Array.isArray(params) && params.length ? params[0].dataIndex : -1;
      const p = pts[idx];
      if (!p) return "";

      const xLabel = p.x_label ?? p.x ?? "";
      let html = `<div style="font-weight:600;margin-bottom:4px;">${xLabel}</div>`;

      html += `<div style="margin-top:6px;font-weight:600;">TOTAL</div>`;
      html += `<div>glass_cnt: ${fmtInt(p.glass_cnt)}</div>`;
      html += `<div>defect_cnt: ${fmtInt(p.defect_cnt)}</div>`;
      html += `<div>density: ${fmtPct(p.density)}</div>`;

      html += `<div style="margin-top:6px;font-weight:600;">SELECT</div>`;
      html += `<div>select_total_glass_cnt: ${fmtInt(p.select_total_glass_cnt)}</div>`;
      html += `<div>select_def_glass_cnt: ${fmtInt(p.select_def_glass_cnt)}</div>`;
      html += `<div>select_def_cnt: ${fmtInt(p.select_def_cnt)}</div>`;
      html += `<div>select_density: ${fmtPct(p.select_density)}</div>`;

      if (domId === "aoi-inspection-density-trend-chart-canvas-0" && p.segment) {
        html += `<div style="margin-top:6px;opacity:.75;">segment: ${p.segment}</div>`;
      }

      return `<div style="line-height:1.4;">${html}</div>`;
    };

    const COLOR_MONTH  = "#4fd1c5";
    const COLOR_WEEK   = "#caa14a";
    const COLOR_DAY    = "#b79cff";
    const COLOR_SINGLE = "#7aa7ff";

    function hexToRgba(hex, a = 0.55) {
      const h = String(hex || "").replace("#", "");
      const x = (h.length === 3) ? h.split("").map(c => c + c).join("") : h;
      const n = parseInt(x, 16);
      if (!Number.isFinite(n)) return `rgba(170,175,190,${a})`;
      const r = (n >> 16) & 255;
      const g = (n >> 8) & 255;
      const b = n & 255;
      return `rgba(${r},${g},${b},${a})`;
    }

    const SEG_COLOR = {
      month:  COLOR_MONTH,
      week:   COLOR_WEEK,
      day:    COLOR_DAY,
      single: COLOR_SINGLE
    };
    const SEG_BAR = {
      month:  hexToRgba(COLOR_MONTH, 0.45),
      week:   hexToRgba(COLOR_WEEK, 0.45),
      day:    hexToRgba(COLOR_DAY, 0.45),
      single: hexToRgba(COLOR_SINGLE, 0.35)
    };

    const L = {
      TotalDensity: "TotalDensity",
      TotalGlass: "TotalGlass",
      SelectTotalGlass: "SelectTotalGlass",
      SelectGlass: "SelectGlass",
      SelectDensity: "SelectDensity",
    };

    const isSummary = (domId === "aoi-inspection-density-trend-chart-canvas-0");
    const maskBySeg = (arr, seg) => pts.map((p, i) => (p.segment === seg ? arr[i] : null));
    const segs = isSummary ? ["month", "week", "day"] : ["single"];

    const axisLabelRich = {
      m: { color: COLOR_MONTH, fontWeight: 600 },
      w: { color: COLOR_WEEK,  fontWeight: 600 },
      d: { color: COLOR_DAY,   fontWeight: 600 },
      n: { color: "#aeb6c7" }
    };

    function axisLabelFormatter(value, idx) {
      if (!isSummary) return value;
      const seg = pts[idx]?.segment;
      if (seg === "month") return `{m|${value}}`;
      if (seg === "week") return `{w|${value}}`;
      if (seg === "day") return `{d|${value}}`;
      return `{n|${value}}`;
    }

    const series = [];

    segs.forEach(seg => {
      const data  = (seg === "single") ? totalGlass : maskBySeg(totalGlass, seg);
      const color = (seg === "single") ? SEG_BAR.single : (SEG_BAR[seg] || SEG_BAR.single);
      series.push({
        name: L.TotalGlass,
        type: "bar",
        yAxisIndex: 1,
        data,
        barWidth: 18,
        barGap: "-100%",
        z: 1,
        itemStyle: { color, opacity: 0.75 },
        emphasis: { focus: "series" }
      });
    });

    segs.forEach(seg => {
      const data = (seg === "single") ? selTotalGlass : maskBySeg(selTotalGlass, seg);
      series.push({
        name: L.SelectTotalGlass,
        type: "bar",
        yAxisIndex: 1,
        data,
        barWidth: 18,
        barGap: "-100%",
        z: 2,
        itemStyle: { color: "#4B2E83", opacity: 0.85 },
        emphasis: { focus: "series" }
      });
    });

    segs.forEach(seg => {
      const data  = (seg === "single") ? selGlass : maskBySeg(selGlass, seg);
      const color = (seg === "single") ? SEG_BAR.single : (SEG_BAR[seg] || SEG_BAR.single);
      series.push({
        name: L.SelectGlass,
        type: "bar",
        yAxisIndex: 1,
        data,
        barWidth: 18,
        barGap: "-100%",
        z: 3,
        itemStyle: { color, opacity: 0.95 },
        emphasis: { focus: "series" }
      });
    });

    const TOTAL_DENSITY_COLOR = "#a0aec0";
    segs.forEach(seg => {
      const data = (seg === "single") ? totalDen : maskBySeg(totalDen, seg);
      series.push({
        name: L.TotalDensity,
        type: "line",
        yAxisIndex: 0,
        data,
        smooth: false,
        connectNulls: false,
        showSymbol: true,
        lineStyle: { width: 2, type: "dashed", color: TOTAL_DENSITY_COLOR },
        itemStyle: { color: TOTAL_DENSITY_COLOR },
        label: {
          show: true,
          position: "top",
          distance: 6,
          formatter: (p) => fmtPctLabel(p.value),
          color: "#ffffff",
          textBorderWidth: 0,
          textBorderColor: "transparent",
          textShadowBlur: 0,
          textShadowColor: "transparent"
        },
        z: 10,
        emphasis: { focus: "series" }
      });
    });

    segs.forEach(seg => {
      const data  = (seg === "single") ? selDen : maskBySeg(selDen, seg);
      const color = (seg === "single") ? SEG_COLOR.single : (SEG_COLOR[seg] || SEG_COLOR.single);

      series.push({
        name: L.SelectDensity,
        type: "line",
        yAxisIndex: 0,
        data,
        smooth: false,
        connectNulls: false,
        showSymbol: true,
        lineStyle: { width: 2, type: "solid", color },
        itemStyle: { color },
        z: 11,
        emphasis: { focus: "series" },
        label: {
          show: true,
          position: "top",
          distance: 6,
          formatter: (p) => fmtPctLabel(p.value),
          color: "#ffffff",
          textBorderWidth: 0,
          textBorderColor: "transparent",
          textShadowBlur: 0,
          textShadowColor: "transparent"
        }
      });
    });

    const selected = {};
    Object.values(L).forEach(k => selected[k] = false);
    selected[L.SelectTotalGlass] = true;
    selected[L.SelectDensity] = true;

    const option = {
      animation: false,
      tooltip: {
        trigger: "axis",
        formatter: tooltipFormatter,
        appendToBody: true,
        confine: false,
        extraCssText: "z-index: 999999 !important;"
      },
      legend: {
        data: Object.values(L),
        bottom: 5,
        textStyle: { color: "#d7dde9", fontSize: 11 },
        selected,
        formatter: (name) => {
          const map = {
            [L.TotalDensity]: "Total density (dashed)",
            [L.TotalGlass]: "Total glass",
            [L.SelectTotalGlass]: "select_total_glass_cnt",
            [L.SelectGlass]: "select_def_glass_cnt",
            [L.SelectDensity]: "select_density",
          };
          return map[name] || name;
        }
      },
      grid: { left: 56, right: 50, top: 45, bottom: 55, containLabel: true },
      xAxis: {
        type: "category",
        data: xs,
        axisLabel: isSummary
          ? {
              interval: 0,
              hideOverlap: false,
              formatter: axisLabelFormatter,
              rich: axisLabelRich
            }
          : {
              interval: 0,
              hideOverlap: false,
              color: "#aeb6c7"
            },
        axisLine: { lineStyle: { color: "rgba(255,255,255,0.35)" } },
        axisTick: { alignWithLabel: true, lineStyle: { color: "rgba(255,255,255,0.22)" } }
      },
      yAxis: [
        {
          type: "value",
          name: "Density",
          nameTextStyle: { color: "#ffffff" },
          axisLabel: { color: "#ffffff", formatter: (v) => fmtPct(v) },
          axisLine: { lineStyle: { color: "rgba(255,255,255,0.35)" } },
          splitLine: { show: true, lineStyle: { color: "rgba(255,255,255,0.14)" } },
          min: 0
        },
        {
          type: "value",
          name: "Count",
          nameTextStyle: { color: "#ffffff" },
          axisLabel: { color: "#ffffff" },
          axisLine: { lineStyle: { color: "rgba(255,255,255,0.35)" } },
          splitLine: { show: false }
        }
      ],
      series
    };

    ins.setOption(option, true);
  }

  function renderAllCharts(resp) {
    const td = resp?.TrendDict || {};
    renderChart(TARGET_TO_CANVAS.summary, td?.summary?.points, TARGET_TO_TITLE.summary);
    renderChart(TARGET_TO_CANVAS.month, td?.month?.points, TARGET_TO_TITLE.month);
    renderChart(TARGET_TO_CANVAS.week, td?.week?.points, TARGET_TO_TITLE.week);
    renderChart(TARGET_TO_CANVAS.day, td?.day?.points, TARGET_TO_TITLE.day);
    adjustChartHeights();
  }

  function renderOneChart(resp, target) {
    const td = resp?.TrendDict || {};
    const canvasId = TARGET_TO_CANVAS[target];
    if (!canvasId) return;
    const pts = td?.[target]?.points;
    renderChart(canvasId, pts, TARGET_TO_TITLE[target]);
    adjustChartHeights();
  }

  function getDynHostElByGroup(groupKey) {
    return document.getElementById(`aoi-inspection-density-trend-chart-dynhosts-${groupKey}`);
  }
  
  function updateOneGroupMultiDD(groupKey, resp, { selectAll = false, keepSelected = true } = {}) {
    const hostEl = getDynHostElByGroup(groupKey);
    if (!hostEl) return;
  
    const fod = getFilterOptionDict(resp);
    const prevRaw = keepSelected ? readGroupFilters(groupKey) : {};
    const onAnyChange = () => {};
  
    buildDynFiltersAsMultiDD(groupKey, hostEl, fod, onAnyChange);
  
    const bucket = _mdd[groupKey] || {};
    Object.keys(bucket).forEach((k) => {
      const inst = bucket[k];
      if (!inst) return;
  
      const newOpts = Array.isArray(_mddAllOptions?.[groupKey]?.[k])
        ? _mddAllOptions[groupKey][k]
        : [];
  
      if (selectAll) {
        _selectAllOnInst(inst, newOpts);
        return;
      }
  
      if (keepSelected) {
        const oldSel = Array.isArray(prevRaw?.[k]) ? prevRaw[k] : [];
        const validSel = oldSel.filter(v => newOpts.includes(v));
        if (validSel.length) {
          inst.setSelected(validSel);
        } else {
          inst.clear();
        }
      }
    });
  }
  
 

  function getFilterOptionDict(resp) {
    return resp?.ParamDict?.filterOptionDict || resp?.filterOptionDict || {};
  }

  function buildAllGroupsMultiDD(resp, { selectAll = false } = {}) {
    const fod = getFilterOptionDict(resp);
    const onAnyChange = () => {};

    buildDynFiltersAsMultiDD("g0", $("#aoi-inspection-density-trend-chart-dynhosts-g0"), fod, onAnyChange);
    buildDynFiltersAsMultiDD("g1", $("#aoi-inspection-density-trend-chart-dynhosts-g1"), fod, onAnyChange);
    buildDynFiltersAsMultiDD("g2", $("#aoi-inspection-density-trend-chart-dynhosts-g2"), fod, onAnyChange);
    buildDynFiltersAsMultiDD("g3", $("#aoi-inspection-density-trend-chart-dynhosts-g3"), fod, onAnyChange);

    const defaults = resp?.ParamDict?.defaultTrendFilters || null;

    function applyDefaultsToGroup(groupKey, defaultDict) {
      if (!defaultDict || typeof defaultDict !== "object") return;
      setGroupFiltersSelectAll(groupKey);
      const bucket = _mdd[groupKey] || {};
      Object.keys(defaultDict).forEach((k) => {
        const inst = bucket[k];
        const want = defaultDict[k];
        if (!inst) return;
        if (Array.isArray(want) && want.length) {
          inst.setSelected(want.slice());
        }
      });
    }

    if (defaults && typeof defaults === "object" && Object.keys(defaults).length) {
      applyDefaultsToGroup("g0", defaults);
      applyDefaultsToGroup("g1", defaults);
      applyDefaultsToGroup("g2", defaults);
      applyDefaultsToGroup("g3", defaults);
      return defaults;
    }

    if (selectAll) {
      setGroupFiltersSelectAll("g0");
      setGroupFiltersSelectAll("g1");
      setGroupFiltersSelectAll("g2");
      setGroupFiltersSelectAll("g3");
    }

    return null;
  }

  function bindButtons() {
    const groups = ["g0","g1","g2","g3"];
    groups.forEach(g => {
      const target = GROUP_TO_TARGET[g];
      const applyBtn = document.getElementById(`aoi-inspection-density-trend-chart-${g}-apply`);
      const clearBtn = document.getElementById(`aoi-inspection-density-trend-chart-${g}-clear`);

      if (applyBtn) {
        applyBtn.addEventListener("click", async () => {
          const resp = await postTrend({ reason: `apply:${g}`, groupKey: g, target });
          if (!resp) return;
          renderOneChart(resp, target);
        });
      }

      if (clearBtn) {
        clearBtn.addEventListener("click", async () => {
          clearTimeInputsForGroup(g);
          setDefaultRangesForGroup(g);
      
          clearGroupFilters(g);
          _hasFilterSelectedByTarget[target] = false;
      
          const resp = await postTrend({ reason: `clear:${g}`, groupKey: g, target });
          if (!resp) return;
      
          updateOneGroupMultiDD(g, resp, { selectAll: true, keepSelected: false });
          renderOneChart(resp, target);
        });
      }
    });
  }

  const _debByGroup = { g0: null, g1: null, g2: null, g3: null };

  function parseGroupFromSelectId(id) {
    if (!id || typeof id !== "string") return "";
    const m = id.match(/^aoi-inspection-density-trend-chart-(g[0-3])-mddsel-/);
    return m ? m[1] : "";
  }

  function enableLiveUpdate() {
    const root = document.getElementById("aoi-inspection-density-chart-root");
    if (!root) return;

    const triggerSelectOnly = (groupKey) => {
      if (!groupKey) return;
      clearTimeout(_debByGroup[groupKey]);
      _debByGroup[groupKey] = setTimeout(async () => {
        const target = GROUP_TO_TARGET[groupKey];
        const resp = await postTrend({ reason: `filter-change:${groupKey}`, groupKey, target });
        if (!resp) return;

        updateOneGroupMultiDD(groupKey, resp, { selectAll: false, keepSelected: true });
        renderOneChart(resp, target);
      }, 240);
    };

    root.addEventListener("change", (ev) => {
      const t = ev.target;
      if (!t) return;
      if (t.tagName === "SELECT" && t.multiple) {
        const groupKey = parseGroupFromSelectId(t.id || "");
        triggerSelectOnly(groupKey);
      }
    });
  }

  let _inited = false;

  document.addEventListener("aoi_inspection:subtab-chart", async (ev) => {
    const detail = ev?.detail || {};
    const restoreOnly = !!detail.restoreOnly;

    if (!_inited) {
      _inited = true;
      setDateMaxToWorkdayToday();
      setMonthWeekMaxToWorkdayToday();
      setDefaultRangesOnInputs();
      bindButtons();
      enableLiveUpdate();
      window.addEventListener("resize", () => adjustChartHeights());
    }

    if (restoreOnly) {
      resizeAllChartsSoon();
      return;
    }

    _hasFilterSelectedByTarget.summary = false;
    _hasFilterSelectedByTarget.month = false;
    _hasFilterSelectedByTarget.week = false;
    _hasFilterSelectedByTarget.day = false;

    const resp = await postTrend({ reason: "init" });
    if (!resp) return;

    _trendState.lastInitResp = resp;

    buildAllGroupsMultiDD(resp, { selectAll: true });

    ["g0", "g1", "g2", "g3"].forEach((g) => {
      const target = GROUP_TO_TARGET[g];
      const raw = readGroupFilters(g);
      const norm = normalizeGroupFilters(g, raw);
      _hasFilterSelectedByTarget[target] = Object.keys(norm || {}).length > 0;
    });

    renderAllCharts(resp);
    resizeAllChartsSoon();
  });
})();