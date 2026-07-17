/* Search-driven mean-variance optimization over the S&P 500 + held names.
   Expected returns and covariance are computed in the browser from the shared
   returns matrix, for whatever subset is searched/added. Long-only frontier via
   Frank-Wolfe (no matrix inverse). */

let INDEX, IDX_MAP, MATRIX, RF = 0.04;
let charts = {};
const state = { selected: [], muMode: "mean", optType: "sharpe", showCloud: true };
const sectorSlot = {}; let sectorN = 0;

async function init() {
  const content = document.getElementById("content");
  document.getElementById("asof").textContent = "Loading universe…";
  try {
    [INDEX, MATRIX] = await Promise.all([
      loadJSON("data/universe_index.json"),
      loadJSON("data/returns_matrix.json"),
    ]);
  } catch (err) { showError(content, err); return; }
  IDX_MAP = new Map(INDEX.map(x => [x.symbol, x]));
  document.getElementById("asof").textContent = `${INDEX.length} symbols · 3y daily`;
  wireControls();
  wireSearch();
  renderAll();
  onThemeChange(renderAll);
}

// ---------- linear algebra ----------
function matvec(S, w) { const n = w.length, o = new Array(n).fill(0);
  for (let i = 0; i < n; i++) { let s = 0; for (let j = 0; j < n; j++) s += S[i][j] * w[j]; o[i] = s; } return o; }
function quad(w, S) { const Sw = matvec(S, w); let s = 0; for (let i = 0; i < w.length; i++) s += w[i] * Sw[i]; return s; }
function dot(a, b) { let s = 0; for (let i = 0; i < a.length; i++) s += a[i] * b[i]; return s; }

function frankWolfe(mu, S, lam, iters = 300) {
  const n = mu.length; let w = new Array(n).fill(1 / n);
  for (let t = 0; t < iters; t++) {
    const Sw = matvec(S, w); let k = 0, best = -Infinity;
    for (let i = 0; i < n; i++) { const g = mu[i] - 2 * lam * Sw[i]; if (g > best) { best = g; k = i; } }
    const gamma = 2 / (t + 2);
    for (let i = 0; i < n; i++) w[i] = (1 - gamma) * w[i] + (i === k ? gamma : 0);
  }
  return w;
}

// ---------- build subset stats from the returns matrix ----------
const TRADING = 252;
function subsetStats() {
  const syms = state.selected;
  const cols = syms.map(s => MATRIX.data[s]);
  const T = MATRIX.dates.length;
  // intersection window: rows where every selected name has data
  const rows = [];
  for (let t = 0; t < T; t++) {
    let ok = true; for (const c of cols) if (c[t] == null) { ok = false; break; }
    if (ok) rows.push(t);
  }
  const k = syms.length, n = rows.length;
  const counts = cols.map(c => c.reduce((a, v) => a + (v != null ? 1 : 0), 0));
  let limIdx = 0; for (let i = 1; i < k; i++) if (counts[i] < counts[limIdx]) limIdx = i;
  const R = rows.map(t => cols.map(c => c[t]));           // n x k
  const mean = new Array(k).fill(0);
  for (const r of R) for (let j = 0; j < k; j++) mean[j] += r[j] / n;
  // sample covariance (annualized) + tiny ridge
  const cov = Array.from({ length: k }, () => new Array(k).fill(0));
  for (const r of R) for (let i = 0; i < k; i++) for (let j = 0; j < k; j++)
    cov[i][j] += (r[i] - mean[i]) * (r[j] - mean[j]);
  for (let i = 0; i < k; i++) for (let j = 0; j < k; j++) {
    cov[i][j] = cov[i][j] / Math.max(n - 1, 1) * TRADING;
    if (i === j) cov[i][j] += 1e-6;
  }
  let mu = mean.map(m => m * TRADING);                    // annualized mean
  if (state.muMode === "shrunk") {
    const grand = mu.reduce((a, b) => a + b, 0) / k;
    mu = mu.map(m => 0.5 * grand + 0.5 * m);
  } else if (state.muMode === "risk") {
    mu = mu.map(() => 0);
  }
  const vol = cov.map((row, i) => Math.sqrt(row[i]));
  const ret = mean.map(m => m * TRADING);                 // true annualized return (for plotting)
  return { syms, mu, cov, vol, ret, nobs: n, k, limiter: syms[limIdx], limiterN: counts[limIdx] };
}

