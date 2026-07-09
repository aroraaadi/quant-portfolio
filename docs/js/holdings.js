/* Holdings page: latest-rebalance change table + stacked composition per rebalance. */

let compChart, HIST;

async function init() {
  const table = document.querySelector("#changes-table tbody");
  try {
    HIST = await loadJSON("data/holdings_history.json");
  } catch (err) {
    showError(document.querySelector(".card"), err);
    return;
  }
  HIST.sort((a, b) => a.date.localeCompare(b.date));
  document.getElementById("asof").textContent =
    `As of ${fmtDate(HIST[HIST.length - 1].date)}`;
  renderAll();
  onThemeChange(renderAll);
}

function renderAll() {
  applyChartDefaults();
  renderChanges();
  renderComposition();
}

function renderChanges() {
  const latest = HIST[HIST.length - 1];
  const prev = HIST.length > 1 ? HIST[HIST.length - 2] : null;
  const tickers = new Set([...Object.keys(latest.weights), ...(prev ? Object.keys(prev.weights) : [])]);
  const rows = [...tickers].map(t => ({
    ticker: t,
    now: latest.weights[t] || 0,
    before: prev ? (prev.weights[t] || 0) : null,
  })).sort((a, b) => b.now - a.now);

  const tbody = document.querySelector("#changes-table tbody");
  tbody.innerHTML = "";
  for (const r of rows) {
    const tr = document.createElement("tr");
    const name = document.createElement("td");
    const wrap = document.createElement("span");
    wrap.className = "tick";
    const dot = document.createElement("span");
    dot.className = "dot";
    dot.style.background = slotColor(r.ticker);
    const label = document.createElement("span");
    label.textContent = r.ticker;
    wrap.append(dot, label);
    name.appendChild(wrap);

    const now = document.createElement("td");
    now.className = "num";
    now.textContent = (r.now * 100).toFixed(1) + "%";
    const before = document.createElement("td");
    before.className = "num";
    before.textContent = r.before == null ? "–" : (r.before * 100).toFixed(1) + "%";
    const change = document.createElement("td");
    change.className = "num";
    if (r.before == null) {
      change.textContent = "new";
      change.classList.add("pos");
    } else {
      const d = (r.now - r.before) * 100;
      change.textContent = `${d >= 0 ? "+" : ""}${d.toFixed(1)}pp`;
      if (d > 0.05) change.classList.add("pos");
      if (d < -0.05) change.classList.add("neg");
    }
    tr.append(name, now, before, change);
    tbody.appendChild(tr);
  }
  const note = document.getElementById("turnover-note");
  note.textContent = `Rebalanced ${fmtDate(latest.date)} — one-way turnover ` +
    `${(latest.turnover * 100).toFixed(0)}%` + (latest.note ? ` (${latest.note})` : "");
}

/* Fixed slot per ticker by order of first appearance across all history. */
let slotMap = null;
function buildSlotMap() {
  slotMap = new Map();
  for (const entry of HIST) {
    const sorted = Object.entries(entry.weights).sort((a, b) => b[1] - a[1]);
    for (const [t] of sorted) {
      if (!slotMap.has(t) && slotMap.size < SLOT_VARS.length) slotMap.set(t, slotMap.size);
    }
  }
}
function slotColor(ticker) {
  if (!slotMap) buildSlotMap();
  const slot = slotMap.get(ticker);
  return slot == null ? tok("--muted") : tok(SLOT_VARS[slot]);
}

function renderComposition() {
  if (!slotMap) buildSlotMap();
  const namedTickers = [...slotMap.keys()];
  const labels = HIST.map(e => e.date);
  const hasOther = HIST.some(e =>
    Object.keys(e.weights).some(t => !slotMap.has(t)));

  const datasets = namedTickers.map(t => ({
    label: t,
    data: HIST.map(e => (e.weights[t] || 0) * 100),
    backgroundColor: slotColor(t),
    borderColor: tok("--surface"),
    borderWidth: 1,           /* the 2px surface gap between segments */
    barThickness: 22,
    borderRadius: 2,
  }));
  if (hasOther) {
    datasets.push({
      label: "Other",
      data: HIST.map(e => Object.entries(e.weights)
        .filter(([t]) => !slotMap.has(t))
        .reduce((s, [, w]) => s + w, 0) * 100),
      backgroundColor: tok("--muted"),
      borderColor: tok("--surface"),
      borderWidth: 1,
      barThickness: 22,
    });
  }

  buildLegend(document.getElementById("comp-legend"),
    datasets.map(d => ({ label: d.label, color: d.backgroundColor, shape: "rect" })));

  document.getElementById("comp-box").style.height = `${90 + HIST.length * 40}px`;

  const cfg = {
    type: "bar",
    data: { labels, datasets },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "nearest", intersect: true },
      scales: {
        x: {
          stacked: true, max: 100,
          grid: { color: tok("--grid") },
          border: { display: false },
          ticks: { callback: v => v + "%" },
        },
        y: {
          stacked: true,
          grid: { display: false },
          border: { color: tok("--baseline") },
          ticks: {
            color: tok("--ink-2"),
            callback(v) {
              const d = new Date(this.getLabelForValue(v) + "T00:00:00");
              return d.toLocaleDateString(undefined, { month: "short", year: "2-digit" });
            },
          },
        },
      },
      plugins: {
        tooltip: {
          callbacks: {
            title: (items) => fmtDate(items[0].label),
            label: (item) => ` ${item.raw.toFixed(1)}%  ${item.dataset.label}`,
          },
        },
      },
    },
  };
  if (compChart) compChart.destroy();
  compChart = new Chart(document.getElementById("comp-chart"), cfg);
}

init();
