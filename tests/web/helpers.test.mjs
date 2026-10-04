// Unit tests for the pure helpers in src/lens/web/js/lib.js.
// Run from anywhere: node --test tests/web/helpers.test.mjs   (or plain: node tests/web/helpers.test.mjs)
import assert from "node:assert/strict";

const lib = await import(new URL("../../src/lens/web/js/lib.js", import.meta.url).href);

assert.equal(lib.fmtBytes(512), "512 B");
assert.equal(lib.fmtBytes(1536), "1.5 KiB");
assert.equal(lib.fmtBytes(17 * 1024 * 1024), "17 MiB");
assert.equal(lib.fmtDuration(45), "45s");
assert.equal(lib.fmtDuration(125), "2m 5s");
assert.equal(lib.fmtDuration(3900), "1h 5m");
assert.equal(lib.fmtPct(0.1234), "12.3%");
assert.equal(lib.buildQuery({ a: "x", b: "", c: undefined, d: 0 }), "?a=x&d=0");
assert.equal(lib.buildQuery({}), "");

const f = (name, size, lm = 1) => ({ name, size, lastModified: lm });
const checked = lib.checkFiles([f("a.jsonl", 10), f("b.txt", 10), f("c.jsonl", 0), f("d.JSONL", lib.MAX_FILE_BYTES + 1)]);
assert.deepEqual(checked.map((c) => c.problem === null), [true, false, false, false]);
assert.match(checked[3].problem, /limit/);

const merged = lib.mergeFiles([f("a.jsonl", 1)], [f("a.jsonl", 1), f("a.jsonl", 2)]);
assert.equal(merged.length, 2);

assert.equal(lib.batchActive({ counts: { queued: 0, running: 1 } }), true);
assert.equal(lib.batchActive({ counts: { done: 3, failed: 1 } }), false);

assert.deepEqual(lib.parseHash("#/sessions/42?x=1"), { parts: ["sessions", "42"], query: { x: "1" } });
assert.deepEqual(lib.parseHash(""), { parts: ["submit"], query: {} });
assert.deepEqual(lib.asList({ items: [1] }), [1]);
assert.deepEqual(lib.asList([2]), [2]);

const cfg = { storage: "filesystem", enricher: "mock", raw_retention_days: 30, cleanup_interval_seconds: null, version: "1" };
assert.equal(lib.statusLine(cfg), "Local only · storage: filesystem · enrichment: mock · raw kept 30 days");
assert.match(lib.statusLine({ ...cfg, raw_retention_days: 0 }), /raw kept until deleted$/);
assert.match(lib.statusLine({ ...cfg, enricher: "ollama" }), /enrichment: local model/);
assert.match(lib.statusLine({ ...cfg, raw_retention_days: 1 }), /raw kept 1 day$/);
assert.match(lib.statusLine({ ...cfg, storage: "s3" }), /^Not verified as local-only/);
assert.match(lib.statusLine({ ...cfg, enricher: "anthropic" }), /^Sends digests to Anthropic · storage: filesystem · enrichment: anthropic/);
assert.equal(lib.isLocalOnly({ ...cfg, enricher: "anthropic" }), false);
assert.equal(lib.isRemoteEnrichment({ ...cfg, enricher: "anthropic" }), true);
assert.equal(lib.isRemoteEnrichment(cfg), false);
assert.match(lib.statusDetails(cfg)[0], /^Nothing is uploaded/);
assert.match(lib.statusDetails({ ...cfg, enricher: "anthropic" })[0], /Raw recordings stay on this machine.*sends a bounded digest.*Anthropic API/i);
assert.doesNotMatch(lib.statusDetails({ ...cfg, enricher: "anthropic" }).join(" "), /Nothing is uploaded/);
assert.equal(lib.statusLine(null), "Status unavailable");
assert.match(lib.expiredText(cfg), /^Raw recording expired after 30 days\./);
assert.match(lib.expiredText({ ...cfg, raw_retention_days: 0 }), /retention is off/);
assert.match(lib.expiredText(null), /after the retention period/);

console.log("helpers ok");

// Every explanation is a real sentence, and the vague terms are defined.
for (const [label, text] of Object.entries(lib.GLOSSARY)) {
  assert.ok(text.length > 30 && text.endsWith("."), `glossary entry for ${label}`);
}
assert.match(lib.GLOSSARY["Frustration"], /0 \(calm\) to 1/);
assert.match(lib.GLOSSARY["Frustration"], /judgement, not a measurement/);
assert.match(lib.GLOSSARY["Analysis model"], /not the model the agent used/);
console.log("glossary ok");
