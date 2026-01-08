// static/js/defect_list.js
(function(){
  const contId = 'defect-lists-container';
  const countId = 'dl-count';
  const galleryId = 'gallery-grid';

  // ---- Lightbox（建立一次）----
  function ensureLightbox(){
    if(document.getElementById('img-lightbox')) return;
    const lb = document.createElement('div');
    lb.id = 'img-lightbox';
    lb.innerHTML = `
      <div class="lb-inner">
        <img alt="">
        <div class="lb-caption"></div>
      </div>
    `;
    document.body.appendChild(lb);

    // 點背景關閉（點 inner 不關閉）
    lb.addEventListener('click', (e)=>{
      if(e.target.id === 'img-lightbox') lb.style.display = 'none';
    });
    // ESC 關閉
    window.addEventListener('keydown', (e)=>{
      if(e.key === 'Escape') lb.style.display = 'none';
    });

    // 事件代理：點任何 .zoomable 觸發
    document.addEventListener('click', (e)=>{
      const t = e.target;
      if(!(t && t.tagName === 'IMG' && t.classList.contains('zoomable'))) return;
      const src = t.getAttribute('src');
      const cap = t.getAttribute('alt') || '';
      lb.querySelector('img').setAttribute('src', src);
      lb.querySelector('.lb-caption').textContent = cap;
      lb.style.display = 'flex';
    });
  }
  ensureLightbox();
  // ----------------------------

  function buildTableForKey(key, defects){
    const { scantime, glass_id, recipe_id } = Utils.parseKey(key);
    const wrap = document.createElement('div');
    wrap.className = 'defect-table-wrap';

    const title = document.createElement('div');
    title.className = 'defect-table-title';
    title.textContent = `${scantime} ｜ ${glass_id} ｜ ${recipe_id}`;
    wrap.appendChild(title);

    const tbl = document.createElement('table');
    tbl.className = 'table defect-table';
    const thead = document.createElement('thead');
    thead.innerHTML = '<tr><th>#</th><th>x</th><th>y</th><th>size</th><th>type</th><th>chip</th><th>image</th></tr>';
    tbl.appendChild(thead);
    const tbody = document.createElement('tbody');

    // 排序：先 x 再 y（由近到遠）
    const sorted = defects.slice().sort((a,b)=> (a.x-b.x) || (a.y-b.y));
    const imgBase = State.imgBaseByKey[key] || '';

    sorted.forEach((d, idx)=>{
      const file = Utils.ensureJpg(d.img||'');
      const src  = file ? (window.IMG_HOST + imgBase + (file.toLowerCase().includes('.jpg') ? file : (file+'.jpg'))) : '';
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${idx+1}</td>
        <td>${d.x}</td>
        <td>${d.y}</td>
        <td>${d.size}</td>
        <td>${d.type}</td>
        <td>${d.chip||''}</td>
        <td class="img-cell mini">
          ${src ? `<img loading="lazy" class="zoomable" src="${src}" alt="${glass_id} ${recipe_id} #${idx+1}">` : ''}
          <div class="idx">${idx+1}</div>
        </td>
      `;
      tbody.appendChild(tr);
    });

    tbl.appendChild(tbody);
    wrap.appendChild(tbl);
    return wrap;
  }

  function buildGallery(){
    const host = document.getElementById(galleryId);
    if(!host) return;
    host.innerHTML = '';

    const keys = State.selectedKeys.slice();
    keys.forEach(k=>{
      const list = State.DefectCache[k]||[];
      const imgBase = State.imgBaseByKey[k]||'';

      const group = document.createElement('div');
      group.className = 'gallery-group';

      const head = document.createElement('div');
      head.className = 'gallery-head';
      head.textContent = k;
      group.appendChild(head);

      const grid = document.createElement('div');
      grid.className = 'gallery-grid-inner';

      list.forEach((d, idx)=>{
        const file = Utils.ensureJpg(d.img||'');
        const src  = file ? (window.IMG_HOST + imgBase + (file.toLowerCase().includes('.jpg') ? file : (file+'.jpg'))) : '';
        const fig = document.createElement('figure');
        fig.className = 'gallery-item';
        fig.innerHTML = `
          <div class="idx-tag">${idx+1}</div>
          ${src ? `<img loading="lazy" class="zoomable" src="${src}" alt="${k} #${idx+1}">` : ''}
        `;
        grid.appendChild(fig);
      });

      group.appendChild(grid);
      host.appendChild(group);
    });
  }

  function renderAll(){
    const cont = document.getElementById(contId);
    if(!cont) return;
    cont.innerHTML = '';

    const keys = State.selectedKeys.slice();
    keys.forEach(k=>{
      const list = State.DefectCache[k]||[];
      cont.appendChild(buildTableForKey(k, list));
    });

    const c = document.getElementById(countId);
    if(c) c.textContent = String(keys.length);

    buildGallery();
  }

  Bus.on('defect-refresh', renderAll);
  Bus.on('selection-changed', renderAll);
})();