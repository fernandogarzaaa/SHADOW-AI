// Shadow dashboard. No build step, no inline handlers (CSP: script-src 'self').
// All user/node text is rendered through esc(); actions use data-* attributes
// and one delegated click handler.
import {
  authHeaders, clearCredential, loadCredential, newPublicKey,
  saveCredential, secureContext, updateExpiry,
} from "./signer.js";
import { initOrbs, orbHTML } from "./orb.js";

const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const state = { cred: null, health: null, authRequired: true, pairing: null, auditLimit: 100 };

// --- feedback ---------------------------------------------------------------------

function toast(msg, bad = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.toggle("bad", bad);
  t.classList.add("show");
  clearTimeout(t._t);
  t._t = setTimeout(() => t.classList.remove("show"), bad ? 4500 : 2400);
}

const FRIENDLY = {
  unknown_device: "This browser isn't paired with the node any more.",
  revoked_device: "This browser was disconnected from the node.",
  session_expired: "This browser's session expired. Pair it again.",
  sig_downgrade: "The node rejected an outdated signature. Pair this browser again.",
  invalid_signature: "The node couldn't verify this request. Check this computer's clock, then try again.",
  expired_timestamp: "This computer's clock is out of sync with the node. Fix the clock, then try again.",
  replayed_nonce: "That request was already sent. Try again.",
  invalid_bootstrap_code: "That setup code isn't right. Check the code in the node's terminal and try again. After 5 wrong tries the node prints a new code.",
  "too many pending pairings": "Too many devices are waiting to pair. Try again in a few minutes.",
  "owner device required": "Only an owner device can do that.",
  "approver is not a trusted owner device": "Only an owner device can do that.",
  "active consent grant required": "Add a consent grant for this data first.",
  "cloud escalation requires active grant and explicit approval": "Using the cloud model needs a cloud consent grant. Add one, or ask without the cloud.",
};
const REAUTH = new Set(["unknown_device", "revoked_device", "session_expired", "sig_downgrade"]);

class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function errText(e) {
  if (e instanceof ApiError) return e.message;
  if (e instanceof TypeError) return "Can't reach the node. Is it running?";
  return String(e?.message || e || "Something went wrong.");
}

// --- API --------------------------------------------------------------------------

async function api(path, { method = "GET", body, auth = true } = {}) {
  const payload = body === undefined ? "" : JSON.stringify(body);
  const headers = {};
  if (payload) headers["Content-Type"] = "application/json";
  if (auth && state.authRequired && state.cred) Object.assign(headers, await authHeaders(state.cred, method, path, payload));
  const r = await fetch(path, { method, headers, body: payload || undefined, credentials: "same-origin" });
  const expires = r.headers.get("x-shadow-session-expires");
  if (expires && state.cred) updateExpiry(state.cred, expires);
  const text = await r.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }
  if (!r.ok && r.status !== 202) {
    let code = data?.error?.code ?? data?.detail ?? `HTTP ${r.status}`;
    if (Array.isArray(code)) code = code.map((x) => x.msg || JSON.stringify(x)).join("; ");
    if (typeof code !== "string") code = JSON.stringify(code);
    if (r.status === 401 && REAUTH.has(code)) {
      await signOut(FRIENDLY[code]);
    }
    throw new ApiError(r.status, code, FRIENDLY[code] || data?.error?.message || code);
  }
  return { data, status: r.status };
}
const get = async (p) => (await api(p)).data;
const post = async (p, body = {}) => (await api(p, { method: "POST", body })).data;
const patch = async (p, body) => (await api(p, { method: "PATCH", body })).data;
const del = async (p) => (await api(p, { method: "DELETE" })).data;

// --- helpers ------------------------------------------------------------------------

const fmtTime = (v) => {
  if (v == null || v === "") return "";
  const d = typeof v === "number" ? new Date(v * 1000) : new Date(v);
  if (isNaN(d)) return "";
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
};
const relDays = (iso) => {
  const ms = new Date(iso) - Date.now();
  const days = Math.round(ms / 86400000);
  return days <= 0 ? "expired" : days === 1 ? "1 day left" : `${days} days left`;
};
const skeleton = (n = 3) => '<div class="skel" aria-hidden="true"></div>'.repeat(n);
const empty = (title, detail = "", orb = false) =>
  `<div class="empty">${orb ? `<canvas data-orb="breathing" data-size="32" data-paused aria-hidden="true"></canvas>` : ""}<b>${esc(title)}</b>${esc(detail)}</div>`;
const failed = (e) => `<div class="empty"><b>Couldn't load this.</b>${esc(errText(e))}</div>`;

async function busy(btn, fn) {
  if (!btn) return fn();
  const label = btn.textContent;
  btn.disabled = true;
  btn.setAttribute("aria-busy", "true");
  try {
    return await fn();
  } finally {
    btn.disabled = false;
    btn.removeAttribute("aria-busy");
    btn.textContent = label;
  }
}

function panelCard(p, extra = "") {
  const tiles = (p.tiles || []).map((t) => `<div class="tile"><b>${esc(t.value)}</b><span>${esc(t.label)}</span></div>`).join("");
  const rows = (p.rows || []).map((r) => `<div class="src"><b>${esc(r.title)}</b>${r.detail ? ` · ${esc(r.detail)}` : ""}${r.timestamp ? ` <span class="pill">${esc(fmtTime(r.timestamp))}</span>` : ""}</div>`).join("");
  return `<div class="card"><div class="card-head"><h2>${esc(p.title)}</h2>${extra}</div><p class="hint">${esc(p.headline)}</p>${tiles ? `<div class="tiles">${tiles}</div>` : ""}${rows}</div>`;
}

// --- router -------------------------------------------------------------------------

const VIEWS = {
  overview: ["Overview", "What needs your attention, at a glance.", loadOverview],
  ask: ["Ask Shadow", "Ask about your private memory.", null],
  approvals: ["Approvals", "Your explicit yes or no.", loadApprovals],
  actions: ["Actions", "Real actions, behind the approval gate.", loadActions],
  memory: ["Memory", "What Shadow knows, encrypted on this node.", loadMemory],
  goals: ["Goals", "Outcomes you're working toward.", loadGoals],
  schedule: ["Schedule", "Reminders and background tasks.", loadSchedule],
  feed: ["Feed", "Digests built on this node.", loadFeed],
  panels: ["Panels", "Glanceable views you define in plain words.", loadPanels],
  devices: ["Devices", "Everything that can talk to this node.", loadDevices],
  models: ["Models", "Where answers come from.", loadModels],
  audit: ["Audit", "A complete record of what the node did.", loadAudit],
};

