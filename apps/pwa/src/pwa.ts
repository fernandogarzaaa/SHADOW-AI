import { Platform } from 'react-native';

// Makes the web build an installable PWA: injects the manifest + theme color
// and registers a service worker for offline app-shell caching. No-op on native.
export function registerPWA(): void {
  if (Platform.OS !== 'web' || typeof document === 'undefined') return;

  if (!document.querySelector('link[rel="manifest"]')) {
    const link = document.createElement('link');
    link.rel = 'manifest';
    link.href = '/manifest.json';
    document.head.appendChild(link);
  }
  if (!document.querySelector('meta[name="theme-color"]')) {
    const meta = document.createElement('meta');
    meta.name = 'theme-color';
    meta.content = '#0b0c0e';
    document.head.appendChild(meta);
  }
  if (typeof navigator !== 'undefined' && 'serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js').catch(() => {});
    });
  }
}
