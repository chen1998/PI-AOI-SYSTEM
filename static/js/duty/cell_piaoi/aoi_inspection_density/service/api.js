// static/js/aoi_inspection_density/service/api.js
(function () {
  const NS = (window.AOI_INSPECTION_API = window.AOI_INSPECTION_API || {});

  // =========================
  // inflight lock
  // =========================
  const inflight = new Set();

  function buildLockKey(method, url, body) {
    return `${method}|${url}|${body ? JSON.stringify(body) : ""}`;
  }

  async function withLock(method, url, body, fn, ttlMs = 300) {
    const key = buildLockKey(method, url, body);
    if (inflight.has(key)) return null;

    inflight.add(key);
    try {
      return await fn();
    } finally {
      setTimeout(() => inflight.delete(key), ttlMs);
    }
  }

  // =========================
  // utils
  // =========================
  function toQuery(params) {
    const usp = new URLSearchParams();
    if (!params || typeof params !== "object") return "";

    Object.entries(params).forEach(([k, v]) => {
      if (v == null) return;

      if (Array.isArray(v)) {
        v.forEach((vv) => usp.append(k, String(vv)));
      } else {
        usp.set(k, String(v));
      }
    });

    return usp.toString();
  }

  async function rawGet(url, params) {
    const qs = toQuery(params);
    const full = qs ? `${url}?${qs}` : url;

    const res = await fetch(full, { method: "GET" });
    if (!res.ok) {
      let text = "";
      try {
        text = await res.text();
      } catch (_) {}
      throw new Error(`${full} 失敗 (${res.status}) ${text || res.statusText}`);
    }
    return res.json();
  }

  async function rawPost(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    });

    if (!res.ok) {
      let text = "";
      try {
        text = await res.text();
      } catch (_) {}
      throw new Error(`${url} 失敗 (${res.status}) ${text || res.statusText}`);
    }
    return res.json();
  }

  async function get(url, params) {
    const qs = toQuery(params);
    const full = qs ? `${url}?${qs}` : url;
    return withLock("GET", full, null, () => rawGet(full), 200);
  }

  async function post(url, body) {
    return withLock("POST", url, body, () => rawPost(url, body), 300);
  }

  // =========================
  // route helpers
  // =========================
  function inspectionBase(path = "") {
    return `${window.API_BASE}/aoi_inspection_density${path}`;
  }

  function commonBase(path = "") {
    return `${window.API_BASE}/common${path}`;
  }

  // =========================
  // inspection routes
  // =========================
  async function resetSummaryFilter(params) {
    return get(inspectionBase("/reset_summary_filter"), params);
  }

  async function postDefectMap(rows) {
    if (!Array.isArray(rows) || !rows.length) {
      return { DefectGroupDict: {} };
    }
    console.log('click defect group', rows);
    const url = inspectionBase("/defect_map");
    const body = { rows };
    const r = await withLock("POST", url, body, () => rawPost(url, body), 300);
    return r || { DefectGroupDict: {} };
  }

  async function getInspectionTrend(payload) {
    const url = inspectionBase("/trend");
    const body = payload || {};
    const r = await withLock("POST", url, body, () => rawPost(url, body), 300);
    return r || {};
  }

  // =========================
  // common routes
  // =========================
  async function ActionHisEditor(payload) {
    const url = `${window.API_BASE}/common/editor_summary`;
    return post(url, payload);
  }

  async function CommentEditor(payload) {
    //console.log('density payload', payload);
    const url = `${window.API_BASE}/common/edit_table`;
    return post(url, payload);
  }
  async function specEditor(payload) {
    const url = commonBase("/spec_editor");
    const body = payload || {};
    return post(url, body);
  }

  // =========================
  // expose
  // =========================
  NS.get = get;
  NS.post = post;

  NS.resetSummaryFilter = resetSummaryFilter;
  NS.postDefectMap = postDefectMap;
  NS.getInspectionTrend = getInspectionTrend;

  NS.ActionHisEditor= ActionHisEditor;
  NS.CommentEditor = CommentEditor;
  NS.specEditor = specEditor;
})();