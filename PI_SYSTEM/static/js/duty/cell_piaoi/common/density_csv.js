// static/js/common/density_csv.js
// 共用 Density CSV Download / Preview
//
// 對應 HTML：
//   section#density-csv-download-root
//   input#density-csv-start
//   input#density-csv-end
//   button#density-csv-preview-btn
//   button#density-csv-download-btn
//   div#density-csv-status
//   table#density-csv-preview-table
//
// 用途：
//   BPI Density(AOI) / AOI Density / Inspection Density 共用同一個下載頁面。
//   各 system service.js 切到 type="csv" 時呼叫：
//     window.DENSITY_CSV_DOWNLOAD.setSystem({
//       system: "aoi_density" | "aoi_bpi_density" | "aoi_inspection_density",
//       tabKey,
//       config
//     });
//
// 預設：
//   日期區間 = 前 30 天 ~ 今天
//   切入 csv 頁面後自動 preview

(function () {
    const MOD = (window.DENSITY_CSV_DOWNLOAD = window.DENSITY_CSV_DOWNLOAD || {});
  
    const API_BASE = window.API_BASE || "";
  
    const state = {
      system: "",
      tabKey: "",
      config: null,
      lastPreview: null,
      bound: false,
      autoPreviewDoneBySystem: {}
    };
  
    // ============================================================
    // DOM helpers
    // ============================================================
    function $(id) {
      return document.getElementById(id);
    }
  
    function setStatus(msg) {
      const el = $("density-csv-status");
      if (el) el.textContent = msg || "";
    }
  
    function setBusy(isBusy) {
      const previewBtn = $("density-csv-preview-btn");
      const downloadBtn = $("density-csv-download-btn");
  
      if (previewBtn) previewBtn.disabled = !!isBusy;
      if (downloadBtn) downloadBtn.disabled = !!isBusy;
    }
  
    function pad2(n) {
      return String(n).padStart(2, "0");
    }
  
    function toYMD(d) {
      const y = d.getFullYear();
      const m = pad2(d.getMonth() + 1);
      const day = pad2(d.getDate());
      return `${y}-${m}-${day}`;
    }
  
    function getDefaultDateRange() {
      const end = new Date();
      end.setHours(0, 0, 0, 0);
  
      const start = new Date(end);
      start.setDate(start.getDate() - 30);
  
      return {
        start_date: toYMD(start),
        end_date: toYMD(end)
      };
    }
  
    function ensureDefaultDates(force) {
      const startEl = $("density-csv-start");
      const endEl = $("density-csv-end");
  
      if (!startEl || !endEl) return;
  
      const def = getDefaultDateRange();
  
      if (force || !startEl.value) startEl.value = def.start_date;
      if (force || !endEl.value) endEl.value = def.end_date;
    }
  
    function readDates() {
      return {
        start_date: $("density-csv-start")?.value || "",
        end_date: $("density-csv-end")?.value || ""
      };
    }
  
    function validatePayload(payload) {
      if (!payload.system) {
        alert("尚未指定下載系統");
        return false;
      }
  
      if (!payload.start_date || !payload.end_date) {
        alert("請選擇日期區間");
        return false;
      }
  
      return true;
    }
  
    function buildPayload(extra) {
      const dates = readDates();
  
      return {
        system: state.system,
        start_date: dates.start_date,
        end_date: dates.end_date,
        ...(extra || {})
      };
    }
  
    function buildUrl(path) {
      return `${API_BASE}${path}`;
    }
  
    async function postJson(path, body) {
      const resp = await fetch(buildUrl(path), {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(body || {})
      });
  
      if (!resp.ok) {
        const txt = await resp.text().catch(() => "");
        throw new Error(txt || `HTTP ${resp.status}`);
      }
  
      return await resp.json();
    }
  
    async function postBlobResponse(path, body) {
      const resp = await fetch(buildUrl(path), {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(body || {})
      });
  
      if (!resp.ok) {
        const txt = await resp.text().catch(() => "");
        throw new Error(txt || `HTTP ${resp.status}`);
      }
  
      return resp;
    }
  
    function parseFilenameFromContentDisposition(cd, fallback) {
      if (!cd) return fallback;
  
      // filename*=UTF-8''xxx.csv
      const m1 = cd.match(/filename\*=UTF-8''([^;]+)/i);
      if (m1 && m1[1]) {
        try {
          return decodeURIComponent(m1[1]);
        } catch (_) {
          return m1[1];
        }
      }
  
      // filename="xxx.csv"
      const m2 = cd.match(/filename="?([^"]+)"?/i);
      if (m2 && m2[1]) return m2[1];
  
      return fallback;
    }
  
    // ============================================================
    // API
    // ============================================================
    const API = {
      async preview(payload) {
        return await postJson("/common/density_csv/preview", payload);
      },
  
      async download(payload) {
        const resp = await postBlobResponse("/common/density_csv/download", payload);
        const blob = await resp.blob();
  
        const cd = resp.headers.get("Content-Disposition") || "";
        const fallback = `${payload?.system || "density"}_${payload?.start_date || ""}_${payload?.end_date || ""}.csv`;
        const filename = parseFilenameFromContentDisposition(cd, fallback);
  
        const a = document.createElement("a");
        const url = URL.createObjectURL(blob);
  
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
  
        URL.revokeObjectURL(url);
        a.remove();
  
        return {
          ok: true,
          filename
        };
      }
    };
  
    // 也暴露一份 API，讓其他 JS 可直接呼叫
    window.DENSITY_CSV_API = API;
  
    // ============================================================
    // Table render
    // ============================================================
    function normalizeCellValue(v) {
      if (v == null) return "";
  
      if (typeof v === "object") {
        try {
          return JSON.stringify(v);
        } catch (_) {
          return String(v);
        }
      }
  
      return String(v);
    }
  
    function renderPreview(rows, columns) {
      const table = $("density-csv-preview-table");
      if (!table) return;
  
      const thead = table.querySelector("thead");
      const tbody = table.querySelector("tbody");
  
      if (!thead || !tbody) return;
  
      thead.innerHTML = "";
      tbody.innerHTML = "";
  
      const arr = Array.isArray(rows) ? rows : [];
  
      const cols = Array.isArray(columns) && columns.length
        ? columns
        : Object.keys(arr?.[0] || {});
  
      if (!cols.length) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.textContent = "（無資料）";
        td.className = "muted";
        tr.appendChild(td);
        tbody.appendChild(tr);
        return;
      }
  
      const trh = document.createElement("tr");
  
      cols.forEach(c => {
        const th = document.createElement("th");
        th.textContent = c;
        th.style.whiteSpace = "nowrap";
        trh.appendChild(th);
      });
  
      thead.appendChild(trh);
  
      arr.forEach(r => {
        const tr = document.createElement("tr");
  
        cols.forEach(c => {
          const td = document.createElement("td");
          td.textContent = normalizeCellValue(r?.[c]);
          td.style.whiteSpace = "nowrap";
          td.style.maxWidth = "360px";
          td.style.overflow = "hidden";
          td.style.textOverflow = "ellipsis";
          tr.appendChild(td);
        });
  
        tbody.appendChild(tr);
      });
    }
  
    // ============================================================
    // Main actions
    // ============================================================
    MOD.setSystem = function ({ system, tabKey, config }) {
      state.system = system || "";
      state.tabKey = tabKey || "";
      state.config = config || null;
  
      ensureDefaultDates(false);
  
      const labelMap = {
        aoi_density: "AOI Density",
        aoi_bpi_density: "BPI Density(AOI)",
        aoi_inspection_density: "Inspection Density"
      };
  
      const label = labelMap[state.system] || state.system || "未指定";
      setStatus(`目前系統：${label}`);
  
      // 每次切到 csv 頁，都自動查詢目前日期區間。
      // 預設第一次是 前30天~今天；若使用者已改日期，會沿用目前欄位。
      MOD.preview();
    };
  
    MOD.preview = async function () {
      ensureDefaultDates(false);
  
      const payload = buildPayload({
        limit: 100
      });
  
      if (!validatePayload(payload)) return;
  
      try {
        setBusy(true);
        setStatus("查詢中...");
  
        const resp = await API.preview(payload);
  
        state.lastPreview = resp;
  
        renderPreview(resp?.rows || [], resp?.columns || []);
  
        //const count = Number(resp?.count || 0);
        //const shown = Array.isArray(resp?.rows) ? resp.rows.length : 0;
        setStatus(`預覽顯示:`);
        //setStatus(`預覽完成：顯示 ${shown} 筆，總筆數/查詢筆數 ${count}。`);
      } catch (err) {
        console.error("[density_csv] preview failed:", err);
        renderPreview([], []);
        setStatus("查詢失敗");
        alert("查詢失敗：" + (err?.message || String(err)));
      } finally {
        setBusy(false);
      }
    };
  
    MOD.download = async function () {
      ensureDefaultDates(false);
  
      const payload = buildPayload();
  
      if (!validatePayload(payload)) return;
  
      try {
        setBusy(true);
        setStatus("準備下載 CSV...");
  
        const result = await API.download(payload);
  
        setStatus(`下載完成：${result.filename || ""}`);
      } catch (err) {
        console.error("[density_csv] download failed:", err);
        setStatus("下載失敗");
        alert("下載失敗：" + (err?.message || String(err)));
      } finally {
        setBusy(false);
      }
    };
  
    MOD.clearPreview = function () {
      state.lastPreview = null;
      renderPreview([], []);
      setStatus("");
    };
  
    MOD.getState = function () {
      return { ...state };
    };
  
    // ============================================================
    // Bind events
    // ============================================================
    function bind() {
      if (state.bound) return;
      state.bound = true;
  
      ensureDefaultDates(false);
  
      $("density-csv-preview-btn")?.addEventListener("click", () => {
        MOD.preview();
      });
  
      $("density-csv-download-btn")?.addEventListener("click", () => {
        MOD.download();
      });
  
      document.addEventListener("density-csv-download:show", (ev) => {
        MOD.setSystem(ev.detail || {});
      });
    }
  
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", bind);
    } else {
      bind();
    }
  })();