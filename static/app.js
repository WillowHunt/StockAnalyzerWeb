// ── Chart ────────────────────────────────────────────────────────────────────

let currentChartType = 'candlestick';
let currentPrices    = [];
let currentSignals   = [];
let compareData      = {};   // { ticker: [{date, close}] | null (loading) }

const DARK   = '#1e1e2e';
const GRID   = '#313244';
const TEXT   = '#cdd6f4';
const ACCENT = '#26a69a';
const COMPARE_COLORS = ['#f9e2af', '#a6e3a1', '#cba6f7', '#89dceb', '#fab387'];

let visibleIndicators = {
    sma20: true, sma50: true, sma200: true,
    ema12: false, ema26: false,
    bb: true, volume: true, signals: true,
    rsi: true, macd: true, stoch: true,
    regime: true,
};

let currentRegimeData  = [];
let currentRegimeIndex = '^GSPC';

async function loadRegimeData(prices) {
    if (!prices.length || !visibleIndicators.regime) { currentRegimeData = []; return; }
    const start = prices[0].date;
    const end   = prices[prices.length - 1].date;
    try {
        const res      = await fetch(`/api/regime?index=${encodeURIComponent(currentRegimeIndex)}&start=${start}&end=${end}`);
        currentRegimeData = res.ok ? await res.json() : [];
        if (!currentRegimeData.length) showToast(`Ingen regime-data for ${currentRegimeIndex}`, true);
    } catch { currentRegimeData = []; showToast(`Kunne ikke hente regime-data`, true); }
}

async function setRegimeIndex(index, btn) {
    currentRegimeIndex = index;
    document.querySelectorAll('.regime-idx-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    if (visibleIndicators.regime && currentPrices.length) {
        await loadRegimeData(currentPrices);
        const saved = document.getElementById('price-chart')?._fullLayout?.xaxis?.range?.slice() ?? null;
        renderCharts(currentPrices, currentSignals, saved);
        renderTechnicalAnalysis();
    }
}

function buildRegimeShapes() {
    if (!visibleIndicators.regime || !currentRegimeData.length) return [];
    return currentRegimeData.map(seg => ({
        type: 'rect', xref: 'x', yref: 'paper',
        x0: seg.start, x1: seg.end, y0: 0, y1: 1,
        fillcolor: seg.is_bull ? 'rgba(0,180,0,0.07)' : 'rgba(220,0,0,0.07)',
        line: { width: 0 }, layer: 'below',
    }));
}

