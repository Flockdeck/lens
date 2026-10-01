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

/** The always-visible status text. The words carry the meaning, not a colour. */
export function statusLine(cfg) {
  if (!cfg) return "Status unavailable";
  const enrichment = cfg.enricher === "ollama" ? "local model (ollama)" : cfg.enricher;
  const parts = [
    isLocalOnly(cfg) ? "Local only" : "Not verified as local-only",
    `storage: ${cfg.storage}`,
    `enrichment: ${enrichment}`,
  ];
  const r = retentionText(cfg);
  if (r) parts.push(r);
  return parts.join(" · ");
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
