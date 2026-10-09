// The frame's behaviour, on bh-01's own components (vendor/bh-01/bh-01.js defines them all).
//
// - The activity bar picks which section's tree the sidebar shows; choosing the shown one again
//   closes the sidebar (ActivityBar's own toggle, wired to AppShell's sidebarOpen, as bh-01's
//   application-shell pattern has it). The tree's selected item is the page being read; a
//   choice in it goes to that page.
// - Narrow, measured from the frame's own parts (the main column would be narrower than twice
//   the sidebar): the sidebar starts closed, and opened it takes the width beside the activity bar.
// - Search is CommandPalette, opened with Ctrl+K or from the status bar, over MkDocs' search index.
// - The theme follows the system until the reader picks one; the pick is kept in localStorage
//   when the browser allows it, and the page is the same without it.
// - Code blocks get a copy button; a page opened at an anchor is scrolled to it once the frame
//   is drawn (the page scrolls inside AppShell's main region, not the document).
import "../vendor/bh-01/bh-01.js";

// Icons in bh-01's style (24 grid, 2px round stroke, no fill), registered as bh-01 asks an app to.
const ICONS = {
  home: '<path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10v10h13V10"/><path d="M10 20v-5h4v5"/>',
  terminal: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3"/><path d="M13 15h4"/>',
  blocks:
    '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>' +
    '<rect x="3" y="14" width="7" height="7" rx="1"/><path d="M17.5 14v7"/><path d="M14 17.5h7"/>',
  lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  pulse: '<path d="M3 12h4l3-7 4 14 3-7h4"/>',
  pencil: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
  branch:
    '<circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="7" r="2"/>' +
    '<path d="M6 7v10"/><path d="M18 9c0 4-4 6-11 8"/>',
};
const BhIcon = customElements.get("bh-icon");
for (const [name, svg] of Object.entries(ICONS)) BhIcon.register(name, svg);

const THEME_KEY = "bh-docs-theme";
const root = document.documentElement;
const shell = document.querySelector("bh-app-shell");
const bar = shell.querySelector("bh-activity-bar");
const panel = shell.querySelector("bh-sidebar-panel");
const header = panel.querySelector("bh-panel-header");
const trees = [...panel.querySelectorAll("bh-tree")];
const palette = document.querySelector("bh-command-palette");
const site = JSON.parse(document.getElementById("site-pages").textContent);
const base = new URL(site.base.endsWith("/") ? site.base : `${site.base}/`, location.href);
const here = bar.querySelector("bh-activity-item[data-current]")?.getAttribute("item-id") ?? "";

// ---- Sections and the sidebar ------------------------------------------------------------

function show(view) {
  for (const tree of trees) tree.hidden = tree.dataset.view !== view;
  const label = trees.find((tree) => tree.dataset.view === view)?.dataset.label ?? "";
  header.label = label;
  panel.setAttribute("aria-label", label);
}

function open(view) {
  for (const item of bar.querySelectorAll("bh-activity-item")) item.active = item.getAttribute("item-id") === view;
  bar.updateComplete.then(() => bar.setActive(view));
  if (view) show(view);
  shell.sidebarOpen = Boolean(view);
}

// The activity bar's width and the sidebar's, as bh-01 sizes them, measured on hidden copies
// (the frame's own have no box until AppShell draws its regions).
function measured(tag) {
  const probe = document.createElement(tag);
  probe.style.position = "absolute";
  probe.style.visibility = "hidden";
  document.body.append(probe);
  const width = probe.getBoundingClientRect().width;
  probe.remove();
  return width;
}
const activityWidth = measured("bh-activity-bar");
const sidebarWidth = measured("bh-sidebar-panel");
root.style.setProperty("--docs-activity-width", `${activityWidth}px`);
const isNarrow = () => window.innerWidth < activityWidth + sidebarWidth * 3;
let narrow = isNarrow();
root.toggleAttribute("data-narrow", narrow);
open(narrow ? "" : here);
show(here);

window.addEventListener("resize", () => {
  if (isNarrow() === narrow) return;
  narrow = !narrow;
  root.toggleAttribute("data-narrow", narrow);
  open(narrow ? "" : here);
});

bar.addEventListener("bh-activity-change", (event) => {
  const view = event.detail.id;
  if (view) show(view);
  shell.sidebarOpen = Boolean(view);
});

for (const tree of trees) {
  const page = tree.selected;
  tree.addEventListener("bh-select", (event) => {
    const value = event.detail.value;
    if (value.startsWith("group:")) {
      tree.selected = page; // a group opens or closes; the page being read stays the selected one
    } else if (value !== page) {
      location.href = value;
    }
  });
}

// ---- Search ----------------------------------------------------------------------------

