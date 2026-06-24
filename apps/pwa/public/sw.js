// Minimal service worker: caches ONLY the static app shell.
// It must never cache Shadow Node API responses — when the PWA is served from
// the node's own origin those GETs (/audit, /memory/search, /providers, …) are
// same-origin and authenticated, and Cache storage would leak that state and
// keep serving it cache-first even after unpairing or after the node revokes.
const CACHE = 'shadow-pwa-v1';

// Node API surface — never cached, always network-only.
const API_PREFIXES = [
  '/health', '/ready', '/agent', '/memory', '/providers', '/approvals',
  '/audit', '/pair', '/emergency_pause', '/tools', '/consent',
];

// Static app-shell asset extensions that are safe to cache.
const STATIC_EXT = /\.(?:js|css|png|jpg|jpeg|gif|svg|ico|webp|woff2?|ttf|otf|json|map)$/i;

function isAppShell(url, request) {
  if (API_PREFIXES.some((p) => url.pathname === p || url.pathname.startsWith(p + '/'))) {
    return false; // explicitly an API path
  }
  // Navigation requests (the HTML document) and Expo's static bundle/assets.
  if (request.mode === 'navigate') return true;
  if (url.pathname.startsWith('/_expo/')) return true;
  if (url.pathname === '/' || url.pathname === '/index.html') return true;
  if (url.pathname === '/manifest.json' || url.pathname === '/favicon.ico') return true;
  return STATIC_EXT.test(url.pathname);
}

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return; // never touch API mutations
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return; // cross-origin: leave to the browser
  if (!isAppShell(url, request)) return;          // API / dynamic: never cached

  event.respondWith(
    caches.open(CACHE).then(async (cache) => {
      const cached = await cache.match(request);
      const network = fetch(request)
        .then((res) => {
          if (res && res.status === 200) cache.put(request, res.clone());
          return res;
        })
        .catch(() => cached);
      // Cache-first for the static app shell; fall back to network.
      return cached || network;
    })
  );
});