function computeFrontier(st) {
  const { mu, cov } = st;
  const pts = [];
  for (let i = 0; i < 60; i++) {
    const lam = Math.exp(Math.log(0.15) + (Math.log(1200) - Math.log(0.15)) * i / 59);
    const w = frankWolfe(mu, cov, lam);
    const ret = dot(mu, w), vol = Math.sqrt(Math.max(quad(w, cov), 0));
    pts.push({ w, ret, vol, sharpe: vol > 0 ? (ret - RF) / vol : -Infinity });
  }
  const mvW = frankWolfe(mu.map(() => 0), cov, 1, 500);
  const minVar = { w: mvW, ret: dot(mu, mvW), vol: Math.sqrt(Math.max(quad(mvW, cov), 0)) };
  minVar.sharpe = minVar.vol > 0 ? (minVar.ret - RF) / minVar.vol : -Infinity;
  pts.push(minVar);
  pts.sort((a, b) => a.vol - b.vol);
  const frontier = []; let mr = -Infinity;
  for (const p of pts) { if (p.ret >= mr - 1e-9) { frontier.push(p); mr = Math.max(mr, p.ret); } }
  let maxSharpe = frontier[0];
  for (const p of frontier) if (p.sharpe > maxSharpe.sharpe) maxSharpe = p;
  return { frontier, minVar, maxSharpe };
}

// ---------- selection ----------
function sectorHex(sec) {
  if (!(sec in sectorSlot)) { sectorSlot[sec] = SLOT_VARS[sectorN % SLOT_VARS.length]; sectorN++; }
  return tok(sectorSlot[sec]);
}
function addSymbol(sym) { if (!state.selected.includes(sym) && IDX_MAP.has(sym)) { state.selected.push(sym); renderAll(); } }
function removeSymbol(sym) { state.selected = state.selected.filter(s => s !== sym); renderAll(); }

async function loadHoldings() {
  let pf; try { pf = await loadJSON("data/current_portfolio.json"); } catch { return; }
  for (const p of pf.positions) {
    let sym = p.symbol;
    if (sym.endsWith(".TO")) {
      const base = sym.slice(0, -3);
      sym = IDX_MAP.has(base) ? base : (IDX_MAP.has(sym) ? sym : null);
    } else if (!IDX_MAP.has(sym)) sym = null;
    if (sym && !state.selected.includes(sym)) state.selected.push(sym);
  }
  renderAll();
}

// ---------- search ----------
function wireSearch() {
  const input = document.getElementById("search"), dd = document.getElementById("dropdown");
  const close = () => { dd.innerHTML = ""; };
  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    if (!q) return close();
    const hits = INDEX.filter(x => !state.selected.includes(x.symbol) &&
      (x.symbol.toLowerCase().startsWith(q) || x.name.toLowerCase().includes(q)))
      .sort((a, b) => (a.symbol.toLowerCase().startsWith(q) ? 0 : 1) - (b.symbol.toLowerCase().startsWith(q) ? 0 : 1))
      .slice(0, 20);
    dd.className = "search-dropdown";
    dd.innerHTML = "";
    if (!hits.length) { const e = document.createElement("div"); e.className = "search-empty"; e.textContent = "No matches"; dd.appendChild(e); return; }
    for (const h of hits) {
      const row = document.createElement("div"); row.className = "search-result";
      const sym = document.createElement("span"); sym.className = "sym"; sym.textContent = h.symbol;
      const nm = document.createElement("span"); nm.className = "nm"; nm.textContent = h.name;
      const sec = document.createElement("span"); sec.className = "sec"; sec.textContent = h.sector;
      row.append(sym, nm, sec);
      row.addEventListener("mousedown", (e) => { e.preventDefault(); addSymbol(h.symbol); input.value = ""; close(); });
      dd.appendChild(row);
    }
  });
  input.addEventListener("blur", () => setTimeout(close, 150));
}

function wireControls() {
  document.querySelectorAll("#mu-seg button").forEach(b => b.addEventListener("click", () => seg("mu-seg", b, () => state.muMode = b.dataset.v)));
  document.querySelectorAll("#opt-seg button").forEach(b => b.addEventListener("click", () => seg("opt-seg", b, () => state.optType = b.dataset.v)));
  document.getElementById("show-cloud").addEventListener("change", e => { state.showCloud = e.target.checked; renderAll(); });
  document.getElementById("clear").addEventListener("click", () => { state.selected = []; renderAll(); });
  document.getElementById("load-holdings").addEventListener("click", loadHoldings);
}
function seg(id, btn, apply) {
  document.querySelectorAll(`#${id} button`).forEach(b => b.classList.remove("active"));
  btn.classList.add("active"); apply(); renderAll();
}

