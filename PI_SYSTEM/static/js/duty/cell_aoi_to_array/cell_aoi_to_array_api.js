// static/js/duty/cell_aoi_to_array/cell_aoi_to_array_api.js
(function () {
  "use strict";

  window.CELL_AOI_TO_ARRAY = window.CELL_AOI_TO_ARRAY || {};
  const MOD = window.CELL_AOI_TO_ARRAY;

  const API_BASE = String(window.API_BASE || "").replace(/\/$/, "");
  const ROUTE_BASE = `${API_BASE}/cell_aoi_to_array`;

  console.log("[cell-aoi-to-array-api] ROUTE_BASE =", ROUTE_BASE);

  MOD.API = {
    fetchConfig,
    fetchCompareData,
    fetchDetailData,
    fetchDefectGroups,
    updateAction
  };

  async function fetchConfig() {
    console.log("[cell-aoi-to-array-api] GET config");

    const res = await fetch(`${ROUTE_BASE}/config`, {
      method: "GET",
      headers: {
        Accept: "application/json"
      }
    });

    if (!res.ok) {
      const text = await res.text().catch(function () {
        return "";
      });
      throw new Error(`fetch config failed: ${res.status} ${text}`);
    }

    return await res.json();
  }

  async function fetchCompareData(payload) {
    const safePayload = normalizeComparePayload(payload);
  
    console.log("[cell-aoi-to-array-api] POST compare", safePayload);
  
    const res = await fetch(`${ROUTE_BASE}/compare`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json"
      },
      body: JSON.stringify(safePayload)
    });
  
    if (!res.ok) {
      const text = await res.text().catch(function () {
        return "";
      });
      throw new Error(`fetch compare failed: ${res.status} ${text}`);
    }
  
    return await res.json();
  }
  

  async function fetchDetailData(rowOrPayload) {
    const payload = normalizeDetailPayload(rowOrPayload);

    console.log("[cell-aoi-to-array-api] POST detail", payload);

    const res = await fetch(`${ROUTE_BASE}/detail`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json"
      },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const text = await res.text().catch(function () {
        return "";
      });
      throw new Error(`fetch detail failed: ${res.status} ${text}`);
    }

    return await res.json();
  }

  async function fetchDefectGroups(rowOrPayload) {
    const payload = normalizeDetailPayload(rowOrPayload);

    console.log("[cell-aoi-to-array-api] POST detail-defect-groups", payload);

    const res = await fetch(`${ROUTE_BASE}/detail-defect-groups`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json"
      },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const text = await res.text().catch(function () {
        return "";
      });
      throw new Error(`fetch defect groups failed: ${res.status} ${text}`);
    }

    return await res.json();
  }

  async function updateAction(rowOrPayload) {
    const payload = Object.assign(
      {},
      normalizeDetailPayload(rowOrPayload),
      {
        comment: rowOrPayload?.comment ?? "",
        action: rowOrPayload?.action ?? "",
        editor: rowOrPayload?.editor ?? ""
      }
    );

    console.log("[cell-aoi-to-array-api] POST update-action", payload);

    const res = await fetch(`${ROUTE_BASE}/update-action`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json"
      },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const text = await res.text().catch(function () {
        return "";
      });
      throw new Error(`update action failed: ${res.status} ${text}`);
    }

    return await res.json();
  }

  function normalizeComparePayload(payload) {
    const state = MOD.State && MOD.State.state ? MOD.State.state : {};
    const filters = Object.assign(
      {},
      state.filters || {},
      payload?.filters || {}
    );
  
    const sheetIds = Array.isArray(filters.sheetIds)
      ? filters.sheetIds
          .map(function (v) {
            return String(v || "").trim().toUpperCase();
          })
          .filter(function (v, idx, arr) {
            return (
              v &&
              !["NAN", "NONE", "NULL", "<NA>", "NAT"].includes(v) &&
              arr.indexOf(v) === idx
            );
          })
      : [];
  
    return {
      category: payload?.category || state.category || "PI",
      feature: payload?.feature || state.feature || "aoi-sampling-compare",
      filters: {
        startDate: filters.startDate || "",
        endDate: filters.endDate || "",
  
        tool: filters.tool || "",
        lineId: filters.lineId || "",
  
        sheetType: filters.sheetType || "",
        sheetId: filters.sheetId || "",
  
        // CSV 多片 sheet 查詢
        sheetIds: sheetIds,
  
        aoi: filters.aoi || "",
        piType: filters.piType || "",
        sourceOpId: filters.sourceOpId || "",
        matchStatus: filters.matchStatus || "",
        modelNo: filters.modelNo || "",
        recipeId: filters.recipeId || ""
      }
    };
  }

  function normalizeDetailPayload(row) {
    const state = MOD.State && MOD.State.state ? MOD.State.state : {};

    return {
      feature: row?.feature || state.feature || "aoi-sampling-compare",

      sheet_id_chip_id:
        row?.sheet_id_chip_id ||
        row?.sheet_id ||
        row?.detail?.sheet_id ||
        "",

      test_time:
        row?.test_time ||
        row?.scan_time ||
        row?.detail?.scan_time ||
        "",

      pi_type:
        row?.pi_type ||
        row?.cell_op ||
        row?.detail?.cell_op ||
        "",

      source_op_id:
        row?.source_op_id ||
        row?.tool ||
        row?.detail?.source_op_id ||
        ""
    };
  }
})();




































