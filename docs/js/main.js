/* Dashboard: stat tiles, performance emphasis chart, holdings bar + table. */

let perfChart, weightsChart;
let PERF, PORT, RISK, SIGNALS;

async function init() {
  const tiles = document.getElementById("tiles");
  try {
    [PERF, PORT, RISK, SIGNALS] = await Promise.all([
      loadJSON("data/performance.json"),
      loadJSON("data/portfolio.json"),
      loadJSON("data/risk.json").catch(() => null),
      loadJSON("data/signals.json").catch(() => null),
    ]);
  } catch (err) {
    showError(tiles, err);
    return;
  }
  document.getElementById("asof").textContent = `As of ${fmtDate(PORT.as_of)}`;
  renderAll();
  onThemeChange(renderAll);
}

function renderAll() {
  applyChartDefaults();
  renderTiles();
  renderPerf();
  renderWeights();
  renderTable();
  renderMethodology();
}

function renderTiles() {
  const s = PERF.stats.portfolio || {};
  const spx = PERF.stats.spx || {};
  const el = document.getElementById("tiles");
  el.innerHTML = "";
  const defs = [
    { label: "CAGR", value: fmtPct(s.cagr), delta: spx.cagr != null ? deltaVs(s.cagr, spx.cagr) : null },
    { label: "Volatility (ann.)", value: fmtPct(s.vol), delta: { text: `target ${fmtPct(PORT.vol_target_band[0], 0)}–${fmtPct(PORT.vol_target_band[1], 1)}`, cls: "" } },
    { label: "Sharpe", value: s.sharpe != null ? s.sharpe.toFixed(2) : "–", delta: spx.sharpe != null ? { text: `SPX ${spx.sharpe.toFixed(2)}`, cls: "" } : null },
    { label: "Max drawdown", value: fmtPct(s.max_dd), delta: spx.max_dd != null ? { text: `SPX ${fmtPct(spx.max_dd)}`, cls: "" } : null },
    { label: "Positions", value: PORT.n_positions, delta: { text: `model vol ${fmtPct(PORT.model_vol)}`, cls: "" } },
  ];
  for (const d of defs) {
    const tile = document.createElement("div");
    tile.className = "tile";
    const label = document.createElement("div");
    label.className = "label";
    label.textContent = d.label;
    const value = document.createElement("div");
    value.className = "value";
    value.textContent = d.value;
    tile.append(label, value);
    if (d.delta) {
      const delta = document.createElement("div");
      delta.className = "delta " + (d.delta.cls || "");
      delta.textContent = d.delta.text;
      tile.appendChild(delta);
    }
    el.appendChild(tile);
  }
}

function deltaVs(x, bench) {
  const diff = x - bench;
  return { text: `${diff >= 0 ? "+" : ""}${(diff * 100).toFixed(1)}pp vs SPX`, cls: diff >= 0 ? "up" : "down" };
}

/* Shade the hypothetical region and mark the live start. */
const liveMarkerPlugin = {
  id: "liveMarker",
  beforeDatasetsDraw(chart) {
    const liveStart = chart.options.liveStartDate;
    if (!liveStart) return;
    const idx = chart.data.labels.indexOf(liveStart);
    if (idx < 1) return;
    const x = chart.scales.x.getPixelForValue(idx);
    const { top, bottom, left } = chart.chartArea;
    const ctx = chart.ctx;
    ctx.save();
    ctx.fillStyle = tok("--grid") + "55";
    ctx.fillRect(left, top, x - left, bottom - top);
    ctx.strokeStyle = tok("--baseline");
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke();
    ctx.fillStyle = tok("--muted");
    ctx.font = "11px system-ui, sans-serif";
    ctx.textAlign = "right";
    ctx.fillText("hypothetical", x - 6, top + 12);
    ctx.textAlign = "left";
    ctx.fillText("live", x + 6, top + 12);
    ctx.restore();
  },
};

