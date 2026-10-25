# thinking-orbs (vendored)

Framework-free engine from [thinking-orbs](https://libraries.dev/orbs) 0.3.2
(MIT, © Jakub Antalik, https://github.com/Jakubantalik/Libraries.dev).

Only `dist/engine.es.js` and its shared chunk are vendored: the React
component is not used. The dashboard drives the engine from `web/orb.js`.
Files are served same-origin so the dashboard CSP stays `script-src 'self'`.

To update: `npm pack thinking-orbs@<version>`, copy `dist/engine.es.js` and the
`index-*.js` chunk it imports, and update the allowlist in
`shadow_node/main.py` (`DASHBOARD_VENDOR`).
