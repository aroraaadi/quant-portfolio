/* Transaction log — the ledger parsed from the monthly statements.
   All sizes are relative (% of the account); no dollar amounts are published. */

let TX, filter = "all";

async function init() {
  const content = document.getElementById("content");
  try { TX = await loadJSON("data/transactions.json"); }
  catch (err) { showError(content, err); return; }
  TX.sort((a, b) => b.date.localeCompare(a.date));
  const span = TX.length ? `${fmtDate(TX[TX.length - 1].date)} – ${fmtDate(TX[0].date)}` : "";
  document.getElementById("asof").textContent = span;
  renderTiles();
  renderFilters();
  renderTable();
}

function count(act) { return TX.filter(t => t.activity === act).length; }

function renderTiles() {
  const el = document.getElementById("tiles"); el.innerHTML = "";
  const defs = [
    ["Transactions", TX.length],
    ["Buys", count("buy")],
    ["Sells", count("sell")],
    ["Dividends", count("dividend")],
    ["Contributions", count("contribution")],
  ];
  for (const [label, value] of defs) {
    const t = document.createElement("div"); t.className = "tile";
    const l = document.createElement("div"); l.className = "label"; l.textContent = label;
    const v = document.createElement("div"); v.className = "value"; v.textContent = value;
    t.append(l, v); el.appendChild(t);
  }
}

function renderFilters() {
  const el = document.getElementById("filters"); el.innerHTML = "";
  const acts = ["all", ...[...new Set(TX.map(t => t.activity))].sort((a, b) => count(b) - count(a))];
  for (const a of acts) {
    const b = document.createElement("button");
    b.className = "filter-chip" + (a === filter ? " active" : "");
    b.textContent = a === "all" ? `All (${TX.length})` : `${a} (${count(a)})`;
    b.style.textTransform = a === "all" ? "none" : "capitalize";
    b.addEventListener("click", () => { filter = a; renderFilters(); renderTable(); });
    el.appendChild(b);
  }
}

function badgeClass(act) { return act === "buy" ? "act-buy" : act === "sell" ? "act-sell" : "act-other"; }

function renderTable() {
  const rows = filter === "all" ? TX : TX.filter(t => t.activity === filter);
  const maxSize = Math.max(...TX.map(t => t.size_pct || 0), 0.01);
  const tbody = document.querySelector("#tx-table tbody"); tbody.innerHTML = "";
  for (const t of rows) {
    const tr = document.createElement("tr");
    const d = document.createElement("td"); d.textContent = fmtDate(t.date); d.style.whiteSpace = "nowrap"; tr.appendChild(d);

    const a = document.createElement("td");
    const badge = document.createElement("span"); badge.className = "act-badge " + badgeClass(t.activity);
    badge.textContent = t.activity; a.appendChild(badge); tr.appendChild(a);

    const sec = document.createElement("td"); sec.textContent = t.description; tr.appendChild(sec);
    const c = document.createElement("td"); c.textContent = t.currency || ""; c.style.color = "var(--ink-2)"; tr.appendChild(c);

    const px = document.createElement("td"); px.className = "num";
    px.textContent = t.price != null ? t.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "–";
    tr.appendChild(px);

    const s = document.createElement("td");
    if (t.size_pct != null) {
      const wrap = document.createElement("span"); wrap.className = "size-bar-wrap";
      const track = document.createElement("span"); track.className = "size-bar-track";
      const bar = document.createElement("span"); bar.className = "size-bar";
      bar.style.width = `${Math.max(2, (t.size_pct / maxSize) * 100)}%`;
      bar.style.display = "block";
      track.appendChild(bar);
      const lbl = document.createElement("span"); lbl.textContent = (t.size_pct * 100).toFixed(1) + "%";
      lbl.style.cssText = "font-size:12px;color:var(--ink-2);font-variant-numeric:tabular-nums;min-width:40px";
      wrap.append(track, lbl); s.appendChild(wrap);
    } else { s.textContent = "–"; s.style.color = "var(--muted)"; }
    tr.appendChild(s);
    tbody.appendChild(tr);
  }
  document.getElementById("tx-note").textContent =
    `${rows.length} of ${TX.length} transactions. Size = the trade's value as a share of the account that month.`;
}

init();
