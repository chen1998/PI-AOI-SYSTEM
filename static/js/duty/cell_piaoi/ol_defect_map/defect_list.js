// static/js/ol_defect_map/defect_list.js
(function () {
  const Bus = window.OLDefectMapBus;
  const State = window.OLDefectMapState;
  const Utils = window.OLDefectMapUtils;

  if (!Bus || !State || !Utils) {
    console.error("[ol-defect-map][defect_list] dependencies missing", {
      hasBus: !!Bus,
      hasState: !!State,
      hasUtils: !!Utils,
    });
    return;
  }

  const contId = "ol-defect-map-defect-lists-container";
  const countId = "ol-defect-map-defect-list-count";
  const galleryId = "ol-defect-map-gallery-grid";

  function ensureLightbox() {
    let lb = document.getElementById("ol-defect-map-img-lightbox");
    if (!lb) {
      lb = document.createElement("div");
      lb.id = "ol-defect-map-img-lightbox";
      lb.innerHTML = `
        <div class="lb-inner">
          <img alt="">
          <div class="lb-caption"></div>
        </div>
      `;
      document.body.appendChild(lb);
    }

    Object.assign(lb.style, {
      display: "none",
      position: "fixed",
      inset: "0",
      zIndex: "99999",
      background: "rgba(0,0,0,.72)",
      alignItems: "center",
      justifyContent: "center",
      padding: "24px"
    });

    const inner = lb.querySelector(".lb-inner");
    if (inner) {
      Object.assign(inner.style, {
        maxWidth: "92vw",
        maxHeight: "92vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: "10px"
      });
    }

    const img = lb.querySelector("img");
    if (img) {
      Object.assign(img.style, {
        maxWidth: "92vw",
        maxHeight: "82vh",
        objectFit: "contain",
        borderRadius: "8px",
        boxShadow: "0 8px 28px rgba(0,0,0,.45)",
        background: "#111"
      });
    }

    const cap = lb.querySelector(".lb-caption");
    if (cap) {
      Object.assign(cap.style, {
        color: "#fff",
        fontSize: "13px",
        textAlign: "center"
      });
    }

    lb.addEventListener("click", (e) => {
      if (e.target.id === "ol-defect-map-img-lightbox") {
        lb.style.display = "none";
      }
    });

    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape") lb.style.display = "none";
    });

    document.addEventListener("click", (e) => {
      const t = e.target;
      if (!(t && t.tagName === "IMG" && t.classList.contains("zoomable"))) return;

      const src = t.getAttribute("src");
      const capText = t.getAttribute("alt") || "";

      lb.querySelector("img").setAttribute("src", src);
      lb.querySelector(".lb-caption").textContent = capText;
      lb.style.display = "flex";
    });
  }
  ensureLightbox();

  function buildTableForKey(key, defects) {
    //console.log('defects',defects);
    const { test_time, sheet_id_chip_id, recipe_id, line_id, aoi } = Utils.parseKey(key);

    const wrap = document.createElement("div");
    wrap.className = "ol-defect-map-defect-table-wrap";

    const title = document.createElement("div");
    title.className = "ol-defect-map-defect-table-title";
    title.textContent = `${test_time} ｜ ${sheet_id_chip_id} ｜ ${recipe_id} ｜ ${line_id} ｜ ${aoi}`;
    wrap.appendChild(title);

    const tbl = document.createElement("table");
    tbl.className = "table ol-defect-map-defect-table";

    const thead = document.createElement("thead");
    thead.innerHTML = `
      <tr>
        <th class="ol-defect-map-index-col">#</th>
        <th>x</th>
        <th>y</th>
        <th>size</th>
        <th>type</th>
        <th>chip</th>
        <th>image</th>
      </tr>
    `;
    tbl.appendChild(thead);

    const tbody = document.createElement("tbody");
    const sorted = defects.slice().sort((a, b) => (a.x - b.x) || (a.y - b.y));

    sorted.forEach((d, idx) => {
      const src = Utils.buildImageUrl(d);
      //console.log('src', src);
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="ol-defect-map-index-col">${idx + 1}</td>
        <td>${d.x ?? ""}</td>
        <td>${d.y ?? ""}</td>
        <td>${d.size ?? ""}</td>
        <td>${d.type ?? ""}</td>
        <td>${d.chip ?? ""}</td>
        <td class="ol-defect-map-img-cell">
          ${src ? `<img loading="lazy" class="zoomable" src="${src}" alt="${sheet_id_chip_id} ${recipe_id} #${idx + 1}">` : ""}
        </td>
      `;
      tbody.appendChild(tr);
    });

    tbl.appendChild(tbody);
    wrap.appendChild(tbl);
    return wrap;
  }

  function buildGallery() {
    const host = document.getElementById(galleryId);
    if (!host) return;

    host.innerHTML = "";
    const keys = State.selectedKeys.slice();

    keys.forEach((k) => {
      const list = State.DefectCache[k] || [];

      const group = document.createElement("div");
      group.className = "ol-defect-map-gallery-group";

      const head = document.createElement("div");
      head.className = "ol-defect-map-gallery-title";
      head.textContent = k;
      group.appendChild(head);

      const grid = document.createElement("div");
      grid.className = "ol-defect-map-img-grid";

      list.forEach((d, idx) => {
        const src = Utils.buildImageUrl(d);
 
        const fig = document.createElement("figure");
        fig.className = "ol-defect-map-gallery-item";
        fig.innerHTML = `
          <div class="ol-defect-map-idx-badge">${idx + 1}</div>
          ${src ? `<img loading="lazy" class="zoomable" src="${src}" alt="${k} #${idx + 1}">` : ""}
        `;
        grid.appendChild(fig);
      });

      group.appendChild(grid);
      host.appendChild(group);
    });
  }

  
  function renderAll() {
    const cont = document.getElementById(contId);
    if (!cont) return;

    cont.innerHTML = "";
    const keys = State.selectedKeys.slice();

    keys.forEach((k) => {
      const list = State.DefectCache[k] || [];
      cont.appendChild(buildTableForKey(k, list));
    });

    const c = document.getElementById(countId);
    if (c) c.textContent = String(keys.length);

    buildGallery();
  }

  Bus.on("defect-refresh", renderAll);
  Bus.on("selection-changed", renderAll);
})();