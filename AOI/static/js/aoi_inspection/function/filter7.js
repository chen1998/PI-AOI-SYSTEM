// static/js/aoi_inspection/filter.js
// 右側篩選（以 ParamDict.filtetItemKeyDict + ParamDict.filterOptionDict 動態建置 MultiDD）
(function(){
  const AOI = (window.AOI_INSPECTION = window.AOI_INSPECTION || {});
  AOI.Filter = AOI.Filter || {};

  const $  = (sel, root=document) => root.querySelector(sel);

  function selectIdOf(key){ return `insp-f-${key}`; }
  function hostIdOf(key){ return `insp-host-${key}`; }

  function ensureDynHostsContainer(){
    const aside = $('#inspection-right');
    if (!aside) return null;
    let dyn = $('#inspection-dynhosts');
    if (!dyn) {
      dyn = document.createElement('div');
      dyn.id = 'inspection-dynhosts';
      const actions = $('#inspection-right .filter-actions');
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

  // === 新增：依 FilterDefaultDict 算這個 key 的預設勾選值 ===
  function getDefaultSelected(key, opts){
    const defMap = AOI.state.paramDict?.FilterDefaultDict || {};
    const preset = defMap[key];

    if (!opts || !opts.length) return [];

    // 沒設定這個 key → 視為全選
    if (preset == null) return opts.slice();

    // 空陣列 [] → 也視為全選
    if (Array.isArray(preset) && preset.length === 0) return opts.slice();

    // 有給清單 → 取和 options 的交集
    const list = Array.isArray(preset) ? preset : [preset];
    const inter = opts.filter(v => list.includes(v));
    return inter.length ? inter : opts.slice();  // 若沒交集就 fallback 全選
  }

  // ========= 建立右側 MultiDD =========
  AOI.Filter.ensureWidgets = function(){
    const cfgMap  = AOI.state.paramDict?.filtetItemKeyDict || {};
    const keys = Object.keys(cfgMap);
    if (!keys.length) return;
    //console.log('[INSPECTION Filter] cfgMap keys =', keys);
    const dynHosts = ensureDynHostsContainer();
    if (!dynHosts) return;
    
    AOI.mdd = AOI.mdd || {};
    let didDefaultAny = false;
    //console.log('AOI.mdd',AOI.mdd);
    keys.forEach((key)=>{
      const title = getDisplayName(key);
      const opts  = getOptionsOf(key);
      const host = ensureOneHost(dynHosts, key);
      const selectId = selectIdOf(key);
      const defSel = getDefaultSelected(key, opts);  
      /*console.log(key, 'opts',opts);
      console.log('defSel',defSel);*/
      if (AOI.mdd[key]) {
        AOI.mdd[key].title = title;
        AOI.mdd[key].updateOptions(opts);
      } else {
        AOI.mdd[key] = new AOI.MultiDD({
          hostId: host.id,
          selectId,
          options: opts,
          title,
          onChange: ()=>{/* Router 用事件代理監聽 select 改變 */}
        });
      }
  
      // 若目前沒有選取值，依 FilterDefaultDict 設定預設勾選
      const cur = AOI.mdd[key].getSelected();
      //console.log('cur',cur);
      if ((!cur || cur.length === 0) && defSel?.length) {
        //console.log(AOI.mdd[key]);
        AOI.mdd[key].setSelected(defSel);
        const sel = document.getElementById(selectId);
        sel?.dispatchEvent(new Event('change', {bubbles:true}));
        didDefaultAny = true;
      }
    });
  
    if (didDefaultAny) {
      const dynFirstSelect = dynHosts.querySelector('select[id^="insp-f-"]');
      dynFirstSelect?.dispatchEvent(new Event('change', {bubbles:true}));
    }
  };

  // ========= Filter 讀取工具 =========
  function parsePiHourToDate(s){
    if (!s) return null;
    if (/^\d{2}-\d{2}-\d{2}\s+\d{2}$/.test(s)){
      const [datePart,hh]=s.split(/\s+/);
      const [yy,mm,dd]=datePart.split("-").map(Number);
      return new Date(2000+yy,mm-1,dd,Number(hh),0,0);
    }
    const d=new Date(String(s).replace(" ","T"));
    return isNaN(d.getTime()) ? null : d;
  }

  AOI.readFiltersFromUI = function(){
    const out = {};
    const cfgMap  = AOI.state.paramDict?.filtetItemKeyDict || {};
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

  // ========= defect_size 用的 row 判斷工具 =========
  function rowMatchDefectSize(row, selectedSizes){
    if (!selectedSizes || !selectedSizes.length) return true;

    const dsMeta = AOI.state.paramDict?.DefectSize || {};
    const maskBits = dsMeta.maskBits || null;
    const maskKey  = dsMeta.maskKey  || "size_mask";
    const virtualKey = dsMeta.virtualKey || "available_sizes";

    // 1) 優先用 mask 判斷
    const rowMask = Number(row[maskKey] ?? 0);
    if (maskBits && rowMask > 0) {
      let wantMask = 0;
      selectedSizes.forEach(s=>{
        if (maskBits[s] != null) wantMask |= maskBits[s];
      });
      if (!wantMask) return true;  // 沒有有效的 bit，當作沒選
      return (rowMask & wantMask) !== 0;
    }

    // 2) 退回用 available_sizes 做交集判斷
    const av = row[virtualKey];
    if (Array.isArray(av) && av.length) {
      return selectedSizes.some(s => av.includes(s));
    }

    // 如果 row 上完全沒有 size 資訊，就當作不符合
    return false;
  }

  // ========= 解析 "S:1 M:0 L:2 O:0 T:3" 這種字串 =========
  function parseSizeStats(stat){
    const out = { S:0, M:0, L:0, O:0, T:0 };
    if (!stat) return out;

    if (typeof stat === "string"){
      const rx = /\b([SMLOT])\s*:\s*(\d+)/g;
      let m;
      while((m = rx.exec(stat)) !== null){
        const k = m[1].toUpperCase();
        const v = Number(m[2] || 0);
        if (k in out && Number.isFinite(v)) out[k] = v;
      }
      if (!/\bT\s*:/.test(stat)) {
        out.T = out.S + out.M + out.L + out.O;
      }
      return out;
    }

    if (typeof stat === "object"){
      out.S = Number(stat.S || 0);
      out.M = Number(stat.M || 0);
      out.L = Number(stat.L || 0);
      out.O = Number(stat.O || 0);
      out.T = Number(
        stat.T != null
          ? stat.T
          : (out.S + out.M + out.L + out.O)
      );
      return out;
    }

    return out;
  }

  // ========= 依 Filter / 日期 篩選 rows + 尺寸投影 =========
  AOI.getFiltered = function(opts){
    const dates   = (opts && opts.dates) || undefined;
    const filters = AOI.readFiltersFromUI();
    const rows    = AOI.state.rows || [];
    if (!rows.length) return [];

    // 日期區間
    let begin = null, end = null;
    if (dates && dates.length === 2 && dates[0] && dates[1]) {
      begin = new Date(dates[0] + "T00:00:00");
      end   = new Date(dates[1] + "T23:59:59");
    }

    // 先做「篩列」
    const outFiltered = rows.filter(r=>{
      // 先過日期
      if (begin && end) {
        const d = parsePiHourToDate(r.pi_hour || r.tick_str);
        if (!d || d < begin || d > end) return false;
      }

      // 再依各 filter 過濾
      for (const [k, valsRaw] of Object.entries(filters)) {
        const vals = Array.isArray(valsRaw) ? valsRaw : [valsRaw];

        // ★ defect_size 不再在這裡決定要不要保留 row
        //   交給後面的「尺寸投影」去改數值（chart.js + filter.js 裡的投影邏輯）
        if (k === "defect_size") {
          continue;
        }

        // 其他欄位仍用原本的等於比較
        const v = (r[k] ?? "").toString();
        if (vals.length && !vals.includes(v)) return false;
      }
      return true;
    });

    // ========= 尺寸投影（跟 aoi_density 一樣） =========
    const sizeKey = "defect_size";
    const sizeFilterArr = filters[sizeKey];
    const selectedSizes =
      Array.isArray(sizeFilterArr) && sizeFilterArr.length
        ? new Set(sizeFilterArr)
        : null;

    // 沒有選尺寸 → 不改數值，直接回傳篩過的 rows
    if (!selectedSizes || !selectedSizes.size){
      return outFiltered.slice();
    }

    // 有選尺寸 → 依選到的 S/M/L/O 重新投影數值
    const projected = outFiltered.map((r)=>{
      // 1) glass 數（分母）
      const nG = Number(
        r.n_glasses ??
        r.maingroup_glass_count ??
        r.total_glass_count ??
        0
      );

      // 2) 原始尺寸數量（base）
      const baseS = Number(r.s_count ?? r.small_defect_count ?? 0);
      const baseM = Number(r.m_count ?? r.middle_defect_count ?? 0);
      const baseL = Number(r.l_count ?? r.large_defect_count  ?? 0);
      const baseO = Number(r.o_count ?? r.over_defect_count   ?? 0);

      // 3) 沒被勾到的尺寸 → 歸零
      const s = selectedSizes.has("S") ? baseS : 0;
      const m = selectedSizes.has("M") ? baseM : 0;
      const l = selectedSizes.has("L") ? baseL : 0;
      const o = selectedSizes.has("O") ? baseO : 0;

      const newDef     = s + m + l + o;
      const newDensity = nG > 0 ? (newDef / nG) : 0;

      // 4) 重新計算「有選尺寸的 defect glass 數」
      let newCodeGlass = Number(
        r.defect_code_glass_count ??
        r.code_glass_num ??
        0
      );

      const gdc = r.glass_defect_count;
      if (gdc && typeof gdc === "object" && !Array.isArray(gdc) && Object.keys(gdc).length) {
        let cnt = 0;
        Object.values(gdc).forEach((stat)=>{
          const st = parseSizeStats(stat);
          const hit =
            (selectedSizes.has("S") && st.S > 0) ||
            (selectedSizes.has("M") && st.M > 0) ||
            (selectedSizes.has("L") && st.L > 0) ||
            (selectedSizes.has("O") && st.O > 0);
          if (hit) cnt += 1;
        });
        newCodeGlass = cnt;
      }

      return {
        ...r,

        // 表格欄位（以「勾到的尺寸」為主）
        small_defect_count:  s,
        middle_defect_count: m,
        large_defect_count:  l,
        over_defect_count:   o,

        // Chart 友善欄位（有用到 s_count/m_count/... 的地方）
        s_count: s,
        m_count: m,
        l_count: l,
        o_count: o,

        // defect 數量
        defect_code_count: newDef,
        n_rows:            newDef,
        defect_num:        newDef,

        // density
        density: newDensity,

        // defect glass count
        defect_code_glass_count: newCodeGlass,
        code_glass_num:          newCodeGlass
      };
    });

    return projected;
  };

  // ========= 資料就緒時啟動 =========
  document.addEventListener('aoi_inspection:data-ready', ()=>{
    //console.log('[INSPECTION Filter] data-ready fired, detail =', ev.detail);
    AOI.Filter.ensureWidgets();
    // 如果未來有 SubTabs，可以這裡判斷 AOI.applySubTab 再呼叫
    // const subTabsMap = AOI.state.paramDict?.SubTabsFilterDefaultDict || {};
    // const firstKey = Object.keys(subTabsMap)[0];
    // if (firstKey && typeof AOI.applySubTab === "function") AOI.applySubTab(firstKey);
  });

  // 暴露工具
  AOI.selectIdOf = selectIdOf;
  AOI.hostIdOf   = hostIdOf;
})();