/* Full risk-analytics package for the actual portfolio. All figures are ratios /
   percentages (no dollars), computed from current holdings over ~3y of history. */

let MET, charts = {};

async function init() {
  const content = document.getElementById("content");
  try { MET = await loadJSON("data/portfolio_metrics.json"); }
  catch (err) { showError(content, err); return; }
  document.getElementById("asof").textContent = `As of ${fmtDate(MET.as_of)}`;
  const yrs = Math.round(MET.window_days / 252 * 10) / 10;
  document.getElementById("intro").textContent =
    `Institutional risk metrics from your current holdings applied over the past ${yrs} years `
    + `(${Math.round(MET.coverage_pct * 100)}% of the book with return history) — hypothetical, since weights change over time.`;
  render();
  onThemeChange(render);
}

const pct = (x, d = 1) => x == null ? "–" : (x * 100).toFixed(d) + "%";
const f2 = (x) => x == null ? "–" : x.toFixed(2);

function metric(el, label, value, opts = {}) {
  const m = document.createElement("div"); m.className = "metric";
  const l = document.createElement("div"); l.className = "m-label"; l.textContent = label;
  const v = document.createElement("div"); v.className = "m-value" + (opts.tone ? " " + opts.tone : "");
  v.textContent = value;
  m.append(l, v);
  if (opts.hint) { const h = document.createElement("div"); h.className = "m-hint"; h.textContent = opts.hint; m.appendChild(h); }
  el.appendChild(m);
}

function render() {
  applyChartDefaults();
  const M = MET;
  const g = (id) => { const e = document.getElementById(id); e.innerHTML = ""; return e; };

  const r = g("g-return");
  metric(r, "CAGR", pct(M.cagr), { tone: M.cagr >= 0 ? "up" : "down", hint: "annualized, hypothetical" });
  metric(r, "Volatility", pct(M.vol_annual), { hint: "annualized" });
  metric(r, "Sharpe", f2(M.sharpe), { hint: "excess return / vol" });
  metric(r, "Sortino", f2(M.sortino), { hint: "vs downside vol" });
  metric(r, "Calmar", f2(M.calmar), { hint: "CAGR / max drawdown" });
  metric(r, "Max drawdown", pct(M.max_drawdown), { tone: "down", hint: "worst peak-to-trough" });
  metric(r, "Downside dev.", pct(M.downside_dev), { hint: "annualized" });

  const mk = g("g-market");
  metric(mk, "Beta", f2(M.beta), { hint: "vs S&P 500" });
  metric(mk, "Downside beta β⁻", f2(M.beta_down), { hint: "on down-market days" });
  metric(mk, "Upside beta β⁺", f2(M.beta_up), { hint: "on up-market days" });
  metric(mk, "Beta asymmetry", (M.beta_asymmetry >= 0 ? "+" : "") + f2(M.beta_asymmetry),
    { tone: M.beta_asymmetry >= 0 ? "up" : "down", hint: "β⁺ − β⁻ (want ≥ 0)" });
  metric(mk, "Alpha", pct(M.alpha_annual), { tone: M.alpha_annual >= 0 ? "up" : "down", hint: "annualized, CAPM" });
  metric(mk, "Correlation", f2(M.correlation), { hint: "to the market" });
  metric(mk, "R²", f2(M.r2), { hint: "variance explained by market" });
  metric(mk, "Up capture", f2(M.up_capture), { hint: "vs market up days" });
  metric(mk, "Down capture", f2(M.down_capture), { hint: "vs market down days" });
  metric(mk, "Tracking error", pct(M.tracking_error), { hint: "annualized active risk" });
  metric(mk, "Information ratio", f2(M.information_ratio), { hint: "active return / TE" });

  const t = g("g-tail");
  metric(t, "VaR 95% (1-day)", pct(M.var95), { tone: "down", hint: "worst ~1 in 20 days" });
  metric(t, "CVaR 95%", pct(M.cvar95), { tone: "down", hint: "avg of the worst 5%" });
  metric(t, "Skew", f2(M.skew), { hint: ">0 = right-tailed" });
  metric(t, "Kurtosis", f2(M.kurtosis), { hint: "excess; >0 = fat tails" });
  metric(t, "Positive days", pct(M.pct_positive, 0), { hint: "hit rate" });
  metric(t, "Best day", pct(M.best_day), { tone: "up" });
  metric(t, "Worst day", pct(M.worst_day), { tone: "down" });

  const c = g("g-conc");
  metric(c, "HHI", M.hhi.toFixed(3), { hint: "0 = diversified, 1 = one name" });
  metric(c, "Effective names", f2(M.effective_n).replace(".00", ""), { hint: "1 / HHI" });
  metric(c, "Top 5 weight", pct(M.top5_weight, 0));
  metric(c, "Top 10 weight", pct(M.top10_weight, 0));
  metric(c, "Sector HHI", M.hhi_sector.toFixed(3), { hint: "concentration by sector" });
  const cadw = (M.currency_exposure.find(x => x.currency === "CAD") || { weight: 0 }).weight;
  metric(c, "CAD / USD", `${Math.round(cadw * 100)}% / ${Math.round((1 - cadw) * 100)}%`);

  drawDrawdown(); drawBeta(); drawHist(); drawSector();
}

