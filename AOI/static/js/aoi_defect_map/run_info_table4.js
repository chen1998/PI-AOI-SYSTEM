
// static/js/run_info_table.js
(function(){
  const theadCols = [
    {text:'選'},
    {text:'時間', key:'time', sortable:true},
    {text:'Recipe', key:'recipe_id'},
    {text:'Glass', key:'glass_id'},
    {text:'S', key:'s', sortable:true},
    {text:'M', key:'m', sortable:true},
    {text:'L', key:'l', sortable:true},
    {text:'O', key:'o', sortable:true},
    {text:'總', key:'total', sortable:true}
  ];

  // --------- ✅ 新增：可勾選多選的下拉元件 ----------
  // 會把 #multi_select_recipe 取代成一顆按鈕 + 勾選清單
  function initMultiDD(baseId, items, placeholder, onChange) {
    const host = document.getElementById(baseId);
    if (!host) return;

    // 砍掉舊的，重建（方便切換 line 時重灌）
    const wrap = document.createElement("div");
    wrap.className = "multi-dd";
    wrap.id = baseId;

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "multi-dd-btn";
    btn.textContent = placeholder || "Recipe（多選）";

    const list = document.createElement("div");
    list.className = "multi-dd-list";

    // 依 items 建立 checkbox 列表
    (items || []).forEach(v => {
      const vv = String(v || "").trim();
      if (!vv) return;

      const lab = document.createElement("label");
      const chk = document.createElement("input");
      chk.type = "checkbox";
      chk.value = vv;

      // 預設勾選狀態：依 State.filters.recipes
      if (State.filters && State.filters.recipes instanceof Set) {
        chk.checked = State.filters.recipes.has(vv);
      }

      lab.append(chk, document.createTextNode(vv));
      list.appendChild(lab);
    });

    // 動作區：清空 / 套用
    const actions = document.createElement('div');
    actions.className = 'multi-dd-actions';

    const btnClear = document.createElement('button');
    btnClear.type = 'button';
    btnClear.className = 'multi-dd-clear';
    btnClear.textContent = '清空';
    btnClear.addEventListener('click', () => {
      list.querySelectorAll('input[type="checkbox"]').forEach(ch => ch.checked = false);
      if (typeof onChange === 'function') onChange([]);
      updateButtonText([]);
      wrap.classList.remove('open');
    });

    const btnApply = document.createElement('button');
    btnApply.type = 'button';
    btnApply.className = 'multi-dd-apply';
    btnApply.textContent = '套用';
    btnApply.addEventListener('click', () => {
      const vals = [...list.querySelectorAll('input[type="checkbox"]:checked')].map(c => c.value);
      if (typeof onChange === 'function') onChange(vals);
      updateButtonText(vals);
      wrap.classList.remove('open');
    });

    actions.append(btnClear, btnApply);
    list.appendChild(actions);

    function updateButtonText(vals) {
      const txt = (vals && vals.length) ? vals.join(' & ') : (placeholder || 'Recipe（多選）');
      btn.textContent = txt;
    }
    // 初始化按鈕文字
    const initial = [...(State.filters?.recipes || [])];
    updateButtonText(initial);

    // 開關
    btn.addEventListener('click', () => wrap.classList.toggle('open'));
    document.addEventListener('click', (e)=>{
      if (!wrap.contains(e.target)) wrap.classList.remove('open');
    });

    wrap.append(btn, list);
    host.replaceWith(wrap);
  }

  // 由 rows 萃取唯一 recipe_id 清單，建立/重建下拉
  function ensureRecipeDropdown(rows) {
    const recipes = Array.from(
      new Set(
        (rows || []).map(r => String(r.recipe_id || '').trim()).filter(Boolean)
      )
    ).sort();
    initMultiDD('multi_select_recipe', recipes, 'Recipe（多選）', (selectedArr) => {
      State.filters.recipes = new Set(selectedArr || []);
      Bus.emit('filters-changed');
    });
  }
  // ----------------------------------------------------

  let currentRows = [];
  let sortKey = 'time';
  let sortDir = 'desc';

  function enrich(r){
    const ds = r.defect_summary || {};
    const s = +(r.small_defect_count ?? ds.small_defect_count ?? 0);
    const m = +(r.middle_defect_count ?? ds.middle_defect_count ?? 0);
    const l = +(r.large_defect_count  ?? ds.large_defect_count  ?? 0);
    const o = +(r.over_defect_count   ?? ds.over_defect_count   ?? 0);
    const total = +(r.defect_count     ?? ds.defect_count        ?? (s+m+l+o));
    return { ...r, s, m, l, o, total };
  }
  function toDate(s){ return s? new Date(String(s).replace(' ','T')) : new Date(0); }

  function passFilters(rows){
    let r = rows;

    // 1) 只篩 glass_id（依需求）
    const q = (State.filters.glassORrecipe||'').toLowerCase();
    if(q){
      r = r.filter(x => String(x.glass_id||'').toLowerCase().includes(q));
    }

    // 2) Recipe 多選（交叉條件；空集合 = 不限制）
    if (State.filters.recipes instanceof Set && State.filters.recipes.size > 0) {
      r = r.filter(x => State.filters.recipes.has(String(x.recipe_id || '').trim()));
    }

    // 3) 同 glass 自動篩
    if(State.flags.matchSameGlass && State.selectedKeys.length>=1){
      const g = Utils.parseKey(State.selectedKeys[0]).glass_id;
      if(g) r = r.filter(x=> x.glass_id===g);
    }
    return r;
  }

  function sortRows(rows){
    const arr = rows.slice();
    if(sortKey==='time') arr.sort((a,b)=> toDate(a.scantime)-toDate(b.scantime));
    if(['s','m','l','o','total'].includes(sortKey)) arr.sort((a,b)=> (a[sortKey]||0)-(b[sortKey]||0));
    if(sortDir==='desc') arr.reverse();
    return arr;
  }

  function renderHead(thead){
    thead.innerHTML = '';
    const tr = document.createElement('tr');
    theadCols.forEach(c=>{
      const th = document.createElement('th');
      th.textContent = c.text;
      if(c.sortable){
        th.classList.add('sortable'); th.dataset.key = c.key;
        const arrow = document.createElement('span');
        arrow.className = 'sort-arrow';
        arrow.textContent = (sortKey===c.key ? (sortDir==='asc'?' ▲':' ▼') : ' ↕');
        th.appendChild(arrow);
        th.addEventListener('click', ()=>{
          if(sortKey===c.key){ sortDir = (sortDir==='asc'?'desc':'asc'); }
          else { sortKey = c.key; sortDir = 'desc'; }
          render(currentRows);
        });
      }
      tr.appendChild(th);
    });
    thead.appendChild(tr);
  }

  function renderBody(tbody, rows){
    tbody.innerHTML='';
    rows.forEach(r=>{
      const rr = enrich(r);
      const key = Utils.keyFromRow(rr);
      State.rowByKey[key] = rr;
      const tr = document.createElement('tr');
      tr.dataset.key = key;
      const imgBase = (window.IMG_BASE || '') + (rr.image_path || '');
      tr.dataset.imgfld = imgBase;
      if(State.selectedKeys.includes(key)) tr.classList.add('selected');

      const tdSel = document.createElement('td');
      const cb = document.createElement('input');
      cb.type='checkbox'; cb.className='sel'; cb.checked = State.selectedKeys.includes(key);
      tdSel.appendChild(cb); tr.appendChild(tdSel);

      [rr.scantime, rr.recipe_id, rr.glass_id, rr.s, rr.m, rr.l, rr.o, rr.total].forEach(val=>{
        const td = document.createElement('td'); td.textContent = (val??''); tr.appendChild(td);
      });

      function toggle(checked){
        const exists = State.selectedKeys.includes(key);
        if(checked && !exists){
          State.selectedKeys.push(key);
          State.imgBaseByKey[key] = tr.dataset.imgfld || '';
        }else if(!checked && exists){
          State.selectedKeys = State.selectedKeys.filter(k=>k!==key);
        }
        document.getElementById('sel-count').textContent = String(State.selectedKeys.length||0);
        tr.classList.toggle('selected', checked);
        Bus.emit('selection-changed', State.selectedKeys.slice());
        if(State.flags.matchSameGlass) render(currentRows);
      }

      cb.addEventListener('change', ()=> toggle(cb.checked));
      tbody.appendChild(tr);
    });

    const el = document.querySelector('#run-stats .badge b');
    if(el) el.textContent = String(rows.length);
  }

  function render(rows){
    currentRows = rows.slice();

    //  每次渲染前，先重建「Recipe 多選下拉」
    ensureRecipeDropdown(currentRows);

    const cont = document.getElementById('run-info-table-container');
    if(!cont) return;
    const thead = cont.querySelector('thead');
    const tbody = document.getElementById('run-info-tbody');

    renderHead(thead);
    const filtered = passFilters(currentRows);
    const sorted   = sortRows(filtered);
    renderBody(tbody, sorted);
  }

  Bus.on('render-run-info', (rows)=> render(rows||[]));
  Bus.on('filters-changed', ()=> render(currentRows));
  Bus.on('selection-changed', ()=> render(currentRows));

  // Glass 查詢欄（只篩 glass_id）
  const btnApply = document.getElementById('applyQuery');
  const btnClear = document.getElementById('clearQuery');
  const fQuery   = document.getElementById('fQuery');
  if(btnApply && fQuery){
    btnApply.addEventListener('click', ()=>{
      State.filters.glassORrecipe = (fQuery.value||'').trim();
      Bus.emit('filters-changed');
    });
  }
  if(btnClear && fQuery){
    btnClear.addEventListener('click', ()=>{
      fQuery.value = '';
      State.filters.glassORrecipe = '';
      Bus.emit('filters-changed');
    });
  }

  // 清除選取
  const btnClearSel = document.getElementById('btnClearSel');
  if (btnClearSel) btnClearSel.addEventListener('click', () => {
    // 1) 清除已選 key
    State.selectedKeys = [];
    document.getElementById('sel-count').textContent = '0';

    // 2) 取消表格勾選與選取樣式
    document.querySelectorAll('#run-info-tbody input.sel').forEach(cb => cb.checked = false);
    document.querySelectorAll('#run-info-tbody tr').forEach(tr => tr.classList.remove('selected'));

    // 3) 清除 map-info-container 內的 offset 影像區塊（← 新增）
    const mapInfo = document.getElementById('map-info-container');
    if (mapInfo) mapInfo.innerHTML = ''; // 或：document.querySelectorAll('#map-info-container .offset-img-group').forEach(n => n.remove());

    // 4) 通知其它模組
    Bus.emit('selection-changed', []);
  });
})();

