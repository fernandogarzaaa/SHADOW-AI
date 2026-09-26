/**
 * OpenCode Zen adapter (BYOK, streaming).
 *
 * Zen is the OpenCode team's pay-as-you-go model gateway. Chat goes through
 * POST /zen/v1/chat/completions with an OpenAI-compatible body and SSE
 * stream; the error envelope is Zen-native
 * ({"type":"error","error":{"type","message"}}). The model catalog is public
 * (GET /zen/v1/models, no key needed) and is the source of the selectable
 * model list, so new Zen models appear without an app update.
 *
 * Two honest limitations, both surfaced to the user rather than hidden:
 * - Zen serves some models on non-OpenAI dialects (/responses, /messages).
 *   This adapter speaks /chat/completions; anything else fails loudly with
 *   a clear message instead of guessing.
 * - Zen has no dedicated key-check endpoint, so key validation makes one
 *   minimal non-streaming call (max_tokens: 1) against a model known to
 *   speak /chat/completions. Only statuses that positively prove the key
 *   was accepted count as valid: 2xx, 429 (rate-limited means accepted),
 *   and the tier-gated 403 FreeTierError. A 401 means a bad key; a 400 or
 *   5xx means Zen could not verify the key, and is reported as such
 *   instead of being misread as valid.
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

const API_BASE = "https://opencode.ai/zen/v1";

/**
 * Model ids known to speak /chat/completions on Zen. The live catalog may
 * list models that require /responses or /messages; the validation probe
 * must never pick one of those, or a good key would look broken.
 */
const CHAT_SAFE_MODELS = ["claude-sonnet-5", "gemini-3.6-flash"];

function baseHeaders(apiKey: string): Record<string, string> {
	return {
		authorization: `Bearer ${apiKey}`,
		"content-type": "application/json",
	};
}

interface ZenModelEntry {
	id?: string;
}

/** "claude-sonnet-5" -> "Claude Sonnet 5". Pure: unit-tested. */
export function prettifyZenId(id: string): string {
	return id
		.split(/[-_]/)
		.map((word) => (word ? word.charAt(0).toUpperCase() + word.slice(1) : word))
		.join(" ");
}

/** Map one Zen /models entry to a ModelInfo. Pure: unit-tested. */
export function toModelInfo(entry: ZenModelEntry): ModelInfo | null {
	if (!entry.id) {
		return null;
	}
	return {
		id: entry.id,
		label: prettifyZenId(entry.id),
		blurb: "via OpenCode Zen",
		// Protocol is deliberately left unset: Zen serves models on several
		// dialects and its catalog does not report which. The adapter speaks
		// /chat/completions and fails loudly on anything else.
		capabilities: { source: "live" },
	};
}

/**
 * Fetch the live Zen catalog. Public endpoint; the key is accepted for
 * API-shape symmetry but not required. Pure-ish: unit-tested with an
 * injected fetch.
 */
export async function fetchZenModels(
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
		throw toProviderError(error, "OpenCode Zen");
	}
	if (!response.ok) {
		const text = await response.text().catch(() => "");
		throw mapHttpError(response.status, text, "OpenCode Zen");
	}
	const data = (await response.json()) as { data?: ZenModelEntry[] };
	const models: ModelInfo[] = [];
	for (const entry of data.data ?? []) {
		const info = toModelInfo(entry);
		if (info) {
			models.push(info);
		}
	}
	if (models.length === 0) {
		throw new ProviderError("server", "OpenCode Zen returned no models.");
	}
	return models;
}

/** Exported for unit tests: runs a stream against an injected transport. */
export async function runZenStream(
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
		throw mapHttpError(status, finalText, "OpenCode Zen");
	}
	for (const payload of parser.flush()) {
		emit(payload);
	}
	if (!done) {
		onEvent({ type: "done" });
	}
}

export const opencodeProvider: ModelProvider = {
	id: "opencode",
	label: "OpenCode Zen",
	// Static fallback shown when the live catalog cannot be reached.
	models: [
		{
			id: "claude-sonnet-5",
			label: "Claude Sonnet 5",
			blurb: "Balanced speed and intelligence via Zen.",
		},
		{
			id: "gemini-3.6-flash",
			label: "Gemini 3.6 Flash",
			blurb: "Fast and cheap via Zen.",
		},
	],
	defaultModel: "claude-sonnet-5",

	listModels: async (_apiKey, fetchImpl) => fetchZenModels(fetchImpl),

	validateKey: async (apiKey: string, fetchImpl?: FetchLike) => {
		const runFetch: FetchLike =
			fetchImpl ?? (globalThis.fetch as unknown as FetchLike);
		// Zen has no key-check endpoint. Probe with one minimal non-streaming
		// call (max_tokens: 1) against a chat-completions-safe model: prefer
		// a known-safe id that is also on the live roster; otherwise probe
		// the first known-safe id. Costs ~1 token on a valid key.
		let probeModel = CHAT_SAFE_MODELS[0];
		try {
			const models = await fetchZenModels(runFetch);
			const safe = models.find((m) => CHAT_SAFE_MODELS.includes(m.id));
			if (safe) {
				probeModel = safe.id;
			}
		} catch {
			// No catalog (offline or blocked); probe with the static id.
		}
		let response;
		try {
			response = await runFetch(`${API_BASE}/chat/completions`, {
				method: "POST",
				headers: baseHeaders(apiKey),
				body: JSON.stringify(
					buildOpenAIBody(probeModel, [{ role: "user", content: "hi" }], 1, false),
				),
			});
		} catch (error) {
			throw toProviderError(error, "OpenCode Zen");
		}
		const text = await response.text().catch(() => "");
		if (response.status === 401) {
			throw mapHttpError(401, text, "OpenCode Zen");
		}
		if (response.status === 403) {
			// A tier-gated key (FreeTierError) is still a valid key.
			if (text.toLowerCase().includes("freetier")) {
				return;
			}
			throw mapHttpError(403, text, "OpenCode Zen");
		}
		// 2xx: the call worked. 429: rate-limited, which still proves the
		// key was accepted.
		if (response.ok || response.status === 429) {
			return;
		}
		// Anything else (400, 404, 5xx): Zen did not confirm the key. Fail
		// loud instead of misreading it as valid.
		throw new ProviderError(
			"server",
			`OpenCode Zen could not verify the key (HTTP ${response.status}). Check the key and try again.`,
		);
	},

	streamChat: async (request: StreamRequest, transport?: StreamTransport) => {
		if (!transport) {
			throw new ProviderError("unknown", "No network transport available.");
		}
		try {
			await runZenStream(request, 4096, transport);
		} catch (error) {
			throw toProviderError(error, "OpenCode Zen");
		}
	},

	quickComplete: async (request, transport?: StreamTransport) => {
		if (!transport) {
			throw new ProviderError("unknown", "No network transport available.");
		}
		let text = "";
		await runZenStream(
			{ ...request, onEvent: (e) => { if (e.type === "delta") text += e.text; } },
			request.maxTokens,
			transport,
		);
		return text;
	},
};
