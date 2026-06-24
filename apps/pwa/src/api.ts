// Shadow Node API client. Works against the FastAPI node (default localhost:8787).
import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { pair as pairNode, signHeaders, DeviceCreds } from './auth';

const KEY = 'shadow.baseUrl';
const CREDS_KEY = 'shadow.creds';

function defaultBase(): string {
  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    // If the PWA is served by the node itself, same-origin; else localhost.
    const o = window.location.origin;
    return o.startsWith('http') && !o.includes('localhost:19') ? o : 'http://localhost:8787';
  }
  return 'http://localhost:8787';
}

let baseUrl = defaultBase();
let creds: DeviceCreds | null = null;

export async function loadBaseUrl(): Promise<string> {
  try {
    const v = await AsyncStorage.getItem(KEY);
    if (v) baseUrl = v;
    const c = await AsyncStorage.getItem(CREDS_KEY);
    if (c) creds = JSON.parse(c);
  } catch {}
  return baseUrl;
}

export async function setBaseUrl(url: string): Promise<void> {
  baseUrl = url.replace(/\/$/, '');
  try { await AsyncStorage.setItem(KEY, baseUrl); } catch {}
}

export function getBaseUrl(): string { return baseUrl; }
export function isPaired(): boolean { return creds !== null; }

/** Pair with the current node and persist the device credentials. */
export async function pairDevice(deviceName = 'Shadow PWA'): Promise<void> {
  creds = await pairNode(baseUrl, deviceName);
  try { await AsyncStorage.setItem(CREDS_KEY, JSON.stringify(creds)); } catch {}
}

export async function unpair(): Promise<void> {
  creds = null;
  try { await AsyncStorage.removeItem(CREDS_KEY); } catch {}
}

async function req(path: string, opts: RequestInit = {}): Promise<any> {
  const method = (opts.method || 'GET').toUpperCase();
  const body = typeof opts.body === 'string' ? opts.body : '';
  // Sign with the node's HMAC scheme when paired (required if the node enforces auth).
  const signed = creds ? signHeaders(creds, method, path.split('?')[0], body) : {};
  const res = await fetch(baseUrl + path, {
    ...opts,
    headers: { 'Content-Type': 'application/json', ...signed, ...(opts.headers || {}) },
  });
  const text = await res.text();
  let json: any = {};
  try { json = text ? JSON.parse(text) : {}; } catch { json = { raw: text }; }
  if (!res.ok) throw new Error(json?.error?.message || json?.detail || `HTTP ${res.status}`);
  return json;
}

export const api = {
  health: () => req('/health'),
  ready: () => req('/ready'),
  ask: (prompt: string, allow_cloud = false) =>
    req('/agent/ask', { method: 'POST', body: JSON.stringify({ prompt, allow_cloud, cloud_approval: allow_cloud }) }),
  ingest: (text: string, source_title = 'Mobile Import') =>
    req('/memory/ingest', { method: 'POST', body: JSON.stringify({ text, source_title }) }),
  search: (q: string) => req('/memory/search?q=' + encodeURIComponent(q)),
  execute: (tool_name: string, params: Record<string, any>) =>
    req('/agent/execute', {
      method: 'POST',
      body: JSON.stringify({ action: { tool_name, description: 'PWA action: ' + tool_name, params, requires_approval: true }, approved: true, double_confirmed: true }),
    }),
  tools: () => req('/tools'),
  providers: () => req('/providers'),
  connectProvider: (name: string, api_key: string) =>
    req(`/providers/${name}/connect`, { method: 'POST', body: JSON.stringify({ api_key }) }),
  disconnectProvider: (name: string) => req(`/providers/${name}`, { method: 'DELETE' }),
  approvals: () => req('/approvals'),
  decide: (id: string, ok: boolean) =>
    req(`/approvals/${id}/${ok ? 'approve' : 'deny'}`, { method: 'POST', body: JSON.stringify({ reason: 'from PWA' }) }),
  audit: () => req('/audit'),
  emergencyPause: (paused: boolean) =>
    req('/emergency_pause', { method: 'POST', body: JSON.stringify({ paused, reason: 'toggled from PWA' }) }),
};
