/**
 * Unit tests for the dynamic model catalog: static fallback tagging and
 * stale-cache eviction on failed refreshes.
 *
 * Run: `npm run test:providers`
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { clearModelCache, getModels, __testAgeCacheEntry } from "../modelCatalog";
import type { FetchLike, ModelInfo, ModelProvider } from "../types";

function fakeProvider(overrides: Partial<ModelProvider>): ModelProvider {
	const base: ModelProvider = {
		id: "openrouter",
		label: "Test",
		models: [{ id: "static-a", label: "Static A", blurb: "fallback" }],
		defaultModel: "static-a",
		validateKey: async () => {},
		streamChat: async () => {},
	};
	return { ...base, ...overrides };
}

describe("model catalog fallback tagging", () => {
	it("tags static fallback entries as static", async () => {
		clearModelCache("openrouter");
		const provider = fakeProvider({
			listModels: async () => {
				throw new Error("offline");
			},
		});
		const fetch: FetchLike = async () => {
			throw new Error("unreachable");
		};
		const result = await getModels(provider, "key", fetch);
		assert.equal(result.live, false);
		assert.equal(result.models.length, 1);
		assert.equal(result.models[0].capabilities?.source, "static");
	});

	it("keeps an existing source tag instead of overwriting it", async () => {
		clearModelCache("openrouter");
		const live: ModelInfo[] = [
			{
				id: "live-a",
				label: "Live A",
				blurb: "",
				capabilities: { protocol: "chat-completions", source: "live" },
			},
		];
		const provider = fakeProvider({
			listModels: async () => {
				throw new Error("offline");
			},
			models: live,
		});
		const result = await getModels(provider, "key");
		assert.equal(result.models[0].capabilities?.source, "live");
		assert.equal(result.models[0].capabilities?.protocol, "chat-completions");
	});

	it("serves a fresh cache even when a refresh would fail", async () => {
		clearModelCache("openrouter");
		const live: ModelInfo[] = [
			{ id: "live-a", label: "Live A", blurb: "", capabilities: { source: "live" } },
		];
		const provider = fakeProvider({
			listModels: async () => live,
		});
		const first = await getModels(provider, "key");
		assert.equal(first.live, true);
		assert.equal(first.models[0].id, "live-a");

		// A failed refresh with a fresh cache keeps serving the cache.
		const failing = fakeProvider({
			listModels: async () => {
				throw new Error("offline");
			},
		});
		const second = await getModels(failing, "key");
		assert.equal(second.live, true);
		assert.equal(second.models[0].id, "live-a");
	});

	it("evicts a stale cache entry when a refresh fails", async () => {
		clearModelCache("openrouter");
		const live: ModelInfo[] = [
			{ id: "live-a", label: "Live A", blurb: "", capabilities: { source: "live" } },
		];
		const provider = fakeProvider({
			listModels: async () => live,
		});
		const first = await getModels(provider, "key");
		assert.equal(first.live, true);

		// Age the entry past the 24h TTL, then fail the refresh: the stale
		// entry must be dropped and reported as a static fallback.
		__testAgeCacheEntry("openrouter", 25 * 60 * 60 * 1000);
		const failing = fakeProvider({
			listModels: async () => {
				throw new Error("offline");
			},
		});
		const second = await getModels(failing, "key");
		assert.equal(second.live, false);
		assert.equal(second.models[0].id, "static-a");
		assert.equal(second.models[0].capabilities?.source, "static");
	});
});
