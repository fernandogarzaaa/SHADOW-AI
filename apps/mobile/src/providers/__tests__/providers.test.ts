/**
 * Provider unit tests: Anthropic + OpenAI streaming adapters and key
 * validation, with the HTTP layer mocked.
 *
 * Run: `npm run test:providers` (compiles this dir with tsc, runs node --test).
 * No npm test dependencies needed; uses node:test + node:assert/strict.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { runAnthropicStream, anthropicProvider } from "../anthropic";
import { runOpenAIStream, openaiProvider } from "../openai";
import { ProviderError } from "../errors";
import type {
	FetchLike,
	StreamEvent,
	StreamRequest,
	StreamTransport,
} from "../types";

/** Build a mock transport that feeds the full SSE body in `splits` pieces. */
function mockTransport(
	fullBody: string,
	splits: number[],
	status = 200,
): StreamTransport {
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
			apiKey: "sk-fake-test-key",
			model: "test-model",
			messages: [{ role: "user", content: "hi" }],
			onEvent: (e) => events.push(e),
			...extra,
		}),
	};
}

function mockFetch(
	ok: boolean,
	status: number,
	body = "",
	impl?: () => Promise<never>,
): FetchLike {
	return async () => {
		if (impl) await impl();
		return {
			ok,
			status,
			text: async () => body,
			json: async () => ({}),
		};
	};
}

describe("anthropic stream", () => {
	const sseBody =
		`event: message_start\ndata: {"type":"message_start","message":{"id":"m1"}}\n\n` +
		`event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hel"}}\n\n` +
		`event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"lo"}}\n\n` +
		`event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}\n\n` +
		`event: message_stop\ndata: {"type":"message_stop"}\n\n`;

	it("reassembles deltas split mid-event across chunks", async () => {
		const { events, request } = collectEvents();
		// Split at odd byte offsets, including inside JSON payloads.
		// The adapters swallow server-side done markers (message_stop /
		// [DONE]) and only synthesize a done event when the stream ends
		// without one, so completion is the resolved promise, not an event.
		await runAnthropicStream(request(), 64, mockTransport(sseBody, [37, 5, 61, 3, 200]));
		const text = events
			.filter((e) => e.type === "delta")
			.map((e) => (e as { text: string }).text)
			.join("");
		assert.equal(text, "Hello");
	});

	it("synthesizes done when the stream ends without a stop marker", async () => {
		const body =
			`event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hi"}}\n\n`;
		const { events, request } = collectEvents();
		await runAnthropicStream(request(), 64, mockTransport(body, [20, 20]));
		const text = events
			.filter((e) => e.type === "delta")
			.map((e) => (e as { text: string }).text)
			.join("");
		assert.equal(text, "Hi");
		assert.ok(events.some((e) => e.type === "done"), "expected a done event");
	});

	it("single-chunk delivery also works", async () => {
		const { events, request } = collectEvents();
		await runAnthropicStream(request(), 64, mockTransport(sseBody, [sseBody.length]));
		const text = events
			.filter((e) => e.type === "delta")
			.map((e) => (e as { text: string }).text)
			.join("");
		assert.equal(text, "Hello");
	});

	it("skips malformed events without aborting the stream", async () => {
		const body =
			`event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"A"}}\n\n` +
			`event: content_block_delta\ndata: not-json{{{\n\n` +
			`event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"B"}}\n\n` +
			`event: message_stop\ndata: {"type":"message_stop"}\n\n`;
		const { events, request } = collectEvents();
		await runAnthropicStream(request(), 64, mockTransport(body, [40, 40, 40, 40, 40]));
		const text = events
			.filter((e) => e.type === "delta")
			.map((e) => (e as { text: string }).text)
			.join("");
		assert.equal(text, "AB");
	});

	it("maps HTTP failures to typed errors", async () => {
		const cases: Array<[number, string, string]> = [
			[401, "invalid_key", ""],
			[429, "rate_limited", ""],
			[500, "server", ""],
			[400, "bad_request", ""],
		];
		for (const [status, code, body] of cases) {
			const { request } = collectEvents();
			await assert.rejects(
				runAnthropicStream(request(), 64, mockTransport(body, [], status)),
				(err: unknown) => {
					assert.ok(err instanceof ProviderError);
					assert.equal((err as ProviderError).code, code);
					return true;
				},
				`status ${status} should map to ${code}`,
			);
		}
	});

	it("never leaks the key into error messages", async () => {
		const fakeKey = "sk-ant-fake-test-key-000";
		const { request } = collectEvents();
		const req = request({ apiKey: fakeKey });
		await assert.rejects(
			runAnthropicStream(req, 64, mockTransport("", [], 401)),
			(err: unknown) => {
				assert.ok(err instanceof Error);
				assert.ok(!(err as Error).message.includes(fakeKey));
				return true;
			},
		);
	});
});

