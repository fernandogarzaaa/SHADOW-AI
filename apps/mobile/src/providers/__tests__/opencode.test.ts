/**
 * OpenCode Zen adapter unit tests: SSE streaming, live model catalog
 * mapping, key validation (including the tier-gated 403 case), with the
 * HTTP layer mocked.
 *
 * Run: `npm run test:providers`
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
	fetchZenModels,
	opencodeProvider,
	prettifyZenId,
	runZenStream,
	toModelInfo,
} from "../opencode";
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
			let cursor = 0;
			for (const size of splits) {
				cursor = Math.min(fullBody.length, cursor + size);
				init.onChunk(fullBody.slice(0, cursor));
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
			apiKey: "zen-test-key",
			model: "claude-sonnet-5",
			messages: [{ role: "user", content: "hi" }],
			onEvent: (e) => events.push(e),
			...extra,
		}),
	};
}

interface MockResponse {
	ok: boolean;
	status: number;
	body?: unknown;
}

function mockFetchSequence(responses: MockResponse[]): FetchLike {
	let i = 0;
	return async () => {
		const r = responses[Math.min(i++, responses.length - 1)];
		return {
			ok: r.ok,
			status: r.status,
			text: async () =>
				typeof r.body === "string" ? r.body : JSON.stringify(r.body ?? {}),
			json: async () => (typeof r.body === "string" ? {} : (r.body ?? {})),
		};
	};
}

describe("zen model catalog", () => {
	it("prettifyZenId: title-cases segments", () => {
		assert.equal(prettifyZenId("claude-sonnet-5"), "Claude Sonnet 5");
		assert.equal(prettifyZenId("gemini-3.6-flash"), "Gemini 3.6 Flash");
	});

	it("toModelInfo: maps id with a Zen blurb and live source", () => {
		assert.deepEqual(toModelInfo({ id: "claude-opus-5" }), {
			id: "claude-opus-5",
			label: "Claude Opus 5",
			blurb: "via OpenCode Zen",
			capabilities: { source: "live" },
		});
	});

	it("toModelInfo: drops null ids", () => {
		assert.equal(toModelInfo({}), null);
	});

	it("fetchZenModels: parses the public list", async () => {
		const models = await fetchZenModels(
			mockFetchSequence([
				{
					ok: true,
					status: 200,
					body: {
						object: "list",
						data: [{ id: "claude-sonnet-5" }, { id: "gemini-3.6-flash" }, {}],
					},
				},
			]),
		);
		assert.equal(models.length, 2);
		assert.equal(models[0].label, "Claude Sonnet 5");
	});

	it("fetchZenModels: throws when the catalog is empty", async () => {
		await assert.rejects(
			fetchZenModels(mockFetchSequence([{ ok: true, status: 200, body: { data: [] } }])),
			(err: unknown) => err instanceof ProviderError,
		);
	});
});

describe("zen stream", () => {
	const sseBody =
		`data: {"id":"z1","choices":[{"delta":{"content":"Hel"},"finish_reason":null}]}\n\n` +
		`data: {"id":"z1","choices":[{"delta":{"content":"lo"},"finish_reason":null}]}\n\n` +
		`data: {"id":"z1","choices":[{"delta":{},"finish_reason":"stop"}]}\n\n` +
		`data: [DONE]\n\n`;

	it("zen: streams deltas; done markers are swallowed", async () => {
		const { events, request } = collectEvents();
		await runZenStream(request(), 64, mockTransport(sseBody, [40, 40]));
		assert.deepEqual(events, [
			{ type: "delta", text: "Hel" },
			{ type: "delta", text: "lo" },
		]);
	});

	it("zen: posts to the Zen chat endpoint with Bearer auth", async () => {
		let seenUrl = "";
		let seenHeaders: Record<string, string> = {};
		const transport: StreamTransport = {
			postStream: async (url, init) => {
				seenUrl = url;
				seenHeaders = init.headers;
				return { status: 200, finalText: "data: [DONE]\n\n" };
			},
		};
		const { request } = collectEvents();
		await runZenStream(request(), 64, transport);
		assert.equal(seenUrl, "https://opencode.ai/zen/v1/chat/completions");
		assert.equal(seenHeaders["authorization"], "Bearer zen-test-key");
	});

	it("zen: maps 401 to invalid_key", async () => {
		const { request } = collectEvents();
		const zenAuthError = JSON.stringify({
			type: "error",
			error: { type: "AuthError", message: "Invalid API key." },
		});
		await assert.rejects(
			runZenStream(request(), 64, mockTransport(zenAuthError, [50], 401)),
			(err: unknown) => {
				assert.ok(err instanceof ProviderError);
				assert.equal((err as ProviderError).code, "invalid_key");
				return true;
			},
		);
	});

	it("zen: maps a tier-gated 403 to forbidden, not invalid_key", async () => {
		const { request } = collectEvents();
		const freeTierError = JSON.stringify({
			type: "error",
			error: { type: "FreeTierError", message: "Free tier gated." },
		});
		await assert.rejects(
			runZenStream(request(), 64, mockTransport(freeTierError, [50], 403)),
			(err: unknown) => {
				assert.ok(err instanceof ProviderError);
				assert.equal((err as ProviderError).code, "forbidden");
				return true;
			},
		);
	});
});

describe("zen key validation", () => {
	const catalog = {
		ok: true,
		status: 200,
		body: { object: "list", data: [{ id: "claude-sonnet-5" }] },
	};

	it("zen: resolves when Zen accepts the probe call", async () => {
		await opencodeProvider.validateKey(
			"zen-good",
			mockFetchSequence([catalog, { ok: true, status: 200, body: { id: "z1" } }]),
		);
	});

	it("zen: rejects on 401", async () => {
		await assert.rejects(
			opencodeProvider.validateKey(
				"zen-bad",
				mockFetchSequence([
					catalog,
					{
						ok: false,
						status: 401,
						body: { type: "error", error: { type: "AuthError", message: "Invalid API key." } },
					},
				]),
			),
			(err: unknown) => {
				assert.ok(err instanceof ProviderError);
				assert.equal((err as ProviderError).code, "invalid_key");
				return true;
			},
		);
	});

	it("zen: treats a tier-gated 403 as a valid key", async () => {
		await opencodeProvider.validateKey(
			"zen-gated",
			mockFetchSequence([
				catalog,
				{
					ok: false,
					status: 403,
					body: { type: "error", error: { type: "FreeTierError", message: "gated" } },
				},
			]),
		);
	});

	it("zen: probes with the static id when the catalog is unreachable", async () => {
		let seenBodies: string[] = [];
		const fetch: FetchLike = async (input, init) => {
			if (input.endsWith("/models")) {
				throw new Error("offline");
			}
			seenBodies.push(init?.body ?? "");
			return { ok: true, status: 200, text: async () => "{}", json: async () => ({}) };
		};
		await opencodeProvider.validateKey("zen-good", fetch);
		assert.ok(seenBodies[0].includes('"model":"claude-sonnet-5"'));
	});

	it("zen: probe skips catalog models that may need a non-chat dialect", async () => {
		let seenBodies: string[] = [];
		const fetch: FetchLike = async (input, init) => {
			if (input.endsWith("/models")) {
				return {
					ok: true,
					status: 200,
					text: async () => "{}",
					json: async () => ({
						object: "list",
						data: [{ id: "some-responses-only-model" }, { id: "gemini-3.6-flash" }],
					}),
				};
			}
			seenBodies.push(init?.body ?? "");
			return { ok: true, status: 200, text: async () => "{}", json: async () => ({}) };
		};
		await opencodeProvider.validateKey("zen-good", fetch);
		// gemini-3.6-flash is chat-safe; the unknown first entry is skipped.
		assert.ok(seenBodies[0].includes('"model":"gemini-3.6-flash"'));
	});

	it("zen: treats 429 as a valid key (rate-limited means accepted)", async () => {
		await opencodeProvider.validateKey(
			"zen-good",
			mockFetchSequence([catalog, { ok: false, status: 429, body: {} }]),
		);
	});

	it("zen: rejects a non-tier 403 as a rejected key", async () => {
		await assert.rejects(
			opencodeProvider.validateKey(
				"zen-bad",
				mockFetchSequence([
					catalog,
					{
						ok: false,
						status: 403,
						body: { type: "error", error: { type: "OtherError", message: "no" } },
					},
				]),
			),
			(err: unknown) => {
				assert.ok(err instanceof ProviderError);
				assert.equal((err as ProviderError).code, "invalid_key");
				return true;
			},
		);
	});

	it("zen: does not mistake a 400 for a valid key", async () => {
		await assert.rejects(
			opencodeProvider.validateKey(
				"zen-unknown",
				mockFetchSequence([catalog, { ok: false, status: 400, body: {} }]),
			),
			(err: unknown) => {
				assert.ok(err instanceof ProviderError);
				assert.equal((err as ProviderError).code, "server");
				assert.match((err as ProviderError).message, /could not verify/i);
				return true;
			},
		);
	});

	it("zen: does not mistake a 500 for a valid key", async () => {
		await assert.rejects(
			opencodeProvider.validateKey(
				"zen-unknown",
				mockFetchSequence([catalog, { ok: false, status: 500, body: {} }]),
			),
			(err: unknown) => {
				assert.ok(err instanceof ProviderError);
				assert.equal((err as ProviderError).code, "server");
				assert.match((err as ProviderError).message, /could not verify/i);
				return true;
			},
		);
	});
});
