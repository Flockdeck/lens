import { getToken, setToken } from "./api.js";
import { parseHash } from "./lib.js";
import { h, clear } from "./ui.js";

const main = document.getElementById("main");
const nav = document.getElementById("nav");
let cleanup = null;
let renderId = 0;

const ROUTES = {
  submit: () => import("./views/submit.js"),
  batches: () => import("./views/batch.js"),
  sessions: () => import("./views/sessions.js"),
  insights: () => import("./views/insights.js"),
};
const TITLES = { submit: "Submit", batches: "Batch", sessions: "Sessions", insights: "Insights" };

async function route() {
  if (!getToken()) return showTokenPrompt();
  const { parts, query } = parseHash(location.hash);
  let name = parts[0] in ROUTES ? parts[0] : "submit";
  const loader = ROUTES[name];
  if (name === "sessions" && parts[1]) name = "session";
  const id = ++renderId;
  if (cleanup) { try { cleanup(); } catch { /* ignore */ } cleanup = null; }
  clear(main);
  const mod = await (name === "session" ? import("./views/session.js") : loader());
  if (id !== renderId) return; // a newer navigation won
  const section = h("div", { class: "view" });
  main.append(section);
  cleanup = mod.render(section, { parts, query }) || null;
  document.title = `${TITLES[name] || "Session"} - session-lens`;
  for (const a of nav.querySelectorAll("a")) {
    const on = a.getAttribute("href").split("/")[1] === (parts[0] || "submit");
    if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  }
  main.focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

function showTokenPrompt(message) {
  if (cleanup) { cleanup(); cleanup = null; }
  renderId += 1;
  nav.hidden = true;
  const input = h("input", { id: "token", type: "password", autocomplete: "off", required: true, "aria-describedby": "token-help" });
  const form = h("form", { class: "token-form" },
    h("h1", null, "API token"),
    h("p", { id: "token-help", class: "muted" }, "Enter the API token for this server. It is kept in this browser tab only and cleared when you close it."),
    message ? h("p", { class: "problem", role: "alert" }, message) : null,
    h("div", { class: "field" }, h("label", { for: "token" }, "Token"), input),
    h("button", { class: "btn btn-primary", type: "submit" }, "Continue"));
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    setToken(input.value.trim());
    nav.hidden = false;
    route();
  });
  clear(main).append(form);
  input.focus();
}

window.addEventListener("hashchange", route);
window.addEventListener("auth-required", () => showTokenPrompt("That token was not accepted."));

document.getElementById("signout").addEventListener("click", () => { setToken(""); showTokenPrompt(); });
document.getElementById("theme").addEventListener("click", () => {
  const root = document.documentElement;
  const dark = (root.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")) === "dark";
  root.dataset.theme = dark ? "light" : "dark";
  try { localStorage.setItem("session-lens.theme", root.dataset.theme); } catch { /* ignore */ }
});

route();
