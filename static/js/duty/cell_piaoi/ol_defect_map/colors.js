
// static/js/ol_defect_map/colors2.js
// OL Defect Map 專用高對比度顏色方案
// - 尺寸（S/M/L/O）固定色
// - 多 key 疊圖時的 key 輪替高對比色

(function () {
  const SIZE_COLORS = {
    S: "#00B0FF", // vivid blue
    M: "#FF9800", // vivid orange
    L: "#00C853", // vivid green
    O: "#FF1744"  // vivid red
  };

  const KEY_CYCLE = [
    "#377eb8", "#4daf4a", "#984ea3", "#ff7f00",
    "#ffff33", "#a65628", "#f781bf", "#999999", "#e41a1c",
    "#ff3d00", "#2979ff", "#00e676", "#d500f9", "#ffab00",
    "#00bcd4", "#8bc34a", "#ff1744", "#00b0ff"
  ];

  function hashIdx(s, m) {
    let h = 0;
    const str = String(s || "");
    for (let i = 0; i < str.length; i++) {
      h = ((h << 5) - h + str.charCodeAt(i)) | 0;
    }
    return Math.abs(h) % m;
  }

  window.OLDefectMapColorKit = window.OLDefectMapColorKit || {};

  // 尺寸固定色
  window.OLDefectMapColorKit.sizeColor = (sz) => {
    const k = String(sz || "").toUpperCase();
    return SIZE_COLORS[k] || "#ffffff";
  };

  // 依 keys 順序生成 key -> color 映射
  window.OLDefectMapColorKit.mapKeys = (keys) => {
    const mapping = {};
    (keys || []).forEach((k, i) => {
      mapping[k] = KEY_CYCLE[i % KEY_CYCLE.length];
    });
    return mapping;
  };

  // 若要單獨雜湊色
  window.OLDefectMapColorKit.hashKeyColor = (key) => {
    return KEY_CYCLE[hashIdx(key, KEY_CYCLE.length)];
  };

  // debug / legend
  window.OLDefectMapColorKit.__SIZE = SIZE_COLORS;
  window.OLDefectMapColorKit.__KEYS = KEY_CYCLE;
})();
