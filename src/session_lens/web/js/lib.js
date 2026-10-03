// Pure helpers, no DOM access, so they can be unit-tested under node.

export const MAX_FILE_BYTES = 17 * 1024 * 1024; // mirrors Settings.max_file_bytes
export const MAX_FILES = 100; // mirrors Settings.max_files_per_batch

export function fmtBytes(n) {
  if (!Number.isFinite(n)) return "";
  if (n < 1024) return `${n} B`;
  const units = ["KiB", "MiB", "GiB"];
  let v = n / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v < 10 ? v.toFixed(1) : Math.round(v)} ${units[i]}`;
}

export function fmtDuration(seconds) {
  if (!Number.isFinite(seconds)) return "";
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

export function fmtPct(x, digits = 1) {
  return Number.isFinite(x) ? `${(x * 100).toFixed(digits)}%` : "";
}

export function fmtNum(n) {
  return Number.isFinite(n) ? n.toLocaleString("en-GB") : "";
}

export function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString("en-GB", {
    year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

export function buildQuery(params) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

/** Classify chosen files before anything is sent. Returns [{file, key, problem|null}]. */
export function checkFiles(files, limits = {}) {
  const maxBytes = limits.maxBytes ?? MAX_FILE_BYTES;
  const maxFiles = limits.maxFiles ?? MAX_FILES;
  return files.map((file, i) => {
    let problem = null;
    if (!/\.jsonl$/i.test(file.name)) problem = "Not a .jsonl file";
    else if (file.size === 0) problem = "File is empty";
    else if (file.size > maxBytes) problem = `Over the ${fmtBytes(maxBytes)} limit`;
    else if (i >= maxFiles) problem = `Only ${maxFiles} files per batch`;
    return { file, key: fileKey(file), problem };
  });
}

export const fileKey = (f) => `${f.name}|${f.size}|${f.lastModified}`;

/** Merge newly picked files into the current list, dropping exact duplicates. */
export function mergeFiles(current, incoming) {
  const seen = new Set(current.map(fileKey));
  const out = [...current];
  for (const f of incoming) {
    const k = fileKey(f);
    if (!seen.has(k)) {
      seen.add(k);
      out.push(f);
    }
  }
  return out;
}

/** Items a batch is still working on: stop polling when this is 0. */
export function batchActive(batch) {
  const c = (batch && batch.counts) || {};
  return (c.queued || 0) + (c.running || 0) > 0;
}

export function parseHash(hash) {
  const raw = (hash || "").replace(/^#/, "") || "/submit";
  const [path, query = ""] = raw.split("?");
  const parts = path.split("/").filter(Boolean);
  return { parts, query: Object.fromEntries(new URLSearchParams(query)) };
}

/** Accept either a bare list or {items: [...]} for list-ish responses. */
export const asList = (x) => (Array.isArray(x) ? x : (x && (x.items || x.events)) || []);

export function sum(obj) {
  return Object.values(obj || {}).reduce((a, b) => a + (Number(b) || 0), 0);
}

// ---- Runtime config (GET /config) -------------------------------------------------------

/** Human text for how long raw recordings are kept, or null if the value is unusable. */
export function retentionText(cfg) {
  const d = cfg && cfg.raw_retention_days;
  if (!Number.isInteger(d) || d < 0) return null;
  return d === 0 ? "raw kept until deleted" : `raw kept ${d} day${d === 1 ? "" : "s"}`;
}

/** True only when both storage and enrichment are known to stay on this machine. */
export function isLocalOnly(cfg) {
  return !!cfg && cfg.storage === "filesystem" && (cfg.enricher === "mock" || cfg.enricher === "ollama");
}

/** True when the configured enricher sends session digests off this machine. */
export function isRemoteEnrichment(cfg) {
  return !!cfg && cfg.enricher === "anthropic";
}

/** The always-visible status text. The words carry the meaning, not a colour. */
export function statusLine(cfg) {
  if (!cfg) return "Status unavailable";
  const enrichment = cfg.enricher === "ollama" ? "local model (ollama)" : cfg.enricher;
  const first = isRemoteEnrichment(cfg)
    ? "Sends digests to Anthropic"
    : isLocalOnly(cfg) ? "Local only" : "Not verified as local-only";
  const parts = [first, `storage: ${cfg.storage}`, `enrichment: ${enrichment}`];
  const r = retentionText(cfg);
  if (r) parts.push(r);
  return parts.join(" · ");
}

/** The two lines under the status text: what leaves the machine, and who sets retention. */
export function statusDetails(cfg) {
  const retention = "How long raw recordings are kept is set on the server by RAW_RETENTION_DAYS (0 keeps them until you delete them).";
  if (isRemoteEnrichment(cfg)) {
    return [
      "Raw recordings stay on this machine. Enrichment sends a bounded digest of each session (your prompts, the agent's final messages, trimmed failing output and metrics) to the Anthropic API, because ENRICHER=anthropic is set. Choose the mock or a local Ollama model to send nothing.",
      retention,
    ];
  }
  return ["Nothing is uploaded. Recordings stay on this machine and are read only by this server.", retention];
}

/** Why a session's raw recording is gone, worded from the configured retention. */
export function expiredText(cfg) {
  const d = cfg && cfg.raw_retention_days;
  let first;
  if (Number.isInteger(d) && d > 0) first = `Raw recording expired after ${d} day${d === 1 ? "" : "s"}.`;
  else if (d === 0) first = "Raw recording is no longer available (retention is off, so it was deleted by hand or lost).";
  else first = "Raw recording expired after the retention period.";
  return `${first} Metrics and enrichment are kept.`;
}

// ---- What each label means. Shown by the "?" buttons (ui.js `info`). -------------------------
// Two kinds of thing are on a session page: facts computed from the recording, and judgements the
// session-lens LLM made about it. Each entry says which, and for judgements how it was made.
export const GLOSSARY = {
  // from the LLM
  "Frustration": "The LLM's estimate, from 0 (calm) to 1 (very frustrated), of how frustrated the user seemed. It judges this from the user's prompts, repeated corrections, denied permissions and tool errors. It is a judgement, not a measurement, and can be wrong.",
  "Outcome": "The LLM's verdict on how the session ended. Done: the goal looks achieved. Stuck: going in circles or blocked. Abandoned: it ended unfinished with no clear blockage. A recording that was cut off is not by itself abandonment.",
  "Category": "What kind of work the session was, chosen by the LLM: bugfix, feature, refactor, exploration, docs, tests, ops or other.",
  "Prompt version": "Which version of session-lens's analysis prompt produced this. If it changes, older and newer analyses are not strictly comparable. Re-enrich to redo a session with the current one.",
  "Analysis model": "The model that wrote this analysis. This is not the model the agent used in the session (see Agent model in the header).",
  "Tokens in": "Tokens sent to the analysis model for this session: the instructions plus a digest of it. This is what the analysis cost, not what the session used.",
  "Tokens out": "Tokens the analysis model wrote back. This is what the analysis cost, not what the session used.",
  "Stuck points": "Places the LLM thinks progress stalled. 'Around event N' points to that event in Raw events.",
  "Prompt feedback": "The LLM's suggestions for how the user could have prompted better.",
  // from the recording
  "Agent model": "The model the coding agent was running in this session, as the recording reports it.",
  "Agent": "The coding agent that was recorded.",
  "Pane": "The Flockdeck pane the agent ran in.",
  "Completeness": "How the recording ended. Clean: it has its stop line. Truncated: the recorder hit its size cap and stopped. Cut off: no stop line, so the app closed or crashed. Partial agent: the agent only reports start and stop, so there are no details.",
  "Duration": "Time from the first to the last line of the recording.",
  "Turns": "Prompts the user typed. Subagent prompts and the agent's own task notifications are not counted.",
  "Tool calls": "Times the agent used a tool (run a command, read or edit a file, and so on).",
  "Tool errors": "Tool calls that failed, not counting ones the user interrupted. The percentage is of all tool calls.",
  "Interrupted": "Tool calls the user stopped before they finished.",
  "Unpaired calls": "Tool calls with no recorded result, usually because the recording ended mid-call.",
  "Redacted lines": "Lines in which Flockdeck's recorder removed something sensitive before writing.",
  "Clipped lines": "Lines in which the recorder shortened very long content.",
  "Tool mix": "How many times each tool was used.",
  "Permissions": "What happened when the agent asked the user for permission.",
  "Time in each status": "How long the pane spent working, waiting for the user and idle.",
  "From the recording": "Computed directly from the recording by session-lens's parser and rules. No LLM was involved, so it does not vary between runs.",
  "session-lens LLM": "Written by a language model that session-lens ran over a digest of this session. It is an interpretation, can be wrong, and can change when you re-enrich.",
  "Severity": "How risky the action looks, from fixed rules.",
  "Rule": "The rule that flagged the action.",
  "Note (LLM)": "The LLM's comment on whether the action was a concern in context. The flagging itself is rule-based.",
  "Input tokens": "Tokens sent to analysis models across all sessions. This is session-lens's own usage, not what your agents used.",
  "Output tokens": "Tokens the analysis models wrote back, across all sessions.",
};