function currentView() {
  const v = location.hash.replace(/^#\/?/, "").split("?")[0];
  return VIEWS[v] ? v : "overview";
}

function showView(focus) {
  const v = currentView();
  const [title, sub, loader] = VIEWS[v];
  $$("#nav a").forEach((a) => (a.dataset.view === v ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  $$(".view").forEach((s) => s.classList.toggle("on", s.id === `view-${v}`));
  $("#title").textContent = title;
  $("#subtitle").textContent = sub;
  document.title = `${title} · Shadow`;
  if (focus) $("#title").focus();
  if (loader) loader();
}

window.addEventListener("hashchange", () => showView(true));

// --- status, pause, theme --------------------------------------------------------

async function refreshStatus() {
  try {
    const { data: h } = await api("/health", { auth: false });
    state.health = h;
    $("#statusTxt").textContent = `Node ${h.version}${h.auth_required ? "" : " · auth off (dev mode)"}`;
    $("#ver").textContent = state.cred?.name ? `${state.cred.name}` : `v${h.version}`;
    $("#liveDot").className = `live ${h.emergency_paused ? "bad" : "ok"}`;
    $("#pauseSw").setAttribute("aria-checked", String(!!h.emergency_paused));
    $("#pausedBanner").hidden = !h.emergency_paused;
    setBrandOrb(h.emergency_paused ? "paused" : "idle");
  } catch {
    $("#statusTxt").textContent = "Node offline";
    $("#liveDot").className = "live bad";
    setBrandOrb("offline");
  }
}

// The sidebar orb is Shadow's live mark: it breathes while idle, works while
// a request is in flight, and freezes when paused or offline.
let brandBusy = 0;
let brandBase = "idle";
function setBrandOrb(base) {
  if (base) brandBase = base;
  const orb = $("#brandOrb");
  if (!orb) return;
  const busyNow = brandBusy > 0 && brandBase === "idle";
  orb.dataset.orb = busyNow ? "working" : "breathing";
  if (brandBase === "idle") delete orb.dataset.paused;
  else orb.dataset.paused = "";
  orb.setAttribute("aria-label", busyNow ? "Shadow is working" : brandBase === "paused" ? "Shadow is paused" : brandBase === "offline" ? "Node offline" : "Shadow is idle");
}
function trackBusy(promise) {
  brandBusy++;
  setBrandOrb();
  return promise.finally(() => { brandBusy--; setBrandOrb(); });
}

async function refreshBadges() {
  try {
    const r = await get("/approvals?status=pending");
    const b = $("#apprBadge");
    b.hidden = !r.count;
    b.textContent = r.count;
    b.setAttribute("aria-label", `${r.count} waiting`);
  } catch { /* status line already reports connectivity */ }
}

$("#pauseSw").addEventListener("click", async () => {
  const on = $("#pauseSw").getAttribute("aria-checked") !== "true";
  try {
    await post("/emergency_pause", { paused: on, reason: "toggled from dashboard" });
    toast(on ? "Paused. Shadow won't act until you resume." : "Resumed.");
    refreshStatus();
  } catch (e) {
    toast(errText(e), true);
  }
});

const THEMES = ["system", "dark", "light"];
function applyTheme(t) {
  if (t === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = t;
  $("#themeBtn").textContent = `Theme: ${t}`;
}
let theme = "system";
try { theme = localStorage.getItem("shadow.theme") || "system"; } catch { /* storage blocked */ }
applyTheme(theme);
$("#themeBtn").addEventListener("click", () => {
  theme = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
  try { localStorage.setItem("shadow.theme", theme); } catch { /* ignore */ }
  applyTheme(theme);
});

// --- connect / pairing ------------------------------------------------------------

function showConnect(message) {
  $("#app").hidden = true;
  $("#connect").hidden = false;
  $("#pairForm").hidden = false;
  $("#pairWaiting").hidden = true;
  $("#insecureNote").hidden = secureContext;
  $("#bootstrapField").hidden = !state.health?.bootstrap_open;
  if (!$("#pairName").value) $("#pairName").value = defaultBrowserName();
  setPairError(message || "");
  $("#connectTitle").focus();
}

function defaultBrowserName() {
  const ua = navigator.userAgent;
  const browser = /Edg\//.test(ua) ? "Edge" : /Chrome\//.test(ua) ? "Chrome" : /Firefox\//.test(ua) ? "Firefox" : /Safari\//.test(ua) ? "Safari" : "Browser";
  const os = /Mac OS X/.test(ua) ? "Mac" : /Windows/.test(ua) ? "Windows" : /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iOS" : /Linux/.test(ua) ? "Linux" : "";
  return `${browser}${os ? ` on ${os}` : ""}`;
}

function setPairError(msg) {
  $("#pairError").hidden = !msg;
  $("#pairError").textContent = msg;
}

$("#pairForm").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  setPairError("");
  const name = $("#pairName").value.trim() || defaultBrowserName();
  const code = $("#pairBootstrap").value.trim();
  if (state.health?.bootstrap_open && !code) {
    setPairError("Enter the setup code from the node's terminal.");
    $("#pairBootstrap").focus();
    return;
  }
  await busy($("#pairBtn"), async () => {
    try {
      const start = (await api("/pair/start", { method: "POST", auth: false, body: { device_name: name, public_key: newPublicKey(), client_kind: "web" } })).data;
      state.pairing = { id: start.pairing_id, name, code, startedAt: Date.now(), ttl: start.expires_in_seconds };
      await confirmPairing();
    } catch (e) {
      setPairError(errText(e));
    }
  });
});

async function confirmPairing() {
  const p = state.pairing;
  if (!p) return;
  const body = { pairing_id: p.id };
  if (p.code) body.bootstrap_code = p.code;
  let res;
  try {
    res = await api("/pair/confirm", { method: "POST", auth: false, body });
  } catch (e) {
    state.pairing = null;
    $("#pairForm").hidden = false;
    $("#pairWaiting").hidden = true;
    setPairError(e.status === 404 || e.status === 410 ? "The pairing request expired. Start again." : errText(e));
    return;
  }
  if (res.status === 202) {
    $("#pairForm").hidden = true;
    $("#pairWaiting").hidden = false;
    $("#pairCode").textContent = p.id.slice(-6).toUpperCase();
    const left = Math.max(0, Math.round(p.ttl - (Date.now() - p.startedAt) / 1000));
    $("#pairExpiry").textContent = `The request expires in ${Math.ceil(left / 60)} minute${left > 60 ? "s" : ""}.`;
    p.timer = setTimeout(confirmPairing, 2000);
    return;
  }
  const d = res.data;
  state.pairing = null;
  state.cred = await saveCredential({ deviceId: d.device.id, secret: d.secret, expiresAt: d.session_expires_at, name: d.device.name });
  $("#pairBootstrap").value = "";
  toast(d.device.is_owner ? "Paired. This browser is the owner." : "Paired.");
  enterApp();
}

async function signOut(message) {
  state.cred = null;
  await clearCredential();
  showConnect(message);
}

// --- delegated actions -------------------------------------------------------------

const ACTIONS = {
  "pair-cancel": () => {
    clearTimeout(state.pairing?.timer);
    state.pairing = null;
    showConnect();
  },
  "sign-out": async () => {
    if (!confirm("Disconnect this browser? You'll need to pair it again to use the dashboard.")) return;
    try {
      if (state.cred) await post(`/devices/${encodeURIComponent(state.cred.deviceId)}/revoke`);
    } catch { /* still forget locally */ }
    await signOut("Disconnected.");
  },
  reload: (el) => VIEWS[el.dataset.target]?.[2]?.(),
  "approval-decide": (el) => decideApproval(el.dataset.id, el.dataset.ok === "1", el),
  "approval-run": (el) => runApproval(el.dataset.id, el),
  "mem-delete": async (el) => {
    if (!confirm("Delete this memory? It will no longer be searched or sent anywhere.")) return;
    try {
      await del(`/memory/${encodeURIComponent(el.dataset.id)}`);
      toast("Deleted.");
      loadMemory();
      searchMem();
    } catch (e) { toast(errText(e), true); }
  },
  "goal-progress": (el) => goalProgress(el.dataset.id),
  "goal-status": async (el) => {
    try {
      await patch(`/goals/${encodeURIComponent(el.dataset.id)}`, { status: el.dataset.status });
      toast(el.dataset.status === "completed" ? "Goal completed." : "Goal updated.");
      loadGoals();
    } catch (e) { toast(errText(e), true); }
  },
  "goal-delete": async (el) => {
    if (!confirm("Delete this goal and its progress history?")) return;
    try { await del(`/goals/${encodeURIComponent(el.dataset.id)}`); loadGoals(); } catch (e) { toast(errText(e), true); }
  },
  "sched-create": async (el) => {
    try {
      const pr = JSON.parse(el.dataset.proposal);
      await post("/scheduled-tasks", { title: pr.title, note: pr.note || "", due_at: pr.due_at, recurrence: pr.recurrence });
      $("#schedPreview").innerHTML = "";
      $("#schedText").value = "";
      toast("Scheduled.");
      loadSchedule();
    } catch (e) { toast(errText(e), true); }
  },
  "sched-toggle": async (el) => {
    try {
      await patch(`/scheduled-tasks/${encodeURIComponent(el.dataset.id)}`, { enabled: el.dataset.enabled !== "1" });
      loadSchedule();
    } catch (e) { toast(errText(e), true); }
  },
  "sched-delete": async (el) => {
    if (!confirm("Delete this reminder?")) return;
    try { await del(`/scheduled-tasks/${encodeURIComponent(el.dataset.id)}`); loadSchedule(); } catch (e) { toast(errText(e), true); }
  },
  "sched-suggest": (el) => {
    $("#schedText").value = el.dataset.text;
    $("#schedForm").requestSubmit();
  },
  "feed-generate": async (el) => {
    await busy(el, async () => {
      el.innerHTML = `${orbHTML("composing", 20)}Writing…`;
      try { const r = await post("/feed/generate", { force: true }); toast(`${r.count} new item${r.count === 1 ? "" : "s"}.`); loadFeed(); } catch (e) { toast(errText(e), true); }
    });
  },
  "panel-create": async (el) => {
    try {
      const pr = JSON.parse(el.dataset.proposal);
      await post("/custom-panels", { name: pr.name, source: pr.source, filter: pr.filter, sort: pr.sort, limit: pr.limit });
      $("#panelPreview").innerHTML = "";
      $("#panelText").value = "";
      toast("Panel added.");
      loadPanels();
    } catch (e) { toast(errText(e), true); }
  },
  "panel-suggest": (el) => {
    $("#panelText").value = el.dataset.text;
    $("#panelForm").requestSubmit();
  },
  "panel-delete": async (el) => {
    if (!confirm("Remove this panel?")) return;
    try { await del(`/custom-panels/${encodeURIComponent(el.dataset.id)}`); loadPanels(); } catch (e) { toast(errText(e), true); }
  },
  "pair-approve": async (el) => {
    try { await post("/pair/approve", { pairing_id: el.dataset.id }); toast("Approved. The device will finish pairing on its own."); loadDevices(); } catch (e) { toast(errText(e), true); }
  },
  "device-revoke": async (el) => {
    const self = el.dataset.id === state.cred?.deviceId;
    if (!confirm(self ? "Disconnect this browser?" : `Disconnect "${el.dataset.name}"? It will lose access immediately.`)) return;
    try {
      await post(`/devices/${encodeURIComponent(el.dataset.id)}/revoke`);
      if (self) return signOut("Disconnected.");
      toast("Disconnected.");
      loadDevices();
    } catch (e) { toast(errText(e), true); }
  },
  "device-renew": async (el) => {
    try { await post(`/devices/${encodeURIComponent(el.dataset.id)}/renew`); toast("Renewed for 30 days."); loadDevices(); } catch (e) { toast(errText(e), true); }
  },
  "add-phone": async (el) => {
    await busy(el, async () => {
      try {
        const r = await post("/devices/register", { name: "Phone", public_key: newPublicKey() });
        const url = location.origin;
        const payload = JSON.stringify({ v: 1, url, pairing_id: r.pairing_id });
        $("#addPhoneOut").innerHTML = `
          <dl class="kv" style="margin-top:12px">
            <dt>Node address</dt><dd><code>${esc(url)}</code> <button class="link" type="button" data-action="copy" data-text="${esc(url)}">Copy</button></dd>
            <dt>Pairing ID</dt><dd><code>${esc(r.pairing_id)}</code> <button class="link" type="button" data-action="copy" data-text="${esc(r.pairing_id)}">Copy</button></dd>
            <dt>Code</dt><dd><b>${esc(r.code)}</b></dd>
            <dt>Expires</dt><dd>in ${Math.round(r.expires_in_seconds / 60)} minutes</dd>
          </dl>
          <p class="hint" style="margin-top:12px">QR payload (paste into a QR generator if you prefer scanning): <code>${esc(payload)}</code> <button class="link" type="button" data-action="copy" data-text="${esc(payload)}">Copy</button></p>
          ${/^(localhost|127\.)/.test(location.hostname) ? '<p class="banner">This address only works on this computer. For a phone, start the node with SHADOW_HOST=0.0.0.0 and use its LAN address.</p>' : ""}`;
      } catch (e) { toast(errText(e), true); }
    });
  },
  copy: async (el) => {
    try { await navigator.clipboard.writeText(el.dataset.text); toast("Copied."); } catch { toast("Couldn't copy. Select the text and copy it manually.", true); }
  },
  "provider-connect": async (el) => {
    const name = el.dataset.name;
    const input = $(`#key-${name}`);
    const k = input.value.trim();
    if (!k) { toast("Paste an API key first.", true); input.focus(); return; }
    try { await post(`/providers/${encodeURIComponent(name)}/connect`, { api_key: k }); input.value = ""; toast("Connected."); loadModels(); } catch (e) { toast(errText(e), true); }
  },
  "provider-disconnect": async (el) => {
    try { await del(`/providers/${encodeURIComponent(el.dataset.name)}`); toast("Disconnected."); loadModels(); } catch (e) { toast(errText(e), true); }
  },
  "provider-oauth": async (el) => {
    try {
      const redirect = `${location.origin}/`;
      const r = await get(`/providers/${encodeURIComponent(el.dataset.name)}/oauth/start?redirect_uri=${encodeURIComponent(redirect)}`);
      sessionStorage.setItem("shadow.oauth", el.dataset.name);
      location.assign(r.authorization_url);
    } catch (e) { toast(errText(e), true); }
  },
  "audit-more": () => {
    state.auditLimit = Math.min(1000, state.auditLimit + 200);
    loadAudit();
  },
};

document.addEventListener("click", (ev) => {
  const el = ev.target.closest("[data-action]");
  if (!el) return;
  const fn = ACTIONS[el.dataset.action];
  if (fn) {
    ev.preventDefault();
    fn(el);
  }
});

// --- overview ------------------------------------------------------------------------

async function loadOverview() {
  get("/approvals?status=pending").then((r) => {
    const n = r.count;
    $("#heroTitle").textContent = n ? `${n} approval${n === 1 ? "" : "s"} waiting for you.` : "All quiet.";
    $("#heroSub").innerHTML = n ? 'Nothing runs until you decide. <a href="#/approvals">Review now</a>' : "Nothing needs your decision right now.";
    $("#heroOrb").dataset.orb = n ? "listening" : "breathing";
  }).catch(() => {});
  const out = $("#overviewPanels");
  if (!out.innerHTML) out.innerHTML = skeleton(3);
  try {
    const panels = await get("/panels");
    out.innerHTML = panels.map((p) => panelCard(p, p.id === "approvals" && !p.empty ? '<a class="btn sm" href="#/approvals">Review</a>' : "")).join("") ||
      empty("Nothing to show yet.");
  } catch (e) {
    out.innerHTML = `<div class="card">${failed(e)}</div>`;
  }
}

// --- ask ----------------------------------------------------------------------------

$("#askForm").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const prompt = $("#askInput").value.trim();
  if (!prompt) return $("#askInput").focus();
  const cloud = $("#askCloud").checked;
  const form = $("#askForm");
  await busy($("#askBtn"), async () => {
    $("#askBtn").textContent = "Thinking…";
    form.classList.add("beam");
    form.setAttribute("aria-busy", "true");
    $("#askOut").innerHTML = `<div class="thinking" role="status">${orbHTML("searching", 20)}<span>Searching your memory…</span></div>`;
    const phase = setTimeout(() => {
      const t = $("#askOut .thinking");
      if (!t) return;
      t.querySelector("canvas").dataset.orb = cloud ? "connecting" : "composing";
      t.querySelector("span").textContent = cloud ? "Asking the cloud model…" : "Writing the answer…";
    }, 900);
    try {
      const r = await trackBusy(post("/agent/ask", { prompt, allow_cloud: cloud, cloud_approval: cloud }));
      const sv = r.savings || {};
      const where = r.route === "frontier" ? `cloud · ${r.model_used}` : `on-device · ${r.model_used}`;
      const tone = r.degraded ? " bad" : r.model_used === "local_mock" ? " warn" : "";
      let h = `<div class="answer-row"><canvas data-orb="${r.degraded ? "breathing" : "composing"}" data-size="32" data-color="accent" data-paused aria-hidden="true"></canvas><div class="answer${tone}">${esc(r.answer)}</div></div>`;
      if (r.model_used === "local_mock" && !r.degraded) {
        h += `<p class="hint" style="margin-top:8px">This came from the on-device placeholder model, not a real one. Connect a provider in <a href="#/models">Models</a> and tick "Use the cloud model" for real answers.</p>`;
      }
      h += `<div class="meta"><span class="pill accent">${esc(where)}</span><span class="pill">${(r.sources || []).length} source${(r.sources || []).length === 1 ? "" : "s"}</span>`;
      if (sv.tokens_saved_estimate) h += `<span class="pill ok">~${esc(sv.tokens_saved_estimate)} tokens saved${sv.saved_pct ? ` (${esc(sv.saved_pct)}%)` : ""}</span>`;
      h += "</div>";
      (r.why || []).forEach((w) => (h += `<div class="src">${esc(w)}</div>`));
      $("#askOut").innerHTML = h;
      if (sv.raw_context_tokens != null) {
        $("#savingsBox").innerHTML = `<span class="pill accent">route · ${esc(r.route)}</span><span class="pill">context ${esc(sv.raw_context_tokens)} tokens</span><span class="pill">sent ${esc(sv.frontier_tokens_sent)} tokens</span><span class="pill ok">saved ~${esc(sv.tokens_saved_estimate)} (${esc(sv.saved_pct || 0)}%)</span>`;
      }
    } catch (e) {
      $("#askOut").innerHTML = `<div class="answer bad" role="alert">${esc(errText(e))}</div>`;
    } finally {
      clearTimeout(phase);
      form.classList.remove("beam");
      form.removeAttribute("aria-busy");
    }
  });
});
$("#heroForm").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const q = $("#heroAsk").value.trim();
  if (!q) return $("#heroAsk").focus();
  $("#askInput").value = q;
  $("#heroAsk").value = "";
  location.hash = "#/ask";
  setTimeout(() => $("#askForm").requestSubmit(), 0);
});
$("#askInput").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && (ev.metaKey || ev.ctrlKey)) {
    ev.preventDefault();
    $("#askForm").requestSubmit();
  }
});

