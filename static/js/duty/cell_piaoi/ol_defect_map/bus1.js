// static/js/ol_defect_map/bus.js
(function () {
  const listeners = {};

  window.OLDefectMapBus = window.OLDefectMapBus || {
    on(evt, fn) {
      (listeners[evt] ||= []).push(fn);
    },
    emit(evt, payload) {
      (listeners[evt] || []).forEach((fn) => {
        try {
          fn(payload);
        } catch (e) {
          console.error("[OLDefectMapBus]", evt, e);
        }
      });
    }
  };

  window.OLDefectMapState = window.OLDefectMapState || {};
  const S = window.OLDefectMapState;

  S.filters = S.filters || {
    dateFrom: "",
    dateTo: "",
    glassQuery: "",
    recipeList: []
  };

  if (!(S.filters.recipes instanceof Set)) {
    S.filters.recipes = new Set();
  }
  if (!(S.filters.sizeSet instanceof Set)) {
    S.filters.sizeSet = new Set(["S", "M", "L", "O"]);
  }
  if (!(S.filters.typeSetSelected instanceof Set)) {
    S.filters.typeSetSelected = new Set();
  }
  if (typeof S.filters.glassQuery !== "string") {
    S.filters.glassQuery = "";
  }

  /*S.flags = S.flags || {
    matchSameGlass: false
  };*/
  S.flags = S.flags || {
    matchSameGlass: false,
    onlyMultiMeasuredGlass: false
  };

  S.selectedKeys = S.selectedKeys || [];
  S.currentAoi = S.currentAoi || null;
  S.AllRunInfo = S.AllRunInfo || {};
  S.rowByKey = S.rowByKey || {};
  S.DefectCache = S.DefectCache || {};
  S.keyColors = S.keyColors || {};
  S.typeSet = S.typeSet || new Set();
  S.offsetUm = S.offsetUm || 5;

  window.OLDefectMapUtils = window.OLDefectMapUtils || {};
  const U = window.OLDefectMapUtils;

  U.toDate = (s) => {
    if (!s) return new Date(0);
    return new Date(String(s).replace(" ", "T"));
  };

  U.keyFromRow = (r) => {
    const testTime = String(r.test_time || "").replace(" ", "T");
    const glassId = String(r.sheet_id_chip_id || "");
    const recipeId = String(r.recipe_id || "");
    const lineId = String(r.line_id || "");
    const aoi = String(r.aoi || "").toLowerCase();
    return `${testTime}|${glassId}|${recipeId}|${lineId}|${aoi}`;
  };

  U.parseKey = (key) => {
    const parts = String(key || "").split("|");
    return {
      test_time: parts[0] || "",
      sheet_id_chip_id: parts[1] || "",
      recipe_id: parts[2] || "",
      line_id: parts[3] || "",
      aoi: parts[4] || ""
    };
  };

  U.dist = (x1, y1, x2, y2) => {
    const dx = (+x1) - (+x2);
    const dy = (+y1) - (+y2);
    return Math.sqrt(dx * dx + dy * dy);
  };

  U.ensureJpg = (s) => {
    if (!s) return s;
    const low = String(s).toLowerCase();
    if (low.endsWith(".jpg") || low.endsWith(".jpeg") || low.endsWith(".png")) return s;
    if (low.includes(".jpg") || low.includes(".jpeg") || low.includes(".png")) return s;
    return s + ".jpg";
  };

  U.hashColor = (str) => {
    let h = 0;
    for (let i = 0; i < String(str || "").length; i++) {
      h = (h * 31 + String(str).charCodeAt(i)) | 0;
    }
    const r = 128 + (h & 0x3F);
    const g = 128 + ((h >> 6) & 0x3F);
    const b = 128 + ((h >> 12) & 0x3F);
    return `rgb(${r},${g},${b})`;
  };

  U.sizeBucket = (v) => {
    if (v == null) return "S";
    const s = String(v).trim().toUpperCase();
    if (["S", "M", "L", "O"].includes(s)) return s;

    const n = parseFloat(s);
    if (isNaN(n)) return "O";
    if (n <= 20) return "S";
    if (n <= 100) return "M";
    if (n <= 400) return "L";
    return "O";
  };

  U.unifyDefect = (d) => {
    const rawType =
      d.type ||
      d.adc_def_code ||
      d.retype_def_code ||
      d.predict_code ||
      d.judge_code ||
      "!";
  
    const typeVal = String(rawType).trim() || "!";
  
    return {
      x: +(d.x ?? d.X ?? d.pox_x1 ?? 0),
      y: +(d.y ?? d.Y ?? d.pox_y1 ?? 0),
      size: U.sizeBucket(d.size ?? d.defect_size),
      type: typeVal,
      img: String(d.img ?? d.image_file_name ?? ""),
      chip: String(d.chip ?? d.chip_id ?? d.chip_name ?? ""),
      adc_def_code: String(d.adc_def_code ?? ""),
      retype_def_code: String(d.retype_def_code ?? ""),
      image_file_path: String(d.image_file_path ?? ""),
      img_file_url_path: String(d.img_file_url_path ?? ""),
      pic_path:String(d.pic_path ?? ""),
      test_time: String(d.test_time ?? ""),
      pi_time: String(d.pi_time ?? ""),
      pi_hour: String(d.pi_hour ?? "")
    };
  };

  U.unique = (arr) => Array.from(new Set(arr));
  U.by = (arr, fn) => arr.slice().sort((a, b) => fn(a) - fn(b));

  U.buildImageUrl = (d) => {
    const picPath = String(d.pic_path ?? "").trim();
    if (/^https?:\/\//i.test(picPath)) {
      return picPath;
    }

    const img = U.ensureJpg(d.img ?? d.image_file_name ?? "");
    const rel = String(d.img_file_url_path ?? "").trim();
    
    
    if (!img || !rel) return "";
    if (/^https?:\/\//i.test(img)) return img;

    const base = "http://l6apaimg103/dms/CELAIDI_L6A";
    const cleanBase = base.replace(/\/+$/, "");
    const cleanRel = rel.replace(/^\/+/, "").replace(/\/+$/, "");
    const cleanImg = String(img).replace(/^\/+/, "");

    return `${cleanBase}/${cleanRel}/${cleanImg}`;
    
    

    
  };

  window.olDefectMapToast = function (msg) {
    let t = document.querySelector(".toast");
    if (!t) {
      t = document.createElement("div");
      t.className = "toast";
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.classList.add("show");
    setTimeout(() => t.classList.remove("show"), 1600);
  };
})();