/**
 * BYOK provider contracts.
 *
 * A ModelProvider talks directly to a model vendor's HTTP API using the
 * user's own API key. Keys live in expo-secure-store and are passed to the
 * provider on each call; they are never persisted anywhere else and never
 * sent to any other host.
 *
 * Streaming uses XMLHttpRequest under the hood (React Native's fetch has no
 * streaming body access), but that plumbing is injected so the parsing and
 * error mapping stay pure and unit-testable.
 */

export type ProviderId =
	| "anthropic"
	| "openai"
	| "node"
	| "openrouter"
	| "opencode"
	| "xai"
	| "gemini"
	| "deepseek"
	| "mistral"
	| "groq"
	| "together"
	| "cohere"
	| "custom";

export interface ModelInfo {
	id: string;
	label: string;
	blurb: string;
	capabilities?: ModelCapabilities;
}

/**
 * Capability metadata for a model entry. Every field is optional and must
 * stay unset when the discovery source does not report it: an unknown
 * capability is rendered as unknown, never guessed. Filled in from live
 * catalogs where the provider exposes the data (OpenRouter is the richest
 * source today); static fallbacks carry only `source: "static"`.
 */
export interface ModelCapabilities {
	/** Wire protocol the model entry is known to speak. */
	protocol?: "chat-completions" | "responses" | "messages" | "native";
	/** Context window in tokens, when the catalog reports it. */
	contextWindow?: number;
	/** Max output tokens, when the catalog reports it. */
	maxOutputTokens?: number;
	/** True when the catalog reports image input. */
	vision?: boolean;
	/** True when the catalog reports tool/function calling. */
	tools?: boolean;
	/** True when this adapter can stream the model. */
	streaming?: boolean;
	/** Where this entry came from: a live catalog or a static fallback. */
	source?: "live" | "static";
}

export interface ProviderMessage {
	role: "system" | "user" | "assistant";
	content: string;
}

export type StreamEvent =
	| { type: "delta"; text: string }
	| { type: "done"; stopReason?: string };

export interface StreamRequest {
	/** Raw API key. Never logged, never stored by the provider layer. */
	apiKey: string;
	model: string;
	messages: ProviderMessage[];
	signal?: AbortSignal;
	onEvent: (event: StreamEvent) => void;
}

/**
 * Minimal byte-source abstraction over XMLHttpRequest-style progressive
 * reads. `onChunk` receives the full responseText seen so far; the adapter
 * diffs it internally.
 */
export interface StreamTransport {
	postStream(
		url: string,
		init: {
			headers: Record<string, string>;
			body: string;
			signal?: AbortSignal;
			onChunk: (fullText: string) => void;
		},
	): Promise<{ status: number; finalText: string }>;
}

export interface ModelProvider {
	id: ProviderId;
	label: string;
	models: ModelInfo[];
	defaultModel: string;
	/** Cheap call that proves the key works. Throws ProviderError. */
	validateKey: (apiKey: string, fetchImpl?: FetchLike) => Promise<void>;
	/**
	 * Fetch the live model catalog (e.g. OpenRouter's /models, models.dev).
	 * When present, the UI prefers this over the static `models` list and
	 * caches the result. Implementations must throw ProviderError on
	 * failure; callers fall back to the static `models` list.
	 */
	listModels?: (apiKey: string, fetchImpl?: FetchLike) => Promise<ModelInfo[]>;
	streamChat: (request: StreamRequest, transport?: StreamTransport) => Promise<void>;
	/**
	 * Tiny non-streaming completion used for thread titles and smart
	 * replies. Default implementation reuses streamChat and concatenates.
	 */
	quickComplete?: (
		request: Omit<StreamRequest, "onEvent" | "signal"> & { maxTokens: number },
		transport?: StreamTransport,
	) => Promise<string>;
}

/** Minimal fetch shape so tests can inject a mock. */
export type FetchLike = (
	input: string,
	init?: { method?: string; headers?: Record<string, string>; body?: string },
) => Promise<{
	ok: boolean;
	status: number;
	text: () => Promise<string>;
	json: () => Promise<unknown>;
}>;
