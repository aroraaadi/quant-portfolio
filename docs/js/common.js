/* Shared helpers: token access, data fetch, Chart.js defaults, theme re-render. */

function tok(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

async function loadJSON(path) {
  // Pages in subfolders (my/, research/) set window.ASSET_BASE = "../" so shared
  // data under docs/data/ resolves regardless of page depth.
  const full = (window.ASSET_BASE || "") + path;
  const res = await fetch(full);
  if (!res.ok) throw new Error(`${full}: HTTP ${res.status}`);
  return res.json();
}

function showError(el, err) {
  el.innerHTML = "";
  const box = document.createElement("div");
  box.className = "error-box";
  box.textContent = `Failed to load data — ${err.message}`;
  el.appendChild(box);
}

function fmtPct(x, dp = 1) {
  return x == null ? "–" : (x * 100).toFixed(dp) + "%";
}

function fmtDate(iso) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

/* Categorical slot for a ticker: fixed order of first appearance, never cycled.
   Slot 9+ folds into "Other" (muted gray). */
const SLOT_VARS = ["--s1", "--s2", "--s3", "--s4", "--s5", "--s6", "--s7", "--s8"];

function applyChartDefaults() {
  Chart.defaults.font.family = 'system-ui, -apple-system, "Segoe UI", sans-serif';
  Chart.defaults.font.size = 12;
  Chart.defaults.color = tok("--muted");
  Chart.defaults.borderColor = tok("--grid");
  Chart.defaults.plugins.legend.display = false; // legends are our own HTML
  Chart.defaults.plugins.tooltip.backgroundColor = tok("--ink");
  Chart.defaults.plugins.tooltip.titleColor = tok("--page");
  Chart.defaults.plugins.tooltip.bodyColor = tok("--page");
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
  Chart.defaults.plugins.tooltip.boxPadding = 4;
  Chart.defaults.animation = false;
}

/* Re-render charts when the OS theme flips (tokens change under us). */
function onThemeChange(rerender) {
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", rerender);
}

function buildLegend(el, items) {
  el.innerHTML = "";
  for (const it of items) {
    const key = document.createElement("span");
    key.className = "key";
    const swatch = document.createElement("span");
    swatch.className = it.shape === "rect" ? "swatch-rect" : "swatch-line";
    if (it.shape === "rect") swatch.style.background = it.color;
    else swatch.style.borderTopColor = it.color;
    const label = document.createElement("span");
    label.textContent = it.label;
    key.append(swatch, label);
    el.appendChild(key);
  }
}

/* Vertical crosshair that snaps to the hovered index (line charts). */
const crosshairPlugin = {
  id: "crosshair",
  afterDraw(chart) {
    const active = chart.tooltip?.getActiveElements();
    if (!active || !active.length) return;
    const x = active[0].element.x;
    const { top, bottom } = chart.chartArea;
    const ctx = chart.ctx;
    ctx.save();
    ctx.strokeStyle = tok("--baseline");
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, top);
    ctx.lineTo(x, bottom);
    ctx.stroke();
    ctx.restore();
  },
};
