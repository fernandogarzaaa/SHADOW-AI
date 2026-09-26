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

export type ProviderId = "anthropic" | "openai" | "node";

export interface ModelInfo {
	id: string;
	label: string;
	blurb: string;
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
