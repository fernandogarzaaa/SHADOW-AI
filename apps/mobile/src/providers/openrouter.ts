/**
 * OpenRouter adapter (BYOK, streaming).
 *
 * OpenRouter exposes an OpenAI-compatible API, so chat completions reuse
 * the OpenAI request builder and SSE parser. The model catalog is dynamic:
 * GET /api/v1/models is public (no key needed) and lists every model on
 * OpenRouter, so the app always shows current models without an app update.
 *
 * Docs: https://openrouter.ai/docs
 */

import {
	ProviderError,
	mapHttpError,
	toProviderError,
} from "./errors";
import { buildOpenAIBody, parseOpenAIPayload } from "./openai";
import { IncrementalSseParser } from "./sse";
import type {
	FetchLike,
	ModelInfo,
	ModelProvider,
	StreamRequest,
	StreamTransport,
} from "./types";

const API_BASE = "https://openrouter.ai/api/v1";

function baseHeaders(apiKey: string): Record<string, string> {
	return {
		authorization: `Bearer ${apiKey}`,
		"content-type": "application/json",
		// OpenRouter asks apps to identify themselves for analytics/rate limits.
		"HTTP-Referer": "https://shadow.app",
		"X-Title": "SHADOW",
	};
}

interface OpenRouterModelEntry {
	id?: string;
	name?: string;
	context_length?: number;
	architecture?: {
		input_modalities?: string[];
		output_modalities?: string[];
	};
}

/** Map one OpenRouter /models entry to a ModelInfo. Pure: unit-tested. */
export function toModelInfo(entry: OpenRouterModelEntry): ModelInfo | null {
	if (!entry.id) {
		return null;
	}
	// Chat UI only: skip models that cannot produce text.
	const out = entry.architecture?.output_modalities;
	if (out && out.length > 0 && !out.includes("text")) {
		return null;
	}
	const ctx = entry.context_length;
	const input = entry.architecture?.input_modalities ?? [];
	const vision = input.includes("image");
	return {
		id: entry.id,
		label: entry.name || entry.id,
		blurb:
			typeof ctx === "number" && ctx > 0
				? `${Math.round(ctx / 1000)}k context`
				: "OpenRouter",
		capabilities: {
			protocol: "chat-completions",
			source: "live",
			...(typeof ctx === "number" && ctx > 0 ? { contextWindow: ctx } : {}),
			...(vision ? { vision: true } : {}),
		},
	};
}

/**
 * Fetch the live OpenRouter catalog. The endpoint is public; the key is
 * accepted for API-shape symmetry but not required. Pure-ish: unit-tested
 * with an injected fetch.
 */
export async function fetchOpenRouterModels(
	_fetchImpl?: FetchLike,
): Promise<ModelInfo[]> {
	const runFetch: FetchLike =
		_fetchImpl ?? (globalThis.fetch as unknown as FetchLike);
	let response;
	try {
		response = await runFetch(`${API_BASE}/models`, {
			method: "GET",
			headers: { "content-type": "application/json" },
		});
	} catch (error) {
		throw toProviderError(error, "OpenRouter");
	}
	if (!response.ok) {
		const text = await response.text().catch(() => "");
		throw mapHttpError(response.status, text, "OpenRouter");
	}
	const data = (await response.json()) as {
		data?: OpenRouterModelEntry[];
	};
	const models: ModelInfo[] = [];
	for (const entry of data.data ?? []) {
		const info = toModelInfo(entry);
		if (info) {
			models.push(info);
		}
	}
	if (models.length === 0) {
		throw new ProviderError("server", "OpenRouter returned no models.");
	}
	return models;
}

/** Exported for unit tests: runs a stream against an injected transport. */
export async function runOpenRouterStream(
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
		if (!events) {
			return;
		}
		for (const event of events) {
			if (event.type === "done") {
				done = true;
			} else {
				onEvent(event);
			}
		}
	};

	const { status, finalText } = await transport.postStream(
		`${API_BASE}/chat/completions`,
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
		throw mapHttpError(status, finalText, "OpenRouter");
	}
	for (const payload of parser.flush()) {
		emit(payload);
	}
	if (!done) {
		onEvent({ type: "done" });
	}
}

export const openrouterProvider: ModelProvider = {
	id: "openrouter",
	label: "OpenRouter",
	// Static fallback shown when the live catalog cannot be reached.
	models: [
		{
			id: "openrouter/auto",
			label: "Auto Router",
			blurb: "Routes each prompt to a strong model automatically.",
		},
		{
			id: "anthropic/claude-sonnet-5",
			label: "Sonnet 5",
			blurb: "Balanced speed and intelligence via OpenRouter.",
		},
		{
			id: "openai/gpt-5.6",
			label: "GPT-5.6",
			blurb: "Strong all-rounder via OpenRouter.",
		},
	],
	defaultModel: "openrouter/auto",

	listModels: async (_apiKey, fetchImpl) => fetchOpenRouterModels(fetchImpl),

	validateKey: async (apiKey: string, fetchImpl?: FetchLike) => {
		const runFetch: FetchLike =
			fetchImpl ?? (globalThis.fetch as unknown as FetchLike);
		let response;
		try {
			// Official key health check: cheap, non-billable.
			// Docs: https://openrouter.ai/docs/api-reference/limits
			response = await runFetch(`${API_BASE}/key`, {
				method: "GET",
				headers: baseHeaders(apiKey),
			});
		} catch (error) {
			throw toProviderError(error, "OpenRouter");
		}
		if (!response.ok) {
			const text = await response.text().catch(() => "");
			throw mapHttpError(response.status, text, "OpenRouter");
		}
	},

	streamChat: async (request: StreamRequest, transport?: StreamTransport) => {
		if (!transport) {
			throw new ProviderError("unknown", "No network transport available.");
		}
		try {
			await runOpenRouterStream(request, 4096, transport);
		} catch (error) {
			throw toProviderError(error, "OpenRouter");
		}
	},

	quickComplete: async (request, transport?: StreamTransport) => {
		if (!transport) {
			throw new ProviderError("unknown", "No network transport available.");
		}
		let text = "";
		await runOpenRouterStream(
			{ ...request, onEvent: (e) => { if (e.type === "delta") text += e.text; } },
			request.maxTokens,
			transport,
		);
		return text;
	},
};
