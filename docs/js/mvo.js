/* Interactive mean-variance optimization.

   The efficient frontier for whatever subset of assets is selected is solved
   right here in the browser (Frank-Wolfe over the long-only simplex), so
   toggling assets redraws instantly. Only matrix-vector products are needed —
   no matrix inverse, no external math library. */

let MVO;                 // loaded payload
let frontierChart, weightsChart;
const state = {
  selected: new Set(),   // indices into MVO.assets
  muSource: "hist",      // "hist" | "alpha"
  optType: "sharpe",     // "sharpe" | "minvar"
  showCloud: true,
};
let sectorColor = {};    // sector -> css color

// ---------- linear algebra ----------
function matvec(S, w) {
  const n = w.length, out = new Array(n).fill(0);
  for (let i = 0; i < n; i++) {
    let s = 0;
    for (let j = 0; j < n; j++) s += S[i][j] * w[j];
    out[i] = s;
  }
  return out;
}
function quad(w, S) {
  const Sw = matvec(S, w);
  let s = 0;
  for (let i = 0; i < w.length; i++) s += w[i] * Sw[i];
  return s;
}
function dot(a, b) { let s = 0; for (let i = 0; i < a.length; i++) s += a[i] * b[i]; return s; }

/* max  muᵀw − lam·wᵀSw   s.t.  Σw = 1, w ≥ 0   (Frank-Wolfe on the simplex) */
function frankWolfe(mu, S, lam, iters = 300) {
  const n = mu.length;
  let w = new Array(n).fill(1 / n);
  for (let t = 0; t < iters; t++) {
    const Sw = matvec(S, w);
    let k = 0, best = -Infinity;
    for (let i = 0; i < n; i++) {
      const g = mu[i] - 2 * lam * Sw[i];
      if (g > best) { best = g; k = i; }
    }
    const gamma = 2 / (t + 2);
    for (let i = 0; i < n; i++) w[i] = (1 - gamma) * w[i] + (i === k ? gamma : 0);
  }
  return w;
}

// ---------- subset extraction ----------
function subset() {
  const idx = [...state.selected].sort((a, b) => a - b);
  const mu = idx.map(i => (state.muSource === "hist" ? MVO.mu_hist : MVO.mu_alpha)[i]);
  const S = idx.map(i => idx.map(j => MVO.sigma[i][j]));
  return {
    idx,
    assets: idx.map(i => MVO.assets[i]),
    sectors: idx.map(i => MVO.sectors[i]),
    vol: idx.map(i => MVO.vol[i]),
    ret: idx.map((i, k) => mu[k]),
    mu, S,
    rf: state.muSource === "hist" ? MVO.rf : 0,
  };
}

// ---------- frontier + optimal points ----------
function computeFrontier(sub) {
  const { mu, S, rf } = sub;
  const pts = [];
  const lambdas = [];
  for (let k = 0; k < 60; k++) lambdas.push(Math.exp(Math.log(0.15) + (Math.log(1200) - Math.log(0.15)) * k / 59));
  for (const lam of lambdas) {
    const w = frankWolfe(mu, S, lam);
    const ret = dot(mu, w), vol = Math.sqrt(Math.max(quad(w, S), 0));
    pts.push({ vol, ret, w, sharpe: vol > 0 ? (ret - rf) / vol : -Infinity });
  }
  const minVarW = frankWolfe(mu.map(() => 0), S, 1, 600);
  const minVar = { w: minVarW, ret: dot(mu, minVarW), vol: Math.sqrt(Math.max(quad(minVarW, S), 0)) };
  pts.push({ ...minVar, sharpe: minVar.vol > 0 ? (minVar.ret - rf) / minVar.vol : -Infinity });

  pts.sort((a, b) => a.vol - b.vol);
  // upper envelope: keep only points whose return exceeds all lower-vol points
  const frontier = [];
  let maxRet = -Infinity;
  for (const p of pts) { if (p.ret >= maxRet - 1e-9) { frontier.push(p); maxRet = Math.max(maxRet, p.ret); } }

  let maxSharpe = frontier[0];
  for (const p of frontier) if (p.sharpe > maxSharpe.sharpe) maxSharpe = p;
  return { frontier, minVar, maxSharpe };
}

