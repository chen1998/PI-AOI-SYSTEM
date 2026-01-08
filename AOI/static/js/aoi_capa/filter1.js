// static/js/aoi_capa/filter.js
// 右側篩選（以 ParamDict.filtetItemKeyDict + ParamDict.FilterDefaultDict 動態建置 MultiDD）— CAPA 版
(function(){
  const AOI = (window.AOI_CAPA = window.AOI_CAPA || {});
  AOI.Filter = AOI.Filter || {};

  const $  = (sel, root=document) => root.querySelector(sel);

  function selectIdOf(key){ return `capa-f-${key}`; }
  function hostIdOf(key){ return `capa-host-${key}`; }

  function ensureDynHostsContainer(){
    const aside = $('#aoi_capa-right');
    if (!aside) return null;
    let dyn = $('#aoi_capa-dynhosts');
    if (!dyn) {
      dyn = document.createElement('div');
      dyn.id = 'aoi_capa-dynhosts';
      const actions = $('#aoi_capa-right .aoi_capa-filter-actions');
      if (actions && actions.parentElement) {
        actions.parentElement.insertAdjacentElement('afterend', dyn);
      } else {
        aside.appendChild(dyn);
      }
    }
    return dyn;
  }

  function getDisplayName(cfgKey){
    // 後端 filtetItemKeyDict: { aoi: 'aoi', pi_type: 'pi_type' } → 你可以改成中文顯示
    const map = AOI.state?.paramDict?.filtetItemKeyDict || {};
    return map?.[cfgKey] || cfgKey;
  }

  function ensureOneHost(dynHostsEl, key){
    let host = $('#'+hostIdOf(key));
    if (!host) {
      host = document.createElement('div');
      host.className = 'multi-dd-host';
      host.id = hostIdOf(key);
      dynHostsEl.appendChild(host);
    }
    return host;
  }

  // CAPA 版：option 候選值就直接用 FilterDefaultDict[key]
  function getOptionsOf(key){
    const dict = AOI.state?.paramDict?.FilterDefaultDict || {};
    const arr = dict?.[key];
    if (Array.isArray(arr)) return arr.slice();
    if (arr != null) return [arr];
    return [];
  }

  // 根據 FilterDefaultDict 算「預設勾選值」
  function getDefaultSelected(key, opts){
    const defMap = AOI.state?.paramDict?.FilterDefaultDict || {};
    const preset = defMap?.[key];

    if (!opts || !opts.length) return [];

    // 沒設定 → 視為全選
    if (preset == null) return opts.slice();

    // [] → 視為全選
    if (Array.isArray(preset) && preset.length === 0) return opts.slice();

    // 有給清單 → 取和 options 的交集
    const list = Array.isArray(preset) ? preset : [preset];
    const inter = opts.filter(v => list.includes(v));
    return inter.length ? inter : opts.slice();  // 無交集 fallback 全選
  }

  // ========= 建立右側 MultiDD =========
  AOI.Filter.ensureWidgets = function(){
    const cfgMap  = AOI.state?.paramDict?.filtetItemKeyDict || {};
    const keys = Object.keys(cfgMap);
    if (!keys.length) return;

    const dynHosts = ensureDynHostsContainer();
    if (!dynHosts) return;
    
    AOI.mdd = AOI.mdd || {};
    let didDefaultAny = false;

    keys.forEach((key)=>{
      const title   = getDisplayName(key);  // 顯示名稱
      const opts    = getOptionsOf(key);    // option 候選值
      const host    = ensureOneHost(dynHosts, key);
      const selectId= selectIdOf(key);
      const defSel  = getDefaultSelected(key, opts);

      if (AOI.mdd[key]) {
        AOI.mdd[key].title = title;
        AOI.mdd[key].updateOptions(opts);
      } else {
        AOI.mdd[key] = new AOI.MultiDD({
          hostId: host.id,
          selectId,
          options: opts,
          title,
          onChange: ()=>{/* Router / chart 可用事件或 AOI.readFiltersFromUI 取值 */}
        });
      }

      // 若目前沒有選取值 → 用 FilterDefaultDict 當預設
      const cur = AOI.mdd[key].getSelected();
      if ((!cur || cur.length === 0) && defSel?.length) {
        AOI.mdd[key].setSelected(defSel);
        const sel = document.getElementById(selectId);
        sel?.dispatchEvent(new Event('change', {bubbles:true}));
        didDefaultAny = true;
      }
    });

    if (didDefaultAny) {
      const dynFirstSelect = dynHosts.querySelector('select[id^="capa-f-"]');
      dynFirstSelect?.dispatchEvent(new Event('change', {bubbles:true}));
    }
  };

  // ========= Filter 讀取工具 =========
  // 回傳：{ aoi: [...], pi_type: [...] }
  AOI.readFiltersFromUI = function(){
    const out = {};
    const cfgMap  = AOI.state?.paramDict?.filtetItemKeyDict || {};
    const keys = Object.keys(cfgMap);
    keys.forEach(key=>{
      const widget = AOI.mdd?.[key];
      if (widget) {
        const vals = widget.getSelected();
        if (vals && vals.length) out[key] = vals.slice();
      } else {
        const sel = document.getElementById(selectIdOf(key));
        if (sel) {
          const vals = Array.from(sel.options)
            .filter(o=>o.selected)
            .map(o=>o.value);
          if (vals.length) out[key] = vals;
        }
      }
    });
    return out;
  };

  // ========= 資料就緒時啟動 =========
  // 1) 若你在 aoi_capa/api.js 裡有這樣 dispatch：
  //    document.dispatchEvent(new CustomEvent('aoi_capa:data-ready', { detail: AOI.state }));
  document.addEventListener('aoi_capa:data-ready', (ev)=>{
    if (ev && ev.detail) {
      AOI.state = ev.detail;   // { rows, paramDict, ... }
    }
    AOI.Filter.ensureWidgets();
  });

  // 2) 也支援用 window 事件叫 AOI_CAPA_SUMMARY_UPDATED（如果你已經這樣寫）
  window.addEventListener("AOI_CAPA_SUMMARY_UPDATED", (ev)=>{
    if (ev && ev.detail) {
      AOI.state = ev.detail;
    }
    AOI.Filter.ensureWidgets();
  });

  // 暴露工具（給其他 JS 用）
  AOI.selectIdOf = selectIdOf;
  AOI.hostIdOf   = hostIdOf;
})();