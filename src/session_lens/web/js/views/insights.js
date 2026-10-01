import { api } from "../api.js";
import { fmtNum, fmtPct, sum } from "../lib.js";
import { h, clear, skeleton, errorBox, empty, stat } from "../ui.js";
import { stackedBars, lines } from "../charts.js";

const OUTCOMES = ["done", "abandoned", "stuck"];

export function render(root) {
  const ctrl = new AbortController();
  let interval = "day";
  let project = "";
  let by = "agent";

  const usageBox = h("section", null, h("h2", null, "Token usage"), skeleton(1));
  const trendBox = h("section", null, h("h2", null, "Trends"));
  const compareBox = h("section", null, h("h2", null, "Compare"));
  root.append(h("header", { class: "page-head" }, h("h1", null, "Insights")), usageBox, trendBox, compareBox);

  const guard = (box, title, fn) => {
    let latest = 0; // a slow older response must not overwrite a newer one
    return async () => {
    const mine = ++latest;
    clear(box).append(h("h2", null, title), skeleton(4));
    try {
      const content = await fn();
      if (mine !== latest) return;
      clear(box).append(h("h2", null, title), ...[].concat(content));
    } catch (e) {
      if (e.name === "AbortError" || mine !== latest) return;
      clear(box).append(h("h2", null, title), errorBox(e.message, loadAll[title]));
    }
    };
  };

  const loadUsage = guard(usageBox, "Token usage", async () => {
    const u = await api.usage(ctrl.signal);
    return h("dl", { class: "stats" },
      stat("Input tokens", fmtNum(u.input_tokens)), stat("Output tokens", fmtNum(u.output_tokens)),
      stat("Total tokens", fmtNum((u.input_tokens || 0) + (u.output_tokens || 0))), stat("Enrichments", fmtNum(u.enrichments)));
  });

  const loadTrends = guard(trendBox, "Trends", async () => {
    const rows = await api.trends({ interval, project }, ctrl.signal);
    const controls = h("div", { class: "filters inline" },
      h("div", { class: "field" }, h("label", { for: "t-interval" }, "Interval"),
        h("select", { id: "t-interval", onchange: (e) => { interval = e.target.value; loadTrends(); } },
          ["day", "week"].map((v) => h("option", { value: v, selected: v === interval }, v)))),
      h("div", { class: "field" }, h("label", { for: "t-project" }, "Project"),
        h("input", { id: "t-project", type: "text", value: project, onchange: (e) => { project = e.target.value.trim(); loadTrends(); } })));
    if (!rows.length) return [controls, empty("No sessions in this range", "Submit recordings to see trends.")];

    const buckets = rows.map((r) => r.bucket);
    const counts = stackedBars(rows.map((r) => ({ bucket: r.bucket, values: r.outcomes || {} })), OUTCOMES,
      `Sessions per ${interval} by outcome`);
    const rates = lines(buckets, [
      { name: "tool error rate", cls: "line-a", points: rows.map((r) => r.tool_error_rate ?? null) },
      { name: "avg frustration", cls: "line-b", points: rows.map((r) => r.avg_frustration ?? null) },
    ], `Tool error rate and average frustration per ${interval}`, (v) => v.toFixed(2));
    const legend = (items) => h("ul", { class: "legend" }, items.map(([cls, label]) => h("li", null, h("span", { class: `swatch ${cls}` }), label)));

    return [controls,
      h("div", { class: "cols-2" },
        h("figure", null, h("figcaption", null, `Sessions per ${interval}`), counts,
          legend(OUTCOMES.map((o) => [`seg-${o}`, o]))),
        h("figure", null, h("figcaption", null, "Quality signals"), rates,
          legend([["line-a", "Tool error rate"], ["line-b", "Average frustration"]]))),
      h("details", null, h("summary", null, "Data table"),
        h("div", { class: "table-wrap" }, h("table", { class: "table" },
          h("thead", null, h("tr", null, ["Bucket", "Sessions", "Done", "Abandoned", "Stuck", "Avg frustration", "Tool error rate"].map((t) => h("th", { scope: "col" }, t)))),
          h("tbody", null, rows.map((r) => h("tr", null,
            h("td", null, r.bucket), h("td", { class: "num" }, r.sessions ?? sum(r.outcomes)),
            ...OUTCOMES.map((o) => h("td", { class: "num" }, (r.outcomes || {})[o] || 0)),
            h("td", { class: "num" }, r.avg_frustration == null ? "" : r.avg_frustration.toFixed(2)),
            h("td", { class: "num" }, fmtPct(r.tool_error_rate))))))))];
  });

  const loadCompare = guard(compareBox, "Compare", async () => {
    const rows = await api.compare(by, ctrl.signal);
    const controls = h("div", { class: "seg-control", role: "group", "aria-label": "Compare by" },
      ["agent", "model"].map((v) => h("button", {
        type: "button", class: "btn", "aria-pressed": String(v === by),
        onclick: () => { by = v; loadCompare(); },
      }, `By ${v}`)));
    if (!rows.length) return [controls, empty("Nothing to compare yet")];
    const maxRate = Math.max(0.0001, ...rows.flatMap((r) => [r.tool_error_rate || 0, r.permission_denial_rate || 0]));
    const rate = (v) => h("td", { class: "rate" }, h("span", { class: "rate-bar", style: { width: `${((v || 0) / maxRate) * 100}%` } }), h("span", null, fmtPct(v)));
    return [controls, h("div", { class: "table-wrap" }, h("table", { class: "table" },
      h("thead", null, h("tr", null, [by, "Sessions", "Done", "Abandoned", "Stuck", "Tool error rate", "Permission denial rate", "Avg frustration"].map((t) => h("th", { scope: "col" }, t)))),
      h("tbody", null, rows.map((r) => h("tr", null,
        h("th", { scope: "row", class: "mono wrap" }, r.key || "unknown"), h("td", { class: "num" }, r.sessions),
        ...OUTCOMES.map((o) => h("td", { class: "num" }, (r.outcomes || {})[o] || 0)),
        rate(r.tool_error_rate), rate(r.permission_denial_rate),
        h("td", { class: "num" }, r.avg_frustration == null ? "" : r.avg_frustration.toFixed(2)))))))];
  });

  const loadAll = { "Token usage": loadUsage, Trends: loadTrends, Compare: loadCompare };
  loadUsage();
  loadTrends();
  loadCompare();
  return () => ctrl.abort();
}
