// The only module that talks to the network. Everything goes through the documented HTTP API.
import { buildQuery } from "./lib.js";

const TOKEN_KEY = "session-lens.token";

export function getToken() {
  try {
    return sessionStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setToken(token) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* sessionStorage unavailable: token lives only until reload */
  }
}

export class ApiError extends Error {
  constructor(status, message, body) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

function describe(status, body) {
  const d = body && body.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join("; ");
  if (d && typeof d === "object" && d.message) return d.message;
  return `Request failed (${status})`;
}

async function request(method, path, { query, body, signal } = {}) {
  const headers = { Accept: "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let res;
  try {
    res = await fetch(path + buildQuery(query), { method, headers, body, signal });
  } catch (e) {
    if (e && e.name === "AbortError") throw e;
    throw new ApiError(0, "Could not reach the server");
  }
  let data = null;
  if (res.status !== 204) {
    const text = await res.text();
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = null;
      }
    }
  }
  if (res.status === 401) {
    setToken("");
    window.dispatchEvent(new CustomEvent("auth-required"));
  }
  if (!res.ok) throw new ApiError(res.status, describe(res.status, data), data);
  return data;
}

export const api = {
  uploadBatch(files, signal) {
    const form = new FormData();
    for (const f of files) form.append("files", f, f.name);
    return request("POST", "/batches", { body: form, signal });
  },
  getBatch: (id, signal) => request("GET", `/batches/${encodeURIComponent(id)}`, { signal }),
  retryBatch: (id) => request("POST", `/batches/${encodeURIComponent(id)}/retry`),
  cancelBatch: (id) => request("POST", `/batches/${encodeURIComponent(id)}/cancel`),
  listSessions: (query, signal) => request("GET", "/sessions", { query, signal }),
  getSession: (id, signal) => request("GET", `/sessions/${encodeURIComponent(id)}`, { signal }),
  getEvents: (id, query, signal) =>
    request("GET", `/sessions/${encodeURIComponent(id)}/events`, { query, signal }),
  enrichSession: (id) => request("POST", `/sessions/${encodeURIComponent(id)}/enrich`),
  deleteSession: (id) => request("DELETE", `/sessions/${encodeURIComponent(id)}`),
  trends: (query, signal) => request("GET", "/stats/trends", { query, signal }),
  compare: (by, signal) => request("GET", "/stats/compare", { query: { by }, signal }),
  usage: (signal) => request("GET", "/stats/usage", { signal }),
};
