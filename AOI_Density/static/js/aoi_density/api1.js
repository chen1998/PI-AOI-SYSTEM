// static/js/aoi_density/api.js
(function () {
  if (window.API) return;

  // ===== 內部：短時間防重複請求（同 method+url+body 視為重複） =====
  const _inflight = new Set();
  function _key(method, url, body) {
    return method + "|" + url + "|" + (body ? JSON.stringify(body) : "");
  }
  async function _withLock(method, url, body, fn, ttlMs = 300) {
    const k = _key(method, url, body);
    if (_inflight.has(k)) {
      // 已有相同請求在進行，直接略過（回傳 null 代表沒打）
      return null;
    }
    _inflight.add(k);
    try {
      return await fn();
    } finally {
      setTimeout(() => _inflight.delete(k), ttlMs);
    }
  }

  function toQuery(params) {
    const usp = new URLSearchParams();
    if (!params) return usp.toString();
    Object.keys(params).forEach((k) => {
      const v = params[k];
      if (v == null) return;
      if (Array.isArray(v)) {
        v.forEach((vv) => usp.append(k, String(vv)));
      } else {
        usp.set(k, String(v));
      }
    });
    return usp.toString();
  }

  async function _rawGet(url, params) {
    const qs = toQuery(params);
    const full = qs ? `${url}?${qs}` : url;
    const res = await fetch(full, { method: "GET" });
    if (!res.ok) {
      let text;
      try { text = await res.text(); } catch (e) { text = res.statusText; }
      throw new Error(`${url} 失敗 (${res.status}) ${text || ""}`);
    }
    return res.json();
  }

  async function _rawPost(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    });
    if (!res.ok) {
      let text;
      try { text = await res.text(); } catch (e) { text = res.statusText; }
      throw new Error(`${url} 失敗 (${res.status}) ${text || ""}`);
    }
    return res.json();
  }

  // ===== 對外：維持原本 window.API.get/post 行為 =====
  /*async function get(url, params) {
    return _withLock("GET", url, null, () => _rawGet(url, params), 200); // GET 也給一點點鎖
  }*/
  async function get(url, params) {
    console.log('params',params);
    const qs = toQuery(params);
    const full = qs ? `${url}?${qs}` : url;
    return _withLock("GET", full, null, () => _rawGet(url, params), 200);
  }
      
  async function post(url, body) {
    return _withLock("POST", url, body, () => _rawPost(url, body), 250);
  }

  // ===== 對外：保留你的初始化 API（別名，方便直接呼叫） =====
  async function resetSummaryFilter(params) {
    // 你原本 service.js 會呼叫：/aoi_density/api/reset_summary_filter
    return get(`${window.API_BASE}/aoi_density/api/reset_summary_filter`, params);
  }

  // ===== 對外：defect_map 封裝，只在 chart 的 series click 用 =====
  async function postDefectMap(rows) {
    if (!Array.isArray(rows) || !rows.length) return { DefectGroupDict: [] };
    const url = `${window.API_BASE}/aoi_density/api/defect_map`;
    const body = { rows };
    // 與上方 post 相同，但再加一層鎖，避免連點同一顆點瘋狂送
    const r = await _withLock("POST", url, body, () => _rawPost(url, body), 300);
    return r || { DefectGroupDict: [] }; // 若被視為重複，回傳空結構，不影響前端流程
  }

  window.API = { get, post, resetSummaryFilter, postDefectMap };
})();
