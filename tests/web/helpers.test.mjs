// Unit tests for the pure helpers in src/session_lens/web/js/lib.js.
// Run from anywhere: node --test tests/web/helpers.test.mjs   (or plain: node tests/web/helpers.test.mjs)
import assert from "node:assert/strict";

const lib = await import(new URL("../../src/session_lens/web/js/lib.js", import.meta.url).href);

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

console.log("helpers ok");
