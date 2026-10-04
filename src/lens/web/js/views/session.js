import { api, ApiError } from "../api.js";
import { getConfig, loadConfig } from "../config.js";
import { asList, expiredText, fmtBytes, fmtDate, fmtDuration, fmtNum, fmtPct } from "../lib.js";
import { h, clear, append, info, badge, skeleton, errorBox, empty, stat, toast, confirmDialog, withBusy } from "../ui.js";

const EVENT_PAGE = 100;

export function render(root, { parts, query }) {
  const id = parts[1];
  const ctrl = new AbortController();
  const host = h("div");
  let rawGone = false; // set when the API says the raw recording has expired (410)
  let current = null;
  let activeTab = (query && query.tab) || "analysis"; // kept across a reload of the data
  root.append(host, skeleton(8));

  async function load() {
    try {
      const [s] = await Promise.all([api.getSession(id, ctrl.signal), loadConfig()]);
      root.querySelector(".skeleton")?.remove();
      draw(s);
    } catch (e) {
      if (e.name === "AbortError") return;
      root.querySelector(".skeleton")?.remove();
      if (e instanceof ApiError && e.status === 404) {
        clear(host).append(empty("Session not found", "It may have been deleted.", h("a", { class: "btn", href: "#/sessions" }, "Back to sessions")));
      } else {
        clear(host).append(errorBox(e.message, () => { root.append(skeleton(8)); load(); }));
      }
    }
  }

  function draw(s) {
    current = s;
    const enr = s.enrichment || null;
    const m = s.metrics || {};
    const risks = s.risky_actions || [];
    const tabs = [
      { key: "analysis", label: "Analysis", llm: true, build: () => enr ? enrichmentSection(enr) : h("section", { class: "llm-panel" }, heading("Analysis", FROM_LLM), empty("Not enriched yet", "Use Re-enrich to run it now.")) },
      { key: "metrics", label: "Metrics", build: () => h("div", null, metricsSection(m), warningsSection(s.warnings, s.completeness)) },
      { key: "risks", label: `Risky actions (${risks.length})`, build: () => risksSection(s, enr) },
      { key: "files", label: "Files", build: () => filesSection(s.files_touched) },
      { key: "events", label: "Raw events", build: () => eventsSection(s) },
    ];
    if (!tabs.some((t) => t.key === activeTab)) activeTab = "analysis";
    // `append` skips null sections; the native Element.append would write the text "null".
    append(clear(host), [header(s, enr), tabset(tabs)]);
  }

  // An ARIA tab set. A panel is built the first time its tab opens and then kept (hidden), so the
  // raw-events list and what was scrolled to survive switching tabs. The tab is in the URL.
  function tabset(tabs) {
    const list = h("div", { class: "tabs", role: "tablist", "aria-label": "Session details" });
    const panels = new Map();
    const buttons = new Map();

    function show(key, focus) {
      activeTab = key;
      for (const t of tabs) {
        const on = t.key === key;
        buttons.get(t.key).setAttribute("aria-selected", on ? "true" : "false");
        buttons.get(t.key).tabIndex = on ? 0 : -1;
        if (on && !panels.has(t.key)) {
          const p = h("div", { role: "tabpanel", id: `panel-${t.key}`, "aria-labelledby": `tab-${t.key}`, tabindex: "0", class: "tabpanel" }, t.build());
          panels.set(t.key, p);
          wrap.append(p);
        }
        if (panels.has(t.key)) panels.get(t.key).hidden = !on;
      }
      if (focus) buttons.get(key).focus();
      history.replaceState(null, "", `#/sessions/${encodeURIComponent(id)}?tab=${key}`); // no hashchange
    }

    for (const t of tabs) {
      const b = h("button", {
        type: "button", role: "tab", id: `tab-${t.key}`, "aria-controls": `panel-${t.key}`, class: `tab${t.llm ? " tab-llm" : ""}`,
        onclick: () => show(t.key, false),
        onkeydown: (e) => {
          const at = tabs.findIndex((x) => x.key === t.key);
          const go = { ArrowRight: at + 1, ArrowLeft: at - 1, Home: 0, End: tabs.length - 1 }[e.key];
          if (go === undefined) return;
          e.preventDefault();
          show(tabs[(go + tabs.length) % tabs.length].key, true);
        },
      }, t.llm ? h("span", { class: "tab-mark", "aria-hidden": "true" }, "✦") : null, t.llm ? " " : null, t.label, t.llm ? h("span", { class: "visually-hidden" }, " (written by the lens LLM)") : null);
      buttons.set(t.key, b);
      list.append(b);
    }
    const wrap = h("div", { class: "tabpanels" });
    show(activeTab, false);
    return h("div", null, list, wrap);
  }

  function header(s, enr) {
    const gone = rawGone || s.raw_available === false;
    const reenrich = h("button", {
      type: "button", class: "btn", disabled: gone, "aria-describedby": gone ? "raw-expired" : null,
    }, "Re-enrich");
    reenrich.addEventListener("click", () => withBusy(reenrich, async () => {
      try {
        await api.enrichSession(id);
        toast("Re-enriched");
        await load();
      } catch (e) {
        if (e instanceof ApiError && e.status === 410) { rawGone = true; draw(current); return; }
        toast(e.message, "error");
      }
    }));
    const del = h("button", { type: "button", class: "btn btn-danger-quiet" }, "Delete session");
    del.addEventListener("click", async () => {
      const ok = await confirmDialog("Delete this session?",
        "The session, its raw recording and its enrichment are removed. This cannot be undone.", "Delete");
      if (!ok) return;
      await withBusy(del, async () => {
        try {
          await api.deleteSession(id);
          toast("Session deleted");
          location.hash = "#/sessions";
        } catch (e) { toast(e.message, "error"); }
      });
    });
    const out = (enr && enr.outcome) || s.outcome;
    const cat = (enr && enr.category) || s.category;
    return h("header", { class: "page-head" },
      h("p", { class: "crumb" }, h("a", { href: "#/sessions" }, "Sessions")),
      h("h1", null, s.project || "Session"),
      h("div", { class: "row" },
        out ? badge(out) : null, enr && out ? info("Outcome") : null,
        cat ? h("span", { class: "tag" }, cat) : null, enr && cat ? info("Category") : null,
        s.completeness ? badge(s.completeness.replace("_", " "), `c-${s.completeness}`) : null,
        s.completeness ? info("Completeness") : null),
      enr ? h("p", { class: "muted small" }, "Outcome and category are the lens LLM's. Completeness and the details below are from the recording.") : null,
      h("dl", { class: "meta" },
        meta("Agent", s.agent), meta(models(s).length > 1 ? "Agent models" : "Agent model", models(s).join(" \u2192 ")),
        meta("Pane", s.pane_name || s.pane),
        meta("Started", fmtDate(s.started_at)), meta("Ended", fmtDate(s.ended_at)),
        meta("Session", s.recording_session, true)),
      h("div", { class: "row" }, reenrich, del),
      gone ? h("p", { id: "raw-expired", class: "muted small" }, expiredText(getConfig())) : null);
  }

  // Where a block comes from: the recording itself (parsed, rules) or the LLM lens ran.
  const FROM_RECORDING = "From the recording";
  const FROM_LLM = "lens LLM";
  const origin = (kind) => h("span", { class: "origin-wrap" }, h("span", { class: `origin origin-${kind === FROM_LLM ? "llm" : "rec"}` }, kind), info(kind));
  const heading = (title, kind) => h("div", { class: "section-head" }, h("h2", null, title), origin(kind));

  // The metrics list every model used; sessions stored before that was added only have the first.
  const models = (s) => ((s.metrics && s.metrics.models) || []).length ? s.metrics.models : (s.model ? [s.model] : []);

  const meta = (k, v, mono) => (v ? h("div", null, h("dt", null, k, info(k)), h("dd", { class: mono ? "mono wrap" : "" }, v)) : null);

  function enrichmentSection(e) {
    return h("section", { class: "llm-panel" }, heading("Analysis", FROM_LLM),
      h("p", { class: "muted small" }, "Written by a model lens ran over this session's digest. None of it is in the recording."),
      h("p", { class: "lead" }, e.summary || ""),
      h("dl", { class: "stats" },
        stat("Frustration", e.frustration == null ? "n/a" : e.frustration.toFixed(2), "0 calm, 1 high. The LLM's estimate"),
        stat("Prompt version", e.prompt_version || "n/a", "of lens's analysis prompt")),
      h("h3", null, "What this analysis cost"),
      h("dl", { class: "stats" },
        stat("Analysis model", e.model || "n/a", "the model that wrote this"),
        stat("Tokens in", fmtNum(e.input_tokens), "sent to it"), stat("Tokens out", fmtNum(e.output_tokens), "it wrote")),
      modelFitBlock(e),
      stuckList(e),
      e.prompt_feedback ? h("div", { class: "note" }, h("h3", null, "Prompt feedback", info("Prompt feedback")), h("p", null, e.prompt_feedback)) : null);
  }

  const FIT = {
    well_matched: ["Well matched", "\u2713", "done"],
    overpowered: ["Probably more than needed", "\u25B2", "stuck"],
    underpowered: ["Probably not enough", "\u25A0", "failed"],
    unclear: ["Can't tell", "\u25CB", "queued"],
  };

  // Was the agent's model a sensible choice? The LLM's estimate; the model itself is from the recording.
  function modelFitBlock(e) {
    const used = current ? models(current).join(" \u2192 ") : "";
    const body = e.model_fit == null
      ? h("p", { class: "muted" }, "Not assessed. This analysis was made before lens judged model fit. Re-enrich to add it.")
      : [h("p", null, h("span", { class: `badge badge-${FIT[e.model_fit][2]}` },
          h("span", { class: "glyph", "aria-hidden": "true" }, FIT[e.model_fit][1]), FIT[e.model_fit][0])),
        e.model_fit_reason ? h("p", null, e.model_fit_reason) : null];
    return h("div", { class: "model-fit" },
      h("h3", null, "Was the model a good fit?", info("Model fit")),
      h("p", { class: "muted small" }, used ? `The agent used ${used}.` : "The recording does not say which model the agent used."),
      body);
  }

  function stuckList(e) {
    const pts = e.stuck_points || [];
    if (!pts.length) return null;
    return h("div", null, h("h3", null, `Stuck points (${pts.length})`, info("Stuck points")),
      h("ol", { class: "plain-list" }, pts.map((p) => h("li", null, p.description, p.approx_seq != null ? h("span", { class: "muted" }, ` (around event ${p.approx_seq})`) : null))));
  }

  function bars(obj, fmt = (v) => v) {
    const entries = Object.entries(obj || {}).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
    if (!entries.length) return h("p", { class: "muted" }, "None recorded");
    const max = Math.max(...entries.map(([, v]) => v));
    return h("ul", { class: "bars" }, entries.map(([k, v]) => h("li", null,
      h("span", { class: "bar-label" }, k),
      h("span", { class: "bar", style: { width: `${Math.max(2, (v / max) * 100)}%` } }),
      h("span", { class: "bar-value" }, fmt(v)))));
  }

  function metricsSection(m) {
    const p = m.permission || {};
    return h("section", null, heading("Metrics", FROM_RECORDING),
      h("dl", { class: "stats" },
        stat("Duration", fmtDuration(m.duration_seconds) || "n/a"), stat("Turns", fmtNum(m.turns ?? 0)),
        stat("Tool calls", fmtNum(m.tool_calls ?? 0)),
        stat("Tool errors", fmtNum(m.tool_errors ?? 0), m.tool_calls ? fmtPct(m.tool_errors / m.tool_calls) : ""),
        stat("Interrupted", fmtNum(m.tool_interrupted ?? 0)), stat("Unpaired calls", fmtNum(m.unpaired_calls ?? 0)),
        stat("Redacted lines", fmtNum(m.redacted_lines ?? 0)), stat("Clipped lines", fmtNum(m.clipped_lines ?? 0))),
      h("div", { class: "cols" },
        h("div", null, h("h3", null, "Tool mix", info("Tool mix")), bars(m.tool_mix)),
        h("div", null, h("h3", null, "Permissions", info("Permissions")), bars(p), p.prompts ? null : h("p", { class: "muted small" }, "No permission prompts")),
        h("div", null, h("h3", null, "Time in each status", info("Time in each status")), bars(m.status_seconds, fmtDuration))));
  }

  function risksSection(s, enr) {
    const risks = s.risky_actions || [];
    const notes = new Map(((enr && enr.risk_notes) || []).map((n) => [n.seq, n.explanation]));
    return h("section", null, heading(`Risky actions (${risks.length})`, FROM_RECORDING),
      h("p", { class: "muted small" }, "Detected by rules over the recording. The Note column is written by the lens LLM."),
      !risks.length ? h("p", { class: "muted" }, "No risky actions detected.")
        : h("div", { class: "table-wrap" }, h("table", { class: "table" },
          h("thead", null, h("tr", null, ["Seq", "Severity", "Tool", "Action", "Rule", "Note (LLM)"].map((t) => h("th", { scope: "col" }, t, info(t))))),
          h("tbody", null, risks.map((r) => h("tr", null,
            h("td", { class: "num" }, r.seq), h("td", null, badge(r.severity, `sev-${r.severity}`)), h("td", null, r.tool),
            h("td", { class: "mono wrap" }, r.summary), h("td", { class: "mono" }, r.rule), h("td", { class: "wrap" }, notes.get(r.seq) || "")))))));
  }

  function filesSection(f) {
    f = f || {};
    const group = (title, list) => h("details", { class: "files" },
      h("summary", null, `${title} (${(list || []).length})`),
      (list || []).length ? h("ul", { class: "mono plain-list" }, list.map((x) => h("li", { class: "wrap" }, x))) : h("p", { class: "muted" }, "None"));
    return h("section", null, heading("Files touched", FROM_RECORDING), group("Edited", f.edited), group("Read", f.read), group("Commands", f.commands));
  }

  function warningsSection(warnings, completeness) {
    const list = warnings || [];
    if (!list.length && (!completeness || completeness === "clean")) return null;
    return h("section", null, heading("Parse warnings", FROM_RECORDING),
      completeness && completeness !== "clean" ? h("p", null, `Recording completeness: ${completeness.replace("_", " ")}.`) : null,
      list.length ? h("ul", { class: "plain-list" }, list.map((w) => h("li", null, w))) : null);
  }

  function eventsSection(s) {
    if (rawGone || s.raw_available === false) {
      return h("section", null, heading("Raw events", FROM_RECORDING), h("p", { class: "muted" }, expiredText(getConfig())));
    }
    const list = h("div", { class: "events" });
    const more = h("button", { type: "button", class: "btn" }, "Load more events");
    const status = h("p", { class: "muted", "aria-live": "polite" });
    let afterSeq = 0;
    let started = false;
    let count = 0;

    async function next() {
      await withBusy(more, async () => {
        try {
          const data = await api.getEvents(id, { after_seq: afterSeq, limit: EVENT_PAGE }, ctrl.signal);
          const evs = asList(data);
          for (const ev of evs) {
            list.append(eventRow(ev));
            if (typeof ev.seq === "number") afterSeq = Math.max(afterSeq, ev.seq);
          }
          // The API returns {items, next_after_seq}; null means this was the last page.
          const next = data && !Array.isArray(data) ? data.next_after_seq : undefined;
          if (typeof next === "number") afterSeq = next;
          count += evs.length;
          status.textContent = `${count} event${count === 1 ? "" : "s"} loaded`;
          more.hidden = next === null || (next === undefined && evs.length < EVENT_PAGE);
          if (!count) status.textContent = "No events in this recording.";
        } catch (e) {
          if (e.name === "AbortError") return;
          if (e instanceof ApiError && e.status === 410) { rawGone = true; draw(current); return; }
          status.textContent = e.message;
          more.hidden = true;
        }
      });
    }

    const open = h("button", { type: "button", class: "btn" }, "Show raw events");
    more.addEventListener("click", next);
    more.hidden = true;
    open.addEventListener("click", async () => {
      if (started) return;
      started = true;
      open.hidden = true;
      more.hidden = false;
      await next();
    });
    return h("section", null, heading("Raw events", FROM_RECORDING), open, list, status, more);
  }

  function eventRow(ev) {
    const { v, seq, time, session, pane, type, ...rest } = ev;
    const hasBody = Object.keys(rest).length > 0;
    const body = hasBody ? JSON.stringify(rest, null, 2) : "";
    return h("details", { class: "event" },
      h("summary", null,
        h("span", { class: "num mono" }, seq), h("span", { class: "tag" }, type), h("span", { class: "muted nowrap" }, time ? fmtDate(time) : ""),
        h("span", { class: "muted small" }, hasBody ? fmtBytes(body.length) : "")),
      hasBody ? h("pre", { class: "mono" }, body) : h("p", { class: "muted" }, "No further fields"));
  }

  load();
  return () => ctrl.abort();
}
