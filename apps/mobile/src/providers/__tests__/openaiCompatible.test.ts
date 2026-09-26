/**
 * Config-driven OpenAI-compatible provider factory unit tests: catalog
 * parsing/mapping, key validation strategies, streaming, and error
 * mapping, with the HTTP layer mocked.
 *
 * Run: `npm run test:providers`
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
	fetchCompatModels,
	makeOpenAICompatibleProvider,
	runCompatStream,
	type OpenAICompatConfig,
} from "../openaiCompatible";
import { compatConfigs } from "../compatProviders";
import { ProviderError } from "../errors";
import type {
	FetchLike,
	StreamEvent,
	StreamRequest,
	StreamTransport,
} from "../types";

const baseConfig: OpenAICompatConfig = {
	id: "xai",
	label: "xAI",
	chatBaseUrl: "https://api.x.ai/v1",
	modelsUrl: "https://api.x.ai/v1/models",
	staticModels: [{ id: "grok-4.6", label: "Grok 4.6", blurb: "x" }],
	defaultModel: "grok-4.6",
};

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
			model: "grok-4.6",
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

describe("compat catalog", () => {
	it("parses OpenAI-style {data:[{id}]} entries", async () => {
		const { fetch } = mockFetch([
			{
				ok: true,
				status: 200,
				body: { data: [{ id: "grok-4.6" }, { id: "grok-4.5" }] },
			},
		]);
		const models = await fetchCompatModels(baseConfig, "sk-test", fetch);
		assert.deepEqual(
			models.map((m) => m.id),
			["grok-4.6", "grok-4.5"],
		);
	});

	it("sends Bearer auth to the catalog URL", async () => {
		const { fetch, calls } = mockFetch([
			{ ok: true, status: 200, body: { data: [{ id: "a" }] } },
		]);
		await fetchCompatModels(baseConfig, "sk-test", fetch);
		assert.equal(calls[0].url, "https://api.x.ai/v1/models");
		const headers = calls[0].init["headers"] as Record<string, string>;
		assert.equal(headers["authorization"], "Bearer sk-test");
	});

	it("supports custom extract + map (Gemini native list shape)", async () => {
		const gemini = compatConfigs["gemini"];
		const { fetch } = mockFetch([
			{
				ok: true,
				status: 200,
				body: {
					models: [
						{
							name: "models/gemini-2.5-flash",
							supportedGenerationMethods: ["generateContent"],
						},
						{
							name: "models/gemini-embedding-001",
							supportedGenerationMethods: ["embedContent"],
						},
					],
				},
			},
		]);
		const models = await fetchCompatModels(gemini, "sk-test", fetch);
		// Embedding-only model is filtered out; the "models/" prefix is stripped.
		assert.deepEqual(
			models.map((m) => m.id),
			["gemini-2.5-flash"],
		);
	});

	it("maps non-generateContent entries out (Mistral capabilities filter)", async () => {
		const mistral = compatConfigs["mistral"];
		const { fetch } = mockFetch([
			{
				ok: true,
				status: 200,
				body: {
					data: [
						{ id: "mistral-large-latest", capabilities: { completion_chat: true } },
						{ id: "mistral-embed", capabilities: { completion_chat: false } },
					],
				},
			},
		]);
		const models = await fetchCompatModels(mistral, "sk-test", fetch);
		assert.deepEqual(
			models.map((m) => m.id),
			["mistral-large-latest"],
		);
	});

	it("excludes audio/guard models (Groq filter)", async () => {
		const groq = compatConfigs["groq"];
		const { fetch } = mockFetch([
			{
				ok: true,
				status: 200,
				body: {
					data: [
						{ id: "llama-3.3-70b-versatile" },
						{ id: "whisper-large-v3" },
						{ id: "meta-llama/llama-guard-4-12b" },
					],
				},
			},
		]);
		const models = await fetchCompatModels(groq, "sk-test", fetch);
		assert.deepEqual(
			models.map((m) => m.id),
			["llama-3.3-70b-versatile"],
		);
	});

	it("throws ProviderError when the catalog is empty", async () => {
		const { fetch } = mockFetch([{ ok: true, status: 200, body: { data: [] } }]);
		await assert.rejects(
			() => fetchCompatModels(baseConfig, "sk-test", fetch),
			(err) => err instanceof ProviderError,
		);
	});

	it("maps 401 to auth error with the provider label", async () => {
		const { fetch } = mockFetch([
			{ ok: false, status: 401, body: { error: { message: "bad key" } } },
		]);
		await assert.rejects(() => fetchCompatModels(baseConfig, "sk-test", fetch), (err) => {
			assert.ok(err instanceof ProviderError);
			assert.equal(err.code, "invalid_key");
			assert.match(err.message, /xAI/);
			return true;
		});
	});

	it("maps network failures to the network error", async () => {
		const fetch = (async () => {
			throw new Error("fetch failed");
		}) as FetchLike;
		await assert.rejects(() => fetchCompatModels(baseConfig, "k", fetch), (err) => {
			assert.ok(err instanceof ProviderError);
			assert.equal(err.code, "network");
			return true;
		});
	});
});

describe("compat key validation", () => {
	it("endpoint strategy (xAI /api-key): 200 means valid", async () => {
		const provider = makeOpenAICompatibleProvider({
			...baseConfig,
			validate: { kind: "endpoint", path: "/api-key" },
		});
		const { fetch, calls } = mockFetch([{ ok: true, status: 200, body: {} }]);
		await provider.validateKey("sk-test", fetch);
		assert.equal(calls[0].url, "https://api.x.ai/v1/api-key");
	});

	it("endpoint strategy: 401 means invalid key", async () => {
		const provider = makeOpenAICompatibleProvider({
			...baseConfig,
			validate: { kind: "endpoint", path: "/api-key" },
		});
		const { fetch } = mockFetch([{ ok: false, status: 401, body: {} }]);
		await assert.rejects(() => provider.validateKey("bad", fetch), (err) => {
			assert.ok(err instanceof ProviderError);
			assert.equal(err.code, "invalid_key");
			return true;
		});
	});

	it("default models strategy: a 200 catalog call validates the key", async () => {
		const provider = makeOpenAICompatibleProvider(baseConfig);
		const { fetch } = mockFetch([
			{ ok: true, status: 200, body: { data: [{ id: "grok-4.6" }] } },
		]);
		await provider.validateKey("sk-test", fetch);
	});
});

describe("compat streaming", () => {
	const sse =
		`data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n` +
		`data: {"choices":[{"delta":{"content":" world"}}]}\n\n` +
		`data: [DONE]\n\n`;

	it("streams deltas; the wire [DONE] is consumed, not forwarded", async () => {
		const { events, request } = collectEvents();
		await runCompatStream(baseConfig, request(), 100, mockTransport(sse));
		assert.deepEqual(
			events.map((e) => (e.type === "delta" ? e.text : e.type)),
			["Hello", " world"],
		);
	});

	it("emits a synthetic done when the wire never ends cleanly", async () => {
		const { events, request } = collectEvents();
		const noDone = `data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n`;
		await runCompatStream(baseConfig, request(), 100, mockTransport(noDone));
		assert.deepEqual(
			events.map((e) => (e.type === "delta" ? e.text : e.type)),
			["Hi", "done"],
		);
	});

	it("posts to chat/completions with Bearer auth", async () => {
		const { request } = collectEvents();
		const seen: { url: string; init: Record<string, unknown> }[] = [];
		const transport: StreamTransport = {
			postStream: async (url, init) => {
				seen.push({ url, init: init as unknown as Record<string, unknown> });
				init.onChunk("data: [DONE]\n\n");
				return { status: 200, finalText: "" };
			},
		};
		await runCompatStream(baseConfig, request(), 100, transport);
		assert.equal(seen.length, 1);
		const s = seen[0];
		assert.equal(s.url, "https://api.x.ai/v1/chat/completions");
		const headers = s.init["headers"] as Record<string, string>;
		assert.equal(headers["authorization"], "Bearer sk-test");
		const body = JSON.parse(s.init["body"] as string) as Record<string, unknown>;
		assert.equal(body["model"], "grok-4.6");
		assert.equal(body["stream"], true);
	});

	it("rewrites model ids before chat (Gemini strips models/)", async () => {
		const gemini = compatConfigs["gemini"];
		const { request } = collectEvents();
		let seenBody = "";
		const transport: StreamTransport = {
			postStream: async (_url, init) => {
				seenBody = init.body as string;
				init.onChunk("data: [DONE]\n\n");
				return { status: 200, finalText: "" };
			},
		};
		await runCompatStream(
			gemini,
			request({ model: "models/gemini-2.5-flash" }),
			100,
			transport,
		);
		const body = JSON.parse(seenBody) as Record<string, unknown>;
		assert.equal(body["model"], "gemini-2.5-flash");
	});

	it("maps non-200 chat responses to provider errors", async () => {
		const { request } = collectEvents();
		await assert.rejects(
			() =>
				runCompatStream(
					baseConfig,
					request(),
					100,
					mockTransport("insufficient credits", 402),
				),
			(err) => {
				assert.ok(err instanceof ProviderError);
				return true;
			},
		);
	});

	it("quickComplete aggregates deltas into text", async () => {
		const provider = makeOpenAICompatibleProvider(baseConfig);
		const text = await provider.quickComplete!(
			{
				apiKey: "sk-test",
				model: "grok-4.6",
				messages: [{ role: "user", content: "hi" }],
				maxTokens: 50,
			},
			mockTransport(sse),
		);
		assert.equal(text, "Hello world");
	});
});

describe("curated compat providers", () => {
	it("every config has static models, a default, and a distinct base URL", () => {
		const seen = new Set<string>();
		for (const [id, config] of Object.entries(compatConfigs)) {
			assert.ok(config.staticModels.length > 0, `${id} static models`);
			assert.ok(config.defaultModel.length > 0, `${id} default model`);
			assert.ok(!seen.has(config.chatBaseUrl), `${id} duplicate base URL`);
			seen.add(config.chatBaseUrl);
			assert.match(config.modelsUrl, /^https:\/\//, `${id} models URL`);
		}
	});
});
