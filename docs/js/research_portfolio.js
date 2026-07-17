/* Research › Portfolio — the model's current target allocation (portfolio.json). */

let PORT, charts = {};
const SLOTS = ["--s1", "--s2", "--s3", "--s4", "--s5", "--s6", "--s7", "--s8"];

async function init() {
  try { PORT = await loadJSON("data/portfolio.json"); }
  catch (err) { showError(document.getElementById("content"), err); return; }
  document.getElementById("asof").textContent = `As of ${fmtDate(PORT.as_of)}`;
  renderAll();
  onThemeChange(renderAll);
}

// Fixed sector -> categorical slot color (order of first appearance).
let sectorColor = null;
function sectorHex(sec) {
  if (!sectorColor) {
    sectorColor = {}; const order = [];
    PORT.holdings.forEach(h => { const s = h.sector || "Other"; if (!order.includes(s)) order.push(s); });
    order.forEach((s, i) => { sectorColor[s] = SLOTS[i] || "--muted"; });
  }
  return tok(sectorColor[sec] || "--muted");
}

function renderAll() {
  applyChartDefaults();
  renderTiles();
  renderDoughnut();
  renderSectors();
}

function tile(el, label, value) {
  const t = document.createElement("div"); t.className = "tile";
  const l = document.createElement("div"); l.className = "label"; l.textContent = label;
  const v = document.createElement("div"); v.className = "value"; v.textContent = value;
  t.append(l, v); el.appendChild(t);
}

function renderTiles() {
  const el = document.getElementById("tiles"); el.innerHTML = "";
  tile(el, "Positions", PORT.n_positions);
  tile(el, "Model volatility", fmtPct(PORT.model_vol));
  tile(el, "Vol target", `${fmtPct(PORT.vol_target_band[0], 0)}–${fmtPct(PORT.vol_target_band[1], 1)}`);
  tile(el, "Max position", fmtPct(PORT.max_weight, 0));
}

function renderDoughnut() {
  const h = [...PORT.holdings].sort((a, b) => b.weight - a.weight);
  buildLegend(document.getElementById("alloc-legend"),
    h.map(x => ({ label: `${x.ticker} ${fmtPct(x.weight, 0)}`, color: sectorHex(x.sector), shape: "rect" })));
  draw("alloc-chart", {
    type: "doughnut",
    data: { labels: h.map(x => x.ticker), datasets: [{
      data: h.map(x => x.weight * 100), backgroundColor: h.map(x => sectorHex(x.sector)),
      borderColor: tok("--surface"), borderWidth: 2 }] },
    options: { responsive: true, maintainAspectRatio: false, cutout: "58%",
      plugins: { tooltip: { callbacks: { label: (i) => ` ${i.label} (${h[i.dataIndex].sector}): ${i.raw.toFixed(1)}%` } } } },
  });
}

function renderSectors() {
  const bySector = {};
  for (const h of PORT.holdings) bySector[h.sector || "Other"] = (bySector[h.sector || "Other"] || 0) + h.weight;
  const rows = Object.entries(bySector).sort((a, b) => b[1] - a[1]);
  document.getElementById("sector-box").style.height = `${50 + rows.length * 34}px`;
  draw("sector-chart", {
    type: "bar",
    data: { labels: rows.map(r => r[0]), datasets: [{
      data: rows.map(r => r[1] * 100), backgroundColor: rows.map(r => sectorHex(r[0])),
      borderRadius: { topRight: 4, bottomRight: 4 }, borderSkipped: "start", barThickness: 20 }] },
    options: {
      indexAxis: "y", responsive: true, maintainAspectRatio: false, layout: { padding: { right: 44 } },
      scales: { x: { grid: { color: tok("--grid") }, border: { display: false }, ticks: { callback: v => v + "%" } },
                y: { grid: { display: false }, border: { color: tok("--baseline") }, ticks: { color: tok("--ink-2"), font: { weight: 600 } } } },
      plugins: { tooltip: { callbacks: { label: (i) => ` ${i.raw.toFixed(1)}%` } } },
    },
    plugins: [{ id: "seclabels", afterDatasetsDraw(chart) {
      const meta = chart.getDatasetMeta(0), ctx = chart.ctx;
      ctx.save(); ctx.fillStyle = tok("--ink-2"); ctx.font = "12px system-ui, sans-serif"; ctx.textBaseline = "middle";
      meta.data.forEach((bar, i) => ctx.fillText(`${rows[i][1] * 100 < 0.1 ? "<0.1" : (rows[i][1] * 100).toFixed(1)}%`, bar.x + 8, bar.y));
      ctx.restore(); } }],
  });
}

function draw(id, cfg) { if (charts[id]) charts[id].destroy(); charts[id] = new Chart(document.getElementById(id), cfg); }

init();
