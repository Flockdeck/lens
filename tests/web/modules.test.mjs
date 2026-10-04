// Every browser module must parse as an ES module. `node --check` parses a .js file as a script,
// which accepts less (and, as it turned out, let a missing parenthesis through).
import { readdirSync, statSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import assert from "node:assert/strict";

const root = join(dirname(fileURLToPath(import.meta.url)), "../../src/lens/web/js");
const files = [];
(function walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p);
    else if (name.endsWith(".js")) files.push(p);
  }
})(root);
assert.ok(files.length >= 10, "found the modules");

// Importing runs a module's top level, which needs a browser for some of them. A syntax error
// is raised before any of that, so only a SyntaxError counts as a failure here.
for (const f of files) {
  try {
    await import(pathToFileURL(f).href);
  } catch (e) {
    assert.ok(!(e instanceof SyntaxError), `${f}: ${e.message}`);
  }
}
console.log(`modules ok (${files.length})`);
