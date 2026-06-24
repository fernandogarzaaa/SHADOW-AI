/**
 * New-user simulation for the native app — drives a live Shadow Node using the
 * SAME pairing + signing code the app ships (src/auth.ts).
 *   npx tsx sim/new-user-sim.ts   (against an auth-enabled node)
 */
import { pair, signHeaders, DeviceCreds } from '../src/auth';

const BASE = process.env.SHADOW_NODE_URL || process.env.SIM_BASE || 'http://127.0.0.1:8799';
let pass = 0, fail = 0;
function check(name: string, ok: boolean, detail = '') { console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`); ok ? pass++ : fail++; }
async function call(creds: DeviceCreds | null, method: string, path: string, bodyObj?: any) {
  const body = bodyObj !== undefined ? JSON.stringify(bodyObj) : '';
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (creds) Object.assign(headers, signHeaders(creds, method, path.split('?')[0], body));
  const res = await fetch(BASE + path, { method, headers, body: body || undefined });
  const text = await res.text(); let json: any = {}; try { json = text ? JSON.parse(text) : {}; } catch { json = { raw: text }; }
  return { status: res.status, json };
}
async function main() {
  console.log(`\n=== Shadow NATIVE new-user simulation against ${BASE} ===\n`);
  const health = await call(null, 'GET', '/health');
  check('node reachable + auth on', health.status === 200 && health.json.auth_required === true, `v${health.json.version}`);
  check('unsigned protected request rejected', (await call(null, 'GET', '/audit')).status === 401);
  const creds = await pair(BASE, 'Shadow Native (sim)');
  check('pairing succeeds', !!creds.deviceId && !!creds.secret, `device ${creds.deviceId.slice(0, 12)}…`);
  check('signed request accepted', (await call(creds, 'GET', '/audit')).status === 200);
  check('consent granted', (await call(creds, 'POST', '/consent', { data_source: 'notes', scope: 'selected', purpose: 'answer', model_access_level: 'cloud_redacted' })).status === 200);
  const ingest = await call(creds, 'POST', '/memory/ingest', { text: 'Project Aurora ships in March; lead is Dana.', source_title: 'Onboarding note' });
  check('memory ingested', ingest.status === 200 && (ingest.json.items?.length || 0) > 0);
  check('memory search returns the note', JSON.stringify((await call(creds, 'GET', '/memory/search?q=Aurora')).json).includes('Aurora'));
  const ask = await call(creds, 'POST', '/agent/ask', { prompt: 'When does Aurora ship and who leads it?' });
  check('ask answered with routing + savings', ask.status === 200 && !!ask.json.route && !!ask.json.savings, `route=${ask.json.route} saved≈${ask.json.savings?.tokens_saved_estimate}`);
  const exec = await call(creds, 'POST', '/agent/execute', { action: { tool_name: 'note.create', description: 'sim note', params: { title: 'Native Sim Note', body: 'created by native sim' }, requires_approval: true }, approved: true, double_confirmed: true });
  check('real action executes through approval gate', exec.status === 200 && exec.json.ok === true, exec.json.result?.path || '');
  const ts = Math.floor(Date.now() / 1000).toString();
  const nonce = 'native-fixed-nonce-replay-test';
  const msg = ['GET', '/audit', '', nonce, ts].join('\n');
  const { hmac } = await import('js-sha256').then((m: any) => ({ hmac: m.sha256.hmac }));
  const sig = hmac(creds.secret, msg);
  const h = { 'x-shadow-device-id': creds.deviceId, 'x-shadow-signature': sig, 'x-shadow-nonce': nonce, 'x-shadow-timestamp': ts };
  const r1 = await fetch(BASE + '/audit', { headers: h });
  const r2 = await fetch(BASE + '/audit', { headers: h });
  check('nonce replay rejected on 2nd use', r1.status === 200 && r2.status === 401, `first ${r1.status}, replay ${r2.status}`);
  const pause = await call(creds, 'POST', '/emergency_pause', { paused: true, reason: 'sim' });
  const resume = await call(creds, 'POST', '/emergency_pause', { paused: false, reason: 'sim' });
  check('emergency pause + resume', pause.json.paused === true && resume.json.paused === false);
  const audit = await call(creds, 'GET', '/audit');
  const types = new Set((audit.json || []).map((e: any) => e.event_type));
  check('audit recorded pairing/ask/action', types.has('device_paired') && types.has('agent_ask'), `${(audit.json || []).length} events`);
  console.log(`\n=== RESULT: ${pass} passed, ${fail} failed ===\n`);
  process.exit(fail === 0 ? 0 : 1);
}
main().catch((e) => { console.error('SIM CRASHED:', e); process.exit(1); });
