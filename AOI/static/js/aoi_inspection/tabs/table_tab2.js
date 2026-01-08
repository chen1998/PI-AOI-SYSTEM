// static/js/inspection/table_tab.js
(function () {
  // MultiDD 還是共用 AOI_DENSITY 底下的元件
  const AOI = (window.AOI_DENSITY = window.AOI_DENSITY || {});
  const INS = (window.INSPECTION = window.INSPECTION || {});
  const $   = (sel, root=document) => root.querySelector(sel);
  const API = window.API;
  const editor = window.USER || '預設';
  //const payload = window.AOI.state.payload;
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
    deleteBtn: null,

    // EditSummary 用
    editSummaryCancelBtn: null,
    editSummaryBackupRows: null
  };


  // ---------- 常用集合（靠 header label 判斷） ----------
  const EDIT_TEXT_LABELS   = new Set(['MODEL_ID', 'PROCESS_TYPE', 'OOC', 'OOS']);
  const EDIT_SELECT_LABELS = new Set(['MODEL_TYPE', 'DEFECT_CODE', 'SIZE_TYPE']);

  // ✅ 新增：PI Line / Type 走 filterConfig.values 的下拉
  const EDIT_FILTER_SELECT_LABELS = new Set(['PI Line', 'Type']);

  // ---------- ID 工具 ----------
  function specSelectIdOf(key){ return `inspection-spec-f-${key}`; }
  function specHostIdOf(key){ return `inspection-spec-host-${key}`; }

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
    const aside = $('#inspection_spec-right');
    if (!aside) return null;
    let dyn = $('#inspection_spec-dynhosts');
    if (!dyn) {
      dyn = document.createElement('div');
      dyn.id = 'inspection_spec-dynhosts';
      aside.appendChild(dyn);
    }
    return dyn;
  }


  function ensurePager(){
    const wrap = $('#inspection_spec-left .table-wrap');
    if (!wrap) return null;
    let pager = $('#inspection_spec-pager');
    if (!pager) {
      pager = document.createElement('div');
      pager.id = 'inspection_spec-pager';
      pager.className = 'inspection_spec-pager';
      wrap.appendChild(pager);
    }
    return pager;
  }

  function ensureFilterCountSpan(){
    const title = $('.inspection-spec-filter-panel-title');
    if (!title) return null;
    let span = $('#inspection_spec-count');
    if (!span) {
      span = document.createElement('span');
      span.id = 'inspection_spec-count';
      span.className = 'spec-filter-count';
      title.appendChild(span);
    }
    return span;
  }

  function ensureBottomClearButton(){
    const aside = $('#inspection_spec-right');
    if (!aside) return null;
    let box = aside.querySelector('.inspection-spec-filter-bottom-actions');
    if (!box) {
      box = document.createElement('div');
      box.className = 'inspection-spec-filter-bottom-actions';
      const btn = document.createElement('button');
      btn.id = 'inspection_specClearBottom';
      btn.className = 'btn btn-xs btn-secondary';
      btn.textContent = '清空篩選';
      box.appendChild(btn);
      aside.appendChild(box);
    }
    return $('#inspection_specClearBottom');
  }

  function ensureAddPanel(){
    let panel = $('#inspection_spec-add-panel');
    if (panel) return panel;
    const left = $('#inspection_spec-left');
    if (!left) return null;
    panel = document.createElement('section');
    panel.id = 'inspection_spec-add-panel';
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

  // ====== 日期相關小工具 ======
  function formatYMD(d){
    const pad = (n) => String(n).padStart(2, '0');
    const yyyy = d.getFullYear();
    const mm   = pad(d.getMonth() + 1);
    const dd   = pad(d.getDate());
    return `${yyyy}-${mm}-${dd}`;
  }

  // EditSummary 初始進來時預設為「今天往回三天 (共 3 天)」
  function initEditSummaryDefaultDateRange(){
    const s = $('#inspection_specStart');
    const e = $('#inspection_specEnd');
    if (!s || !e) return;

    const today = new Date();
    const endDate = formatYMD(today);

    const startDateObj = new Date(today);
    startDateObj.setDate(startDateObj.getDate() - 3); // 今天 -2 天 => 共 3 天區間
    const startDate = formatYMD(startDateObj);

    s.value = startDate;
    e.value = endDate;
  }


  // ---------- filter 選項的工具：依 label 取得 options（MultiDD） ----------
  function getOptionsForLabel(label){
    const cfg = Spec.filterConfig && Spec.filterConfig[label];
    if (!cfg) return [];
    const dataKey = cfg.key || label;
    const wrap = Spec.mdd[dataKey];
    if (!wrap || !Array.isArray(wrap.options)) return [];
    return wrap.options.slice();
  }

  //  新增：從 Spec.filterConfig[label].values 取選項（不走 MultiDD）
  function getOptionsFromFilterConfigValues(label){
    const cfg = Spec.filterConfig && Spec.filterConfig[label];
    if (!cfg) return [];
    const vals = cfg.values;
    if (!Array.isArray(vals)) return [];
    return vals.map(v => String(v));
  }

  // ---------- header & 日期 + default_spec_table header buttons ----------
  function setupHeaderTitle(tabKey, config){
    const h2 = $('#inspection_spec-info .inspection_spec-info-head .t');
    if (h2) {
      const name = (config && config.tab_name) || tabKey || '';
      h2.textContent = name;
    }

    const dateBlock = $('#inspection_spec-right .inspection-spec-filter-item');
    if (dateBlock) {
      if (tabKey === 'EditSummary') {
        dateBlock.style.display = '';
      } else {
        dateBlock.style.display = 'none';
      }
    }

    // header actions（編輯 / 新增 / 刪除）
    const head = $('#inspection_spec-info .inspection_spec-info-head');
    if (!head) return;

    let actions = head.querySelector('.spec-header-actions');
    if (!actions) {
      actions = document.createElement('div');
      actions.className = 'spec-header-actions';
      head.appendChild(actions);
    }

    actions.innerHTML = '';

    if (tabKey === 'default_spec_table') {
      // 🔵 原本 default_spec_table 的三顆按鈕維持不動
      const editBtn = document.createElement('button');
      editBtn.id = 'inspection_specEdit';
      editBtn.className = 'btn-spec-action';
      editBtn.textContent = '編輯';

      const addBtn = document.createElement('button');
      addBtn.id = 'inspection_specAdd';
      addBtn.className = 'btn-spec-action';
      addBtn.textContent = '新增';

      const deleteBtn = document.createElement('button');
      deleteBtn.id = 'inspection_specDelete';
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

    } else if (tabKey === 'EditSummary') {
      // 🟣 EditSummary：只有一顆「編輯」按鈕
      const editBtn = document.createElement('button');
      editBtn.id = 'inspection_specEditSummary';
      editBtn.className = 'btn-spec-action';
      editBtn.textContent = '編輯';

      actions.appendChild(editBtn);
      actions.style.display = '';

      Spec.editBtn   = editBtn;
      Spec.addBtn    = null;
      Spec.deleteBtn = null;

      Spec.editSummaryCancelBtn = null;
      Spec.isEditMode = false;

      bindHeaderButtons();

    } else {
      actions.style.display = 'none';
      Spec.editBtn      = null;
      Spec.addBtn       = null;
      Spec.deleteBtn    = null;
      Spec.isEditMode   = false;
      Spec.isAddMode    = false;
      Spec.isDeleteMode = false;
      const panel = $('#inspection_spec-add-panel');
      if (panel) panel.style.display = 'none';
    }
  }

  // ---------- 表頭欄位設定 ----------
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
    const table = $('#inspection_spec-table');
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
      thDel.textContent = '';
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
      out[dataKey] = new Set(sel.map(String));
    });
    return out;
  }

  // ---------- MultiDD 搜尋綁定 ----------
  function wireSearchForHost(hostEl){
    if (!hostEl) return;
    const ddRoot  = hostEl.querySelector('.multi-dd');
    if (!ddRoot) return;
    const input   = ddRoot.querySelector('.multi-dd-search');
    if (!input) return;

    input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
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
      console.error('[inspection_spec] AOI.MultiDD 未載入，請確認 multidd.js 已在 inspection table_tab.js 之前載入');
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
    const pages = Spec.totalPages || 1;

    pager.innerHTML = '';
    pager.style.display = 'flex';

    const info = document.createElement('div');
    info.className = 'inspection_spec-pager-info';
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

  // ---------- render tbody ----------
  function renderBody(){
    const table = $('#inspection_spec-table');
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
        colSpan += 1;
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
            system: 'inspection',
            mode: 'delete',
            tabKey: Spec.tabKey,
            row: row
          };

          if (API && API.frontEditor) {
            API.frontEditor(payload).then(res=>{
              console.log('[inspection_spec] front_editor delete result', res);
              Spec.allRows = Spec.allRows.filter(x => x !== row);
              Spec.filteredRows = Spec.filteredRows.filter(x => x !== row);
              updatePagination();
              renderBody();
              renderPager();
              updateFilterCount();
            }).catch(err=>{
              console.error('[inspection_spec] front_editor delete error', err);
              alert('刪除失敗：' + (err && err.message ? err.message : err));
            });
          } else {
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
        if (Spec.tabKey === 'EditSummary' &&
          Spec.isEditMode &&
          (dataKey === 'comment' || dataKey === 'action')) {

        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'edit-summary-input';
        input.value = v == null ? '' : String(v);
        input.dataset.field = dataKey;
        td.appendChild(input);
      
        
        }// default_spec_table 的 Editor 欄位：Editor + modify_time
        else if (isDefault && header === 'Editor') {
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
        //  編輯模式：PI Line / Type（選項來源：Spec.filterConfig[label].values）
        else if (isDefault && Spec.isEditMode && EDIT_FILTER_SELECT_LABELS.has(header)) {
          const select = document.createElement('select');
          select.className = 'spec-edit-select';
          select.dataset.field = dataKey;
        
          const opts = getOptionsFromFilterConfigValues(header);
          const cur  = v == null ? '' : String(v);
          /*
          
          */
          //  placeholder
          const ph = document.createElement('option');
          ph.value = '';
          ph.textContent = '-- 請選擇 --';
          select.appendChild(ph);
        
          opts.forEach(optVal=>{
            const opt = document.createElement('option');
            opt.value = optVal;
            opt.textContent = optVal;
            if (String(optVal) === cur) opt.selected = true;
            select.appendChild(opt);
          });
        
          // 若目前值不在 values 內，仍保留（避免資料庫有舊值）
          if (cur && cur !== '' && !opts.includes(cur)) {
            const opt = document.createElement('option');
            opt.value = cur;
            opt.textContent = cur;
            opt.selected = true;
            select.appendChild(opt);
          }
        
          //  若沒有選到任何值，預設停在 placeholder
          if (!cur) select.value = '';
        
          td.appendChild(select);
        }
        // 編輯模式：下拉選單（走 MultiDD options）
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
    const table = $('#inspection_spec-table');
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

    console.log('[inspection_spec] edited changes =', changes);

    if (changes.length) {
      const MDFTime = getNowStr();
      changes.forEach(ch => {
        ch.row.Editor = editor;
        ch.row.modify_time = MDFTime;
      });

      if (API && API.frontEditor) {
        API.frontEditor({
          system: 'inspection',
          mode: 'edit',
          tabKey: Spec.tabKey,
          Editor: editor,
          modify_time: MDFTime,
          changes
        }).then(res => {
          console.log('[inspection_spec] front_editor edit result', res);
        }).catch(err => {
          console.error('[inspection_spec] front_editor edit error', err);
          alert('儲存失敗：' + (err && err.message ? err.message : err));
        });
      }
    }

    Spec.isEditMode = false;
    if (Spec.editBtn) Spec.editBtn.textContent = '編輯';
    if (Spec.addBtn)  { 
      Spec.addBtn.textContent = '新增';
      Spec.addBtn.onclick = onClickAdd;     
    }
    renderHeader();
    renderBody();
    renderPager();
  }

  function cancelEditMode(){
    if (!Spec.isEditMode) return;
  
    Spec.isEditMode = false;
  
    if (Spec.editBtn) Spec.editBtn.textContent = '編輯';
  
    if (Spec.addBtn) {
      Spec.addBtn.textContent  = '新增';
      Spec.addBtn.onclick = onClickAdd;   // ✅ 關鍵：恢復新增行為
    }
  
    renderHeader();
    renderBody();
    renderPager();
  }

  // ---------- Header buttons 顯示控制小工具 ----------
  function hideHeaderButtons(){
    if (Spec.editBtn)   Spec.editBtn.style.display   = 'none';
    if (Spec.addBtn)    Spec.addBtn.style.display    = 'none';
    if (Spec.deleteBtn) Spec.deleteBtn.style.display = 'none';
  }

  function resetHeaderButtonsDefault(){
    if (Spec.editBtn) {
      Spec.editBtn.style.display   = '';
      Spec.editBtn.textContent     = '編輯';
    }
    if (Spec.addBtn) {
      Spec.addBtn.style.display    = '';
      Spec.addBtn.textContent      = '新增';
    }
    if (Spec.deleteBtn) {
      Spec.deleteBtn.style.display = '';
      Spec.deleteBtn.textContent   = '刪除';
    }
  }

  // ---------- 新增 panel ----------
  function showAddPanel(){
    const panel = ensureAddPanel();
    if (!panel) return;

    // 進入新增模式：關閉編輯 / 刪除狀態，隱藏 header 按鈕
    Spec.isAddMode    = true;
    Spec.isEditMode   = false;
    Spec.isDeleteMode = false;

    panel.innerHTML = '';
    hideHeaderButtons();

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

      } else if (EDIT_FILTER_SELECT_LABELS.has(header)) {
        inputEl = document.createElement('select');
      
        // ✅ placeholder
        const ph = document.createElement('option');
        ph.value = '';
        ph.textContent = '-- 請選擇 --';
        inputEl.appendChild(ph);
      
        const opts = getOptionsFromFilterConfigValues(header);
        (opts || []).forEach(v=>{
          const opt = document.createElement('option');
          opt.value = v;
          opt.textContent = v;
          inputEl.appendChild(opt);
        });
      
        // ✅ 預設停在 placeholder
        inputEl.value = '';
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
      inputEl.dataset.label = header;
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

    // 取消：只由 panel 控制，關掉新增模式 + 還原 header 按鈕
    btnCancel.addEventListener('click', ()=>{
      Spec.isAddMode = false;
      panel.style.display = 'none';
      resetHeaderButtonsDefault();
    });

    // 儲存：成功後關掉 panel + 還原 header 按鈕
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

      console.log('[inspection_spec] new default_spec_table row =', newRow);

      if (API && API.frontEditor) {
        API.frontEditor({
          system: 'inspection',
          mode: 'add',
          tabKey: Spec.tabKey,
          Editor: editor,
          modify_time: MDFTime,
          row: newRow
        }).then(res => {
          console.log('[inspection_spec] front_editor add result', res);
          Spec.allRows.push(newRow);
          Spec.isAddMode = false;
          panel.style.display = 'none';
          resetHeaderButtonsDefault();
          applySpecFilter();
        }).catch(err => {
          console.error('[inspection_spec] front_editor add error', err);
          alert('新增失敗：' + (err && err.message ? err.message : err));
          // 失敗時維持新增 panel 開啟，header 按鈕持續隱藏，讓使用者可以修改後再按儲存
        });
      } else {
        Spec.allRows.push(newRow);
        Spec.isAddMode = false;
        panel.style.display = 'none';
        resetHeaderButtonsDefault();
        applySpecFilter();
      }
    });

    panel.style.display = '';
  }

  // ---------- Apply / Clear ----------
  let btnBound = false;

  function clearAllFilters(){
    const s = $('#inspection_specStart'); if (s) s.value = '';
    const e = $('#inspection_specEnd');   if (e) e.value = '';

    buildSpecFilters(null);
    Spec.currentPage = 1;
    applySpecFilter();
  }

  function bindSpecButtons(){
    if (btnBound) return;
    btnBound = true;

    const btnApply = $('#inspection_specApply');
    const btnClear = $('#inspection_specClear');
    const btnBottomClear = ensureBottomClearButton();

    if (btnApply) {
      btnApply.addEventListener('click', async ()=>{
        // EditSummary：按套用 → 讀日期 → 打 /api/edit_summary → 更新 EditSummary table
        if (Spec.tabKey === 'EditSummary') {
          const s = $('#inspection_specStart');
          const e = $('#inspection_specEnd');
          const startDate = s && s.value;
          const endDate   = e && e.value;
    
          if (!startDate || !endDate) {
            alert('請先選擇起訖日期');
            return;
          }
    
          btnApply.disabled = true;
          const oldText = btnApply.textContent;
          btnApply.textContent = '載入中...';
    
          try {
            if (!API || !API.fetchActionEditSummary) {
              console.warn('[inspection_spec] API.fetchActionEditSummary 未定義，改用本地篩選');
              const curSel = collectSelectionsFromState();
              buildSpecFilters(curSel);
              Spec.currentPage = 1;
              applySpecFilter();
              return;
            }
            /*
            
        
            */
    
            const payload = {
              system: 'inspection',
              tabKey: 'EditSummary',
              start_date: startDate,
              end_date: endDate
            };
    
            const res = await API.fetchActionEditSummary(payload);
    
            let newRows = [];
            if (res && res.prospecdict && res.prospecdict.EditSummary) {
              const es = res.prospecdict.EditSummary;
              if (Array.isArray(es)) {
                newRows = es;
              } else if (es && typeof es === 'object') {
                // 後端如果回 dict(index -> row)
                newRows = Object.values(es);
              }
            }
    
            console.log('[inspection_spec] EditSummary 新資料筆數 =', newRows.length);
    
            // ✅ 只更新 EditSummary 這個 tab 的 rows
            Spec.allRows = (newRows || []).slice();
            Spec.currentPage = 1;
    
            // filterConfig 不變（仍用 line_id / model / glass_type），重新建 MultiDD + 套用
            buildSpecFilters(null);
            applySpecFilter();
    
          } catch (err) {
            console.error('[inspection_spec] EditSummary 重新載入失敗', err);
            alert('重新載入 EditSummary 資料失敗：' + (err && err.message ? err.message : err));
          } finally {
            btnApply.disabled = false;
            btnApply.textContent = oldText || '套用';
          }
    
          return;
        }
    
        // 🔵 其他 tab 維持原本行為：只重建 MultiDD + 本地篩選
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
    // 🔵 default_spec_table：維持原本行為
    if (Spec.tabKey === 'default_spec_table') {
      if (Spec.isAddMode) {
        const panel = $('#inspection_spec-add-panel');
        if (panel) panel.style.display = 'none';
        Spec.isAddMode = false;
      }
    
      if (!Spec.isEditMode) {
        Spec.isEditMode = true;
        Spec.isDeleteMode = false;
    
        if (Spec.editBtn) { 
          Spec.editBtn.textContent = '儲存'; 
          Spec.editBtn.style.display = ''; 
        }
    
        if (Spec.addBtn)  { 
          Spec.addBtn.textContent  = '取消'; 
          Spec.addBtn.style.display  = '';
          Spec.addBtn.onclick = cancelEditMode;
        }
    
        if (Spec.deleteBtn) {
          Spec.deleteBtn.textContent = '刪除';
          Spec.deleteBtn.style.display = '';
        }
    
        renderHeader();
        renderBody();
        return;
      }
    
      // default_spec_table：編輯中 → 儲存
      saveEditChanges();
      return;
    }

    // 🟣 EditSummary：只用 Editor 那顆按鈕
    if (Spec.tabKey === 'EditSummary') {
      if (!Spec.isEditMode) {
        enterEditSummaryEditMode();
      } else {
        // 編輯中 → 儲存
        saveEditSummaryChanges();
      }
      return;
    }
  }

  // 🟣 EditSummary：進入編輯模式
  function enterEditSummaryEditMode(){
    // 備份目前的 allRows，給「取消」用
    Spec.editSummaryBackupRows = JSON.parse(JSON.stringify(Spec.allRows || []));
    Spec.isEditMode = true;

    if (Spec.editBtn) {
      Spec.editBtn.textContent = '儲存';
    }

    // 產生「取消」按鈕
    const head = $('#inspection_spec-info .inspection_spec-info-head');
    const actions = head && head.querySelector('.spec-header-actions');

    if (actions && !Spec.editSummaryCancelBtn) {
      const cancelBtn = document.createElement('button');
      cancelBtn.id = 'inspection_specEditSummaryCancel';
      cancelBtn.className = 'btn-spec-action';
      cancelBtn.textContent = '取消';
      cancelBtn.addEventListener('click', cancelEditSummaryEditMode);
      actions.appendChild(cancelBtn);
      Spec.editSummaryCancelBtn = cancelBtn;
    }

    renderHeader();
    renderBody();
    renderPager();
  }

    // 🟣 EditSummary：取消編輯（還原資料）
    function cancelEditSummaryEditMode(){
      if (!Spec.editSummaryBackupRows) {
        Spec.isEditMode = false;
      } else {
        // 還原資料
        Spec.allRows = JSON.parse(JSON.stringify(Spec.editSummaryBackupRows));
        Spec.editSummaryBackupRows = null;
        Spec.isEditMode = false;
      }
  
      if (Spec.editBtn) {
        Spec.editBtn.textContent = '編輯';
      }
      if (Spec.editSummaryCancelBtn) {
        Spec.editSummaryCancelBtn.remove();
        Spec.editSummaryCancelBtn = null;
      }
  
      // 重新建 filter + table
      buildSpecFilters(null);
      applySpecFilter();
    }
  
    // 🟣 EditSummary：儲存編輯結果（只處理 comment / action）
  async function saveEditSummaryChanges(){
    const table = $('#inspection_spec-table');
    if (!table) return;
    const tbody = table.querySelector('tbody');
    if (!tbody) return;

    const rows = Spec.filteredRows || [];
    const trs  = Array.from(tbody.querySelectorAll('tr'));

    const changes = [];

    trs.forEach(tr => {
      const idxStr = tr.dataset.rowIndex;
      const rowIndex = Number(idxStr);
      if (Number.isNaN(rowIndex)) return;
      const row = rows[rowIndex];
      if (!row) return;
      //console.log('api_row',api_row);
      const cInput = tr.querySelector('input[data-field="comment"]');
      const aInput = tr.querySelector('input[data-field="action"]');

      if (cInput) {
        const newVal = cInput.value;
        const oldRaw = row.comment;
        const oldVal = oldRaw == null ? '' : String(oldRaw);
        if (newVal !== oldVal) {
          changes.push({
            row,
            key: 'comment',
            oldValue: oldRaw,
            newValue: newVal
          });
          row.comment = newVal;
        }
      }

      if (aInput) {
        const newVal = aInput.value;
        const oldRaw = row.action;
        const oldVal = oldRaw == null ? '' : String(oldRaw);
        
        
        if (newVal !== oldVal) {
          changes.push({
            row,
            key: 'action',
            oldValue: oldRaw,
            newValue: newVal
          });
          row.action = newVal;
        }
      }
    });

    console.log('[inspection_spec] EditSummary changes =', changes);

    if (!changes.length) {
      // 沒變更就直接退出編輯
      Spec.isEditMode = false;
      if (Spec.editBtn) Spec.editBtn.textContent = '編輯';
      if (Spec.editSummaryCancelBtn) {
        Spec.editSummaryCancelBtn.remove();
        Spec.editSummaryCancelBtn = null;
      }
      renderHeader();
      renderBody();
      renderPager();
      return;
    }

    const MDFTime = getNowStr();
    const curEditor = editor || '預設';

    if (!API || !API.frontEditor) {
      alert('後端 front_editor API 未定義，無法儲存');
      return;
    }

    try {
      // 一筆一筆打：mode = 'comment' 或 'action'
      for (const ch of changes) {
        const payload = {
          system: 'inspection',
          mode: ch.key,               // 'comment' or 'action'
          tabKey: Spec.tabKey,
          row: ch.row,
          editor: curEditor,
          modify_time: MDFTime
        };
        payload[ch.key] = ch.newValue;

        await API.frontEditor(payload);
      }

      // 儲存成功後關閉編輯模式
      Spec.isEditMode = false;
      Spec.editSummaryBackupRows = null;

      if (Spec.editBtn) {
        Spec.editBtn.textContent = '編輯';
      }
      if (Spec.editSummaryCancelBtn) {
        Spec.editSummaryCancelBtn.remove();
        Spec.editSummaryCancelBtn = null;
      }

      renderHeader();
      renderBody();
      renderPager();
      updateFilterCount();

    } catch (err) {
      console.error('[inspection_spec] EditSummary 儲存失敗', err);
      alert('儲存失敗：' + (err && err.message ? err.message : err));
    }
  }
  

  function onClickAdd(){
    if (Spec.tabKey !== 'default_spec_table') return;

    // 若目前是編輯模式，先關掉編輯模式（會還原 header 按鈕文字）
    if (Spec.isEditMode) {
      cancelEditMode();
    }

    // 若目前是刪除模式，先關掉刪除模式並重畫 table
    if (Spec.isDeleteMode) {
      Spec.isDeleteMode = false;
      renderHeader();
      renderBody();
      renderPager();
    }

    // 已在新增模式就不重複進入
    if (Spec.isAddMode) return;

    // 進入新增模式的細節交給 showAddPanel 處理（含隱藏 header 按鈕）
    showAddPanel();
  }

  function onClickDelete(){
    if (Spec.tabKey !== 'default_spec_table') return;

    if (!Spec.isDeleteMode) {
      Spec.isDeleteMode = true;
      Spec.isEditMode   = false;
      Spec.isAddMode    = false;

      const panel = $('#inspection_spec-add-panel');
      if (panel) panel.style.display = 'none';

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

    renderHeader();
    renderBody();
    renderPager();
  }

  // ---------- 事件入口 ----------
  document.addEventListener("aoi_inspection:subtab-table", (ev)=>{
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
    console.log("[inspection_spec] detail =", detail);
    console.log("[inspection_spec] resolved rows length =", rows.length, rows[0]);

    Spec.tabKey   = tabKey;
    Spec.config   = config;
    Spec.allRows  = rows.slice();
    Spec.filterConfig = (config && config.filter_item_coldict) || {};
    console.log('Spec.filterConfig', Spec.filterConfig);
    Spec.filterOrder  = Object.keys(Spec.filterConfig || {});
    Spec.currentPage  = 1;
    Spec.isEditMode   = false;
    Spec.isAddMode    = false;
    Spec.isDeleteMode = false;

    console.log("[inspection_spec] Spec.allRows length =", Spec.allRows.length);

    setupHeaderTitle(tabKey, Spec.config);
    if (tabKey === 'EditSummary') {
      initEditSummaryDefaultDateRange();
    } else {
      // 其他 tab 不使用日期，順便清空
      const ds = $('#inspection_specStart'); if (ds) ds.value = '';
      const de = $('#inspection_specEnd');   if (de) de.value = '';
    }

    buildColConfig(Spec.config, Spec.allRows);
    renderHeader();

    buildSpecFilters(null);
    applySpecFilter();

    bindSpecButtons();
  });

})();