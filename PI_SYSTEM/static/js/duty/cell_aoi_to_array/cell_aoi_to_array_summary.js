// static/js/duty/cell_aoi_to_array/cell_aoi_to_array_summary.js
(function () {
  "use strict";

  window.CELL_AOI_TO_ARRAY = window.CELL_AOI_TO_ARRAY || {};
  const MOD = window.CELL_AOI_TO_ARRAY;

  MOD.Summary = {
    render,
    clear
  };

  function render() {
    if (!MOD.State || !MOD.State.dom || !MOD.State.state) return;

    const { dom, state } = MOD.State;
    const cfg = MOD.State.getConfig ? MOD.State.getConfig() : {};

    if (!dom.summaryCards) return;

    dom.summaryCards.innerHTML = "";

    const cards = Array.isArray(cfg.summaryCards) ? cfg.summaryCards : [];

    if (!cards.length) {
      dom.summaryCards.style.display = "none";
      return;
    }

    dom.summaryCards.style.display = "";

    cards.forEach(function (card) {
      const value = state.summary && Object.prototype.hasOwnProperty.call(state.summary, card.key)
        ? state.summary[card.key]
        : "-";

      const el = document.createElement("article");
      el.className = "cell-aoi-to-array-summary-card";

      const label = document.createElement("div");
      label.className = "cell-aoi-to-array-summary-label";
      label.textContent = card.label || card.key || "";
      el.appendChild(label);

      const valueEl = document.createElement("div");
      valueEl.className = "cell-aoi-to-array-summary-value";
      valueEl.textContent = formatSummaryValue(value);
      el.appendChild(valueEl);

      if (card.sub) {
        const sub = document.createElement("div");
        sub.className = "cell-aoi-to-array-summary-sub";
        sub.textContent = card.sub;
        el.appendChild(sub);
      }

      dom.summaryCards.appendChild(el);
    });
  }

  function clear() {
    if (!MOD.State || !MOD.State.dom) return;

    const { dom } = MOD.State;

    if (dom.summaryCards) {
      dom.summaryCards.innerHTML = "";
    }
  }

  function formatSummaryValue(value) {
    if (value === null || value === undefined || value === "") return "-";

    if (Array.isArray(value)) {
      return value.join("\n");
    }

    if (typeof value === "object") {
      try {
        return JSON.stringify(value, null, 2);
      } catch (err) {
        return String(value);
      }
    }

    return String(value);
  }
})();






