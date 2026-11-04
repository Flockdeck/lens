import { parseHash } from "./lib.js";
import { h, clear } from "./ui.js";
import { loadConfig, onConfig } from "./config.js";
import { statusLine, statusDetails, isLocalOnly, isRemoteEnrichment } from "./lib.js";

const statusText = document.getElementById("status-text");
const statusBar = document.getElementById("statusbar");
onConfig((cfg) => {
  statusText.textContent = statusLine(cfg);
  statusBar.dataset.state = !cfg ? "unknown" : isRemoteEnrichment(cfg) ? "remote" : isLocalOnly(cfg) ? "local" : "unverified";
  const [first, second] = statusDetails(cfg);
  document.getElementById("status-detail-1").textContent = first;
  document.getElementById("status-detail-2").textContent = second;
});

const main = document.getElementById("main");
const nav = document.getElementById("nav");

// "Skip to content" points at #main so it works without scripts, but here the hash is the route:
// following it would send the router to its default page. Move the focus without touching the URL.
document.querySelector(".skip")?.addEventListener("click", (event) => {
  event.preventDefault();
  main.focus();
});

let cleanup = null;
let renderId = 0;

const ROUTES = {
  submit: () => import("./views/submit.js"),
  batches: () => import("./views/batch.js"),
  sessions: () => import("./views/sessions.js"),
  insights: () => import("./views/insights.js"),
  settings: () => import("./views/settings.js"),
};
const TITLES = { submit: "Submit", batches: "Batch", sessions: "Sessions", insights: "Insights", settings: "Settings" };

// A view that did not load (the server restarting, the network dropping) or threw while drawing
// would otherwise leave an empty page. The link reloads, since the same hash fires no event.
function showLoadError() {
  main.append(h("div", { class: "error-box", role: "alert" },
    h("p", null, "This page could not be loaded."),
    h("button", { type: "button", class: "btn", onclick: () => location.reload() }, "Reload")));
}

async function route() {
  loadConfig();
  const { parts, query } = parseHash(location.hash);
  let name = Object.hasOwn(ROUTES, parts[0]) ? parts[0] : "submit";
  const loader = ROUTES[name];
  if (name === "sessions" && parts[1]) name = "session";
  const id = ++renderId;
  if (cleanup) { try { cleanup(); } catch { /* ignore */ } cleanup = null; }
  clear(main);
  let mod;
  try {
    mod = await (name === "session" ? import("./views/session.js") : loader());
  } catch {
    if (id === renderId) showLoadError();
    return;
  }
  if (id !== renderId) return; // a newer navigation won
  const section = h("div", { class: "view" });
  main.append(section);
  try {
    cleanup = mod.render(section, { parts, query }) || null;
  } catch {
    clear(main);
    showLoadError();
    return;
  }
  document.title = `${TITLES[name] || "Session"} - lens`;
  for (const a of nav.querySelectorAll("a")) {
    const on = a.getAttribute("href").split("/")[1] === (parts[0] || "submit");
    if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  }
  main.focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

window.addEventListener("hashchange", route);

route();
