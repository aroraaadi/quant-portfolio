/* "My Portfolio" section — actual Questrade holdings.
   One element-guarded module drives all three pages (Dashboard / Portfolio /
   Holdings): each render step runs only if its container exists on the page. */

let PF, PHIST, charts = {};
const CCY_SLOT = { USD: "--s1", CAD: "--s2" };

async function init() {
  const content = document.getElementById("content");
  try {
    PF = await loadJSON("data/current_portfolio.json");
    if (document.getElementById("value-chart")) {
      PHIST = await loadJSON("data/portfolio_history.json").catch(() => []);
    }
  } catch (err) { showError(content, err); return; }
  document.getElementById("asof").textContent = `As of ${fmtDate(PF.as_of)}`;
  renderAll();
  onThemeChange(renderAll);
}

function renderAll() {
  applyChartDefaults();
  if (document.getElementById("tiles")) renderTiles();
  if (document.getElementById("value-chart")) renderValueChart();
  if (document.getElementById("alloc-chart")) renderAllocation();
  if (document.getElementById("pf-chart")) renderWeightChart();
  if (document.getElementById("pf-table")) renderTable();
}

const ccyColor = (c) => tok(CCY_SLOT[c] || "--muted");

function tile(el, label, value, opts = {}) {
  const t = document.createElement("div"); t.className = "tile";
  const l = document.createElement("div"); l.className = "label"; l.textContent = label;
  const v = document.createElement("div"); v.className = "value"; v.textContent = value;
  if (opts.color) v.style.color = opts.color === "up" ? "var(--up)" : "var(--down)";
  if (opts.small) v.style.fontSize = "20px";
  t.append(l, v);
  if (opts.delta) { const d = document.createElement("div"); d.className = "delta"; d.textContent = opts.delta; t.appendChild(d); }
  el.appendChild(t);
}

function renderTiles() {
  const el = document.getElementById("tiles"); el.innerHTML = "";
  const p = PF.positions;
  const largest = p.reduce((a, b) => (b.weight > a.weight ? b : a));
  const cadPct = p.filter(x => x.currency === "CAD").reduce((s, x) => s + x.weight, 0);
  tile(el, "Positions", p.length, { delta: `${largest.symbol} largest ${fmtPct(largest.weight, 1)}` });
  tile(el, "CAD / USD split", `${Math.round(cadPct * 100)}% / ${Math.round((1 - cadPct) * 100)}%`, { small: true });
  if (document.getElementById("value-chart") && PHIST && PHIST.length) {
    const last = PHIST[PHIST.length - 1];
    const twr = last.twr_index - 100, spx = last.spx_index != null ? last.spx_index - 100 : null;
    tile(el, "Time-weighted return", `${twr >= 0 ? "+" : ""}${twr.toFixed(1)}%`,
      { color: twr >= 0 ? "up" : "down", delta: "since Jan 2024" });
    if (spx != null) tile(el, "S&P 500 (same period)", `${spx >= 0 ? "+" : ""}${spx.toFixed(1)}%`, { small: true });
  }
}

function renderValueChart() {
  const rows = (PHIST || []).slice();
  const line = (label, key, color, dash) => ({
    label, data: rows.map(r => r[key]), borderColor: color, backgroundColor: color,
    borderWidth: 2, borderDash: dash || [], pointRadius: 0, pointHoverRadius: 4, tension: 0,
  });
  const cfg = {
    type: "line",
    data: {
      labels: rows.map(r => r.date),
      datasets: [
        line("Portfolio value", "value_index", tok("--accent")),
        line("Net contributions", "invested_index", tok("--muted"), [5, 4]),
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { grid: { display: false }, border: { color: tok("--baseline") },
             ticks: { maxTicksLimit: 8, callback(v) { const d = new Date(this.getLabelForValue(v) + "T00:00:00"); return d.toLocaleDateString(undefined, { month: "short", year: "2-digit" }); } } },
        y: { grid: { color: tok("--grid") }, border: { display: false },
             ticks: { callback: v => v + "" } },
      },
      plugins: { tooltip: { callbacks: {
        title: (i) => fmtDate(i[0].label),
        label: (i) => ` ${i.dataset.label}: ${i.raw} (base 100)`,
      } } },
    },
    plugins: [crosshairPlugin],
  };
  draw("value-chart", cfg);
  buildLegend(document.getElementById("value-legend"), [
    { label: "Portfolio value", color: tok("--accent") },
    { label: "Net contributions", color: tok("--muted") },
  ]);
  const note = document.getElementById("value-note");
  if (note) note.textContent = rows.length
    ? "Indexed to 100 at Jan 2024. The gap between the two lines is market gains (vs money deposited). "
      + "Time-weighted return above strips out deposit timing."
    : "";
}

