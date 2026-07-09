// static/js/bpi_area/bpi_same_point/api.js
(function () {
  const MOD = (window.BPI_SAME_POINT = window.BPI_SAME_POINT || {});
  const API_BASE = window.API_BASE || "";

  function buildUrl(path) {
    if (!path) return API_BASE;

    // 若已經是完整 URL，直接回傳
    if (/^https?:\/\//i.test(path)) {
      return path;
    }

    return `${API_BASE}${path}`;
  }

  async function postJson(path, body) {
    const resp = await fetch(buildUrl(path), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body || {}),
    });

    if (!resp.ok) {
      const txt = await resp.text().catch(() => "");
      throw new Error(txt || `HTTP ${resp.status}`);
    }

    return await resp.json();
  }

  MOD.API = {
    async resetFilter(payload) {
      return await postJson("/bpi_same_point/reset_filter", payload);
    },

    async defectMap(payload) {
      return await postJson("/bpi_same_point/defect_map", payload);
    },

    async CommentEditor(payload) {
      return await postJson("/common/edit_table", payload);
    },
  };
})();