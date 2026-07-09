/* Blog: list posts from posts/index.json; render one with marked + DOMPurify. */

const FRONT_MATTER = /^---\s*\n([\s\S]*?)\n---\s*\n/;

async function init() {
  const content = document.getElementById("content");
  const slug = new URLSearchParams(location.search).get("post");
  try {
    if (slug) await renderPost(content, slug);
    else await renderList(content);
  } catch (err) {
    showError(content, err);
  }
}

async function renderList(content) {
  const posts = await loadJSON("posts/index.json");
  content.innerHTML = "";
  const h1 = document.createElement("h1");
  h1.textContent = "Market thoughts";
  const sub = document.createElement("p");
  sub.className = "sub";
  sub.textContent = "Occasional notes on the portfolio, its signals, and the market.";
  content.append(h1, sub);

  const card = document.createElement("div");
  card.className = "card post-list";
  if (!posts.length) {
    const empty = document.createElement("p");
    empty.className = "sub";
    empty.textContent = "No posts yet.";
    card.appendChild(empty);
  }
  for (const p of posts) {
    const row = document.createElement("div");
    row.className = "post-row";
    const date = document.createElement("div");
    date.className = "date";
    date.textContent = p.date ? fmtDate(p.date) : "";
    const title = document.createElement("a");
    title.className = "title";
    title.href = `blog.html?post=${encodeURIComponent(p.slug)}`;
    title.textContent = p.title;
    const summary = document.createElement("div");
    summary.className = "summary";
    summary.textContent = p.summary || "";
    row.append(date, title, summary);
    card.appendChild(row);
  }
  content.appendChild(card);
}

async function renderPost(content, slug) {
  if (!/^[\w-]+$/.test(slug)) throw new Error("bad post name");
  const res = await fetch(`posts/${slug}.md`);
  if (!res.ok) throw new Error(`post not found (HTTP ${res.status})`);
  let md = await res.text();

  let title = slug.replace(/-/g, " ");
  let date = "";
  const fm = md.match(FRONT_MATTER);
  if (fm) {
    md = md.slice(fm[0].length);
    for (const line of fm[1].split("\n")) {
      const idx = line.indexOf(":");
      if (idx < 0) continue;
      const key = line.slice(0, idx).trim();
      const value = line.slice(idx + 1).trim();
      if (key === "title") title = value;
      if (key === "date") date = value;
    }
  }
  document.title = `${title} — Quant Portfolio`;

  content.innerHTML = "";
  const back = document.createElement("a");
  back.className = "back";
  back.href = "blog.html";
  back.textContent = "← All posts";
  const h1 = document.createElement("h1");
  h1.textContent = title;
  const sub = document.createElement("p");
  sub.className = "sub";
  sub.textContent = date ? fmtDate(date) : "";

  const card = document.createElement("div");
  card.className = "card post-body";
  card.innerHTML = DOMPurify.sanitize(marked.parse(md));
  content.append(back, h1, sub, card);
}

init();
