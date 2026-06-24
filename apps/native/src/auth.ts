// Device pairing + HMAC request signing — matches the Shadow Node's
// DeviceSessionStore.verify (HMAC-SHA256 over method\npath\nbody\nnonce\ntimestamp).
// Pure module (no React Native deps) so it runs in the app AND the simulation.
import { sha256 } from 'js-sha256';

export interface DeviceCreds {
  deviceId: string;
  secret: string;
}

function randHex(bytes = 16): string {
  let s = '';
  for (let i = 0; i < bytes; i++) s += Math.floor(Math.random() * 256).toString(16).padStart(2, '0');
  return s;
}

/** Pair with a node: POST /pair/start then /pair/confirm. Both are auth-exempt. */
export async function pair(baseUrl: string, deviceName = 'Shadow Client'): Promise<DeviceCreds> {
  const start = await fetch(baseUrl + '/pair/start', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
  }).then((r) => r.json());
  const publicKey = 'shadow-' + randHex(16);
  const confirm = await fetch(baseUrl + '/pair/confirm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pairing_id: start.pairing_id, device_name: deviceName, public_key: publicKey }),
  }).then((r) => r.json());
  if (!confirm?.device?.id || !confirm?.shared_secret) {
    throw new Error('pairing failed: ' + JSON.stringify(confirm));
  }
  return { deviceId: confirm.device.id, secret: confirm.shared_secret };
}

/** Build the signed-request headers for a single call. `path` must exclude the query string. */
export function signHeaders(creds: DeviceCreds, method: string, path: string, body: string): Record<string, string> {
  const ts = Math.floor(Date.now() / 1000).toString();
  const nonce = randHex(16);
  const msg = [method.toUpperCase(), path, body || '', nonce, ts].join('\n');
  const signature = (sha256 as any).hmac(creds.secret, msg);
  return {
    'x-shadow-device-id': creds.deviceId,
    'x-shadow-signature': signature,
    'x-shadow-nonce': nonce,
    'x-shadow-timestamp': ts,
  };
}