function randomCloud(sub, n = 2000) {
  const { mu, S, rf } = sub, k = mu.length, out = [];
  for (let c = 0; c < n; c++) {
    const e = new Array(k), w = new Array(k);
    let sum = 0;
    for (let i = 0; i < k; i++) { e[i] = -Math.log(1 - Math.random()); sum += e[i]; }
    for (let i = 0; i < k; i++) w[i] = e[i] / sum;
    const ret = dot(mu, w), vol = Math.sqrt(Math.max(quad(w, S), 0));
    out.push({ x: vol, y: ret, s: vol > 0 ? (ret - rf) / vol : 0 });
  }
  return out;
}

// ---------- init ----------
async function init() {
  const content = document.getElementById("content");
  try {
    MVO = await loadJSON("data/mvo.json");
  } catch (err) { showError(content, err); return; }

  // fixed sector -> categorical slot color, in order of first appearance
  const order = [];
  MVO.sectors.forEach(s => { if (!order.includes(s)) order.push(s); });
  order.forEach((s, i) => { sectorColor[s] = SLOT_VARS[i] || null; });

  MVO.assets.forEach((_, i) => state.selected.add(i));
  buildAssetToggles(order);
  wireControls();
  renderAll();
  onThemeChange(renderAll);
}

function sectorHex(sector) {
  const v = sectorColor[sector];
  return v ? tok(v) : tok("--muted");
}

function buildAssetToggles(order) {
  const grid = document.getElementById("assetgrid");
  grid.innerHTML = "";
  for (const sector of order) {
    const group = document.createElement("div");
    group.className = "sector-group";
    const name = document.createElement("div");
    name.className = "sector-name";
    name.textContent = sector;
    group.appendChild(name);
    MVO.assets.forEach((ticker, i) => {
      if (MVO.sectors[i] !== sector) return;
      const label = document.createElement("label");
      label.className = "asset-toggle";
      const box = document.createElement("input");
      box.type = "checkbox"; box.checked = true; box.dataset.idx = i;
      box.addEventListener("change", () => {
        if (box.checked) state.selected.add(i); else state.selected.delete(i);
        label.classList.toggle("off", !box.checked);
        renderAll();
      });
      const sw = document.createElement("span");
      sw.className = "swatch"; sw.style.background = sectorHex(sector);
      const txt = document.createElement("span");
      txt.textContent = ticker;
      label.append(box, sw, txt);
      group.appendChild(label);
    });
    grid.appendChild(group);
  }
}

function wireControls() {
  document.querySelectorAll("#mu-seg button").forEach(b =>
    b.addEventListener("click", () => setSeg("mu-seg", b, () => { state.muSource = b.dataset.v; })));
  document.querySelectorAll("#opt-seg button").forEach(b =>
    b.addEventListener("click", () => setSeg("opt-seg", b, () => { state.optType = b.dataset.v; })));
  document.getElementById("show-cloud").addEventListener("change", e => {
    state.showCloud = e.target.checked; renderAll();
  });
  document.getElementById("sel-all").addEventListener("click", () => setAllAssets(true));
  document.getElementById("sel-none").addEventListener("click", () => setAllAssets(false));
}
function setSeg(segId, btn, apply) {
  document.querySelectorAll(`#${segId} button`).forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  apply();
  renderAll();
}
function setAllAssets(on) {
  state.selected.clear();
  document.querySelectorAll("#assetgrid input").forEach(box => {
    box.checked = on;
    box.closest(".asset-toggle").classList.toggle("off", !on);
    if (on) state.selected.add(+box.dataset.idx);
  });
  renderAll();
}

// ---------- rendering ----------
function renderAll() {
  applyChartDefaults();
  document.getElementById("asset-count").textContent =
    `— ${state.selected.size} of ${MVO.assets.length} selected`;
  document.getElementById("frontier-note").textContent = "";

  if (state.selected.size < 2) {
    if (frontierChart) { frontierChart.destroy(); frontierChart = null; }
    if (weightsChart) { weightsChart.destroy(); weightsChart = null; }
    renderTiles(null);
    document.getElementById("frontier-note").textContent =
      "Select at least 2 assets to build a frontier.";
    return;
  }

  const sub = subset();
  const { frontier, minVar, maxSharpe } = computeFrontier(sub);
  const optimal = state.optType === "sharpe" ? maxSharpe : minVar;

  renderTiles({ ...optimal, sub, rf: sub.rf });
  renderFrontier(sub, frontier, minVar, maxSharpe);
  renderWeights(sub, optimal);
}