function setChartType(btn, type) {
    document.querySelectorAll('.chart-type-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentChartType = type;
    if (currentPrices.length) {
        const el = document.getElementById('price-chart');
        const savedRange = el._fullLayout?.xaxis?.range?.slice() ?? null;
        renderCharts(currentPrices, currentSignals, savedRange);
    }
}

async function loadChart(ticker, limit) {
    const url = `/api/stocks/${ticker}/prices` + (limit ? `?limit=${limit}` : '');
    const [pricesRes, signalsRes] = await Promise.all([
        fetch(url),
        fetch(`/api/stocks/${ticker}/signals`).catch(() => null),
    ]);

    if (!pricesRes.ok) {
        document.getElementById('price-chart').innerHTML =
            '<p style="color:var(--muted);padding:40px;text-align:center">Ingen kursdata — klik "Opdater data"</p>';
        return;
    }

    const rawPrices = await pricesRes.json();
    const prices  = rawPrices.filter(p => p.close != null);
    const signals = (signalsRes && signalsRes.ok) ? await signalsRes.json() : [];
    currentPrices  = prices;
    currentSignals = signals;
    await loadRegimeData(prices);
    renderCharts(prices, signals);
    renderTechnicalAnalysis();
}

function reloadChart(ticker, limit) {
    const parsed = parseInt(limit) || 0;
    const trigger = document.getElementById('chart-trigger');
    if (trigger) trigger.dataset.limit = parsed;
    loadChart(ticker, parsed);
}

function renderCharts(prices, signals, preserveRange = null) {
    if (!prices.length) return;
    const dates  = prices.map(p => p.date);
    const config = { responsive: true, displayModeBar: false };

    const { xRange, yRange } = computeRanges(dates, preserveRange, prices);

    Plotly.newPlot('price-chart', buildPriceTraces(prices, signals, dates, xRange),
                   buildPriceLayout(xRange, yRange), config);

    const subcharts = [
        { key: 'rsi',   id: 'rsi-chart',   traces: () => buildRsiTraces(prices, dates),   title: 'RSI'   },
        { key: 'macd',  id: 'macd-chart',  traces: () => buildMacdTraces(prices, dates),  title: 'MACD'  },
        { key: 'stoch', id: 'stoch-chart', traces: () => buildStochTraces(prices, dates), title: 'Stoch' },
    ];
    const lastVisible = [...subcharts].reverse().find(s => visibleIndicators[s.key]);
    for (const s of subcharts) {
        const el = document.getElementById(s.id);
        if (!visibleIndicators[s.key]) { el.style.display = 'none'; continue; }
        el.style.display = '';
        Plotly.newPlot(s.id, s.traces(), buildSubLayout(xRange, s.title, s === lastVisible), config);
    }

    attachChartSync(prices, signals);
}

// ── Range helpers ─────────────────────────────────────────────────────────────

function computeRanges(dates, preserveRange, prices) {
    const lastDate    = new Date(dates[dates.length - 1]);
    const defaultFrom = new Date(lastDate);
    defaultFrom.setMonth(defaultFrom.getMonth() - 3);
    const fmt    = d => d.toISOString().split('T')[0];
    const xRange = preserveRange ?? [fmt(defaultFrom), fmt(lastDate)];

    // Clip left edge to first available data — prevents empty space when range exceeds data
    if (xRange[0] < dates[0]) xRange[0] = dates[0];

    const visible = prices.filter(p => p.date >= xRange[0] && p.date <= xRange[1]);
    let yRange;
    if (visible.length > 0) {
        const vals = [];
        for (const p of visible) {
            for (const k of ['high', 'low', 'close', 'sma_20', 'sma_50', 'sma_200', 'bb_upper', 'bb_lower']) {
                if (p[k] != null) vals.push(p[k]);
            }
        }
        if (vals.length) {
            const span = Math.max(...vals) - Math.min(...vals);
            const pad  = span * 0.06;
            yRange = [Math.min(...vals) - pad, Math.max(...vals) + pad];
        }
    }
    return { xRange, yRange };
}

// ── Layouts ───────────────────────────────────────────────────────────────────

function buildPriceLayout(xRange, yRange) {
    const hasCompare = Object.values(compareData).some(d => d && d.length);
    const rangeselector = {
        buttons: [
            { count: 3,  label: '3M',  step: 'month', stepmode: 'backward' },
            { count: 9,  label: '9M',  step: 'month', stepmode: 'backward' },
            { count: 1,  label: '1Y',  step: 'year',  stepmode: 'backward' },
            { count: 2,  label: '2Y',  step: 'year',  stepmode: 'backward' },
            { count: 3,  label: '3Y',  step: 'year',  stepmode: 'backward' },
            { count: 5,  label: '5Y',  step: 'year',  stepmode: 'backward' },
            { step: 'all', label: 'Alt' },
        ],
        bgcolor: '#313244', activecolor: ACCENT,
        bordercolor: '#45475a', borderwidth: 1,
        font: { color: TEXT, size: 11 },
        x: 0, y: 1.06,
    };
    return {
        paper_bgcolor: DARK, plot_bgcolor: DARK,
        font: { color: TEXT, size: 11 },
        margin: { l: 60, r: 16, t: 48, b: 0 },
        height: 340,
        xaxis: {
            gridcolor: GRID, rangeslider: { visible: false },
            range: xRange, rangeselector, showticklabels: false,
        },
        yaxis: hasCompare ? {
            gridcolor: GRID, autorange: true,
            title: { text: '% afkast', font: { size: 10 } },
            ticksuffix: '%', zeroline: true, zerolinecolor: GRID,
        } : {
            gridcolor: GRID, rangemode: 'normal', range: yRange,
            domain: (!hasCompare && visibleIndicators.volume) ? [0.24, 1] : [0, 1],
        },
        ...(!hasCompare && visibleIndicators.volume ? {
            yaxis2: {
                domain: [0, 0.21], showgrid: false,
                showticklabels: false, fixedrange: true, autorange: true,
            },
        } : {}),
        legend: { bgcolor: 'rgba(0,0,0,0)', bordercolor: GRID, x: 0, y: 1, font: { size: 10 } },
        showlegend: true,
        shapes: buildRegimeShapes(),
    };
}

function buildSubLayout(xRange, title, showXLabels) {
    return {
        paper_bgcolor: DARK, plot_bgcolor: DARK,
        font: { color: TEXT, size: 11 },
        margin: { l: 60, r: 16, t: 4, b: showXLabels ? 30 : 0 },
        height: 110,
        xaxis: {
            gridcolor: GRID, rangeslider: { visible: false },
            range: xRange, showticklabels: showXLabels,
            tickfont: { size: 10 },
        },
        yaxis: {
            gridcolor: GRID,
            title: { text: title, font: { size: 10 } },
            ...(['RSI', 'Stoch'].includes(title) ? { range: [0, 100] } : {}),
        },
        showlegend: false,
    };
}

// ── X-axis sync + Y auto-scale ────────────────────────────────────────────────

function attachChartSync(prices, signals) {
    const priceEl = document.getElementById('price-chart');
    if (!priceEl) return;
    priceEl.removeAllListeners?.('plotly_relayout');

    let busy = false;

    function scalePriceY(x0, x1) {
        const d0      = x0 ? x0.slice(0, 10) : null;
        const d1      = x1 ? x1.slice(0, 10) : null;
        const visible = (d0 && d1) ? prices.filter(p => p.date >= d0 && p.date <= d1) : prices;
        if (visible.length < 2) return;
        const vals = [];
        for (const p of visible) {
            for (const k of ['high', 'low', 'close', 'sma_20', 'sma_50', 'sma_200', 'bb_upper', 'bb_lower']) {
                if (p[k] != null) vals.push(p[k]);
            }
        }
        if (!vals.length) return;
        const span = Math.max(...vals) - Math.min(...vals);
        const pad  = span * 0.05;
        Plotly.relayout('price-chart', { 'yaxis.range': [Math.min(...vals) - pad, Math.max(...vals) + pad] });
    }

    priceEl.on('plotly_relayout', function (ev) {
        if (busy) return;
        const keys      = Object.keys(ev);
        const isXChange = keys.some(k => k.startsWith('xaxis.range') || k === 'xaxis.autorange');
        if (!isXChange) return;

        const hasCompare = Object.values(compareData).some(d => d && d.length);
        const isAuto     = !!ev['xaxis.autorange'];
        let x0 = isAuto ? prices[0].date                 : ev['xaxis.range[0]'];
        let x1 = isAuto ? prices[prices.length - 1].date : ev['xaxis.range[1]'];

        // Clip left edge — prevents empty chart space when range exceeds available data
        const clipped = x0 < prices[0].date;
        if (clipped) x0 = prices[0].date;

        busy = true;
        const promises  = [];
        const xUpdate   = { 'xaxis.range[0]': x0, 'xaxis.range[1]': x1 };

        // Sync visible sub-charts
        for (const [key, id] of [['rsi','rsi-chart'],['macd','macd-chart'],['stoch','stoch-chart']]) {
            if (visibleIndicators[key]) promises.push(Plotly.relayout(id, xUpdate));
        }

        if (hasCompare) {
            // Re-normalize from new left edge, update price chart via react
            const dates  = prices.map(p => p.date);
            const traces = buildPriceTraces(prices, signals, dates, [x0, x1]);
            const layout = buildPriceLayout([x0, x1], null);
            promises.push(Plotly.react('price-chart', traces, layout));
        } else {
            scalePriceY(x0, x1);
            // Update price chart range when autorange padding was fixed or left edge was clipped
            if (isAuto || clipped) promises.push(Plotly.relayout('price-chart', xUpdate));
        }

        Promise.all(promises).finally(() => { busy = false; });
    });
}

// ── Traces ────────────────────────────────────────────────────────────────────

function buildPriceTraces(prices, signals, dates, xRange) {
    const hasCompare = Object.values(compareData).some(d => d && d.length);
    if (hasCompare) return buildCompareTraces(prices, dates, xRange);

    const traces = [];

    if (currentChartType === 'candlestick') {
        traces.push({
            type: 'candlestick', x: dates,
            open: prices.map(p => p.open), high: prices.map(p => p.high),
            low:  prices.map(p => p.low),  close: prices.map(p => p.close),
            name: 'Kurs', showlegend: false,
            increasing: { line: { color: '#26a69a' }, fillcolor: '#26a69a' },
            decreasing: { line: { color: '#ef5350' }, fillcolor: '#ef5350' },
        });
    } else if (currentChartType === 'ohlc') {
        traces.push({
            type: 'ohlc', x: dates,
            open: prices.map(p => p.open), high: prices.map(p => p.high),
            low:  prices.map(p => p.low),  close: prices.map(p => p.close),
            name: 'Kurs', showlegend: false,
            increasing: { line: { color: '#26a69a' } },
            decreasing: { line: { color: '#ef5350' } },
        });
    } else if (currentChartType === 'line') {
        traces.push({
            type: 'scatter', mode: 'lines', x: dates, y: prices.map(p => p.close),
            name: 'Luk', showlegend: false, line: { color: '#89b4fa', width: 1.5 },
        });
    } else {
        traces.push({
            type: 'scatter', mode: 'lines', x: dates, y: prices.map(p => p.close),
            name: 'Luk', showlegend: false,
            line: { color: '#89b4fa', width: 1.5 },
            fill: 'tonexty', fillcolor: 'rgba(137,180,250,0.12)',
        });
    }

    // Bollinger Bands fill
    if (visibleIndicators.bb) {
        traces.push({
            type: 'scatter', mode: 'lines', x: dates, y: prices.map(p => p.bb_upper),
            name: 'BB Upper', showlegend: false,
            line: { color: 'rgba(100,100,150,0.4)', width: 1 },
        });
        traces.push({
            type: 'scatter', mode: 'lines', x: dates, y: prices.map(p => p.bb_lower),
            name: 'BB', line: { color: 'rgba(100,100,150,0.4)', width: 1 },
            fill: 'tonexty', fillcolor: 'rgba(100,100,150,0.06)',
        });
    }

    // SMA lines
    for (const { key, indKey, color, label, width } of [
        { key: 'sma_20',  indKey: 'sma20',  color: '#ff9800', label: 'SMA 20',  width: 1   },
        { key: 'sma_50',  indKey: 'sma50',  color: '#00e5ff', label: 'SMA 50',  width: 1   },
        { key: 'sma_200', indKey: 'sma200', color: '#e040fb', label: 'SMA 200', width: 1.5 },
        { key: 'ema_12',  indKey: 'ema12',  color: '#a6e3a1', label: 'EMA 12',  width: 1   },
        { key: 'ema_26',  indKey: 'ema26',  color: '#fab387', label: 'EMA 26',  width: 1   },
    ]) {
        if (!visibleIndicators[indKey]) continue;
        traces.push({
            type: 'scatter', mode: 'lines',
            x: dates, y: prices.map(p => p[key]),
            name: label, line: { color, width },
        });
    }

    // Volume bars (bottom panel, yaxis2)
    if (visibleIndicators.volume) {
        traces.push({
            type: 'bar', x: dates, y: prices.map(p => p.volume),
            yaxis: 'y2', name: 'Volumen', showlegend: false,
            marker: {
                color: prices.map(p =>
                    (p.close ?? 0) >= (p.open ?? 0)
                        ? 'rgba(38,166,154,0.45)'
                        : 'rgba(239,83,80,0.45)'
                ),
            },
        });
    }

    // Signal markers
    if (visibleIndicators.signals) {
        const buys  = signals.filter(s => s.signal_type === 'BUY');
        const sells = signals.filter(s => s.signal_type === 'SELL');
        if (buys.length) {
            traces.push({
                type: 'scatter', mode: 'markers',
                x: buys.map(s => s.date), y: buys.map(s => s.price),
                name: 'BUY',
                marker: { symbol: 'triangle-up', size: 9, color: '#26a69a', line: { width: 0 } },
            });
        }
        if (sells.length) {
            traces.push({
                type: 'scatter', mode: 'markers',
                x: sells.map(s => s.date), y: sells.map(s => s.price),
                name: 'SELL',
                marker: { symbol: 'triangle-down', size: 9, color: '#ef5350', line: { width: 0 } },
            });
        }
    }

    return traces;
}

function buildCompareTraces(prices, allDates, xRange) {
    const fromDate = (xRange ? xRange[0] : allDates[0]).slice(0, 10);

    function normalize(series) {
        const baseline = series.find(p => p.date >= fromDate);
        if (!baseline || !baseline.close) return { x: [], y: [] };
        const base     = baseline.close;
        const filtered = series.filter(p => p.date >= fromDate);
        return {
            x: filtered.map(p => p.date),
            y: filtered.map(p => p.close != null ? +((p.close / base - 1) * 100).toFixed(3) : null),
        };
    }

    const traces = [];

    // Main stock as a line (normalized)
    const mainTicker = document.getElementById('chart-trigger')?.dataset.ticker || 'Aktie';
    const mainSeries = prices.map(p => ({ date: p.date, close: p.close }));
    const main       = normalize(mainSeries);
    traces.push({
        type: 'scatter', mode: 'lines',
        x: main.x, y: main.y, name: mainTicker,
        line: { color: '#89b4fa', width: 2 }, connectgaps: false,
    });

    // Comparison tickers
    Object.entries(compareData).forEach(([ticker, data], i) => {
        if (!data || !data.length) return;
        const norm = normalize(data);
        traces.push({
            type: 'scatter', mode: 'lines',
            x: norm.x, y: norm.y, name: ticker,
            line: { color: COMPARE_COLORS[i % COMPARE_COLORS.length], width: 1.5 },
            connectgaps: false,
        });
    });

    return traces;
}

function buildRsiTraces(prices, dates) {
    return [
        {
            type: 'scatter', mode: 'lines',
            x: dates, y: prices.map(p => p.rsi_14),
            name: 'RSI 14', line: { color: '#f38ba8', width: 1.5 },
        },
        {
            type: 'scatter', mode: 'lines', x: dates, y: dates.map(() => 70),
            name: '70', line: { color: '#ef5350', width: 1, dash: 'dot' },
        },
        {
            type: 'scatter', mode: 'lines', x: dates, y: dates.map(() => 30),
            name: '30', line: { color: '#26a69a', width: 1, dash: 'dot' },
        },
    ];
}

function buildMacdTraces(prices, dates) {
    return [
        {
            type: 'bar', x: dates, y: prices.map(p => p.macd_hist),
            name: 'MACD hist',
            marker: { color: prices.map(p => (p.macd_hist || 0) >= 0 ? 'rgba(38,166,154,0.6)' : 'rgba(239,83,80,0.6)') },
        },
        {
            type: 'scatter', mode: 'lines',
            x: dates, y: prices.map(p => p.macd),
            name: 'MACD', line: { color: '#89b4fa', width: 1.5 },
        },
        {
            type: 'scatter', mode: 'lines',
            x: dates, y: prices.map(p => p.macd_signal),
            name: 'Signal', line: { color: '#f9e2af', width: 1 },
        },
    ];
}

function buildStochTraces(prices, dates) {
    return [
        {
            type: 'scatter', mode: 'lines',
            x: dates, y: prices.map(p => p.stoch_k),
            name: '%K', line: { color: '#89b4fa', width: 1.5 },
        },
        {
            type: 'scatter', mode: 'lines',
            x: dates, y: prices.map(p => p.stoch_d),
            name: '%D', line: { color: '#f9e2af', width: 1, dash: 'dot' },
        },
        {
            type: 'scatter', mode: 'lines', x: dates, y: dates.map(() => 80),
            name: '80', line: { color: '#ef5350', width: 1, dash: 'dot' }, showlegend: false,
        },
        {
            type: 'scatter', mode: 'lines', x: dates, y: dates.map(() => 20),
            name: '20', line: { color: '#26a69a', width: 1, dash: 'dot' }, showlegend: false,
        },
    ];
}

// ── Comparison ────────────────────────────────────────────────────────────────

async function addCompareTicker(ticker) {
    ticker = ticker.trim().toUpperCase();
    if (!ticker || compareData.hasOwnProperty(ticker)) return;

    compareData[ticker] = null;   // loading placeholder
    renderCompareChips();
    showToast(`Henter ${ticker}…`);

    try {
        const res  = await fetch(`/api/compare?tickers=${encodeURIComponent(ticker)}`);
        const data = await res.json();
        if (data[ticker] && data[ticker].length) {
            compareData[ticker] = data[ticker];
        } else {
            delete compareData[ticker];
            showToast(`Ingen data for ${ticker}`, true);
            renderCompareChips();
            return;
        }
    } catch {
        delete compareData[ticker];
        showToast(`Fejl ved hentning af ${ticker}`, true);
        renderCompareChips();
        return;
    }

    renderCompareChips();
    if (currentPrices.length) {
        const saved = document.getElementById('price-chart')._fullLayout?.xaxis?.range?.slice() ?? null;
        renderCharts(currentPrices, currentSignals, saved);
    }
}

function removeCompareTicker(ticker) {
    delete compareData[ticker];
    renderCompareChips();
    if (currentPrices.length) {
        let saved = document.getElementById('price-chart')?._fullLayout?.xaxis?.range?.slice() ?? null;
        if (saved && currentPrices.length) {
            // Clip to available data — comparison tickers may have extended the range beyond our data
            const first = currentPrices[0].date;
            const last  = currentPrices[currentPrices.length - 1].date;
            if (saved[0] < first) saved[0] = first;
            if (saved[1] > last)  saved[1] = last;
        }
        renderCharts(currentPrices, currentSignals, saved);
    }
}

function renderCompareChips() {
    const container = document.getElementById('compare-chips');
    if (!container) return;
    container.innerHTML = Object.entries(compareData).map(([t, d], i) => {
        const color   = COMPARE_COLORS[i % COMPARE_COLORS.length];
        const loading = d === null;
        return `<span class="compare-chip" style="border-color:${color};color:${color}">
            ${loading ? '…' : t}
            <button class="compare-chip-remove" onclick="removeCompareTicker('${t}')" title="Fjern">×</button>
        </span>`;
    }).join('');
}

function handleCompareInput(event) {
    if (event.key !== 'Enter') return;
    const input  = event.target;
    const ticker = input.value.trim();
    input.value  = '';
    if (ticker) addCompareTicker(ticker);
}

// ── Indicator toggles ─────────────────────────────────────────────────────────

function toggleIndicator(key) {
    visibleIndicators[key] = !visibleIndicators[key];
    document.querySelectorAll(`.ind-btn[data-indicator="${key}"]`).forEach(btn =>
        btn.classList.toggle('active', visibleIndicators[key])
    );

    if (key === 'regime') {
        const picker = document.getElementById('regime-index-picker');
        if (picker) picker.style.display = visibleIndicators.regime ? '' : 'none';
        if (visibleIndicators.regime && !currentRegimeData.length && currentPrices.length) {
            loadRegimeData(currentPrices).then(() => {
                const saved = document.getElementById('price-chart')?._fullLayout?.xaxis?.range?.slice() ?? null;
                renderCharts(currentPrices, currentSignals, saved);
                renderTechnicalAnalysis();
            });
            return;
        }
        renderTechnicalAnalysis();
    }

    if (currentPrices.length) {
        const saved = document.getElementById('price-chart')?._fullLayout?.xaxis?.range?.slice() ?? null;
        renderCharts(currentPrices, currentSignals, saved);
    }
}

function syncIndicatorButtons() {
    document.querySelectorAll('.ind-btn[data-indicator]').forEach(btn => {
        const key = btn.dataset.indicator;
        btn.classList.toggle('active', visibleIndicators[key] !== false);
    });
    const picker = document.getElementById('regime-index-picker');
    if (picker) picker.style.display = visibleIndicators.regime ? '' : 'none';
}

// ── Regime-aware technical analysis ──────────────────────────────────────────

function computeTechnicalAnalysis() {
    if (!currentPrices.length || !currentRegimeData.length) return null;

    const last   = currentRegimeData[currentRegimeData.length - 1];
    const regime = last.is_bull ? 'bull' : 'bear';
    const p      = currentPrices[currentPrices.length - 1];
    const signals = [];

    if (regime === 'bull') {
        // Trend-following: virker bedst i stigende markeder
        if (p.macd_hist != null) {
            signals.push({ name: 'MACD', verdict: p.macd_hist > 0 ? 'BUY' : 'SELL' });
        }
        if (p.ema_12 != null && p.ema_26 != null) {
            signals.push({ name: 'EMA-kryds', verdict: p.ema_12 > p.ema_26 ? 'BUY' : 'SELL' });
        }
        if (p.close != null && p.sma_50 != null && p.sma_200 != null) {
            let verdict;
            if (p.close > p.sma_50 && p.sma_50 > p.sma_200)  verdict = 'BUY';
            else if (p.close < p.sma_200)                      verdict = 'SELL';
            else                                               verdict = 'HOLD';
            signals.push({ name: 'SMA-trend', verdict });
        }
    } else {
        // Mean-reversion/defensiv: virker bedst i faldende markeder
        if (p.rsi_14 != null) {
            let verdict;
            if (p.rsi_14 < 35)      verdict = 'BUY';
            else if (p.rsi_14 > 65) verdict = 'SELL';
            else                    verdict = 'HOLD';
            signals.push({ name: 'RSI', verdict });
        }
        if (p.close != null && p.bb_lower != null && p.bb_upper != null) {
            let verdict;
            if (p.close <= p.bb_lower)      verdict = 'BUY';
            else if (p.close >= p.bb_upper) verdict = 'SELL';
            else                            verdict = 'HOLD';
            signals.push({ name: 'Bollinger', verdict });
        }
        if (p.stoch_k != null) {
            let verdict;
            if (p.stoch_k < 25)      verdict = 'BUY';
            else if (p.stoch_k > 75) verdict = 'SELL';
            else                     verdict = 'HOLD';
            signals.push({ name: 'Stokastisk', verdict });
        }
    }

    if (!signals.length) return null;

    const buyN  = signals.filter(s => s.verdict === 'BUY').length;
    const sellN = signals.filter(s => s.verdict === 'SELL').length;
    let verdict;
    if (buyN > sellN && buyN > signals.length - buyN - sellN)       verdict = 'BUY';
    else if (sellN > buyN && sellN > signals.length - buyN - sellN) verdict = 'SELL';
    else                                                             verdict = 'HOLD';

    return { regime, verdict, signals };
}

function renderTechnicalAnalysis() {
    const box = document.getElementById('technical-box');
    if (!box) return;
    if (!currentPrices.length) { box.innerHTML = ''; return; }

    const result = computeTechnicalAnalysis();
    if (!result) { box.innerHTML = '<span class="analyst-loading">Ingen regime-data</span>'; return; }

    const { regime, verdict, signals } = result;
    const vColor   = { BUY: '#26a69a', HOLD: '#ffa726', SELL: '#ef5350' }[verdict];
    const vLabel   = { BUY: 'KØB', HOLD: 'HOLD', SELL: 'SÆLG' }[verdict];
    const rColor   = regime === 'bull' ? '#26a69a' : '#ef5350';
    const rLabel   = regime === 'bull' ? 'Bull' : 'Bear';

    const sigsHtml = signals.map(s => {
        const c = { BUY: '#26a69a', HOLD: '#ffa726', SELL: '#ef5350' }[s.verdict];
        const l = { BUY: 'Køb', HOLD: 'Hold', SELL: 'Sælg' }[s.verdict];
        return `<span class="tech-sig" style="color:${c}">${s.name}: ${l}</span>`;
    }).join('');

    box.innerHTML = `
        <div class="tech-top">
            <span class="tech-regime" style="color:${rColor}">${rLabel}</span>
            <span class="tech-label">marked</span>
            <span class="tech-verdict" style="color:${vColor}">${vLabel}</span>
        </div>
        <div class="tech-signals">${sigsHtml}</div>`;
}

// ── Analyst recommendations ───────────────────────────────────────────────────

async function loadRecommendations(ticker) {
    const box = document.getElementById('analyst-box');
    if (!box) return;
    box.innerHTML = '<span class="analyst-loading">Henter analyser…</span>';
    try {
        const res  = await fetch(`/api/stocks/${ticker}/recommendations`);
        const data = res.ok ? await res.json() : null;
        renderRecommendations(box, data);
    } catch {
        box.innerHTML = '';
    }
}

function renderRecommendations(box, d) {
    if (!d || d.total === 0) { box.innerHTML = ''; return; }

    const consensusColor = {
        'Stærkt Køb': '#26a69a', 'Køb': '#66bb6a',
        'Hold': '#ffa726',
        'Sælg': '#ef5350', 'Stærkt Sælg': '#b71c1c',
    };
    const color = consensusColor[d.consensus] || '#888';

    const buyN  = d.strong_buy + d.buy;
    const sellN = d.sell + d.strong_sell;
    const total = d.total;
    const pct   = v => total ? Math.round(v / total * 100) : 0;

    box.innerHTML = `
        <div class="analyst-consensus" style="color:${color}">${d.consensus}</div>
        <div class="analyst-bar">
            <div class="analyst-seg analyst-buy"  style="width:${pct(buyN)}%"  title="${buyN} Køb"></div>
            <div class="analyst-seg analyst-hold" style="width:${pct(d.hold)}%" title="${d.hold} Hold"></div>
            <div class="analyst-seg analyst-sell" style="width:${pct(sellN)}%" title="${sellN} Sælg"></div>
        </div>
        <div class="analyst-counts">
            <span class="ac-buy">${buyN} køb</span>
            <span class="ac-hold">${d.hold} hold</span>
            <span class="ac-sell">${sellN} sælg</span>
            <span class="ac-total">${total} analytikere</span>
        </div>`;
}

// ── HTMX afterSwap — start chart after stock view is injected ────────────────

document.body.addEventListener('htmx:afterSwap', function (evt) {
    if (evt.detail.target.id !== 'main') return;
    const trigger = document.getElementById('chart-trigger');
    if (!trigger) return;
    const ticker = trigger.dataset.ticker;
    const limit  = parseInt(trigger.dataset.limit);   // 0 = all data
    compareData  = {};
    renderCompareChips();
    syncIndicatorButtons();
    loadChart(ticker, limit);
    loadRecommendations(ticker);
    htmx.ajax('GET', `/partials/signals/${ticker}`, { target: '#tab-content', swap: 'innerHTML' });
});

// ── Sidebar ───────────────────────────────────────────────────────────────────

function filterStocks(query) {
    const q = query.toLowerCase();
    document.querySelectorAll('.stock-item').forEach(el => {
        const match = el.dataset.ticker.toLowerCase().includes(q) ||
                      (el.dataset.name || '').includes(q);
        el.style.display = match ? '' : 'none';
    });
}

function setActive(el) {
    document.querySelectorAll('.stock-item').forEach(i => i.classList.remove('active'));
    el.classList.add('active');
}

// ── Tabs ──────────────────────────────────────────────────────────────────────

function setTab(el) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    el.classList.add('active');
}

