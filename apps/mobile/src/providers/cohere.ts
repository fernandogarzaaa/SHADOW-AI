/**
 * Cohere adapter (BYOK, streaming, native v2 API).
 *
 * Cohere is not OpenAI wire-compatible: chat is POST /v2/chat with typed
 * content blocks, and streaming uses typed SSE events. The event shapes
 * below are corroborated by multiple independent consumer implementations
 * (cohere-python README, Braintrust integrations, Swift client docs):
 *
 *   {"type":"content-delta","delta":{"message":{"content":{"type":"text","text":"..."}}}}
 *   {"type":"message-end","delta":{"finish_reason":"COMPLETE",...}}
 *
 * Event type names are normalized (hyphens stripped) so both
 * "content-delta" and "contentdelta" parse.
 */

import {
	ProviderError,
	mapHttpError,
	toProviderError,
} from "./errors";
import { IncrementalSseParser } from "./sse";
import type {
	FetchLike,
	ModelInfo,
	ModelProvider,
	ProviderMessage,
	StreamRequest,
	StreamTransport,
} from "./types";

const API_BASE = "https://api.cohere.com";

function baseHeaders(apiKey: string): Record<string, string> {
	return {
		authorization: `Bearer ${apiKey}`,
		"content-type": "application/json",
	};
}

/** Normalize "content-delta" and "contentdelta" to the same token. */
function normType(type: unknown): string {
	return typeof type === "string" ? type.replace(/-/g, "") : "";
}

export interface CohereStreamEvent {
	kind: "delta" | "done";
	text?: string;
	stopReason?: string;
}

/**
 * Parse one Cohere SSE data payload. Returns null for events that carry
 * no text (message-start, content-start/end, citations, tool calls).
 * Pure: unit-tested.
 */
export function parseCoherePayload(payload: string): CohereStreamEvent | null {
	const trimmed = payload.trim();
	if (trimmed === "" || trimmed === "[DONE]") {
		return { kind: "done" };
	}
	let data: Record<string, unknown>;
	try {
		data = JSON.parse(trimmed) as Record<string, unknown>;
	} catch {
		return null;
	}
	const type = normType(data["type"]);
	if (type === "contentdelta") {
		const delta = data["delta"] as
			| { message?: { content?: { text?: unknown } } }
			| undefined;
		const text = delta?.message?.content?.text;
		if (typeof text === "string" && text.length > 0) {
			return { kind: "delta", text };
		}
		return null;
	}
	if (type === "messageend" || type === "streamend") {
		const delta = data["delta"] as { finish_reason?: unknown } | undefined;
		const reason = delta?.finish_reason;
		return {
			kind: "done",
			stopReason: typeof reason === "string" ? reason : undefined,
		};
	}
	return null;
}

function toCohereMessages(messages: ProviderMessage[]): { role: string; content: string }[] {
	return messages.map((m) => ({
		role: m.role,
		content: m.content,
	}));
}

interface CohereModelEntry {
	name?: unknown;
	id?: unknown;
}

/** Map one catalog entry to a ModelInfo. Pure: unit-tested. */
export function toModelInfo(entry: CohereModelEntry): ModelInfo | null {
	const raw = entry.name ?? entry.id;
	if (typeof raw !== "string" || raw.length === 0) {
		return null;
	}
	return { id: raw, label: raw, blurb: "via Cohere", capabilities: { protocol: "native", source: "live" } };
}

/**
 * Fetch the live Cohere catalog. Tries /v1/models, then /v2/models;
 * accepts both {models:[{name}]} and {data:[{id}]} shapes.
 * Pure-ish: unit-tested with an injected fetch.
 */