// --- approvals ------------------------------------------------------------------------

function approvalItem(a, mode) {
  const act = a.action || {};
  const params = act.params && Object.keys(act.params).length ? `<pre class="json">${esc(JSON.stringify(act.params, null, 2))}</pre>` : "";
  const dbl = a.requires_double_confirmation ? '<span class="pill warn">needs a second confirmation</span>' : "";
  const exp = a.expires_at ? `<span class="pill">expires ${esc(fmtTime(a.expires_at))}</span>` : "";
  const buttons = mode === "pending"
    ? `<button class="btn sm" type="button" data-action="approval-decide" data-ok="1" data-id="${esc(a.id)}">Approve</button>
       <button class="ghost sm danger" type="button" data-action="approval-decide" data-ok="0" data-id="${esc(a.id)}">Deny</button>`
    : `<button class="btn sm" type="button" data-action="approval-run" data-id="${esc(a.id)}">Run now</button>`;
  return `<div class="item${mode === "pending" ? " beam-pulse" : ""}"><div class="t">${esc(act.tool_name)} <span class="pill ${esc(a.risk_label)}">${esc(a.risk_label)} risk</span>${dbl}${exp}</div>
    <div class="d">${esc(act.description)}</div>${a.consequence ? `<div class="d">${esc(a.consequence)}</div>` : ""}${params}
    <div class="acts">${buttons}</div></div>`;
}

