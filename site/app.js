// Gallery page: loads index.json (built by scripts/build.py) and renders one card per theme.
const grid = document.getElementById("grid");
const status = document.getElementById("status");
const q = document.getElementById("q");
const tagBar = document.getElementById("tags");
const tpl = document.getElementById("card");
let themes = [];
let activeTag = null;

// fastfetch logo text: $1..$9 switch colour (and carry across lines), $$ is a literal dollar.
function renderLogo(pre, text, colors) {
  const lines = text.replace(/\n+$/, "").split("\n");
  let current = colors["1"] || null;
  let cols = 0;
  lines.forEach((line, n) => {
    let span = document.createElement("span");
    let width = 0;
    const flush = () => { if (span.textContent) { if (current) span.style.color = current; pre.append(span); } };
    for (let i = 0; i < line.length; i++) {
      if (line[i] === "$" && /[0-9$]/.test(line[i + 1] || "")) {
        const t = line[++i];
        if (t === "$") { span.textContent += "$"; width++; continue; }
        flush();
        current = colors[t] || null;
        span = document.createElement("span");
      } else {
        span.textContent += line[i];
        width++;
      }
    }
    flush();
    if (n < lines.length - 1) pre.append("\n");
    cols = Math.max(cols, width);
  });
  pre.style.setProperty("--cols", cols || 40);
}

function card(t) {
  const el = tpl.content.firstElementChild.cloneNode(true);
  const pre = el.querySelector(".ascii");
  const keys = el.querySelector(".keys");
  if (t.screenshot) {
    // A real screenshot beats the logo-only preview when the author sent one.
    const img = document.createElement("img");
    img.className = "shot";
    img.loading = "lazy";
    img.alt = `${t.name} in a terminal`;
    img.src = `themes/${encodeURIComponent(t.code)}/${encodeURIComponent(t.screenshot)}`;
    el.querySelector(".term").replaceChildren(img);
  } else if (t.logo) renderLogo(pre, t.logo, t.colors || {});
  else { pre.textContent = "(image or built-in logo)"; pre.classList.add("none"); }
  // A screenshot replaces the whole preview, key colour strip included.
  if (!t.screenshot) (t.keyColors || []).forEach(c => { const i = document.createElement("i"); i.style.background = c; keys.append(i); });
  el.querySelector(".name").textContent = `${t.name}`;
  const by = el.querySelector(".by");
  by.textContent = "by " + t.author;
  if (t.link) {
    const a = document.createElement("a");
    a.href = t.link;
    a.rel = "noopener";
    a.textContent = "source";
    by.append(" · ", a);
  }
  el.querySelector(".desc").textContent = t.description || "";
  el.querySelector(".card-tags").replaceChildren(...t.tags.map(g => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "tag";
    b.textContent = `#${g}`;
    b.addEventListener("click", () => setTag(g));
    return b;
  }));
  const btn = el.querySelector(".code");
  btn.querySelector("b").textContent = t.code;
  btn.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(`fastcat-tui get ${t.code}`); } catch { return; }
    btn.classList.add("done");
    setTimeout(() => btn.classList.remove("done"), 1200);
  });
  return el;
}

function matches(t, words) {
  if (activeTag && !t.tags.includes(activeTag)) return false;
  const hay = [t.code, t.name, t.author, t.description, ...t.tags].join(" ").toLowerCase();
  return words.every(w => hay.includes(w));
}

function setTag(g) {
  activeTag = activeTag === g ? null : g;
  drawTags();
  draw();
}

// Keep the search in the address bar so it can be linked (fastcat-tui shows these links too).
function syncUrl() {
  const params = new URLSearchParams();
  if (q.value.trim()) params.set("q", q.value.trim());
  if (activeTag) params.set("tag", activeTag);
  const search = params.toString();
  history.replaceState(null, "", search ? `?${search}` : location.pathname);
}

function draw() {
  syncUrl();
  const words = q.value.toLowerCase().split(/\s+/).filter(Boolean);
  const shown = themes.filter(t => matches(t, words));
  grid.replaceChildren(...shown.map(card));
  status.textContent = shown.length === themes.length ? `${themes.length} themes` : `${shown.length} of ${themes.length} themes`;
}

function drawTags() {
  const counts = {};
  themes.forEach(t => t.tags.forEach(g => (counts[g] = (counts[g] || 0) + 1)));
  const tags = Object.keys(counts).sort((a, b) => counts[b] - counts[a] || a.localeCompare(b)).slice(0, 24);
  tagBar.replaceChildren(...tags.map(g => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = g === activeTag ? "btn btn-primary" : "btn btn-default btn-ghost";
    b.textContent = `#${g}`;
    b.setAttribute("aria-pressed", String(g === activeTag));
    b.addEventListener("click", () => setTag(g));
    return b;
  }));
}

fetch("index.json", { cache: "no-cache" })
  .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
  .then(data => {
    themes = data.themes.sort((a, b) => a.name.localeCompare(b.name));
    const params = new URLSearchParams(location.search);
    if (params.get("q")) q.value = params.get("q");
    if (themes.some(t => t.tags.includes(params.get("tag")))) activeTag = params.get("tag");
    drawTags();
    draw();
  })
  .catch(e => { status.textContent = `could not load themes (${e.message})`; });

q.addEventListener("input", draw);
