/**
 * Expo config plugin: SHADOW system integrations (Android).
 *
 * 1. Digital assistant: adds the ASSIST intent-filter to MainActivity so
 *    SHADOW appears in Settings > Apps > Default apps > Digital assistant.
 *    Long-press home then opens SHADOW instead of Gemini/Assistant.
 * 2. Share sheet: adds SEND intent-filters (text/plain, image/*, video/*)
 *    so other apps can share into SHADOW. The JS side
 *    (src/lib/shareReceive.ts) reads the shared content through
 *    react-native-receive-sharing-intent and files it as a chat message.
 *
 * Filters are added idempotently: repeated prebuilds never duplicate them.
 */

const { withAndroidManifest } = require("@expo/config-plugins");

const ASSIST_FILTER = {
	actions: ["android.intent.action.ASSIST"],
	categories: ["android.intent.category.DEFAULT"],
	data: [],
};

const SHARE_FILTERS = [
	{
		actions: ["android.intent.action.SEND"],
		categories: ["android.intent.category.DEFAULT"],
		data: [{ "android:mimeType": "text/plain" }],
	},
	{
		actions: ["android.intent.action.SEND"],
		categories: ["android.intent.category.DEFAULT"],
		data: [
			{ "android:mimeType": "image/*" },
			{ "android:mimeType": "video/*" },
		],
	},
];

function filterKey(filter) {
	const actions = (filter.actions || []).slice().sort().join(",");
	const data = (filter.data || [])
		.map((d) => d["android:mimeType"] || "")
		.sort()
		.join(",");
	return `${actions}|${data}`;
}

function toManifestFilter(filter) {
	const out = {};
	if (filter.actions && filter.actions.length) {
		out.action = filter.actions.map((name) => ({ $: { "android:name": name } }));
	}
	if (filter.categories && filter.categories.length) {
		out.category = filter.categories.map((name) => ({ $: { "android:name": name } }));
	}
	if (filter.data && filter.data.length) {
		out.data = filter.data.map((attrs) => ({ $: attrs }));
	}
	return out;
}

function manifestFilterKey(node) {
	const actions = ((node.action || []).map((a) => a.$["android:name"]) || [])
		.slice()
		.sort()
		.join(",");
	const data = ((node.data || []).map((d) => d.$["android:mimeType"] || "") || [])
		.slice()
		.sort()
		.join(",");
	return `${actions}|${data}`;
}

function ensureFilters(activity, filters) {
	activity["intent-filter"] = activity["intent-filter"] || [];
	const existing = new Set(activity["intent-filter"].map(manifestFilterKey));
	for (const filter of filters) {
		if (!existing.has(filterKey(filter))) {
			activity["intent-filter"].push(toManifestFilter(filter));
			existing.add(filterKey(filter));
		}
	}
}

function withSystemIntegrations(config) {
	return withAndroidManifest(config, (config) => {
		const application = config.modResults.manifest.application?.[0];
		if (!application) return config;
		const activities = application.activity || [];
		const mainActivity = activities.find(
			(a) => a.$ && a.$["android:name"] === ".MainActivity",
		);
		if (!mainActivity) return config;

		// Share intents arriving while the app is alive must land on the
		// existing activity (onNewIntent) instead of stacking a new one.
		mainActivity.$["android:launchMode"] = "singleTask";

		ensureFilters(mainActivity, [ASSIST_FILTER, ...SHARE_FILTERS]);
		return config;
	});
}

module.exports = withSystemIntegrations;
// Exported for unit tests.
module.exports.filterKey = filterKey;
module.exports.ensureFilters = ensureFilters;
module.exports.ASSIST_FILTER = ASSIST_FILTER;
module.exports.SHARE_FILTERS = SHARE_FILTERS;
