/**
 * Custom OpenAI-compatible endpoint (BYOK, streaming).
 *
 * The universal escape hatch: the user enters any OpenAI-compatible base
 * URL (vLLM, LM Studio, Ollama's /v1, LiteLLM proxy, a self-hosted
 * gateway) plus a key and a model id. Chat, streaming, and the model
 * catalog all reuse the shared OpenAI-compatible implementation.
 *
 * The base URL lives in SecureStore next to the key. It is resolved at
 * call time so the provider object stays a plain ModelProvider.
 */

import {
	fetchCompatModels,
	runCompatStream,
	type OpenAICompatConfig,
} from "./openaiCompatible";
import { ProviderError, toProviderError } from "./errors";
import type {
	ModelInfo,
	ModelProvider,
	StreamRequest,
	StreamTransport,
} from "./types";

const STORE_KEY = "shadow.custom.baseUrl";

/** Read the stored base URL, or null when the user has not set one. */
export async function getCustomBaseUrl(): Promise<string | null> {
	// Dynamic import: keeps this module importable from plain node tests,
	// which never call this function.
	const SecureStore = await import("expo-secure-store");
	return SecureStore.getItemAsync(STORE_KEY);
}

/** Persist the base URL. Throws ProviderError on a malformed URL. */
export async function setCustomBaseUrl(rawUrl: string): Promise<void> {
	const baseUrl = normalizeBaseUrl(rawUrl);
	const SecureStore = await import("expo-secure-store");
	await SecureStore.setItemAsync(STORE_KEY, baseUrl);
}

/** Strip trailing slashes; require an http(s) URL. Pure: unit-tested. */
export function normalizeBaseUrl(rawUrl: string): string {
	const trimmed = rawUrl.trim().replace(/\/+$/, "");
	if (!/^https?:\/\/.+/.test(trimmed)) {
		throw new ProviderError(
			"bad_request",
			"Enter a valid base URL starting with http:// or https://.",
		);
	}
	return trimmed;
}

function configFor(baseUrl: string): OpenAICompatConfig {
	return {
		id: "custom",
		label: "Custom Endpoint",
		chatBaseUrl: baseUrl,
		modelsUrl: `${baseUrl}/models`,
		// No static list: the model id is user-defined. The manual input
		// in the model sheet is the source of truth.
		staticModels: [],
		defaultModel: "",
	};
}

async function requireBaseUrl(): Promise<string> {
	const baseUrl = await getCustomBaseUrl();
	if (!baseUrl) {
		throw new ProviderError(
			"bad_request",
			"Set a base URL for the custom endpoint first.",
		);
	}
	return baseUrl;
}

/**
 * Build a custom-endpoint provider around an injected base-URL getter.
 * The shipped instance uses SecureStore; tests inject an in-memory getter.
 */
export function createCustomProvider(
	getBaseUrl: () => Promise<string | null>,
): ModelProvider {
	async function configNow(): Promise<OpenAICompatConfig> {
		const baseUrl = await getBaseUrl();
		if (!baseUrl) {
			throw new ProviderError(
				"bad_request",
				"Set a base URL for the custom endpoint first.",
			);
		}
		return configFor(baseUrl);
	}

	return {
		id: "custom",
		label: "Custom Endpoint",
		models: [] as ModelInfo[],
		defaultModel: "",

		listModels: async (apiKey, fetchImpl) => {
			const live = await configNow();
			try {
				return await fetchCompatModels(live, apiKey, fetchImpl);
			} catch (error) {
				// No static list to fall back to; surface the real error.
				throw toProviderError(error, "Custom Endpoint");
			}
		},

		validateKey: async (apiKey: string, fetchImpl) => {
			const live = await configNow();
			// The catalog call doubles as the health check.
			await fetchCompatModels(live, apiKey, fetchImpl);
		},

		streamChat: async (request: StreamRequest, transport?: StreamTransport) => {
			if (!transport) {
				throw new ProviderError("unknown", "No network transport available.");
			}
			const live = await configNow();
			try {
				await runCompatStream(live, request, 4096, transport);
			} catch (error) {
				throw toProviderError(error, "Custom Endpoint");
			}
		},

		quickComplete: async (request, transport?: StreamTransport) => {
			if (!transport) {
				throw new ProviderError("unknown", "No network transport available.");
			}
			const live = await configNow();
			let text = "";
			try {
				await runCompatStream(
					live,
					{
						...request,
						onEvent: (e) => {
							if (e.type === "delta") text += e.text;
						},
					},
					request.maxTokens,
					transport,
				);
			} catch (error) {
				throw toProviderError(error, "Custom Endpoint");
			}
			return text;
		},
	};
}

export const customProvider: ModelProvider = createCustomProvider(getCustomBaseUrl);