const approvalCache = new Map();

async function loadApprovals() {
  const out = $("#apprOut");
  const ready = $("#apprReady");
  if (!out.innerHTML) { out.innerHTML = skeleton(2); ready.innerHTML = skeleton(1); }
  try {
    const [pend, appr] = await Promise.all([get("/approvals?status=pending"), get("/approvals?status=approved")]);
    [...pend.items, ...appr.items].forEach((a) => approvalCache.set(a.id, a));
    out.innerHTML = pend.items.length ? pend.items.map((a) => approvalItem(a, "pending")).join("") : empty("Nothing waiting.", " New requests will appear here.", true);
    ready.innerHTML = appr.items.length ? appr.items.map((a) => approvalItem(a, "approved")).join("") : empty("Nothing approved and waiting to run.");
    refreshBadges();
  } catch (e) {
    out.innerHTML = failed(e);
    ready.innerHTML = "";
  }
}

async function decideApproval(id, ok, el) {
  await busy(el, async () => {
    try {
      if (ok) {
        await post(`/approvals/${encodeURIComponent(id)}/approve`);
        toast("Approved. Run it below when you're ready.");
      } else {
        const reason = prompt("Why are you denying this? (optional)") ?? "";
        await post(`/approvals/${encodeURIComponent(id)}/deny`, { reason: reason || "Denied from dashboard" });
        toast("Denied.");
      }
      loadApprovals();
    } catch (e) { toast(errText(e), true); }
  });
}

