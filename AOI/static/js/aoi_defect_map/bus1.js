// static/js/bus.js
(function(){
  // --- Simple Event Bus ---
  const listeners = {};
  window.Bus = {
    on(evt, fn){ (listeners[evt] ||= []).push(fn); },
    emit(evt, payload){ (listeners[evt]||[]).forEach(fn=>{ try{ fn(payload); }catch(e){ console.error('[Bus]', evt, e);} }); }
  };

  // --- Global State ---
  window.State = window.State || {};
  State.filters = State.filters || { dateFrom:'', dateTo:'', glassORrecipe:'' };
  State.flags   = State.flags   || { matchSameGlass:true };
  State.selectedKeys = State.selectedKeys || [];         // ['YYYY-MM-DDTHH:MM:SS|GLASS|RECIPE', ...]
  State.currentLine  = State.currentLine  || null;       // e.g. 'CAPIT203'
  State.AllRunInfo   = State.AllRunInfo   || {};         // { line_id: {idx: row, ...}, ... }
  State.rowByKey     = State.rowByKey     || {};         // { key: row }
  State.DefectCache  = State.DefectCache  || {};         // { key: [ {x,y,size,type,img,chip}, ... ] }
  State.imgBaseByKey = State.imgBaseByKey || {};         // { key: 'http://.../path/' }
  State.keyColors    = State.keyColors    || {};         // stable color per key
  State.typeSet      = State.typeSet      || new Set();  // union of defect types

  // --- Utils ---
  window.Utils = window.Utils || {};
  const U = window.Utils;
  const palette = [
    '#4e79a7','#f28e2b','#e15759','#76b7b2','#59a14f',
    '#edc949','#af7aa1','#ff9da7','#9c755f','#bab0ab'
  ];

  U.toDate = (s)=> s ? new Date(String(s).replace(' ','T')) : new Date(0);
  U.keyFromRow = (r)=> {
    const t = (r.scantime || r.measure_time || '').toString().replace(' ','T');
    return `${t}|${r.glass_id}|${r.recipe_id}`;
  };
  U.parseKey = (key)=>{
    const [scantime, glass_id, recipe_id] = String(key||'').split('|');
    return { scantime, glass_id, recipe_id };
  };
  U.dist = (x1,y1,x2,y2)=>{
    const dx = (+x1)-(+x2), dy = (+y1)-(+y2);
    return Math.sqrt(dx*dx + dy*dy);
  };
  U.ensureJpg = (s)=>{
    if(!s) return s;
    const low = s.toLowerCase();
    if(low.endsWith('.jpg') || low.endsWith('.jpeg') || low.endsWith('.png')) return s;
    if(low.includes('.jpg') || low.includes('.jpeg') || low.includes('.png')) return s; // 若內含副檔名（查詢字串）
    return s + '.jpg';
  };
  U.hashColor = (str)=>{
    // stable pastel-ish
    let h = 0; for(let i=0;i<str.length;i++){ h = (h*31 + str.charCodeAt(i))|0; }
    const r = 128 + (h & 0x3F); const g = 128 + ((h>>6) & 0x3F); const b = 128 + ((h>>12)&0x3F);
    return `rgb(${r},${g},${b})`;
  };
  U.sizeBucket = (v)=>{
    if(v==null) return 'S';
    const s = String(v).trim().toUpperCase();
    if(['S','M','L','O'].includes(s)) return s;
    const n = parseFloat(s);
    if(isNaN(n)) return 'S';
    if(n <= 20) return 'S';
    if(n <= 100) return 'M';
    if(n <= 400) return 'L';
    return 'O';
  };
  U.unifyDefect = (d)=>{
    return {
      x: +((d.x ?? d.X ?? 0)),
      y: +((d.y ?? d.Y ?? 0)),
      size: U.sizeBucket(d.size ?? d.defect_size),
      type: String(d.type ?? d.predict_code ?? d.judge_code ?? '!'),
      img: (d.img ?? d.pic_name ?? ''),
      chip: (d.chip ?? d.chip_name ?? '')
    };
  };
  U.unique = (arr)=> Array.from(new Set(arr));
  U.by = (arr, fn)=> arr.slice().sort((a,b)=> fn(a)-fn(b));

  // toast
  window.toast = function (msg) {
    let t = document.querySelector('.toast');
    if (!t) {
      t = document.createElement('div');
      t.className = 'toast';
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 1600);
  };
})();


