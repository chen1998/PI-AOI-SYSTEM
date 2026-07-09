// static/js/bpi_area/bpi_density/shared1.js
// BPI Density 共用工具：欄位、時間、glass_size_detail、Accessor、ParamDict helpers

(function () {
  const AOI = (window.AOI_BPI_DENSITY = window.AOI_BPI_DENSITY || {});
  AOI.Shared = AOI.Shared || {};

  const SH = AOI.Shared;

  // =========================
  // 0) 欄位：以後端 DictData 為主
  // =========================
  // 用於 defect_map payload 去重與 state.defectGroups 的 key
  SH.RAW_KEYS = [
    "aoi",
    "model",
    "scan_hour",
    "cassette_id",
    "glass_side",
    "recipe_id",
    "glass_list",
    "glass_size_detail"
  ];

  // 若後端未提供 DefectSize meta，前端 fallback 用這套
  SH.DEFECT_SIZE_BITS = { S: 1, M: 2, L: 4, O: 8 };
  SH.DEFECT_SIZE_MASK_KEY = "size_mask";

  // =========================
  // 1) 小工具
  // =========================
  SH.isObj = (o) => o && typeof o === "object" && !Array.isArray(o);

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

  SH.cleanStr = function (v) {
    if (v == null) return "";
    const s = String(v).trim();
    if (!s) return "";
    if (["nan", "none", "null", "nat", "<na>"].includes(s.toLowerCase())) return "";
    return s;
  };

  SH.num = function (v) {
    const n = Number(v);
    return Number.isFinite(n) ? n : 0;
  };

  // =========================
  // 2) 新版 ParamDict helpers
  // =========================
  SH.getBpiDensityConfig = function (paramDict) {
    const pd = paramDict || AOI.state?.paramDict || {};
    return pd.bpiDensity || pd || {};
  };

  SH.getBpiDensityFilterItemDict = function (paramDict) {
    const cfg = SH.getBpiDensityConfig(paramDict);
    return cfg.filtetItemKeyDict || cfg.filterItemKeyDict || {};
  };

  SH.getBpiDensityFilterOptionDict = function (paramDict) {
    const cfg = SH.getBpiDensityConfig(paramDict);
    return cfg.filterOptionDict || {};
  };

  SH.getBpiDensityHourlyTable = function (paramDict) {
    const cfg = SH.getBpiDensityConfig(paramDict);
    return cfg.hourlyTable || {};
  };

  SH.getBpiDensityHourlyKeyGroup = function (paramDict) {
    const cfg = SH.getBpiDensityConfig(paramDict);
    return cfg.hourlyTable_key_group || {};
  };

  SH.getBpiDensityUniGlassInfo = function (paramDict) {
    const cfg = SH.getBpiDensityConfig(paramDict);
    return cfg.uniGlassInfo || {};
  };

  // =========================
  // 3) 時間：scan_hour 解析與顯示格式
  // =========================
  SH.parseScanHourToDate = function (s) {
    if (!s) return null;

    const raw = String(s).trim();
    if (!raw) return null;

    const d1 = new Date(raw);
    if (!isNaN(d1.getTime())) return d1;

    if (/^\d{4}-\d{2}-\d{2}\s+\d{2}$/.test(raw)) {
      return new Date(raw.replace(" ", "T") + ":00:00");
    }

    if (/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}$/.test(raw)) {
      return new Date(raw.replace(" ", "T") + ":00");
    }

    if (/^\d{2}-\d{2}-\d{2}\s+\d{2}$/.test(raw)) {
      const [datePart, hh] = raw.split(/\s+/);
      const [yy, mm, dd] = datePart.split("-").map(Number);
      return new Date(2000 + yy, mm - 1, dd, Number(hh), 0, 0);
    }

    if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
      return new Date(raw + "T00:00:00");
    }

    if (/^\d{2}-\d{2}-\d{2}$/.test(raw)) {
      const [yy, mm, dd] = raw.split("-").map(Number);
      return new Date(2000 + yy, mm - 1, dd, 0, 0, 0);
    }

    const d2 = new Date(raw.replace(" ", "T"));
    return isNaN(d2.getTime()) ? null : d2;
  };

  SH.fmtScanHourToShort = function (s) {
    const d = SH.parseScanHourToDate(s);
    if (!d) return String(s || "");

    const yy = String(d.getFullYear()).slice(-2);
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    const hh = String(d.getHours()).padStart(2, "0");

    return `${yy}-${mm}-${dd} ${hh}`;
  };

  // 相容舊寫法
  SH.parsePiHourToDate = SH.parseScanHourToDate;
  SH.fmtPiHourToShort = SH.fmtScanHourToShort;

  // =========================
  // 4) glass / glass_size_detail 解析
  // =========================
  SH.parseGlassList = function (glassField) {
    if (Array.isArray(glassField)) {
      return glassField.map(x => String(x).trim()).filter(Boolean);
    }

    if (glassField == null) return [];

    return String(glassField)
      .split(",")
      .map(x => x.trim())
      .filter(Boolean);
  };

  SH.parseSizeStats = function (stat) {
    const out = { S: 0, M: 0, L: 0, O: 0, T: 0 };
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
      out.S = Number(stat.S || 0);
      out.M = Number(stat.M || 0);
      out.L = Number(stat.L || 0);
      out.O = Number(stat.O || 0);
      out.T = Number(stat.T != null ? stat.T : (out.S + out.M + out.L + out.O));
      return out;
    }

    return out;
  };

  SH.parseGlassSizeDetail = function (gsdField) {
    const obj = SH.safeJsonParse(gsdField, {});
    const out = {};

    for (const [gid, stat] of Object.entries(obj || {})) {
      const base = SH.parseSizeStats(stat);
      const meta = SH.isObj(stat) ? stat : {};

      out[String(gid).trim()] = {
        ...base,
        line_id: String(meta.line_id || ""),
        test_time: String(meta.test_time || "")
      };
    }

    return out;
  };

  // =========================
  // 5) defect_map group key
  // =========================
  SH.makeDefectGroupKey = function (row, keys) {
    const ks = Array.isArray(keys) ? keys : SH.RAW_KEYS;
    return ks.map(k => (row?.[k] ?? "")).join("||");
  };

  SH.pickRowFields = function (row, keys) {
    const ks = Array.isArray(keys) ? keys : SH.RAW_KEYS;
    const out = {};

    ks.forEach(k => {
      if (row && (k in row)) out[k] = row[k];
    });

    return out;
  };

  // =========================
  // 6) 圖片路徑 helper
  // =========================
  SH.buildPicFullPath = function (p) {
    const base = String(p?.pic_path || "");
    const name = String(p?.pic_name || "");

    if (!base) return name;
    if (!name) return base;

    return (base.endsWith("\\") || base.endsWith("/"))
      ? (base + name)
      : (base + "\\" + name);
  };

  // =========================
  // 7) 統一欄位 Accessor
  // =========================
  SH.U = SH.U || {};

  SH.U.aoi     = r => String(r?.aoi ?? "");
  SH.U.model   = r => String(r?.model ?? "");
  SH.U.cst     = r => String(r?.cassette_id ?? r?.cst ?? "");
  SH.U.side    = r => String(r?.glass_side ?? r?.side ?? "");
  SH.U.recipe  = r => String(r?.recipe_id ?? r?.recipe ?? "");
  SH.U.piType  = r => String(r?.pi_type ?? "");
  SH.U.tick    = r => String(r?.scan_hour ?? r?.tick_str ?? "");

  SH.U.gTotal  = r => Number(r?.glass_count ?? 0);
  SH.U.dTotal  = r => Number(r?.total_defect_count ?? 0);
  SH.U.dens    = r => Number(r?.density ?? 0);

  SH.U.sCnt    = r => Number(r?.small_defect_count ?? 0);
  SH.U.mCnt    = r => Number(r?.middle_defect_count ?? 0);
  SH.U.lCnt    = r => Number(r?.large_defect_count ?? 0);
  SH.U.oCnt    = r => Number(r?.over_defect_count ?? 0);

  SH.U.glassList = r => SH.parseGlassList(r?.glass_list);
  SH.U.gsdObj    = r => SH.parseGlassSizeDetail(r?.glass_size_detail);
})();