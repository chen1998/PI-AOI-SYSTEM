
// static/js/defect_map.js
(function(){
  const canvas = document.getElementById('defect-map-canvas');
  if(!canvas){ console.warn('[map] canvas not found'); return; }
  const ctx = canvas.getContext('2d');

  // === 全域 State 保障 =================================
  const State = window.State || (window.State = {});

  // === Viewport & transforms =========================
  const View = {
    pad: 20,
    scale: 1,
    tx: 0,
    ty: 0,
    boxZoom: false,
    box: null, // {x1,y1,x2,y2}
  };

  // === 常數（單位與預設邊界）=======================
  const UM_PER_MM = 1000;     // µm / mm
  const DEFAULT_BOUNDS = {    // 若目前無點，用大板尺寸（µm）
    minX: 0, minY: 0, maxX: 1850000, maxY: 1500000
  };

  // === Lightbox：點小圖放大 =========================
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
    lb.style.display = 'none';
    document.body.appendChild(lb);
    // 背景關閉
    lb.addEventListener('click', (e)=>{ if(e.target.id==='img-lightbox') lb.style.display='none'; });
    // ESC 關閉
    window.addEventListener('keydown', (e)=>{ if(e.key==='Escape') lb.style.display='none'; });
    // 任意 .zoomable 觸發
    document.addEventListener('click', (e)=>{
      const t = e.target;
      if(!(t && t.tagName==='IMG' && t.classList.contains('zoomable'))) return;
      const src = t.getAttribute('src');
      const cap = t.getAttribute('alt') || '';
      lb.querySelector('img').setAttribute('src', src);
      lb.querySelector('.lb-caption').textContent = cap;
      lb.style.display = 'flex';
    });
  }
  ensureLightbox();

  // === Key 顏色：高對比色盤 =========================
  const FALLBACK_CYCLE = [
    '#e41a1c','#377eb8','#4daf4a','#984ea3','#ff7f00',
    '#ffff33','#a65628','#f781bf','#999999'
  ];
  function mapKeysFallback(keys){
    const map = {};
    keys.forEach((k, i)=>{ map[k] = FALLBACK_CYCLE[i % FALLBACK_CYCLE.length]; });
    return map;
  }
  function ensureKeyColors(keys){
    try{
      if(window.ColorKit && typeof ColorKit.mapKeys === 'function'){
        State.keyColors = ColorKit.mapKeys(keys||[]);
      }else{
        State.keyColors = mapKeysFallback(keys||[]);
      }
    }catch(e){
      State.keyColors = mapKeysFallback(keys||[]);
    }
  }

  // === Key 圖例 =====================================
  function renderLegend(){
    const host = document.getElementById('map-legend');
    if(!host) return;
    host.innerHTML = '';
    const keys = State.selectedKeys || [];
    const palette = State.keyColors || {};
    keys.forEach(k=>{
      const color = palette[k] || '#ccc';
      const item = document.createElement('div');
      item.className = 'legend-item';
      const sw = document.createElement('span'); sw.className='c'; sw.style.background = color;
      const tt = document.createElement('span'); tt.className='t'; tt.textContent = k;
      item.appendChild(sw); item.appendChild(tt);
      host.appendChild(item);
    });
  }

  // === 篩選（Size/Type）==============================
  function getAllowedSizes(){
    return ['S','M','L','O'].filter(s=>{
      const el = document.getElementById(`size-${s}`);
      return !el || el.checked;
    });
  }
  function getAllowedTypes(){
    const host = document.getElementById('type-filters');
    if(!host) return null;
    const cbs = host.querySelectorAll('input[type=checkbox][data-type]');
    const on = [];
    cbs.forEach(cb=>{ if(cb.checked) on.push(cb.dataset.type); });
    return on.length? on : null;
  }

  // === 取點：把每個 key 的 defects 展平 =================
  function allPoints(keys){
    const pts = [];
    const palette = State.keyColors || {};
    keys.forEach(k=>{
      const lst = State.DefectCache[k] || [];
      const col = palette[k] || '#bbb';
      lst.forEach(d=>{
        const size = d.size ?? d.defect_size ?? '';        // 統一 size 欄
        const type = d.type ?? d.predict_code ?? '';
        pts.push({ k, x:+d.x, y:+d.y, size, type, color: col });
      });
    });
    return pts;
  }

  // === 邊界計算（若無點回傳預設板尺寸）=================
  function computeBounds(points){
    if(!points.length) return { ...DEFAULT_BOUNDS };
    let minX=+points[0].x, minY=+points[0].y, maxX=minX, maxY=minY;
    points.forEach(p=>{
      if(p.x<minX)minX=p.x; if(p.y<minY)minY=p.y;
      if(p.x>maxX)maxX=p.x; if(p.y>maxY)maxY=p.y;
    });
    // 邊界外擴 1%
    const w = Math.max(1, maxX-minX);
    const h = Math.max(1, maxY-minY);
    const padX = w * 0.01, padY = h * 0.01;
    return { minX:minX-padX, minY:minY-padY, maxX:maxX+padX, maxY:maxY+padY };
  }

  // === Offset 套用（使用者輸入『μm』；僅在按鈕時才生效）================
  const offsetInputEl = document.getElementById('offsetInput');  // 請在 HTML 標註 data-unit="um" 或 "mm"
  const applyOffsetBtn = document.getElementById('applyOffset');

  // 舊資料相容：若曾以 mm 存過，轉成 μm 一次
  if (typeof State.mapOffsetUm !== 'number') {
    if (typeof State.mapOffsetMm === 'number') {
      State.mapOffsetUm = State.mapOffsetMm * UM_PER_MM; // mm → μm
    }
  }

  function parseOffsetInputUm(){
    const raw = parseFloat(offsetInputEl?.value || '5000') || 0; // 預設 5000 μm ≈ 5 mm
    const unit = (offsetInputEl?.dataset?.unit || 'um').toLowerCase();
    return unit === 'mm' ? raw * UM_PER_MM : raw; // mm→μm；um 直接回傳
  }

  // State 初始化（μm）
  if (typeof State.mapOffsetUm !== 'number') {
    State.mapOffsetUm = parseOffsetInputUm();
  }

  // 取得目前 Offset（μm）
  function getOffsetUm(){ return Math.max(0, State.mapOffsetUm || 0); }

  if(applyOffsetBtn){
    applyOffsetBtn.addEventListener('click', ()=>{
      State.mapOffsetUm = parseOffsetInputUm(); // 以 μm 存
      Bus.emit('map-refresh');                  // 只在按鈕時觸發重繪
    });
  }

  // === 座標轉換（世界座標：µm；左上角為原點，y 向下增）===
  function worldToScreen(x,y, bbox){
    const W = canvas.clientWidth, H = canvas.clientHeight;
    const w = (bbox.maxX - bbox.minX) || 1;
    const h = (bbox.maxY - bbox.minY) || 1;
    const sx = ((x - bbox.minX) / w) * (W - 2*View.pad) + View.pad;
    const sy = ((y - bbox.minY) / h) * (H - 2*View.pad) + View.pad; // 不再上下翻轉
    return { x: sx*View.scale + View.tx, y: sy*View.scale + View.ty };
  }
  function screenToWorld(px,py, bbox){
    const W = canvas.clientWidth, H = canvas.clientHeight;
    const x0 = (px - View.tx) / View.scale;
    const y0 = (py - View.ty) / View.scale;
    const w = (bbox.maxX - bbox.minX) || 1;
    const h = (bbox.maxY - bbox.minY) || 1;
    const wx = ((x0 - View.pad) / (W - 2*View.pad)) * w + bbox.minX;
    const wy = ((y0 - View.pad) / (H - 2*View.pad)) * h + bbox.minY; // 不再上下翻轉
    return { x: wx, y: wy }; // µm
  }

  // === 軸線 + 刻度（mm；軸線移到上/左）================
  function drawAxes(){
    const W = canvas.clientWidth, H = canvas.clientHeight;
    ctx.save();
    ctx.strokeStyle = '#6b7280';
    ctx.lineWidth = 1;
    // X（上方）
    ctx.beginPath(); ctx.moveTo(8, 12); ctx.lineTo(W-8, 12); ctx.stroke();
    // Y（左側）
    ctx.beginPath(); ctx.moveTo(12, 8); ctx.lineTo(12, H-8); ctx.stroke();
    ctx.restore();
  }
  function niceStep(rangeMm, pxSpan){
    // 目標每格 ~80px
    const targetPx = 80;
    const n = Math.max(1, pxSpan / targetPx);
    const rough = rangeMm / n;
    const pow10 = Math.pow(10, Math.floor(Math.log10(Math.max(rough, 1e-9))));
    const cand = [1,2,5,10];
    let best = pow10;
    for(const c of cand){
      const step = c * pow10;
      best = step;
      if(rough <= step) break;
    }
    return best;
  }
  function drawAxisTicks(bbox){
    const W = canvas.clientWidth, H = canvas.clientHeight;

    // 視窗邊界（左上為原點）
    const leftScr  = View.tx + View.scale * View.pad;
    const rightScr = View.tx + View.scale * (W - View.pad);
    const topScr   = View.ty + View.scale * View.pad;
    const botScr   = View.ty + View.scale * (H - View.pad);

    // 對應世界座標
    const xWorldL = screenToWorld(leftScr,  topScr, bbox).x;
    const xWorldR = screenToWorld(rightScr, topScr, bbox).x;
    const yWorldT = screenToWorld(leftScr,  topScr,  bbox).y; // top
    const yWorldB = screenToWorld(leftScr,  botScr,  bbox).y; // bottom

    const xMinMm = xWorldL / UM_PER_MM, xMaxMm = xWorldR / UM_PER_MM;
    const yMinMm = yWorldT / UM_PER_MM, yMaxMm = yWorldB / UM_PER_MM;

    const xStep = niceStep(Math.max(1e-9, xMaxMm - xMinMm), (W - 2*View.pad));
    const yStep = niceStep(Math.max(1e-9, yMaxMm - yMinMm), (H - 2*View.pad));
    const xStart = Math.ceil(xMinMm / xStep) * xStep;
    const yStart = Math.ceil(yMinMm / yStep) * yStep;

    ctx.save();
    ctx.fillStyle = '#9aa3ad';
    ctx.strokeStyle = '#808695';
    ctx.lineWidth = 1;
    ctx.font = '10px system-ui, -apple-system, Segoe UI, Roboto, Noto Sans TC, Arial';

    // X ticks（畫在上方，向下刻）
    for(let mm = xStart; mm <= xMaxMm + 1e-9; mm += xStep){
      const um = mm * UM_PER_MM;
      const s = worldToScreen(um, yWorldT, bbox);
      ctx.beginPath(); ctx.moveTo(s.x, 12); ctx.lineTo(s.x, 16); ctx.stroke();
      const txt = String(Math.round(mm*1000)/1000);
      ctx.fillText(txt, s.x - ctx.measureText(txt).width/2, 26);
    }
    // Y ticks（畫在左側，向右刻）
    for(let mm = yStart; mm <= yMaxMm + 1e-9; mm += yStep){
      const um = mm * UM_PER_MM;
      const s = worldToScreen(xWorldL, um, bbox);
      ctx.beginPath(); ctx.moveTo(12, s.y); ctx.lineTo(16, s.y); ctx.stroke();
      const txt = String(Math.round(mm*1000)/1000);
      if (mm!==0){
        ctx.fillText(txt, 18, s.y + 3);
      }
    }

    ctx.fillStyle = '#cfd7df';
    ctx.fillText('mm', W-28, 22);
    ctx.restore();
  }

  // === 像素→μm 命中半徑換算（含最小 μm 下限）=========================
  function pxToUm(px, bbox){
    const W = canvas.clientWidth, H = canvas.clientHeight;
    const worldW = Math.max(1, bbox.maxX - bbox.minX); // μm
    const worldH = Math.max(1, bbox.maxY - bbox.minY); // μm
    const scrW = Math.max(1, (W - 2*View.pad) * (View.scale || 1));
    const scrH = Math.max(1, (H - 2*View.pad) * (View.scale || 1));
    const umPerPxX = worldW / scrW; // μm / px
    const umPerPxY = worldH / scrH; // μm / px
    return Math.max(umPerPxX, umPerPxY) * px; // 取較寬鬆者
  }
  const CLICK_HIT_PX = 8;       // 點擊容錯（像素）
  const HOVER_HIT_PX = 6;       // 浮標容錯（像素）
  const MIN_CLICK_HIT_UM = 80;  // μm 最小點擊半徑（避免極度縮放時太小）
  const MIN_HOVER_HIT_UM = 60;  // μm 最小 hover 半徑

  function getClickHitUm(bbox){
    return Math.max(pxToUm(CLICK_HIT_PX, bbox), MIN_CLICK_HIT_UM);
  }
  function getHoverHitUm(bbox){
    return Math.max(pxToUm(HOVER_HIT_PX, bbox), MIN_HOVER_HIT_UM);
  }

  // === ☆ 重疊星星 ===============================
  function drawStar(x, y, outerR = 5, innerR = 2.5, spikes = 5){
    ctx.save();
    ctx.beginPath();
    let rot = Math.PI / 2 * 3;
    ctx.moveTo(x, y - outerR);
    const step = Math.PI / spikes;
    for (let i = 0; i < spikes; i++) {
      ctx.lineTo(x + Math.cos(rot) * outerR, y + Math.sin(rot) * outerR);
      rot += step;
      ctx.lineTo(x + Math.cos(rot) * innerR, y + Math.sin(rot) * innerR);
      rot += step;
    }
    ctx.lineTo(x, y - outerR);
    ctx.closePath();
    ctx.fillStyle = '#FF1744';
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 1;
    ctx.fill();
    ctx.stroke();
    ctx.restore();
  }

  function drawOverlapStars(filteredPoints, bbox){
    const keys = State.selectedKeys || [];
    if(keys.length < 2) return;

    const offUm = getOffsetUm(); // 使用者設定（μm）

    const centers = [];
    for(let i=0; i<filteredPoints.length; i++){
      const a = filteredPoints[i];
      for(let j=i+1; j<filteredPoints.length; j++){
        const b = filteredPoints[j];
        if(a.k === b.k) continue;
        const d = Utils.dist(a.x, a.y, b.x, b.y);
        if(d <= offUm){
          centers.push({ x:(a.x+b.x)/2, y:(a.y+b.y)/2 });
        }
      }
    }
    if(!centers.length) return;

    const merged = [];
    const mergeDist = offUm * 0.5;
    centers.forEach(c=>{
      const hit = merged.find(m => Utils.dist(m.x, m.y, c.x, c.y) <= mergeDist);
      if(!hit) merged.push(c);
    });

    merged.forEach(c=>{
      const s = worldToScreen(c.x, c.y, bbox);
      drawStar(s.x, s.y, 5, 2.5, 5);
    });
  }

  // === 重繪 =========================================
  function drawAll(){
    ensureKeyColors(State.selectedKeys || []);
    renderLegend();

    const rect = canvas.getBoundingClientRect();
    canvas.width  = Math.max(1, Math.floor(rect.width));
    canvas.height = Math.max(1, Math.floor(rect.height));

    ctx.clearRect(0,0,canvas.width, canvas.height);
    drawAxes();

    const keys = State.selectedKeys || [];
    const pts  = allPoints(keys);
    const bbox = computeBounds(pts);

    const sizes = getAllowedSizes();
    const types = getAllowedTypes();

    const drawPts = pts.filter(p=>{
      if(sizes && !sizes.includes(p.size)) return false;
      if(types && !types.includes(p.type)) return false;
      return true;
    });

    drawPts.forEach(p=>{
      const s = worldToScreen(p.x, p.y, bbox);
      const r = p.size==='S'? 1.5 : p.size==='M'? 2.2 : p.size==='L'? 3.2 : 4.2;
      ctx.fillStyle = p.color;
      ctx.beginPath(); ctx.arc(s.x, s.y, r, 0, Math.PI*2); ctx.fill();
    });

    drawAxisTicks(bbox);
    drawOverlapStars(drawPts, bbox);

    if(View.boxZoom && View.box){
      const b = View.box;
      ctx.save();
      ctx.strokeStyle = '#10b981';
      ctx.setLineDash([5,4]);
      ctx.strokeRect(Math.min(b.x1,b.x2), Math.min(b.y1,b.y2), Math.abs(b.x2-b.x1), Math.abs(b.y2-b.y1));
      ctx.restore();
    }
  }

  // === Tooltip（滑鼠懸浮）============================
  ;(function injectTipCss(){
    if(document.getElementById('map-tip-style')) return;
    const st = document.createElement('style');
    st.id = 'map-tip-style';
    st.textContent = `
      .map-tooltip{
        position:absolute; z-index:10; pointer-events:none;
        background:#0f1115; color:#e8e8e8; border:1px solid #394151;
        border-radius:6px; padding:8px 10px; font-size:12px; line-height:1.35;
        max-width: 360px; box-shadow: 0 6px 16px rgba(0,0,0,.35);
      }
      .map-tooltip .row{ margin:4px 0; }
      .map-tooltip .key{ display:flex; align-items:center; gap:6px; margin:6px 0 2px; }
      .map-tooltip .sw{ width:12px; height:10px; border-radius:2px; display:inline-block; }
      .map-tooltip table{ width:100%; border-collapse:collapse; }
      .map-tooltip td{ border-top:1px solid #2b3240; padding:2px 4px; }
      .map-tooltip td:first-child{ width:48%; }
      .map-tooltip .muted{ color:#9aa3ad; }
    `;
    document.head.appendChild(st);
  })();

  const tipHost = document.getElementById('defect-map-container') || canvas.parentElement;
  const tip = document.createElement('div');
  tip.className = 'map-tooltip';
  tip.style.display = 'none';
  tipHost.appendChild(tip);

  function updateTooltip(px, py, contentHtml){
    tip.style.left = (px + 14) + 'px';
    tip.style.top  = (py + 14) + 'px';
    tip.innerHTML = contentHtml || '';
    tip.style.display = contentHtml ? 'block' : 'none';
  }

  function handleHover(ev){
    const rect = canvas.getBoundingClientRect();
    const px = ev.clientX - rect.left, py = ev.clientY - rect.top;

    const keys = State.selectedKeys;
    if(!keys || !keys.length){ updateTooltip(px, py, ''); return; }

    const pts = allPoints(keys);
    const bbox = computeBounds(pts);
    const world = screenToWorld(px, py, bbox);

    const hitUm = getHoverHitUm(bbox);

    let html = `<div class="row"><b>Cursor</b>：${(world.x/UM_PER_MM).toFixed(3)} mm, ${(world.y/UM_PER_MM).toFixed(3)} mm</div>`;

    keys.forEach(k=>{
      const color = (State.keyColors && State.keyColors[k]) || '#ccc';
      const list = State.DefectCache[k]||[];
      const within = list.filter(d => Utils.dist(world.x, world.y, +d.x, +d.y) <= hitUm);

      html += `<div class="key"><span class="sw" style="background:${color}"></span><b>${k}</b></div>`;
      if(within.length){
        html += `<table>`;
        within.forEach(d=>{
          const chip = d.chip ?? d.chip_name ?? '';
          const sz   = d.size ?? d.defect_size ?? '';
          html += `<tr><td>x=${Math.round(d.x)} µm, y=${Math.round(d.y)} µm</td><td>${chip}</td><td>${sz}</td></tr>`;
        });
        html += `</table>`;
      }else{
        html += `<div class="muted">（無符合）</div>`;
      }
    });

    updateTooltip(px, py, html);
  }

  // === Click：顯示 offset 影像（每 key 一區，四欄、可捲）===
  function handleClick(ev){
    const rect = canvas.getBoundingClientRect();
    const px = ev.clientX - rect.left, py = ev.clientY - rect.top;

    const keys = State.selectedKeys || [];
    const pts  = allPoints(keys);
    const bbox = computeBounds(pts);
    const world = screenToWorld(px, py, bbox);

    const hitUm = getClickHitUm(bbox);

    const container = document.getElementById('map-info-container');
    if(!container) return;
    container.innerHTML = '';

    keys.forEach(k=>{
      const list = State.DefectCache[k]||[];
      let within = list.filter(d => Utils.dist(world.x, world.y, +d.x, +d.y) <= hitUm);

      // 限距離 <= 0.25 * hitU
      if (!within.length && list.length){
        let best = null, bestDist = Infinity;
        list.forEach(d=>{
          const dd = Utils.dist(world.x, world.y, +d.x, +d.y);
          if (dd < bestDist){ bestDist = dd; best = d; }
        });
        if (best && bestDist <= hitUm * 0.25){
          within = [best];
        }
      }

      const block = document.createElement('div');
      block.className = 'offset-img-group';
      const title = document.createElement('div');
      title.className = 'offset-title';
      title.textContent = `${k} (${within.length})`;
      block.appendChild(title);

      const grid = document.createElement('div');
      grid.className = 'offset-img-grid';

      const imgBase = State.imgBaseByKey[k] || '';
      if(within.length){
        within.forEach((d, idx)=>{
          const file = Utils.ensureJpg(d.img || d.pic_name || '');
          if(!file) return;
          const src = (file.startsWith('http') ? file : (window.IMG_HOST + imgBase + file));

          const fig = document.createElement('figure');
          fig.className = 'img-card';
          fig.innerHTML = `<img loading="lazy" class="zoomable" src="${src}" alt="${k} #${idx+1}">`;
          grid.appendChild(fig);
        });
      }else{
        const empty = document.createElement('div');
        empty.className = 'muted';
        empty.textContent = '（無Defect符合）';
        grid.appendChild(empty);
      }

      block.appendChild(grid);
      container.appendChild(block);
    });
  }

  // === Map controls =================================
  const btnReset = document.getElementById('btnMapReset');
  const btnIn    = document.getElementById('btnZoomIn');
  const btnOut   = document.getElementById('btnZoomOut');
  const btnBox   = document.getElementById('btnBoxZoom');
  const btnClr   = document.getElementById('btnClearBox');

  if(btnReset) btnReset.addEventListener('click', ()=>{ View.scale=1; View.tx=0; View.ty=0; drawAll(); });
  if(btnIn)    btnIn.addEventListener('click', ()=>{ View.scale*=1.25; drawAll(); });
  if(btnOut)   btnOut.addEventListener('click', ()=>{ View.scale/=1.25; drawAll(); });
  if(btnBox)   btnBox.addEventListener('click', ()=>{ View.boxZoom = !View.boxZoom; View.box = null; drawAll(); });
  if(btnClr)   btnClr.addEventListener('click', ()=>{ View.box = null; drawAll(); });

  let dragging = false;
  canvas.addEventListener('mousedown', (ev)=>{
    if(View.boxZoom){
      const r = canvas.getBoundingClientRect();
      View.box = { x1: ev.clientX - r.left, y1: ev.clientY - r.top, x2: ev.clientX - r.left, y2: ev.clientY - r.top };
    }else{
      dragging = true; canvas.style.cursor = 'grabbing';
      View._lastX = ev.clientX; View._lastY = ev.clientY;
    }
  });
  window.addEventListener('mousemove', (ev)=>{
    if(View.boxZoom && View.box){
      const r = canvas.getBoundingClientRect();
      View.box.x2 = ev.clientX - r.left; View.box.y2 = ev.clientY - r.top;
      drawAll(); return;
    }
    if(dragging){
      View.tx += (ev.clientX - View._lastX);
      View.ty += (ev.clientY - View._lastY);
      View._lastX = ev.clientX; View._lastY = ev.clientY;
      drawAll();
    }
  });
  window.addEventListener('mouseup', ()=>{
    if(View.boxZoom && View.box){
      const b = View.box;
      if(b && Math.abs(b.x2-b.x1)>10 && Math.abs(b.y2-b.y1)>10){
        // 簡易：以框選中心為基準放大
        View.scale *= 1.4;
        View.tx -= (Math.min(b.x1,b.x2) + Math.abs(b.x2-b.x1)/2 - canvas.clientWidth/2);
        View.ty -= (Math.min(b.y1,b.y2) + Math.abs(b.y2-b.y1)/2 - canvas.clientHeight/2);
      }
      View.box = null; drawAll();
    }
    dragging = false; canvas.style.cursor = 'default';
  });

  // 事件：hover + click
  canvas.addEventListener('mousemove', handleHover);
  canvas.addEventListener('mouseleave', ()=> updateTooltip(0,0,''));
  canvas.addEventListener('click', handleClick);

  // === Bus 事件：重繪與圖例 ===
  Bus.on('defect-refresh', drawAll);
  Bus.on('selection-changed', drawAll);
  Bus.on('map-refresh', drawAll);

  Bus.on('selection-changed', renderLegend);
  Bus.on('defect-refresh',    renderLegend);
  Bus.on('map-refresh',       renderLegend);

  // 若外部清除 offset 影像群組
  Bus.on('clear-offset-images', ()=>{
    const container = document.getElementById('map-info-container');
    if(container) container.innerHTML = '';
  });

  // 初始繪製
  drawAll();
})();