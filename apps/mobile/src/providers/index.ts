/**
 * BYOK provider registry.
 */

import { anthropicProvider } from "./anthropic";
import { nodeProvider } from "./node";
import { openaiProvider } from "./openai";
import type { ModelProvider, ProviderId } from "./types";

export const PROVIDERS: Record<ProviderId, ModelProvider> = {
	anthropic: anthropicProvider,
	openai: openaiProvider,
	node: nodeProvider,
};

/** Providers that take a user-supplied API key (onboarding + settings). */
export const KEY_PROVIDERS: ProviderId[] = ["anthropic", "openai"];

export const DEFAULT_PROVIDER: ProviderId = "anthropic";

export function getProvider(id: ProviderId): ModelProvider {
	return PROVIDERS[id];
}

export function getDefaultModel(providerId: ProviderId): string {
	return PROVIDERS[providerId].defaultModel;
}

export * from "./types";
export { ProviderError, mapHttpError, toProviderError } from "./errors";
export type { ProviderErrorCode } from "./errors";
export {
	getProviderKey,
	setProviderKey,
	deleteProviderKey,
	hasProviderKey,
	clearAllProviderKeys,
	KeyStoreError,
} from "./keyStore";
export { xhrStreamTransport } from "./xhrTransport";
