// static/js/duty/cell_piaoi/aoi_density2/shared1.js
// 目的：集中「共同欄位/解析/Accessor/Key 產生」，讓 table.js / chart.js / service.js 共用同一套。

(function () {
  const AOI = (window.AOI_DENSITY = window.AOI_DENSITY || {});
  AOI.Shared = AOI.Shared || {};

  const SH = AOI.Shared;

  // =========================
  // 0) 欄位：以後端 DictData 為主
  // =========================
  // 用於 defect_map payload 去重與 state.defectGroups 的 key
  // 注意：
  // - 真正送後端時，service1.js 會把 pi_hour 改成 pi_hour_raw 優先。
  // - glass_size_detail 原始 JSON 會保留 test_time。
  SH.RAW_KEYS = [
    "pi_hour",
    "line_id",
    "aoi",
    "model",
    "glass_type",
    "recipe_id",
    "adc_def_code",
    "glass",
    "glass_size_detail"
  ];

  // 若後端未提供 DefectSize meta，前端 fallback 用這套
  SH.DEFECT_SIZE_BITS = { S: 1, M: 2, L: 4, O: 8 };
  SH.DEFECT_SIZE_MASK_KEY = "size_mask";

  // =========================
  // 1) 小工具：安全處理
  // =========================
  SH.isObj = function (o) {
    return o && typeof o === "object" && !Array.isArray(o);
  };

  SH.safeJsonParse = function (x, fallback) {
    if (x == null) return fallback;
    if (SH.isObj(x)) return x;
    if (typeof x !== "string") return fallback;

    const s = x.trim();
    if (!s) return fallback;

    try {
      return JSON.parse(s);
    } catch {
      return fallback;
    }
  };

  SH.toNumber = function (v, fallback) {
    const n = Number(v);
    return Number.isFinite(n) ? n : (fallback == null ? 0 : fallback);
  };

  SH.toString = function (v) {
    return v == null ? "" : String(v);
  };

  // =========================
  // 2) 時間：pi_hour 解析與顯示格式
  // =========================
  // 後端 pi_hour 可能是：
  // - "2026-01-28T12:00:00"
  // - "2026-01-28 12:00:00"
  // - "2026-01-28 12"
  // - "26-01-28 12"
  SH.parsePiHourToDate = function (s) {
    if (!s) return null;

    const raw = String(s).trim();
    if (!raw) return null;

    // ISO / ISO-like
    const d1 = new Date(raw);
    if (!isNaN(d1.getTime())) return d1;

    // "YYYY-MM-DD HH"
    if (/^\d{4}-\d{2}-\d{2}\s+\d{2}$/.test(raw)) {
      return new Date(raw.replace(" ", "T") + ":00:00");
    }

    // "YYYY-MM-DD HH:mm"
    if (/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}$/.test(raw)) {
      return new Date(raw.replace(" ", "T") + ":00");
    }

    // "YYYY-MM-DD HH:mm:ss"
    if (/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}$/.test(raw)) {
      return new Date(raw.replace(" ", "T"));
    }

    // "YY-MM-DD HH" -> 20YY
    if (/^\d{2}-\d{2}-\d{2}\s+\d{2}$/.test(raw)) {
      const [datePart, hh] = raw.split(/\s+/);
      const [yy, mm, dd] = datePart.split("-").map(Number);
      return new Date(2000 + yy, mm - 1, dd, Number(hh), 0, 0);
    }

    // "YYYY-MM-DD" / "YY-MM-DD"
    if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
      return new Date(raw + "T00:00:00");
    }

    if (/^\d{2}-\d{2}-\d{2}$/.test(raw)) {
      const [yy, mm, dd] = raw.split("-").map(Number);
      return new Date(2000 + yy, mm - 1, dd, 0, 0, 0);
    }

    // fallback
    const d2 = new Date(raw.replace(" ", "T"));
    return isNaN(d2.getTime()) ? null : d2;
  };

  // 輸出舊版 chart/table 友善的 key："YY-MM-DD HH"
  SH.fmtPiHourToShort = function (s) {
    const d = SH.parsePiHourToDate(s);
    if (!d) return String(s || "");

    const yy = String(d.getFullYear()).slice(-2);
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    const hh = String(d.getHours()).padStart(2, "0");

    return `${yy}-${mm}-${dd} ${hh}`;
  };

  // 輸出後端友善格式："YYYY-MM-DD HH:00:00"
  SH.fmtPiHourToBackend = function (s) {
    const d = SH.parsePiHourToDate(s);
    if (!d) return String(s || "");

    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    const hh = String(d.getHours()).padStart(2, "0");

    return `${yyyy}-${mm}-${dd} ${hh}:00:00`;
  };

  // =========================
  // 3) glass / glass_size_detail 解析
  // =========================
  SH.parseGlassList = function (glassField) {
    if (Array.isArray(glassField)) {
      return glassField
        .map(x => String(x).trim())
        .filter(Boolean);
    }

    if (glassField == null) return [];

    return String(glassField)
      .split(",")
      .map(x => x.trim())
      .filter(Boolean);
  };

  // 解析單片 glass 的 size stat。
  // 新版支援：
  // {
  //   "test_time": "2026-07-01 00:10:23",
  //   "S":0, "M":0, "L":1, "O":0, "T":1
  // }
  //
  // 舊版也支援：
  // "S:1 M:0 L:0 O:0 T:1"
  SH.parseSizeStats = function (stat) {
    const out = {
      test_time: "",
      S: 0,
      M: 0,
      L: 0,
      O: 0,
      T: 0
    };

    if (!stat) return out;

    if (typeof stat === "string") {
      const rx = /\b([SMLOT])\s*:\s*(\d+)/g;
      let m;

      while ((m = rx.exec(stat)) !== null) {
        out[m[1].toUpperCase()] = Number(m[2] || 0);
      }

      if (!/\bT\s*:/.test(stat)) {
        out.T = out.S + out.M + out.L + out.O;
      }

      return out;
    }

    if (SH.isObj(stat)) {
      out.test_time = String(
        stat.test_time ??
        stat.scan_time ??
        stat.TEST_TIME ??
        stat.SCAN_TIME ??
        ""
      ).trim();

      out.S = Number(stat.S || 0);
      out.M = Number(stat.M || 0);
      out.L = Number(stat.L || 0);
      out.O = Number(stat.O || 0);
      out.T = Number(
        stat.T != null
          ? stat.T
          : (out.S + out.M + out.L + out.O)
      );

      return out;
    }

    return out;
  };

  // 後端 glass_size_detail JSON：
  // {
  //   "GLASS_ID": {
  //     "test_time":"2026-07-01 00:10:23",
  //     "S":0,"M":0,"L":0,"O":1,"T":1
  //   }
  // }
  SH.parseGlassSizeDetail = function (gsdField) {
    const obj = SH.safeJsonParse(gsdField, {});
    const out = {};

    for (const [gid, stat] of Object.entries(obj || {})) {
      const glassId = String(gid).trim();
      if (!glassId) continue;
      out[glassId] = SH.parseSizeStats(stat);
    }

    return out;
  };

  SH.getPerGlassSizeStat = function (row, glassId) {
    const gid = String(glassId || "").trim();
    if (!gid) return null;

    const obj =
      row?.glass_size_detail_obj ||
      row?.__glassSizeDetailObj ||
      SH.parseGlassSizeDetail(row?.glass_size_detail);

    if (!obj || !SH.isObj(obj)) return null;

    return obj[gid] || null;
  };

  SH.getPerGlassTestTime = function (row, glassId) {
    const stat = SH.getPerGlassSizeStat(row, glassId);
    if (!stat || !SH.isObj(stat)) return "";

    return String(
      stat.test_time ||
      stat.scan_time ||
      stat.TEST_TIME ||
      stat.SCAN_TIME ||
      ""
    ).trim();
  };

  // =========================
  // 4) defect_map group key（去重/索引）
  // =========================
  SH.makeDefectGroupKey = function (row, keys) {
    const ks = Array.isArray(keys) ? keys : SH.RAW_KEYS;

    return ks.map(k => {
      if (k === "pi_hour") {
        return row?.pi_hour_raw ?? row?.pi_hour ?? "";
      }
      return row?.[k] ?? "";
    }).join("||");
  };

  SH.pickRowFields = function (row, keys) {
    const ks = Array.isArray(keys) ? keys : SH.RAW_KEYS;
    const out = {};

    ks.forEach(k => {
      if (!row) return;

      if (k === "pi_hour") {
        out.pi_hour = row.pi_hour_raw || row.pi_hour || "";
        return;
      }

      if (k in row) {
        out[k] = row[k];
      }
    });

    return out;
  };

  // =========================
  // 5) defect_map 單點圖：圖片路徑 helper
  // =========================
  SH.buildPicFullPath = function (p) {
    const direct = String(
      p?.image_url ||
      p?.img_url ||
      p?.url ||
      p?.img_file_url_path ||
      ""
    ).trim();

    if (direct) return direct;

    const base = String(p?.pic_path || "");
    const name = String(p?.pic_name || "");

    if (!base) return name;
    if (!name) return base;

    return base.replace(/[\\/]+$/, "") + "/" + name.replace(/^[\\/]+/, "");
  };

  // =========================
  // 6) 統一欄位 Accessor
  // =========================
  SH.U = SH.U || {};

  SH.U.line = r => String(r?.line_id ?? r?.line ?? "");
  SH.U.aoi = r => String(r?.aoi ?? r?.aoi_tool ?? "");
  SH.U.model = r => String(r?.model ?? r?.model_id ?? "");
  SH.U.side = r => String(r?.glass_type ?? r?.side ?? "");
  SH.U.recipe = r => String(r?.recipe_id ?? r?.recipe ?? "");
  SH.U.code = r => String(r?.adc_def_code ?? r?.ai_code_1 ?? r?.defect_code ?? "");
  SH.U.tick = r => String(r?.pi_hour ?? r?.tick_str ?? "");
  SH.U.tickRaw = r => String(r?.pi_hour_raw ?? r?.pi_hour ?? "");

  // tab summary 母體
  SH.U.tabName = r => String(r?.tab_name ?? "");
  SH.U.recipeFamily = r => String(r?.recipe_family ?? "");

  SH.U.tabGlass = r => Number(
    r?.tab_total_glass_cnt ??
    r?.total_glass_cnt ??
    0
  );

  SH.U.tabDefect = r => Number(
    r?.tab_total_defect_cnt ??
    r?.total_defect_cnt ??
    0
  );

  SH.U.tabDensity = r => Number(
    r?.tab_total_density ??
    r?.total_density ??
    0
  );

  // recipe 母體
  SH.U.recipeGlass = r => Number(
    r?.recipe_total_glass_cnt ??
    r?.glass_cnt ??
    0
  );

  SH.U.recipeDefect = r => Number(
    r?.recipe_total_defect_cnt ??
    0
  );

  SH.U.recipeDensity = r => Number(
    r?.recipe_total_density ??
    0
  );

  // 舊名稱相容：gTotal 代表 chart/table 使用的主要分母，優先 tab total
  SH.U.gTotal = r => Number(
    r?.tab_total_glass_cnt ??
    r?.total_glass_cnt ??
    r?.glass_cnt ??
    r?.recipe_total_glass_cnt ??
    r?.n_glasses ??
    0
  );

  SH.U.dTotal = r => Number(r?.defect_cnt ?? r?.n_rows ?? 0);
  SH.U.gCode = r => Number(r?.def_glass_cnt ?? r?.defect_code_glass_count ?? r?.code_glass_num ?? 0);
  SH.U.dens = r => Number(r?.density ?? 0);

  SH.U.glassList = r => SH.parseGlassList(r?.glass);
  SH.U.gsdObj = r => SH.parseGlassSizeDetail(r?.glass_size_detail);

})();
