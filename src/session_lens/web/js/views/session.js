import { api, ApiError } from "../api.js";
import { getConfig, loadConfig } from "../config.js";
import { asList, expiredText, fmtBytes, fmtDate, fmtDuration, fmtNum, fmtPct } from "../lib.js";
import { h, clear, badge, skeleton, errorBox, empty, stat, toast, confirmDialog, withBusy } from "../ui.js";

const EVENT_PAGE = 100;

export function render(root, { parts }) {
  const id = parts[1];
  const ctrl = new AbortController();
  const host = h("div");
  let rawGone = false; // set when the API says the raw recording has expired (410)
  let current = null;
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
    clear(host).append(
      header(s, enr),
      enr ? enrichmentSection(enr) : h("section", null, h("h2", null, "Enrichment"), empty("Not enriched yet", "Use Re-enrich to run it now.")),
      metricsSection(m),
      risksSection(s, enr),
      stuckSection(enr),
      filesSection(s.files_touched),
      warningsSection(s.warnings, s.completeness),
      eventsSection(s));
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
        out ? badge(out) : null, cat ? h("span", { class: "tag" }, cat) : null,
        s.completeness ? badge(s.completeness.replace("_", " "), `c-${s.completeness}`) : null),
      h("dl", { class: "meta" },
        meta("Agent", s.agent), meta("Model", s.model), meta("Pane", s.pane),
        meta("Started", fmtDate(s.started_at)), meta("Ended", fmtDate(s.ended_at)),
        meta("Session", s.recording_session, true)),
      h("div", { class: "row" }, reenrich, del),
      gone ? h("p", { id: "raw-expired", class: "muted small" }, expiredText(getConfig())) : null);
  }

  const meta = (k, v, mono) => (v ? h("div", null, h("dt", null, k), h("dd", { class: mono ? "mono wrap" : "" }, v)) : null);

  function enrichmentSection(e) {
    return h("section", null, h("h2", null, "Enrichment"),
      h("p", { class: "lead" }, e.summary || ""),
      h("dl", { class: "stats" },
        stat("Frustration", e.frustration == null ? "n/a" : e.frustration.toFixed(2), "0 calm, 1 high"),
        stat("Tokens in", fmtNum(e.input_tokens)), stat("Tokens out", fmtNum(e.output_tokens)),
        stat("Model", e.model || "n/a"), stat("Prompt version", e.prompt_version || "n/a")),
      e.prompt_feedback ? h("div", { class: "note" }, h("h3", null, "Prompt feedback"), h("p", null, e.prompt_feedback)) : null);
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
    return h("section", null, h("h2", null, "Metrics"),
      h("dl", { class: "stats" },
        stat("Duration", fmtDuration(m.duration_seconds) || "n/a"), stat("Turns", fmtNum(m.turns ?? 0)),
        stat("Tool calls", fmtNum(m.tool_calls ?? 0)),
        stat("Tool errors", fmtNum(m.tool_errors ?? 0), m.tool_calls ? fmtPct(m.tool_errors / m.tool_calls) : ""),
        stat("Interrupted", fmtNum(m.tool_interrupted ?? 0)), stat("Unpaired calls", fmtNum(m.unpaired_calls ?? 0)),
        stat("Redacted lines", fmtNum(m.redacted_lines ?? 0)), stat("Clipped lines", fmtNum(m.clipped_lines ?? 0))),
      h("div", { class: "cols" },
        h("div", null, h("h3", null, "Tool mix"), bars(m.tool_mix)),
        h("div", null, h("h3", null, "Permissions"), bars(p), p.prompts ? null : h("p", { class: "muted small" }, "No permission prompts")),
        h("div", null, h("h3", null, "Time in each status"), bars(m.status_seconds, fmtDuration))));
  }

  function risksSection(s, enr) {
    const risks = s.risky_actions || [];
    const notes = new Map(((enr && enr.risk_notes) || []).map((n) => [n.seq, n.explanation]));
    return h("section", null, h("h2", null, `Risky actions (${risks.length})`),
      !risks.length ? h("p", { class: "muted" }, "No risky actions detected.")
        : h("div", { class: "table-wrap" }, h("table", { class: "table" },
          h("thead", null, h("tr", null, ["Seq", "Severity", "Tool", "Action", "Rule", "Note"].map((t) => h("th", { scope: "col" }, t)))),
          h("tbody", null, risks.map((r) => h("tr", null,
            h("td", { class: "num" }, r.seq), h("td", null, badge(r.severity, `sev-${r.severity}`)), h("td", null, r.tool),
            h("td", { class: "mono wrap" }, r.summary), h("td", { class: "mono" }, r.rule), h("td", { class: "wrap" }, notes.get(r.seq) || "")))))));
  }

  function stuckSection(enr) {
    const pts = (enr && enr.stuck_points) || [];
    if (!pts.length) return null;
    return h("section", null, h("h2", null, `Stuck points (${pts.length})`),
      h("ol", { class: "plain-list" }, pts.map((p) => h("li", null, p.description, p.approx_seq != null ? h("span", { class: "muted" }, ` (around event ${p.approx_seq})`) : null))));
  }

  function filesSection(f) {
    f = f || {};
    const group = (title, list) => h("details", { class: "files" },
      h("summary", null, `${title} (${(list || []).length})`),
      (list || []).length ? h("ul", { class: "mono plain-list" }, list.map((x) => h("li", { class: "wrap" }, x))) : h("p", { class: "muted" }, "None"));
    return h("section", null, h("h2", null, "Files touched"), group("Edited", f.edited), group("Read", f.read), group("Commands", f.commands));
  }

  function warningsSection(warnings, completeness) {
    const list = warnings || [];
    if (!list.length && (!completeness || completeness === "clean")) return null;
    return h("section", null, h("h2", null, "Parse warnings"),
      completeness && completeness !== "clean" ? h("p", null, `Recording completeness: ${completeness.replace("_", " ")}.`) : null,
      list.length ? h("ul", { class: "plain-list" }, list.map((w) => h("li", null, w))) : null);
  }

  function eventsSection(s) {
    if (rawGone || s.raw_available === false) {
      return h("section", null, h("h2", null, "Raw events"), h("p", { class: "muted" }, expiredText(getConfig())));
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
    return h("section", null, h("h2", null, "Raw events"), open, list, status, more);
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