function draw(id, cfg) { if (charts[id]) charts[id].destroy(); charts[id] = new Chart(document.getElementById(id), cfg); }

function drawDrawdown() {
  const s = MET.series;
  draw("dd-chart", {
    type: "line",
    data: { labels: s.dates, datasets: [{
      data: s.drawdown.map(x => x * 100), borderColor: tok("--down"), borderWidth: 1.5,
      backgroundColor: tok("--down") + "22", fill: true, pointRadius: 0, tension: 0 }] },
    options: { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      scales: {
        x: { grid: { display: false }, border: { color: tok("--baseline") },
             ticks: { maxTicksLimit: 8, callback(v) { const d = new Date(this.getLabelForValue(v) + "T00:00:00"); return d.toLocaleDateString(undefined, { month: "short", year: "2-digit" }); } } },
        y: { grid: { color: tok("--grid") }, border: { display: false }, ticks: { callback: v => v + "%" }, max: 0 } },
      plugins: { tooltip: { callbacks: { title: i => fmtDate(i[0].label), label: i => " drawdown " + i.raw.toFixed(1) + "%" } } } },
    plugins: [crosshairPlugin],
  });
  document.getElementById("dd-note").textContent =
    `Underwater plot — % below the running peak. Deepest: ${pct(MET.max_drawdown)}.`
    + (MET.twr_max_drawdown != null ? ` Actual monthly equity-curve worst: ${pct(MET.twr_max_drawdown)}.` : "");
}

function drawBeta() {
  const s = MET.series, pts = s.mkt.map((x, i) => ({ x: x * 100, y: s.port[i] * 100 }));
  const xlo = Math.min(...s.mkt) * 100, xhi = Math.max(...s.mkt) * 100;
  buildLegend(document.getElementById("beta-legend"), [
    { label: `Down-market slope β⁻ ${f2(MET.beta_down)}`, color: tok("--down") },
    { label: `Up-market slope β⁺ ${f2(MET.beta_up)}`, color: tok("--up") },
  ]);
  draw("beta-chart", {
    data: { datasets: [
      { type: "scatter", data: pts, pointRadius: 2, pointHoverRadius: 3, backgroundColor: tok("--accent") + "66", order: 3 },
      { type: "line", data: [{ x: xlo, y: MET.beta_down * xlo }, { x: 0, y: 0 }], borderColor: tok("--down"), borderWidth: 2, pointRadius: 0, order: 1 },
      { type: "line", data: [{ x: 0, y: 0 }, { x: xhi, y: MET.beta_up * xhi }], borderColor: tok("--up"), borderWidth: 2, pointRadius: 0, order: 1 },
    ] },
    options: { responsive: true, maintainAspectRatio: false,
      scales: {
        x: { type: "linear", title: { display: true, text: "S&P 500 daily return", color: tok("--ink-2") }, grid: { color: tok("--grid") }, border: { color: tok("--baseline") }, ticks: { callback: v => v + "%" } },
        y: { title: { display: true, text: "Portfolio daily return", color: tok("--ink-2") }, grid: { color: tok("--grid") }, border: { display: false }, ticks: { callback: v => v + "%" } } },
      plugins: { tooltip: { callbacks: { label: i => ` mkt ${i.raw.x.toFixed(1)}% · port ${i.raw.y.toFixed(1)}%` } } } },
  });
}

