// Runtime config from GET /config, loaded once per token. Failure is never fatal: callers get
// null and fall back to neutral wording.
import { api } from "./api.js";

let current = null;
let pending = null;
let latest = 0; // which load started last; an older response must not overwrite a newer one
const listeners = new Set();

export const getConfig = () => current;
export const onConfig = (fn) => { listeners.add(fn); return () => listeners.delete(fn); };

export function loadConfig({ force = false } = {}) {
  if (pending && !force) return pending;
  const mine = ++latest;
  pending = api.config().then((c) => c, () => null).then((c) => {
    if (mine !== latest) return pending || c; // superseded by a newer load or a reset
    current = c;
    if (!c) pending = null; // a failure is retried on the next navigation
    for (const fn of listeners) fn(c);
    return c;
  });
  return pending;
}

export function resetConfig() {
  latest += 1;
  current = null;
  pending = null;
  for (const fn of listeners) fn(null);
}
