(function () {
  'use strict';

  const MOD = (window.AOI_DENSITY = window.AOI_DENSITY || {});
  const C = (MOD.ChartCore = MOD.ChartCore || {});

  function buildLayout(dom, columns, global) {
    const L = C.LAYOUT;
    const padTop = L.legendBlockH + L.titleGap + L.headerTextH;
    const leftMargin = L.baseLeft + L.gutterLineW + L.gutterGap + L.gutterModelW + 25;
    const maxRows = Math.max(1, global.order.length);

    const totalH = padTop + maxRows * L.rowH + (maxRows - 1) * L.rowGap + L.padBottom + L.bottomExtra;
    dom.style.height = `${totalH}px`;
    dom.style.minHeight = `${totalH}px`;

    const width = Math.max(dom.clientWidth || L.minChartWidth, L.minChartWidth);
    const nCols = Math.max(1, columns.length);
    const colWidth = Math.max(
      L.minColWidth,
      Math.floor((width - leftMargin - L.rightMargin - (nCols - 1) * L.colGap) / nCols)
    );

    const totalChartWidth = leftMargin + nCols * (colWidth + L.colGap) - L.colGap + L.rightMargin;
    dom.style.width = `${totalChartWidth}px`;
    dom.style.minWidth = `${totalChartWidth}px`;

    return {
      ...L,
      padTop,
      leftMargin,
      maxRows,
      totalH,
      width,
      nCols,
      colWidth,
      totalChartWidth
    };
  }

  function calcOpacity(interopState, aoi, code, rowKey, xIdx) {
    const st = interopState || {};
    const selectedTicks = st.selectedTicks instanceof Set
      ? st.selectedTicks
      : new Set();
  
    let passTick = true;
  
    if (selectedTicks.size > 0) {
      passTick = selectedTicks.has(`${xIdx}|${aoi}|${code}`);
    }
  
    let passRow = true;
  
    if (st.focusRowKey && st.focusRowKey !== rowKey) {
      passRow = false;
    }
  
    if (passTick && passRow) return 1;
    if (!passTick) return 0.18;
    if (!passRow) return 0.28;
  
    return 1;
  }

  function buildGroups(columns) {
    const groups = [];
    let curAoi = null;
    let start = 0;

    columns.forEach((c, idx) => {
      if (c.aoi !== curAoi) {
        if (curAoi != null) {
          groups.push({ aoi: curAoi, startCol: start, count: idx - start });
        }
        curAoi = c.aoi;
        start = idx;
      }

      if (idx === columns.length - 1) {
        groups.push({ aoi: c.aoi, startCol: start, count: idx - start + 1 });
      }
    });

    return groups;
  }

  function makeSeriesData(row, col, aoi, code, rowKey, interopState, ctx, type) {
    const xTicks = col.xTicks || [];

    if (type === 'glassTotal') {
      return (row.tabTotalGlassArr || []).map((v, i) => ({
        value: Math.trunc(Number(v || 0)),
        itemStyle: { opacity: calcOpacity(interopState, aoi, code, rowKey, i) }
      }));
    }

    if (type === 'defectGlass') {
      return (row.codeGlasses || []).map((v, i) => ({
        value: v,
        itemStyle: { opacity: calcOpacity(interopState, aoi, code, rowKey, i) }
      }));
    }

    if (type === 'density') {
      return (row.density || []).map((v, i) => {
        const totalDensity = Number(row.tabTotalDensity?.[i]);
        const needAlert = C.shouldTotalDensityPointAlert(totalDensity);
        const tabTG = Number(row.tabTotalGlassArr?.[i] ?? 0);
        const tabTD = Number(row.tabTotalDefArr?.[i] ?? 0);
        const tickStr = xTicks?.[i] || '';
        const alertRow = needAlert
          ? C.buildAlertRowFromChartPoint(row, tickStr, aoi, code, totalDensity, tabTG, tabTD)
          : null;

        if (alertRow) ctx.totalDensityAlertRows.push(alertRow);

        return {
          value: v,
          needAlert,
          alertRow,
          itemStyle: {
            opacity: v == null ? 0 : calcOpacity(interopState, aoi, code, rowKey, i),
            color: needAlert ? C.ALERT_CONFIG.blinkColorA : C.CHART_COLOR.densityPoint
          }
        };
      });
    }

    if (type === 'totalDensity') {
      return (row.tabTotalDensity || []).map((v, i) => {
        const totalDensity = Number(v);
        const needAlert = C.shouldTotalDensityPointAlert(totalDensity);
        const tabTG = Number(row.tabTotalGlassArr?.[i] ?? 0);
        const tabTD = Number(row.tabTotalDefArr?.[i] ?? 0);
        const tickStr = xTicks?.[i] || '';
        const alertRow = needAlert
          ? C.buildAlertRowFromChartPoint(row, tickStr, aoi, code, totalDensity, tabTG, tabTD)
          : null;

        if (alertRow) ctx.totalDensityAlertRows.push(alertRow);

        return {
          value: Number.isFinite(totalDensity) ? totalDensity : null,
          needAlert,
          alertRow,
          hasSamePoint: row.samePointArr?.[i] === true,
          itemStyle: {
            opacity: v == null ? 0 : calcOpacity(interopState, aoi, code, rowKey, i),
            color: needAlert ? C.ALERT_CONFIG.blinkColorA : C.CHART_COLOR.totalDensityPoint
          }
        };
      });
    }

    return [];
  }

  function buildDensityLabel(ctx) {
    const heavy = !!ctx.heavy;

    return {
      show: !heavy,
      position: 'top',
      distance: 2,
      formatter: p => {
        const vv = Array.isArray(p.value) ? p.value[1] : p.value;
        const hasValue = typeof vv === 'number' && Number.isFinite(vv);
        if (!hasValue) return '';

        if (p?.data?.needAlert) {
          return `{alert|爆點}\n{gap| }\n{val|${vv.toFixed(2)}}`;
        }

        return `{val|${vv.toFixed(2)}}`;
      },
      backgroundColor: 'transparent',
      padding: [0, 0],
      borderRadius: 0,
      rich: {
        alert: {
          color: '#FF0000',
          fontSize: 12,
          fontWeight: 800,
          lineHeight: 14,
          align: 'center',
          backgroundColor: C.CHART_THEME.labelBg,
          padding: [0, 0, 0, 0]
        },
        gap: {
          fontSize: 1,
          lineHeight: 3,
          backgroundColor: 'transparent'
        },
        val: {
          color: C.CHART_THEME.labelText,
          fontSize: 10,
          lineHeight: 14,
          align: 'center',
          backgroundColor: C.CHART_THEME.labelBg,
          padding: C.CHART_THEME.labelPad,
          borderRadius: C.CHART_THEME.labelRadius
        }
      }
    };
  }

  function buildTotalDensityLabel(ctx) {
    const heavy = !!ctx.heavy;

    return {
      show: !heavy,
      position: 'top',
      distance: 10,
      formatter: p => {
        const vv = Array.isArray(p.value) ? p.value[1] : p.value;
        const valText = typeof vv === 'number' && Number.isFinite(vv) ? vv.toFixed(2) : '';

        if (p?.data?.hasSamePoint && ctx.legendSelectedState[C.SERIES_NAMES.totalDensity] === true) {
          return valText ? `{sp|同點}\n{val|${valText}}` : '{sp|同點}';
        }

        return valText ? `{val|${valText}}` : '';
      },
      backgroundColor: 'transparent',
      padding: [0, 0],
      rich: {
        sp: {
          color: '#FFDC00',
          fontSize: 12,
          fontWeight: 800,
          lineHeight: 15,
          align: 'center',
          backgroundColor: C.CHART_THEME.labelBg,
          padding: [1, 4],
          borderRadius: 3
        },
        val: {
          color: C.CHART_THEME.labelText,
          fontSize: 10,
          lineHeight: 14,
          align: 'center',
          backgroundColor: C.CHART_THEME.labelBg,
          padding: C.CHART_THEME.labelPad,
          borderRadius: C.CHART_THEME.labelRadius
        }
      }
    };
  }

  function pushSpecMarkLine(series, args) {
    const { name, xAxisIndex, yAxisIndex, value, color, labelText, z = 30 } = args;
    if (value == null || !Number.isFinite(Number(value))) return;

    series.push({
      name,
      type: 'line',
      xAxisIndex,
      yAxisIndex,
      data: [],
      showSymbol: false,
      silent: true,
      tooltip: { show: false },
      lineStyle: { opacity: 0 },
      z,
      zlevel: 1,
      clip: false,
      markLine: {
        silent: true,
        symbol: ['none', 'none'],
        lineStyle: {
          type: 'dashed',
          width: 1.3,
          color
        },
        label: {
          show: true,
          position: 'end',
          formatter: labelText,
          color: C.CHART_THEME.mlText,
          backgroundColor: C.CHART_THEME.mlBg,
          padding: [2, 2],
          borderRadius: 3,
          fontSize: 10,
          offset: [10, 0]
        },
        data: [{ yAxis: value }]
      }
    });
  }

  function buildTooltip(ctx, columns, rawRows, rowIndex) {
    return {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
        snap: true
      },
      renderMode: 'html',
      extraCssText: 'max-width:560px; white-space:normal; line-height:1.35;',
      formatter: params => {
        const list = Array.isArray(params) ? params : [params];
        const p0 = list[0] || {};
        const [, aoi = '', code = '', rIdxStr = '0'] = String(p0.seriesId || '').split(':');
        const rIdx = Number(rIdxStr) || 0;
        const col = (columns || []).find(c => c.aoi === aoi && c.code === code);
        const tickStr = p0.axisValue != null ? String(p0.axisValue) : (col ? col.xTicks[p0.dataIndex] : '');
        const row = col ? col.rows[rIdx] : null;

        if (!row || !tickStr) return '';

        const pick = C.rowsByCriteriaFromIndex(rowIndex, rawRows, {
          aoi,
          code,
          line: row.line_id,
          model: row.model,
          side: row.glass_type,
          tick: tickStr
        });

        const idx = col.xTicks.indexOf(tickStr);
        const tabTG = idx >= 0 ? Number(row.tabTotalGlassArr?.[idx] ?? 0) : 0;
        const tabTD = idx >= 0 ? Number(row.tabTotalDefArr?.[idx] ?? 0) : 0;
        const tabD = idx >= 0 ? row.tabTotalDensity?.[idx] : null;
        const dens = idx >= 0 && row.density[idx] != null ? Number(row.density[idx]).toFixed(2) : '';
        const gCode = idx >= 0 ? row.codeGlasses[idx] : null;
        const tooltipCnt = C.calcTooltipCountsFromRows(pick);

        const sizeLine = [
          ['S', tooltipCnt.S],
          ['M', tooltipCnt.M],
          ['L', tooltipCnt.L],
          ['O', tooltipCnt.O]
        ]
          .filter(([, v]) => v > 0)
          .map(([k, v]) => `${k}${Math.trunc(v)}`)
          .join(', ');

        const samePointText = row.samePointArr?.[idx] === true ? 'Yes' : '';

        const kv = [
          ['density', dens],
          ['Total density (tab)', tabD == null ? '' : Number(tabD).toFixed(2)],
          ['Total defect count (tab)', String(Math.trunc(tabTD))],
          ['Total glass count (tab)', String(Math.trunc(tabTG))],
          ['defect glass count', gCode == null ? '' : String(Math.trunc(gCode))],
          ['defect count', String(Math.trunc(tooltipCnt.dCode))],
          ['S/M/L/O', sizeLine],
          ['same point', samePointText]
        ].filter(([, v]) => v !== '' && v != null);

        return kv.map(([k, v]) => `<div><b>${k}</b>: ${v}</div>`).join('');
      }
    };
  }

  function addTitleGraphics(graphics, columns, global, layout) {
    const groups = buildGroups(columns);

    groups.forEach(g => {
      const left = layout.leftMargin + g.startCol * (layout.colWidth + layout.colGap);
      const right = left + g.count * layout.colWidth + (g.count - 1) * layout.colGap;

      graphics.push({
        type: 'text',
        left: (left + right) / 2,
        top: layout.legendBlockH + 4,
        style: {
          text: g.aoi,
          fill: '#89a6ff',
          fontWeight: 800,
          fontSize: 13,
          textAlign: 'center'
        }
      });
    });

    const lineX = 16 + Math.floor(26 / 2);
    const modelX = 16 + 26 + 8 + Math.floor(26 / 2);

    (global.lineGroups || []).forEach(gp => {
      const top = layout.padTop + gp.start * (layout.rowH + layout.rowGap);
      graphics.push({
        type: 'text',
        left: lineX - 15,
        top: top - 20,
        style: {
          text: gp.line_id,
          fill: '#f38aff',
          fontWeight: 700,
          fontSize: 12,
          textAlign: 'center'
        }
      });
    });

    (global.order || []).forEach((rm, idx) => {
      const top = layout.padTop + idx * (layout.rowH + layout.rowGap);
      const centerY = top + layout.rowH / 2;
      const t1 = String(rm.model || '').trim();
      const t2 = String(rm.glass_type || '').trim();

      graphics.push({
        type: 'text',
        left: modelX - 60,
        top: centerY - 12,
        style: {
          text: t2 ? `${t1}\n(${t2})` : t1,
          fill: '#b1ffea',
          fontWeight: 600,
          fontSize: 11,
          lineHeight: 14,
          textAlign: 'center'
        }
      });
    });
  }

  C.calcOpacity = calcOpacity;
  C.makeSeriesData = makeSeriesData;

  function buildOption(ctx) {
    const columns = ctx.columns || [];
    const global = ctx.global || { order: [], lineGroups: [] };
    const rowIndex = ctx.rowIndex || null;
    const heavy = !!ctx.heavy;

    const SERIES_NAMES = C.SERIES_NAMES || {};
    const NAME_GLASS_TOTAL = SERIES_NAMES.glassTotal || 'glass (total)';
    const NAME_DEFECT_GLASS = SERIES_NAMES.defectGlass || 'defect glass';
    const NAME_DENSITY = SERIES_NAMES.density || 'density';
    const NAME_TOTAL_DENSITY = SERIES_NAMES.totalDensity || 'Total defect density';
    const NAME_SAME_POINT = SERIES_NAMES.samePoint || '同點';
    const NAME_DEFAULT_SPEC = SERIES_NAMES.defaultSpec || '預設SPEC';
    const NAME_FIXED_SPEC = SERIES_NAMES.fixedSpec || '動態SPEC';

    const legendSelectedState = {
      ...C.buildDefaultLegendSelectedState(),
      ...(ctx.legendSelectedState || {})
    };
    
    // 同點 legend 預設一定關閉；只有使用者點擊後才會變 true
    legendSelectedState[NAME_SAME_POINT] = ctx.legendSelectedState?.[NAME_SAME_POINT] === true;
    
    // 寫回 ctx，讓 rebuild 後狀態一致
    ctx.legendSelectedState = legendSelectedState;
    
    const totalDensityAlertRows = ctx.totalDensityAlertRows || [];
      
    totalDensityAlertRows.length = 0;
  
    const CHART_THEME = C.CHART_THEME;
    const CHART_COLOR = C.CHART_COLOR;
  
    const LEGEND_BLOCK_H = 42;
    const TITLE_GAP = 12;
    const HEADER_TEXT_H = 32;
    const padTop = LEGEND_BLOCK_H + TITLE_GAP + HEADER_TEXT_H;
    const padBottom = 70;
  
    const baseLeft = 16;
    const gutterLineW = 26;
    const gutterGap = 8;
    const gutterModelW = 26;
    const leftMargin = baseLeft + gutterLineW + gutterGap + gutterModelW + 25;
  
    const rightMargin = 80;
    const colGap = 80;
    const rowH = 118;
    const rowGap = 50;
  
    const maxRows = Math.max(1, (global.order || []).length);
  
    const totalH =
      padTop +
      maxRows * rowH +
      Math.max(0, maxRows - 1) * rowGap +
      padBottom;
  
    ctx.dom.style.height = `${totalH}px`;
  
    const width = ctx.dom.clientWidth || 1200;
    const nCols = Math.max(1, columns.length);
    const colWidth = Math.max(
      260,
      Math.floor((width - leftMargin - rightMargin - (nCols - 1) * colGap) / nCols)
    );
  
    const totalChartWidth =
      leftMargin +
      nCols * (colWidth + colGap) -
      colGap +
      rightMargin;
  
    ctx.dom.style.width = `${totalChartWidth}px`;
  
    const grids = [];
    const xAxes = [];
    const yAxes = [];
    const series = [];
    const graphics = [];
    const dataZoom = [];
    const densRightAxisMeta = [];
  
    let xAxisCountSoFar = 0;
    const colAxisIndexRange = [];
    const yAxisMetaMap = {};
  
    function pushSpecMarkLine(opt) {
      const value = Number(opt.value);
      if (!Number.isFinite(value)) return;
  
      series.push({
        name: opt.name,
        type: "line",
        xAxisIndex: opt.xAxisIndex,
        yAxisIndex: opt.yAxisIndex,
        data: [],
        showSymbol: false,
        silent: true,
        tooltip: { show: false },
        lineStyle: { opacity: 0 },
        z: opt.z || 30,
        zlevel: 1,
        clip: false,
        markLine: {
          silent: true,
          symbol: ["none", "none"],
          lineStyle: {
            type: "dashed",
            width: heavy ? 1 : 1.3,
            color: opt.color
          },
          label: {
            show: !heavy,
            position: "end",
            formatter: opt.labelText,
            color: CHART_THEME.mlText,
            backgroundColor: CHART_THEME.mlBg,
            padding: [2, 2],
            borderRadius: 3,
            fontSize: 10,
            offset: [10, 0]
          },
          data: [{ yAxis: value }]
        }
      });
    }
  
    const groups = [];
    let curAoi = null;
    let groupStart = 0;
  
    columns.forEach((c, idx) => {
      if (c.aoi !== curAoi) {
        if (curAoi != null) {
          groups.push({
            aoi: curAoi,
            startCol: groupStart,
            count: idx - groupStart
          });
        }
  
        curAoi = c.aoi;
        groupStart = idx;
      }
  
      if (idx === columns.length - 1) {
        groups.push({
          aoi: c.aoi,
          startCol: groupStart,
          count: idx - groupStart + 1
        });
      }
    });
  
    columns.forEach((col, colIdx) => {
      const { aoi, code, xTicks, rows } = col;
      const colLeft = leftMargin + colIdx * (colWidth + colGap);
  
      graphics.push({
        type: "text",
        left: colLeft + colWidth / 2,
        top: LEGEND_BLOCK_H + 22,
        style: {
          text: code,
          fill: "#d4e0ff",
          fontWeight: 700,
          fontSize: 12,
          textAlign: "center"
        }
      });
  
      rows.forEach((row, rIdx) => {
        const isBottom = rIdx === rows.length - 1;
  
        const gridTop = padTop + rIdx * (rowH + rowGap);
        const gridIndex = grids.length;
  
        grids.push({
          left: colLeft,
          top: gridTop,
          width: colWidth,
          height: rowH
        });
  
        const xAxisIndex = xAxes.length;
  
        xAxes.push({
          type: "category",
          gridIndex,
          data: xTicks,
          axisTick: {
            alignWithLabel: true,
            lineStyle: {
              color: CHART_THEME.axisTick,
              width: 1
            }
          },
          axisLabel: {
            show: isBottom,
            rotate: 90,
            margin: 12,
            color: CHART_THEME.axisLabel
          },
          axisLine: {
            onZero: false,
            lineStyle: {
              color: CHART_THEME.axisLine,
              width: 1
            }
          },
          triggerEvent: true
        });
  
        const gMax = Math.max(1, Math.ceil((row.maxG || 1) * 1.2));
  
        const yLeftIndex = yAxes.length;
        const yLeftId = `yL:${aoi}:${code}:${rIdx}`;
  
        yAxes.push({
          id: yLeftId,
          type: "value",
          gridIndex,
          min: 0,
          max: gMax,
          splitLine: {
            show: true,
            lineStyle: {
              color: CHART_THEME.splitLine,
              width: 1,
              type: "dashed"
            }
          },
          axisLabel: {
            show: true,
            color: CHART_THEME.axisLabel
          },
          axisLine: {
            lineStyle: {
              color: CHART_THEME.axisLine,
              width: 1
            }
          },
          axisTick: {
            lineStyle: {
              color: CHART_THEME.axisTick,
              width: 1
            }
          },
          triggerEvent: true
        });
  
        const showTotalDensity = legendSelectedState["Total defect density"] === true;
        const densityMax = Number(row.maxDensity || 0);
        const totalDensityMax = Number(row.maxTotalDensity || 0);
        const usedDensityMax = showTotalDensity
          ? Math.max(densityMax, totalDensityMax)
          : densityMax;
  
        const dBaseMax = Math.max(1, usedDensityMax * 1.4);
  
        const mlMax = Math.max(
          0,
          row?.specDefault?.ooc || 0,
          row?.specDefault?.oos || 0,
          row?.specFixed?.ooc || 0,
          row?.specFixed?.oos || 0
        );
  
        const yRightMax = Math.max(dBaseMax, mlMax ? mlMax * 1.05 : 0);
  
        const yRightIndex = yAxes.length;
        const yRightId = `yR:${aoi}:${code}:${rIdx}`;
  
        yAxes.push({
          id: yRightId,
          type: "value",
          gridIndex,
          min: 0,
          max: yRightMax,
          splitLine: { show: false },
          axisLabel: {
            show: false,
            color: CHART_THEME.axisLabel
          },
          axisLine: {
            lineStyle: {
              color: CHART_THEME.axisLine,
              width: 1
            }
          },
          axisTick: {
            lineStyle: {
              color: CHART_THEME.axisTick,
              width: 1
            }
          }
        });
  
        const densKey = `${aoi}|${code}|${rIdx}|${row.glass_type || ""}`;
  
        densRightAxisMeta.push({
          key: densKey,
          gridIndex,
          yId: yRightId,
          baseMax: yRightMax,
          debug: {
            aoi,
            code,
            rIdx,
            glass_type: row.glass_type
          }
        });
  
        yAxisMetaMap[yLeftIndex] = {
          aoi,
          code,
          local: rIdx
        };
  
        const rowKey = densKey;
  
        series.push({
          id: `barG:${aoi}:${code}:${rIdx}`,
          name: "glass (total)",
          type: "bar",
          xAxisIndex,
          yAxisIndex: yLeftIndex,
          barMaxWidth: 14,
          barGap: "0%",
          z: 1,
          itemStyle: { color: CHART_COLOR.glassTotalBar },
          data: (row.tabTotalGlassArr || []).map((v, i) => ({
            value: Math.trunc(Number(v || 0)),
            itemStyle: {
              opacity: C.calcOpacity(ctx.interopState, aoi, code, rowKey, i)
            }
          })),
          universalTransition: !heavy
        });
  
        series.push({
          id: `barCG:${aoi}:${code}:${rIdx}`,
          name: "defect glass",
          type: "bar",
          xAxisIndex,
          yAxisIndex: yLeftIndex,
          barMaxWidth: 14,
          barGap: "-100%",
          z: 2,
          itemStyle: { color: CHART_COLOR.defectGlassBar },
          label: { show: false },
          data: (row.codeGlasses || []).map((v, i) => ({
            value: v,
            itemStyle: {
              opacity: C.calcOpacity(ctx.interopState, aoi, code, rowKey, i)
            }
          })),
          universalTransition: !heavy
        });
  
        series.push({
          id: `sc:${aoi}:${code}:${rIdx}`,
          name: "density",
          type: "scatter",
          xAxisIndex,
          yAxisIndex: yRightIndex,
          symbolSize: heavy ? 5 : 7,
          z: 50,
          itemStyle: { color: CHART_COLOR.densityPoint },
          label: {
            show: !heavy,
            position: "top",
            distance: 10,
            formatter: (p) => {
              const vv = Array.isArray(p.value) ? p.value[1] : p.value;
              if (typeof vv !== "number" || !isFinite(vv)) return "";
  
              if (p?.data?.needAlert) {
                return `{alert|爆點}\n{gap| }\n{val|${vv.toFixed(2)}}`;
              }
  
              return `{val|${vv.toFixed(2)}}`;
            },
            backgroundColor: "transparent",
            padding: [0, 0],
            borderRadius: 0,
            rich: {
              alert: {
                color: "#FF0000",
                fontSize: 12,
                fontWeight: 800,
                lineHeight: 14,
                align: "center",
                backgroundColor: CHART_THEME.labelBg,
                padding: [0, 0, 0, 0]
              },
              gap: {
                fontSize: 1,
                lineHeight: 3,
                backgroundColor: "transparent"
              },
              val: {
                color: CHART_THEME.labelText,
                fontSize: 10,
                lineHeight: 14,
                align: "center",
                backgroundColor: CHART_THEME.labelBg,
                padding: CHART_THEME.labelPad,
                borderRadius: CHART_THEME.labelRadius
              }
            }
          },
          data: (row.density || []).map((v, i) => {
            const totalDensity = Number(row.tabTotalDensity?.[i]);
            const needAlert = C.shouldTotalDensityPointAlert(totalDensity);
  
            const tabTG = Number(row.tabTotalGlassArr?.[i] ?? 0);
            const tabTD = Number(row.tabTotalDefArr?.[i] ?? 0);
            const tickStr = xTicks?.[i] || "";
  
            const alertRow = needAlert
              ? C.buildAlertRowFromChartPoint(row, tickStr, aoi, code, totalDensity, tabTG, tabTD)
              : null;
  
            if (alertRow) totalDensityAlertRows.push(alertRow);
  
            return {
              value: v,
              needAlert,
              alertRow,
              itemStyle: {
                opacity: v == null ? 0 : C.calcOpacity(ctx.interopState, aoi, code, rowKey, i),
                color: needAlert ? C.ALERT_CONFIG.blinkColorA : CHART_COLOR.densityPoint
              }
            };
          }),
          connectNulls: false,
          universalTransition: !heavy
        });
  
        series.push({
          id: `scTotal:${aoi}:${code}:${rIdx}`,
          name: NAME_TOTAL_DENSITY,
          type: "scatter",
          xAxisIndex,
          yAxisIndex: yRightIndex,
          symbolSize: heavy ? 6 : 8,
          z: 60,
          itemStyle: { color: CHART_COLOR.totalDensityPoint },
          label: {
            show: !heavy,
            position: "top",
            distance: 10,
            formatter: (p) => {
              const vv = Array.isArray(p.value) ? p.value[1] : p.value;
              const valText = typeof vv === "number" && Number.isFinite(vv)
                ? vv.toFixed(2)
                : "";
            
              // Total defect density 本身只顯示數值
              // 不再負責顯示「同點」
              return valText ? `{val|${valText}}` : "";
            },
            backgroundColor: "transparent",
            padding: [0, 0],
            rich: {
              sp: {
                color: "#FFDC00",
                fontSize: 12,
                fontWeight: 800,
                lineHeight: 15,
                align: "center",
                backgroundColor: CHART_THEME.labelBg,
                padding: [1, 4],
                borderRadius: 3
              },
              val: {
                color: CHART_THEME.labelText,
                fontSize: 10,
                lineHeight: 14,
                align: "center",
                backgroundColor: CHART_THEME.labelBg,
                padding: CHART_THEME.labelPad,
                borderRadius: CHART_THEME.labelRadius
              }
            }
          },
          data: (row.tabTotalDensity || []).map((v, i) => {
            const totalDensity = Number(v);
            const needAlert = C.shouldTotalDensityPointAlert(totalDensity);
  
            const tabTG = Number(row.tabTotalGlassArr?.[i] ?? 0);
            const tabTD = Number(row.tabTotalDefArr?.[i] ?? 0);
            const tickStr = xTicks?.[i] || "";
  
            const alertRow = needAlert
              ? C.buildAlertRowFromChartPoint(row, tickStr, aoi, code, totalDensity, tabTG, tabTD)
              : null;
  
            if (alertRow) totalDensityAlertRows.push(alertRow);
  
            return {
              value: Number.isFinite(totalDensity) ? totalDensity : null,
              needAlert,
              alertRow,
              hasSamePoint: row.samePointArr?.[i] === true,
              itemStyle: {
                opacity: v == null ? 0 : C.calcOpacity(ctx.interopState, aoi, code, rowKey, i),
                color: needAlert ? C.ALERT_CONFIG.blinkColorA : CHART_COLOR.totalDensityPoint
              }
            };
          }),
          connectNulls: false,
          universalTransition: !heavy
        });

        series.push({
          id: `samePoint:${aoi}:${code}:${rIdx}`,
        
          // 必須跟 legend.data 裡的 NAME_SAME_POINT 完全一致
          name: NAME_SAME_POINT,
        
          type: "scatter",
          xAxisIndex,
          yAxisIndex: yLeftIndex,
        
          // 點本身只是定位用，不顯示實體點
          symbolSize: 6,
          z: 100,
          silent: true,
          tooltip: { show: false },
          legendHoverLink: false,
          clip: false,
        
          // 這裡不要設 opacity: 0，否則 label 也可能被一起透明
          // 給黃色是為了 legend icon 看得到
          itemStyle: {
            color: "#FFDC00"
          },
        
          label: {
            show: !heavy,
            position: "top",
            distance: 6,
        
            formatter: (p) => {
              if (!p?.data?.hasSamePoint) return "";
              return "{sp|同點}";
            },
        
            backgroundColor: "transparent",
            padding: [0, 0],
        
            rich: {
              sp: {
                color: "#FFDC00",
                fontSize: 12,
                fontWeight: 800,
                lineHeight: 15,
                align: "center",
                backgroundColor: CHART_THEME.labelBg,
                padding: [1, 4],
                borderRadius: 3
              }
            }
          },
        
          data: (row.tabTotalGlassArr || []).map((v, i) => {
            const hasSamePoint = row.samePointArr?.[i] === true;
        
            const totalGlass = Number(row.tabTotalGlassArr?.[i] ?? 0);
            const defectGlass = Number(row.codeGlasses?.[i] ?? 0);
        
            // 放在 bar 最高點
            const y = Math.max(totalGlass, defectGlass, 0);
        
            return {
              // 用 [x, y] 明確指定位置，避免 category scatter 用 index 判斷失準
              value: hasSamePoint ? [xTicks[i], y] : [xTicks[i], null],
              hasSamePoint,
        
              // 只把 data point 顏色透明，不要用 opacity: 0
              // 這樣 label 不會一起消失
              itemStyle: {
                color: "rgba(255,220,0,0)"
              }
            };
          }),
        
          connectNulls: false,
          universalTransition: false
        });
  
        if (row.specDefault) {
          if (row.specDefault.ooc != null) {
            pushSpecMarkLine({
              name: "預設SPEC",
              xAxisIndex,
              yAxisIndex: yRightIndex,
              value: Number(row.specDefault.ooc),
              color: CHART_COLOR.defaultSpecOOC,
              labelText: () => `${Number(row.specDefault.ooc).toFixed(1)}`,
              z: 30
            });
          }
  
          if (row.specDefault.oos != null) {
            pushSpecMarkLine({
              name: "預設SPEC",
              xAxisIndex,
              yAxisIndex: yRightIndex,
              value: Number(row.specDefault.oos),
              color: CHART_COLOR.defaultSpecOOS,
              labelText: () => `${Number(row.specDefault.oos).toFixed(1)}`,
              z: 30
            });
          }
        }
  
        if (row.specFixed) {
          if (row.specFixed.ooc != null) {
            pushSpecMarkLine({
              name: "動態SPEC",
              xAxisIndex,
              yAxisIndex: yRightIndex,
              value: Number(row.specFixed.ooc),
              color: CHART_COLOR.fixedSpecOOC,
              labelText: () => `${Number(row.specFixed.ooc).toFixed(1)}`,
              z: 31
            });
          }
  
          if (row.specFixed.oos != null) {
            pushSpecMarkLine({
              name: "動態SPEC",
              xAxisIndex,
              yAxisIndex: yRightIndex,
              value: Number(row.specFixed.oos),
              color: CHART_COLOR.fixedSpecOOS,
              labelText: () => `${Number(row.specFixed.oos).toFixed(1)}`,
              z: 31
            });
          }
        }
      });
  
      const xStart = xAxisCountSoFar;
      const xEnd = xStart + rows.length;
  
      colAxisIndexRange.push({
        colIndex: colIdx,
        aoi,
        code,
        xStart,
        xEnd
      });
  
      xAxisCountSoFar = xEnd;
  
      if (rows.length) {
        const xIdxs = Array.from({ length: rows.length }, (_, i) => xStart + i);
  
        dataZoom.push(
          {
            type: "inside",
            xAxisIndex: xIdxs,
            filterMode: "filter"
          },
          {
            type: "slider",
            xAxisIndex: xIdxs,
            left: colLeft,
            bottom: 8,
            width: colWidth,
            height: 16,
            brushSelect: false
          }
        );
      }
    });
  
    if (!series.some(ss => ss.name === "預設SPEC") && xAxes.length > 0 && yAxes.length > 1) {
      series.push({
        name: "預設SPEC",
        type: "line",
        xAxisIndex: 0,
        yAxisIndex: 1,
        data: [],
        showSymbol: false,
        silent: true,
        tooltip: { show: false },
        lineStyle: { opacity: 0 }
      });
    }
  
    if (!series.some(ss => ss.name === "動態SPEC") && xAxes.length > 0 && yAxes.length > 1) {
      series.push({
        name: "動態SPEC",
        type: "line",
        xAxisIndex: 0,
        yAxisIndex: 1,
        data: [],
        showSymbol: false,
        silent: true,
        tooltip: { show: false },
        lineStyle: { opacity: 0 }
      });
    }

  
    groups.forEach(g => {
      const left = leftMargin + g.startCol * (colWidth + colGap);
      const right = left + g.count * colWidth + (g.count - 1) * colGap;
  
      graphics.push({
        type: "text",
        left: (left + right) / 2,
        top: LEGEND_BLOCK_H + 4,
        style: {
          text: g.aoi,
          fill: "#89a6ff",
          fontWeight: 800,
          fontSize: 13,
          textAlign: "center"
        }
      });
    });
  
    const lineX = 16 + Math.floor(26 / 2);
    const modelX = 16 + 26 + 8 + Math.floor(26 / 2);
  
    (global.lineGroups || []).forEach(gp => {
      const top = padTop + gp.start * (rowH + rowGap);
  
      graphics.push({
        type: "text",
        left: lineX - 15,
        top: top - 20,
        style: {
          text: gp.line_id,
          fill: "#f38aff",
          fontWeight: 700,
          fontSize: 12,
          textAlign: "center"
        }
      });
    });
  
    (global.order || []).forEach((rm, idx) => {
      const top = padTop + idx * (rowH + rowGap);
      const centerY = top + rowH / 2;
  
      const model = String(rm.model || "").trim();
      const side = String(rm.glass_type || "").trim();
  
      graphics.push({
        type: "text",
        left: modelX - 60,
        top: centerY - 12,
        style: {
          text: side ? `${model}\n(${side})` : model,
          fill: "#b1ffea",
          fontWeight: 600,
          fontSize: 11,
          lineHeight: 14,
          textAlign: "center"
        }
      });
    });
  
    return {
      animation: !heavy,
      legend: {
        top: 0,
        right: 10,
        itemGap: 18,
        data: [
          NAME_GLASS_TOTAL,
          NAME_DEFECT_GLASS,
          NAME_DENSITY,
          NAME_TOTAL_DENSITY,
          NAME_SAME_POINT,
          NAME_DEFAULT_SPEC,
          NAME_FIXED_SPEC
        ],
        selected: legendSelectedState
      },
      tooltip: buildTooltip(ctx, columns, ctx.rawRows || [], rowIndex),
      axisPointer: { link: [] },
      brush: {
        toolbox: [],
        brushMode: "single",
        brushType: "lineX",
        xAxisIndex: Array.from({ length: xAxisCountSoFar }, (_, i) => i)
      },
      grid: grids,
      xAxis: xAxes,
      yAxis: yAxes,
      series,
      graphic: graphics,
      dataZoom,
      __colAxisIndexRange: colAxisIndexRange,
      __yAxisMetaMap: yAxisMetaMap,
      __densRightAxisMeta: densRightAxisMeta
    };
  }
  
  C.buildOption = buildOption;
})();