// ---------- render ----------
function renderChips() {
  const el = document.getElementById("chips"); el.innerHTML = "";
  for (const sym of state.selected) {
    const meta = IDX_MAP.get(sym);
    const chip = document.createElement("span"); chip.className = "chip";
    const sw = document.createElement("span"); sw.className = "csec"; sw.style.background = sectorHex(meta.sector);
    const s = document.createElement("span"); s.className = "csym"; s.textContent = sym;
    const x = document.createElement("button"); x.className = "cx"; x.textContent = "×";
    x.title = `Remove ${sym}`; x.addEventListener("click", () => removeSymbol(sym));
    chip.append(sw, s, x); el.appendChild(chip);
  }
}

function renderAll() {
  applyChartDefaults();
  renderChips();
  const note = document.getElementById("sel-note");
  ["tiles", "frontier-legend", "heatmap"].forEach(id => { const e = document.getElementById(id); });

  if (state.selected.length < 2) {
    note.textContent = "Search and add at least 2 stocks to build a frontier.";
    ["frontier-chart", "weights-chart", "risk-chart"].forEach(id => { if (charts[id]) { charts[id].destroy(); delete charts[id]; } });
    document.getElementById("tiles").innerHTML = "";
    document.getElementById("frontier-legend").innerHTML = "";
    document.getElementById("heatmap").innerHTML = "";
    document.getElementById("frontier-note").textContent = "";
    return;
  }

  const st = subsetStats();
  note.textContent = `${st.k} names · ${st.nobs} overlapping trading days`
    + (st.nobs < 120 ? ` ⚠ short window (limited by ${st.limiter}, ${st.limiterN}d) — estimates unreliable; remove it for more history` : "");
  const { frontier, minVar, maxSharpe } = computeFrontier(st);
  const optimal = state.optType === "sharpe" ? maxSharpe : minVar;

  renderTiles(optimal, st);
  renderFrontier(st, frontier, minVar, maxSharpe);
  renderWeights(st, optimal);
  renderRisk(st, optimal);
  renderHeatmap(st);
}

function renderTiles(o, st) {
  const el = document.getElementById("tiles"); el.innerHTML = "";
  const rf = state.muMode === "risk" ? 0 : RF;
  const defs = [
    { l: state.muMode === "risk" ? "Realized return" : "Expected return", v: fmtPct(state.muMode === "risk" ? dot(st.ret, o.w) : o.ret) },
    { l: "Volatility", v: fmtPct(o.vol) },
    { l: "Sharpe", v: o.vol > 0 ? ((o.ret - rf) / o.vol).toFixed(2) : "–" },
    { l: "Holdings", v: o.w.filter(x => x > 0.001).length },
  ];
  for (const d of defs) {
    const t = document.createElement("div"); t.className = "tile";
    const l = document.createElement("div"); l.className = "label"; l.textContent = d.l;
    const v = document.createElement("div"); v.className = "value"; v.textContent = d.v;
    t.append(l, v); el.appendChild(t);
  }
}

function rampFor(t) {
  const steps = ["--ramp-250", "--ramp-350", "--ramp-450", "--ramp-550", "--ramp-650"];
  return tok(steps[Math.min(steps.length - 1, Math.max(0, Math.floor(t * steps.length)))]);
}