export async function fetchCohereModels(
	apiKey: string,
	fetchImpl?: FetchLike,
): Promise<ModelInfo[]> {
	const runFetch: FetchLike =
		fetchImpl ?? (globalThis.fetch as unknown as FetchLike);
	let lastError: ProviderError | null = null;
	for (const path of ["/v1/models", "/v2/models"]) {
		let response;
		try {
			response = await runFetch(`${API_BASE}${path}`, {
				method: "GET",
				headers: baseHeaders(apiKey),
			});
		} catch (error) {
			throw toProviderError(error, "Cohere");
		}
		if (response.status === 404) {
			continue;
		}
		if (!response.ok) {
			const text = await response.text().catch(() => "");
			throw mapHttpError(response.status, text, "Cohere");
		}
		const json = (await response.json()) as {
			models?: CohereModelEntry[];
			data?: CohereModelEntry[];
		};
		const entries = json.models ?? json.data ?? [];
		const models: ModelInfo[] = [];
		for (const entry of entries) {
			const info = toModelInfo(entry);
			if (info) {
				models.push(info);
			}
		}
		if (models.length === 0) {
			throw new ProviderError("server", "Cohere returned no models.");
		}
		return models;
	}
	throw lastError ?? new ProviderError("server", "Cohere returned no models.");
}

async function postChat(
	apiKey: string,
	model: string,
	messages: ProviderMessage[],
	maxTokens: number,
	stream: boolean,
	fetchImpl?: FetchLike,
): Promise<Response> {
	const runFetch: FetchLike =
		fetchImpl ?? (globalThis.fetch as unknown as FetchLike);
	return (await runFetch(`${API_BASE}/v2/chat`, {
		method: "POST",
		headers: baseHeaders(apiKey),
		body: JSON.stringify({
			model,
			messages: toCohereMessages(messages),
			max_tokens: maxTokens,
			stream,
		}),
	})) as Response;
}

/** Exported for unit tests: runs a stream against an injected transport. */
export async function runCohereStream(
	request: StreamRequest,
	maxTokens: number,
	transport: StreamTransport,
): Promise<void> {
	const { apiKey, model, messages, signal, onEvent } = request;
	const body = JSON.stringify({
		model,
		messages: toCohereMessages(messages),
		max_tokens: maxTokens,
		stream: true,
	});
	const parser = new IncrementalSseParser();
	let done = false;

	const emit = (payload: string) => {
		const event = parseCoherePayload(payload);
		if (!event) {
			return;
		}
		if (event.kind === "done") {
			done = true;
		} else if (event.text) {
			onEvent({ type: "delta", text: event.text });
		}
	};

	const { status, finalText } = await transport.postStream(
		`${API_BASE}/v2/chat`,
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
		throw mapHttpError(status, finalText, "Cohere");
	}
	for (const payload of parser.flush()) {
		emit(payload);
	}
	if (!done) {
		onEvent({ type: "done" });
	}
}

export const cohereProvider: ModelProvider = {
	id: "cohere",
	label: "Cohere",
	models: [
		{
			id: "command-a-03-2025",
			label: "Command A",
			blurb: "Flagship chat model.",
		},
		{
			id: "command-r-plus-08-2024",
			label: "Command R+",
			blurb: "Strong RAG and chat model.",
		},
	],
	defaultModel: "command-a-03-2025",

	listModels: (apiKey, fetchImpl) => fetchCohereModels(apiKey, fetchImpl),

	validateKey: async (apiKey: string, fetchImpl?: FetchLike) => {
		// The catalog call doubles as the health check; a 200 means the
		// key is accepted.
		await fetchCohereModels(apiKey, fetchImpl);
	},

	streamChat: async (request: StreamRequest, transport?: StreamTransport) => {
		if (!transport) {
			throw new ProviderError("unknown", "No network transport available.");
		}
		try {
			await runCohereStream(request, 4096, transport);
		} catch (error) {
			throw toProviderError(error, "Cohere");
		}
	},

	quickComplete: async (request, transport?: StreamTransport) => {
		if (!transport) {
			throw new ProviderError("unknown", "No network transport available.");
		}
		const { apiKey, model, messages, maxTokens } = request;
		let response: Response;
		try {
			response = await postChat(apiKey, model, messages, maxTokens, false);
		} catch (error) {
			throw toProviderError(error, "Cohere");
		}
		if (!response.ok) {
			const text = await response.text().catch(() => "");
			throw mapHttpError(response.status, text, "Cohere");
		}
		const json = (await response.json()) as {
			message?: { content?: { type?: string; text?: string }[] };
		};
		const blocks = json.message?.content ?? [];
		return blocks
			.filter((b) => b.type === "text" && typeof b.text === "string")
			.map((b) => b.text as string)
			.join("");
	},
};
