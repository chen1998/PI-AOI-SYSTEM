// static/js/duty/cell_aoi_to_array/cell_aoi_to_array_ui.js
(function () {
  "use strict";

  window.CELL_AOI_TO_ARRAY = window.CELL_AOI_TO_ARRAY || {};
  const MOD = window.CELL_AOI_TO_ARRAY;

  MOD.UI = {
    escapeHtml,
    toDateInputValue,
    debounce,
    getPagerPages,
    createEl,
    clearEl,
    appendTd,
    createEmptyState
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function toDateInputValue(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }

  function debounce(fn, wait) {
    let timer = null;

    return function (...args) {
      window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        fn.apply(null, args);
      }, wait);
    };
  }

  function getPagerPages(current, total) {
    if (total <= 7) {
      return Array.from({ length: total }, function (_, i) {
        return i + 1;
      });
    }

    const pages = [1];

    if (current > 4) pages.push("...");

    const start = Math.max(2, current - 1);
    const end = Math.min(total - 1, current + 1);

    for (let i = start; i <= end; i += 1) {
      pages.push(i);
    }

    if (current < total - 3) pages.push("...");

    pages.push(total);
    return pages;
  }

  function createEl(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined && text !== null) el.textContent = text;
    return el;
  }

  function clearEl(el) {
    if (el) el.innerHTML = "";
  }

  function appendTd(tr, text, className) {
    const td = document.createElement("td");
    if (className) td.className = className;
    td.textContent = text ?? "";
    tr.appendChild(td);
    return td;
  }

  function createEmptyState(iconText, message) {
    const box = document.createElement("div");
    box.className = "cell-aoi-to-array-empty-state";

    const icon = document.createElement("div");
    icon.className = "cell-aoi-to-array-empty-icon";
    icon.textContent = iconText || "∅";
    box.appendChild(icon);

    const text = document.createElement("div");
    text.textContent = message || "查無資料";
    box.appendChild(text);

    return box;
  }
})();