// static/js/aoi_density/filter.js
// 右側篩選（以 ParamDict.filtetItemKeyDict + ParamDict.filterOptionDict 動態建置 MultiDD）
(function(){
  const AOI = (window.AOI_DENSITY = window.AOI_DENSITY || {});
  AOI.Filter = AOI.Filter || {};

  const $  = (sel, root=document) => root.querySelector(sel);

  function selectIdOf(key){ return `f-${key}`; }
  function hostIdOf(key){ return `host-${key}`; }

  function ensureDynHostsContainer(){
    const aside = $('#aoi_density-right');
    if (!aside) return null;
    let dyn = $('#aoi_density-dynhosts');
    if (!dyn) {
      dyn = document.createElement('div');
      dyn.id = 'aoi_density-dynhosts';
      const actions = $('#aoi_density-right .filter-actions');
      if (actions && actions.parentElement) {
        actions.parentElement.insertAdjacentElement('afterend', dyn);
      } else {
        aside.appendChild(dyn);
      }
    }
    return dyn;
  }

  function getDisplayName(cfgKey){
    const map = AOI.state.paramDict?.filtetItemKeyDict || {};
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

  function getOptionsOf(key){
    const dict = AOI.state.paramDict?.filterOptionDict || {};
    const arr = dict?.[key];
    if (Array.isArray(arr)) return arr.slice();
    return [];
  }

  
  AOI.Filter.ensureWidgets = function(){
    const cfgMap  = AOI.state.paramDict?.filtetItemKeyDict || {};
    const keys = Object.keys(cfgMap);
    if (!keys.length) return;
  
    const dynHosts = ensureDynHostsContainer();
    if (!dynHosts) return;
    
    AOI.mdd = AOI.mdd || {};
    let didDefaultAny = false;
  
    keys.forEach((key)=>{
      const title = getDisplayName(key);
      let opts  = getOptionsOf(key); // 原始 options
      const host = ensureOneHost(dynHosts, key);
      const selectId = selectIdOf(key);
  
      if (AOI.mdd[key]) {
        AOI.mdd[key].title = title;
        AOI.mdd[key].updateOptions(opts);
      } else {
        AOI.mdd[key] = new AOI.MultiDD({
          hostId: host.id,
          selectId,
          options: opts,
          title,
          onChange: ()=>{/* Router 以事件代理監聽 select 改變 */}
        });
      }
  
      // 若目前沒有選取值，預設選取「當前 options」
      const cur = AOI.mdd[key].getSelected();
      if ((!cur || cur.length === 0) && opts?.length) {
        AOI.mdd[key].setSelected(opts);
        const sel = document.getElementById(selectId);
        sel?.dispatchEvent(new Event('change', {bubbles:true}));
        didDefaultAny = true;
      }
    });
  
    if (didDefaultAny) {
      const dynFirstSelect = dynHosts.querySelector('select[id^="f-"]');
      dynFirstSelect?.dispatchEvent(new Event('change', {bubbles:true}));
    }
  };
  
  // 4) 首次資料就緒後，先建立篩選器，再用預設第一個 sub tab（或你當下的 tabKey）觸發一次套用
  document.addEventListener('aoi_density:data-ready', ()=>{
    AOI.Filter.ensureWidgets();
    // 若希望進頁就依目前 activeSubTab 套一次（可選）
    const subTabsMap = AOI.state.paramDict?.SubTabsFilterDefaultDict || {};
    const firstKey = Object.keys(subTabsMap)[0];
    if (firstKey) AOI.applySubTab(firstKey);
  });
  
  // 暴露工具
  AOI.selectIdOf = selectIdOf;
  AOI.hostIdOf   = hostIdOf;
})();