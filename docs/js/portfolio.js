/* Current portfolio page: actual brokerage holdings from a manual snapshot. */

let PF, pfChart;
const CCY_SLOT = { USD: "--s1", CAD: "--s2" };

async function init() {
  const content = document.getElementById("content");
  try {
    PF = await loadJSON("data/current_portfolio.json");
  } catch (err) { showError(content, err); return; }
  document.getElementById("asof").textContent = `As of ${fmtDate(PF.as_of)}`;
  renderAll();
  onThemeChange(renderAll);
}

function renderAll() {
  applyChartDefaults();
  renderTiles();
  renderChart();
  renderTable();
}

function ccyColor(ccy) {
  return tok(CCY_SLOT[ccy] || "--muted");
}

function money(x, ccy) {
  const sign = x < 0 ? "-" : "";
  return `${sign}$${Math.abs(x).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${ccy}`;
}

function renderTiles() {
  const el = document.getElementById("tiles");
  el.innerHTML = "";
  const positions = PF.positions;
  const largest = positions.reduce((a, b) => (b.weight > a.weight ? b : a));
  const defs = [
    { label: "Positions", value: positions.length },
    { label: "Open P&L (CAD)", value: money(PF.open_pnl_cad, "").trim(), cls: PF.open_pnl_cad >= 0 ? "up" : "down" },
    { label: "Open P&L (USD)", value: money(PF.open_pnl_usd, "").trim(), cls: PF.open_pnl_usd >= 0 ? "up" : "down" },
    { label: "Largest position", value: `${largest.symbol}`, delta: fmtPct(largest.weight, 1) },
  ];
  for (const d of defs) {
    const tile = document.createElement("div");
    tile.className = "tile";
    const l = document.createElement("div"); l.className = "label"; l.textContent = d.label;
    const v = document.createElement("div"); v.className = "value"; v.textContent = d.value;
    if (d.cls) v.style.color = d.cls === "up" ? "var(--up)" : "var(--down)";
    tile.append(l, v);
    if (d.delta) {
      const dl = document.createElement("div"); dl.className = "delta"; dl.textContent = d.delta;
      tile.appendChild(dl);
    }
    el.appendChild(tile);
  }
}

function renderChart() {
  const rows = [...PF.positions].sort((a, b) => b.weight - a.weight);
  buildLegend(document.getElementById("pf-legend"), [
    { label: "USD", color: ccyColor("USD"), shape: "rect" },
    { label: "CAD", color: ccyColor("CAD"), shape: "rect" },
  ]);
  document.getElementById("pf-box").style.height = `${60 + rows.length * 26}px`;

  const cfg = {
    type: "bar",
    data: {
      labels: rows.map(r => r.symbol),
      datasets: [{
        data: rows.map(r => r.weight * 100),
        backgroundColor: rows.map(r => ccyColor(r.currency)),
        borderRadius: { topRight: 4, bottomRight: 4 }, borderSkipped: "start", barThickness: 15,
      }],
    },
    options: {
      indexAxis: "y", responsive: true, maintainAspectRatio: false,
      layout: { padding: { right: 46 } },
      scales: {
        x: { grid: { color: tok("--grid") }, border: { display: false }, ticks: { callback: v => v + "%" } },
        y: { grid: { display: false }, border: { color: tok("--baseline") },
             ticks: { color: tok("--ink-2"), font: { weight: 600, size: 11 } } },
      },
      plugins: {
        tooltip: {
          callbacks: {
            label: (item) => {
              const r = rows[item.dataIndex];
              return ` ${(r.weight * 100).toFixed(1)}% · ${money(r.mkt_value, r.currency)} · ${r.kind}`;
            },
          },
        },
      },
    },
    plugins: [{
      id: "pflabels",
      afterDatasetsDraw(chart) {
        const meta = chart.getDatasetMeta(0), ctx = chart.ctx;
        ctx.save(); ctx.fillStyle = tok("--ink-2"); ctx.font = "11px system-ui, sans-serif";
        ctx.textBaseline = "middle";
        meta.data.forEach((bar, i) => ctx.fillText(`${(rows[i].weight * 100).toFixed(1)}%`, bar.x + 8, bar.y));
        ctx.restore();
      },
    }],
  };
  if (pfChart) pfChart.destroy();
  pfChart = new Chart(document.getElementById("pf-chart"), cfg);
}

function renderTable() {
  const tbody = document.querySelector("#pf-table tbody");
  tbody.innerHTML = "";
  const rows = [...PF.positions].sort((a, b) => b.weight - a.weight);
  for (const r of rows) {
    const tr = document.createElement("tr");

    const sym = document.createElement("td");
    const wrap = document.createElement("span");
    wrap.className = "tick";
    const dot = document.createElement("span");
    dot.className = "dot"; dot.style.background = ccyColor(r.currency);
    const label = document.createElement("span");
    label.textContent = r.symbol; label.style.fontWeight = "600";
    wrap.append(dot, label); sym.appendChild(wrap); tr.appendChild(sym);

    const kind = document.createElement("td"); kind.textContent = r.kind; kind.style.color = "var(--ink-2)";
    const ccy = document.createElement("td"); ccy.textContent = r.currency; ccy.style.color = "var(--ink-2)";
    tr.append(kind, ccy);

    const wt = document.createElement("td"); wt.className = "num";
    wt.textContent = (r.weight * 100).toFixed(2) + "%"; tr.appendChild(wt);

    const mv = document.createElement("td"); mv.className = "num";
    mv.textContent = r.mkt_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    tr.appendChild(mv);

    const pnl = document.createElement("td"); pnl.className = "num";
    pnl.textContent = (r.open_pnl >= 0 ? "+" : "") + r.open_pnl.toFixed(2);
    pnl.classList.add(r.open_pnl >= 0 ? "pos" : "neg"); tr.appendChild(pnl);

    for (const val of [r.qty, r.avg_price, r.last_price]) {
      const td = document.createElement("td"); td.className = "num";
      td.textContent = typeof val === "number" ? val.toLocaleString() : val;
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  document.getElementById("pf-note").textContent =
    `${rows.length} positions. Colored dot marks currency (blue USD, aqua CAD). Open P&L is in each position's own currency.`;
}

init();
