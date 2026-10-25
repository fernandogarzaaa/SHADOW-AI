// Shadow node request signer for the browser dashboard (signature v2).
//
// Canonical string (must match agent_core.security._build_signed_message_v2):
//   "SHADOW-SIG-v2\nMETHOD\npath\ncanonical_query\nsha256hex(body)\nnonce\ntimestamp\ndevice_id"
// canonical_query: decoded pairs, RFC 3986 re-encoded, sorted by (key, value),
// joined with "&". Shared vectors: tests/fixtures/sig_v2_vectors.json.
//
// Key storage: in a secure context (https or localhost) the device secret is
// imported as a NON-EXTRACTABLE WebCrypto HMAC key and kept in IndexedDB, so
// page scripts can sign with it but never read it back. Plain-http LAN
// addresses have no crypto.subtle; there the secret falls back to
// localStorage with a pure-JS HMAC, and the UI warns about it.

const K = [
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];
const rotr = (x, n) => (x >>> n) | (x << (32 - n));
const enc = new TextEncoder();

export function sha256(data) {
  const h = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
  const len = ((data.length + 9 + 63) >> 6) << 6;
  const p = new Uint8Array(len);
  p.set(data);
  p[data.length] = 0x80;
  const v = new DataView(p.buffer);
  v.setUint32(len - 8, Math.floor((data.length * 8) / 0x100000000));
  v.setUint32(len - 4, (data.length * 8) >>> 0);
  const w = new Array(64);
  for (let o = 0; o < len; o += 64) {
    for (let i = 0; i < 16; i++) w[i] = v.getUint32(o + i * 4);
    for (let i = 16; i < 64; i++) {
      const s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >>> 3);
      const s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >>> 10);
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) | 0;
    }
    let [a, b, c, d, e, f, g, hh] = h;
    for (let i = 0; i < 64; i++) {
      const t1 = (hh + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + w[i]) | 0;
      const t2 = ((rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) | 0;
      hh = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
    }
    h[0] = (h[0] + a) | 0; h[1] = (h[1] + b) | 0; h[2] = (h[2] + c) | 0; h[3] = (h[3] + d) | 0;
    h[4] = (h[4] + e) | 0; h[5] = (h[5] + f) | 0; h[6] = (h[6] + g) | 0; h[7] = (h[7] + hh) | 0;
  }
  const out = new Uint8Array(32);
  const ov = new DataView(out.buffer);
  for (let i = 0; i < 8; i++) ov.setUint32(i * 4, h[i] >>> 0);
  return out;
}

export const hex = (bytes) => Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");

export function hmacSha256Hex(key, message) {
  let k = enc.encode(key);
  if (k.length > 64) k = sha256(k);
  const pk = new Uint8Array(64);
  pk.set(k);
  const ipad = pk.map((b) => b ^ 0x36);
  const opad = pk.map((b) => b ^ 0x5c);
  const m = enc.encode(message);
  const inner = new Uint8Array(64 + m.length);
  inner.set(ipad);
  inner.set(m, 64);
  const outer = new Uint8Array(96);
  outer.set(opad);
  outer.set(sha256(inner), 64);
  return hex(sha256(outer));
}

