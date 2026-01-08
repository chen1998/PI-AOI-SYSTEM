// static/js/aoi_capa/api.js
(function () {
  const AOI = (window.AOI_CAPA = window.AOI_CAPA || {});
  AOI.API = AOI.API || {};

  const BASE = window.API_BASE || "";  // 你 HTML 裡有設 window.API_BASE

  /**
   * 呼叫 /aoi_capa/api/reset_summary_filter
   * @param {string[] | null} dates - 例如 ['2025-11-01','2025-11-07']
   */
  AOI.API.fetchSummary = async function (dates) {
    const params = new URLSearchParams();
    if (Array.isArray(dates) && dates.length === 2) {
      if (dates[0]) params.append("dates", dates[0]);
      if (dates[1]) params.append("dates", dates[1]);
    }
    const url = `${BASE}/aoi_capa/api/reset_summary_filter` +
      (params.toString() ? `?${params.toString()}` : "");

    const resp = await fetch(url);
    if (!resp.ok) {
      const txt = await resp.text();
      throw new Error(`fetchSummary failed: ${resp.status} ${txt}`);
    }
    return resp.json();
  };

  /**
   * 呼叫 /aoi_capa/api/hourly_rawdata_filter
   * @param {{aoi: string, pi_type?: string|null, run_day: string}} ask
   */
  AOI.API.fetchHourly = async function (ask) {
    const payload = {
      aoi: ask.aoi,
      pi_type: ask.pi_type ?? null,
      run_day: ask.run_day,
    };
    const params = new URLSearchParams();
    params.set("filter_ask_keys", JSON.stringify(payload));
    const url = `${BASE}/aoi_capa/api/hourly_rawdata_filter?${params.toString()}`;

    const resp = await fetch(url);
    if (!resp.ok) {
      const txt = await resp.text();
      throw new Error(`fetchHourly failed: ${resp.status} ${txt}`);
    }
    return resp.json();
  };


  AOI.API.saveCapaConfig = async function (payload) {
    const url = `${BASE}/aoi_capa/api/save_config`;

    const resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload || {}),
    });

    if (!resp.ok) {
      const txt = await resp.text();
      throw new Error(`saveCapaConfig failed: ${resp.status} ${txt}`);
    }
    return resp.json();
  };
})();