function renderFrontier(st, frontier, minVar, maxSharpe) {
  const riskOnly = state.muMode === "risk";
  const yLabel = riskOnly ? "Annualized return" : (state.muMode === "shrunk" ? "Expected return (shrunk)" : "Expected return");
  document.getElementById("frontier-title").textContent = riskOnly ? "Risk map (minimum-variance)" : "Efficient frontier";
  const datasets = [];

  if (state.showCloud) {
    const cloud = [];
    for (let c = 0; c < 1500; c++) {
      const e = st.mu.map(() => -Math.log(1 - Math.random())); const s = e.reduce((a, b) => a + b, 0);
      const w = e.map(x => x / s);
      cloud.push({ x: Math.sqrt(Math.max(quad(w, st.cov), 0)), y: dot(riskOnly ? st.ret : st.mu, w) });
    }
    datasets.push({ type: "scatter", label: "Random", data: cloud, pointRadius: 2, pointHoverRadius: 2,
      backgroundColor: tok("--ramp-350") + "44", order: 5 });
  }
  if (!riskOnly) {
    datasets.push({ type: "line", label: "Frontier", data: frontier.map(p => ({ x: p.vol, y: p.ret })),
      borderColor: tok("--ink"), borderWidth: 2.5, pointRadius: 0, tension: 0, order: 1 });
  }
  datasets.push({ type: "scatter", label: "Assets",
    data: st.vol.map((v, i) => ({ x: v, y: (riskOnly ? st.ret : st.mu)[i], t: st.syms[i], sec: IDX_MAP.get(st.syms[i]).sector })),
    pointRadius: 6, pointHoverRadius: 8, backgroundColor: st.syms.map(s => sectorHex(IDX_MAP.get(s).sector)),
    borderColor: tok("--surface"), borderWidth: 2, order: 3 });
  datasets.push({ type: "scatter", label: "Min variance", data: [{ x: minVar.vol, y: minVar.ret }],
    pointStyle: "circle", pointRadius: 9, pointHoverRadius: 11, backgroundColor: "transparent",
    borderColor: tok("--accent"), borderWidth: 2.5, order: 0 });
  if (!riskOnly) datasets.push({ type: "scatter", label: "Max Sharpe", data: [{ x: maxSharpe.vol, y: maxSharpe.ret }],
    pointStyle: "star", pointRadius: 11, pointHoverRadius: 13, backgroundColor: tok("--s3"), borderColor: tok("--s3"), order: 0 });

  const legend = [{ label: "Min variance ○", color: tok("--accent") }, { label: "Assets (by sector)", color: tok("--muted"), shape: "rect" }];
  if (!riskOnly) legend.unshift({ label: "Frontier", color: tok("--ink") }, { label: "Max Sharpe ★", color: tok("--s3") });
  buildLegend(document.getElementById("frontier-legend"), legend);
  document.getElementById("frontier-note").textContent = riskOnly
    ? "Risk-only mode ignores return estimates — the marked point is the minimum-variance portfolio."
    : "Each dot is one selected name; the frontier bulges left of them — the gain from diversification.";

  draw("frontier-chart", {
    data: { datasets },
    options: {
      responsive: true, maintainAspectRatio: false, interaction: { mode: "nearest", intersect: true },
      scales: {
        x: { type: "linear", title: { display: true, text: "Volatility (annualized)", color: tok("--ink-2") },
          grid: { color: tok("--grid") }, border: { color: tok("--baseline") }, ticks: { callback: v => (v * 100).toFixed(0) + "%" } },
        y: { title: { display: true, text: yLabel, color: tok("--ink-2") }, grid: { color: tok("--grid") },
          border: { display: false }, ticks: { callback: v => (v * 100).toFixed(0) + "%" } },
      },
      plugins: { tooltip: { callbacks: { label: (it) => { const r = it.raw;
        return r.t ? ` ${r.t} (${r.sec}): ${(r.y * 100).toFixed(1)}% / ${(r.x * 100).toFixed(1)}% vol`
                   : ` ${(r.y * 100).toFixed(1)}% ret, ${(r.x * 100).toFixed(1)}% vol`; } } } },
    },
  });
}

function renderWeights(st, optimal) {
  document.getElementById("weights-title").textContent =
    (state.optType === "sharpe" && state.muMode !== "risk" ? "Max-Sharpe" : "Minimum-variance") + " portfolio weights";
  const rows = st.syms.map((s, i) => ({ s, sec: IDX_MAP.get(s).sector, w: optimal.w[i] }))
    .filter(r => r.w > 0.001).sort((a, b) => b.w - a.w);
  document.getElementById("weights-box").style.height = `${70 + rows.length * 30}px`;
  draw("weights-chart", {
    type: "bar",
    data: { labels: rows.map(r => r.s), datasets: [{ data: rows.map(r => r.w * 100),
      backgroundColor: rows.map(r => sectorHex(r.sec)), borderRadius: { topRight: 4, bottomRight: 4 }, borderSkipped: "start", barThickness: 18 }] },
    options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, layout: { padding: { right: 44 } },
      scales: { x: { grid: { color: tok("--grid") }, border: { display: false }, ticks: { callback: v => v + "%" } },
        y: { grid: { display: false }, border: { color: tok("--baseline") }, ticks: { color: tok("--ink-2"), font: { weight: 600 } } } },
      plugins: { tooltip: { callbacks: { label: (i) => ` ${i.raw.toFixed(1)}%  (${rows[i.dataIndex].sec})` } } } },
    plugins: [barLabels(rows.map(r => `${(r.w * 100).toFixed(1)}%`))],
  });
}

