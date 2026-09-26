#!/bin/bash
# Provider unit tests: compile the pure provider modules + tests with tsc,
# then run them with node --test. No npm test dependencies required.
set -euo pipefail
cd "$(dirname "$0")/.."
# NOTE: /tmp is a small tmpfs in this environment; keep build output in the
# workspace (gitignored) instead.
OUT_DIR="$PWD/.test-out"
APP_DIR="$PWD"
rm -rf "$OUT_DIR"
npx tsc -p tsconfig.test.json --outDir "$OUT_DIR"
# Point at the test file explicitly: `node --test <dir>` misresolves on
# some node builds, while the file path always works.
node --test "$OUT_DIR/providers/__tests__/providers.test.js" "$OUT_DIR/providers/__tests__/openrouter.test.js" "$OUT_DIR/providers/__tests__/opencode.test.js" "$OUT_DIR/providers/__tests__/openaiCompatible.test.js" "$OUT_DIR/providers/__tests__/cohere.test.js" "$OUT_DIR/providers/__tests__/custom.test.js" "$OUT_DIR/providers/__tests__/modelCatalog.test.js" "$OUT_DIR/lib/__tests__/approvalNotificationRouting.test.js" "$OUT_DIR/lib/__tests__/localTriage.test.js" "$OUT_DIR/lib/__tests__/intentRouting.test.js" "$OUT_DIR/lib/__tests__/shareFormat.test.js" "$APP_DIR/plugins/__tests__/withSystemIntegrations.test.js"
