// static/js/api.js
(function(){
  const API = {
    async getAll(){
      const url = (window.API_BASE||'') + '/api/run-info';
      console.log(url);
      const res = await fetch(url);
      if(!res.ok) throw new Error('GET /api/run-info failed');
      return res.json();
    },
    async getByLine(line_id, start, end){
      const u = new URL((window.API_BASE||'') + '/api/run-info', window.location.origin);
      u.searchParams.set('line_id', line_id);
      if(start) u.searchParams.set('start', start);
      if(end)   u.searchParams.set('end', end);
      const res = await fetch(u.toString());
      if(!res.ok) throw new Error('GET /api/run-info by line failed');
      return res.json();
    },
    async getDefects(line_id, key){
      const u = new URL((window.API_BASE||'') + '/api/defect-data', window.location.origin);
      u.searchParams.set('line_id', line_id);
      u.searchParams.set('key', key);
      const res = await fetch(u.toString());
      if(!res.ok) throw new Error('GET /api/defect-data failed');
      return res.json();
    }
  };

  function buildTabs(lineTabs){
    const cont = document.getElementById('all-tab-container');
    if(!cont) return;
    cont.innerHTML = '';
    const row = document.createElement('div');
    row.className = 'tabs-row';
    lineTabs.forEach((line, idx)=>{
      const btn = document.createElement('button');
      btn.className = 'tab-btn';
      btn.textContent = line;
      if(idx===0) btn.classList.add('active');
      btn.addEventListener('click', async ()=>{
        row.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
        btn.classList.add('active');
        State.currentLine = line;
        const dictRows = State.AllRunInfo[line] || {};
        const rows = Object.values(dictRows||{});
        Bus.emit('render-run-info', rows);
      });
      row.appendChild(btn);
    });
    cont.appendChild(row);
  }

  // 依目前選取 keys，補抓缺陷資料
  async function fetchDefectsIfNeeded(keys){
    const promises = [];
    const newKeys = [];
    keys.forEach(k=>{
      if(!State.DefectCache[k]){ // 尚未快取
        newKeys.push(k);
        promises.push(API.getDefects(State.currentLine, k).then(j=>{
          const list = (j && j.defects) ? j.defects.map(Utils.unifyDefect) : [];
          State.DefectCache[k] = list;
          // 補登記 types
          list.forEach(d=> State.typeSet.add(d.type));
        }).catch(e=> console.error('[api] getDefects', e)));
      }
    });
    if(promises.length){
      await Promise.all(promises);
      Bus.emit('defect-refresh', newKeys);
      // 同步刷新 legend 和 type filters
      refreshLegend();
      buildTypeFilters();
    }
  }

  function refreshLegend(){
    const box = document.getElementById('map-legend');
    if(!box) return;
    box.innerHTML = '';
    const keys = State.selectedKeys;
    keys.forEach(k=>{
      const c = (State.keyColors[k] ||= Utils.hashColor(k));
      const div = document.createElement('div');
      div.className = 'legend-item';
      div.innerHTML = `<span class="c" style="background:${c}"></span><span class="t">${k}</span>`;
      box.appendChild(div);
    });
  }

  function buildTypeFilters(){
    const host = document.getElementById('type-filters');
    if(!host) return;
    host.innerHTML = '<span>Type：</span>';
    const types = Array.from(State.typeSet).sort();
    if(!types.length){
      // 預設 '!' 類型
      const lab = document.createElement('label');
      lab.innerHTML = `<input type="checkbox" data-type="!" checked> !`;
      host.appendChild(lab);
      return;
    }
    types.forEach(t=>{
      const id = `tp-${t}`;
      const lab = document.createElement('label');
      lab.innerHTML = `<input type="checkbox" id="${id}" data-type="${t}" checked> ${t}`;
      host.appendChild(lab);
    });
    host.querySelectorAll('input[type=checkbox]').forEach(cb=>{
      cb.addEventListener('change', ()=> Bus.emit('map-refresh'));
    });
  }

  function wireGlobalFilters(){
    const q = document.getElementById('fQuery');
    const btnQ = document.getElementById('applyQuery');
    const btnQC = document.getElementById('clearQuery');
    const df = document.getElementById('fDateFrom');
    const dt = document.getElementById('fDateTo');
    const btnApply = document.getElementById('applyDates');
    const btnClear = document.getElementById('clearDates');
    const same = document.getElementById('match-same-glass');

    if(btnQ) btnQ.addEventListener('click', ()=>{
      State.filters.glassORrecipe = (q.value||'').trim();
      Bus.emit('filters-changed');
    });
    if(btnQC) btnQC.addEventListener('click', ()=>{
      q.value=''; State.filters.glassORrecipe=''; Bus.emit('filters-changed');
    });
    if(btnApply) btnApply.addEventListener('click', async ()=>{
      if(!State.currentLine) return;
      const res = await API.getByLine(State.currentLine, df.value||'', dt.value||'');
      const dict = res.UniRunInfoTableData || {};
      State.AllRunInfo[State.currentLine] = dict;
      const rows = Object.values(dict);
      Bus.emit('render-run-info', rows);
    });
    if(btnClear) btnClear.addEventListener('click', async ()=>{
      if(!State.currentLine) return;
      df.value=''; dt.value='';
      const res = await API.getByLine(State.currentLine, '', '');
      const dict = res.UniRunInfoTableData || {};
      State.AllRunInfo[State.currentLine] = dict;
      const rows = Object.values(dict);
      Bus.emit('render-run-info', rows);
    });
    if(same){
      same.checked = !!State.flags.matchSameGlass;
      same.addEventListener('change', ()=>{
        State.flags.matchSameGlass = !!same.checked;
        Bus.emit('filters-changed');
      });
    }

    // Size filters
    ['S','M','L','O'].forEach(sid=>{
      const el = document.getElementById(`size-${sid}`);
      if(el) el.addEventListener('change', ()=> Bus.emit('map-refresh'));
    });
    // === ⭐ 預設日期：今天與前 3 天 ⭐ ===
    (function setDefaultDates(){
      if (!df || !dt) return;

      const today = new Date();
      const end = today.toISOString().slice(0, 10);

      const startDate = new Date(today);
      startDate.setDate(startDate.getDate() - 3);
      const start = startDate.toISOString().slice(0, 10);

      df.value = start;
      dt.value = end;

      //console.log("[init default dates]", start, end);
    })();
  }

  // 入口
  async function init(){
    try{
      const payload = await API.getAll();
      State.AllRunInfo = payload.AllRunInfoTableData || {};
      const tabs = payload.AllLineTabs || Object.keys(State.AllRunInfo);
      // 第一個 line
      State.currentLine = tabs && tabs[0] || null;
      buildTabs(tabs);
      wireGlobalFilters();
      // 預設顯示第一個 line 的資料
      const dictRows = State.AllRunInfo[State.currentLine] || {};
      Bus.emit('render-run-info', Object.values(dictRows));
    }catch(e){
      console.error('[api] init failed', e);
      toast('載入資料失敗');
    }
  }

  // 當 selection 改變時，嘗試補抓缺陷資料
  Bus.on('selection-changed', (keys)=>{
    if(!keys || !keys.length) return;
    fetchDefectsIfNeeded(keys);
    refreshLegend();
  });

  document.addEventListener('DOMContentLoaded', init);
})();
