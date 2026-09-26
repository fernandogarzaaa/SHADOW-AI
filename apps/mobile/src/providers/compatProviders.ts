/**
 * Curated OpenAI-compatible providers, built on the shared factory in
 * ./openaiCompatible. Each entry carries its own base URL, key-validation
 * strategy, catalog mapping, and static fallback list.
 *
 * Static lists are fallbacks only: whenever the network is reachable the
 * app shows the provider's live catalog instead. Model ids below were
 * current at the time of writing; the live catalog corrects them.
 */

import {
	makeOpenAICompatibleProvider,
	type OpenAICompatConfig,
} from "./openaiCompatible";
import type { ModelInfo, ModelProvider } from "./types";

const xaiConfig: OpenAICompatConfig = {
	id: "xai",
	label: "xAI",
	chatBaseUrl: "https://api.x.ai/v1",
	modelsUrl: "https://api.x.ai/v1/models",
	// Documented key health check (docs.x.ai REST reference).
	validate: { kind: "endpoint", path: "/api-key" },
	staticModels: [
		{ id: "grok-4.6", label: "Grok 4.6", blurb: "Flagship reasoning model." },
		{ id: "grok-4.5", label: "Grok 4.5", blurb: "Fast flagship chat." },
	],
	defaultModel: "grok-4.6",
};

const geminiConfig: OpenAICompatConfig = {
	id: "gemini",
	label: "Google Gemini",
	// Official OpenAI-compat shim; reuses the OpenAI transport as-is.
	chatBaseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
	modelsUrl: "https://generativelanguage.googleapis.com/v1beta/models",
	// The native models API takes the AI Studio key via x-goog-api-key.
	modelsHeaders: (apiKey) => ({ "x-goog-api-key": apiKey }),
	extractEntries: (json) => {
		const root = json as {
			models?: Record<string, unknown>[];
			nextPageToken?: string;
		};
		return Array.isArray(root?.models) ? root.models : [];
	},
	mapEntry: (entry) => {
		const name = entry["name"];
		const methods = entry["supportedGenerationMethods"];
		if (typeof name !== "string") {
			return null;
		}
		// Only models that can generate content are chattable.
		if (Array.isArray(methods) && !methods.includes("generateContent")) {
			return null;
		}
		const id = name.replace(/^models\//, "");
		return { id, label: id, blurb: "via Google AI" };
	},
	toChatModelId: (id) => id.replace(/^models\//, ""),
	staticModels: [
		{ id: "gemini-2.5-flash", label: "Gemini 2.5 Flash", blurb: "Fast and cheap." },
		{ id: "gemini-2.5-pro", label: "Gemini 2.5 Pro", blurb: "Strongest reasoning." },
	],
	defaultModel: "gemini-2.5-flash",
};

const deepseekConfig: OpenAICompatConfig = {
	id: "deepseek",
	label: "DeepSeek",
	chatBaseUrl: "https://api.deepseek.com/v1",
	modelsUrl: "https://api.deepseek.com/v1/models",
	staticModels: [
		{ id: "deepseek-chat", label: "DeepSeek V3", blurb: "General chat model." },
		{ id: "deepseek-reasoner", label: "DeepSeek R1", blurb: "Reasoning model." },
	],
	defaultModel: "deepseek-chat",
};

const mistralConfig: OpenAICompatConfig = {
	id: "mistral",
	label: "Mistral",
	chatBaseUrl: "https://api.mistral.ai/v1",
	modelsUrl: "https://api.mistral.ai/v1/models",
	mapEntry: (entry) => {
		const id = entry["id"];
		if (typeof id !== "string" || id.length === 0) {
			return null;
		}
		// Entries carry capabilities.completion_chat; drop embed/moderation.
		const caps = entry["capabilities"] as { completion_chat?: boolean } | undefined;
		if (caps && caps.completion_chat === false) {
			return null;
		}
		return { id, label: id, blurb: "via Mistral La Plateforme" };
	},
	staticModels: [
		{ id: "mistral-large-latest", label: "Mistral Large", blurb: "Flagship chat model." },
		{ id: "mistral-small-latest", label: "Mistral Small", blurb: "Fast and cheap." },
	],
	defaultModel: "mistral-large-latest",
};

const groqConfig: OpenAICompatConfig = {
	id: "groq",
	label: "Groq",
	chatBaseUrl: "https://api.groq.com/openai/v1",
	modelsUrl: "https://api.groq.com/openai/v1/models",
	mapEntry: (entry) => {
		const id = entry["id"];
		if (typeof id !== "string" || id.length === 0) {
			return null;
		}
		// Not chattable in this UI: audio and guard models.
		if (/whisper|tts|guard/i.test(id)) {
			return null;
		}
		return { id, label: id, blurb: "Fast inference on Groq" };
	},
	staticModels: [
		{
			id: "llama-3.3-70b-versatile",
			label: "Llama 3.3 70B",
			blurb: "Strong open-weight chat.",
		},
		{
			id: "llama-3.1-8b-instant",
			label: "Llama 3.1 8B",
			blurb: "Fastest responses.",
		},
	],
	defaultModel: "llama-3.3-70b-versatile",
};

const togetherConfig: OpenAICompatConfig = {
	id: "together",
	label: "Together AI",
	chatBaseUrl: "https://api.together.xyz/v1",
	modelsUrl: "https://api.together.xyz/v1/models",
	staticModels: [
		{
			id: "meta-llama/Llama-3.3-70B-Instruct-Turbo",
			label: "Llama 3.3 70B Turbo",
			blurb: "Strong open-weight chat.",
		},
		{
			id: "Qwen/Qwen2.5-72B-Instruct-Turbo",
			label: "Qwen 2.5 72B Turbo",
			blurb: "Strong multilingual chat.",
		},
	],
	defaultModel: "meta-llama/Llama-3.3-70B-Instruct-Turbo",
};

export const xaiProvider: ModelProvider = makeOpenAICompatibleProvider(xaiConfig);
export const geminiProvider: ModelProvider =
	makeOpenAICompatibleProvider(geminiConfig);
export const deepseekProvider: ModelProvider =
	makeOpenAICompatibleProvider(deepseekConfig);
export const mistralProvider: ModelProvider =
	makeOpenAICompatibleProvider(mistralConfig);
export const groqProvider: ModelProvider = makeOpenAICompatibleProvider(groqConfig);
export const togetherProvider: ModelProvider =
	makeOpenAICompatibleProvider(togetherConfig);

/** Exported for unit tests. */
export const compatConfigs: Record<string, OpenAICompatConfig> = {
	xai: xaiConfig,
	gemini: geminiConfig,
	deepseek: deepseekConfig,
	mistral: mistralConfig,
	groq: groqConfig,
	together: togetherConfig,
};

/** The static fallback lists, exported for unit tests. */
export function staticModelsOf(id: keyof typeof compatConfigs): ModelInfo[] {
	return compatConfigs[id].staticModels;
}