function renderTiles(o) {
  const el = document.getElementById("tiles");
  el.innerHTML = "";
  const retLabel = state.muSource === "hist" ? "Expected return" : "Expected alpha";
  const tiles = o ? [
    { label: retLabel, value: fmtPct(o.ret) },
    { label: "Volatility", value: fmtPct(o.vol) },
    { label: "Sharpe", value: ((o.ret - o.rf) / o.vol).toFixed(2) },
    { label: "Holdings", value: o.w.filter(x => x > 0.001).length },
  ] : [{ label: retLabel, value: "–" }, { label: "Volatility", value: "–" },
       { label: "Sharpe", value: "–" }, { label: "Holdings", value: "0" }];
  for (const t of tiles) {
    const tile = document.createElement("div");
    tile.className = "tile";
    const l = document.createElement("div"); l.className = "label"; l.textContent = t.label;
    const v = document.createElement("div"); v.className = "value"; v.textContent = t.value;
    tile.append(l, v); el.appendChild(tile);
  }
}

function rampFor(t) {  // t in [0,1] -> blue sequential step
  const steps = ["--ramp-250", "--ramp-350", "--ramp-450", "--ramp-550", "--ramp-650"];
  return tok(steps[Math.min(steps.length - 1, Math.max(0, Math.floor(t * steps.length)))]);
}

function renderFrontier(sub, frontier, minVar, maxSharpe) {
  const retLabel = state.muSource === "hist"
    ? "Expected return (annualized)" : "Expected alpha (annualized)";
  document.getElementById("frontier-title").textContent =
    state.muSource === "hist" ? "Efficient frontier — historical mean returns"
                              : "Efficient frontier — model alpha";

  const datasets = [];

  if (state.showCloud) {
    const cloud = randomCloud(sub);
    const smin = Math.min(...cloud.map(p => p.s)), smax = Math.max(...cloud.map(p => p.s));
    datasets.push({
      type: "scatter", label: "Random portfolios",
      data: cloud.map(p => ({ x: p.x, y: p.y })),
      pointRadius: 2, pointHoverRadius: 2,
      backgroundColor: cloud.map(p => rampFor(smax > smin ? (p.s - smin) / (smax - smin) : 0.5) + "55"),
      order: 5,
    });
  }

  // frontier line (neutral ink so sector hues stay legible)
  datasets.push({
    type: "line", label: "Frontier",
    data: frontier.map(p => ({ x: p.vol, y: p.ret })),
    borderColor: tok("--ink"), borderWidth: 2.5, pointRadius: 0, tension: 0, order: 1,
  });

  // capital allocation line (only meaningful with a positive risk-free rate)
  if (state.optType === "sharpe" && sub.rf > 0) {
    const maxVol = Math.max(...frontier.map(p => p.vol), maxSharpe.vol) * 1.05;
    const slope = (maxSharpe.ret - sub.rf) / maxSharpe.vol;
    datasets.push({
      type: "line", label: "Capital allocation line",
      data: [{ x: 0, y: sub.rf }, { x: maxVol, y: sub.rf + slope * maxVol }],
      borderColor: tok("--muted"), borderWidth: 1, borderDash: [], pointRadius: 0, order: 2,
    });
  }

  // individual assets, colored by sector
  datasets.push({
    type: "scatter", label: "Assets",
    data: sub.vol.map((v, k) => ({ x: v, y: sub.ret[k], t: sub.assets[k], sec: sub.sectors[k] })),
    pointRadius: 6, pointHoverRadius: 8,
    backgroundColor: sub.sectors.map(s => sectorHex(s)),
    borderColor: tok("--surface"), borderWidth: 2, order: 3,
  });

  // min-variance (hollow ring) + max-Sharpe (star)
  datasets.push({
    type: "scatter", label: "Min variance",
    data: [{ x: minVar.vol, y: minVar.ret }],
    pointStyle: "circle", pointRadius: 9, pointHoverRadius: 11,
    backgroundColor: "transparent", borderColor: tok("--accent"), borderWidth: 2.5, order: 0,
  });
  datasets.push({
    type: "scatter", label: "Max Sharpe",
    data: [{ x: maxSharpe.vol, y: maxSharpe.ret }],
    pointStyle: "star", pointRadius: 11, pointHoverRadius: 13,
    backgroundColor: tok("--s3"), borderColor: tok("--s3"), borderWidth: 1, order: 0,
  });

  buildLegend(document.getElementById("frontier-legend"), [
    { label: "Frontier", color: tok("--ink") },
    { label: "Max Sharpe ★", color: tok("--s3") },
    { label: "Min variance ○", color: tok("--accent") },
    { label: "Assets (by sector)", color: tok("--muted"), shape: "rect" },
  ]);
  document.getElementById("frontier-note").textContent =
    "Each dot is one asset (colored by sector — see the toggles above). The frontier bulges up and to the "
    + "left of the assets: that gap is the benefit of diversification.";

  const cfg = {
    data: { datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: "nearest", intersect: true },
      scales: {
        x: {
          type: "linear", title: { display: true, text: "Volatility (annualized)", color: tok("--ink-2") },
          grid: { color: tok("--grid") }, border: { color: tok("--baseline") },
          ticks: { callback: v => (v * 100).toFixed(0) + "%" },
        },
        y: {
          title: { display: true, text: retLabel, color: tok("--ink-2") },
          grid: { color: tok("--grid") }, border: { display: false },
          ticks: { callback: v => (v * 100).toFixed(0) + "%" },
        },
      },
      plugins: {
        tooltip: {
          callbacks: {
            label: (item) => {
              const r = item.raw;
              const head = r.t ? `${r.t} (${r.sec})` : item.dataset.label;
              return ` ${head}: ${(r.y * 100).toFixed(1)}% ret, ${(r.x * 100).toFixed(1)}% vol`;
            },
          },
        },
      },
    },
  };
  if (frontierChart) frontierChart.destroy();
  frontierChart = new Chart(document.getElementById("frontier-chart"), cfg);
}

