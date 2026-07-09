
// static/js/duty/cell_piaoi/ol_defect_map/api.js
(function () {
  const Bus = window.OLDefectMapBus;
  const State = window.OLDefectMapState;
  const Utils = window.OLDefectMapUtils;
  const ColorKit = window.OLDefectMapColorKit;
  const FilterController = window.OLDefectMapFilterController;

  if (!Bus || !State || !Utils || !ColorKit || !FilterController) {
    console.error("[ol-defect-map][api] dependencies missing", {
      hasBus: !!Bus,
      hasState: !!State,
      hasUtils: !!Utils,
      hasColorKit: !!ColorKit,
      hasFilterController: !!FilterController,
    });
    return;
  }

  const API = {
    async getAll(start, end) {
      const u = new URL(
        (window.API_BASE || "") + "/aoi_ol_defect_map/run_info",
        window.location.origin
      );

      if (start) u.searchParams.set("start", start);
      if (end) u.searchParams.set("end", end);

      const res = await fetch(u.toString());

      if (!res.ok) {
        throw new Error(`GET /aoi_ol_defect_map/run_info failed (${res.status})`);
      }

      const data = await res.json();
      console.log("[ol-defect-map][api] getAll payload:", data);
      return data;
    },

    async getByAoi(aoi, start, end) {
      const u = new URL(
        (window.API_BASE || "") + "/aoi_ol_defect_map/run_info",
        window.location.origin
      );

      u.searchParams.set("aoi", aoi);

      if (start) u.searchParams.set("start", start);
      if (end) u.searchParams.set("end", end);

      const res = await fetch(u.toString());

      if (!res.ok) {
        throw new Error(`GET /aoi_ol_defect_map/run_info by aoi failed (${res.status})`);
      }

      const data = await res.json();

      return data;
    },

    async getDefects(key) {
      const u = new URL(
        (window.API_BASE || "") + "/aoi_ol_defect_map/gld_defect_map",
        window.location.origin
      );

      u.searchParams.set("key", key);

      const res = await fetch(u.toString());

      if (!res.ok) {
        const txt = await res.text();
        console.error("[ol-defect-map][api] getDefects failed body:", txt);
        throw new Error(`GET /aoi_ol_defect_map/gld_defect_map failed (${res.status})`);
      }

      const data = await res.json();

      return data;
    }
  };

  function buildTabs(aoiTabs) {
    const cont = document.getElementById("all-tab-container");
    if (!cont) return;

    cont.innerHTML = "";

    const row = document.createElement("div");
    row.className = "tabs-row";

    (aoiTabs || []).forEach((aoi, idx) => {
      const btn = document.createElement("button");
      btn.className = "tab-btn";
      btn.textContent = aoi;

      if (idx === 0) {
        btn.classList.add("active");
      }

      btn.addEventListener("click", async () => {
        row.querySelectorAll(".tab-btn").forEach((b) => {
          b.classList.remove("active");
        });

        btn.classList.add("active");

        State.currentAoi = aoi;

        const dictRows = State.AllRunInfo[aoi] || {};
        const rows = Object.values(dictRows || {});

        Bus.emit("render-run-info", rows);
      });

      row.appendChild(btn);
    });

    cont.appendChild(row);
  }

  function refreshLegend() {
    const box = document.getElementById("ol-defect-map-legend");
    if (!box) return;

    box.innerHTML = "";

    const keys = State.selectedKeys || [];
    const keyColorMap = ColorKit.mapKeys(keys);

    State.keyColors = State.keyColors || {};

    keys.forEach((k) => {
      const c = (State.keyColors[k] ||= keyColorMap[k] || Utils.hashColor(k));

      const div = document.createElement("div");
      div.className = "ol-defect-map-legend-item";

      div.innerHTML = `
        <span class="ol-defect-map-legend-color" style="background:${c}"></span>
        <span class="ol-defect-map-legend-text">${k}</span>
      `;

      box.appendChild(div);
    });
  }

  function wireGlobalFilters() {
    const q = document.getElementById("ol-defect-map-query-input");
    const btnQ = document.getElementById("ol-defect-map-apply-query");
    const btnQC = document.getElementById("ol-defect-map-clear-query");

    const df = document.getElementById("ol-defect-map-date-from");
    const dt = document.getElementById("ol-defect-map-date-to");
    const btnApply = document.getElementById("ol-defect-map-apply-dates");
    const btnClear = document.getElementById("ol-defect-map-clear-dates");

    const same = document.getElementById("ol-defect-map-match-same-glass");
    const offsetInput = document.getElementById("ol-defect-map-offset-input");
    const offsetBtn = document.getElementById("ol-defect-map-apply-offset");

    if (btnQ) {
      btnQ.addEventListener("click", () => {
        State.filters.glassQuery = (q?.value || "").trim();
        Bus.emit("filters-changed");
      });
    }

    if (q) {
      q.addEventListener("keydown", (e) => {
        if (e.key !== "Enter") return;
        State.filters.glassQuery = (q.value || "").trim();
        Bus.emit("filters-changed");
      });
    }

    if (btnQC) {
      btnQC.addEventListener("click", () => {
        if (q) q.value = "";
        State.filters.glassQuery = "";
        Bus.emit("filters-changed");
      });
    }

    if (btnApply) {
      btnApply.addEventListener("click", async () => {
        if (!State.currentAoi) return;

        const start = df?.value || "";
        const end = dt?.value || "";

        try {
          const res = await API.getByAoi(State.currentAoi, start, end);
          const dict = res.UniRunInfoTableData || {};

          State.AllRunInfo[State.currentAoi] = dict;
          State.selectedKeys = [];
          State.DefectCache = {};
          State.typeSet = new Set();
          State.filters.typeSetSelected = new Set();
          State._lastTypeOptions = [];

          FilterController.buildTypeFilters();

          Bus.emit("clear-offset-images");
          Bus.emit("render-run-info", Object.values(dict));
          Bus.emit("map-refresh");
        } catch (e) {
          console.error("[ol-defect-map][api] apply date failed", e);
          window.olDefectMapToast?.("日期篩選載入失敗");
        }
      });
    }

    if (btnClear) {
      btnClear.addEventListener("click", async () => {
        if (!State.currentAoi) return;

        if (df) df.value = "";
        if (dt) dt.value = "";

        try {
          const res = await API.getByAoi(State.currentAoi, "", "");
          const dict = res.UniRunInfoTableData || {};

          State.AllRunInfo[State.currentAoi] = dict;
          State.selectedKeys = [];
          State.DefectCache = {};
          State.typeSet = new Set();
          State.filters.typeSetSelected = new Set();
          State._lastTypeOptions = [];

          FilterController.buildTypeFilters();

          Bus.emit("clear-offset-images");
          Bus.emit("render-run-info", Object.values(dict));
          Bus.emit("map-refresh");
        } catch (e) {
          console.error("[ol-defect-map][api] clear date failed", e);
          window.olDefectMapToast?.("清空日期篩選失敗");
        }
      });
    }

    if (same) {
      same.checked = !!State.flags.matchSameGlass;

      same.addEventListener("change", () => {
        State.flags.matchSameGlass = !!same.checked;
        Bus.emit("filters-changed");
      });
    }

    if (offsetBtn && offsetInput) {
      offsetBtn.addEventListener("click", () => {
        const v = parseFloat(offsetInput.value || "5");
        State.offsetUm = Number.isFinite(v) && v > 0 ? v : 5;
        State.mapOffsetUm = State.offsetUm;

        Bus.emit("map-refresh");
      });
    }

    if (offsetInput) {
      offsetInput.addEventListener("keydown", (e) => {
        if (e.key !== "Enter") return;

        const v = parseFloat(offsetInput.value || "5");
        State.offsetUm = Number.isFinite(v) && v > 0 ? v : 5;
        State.mapOffsetUm = State.offsetUm;

        Bus.emit("map-refresh");
      });
    }

    if (df && dt && !df.value && !dt.value) {
      const today = new Date();
      const end = today.toISOString().slice(0, 10);

      const startDate = new Date(today);
      startDate.setDate(startDate.getDate() - 3);

      const start = startDate.toISOString().slice(0, 10);

      df.value = start;
      dt.value = end;
    }
  }

  async function fetchDefectsIfNeeded(keys) {
    const promises = [];
    const newKeys = [];

    (keys || []).forEach((k) => {
      if (!State.DefectCache[k]) {
        newKeys.push(k);

        promises.push(
          API.getDefects(k)
            .then((j) => {
              const ctx = Utils.parseKey(k);

              const list = (j && j.defects)
                ? j.defects.map((raw) => {
                    /*
                      若 bus1.js 的 Utils.unifyDefect 已支援第二參數 ctx，
                      這裡會把 key 裡的 aoi 傳入，方便 aoi200 空 defect_size 歸 O。
                      若目前 unifyDefect 還沒改成接 ctx，JS 仍可正常執行，
                      多傳的參數會被忽略。
                    */
                    return Utils.unifyDefect(raw, ctx);
                  })
                : [];

              State.DefectCache[k] = list;

              list.forEach((d) => {
                if (d && d.type) {
                  State.typeSet.add(d.type);
                }
              });
            })
            .catch((e) => {
              console.error("[ol-defect-map][api] getDefects error:", k, e);
            })
        );
      }
    });

    if (promises.length) {
      await Promise.all(promises);

      FilterController.buildTypeFilters();
      refreshLegend();

      Bus.emit("defect-refresh", newKeys);
    }
  }

  async function init() {
    try {
      const df = document.getElementById("ol-defect-map-date-from");
      const dt = document.getElementById("ol-defect-map-date-to");

      if (df && dt && !df.value && !dt.value) {
        const today = new Date();
        const end = today.toISOString().slice(0, 10);

        const startDate = new Date(today);
        startDate.setDate(startDate.getDate() - 3);

        const start = startDate.toISOString().slice(0, 10);

        df.value = start;
        dt.value = end;
      }

      const payload = await API.getAll(df?.value || "", dt?.value || "");

      State.AllRunInfo = payload.AllRunInfoTableData || {};

      const tabs = payload.AllAoiTabs || Object.keys(State.AllRunInfo || {});
      State.currentAoi = (tabs && tabs[0]) || null;

      State.selectedKeys = State.selectedKeys || [];
      State.DefectCache = State.DefectCache || {};
      State.typeSet = State.typeSet || new Set();

      buildTabs(tabs);
      wireGlobalFilters();

      FilterController.buildSizeFilters();
      FilterController.buildTypeFilters();

      const dictRows = State.AllRunInfo[State.currentAoi] || {};
      const rows = Object.values(dictRows || {});

      Bus.emit("render-run-info", rows);
    } catch (e) {
      console.error("[ol-defect-map][api] init failed", e);
      window.olDefectMapToast?.("載入資料失敗");
    }
  }

  Bus.on("selection-changed", (keys) => {
    console.log("[ol-defect-map][api] selection-changed:", keys);

    if (!keys || !keys.length) {
      refreshLegend();
      Bus.emit("defect-refresh", []);
      Bus.emit("map-refresh");
      return;
    }

    fetchDefectsIfNeeded(keys);
    refreshLegend();
  });

  window.OLDefectMapAPI = API;

  window.OLDefectMapAPIController = {
    init,
    refreshLegend,

    // 保留舊接口，避免其他檔案仍然呼叫 APIController.buildSizeFilters/buildTypeFilters 時失效
    buildSizeFilters: FilterController.buildSizeFilters,
    buildTypeFilters: FilterController.buildTypeFilters,

    fetchDefectsIfNeeded,
  };
})();