function renderAllocation() {
  const sorted = [...PF.positions].sort((a, b) => b.weight - a.weight);
  const top = sorted.slice(0, 8);
  const otherW = sorted.slice(8).reduce((s, r) => s + r.weight, 0);
  const labels = top.map(r => r.symbol).concat(otherW > 0 ? ["Other"] : []);
  const data = top.map(r => r.weight * 100).concat(otherW > 0 ? [otherW * 100] : []);
  const slots = ["--s1", "--s2", "--s3", "--s4", "--s5", "--s6", "--s7", "--s8"];
  const colors = top.map((_, i) => tok(slots[i])).concat(otherW > 0 ? [tok("--muted")] : []);
  buildLegend(document.getElementById("alloc-legend"),
    labels.map((l, i) => ({ label: l, color: colors[i], shape: "rect" })));
  const cfg = {
    type: "doughnut",
    data: { labels, datasets: [{ data, backgroundColor: colors, borderColor: tok("--surface"), borderWidth: 2 }] },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: "58%",
      plugins: { tooltip: { callbacks: { label: (i) => ` ${i.label}: ${i.raw.toFixed(1)}%` } } },
    },
  };
  draw("alloc-chart", cfg);
}

function renderWeightChart() {
  const rows = [...PF.positions].sort((a, b) => b.weight - a.weight);
  buildLegend(document.getElementById("pf-legend"), [
    { label: "USD", color: ccyColor("USD"), shape: "rect" },
    { label: "CAD", color: ccyColor("CAD"), shape: "rect" },
  ]);
  document.getElementById("pf-box").style.height = `${60 + rows.length * 26}px`;
  const cfg = {
    type: "bar",
    data: { labels: rows.map(r => r.symbol), datasets: [{
      data: rows.map(r => r.weight * 100), backgroundColor: rows.map(r => ccyColor(r.currency)),
      borderRadius: { topRight: 4, bottomRight: 4 }, borderSkipped: "start", barThickness: 15 }] },
    options: {
      indexAxis: "y", responsive: true, maintainAspectRatio: false, layout: { padding: { right: 46 } },
      scales: {
        x: { grid: { color: tok("--grid") }, border: { display: false }, ticks: { callback: v => v + "%" } },
        y: { grid: { display: false }, border: { color: tok("--baseline") }, ticks: { color: tok("--ink-2"), font: { weight: 600, size: 11 } } } },
      plugins: { tooltip: { callbacks: { label: (i) => {
        const r = rows[i.dataIndex]; return ` ${(r.weight * 100).toFixed(1)}% · ${r.kind} · ${r.currency}`; } } } },
    },
    plugins: [{ id: "pflabels", afterDatasetsDraw(chart) {
      const meta = chart.getDatasetMeta(0), ctx = chart.ctx;
      ctx.save(); ctx.fillStyle = tok("--ink-2"); ctx.font = "11px system-ui, sans-serif"; ctx.textBaseline = "middle";
      meta.data.forEach((bar, i) => ctx.fillText(`${(rows[i].weight * 100).toFixed(1)}%`, bar.x + 8, bar.y));
      ctx.restore(); } }],
  };
  draw("pf-chart", cfg);
}

function renderTable() {
  const tbody = document.querySelector("#pf-table tbody"); tbody.innerHTML = "";
  const rows = [...PF.positions].sort((a, b) => b.weight - a.weight);
  for (const r of rows) {
    const tr = document.createElement("tr");
    const sym = document.createElement("td");
    const wrap = document.createElement("span"); wrap.className = "tick";
    const dot = document.createElement("span"); dot.className = "dot"; dot.style.background = ccyColor(r.currency);
    const label = document.createElement("span"); label.textContent = r.symbol; label.style.fontWeight = "600";
    wrap.append(dot, label); sym.appendChild(wrap); tr.appendChild(sym);
    const kind = document.createElement("td"); kind.textContent = r.kind; kind.style.color = "var(--ink-2)";
    const ccy = document.createElement("td"); ccy.textContent = r.currency; ccy.style.color = "var(--ink-2)";
    tr.append(kind, ccy);
    const wt = document.createElement("td"); wt.className = "num"; wt.textContent = (r.weight * 100).toFixed(2) + "%"; tr.appendChild(wt);
    tbody.appendChild(tr);
  }
  const note = document.getElementById("pf-note");
  if (note) note.textContent = `${rows.length} positions. Weights only — dollar values are kept private.`;
}

function draw(id, cfg) {
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(document.getElementById(id), cfg);
}

init();
