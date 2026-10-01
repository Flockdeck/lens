import { api } from "../api.js";
import { fmtDate, fmtDuration, fmtNum } from "../lib.js";
import { h, clear, badge, skeleton, errorBox, empty } from "../ui.js";

export const CATEGORIES = ["bugfix", "feature", "refactor", "exploration", "docs", "tests", "ops", "other"];
export const OUTCOMES = ["done", "abandoned", "stuck"];
const PAGE = 25;
const FILTERS = ["project", "agent", "model", "category", "outcome", "from", "to"];

// Distinct project/agent/model values seen so far, offered as suggestions in the filter inputs.
const seen = { project: new Set(), agent: new Set(), model: new Set() };

export function render(root, { query }) {
  const ctrl = new AbortController();
  const page = Math.max(1, Number(query.page) || 1);

  const field = (name, label, control, help) =>
    h("div", { class: "field" }, h("label", { for: `f-${name}` }, label), control,
      help ? h("span", { id: `h-${name}`, class: "muted small" }, help) : null);
  const text = (name, label) => {
    const list = h("datalist", { id: `dl-${name}` }, [...seen[name]].sort().map((v) => h("option", { value: v })));
    return field(name, label, h("div", null,
      h("input", { id: `f-${name}`, name, type: "text", value: query[name] || "", list: `dl-${name}`, autocomplete: "off" }), list));
  };
  const select = (name, label, options) =>
    field(name, label, h("select", { id: `f-${name}`, name },
      h("option", { value: "" }, "Any"),
      options.map((o) => h("option", { value: o, selected: query[name] === o }, o))));
  const date = (name, label) =>
    field(name, label, h("input", {
      id: `f-${name}`, name, type: "date", value: query[name] || "", "aria-describedby": `h-${name}`,
    }), "Inclusive, UTC day");

  const form = h("form", { class: "filters", role: "search", "aria-label": "Filter sessions" },
    text("project", "Project"), text("agent", "Agent"), text("model", "Model"),
    select("category", "Category", CATEGORIES), select("outcome", "Outcome", OUTCOMES),
    date("from", "From"), date("to", "To"),
    h("div", { class: "row filter-actions" },
      h("button", { class: "btn btn-primary", type: "submit" }, "Apply"),
      h("button", { class: "btn", type: "button", onclick: () => { location.hash = "#/sessions"; } }, "Reset")));
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    go({ ...pick(new FormData(form)), page: 1 });
  });

  const results = h("div", { "aria-live": "polite" });
  root.append(h("header", { class: "page-head" }, h("h1", null, "Sessions")), form, results, skeleton(6));

  function pick(fd) {
    const out = {};
    for (const k of FILTERS) if (fd.get(k)) out[k] = fd.get(k);
    return out;
  }
  function go(q) {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(q)) if (v && !(k === "page" && Number(v) === 1)) p.set(k, v);
    const s = p.toString();
    location.hash = `#/sessions${s ? `?${s}` : ""}`;
  }

  async function load() {
    const params = {};
    for (const k of FILTERS) if (query[k]) params[k] = query[k];
    try {
      const data = await api.listSessions({ ...params, limit: PAGE, offset: (page - 1) * PAGE }, ctrl.signal);
      root.querySelector(".skeleton")?.remove();
      for (const s of data.items) for (const k of Object.keys(seen)) if (s[k]) seen[k].add(s[k]);
      for (const k of Object.keys(seen)) {
        const dl = form.querySelector(`#dl-${k}`);
        if (dl) dl.replaceChildren(...[...seen[k]].sort().map((v) => h("option", { value: v })));
      }
      drawResults(data);
    } catch (e) {
      if (e.name === "AbortError") return;
      root.querySelector(".skeleton")?.remove();
      clear(results).append(errorBox(e.message, () => { clear(results); root.append(skeleton(6)); load(); }));
    }
  }

  function drawResults({ total, items }) {
    clear(results);
    const pages = Math.max(1, Math.ceil(total / PAGE));
    const link = (p, label, disabled) => {
      const q = { ...Object.fromEntries(FILTERS.filter((k) => query[k]).map((k) => [k, query[k]])), page: p };
      const sp = new URLSearchParams();
      for (const [k, v] of Object.entries(q)) if (!(k === "page" && v === 1)) sp.set(k, v);
      return disabled
        ? h("span", { class: "btn", "aria-disabled": "true" }, label)
        : h("a", { class: "btn", href: `#/sessions${sp.toString() ? `?${sp}` : ""}` }, label);
    };
    if (!items.length) {
      results.append(total
        ? empty("No sessions on this page", `There are ${fmtNum(total)} sessions in ${pages} page${pages === 1 ? "" : "s"}.`,
          h("div", { class: "row" }, link(1, "First page", false), link(pages, "Last page", false)))
        : empty("No sessions match", "Adjust the filters, or submit recordings to get started.",
          h("a", { class: "btn", href: "#/submit" }, "Submit recordings")));
      return;
    }
    results.append(
      h("p", { class: "muted" }, `${fmtNum(total)} session${total === 1 ? "" : "s"}`),
      h("div", { class: "table-wrap" }, h("table", { class: "table table-rows" },
        h("thead", null, h("tr", null,
          ["Started", "Project", "Agent", "Model", "Category", "Outcome", "Frustration", "Duration", "Summary"]
            .map((t) => h("th", { scope: "col" }, t)))),
        h("tbody", null, items.map((s) => h("tr", null,
          h("td", { class: "nowrap" }, h("a", { href: `#/sessions/${encodeURIComponent(s.id)}` }, fmtDate(s.started_at) || "Open")),
          h("td", { class: "wrap" }, s.project || ""),
          h("td", null, s.agent || ""),
          h("td", { class: "mono" }, s.model || ""),
          h("td", null, s.category || ""),
          h("td", null, s.outcome ? badge(s.outcome) : ""),
          h("td", { class: "num" }, s.frustration == null ? "" : s.frustration.toFixed(2)),
          h("td", { class: "num nowrap" }, fmtDuration(s.duration_seconds ?? (s.metrics && s.metrics.duration_seconds))),
          h("td", { class: "summary-cell" }, s.summary || "")))))),
      h("nav", { class: "row pager", "aria-label": "Pagination" },
        link(page - 1, "Previous", page <= 1), h("span", { class: "muted" }, `Page ${page} of ${pages}`),
        link(page + 1, "Next", page >= pages)));
  }

  load();
  return () => ctrl.abort();
}