describe("openai stream", () => {
	const sseBody =
		`data: {"id":"c1","choices":[{"delta":{"content":"Hel"},"finish_reason":null}]}\n\n` +
		`data: {"id":"c1","choices":[{"delta":{"content":"lo"},"finish_reason":null}]}\n\n` +
		`data: {"id":"c1","choices":[{"delta":{},"finish_reason":"stop"}]}\n\n` +
		`data: [DONE]\n\n`;

	it("reassembles deltas split mid-event across chunks", async () => {
		const { events, request } = collectEvents();
		// Server-side termination ([DONE] / finish_reason) is swallowed by
		// the adapter; stream completion is the resolved promise.
		await runOpenAIStream(request(), 64, mockTransport(sseBody, [29, 7, 53, 11, 300]));
		const text = events
			.filter((e) => e.type === "delta")
			.map((e) => (e as { text: string }).text)
			.join("");
		assert.equal(text, "Hello");
	});

	it("handles [DONE] as stream termination", async () => {
		const body = `data: [DONE]\n\n`;
		const { events, request } = collectEvents();
		await runOpenAIStream(request(), 64, mockTransport(body, [5]));
		assert.deepEqual(events, []);
	});

	it("skips malformed events without aborting the stream", async () => {
		const body =
			`data: {"id":"c1","choices":[{"delta":{"content":"A"},"finish_reason":null}]}\n\n` +
			`data: {broken\n\n` +
			`data: {"id":"c1","choices":[{"delta":{"content":"B"},"finish_reason":null}]}\n\n` +
			`data: [DONE]\n\n`;
		const { events, request } = collectEvents();
		await runOpenAIStream(request(), 64, mockTransport(body, [30, 30, 30, 30, 30]));
		const text = events
			.filter((e) => e.type === "delta")
			.map((e) => (e as { text: string }).text)
			.join("");
		assert.equal(text, "AB");
	});

	it("maps HTTP failures to typed errors", async () => {
		const cases: Array<[number, string]> = [
			[401, "invalid_key"],
			[429, "rate_limited"],
			[500, "server"],
			[404, "bad_request"],
		];
		for (const [status, code] of cases) {
			const { request } = collectEvents();
			await assert.rejects(
				runOpenAIStream(request(), 64, mockTransport("", [], status)),
				(err: unknown) => {
					assert.ok(err instanceof ProviderError);
					assert.equal((err as ProviderError).code, code);
					return true;
				},
				`status ${status} should map to ${code}`,
			);
		}
	});
});

describe("validateKey", () => {
	it("anthropic: resolves on 200", async () => {
		await anthropicProvider.validateKey("sk-ant-x", mockFetch(true, 200));
	});

	it("anthropic: rejects invalid keys", async () => {
		await assert.rejects(
			anthropicProvider.validateKey("bad", mockFetch(false, 401, "invalid x-api-key")),
			(err: unknown) => {
				assert.ok(err instanceof ProviderError);
				assert.equal((err as ProviderError).code, "invalid_key");
				return true;
			},
		);
	});

	it("anthropic: maps network failures", async () => {
		await assert.rejects(
			anthropicProvider.validateKey(
				"sk-ant-x",
				mockFetch(false, 0, "", async () => {
					throw new TypeError("fetch failed");
				}),
			),
			(err: unknown) => {
				assert.ok(err instanceof ProviderError);
				assert.equal((err as ProviderError).code, "network");
				return true;
			},
		);
	});

	it("openai: resolves on 200", async () => {
		await openaiProvider.validateKey("sk-x", mockFetch(true, 200));
	});

	it("openai: rejects invalid keys", async () => {
		await assert.rejects(
			openaiProvider.validateKey("bad", mockFetch(false, 401, "Incorrect API key")),
			(err: unknown) => {
				assert.ok(err instanceof ProviderError);
				assert.equal((err as ProviderError).code, "invalid_key");
				return true;
			},
		);
	});

	it("openai: maps rate limits", async () => {
		await assert.rejects(
			openaiProvider.validateKey("sk-x", mockFetch(false, 429, "rate limit")),
			(err: unknown) => {
				assert.ok(err instanceof ProviderError);
				assert.equal((err as ProviderError).code, "rate_limited");
				return true;
			},
		);
	});
});
