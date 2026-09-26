/**
 * OpenRouter adapter unit tests: SSE streaming, live model catalog
 * mapping, and key validation, with the HTTP layer mocked.
 *
 * Run: `npm run test:providers`
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
	fetchOpenRouterModels,
	openrouterProvider,
	runOpenRouterStream,
	toModelInfo,
} from "../openrouter";
import { anthropicProvider } from "../anthropic";
import { clearModelCache, getModels } from "../modelCatalog";
import { ProviderError } from "../errors";
import type {
	FetchLike,
	StreamEvent,
	StreamRequest,
	StreamTransport,
} from "../types";

function mockTransport(fullBody: string, splits: number[], status = 200): StreamTransport {
	return {
		postStream: async (_url, init) => {
			let seen = "";
			let cursor = 0;
			for (const size of splits) {
				cursor = Math.min(fullBody.length, cursor + size);
				seen = fullBody.slice(0, cursor);
				init.onChunk(seen);
			}
			if (cursor < fullBody.length) {
				init.onChunk(fullBody);
			}
			return { status, finalText: fullBody };
		},
	};
}

function collectEvents() {
	const events: StreamEvent[] = [];
	return {
		events,
		request: (extra: Partial<StreamRequest> = {}): StreamRequest => ({
			apiKey: "sk-or-test",
			model: "openrouter/auto",
			messages: [{ role: "user", content: "hi" }],
			onEvent: (e) => events.push(e),
			...extra,
		}),
	};
}

function mockFetch(
	ok: boolean,
	status: number,
	body: unknown = "",
	impl?: () => Promise<never>,
): FetchLike {
	return async () => {
		if (impl) await impl();
		return {
			ok,
			status,
			text: async () => (typeof body === "string" ? body : JSON.stringify(body)),
			json: async () => (typeof body === "string" ? {} : body),
		};
	};
}

describe("openrouter stream", () => {
	const sseBody =
		`data: {"id":"c1","choices":[{"delta":{"content":"Hel"},"finish_reason":null}]}\n\n` +
		`data: {"id":"c1","choices":[{"delta":{"content":"lo"},"finish_reason":null}]}\n\n` +
		`data: {"id":"c1","choices":[{"delta":{},"finish_reason":"stop"}]}\n\n` +
		`data: [DONE]\n\n`;

	it("openrouter: streams deltas; done markers are swallowed", async () => {
		const { events, request } = collectEvents();
		// Server-side termination ([DONE] / finish_reason) is swallowed by
		// the adapter; stream completion is the resolved promise.
		await runOpenRouterStream(request(), 64, mockTransport(sseBody, [40, 40]));
		assert.deepEqual(events, [
			{ type: "delta", text: "Hel" },
			{ type: "delta", text: "lo" },
		]);
	});

	it("openrouter: sends OpenRouter headers", async () => {
		let seenHeaders: Record<string, string> = {};
		let seenUrl = "";
		const transport: StreamTransport = {
			postStream: async (url, init) => {
				seenUrl = url;
				seenHeaders = init.headers;
				return { status: 200, finalText: "data: [DONE]\n\n" };
			},
		};
		const { request } = collectEvents();
		await runOpenRouterStream(request(), 64, transport);
		assert.equal(seenUrl, "https://openrouter.ai/api/v1/chat/completions");
		assert.equal(seenHeaders["authorization"], "Bearer sk-or-test");
		assert.ok(seenHeaders["HTTP-Referer"]);
		assert.equal(seenHeaders["X-Title"], "SHADOW");
	});

	it("openrouter: maps 401 to invalid_key", async () => {
		const { request } = collectEvents();
		await assert.rejects(
			runOpenRouterStream(request(), 64, mockTransport("nope", [4], 401)),
			(err: unknown) => {
				assert.ok(err instanceof ProviderError);
				assert.equal((err as ProviderError).code, "invalid_key");
				return true;
			},
		);
	});
});

describe("openrouter model catalog", () => {
	it("toModelInfo: maps id, name, context, and capabilities", () => {
		assert.deepEqual(
			toModelInfo({
				id: "anthropic/claude-sonnet-5",
				name: "Anthropic: Claude Sonnet 5",
				context_length: 200000,
				architecture: { input_modalities: ["text", "image"] },
			}),
			{
				id: "anthropic/claude-sonnet-5",
				label: "Anthropic: Claude Sonnet 5",
				blurb: "200k context",
				capabilities: {
					protocol: "chat-completions",
					source: "live",
					contextWindow: 200000,
					vision: true,
				},
			},
		);
	});

	it("toModelInfo: drops null ids and non-text models", () => {
		assert.equal(toModelInfo({ name: "No id" }), null);
		assert.equal(
			toModelInfo({
				id: "img/gen-1",
				architecture: { output_modalities: ["image"] },
			}),
			null,
		);
	});

	it("fetchOpenRouterModels: parses the public catalog", async () => {
		const models = await fetchOpenRouterModels(
			mockFetch(true, 200, {
				data: [
					{ id: "openrouter/auto", name: "Auto", context_length: 100000 },
					{ id: "img/gen-1", name: "Gen", architecture: { output_modalities: ["image"] } },
				],
			}),
		);
		assert.equal(models.length, 1);
		assert.equal(models[0].id, "openrouter/auto");
		assert.equal(models[0].blurb, "100k context");
	});

	it("fetchOpenRouterModels: throws when the catalog is empty", async () => {
		await assert.rejects(
			fetchOpenRouterModels(mockFetch(true, 200, { data: [] })),
			(err: unknown) => err instanceof ProviderError,
		);
	});

	it("fetchOpenRouterModels: maps network errors", async () => {
		await assert.rejects(
			fetchOpenRouterModels(
				mockFetch(true, 200, {}, async () => {
					throw new Error("boom");
				}),
			),
			(err: unknown) => err instanceof ProviderError,
		);
	});
});

describe("openrouter key validation", () => {
	it("openrouter: validates against the official /key endpoint", async () => {
		let seenUrl = "";
		const fetch: FetchLike = async (input) => {
			seenUrl = input;
			return {
				ok: true,
				status: 200,
				text: async () => "{}",
				json: async () => ({}),
			};
		};
		await openrouterProvider.validateKey("sk-or-x", fetch);
		assert.equal(seenUrl, "https://openrouter.ai/api/v1/key");
	});

	it("openrouter: resolves on 200", async () => {
		await openrouterProvider.validateKey("sk-or-x", mockFetch(true, 200, { data: {} }));
	});

	it("openrouter: rejects invalid keys", async () => {
		await assert.rejects(
			openrouterProvider.validateKey("bad", mockFetch(false, 401, "Unauthorized")),
			(err: unknown) => {
				assert.ok(err instanceof ProviderError);
				assert.equal((err as ProviderError).code, "invalid_key");
				return true;
			},
		);
	});
});

describe("modelCatalog", () => {
	it("getModels: returns the static list for static providers", async () => {
		const { models, live } = await getModels(anthropicProvider, "sk-x");
		assert.equal(live, false);
		assert.ok(models.length > 0);
		assert.equal(models[0].id, "claude-sonnet-5");
	});

	it("getModels: falls back to static on catalog failure", async () => {
		clearModelCache("openrouter");
		const { models, live } = await getModels(
			openrouterProvider,
			"sk-or-x",
			mockFetch(false, 500, "oops"),
		);
		assert.equal(live, false);
		assert.ok(models.some((m) => m.id === "openrouter/auto"));
	});

	it("getModels: caches a live catalog", async () => {
		clearModelCache("openrouter");
		const first = await getModels(
			openrouterProvider,
			"sk-or-x",
			mockFetch(true, 200, { data: [{ id: "m/1", name: "M1" }] }),
		);
		assert.equal(first.live, true);
		assert.equal(first.models[0].id, "m/1");
		// Second call with a failing fetch still serves the cache.
		const second = await getModels(
			openrouterProvider,
			"sk-or-x",
			mockFetch(false, 500, "oops"),
		);
		assert.equal(second.live, true);
		assert.equal(second.models[0].id, "m/1");
		clearModelCache("openrouter");
	});
});
