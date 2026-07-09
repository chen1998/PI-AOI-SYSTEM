// static/js/aoi_capa/api.js
(function () {
  const AOI = (window.AOI_CAPA = window.AOI_CAPA || {});
  AOI.API = AOI.API || {};

  const BASE = String(window.API_BASE || "").replace(/\/+$/, "");

  function buildUrl(path, params) {
    const cleanPath = String(path || "").startsWith("/") ? path : `/${path}`;
    const usp = new URLSearchParams();

    if (params && typeof params === "object") {
      Object.entries(params).forEach(([k, v]) => {
        if (v == null) return;

        if (Array.isArray(v)) {
          v.forEach((item) => {
            if (item != null && item !== "") {
              usp.append(k, String(item));
            }
          });
        } else if (v !== "") {
          usp.append(k, String(v));
        }
      });
    }

    const qs = usp.toString();
    return `${BASE}${cleanPath}${qs ? `?${qs}` : ""}`;
  }

  async function fetchJSON(url, opt = {}) {
    const res = await fetch(url, opt);

    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      throw new Error(`${opt.method || "GET"} ${url} failed: ${res.status} ${txt}`);
    }

    return res.json();
  }

  /**
   * Summary 主資料
   * GET /aoi_capa/api/reset_summary_filter
   */
  AOI.API.fetchSummary = async function (dates) {
    return fetchJSON(
      buildUrl("/aoi_capa/api/reset_summary_filter", {
        dates: Array.isArray(dates) && dates.length === 2 ? dates : null,
      })
    );
  };

  /**
   * Hourly rawdata
   * GET /aoi_capa/api/hourly_rawdata_filter
   */
  AOI.API.fetchHourly = async function (ask) {
    const payload = {
      aoi: ask?.aoi || "",
      pi_type: ask?.pi_type ?? null,
      run_day: ask?.run_day || "",
    };

    return fetchJSON(
      buildUrl("/aoi_capa/api/hourly_rawdata_filter", {
        filter_ask_keys: JSON.stringify(payload),
      })
    );
  };

  /**
   * 儲存 target/spec 或 day info comment/action
   * POST /aoi_capa/api/save_config
   */
  AOI.API.saveCapaConfig = async function (payload) {
    return fetchJSON(buildUrl("/aoi_capa/api/save_config"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
  };

  /**
   * Action History / EditSummary 資料
   * 這支是你新加的後端 API
   * GET /aoi_capa/api/action_history_data
   *
   * dates: ['2026-04-01', '2026-04-21']
   */
  AOI.API.fetchActionHistoryData = async function (dates) {
    return fetchJSON(
      buildUrl("/aoi_capa/api/action_history_data", {
        dates: Array.isArray(dates) && dates.length === 2 ? dates : null,
      })
    );
  };

  AOI.API.ENDPOINTS = {
    fetchSummary: "/aoi_capa/api/reset_summary_filter",
    fetchHourly: "/aoi_capa/api/hourly_rawdata_filter",
    saveCapaConfig: "/aoi_capa/api/save_config",
    fetchActionHistoryData: "/aoi_capa/api/action_history_data",
  };
})();