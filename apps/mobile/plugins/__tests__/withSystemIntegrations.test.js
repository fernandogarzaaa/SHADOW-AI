/**
 * Unit tests for the withSystemIntegrations Expo config plugin.
 *
 * Tests the pure filter helpers (idempotent manifest edits) without
 * running a full prebuild. Run with plain node: `node --test`.
 */

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const {
	ensureFilters,
	filterKey,
	ASSIST_FILTER,
	SHARE_FILTERS,
} = require("../withSystemIntegrations");

function mainActivity() {
	return { $: { "android:name": ".MainActivity" } };
}

describe("withSystemIntegrations", () => {
	it("adds the assist filter to MainActivity", () => {
		const activity = mainActivity();
		ensureFilters(activity, [ASSIST_FILTER]);
		const filters = activity["intent-filter"];
		assert.equal(filters.length, 1);
		assert.ok(
			filters[0].action.some((a) => a.$["android:name"] === "android.intent.action.ASSIST"),
		);
	});

	it("adds share filters for text and media", () => {
		const activity = mainActivity();
		ensureFilters(activity, SHARE_FILTERS);
		const keys = activity["intent-filter"].map((f) =>
			(f.data || []).map((d) => d.$["android:mimeType"]).sort().join(","),
		);
		assert.ok(keys.some((k) => k === "text/plain"));
		assert.ok(keys.some((k) => k.includes("image/*") && k.includes("video/*")));
	});

	it("is idempotent across repeated prebuilds", () => {
		const activity = mainActivity();
		const all = [ASSIST_FILTER, ...SHARE_FILTERS];
		ensureFilters(activity, all);
		ensureFilters(activity, all);
		assert.equal(activity["intent-filter"].length, 3);
	});

	it("preserves pre-existing intent filters", () => {
		const activity = mainActivity();
		activity["intent-filter"] = [
			{
				action: [{ $: { "android:name": "android.intent.action.MAIN" } }],
				category: [{ $: { "android:name": "android.intent.category.LAUNCHER" } }],
			},
		];
		ensureFilters(activity, [ASSIST_FILTER]);
		assert.equal(activity["intent-filter"].length, 2);
	});

	it("filterKey is order-insensitive", () => {
		const a = { actions: ["x", "y"], data: [{ "android:mimeType": "b" }, { "android:mimeType": "a" }] };
		const b = { actions: ["y", "x"], data: [{ "android:mimeType": "a" }, { "android:mimeType": "b" }] };
		assert.equal(filterKey(a), filterKey(b));
	});
});