function renderPerf() {
  const colors = { port: tok("--accent"), spx: tok("--ctx-1"), comp: tok("--ctx-2") };
  buildLegend(document.getElementById("perf-legend"), [
    { label: "Portfolio", color: colors.port },
    { label: "S&P 500", color: colors.spx },
    { label: "Nasdaq Composite", color: colors.comp },
  ]);
  const note = document.getElementById("perf-note");
  note.textContent = PERF.live_start
    ? `Shaded region is hypothetical (today's weights applied backwards). Live track record begins ${fmtDate(PERF.live_start)}.`
    : "";

  const mkDataset = (label, data, color, emphasized) => ({
    label, data,
    borderColor: color,
    backgroundColor: color,
    borderWidth: 2,
    pointRadius: 0,
    pointHoverRadius: 5,
    pointHoverBorderColor: tok("--surface"),
    pointHoverBorderWidth: 2,
    pointHoverBackgroundColor: color,
    tension: 0,
    order: emphasized ? 0 : 1,
  });

  const cfg = {
    type: "line",
    data: {
      labels: PERF.dates,
      datasets: [
        mkDataset("Portfolio", PERF.portfolio, colors.port, true),
        mkDataset("S&P 500", PERF.spx, colors.spx, false),
        mkDataset("Nasdaq Composite", PERF.comp, colors.comp, false),
      ],
    },
    options: {
      liveStartDate: PERF.live_start,
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: {
          grid: { display: false },
          border: { color: tok("--baseline") },
          ticks: {
            maxTicksLimit: 8, maxRotation: 0, autoSkip: true,
            callback(v) {
              const d = new Date(this.getLabelForValue(v) + "T00:00:00");
              return d.toLocaleDateString(undefined, { month: "short", year: "2-digit" });
            },
          },
        },
        y: {
          grid: { color: tok("--grid"), lineWidth: 1 },
          border: { display: false },
          ticks: { maxTicksLimit: 6 },
        },
      },
      plugins: {
        tooltip: {
          callbacks: {
            title: (items) => fmtDate(items[0].label),
            label: (item) => ` ${item.formattedValue}  ${item.dataset.label}`,
          },
        },
      },
    },
    plugins: [liveMarkerPlugin, crosshairPlugin],
  };
  if (perfChart) perfChart.destroy();
  perfChart = new Chart(document.getElementById("perf-chart"), cfg);
}

function renderWeights() {
  const holdings = PORT.holdings;
  const ramp = ["--ramp-650", "--ramp-550", "--ramp-450", "--ramp-350", "--ramp-250"];
  const colors = holdings.map((_, i) =>
    tok(ramp[Math.min(Math.floor(i / holdings.length * ramp.length), ramp.length - 1)]));

  document.getElementById("weights-box").style.height = `${60 + holdings.length * 34}px`;

  const cfg = {
    type: "bar",
    data: {
      labels: holdings.map(h => h.ticker),
      datasets: [{
        data: holdings.map(h => h.weight * 100),
        backgroundColor: colors,
        borderRadius: { topRight: 4, bottomRight: 4 },
        borderSkipped: "start",
        barThickness: 20,
      }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { right: 48 } },
      scales: {
        x: {
          grid: { color: tok("--grid") },
          border: { display: false },
          ticks: { callback: v => v + "%" },
          max: Math.ceil(Math.max(...holdings.map(h => h.weight * 100)) / 5) * 5,
        },
        y: {
          grid: { display: false },
          border: { color: tok("--baseline") },
          ticks: { color: tok("--ink-2"), font: { weight: 600 } },
        },
      },
      plugins: {
        tooltip: {
          callbacks: {
            label: (item) => {
              const h = holdings[item.dataIndex];
              return ` ${h.weight != null ? (h.weight * 100).toFixed(1) : "–"}%  weight · alpha ${h.alpha_score?.toFixed(2)}`;
            },
          },
        },
      },
    },
    plugins: [{
      id: "tipLabels",  /* value at the bar tip */
      afterDatasetsDraw(chart) {
        const meta = chart.getDatasetMeta(0);
        const ctx = chart.ctx;
        ctx.save();
        ctx.fillStyle = tok("--ink-2");
        ctx.font = "12px system-ui, sans-serif";
        ctx.textBaseline = "middle";
        meta.data.forEach((bar, i) => {
          ctx.fillText(`${(holdings[i].weight * 100).toFixed(1)}%`, bar.x + 8, bar.y);
        });
        ctx.restore();
      },
    }],
  };
  if (weightsChart) weightsChart.destroy();
  weightsChart = new Chart(document.getElementById("weights-chart"), cfg);
}