const pages = site.pages.map((page) => ({
  id: page.url,
  label: page.title,
  ...(page.section !== page.title ? { category: page.section } : {}),
}));
const byUrl = new Map(site.pages.map((page) => [page.url, page]));
palette.items = pages;

let index = null;
const docs = () =>
  (index ??= fetch(new URL(site.index, base))
    .then((response) => (response.ok ? response.json() : { docs: [] }))
    .then((data) => data.docs ?? [])
    .catch(() => []));

const squash = (text) => text.replace(/\s+/g, " ").trim();

function excerpt(text, at, length) {
  const start = Math.max(0, at - 30);
  const end = Math.min(text.length, at + length + 50);
  return `${start > 0 ? "…" : ""}${text.slice(start, end).trim()}${end < text.length ? "…" : ""}`;
}

// Pages and sections whose title or text holds the query, titles first. Each label holds the
// query itself, so CommandPalette's own filter (a fuzzy match on the label) keeps it.
function results(query, entries) {
  const q = squash(query).toLowerCase();
  if (!q) return pages;
  const titled = [];
  const texted = [];
  const seen = new Set();
  for (const entry of entries) {
    const [url, anchor] = entry.location.split("#");
    const page = byUrl.get(url);
    if (!page) continue;
    const title = squash(entry.title);
    // a page's first heading carries the page's title: as a title match, it is the page
    const heading = anchor && title !== page.title ? title : "";
    const id = heading ? entry.location : url;
    if (seen.has(id)) continue;
    const name = heading ? `${page.title} / ${heading}` : page.title;
    const category = page.section !== page.title ? { category: page.section } : {};
    if (title.toLowerCase().includes(q)) {
      titled.push({ id, label: name, ...category });
      seen.add(id);
    } else if (anchor) {
      const text = squash(entry.text ?? "");
      const at = text.toLowerCase().indexOf(q);
      if (at >= 0) {
        texted.push({ id: entry.location, label: `${name}: ${excerpt(text, at, q.length)}`, ...category });
        seen.add(entry.location);
      }
    }
  }
  return [...titled, ...texted].slice(0, 30);
}

let latest = "";
palette.addEventListener("input", async (event) => {
  latest = event.composedPath()[0].value ?? "";
  const query = latest;
  const entries = await docs();
  if (query === latest) palette.items = results(query, entries);
});

palette.addEventListener("bh-open", () => {
  latest = "";
  palette.items = pages;
  docs();
});

palette.addEventListener("bh-execute", (event) => {
  location.href = new URL(event.detail.id, base).href;
});

// CommandPalette moves focus into its input on open but keeps no opener; bh-01's overlay rule
// returns focus to what opened it on close, so the page does that.
let opener = null;
function deepActive() {
  let element = document.activeElement;
  while (element?.shadowRoot?.activeElement) element = element.shadowRoot.activeElement;
  return element;
}

function search() {
  if (palette.open) return palette.close();
  opener = deepActive();
  palette.show();
}

palette.addEventListener("bh-close", () => {
  if (opener?.isConnected) opener.focus();
  opener = null;
});

document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && !event.altKey && !event.shiftKey && event.key.toLowerCase() === "k") {
    event.preventDefault();
    search();
  }
});

document.querySelector('[data-action="search"]').addEventListener("click", search);

// ---- Theme -------------------------------------------------------------------------------

const toggle = document.querySelector('[data-action="theme"]');
const system = window.matchMedia("(prefers-color-scheme: dark)");

function chosen() {
  try {
    const value = localStorage.getItem(THEME_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

function keep(theme) {
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // storage refused (a private window, blocked site data): the choice lasts this page
  }
}

function theme(name) {
  root.setAttribute("data-theme", name);
  toggle.setAttribute("aria-checked", String(name === "dark"));
}

theme(chosen() ?? (system.matches ? "dark" : "light"));
system.addEventListener("change", (event) => {
  if (!chosen()) theme(event.matches ? "dark" : "light");
});
toggle.addEventListener("click", () => {
  const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
  keep(next);
  theme(next);
});

// ---- The page ----------------------------------------------------------------------------

for (const block of document.querySelectorAll(".page-content .highlight, .page-content > pre")) {
  const pre = block.matches("pre") ? block : block.querySelector("pre");
  if (!pre) continue;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "copy-code";
  button.textContent = "Copy";
  button.setAttribute("aria-label", "Copy this code");
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(pre.textContent);
      button.textContent = "Copied";
    } catch {
      button.textContent = "Copy failed";
    }
    button.toggleAttribute("data-copied", true);
    setTimeout(() => {
      button.textContent = "Copy";
      button.toggleAttribute("data-copied", false);
    }, 1500);
  });
  block.append(button);
}

if (location.hash) {
  shell.updateComplete.then(() => {
    const target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
    target?.scrollIntoView();
  });
}
