// static/js/aoi_inspection_density/function/multidd.js
(function () {
  const AOI = (window.AOI_INSPECTION = window.AOI_INSPECTION || {});
  AOI.mdd = AOI.mdd || {};

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  function el(tag, attrs = {}) {
    const node = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => {
      if (k === "class") node.className = v;
      else node.setAttribute(k, v);
    });
    return node;
  }

  class MultiDD {
    constructor({ hostId, selectId, options = [], onChange, title = "" }) {
      this.hostId = hostId;
      this.selectId = selectId;
      this.options = Array.isArray(options) ? options.slice().sort() : [];
      this.selected = new Set();
      this.nodes = {};
      this.onChange = typeof onChange === "function" ? onChange : () => {};
      this.title = title || "";
      this.render();
    }

    render() {
      const host = $("#" + this.hostId);
      let select = $("#" + this.selectId);

      if (!host) {
        if (!select) {
          select = el("select", {
            id: this.selectId,
            multiple: "multiple",
            style: "display:none"
          });
          document.body.appendChild(select);
        }
        this._fillSelect(select, this.options);
        this.nodes = { select };
        return;
      }

      if (!select) {
        select = el("select", {
          id: this.selectId,
          multiple: "multiple",
          style: "display:none"
        });
        host.parentElement.insertBefore(select, host.nextSibling);
      }
      this._fillSelect(select, this.options);

      host.innerHTML = "";

      const wrap = el("div", { class: "multi-dd" });
      const btn = el("button", { class: "multi-dd-btn", type: "button" });
      this._updateBtnText(btn);

      const list = el("div", { class: "multi-dd-list", style: "display:none" });
      const search = el("input", {
        type: "text",
        class: "multi-dd-search",
        placeholder: "搜尋…"
      });
      const cont = el("div");
      const footer = el("div", { class: "multi-dd-footer" });
      const bToggle = el("button", { class: "btn btn-xs", type: "button" });

      footer.appendChild(bToggle);
      list.append(search, footer, cont);
      wrap.append(btn, list);
      host.appendChild(wrap);

      btn.addEventListener("click", () => {
        const open = list.style.display !== "none";
        $$(".multi-dd .multi-dd-list").forEach((x) => { x.style.display = "none"; });
        $$(".multi-dd").forEach((x) => x.classList.remove("open"));

        if (!open) {
          list.style.display = "";
          wrap.classList.add("open");
          search.focus();
        }
      });

      document.addEventListener("click", (ev) => {
        if (!wrap.contains(ev.target)) {
          list.style.display = "none";
          wrap.classList.remove("open");
        }
      });

      const updateFooterButton = () => {
        if (this.selected.size > 0) {
          bToggle.textContent = "清空";
          bToggle.classList.remove("btn-secondary");
        } else {
          bToggle.textContent = "全選";
          bToggle.classList.add("btn-secondary");
        }
      };

      const rebuildList = () => {
        const kw = search.value.trim().toLowerCase();
        cont.innerHTML = "";

        this.options
          .filter((v) => !kw || String(v).toLowerCase().includes(kw))
          .forEach((v) => {
            const row = el("label", { class: "multi-dd-item" });
            const ck = el("input", { type: "checkbox", value: v });
            ck.checked = this.selected.has(v);

            ck.addEventListener("change", () => {
              if (ck.checked) this.selected.add(v);
              else this.selected.delete(v);

              this._syncSelect(select);
              this._updateBtnText(btn);
              updateFooterButton();
              this.onChange(this.getSelected());
              select.dispatchEvent(new Event("change", { bubbles: true }));
            });

            const txt = el("span");
            txt.textContent = v;
            row.append(ck, txt);
            cont.appendChild(row);
          });
      };

      bToggle.addEventListener("click", () => {
        if (this.selected.size > 0) {
          this.clear();
        } else {
          this.setSelected(this.options.slice());
        }

        this._syncSelect(select);
        this._updateBtnText(btn);
        updateFooterButton();

        if (this.nodes?.rebuildList) this.nodes.rebuildList();
        this.onChange(this.getSelected());
        select.dispatchEvent(new Event("change", { bubbles: true }));
      });

      this._updateBtnText(btn);
      updateFooterButton();
      rebuildList();

      this.nodes = {
        host, wrap, btn, list, search, cont, select,
        rebuildList, bToggle, updateFooterButton
      };
    }

    updateOptions(options = []) {
      this.options = Array.isArray(options) ? options.slice().sort() : [];

      this.selected.forEach((v) => {
        if (!this.options.includes(v)) this.selected.delete(v);
      });

      if (this.nodes.select) this._fillSelect(this.nodes.select, this.options, this.selected);
      if (this.nodes.rebuildList) this.nodes.rebuildList();
      if (this.nodes.btn) this._updateBtnText(this.nodes.btn);
      if (this.nodes.updateFooterButton) this.nodes.updateFooterButton();
    }

    clear() {
      this.selected.clear();
      if (this.nodes.select) this._syncSelect(this.nodes.select);
      if (this.nodes.btn) this._updateBtnText(this.nodes.btn);
      if (this.nodes.search) this.nodes.search.value = "";
      if (this.nodes.rebuildList) this.nodes.rebuildList();
      if (this.nodes.updateFooterButton) this.nodes.updateFooterButton();
    }

    setSelected(vals = []) {
      this.selected = new Set(Array.isArray(vals) ? vals : []);
      if (this.nodes.select) this._syncSelect(this.nodes.select);
      if (this.nodes.btn) this._updateBtnText(this.nodes.btn);
      if (this.nodes.rebuildList) this.nodes.rebuildList();
      if (this.nodes.updateFooterButton) this.nodes.updateFooterButton();
    }

    getSelected() {
      return Array.from(this.selected);
    }

    _fillSelect(select, options, selectedSet = this.selected) {
      select.innerHTML = "";
      options.forEach((v) => {
        const o = el("option");
        o.value = v;
        o.textContent = v;
        o.selected = selectedSet.has(v);
        select.appendChild(o);
      });
    }

    _syncSelect(select) {
      Array.from(select.options).forEach((o) => {
        o.selected = this.selected.has(o.value);
      });
    }

    _updateBtnText(btn) {
      const n = this.selected.size;
      const all = this.options.length;
      const prefix = this.title ? `${this.title}：` : "";

      let suffix;
      if (all > 0 && n === all) suffix = "全選";
      else suffix = `已選 ${n} 項`;

      btn.textContent = prefix + suffix;
    }
  }

  AOI.MultiDD = MultiDD;
})();