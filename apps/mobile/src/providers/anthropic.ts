/**
 * Anthropic Messages API adapter (BYOK).
 *
 * Docs: https://docs.anthropic.com/en/api/messages-streaming
 * Direct calls from a mobile client require the
 * `anthropic-dangerous-direct-browser-access: true` header.
 */

import {
	ProviderError,
	mapHttpError,
	toProviderError,
} from "./errors";
import { IncrementalSseParser } from "./sse";
import type {
	FetchLike,
	ModelProvider,
	ProviderMessage,
	StreamEvent,
	StreamRequest,
	StreamTransport,
} from "./types";

const API_BASE = "https://api.anthropic.com";
const ANTHROPIC_VERSION = "2023-06-01";

function baseHeaders(apiKey: string): Record<string, string> {
	return {
		"x-api-key": apiKey,
		"anthropic-version": ANTHROPIC_VERSION,
		"content-type": "application/json",
		"anthropic-dangerous-direct-browser-access": "true",
	};
}

export interface AnthropicRequestBody {
	model: string;
	max_tokens: number;
	stream: boolean;
	system?: string;
	messages: Array<{ role: "user" | "assistant"; content: string }>;
}

/** Build the POST /v1/messages body. Pure: unit-tested. */
export function buildAnthropicBody(
	model: string,
	messages: ProviderMessage[],
	maxTokens: number,
	stream: boolean,
): AnthropicRequestBody {
	let system: string | undefined;
	const rest: Array<{ role: "user" | "assistant"; content: string }> = [];
	for (const m of messages) {
		if (m.role === "system") {
			system = system ? `${system}\n\n${m.content}` : m.content;
		} else {
			rest.push({ role: m.role, content: m.content });
		}
	}
	const body: AnthropicRequestBody = {
		model,
		max_tokens: maxTokens,
		stream,
		messages: rest,
	};
	if (system) {
		body.system = system;
	}
	return body;
}

type AnthropicSsePayload = {
	type?: string;
	delta?: { type?: string; text?: string };
	message?: { stop_reason?: string };
	error?: { type?: string; message?: string };
};

/**
 * Map one raw SSE data payload to stream events. Pure: unit-tested.
 * Returns null for events that carry no user-visible content.
 */
export function parseAnthropicPayload(payload: string): StreamEvent[] | null {
	if (payload === "[DONE]") {
		return [{ type: "done" }];
	}
	let data: AnthropicSsePayload;
	try {
		data = JSON.parse(payload) as AnthropicSsePayload;
	} catch {
		return null;
	}
	if (data.type === "content_block_delta" && data.delta?.type === "text_delta") {
		const text = data.delta.text ?? "";
		return text.length > 0 ? [{ type: "delta", text }] : null;
	}
	if (data.type === "message_stop") {
		return [{ type: "done", stopReason: data.message?.stop_reason }];
	}
	if (data.type === "error") {
		// Never surface provider payload text to the user; keep it generic.
		throw new ProviderError("server", "Anthropic reported an error. Try again.");
	}
	return null;
}

/** Exported for unit tests: runs a stream against an injected transport. */
export async function runAnthropicStream(
	request: StreamRequest,
	maxTokens: number,
	transport: StreamTransport,
): Promise<void> {
	const { apiKey, model, messages, signal, onEvent } = request;
	const body = JSON.stringify(buildAnthropicBody(model, messages, maxTokens, true));
	const parser = new IncrementalSseParser();
	let done = false;

	const { status, finalText } = await transport.postStream(`${API_BASE}/v1/messages`, {
		headers: baseHeaders(apiKey),
		body,
		signal,
		onChunk: (fullText) => {
			for (const payload of parser.push(fullText)) {
				const events = parseAnthropicPayload(payload);
				if (!events) continue;
				for (const event of events) {
					if (event.type === "done") {
						done = true;
					} else {
						onEvent(event);
					}
				}
			}
		},
	});

	if (status !== 200) {
		throw mapHttpError(status, finalText, "Anthropic");
	}
	for (const payload of parser.flush()) {
		const events = parseAnthropicPayload(payload);
		if (!events) continue;
		for (const event of events) {
			if (event.type === "done") {
				done = true;
			} else {
				onEvent(event);
			}
		}
	}
	if (!done) {
		onEvent({ type: "done" });
	}
}

export const anthropicProvider: ModelProvider = {
	id: "anthropic",
	label: "Anthropic",
	models: [
		{
			id: "claude-sonnet-5",
			label: "Sonnet 5",
			blurb: "Balanced speed and intelligence. Good default.",
		},
		{
			id: "claude-opus-5",
			label: "Opus 5",
			blurb: "Most capable. Best for hard reasoning and long tasks.",
		},
		{
			id: "claude-haiku-4-5",
			label: "Haiku 4.5",
			blurb: "Fast and cheap. Good for quick questions.",
		},
		{
			id: "claude-opus-4-8",
			label: "Opus 4.8",
			blurb: "Previous flagship, still supported.",
		},
	],
	defaultModel: "claude-sonnet-5",

	validateKey: async (apiKey: string, fetchImpl?: FetchLike) => {
		const runFetch: FetchLike =
			fetchImpl ??
			((globalThis.fetch as unknown) as FetchLike);
		let response;
		try {
			response = await runFetch(`${API_BASE}/v1/models`, {
				method: "GET",
				headers: baseHeaders(apiKey),
			});
		} catch (error) {
			throw toProviderError(error, "Anthropic");
		}
		if (!response.ok) {
			const text = await response.text().catch(() => "");
			throw mapHttpError(response.status, text, "Anthropic");
		}
	},

	streamChat: async (request: StreamRequest, transport?: StreamTransport) => {
		if (!transport) {
			throw new ProviderError("unknown", "No network transport available.");
		}
		try {
			await runAnthropicStream(request, 4096, transport);
		} catch (error) {
			throw toProviderError(error, "Anthropic");
		}
	},

	quickComplete: async (request, transport?: StreamTransport) => {
		if (!transport) {
			throw new ProviderError("unknown", "No network transport available.");
		}
		let text = "";
		await runAnthropicStream(
			{ ...request, onEvent: (e) => { if (e.type === "delta") text += e.text; } },
			request.maxTokens,
			transport,
		);
		return text;
	},
};
