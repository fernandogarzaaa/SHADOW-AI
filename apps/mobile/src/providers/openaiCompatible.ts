/**
 * Config-driven factory for OpenAI-compatible providers.
 *
 * xAI, DeepSeek, Mistral, Groq, Together AI, and Google's Gemini
 * OpenAI-compat shim all speak the same wire protocol: Bearer auth,
 * POST {base}/chat/completions, OpenAI-style SSE. One factory covers them;
 * only Cohere (and Anthropic) need native adapters.
 *
 * Each config carries everything that differs: base URLs, how to validate
 * the key, how to read the model catalog, and the static fallback list
 * shown when discovery fails.
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
	ProviderId,
	StreamRequest,
	StreamTransport,
} from "./types";

export interface OpenAICompatConfig {
	id: ProviderId;
	label: string;
	/** Base URL for chat, e.g. https://api.x.ai/v1 */
	chatBaseUrl: string;
	chatPath?: string;
	/** Full URL of the model catalog, e.g. https://api.x.ai/v1/models */
	modelsUrl: string;
	/** Extra headers for the catalog call (Gemini needs x-goog-api-key). */
	modelsHeaders?: (apiKey: string) => Record<string, string>;
	/** How to prove a key works. Defaults to the catalog call. */
	validate?:
		| { kind: "models" }
		| { kind: "endpoint"; path: string };
	/** Pull raw entries out of the catalog JSON. Default: json.data ?? [] */
	extractEntries?: (json: unknown) => Record<string, unknown>[];
	/** Map one raw entry to a ModelInfo (null drops it). Default: OpenAI-style. */
	mapEntry?: (entry: Record<string, unknown>) => ModelInfo | null;
	/** Rewrite a catalog model id before sending it to chat. */
	toChatModelId?: (id: string) => string;
	staticModels: ModelInfo[];
	defaultModel: string;
}

function defaultMapEntry(entry: Record<string, unknown>): ModelInfo | null {
	const id = entry["id"];
	if (typeof id !== "string" || id.length === 0) {
		return null;
	}
	const name = entry["name"];
	return {
		id,
		label: typeof name === "string" && name.length > 0 ? name : id,
		blurb: "OpenAI-compatible",
		capabilities: { protocol: "chat-completions", source: "live" },
	};
}

function bearerHeaders(apiKey: string): Record<string, string> {
	return {
		authorization: `Bearer ${apiKey}`,
		"content-type": "application/json",
	};
}

/** Exported for unit tests: fetch + map the catalog with an injected fetch. */
export async function fetchCompatModels(
	config: OpenAICompatConfig,
	apiKey: string,
	fetchImpl?: FetchLike,
): Promise<ModelInfo[]> {
	const runFetch: FetchLike =
		fetchImpl ?? (globalThis.fetch as unknown as FetchLike);
	const headers = config.modelsHeaders
		? { ...config.modelsHeaders(apiKey), "content-type": "application/json" }
		: bearerHeaders(apiKey);
	let response;
	try {
		response = await runFetch(config.modelsUrl, { method: "GET", headers });
	} catch (error) {
		throw toProviderError(error, config.label);
	}
	if (!response.ok) {
		const text = await response.text().catch(() => "");
		throw mapHttpError(response.status, text, config.label);
	}
	const json = (await response.json()) as unknown;
	const extract = config.extractEntries ?? ((j) => {
		const data = (j as { data?: unknown })?.data;
		return Array.isArray(data) ? (data as Record<string, unknown>[]) : [];
	});
	const map = config.mapEntry ?? defaultMapEntry;
	const models: ModelInfo[] = [];
	for (const entry of extract(json)) {
		const info = map(entry);
		if (info) {
			models.push(info);
		}
	}
	if (models.length === 0) {
		throw new ProviderError("server", `${config.label} returned no models.`);
	}
	return models;
}

/** Exported for unit tests: runs a stream against an injected transport. */
export async function runCompatStream(
	config: OpenAICompatConfig,
	request: StreamRequest,
	maxTokens: number,
	transport: StreamTransport,
): Promise<void> {
	const { apiKey, model, messages, signal, onEvent } = request;
	const chatModel = config.toChatModelId ? config.toChatModelId(model) : model;
	const body = JSON.stringify(buildOpenAIBody(chatModel, messages, maxTokens, true));
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

	const chatPath = config.chatPath ?? "/chat/completions";
	const { status, finalText } = await transport.postStream(
		`${config.chatBaseUrl}${chatPath}`,
		{
			headers: bearerHeaders(apiKey),
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
		throw mapHttpError(status, finalText, config.label);
	}
	for (const payload of parser.flush()) {
		emit(payload);
	}
	if (!done) {
		onEvent({ type: "done" });
	}
}

export function makeOpenAICompatibleProvider(
	config: OpenAICompatConfig,
): ModelProvider {
	const validate = config.validate ?? { kind: "models" as const };

	return {
		id: config.id,
		label: config.label,
		models: config.staticModels,
		defaultModel: config.defaultModel,

		listModels: (apiKey, fetchImpl) =>
			fetchCompatModels(config, apiKey, fetchImpl),

		validateKey: async (apiKey: string, fetchImpl?: FetchLike) => {
			if (validate.kind === "endpoint") {
				const runFetch: FetchLike =
					fetchImpl ?? (globalThis.fetch as unknown as FetchLike);
				let response;
				try {
					response = await runFetch(
						`${config.chatBaseUrl}${validate.path}`,
						{ method: "GET", headers: bearerHeaders(apiKey) },
					);
				} catch (error) {
					throw toProviderError(error, config.label);
				}
				if (!response.ok) {
					const text = await response.text().catch(() => "");
					throw mapHttpError(response.status, text, config.label);
				}
				return;
			}
			// Default: the catalog call doubles as the health check. A 200
			// means the key is accepted; the model list itself is discarded.
			await fetchCompatModels(config, apiKey, fetchImpl);
		},

		streamChat: async (request: StreamRequest, transport?: StreamTransport) => {
			if (!transport) {
				throw new ProviderError("unknown", "No network transport available.");
			}
			try {
				await runCompatStream(config, request, 4096, transport);
			} catch (error) {
				throw toProviderError(error, config.label);
			}
		},

		quickComplete: async (request, transport?: StreamTransport) => {
			if (!transport) {
				throw new ProviderError("unknown", "No network transport available.");
			}
			let text = "";
			await runCompatStream(
				config,
				{ ...request, onEvent: (e) => { if (e.type === "delta") text += e.text; } },
				request.maxTokens,
				transport,
			);
			return text;
		},
	};
}