// RFC 3986 unreserved set, matching Python's quote(s, safe="-_.~").
const rfc3986 = (s) =>
  encodeURIComponent(s).replace(/[!'()*]/g, (c) => "%" + c.charCodeAt(0).toString(16).toUpperCase());

export function canonicalQuery(query) {
  const q = (query || "").replace(/^\?/, "");
  if (!q) return "";
  const pairs = [];
  for (const [k, v] of new URLSearchParams(q)) pairs.push([rfc3986(k), rfc3986(v)]);
  pairs.sort((x, y) => (x[0] < y[0] ? -1 : x[0] > y[0] ? 1 : x[1] < y[1] ? -1 : x[1] > y[1] ? 1 : 0));
  return pairs.map(([k, v]) => `${k}=${v}`).join("&");
}

export function canonicalString({ method, path, query, bodySha256, nonce, timestamp, deviceId }) {
  return ["SHADOW-SIG-v2", method.toUpperCase(), path, canonicalQuery(query), bodySha256, nonce, String(timestamp), deviceId].join("\n");
}

const subtle = globalThis.crypto && globalThis.crypto.subtle;
export const secureContext = !!subtle && globalThis.isSecureContext !== false;

async function bodyDigest(bytes) {
  if (subtle) return hex(new Uint8Array(await subtle.digest("SHA-256", bytes)));
  return hex(sha256(bytes));
}

function randomHex(n) {
  const b = new Uint8Array(n);
  globalThis.crypto.getRandomValues(b); // fail closed if no secure RNG
  return hex(b);
}

// --- credential storage --------------------------------------------------------

const DB = "shadow-dashboard";
const STORE = "credentials";
const LS_KEY = "shadow.credential";

function idb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function idbOp(mode, fn) {
  const db = await idb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, mode);
    const req = fn(tx.objectStore(STORE));
    tx.oncomplete = () => resolve(req && req.result);
    tx.onerror = () => reject(tx.error);
  });
}

/** Persist a freshly issued credential. Returns the in-memory credential. */
export async function saveCredential({ deviceId, secret, expiresAt, name }) {
  if (secureContext) {
    const key = await subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
    const cred = { deviceId, key, expiresAt, name, kind: "webcrypto" };
    await idbOp("readwrite", (s) => s.put(cred, "current"));
    return cred;
  }
  const cred = { deviceId, secret, expiresAt, name, kind: "fallback" };
  localStorage.setItem(LS_KEY, JSON.stringify(cred));
  return cred;
}

export async function loadCredential() {
  try {
    if (secureContext) {
      const cred = await idbOp("readonly", (s) => s.get("current"));
      if (cred) return cred;
    }
  } catch {
    /* IndexedDB unavailable (private mode): fall through */
  }
  try {
    const raw = localStorage.getItem(LS_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export async function clearCredential() {
  try {
    await idbOp("readwrite", (s) => s.delete("current"));
  } catch {
    /* ignore */
  }
  try {
    localStorage.removeItem(LS_KEY);
  } catch {
    /* ignore */
  }
}

export async function updateExpiry(cred, expiresAt) {
  if (!cred || cred.expiresAt === expiresAt) return;
  cred.expiresAt = expiresAt;
  try {
    if (cred.kind === "webcrypto") await idbOp("readwrite", (s) => s.put(cred, "current"));
    else localStorage.setItem(LS_KEY, JSON.stringify(cred));
  } catch {
    /* best effort */
  }
}

// --- signing ---------------------------------------------------------------------

async function hmacHex(cred, message) {
  if (cred.kind === "webcrypto") {
    return hex(new Uint8Array(await subtle.sign("HMAC", cred.key, enc.encode(message))));
  }
  return hmacSha256Hex(cred.secret, message);
}

/** The x-shadow-* headers for one request. `body` is the exact string sent. */
export async function authHeaders(cred, method, url, body = "") {
  const u = new URL(url, location.origin);
  const nonce = randomHex(16);
  const timestamp = Math.floor(Date.now() / 1000);
  const bodySha256 = await bodyDigest(enc.encode(body || ""));
  const msg = canonicalString({ method, path: u.pathname, query: u.search, bodySha256, nonce, timestamp, deviceId: cred.deviceId });
  return {
    "x-shadow-device-id": cred.deviceId,
    "x-shadow-signature-version": "2",
    "x-shadow-nonce": nonce,
    "x-shadow-timestamp": String(timestamp),
    "x-shadow-signature": await hmacHex(cred, msg),
  };
}

/** Random 32-byte identity proposed at pairing (the node fingerprints it). */
export const newPublicKey = () => randomHex(32);
