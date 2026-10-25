// Cross-language check: the dashboard signer must reproduce the Python
// signature-v2 vectors byte for byte. Run: node tests/js/sig_v2_vectors.test.mjs
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..", "..");
const { canonicalQuery, canonicalString, hmacSha256Hex, sha256, hex } = await import(
  join(root, "apps/shadow-node/shadow_node/web/signer.js")
);
const V = JSON.parse(readFileSync(join(here, "..", "fixtures", "sig_v2_vectors.json"), "utf8"));
const enc = new TextEncoder();
let n = 0;
for (const c of V.cases) {
  assert.equal(canonicalQuery(c.query), c.canonical_query, `${c.name}: canonical query`);
  const msg = canonicalString({
    method: c.method, path: c.path, query: c.query,
    bodySha256: hex(sha256(enc.encode(c.body))),
    nonce: V.nonce, timestamp: V.timestamp, deviceId: V.device_id,
  });
  assert.equal(hmacSha256Hex(V.secret, msg), c.signature, `${c.name}: signature`);
  n++;
}
console.log(`sig v2 vectors OK (${n} cases)`);