function drawHist() {
  const vals = MET.series.port, nb = 41;
  const lo = Math.min(...vals), hi = Math.max(...vals), w = (hi - lo) / nb;
  const bins = new Array(nb).fill(0);
  for (const v of vals) bins[Math.min(nb - 1, Math.floor((v - lo) / w))]++;
  const labels = bins.map((_, i) => ((lo + (i + 0.5) * w) * 100));
  draw("hist-chart", {
    type: "bar",
    data: { labels: labels.map(x => x.toFixed(1)), datasets: [{
      data: bins, backgroundColor: labels.map(x => (x < 0 ? tok("--down") : tok("--up")) + "cc"),
      borderWidth: 0, barPercentage: 1, categoryPercentage: 1 }] },
    options: { responsive: true, maintainAspectRatio: false,
      scales: {
        x: { grid: { display: false }, border: { color: tok("--baseline") }, ticks: { maxTicksLimit: 11, callback(v) { return this.getLabelForValue(v) + "%"; } } },
        y: { grid: { color: tok("--grid") }, border: { display: false }, title: { display: true, text: "days", color: tok("--ink-2") } } },
      plugins: { tooltip: { callbacks: { title: i => i[0].label + "% daily return", label: i => ` ${i.raw} days` } } } },
  });
  document.getElementById("hist-note").textContent =
    `${MET.series.port.length} trading days. Skew ${f2(MET.skew)}, excess kurtosis ${f2(MET.kurtosis)} `
    + `(fat tails); ${pct(MET.pct_positive, 0)} of days positive.`;
}

function drawSector() {
  const rows = MET.sector_exposure, slots = ["--s1", "--s2", "--s3", "--s4", "--s5", "--s6", "--s7", "--s8"];
  const colors = rows.map((_, i) => tok(slots[i % slots.length]));
  buildLegend(document.getElementById("sector-legend"),
    rows.map((r, i) => ({ label: `${r.sector} ${pct(r.weight, 0)}`, color: colors[i], shape: "rect" })));
  document.getElementById("sector-box").style.height = `${50 + rows.length * 32}px`;
  draw("sector-chart", {
    type: "bar",
    data: { labels: rows.map(r => r.sector), datasets: [{
      data: rows.map(r => r.weight * 100), backgroundColor: colors,
      borderRadius: { topRight: 4, bottomRight: 4 }, borderSkipped: "start", barThickness: 20 }] },
    options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, layout: { padding: { right: 42 } },
      scales: { x: { grid: { color: tok("--grid") }, border: { display: false }, ticks: { callback: v => v + "%" } },
        y: { grid: { display: false }, border: { color: tok("--baseline") }, ticks: { color: tok("--ink-2"), font: { weight: 600 } } } },
      plugins: { tooltip: { callbacks: { label: i => " " + i.raw.toFixed(1) + "%" } } } },
    plugins: [{ id: "seclab", afterDatasetsDraw(ch) { const md = ch.getDatasetMeta(0), ctx = ch.ctx;
      ctx.save(); ctx.fillStyle = tok("--ink-2"); ctx.font = "12px system-ui,sans-serif"; ctx.textBaseline = "middle";
      md.data.forEach((b, i) => ctx.fillText(`${(rows[i].weight * 100).toFixed(1)}%`, b.x + 8, b.y)); ctx.restore(); } }],
  });
  document.getElementById("conc-note").textContent =
    `Effective ${f2(MET.effective_n).replace(".00", "")} names (1/HHI) across ${rows.length} sectors; top 5 positions are ${pct(MET.top5_weight, 0)} of the book.`;
}

init();
