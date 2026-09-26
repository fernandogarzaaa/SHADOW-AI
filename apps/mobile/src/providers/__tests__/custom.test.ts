/**
 * Custom OpenAI-compatible endpoint unit tests: base-URL normalization,
 * missing-URL errors, catalog fetch, key validation, and streaming,
 * with the HTTP layer and the URL store mocked.
 *
 * Run: `npm run test:providers`
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { createCustomProvider, normalizeBaseUrl } from "../custom";
import { ProviderError } from "../errors";
import type {
	FetchLike,
	StreamEvent,
	StreamRequest,
	StreamTransport,
} from "../types";

function providerWith(baseUrl: string | null) {
	return createCustomProvider(async () => baseUrl);
}

function mockTransport(fullBody: string, status = 200): StreamTransport {
	return {
		postStream: async (_url, init) => {
			init.onChunk(fullBody);
			return { status, finalText: fullBody };
		},
	};
}

function collectEvents() {
	const events: StreamEvent[] = [];
	return {
		events,
		request: (extra: Partial<StreamRequest> = {}): StreamRequest => ({
			apiKey: "sk-test",
			model: "llama3.1",
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

function mockFetch(responses: MockResponse[]): {
	fetch: FetchLike;
	calls: { url: string; init: Record<string, unknown> }[];
} {
	const calls: { url: string; init: Record<string, unknown> }[] = [];
	let i = 0;
	const fetch: FetchLike = (async (url: string, init: Record<string, unknown>) => {
		calls.push({ url, init });
		const r = responses[Math.min(i++, responses.length - 1)];
		return {
			ok: r.ok,
			status: r.status,
			text: async () =>
				typeof r.body === "string" ? r.body : JSON.stringify(r.body ?? {}),
			json: async () => (typeof r.body === "string" ? {} : (r.body ?? {})),
		};
	}) as FetchLike;
	return { fetch, calls };
}

describe("normalizeBaseUrl", () => {
	it("accepts http(s) URLs and strips trailing slashes", () => {
		assert.equal(
			normalizeBaseUrl("http://192.168.1.10:11434/v1///"),
			"http://192.168.1.10:11434/v1",
		);
		assert.equal(
			normalizeBaseUrl("  https://example.com/v1  "),
			"https://example.com/v1",
		);
	});

	it("rejects non-http(s) URLs", () => {
		assert.throws(() => normalizeBaseUrl("not a url"), (err) => {
			assert.ok(err instanceof ProviderError);
			assert.equal(err.code, "bad_request");
			return true;
		});
		assert.throws(() => normalizeBaseUrl("ftp://example.com"), (err) => {
			assert.ok(err instanceof ProviderError);
			return true;
		});
	});
});

describe("custom provider without a base URL", () => {
	it("listModels throws a helpful error", async () => {
		const provider = providerWith(null);
		const { fetch } = mockFetch([]);
		await assert.rejects(() => provider.listModels!("sk-test", fetch), (err) => {
			assert.ok(err instanceof ProviderError);
			assert.equal(err.code, "bad_request");
			assert.match(err.message, /base URL/i);
			return true;
		});
	});

	it("streamChat throws a helpful error", async () => {
		const provider = providerWith(null);
		const { request } = collectEvents();
		await assert.rejects(
			() => provider.streamChat(request(), mockTransport("")),
			(err) => {
				assert.ok(err instanceof ProviderError);
				assert.equal(err.code, "bad_request");
				return true;
			},
		);
	});
});

describe("custom provider with a base URL", () => {
	const base = "http://192.168.1.10:11434/v1";

	it("fetches the catalog from {base}/models", async () => {
		const provider = providerWith(base);
		const { fetch, calls } = mockFetch([
			{ ok: true, status: 200, body: { data: [{ id: "llama3.1" }] } },
		]);
		const models = await provider.listModels!("sk-test", fetch);
		assert.equal(calls[0].url, `${base}/models`);
		assert.deepEqual(
			models.map((m) => m.id),
			["llama3.1"],
		);
	});

	it("validateKey accepts a 200 catalog response", async () => {
		const provider = providerWith(base);
		const { fetch } = mockFetch([
			{ ok: true, status: 200, body: { data: [{ id: "llama3.1" }] } },
		]);
		await provider.validateKey!("sk-test", fetch);
	});

	it("validateKey rejects a 401", async () => {
		const provider = providerWith(base);
		const { fetch } = mockFetch([{ ok: false, status: 401, body: {} }]);
		await assert.rejects(() => provider.validateKey!("bad", fetch), (err) => {
			assert.ok(err instanceof ProviderError);
			assert.equal(err.code, "invalid_key");
			return true;
		});
	});

	it("streams via {base}/chat/completions", async () => {
		const provider = providerWith(base);
		const sse =
			`data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n` + `data: [DONE]\n\n`;
		const { events, request } = collectEvents();
		let seenUrl = "";
		const transport: StreamTransport = {
			postStream: async (url, init) => {
				seenUrl = url;
				init.onChunk(sse);
				return { status: 200, finalText: sse };
			},
		};
		await provider.streamChat(request(), transport);
		assert.equal(seenUrl, `${base}/chat/completions`);
		assert.deepEqual(
			events.map((e) => (e.type === "delta" ? e.text : e.type)),
			["Hi"],
		);
	});
});
