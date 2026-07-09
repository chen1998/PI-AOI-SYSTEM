// static/js/aoi_density/trend_chart.js
(function () {
  const AOI = (window.AOI_DENSITY = window.AOI_DENSITY || {});
  const API = window.AOI_DENSITY_API;

  const $ = (sel, root = document) => root.querySelector(sel);

  // =========================
  // 0) state
  // =========================
  const _hasFilterSelectedByTarget = {
    summary: false,
    month: false,
    week: false,
    day: false
  };

  const _charts = {};

  const _trendState = {
    lastResp: null,
    lastDateInputs: null,
    lastSelections: null
  };

  // group <-> target mapping
  const GROUP_TO_TARGET = { g0: "summary", g1: "month", g2: "week", g3: "day" };
  const TARGET_TO_CANVAS = {
    summary: "aoi-density-trend-chart-canvas-0",
    month:   "aoi-density-trend-chart-canvas-1",
    week:    "aoi-density-trend-chart-canvas-2",
    day:     "aoi-density-trend-chart-canvas-3"
  };
  const TARGET_TO_TITLE = { summary: "Summary", month: "Month", week: "Week", day: "Day" };

  // =========================
  // 1) date helpers (yesterday as max)
  // =========================
  
  function pad2(n) { return String(n).padStart(2, "0"); }
  function ymd(d){ return `${d.getFullYear()}-${pad2(d.getMonth()+1)}-${pad2(d.getDate())}`; }

  const SHIFT_HOUR = 7;
  const SHIFT_MIN  = 30;

  function nowFloorHour(){
    const d = new Date();
    d.setMinutes(0,0,0);
    return d;
  }

  // ✅ 取得「工作日 label」的日期：label = (now_floor_hour - 07:30).date
  function workdayLabelToday(){
    const d = nowFloorHour();
    d.setHours(d.getHours() - SHIFT_HOUR);
    d.setMinutes(d.getMinutes() - SHIFT_MIN);
    d.setHours(0,0,0,0);
    return d;
  }

  function setDateMaxToWorkdayToday(){
    const max = ymd(workdayLabelToday());
    [
      "aoi-density-trend-chart-g0-dayStart",
      "aoi-density-trend-chart-g0-dayEnd",
      "aoi-density-trend-chart-g3-dayStart",
      "aoi-density-trend-chart-g3-dayEnd"
    ].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.max = max;
    });
  }

  function ymStr(d) { return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}`; }

  function isoWeekString(dateObj) {
    const d = new Date(Date.UTC(dateObj.getFullYear(), dateObj.getMonth(), dateObj.getDate()));
    const dayNum = d.getUTCDay() || 7;
    d.setUTCDate(d.getUTCDate() + 4 - dayNum);
    const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    const weekNo = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
    return `${d.getUTCFullYear()}-W${pad2(weekNo)}`;
  }

  function setMonthWeekMaxToWorkdayToday() {
    const endLabel = workdayLabelToday();     // ✅ 以 07:30 工作日 label 當最大日
    const maxMonth = ymStr(endLabel);         // YYYY-MM
    const maxWeek  = isoWeekString(endLabel); // YYYY-Www
  
    [
      "aoi-density-trend-chart-g0-monthStart",
      "aoi-density-trend-chart-g0-monthEnd",
      "aoi-density-trend-chart-g1-monthStart",
      "aoi-density-trend-chart-g1-monthEnd"
    ].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.max = maxMonth;
    });
  
    [
      "aoi-density-trend-chart-g0-weekStart",
      "aoi-density-trend-chart-g0-weekEnd",
      "aoi-density-trend-chart-g2-weekStart",
      "aoi-density-trend-chart-g2-weekEnd"
    ].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.max = maxWeek;
    });
  }

  // =========================
  // 1.5) default ranges (show on inputs)
  // =========================
  function toMonthInput(d){ return `${d.getFullYear()}-${pad2(d.getMonth()+1)}`; } // YYYY-MM
  function startOfMonth(d){ return new Date(d.getFullYear(), d.getMonth(), 1); }
  function addMonths(d, n){ return new Date(d.getFullYear(), d.getMonth()+n, 1); }

  function startOfISOWeek(d){
    const x = new Date(d);
    const day = x.getDay() || 7; // Mon=1..Sun=7
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
    const endLabel = workdayLabelToday(); // ✅ 以 07:30 工作日 label 當 dayEnd
  
    // summary=6月/9週/6天；others=7月/7週/7天（維持你原本規則）
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
        dayStart: ymd(g0dStart),           dayEnd:  ymd(g0dEnd)
      },
      g1: { monthStart: toMonthInput(g1mStart), monthEnd: toMonthInput(g1mEnd) },
      g2: { weekStart: isoWeekString(g2wStart), weekEnd: isoWeekString(g2wEnd) },
      g3: { dayStart: ymd(g3dStart), dayEnd: ymd(g3dEnd) }
    };
  }

  function setDefaultRangesOnInputs(){
    const d = computeDefaultRanges();

    // g0
    $("#aoi-density-trend-chart-g0-monthStart").value = d.g0.monthStart;
    $("#aoi-density-trend-chart-g0-monthEnd").value   = d.g0.monthEnd;
    $("#aoi-density-trend-chart-g0-weekStart").value  = d.g0.weekStart;
    $("#aoi-density-trend-chart-g0-weekEnd").value    = d.g0.weekEnd;
    $("#aoi-density-trend-chart-g0-dayStart").value   = d.g0.dayStart;
    $("#aoi-density-trend-chart-g0-dayEnd").value     = d.g0.dayEnd;

    // g1
    $("#aoi-density-trend-chart-g1-monthStart").value = d.g1.monthStart;
    $("#aoi-density-trend-chart-g1-monthEnd").value   = d.g1.monthEnd;

    // g2
    $("#aoi-density-trend-chart-g2-weekStart").value  = d.g2.weekStart;
    $("#aoi-density-trend-chart-g2-weekEnd").value    = d.g2.weekEnd;

    // g3
    $("#aoi-density-trend-chart-g3-dayStart").value   = d.g3.dayStart;
    $("#aoi-density-trend-chart-g3-dayEnd").value     = d.g3.dayEnd;
  }

  function setDefaultRangesForGroup(groupKey){
    const d = computeDefaultRanges()[groupKey];
    if (!d) return;

    if (groupKey === "g0") {
      $("#aoi-density-trend-chart-g0-monthStart").value = d.monthStart;
      $("#aoi-density-trend-chart-g0-monthEnd").value   = d.monthEnd;
      $("#aoi-density-trend-chart-g0-weekStart").value  = d.weekStart;
      $("#aoi-density-trend-chart-g0-weekEnd").value    = d.weekEnd;
      $("#aoi-density-trend-chart-g0-dayStart").value   = d.dayStart;
      $("#aoi-density-trend-chart-g0-dayEnd").value     = d.dayEnd;
    }
    if (groupKey === "g1") {
      $("#aoi-density-trend-chart-g1-monthStart").value = d.monthStart;
      $("#aoi-density-trend-chart-g1-monthEnd").value   = d.monthEnd;
    }
    if (groupKey === "g2") {
      $("#aoi-density-trend-chart-g2-weekStart").value  = d.weekStart;
      $("#aoi-density-trend-chart-g2-weekEnd").value    = d.weekEnd;
    }
    if (groupKey === "g3") {
      $("#aoi-density-trend-chart-g3-dayStart").value   = d.dayStart;
      $("#aoi-density-trend-chart-g3-dayEnd").value     = d.dayEnd;
    }
  }

  // =========================
  // 2) Convert UI inputs -> backend tokens
  // =========================
  function monthInputToYYYYMM(v) {
    if (!v || typeof v !== "string") return "";
    const s = v.replace("-", "").trim(); // YYYYMM
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

  // =========================
  // 3) MultiDD builders (per group)
  // =========================
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
    const hostId = `aoi-density-trend-chart-${groupKey}-mddhost-${key}`;
    const selectId = `aoi-density-trend-chart-${groupKey}-mddsel-${key}`;

    const host = document.getElementById(hostId);
    if (!host) return null;

    const opts = Array.isArray(options) ? options : [];
    _mddAllOptions[groupKey][key] = opts;
    
    if (_mdd[groupKey] && _mdd[groupKey][key]) {
      _mdd[groupKey][key].updateOptions(opts);
      return _mdd[groupKey][key];
    }
    

    

    const inst = new AOI.MultiDD({
      hostId,
      selectId,
      options: opts,
      title: key,
      onChange
    });

    _mdd[groupKey][key] = inst;
    return inst;
  }

  function buildDynFiltersAsMultiDD(groupKey, hostEl, filterOptionDict, onAnyChange) {
    if (!hostEl) return;
  
    const keys = Object.keys(filterOptionDict || {});
  
    // ✅ 第一次才建 DOM；之後只 update options
    if (hostEl.dataset.inited === "1") {
      keys.forEach((k) => {
        // options 永遠更新
        ensureMultiDD(groupKey, k, filterOptionDict[k] || [], onAnyChange);
      });
      return;
    }
  
    hostEl.dataset.inited = "1";
    hostEl.innerHTML = ""; // ✅ 只允許第一次清
  
    keys.forEach((k) => {
      const slot = document.createElement("div");
      slot.className = "aoi-mdd-host";
      slot.id = `aoi-density-trend-chart-${groupKey}-mddhost-${k}`;
      hostEl.appendChild(slot);
  
      ensureMultiDD(groupKey, k, filterOptionDict[k] || [], onAnyChange);
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

  function snapshotDateInputs() {
    return {
      g0: {
        monthStart: v("aoi-density-trend-chart-g0-monthStart"),
        monthEnd:   v("aoi-density-trend-chart-g0-monthEnd"),
        weekStart:  v("aoi-density-trend-chart-g0-weekStart"),
        weekEnd:    v("aoi-density-trend-chart-g0-weekEnd"),
        dayStart:   v("aoi-density-trend-chart-g0-dayStart"),
        dayEnd:     v("aoi-density-trend-chart-g0-dayEnd")
      },
      g1: {
        monthStart: v("aoi-density-trend-chart-g1-monthStart"),
        monthEnd:   v("aoi-density-trend-chart-g1-monthEnd")
      },
      g2: {
        weekStart:  v("aoi-density-trend-chart-g2-weekStart"),
        weekEnd:    v("aoi-density-trend-chart-g2-weekEnd")
      },
      g3: {
        dayStart:   v("aoi-density-trend-chart-g3-dayStart"),
        dayEnd:     v("aoi-density-trend-chart-g3-dayEnd")
      }
    };
  }
  
  
  function restoreDateInputs(snapshot) {
    if (!snapshot) return;
  
    const setVal = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.value = val || "";
    };
  
    setVal("aoi-density-trend-chart-g0-monthStart", snapshot?.g0?.monthStart);
    setVal("aoi-density-trend-chart-g0-monthEnd",   snapshot?.g0?.monthEnd);
    setVal("aoi-density-trend-chart-g0-weekStart",  snapshot?.g0?.weekStart);
    setVal("aoi-density-trend-chart-g0-weekEnd",    snapshot?.g0?.weekEnd);
    setVal("aoi-density-trend-chart-g0-dayStart",   snapshot?.g0?.dayStart);
    setVal("aoi-density-trend-chart-g0-dayEnd",     snapshot?.g0?.dayEnd);
  
    setVal("aoi-density-trend-chart-g1-monthStart", snapshot?.g1?.monthStart);
    setVal("aoi-density-trend-chart-g1-monthEnd",   snapshot?.g1?.monthEnd);
  
    setVal("aoi-density-trend-chart-g2-weekStart",  snapshot?.g2?.weekStart);
    setVal("aoi-density-trend-chart-g2-weekEnd",    snapshot?.g2?.weekEnd);
  
    setVal("aoi-density-trend-chart-g3-dayStart",   snapshot?.g3?.dayStart);
    setVal("aoi-density-trend-chart-g3-dayEnd",     snapshot?.g3?.dayEnd);
  }
  
  
  
  function snapshotSelections() {
    return {
      g0: readGroupFilters("g0"),
      g1: readGroupFilters("g1"),
      g2: readGroupFilters("g2"),
      g3: readGroupFilters("g3")
    };
  }
  
  
  
  function restoreSelections(snapshot) {
    if (!snapshot) return;
  
    ["g0", "g1", "g2", "g3"].forEach((g) => {
      const bucket = _mdd[g] || {};
      const sel = snapshot[g] || {};
  
      Object.keys(bucket).forEach((k) => {
        const inst = bucket[k];
        if (!inst) return;
  
        const want = Array.isArray(sel[k]) ? sel[k] : [];
        if (want.length) {
          inst.setSelected(want.slice());
        } else {
          const opts = _mddAllOptions?.[g]?.[k] || [];
          _selectAllOnInst(inst, opts);
        }
      });
    });
  }
  
  
  function persistTrendState(resp) {
    if (resp) {
      const prev = _trendState.lastResp || {};
      const prevTrend = prev?.TrendDict || {};
      const nextTrend = resp?.TrendDict || {};
  
      _trendState.lastResp = {
        ...prev,
        ...resp,
        TrendDict: {
          summary: nextTrend.summary ?? prevTrend.summary ?? { points: [] },
          month:   nextTrend.month   ?? prevTrend.month   ?? { points: [] },
          week:    nextTrend.week    ?? prevTrend.week    ?? { points: [] },
          day:     nextTrend.day     ?? prevTrend.day     ?? { points: [] }
        },
        ParamDict: resp?.ParamDict ?? prev?.ParamDict ?? null,
        Meta: {
          ...(prev?.Meta || {}),
          ...(resp?.Meta || {})
        }
      };
    }
  
    _trendState.lastDateInputs = snapshotDateInputs();
    _trendState.lastSelections = snapshotSelections();
  
    ["g0", "g1", "g2", "g3"].forEach((g) => {
      const target = GROUP_TO_TARGET[g];
      const norm = normalizeGroupFilters(g, _trendState.lastSelections[g] || {});
      _hasFilterSelectedByTarget[target] = Object.keys(norm || {}).length > 0;
    });
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
      if (allLen > 0 && arr.length >= allLen) return; // 全選 => 不送

      out[k] = arr;
    });

    return out;
  }

  // =========================
  // 4) Build date_dict (target-only)
  // =========================
  function v(id) { return document.getElementById(id)?.value || ""; }

  function buildDateDictForTarget(target) {
    if (target === "summary") {
      const out = { summary: { month: [], week: [], day: [] } };

      const ms = monthInputToYYYYMM(v("aoi-density-trend-chart-g0-monthStart"));
      const me = monthInputToYYYYMM(v("aoi-density-trend-chart-g0-monthEnd"));
      if (ms && me) out.summary.month = [ms, me];

      const ws = weekInputToWYYWW(v("aoi-density-trend-chart-g0-weekStart"));
      const we = weekInputToWYYWW(v("aoi-density-trend-chart-g0-weekEnd"));
      if (ws && we) out.summary.week = [ws, we];

      const ds = v("aoi-density-trend-chart-g0-dayStart");
      const de = v("aoi-density-trend-chart-g0-dayEnd");
      if (ds && de) out.summary.day = [ds, de];

      return out;
    }

    if (target === "month") {
      const out = { month: [] };
      const ms = monthInputToYYYYMM(v("aoi-density-trend-chart-g1-monthStart"));
      const me = monthInputToYYYYMM(v("aoi-density-trend-chart-g1-monthEnd"));
      if (ms && me) out.month = [ms, me];
      return out;
    }

    if (target === "week") {
      const out = { week: [] };
      const ws = weekInputToWYYWW(v("aoi-density-trend-chart-g2-weekStart"));
      const we = weekInputToWYYWW(v("aoi-density-trend-chart-g2-weekEnd"));
      if (ws && we) out.week = [ws, we];
      return out;
    }

    if (target === "day") {
      const out = { day: [] };
      const ds = v("aoi-density-trend-chart-g3-dayStart");
      const de = v("aoi-density-trend-chart-g3-dayEnd");
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
        "aoi-density-trend-chart-g0-monthStart",
        "aoi-density-trend-chart-g0-monthEnd",
        "aoi-density-trend-chart-g0-weekStart",
        "aoi-density-trend-chart-g0-weekEnd",
        "aoi-density-trend-chart-g0-dayStart",
        "aoi-density-trend-chart-g0-dayEnd"
      ].forEach(id => { const el = document.getElementById(id); if (el) el.value = ""; });
    }
    if (groupKey === "g1") {
      [
        "aoi-density-trend-chart-g1-monthStart",
        "aoi-density-trend-chart-g1-monthEnd"
      ].forEach(id => { const el = document.getElementById(id); if (el) el.value = ""; });
    }
    if (groupKey === "g2") {
      [
        "aoi-density-trend-chart-g2-weekStart",
        "aoi-density-trend-chart-g2-weekEnd"
      ].forEach(id => { const el = document.getElementById(id); if (el) el.value = ""; });
    }
    if (groupKey === "g3") {
      [
        "aoi-density-trend-chart-g3-dayStart",
        "aoi-density-trend-chart-g3-dayEnd"
      ].forEach(id => { const el = document.getElementById(id); if (el) el.value = ""; });
    }
  }

  // =========================
  // 5) API call + debug (target-only)
  // =========================
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

    //  這行是關鍵：告訴後端這次只算哪個 bucket（init 不帶）
    const payload = isInit
      ? { date_dict, filters }
      : { target, date_dict, filters };

    console.debug("[AOI_TREND] request reason=", reason, "target=", target || "(init)", payload);

    const resp = await API.postTrend(payload);

    try {
      const td = resp?.TrendDict || {};
      const meta = resp?.Meta || {};
      console.debug("[AOI_TREND] response meta=", meta, {
        summary_points: td?.summary?.points?.length || 0,
        month_points:   td?.month?.points?.length   || 0,
        week_points:    td?.week?.points?.length    || 0,
        day_points:     td?.day?.points?.length     || 0,
      });
    } catch (e) {
      console.debug("[AOI_TREND] response parse error", e);
    }

    return resp;
    
  }

  // =========================
  // 6) Charts: size + init + render
  // =========================
  function adjustChartHeights() {
    ["aoi-density-trend-chart-canvas-0",
     "aoi-density-trend-chart-canvas-1",
     "aoi-density-trend-chart-canvas-2",
     "aoi-density-trend-chart-canvas-3"
    ].forEach(id => {
      const ins = _charts[id];
      if (ins && typeof ins.resize === "function") ins.resize();
    });
  }

  function ensureChart(domId) {
    const el = document.getElementById(domId);
    if (!el) return null;
    if (!window.echarts) return null;
    /*
    const parent = el.parentElement;
    const ph = parent ? parent.clientHeight : 0;
    if (ph > 0) el.style.height = Math.floor(ph * 0.9) + "px";
    else el.style.height = "90%";
    */
    if (_charts[domId]) return _charts[domId];
    _charts[domId] = window.echarts.init(el);
    return _charts[domId];
  }

  function renderChart(domId, points, title, hasFilterSelected) {
    const el = document.getElementById(domId);
    if (!el) return;
  
    const pts = Array.isArray(points) ? points : [];
    const xs  = pts.map(p => p.x_label || p.x || "");
  
    // =========
    // 取值（保留 null）
    // =========
    const n = (v) => (v === null || v === undefined || v === "" ? null : Number(v));
    const totalGlass = pts.map(p => n(p.glass_cnt));
    const totalDef   = pts.map(p => n(p.defect_cnt));
    const totalDen   = pts.map(p => n(p.density));
  
    // select：後端已保證欄位存在
    const selTotalGlass = pts.map(p => n(p.select_total_glass_cnt));
    const selDefGlass   = pts.map(p => n(p.select_def_glass_cnt));
    const selDefCnt     = pts.map(p => n(p.select_def_cnt));
  
    // ✅ SelectGlass 這組 legend 用來代表 select_def_glass_cnt
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
  
    // =========
    // format
    // =========
    const fmtInt = (v) => {
      const x = Number(v);
      if (!Number.isFinite(x)) return "-";
      return Math.round(x).toLocaleString();
    };
    const fmtPct = (v) => {
      const n = Number(v);
      if (!Number.isFinite(n)) return "-";
      return (n).toFixed(2);
    };
    
    const fmtPctLabel = (v) => {
      const x = Number(v);
      if (!Number.isFinite(x)) return "";
      return x.toFixed(2);
    };
  
    // =========
    // tooltip：TOTAL + SELECT + (summary 額外 segment)
    // =========
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
  
      if (domId === "aoi-density-trend-chart-canvas-0" && p.segment) {
        html += `<div style="margin-top:6px;opacity:.75;">segment: ${p.segment}</div>`;
      }
      return `<div style="line-height:1.4;">${html}</div>`;
    };
  
    // =========================
    // ✅ Segment Colors（你指定）
    // =========================
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
      week:   hexToRgba(COLOR_WEEK,  0.45),
      day:    hexToRgba(COLOR_DAY,   0.45),
      single: hexToRgba(COLOR_SINGLE,0.35)
    };
  
    // =========
    // legend 名稱固定（綁 5 組）
    // =========
    const L = {
      TotalDensity: "TotalDensity",
      TotalGlass: "TotalGlass",
      SelectTotalGlass: "SelectTotalGlass",
      SelectGlass: "SelectGlass",
      SelectDensity: "SelectDensity",
    };
  
    // =========
    // summary：同 name + 用 null mask 分段（維持 legend=5）
    // =========
    const isSummary = (domId === "aoi-density-trend-chart-canvas-0");
  
    const maskBySeg = (arr, seg) =>
      pts.map((p, i) => (p.segment === seg ? arr[i] : null));
  
    const segs = isSummary ? ["month","week","day"] : ["single"];
  
    // =========================
    // ✅ xAxis label 分 group 上色（只在 summary）
    // =========================
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
      if (seg === "week")  return `{w|${value}}`;
      if (seg === "day")   return `{d|${value}}`;
      return `{n|${value}}`;
    }
  
    // =========
    // series
    // =========
    const series = [];
  
    // --- bars：total glass（summary 分色 / 非 summary single 色）
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
  
    // --- bars：select_total（深紫固定，不分 group）
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
  
    // --- bars：select_def_glass_cnt（summary 分色 / 非 summary single 色）
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
  
    // --- line：total density（固定灰白虛線）
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
          textBorderWidth: 0,          // 關掉描邊
          textBorderColor: "transparent",
          textShadowBlur: 0,           // 保險：避免陰影看起來像外框
          textShadowColor: "transparent"
          
        },
        z: 10,
        emphasis: { focus: "series" }
      });
    });
  
    // --- line：select density（summary 分色 / 非 summary single 色）
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
      
        // 顯示數值 label（小數點後兩位）在點正上方
        label: {
          show: true,
          position: "top",
          distance: 6,
          formatter: (p) => fmtPctLabel(p.value),
          color: "#ffffff",
          textBorderWidth: 0,          // 關掉描邊
          textBorderColor: "transparent",
          textShadowBlur: 0,           // 保險：避免陰影看起來像外框
          textShadowColor: "transparent"
        }
      });
      
    });
  
    // =========
    // legend 預設顯示規則（你原本規則）
    // - 預設只顯示：SelectTotalGlass(bar) + SelectDensity(line)
    // =========
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
    renderChart(TARGET_TO_CANVAS.summary, td?.summary?.points, TARGET_TO_TITLE.summary, !!_hasFilterSelectedByTarget.summary);
    renderChart(TARGET_TO_CANVAS.month,   td?.month?.points,   TARGET_TO_TITLE.month,   !!_hasFilterSelectedByTarget.month);
    renderChart(TARGET_TO_CANVAS.week,    td?.week?.points,    TARGET_TO_TITLE.week,    !!_hasFilterSelectedByTarget.week);
    renderChart(TARGET_TO_CANVAS.day,     td?.day?.points,     TARGET_TO_TITLE.day,     !!_hasFilterSelectedByTarget.day);
    adjustChartHeights();
  }

  function renderOneChart(resp, target) {
    const td = resp?.TrendDict || {};
    const canvasId = TARGET_TO_CANVAS[target];
    if (!canvasId) return;
  
    const pts = td?.[target]?.points;
    renderChart(canvasId, pts, TARGET_TO_TITLE[target], !!_hasFilterSelectedByTarget[target]);
    adjustChartHeights();
  }

  // =========================
  // 7) Build UI from filterOptionDict
  // =========================
  function getFilterOptionDict(resp) {
    return resp?.ParamDict?.filterOptionDict || resp?.filterOptionDict || {};
  }

  function buildAllGroupsMultiDD(resp, { selectAll = false, applyDefaults = true } = {}) {
    const fod = getFilterOptionDict(resp);
    const onAnyChange = () => {};
  
    // 1) 先建四組 MultiDD（不急著 selectAll）
    buildDynFiltersAsMultiDD("g0", $("#aoi-density-trend-chart-dynhosts-g0"), fod, onAnyChange);
    buildDynFiltersAsMultiDD("g1", $("#aoi-density-trend-chart-dynhosts-g1"), fod, onAnyChange);
    buildDynFiltersAsMultiDD("g2", $("#aoi-density-trend-chart-dynhosts-g2"), fod, onAnyChange);
    buildDynFiltersAsMultiDD("g3", $("#aoi-density-trend-chart-dynhosts-g3"), fod, onAnyChange);
  
    // 2) 後端可下發 init 預設勾選
    const defaults = resp?.ParamDict?.defaultTrendFilters || null;
  
    // helper：在某 group 套 defaults（不 dispatch change，避免多打一輪 /trend）
    function applyDefaultsToGroup(groupKey, defaultDict) {
      if (!defaultDict || typeof defaultDict !== "object") return;
  
      // 先全選全部 key（確保其他 key 保持全選）
      setGroupFiltersSelectAll(groupKey);
  
      // 再把 defaultDict 覆蓋指定 key
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
  
    // 3) 若後端有 defaultTrendFilters：用它當 init 預設
    if (applyDefaults && defaults && typeof defaults === "object" && Object.keys(defaults).length) {
      applyDefaultsToGroup("g0", defaults);
      applyDefaultsToGroup("g1", defaults);
      applyDefaultsToGroup("g2", defaults);
      applyDefaultsToGroup("g3", defaults);
  
      // ✅ 回傳 defaults，讓外層知道「init 就有選擇」
      return defaults;
    }
  
    // 4) fallback：原本全選邏輯
    if (selectAll) {
      setGroupFiltersSelectAll("g0");
      setGroupFiltersSelectAll("g1");
      setGroupFiltersSelectAll("g2");
      setGroupFiltersSelectAll("g3");
    }
  
    return null;
  }
  

  // =========================
  // 8) Buttons (group-only)
  // =========================
  function bindButtons() {
    const groups = ["g0","g1","g2","g3"];
    groups.forEach(g => {
      const target = GROUP_TO_TARGET[g];
      const applyBtn = document.getElementById(`aoi-density-trend-chart-${g}-apply`);
      const clearBtn = document.getElementById(`aoi-density-trend-chart-${g}-clear`);

      if (applyBtn) {
        applyBtn.addEventListener("click", async () => {
          const resp = await postTrend({ reason: `apply:${g}`, groupKey: g, target });
          if (!resp) return;
          persistTrendState(resp);
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

          setGroupFiltersSelectAll(g);
          persistTrendState(resp);
          renderOneChart(resp, target);
        });
      }
    });
  }

  // =========================
  // 9) Live update (select-only, group-only)
  // =========================
  const _debByGroup = { g0: null, g1: null, g2: null, g3: null };

  function parseGroupFromSelectId(id) {
    if (!id || typeof id !== "string") return "";
    const m = id.match(/^aoi-density-trend-chart-(g[0-3])-mddsel-/);
    return m ? m[1] : "";
  }

  function enableLiveUpdate() {
    const root = document.getElementById("aoi-density-trend-chart-root");
    if (!root) return;

    const triggerSelectOnly = (groupKey) => {
      if (!groupKey) return;
      clearTimeout(_debByGroup[groupKey]);
      _debByGroup[groupKey] = setTimeout(async () => {
        const target = GROUP_TO_TARGET[groupKey];
        const resp = await postTrend({ reason: `filter-change:${groupKey}`, groupKey, target });
        if (resp) {
          persistTrendState(resp);
          renderOneChart(resp, target);
        }
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

  // =========================
  // 10) subtab-chart event
  // =========================
  let _inited = false;

  document.addEventListener("aoi-density:subtab-chart", async (ev) => {
    const detail = ev.detail || {};
    const { trend, restoreOnly } = detail;
  
    if (!_inited) {
      _inited = true;
      setDateMaxToWorkdayToday();
      setMonthWeekMaxToWorkdayToday();
      setDefaultRangesOnInputs();
      bindButtons();
      enableLiveUpdate();
      window.addEventListener("resize", () => adjustChartHeights());
    }
  
    // restore：不要重打 API、不要重套 defaults
    if (restoreOnly) {
      restoreDateInputs(_trendState.lastDateInputs);
  
      if (_trendState.lastResp) {
        buildAllGroupsMultiDD(_trendState.lastResp, {
          selectAll: false,
          applyDefaults: false
        });
        restoreSelections(_trendState.lastSelections);
        renderAllCharts(_trendState.lastResp);
  
        requestAnimationFrame(() => {
          requestAnimationFrame(() => adjustChartHeights());
        });
      }
      return;
    }
  
    _hasFilterSelectedByTarget.summary = false;
    _hasFilterSelectedByTarget.month   = false;
    _hasFilterSelectedByTarget.week    = false;
    _hasFilterSelectedByTarget.day     = false;
  
    const resp = trend || await postTrend({ reason: "init" });
    if (!resp) return;
  
    buildAllGroupsMultiDD(resp, { selectAll: true, applyDefaults: true });
  
    ["g0", "g1", "g2", "g3"].forEach((g) => {
      const target = GROUP_TO_TARGET[g];
      const raw = readGroupFilters(g);
      const norm = normalizeGroupFilters(g, raw);
      _hasFilterSelectedByTarget[target] = Object.keys(norm || {}).length > 0;
    });
  
    persistTrendState(resp);
    renderAllCharts(resp);
  
    requestAnimationFrame(() => {
      requestAnimationFrame(() => adjustChartHeights());
    });
  });
})();

    