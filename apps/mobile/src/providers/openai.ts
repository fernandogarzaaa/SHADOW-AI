/**
 * OpenAI Chat Completions adapter (BYOK, streaming).
 *
 * Docs: https://platform.openai.com/docs/api-reference/chat-streaming
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

const API_BASE = "https://api.openai.com";

function baseHeaders(apiKey: string): Record<string, string> {
	return {
		authorization: `Bearer ${apiKey}`,
		"content-type": "application/json",
	};
}

export interface OpenAIRequestBody {
	model: string;
	stream: boolean;
	stream_options?: { include_usage: boolean };
	max_completion_tokens: number;
	messages: Array<{ role: "system" | "user" | "assistant"; content: string }>;
}

/** Build the POST /v1/chat/completions body. Pure: unit-tested. */
export function buildOpenAIBody(
	model: string,
	messages: ProviderMessage[],
	maxTokens: number,
	stream: boolean,
): OpenAIRequestBody {
	const body: OpenAIRequestBody = {
		model,
		stream,
		max_completion_tokens: maxTokens,
		messages: messages.map((m) => ({ role: m.role, content: m.content })),
	};
	if (stream) {
		body.stream_options = { include_usage: true };
	}
	return body;
}

type OpenAIChunk = {
	choices?: Array<{
		delta?: { content?: string | null; refusal?: string | null };
		finish_reason?: string | null;
	}>;
	error?: { message?: string; code?: string };
};

/**
 * Map one raw SSE data payload to stream events. Pure: unit-tested.
 * Returns null for keep-alives / usage-only chunks.
 */
export function parseOpenAIPayload(payload: string): StreamEvent[] | null {
	if (payload === "[DONE]") {
		return [{ type: "done" }];
	}
	let data: OpenAIChunk;
	try {
		data = JSON.parse(payload) as OpenAIChunk;
	} catch {
		return null;
	}
	if (data.error) {
		// Never surface provider payload text to the user; keep it generic.
		throw new ProviderError("server", "OpenAI reported an error. Try again.");
	}
	const choice = data.choices?.[0];
	if (!choice) {
		return null;
	}
	const events: StreamEvent[] = [];
	const content = choice.delta?.content;
	if (typeof content === "string" && content.length > 0) {
		events.push({ type: "delta", text: content });
	}
	if (choice.finish_reason) {
		events.push({ type: "done", stopReason: choice.finish_reason });
	}
	return events.length > 0 ? events : null;
}

/** Exported for unit tests: runs a stream against an injected transport. */
export async function runOpenAIStream(
	request: StreamRequest,
	maxTokens: number,
	transport: StreamTransport,
): Promise<void> {
	const { apiKey, model, messages, signal, onEvent } = request;
	const body = JSON.stringify(buildOpenAIBody(model, messages, maxTokens, true));
	const parser = new IncrementalSseParser();
	let done = false;

	const emit = (payload: string) => {
		const events = parseOpenAIPayload(payload);
		if (!events) return;
		for (const event of events) {
			if (event.type === "done") {
				done = true;
			} else {
				onEvent(event);
			}
		}
	};

	const { status, finalText } = await transport.postStream(
		`${API_BASE}/v1/chat/completions`,
		{
			headers: baseHeaders(apiKey),
			body,
			signal,
			onChunk: (fullText) => {
				for (const payload of parser.push(fullText)) {
					emit(payload);
				}
			},
		},
	);

	if (status !== 200) {
		throw mapHttpError(status, finalText, "OpenAI");
	}
	for (const payload of parser.flush()) {
		emit(payload);
	}
	if (!done) {
		onEvent({ type: "done" });
	}
}

export const openaiProvider: ModelProvider = {
	id: "openai",
	label: "OpenAI",
	models: [
		{
			id: "gpt-5.6",
			label: "GPT-5.6",
			blurb: "Strong all-rounder. Good default.",
		},
		{
			id: "gpt-6-astra",
			label: "GPT-6 Astra",
			blurb: "Newest flagship for demanding work.",
		},
		{
			id: "gpt-5.4",
			label: "GPT-5.4",
			blurb: "Capable and efficient.",
		},
		{
			id: "gpt-5.6-luna",
			label: "GPT-5.6 Luna",
			blurb: "Fast and cheap for quick questions.",
		},
	],
	defaultModel: "gpt-5.6",

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
			throw toProviderError(error, "OpenAI");
		}
		if (!response.ok) {
			const text = await response.text().catch(() => "");
			throw mapHttpError(response.status, text, "OpenAI");
		}
	},

	streamChat: async (request: StreamRequest, transport?: StreamTransport) => {
		if (!transport) {
			throw new ProviderError("unknown", "No network transport available.");
		}
		try {
			await runOpenAIStream(request, 4096, transport);
		} catch (error) {
			throw toProviderError(error, "OpenAI");
		}
	},

	quickComplete: async (request, transport?: StreamTransport) => {
		if (!transport) {
			throw new ProviderError("unknown", "No network transport available.");
		}
		let text = "";
		await runOpenAIStream(
			{ ...request, onEvent: (e) => { if (e.type === "delta") text += e.text; } },
			request.maxTokens,
			transport,
		);
		return text;
	},
};
