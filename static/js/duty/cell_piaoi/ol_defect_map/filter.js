






// static/js/duty/cell_piaoi/ol_defect_map/filters.js
(function () {
    const Bus = window.OLDefectMapBus;
    const State = window.OLDefectMapState;
  
    if (!Bus || !State) {
      console.error("[ol-defect-map][filters] dependencies missing", {
        hasBus: !!Bus,
        hasState: !!State,
      });
      return;
    }
  
    const DD_OPEN_CLASS = "open";
    const DD_WRAP_CLASS = "ol-defect-map-multi-dd";
    const DD_BTN_CLASS = "ol-defect-map-multi-dd-btn";
    const DD_LIST_CLASS = "ol-defect-map-multi-dd-list";
  
    let docClickWired = false;
  
    function closeAllDropdowns(exceptWrap = null) {
      document.querySelectorAll(`.${DD_WRAP_CLASS}.${DD_OPEN_CLASS}`).forEach((el) => {
        if (exceptWrap && el === exceptWrap) return;
        el.classList.remove(DD_OPEN_CLASS);
      });
    }
  
    function wireDocumentCloseOnce() {
      if (docClickWired) return;
      docClickWired = true;
  
      document.addEventListener("click", (e) => {
        const inside = e.target.closest?.(`.${DD_WRAP_CLASS}`);
        if (!inside) {
          closeAllDropdowns();
        }
      });
    }
  
    function normalizeItemList(items) {
      return (items || [])
        .map((v) => String(v ?? "").trim())
        .filter(Boolean);
    }
  
    function ensureSelectedSet(selectedSet) {
      if (selectedSet instanceof Set) return selectedSet;
      return new Set();
    }
  
    function createMultiDropdown({
      hostId,
      title,
      items,
      selectedSet,
      defaultAll = false,
      onApply,
      btnEmptyText,
    }) {
      const host = document.getElementById(hostId);
      if (!host) {
        console.warn("[ol-defect-map][filters] host not found:", hostId);
        return;
      }
  
      wireDocumentCloseOnce();
  
      const itemList = normalizeItemList(items);
      const realSelectedSet = ensureSelectedSet(selectedSet);
  
      if (defaultAll && realSelectedSet.size === 0) {
        itemList.forEach((v) => realSelectedSet.add(v));
      }
  
      host.innerHTML = "";
  
      const wrap = document.createElement("div");
      wrap.className = DD_WRAP_CLASS;
  
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = DD_BTN_CLASS;
  
      const panel = document.createElement("div");
      panel.className = DD_LIST_CLASS;
  
      const head = document.createElement("div");
      head.className = "ol-defect-map-multi-dd-head";
  
      const headTitle = document.createElement("div");
      headTitle.className = "ol-defect-map-multi-dd-title";
      headTitle.textContent = title;
  
      const actions = document.createElement("div");
      actions.className = "ol-defect-map-multi-dd-actions";
  
      const btnToggle = document.createElement("button");
      btnToggle.type = "button";
      btnToggle.className = "ol-defect-map-multi-dd-action";
  
      actions.append(btnToggle);
      head.append(headTitle, actions);
  
      const body = document.createElement("div");
      body.className = "ol-defect-map-multi-dd-body";
  
      function checkedValues() {
        return [...body.querySelectorAll('input[type="checkbox"]:checked')]
          .map((el) => el.value);
      }
  
      function setButtonText(vals) {
        if (!vals || vals.length === 0) {
          btn.textContent = btnEmptyText || `${title}（未選）`;
          return;
        }
  
        if (vals.length <= 3) {
          btn.textContent = `${title}：${vals.join(", ")}`;
          return;
        }
  
        btn.textContent = `${title}：已選 ${vals.length} 項`;
      }
  
      function syncToggleText() {
        const boxes = [...body.querySelectorAll('input[type="checkbox"]')];
        const allChecked = boxes.length > 0 && boxes.every((b) => b.checked);
        btnToggle.textContent = allChecked ? "清空" : "全選";
      }
  
      function syncSelectedSet(vals) {
        realSelectedSet.clear();
        vals.forEach((v) => realSelectedSet.add(v));
      }
  
      itemList.forEach((val) => {
        const label = document.createElement("label");
        label.className = "ol-defect-map-multi-dd-option";
  
        const chk = document.createElement("input");
        chk.type = "checkbox";
        chk.value = val;
        chk.checked = realSelectedSet.has(val);
  
        const text = document.createElement("span");
        text.textContent = val;
  
        label.append(chk, text);
        body.appendChild(label);
      });
  
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
  
        closeAllDropdowns(wrap);
        wrap.classList.toggle(DD_OPEN_CLASS);
      });
  
      panel.addEventListener("click", (e) => {
        e.stopPropagation();
      });
  
      btnToggle.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
  
        const boxes = [...body.querySelectorAll('input[type="checkbox"]')];
        const allChecked = boxes.length > 0 && boxes.every((b) => b.checked);
  
        boxes.forEach((b) => {
          b.checked = !allChecked;
        });
  
        const vals = checkedValues();
        syncSelectedSet(vals);
        setButtonText(vals);
        syncToggleText();
  
        if (typeof onApply === "function") {
          onApply(new Set(vals));
        }
      });
  
      body.addEventListener("change", (e) => {
        e.stopPropagation();
  
        const vals = checkedValues();
        syncSelectedSet(vals);
        setButtonText(vals);
        syncToggleText();
  
        if (typeof onApply === "function") {
          onApply(new Set(vals));
        }
      });
  
      panel.append(head, body);
      wrap.append(btn, panel);
      host.appendChild(wrap);
  
      setButtonText([...realSelectedSet]);
      syncToggleText();
    }
  
    function buildSizeFilters() {
      State.filters = State.filters || {};
  
      if (!(State.filters.sizeSet instanceof Set)) {
        State.filters.sizeSet = new Set(["S", "M", "L", "O"]);
      }
  
      createMultiDropdown({
        hostId: "ol-defect-map-size-filter-host",
        title: "Size",
        items: ["S", "M", "L", "O"],
        selectedSet: State.filters.sizeSet,
        defaultAll: true,
        btnEmptyText: "Size（未選）",
        onApply: () => Bus.emit("map-refresh"),
      });
    }
  
    function buildTypeFilters() {
      State.filters = State.filters || {};
  
      if (!(State.filters.typeSetSelected instanceof Set)) {
        State.filters.typeSetSelected = new Set();
      }
  
      const types = Array.from(State.typeSet || [])
        .map((v) => String(v ?? "").trim())
        .filter(Boolean)
        .sort();
  
      const host = document.getElementById("ol-defect-map-type-filter-host");
  
      if (!types.length) {
        if (host) host.innerHTML = "";
        console.log("[ol-defect-map][filters] type filters skipped: no types yet");
        return;
      }
  
      const prevSelected = new Set(State.filters.typeSetSelected || []);
      const prevTypes = new Set(State._lastTypeOptions || []);
  
      const wasAllSelected =
        prevTypes.size === 0 ||
        [...prevTypes].every((t) => prevSelected.has(t));
  
      if (wasAllSelected) {
        State.filters.typeSetSelected = new Set(types);
      } else {
        State.filters.typeSetSelected = new Set(
          [...prevSelected].filter((v) => types.includes(v))
        );
      }
  
      State._lastTypeOptions = [...types];
  
      createMultiDropdown({
        hostId: "ol-defect-map-type-filter-host",
        title: "Type",
        items: types,
        selectedSet: State.filters.typeSetSelected,
        defaultAll: false,
        btnEmptyText: "Type（未選）",
        onApply: () => Bus.emit("map-refresh"),
      });
    }
  
    window.OLDefectMapFilterController = {
      createMultiDropdown,
      buildSizeFilters,
      buildTypeFilters,
      closeAllDropdowns,
    };
  })();
  
  
  
  
  