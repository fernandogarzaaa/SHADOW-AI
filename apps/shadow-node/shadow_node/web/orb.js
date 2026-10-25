// Thinking orbs for the dashboard: a framework-free driver around the
// vendored thinking-orbs engine (libraries.dev, MIT). Mirrors the React
// component's loop: DPR capped at 2, static frame under reduced motion,
// paused offscreen / in hidden tabs, theme from data-theme or the OS.
//
// Usage: render <canvas data-orb="searching" data-size="20"> anywhere (also
// via innerHTML); it is mounted automatically. Change data-orb to switch
// state; set data-paused to freeze.
import { MODE_FRAMES, paintFrame, resolvePreset } from "./vendor/thinking-orbs/engine.es.js";

const STATES = new Set(["working", "searching", "solving", "listening", "connecting",
  "weaving", "composing", "breathing", "shaping"]);
const LABELS = {
  working: "Working", searching: "Searching", solving: "Solving", listening: "Listening",
  connecting: "Connecting", weaving: "Working", composing: "Writing", breathing: "Idle", shaping: "Working",
};
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
const prefersDark = matchMedia("(prefers-color-scheme: dark)");
const orbs = new Map(); // canvas -> state
let raf = 0;

function isDark() {
  const t = document.documentElement.dataset.theme;
  if (t === "dark" || t === "light") return t === "dark";
  return prefersDark.matches;
}

// "accent" follows the theme's accent text colour (--accent-txt), so the
// orb keeps contrast on both dark and light backgrounds.
let accentCache = null;
function accentTint() {
  if (!accentCache) accentCache = parseTint(getComputedStyle(document.documentElement).getPropertyValue("--accent-txt"));
  return accentCache;
}

function parseTint(color) {
  const m = /^#?([0-9a-f]{6})$/i.exec((color || "").trim());
  if (!m) return undefined;
  const n = parseInt(m[1], 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

function configure(canvas) {
  const state = STATES.has(canvas.dataset.orb) ? canvas.dataset.orb : "working";
  const size = [20, 32, 64].includes(Number(canvas.dataset.size)) ? Number(canvas.dataset.size) : 64;
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  canvas.width = Math.round(size * dpr);
  canvas.height = Math.round(size * dpr);
  canvas.style.width = canvas.style.height = `${size}px`;
  if (!canvas.hasAttribute("aria-label")) canvas.setAttribute("aria-label", LABELS[state]);
  canvas.setAttribute("role", "img");
  const { mode, speed, opts } = resolvePreset(state, size);
  return {
    key: `${state}:${size}`, size, dpr, opts, speed,
    frameFn: MODE_FRAMES[mode], ctx: canvas.getContext("2d"),
    tintSpec: canvas.dataset.color, tint: parseTint(canvas.dataset.color), visible: true,
  };
}

function draw(canvas, o, tSec) {
  o.ctx.setTransform(o.dpr, 0, 0, o.dpr, 0, 0);
  o.ctx.clearRect(0, 0, o.size, o.size);
  const tint = o.tintSpec === "accent" ? accentTint() : o.tint;
  paintFrame(o.ctx, o.frameFn(o.size, tSec * o.speed, o.opts), isDark(), tint);
}

const io = new IntersectionObserver((entries) => {
  for (const e of entries) {
    const o = orbs.get(e.target);
    if (o) o.visible = e.isIntersecting;
  }
  schedule();
});

function mount(canvas) {
  if (orbs.has(canvas) || !canvas.dataset.orb) return;
  const o = configure(canvas);
  orbs.set(canvas, o);
  io.observe(canvas);
  draw(canvas, o, 0.6);
  schedule();
}

function tick() {
  raf = 0;
  const t = performance.now() / 1000;
  let active = false;
  for (const [canvas, o] of orbs) {
    if (!canvas.isConnected) {
      orbs.delete(canvas);
      io.unobserve(canvas);
      continue;
    }
    const key = `${canvas.dataset.orb}:${canvas.dataset.size}`;
    if (key !== o.key) orbs.set(canvas, Object.assign(o, configure(canvas)));
    if (!o.visible || canvas.dataset.paused !== undefined) continue;
    draw(canvas, orbs.get(canvas), t);
    active = true;
  }
  if (active) schedule();
}

function schedule() {
  if (raf || reducedMotion.matches || document.visibilityState === "hidden") return;
  raf = requestAnimationFrame(tick);
}

function redrawStatic() {
  accentCache = null;
  for (const [canvas, o] of orbs) draw(canvas, o, 0.6);
}

/** HTML for an orb, for use inside template strings. */
export function orbHTML(state, size = 20, label = "") {
  return `<canvas class="orb orb-${size}" data-orb="${state}" data-size="${size}"${label ? ` aria-label="${label}"` : ""}></canvas>`;
}

export function initOrbs(root = document.body) {
  root.querySelectorAll("canvas[data-orb]").forEach(mount);
  new MutationObserver((records) => {
    for (const r of records) {
      if (r.type === "attributes") { schedule(); continue; }
      for (const n of r.addedNodes) {
        if (n.nodeType !== 1) continue;
        if (n.matches?.("canvas[data-orb]")) mount(n);
        n.querySelectorAll?.("canvas[data-orb]").forEach(mount);
      }
    }
  }).observe(root, { childList: true, subtree: true, attributes: true, attributeFilter: ["data-orb", "data-paused"] });
  document.addEventListener("visibilitychange", schedule);
  reducedMotion.addEventListener("change", () => (reducedMotion.matches ? redrawStatic() : schedule()));
  // Theme switches: repaint (the loop picks up the new ink on its next frame).
  prefersDark.addEventListener("change", redrawStatic);
  new MutationObserver(redrawStatic).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
}