async function runApproval(id, el) {
  const a = approvalCache.get(id);
  if (!a) return toast("Refresh and try again.", true);
  let double = false;
  if (a.requires_double_confirmation) {
    double = confirm(`Second confirmation: run "${a.action.tool_name}" now?\n\n${a.consequence || a.action.description}`);
    if (!double) return;
  }
  await busy(el, async () => {
    try {
      const r = await post("/agent/execute", { action: a.action, approval_id: id, double_confirmed: double });
      toast(r.ok === false ? `Didn't run: ${r.reason || r.status}` : "Done.", r.ok === false);
      loadApprovals();
    } catch (e) { toast(errText(e), true); }
  });
}

// --- actions ----------------------------------------------------------------------------

const FIELDS = {
  "note.create": [["title", "Title"], ["body", "Body", "area"]],
  "note.append": [["title", "Note title"], ["body", "Text to add", "area"]],
  "reminder.create": [["text", "Reminder"], ["when", "When (optional)"]],
  "calendar.create": [["title", "Event title"], ["start", "Start (e.g. 2026-11-10T09:00)"], ["end", "End (optional)"], ["description", "Description (optional)", "area"]],
  "email.draft": [["to", "Recipient email"], ["subject", "Subject"], ["body", "Body", "area"]],
  "http.get": [["url", "URL (public https:// address)"]],
  "web.search": [["query", "Search query"]],
};
let toolMeta = [];

async function loadActions() {
  const cat = $("#toolCatalogOut");
  if (!cat.innerHTML) cat.innerHTML = skeleton(3);
  try {
    const r = await get("/tools");
    toolMeta = r.tool_metadata || [];
    cat.innerHTML = toolMeta.map((t) => `<div class="item"><div class="t">${esc(t.name)} ${t.needs_explicit_consent ? '<span class="pill warn">extra consent</span>' : ""}</div><div class="d">${esc(t.description || "")}</div></div>`).join("");
    const sel = $("#actTool");
    const current = sel.value;
    const usable = toolMeta.filter((t) => FIELDS[t.name]);
    sel.innerHTML = usable.map((t) => `<option value="${esc(t.name)}">${esc(t.name)}${t.needs_explicit_consent ? " (extra consent)" : ""}</option>`).join("");
    if (current && FIELDS[current]) sel.value = current;
    renderFields();
  } catch (e) {
    cat.innerHTML = failed(e);
  }
}

function renderFields() {
  const t = $("#actTool").value;
  $("#actFields").innerHTML = (FIELDS[t] || []).map(([k, ph, ty]) =>
    ty === "area"
      ? `<label for="f-${k}">${esc(ph)}</label><textarea id="f-${k}" data-k="${k}"></textarea>`
      : `<label for="f-${k}">${esc(ph)}</label><input id="f-${k}" data-k="${k}" autocomplete="off" />`).join("");
}
$("#actTool").addEventListener("change", renderFields);

