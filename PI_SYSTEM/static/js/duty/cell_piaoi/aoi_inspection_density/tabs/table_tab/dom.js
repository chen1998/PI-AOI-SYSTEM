// static/js/aoi_inspection_density/tabs/table_tab/dom.js
(function () {
    const AOI = (window.AOI_INSPECTION = window.AOI_INSPECTION || {});
    const MOD = (AOI.TableTab = AOI.TableTab || {});
    const NS = (MOD.DOM = MOD.DOM || {});
  
    const STATE = AOI.TableTab && AOI.TableTab.State;
  
    // =========================
    // 基本工具
    // =========================
    function $(sel, root = document) {
      return root.querySelector(sel);
    }
  
    function $$(sel, root = document) {
      return Array.from(root.querySelectorAll(sel));
    }
  
    function createEl(tag, opts = {}) {
      const el = document.createElement(tag);
      if (opts.id) el.id = opts.id;
      if (opts.className) el.className = opts.className;
      if (opts.text != null) el.textContent = String(opts.text);
      if (opts.html != null) el.innerHTML = String(opts.html);
  
      if (opts.attrs && typeof opts.attrs === "object") {
        Object.entries(opts.attrs).forEach(([k, v]) => {
          if (v != null) el.setAttribute(k, String(v));
        });
      }
      return el;
    }
  
    function clearEl(el) {
      if (!el) return;
      while (el.firstChild) el.removeChild(el.firstChild);
    }
  
    // =========================
    // Selector 常數
    // =========================
    const DOM = {
      // root / main blocks
      specRoot: "#aoi-inspection-density-spec-table",
      specLeft: "#aoi-inspection-density-spec-left",
      specRight: "#aoi-inspection-density-spec-right",
      specInfo: "#aoi-inspection-density-spec-info",
      specInfoHead: "#aoi-inspection-density-spec-info .aoi-inspection-density-spec-info-head",
      specTitle: "#aoi-inspection-density-spec-info .aoi-inspection-density-spec-info-head .t",
  
      // table
      specTable: "#aoi-inspection-density-spec-table-main",
      specTableWrap: "#aoi-inspection-density-spec-left .table-wrap",
      specTableScroll: "#aoi-inspection-density-spec-left .table-scroll",
  
      // dynamic filter area
      specDynHosts: "#aoi-inspection-density-spec-dynhosts",
  
      // filter title / item
      specDateRow: "#aoi-inspection-density-spec-date-row",
      specFilterPanelTitle: ".aoi-inspection-density-spec-filter-panel-title",
      specFilterItem: "#aoi-inspection-density-spec-right .aoi-inspection-density-spec-filter-item",
  
      // date inputs
      specStart: "#aoi-inspection-density-spec-start",
      specEnd: "#aoi-inspection-density-spec-end",
  
      // buttons
      specApply: "#aoi-inspection-density-spec-apply",
      specClear: "#aoi-inspection-density-spec-clear",
  
      // dynamic generated
      specPager: "#aoi-inspection-density-spec-pager",
      specCount: "#aoi-inspection-density-spec-count",
      specBottomActions: ".aoi-inspection-density-spec-filter-bottom-actions",
      specBottomClearBtn: "#aoi-inspection-density-spec-clear-bottom",
      specAddPanel: "#aoi-inspection-density-spec-add-panel",
      specHeaderActions: ".spec-header-actions",
  
      // edit summary dynamic cancel btn
      editSummaryCancelBtn: "#aoi-inspection-density-spec-edit-summary-cancel"
    };
  
    // =========================
    // getter
    // =========================
    function getSpecDateRowEl() {
      return $(DOM.specDateRow);
    }

    function getSpecRootEl() {
      return $(DOM.specRoot);
    }
  
    function getSpecLeftEl() {
      return $(DOM.specLeft);
    }
  
    function getSpecRightEl() {
      return $(DOM.specRight);
    }
  
    function getSpecInfoEl() {
      return $(DOM.specInfo);
    }
  
    function getSpecInfoHeadEl() {
      return $(DOM.specInfoHead);
    }
  
    function getSpecTitleEl() {
      return $(DOM.specTitle);
    }
  
    function getSpecTableEl() {
      return $(DOM.specTable);
    }
  
    function getSpecTheadEl() {
      const table = getSpecTableEl();
      return table ? table.querySelector("thead") : null;
    }
  
    function getSpecTbodyEl() {
      const table = getSpecTableEl();
      return table ? table.querySelector("tbody") : null;
    }
  
    function getSpecTableWrapEl() {
      return $(DOM.specTableWrap);
    }
  
    function getSpecTableScrollEl() {
      return $(DOM.specTableScroll);
    }
  
    function getSpecDynHostsEl() {
      return $(DOM.specDynHosts);
    }
  
    function getSpecStartInput() {
      return $(DOM.specStart);
    }
  
    function getSpecEndInput() {
      return $(DOM.specEnd);
    }
  
    function getSpecApplyBtn() {
      return $(DOM.specApply);
    }
  
    function getSpecClearBtn() {
      return $(DOM.specClear);
    }
  
    function getSpecHeaderActionsEl() {
      const head = getSpecInfoHeadEl();
      if (!head) return null;
      return head.querySelector(DOM.specHeaderActions);
    }
  
    // =========================
    // ensure helpers
    // =========================
    function ensureSpecHeaderActions() {
      const head = getSpecInfoHeadEl();
      if (!head) return null;
  
      let actions = head.querySelector(".spec-header-actions");
      if (!actions) {
        actions = createEl("div", { className: "spec-header-actions" });
        head.appendChild(actions);
      }
      return actions;
    }
  
    function ensureSpecDynHosts() {
      const aside = getSpecRightEl();
      if (!aside) return null;
  
      let dyn = getSpecDynHostsEl();
      if (!dyn) {
        dyn = createEl("div", { id: "aoi-inspection-density-spec-dynhosts" });
        aside.appendChild(dyn);
      }
      return dyn;
    }
  
    function ensurePager() {
      const wrap = getSpecTableWrapEl();
      if (!wrap) return null;
  
      let pager = $(DOM.specPager);
      if (!pager) {
        pager = createEl("div", {
          id: "aoi-inspection-density-spec-pager",
          className: "aoi-inspection-density-spec-pager"
        });
        wrap.appendChild(pager);
      }
      return pager;
    }
  
    function ensureFilterCountSpan() {
      const title = $(DOM.specFilterPanelTitle, getSpecRightEl() || document);
      if (!title) return null;
  
      let span = $(DOM.specCount);
      if (!span) {
        span = createEl("span", {
          id: "aoi-inspection-density-spec-count",
          className: "spec-filter-count"
        });
        title.appendChild(span);
      }
      return span;
    }
  
    function ensureBottomClearButton() {
      const aside = getSpecRightEl();
      if (!aside) return null;
  
      let box = aside.querySelector(DOM.specBottomActions);
      if (!box) {
        box = createEl("div", {
          className: "aoi-inspection-density-spec-filter-bottom-actions"
        });
  
        const btn = createEl("button", {
          id: "aoi-inspection-density-spec-clear-bottom",
          className: "btn btn-xs btn-secondary",
          text: "清空篩選"
        });
  
        box.appendChild(btn);
        aside.appendChild(box);
      }
  
      return $(DOM.specBottomClearBtn);
    }
  
    function ensureAddPanel() {
      let panel = $(DOM.specAddPanel);
      if (panel) return panel;
  
      const left = getSpecLeftEl();
      if (!left) return null;
  
      panel = createEl("section", {
        id: "aoi-inspection-density-spec-add-panel",
        className: "card-sub spec-add-panel"
      });
      panel.style.display = "none";
  
      const tableWrap = getSpecTableWrapEl();
      if (tableWrap) {
        left.insertBefore(panel, tableWrap);
      } else {
        left.appendChild(panel);
      }
  
      return panel;
    }
  
    function ensureEditSummaryCancelBtn() {
      let btn = $(DOM.editSummaryCancelBtn);
      if (btn) return btn;
  
      const actions = ensureSpecHeaderActions();
      if (!actions) return null;
  
      btn = createEl("button", {
        id: "aoi-inspection-density-spec-edit-summary-cancel",
        className: "btn-spec-action",
        text: "取消"
      });
      actions.appendChild(btn);
      return btn;
    }
  
    // =========================
    // table class helper
    // =========================
    function syncTableTabClass(tabKey) {
      const table = getSpecTableEl();
      if (!table || !STATE || !STATE.SpecState) return;
  
      const SpecState = STATE.SpecState;
  
      if (SpecState.lastTabClass) {
        table.classList.remove(SpecState.lastTabClass);
      }
  
      if (tabKey) {
        table.classList.add(tabKey);
        SpecState.lastTabClass = tabKey;
      } else {
        SpecState.lastTabClass = null;
      }
    }
  
    // =========================
    // 清理 helper
    // =========================
    function hideAddPanel() {
      const panel = $(DOM.specAddPanel);
      if (panel) {
        panel.style.display = "none";
        clearEl(panel);
      }
    }
  
    function removeEditSummaryCancelBtn() {
      const btn = $(DOM.editSummaryCancelBtn);
      if (btn) btn.remove();
    }
  
    function clearPager() {
      const pager = $(DOM.specPager);
      if (pager) clearEl(pager);
    }
  
    function clearDynHosts() {
      const dyn = getSpecDynHostsEl();
      if (dyn) clearEl(dyn);
    }
  
    // =========================
    // export
    // =========================
    NS.$ = $;
    NS.$$ = $$;
    NS.createEl = createEl;
    NS.clearEl = clearEl;
  
    NS.DOM = DOM;
    NS.getSpecDateRowEl = getSpecDateRowEl;
    NS.getSpecRootEl = getSpecRootEl;
    NS.getSpecLeftEl = getSpecLeftEl;
    NS.getSpecRightEl = getSpecRightEl;
    NS.getSpecInfoEl = getSpecInfoEl;
    NS.getSpecInfoHeadEl = getSpecInfoHeadEl;
    NS.getSpecTitleEl = getSpecTitleEl;
    NS.getSpecTableEl = getSpecTableEl;
    NS.getSpecTheadEl = getSpecTheadEl;
    NS.getSpecTbodyEl = getSpecTbodyEl;
    NS.getSpecTableWrapEl = getSpecTableWrapEl;
    NS.getSpecTableScrollEl = getSpecTableScrollEl;
    NS.getSpecDynHostsEl = getSpecDynHostsEl;
    NS.getSpecStartInput = getSpecStartInput;
    NS.getSpecEndInput = getSpecEndInput;
    NS.getSpecApplyBtn = getSpecApplyBtn;
    NS.getSpecClearBtn = getSpecClearBtn;
    NS.getSpecHeaderActionsEl = getSpecHeaderActionsEl;
  
    NS.ensureSpecHeaderActions = ensureSpecHeaderActions;
    NS.ensureSpecDynHosts = ensureSpecDynHosts;
    NS.ensurePager = ensurePager;
    NS.ensureFilterCountSpan = ensureFilterCountSpan;
    NS.ensureBottomClearButton = ensureBottomClearButton;
    NS.ensureAddPanel = ensureAddPanel;
    NS.ensureEditSummaryCancelBtn = ensureEditSummaryCancelBtn;
  
    NS.syncTableTabClass = syncTableTabClass;
  
    NS.hideAddPanel = hideAddPanel;
    NS.removeEditSummaryCancelBtn = removeEditSummaryCancelBtn;
    NS.clearPager = clearPager;
    NS.clearDynHosts = clearDynHosts;
  })();