// static/js/colors.js
// 高對比度顏色方案（尺寸固定色 / 類別或 key 輪替高對比色）

(function () {
    // A. 尺寸（S/M/L/O）一眼辨識：亮藍 / 亮橘 / 亮綠 / 亮紅
    const SIZE_COLORS = {
      S: "#00B0FF", // vivid blue
      M: "#FF9800", // vivid orange
      L: "#00C853", // vivid green
      O: "#FF1744"  // vivid red
    };
  
    // B. 高對比循環色盤（色盲友善，深色底可視性佳）
    //   先用 ColorBrewer Set1，再補幾個飽和色，確保很多 key 時不會撞色太嚴重
    const KEY_CYCLE = [
       "#377eb8", "#4daf4a", "#984ea3", "#ff7f00",
      "#ffff33", "#a65628", "#f781bf", "#999999","#e41a1c",
      // 追加一輪高飽和
      "#ff3d00", "#2979ff", "#00e676", "#d500f9", "#ffab00",
      "#00bcd4", "#8bc34a", "#ff1744", "#00b0ff"
    ];
  
    // 若需要備選色盤，可再擴充
    const state = { useAlt: false };
  
    function hashIdx(s, m) {
      let h = 0, str = String(s || "");
      for (let i = 0; i < str.length; i++) h = ((h << 5) - h + str.charCodeAt(i)) | 0;
      return Math.abs(h) % m;
    }
  
    // === 對外 API ===
    window.ColorKit = window.ColorKit || {};
  
    // 尺寸 → 固定高對比色（只影響點徑大小與色參考，不做圖例也可）
    ColorKit.sizeColor = (sz) => {
      const k = String(sz || "").toUpperCase();
      return SIZE_COLORS[k] || "#ffffff";
    };
  
    // 依「目前選取 keys 的順序」生成 key→color 對應（高對比）
    ColorKit.mapKeys = (keys) => {
      const mapping = {};
      const arr = KEY_CYCLE;
      (keys || []).forEach((k, i) => {
        mapping[k] = arr[i % arr.length];
      });
      return mapping;
    };
  
    // 若你真的需要：單獨用雜湊選色（此案不建議使用）
    ColorKit.hashKeyColor = (key) => KEY_CYCLE[hashIdx(key, KEY_CYCLE.length)];
  
    // 給圖例或除錯用
    ColorKit.__SIZE = SIZE_COLORS;
    ColorKit.__KEYS = KEY_CYCLE;
  })();