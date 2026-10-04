import { api, ApiError } from "../api.js";
import { checkFiles, fmtBytes, mergeFiles, MAX_FILE_BYTES, MAX_FILES } from "../lib.js";
import { h, clear, toast, withBusy } from "../ui.js";

export const REJECTED_KEY = "lens.rejected."; // sessionStorage, per batch id

export function render(root) {
  let files = [];
  let serverRejected = [];
  let error = "";

  const input = h("input", {
    type: "file", id: "file-input", multiple: true, accept: ".jsonl", class: "visually-hidden",
    onchange: () => add([...input.files]),
  });
  const dropLabel = h("label", { for: "file-input", class: "dropzone" },
    h("span", { class: "dropzone-title" }, "Drop recordings here or choose files"),
    h("span", { class: "muted" }, `.jsonl, up to ${fmtBytes(MAX_FILE_BYTES)} each, ${MAX_FILES} files per batch`));
  const list = h("div", { class: "file-list" });
  const actions = h("div", { class: "row" });
  const status = h("div", { "aria-live": "polite" });

  let dragDepth = 0;
  const over = (on) => dropLabel.classList.toggle("dragging", on);
  // On the whole document, so a drop that misses the zone never navigates the tab to the file.
  const dnd = {
    dragenter: (e) => { e.preventDefault(); dragDepth += 1; over(true); },
    dragover: (e) => e.preventDefault(),
    dragleave: () => { dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) over(false); },
    drop: (e) => {
      e.preventDefault();
      dragDepth = 0;
      over(false);
      add([...((e.dataTransfer && e.dataTransfer.files) || [])]);
    },
  };
  for (const [name, fn] of Object.entries(dnd)) document.addEventListener(name, fn);

  function add(incoming) {
    files = mergeFiles(files, incoming);
    input.value = "";
    error = "";
    serverRejected = [];
    draw();
  }

  function draw() {
    const checked = checkFiles(files);
    const bad = checked.filter((c) => c.problem);
    const good = checked.length - bad.length;
    const total = checked.filter((c) => !c.problem).reduce((a, c) => a + c.file.size, 0);

    clear(list);
    if (checked.length) {
      list.append(h("table", { class: "table" },
        h("caption", { class: "visually-hidden" }, "Selected recordings"),
        h("thead", null, h("tr", null,
          h("th", { scope: "col" }, "File"), h("th", { scope: "col", class: "num" }, "Size"),
          h("th", { scope: "col" }, "Check"), h("th", { scope: "col" }, h("span", { class: "visually-hidden" }, "Remove")))),
        h("tbody", null, checked.map((c) => h("tr", { class: c.problem ? "row-bad" : "" },
          h("td", { class: "mono wrap" }, c.file.name),
          h("td", { class: "num" }, fmtBytes(c.file.size)),
          h("td", null, c.problem ? h("span", { class: "problem" }, c.problem) : "Ready"),
          h("td", null, h("button", {
            type: "button", class: "btn btn-quiet", "aria-label": `Remove ${c.file.name}`,
            onclick: () => { files = files.filter((f) => f !== c.file); draw(); },
          }, "Remove")))))));
    }

    clear(actions);
    if (checked.length) {
      const send = h("button", { type: "button", class: "btn btn-primary", disabled: good === 0 }, "Submit batch");
      send.addEventListener("click", () => submit(send, checked));
      actions.append(send,
        h("button", { type: "button", class: "btn", onclick: () => { files = []; error = ""; serverRejected = []; draw(); } }, "Clear"),
        h("span", { class: "muted" },
          `${good} ready (${fmtBytes(total)})`, bad.length ? `, ${bad.length} will be skipped` : ""));
    }

    clear(status);
    if (error) status.append(h("div", { class: "error-box", role: "alert" }, h("p", null, error)));
    if (serverRejected.length) {
      status.append(h("div", { class: "error-box" }, h("p", null, "The server rejected these files:"),
        h("ul", null, serverRejected.map((r) => h("li", null, h("span", { class: "mono" }, r.filename), `: ${r.reason}`)))));
    }
  }

  async function submit(button, checked) {
    const send = checked.filter((c) => !c.problem).map((c) => c.file);
    const skipped = checked.filter((c) => c.problem).map((c) => ({ filename: c.file.name, reason: c.problem }));
    await withBusy(button, async () => {
      try {
        const res = await api.uploadBatch(send);
        try {
          sessionStorage.setItem(REJECTED_KEY + res.id, JSON.stringify([...(res.rejected || []), ...skipped]));
        } catch { /* optional */ }
        location.hash = `#/batches/${encodeURIComponent(res.id)}`;
      } catch (e) {
        error = e.message || "Upload failed";
        serverRejected = e instanceof ApiError
          ? (e.body && e.body.detail && e.body.detail.rejected) || (e.body && e.body.rejected) || []
          : [];
        toast(error, "error");
        draw();
      }
    });
  }

  root.append(
    h("header", { class: "page-head" }, h("h1", null, "Submit recordings"),
      h("p", { class: "muted" }, "Choose Flockdeck pane recordings. They go up as one batch and are processed in the background.")),
    input, dropLabel, list, actions, status);
  draw();
  return () => { for (const [name, fn] of Object.entries(dnd)) document.removeEventListener(name, fn); };
}
