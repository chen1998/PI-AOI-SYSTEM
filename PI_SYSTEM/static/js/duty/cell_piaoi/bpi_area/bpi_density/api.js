// static/js/bpi_area/bpi_density/api.js
// BPI Density API wrapper
//
// 注意：
// - 這支只服務「原 BPI Density」功能。
// - BPI/API Same Point 請使用 static/js/bpi_area/bpi_same_point/api.js。
// - 共用 editor / spec editor 仍透過 /common/*。

(function () {
  const _inflight = new Set();

  function _key(method, url, body) {
    return method + "|" + url + "|" + (body ? JSON.stringify(body) : "");
  }

  async function _withLock(method, url, body, fn, ttlMs = 300) {
    const k = _key(method, url, body);

    if (_inflight.has(k)) {
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

    const res = await fetch(full, {
      method: "GET"
    });

    if (!res.ok) {
      let text = "";

      try {
        text = await res.text();
      } catch (_e) {
        text = res.statusText;
      }

      throw new Error(`${url} 失敗 (${res.status}) ${text || ""}`);
    }

    return res.json();
  }

  async function _rawPost(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(body || {})
    });

    if (!res.ok) {
      let text = "";

      try {
        text = await res.text();
      } catch (_e) {
        text = res.statusText;
      }

      throw new Error(`${url} 失敗 (${res.status}) ${text || ""}`);
    }

    return res.json();
  }

  async function get(url, params) {
    const qs = toQuery(params);
    const full = qs ? `${url}?${qs}` : url;

    return _withLock(
      "GET",
      full,
      null,
      () => _rawGet(url, params),
      200
    );
  }

  async function post(url, body) {
    return _withLock(
      "POST",
      url,
      body,
      () => _rawPost(url, body),
      250
    );
  }

  // ============================================================
  // BPI Density main data
  // ============================================================
  async function resetSummaryFilter(params) {
    return get(
      `${window.API_BASE}/bpi_density/reset_summary_filter`,
      params
    );
  }

  // ============================================================
  // BPI Density trend
  // ============================================================
  async function postTrend(body) {
    return post(
      `${window.API_BASE}/bpi_density/trend`,
      body
    );
  }

  // ============================================================
  // BPI Density defect map
  // ============================================================
  async function postCstDefectMap(rows) {
    if (!Array.isArray(rows) || !rows.length) {
      return { DefectGroupDict: {} };
    }

    const url = `${window.API_BASE}/bpi_density/cst_defect_map`;
    const body = { rows };

    const resp = await _withLock(
      "POST",
      url,
      body,
      () => _rawPost(url, body),
      300
    );

    return resp || { DefectGroupDict: {} };
  }

  // ============================================================
  // Common editors
  // ============================================================
  async function CommentEditor(payload) {
    return post(
      `${window.API_BASE}/common/edit_table`,
      payload
    );
  }

  async function FrontSpecEditor(payload) {
    return post(
      `${window.API_BASE}/common/spec_editor`,
      payload
    );
  }

  async function ActionHisEditor(payload) {
    return post(
      `${window.API_BASE}/common/editor_summary`,
      payload
    );
  }

  window.AOI_BPI_DENSITY_API = {
    get,
    post,

    resetSummaryFilter,
    postTrend,
    postCstDefectMap,

    CommentEditor,
    ActionHisEditor,
    FrontSpecEditor
  };
})();