function renderRisk(st, optimal) {
  const w = optimal.w, Sw = matvec(st.cov, w), varp = dot(w, Sw);
  const rows = st.syms.map((s, i) => ({ s, sec: IDX_MAP.get(s).sector, rc: varp > 0 ? w[i] * Sw[i] / varp : 0 }))
    .filter(r => r.rc > 0.0005).sort((a, b) => b.rc - a.rc);
  document.getElementById("risk-box").style.height = `${70 + rows.length * 30}px`;
  draw("risk-chart", {
    type: "bar",
    data: { labels: rows.map(r => r.s), datasets: [{ data: rows.map(r => r.rc * 100),
      backgroundColor: rows.map(r => sectorHex(r.sec)), borderRadius: { topRight: 4, bottomRight: 4 }, borderSkipped: "start", barThickness: 18 }] },
    options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, layout: { padding: { right: 44 } },
      scales: { x: { grid: { color: tok("--grid") }, border: { display: false }, ticks: { callback: v => v + "%" } },
        y: { grid: { display: false }, border: { color: tok("--baseline") }, ticks: { color: tok("--ink-2"), font: { weight: 600 } } } },
      plugins: { tooltip: { callbacks: { label: (i) => ` ${i.raw.toFixed(1)}% of risk` } } } },
    plugins: [barLabels(rows.map(r => `${(r.rc * 100).toFixed(1)}%`))],
  });
}

function barLabels(labels) {
  return { id: "bl" + Math.random(), afterDatasetsDraw(chart) {
    const meta = chart.getDatasetMeta(0), ctx = chart.ctx;
    ctx.save(); ctx.fillStyle = tok("--ink-2"); ctx.font = "12px system-ui, sans-serif"; ctx.textBaseline = "middle";
    meta.data.forEach((bar, i) => ctx.fillText(labels[i], bar.x + 8, bar.y)); ctx.restore(); } };
}

function corrColor(c) {
  // diverging: +1 red (--s6), 0 neutral, -1 blue (--s1)
  const pos = tok("--s6"), neg = tok("--s1"), mid = tok("--surface");
  const hex = c >= 0 ? mix(mid, pos, c) : mix(mid, neg, -c);
  return hex;
}
function mix(a, b, t) {
  const pa = [1, 3, 5].map(i => parseInt(a.slice(i, i + 2), 16));
  const pb = [1, 3, 5].map(i => parseInt(b.slice(i, i + 2), 16));
  const p = pa.map((x, i) => Math.round(x + (pb[i] - x) * t));
  return "#" + p.map(x => x.toString(16).padStart(2, "0")).join("");
}

function renderHeatmap(st) {
  const el = document.getElementById("heatmap");
  const k = st.k, cov = st.cov, vol = st.vol;
  const corr = (i, j) => cov[i][j] / (vol[i] * vol[j]);
  el.className = "heatmap";
  el.style.gridTemplateColumns = `auto repeat(${k}, 30px)`;
  el.innerHTML = "";
  el.appendChild(cell("", "hm-corner"));                       // top-left corner
  for (let j = 0; j < k; j++) el.appendChild(cell(st.syms[j], "hm-collabel"));
  for (let i = 0; i < k; i++) {
    el.appendChild(cell(st.syms[i], "hm-rowlabel"));
    for (let j = 0; j < k; j++) {
      const c = corr(i, j);
      const d = cell(c.toFixed(2), "hm-cell");
      d.style.background = corrColor(c);
      d.style.color = Math.abs(c) > 0.6 ? "#fff" : tok("--ink");
      d.title = `${st.syms[i]} · ${st.syms[j]}: ${c.toFixed(2)}`;
      el.appendChild(d);
    }
  }
  document.getElementById("corr-note").textContent =
    `Daily-return correlation of the ${k} selected names over ${st.nobs} shared days (red = move together, blue = opposite).`;
}
function cell(text, cls) { const d = document.createElement("div"); d.className = cls; d.textContent = text; return d; }

function draw(id, cfg) { if (charts[id]) charts[id].destroy(); charts[id] = new Chart(document.getElementById(id), cfg); }

init();
