import { api } from "../api.js";
import { loadConfig } from "../config.js";
import { h, clear, skeleton, errorBox, toast, withBusy } from "../ui.js";

const ENRICHERS = [
  ["mock", "Mock (nothing is sent anywhere)"],
  ["ollama", "Ollama (a model on this machine)"],
  ["anthropic", "Anthropic (digests are sent to the Anthropic API)"],
];

const KEY_SOURCE = { settings: "Saved here.", environment: "Set in the server's environment." };

export function render(root) {
  const ctrl = new AbortController();
  const body = h("div");
  root.append(
    h("header", { class: "page-head" }, h("h1", null, "Settings")),
    h("p", { class: "muted" }, "Changes apply to the next session the worker enriches. Nothing needs restarting."),
    body,
  );

  async function load() {
    clear(body).append(skeleton(5));
    try {
      draw(await api.getSettings(ctrl.signal));
    } catch (e) {
      if (e.name === "AbortError") return;
      clear(body).append(errorBox(e.message, load));
    }
  }

  function draw(s) {
    const enricher = h("select", { id: "s-enricher", name: "enricher" },
      ENRICHERS.map(([v, label]) => h("option", { value: v, selected: v === s.enricher }, label)));
    const model = h("input", { id: "s-model", name: "anthropic_model", type: "text", value: s.anthropic_model, autocomplete: "off", spellcheck: "false" });
    const key = h("input", {
      id: "s-key", name: "anthropic_api_key", type: "password", autocomplete: "new-password", spellcheck: "false",
      placeholder: s.anthropic_api_key.set ? "A key is set. Type here to replace it." : "sk-ant-...",
    });
    const ollamaUrl = h("input", { id: "s-ourl", name: "ollama_url", type: "text", value: s.ollama_url, autocomplete: "off", spellcheck: "false" });
    const ollamaModel = h("input", { id: "s-omodel", name: "ollama_model", type: "text", value: s.ollama_model, autocomplete: "off", spellcheck: "false" });
    const removeKey = h("button", { type: "button", class: "btn btn-danger-quiet" }, "Remove saved key");
    const save = h("button", { type: "submit", class: "btn btn-primary" }, "Save settings");
    const error = h("div", { role: "alert" });
    const warning = h("p", { class: "callout", id: "s-warning", role: "note" },
      "With Anthropic selected, each session's digest (your prompts, the agent's final messages, trimmed failing output and metrics) is sent to api.anthropic.com. Raw recordings never are.");

    const field = (id, label, input, hint) => h("div", { class: "field" },
      h("label", { for: id }, label), input, hint ? h("p", { class: "muted small", id: `${id}-hint` }, hint) : null);

    const anthropic = h("fieldset", { class: "settings-group" },
      h("legend", null, "Anthropic"),
      field("s-key", "API key", key,
        s.anthropic_api_key.set ? `${KEY_SOURCE[s.anthropic_api_key.source]} It is never shown again.` : "Stored in this machine's database and never shown again."),
      field("s-model", "Model", model));
    const ollama = h("fieldset", { class: "settings-group" },
      h("legend", null, "Ollama"),
      field("s-ourl", "URL", ollamaUrl, "Must be this machine: 127.0.0.1, localhost, ::1 or host.docker.internal."),
      field("s-omodel", "Model", ollamaModel));

    const sync = () => {
      warning.hidden = enricher.value !== "anthropic";
      anthropic.disabled = enricher.value !== "anthropic";
      ollama.disabled = enricher.value !== "ollama";
    };
    enricher.addEventListener("change", sync);
    sync();
    removeKey.hidden = s.anthropic_api_key.source !== "settings";

    async function put(update, done) {
      clear(error);
      try {
        const next = await api.putSettings(update);
        await loadConfig({ force: true });
        toast(done);
        draw(next);
      } catch (e) {
        clear(error).append(errorBox(e.message));
      }
    }

    removeKey.addEventListener("click", () => withBusy(removeKey, () => put({ anthropic_api_key: null }, "Key removed")));
    const form = h("form", { class: "settings", novalidate: true,
      onsubmit: (ev) => {
        ev.preventDefault();
        const update = { enricher: enricher.value, anthropic_model: model.value.trim(), ollama_url: ollamaUrl.value.trim(), ollama_model: ollamaModel.value.trim() };
        if (key.value.trim()) update.anthropic_api_key = key.value.trim();
        return withBusy(save, () => put(update, "Settings saved"));
      } },
      field("s-enricher", "Enrichment", enricher),
      warning, anthropic, ollama, error,
      h("div", { class: "row" }, save, removeKey));
    clear(body).append(form);
  }

  load();
  return () => ctrl.abort();
}