function reloadBacktest(ticker, holdDays) {
    const url = `/partials/backtest/${ticker}?hold_days=${holdDays}`;
    htmx.ajax('GET', url, { target: '#tab-content', swap: 'innerHTML' });
}

// ── Actions ───────────────────────────────────────────────────────────────────

function handleFetch(event, ticker) {
    if (event.detail.successful) {
        const data = JSON.parse(event.detail.xhr.responseText);
        showToast(`Hentet ${data.new_rows} nye rækker for ${ticker}`);
        const limit = parseInt(document.getElementById('chart-trigger')?.dataset.limit) || 0;
        loadChart(ticker, limit);
    } else {
        showToast('Fejl ved datahentning', true);
    }
}

function handleSignals(event, ticker) {
    if (event.detail.successful) {
        const data = JSON.parse(event.detail.xhr.responseText);
        showToast(`${data.signals_generated} signaler genereret`);
        const limit = parseInt(document.getElementById('chart-trigger')?.dataset.limit) || 0;
        loadChart(ticker, limit);
        htmx.ajax('GET', `/partials/signals/${ticker}`, { target: '#tab-content', swap: 'innerHTML' });
    } else {
        showToast('Fejl ved signal-generering', true);
    }
}

async function fetchTickerNews(ticker) {
    showToast('Henter nyheder...');
    try {
        const res  = await fetch(`/api/stocks/${ticker}/news/fetch`, { method: 'POST' });
        const data = await res.json();
        showToast(`${data.new_articles} nye artikler hentet`);
        htmx.ajax('GET', `/partials/news/${ticker}`, { target: '#tab-content', swap: 'innerHTML' });
    } catch {
        showToast('Fejl ved nyhedshentning', true);
    }
}

