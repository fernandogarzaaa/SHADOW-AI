/**
 * BYOK provider registry.
 */

import { anthropicProvider } from "./anthropic";
import { cohereProvider } from "./cohere";
import {
	deepseekProvider,
	geminiProvider,
	groqProvider,
	mistralProvider,
	togetherProvider,
	xaiProvider,
} from "./compatProviders";
import { customProvider } from "./custom";
import { nodeProvider } from "./node";
import { opencodeProvider } from "./opencode";
import { openaiProvider } from "./openai";
import { openrouterProvider } from "./openrouter";
import type { ModelProvider, ProviderId } from "./types";

export const PROVIDERS: Record<ProviderId, ModelProvider> = {
	anthropic: anthropicProvider,
	openai: openaiProvider,
	openrouter: openrouterProvider,
	opencode: opencodeProvider,
	xai: xaiProvider,
	gemini: geminiProvider,
	deepseek: deepseekProvider,
	mistral: mistralProvider,
	groq: groqProvider,
	together: togetherProvider,
	cohere: cohereProvider,
	custom: customProvider,
	node: nodeProvider,
};

/** Providers that take a user-supplied API key (onboarding + settings). */
export const KEY_PROVIDERS: ProviderId[] = [
	"anthropic",
	"openai",
	"openrouter",
	"opencode",
	"xai",
	"gemini",
	"deepseek",
	"mistral",
	"groq",
	"together",
	"cohere",
	"custom",
];

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
export { getModels, clearModelCache } from "./modelCatalog";
export type { CatalogResult } from "./modelCatalog";
export { getCustomBaseUrl, setCustomBaseUrl } from "./custom";