$("#actForm").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const tool = $("#actTool").value;
  const params = {};
  $$("#actFields [data-k]").forEach((el) => { if (el.value.trim()) params[el.dataset.k] = el.value.trim(); });
  const action = { tool_name: tool, description: `Dashboard request: ${tool}`, params, requires_approval: true };
  await busy($("#actBtn"), async () => {
    try {
      const a = await post("/approvals", { action, reason: "Requested from the dashboard" });
      approvalCache.set(a.id, a);
      $("#actOut").innerHTML = `<div class="answer">Approval requested for <b>${esc(tool)}</b>. Nothing has run yet.</div>
        <div class="actions"><a class="btn sm" href="#/approvals">Review in Approvals</a></div>`;
      $$("#actFields [data-k]").forEach((el) => (el.value = ""));
      refreshBadges();
    } catch (e) {
      $("#actOut").innerHTML = `<div class="answer bad" role="alert">${esc(errText(e))}</div>`;
    }
  });
});

// --- memory -------------------------------------------------------------------------------

function memItem(x, withDelete = true) {
  const it = x.item || x;
  const del = withDelete && it.id ? `<div class="acts"><button class="ghost sm danger" type="button" data-action="mem-delete" data-id="${esc(it.id)}">Delete</button></div>` : "";
  const flags = [it.sensitive ? '<span class="pill warn">sensitive</span>' : "", it.do_not_send_to_cloud ? '<span class="pill">stays on device</span>' : ""].join("");
  return `<div class="item"><div class="t">${esc(it.source?.title || "Memory")} ${flags}</div><div class="d">${esc(it.text)}</div>
    <div class="meta">${it.category ? `<span class="pill">${esc(it.category)}</span>` : ""}${it.confidence != null ? `<span class="pill">confidence ${Number(it.confidence).toFixed(2)}</span>` : ""}${it.created_at ? `<span class="pill">${esc(fmtTime(it.created_at))}</span>` : ""}</div>${del}</div>`;
}

async function loadMemory() {
  const out = $("#memRecent");
  if (!out.innerHTML) out.innerHTML = skeleton(3);
  try {
    const r = await get("/memory/recent?limit=20");
    out.innerHTML = r.items.length ? r.items.map((x) => memItem(x)).join("") : empty("Memory is empty.", " Add something above to get started.");
  } catch (e) {
    out.innerHTML = failed(e);
  }
  if (!$("#memOut").innerHTML) $("#memOut").innerHTML = empty("Results appear here as you type.");
}

$("#memForm").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const text = $("#memText").value.trim();
  if (!text) return $("#memText").focus();
  const btn = ev.submitter;
  await busy(btn, async () => {
    try {
      const r = await post("/memory/ingest", { text, source_title: $("#memTitle").value.trim() || "Manual import" });
      toast(`Saved ${r.items?.length ?? ""} memory item${r.items?.length === 1 ? "" : "s"}.`);
      $("#memText").value = "";
      loadMemory();
    } catch (e) { toast(errText(e), true); }
  });
});

let memTimer;
$("#memQuery").addEventListener("input", () => { clearTimeout(memTimer); memTimer = setTimeout(searchMem, 250); });
async function searchMem() {
  const q = $("#memQuery").value.trim();
  const out = $("#memOut");
  if (!q) { out.innerHTML = empty("Results appear here as you type."); return; }
  try {
    const r = await get(`/memory/search?q=${encodeURIComponent(q)}&limit=10`);
    out.innerHTML = r.length ? r.map((x) => memItem(x)).join("") : empty("No matches.", " Try different words.");
  } catch (e) {
    out.innerHTML = failed(e);
  }
}

// --- goals -------------------------------------------------------------------------------

async function loadGoals() {
  const out = $("#goalsOut");
  if (!out.innerHTML) out.innerHTML = skeleton(2);
  const status = $("#goalFilter").value;
  try {
    const goals = await get(`/goals${status ? `?status=${status}` : ""}`);
    out.innerHTML = goals.length ? goals.map((g) => {
      const pct = g.latest_percent ?? 0;
      const due = g.target_date ? `<span class="pill">due ${esc(g.target_date)}</span>` : "";
      const st = g.status !== "active" ? `<span class="pill ${g.status === "completed" ? "ok" : ""}">${esc(g.status)}</span>` : "";
      const acts = g.status === "active"
        ? `<button class="btn sm" type="button" data-action="goal-progress" data-id="${esc(g.id)}">Log progress</button>
           <button class="ghost sm" type="button" data-action="goal-status" data-status="completed" data-id="${esc(g.id)}">Mark complete</button>`
        : `<button class="ghost sm" type="button" data-action="goal-status" data-status="active" data-id="${esc(g.id)}">Reopen</button>`;
      return `<div class="item"><div class="t">${esc(g.title)} ${st}${due}</div>${g.description ? `<div class="d">${esc(g.description)}</div>` : ""}
        <div class="progress" role="progressbar" aria-label="Progress for ${esc(g.title)}" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><i style="width:${Math.max(0, Math.min(100, pct))}%"></i></div>
        <div class="meta"><span class="pill">${pct}%</span><span class="pill">${g.entry_count} update${g.entry_count === 1 ? "" : "s"}</span>${g.last_progress_at ? `<span class="pill">last ${esc(fmtTime(g.last_progress_at))}</span>` : ""}</div>
        <div class="acts">${acts}<button class="ghost sm danger" type="button" data-action="goal-delete" data-id="${esc(g.id)}">Delete</button></div></div>`;
    }).join("") : empty(status === "completed" ? "No completed goals yet." : "No goals yet.", status === "completed" ? "" : " Add one above.");
  } catch (e) {
    out.innerHTML = failed(e);
  }
}
$("#goalFilter").addEventListener("change", loadGoals);

$("#goalForm").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const title = $("#goalTitle").value.trim();
  if (!title) return $("#goalTitle").focus();
  try {
    await post("/goals", { title, description: $("#goalDesc").value.trim(), target_date: $("#goalDate").value || null });
    ev.target.reset();
    toast("Goal added.");
    loadGoals();
  } catch (e) { toast(errText(e), true); }
});

async function goalProgress(id) {
  const note = prompt("What progress did you make?");
  if (!note) return;
  const raw = prompt("Percent complete (0-100, optional)");
  const percent = raw === null || raw.trim() === "" ? null : Math.max(0, Math.min(100, parseInt(raw, 10) || 0));
  try {
    await post(`/goals/${encodeURIComponent(id)}/progress`, { note, percent });
    toast("Progress logged.");
    loadGoals();
  } catch (e) { toast(errText(e), true); }
}

// --- schedule -----------------------------------------------------------------------------

