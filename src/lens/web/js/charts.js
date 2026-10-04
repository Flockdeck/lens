// Small SVG charts. Colours come from CSS classes, so the stylesheet owns the palette.
import { fmtNum } from "./lib.js";

const NS = "http://www.w3.org/2000/svg";
const svg = (tag, attrs, ...kids) => {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
  for (const k of kids) if (k) n.append(k);
  return n;
};
const text = (s, attrs) => {
  const t = svg("text", attrs);
  t.textContent = s;
  return t;
};

function niceMax(v) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  const f = v / p;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
}

const W = 640;
const H = 220;
const M = { t: 10, r: 12, b: 28, l: 38 };

function frame(label, max, fmtTick) {
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img", "aria-label": label });
  for (let i = 0; i <= 4; i += 1) {
    const y = M.t + ((H - M.t - M.b) * i) / 4;
    root.append(svg("line", { x1: M.l, x2: W - M.r, y1: y, y2: y, class: "grid" }));
    root.append(text(fmtTick(max * (1 - i / 4)), { x: M.l - 6, y: y + 4, class: "tick", "text-anchor": "end" }));
  }
  return root;
}

function xLabels(root, buckets, xAt) {
  const step = Math.max(1, Math.ceil(buckets.length / 8));
  buckets.forEach((b, i) => {
    if (i % step === 0) {
      root.append(text(String(b).slice(5, 10) || String(b), {
        // The last label ends at the plot's right edge instead of running past the viewBox.
        x: xAt(i), y: H - 8, class: "tick", "text-anchor": i + step >= buckets.length ? "end" : "middle",
      }));
    }
  });
}

/** Stacked bars: rows = [{bucket, values: {key: n}}]. */
export function stackedBars(rows, keys, label) {
  const totals = rows.map((r) => keys.reduce((a, k) => a + (r.values[k] || 0), 0));
  // Counts: a multiple of 4 so the four grid steps are whole numbers (no repeated labels).
  const max = Math.max(4, Math.ceil(Math.max(0, ...totals) / 4) * 4);
  const root = frame(label, max, (v) => (Number.isInteger(v) ? fmtNum(v) : ""));
  const plotW = W - M.l - M.r;
  const plotH = H - M.t - M.b;
  const slot = plotW / Math.max(rows.length, 1);
  const bw = Math.max(2, Math.min(28, slot * 0.7));
  const xAt = (i) => M.l + slot * i + slot / 2;
  rows.forEach((r, i) => {
    let y = H - M.b;
    for (const k of keys) {
      const v = r.values[k] || 0;
      if (!v) continue;
      const hgt = (v / max) * plotH;
      y -= hgt;
      root.append(svg("rect", { x: xAt(i) - bw / 2, y, width: bw, height: Math.max(hgt - 1, 0.5), class: `seg seg-${k}` },
        (() => {
          const t = svg("title");
          t.textContent = `${r.bucket}: ${k} ${v}`;
          return t;
        })()));
    }
  });
  xLabels(root, rows.map((r) => r.bucket), xAt);
  return root;
}

/** Lines: series = [{name, cls, points: [number|null]}] on a shared 0..max scale. */
export function lines(buckets, series, label, fmtTick) {
  const all = series.flatMap((s) => s.points.filter((p) => p !== null && p !== undefined));
  const max = niceMax(Math.max(0, ...all));
  const root = frame(label, max, fmtTick);
  const plotW = W - M.l - M.r;
  const plotH = H - M.t - M.b;
  const xAt = (i) => M.l + (buckets.length < 2 ? plotW / 2 : (plotW * i) / (buckets.length - 1));
  const yAt = (v) => M.t + plotH * (1 - v / max);
  for (const s of series) {
    let d = "";
    s.points.forEach((p, i) => {
      if (p === null || p === undefined) return;
      d += `${d ? "L" : "M"}${xAt(i).toFixed(1)} ${yAt(p).toFixed(1)}`;
    });
    if (d) root.append(svg("path", { d, class: `line ${s.cls}` }));
    s.points.forEach((p, i) => {
      if (p === null || p === undefined) return;
      const c = svg("circle", { cx: xAt(i), cy: yAt(p), r: 3, class: `dot ${s.cls}` });
      const t = svg("title");
      t.textContent = `${buckets[i]}: ${s.name} ${fmtTick(p)}`;
      c.append(t);
      root.append(c);
    });
  }
  xLabels(root, buckets, xAt);
  return root;
}
