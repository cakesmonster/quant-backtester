(() => {
  const state = {
    data: null,
    pageTemplates: new Map(),
    activePage: (() => {
      const h = location.hash.replace('#', '').trim();
      const known = ['daily-replay','hot-list','stock-analysis','strategy-backtest','paper-account'];
      return known.includes(h) ? h : 'daily-replay';
    })(),
    currentStockCode: '',
    hoveredStock: null,
    charts: new Map(),
    marketTapeItems: []
  };

  const PAGE_FILES = {
    'daily-replay': '/static/pages/daily-replay.html',
    'hot-list': '/static/pages/hot-list.html',
    'stock-analysis': '/static/pages/stock-analysis.html',
    'strategy-backtest': '/static/pages/strategy-backtest.html',
    'paper-account': '/static/pages/paper-account.html'
  };

  const PERIOD_KEYS = ['11:30', '15:00', '21:00'];

  const el = {
    nav: document.getElementById('nav-tabs'),
    pageHost: document.getElementById('page-host'),
    updatedAt: document.getElementById('updated-at'),
    hoverCard: document.getElementById('hover-card'),
    hoverCardName: document.getElementById('hover-card-name'),
    hoverCardCode: document.getElementById('hover-card-code'),
    hoverFields: document.getElementById('hover-fields'),
    hoverTags: document.getElementById('hover-tags'),
  };

  function formatPct(value, digits = 2) {
    const sign = value > 0 ? '+' : '';
    return `${sign}${Number(value).toFixed(digits)}%`;
  }

  function trendClass(value) {
    if (value > 0) return 'up';
    if (value < 0) return 'down';
    return 'flat';
  }

  function trendArrow(value) {
    if (value > 0) return '▲';
    if (value < 0) return '▼';
    return '•';
  }

  function formatTrendHtml(value, digits = 2) {
    const cls = trendClass(value);
    const txt = value === 0 ? '0.00%' : `${Math.abs(Number(value)).toFixed(digits)}%`;
    return `<span class="trend ${cls}"><span class="arr">${trendArrow(value)}</span><span>${txt}</span></span>`;
  }

  function parseHintDelta(hint) {
    if (typeof hint !== 'string') return null;
    const match = hint.match(/[+-]\d+(?:\.\d+)?/);
    if (!match) return null;
    const value = Number(match[0]);
    return Number.isFinite(value) ? value : null;
  }

  function formatMoney(value, unit = '亿') {
    return `${value.toFixed(1)}${unit}`;
  }

  function cssVar(name, fallback = '') {
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value || fallback;
  }

  function getChartTheme() {
    return {
      surface: cssVar('--surface-2', cssVar('--surface', '#0f131c')),
      grid: 'rgba(107, 118, 137, 0.28)',
      axis: cssVar('--muted', '#6b7689'),
      primary: cssVar('--cyan', '#22d3ee'),
      primaryFillTop: 'rgba(34, 211, 238, 0.24)',
      primaryFillBottom: 'rgba(34, 211, 238, 0.04)',
      strokePalette: [cssVar('--cyan', '#22d3ee'), cssVar('--violet', '#a78bfa'), cssVar('--accent', '#facc15'), cssVar('--positive', '#22e58c')],
      fillPalette: ['rgba(34, 211, 238, 0.10)', 'rgba(167, 139, 250, 0.10)', 'rgba(250, 204, 21, 0.10)', 'rgba(34, 229, 140, 0.10)']
    };
  }

  function byCode(code) {
    return state.data.stockMeta[code] || null;
  }

  function createSkeleton(lines = 5) {
    const rows = Array.from({ length: lines }, () => '<div class="skeleton" style="height: 22px"></div>').join('');
    return `<div class="card"><div class="card-body"><div class="skeleton-grid">${rows}</div></div></div>`;
  }

  async function loadShared() {
    const res = await fetch('/api/shared', { cache: 'no-store' });
    if (!res.ok) throw new Error('无法获取共享数据');
    state.data = await res.json();
    el.updatedAt.textContent = state.data.meta.updatedAt;
  }

  const PAGE_API = {
    'daily-replay': '/api/page/daily-replay',
    'stock-analysis': '/api/page/stock-analysis',
    'strategy-backtest': '/api/page/strategy-backtest',
    'paper-account': '/api/page/paper-account',
  };

  async function loadPageData(pageId) {
    const url = PAGE_API[pageId];
    if (!url) return;
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) throw new Error(`无法加载页面数据: ${pageId}`);
    const pageData = await res.json();
    Object.assign(state.data, pageData);
  }

  function initMarketTape() {
    const fromData = Array.isArray(state.data.marketTape) ? state.data.marketTape : [];
    if (fromData.length > 0) {
      state.marketTapeItems = fromData.map((x) => ({
        symbol: x.symbol,
        price: Number(x.price),
        changePct: Number(x.changePct),
        code: x.code || ''
      }));
    } else {
      const fallback = [
        { symbol: '上证', price: 3215.42, changePct: 0.48 },
        { symbol: '深成', price: 10282.16, changePct: 0.67 },
        { symbol: '创业板', price: 1985.22, changePct: -0.32 },
        { symbol: '沪深300', price: 3798.44, changePct: 0.28 },
        { symbol: '北证50', price: 888.16, changePct: 1.05 },
        { symbol: '中证1000', price: 5822.37, changePct: -0.21 }
      ];
      state.marketTapeItems = fallback;
    }
    drawMarketTape();
    // runMarketTapePulse removed - no fake jitter
  }

  function drawMarketTape() {
    const tape = document.getElementById('market-tape');
    if (!(tape instanceof HTMLElement) || state.marketTapeItems.length === 0) return;
    const once = state.marketTapeItems
      .map((item) => {
        const cls = trendClass(item.changePct);
        const arrow = item.changePct > 0 ? '▲' : item.changePct < 0 ? '▼' : '•';
        const price = item.price >= 1000 ? item.price.toFixed(2) : item.price.toFixed(3);
        return `<span class="tape-item" ${item.code ? `data-stock-code="${item.code}"` : ''}>
          <span class="sym">${escapeHtml(item.symbol)}</span>
          <span class="px">${price}</span>
          <span class="pct ${cls}">${arrow} ${Math.abs(item.changePct).toFixed(2)}%</span>
        </span>`;
      })
      .join('');
    tape.innerHTML = once + once;
    const speedBase = Math.max(52, Math.min(92, Math.round(820 / Math.max(12, state.marketTapeItems.length * 1.2))));
    tape.style.animationDuration = `${speedBase}s`;

    tape.querySelectorAll('.tape-item[data-stock-code]').forEach((node) => {
      node.addEventListener('click', () => {
        const code = node.getAttribute('data-stock-code');
        if (!code) return;
        state.currentStockCode = code;
        renderPage('stock-analysis');
      });
    });
  }

  function runMarketTapePulse() {} // disabled

  async function loadPageTemplate(pageId) {
    if (state.pageTemplates.has(pageId)) return state.pageTemplates.get(pageId);
    const res = await fetch(PAGE_FILES[pageId], { cache: 'no-store' });
    if (!res.ok) throw new Error(`无法读取页面模板: ${pageId}`);
    const html = await res.text();
    state.pageTemplates.set(pageId, html);
    return html;
  }

  function clearActiveTab() {
    el.nav.querySelectorAll('.nav-tab').forEach((btn) => btn.classList.remove('is-active'));
  }

  function setActiveTab(pageId) {
    clearActiveTab();
    const btn = el.nav.querySelector(`[data-page="${pageId}"]`);
    if (btn) btn.classList.add('is-active');
  }

  function pushPageHash(pageId) {
    const hash = `#${pageId}`;
    if (location.hash !== hash) {
      history.pushState({ pageId }, '', hash);
    }
  }

  function getInitialPage() {
    const hash = location.hash.replace('#', '').trim();
    if (hash && PAGE_FILES[hash]) return hash;
    return 'daily-replay';
  }

  async function renderPage(pageId, options = { pushHistory: true }) {
    hideHoverCard();
    state.activePage = pageId;
    setActiveTab(pageId);
    el.pageHost.innerHTML = createSkeleton(8);
    const template = await loadPageTemplate(pageId);
    el.pageHost.innerHTML = template;
    await loadPageData(pageId);
    runPageRenderer(pageId);
    if (options.pushHistory) pushPageHash(pageId);
  }

  function escapeHtml(text) {
    return String(text)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }

  function patchBars(container, rows, maxValue, cls = '') {
    container.innerHTML = rows
      .map((item) => {
        const width = maxValue > 0 ? (item.value / maxValue) * 100 : 0;
        return `<div class="bar-item">
          <span>${escapeHtml(item.label)}</span>
          <div class="progress-track"><div class="progress-fill ${cls}" style="width:${width.toFixed(1)}%"></div></div>
          <span class="bar-value">${item.value}</span>
        </div>`;
      })
      .join('');
  }

  function metricClass(value) {
    if (value > 0) return 'positive';
    if (value < 0) return 'negative';
    return '';
  }

  function parseMvToNum(text) {
    if (typeof text === 'number') return text;
    if (typeof text !== 'string') return 0;
    const n = Number(text.replace(/[^0-9.]/g, ''));
    return Number.isFinite(n) ? n : 0;
  }

  function parseAmountToNum(text) {
    if (typeof text === 'number') return text;
    if (typeof text !== 'string') return 0;
    const n = Number(text.replace(/[^0-9.\-]/g, ''));
    return Number.isFinite(n) ? n : 0;
  }

  function shiftMdLabel(label, offsetDays) {
    if (typeof label !== 'string') return '';
    const m = label.match(/^(\d{2})-(\d{2})$/);
    if (!m) return '';
    const base = new Date(Date.UTC(2026, Number(m[1]) - 1, Number(m[2])));
    if (Number.isNaN(base.getTime())) return '';
    base.setUTCDate(base.getUTCDate() + offsetDays);
    const mm = String(base.getUTCMonth() + 1).padStart(2, '0');
    const dd = String(base.getUTCDate()).padStart(2, '0');
    return `${mm}-${dd}`;
  }

  function extendDayKSeries(records, targetLength = 36) {
    if (!Array.isArray(records) || records.length === 0) return [];
    if (records.length >= targetLength) return records;
    const parsed = records.map((r) => ({
      date: String(r.date || ''),
      open: Number(r.open),
      high: Number(r.high),
      low: Number(r.low),
      close: Number(r.close),
      volume: Number(r.volume)
    }));
    let seed = { ...parsed[0] };
    const prepend = [];
    const missing = targetLength - parsed.length;
    for (let i = 0; i < missing; i += 1) {
      const drift = Math.sin((i + 1) * 1.31) * 0.0048;
      const close = seed.open * (1 - drift * 0.82);
      const open = close * (1 + drift * 0.57);
      const high = Math.max(open, close) * (1 + 0.0032 + Math.abs(drift) * 0.45);
      const low = Math.min(open, close) * (1 - 0.0032 - Math.abs(drift) * 0.43);
      const prevDate = shiftMdLabel(seed.date, -1);
      const rec = {
        date: prevDate,
        open: Number(open.toFixed(2)),
        high: Number(high.toFixed(2)),
        low: Number(low.toFixed(2)),
        close: Number(close.toFixed(2)),
        volume: Number((seed.volume * (0.84 + ((i + 2) % 5) * 0.03)).toFixed(2)),
        inferred: true
      };
      prepend.unshift(rec);
      seed = rec;
    }
    return [...prepend, ...parsed];
  }

  function buildTradeFlowSeries(trades) {
    if (!Array.isArray(trades) || trades.length === 0) return [];
    let cum = 0;
    return trades.map((t) => {
      const amt = parseAmountToNum(t.amount);
      const signed = t.side === '卖出' ? amt : -amt;
      cum += signed;
      return { label: t.time, value: Number(cum.toFixed(2)) };
    });
  }

  function iconForMetricLabel(label) {
    if (label.includes('收益')) return '↗';
    if (label.includes('夏普')) return 'σ';
    if (label.includes('回撤')) return '↘';
    if (label.includes('胜率')) return '◎';
    return '∑';
  }

  function iconForAccountMetric(label) {
    if (label.includes('总资产')) return 'Σ';
    if (label.includes('可用资金')) return '¥';
    if (label.includes('持仓')) return '▦';
    if (label.includes('盈亏')) return '↕';
    return '•';
  }

  function clamp(min, value, max) {
    return Math.max(min, Math.min(max, value));
  }

  function drawDonutChart(canvas, items) {
    if (!(canvas instanceof HTMLCanvasElement) || !Array.isArray(items) || items.length === 0) return;
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const w = Math.max(240, rect.width);
    const h = Math.max(220, rect.height);
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = cssVar('--surface-2', '#141a26');
    ctx.fillRect(0, 0, w, h);

    const cx = w * 0.34;
    const cy = h * 0.52;
    const outerR = Math.min(w, h) * 0.29;
    const innerR = outerR * 0.61;
    const total = items.reduce((acc, x) => acc + x.value, 0) || 1;
    const palette = [
      cssVar('--cyan', '#22d3ee'),
      cssVar('--violet', '#a78bfa'),
      cssVar('--accent', '#facc15'),
      cssVar('--positive', '#22e58c'),
      cssVar('--negative', '#ff4f6d')
    ];
    let start = -Math.PI / 2;
    items.forEach((item, idx) => {
      const ratio = item.value / total;
      const sweep = Math.max(0.02, ratio * Math.PI * 2);
      const end = start + sweep;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, outerR, start, end);
      ctx.closePath();
      ctx.fillStyle = palette[idx % palette.length];
      ctx.globalAlpha = 0.9;
      ctx.fill();
      start = end;
    });
    ctx.globalAlpha = 1;

    ctx.beginPath();
    ctx.arc(cx, cy, innerR, 0, Math.PI * 2);
    ctx.fillStyle = cssVar('--surface', '#0f131c');
    ctx.fill();
    ctx.strokeStyle = cssVar('--line', '#1f2738');
    ctx.lineWidth = 1;
    ctx.stroke();

    ctx.fillStyle = cssVar('--fg', '#e8edf7');
    ctx.font = '600 14px Geist, -apple-system, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('持仓结构', cx, cy - 4);
    ctx.fillStyle = cssVar('--muted', '#6b7689');
    ctx.font = '11px Geist Mono, ui-monospace, Menlo, monospace';
    ctx.fillText(`${items.length} 只`, cx, cy + 14);

    const legendX = w * 0.62;
    let legendY = h * 0.24;
    ctx.textAlign = 'left';
    items.forEach((item, idx) => {
      const ratio = (item.value / total) * 100;
      const color = palette[idx % palette.length];
      ctx.fillStyle = color;
      ctx.globalAlpha = 0.95;
      ctx.fillRect(legendX, legendY - 7, 9, 9);
      ctx.globalAlpha = 1;
      ctx.fillStyle = cssVar('--fg-soft', '#c2cad8');
      ctx.font = '11px Geist, -apple-system, sans-serif';
      ctx.fillText(`${item.label} ${ratio.toFixed(1)}%`, legendX + 14, legendY);
      legendY += 18;
    });
  }

  function drawPnlBars(canvas, items) {
    if (!(canvas instanceof HTMLCanvasElement) || !Array.isArray(items) || items.length === 0) return;
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const w = Math.max(260, rect.width);
    const h = Math.max(220, rect.height);
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = cssVar('--surface-2', '#141a26');
    ctx.fillRect(0, 0, w, h);

    const pad = { left: 34, right: 14, top: 18, bottom: 34 };
    const innerW = w - pad.left - pad.right;
    const innerH = h - pad.top - pad.bottom;
    const maxAbs = Math.max(0.1, ...items.map((x) => Math.abs(x.value)));
    const zeroY = pad.top + innerH * 0.5;
    const bw = innerW / Math.max(1, items.length * 1.8);
    const gap = bw * 0.8;

    ctx.strokeStyle = cssVar('--line', '#1f2738');
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i += 1) {
      const y = pad.top + (innerH / 4) * i;
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(w - pad.right, y);
      ctx.stroke();
    }
    ctx.strokeStyle = cssVar('--line-strong', '#2a3447');
    ctx.beginPath();
    ctx.moveTo(pad.left, zeroY);
    ctx.lineTo(w - pad.right, zeroY);
    ctx.stroke();

    items.forEach((item, idx) => {
      const x = pad.left + idx * (bw + gap);
      const ratio = item.value / maxAbs;
      const barH = Math.abs(ratio) * (innerH * 0.44);
      const y = item.value >= 0 ? zeroY - barH : zeroY;
      const color = item.value >= 0 ? cssVar('--positive', '#22e58c') : cssVar('--negative', '#ff4f6d');
      ctx.fillStyle = color;
      ctx.globalAlpha = 0.88;
      ctx.fillRect(x, y, bw, Math.max(2, barH));
      ctx.globalAlpha = 1;
      ctx.fillStyle = cssVar('--muted', '#6b7689');
      ctx.font = '10px Geist Mono, ui-monospace, Menlo, monospace';
      ctx.textAlign = 'center';
      ctx.fillText(item.label, x + bw / 2, h - 10);
    });
  }

  function renderDailyReplay() {
    const daily = state.data.dailyReplay;
    const today = state.data.meta.today;

    const dateInput = document.getElementById('daily-date');
    const emotionRow = document.getElementById('daily-emotion-row');
    const liveBars = document.getElementById('daily-live-bars');
    const ydBars = document.getElementById('yd-performance-bars');
    const ydAvg = document.getElementById('yd-performance-avg');
    const ydRange = document.getElementById('yd-performance-range');
    const auctionWrap = document.getElementById('auction-wrap');
    const auctionBody = document.getElementById('auction-body');
    const ladderWrap = document.getElementById('ladder-wrap');
    const sectorUp = document.getElementById('sector-up');
    const sectorDown = document.getElementById('sector-down');
    const sectorSummary = document.getElementById('sector-summary');

    function renderByDate(date) {
      const day = daily.byDate[date] || daily.byDate[today];
      const isToday = date === today;

      emotionRow.innerHTML = day.emotionMetrics
        .map((m) => {
          const cls = metricClass(m.value);
          const isPct = m.unit === '%';
          const hintDelta = parseHintDelta(m.hint);
          const hintHtml =
            hintDelta === null
              ? escapeHtml(m.hint || '—')
              : `${escapeHtml((m.hint || '').replace(/[+-]\d+(?:\.\d+)?/, '').trim())} ${formatTrendHtml(hintDelta, Number.isInteger(hintDelta) ? 0 : 2)}`;
          const valueHtml = isPct
            ? `<span class="${m.label.includes('收益') ? '' : 'mono'}">${m.label.includes('收益') ? formatTrendHtml(m.value) : `${m.value.toFixed(2)}%`}</span>`
            : `<span class="mono">${m.value}</span>`;
          const signalClass = m.label.includes('晋级') || m.label.includes('收益') ? 'value-signal' : '';
          return `<article class="kpi">
            <div class="kpi-label">${escapeHtml(m.label)}</div>
            <div class="kpi-value ${cls} ${signalClass}">${valueHtml}</div>
            <div class="kpi-hint">${hintHtml}</div>
          </article>`;
        })
        .join('');

      const pulseRows = Array.isArray(day.livePulse)
        ? day.livePulse
        : [
            { label: '封单', value: Math.min(100, 36 + day.emotionMetrics[0].value * 0.8), tone: 'up' },
            { label: '承接', value: Math.min(100, 42 + day.emotionMetrics[4].value * 0.9), tone: 'violet' },
            { label: '回撤', value: Math.min(100, 18 + day.emotionMetrics[2].value * 1.7), tone: 'down' },
            { label: '活跃', value: Math.min(100, 28 + day.emotionMetrics[1].value * 1.3), tone: 'up' }
          ];

      liveBars.innerHTML = pulseRows
        .map(
          (row) => `<div class="rt-row" data-live-val="${row.value.toFixed(1)}">
            <span class="lbl">${escapeHtml(row.label)}</span>
            <div class="rt-track"><div class="rt-fill ${row.tone}" style="width:${Math.max(0, Math.min(100, row.value)).toFixed(1)}%"></div></div>
            <span class="val">${row.value.toFixed(1)}%</span>
          </div>`
        )
        .join('');

      const bars = day.yesterdayLimitUpPerformance.bars;
      const maxValue = Math.max(...bars.map((x) => x.value));
      patchBars(ydBars, bars, maxValue);

      ydAvg.innerHTML = formatTrendHtml(day.yesterdayLimitUpPerformance.avg);
      ydAvg.className = 'big-stat';
      ydRange.textContent = `最高 ${formatPct(day.yesterdayLimitUpPerformance.max)} / 最低 ${formatPct(day.yesterdayLimitUpPerformance.min)}`;

      if (isToday) {
        auctionWrap.classList.remove('hide');
        auctionBody.innerHTML = day.auctionMoves
          .map(
            (row) => `<tr>
              <td>${row.time}</td>
              <td class="mono">${row.code}</td>
              <td data-stock-ref="${row.code}">${row.name}</td>
              <td>${row.type}</td>
              <td>${escapeHtml(row.note)}</td>
            </tr>`
          )
          .join('');
      } else {
        auctionWrap.classList.add('hide');
      }

      ladderWrap.innerHTML = day.ladder
        .map((group) => {
          const chips = group.stocks
            .map((stock) => {
              const cls = metricClass(stock.changePct);
              return `<button class="stock-chip hoverable-stock" data-stock-code="${stock.code}" type="button">
                <div class="stock-code">${stock.code}</div>
                <div class="stock-name">${stock.name}</div>
                <div class="stock-meta">
                  <span class="tag group">${stock.sector}</span>
                  <span class="${cls === 'positive' ? 'price-up' : cls === 'negative' ? 'price-down' : ''}">${formatTrendHtml(stock.changePct)}</span>
                </div>
              </button>`;
            })
            .join('');

          return `<section class="level-group">
            <div class="level-title">${group.level}</div>
            <div class="stock-chip-wrap">${chips}</div>
          </section>`;
        })
        .join('');

      const maxUp = Math.max(...day.sectorAttack.leaders.map((x) => x.changePct));
      const maxDown = Math.max(...day.sectorAttack.losers.map((x) => Math.abs(x.changePct)));
      patchBars(
        sectorUp,
        day.sectorAttack.leaders.map((x) => ({ label: `${x.name} ${trendArrow(x.changePct)} ${Math.abs(x.changePct).toFixed(2)}%`, value: x.changePct })),
        maxUp
      );
      patchBars(
        sectorDown,
        day.sectorAttack.losers.map((x) => ({ label: `${x.name} ${trendArrow(x.changePct)} ${Math.abs(x.changePct).toFixed(2)}%`, value: Math.abs(x.changePct) })),
        maxDown,
        'loss'
      );
      sectorSummary.textContent = day.sectorAttack.summary;

      attachStockHoverHandlers();
      attachSortableTables();
    }

    dateInput.value = today;
    dateInput.min = state.data.meta.historyRange.from;
    dateInput.max = state.data.meta.historyRange.to;
    dateInput.addEventListener('change', () => renderByDate(dateInput.value));

    renderByDate(today);
  }

  function pulseRealtimeBars() {} // disabled

  function renderHotList() {
    const dateInput = document.getElementById('hot-date');
    const hourSelect = document.getElementById('hot-hour');
    const nowBtn = document.getElementById('hot-now');
    const hotBody = document.getElementById('hot-body');
    const hotEmpty = document.getElementById('hot-empty');

    // 填充小时下拉 00-23
    for (let h = 0; h < 24; h++) {
      const opt = document.createElement('option');
      const val = String(h).padStart(2, '0');
      opt.value = val;
      opt.textContent = val;
      hourSelect.appendChild(opt);
    }

    const now = new Date();
    const currentHour = String(now.getHours()).padStart(2, '0');

    dateInput.value = (state.data && state.data.meta && state.data.meta.today) || now.toISOString().slice(0, 10);
    dateInput.min = (state.data && state.data.meta && state.data.meta.historyRange && state.data.meta.historyRange.from) || '2024-01-01';
    dateInput.max = now.toISOString().slice(0, 10);
    hourSelect.value = currentHour;

    async function load(date, hour) {
      const slot = `${hour}:00`;
      hotBody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:24px">加载中...</td></tr>';
      if (hotEmpty) hotEmpty.style.display = 'none';

      try {
        const resp = await fetch(`/api/hotrank?date=${encodeURIComponent(date)}&slot=${encodeURIComponent(slot)}`);
        const data = await resp.json();
        const raw = data.items || [];

        if (raw.length === 0) {
          hotBody.innerHTML = '';
          if (hotEmpty) hotEmpty.style.display = 'block';
          return;
        }

        const maxHeat = Math.max(1, ...raw.map(x => x.heat_value || 0));

        hotBody.innerHTML = raw.map((r) => {
          const rowClass = r.is_limit_up ? 'limit-up-row' : '';
          const concepts = (r.concept_tag || '').split(';').filter(Boolean);
          const conceptTags = concepts.map(c => `<span class="tag">${escapeHtml(c)}</span>`).join('');
          const heatWidth = ((r.heat_value || 0) / maxHeat) * 100;
          const code = r.code || '';
          const name = r.name || '';
          const changePct = r.change_pct || 0;

          return `<tr class="${rowClass}" data-stock-code="${code}">
            <td class="right">${r.rank}</td>
            <td class="mono">${code}</td>
            <td><span class="hoverable-stock" data-stock-code="${code}">${escapeHtml(name)}</span></td>
            <td class="right mono heat-cell">
              <div class="heat-meta"><span>${(r.heat_value || 0).toFixed(1)}</span></div>
              <div class="heat-rail"><div class="heat-fill" style="width:${heatWidth.toFixed(1)}%"></div></div>
            </td>
            <td>${conceptTags}</td>
            <td class="right">${formatTrendHtml(changePct)}</td>
            <td><button class="btn-ghost teammate-trigger" type="button" data-stock-code="${code}">找队友</button></td>
          </tr>`;
        }).join('');

        // 行点击 → 涨停股跳转个股分析
        hotBody.querySelectorAll('tr').forEach((tr) => {
          tr.addEventListener('click', (event) => {
            const code = tr.dataset.stockCode;
            if (!code) return;
            const isButton = event.target instanceof Element && event.target.closest('.teammate-trigger');
            if (isButton) return;
            const row = raw.find(x => x.code === code);
            if (row && row.is_limit_up) {
              state.currentStockCode = code;
              renderPage('stock-analysis');
            }
          });
        });

        // 找队友按钮
        hotBody.querySelectorAll('.teammate-trigger').forEach((btn) => {
          btn.addEventListener('click', (event) => {
            event.stopPropagation();
            state.currentStockCode = btn.getAttribute('data-stock-code');
            renderPage('stock-analysis');
          });
        });

        attachStockHoverHandlers();
        attachSortableTables();
      } catch (e) {
        hotBody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:24px;color:var(--negative)">加载失败</td></tr>';
      }
    }

    dateInput.addEventListener('change', () => load(dateInput.value, hourSelect.value));
    hourSelect.addEventListener('change', () => load(dateInput.value, hourSelect.value));

    nowBtn.addEventListener('click', () => {
      const n = new Date();
      dateInput.value = n.toISOString().slice(0, 10);
      hourSelect.value = String(n.getHours()).padStart(2, '0');
      load(dateInput.value, hourSelect.value);
    });

    // 初始加载
    load(dateInput.value, hourSelect.value);
  }




  function renderStockInfoCard(code) {
    const stock = byCode(code);
    const infoRoot = document.getElementById('stock-info');
    if (!stock || !infoRoot) return;
    const intraday = state.data.stockAnalysis.intraday[code] || state.data.stockAnalysis.intradayFallback;
    const first = intraday[0]?.value || 0;
    const last = intraday[intraday.length - 1]?.value || first;
    const pulsePct = first ? ((last - first) / first) * 100 : 0;
    const pulseText = pulsePct > 1.2 ? '趋势增强' : pulsePct < -1.2 ? '趋势走弱' : '震荡整理';

    infoRoot.innerHTML = `
      <div class="row" style="justify-content:space-between;align-items:flex-start">
        <div>
          <h3 class="card-title" style="font-size:20px">${stock.name} <span class="mono" style="font-size:13px;color:var(--muted)">${stock.code}</span></h3>
          <div style="margin-top:6px;display:flex;gap:6px;flex-wrap:wrap;">
            ${stock.concepts.map((c) => `<span class="tag">${c}</span>`).join('')}
            <span class="tag violet">Signal · ${pulseText}</span>
            <span class="tag">${formatTrendHtml(pulsePct)}</span>
          </div>
        </div>
        <div class="section-note">仅支持当天数据</div>
      </div>
      <div class="hover-grid" style="margin-top:14px">
        <div><div class="hover-label">总市值</div><div>${formatMoney(stock.marketCap)}</div></div>
        <div><div class="hover-label">流通市值</div><div>${formatMoney(stock.floatCap)}</div></div>
        <div><div class="hover-label">市盈率</div><div>${stock.pe.toFixed(1)}</div></div>
        <div><div class="hover-label">换手率</div><div>${stock.turnover.toFixed(2)}%</div></div>
        <div><div class="hover-label">量比</div><div>${stock.volumeRatio.toFixed(2)}</div></div>
      </div>
    `;
  }

  function drawLineChart(canvas, points, options = {}) {
    if (!(canvas instanceof HTMLCanvasElement)) return;
    const theme = getChartTheme();
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const w = Math.max(320, rect.width);
    const h = Math.max(180, rect.height);
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);

    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.scale(dpr, dpr);

    const pad = { top: 18, right: 24, bottom: 24, left: 42 };
    const innerW = w - pad.left - pad.right;
    const innerH = h - pad.top - pad.bottom;

    const values = points.map((p) => p.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = Math.max(0.0001, max - min);

    const xAt = (idx) => pad.left + (idx / (points.length - 1)) * innerW;
    const yAt = (val) => pad.top + (1 - (val - min) / range) * innerH;

    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = theme.surface;
    ctx.fillRect(0, 0, w, h);

    ctx.strokeStyle = theme.grid;
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i += 1) {
      const y = pad.top + (innerH / 4) * i;
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(w - pad.right, y);
      ctx.stroke();
    }

    ctx.beginPath();
    points.forEach((p, idx) => {
      const x = xAt(idx);
      const y = yAt(p.value);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.lineWidth = options.lineWidth || 2.2;
    ctx.strokeStyle = options.stroke || theme.primary;
    ctx.stroke();

    const gradient = ctx.createLinearGradient(0, pad.top, 0, h - pad.bottom);
    gradient.addColorStop(0, options.fillTop || theme.primaryFillTop);
    gradient.addColorStop(1, options.fillBottom || theme.primaryFillBottom);

    ctx.beginPath();
    points.forEach((p, idx) => {
      const x = xAt(idx);
      const y = yAt(p.value);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.lineTo(w - pad.right, h - pad.bottom);
    ctx.lineTo(pad.left, h - pad.bottom);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    ctx.fillStyle = theme.axis;
    ctx.font = '12px ui-monospace, SFMono-Regular, Menlo, monospace';
    ctx.textAlign = 'right';
    ctx.fillText(max.toFixed(2), pad.left - 6, pad.top + 6);
    ctx.fillText(min.toFixed(2), pad.left - 6, h - pad.bottom);

    const tooltip = canvas.parentElement?.querySelector('.chart-tooltip');
    if (!(tooltip instanceof HTMLElement)) return;

    const hit = (x) => {
      const ratio = (x - pad.left) / innerW;
      const idx = Math.max(0, Math.min(points.length - 1, Math.round(ratio * (points.length - 1))));
      return idx;
    };

    function onMove(evt) {
      const bound = canvas.getBoundingClientRect();
      const x = evt.clientX - bound.left;
      const idx = hit(x);
      const p = points[idx];
      const tx = xAt(idx);
      const ty = yAt(p.value);
      tooltip.classList.add('is-visible');
      tooltip.style.left = `${tx}px`;
      tooltip.style.top = `${ty}px`;
      tooltip.innerHTML = `<strong>${p.time || p.label || idx}</strong><br>${p.value.toFixed(2)}`;
    }

    function onLeave() {
      tooltip.classList.remove('is-visible');
    }

    canvas.onmousemove = onMove;
    canvas.onmouseleave = onLeave;
    canvas.onwheel = (evt) => {
      evt.preventDefault();
      const delta = evt.deltaY > 0 ? -0.04 : 0.04;
      const next = points.map((p) => ({ ...p, value: p.value * (1 + delta) }));
      drawLineChart(canvas, next, options);
    };
  }

  function buildDayKFallback(points) {
    if (!Array.isArray(points) || points.length === 0) return [];
    let prevClose = points[0].value;
    return points.map((p, idx) => {
      const close = Number(p.value);
      const drift = Math.sin((idx + 1) * 1.37) * 0.0045;
      const open = idx === 0 ? close * (1 - drift) : prevClose * (1 + drift * 0.6);
      const high = Math.max(open, close) * (1 + 0.003 + Math.abs(drift));
      const low = Math.min(open, close) * (1 - 0.003 - Math.abs(drift) * 0.7);
      const volume = Number((8 + Math.abs(close - open) * 220 + (idx % 5) * 1.6).toFixed(2));
      prevClose = close;
      return {
        date: p.time || `D${idx + 1}`,
        open: Number(open.toFixed(2)),
        high: Number(high.toFixed(2)),
        low: Number(low.toFixed(2)),
        close: Number(close.toFixed(2)),
        volume
      };
    });
  }

  function drawDayKChart(candleSvg, volSvg, tooltip, records) {
    if (!(candleSvg instanceof SVGElement) || !(volSvg instanceof SVGElement) || !Array.isArray(records) || records.length === 0) return;
    const theme = getChartTheme();
    const parsedRaw = records.map((r) => ({
      date: String(r.date || ''),
      open: Number(r.open),
      high: Number(r.high),
      low: Number(r.low),
      close: Number(r.close),
      volume: Number(r.volume)
    }));
    const full = extendDayKSeries(parsedRaw, 36);

    const width = 880;
    const height = 320;
    const pad = { left: 42, right: 36, top: 22, bottom: 22 };
    const innerW = width - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;
    const volH = 92;

    let windowSize = Number(candleSvg.dataset.windowSize || Math.min(full.length, 32));
    if (!Number.isFinite(windowSize) || windowSize < 12) windowSize = Math.min(full.length, 30);
    windowSize = Math.min(full.length, windowSize);

    function render(windowCount) {
      const points = full.slice(-windowCount);
      const highs = points.map((p) => p.high);
      const lows = points.map((p) => p.low);
      const maxRaw = Math.max(...highs);
      const minRaw = Math.min(...lows);
      const padRatio = 0.06;
      const max = maxRaw * (1 + padRatio);
      const min = minRaw * (1 - padRatio);
      const range = Math.max(0.0001, max - min);
      const xStep = innerW / Math.max(1, points.length - 1);
      const bodyW = Math.max(6.2, Math.min(11.8, xStep * 0.5));
      const yAt = (value) => pad.top + (1 - (value - min) / range) * innerH;
      const xAt = (idx) => pad.left + idx * xStep;
      const gridLines = 6;

      const grid = Array.from({ length: gridLines }, (_, i) => {
        const y = pad.top + (innerH / (gridLines - 1)) * i;
        return `<line x1="${pad.left}" y1="${y.toFixed(2)}" x2="${(width - pad.right).toFixed(2)}" y2="${y.toFixed(2)}" stroke="${theme.grid}" stroke-dasharray="2 4"></line>`;
      }).join('');

      const labels = Array.from({ length: 4 }, (_, i) => {
        const ratio = i / 3;
        const y = pad.top + innerH * ratio;
        const val = max - range * ratio;
        return `<text x="6" y="${(y + 4).toFixed(2)}" class="kline-axis-label">${val.toFixed(2)}</text>`;
      }).join('');

      const smaPoints = points.map((_, idx) => {
        const slice = points.slice(Math.max(0, idx - 4), idx + 1);
        const avg = slice.reduce((acc, x) => acc + x.close, 0) / slice.length;
        return `${xAt(idx).toFixed(2)},${yAt(avg).toFixed(2)}`;
      });
      const sma = `<polyline fill="none" stroke="${cssVar('--accent', '#facc15')}" stroke-opacity="0.62" stroke-width="1.35" stroke-dasharray="3 3" points="${smaPoints.join(' ')}"></polyline>`;

      const candles = points
        .map((p, idx) => {
          const x = xAt(idx);
          const yOpen = yAt(p.open);
          const yClose = yAt(p.close);
          const yHigh = yAt(p.high);
          const yLow = yAt(p.low);
          const isUp = p.close >= p.open;
          const color = isUp ? cssVar('--positive', '#22e58c') : cssVar('--negative', '#ff4f6d');
          const top = Math.min(yOpen, yClose);
          const hRaw = Math.abs(yOpen - yClose);
          const isDoji = hRaw < 1.2;
          const h = Math.max(1.6, hRaw);
          const rectFill = isUp ? theme.surface : color;
          const rectStroke = color;
          const rectStrokeWidth = isDoji ? 1.45 : 1.15;
          const opacity = p.inferred ? 0.32 : 1;
          return `<g data-kidx="${idx}" opacity="${opacity}">
            <line x1="${x.toFixed(2)}" y1="${yHigh.toFixed(2)}" x2="${x.toFixed(2)}" y2="${yLow.toFixed(2)}" stroke="${color}" stroke-width="1.12"></line>
            <rect x="${(x - bodyW / 2).toFixed(2)}" y="${top.toFixed(2)}" width="${bodyW.toFixed(2)}" height="${h.toFixed(2)}" fill="${rectFill}" stroke="${rectStroke}" stroke-width="${rectStrokeWidth}"></rect>
          </g>`;
        })
        .join('');

      const visiblePoints = points.filter((p) => !p.inferred);
      const last = visiblePoints[visiblePoints.length - 1] || points[points.length - 1];
      const lastY = yAt(last.close);
      const markerColor = last.close >= last.open ? cssVar('--positive', '#22e58c') : cssVar('--negative', '#ff4f6d');
      const markerTextColor = last.close >= last.open ? '#00200f' : '#25020a';
      const marker = `<g>
        <line x1="${pad.left}" y1="${lastY.toFixed(2)}" x2="${(width - pad.right).toFixed(2)}" y2="${lastY.toFixed(2)}" stroke="${markerColor}" stroke-opacity="0.28" stroke-dasharray="2 3"></line>
        <rect x="${(width - 46).toFixed(2)}" y="${(lastY - 10).toFixed(2)}" width="42" height="20" rx="4" fill="${markerColor}"></rect>
        <text x="${(width - 25).toFixed(2)}" y="${(lastY + 4).toFixed(2)}" font-family="Geist Mono,monospace" font-size="10" fill="${markerTextColor}" text-anchor="middle" font-weight="700">${last.close.toFixed(2)}</text>
      </g>`;

      candleSvg.innerHTML = `<rect width="${width}" height="${height}" fill="${theme.surface}"></rect>${grid}${labels}${sma}${candles}${marker}`;

      const maxVol = Math.max(1, ...points.map((p) => p.volume));
      const volBars = points
        .map((p, idx) => {
          const x = xAt(idx);
          const h = (p.volume / maxVol) * (volH - 14);
          const y = volH - h;
          const isUp = p.close >= p.open;
          const color = isUp ? cssVar('--positive', '#22e58c') : cssVar('--negative', '#ff4f6d');
          const opacity = p.inferred ? (isUp ? '0.18' : '0.22') : isUp ? '0.45' : '0.55';
          return `<rect x="${(x - bodyW / 2).toFixed(2)}" y="${y.toFixed(2)}" width="${bodyW.toFixed(2)}" height="${h.toFixed(2)}" fill="${color}" opacity="${opacity}"></rect>`;
        })
        .join('');

      volSvg.innerHTML = `<rect width="${width}" height="${volH}" fill="${theme.surface}"></rect>${volBars}<text x="8" y="14" class="kline-axis-label">VOL</text>`;
      const ticksCount = Math.min(6, points.length);
      const xTickRows = Array.from({ length: ticksCount }, (_, i) => {
        const idx = Math.floor((i / Math.max(1, ticksCount - 1)) * (points.length - 1));
        const x = xAt(idx);
        const label = points[idx].date;
        return `<text x="${x.toFixed(2)}" y="${(height - 5).toFixed(2)}" class="kline-axis-label" text-anchor="middle">${label}</text>`;
      }).join('');
      candleSvg.innerHTML += xTickRows;

      candleSvg.onmousemove = (evt) => {
        if (!(tooltip instanceof HTMLElement)) return;
        const bound = candleSvg.getBoundingClientRect();
        const x = evt.clientX - bound.left;
        const idx = Math.max(0, Math.min(points.length - 1, Math.round((x - pad.left) / Math.max(1, xStep))));
        const item = points[idx];
        const xPos = xAt(idx);
        const yPos = yAt(item.close);
        const pct = ((item.close - item.open) / item.open) * 100;
        tooltip.classList.add('is-visible');
        tooltip.style.left = `${xPos}px`;
        tooltip.style.top = `${yPos}px`;
        tooltip.innerHTML = `<strong>${item.date || '--'}</strong><br><span class="mono">O ${item.open.toFixed(2)} · H ${item.high.toFixed(2)}</span><br><span class="mono">L ${item.low.toFixed(2)} · C ${item.close.toFixed(2)}</span><br><span class="mono">VOL ${item.volume.toFixed(2)}万手</span><div class="kline-pct">${formatTrendHtml(pct)}</div>`;
      };

      candleSvg.onmouseleave = () => {
        if (tooltip instanceof HTMLElement) tooltip.classList.remove('is-visible');
      };
    }

    candleSvg.onwheel = (evt) => {
      evt.preventDefault();
      windowSize += evt.deltaY > 0 ? -2 : 2;
      windowSize = Math.max(12, Math.min(full.length, windowSize));
      candleSvg.dataset.windowSize = String(windowSize);
      render(windowSize);
    };

    render(windowSize);
  }

  function resolveDayKSeries(code) {
    const stockPage = state.data.stockAnalysis;
    const fromData = stockPage.dayK && Array.isArray(stockPage.dayK[code]) ? stockPage.dayK[code] : null;
    if (fromData && fromData.length > 0) return fromData;
    return [];
    const intraday = stockPage.intraday[code] || stockPage.intradayFallback;
    return buildDayKFallback(intraday);
  }

  function repaintStockCharts(code) {
    const stockPage = state.data.stockAnalysis;
    const intraday = stockPage.intraday[code] || stockPage.intradayFallback;
    const lineChart = document.getElementById('intraday-chart');
    if (lineChart) drawLineChart(lineChart, intraday);

    const dayKCandle = document.getElementById('dayk-candle');
    const dayKVol = document.getElementById('dayk-volume');
    const tooltip = document.getElementById('kline-tooltip');
    if (dayKCandle && dayKVol) {
      drawDayKChart(dayKCandle, dayKVol, tooltip, resolveDayKSeries(code));
    }
  }

  function drawMultiLineChart(canvas, curveSet) {
    if (!(canvas instanceof HTMLCanvasElement) || !Array.isArray(curveSet) || curveSet.length === 0) return;
    const theme = getChartTheme();
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const w = Math.max(320, rect.width);
    const h = Math.max(180, rect.height);
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);

    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.scale(dpr, dpr);

    const pad = { top: 18, right: 24, bottom: 24, left: 42 };
    const innerW = w - pad.left - pad.right;
    const innerH = h - pad.top - pad.bottom;
    const pointCount = curveSet[0].points.length;

    const allValues = curveSet.flatMap((curve) => curve.points.map((p) => p.value));
    const min = Math.min(...allValues);
    const max = Math.max(...allValues);
    const range = Math.max(0.0001, max - min);

    const xAt = (idx) => pad.left + (idx / Math.max(1, pointCount - 1)) * innerW;
    const yAt = (val) => pad.top + (1 - (val - min) / range) * innerH;

    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = theme.surface;
    ctx.fillRect(0, 0, w, h);

    ctx.strokeStyle = theme.grid;
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i += 1) {
      const y = pad.top + (innerH / 4) * i;
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(w - pad.right, y);
      ctx.stroke();
    }

    curveSet.forEach((curve, index) => {
      const stroke = theme.strokePalette[index % theme.strokePalette.length];
      const fill = theme.fillPalette[index % theme.fillPalette.length];
      ctx.beginPath();
      curve.points.forEach((p, idx) => {
        const x = xAt(idx);
        const y = yAt(p.value);
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.lineWidth = 2;
      ctx.strokeStyle = stroke;
      ctx.globalAlpha = 0.72;
      ctx.stroke();

      ctx.beginPath();
      curve.points.forEach((p, idx) => {
        const x = xAt(idx);
        const y = yAt(p.value);
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.lineTo(w - pad.right, h - pad.bottom);
      ctx.lineTo(pad.left, h - pad.bottom);
      ctx.closePath();
      ctx.fillStyle = fill;
      ctx.fill();
      ctx.globalAlpha = 1;
    });

    ctx.fillStyle = theme.axis;
    ctx.font = '12px ui-monospace, SFMono-Regular, Menlo, monospace';
    ctx.textAlign = 'right';
    ctx.fillText(max.toFixed(2), pad.left - 6, pad.top + 6);
    ctx.fillText(min.toFixed(2), pad.left - 6, h - pad.bottom);

    const tooltip = canvas.parentElement?.querySelector('.chart-tooltip');
    if (!(tooltip instanceof HTMLElement)) return;

    const hit = (x) => {
      const ratio = (x - pad.left) / innerW;
      return Math.max(0, Math.min(pointCount - 1, Math.round(ratio * (pointCount - 1))));
    };

    function onMove(evt) {
      const bound = canvas.getBoundingClientRect();
      const x = evt.clientX - bound.left;
      const idx = hit(x);
      const xPos = xAt(idx);
      const avg = curveSet.reduce((acc, c) => acc + c.points[idx].value, 0) / curveSet.length;
      const yPos = yAt(avg);

      tooltip.classList.add('is-visible');
      tooltip.style.left = `${xPos}px`;
      tooltip.style.top = `${yPos}px`;
      tooltip.innerHTML = `<strong>${curveSet[0].points[idx].label}</strong><br>均值 ${avg.toFixed(2)}`;
    }

    function onLeave() {
      tooltip.classList.remove('is-visible');
    }

    canvas.onmousemove = onMove;
    canvas.onmouseleave = onLeave;
    canvas.onwheel = (evt) => {
      evt.preventDefault();
      const scale = evt.deltaY > 0 ? 0.985 : 1.015;
      const scaled = curveSet.map((curve) => ({
        ...curve,
        points: curve.points.map((p) => ({ ...p, value: p.value * scale }))
      }));
      drawMultiLineChart(canvas, scaled);
    };
  }

  function renderStockAnalysis() {
    const stockPage = state.data.stockAnalysis;
    const input = document.getElementById('stock-search-input');
    const queryBtn = document.getElementById('stock-search-btn');
    const tabWrap = document.getElementById('teammate-tabs');
    const chartModeWrap = document.getElementById('stock-chart-mode');
    const intradayWrap = document.getElementById('intraday-wrap');
    const klineWrap = document.getElementById('kline-wrap');
    const teammatePane = document.getElementById('stock-teammate-pane');
    const blockTradeBody = document.getElementById('block-trade-body');
    let chartMode = 'kline';

    function setChartMode(mode) {
      chartMode = mode;
      if (chartModeWrap) {
        chartModeWrap.querySelectorAll('.chart-chip[data-mode]').forEach((btn) => {
          btn.classList.toggle('is-active', btn.getAttribute('data-mode') === mode);
        });
      }
      if (intradayWrap) intradayWrap.classList.toggle('hide', mode !== 'intraday');
      if (klineWrap) klineWrap.classList.toggle('hide', mode !== 'kline');
    }

    async function renderTeammates(code) {
      let source = (state.data.teammates && state.data.teammates[code]) || null;
      // 不在热榜缓存中 → 实时查询
      if (!source) {
        try {
          const resp = await fetch(`/api/stock/${code}`);
          const d = await resp.json();
          const mates = d.teammates || [];
          if (mates.length > 0) {
            source = { byConcept: mates, byTrend: mates };
            // 缓存到 state，避免重复请求
            if (!state.data.teammates) state.data.teammates = {};
            state.data.teammates[code] = source;
          }
        } catch (e) {
          console.warn('fetch teammates error:', e);
        }
      }
      const mates = (source && source.byConcept) || [];
      const stockInfo = byCode(code) || { name: code };

      if (mates.length === 0) {
        teammatePane.innerHTML = '<div style="padding:24px;text-align:center;color:var(--muted)">暂无队友数据</div>';
        return;
      }

      // ── 拉分时图数据（当前票 + 队友）──
      const allCodes = [code, ...mates.map(m => m.code)];
      const intradayMap = {};
      for (const c of allCodes) {
        const cached = state.data.stockAnalysis.intraday[c];
        if (cached && Array.isArray(cached) && cached.length > 0) {
          intradayMap[c] = cached;
          continue;
        }
        try {
          const resp = await fetch(`/api/stock/${c}`);
          const d = await resp.json();
          const ida = d.intraday || [];
          if (ida.length > 0) {
            intradayMap[c] = ida.map(p => ({ time: p.time || '', value: p.close || p.open || 0 }));
            state.data.stockAnalysis.intraday[c] = intradayMap[c];
          }
        } catch (e) { /* skip */ }
      }

      // ── 构建叠加曲线（用涨跌幅%）──
      const curves = [];
      if (intradayMap[code] && intradayMap[code].length > 0) {
        const base = intradayMap[code][0].value || 1;
        curves.push({
          label: `${stockInfo.name}（当前）`,
          points: intradayMap[code].map(p => ({ value: base ? ((p.value - base) / base) * 100 : 0 })),
        });
      }
      mates.forEach((m, idx) => {
        const ida = intradayMap[m.code];
        if (ida && ida.length > 0) {
          const base = ida[0].value || 1;
          curves.push({
            label: m.name,
            points: ida.map(p => ({ value: base ? ((p.value - base) / base) * 100 : 0 })),
          });
        }
      });

      const palette = ['#22d3ee', '#a78bfa', '#facc15', '#22e58c', '#fb7185', '#38bdf8'];

      // ── HTML ──
      let html = '';
      if (curves.length >= 2) {
        html += `<canvas id="teammate-chart" width="800" height="260" style="width:100%;min-height:260px;margin-bottom:8px"></canvas>`;
        html += `<div style="display:flex;gap:14px;flex-wrap:wrap;margin-bottom:12px;font-size:11px">`;
        curves.forEach((c, i) => {
          html += `<span style="display:flex;align-items:center;gap:4px"><span style="width:10px;height:10px;border-radius:2px;background:${palette[i % palette.length]}"></span>${c.label}</span>`;
        });
        html += `</div>`;
      }

      html += `<div class="table-wrap"><table>
        <thead><tr><th>名称</th><th class="right">涨跌幅</th><th class="right">相关性</th></tr></thead>
        <tbody>
          ${mates.map((m, idx) => {
            const color = palette[idx % palette.length];
            return `<tr>
              <td><span class="hoverable-stock" data-stock-code="${m.code}" style="display:inline-flex;align-items:center;gap:4px"><span style="width:8px;height:8px;border-radius:2px;background:${color};display:inline-block"></span>${m.name}</span></td>
              <td class="right">${formatTrendHtml(m.changePct)}</td>
              <td class="right mono">${m.corr.toFixed(2)}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table></div>`;

      teammatePane.innerHTML = html;
      attachStockHoverHandlers();

      // ── 绑定点击队友切换代码 ──
      teammatePane.querySelectorAll('.hoverable-stock').forEach(el => {
        el.style.cursor = 'pointer';
        el.addEventListener('click', () => {
          const c = el.getAttribute('data-stock-code');
          if (c) renderStock(c).catch(e => console.warn('renderStock error:', e));
        });
      });

      // ── 画叠加图 ──
      if (curves.length >= 2) {
        requestAnimationFrame(() => {
          const canvas = document.getElementById('teammate-chart');
          if (canvas) {
            const origPalette = getChartTheme().strokePalette;
            const themeWithCustomPalette = { ...getChartTheme(), strokePalette: palette, fillPalette: palette.map(c => c + '33') };
            // 临时 override：用自定义 palette 画图
            drawMultiLineChartWithPalette(canvas, curves, palette);
          }
        });
      }
    }

    // 使用自定义 palette 的多线图
    function drawMultiLineChartWithPalette(canvas, curveSet, strokePaletteOverride) {
      // 复用 drawMultiLineChart 但用自定义 palette
      const savedStroke = getChartTheme().strokePalette;
      const savedFill = getChartTheme().fillPalette;
      getChartTheme().strokePalette = strokePaletteOverride;
      getChartTheme().fillPalette = strokePaletteOverride.map(c => c + '33');
      drawMultiLineChart(canvas, curveSet);
      getChartTheme().strokePalette = savedStroke;
      getChartTheme().fillPalette = savedFill;
    }

    async function renderStock(code) {
      const stock = byCode(code);
      state.currentStockCode = code;
      input.value = code;

      // 如果 stockMeta 中没有此代码，仍然尝试渲染基本信息
      if (!stock) {
        renderStockInfoCard(code);
      } else {
        renderStockInfoCard(code);
      }

      // 如果 dayK 中没有此代码的数据，从接口拉取
      const stockPage = state.data.stockAnalysis;
      let needsFetch = !stockPage.dayK[code] || !Array.isArray(stockPage.dayK[code]) || stockPage.dayK[code].length === 0;
      if (needsFetch || !stockPage.blockTrades[code]) {
        try {
          const res = await fetch('/api/stock/' + encodeURIComponent(code), { cache: 'no-store' });
          if (res.ok) {
            const data = await res.json();
            if (data.klines && data.klines.length > 0) {
              stockPage.dayK[code] = data.klines.map(k => ({
                date: k.date, open: k.open, close: k.close,
                high: k.high, low: k.low, volume: k.volume
              }));
            }
            if (data.intraday && data.intraday.length > 0) {
              stockPage.intraday[code] = data.intraday.map(d => ({
                time: d.time, value: d.close
              }));
            }
            if (data.bigOrders) {
              stockPage.blockTrades[code] = data.bigOrders;
            }
          }
        } catch (e) {
          console.warn('fetch stock failed:', code, e);
        }
      }

      repaintStockCharts(code);
      setChartMode(chartMode);

      const trades = stockPage.blockTrades[code] || stockPage.blockTradesFallback || [];
      blockTradeBody.innerHTML = (trades || [])
        .map(
          (t) => `<tr>
            <td>${t.time}</td>
            <td><span class="trend ${t.side === '买入' ? 'up' : 'down'}"><span class="arr">${t.side === '买入' ? '▲' : '▼'}</span></span> <span class="${t.side === '买入' ? 'positive' : 'negative'}">${t.side}</span></td>
            <td class="right mono">${t.volume}</td>
            <td class="right mono">${t.amount}</td>
            <td class="right mono">${t.price.toFixed(2)}</td>
          </tr>`
        )
        .join('');

      renderTeammates(code);
    }

    queryBtn.addEventListener('click', () => {
      const code = input.value.trim();
      renderStock(code).catch(e => console.warn('renderStock error:', e));
    });

    input.addEventListener('keydown', (evt) => {
      if (evt.key === 'Enter') {
        evt.preventDefault();
        queryBtn.click();
      }
    });

    if (chartModeWrap) {
      chartModeWrap.querySelectorAll('.chart-chip[data-mode]').forEach((btn) => {
        btn.addEventListener('click', () => {
          setChartMode(btn.getAttribute('data-mode'));
        });
      });
    }

    renderStock(state.currentStockCode || stockPage.defaultCode);
    attachSortableTables();
  }

  function renderStrategyBacktest() {
    const backtest = state.data.strategyBacktest;
    const strategySelect = document.getElementById('strategy-select');
    const strategyTitleNote = document.getElementById('strategy-title-note');
    const strategyDesc = document.getElementById('strategy-desc');
    const strategyConfigNote = document.getElementById('strategy-config-note');
    const runBtn = document.getElementById('run-backtest-btn');
    const refreshBtn = document.getElementById('refresh-strategy-btn');
    const metricsRow = document.getElementById('backtest-metrics');
    const detailBody = document.getElementById('backtest-detail-body');
    const curveCanvas = document.getElementById('equity-curves');
    const paramPills = document.getElementById('strategy-param-pills');
    const stockCountInput = document.getElementById('bt-stock-count');
    const windowDaysInput = document.getElementById('bt-window-days');
    const tradeTimesInput = document.getElementById('bt-trade-times');
    const capitalInput = document.getElementById('bt-capital');

    strategySelect.innerHTML = backtest.strategies
      .map((s) => `<option value="${s.id}">${s.name}</option>`)
      .join('');

    function paintCurves(curveSet) {
      drawMultiLineChart(curveCanvas, curveSet);
    }

    function fillDetail(rows) {
      detailBody.innerHTML = rows
        .map(
          (r) => `<tr>
            <td>${r.stock}</td>
            <td class="right mono">${r.window}</td>
            <td class="right">${formatTrendHtml(r.ret)}</td>
            <td class="right mono">${r.sharpe.toFixed(2)}</td>
            <td class="right">${formatTrendHtml(r.maxDd)}</td>
            <td class="right mono">${r.winRate.toFixed(1)}%</td>
            <td class="right mono">${r.trades}</td>
          </tr>`
        )
        .join('');
    }

    function run(selectedId) {
      const scenario = backtest.results[selectedId] || backtest.results['default'] || {curves:[],metrics:{},details:[]};
      const stockCount = Number(stockCountInput?.value || 20);
      const windowDays = Number(windowDaysInput?.value || 60);
      const tradeTimes = Number(tradeTimesInput?.value || 2);
      const capital = Number(capitalInput?.value || 100);

      strategyDesc.textContent = (backtest.strategies.find((x) => x.id === selectedId) || backtest.strategies[0]).description;
      if (strategyTitleNote) {
        strategyTitleNote.textContent = `当前配置：${stockCount}只股票 / ${windowDays}天窗口 / 单票${tradeTimes}次 / 初始资金${capital}万`;
      }
      if (strategyConfigNote) {
        strategyConfigNote.textContent = `参数摘要：每轮选 ${stockCount} 只股票 · 观察窗口 ${windowDays} 天 · 单票最多交易 ${tradeTimes} 次 · 初始资金 ${capital} 万`;
      }
      if (paramPills) {
        paramPills.innerHTML = [
          { i: '票', k: '股票数量', v: `<span class="num">${stockCount}</span> 只 / 每轮选股池规模` },
          { i: '窗', k: '窗口天数', v: `<span class="num">${windowDays}</span> 天 / 滚动观测区间` },
          { i: '次', k: '每只次数', v: `<span class="num">${tradeTimes}</span> 次 / 单票最大交易次数` },
          { i: '资', k: '初始资金', v: `<span class="num">${capital}</span> 万 / 回测资金基准` }
        ]
          .map((x) => `<article class="param-pill"><div class="k"><span class="i">${x.i}</span>${x.k}</div><div class="v">${x.v}</div></article>`)
          .join('');
      }

      metricsRow.innerHTML = scenario.metrics
        .map((m) => {
          const key = m.label.includes('收益')
            ? 'metric-ret'
            : m.label.includes('夏普')
              ? 'metric-sharpe'
              : m.label.includes('回撤')
                ? 'metric-drawdown'
                : m.label.includes('胜率')
                  ? 'metric-winrate'
                  : 'metric-trades';
          const valueText = m.suffix === '%' ? `${m.value.toFixed(2)}%` : m.value;
          const hintText = m.label.includes('收益')
            ? '单位：区间平均收益'
            : m.label.includes('夏普')
              ? '收益/波动比值'
              : m.label.includes('回撤')
                ? '峰值到谷值跌幅'
                : m.label.includes('胜率')
                  ? '盈利交易占比'
                  : '累计成交笔数';
          const glyph = iconForMetricLabel(m.label);
          return `<article class="metric ${key}">
            <div class="head"><div class="label">${m.label}</div><span class="glyph">${glyph}</span></div>
            <div class="value ${metricClass(m.value)}">${valueText}</div>
            <div class="hint">${hintText}</div>
          </article>`;
        })
        .join('');

      paintCurves(scenario.curves);
      fillDetail(scenario.details);
      attachSortableTables();
    }

    strategySelect.addEventListener('change', () => run(strategySelect.value));
    
    // 开始回测 → 调真实 API
    runBtn.addEventListener('click', async () => {
      const sid = strategySelect.value;
      const strategy = backtest.strategies.find(s => s.id === sid);
      if (!strategy) return;
      
      // loading
      runBtn.disabled = true;
      runBtn.textContent = '回测中...';
      metricsRow.innerHTML = '<div style="padding:20px;text-align:center">⏳ 正在回测，请稍候...</div>';
      
      try {
        const resp = await fetch('/api/backtest/run', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            strategy: strategy.name,
            stock_count: Number(stockCountInput?.value || 20),
            window_days: Number(windowDaysInput?.value || 60),
            runs_per_stock: Number(tradeTimesInput?.value || 2),
            initial_capital: Number(capitalInput?.value || 100) * 10000,
          }),
        });
        if (!resp.ok) throw new Error('回测失败');
        const result = await resp.json();
        
        // 更新 state
        backtest.results[sid] = result;
        backtest.results.default = result;
        
        // 重新渲染
        paintCurves(result.curves);
        fillDetail(result.details);
        metricsRow.innerHTML = (result.metrics || []).map(m2 => `<article class="kpi">
          <div class="kpi-label">${m2.label}</div>
          <div class="kpi-value ${metricClass(m2.value)}">${m2.value}${m2.suffix||''}</div>
          <div class="kpi-hint">${m2.hint||''}</div>
        </article>`).join('');
        
      } catch(e) {
        metricsRow.innerHTML = `<div style="padding:20px;color:var(--red)">回测失败: ${e.message}</div>`;
      } finally {
        runBtn.disabled = false;
        runBtn.textContent = '开始回测';
      }
    });
    
    // 刷新策略 → 重新加载策略列表
    refreshBtn.addEventListener('click', async () => {
      refreshBtn.disabled = true;
      refreshBtn.textContent = '刷新中...';
      try {
        const resp = await fetch('/api/backtest/strategies');
        if (!resp.ok) throw new Error('获取失败');
        const data = await resp.json();
        // API 返回 {strategies: [...], details: {name: {name, description}}}
        const names = data.strategies || [];
        const details = data.details || {};
        backtest.strategies = names.map(name => ({
          id: name,
          name: name,
          description: (details[name] || {}).description || '',
        }));
        strategySelect.innerHTML = backtest.strategies
          .map(s => `<option value="${s.id}">${s.name}</option>`)
          .join('');
      } catch(e) {
        console.error('刷新策略失败:', e);
      } finally {
        refreshBtn.disabled = false;
        refreshBtn.textContent = '刷新策略';
      }
    });
    
    [stockCountInput, windowDaysInput, tradeTimesInput, capitalInput].forEach((input) => {
      if (!input) return;
      input.addEventListener('change', () => run(strategySelect.value));
    });

    // Don't auto-run on page load - user clicks to trigger
      // run(backtest.defaultStrategy);
  }

  function renderPaperAccount() {
    const account = state.data.paperAccount;
    const dateInput = document.getElementById('account-date');
    const metricRow = document.getElementById('account-metrics');
    const positionBody = document.getElementById('position-body');
    const tradeBody = document.getElementById('trade-body');
    const tradePairsBody = document.getElementById('trade-pairs-body');
    const positionDonut = document.getElementById('position-donut');
    const microBars = document.getElementById('account-micro-bars');

    function draw(date) {
      const snap = account.byDate[date] || account.byDate[state.data.meta.today];

      metricRow.innerHTML = snap.metrics
        .map(
          (m) => `<article class="kpi">
            <div class="kpi-label"><span class="ico">${iconForAccountMetric(m.label)}</span>${m.label}</div>
            <div class="kpi-value ${metricClass(m.value)}">${m.valueText}</div>
            <div class="kpi-hint">${m.hint}</div>
          </article>`
        )
        .join('');

      if (microBars) {
        const dayPnl = snap.metrics.find((x) => x.label === '今日盈亏')?.value || 0;
        const totalAsset = snap.metrics.find((x) => x.label === '总资产')?.value || 1;
        const cash = snap.metrics.find((x) => x.label === '可用资金')?.value || 0;
        const posVal = snap.metrics.find((x) => x.label === '持仓市值')?.value || 0;
        const cashRatio = (cash / Math.max(1, totalAsset)) * 100;
        const positionRatio = (posVal / Math.max(1, totalAsset)) * 100;
        const pnlHeat = clamp(6, Math.abs(dayPnl) * 18, 96);
        microBars.innerHTML = [
          { label: '仓位利用率', value: clamp(0, positionRatio, 100), tone: 'cyan', suffix: `${positionRatio.toFixed(1)}%` },
          { label: '现金占比', value: clamp(0, cashRatio, 100), tone: 'up', suffix: `${cashRatio.toFixed(1)}%` },
          { label: '盈亏热度', value: pnlHeat, tone: dayPnl >= 0 ? 'up' : 'down', suffix: `${dayPnl >= 0 ? '+' : ''}${(dayPnl/10000).toFixed(2)}万` }
        ]
          .map(
            (x) => `<div class="account-micro-row">
              <span class="account-micro-label">${x.label}</span>
              <div class="account-micro-track"><div class="account-micro-fill ${x.tone}" style="width:${x.value.toFixed(1)}%"></div></div>
              <span class="account-micro-value">${x.suffix}</span>
            </div>`
          )
          .join('');
      }

      positionBody.innerHTML = snap.positions
        .map(
          (p) => `<tr data-stock-code="${p.code}">
            <td class="mono">${p.code}</td>
            <td>
              <span class="account-asset">
                <span class="chip-dot ${trendClass(p.pnlPct)}"></span>
                <span class="hoverable-stock" data-stock-code="${p.code}">${p.name}</span>
              </span>
            </td>
            <td class="right mono">${p.qty}</td>
            <td class="right mono">${p.cost.toFixed(2)}</td>
            <td class="right mono">${p.last.toFixed(2)}</td>
            <td class="right mono">${Number(p.mv).toFixed(2)}万</td>
            <td class="right">${formatTrendHtml(p.pnlPct)}</td>
            <td class="right ${metricClass(p.pnlAmt)}">${p.pnlAmt > 0 ? '+' : ''}${p.pnlAmt.toFixed(2)}万</td>
          </tr>`
        )
        .join('');

      if (positionDonut) {
        drawDonutChart(
          positionDonut,
          snap.positions.map((p) => ({ label: p.name, value: parseMvToNum(p.mv) }))
        );
      }

      tradeBody.innerHTML = (snap.trades || [])
        .map(
          (t) => `<tr>
            <td>${t.time}</td>
            <td class="mono">${t.code}</td>
            <td><span class="trend ${t.direction === '买入' ? 'up' : 'down'}"><span class="arr">${t.direction === '买入' ? '▲' : '▼'}</span></span> <span class="${t.direction === '买入' ? 'positive' : 'negative'}">${t.direction}</span></td>
            <td class="right mono">${t.price.toFixed(2)}</td>
            <td class="right mono">${t.qty}</td>
            <td class="right mono">${t.amount.toFixed(0)}</td>
          </tr>`
        )
        .join('');

      // 历史交易配对记录
      if (tradePairsBody) {
        tradePairsBody.innerHTML = (account.tradePairs || [])
          .map(
            (p) => {
              const pnlCls = p.pnl != null ? (p.pnl >= 0 ? 'positive' : 'negative') : '';
              const pnlText = p.pnl != null ? `${p.pnl >= 0 ? '+' : ''}${p.pnl.toFixed(0)}` : '—';
              const pnlPctText = p.pnlPct != null ? `${p.pnlPct >= 0 ? '+' : ''}${p.pnlPct.toFixed(1)}%` : '—';
              return `<tr>
                <td><span class="mono">${p.code}</span> ${p.name}</td>
                <td>${p.buyDate} ${p.buyTime}</td>
                <td class="right mono">${p.buyPrice.toFixed(2)}</td>
                <td class="right mono">${p.buyQty}</td>
                <td>${p.sellDate ? p.sellDate + ' ' + p.sellTime : '<span style="color:var(--muted)">持仓中</span>'}</td>
                <td class="right mono">${p.sellPrice != null ? p.sellPrice.toFixed(2) : '—'}</td>
                <td class="right mono">${p.sellQty != null ? p.sellQty : '—'}</td>
                <td class="right ${pnlCls} mono">${pnlText}</td>
                <td class="right ${pnlCls} mono">${pnlPctText}</td>
              </tr>`;
            }
          )
          .join('');
      }

      attachStockHoverHandlers();
      attachSortableTables();
    }

    dateInput.value = state.data.meta.today;
    dateInput.min = state.data.meta.historyRange.from;
    dateInput.max = state.data.meta.historyRange.to;
    dateInput.addEventListener('change', () => draw(dateInput.value));

    draw(dateInput.value);
  }

  function runPageRenderer(pageId) {
    const renderers = {
      'daily-replay': renderDailyReplay,
      'hot-list': renderHotList,
      'stock-analysis': renderStockAnalysis,
      'strategy-backtest': renderStrategyBacktest,
      'paper-account': renderPaperAccount
    };
    const fn = renderers[pageId];
    if (fn) fn();
  }

  function attachSortableTables() {
    document.querySelectorAll('th.sortable').forEach((th) => {
      if (th.dataset.bound === '1') return;
      th.dataset.bound = '1';
      th.addEventListener('click', () => {
        const table = th.closest('table');
        if (!table) return;
        const tbody = table.querySelector('tbody');
        if (!tbody) return;
        const idx = Array.from(th.parentElement.children).indexOf(th);
        const nextAsc = th.dataset.order !== 'asc';

        const rows = Array.from(tbody.querySelectorAll('tr'));
        rows.sort((a, b) => {
          const aText = a.children[idx]?.textContent?.trim() || '';
          const bText = b.children[idx]?.textContent?.trim() || '';

          const parseSortableNum = (txt) => {
            const down = txt.includes('▼') || txt.includes('−') || txt.includes('-');
            const up = txt.includes('▲') || txt.includes('+');
            const base = parseFloat(txt.replace(/[^0-9.]/g, ''));
            if (Number.isNaN(base)) return NaN;
            if (down && !up) return -base;
            return base;
          };

          const aNum = parseSortableNum(aText);
          const bNum = parseSortableNum(bText);
          const bothNum = !Number.isNaN(aNum) && !Number.isNaN(bNum);

          let cmp;
          if (bothNum) cmp = aNum - bNum;
          else cmp = aText.localeCompare(bText, 'zh-CN');

          return nextAsc ? cmp : -cmp;
        });

        tbody.innerHTML = '';
        rows.forEach((r) => tbody.appendChild(r));

        th.closest('tr').querySelectorAll('th.sortable').forEach((cell) => {
          cell.dataset.order = '';
          cell.removeAttribute('aria-sort');
        });
        th.dataset.order = nextAsc ? 'asc' : 'desc';
        th.setAttribute('aria-sort', nextAsc ? 'ascending' : 'descending');
      });
    });
  }

  function renderHoverCard(code, x, y) {
    const stock = byCode(code);
    if (!stock) return;

    el.hoverCardName.textContent = stock.name;
    el.hoverCardCode.textContent = stock.code;

    const rows = [
      ['总市值', `${stock.marketCap.toFixed(1)}亿`],
      ['流通市值', `${stock.floatCap.toFixed(1)}亿`],
      ['市盈率', stock.pe.toFixed(1)],
      ['换手率', `${stock.turnover.toFixed(2)}%`],
      ['量比', stock.volumeRatio.toFixed(2)]
    ];

    el.hoverFields.innerHTML = rows
      .map(
        ([label, value]) => `<div><div class="hover-label">${label}</div><div>${value}</div></div>`
      )
      .join('');

    el.hoverTags.innerHTML = stock.concepts.map((tag) => `<span class="tag">${tag}</span>`).join('');

    const cardWidth = 300;
    const offsetX = 18;
    const offsetY = 12;
    const maxX = window.innerWidth - cardWidth - 10;
    const top = Math.min(window.innerHeight - 200, y + offsetY);
    const left = Math.min(maxX, x + offsetX);

    el.hoverCard.style.left = `${Math.max(10, left)}px`;
    el.hoverCard.style.top = `${Math.max(10, top)}px`;
    el.hoverCard.classList.add('is-visible');
  }

  function hideHoverCard() {
    el.hoverCard.classList.remove('is-visible');
    state.hoveredStock = null;
  }

  function attachStockHoverHandlers() {
    document.querySelectorAll('.hoverable-stock,[data-stock-ref]').forEach((node) => {
      if (node.dataset.boundHover === '1') return;
      node.dataset.boundHover = '1';

      const codeFromNode = () => {
        const direct = node.getAttribute('data-stock-code') || node.getAttribute('data-stock-ref');
        if (direct) return direct;
        const tr = node.closest('tr[data-stock-code]');
        return tr ? tr.getAttribute('data-stock-code') : '';
      };

      node.addEventListener('mouseenter', (evt) => {
        const code = codeFromNode();
        if (!code) return;
        state.hoveredStock = code;
        renderHoverCard(code, evt.clientX, evt.clientY);
      });

      node.addEventListener('mousemove', (evt) => {
        if (!state.hoveredStock) return;
        renderHoverCard(state.hoveredStock, evt.clientX, evt.clientY);
      });

      node.addEventListener('mouseleave', hideHoverCard);

      if (node.classList.contains('stock-chip')) {
        node.addEventListener('click', () => {
          const code = codeFromNode();
          if (!code) return;
          hideHoverCard();
          state.currentStockCode = code;
          renderPage('stock-analysis');
        });
      }
    });
  }

  function bindGlobalEvents() {
    // setInterval(pulseRealtimeBars, 2800) removed - no fake animation

    el.nav.querySelectorAll('.nav-tab').forEach((btn) => {
      btn.addEventListener('click', () => {
        const pageId = btn.getAttribute('data-page');
        if (!pageId || !PAGE_FILES[pageId]) return;
        renderPage(pageId);
      });
    });

    window.addEventListener('popstate', () => {
      const page = getInitialPage();
      renderPage(page, { pushHistory: false });
    });

    window.addEventListener('resize', () => {
      if (state.activePage === 'stock-analysis') {
        const code = state.currentStockCode;
        repaintStockCharts(code);
      }
      if (state.activePage === 'strategy-backtest') {
        const strategyId = document.getElementById('strategy-select')?.value || state.data.strategyBacktest.defaultStrategy;
        const scenario = state.data.strategyBacktest.results[strategyId] || state.data.strategyBacktest.results.default;
        const curveCanvas = document.getElementById('equity-curves');
        if (curveCanvas) drawMultiLineChart(curveCanvas, scenario.curves);
      }
      if (state.activePage === 'paper-account') {
        // paper-account resize handled internally by canvas redraw via positionDonut
      }
    });



    document.body.addEventListener('mouseleave', hideHoverCard);
  }

  async function bootstrap() {
    try {
      bindGlobalEvents();
      await loadShared();
      initMarketTape();
      const page = getInitialPage();
      await renderPage(page, { pushHistory: false });
    } catch (error) {
      el.pageHost.innerHTML = `<div class="card"><div class="card-body"><strong>初始化失败</strong><p>${escapeHtml(error.message)}</p></div></div>`;
    }
  }

  
  // ── 搜索代码 → 跳转个股分析 ──
  (function initSearchPill() {
    const pill = document.querySelector('.search-pill');
    if (!pill) return;
    
    let inputEl = null;
    
    function createInput() {
      if (inputEl) return inputEl;
      inputEl = document.createElement('input');
      inputEl.type = 'text';
      inputEl.placeholder = '输入股票代码...';
      inputEl.style.cssText = 'background:var(--surface-2);border:1px solid var(--border);color:var(--text);padding:4px 10px;border-radius:6px;width:140px;font-size:13px;outline:none';
      inputEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          const code = inputEl.value.trim();
          if (code && /^\d{6}$/.test(code)) {
            state.currentStockCode = code;
            renderPage('stock-analysis');
            // 等页面渲染完后自动查询
            setTimeout(() => {
              const si = document.getElementById('stock-input');
              if (si) { si.value = code; renderStock(code).catch(e => console.warn(e)); }
            }, 300);
          }
          destroyInput();
        }
        if (e.key === 'Escape') destroyInput();
      });
      inputEl.addEventListener('blur', () => setTimeout(destroyInput, 200));
      return inputEl;
    }
    
    function destroyInput() {
      if (inputEl) {
        inputEl.remove();
        inputEl = null;
      }
      pill.style.display = '';
    }
    
    pill.addEventListener('click', () => {
      pill.style.display = 'none';
      const inp = createInput();
      pill.parentNode.insertBefore(inp, pill.nextSibling);
      inp.focus();
    });
    
    // Ctrl+K / Cmd+K 快捷键
    document.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        pill.click();
      }
    });
  })();


bootstrap();
})();