$("#schedForm").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const text = $("#schedText").value.trim();
  if (!text) return;
  const out = $("#schedPreview");
  try {
    const r = await post("/reminders/parse", { text });
    if (r.status === "parsed") {
      const p = r.proposal;
      out.innerHTML = `<div class="answer"><b>${esc(p.title)}</b><br>${esc(p.plain_cadence || "")} · first on ${esc(fmtTime(p.due_at))}</div>
        <div class="actions"><button class="btn sm" type="button" data-action="sched-create" data-proposal="${esc(JSON.stringify(p))}">Save</button></div>`;
    } else {
      const opts = (r.options || []).map((o) => `<button class="ghost sm" type="button" data-action="sched-suggest" data-text="${esc(o)}">${esc(o)}</button>`).join("");
      out.innerHTML = `<div class="answer warn">${esc(r.question || "Could you say that differently?")}</div>${opts ? `<div class="acts" style="margin-top:10px">${opts}</div>` : ""}`;
    }
  } catch (e) {
    out.innerHTML = `<div class="answer bad">${esc(errText(e))}</div>`;
  }
});

async function loadSchedule() {
  const out = $("#schedOut");
  if (!out.innerHTML) out.innerHTML = skeleton(3);
  try {
    const tasks = await get("/scheduled-tasks");
    out.innerHTML = tasks.length ? tasks.map((t) => {
      const kind = t.kind === "reminder" ? '<span class="pill accent">reminder</span>' : '<span class="pill">background task</span>';
      const state_ = t.enabled ? "" : '<span class="pill">off</span>';
      const next = t.next_run ? `<span class="pill">next ${esc(fmtTime(t.next_run))}</span>` : "";
      const delBtn = t.kind === "reminder" ? `<button class="ghost sm danger" type="button" data-action="sched-delete" data-id="${esc(t.id)}">Delete</button>` : "";
      return `<div class="item"><div class="t">${esc(t.title)} ${kind}${state_}</div><div class="d">${esc(t.cadence)}${t.description ? ` · ${esc(t.description)}` : ""}</div>
        <div class="meta">${next}${t.last_run ? `<span class="pill">last ${esc(fmtTime(t.last_run))}</span>` : ""}</div>
        <div class="acts"><button class="ghost sm" type="button" data-action="sched-toggle" data-enabled="${t.enabled ? 1 : 0}" data-id="${esc(t.id)}">${t.enabled ? "Turn off" : "Turn on"}</button>${delBtn}</div></div>`;
    }).join("") : empty("Nothing scheduled.");
  } catch (e) {
    out.innerHTML = failed(e);
  }
}

// --- feed -----------------------------------------------------------------------------------

async function loadFeed() {
  const out = $("#feedOut");
  if (!out.innerHTML) out.innerHTML = skeleton(3);
  try {
    const r = await get("/feed?limit=30");
    out.innerHTML = r.items.length ? r.items.map((u) => `<div class="item"><div class="t">${esc(u.title)} <span class="pill">${esc(u.kind)}</span></div><div class="d" style="white-space:pre-wrap">${esc(u.body)}</div><div class="meta"><span class="pill">${esc(fmtTime(u.created_at))}</span></div></div>`).join("")
      : empty("Your feed is empty.", ' Select "Refresh feed" to build it.', true);
  } catch (e) {
    out.innerHTML = failed(e);
  }
}

// --- panels ------------------------------------------------------------------------------------

$("#panelForm").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const text = $("#panelText").value.trim();
  if (!text) return;
  const out = $("#panelPreview");
  try {
    const r = await post("/custom-panels/parse", { text });
    if (r.status === "proposal") {
      const p = r.proposal;
      out.innerHTML = `<div class="answer"><b>${esc(p.name)}</b><br>${esc(p.source)} · ${esc(p.filter)} · ${esc(p.sort)} · up to ${esc(p.limit)}</div>
        <div class="actions"><button class="btn sm" type="button" data-action="panel-create" data-proposal="${esc(JSON.stringify(p))}">Add panel</button></div>`;
    } else {
      const opts = (r.options || []).map((o) => `<button class="ghost sm" type="button" data-action="panel-suggest" data-text="${esc(o)}">${esc(o)}</button>`).join("");
      out.innerHTML = `<div class="answer warn">${esc(r.question)}</div>${opts ? `<div class="acts" style="margin-top:10px">${opts}</div>` : ""}`;
    }
  } catch (e) {
    out.innerHTML = `<div class="answer bad">${esc(errText(e))}</div>`;
  }
});

async function loadPanels() {
  const out = $("#panelsOut");
  if (!out.innerHTML) out.innerHTML = skeleton(2);
  try {
    const defs = await get("/custom-panels");
    if (!defs.length) {
      out.innerHTML = `<div class="card">${empty("No custom panels yet.", " Describe one above.")}</div>`;
      return;
    }
    const rendered = await Promise.all(defs.map((d) => get(`/custom-panels/${encodeURIComponent(d.id)}/render`).catch(() => null)));
    out.innerHTML = defs.map((d, i) => {
      const remove = `<button class="ghost sm danger" type="button" data-action="panel-delete" data-id="${esc(d.id)}">Remove</button>`;
      return rendered[i] ? panelCard({ ...rendered[i], title: d.name }, remove) : `<div class="card"><div class="card-head"><h2>${esc(d.name)}</h2>${remove}</div>${empty("Couldn't render this panel.")}</div>`;
    }).join("");
  } catch (e) {
    out.innerHTML = `<div class="card">${failed(e)}</div>`;
  }
}

// --- devices -------------------------------------------------------------------------------------