// ── Fetch dialog ──────────────────────────────────────────────────────────────

function showFetchDialog() {
    document.getElementById('fetch-dialog').style.display = 'flex';
    document.getElementById('fetch-ticker').focus();
}

function hideFetchDialog() {
    document.getElementById('fetch-dialog').style.display = 'none';
    document.getElementById('fetch-status').textContent = '';
}

async function fetchNewStock() {
    const ticker = document.getElementById('fetch-ticker').value.trim().toUpperCase();
    const period = document.getElementById('fetch-period').value;
    const status = document.getElementById('fetch-status');

    if (!ticker) return;
    status.textContent = 'Henter data...';

    try {
        const res  = await fetch(`/api/stocks/${ticker}/fetch?period=${period}`, { method: 'POST' });
        const data = await res.json();
        if (!res.ok) {
            status.textContent = data.detail || 'Fejl';
            return;
        }
        status.textContent = `Hentet ${data.new_rows} rækker for ${ticker}`;
        setTimeout(() => {
            hideFetchDialog();
            location.reload();
        }, 800);
    } catch {
        status.textContent = 'Netværksfejl';
    }
}

document.addEventListener('keydown', e => {
    if (e.key === 'Escape') hideFetchDialog();
});

// ── Toast ─────────────────────────────────────────────────────────────────────

let toastTimer;
function showToast(msg, isError = false) {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.style.borderColor = isError ? 'var(--red)' : 'var(--accent)';
    el.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('show'), 3000);
}
