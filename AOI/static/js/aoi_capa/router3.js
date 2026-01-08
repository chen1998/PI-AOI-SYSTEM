// static/js/aoi_capa/router.js
(function () {
  const AOI = (window.AOI_CAPA = window.AOI_CAPA || {});
  AOI.Router = AOI.Router || {};

  const $ = (sel, root = document) => root.querySelector(sel);

  AOI.state = AOI.state || {
    rows: [],
    paramDict: null,
    dateRange: null,
    hourlyCache: {} // key: aoi|run_day|pi_type → hourly rows
  };

  // 重新畫 Chart + Table
  AOI.Router.redraw = function () {
    if (!AOI.Chart || !AOI.Table) return;
    //console.log("[AOI_CAPA] redraw chart & table");
    AOI.Chart.update();
    AOI.Table.build();
  };

  // ======= 讀取右側日期欄位 =======
  function readDateRangeFromUI() {
    const s = $("#aoi_capaStart")?.value || "";
    const e = $("#aoi_capaEnd")?.value || "";
    if (!s || !e) return null;
    return [s, e];
  }

  function clearDateRangeUI() {
    const s = $("#aoi_capaStart");
    const e = $("#aoi_capaEnd");
    if (s) s.value = "";
    if (e) e.value = "";
  }

  // ======= 呼叫 API 抓 Summary =======
  AOI.Router.refreshSummary = async function (dates) {
    try {
      //console.log("[AOI_CAPA] refreshSummary, dates =", dates);
      const payload = await AOI.API.fetchSummary(dates || null);
      AOI.state.rows = payload.DictData || [];
      AOI.state.paramDict = payload.ParamDict || {};
      AOI.state.dateRange = payload.DateRange || null;
  
      /*console.log("[AOI_CAPA] rows len =", AOI.state.rows.length);
      console.log('AOI.state.dateRange',AOI.state.dateRange);*/
      // 自動設定右側日期區域（初次載入 / 點清除後）
      if (!dates && AOI.state.dateRange ) {
        const start = AOI.state.dateRange.start;
        const end = AOI.state.dateRange.end;
        const s = document.querySelector("#aoi_capaStart");
        const e = document.querySelector("#aoi_capaEnd");
        if (s && e) {
          s.value = start;   // YYYY-MM-DD
          e.value = end;
          //console.log(s,e);
        }
      }
  
      // 給 Filter.js 用（動態建 MultiDD）
      document.dispatchEvent(
        new CustomEvent("aoi_capa:data-ready", { detail: AOI.state })
      );
  
      // 初次/重新載入後就畫一次
      AOI.Router.redraw();
    } catch (err) {
      console.error("[AOI_CAPA] refreshSummary failed:", err);
      const toast = document.querySelector(".toast");
      if (toast) {
        toast.textContent = `稼動 summary 讀取失敗：${err.message || err}`;
        toast.classList.add("show");
        setTimeout(() => toast.classList.remove("show"), 3000);
      }
    }
  };

  // ======= 事件繫結 =======
  function bindUIEvents() {
    const btnApply = $("#aoi_capaApply");
    const btnClear = $("#aoi_capaClear");

    if (btnApply) {
      btnApply.addEventListener("click", () => {
        const dr = readDateRangeFromUI();
        AOI.Router.refreshSummary(dr || null);
      });
    }
    if (btnClear) {
      btnClear.addEventListener("click", () => {
        clearDateRangeUI();
        AOI.Router.refreshSummary(null); // 用預設 7 天
      });
    }

    // MultiDD select 改變 → 重新畫圖 + 表
    const right = $("#aoi_capa-right");
    if (right) {
      right.addEventListener("change", (ev) => {
        const id = ev.target?.id || "";
        if (id.startsWith("capa-f-")) {
          //console.log("[AOI_CAPA] filter changed:", id);
          AOI.Router.redraw();
        }
      });
    }

    // ★ 關鍵：切換到「稼動」tab 時，強制重畫 + resize
    const capaTabBtns = document.querySelectorAll('.sys-tab[data-view="aoi_capa"]');
    capaTabBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        // 等 system_tab.js 把 #aoi_capa-root 顯示出來
        setTimeout(() => {
          //console.log("[AOI_CAPA] sys-tab aoi_capa clicked, force redraw+resize");
          AOI.Router.redraw();

          const dom = document.getElementById("aoi_capa-facet");
          if (dom && window.echarts) {
            const inst = window.echarts.getInstanceByDom(dom) || window.echarts.init(dom);
            inst && inst.resize();
          }
        }, 50);
      });
    });
  }
  // ======= 初始化 =======
  AOI.Router.init = function () {
    bindUIEvents();
    // 初次載入：不帶日期 → 後端預設 7 天
    AOI.Router.refreshSummary(null);
  };

  document.addEventListener("DOMContentLoaded", () => {
    const root = document.getElementById("aoi_capa-root");
    if (root) {
      AOI.Router.init();
    }
  });
})();