function renderWeights(sub, optimal) {
  document.getElementById("weights-title").textContent =
    (state.optType === "sharpe" ? "Max-Sharpe" : "Min-variance") + " portfolio weights";
  const rows = sub.assets
    .map((t, k) => ({ t, sec: sub.sectors[k], w: optimal.w[k] }))
    .filter(r => r.w > 0.001)
    .sort((a, b) => b.w - a.w);

  document.getElementById("weights-box").style.height = `${70 + rows.length * 30}px`;
  const cfg = {
    type: "bar",
    data: {
      labels: rows.map(r => r.t),
      datasets: [{
        data: rows.map(r => r.w * 100),
        backgroundColor: rows.map(r => sectorHex(r.sec)),
        borderRadius: { topRight: 4, bottomRight: 4 }, borderSkipped: "start", barThickness: 18,
      }],
    },
    options: {
      indexAxis: "y", responsive: true, maintainAspectRatio: false,
      layout: { padding: { right: 46 } },
      scales: {
        x: { grid: { color: tok("--grid") }, border: { display: false }, ticks: { callback: v => v + "%" } },
        y: { grid: { display: false }, border: { color: tok("--baseline") },
             ticks: { color: tok("--ink-2"), font: { weight: 600 } } },
      },
      plugins: {
        tooltip: { callbacks: { label: item => ` ${item.raw.toFixed(1)}%  (${rows[item.dataIndex].sec})` } },
      },
    },
    plugins: [{
      id: "wlabels",
      afterDatasetsDraw(chart) {
        const meta = chart.getDatasetMeta(0), ctx = chart.ctx;
        ctx.save(); ctx.fillStyle = tok("--ink-2"); ctx.font = "12px system-ui, sans-serif";
        ctx.textBaseline = "middle";
        meta.data.forEach((bar, i) => ctx.fillText(`${rows[i].w * 100 < 0.05 ? "<0.1" : (rows[i].w * 100).toFixed(1)}%`, bar.x + 8, bar.y));
        ctx.restore();
      },
    }],
  };
  if (weightsChart) weightsChart.destroy();
  weightsChart = new Chart(document.getElementById("weights-chart"), cfg);
}

init();
