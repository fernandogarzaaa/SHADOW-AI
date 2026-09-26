/**
 * Cohere native adapter unit tests: typed SSE event parsing, model
 * catalog mapping (both catalog shapes), key validation, and streaming,
 * with the HTTP layer mocked.
 *
 * Run: `npm run test:providers`
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
	cohereProvider,
	fetchCohereModels,
	parseCoherePayload,
	runCohereStream,
	toModelInfo,
} from "../cohere";
import { ProviderError } from "../errors";
import type {
	FetchLike,
	StreamEvent,
	StreamRequest,
	StreamTransport,
} from "../types";

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
			model: "command-a-03-2025",
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

describe("parseCoherePayload", () => {
	it("extracts text from content-delta events", () => {
		const event = parseCoherePayload(
			'{"type":"content-delta","index":0,"delta":{"message":{"content":{"type":"text","text":"Hello"}}}}',
		);
		assert.deepEqual(event, { kind: "delta", text: "Hello" });
	});

	it("accepts the unhyphenated contentdelta spelling", () => {
		const event = parseCoherePayload(
			'{"type":"contentdelta","delta":{"message":{"content":{"type":"text","text":"Hi"}}}}',
		);
		assert.deepEqual(event, { kind: "delta", text: "Hi" });
	});

	it("treats message-end as done with the stop reason", () => {
		const event = parseCoherePayload(
			'{"type":"message-end","delta":{"finish_reason":"COMPLETE"}}',
		);
		assert.deepEqual(event, { kind: "done", stopReason: "COMPLETE" });
	});

	it("treats [DONE] as done", () => {
		assert.deepEqual(parseCoherePayload("[DONE]"), { kind: "done" });
	});

	it("ignores non-text events and garbage", () => {
		assert.equal(
			parseCoherePayload('{"type":"message-start","id":"abc"}'),
			null,
		);
		assert.equal(
			parseCoherePayload(
				'{"type":"tool-call-delta","delta":{"message":{"tool_calls":{}}}}',
			),
			null,
		);
		assert.equal(parseCoherePayload("not json"), null);
		assert.deepEqual(parseCoherePayload("   "), { kind: "done" });
	});
});

describe("toModelInfo", () => {
	it("prefers name, falls back to id", () => {
		assert.deepEqual(toModelInfo({ name: "command-a-03-2025" })?.id, "command-a-03-2025");
		assert.deepEqual(toModelInfo({ id: "x" })?.id, "x");
	});

	it("drops entries without a usable id", () => {
		assert.equal(toModelInfo({}), null);
		assert.equal(toModelInfo({ name: 42 }), null);
	});
});

describe("fetchCohereModels", () => {
	it("parses the {models:[{name}]} shape", async () => {
		const { fetch, calls } = mockFetch([
			{
				ok: true,
				status: 200,
				body: { models: [{ name: "command-a-03-2025" }, { name: "command-r-plus-08-2024" }] },
			},
		]);
		const models = await fetchCohereModels("sk-test", fetch);
		assert.equal(calls[0].url, "https://api.cohere.com/v1/models");
		assert.deepEqual(
			models.map((m) => m.id),
			["command-a-03-2025", "command-r-plus-08-2024"],
		);
	});

	it("falls back to /v2/models on 404, then parses {data:[{id}]}", async () => {
		const { fetch, calls } = mockFetch([
			{ ok: false, status: 404, body: {} },
			{ ok: true, status: 200, body: { data: [{ id: "command-a" }] } },
		]);
		const models = await fetchCohereModels("sk-test", fetch);
		assert.deepEqual(
			calls.map((c) => c.url),
			["https://api.cohere.com/v1/models", "https://api.cohere.com/v2/models"],
		);
		assert.deepEqual(
			models.map((m) => m.id),
			["command-a"],
		);
	});

	it("maps 401 to an auth error", async () => {
		const { fetch } = mockFetch([{ ok: false, status: 401, body: {} }]);
		await assert.rejects(() => fetchCohereModels("bad", fetch), (err) => {
			assert.ok(err instanceof ProviderError);
			assert.equal(err.code, "invalid_key");
			return true;
		});
	});
});

describe("cohere streaming", () => {
	const sse =
		`event: message-start\n` +
		`data: {"type":"message-start","id":"abc"}\n\n` +
		`event: content-delta\n` +
		`data: {"type":"content-delta","index":0,"delta":{"message":{"content":{"type":"text","text":"Hello"}}}}\n\n` +
		`event: content-delta\n` +
		`data: {"type":"content-delta","index":0,"delta":{"message":{"content":{"type":"text","text":" world"}}}}\n\n` +
		`event: message-end\n` +
		`data: {"type":"message-end","delta":{"finish_reason":"COMPLETE"}}\n\n`;

	it("streams deltas; message-end is consumed, not forwarded", async () => {
		const { events, request } = collectEvents();
		await runCohereStream(request(), 100, mockTransport(sse));
		assert.deepEqual(
			events.map((e) => (e.type === "delta" ? e.text : e.type)),
			["Hello", " world"],
		);
	});

	it("posts to /v2/chat with stream:true and Bearer auth", async () => {
		const { request } = collectEvents();
		const seen: { url: string; init: Record<string, unknown> }[] = [];
		const transport: StreamTransport = {
			postStream: async (url, init) => {
				seen.push({ url, init: init as unknown as Record<string, unknown> });
				init.onChunk('data: {"type":"message-end","delta":{}}\n\n');
				return { status: 200, finalText: "" };
			},
		};
		await runCohereStream(request(), 100, transport);
		assert.equal(seen.length, 1);
		const s = seen[0];
		assert.equal(s.url, "https://api.cohere.com/v2/chat");
		const headers = s.init["headers"] as Record<string, string>;
		assert.equal(headers["authorization"], "Bearer sk-test");
		const body = JSON.parse(s.init["body"] as string) as Record<string, unknown>;
		assert.equal(body["stream"], true);
		assert.equal(body["model"], "command-a-03-2025");
		assert.deepEqual(body["messages"], [{ role: "user", content: "hi" }]);
	});

	it("maps non-200 responses to provider errors", async () => {
		const { request } = collectEvents();
		await assert.rejects(
			() => runCohereStream(request(), 100, mockTransport("bad request", 400)),
			(err) => {
				assert.ok(err instanceof ProviderError);
				return true;
			},
		);
	});

	it("provider exposes native metadata", () => {
		assert.equal(cohereProvider.id, "cohere");
		assert.ok(cohereProvider.models.length > 0);
		assert.ok(typeof cohereProvider.validateKey === "function");
		assert.ok(typeof cohereProvider.listModels === "function");
	});
});
