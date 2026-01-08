// static/js/aoi_density/table_tab.js
(function () {
  const AOI = (window.AOI_DENSITY = window.AOI_DENSITY || {});
  const $  = (sel, root=document) => root.querySelector(sel);
  const API = window.API; 
  const editor = window.USER || '預設';

  // 內部狀態
  const Spec = {
    tabKey: null,
    config: null,
    allRows: [],
    filteredRows: [],
    // mdd: { [dataKey]: { mdd, options } }
    mdd: {},
    colKeys: [],
    colLabels: {},
    filterConfig: {},
    filterOrder: [],
    // 分頁
    pageSize: 200,
    currentPage: 1,
    totalPages: 1,
    // tab 專用 class
    lastTabClass: null,
    // 編輯 / 新增 / 刪除狀態
    isEditMode: false,
    isAddMode: false,
    isDeleteMode: false,
    editBtn: null,
    addBtn: null,
    deleteBtn: null
  };

  // ---------- 常用集合（靠 header label 判斷） ----------
  const EDIT_TEXT_LABELS   = new Set(['MODEL_ID', 'PROCESS_TYPE', 'OOC', 'OOS']);
  const EDIT_SELECT_LABELS = new Set(['PI Line', 'MODEL_TYPE', 'DEFECT_CODE', 'SIZE_TYPE']);

  // ---------- ID 工具 ----------
  function specSelectIdOf(key){ return `spec-f-${key}`; }
  function specHostIdOf(key){ return `spec-host-${key}`; }

  function getNowStr(){
    const d = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    const yyyy = d.getFullYear();
    const mm   = pad(d.getMonth() + 1);
    const dd   = pad(d.getDate());
    const hh   = pad(d.getHours());
    const mi   = pad(d.getMinutes());
    const ss   = pad(d.getSeconds());
    return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}`;
  }

  function ensureSpecDynHosts(){
    const aside = $('#aoi_spec-right');
    if (!aside) return null;
    let dyn = $('#aoi_spec-dynhosts');
    if (!dyn) {
      dyn = document.createElement('div');
      dyn.id = 'aoi_spec-dynhosts';
      aside.appendChild(dyn);
    }
    return dyn;
  }

  function ensurePager(){
    const wrap = $('#aoi_spec-left .table-wrap');
    if (!wrap) return null;
    let pager = $('#aoi_spec-pager');
    if (!pager) {
      pager = document.createElement('div');
      pager.id = 'aoi_spec-pager';
      pager.className = 'aoi_spec-pager';
      wrap.appendChild(pager);
    }
    return pager;
  }

  function ensureFilterCountSpan(){
    const title = $('.spec-filter-panel-title');
    if (!title) return null;
    let span = $('#aoi_spec-count');
    if (!span) {
      span = document.createElement('span');
      span.id = 'aoi_spec-count';
      span.className = 'spec-filter-count';
      title.appendChild(span);
    }
    return span;
  }

  function ensureBottomClearButton(){
    const aside = $('#aoi_spec-right');
    if (!aside) return null;
    let box = aside.querySelector('.spec-filter-bottom-actions');
    if (!box) {
      box = document.createElement('div');
      box.className = 'spec-filter-bottom-actions';
      const btn = document.createElement('button');
      btn.id = 'aoi_specClearBottom';
      btn.className = 'btn btn-xs btn-secondary';
      btn.textContent = '清空篩選';
      box.appendChild(btn);
      aside.appendChild(box);
    }
    return $('#aoi_specClearBottom');
  }

  function ensureAddPanel(){
    let panel = $('#aoi_spec-add-panel');
    if (panel) return panel;
    const left = $('#aoi_spec-left');
    if (!left) return null;
    panel = document.createElement('section');
    panel.id = 'aoi_spec-add-panel';
    panel.className = 'card-sub spec-add-panel';
    panel.style.display = 'none';
    // 放在 table 上方（info 下面、table-wrap 前面）
    const tableWrap = left.querySelector('.table-wrap');
    if (tableWrap) {
      left.insertBefore(panel, tableWrap);
    } else {
      left.appendChild(panel);
    }
    return panel;
  }
  /*
  
  */
  // ---------- filter 選項的工具：依 label 取得 options ----------
  function getOptionsForLabel(label){
    const cfg = Spec.filterConfig && Spec.filterConfig[label];
    if (!cfg) return [];
  
    if (Array.isArray(cfg.values) && cfg.values.length) {
      return cfg.values.slice();
    }
  
    const dataKey = cfg.key || label;
    const wrap = Spec.mdd[dataKey];
    if (!wrap || !Array.isArray(wrap.options)) return [];
    return wrap.options.slice();
  }

  

  // ---------- 共用：把 header 三顆按鈕恢復成預設狀態 ----------
   function restoreHeaderButtonsDefault(){
    Spec.isEditMode   = false;
    Spec.isAddMode    = false;
    Spec.isDeleteMode = false;

    if (Spec.editBtn) {
      Spec.editBtn.style.display = '';
      Spec.editBtn.textContent   = '編輯';
    }
    if (Spec.addBtn) {
      Spec.addBtn.style.display  = '';
      Spec.addBtn.textContent    = '新增';
    }
    if (Spec.deleteBtn) {
      Spec.deleteBtn.style.display = '';
      Spec.deleteBtn.textContent   = '刪除';
    }
  }

  // ---------- header & 日期 + default_spec_table header buttons ----------
  function setupHeaderTitle(tabKey, config){
    const h2 = $('#aoi_spec-info .aoi_spec-info-head .t');
    if (h2) {
      const name = (config && config.tab_name) || tabKey || '';
      h2.textContent = name;
    }

    const dateBlock = $('#aoi_spec-right .spec-filter-item');
    if (dateBlock) {
      if (tabKey === 'fixed_spec_table' || tabKey === 'default_spec_table') {
        dateBlock.style.display = 'none';
      } else {
        dateBlock.style.display = '';
      }
    }

    // header actions（編輯 / 新增 / 刪除）
    const head = $('#aoi_spec-info .aoi_spec-info-head');
    if (!head) return;

    let actions = head.querySelector('.spec-header-actions');
    if (!actions) {
      actions = document.createElement('div');
      actions.className = 'spec-header-actions';
      head.appendChild(actions);
    }

    actions.innerHTML = '';

    if (tabKey === 'default_spec_table') {
      const editBtn = document.createElement('button');
      editBtn.id = 'aoi_specEdit';
      editBtn.className = 'btn-spec-action';
      editBtn.textContent = '編輯';

      const addBtn = document.createElement('button');
      addBtn.id = 'aoi_specAdd';
      addBtn.className = 'btn-spec-action';
      addBtn.textContent = '新增';

      const deleteBtn = document.createElement('button');
      deleteBtn.id = 'aoi_specDelete';
      deleteBtn.className = 'btn-spec-action';
      deleteBtn.textContent = '刪除';

      actions.appendChild(editBtn);
      actions.appendChild(addBtn);
      actions.appendChild(deleteBtn);
      actions.style.display = '';

      Spec.editBtn   = editBtn;
      Spec.addBtn    = addBtn;
      Spec.deleteBtn = deleteBtn;

      bindHeaderButtons();
    } else {
      actions.style.display = 'none';
      Spec.editBtn     = null;
      Spec.addBtn      = null;
      Spec.deleteBtn   = null;
      Spec.isEditMode  = false;
      Spec.isAddMode   = false;
      Spec.isDeleteMode = false;
      const panel = $('#aoi_spec-add-panel');
      if (panel) panel.style.display = 'none';
    }
  }

  // ---------- 表頭欄位設定 ----------
  // 支援：
  // 1) label → dataKey ：{ "PI Line": "line_id", ... }
  // 2) dataKey → label ：{ "line_id": "PI Line", ... }
  function buildColConfig(config, rows){
    const tc = config && config.table_columns;
    const sample = Array.isArray(rows) && rows.length ? rows[0] : {};
    const colKeys = [];
    const colLabels = {};

    if (Array.isArray(tc)) {
      tc.forEach(dataKey=>{
        colKeys.push(dataKey);
        colLabels[dataKey] = dataKey;
      });
    } else if (tc && typeof tc === 'object') {
      Object.entries(tc).forEach(([k, v])=>{
        let dataKey;
        let header;
        const sampleHasK = sample && Object.prototype.hasOwnProperty.call(sample, k);
        const sampleHasV = sample && typeof v === 'string' &&
                           Object.prototype.hasOwnProperty.call(sample, v);

        if (sampleHasV && !sampleHasK) {
          // 視為 label → dataKey
          header  = k;
          dataKey = v;
        } else {
          // 視為 dataKey → label
          dataKey = k;
          header  = (typeof v === 'string' && v) ? v : k;
        }

        if (!dataKey) return;
        colKeys.push(dataKey);
        colLabels[dataKey] = header;
      });
    } else {
      Object.keys(sample || {}).forEach(k=>{
        colKeys.push(k);
        colLabels[k] = k;
      });
    }

    Spec.colKeys   = colKeys;
    Spec.colLabels = colLabels;
  }

  function renderHeader(){
    const table = $('#aoi_spec-table');
    if (!table) return;
    const thead = table.querySelector('thead');
    if (!thead) return;

    // table class 加上 tabKey
    if (Spec.lastTabClass) {
      table.classList.remove(Spec.lastTabClass);
    }
    if (Spec.tabKey) {
      table.classList.add(Spec.tabKey);
      Spec.lastTabClass = Spec.tabKey;
    }

    thead.innerHTML = '';
    const tr = document.createElement('tr');

    const isDefault = Spec.tabKey === 'default_spec_table';
    if (isDefault && Spec.isDeleteMode) {
      const thDel = document.createElement('th');
      thDel.className = 'spec-col-del';
      thDel.textContent = ''; // 可視需要顯示 '刪除'
      tr.appendChild(thDel);
    }

    (Spec.colKeys || []).forEach(dataKey=>{
      const th = document.createElement('th');
      th.textContent = Spec.colLabels[dataKey] || dataKey;
      tr.appendChild(th);
    });
    thead.appendChild(tr);
  }

  // ---------- 數值格式化 ----------
  function formatCellValue(v){
    if (v == null) return '';
    const s = String(v).trim();
    if (!s) return '';
    const num = Number(s.replace(/,/g, ''));
    if (!Number.isNaN(num) && Number.isFinite(num)) {
      const fixed = num.toFixed(2);
      if (fixed.endsWith('.00')) {
        return String(Math.round(num));
      }
      return fixed;
    }
    return s;
  }

  // ---------- 取得目前 MultiDD 選擇 ----------
  function collectSelectionsFromState(){
    const out = {};
    Object.entries(Spec.mdd || {}).forEach(([dataKey, wrap])=>{
      if (!wrap || !wrap.mdd) return;
      const mdd = wrap.mdd;
      const sel = (mdd.getSelected && mdd.getSelected()) || [];
      // 這裡即使 sel 為空也先記下來，給「階層重建」用
      out[dataKey] = new Set(sel.map(String));
    });
    return out;
  }

  // ---------- MultiDD 搜尋綁定：依關鍵字顯示 / 隱藏選項 ----------
  function wireSearchForHost(hostEl){
    if (!hostEl) return;
    const ddRoot  = hostEl.querySelector('.multi-dd');
    if (!ddRoot) return;
    const input   = ddRoot.querySelector('.multi-dd-search');
    if (!input) return;

    input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
      // 每次輸入時重新抓現在畫面上的所有 option
      const items = Array.from(ddRoot.querySelectorAll('.multi-dd-item'));
      items.forEach(item => {
        const text = item.textContent.toLowerCase();
        if (!q || text.includes(q)) {
          item.style.display = '';
        } else {
          item.style.display = 'none';
        }
      });
    });
  }

  // ---------- 建立階層式 MultiDD 篩選器 ----------
  function buildSpecFilters(prevSelections){
    const colDict = Spec.filterConfig || {};
    const labels  = Spec.filterOrder.length ? Spec.filterOrder : Object.keys(colDict || {});
    const dynHosts = ensureSpecDynHosts();
    if (!dynHosts) return;

    dynHosts.innerHTML = '';
    Spec.mdd = {};

    if (!labels.length) {
      Spec.filteredRows = (Spec.allRows || []).slice();
      applySpecFilter();
      return;
    }

    if (!AOI.MultiDD) {
      console.error('[aoi_spec] AOI.MultiDD 未載入，請確認 multidd.js 已在 table_tab.js 之前載入');
      Spec.filteredRows = (Spec.allRows || []).slice();
      applySpecFilter();
      return;
    }

    labels.forEach((label, idx)=>{
      const cfg = colDict[label] || {};
      const dataKey = cfg.key || label;

      // 1) 先用「前面所有 filter 的選擇」去篩 baseRows
      let baseRows = Spec.allRows || [];
      if (prevSelections && idx > 0) {
        labels.slice(0, idx).forEach(prevLabel=>{
          const pcfg = colDict[prevLabel] || {};
          const pKey = pcfg.key || prevLabel;
          const set  = prevSelections[pKey];
          if (!set || !set.size) return;
          baseRows = baseRows.filter(r=>{
            if (!r) return false;
            const v = r[pKey];
            const s = v == null ? '' : String(v);
            return set.has(s);
          });
        });
      }

      // 2) 從 baseRows 抓出實際有資料的值
      const uniqSet = new Set();
      (baseRows || []).forEach(r=>{
        if (!r) return;
        const v = r[dataKey];
        if (v === undefined || v === null || v === '') return;
        uniqSet.add(String(v));
      });
      const uniqArr = Array.from(uniqSet).sort();

      // 3) 計算 options
      let opts;
      const cfgVals = Array.isArray(cfg.values) ? cfg.values.slice() : [];
      if (cfgVals.length) {
        opts = cfgVals.filter(v=> uniqSet.has(String(v)));
      } else {
        opts = uniqArr;
      }

      if (!opts.length) {
        return;
      }

      // 4) 建 DOM
      const host = document.createElement('div');
      host.className = 'multi-dd-host';
      host.id = specHostIdOf(dataKey);
      dynHosts.appendChild(host);

      const selectId = specSelectIdOf(dataKey);

      const mdd = new AOI.MultiDD({
        hostId: host.id,
        selectId,
        options: opts,
        title: label,
        onChange: () => {
          Spec.currentPage = 1;
          applySpecFilter();
        }
      });

      // 5) 還原之前選擇（若有）
      const prevSet = prevSelections && prevSelections[dataKey];
      let selected;
      if (prevSet && prevSet.size) {
        const intersect = opts.filter(o => prevSet.has(String(o)));
        selected = intersect.length ? intersect : opts.slice();
      } else {
        selected = opts.slice(); // 預設全選
      }

      if (selected.length && mdd.setSelected) {
        mdd.setSelected(selected);
      }

      Spec.mdd[dataKey] = { mdd, options: opts };
      wireSearchForHost(host);
    });
  }

  // ---------- Filter → rows ----------
  function getActiveFilters(){
    const out = {};
    Object.entries(Spec.mdd || {}).forEach(([dataKey, wrap])=>{
      if (!wrap || !wrap.mdd) return;
      const mdd = wrap.mdd;
      const sel = (mdd.getSelected && mdd.getSelected()) || [];
      if (sel.length) out[dataKey] = new Set(sel.map(String));
    });
    return out;
  }

  function updatePagination(){
    const total = Spec.filteredRows.length || 0;
    const size  = Spec.pageSize || 200;
    Spec.totalPages = total ? Math.ceil(total / size) : 1;
    if (!Spec.currentPage || Spec.currentPage > Spec.totalPages) {
      Spec.currentPage = 1;
    }
  }

  function renderPager(){
    const pager = ensurePager();
    if (!pager) return;
    const total = Spec.filteredRows.length || 0;
    const size  = Spec.pageSize || 200;
    const pages = Spec.totalPages || 1;

    pager.innerHTML = '';
    pager.style.display = 'flex';

    const info = document.createElement('div');
    info.className = 'aoi_spec-pager-info';
    info.textContent = `第 ${Spec.currentPage} / ${pages} 頁（共 ${total} 筆）`;
    pager.appendChild(info);

    const btnPrev = document.createElement('button');
    btnPrev.textContent = '上一頁';
    btnPrev.disabled = (pages <= 1) || (Spec.currentPage <= 1);
    btnPrev.addEventListener('click', ()=>{
      if (Spec.currentPage > 1) {
        Spec.currentPage -= 1;
        renderBody();
        renderPager();
        updateFilterCount();
      }
    });
    pager.appendChild(btnPrev);

    const maxPageButtons = 7;
    let start = Math.max(1, Spec.currentPage - 3);
    let end   = Math.min(pages, start + maxPageButtons - 1);
    if (end - start + 1 < maxPageButtons) {
      start = Math.max(1, end - maxPageButtons + 1);
    }

    for (let p = start; p <= end; p++) {
      const btn = document.createElement('button');
      btn.textContent = String(p);
      btn.className = 'page-btn' + (p === Spec.currentPage ? ' active' : '');
      btn.disabled = (pages <= 1);
      btn.addEventListener('click', ()=>{
        if (p === Spec.currentPage || pages <= 1) return;
        Spec.currentPage = p;
        renderBody();
        renderPager();
        updateFilterCount();
      });
      pager.appendChild(btn);
    }

    const btnNext = document.createElement('button');
    btnNext.textContent = '下一頁';
    btnNext.disabled = (pages <= 1) || (Spec.currentPage >= pages);
    btnNext.addEventListener('click', ()=>{
      if (Spec.currentPage < pages) {
        Spec.currentPage += 1;
        renderBody();
        renderPager();
        updateFilterCount();
      }
    });
    pager.appendChild(btnNext);
  }

  function updateFilterCount(){
    const span = ensureFilterCountSpan();
    if (!span) return;
    const total = Spec.filteredRows.length || 0;
    span.textContent = `( ${total} 筆）`;
  }

  function applySpecFilter(){
    const filters = getActiveFilters();
    const rows = Spec.allRows || [];
    const fKeys = Object.keys(filters);

    if (!fKeys.length) {
      Spec.filteredRows = rows.slice();
    } else {
      Spec.filteredRows = rows.filter(r=>{
        for (const dataKey of fKeys){
          const set = filters[dataKey];
          const v   = (r && r[dataKey] != null) ? String(r[dataKey]) : '';
          if (!set.has(v)) return false;
        }
        return true;
      });
    }

    updatePagination();
    renderBody();
    renderPager();
    updateFilterCount();
  }

  // ---------- render tbody（含分頁 & 格式化 + 編輯模式 + Editor 欄位 + 刪除欄） ----------
  function renderBody(){
    const table = $('#aoi_spec-table');
    if (!table) return;
    const tbody = table.querySelector('tbody');
    if (!tbody) return;

    const rows = Spec.filteredRows || [];
    tbody.innerHTML = '';

    const isDefault = Spec.tabKey === 'default_spec_table';

    if (!rows.length) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      let colSpan = Math.max(1, Spec.colKeys.length);
      if (isDefault && Spec.isDeleteMode) {
        colSpan += 1;  // 多一欄刪除欄
      }
      td.colSpan = colSpan;
      td.className = 'muted';
      td.textContent = '（無資料）';
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    const size = Spec.pageSize || 200;
    const start = (Spec.currentPage - 1) * size;
    const end   = start + size;
    const pageRows = rows.slice(start, end);

    pageRows.forEach((r, idxInPage)=>{
      const tr = document.createElement('tr');
      const globalIndex = start + idxInPage;
      tr.dataset.rowIndex = String(globalIndex);

      // 刪除模式：最左側新增刪除按鈕欄
      if (isDefault && Spec.isDeleteMode) {
        const tdDel = document.createElement('td');
        tdDel.className = 'spec-cell-del';
        const btnDel = document.createElement('button');
        btnDel.type = 'button';
        btnDel.className = 'spec-del-btn';
        btnDel.textContent = '✕';
        btnDel.title = '刪除此列';

        btnDel.addEventListener('click', ()=>{
          const row = rows[globalIndex];
          if (!row) return;

          const payload = {
            system:'density',
            mode: 'delete',
            tabKey: Spec.tabKey,
            row: row
          };

          if (API && API.frontEditor) {
            API.frontEditor(payload).then(res=>{
              console.log('[aoi_spec] front_editor delete result', res);
              // 從前端資料移除該列
              Spec.allRows = Spec.allRows.filter(x => x !== row);
              Spec.filteredRows = Spec.filteredRows.filter(x => x !== row);
              updatePagination();
              renderBody();
              renderPager();
              updateFilterCount();
            }).catch(err=>{
              console.error('[aoi_spec] front_editor delete error', err);
              alert('刪除失敗：' + (err && err.message ? err.message : err));
            });
          } else {
            // 沒有 API 時至少前端刪掉
            Spec.allRows = Spec.allRows.filter(x => x !== row);
            Spec.filteredRows = Spec.filteredRows.filter(x => x !== row);
            updatePagination();
            renderBody();
            renderPager();
            updateFilterCount();
          }
        });

        tdDel.appendChild(btnDel);
        tr.appendChild(tdDel);
      }

      (Spec.colKeys || []).forEach(dataKey=>{
        const td = document.createElement('td');
        const header = Spec.colLabels[dataKey] || dataKey;
        const v  = r && r[dataKey];

        // default_spec_table 的 Editor 欄位：Editor + modify_time
        if (isDefault && header === 'Editor') {
          td.classList.add('editor-cell');
          const e = (r && (r.Editor || r.editor)) || '';
          const mtime  = (r && (r.modify_time || r.modifyTime)) || '';
          td.innerHTML = `${e || ''}${(e && mtime) ? '<br>' : ''}${mtime || ''}`;
        }
        // 編輯模式：文字輸入欄
        else if (isDefault && Spec.isEditMode && EDIT_TEXT_LABELS.has(header)) {
          const input = document.createElement('input');
          input.type = 'text';
          input.className = 'spec-edit-input';
          input.value = v == null ? '' : String(v);
          input.dataset.field = dataKey;
          td.appendChild(input);
        }
        // 編輯模式：下拉選單
        else if (isDefault && Spec.isEditMode && EDIT_SELECT_LABELS.has(header)) {
          const select = document.createElement('select');
          select.className = 'spec-edit-select';
          select.dataset.field = dataKey;
          const opts = getOptionsForLabel(header);
          const cur  = v == null ? '' : String(v);
          opts.forEach(optVal=>{
            const opt = document.createElement('option');
            opt.value = optVal;
            opt.textContent = optVal;
            if (String(optVal) === cur) opt.selected = true;
            select.appendChild(opt);
          });
          // 若目前值不在 options 中，也加一個
          if (cur && !opts.includes(cur)) {
            const opt = document.createElement('option');
            opt.value = cur;
            opt.textContent = cur;
            opt.selected = true;
            select.appendChild(opt);
          }
          td.appendChild(select);
        }
        // 其他欄位
        else {
          td.textContent = formatCellValue(v);
        }

        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  }

  // ---------- 編輯模式：儲存 / 取消 ----------
  function saveEditChanges(){
    if (!Spec.isEditMode) return;
    const table = $('#aoi_spec-table');
    if (!table) return;
    const tbody = table.querySelector('tbody');
    if (!tbody) return;

    const changes = [];
    const rows = Spec.filteredRows || [];

    const trs = Array.from(tbody.querySelectorAll('tr'));
    trs.forEach(tr=>{
      const idxStr = tr.dataset.rowIndex;
      const rowIndex = Number(idxStr);
      if (Number.isNaN(rowIndex)) return;
      const row = rows[rowIndex];
      if (!row) return;

      const inputs = tr.querySelectorAll('input.spec-edit-input[data-field], select.spec-edit-select[data-field]');
      inputs.forEach(inp=>{
        const field = inp.dataset.field;
        const newVal = inp.value;
        const oldValRaw = row[field];
        const oldVal = oldValRaw == null ? '' : String(oldValRaw);
        if (newVal !== oldVal) {
          changes.push({
            rowIndex,
            row,
            key: field,
            oldValue: oldValRaw,
            newValue: newVal
          });
          row[field] = newVal;
        }
      });
    });

    console.log('[aoi_spec] edited changes =', changes);
    /*
    
    */
    if (changes.length) {
      
      const MDFTime = getNowStr();

      // 先把畫面上的資料也補上 Editor / modify_time
      changes.forEach(ch => {
        ch.row.Editor = editor;
        ch.row.modify_time = MDFTime;
      });

      // 呼叫後端寫入，payload 帶 Editor 與 modify_time
      if (API && API.frontEditor) {
        API.frontEditor({
          system:'density',
          mode: 'edit',
          tabKey: Spec.tabKey,
          Editor: editor,
          modify_time: MDFTime,
          changes
        }).then(res => {
          console.log('[aoi_spec] front_editor edit result', res);
        }).catch(err => {
          console.error('[aoi_spec] front_editor edit error', err);
          alert('儲存失敗：' + (err && err.message ? err.message : err));
        });
      }
    }

    Spec.isEditMode = false;
    if (Spec.editBtn) Spec.editBtn.textContent = '編輯';
    if (Spec.addBtn)  Spec.addBtn.textContent  = '新增';

    // 重新 render，Editor 欄會顯示新版 editor + modify_time
    renderBody();
  }

  function cancelEditMode(){
    if (!Spec.isEditMode) return;
    Spec.isEditMode = false;
    if (Spec.editBtn) Spec.editBtn.textContent = '編輯';
    if (Spec.addBtn)  Spec.addBtn.textContent  = '新增';
    // DOM 重新用原本資料 render 回去
    renderBody();
  }
  
  // ---------- 新增 panel：render / show / hide ----------
  function showAddPanel(){
    const panel = ensureAddPanel();
    if (!panel) return;

    panel.innerHTML = '';

    const addTable = document.createElement('table');
    addTable.className = 'spec-add-table';

    const thead = document.createElement('thead');
    const headTr = document.createElement('tr');

    const tbody = document.createElement('tbody');
    const bodyTr = document.createElement('tr');

    (Spec.colKeys || []).forEach(dataKey=>{
      const header = Spec.colLabels[dataKey] || dataKey;
      if (header === 'Editor') return; // Editor 不給新增

      const th = document.createElement('th');
      th.textContent = header;
      headTr.appendChild(th);

      const td = document.createElement('td');

      let inputEl;
      if (EDIT_TEXT_LABELS.has(header)) {
        inputEl = document.createElement('input');
        inputEl.type = 'text';
      } else if (EDIT_SELECT_LABELS.has(header)) {
        inputEl = document.createElement('select');
        const opts = getOptionsForLabel(header);
        (opts || []).forEach(v=>{
          const opt = document.createElement('option');
          opt.value = v;
          opt.textContent = v;
          inputEl.appendChild(opt);
        });
      } else {
        inputEl = document.createElement('input');
        inputEl.type = 'text';
      }

      inputEl.dataset.field = dataKey;
      inputEl.dataset.label = header;      // 之後 alert 用中文欄名
      inputEl.className = 'spec-add-input';

      td.appendChild(inputEl);
      bodyTr.appendChild(td);
    });

    thead.appendChild(headTr);
    tbody.appendChild(bodyTr);
    addTable.appendChild(thead);
    addTable.appendChild(tbody);

    const footer = document.createElement('div');
    footer.className = 'spec-add-footer';

    const btnSave = document.createElement('button');
    btnSave.type = 'button';
    btnSave.className = 'btn btn-xs';
    btnSave.textContent = '儲存';

    const btnCancel = document.createElement('button');
    btnCancel.type = 'button';
    btnCancel.className = 'btn btn-xs btn-secondary';
    btnCancel.textContent = '取消';

    footer.appendChild(btnCancel);
    footer.appendChild(btnSave);

    panel.appendChild(addTable);
    panel.appendChild(footer);

    // 🔹 抽出一個共用的「關閉新增模式」函式
    function closeAddMode(){
      Spec.isAddMode = false;
      panel.style.display = 'none';
      restoreHeaderButtonsDefault();   // ← 關鍵：回復 header 三顆按鈕
    }

    // 取消：關閉 panel + 還原 header
    btnCancel.addEventListener('click', closeAddMode);

    // 儲存：成功後同樣關閉 panel + 還原 header
    btnSave.addEventListener('click', ()=>{
      const inputs = panel.querySelectorAll('[data-field]');
      const newRow = {};
      const emptyLabels = [];

      inputs.forEach(inp=>{
        const field = inp.dataset.field;
        const label = inp.dataset.label || field;
        const val = (inp.value || '').trim();

        if (!val) {
          emptyLabels.push(label);
        }
        newRow[field] = val;
      });

      if (emptyLabels.length) {
        alert('以下欄位不得為空：\n' + emptyLabels.join('、'));
        return;
      }
      const MDFTime = getNowStr();
      newRow.Editor = editor;
      newRow.modify_time = MDFTime;

      console.log('[aoi_spec] new default_spec_table row =', newRow);

      if (API && API.frontEditor) {
        API.frontEditor({
          system:'density',
          mode: 'add',
          tabKey: Spec.tabKey,
          Editor: editor,
          modify_time: MDFTime,
          row: newRow
        }).then(res => {
          console.log('[aoi_spec] front_editor add result', res);
          Spec.allRows.push(newRow);
          applySpecFilter();   // 先重算 filter + 分頁
          closeAddMode();      // 再關 panel + 還原 header
        }).catch(err => {
          console.error('[aoi_spec] front_editor add error', err);
          alert('新增失敗：' + (err && err.message ? err.message : err));
        });
      } else {
        // 後備：沒設定 API 時至少前端還能看到
        Spec.allRows.push(newRow);
        applySpecFilter();
        closeAddMode();
      }
    });

    panel.style.display = '';
  }

  // ---------- Apply / Clear ----------
  let btnBound = false;

  function clearAllFilters(){
    const s = $('#aoi_specStart'); if (s) s.value = '';
    const e = $('#aoi_specEnd');   if (e) e.value = '';

    buildSpecFilters(null);
    Spec.currentPage = 1;
    applySpecFilter();
  }

  function bindSpecButtons(){
    if (btnBound) return;
    btnBound = true;

    const btnApply = $('#aoi_specApply');
    const btnClear = $('#aoi_specClear');
    const btnBottomClear = ensureBottomClearButton();

    if (btnApply) {
      btnApply.addEventListener('click', ()=>{
        const curSel = collectSelectionsFromState();
        buildSpecFilters(curSel);
        Spec.currentPage = 1;
        applySpecFilter();
      });
    }

    if (btnClear) {
      btnClear.addEventListener('click', clearAllFilters);
    }
    if (btnBottomClear) {
      btnBottomClear.addEventListener('click', clearAllFilters);
    }
  }

  // ---------- Header buttons（編輯 / 新增 / 刪除） ----------
  let headerBtnBound = false;
  function bindHeaderButtons(){
    if (headerBtnBound) {
      // 每次 default_spec_table 會重建 button，重新指定事件即可
      if (Spec.editBtn)    Spec.editBtn.onclick    = onClickEdit;
      if (Spec.addBtn)     Spec.addBtn.onclick     = onClickAdd;
      if (Spec.deleteBtn)  Spec.deleteBtn.onclick  = onClickDelete;
      return;
    }
    headerBtnBound = true;

    if (Spec.editBtn)   Spec.editBtn.onclick   = onClickEdit;
    if (Spec.addBtn)    Spec.addBtn.onclick    = onClickAdd;
    if (Spec.deleteBtn) Spec.deleteBtn.onclick = onClickDelete;
  }

  function onClickEdit(){
    if (Spec.tabKey !== 'default_spec_table') return;

    // 若目前在「新增」模式，先關閉新增
    if (Spec.isAddMode) {
      const panel = $('#aoi_spec-add-panel');
      if (panel) panel.style.display = 'none';
      Spec.isAddMode = false;
    }

    // 進入編輯
    if (!Spec.isEditMode) {
      Spec.isEditMode = true;
      Spec.isDeleteMode = false;
      if (Spec.editBtn) { Spec.editBtn.textContent = '儲存'; Spec.editBtn.style.display = ''; }
      if (Spec.addBtn)  { Spec.addBtn.textContent  = '取消'; Spec.addBtn.style.display  = ''; }
      if (Spec.deleteBtn) {
        Spec.deleteBtn.textContent = '刪除';
        Spec.deleteBtn.style.display = '';
      }
      renderHeader();
      renderBody();
      return;
    }

    // 編輯中 → 儲存
    saveEditChanges();
  }

  function onClickAdd(){
    if (Spec.tabKey !== 'default_spec_table') return;

    // 若在編輯模式，新增按鈕 = 取消 編輯
    if (Spec.isEditMode) {
      cancelEditMode();
      return;
    }

    // === 進入新增模式 ===
    if (!Spec.isAddMode) {
      Spec.isAddMode    = true;
      Spec.isEditMode   = false;
      Spec.isDeleteMode = false;

      // 1. 隱藏 header 三顆按鈕
      if (Spec.editBtn)   Spec.editBtn.style.display   = 'none';
      if (Spec.addBtn)    Spec.addBtn.style.display    = 'none';
      if (Spec.deleteBtn) Spec.deleteBtn.style.display = 'none';

      // 2. 顯示新增 panel（內含 儲存 / 取消）
      showAddPanel();
    }
    // === （理論上看不到，但保護一下：若再次點新增當作取消） ===
    else {
      Spec.isAddMode = false;
      const panel = $('#aoi_spec-add-panel');
      if (panel) panel.style.display = 'none';
      restoreHeaderButtonsDefault();
    }
  }

  // 刪除模式：切換 / 取消
  function onClickDelete(){
    if (Spec.tabKey !== 'default_spec_table') return;

    // toggle 刪除模式
    if (!Spec.isDeleteMode) {
      // 進入刪除模式
      Spec.isDeleteMode = true;
      Spec.isEditMode   = false;
      Spec.isAddMode    = false;

      // 關掉新增 panel
      const panel = $('#aoi_spec-add-panel');
      if (panel) panel.style.display = 'none';

      // 隱藏 編輯 / 新增，刪除變「取消」
      if (Spec.editBtn) {
        Spec.editBtn.style.display = 'none';
      }
      if (Spec.addBtn) {
        Spec.addBtn.style.display = 'none';
      }
      if (Spec.deleteBtn) {
        Spec.deleteBtn.textContent = '取消';
        Spec.deleteBtn.style.display = '';
      }
    } else {
      // 取消刪除模式
      Spec.isDeleteMode = false;

      if (Spec.editBtn) {
        Spec.editBtn.style.display = '';
        Spec.editBtn.textContent = '編輯';
      }
      if (Spec.addBtn) {
        Spec.addBtn.style.display = '';
        Spec.addBtn.textContent = '新增';
      }
      if (Spec.deleteBtn) {
        Spec.deleteBtn.textContent = '刪除';
      }
    }

    // 重新 render，讓刪除欄出現 / 消失
    renderHeader();
    renderBody();
    renderPager();
  }

  // ---------- 事件入口（安全取得 rows） ----------
  document.addEventListener("aoi_density:subtab-table", (ev)=>{
    const detail = ev.detail || {};

    const tabKey = detail.tabKey || detail.key || detail.subKey || null;
    const config = detail.config || detail.cfg || {};

    let raw = null;
    if (detail.data !== undefined) {
      raw = detail.data;
    } else if (detail.rows !== undefined) {
      raw = detail.rows;
    } else if (detail.data && Array.isArray(detail.data.rows)) {
      raw = detail.data.rows;
    } else if (detail.payload && Array.isArray(detail.payload.rows)) {
      raw = detail.payload.rows;
    }

    let rows = [];
    if (Array.isArray(raw)) {
      rows = raw;
    } else if (raw && typeof raw === "object") {
      rows = Object.values(raw);
    }

    console.log("[aoi_spec] detail =", detail);
    console.log("[aoi_spec] resolved rows length =", rows.length, rows[0]);

    Spec.tabKey   = tabKey;
    Spec.config   = config;
    Spec.allRows  = rows.slice();
    Spec.filterConfig = (config && config.filter_item_coldict) || {};
    Spec.filterOrder  = Object.keys(Spec.filterConfig || {});
    Spec.currentPage  = 1;
    Spec.isEditMode   = false;
    Spec.isAddMode    = false;
    Spec.isDeleteMode = false;

    console.log("[aoi_spec] Spec.allRows length =", Spec.allRows.length);

    setupHeaderTitle(tabKey, Spec.config);
    buildColConfig(Spec.config, Spec.allRows);
    renderHeader();

    buildSpecFilters(null);
    applySpecFilter();

    bindSpecButtons();
  });

})();