function scoreCell(x) {
  const td = document.createElement("td");
  td.className = "num";
  if (x == null) { td.textContent = "–"; return td; }
  td.textContent = x.toFixed(2);
  if (x > 0.5) td.classList.add("pos");
  if (x < -0.5) td.classList.add("neg");
  return td;
}

function renderTable() {
  const tbody = document.querySelector("#holdings-table tbody");
  tbody.innerHTML = "";
  for (const h of PORT.holdings) {
    const tr = document.createElement("tr");
    const name = document.createElement("td");
    const wrap = document.createElement("span");
    wrap.className = "tick";
    const label = document.createElement("span");
    label.textContent = h.ticker;
    wrap.appendChild(label);
    name.appendChild(wrap);
    tr.appendChild(name);

    const sector = document.createElement("td");
    sector.textContent = h.sector || "–";
    sector.style.color = "var(--ink-2)";
    tr.appendChild(sector);

    const weight = document.createElement("td");
    weight.className = "num";
    weight.textContent = (h.weight * 100).toFixed(1) + "%";
    tr.appendChild(weight);
    tr.appendChild(scoreCell(h.alpha_score));
    tr.appendChild(scoreCell(h.signals.value));
    tr.appendChild(scoreCell(h.signals.quality));
    tr.appendChild(scoreCell(h.signals.momentum));
    tr.appendChild(scoreCell(h.signals.short_interest));
    const pe = document.createElement("td");
    pe.className = "num";
    pe.textContent = h.raw.pe != null ? h.raw.pe.toFixed(1) : "–";
    tr.appendChild(pe);
    tbody.appendChild(tr);
  }
}

function renderMethodology() {
  const band = PORT.vol_target_band;
  document.getElementById("band-line").textContent =
    `${(band[0] * 100).toFixed(0)}–${(band[1] * 100).toFixed(0)}%`;
  if (PORT.max_weight != null) {
    document.getElementById("cap-line").textContent = `${(PORT.max_weight * 100).toFixed(0)}%`;
  }
  if (RISK && RISK.factors_explained_var) {
    const pct = RISK.factors_explained_var.map(v => (v * 100).toFixed(0) + "%").join(", ");
    document.getElementById("risk-line").textContent =
      ` The ${RISK.factors_explained_var.length} factors currently explain ${pct} of return variance.`;
  }
  if (PORT.sector_neutral === false) {
    document.getElementById("neutral-line").textContent = "ranked directly (sector-neutralization off)";
  }
  const icLine = document.getElementById("ic-line");
  if (SIGNALS && SIGNALS.momentum && SIGNALS.momentum.ic != null) {
    const mom = SIGNALS.momentum.ic.toFixed(2);
    const driven = SIGNALS.weighting && SIGNALS.weighting.startsWith("ic");
    icLine.textContent = ` Signal weights are ${driven ? "information-coefficient driven" :
      "held at their static defaults until enough point-in-time history accrues"}; ` +
      `momentum's realized information coefficient over the sample is ${mom}.`;
  }
  // Pending (seasoning) names note
  if (PORT.pending && PORT.pending.length) {
    const note = document.getElementById("holdings-note");
    const names = PORT.pending.map(p => `${p.ticker} (${p.days}/${p.needs}d)`).join(", ");
    const span = document.createElement("span");
    span.textContent = ` Seasoning — held out until they have ${PORT.pending[0].needs} days of history: ${names}.`;
    span.style.color = "var(--muted)";
    note.appendChild(span);
  }
}

init();
