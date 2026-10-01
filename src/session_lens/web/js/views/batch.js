import { api, ApiError } from "../api.js";
import { batchActive, sum } from "../lib.js";
import { h, clear, badge, skeleton, errorBox, toast, withBusy, empty } from "../ui.js";
import { REJECTED_KEY } from "./submit.js";

const POLL_MS = 2000;
const ORDER = ["done", "running", "queued", "failed", "cancelled"];

export function render(root, { parts }) {
  const id = parts[1];
  const ctrl = new AbortController();
  let timer = null;
  let stopped = false;
  let inflight = false; // one request and one timer chain at a time
  let again = false;

  let rejected = [];
  try { rejected = JSON.parse(sessionStorage.getItem(REJECTED_KEY + id) || "[]"); } catch { /* ignore */ }

  const head = h("header", { class: "page-head" });
  const summary = h("div", { "aria-live": "polite" });
  const body = h("div");
  root.append(head, summary, body, skeleton(4));

  function draw(batch) {
    const c = batch.counts || {};
    const total = sum(c);
    const active = batchActive(batch);
    clear(head).append(
      h("h1", null, "Batch"), h("p", { class: "muted mono" }, id),
      h("div", { class: "row" }, badge(batch.status), active ? h("span", { class: "muted" }, "Updating every 2 seconds") : null));

    const retry = h("button", { type: "button", class: "btn", disabled: !c.failed }, `Retry failed${c.failed ? ` (${c.failed})` : ""}`);
    retry.addEventListener("click", () => withBusy(retry, async () => {
      try { await api.retryBatch(id); toast("Failed items re-queued"); await poll(); } catch (e) { toast(e.message, "error"); }
    }));
    const cancel = h("button", { type: "button", class: "btn btn-danger-quiet", disabled: !c.queued }, `Cancel queued${c.queued ? ` (${c.queued})` : ""}`);
    cancel.addEventListener("click", () => withBusy(cancel, async () => {
      try { await api.cancelBatch(id); toast("Queued items cancelled"); await poll(); } catch (e) { toast(e.message, "error"); }
    }));

    clear(summary).append(
      h("div", { class: "progress", role: "img", "aria-label": ORDER.map((k) => `${c[k] || 0} ${k}`).join(", ") },
        total ? ORDER.map((k) => (c[k] ? h("span", { class: `progress-seg seg-${k}`, style: { flex: String(c[k]) } }) : null)) : null),
      h("dl", { class: "stats compact" }, ORDER.map((k) => h("div", { class: "stat" }, h("dt", null, k), h("dd", null, c[k] || 0)))),
      h("div", { class: "row" }, retry, cancel, h("a", { class: "btn", href: "#/sessions" }, "View sessions")));

    clear(body);
    if (rejected.length) {
      body.append(h("section", { class: "error-box" }, h("h2", null, `Not accepted (${rejected.length})`),
        h("ul", null, rejected.map((r) => h("li", null, h("span", { class: "mono" }, r.filename), `: ${r.reason}`)))));
    }
    const items = batch.items || [];
    body.append(h("h2", null, `Items (${items.length})`));
    if (!items.length) { body.append(empty("No items in this batch")); return; }
    body.append(h("div", { class: "table-wrap" }, h("table", { class: "table" },
      h("thead", null, h("tr", null, ["File", "Status", "Attempts", "Error", "Session"].map((t) => h("th", { scope: "col" }, t)))),
      h("tbody", null, items.map((it) => h("tr", null,
        h("td", { class: "mono wrap" }, it.filename),
        h("td", null, badge(it.status)),
        h("td", { class: "num" }, it.attempts ?? 0),
        h("td", { class: "wrap" }, it.error ? h("span", { class: "problem" }, it.error) : ""),
        h("td", null, it.session_id ? h("a", { href: `#/sessions/${encodeURIComponent(it.session_id)}` }, "Open") : "")))))));
  }

  async function poll() {
    if (stopped) return;
    if (inflight) { again = true; return; }
    inflight = true;
    clearTimeout(timer);
    try {
      const batch = await api.getBatch(id, ctrl.signal);
      root.querySelector(".skeleton")?.remove();
      draw(batch);
      if (batchActive(batch)) timer = setTimeout(poll, POLL_MS);
    } catch (e) {
      if (stopped || e.name === "AbortError") return;
      root.querySelector(".skeleton")?.remove();
      if (e instanceof ApiError && e.status === 404) {
        clear(body).append(empty("Batch not found", "It may have been removed."));
        return;
      }
      clear(body).append(errorBox(e.message, poll));
      timer = setTimeout(poll, POLL_MS * 3);
    } finally {
      inflight = false;
      if (again && !stopped) { again = false; poll(); }
    }
  }
  const onVisible = () => { if (!document.hidden && !stopped) poll(); };
  document.addEventListener("visibilitychange", onVisible);
  poll();

  return () => {
    stopped = true;
    clearTimeout(timer);
    ctrl.abort();
    document.removeEventListener("visibilitychange", onVisible);
  };
}
