// static/js/duty/cell_aoi_to_array/cell_aoi_to_array_filters.js
(function () {
  "use strict";

  window.CELL_AOI_TO_ARRAY = window.CELL_AOI_TO_ARRAY || {};
  const MOD = window.CELL_AOI_TO_ARRAY;

  MOD.Filters = {
    init,
    render,
    collect,
    parseSheetCsvText,
    downloadSampleCsv
  };

  function init() {
    const { dom } = MOD.State;

    if (dom.applyBtn) {
      dom.applyBtn.addEventListener("click", function () {
        MOD.Main.reload();
      });
    }

    bindCsvUpload();
  }

  function render() {
    const { dom, state } = MOD.State;
    const cfg = MOD.State.getConfig();

    if (dom.startDate) dom.startDate.value = state.filters.startDate || "";
    if (dom.endDate) dom.endDate.value = state.filters.endDate || "";

    renderToolSelect();

    const sheetTypes =
      cfg.sheetTypes ||
      cfg.CELL_AOI_TO_ARRAY_SHEET_TYPES ||
      ["TFT", "CF"];

    renderSheetRadios(sheetTypes);

    if (dom.sheetInput) {
      dom.sheetInput.value = state.filters.sheetId || "";
    }

    renderCsvInfo();
  }

  function bindCsvUpload() {
    const { dom } = MOD.State;

    if (dom.sheetCsvBtn && dom.sheetCsvInput) {
      dom.sheetCsvBtn.addEventListener("click", function () {
        dom.sheetCsvInput.click();
      });
    }

    if (dom.sheetCsvInput) {
      dom.sheetCsvInput.addEventListener("change", handleCsvFileChange);
    }

    if (dom.sheetCsvClearBtn) {
      dom.sheetCsvClearBtn.addEventListener("click", function () {
        clearCsvSheets();
      });
    }

    const sampleBtn =
      dom.sheetCsvSampleBtn ||
      document.querySelector("#cell-aoi-to-array-sheet-csv-sample-btn");

    if (sampleBtn) {
      sampleBtn.addEventListener("click", function () {
        downloadSampleCsv();
      });
    }
  }

  async function handleCsvFileChange(evt) {
    const { state } = MOD.State;
    const file = evt.target.files && evt.target.files[0];

    if (!file) return;

    const fileName = file.name || "";

    if (!fileName.toLowerCase().endsWith(".csv")) {
      alert("請選擇 CSV 檔案");
      clearCsvSheets();
      return;
    }

    try {
      const text = await readFileAsText(file);
      const sheetIds = parseSheetCsvText(text);

      state.filters.sheetIds = sheetIds;
      state.filters.sheetCsvFileName = fileName;

      renderCsvInfo();

      if (!sheetIds.length) {
        alert("CSV 內沒有解析到 sheet_id");
      }
    } catch (err) {
      console.error("[cell-aoi-to-array-filters] csv parse failed:", err);
      alert(`CSV 解析失敗：${err.message || err}`);
      clearCsvSheets();
    }
  }

  function readFileAsText(file) {
    return new Promise(function (resolve, reject) {
      const reader = new FileReader();

      reader.onload = function () {
        resolve(String(reader.result || ""));
      };

      reader.onerror = function () {
        reject(reader.error || new Error("FileReader failed"));
      };

      // 常見 CSV 如果是 UTF-8 BOM 可正常讀。
      reader.readAsText(file, "utf-8");
    });
  }

  function downloadSampleCsv() {
    const rows = [
      ["AE1UA504MY"],
      ["AE1UA505MY"],
      ["AE1UA506MY"]
    ];

    const csvText = rows
      .map(function (row) {
        return row
          .map(function (cell) {
            const s = String(cell == null ? "" : cell);
            return `"${s.replace(/"/g, '""')}"`;
          })
          .join(",");
      })
      .join("\r\n");

    // 加 UTF-8 BOM，避免 Excel 開啟 CSV 亂碼。
    const blob = new Blob(["\uFEFF" + csvText], {
      type: "text/csv;charset=utf-8;"
    });

    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");

    const now = new Date();
    const pad = function (n) {
      return String(n).padStart(2, "0");
    };

    const ymd =
      now.getFullYear() +
      pad(now.getMonth() + 1) +
      pad(now.getDate());

    a.href = url;
    a.download = `cell_aoi_to_array_sheet_sample_${ymd}.csv`;
    a.style.display = "none";

    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    URL.revokeObjectURL(url);
  }

  function parseSheetCsvText(text) {
    const raw = String(text || "").replace(/^\uFEFF/, "");
    const lines = raw
      .split(/\r?\n/)
      .map(function (line) {
        return line.trim();
      })
      .filter(Boolean);

    if (!lines.length) return [];

    const rows = lines.map(parseCsvLine);
    const header = rows[0].map(function (x) {
      return String(x || "").trim().toLowerCase();
    });

    const sheetHeaderCandidates = [
      "sheet_id_chip_id",
      "sheet_id",
      "sheet",
      "glass_id",
      "glass",
      "id"
    ];

    let sheetColIndex = -1;

    for (let i = 0; i < header.length; i += 1) {
      if (sheetHeaderCandidates.includes(header[i])) {
        sheetColIndex = i;
        break;
      }
    }

    let startRow = 0;

    if (sheetColIndex >= 0) {
      startRow = 1;
    } else {
      // 沒有 header 時，預設第一欄就是 sheet_id。
      sheetColIndex = 0;
      startRow = 0;
    }

    const out = [];
    const seen = new Set();

    for (let r = startRow; r < rows.length; r += 1) {
      const row = rows[r];
      const value = normalizeSheetId(row[sheetColIndex]);

      if (!value) continue;

      if (!seen.has(value)) {
        seen.add(value);
        out.push(value);
      }
    }

    return out;
  }

  function parseCsvLine(line) {
    const out = [];
    let cur = "";
    let inQuote = false;

    for (let i = 0; i < line.length; i += 1) {
      const ch = line[i];
      const next = line[i + 1];

      if (ch === '"' && inQuote && next === '"') {
        cur += '"';
        i += 1;
        continue;
      }

      if (ch === '"') {
        inQuote = !inQuote;
        continue;
      }

      if (ch === "," && !inQuote) {
        out.push(cur);
        cur = "";
        continue;
      }

      cur += ch;
    }

    out.push(cur);

    return out;
  }

  function normalizeSheetId(value) {
    const s = String(value || "")
      .trim()
      .replace(/^["']+|["']+$/g, "")
      .toUpperCase();

    if (!s) return "";

    if (["NAN", "NONE", "NULL", "<NA>", "NAT"].includes(s)) {
      return "";
    }

    return s;
  }

  function clearCsvSheets() {
    const { dom, state } = MOD.State;

    state.filters.sheetIds = [];
    state.filters.sheetCsvFileName = "";

    if (dom.sheetCsvInput) {
      dom.sheetCsvInput.value = "";
    }

    renderCsvInfo();
  }

  function renderCsvInfo() {
    const { dom, state } = MOD.State;

    const sheetIds = Array.isArray(state.filters.sheetIds)
      ? state.filters.sheetIds
      : [];

    if (dom.sheetCsvInfo) {
      if (sheetIds.length) {
        const fileName = state.filters.sheetCsvFileName || "CSV";
        dom.sheetCsvInfo.textContent = `${fileName} / ${sheetIds.length} sheets`;
        dom.sheetCsvInfo.title = sheetIds.slice(0, 50).join(", ");
      } else {
        dom.sheetCsvInfo.textContent = "未選擇";
        dom.sheetCsvInfo.title = "";
      }
    }

    if (dom.sheetCsvClearBtn) {
      dom.sheetCsvClearBtn.style.display = sheetIds.length ? "" : "none";
    }
  }

  function renderToolSelect() {
    const { dom, state } = MOD.State;
    if (!dom.toolSelect) return;

    dom.toolSelect.innerHTML = "";

    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "--line--";
    placeholder.selected = !state.filters.tool && !state.filters.lineId;
    dom.toolSelect.appendChild(placeholder);

    const options = getLineOptions();

    options.forEach(function (lineId) {
      const opt = document.createElement("option");
      opt.value = lineId;
      opt.textContent = lineId;
      opt.selected = lineId === (state.filters.lineId || state.filters.tool);
      dom.toolSelect.appendChild(opt);
    });
  }

  function getLineOptions() {
    const cfg = MOD.State.getConfig();
    const featureCfg = MOD.State.getFeatureConfig ? MOD.State.getFeatureConfig() : {};

    if (Array.isArray(featureCfg.toolOptions) && featureCfg.toolOptions.length) {
      return featureCfg.toolOptions;
    }

    if (Array.isArray(cfg.lineOptions) && cfg.lineOptions.length) {
      return cfg.lineOptions;
    }

    return defaultLineOptions();
  }

  function defaultLineOptions() {
    const out = [];
    for (let i = 1; i <= 7; i += 1) {
      out.push(`CAPIC${i}`);
    }
    return out;
  }

  function renderSheetRadios(sheetTypes) {
    const { dom, state } = MOD.State;
    if (!dom.sheetRadios) return;

    dom.sheetRadios.innerHTML = "";

    dom.sheetRadios.appendChild(
      createRadioItem("", "全部", !state.filters.sheetType)
    );

    sheetTypes.forEach(function (type) {
      dom.sheetRadios.appendChild(
        createRadioItem(type, type, type === state.filters.sheetType)
      );
    });
  }

  function createRadioItem(value, text, checked) {
    const label = document.createElement("label");
    label.className = "cell-aoi-to-array-radio-item";

    const input = document.createElement("input");
    input.type = "radio";
    input.name = "cell-aoi-to-array-sheet-type";
    input.value = value;
    input.checked = checked;

    const span = document.createElement("span");
    span.textContent = text;

    label.appendChild(input);
    label.appendChild(span);

    return label;
  }

  function collect() {
    const { dom, state } = MOD.State;

    const checkedSheetType = dom.sheetRadios
      ? dom.sheetRadios.querySelector("input[type='radio']:checked")
      : null;

    const lineId = dom.toolSelect ? dom.toolSelect.value || "" : "";

    const sheetIds = Array.isArray(state.filters.sheetIds)
      ? state.filters.sheetIds
      : [];

    state.filters = Object.assign({}, state.filters, {
      startDate: dom.startDate ? dom.startDate.value || "" : "",
      endDate: dom.endDate ? dom.endDate.value || "" : "",

      // 保留 tool 給舊前端相容；後端會把 tool 視為 line_id
      tool: lineId,

      // 真正篩選 api_aoi_summary.line_id
      lineId: lineId,

      // 機台別 select 不控制 source_op_id
      sourceOpId: "",

      sheetType: checkedSheetType ? checkedSheetType.value : "",
      sheetId: dom.sheetInput ? (dom.sheetInput.value || "").trim().toUpperCase() : "",

      // CSV 多片 sheet 查詢
      sheetIds: sheetIds,
      sheetCsvFileName: state.filters.sheetCsvFileName || ""
    });

    return state.filters;
  }
})();