async function loadDevices() {
  const out = $("#devicesOut");
  const pend = $("#pendingOut");
  if (!out.innerHTML) out.innerHTML = skeleton(2);
  try {
    const r = await get("/devices");
    const me = state.cred?.deviceId;
    const devices = [...r.items].sort((a, b) => Number(a.revoked) - Number(b.revoked));
    out.innerHTML = devices.length ? devices.map((d) => {
      const tags = [
        d.id === me ? '<span class="pill accent">this browser</span>' : "",
        d.is_owner ? '<span class="pill">owner</span>' : "",
        d.client_kind ? `<span class="pill">${esc(d.client_kind)}</span>` : "",
        d.revoked ? '<span class="pill bad">disconnected</span>' : new Date(d.session_expires_at) < new Date() ? '<span class="pill bad">expired</span>' : `<span class="pill">${esc(relDays(d.session_expires_at))}</span>`,
      ].join("");
      const acts = d.revoked ? "" : `<div class="acts"><button class="ghost sm" type="button" data-action="device-renew" data-id="${esc(d.id)}">Renew</button>
        <button class="ghost sm danger" type="button" data-action="device-revoke" data-id="${esc(d.id)}" data-name="${esc(d.name)}">Disconnect</button></div>`;
      return `<div class="item"><div class="t">${esc(d.name)} ${tags}</div><div class="d">Paired ${esc(fmtTime(d.registered_at))} · fingerprint <code>${esc((d.fingerprint || "").slice(0, 12))}</code></div>${acts}</div>`;
    }).join("") : empty("No devices.");
  } catch (e) {
    out.innerHTML = failed(e);
  }
  try {
    const p = await get("/pair/pending");
    $("#pendingCard").hidden = false;
    pend.innerHTML = p.items.length ? p.items.map((x) => `<div class="item"><div class="t">${esc(x.device_name)} <span class="pill">${esc(x.client_kind || "device")}</span></div>
      <div class="d">Code <b style="font-family:var(--mono);letter-spacing:2px">${esc(x.code)}</b> · expires in ${Math.ceil(x.expires_in_seconds / 60)} min</div>
      <div class="acts"><button class="btn sm" type="button" data-action="pair-approve" data-id="${esc(x.pairing_id)}">Approve</button></div></div>`).join("")
      : empty("No devices waiting.");
    const b = $("#pairBadge");
    b.hidden = !p.count;
    b.textContent = p.count;
  } catch (e) {
    if (e.status === 403) $("#pendingCard").hidden = true; // not an owner
    else pend.innerHTML = failed(e);
  }
}

// --- models -------------------------------------------------------------------------------------

async function loadModels() {
  const out = $("#providersOut");
  if (!out.innerHTML) out.innerHTML = skeleton(3);
  try {
    const d = await get("/providers");
    out.innerHTML = d.providers.map((p) => {
      const badge = p.connected ? `<span class="pill ok">connected${p.credential_source === "env" ? " · from environment" : ""}</span>` : '<span class="pill">not connected</span>';
      const active = p.provider === d.active_provider ? '<span class="pill accent">active</span>' : "";
      const oauth = p.oauth_supported ? `<button class="ghost sm" type="button" data-action="provider-oauth" data-name="${esc(p.provider)}">Sign in with OAuth</button>` : "";
      const dis = p.connected ? `<button class="ghost sm danger" type="button" data-action="provider-disconnect" data-name="${esc(p.provider)}">Disconnect</button>` : "";
      return `<div class="item"><div class="t">${esc(p.label)} ${badge}${active}</div><div class="d">${esc(p.note)}</div>
        <div class="row" style="margin-top:10px"><div class="grow"><label class="sr-only" for="key-${esc(p.provider)}">API key for ${esc(p.label)}</label><input id="key-${esc(p.provider)}" placeholder="Paste API key" type="password" autocomplete="off" style="margin:0" /></div>
        <button class="btn sm" type="button" data-action="provider-connect" data-name="${esc(p.provider)}">Connect</button></div>
        ${oauth || dis ? `<div class="acts">${oauth}${dis}</div>` : ""}</div>`;
    }).join("");
  } catch (e) {
    out.innerHTML = failed(e);
  }
}

async function finishOAuthIfReturning() {
  const params = new URLSearchParams(location.search);
  const code = params.get("code");
  const st = params.get("state");
  const name = sessionStorage.getItem("shadow.oauth");
  if (!code || !st || !name) return;
  history.replaceState(null, "", `${location.pathname}#/models`);
  sessionStorage.removeItem("shadow.oauth");
  try {
    await post(`/providers/${encodeURIComponent(name)}/oauth/exchange`, { state: st, code });
    toast(`${name} connected.`);
  } catch (e) {
    toast(`Sign-in didn't finish: ${errText(e)}`, true);
  }
}

// --- audit ----------------------------------------------------------------------------------------

const STATUS_TONE = { blocked: "bad", denied: "bad", revoked: "bad", fallback_local: "warn", pending: "warn", answered: "ok", allowed: "ok", stored: "ok", approved: "ok", trusted: "ok", ok: "ok" };
let auditTimer;
$("#auditFilter").addEventListener("input", () => { clearTimeout(auditTimer); auditTimer = setTimeout(loadAudit, 300); });

async function loadAudit() {
  const out = $("#auditOut");
  if (!out.innerHTML) out.innerHTML = skeleton(5);
  const type = $("#auditFilter").value.trim();
  try {
    const r = await get(`/audit?limit=${state.auditLimit}${type ? `&event_type=${encodeURIComponent(type)}` : ""}`);
    const events = [...r.items].reverse();
    if (!type) {
      const types = [...new Set(events.map((e) => e.event_type))].sort();
      $("#auditTypes").innerHTML = types.map((t) => `<option value="${esc(t)}"></option>`).join("");
    }
    out.innerHTML = events.length ? events.map((e) => {
      const d = new Date(e.timestamp);
      const tone = STATUS_TONE[e.status] || "";
      return `<div class="audit-row"><time datetime="${esc(e.timestamp)}" title="${esc(d.toLocaleString())}">${esc(d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" }))}</time>
        <span class="ev">${esc(e.event_type)}</span><span class="d">${esc(e.proposed_action || e.result || "")}</span><span class="st pill ${tone}">${esc(e.status)}</span></div>`;
    }).join("") : empty(type ? "No events of that type." : "No events yet.");
    $("#auditMore").hidden = r.count <= events.length || state.auditLimit >= 1000;
  } catch (e) {
    out.innerHTML = failed(e);
  }
}

// --- boot --------------------------------------------------------------------------------------------

function enterApp() {
  $("#connect").hidden = true;
  $("#app").hidden = false;
  $("#signOutBtn").hidden = !state.authRequired;
  $("#insecureBanner").hidden = !state.cred || state.cred.kind !== "fallback";
  refreshStatus();
  refreshBadges();
  showView(false);
}

async function boot() {
  initOrbs();
  await refreshStatus();
  state.authRequired = state.health ? !!state.health.auth_required : true;
  $("#connectVer").textContent = state.health ? `node ${state.health.version}` : "node offline";
  if (state.authRequired) {
    state.cred = await loadCredential();
    if (!state.cred) return showConnect(state.health ? "" : "Can't reach the node. Is it running?");
  }
  await finishOAuthIfReturning();
  enterApp();
  setInterval(() => { if (!$("#app").hidden) { refreshStatus(); refreshBadges(); } }, 10000);
}

boot();
