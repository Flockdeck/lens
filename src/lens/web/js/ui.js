import { GLOSSARY } from "./lib.js";

// Tiny DOM helpers. Everything is inserted via textContent / createElement, never innerHTML,
// because summaries and events come from recordings and must be treated as untrusted.

export function h(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(node.style, v); // CSSOM, CSP-safe
    else if (k === "dataset") Object.assign(node.dataset, v);
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (v === true) node.setAttribute(k, "");
    else node.setAttribute(k, v);
  }
  append(node, children);
  return node;
}

export function append(node, children) {
  for (const c of children.flat(Infinity)) {
    if (c === undefined || c === null || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

export function clear(node) {
  node.replaceChildren();
  return node;
}

// Flockdeck's rule: every status carries a glyph and a word, colour is the third channel.
export const GLYPHS = {
  done: "\u2713", running: "\u25CF", queued: "\u25CB", failed: "\u25A0",
  stuck: "\u25B2", abandoned: "\u25A1", cancelled: "\u25A1",
  "sev-medium": "\u25B2", "sev-high": "\u25A0",
  "c-truncated": "\u25B2", "c-cut_off": "\u25B2", "c-cut-off": "\u25B2",
};

export function badge(text, kind) {
  const key = kind || text;
  const glyph = GLYPHS[key];
  return h("span", { class: `badge badge-${key}` },
    glyph ? h("span", { class: "glyph", "aria-hidden": "true" }, glyph) : null, text);
}

export function skeleton(lines = 3) {
  const box = h("div", { class: "skeleton", "aria-hidden": "true" });
  for (let i = 0; i < lines; i += 1) box.append(h("div", { class: "skeleton-line" }));
  return box;
}

export function empty(title, hint, action) {
  return h("div", { class: "empty" }, h("p", { class: "empty-title" }, title),
    hint ? h("p", { class: "muted" }, hint) : null, action);
}

export function errorBox(message, onRetry) {
  return h("div", { class: "error-box", role: "alert" }, h("p", null, message),
    onRetry ? h("button", { type: "button", class: "btn", onclick: onRetry }, "Try again") : null);
}

export function stat(label, value, hint) {
  return h("div", { class: "stat" }, h("dt", null, label, info(label)), h("dd", null, value),
    hint ? h("span", { class: "muted small" }, hint) : null);
}

let infoCount = 0;
/** A "?" button that opens a short explanation of `label` (from the glossary, or `text`). It is a
 * real button, so keyboard, touch and screen readers get it as well as the mouse; Escape or a
 * second press closes it. Nothing is shown for a label with no entry. */
export function info(label, text = GLOSSARY[label]) {
  if (!text) return null;
  const id = `info-${++infoCount}`;
  const note = h("span", { class: "info-note", id, role: "note", hidden: true }, text);
  const set = (open) => { note.hidden = !open; button.setAttribute("aria-expanded", String(open)); };
  const button = h("button", {
    type: "button", class: "info", "aria-label": `What is ${label}?`, "aria-expanded": "false", "aria-controls": id, title: text,
    onclick: (e) => { e.preventDefault(); e.stopPropagation(); set(note.hidden); },
    onkeydown: (e) => { if (e.key === "Escape" && !note.hidden) { e.stopPropagation(); set(false); } },
  }, "?");
  return h("span", { class: "info-wrap" }, button, note);
}

let toastHost;
export function toast(message, kind = "info") {
  if (!toastHost) {
    toastHost = h("div", { class: "toasts", role: "status", "aria-live": "polite" });
    document.body.append(toastHost);
  }
  const t = h("div", { class: `toast toast-${kind}` }, message);
  toastHost.append(t);
  setTimeout(() => t.remove(), kind === "error" ? 7000 : 3500);
}

/** Accessible confirm built on <dialog>. Resolves true/false. */
export function confirmDialog(title, body, confirmLabel) {
  return new Promise((resolve) => {
    const dlg = h("dialog", { class: "dialog", "aria-labelledby": "dlg-title" },
      h("form", { method: "dialog" },
        h("h2", { id: "dlg-title" }, title),
        h("p", null, body),
        h("div", { class: "row end" },
          h("button", { class: "btn", value: "cancel", type: "submit" }, "Cancel"),
          h("button", { class: "btn btn-danger", value: "ok", type: "submit" }, confirmLabel))));
    dlg.addEventListener("close", () => {
      resolve(dlg.returnValue === "ok");
      dlg.remove();
    });
    document.body.append(dlg);
    dlg.showModal();
  });
}

/** Run an async action with a busy button; errors become toasts. */
export async function withBusy(button, fn) {
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  try {
    return await fn();
  } finally {
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }
}
