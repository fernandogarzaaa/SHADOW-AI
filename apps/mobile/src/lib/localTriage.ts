/**
 * On-device LLM triage via expo-local-llm (Apple Foundation Models on
 * iOS 26+, Gemini Nano on Android). Zero-cost, offline-capable micro-tasks
 * with silent cloud fallback.
 *
 * Design notes:
 * - The native module is absent in Expo Go and on ineligible devices, so
 *   the package is loaded lazily and every entry point degrades to null
 *   instead of throwing. The caller falls back to the user's configured
 *   cloud provider, which keeps behavior identical to before on devices
 *   without on-device AI.
 * - Tasks are deliberately small (titles, smart replies, short summaries).
 *   On-device models have small context windows; agentic tool use stays
 *   on the cloud providers.
 * - No API key is involved: the OS provides the model, so nothing leaves
 *   the device for these tasks.
 */

import type * as LocalLLM from "expo-local-llm";

type LocalLLMModule = typeof LocalLLM | null;

let cachedModule: LocalLLMModule | undefined;

async function loadModule(): Promise<LocalLLMModule> {
	if (cachedModule !== undefined) {
		return cachedModule;
	}
	try {
		cachedModule = (await import("expo-local-llm")) as LocalLLMModule;
	} catch {
		cachedModule = null;
	}
	return cachedModule;
}

export type LocalLLMAvailability =
	| { available: true }
	| { available: false; reason: string };

/**
 * Check whether on-device inference can run right now. Never throws;
 * returns a reason when unavailable (e.g. "notEligible", "notEnabled",
 * "notReady", "downloadRequired", "unknown", "not_installed").
 */
export async function getLocalLLMAvailability(): Promise<LocalLLMAvailability> {
	const mod = await loadModule();
	if (!mod) {
		return { available: false, reason: "not_installed" };
	}
	try {
		const nativeModule = mod.ExpoLocalLlmModule;
		if (!nativeModule) {
			return { available: false, reason: "not_installed" };
		}
		const availability = await nativeModule.getAvailability();
		if (availability === "available") {
			return { available: true };
		}
		return { available: false, reason: availability };
	} catch {
		return { available: false, reason: "unknown" };
	}
}

/** Prompt builders: single source of truth for local and cloud paths. */
export function threadTitlePrompt(firstUserText: string): string {
	return `Give this chat a very short title (max 5 words, no quotes, no punctuation at the end). First message: ${firstUserText.slice(0, 300)}`;
}

export function smartRepliesPrompt(assistantText: string): string {
	return `Suggest 3 short follow-up questions or replies the user might send next. Reply with only the 3 suggestions, one per line, no numbering, no quotes. Keep each under 8 words.\n\nAssistant just said: ${assistantText.slice(0, 600)}`;
}

export function summarizePrompt(text: string): string {
	return `Summarize the following in 2-3 short sentences, no preamble:\n\n${text.slice(0, 2000)}`;
}

/**
 * Run one micro-task on-device. Returns the trimmed text, or null when
 * on-device inference is unavailable or fails. Never throws.
 */
export async function runLocalTask(
	prompt: string,
	maxTokens: number,
): Promise<string | null> {
	const status = await getLocalLLMAvailability();
	if (!status.available) {
		return null;
	}
	const mod = await loadModule();
	if (!mod) {
		return null;
	}
	try {
		const text = await mod.generate(prompt, {
			options: { maxTokens, temperature: 0.3 },
		});
		const trimmed = (text ?? "").trim();
		return trimmed.length > 0 ? trimmed : null;
	} catch {
		return null;
	}
}

export type LocalRunner = (
	prompt: string,
	maxTokens: number,
) => Promise<string | null>;

/**
 * Local-first quick completion: try on-device, fall back to the caller's
 * cloud function. Returns null only when both fail. Never throws.
 *
 * `localRunner` is injectable for tests; production callers omit it.
 */
export async function quickCompleteLocalFirst(
	prompt: string,
	maxTokens: number,
	cloud: () => Promise<string | null>,
	localRunner: LocalRunner = runLocalTask,
): Promise<string | null> {
	try {
		const local = await localRunner(prompt, maxTokens);
		if (local) {
			return local;
		}
	} catch {
		// Fall through to cloud.
	}
	try {
		return await cloud();
	} catch {
		return null;
	}
}
