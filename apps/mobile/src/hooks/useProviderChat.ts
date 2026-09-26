/**
 * Provider chat orchestration: send, stop, auto-title, smart replies.
 *
 * One in-flight stream at a time per hook instance. Streaming deltas are
 * appended to the store optimistically; finalization writes through to
 * AsyncStorage. Title generation and smart replies run as fire-and-forget
 * quick completions after the assistant message finalizes.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
	getProvider,
	getProviderKey,
	xhrStreamTransport,
	ProviderError,
	type ProviderMessage,
} from "@/providers";
import { useChatStore } from "@/stores/useChatStore";
import { buildProfilePrompt, useProfileStore } from "@/stores/useProfileStore";
import { useProviderStore } from "@/stores/useProviderStore";

const MAX_HISTORY_MESSAGES = 40;

function toProviderMessages(
	history: Array<{ role: "user" | "assistant"; text: string }>,
	systemPrompt: string,
): ProviderMessage[] {
	const messages: ProviderMessage[] = [];
	if (systemPrompt) {
		messages.push({ role: "system", content: systemPrompt });
	}
	for (const m of history.slice(-MAX_HISTORY_MESSAGES)) {
		messages.push({ role: m.role, content: m.text });
	}
	return messages;
}

function baseSystemPrompt(): string {
	const { agentName, tone } = useProfileStore.getState().profile;
	const name = agentName || "shadow";
	const toneLine =
		tone === "direct"
			? "Be concise and direct. Short answers, no small talk unless asked."
			: tone === "playful"
				? "Be warm with a light, playful touch. Keep it natural, never forced."
				: "Be helpful, direct, and warm. Calm and first-person, like a thoughtful friend.";
	return [
		`Your name is ${name}. You are a personal AI companion on the user's phone.`,
		toneLine,
		"Match the user's language.",
		"Format with short paragraphs and markdown when it helps; avoid walls of text.",
	].join(" ");
}

export interface UseProviderChat {
	/** True while a stream is in flight. */
	streaming: boolean;
	/** The id of the thread currently streaming, if any. */
	streamingThreadId: string | null;
	/** Last send failure, for inline display. */
	error: string | null;
	/** First-class agent state for the active thread. */
	agentState: AgentState;
	/** Provider label for the in-flight or last generation. */
	stateProviderLabel: string | null;
	/** Model id for the in-flight or last generation. */
	stateModelId: string | null;
	/** When the current generation started, for elapsed display. */
	stateStartedAt: number | null;
	/** Suggested follow-ups for the active thread. */
	smartReplies: string[];
	send: (threadId: string, text: string) => Promise<void>;
	/** Re-run the last turn without appending a duplicate user message. */
	retry: (threadId: string) => Promise<void>;
	stop: () => void;
	clearError: () => void;
	refreshSmartReplies: (threadId: string) => void;
}

/**
 * First-class agent states for chat. The full Personal Agent OS list is
 * idle, thinking, working, waiting, needs_approval, completed, error,
 * offline. Mapping in this BYOK chat surface:
 * - waiting: local setup before the request goes out (persisting the
 *   user message, reading the provider key from SecureStore). Genuine
 *   async work, not a spinner for its own sake.
 * - thinking: request in flight, no tokens yet.
 * - working: tokens streaming in.
 * - completed: the turn finished. Transient; falls back to idle.
 * - needs_approval: reserved for node-provider turns when the node
 *   signals it needs approval to continue. The node's ask_stream
 *   protocol emits no inline approval signal in this version, so the
 *   chat state machine never sets it; pending approvals live in the
 *   Approvals tab. The type and the state line UI support it so the
 *   model stays complete.
 * - error / offline / idle as before.
 */
export type AgentState =
	| "idle"
	| "thinking"
	| "working"
	| "waiting"
	| "needs_approval"
	| "completed"
	| "error"
	| "offline";

export function useProviderChat(): UseProviderChat {
	const [streaming, setStreaming] = useState(false);
	const [streamingThreadId, setStreamingThreadId] = useState<string | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [agentState, setAgentState] = useState<AgentState>("idle");
	const [stateProviderLabel, setStateProviderLabel] = useState<string | null>(null);
	const [stateModelId, setStateModelId] = useState<string | null>(null);
	const [stateStartedAt, setStateStartedAt] = useState<number | null>(null);
	const [smartReplies, setSmartReplies] = useState<string[]>([]);
	const abortRef = useRef<AbortController | null>(null);
	/** Returns the state line to idle after a completed turn lands. */
	const completedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

	useEffect(() => {
		return () => {
			if (completedTimer.current) {
				clearTimeout(completedTimer.current);
				completedTimer.current = null;
			}
		};
	}, []);

	const runQuickComplete = useCallback(
		async (
			providerId: Parameters<typeof getProvider>[0],
			modelId: string,
			messages: ProviderMessage[],
			maxTokens: number,
		): Promise<string | null> => {
			try {
				const provider = getProvider(providerId);
				if (!provider.quickComplete) return null;
				if (providerId === "node") {
					return null;
				}
				const apiKey = await getProviderKey(providerId);
				if (!apiKey) return null;
				return await provider.quickComplete(
					{ apiKey, model: modelId, messages, maxTokens },
					xhrStreamTransport,
				);
			} catch {
				return null;
			}
		},
		[],
	);

	const generateTitle = useCallback(
		async (threadId: string, firstUserText: string) => {
			const { threads, renameThread } = useChatStore.getState();
			const thread = threads.find((t) => t.id === threadId);
			if (!thread) return;
			const title = await runQuickComplete(
				thread.providerId,
				thread.modelId,
				[
					{
						role: "user",
						content: `Give this chat a very short title (max 5 words, no quotes, no punctuation at the end). First message: ${firstUserText.slice(0, 300)}`,
					},
				],
				24,
			);
			const clean = (title ?? "").trim().replace(/^["']|["']$/g, "");
			if (clean) {
				await renameThread(threadId, clean.slice(0, 60));
			}
		},
		[runQuickComplete],
	);

	const refreshSmartReplies = useCallback(
		(threadId: string) => {
			const { threads } = useChatStore.getState();
			const thread = threads.find((t) => t.id === threadId);
			if (!thread || thread.messages.length === 0) {
				setSmartReplies([]);
				return;
			}
			const lastAssistant = [...thread.messages]
				.reverse()
				.find((m) => m.role === "assistant" && !m.failed);
			if (!lastAssistant) {
				setSmartReplies([]);
				return;
			}
			void (async () => {
				const raw = await runQuickComplete(
					thread.providerId,
					thread.modelId,
					[
						{
							role: "user",
							content: `Suggest 3 short follow-up questions or replies the user might send next. Reply with only the 3 suggestions, one per line, no numbering, no quotes. Keep each under 8 words.\n\nAssistant just said: ${lastAssistant.text.slice(0, 600)}`,
						},
					],
					80,
				);
				if (!raw) return;
				const replies = raw
					.split("\n")
					.map((s) => s.replace(/^[-*\d.)\s]+/, "").trim())
					.filter((s) => s.length > 0 && s.length <= 80)
					.slice(0, 3);
				setSmartReplies(replies);
			})();
		},
		[runQuickComplete],
	);

	/**
	 * Run one generation turn. When appendUser is true the user text is
	 * persisted as a new message first (normal send); when false the text
	 * is already the thread's last user message (retry), so no duplicate
	 * is appended.
	 */
	const runTurn = useCallback(
		async (threadId: string, text: string, appendUser: boolean) => {
			const trimmed = text.trim();
			if (!trimmed || abortRef.current) return;

			const chat = useChatStore.getState();
			const thread = chat.threads.find((t) => t.id === threadId);
			if (!thread) return;

			setError(null);
			setSmartReplies([]);
			if (completedTimer.current) {
				clearTimeout(completedTimer.current);
				completedTimer.current = null;
			}
			// Local setup (persisting the message, reading the key) happens
			// before the request goes out; this is the genuine "waiting" phase.
			setAgentState("waiting");
			setStateStartedAt(Date.now());

			if (appendUser) {
				await chat.addMessage(threadId, "user", trimmed);
			}
			const fresh = useChatStore.getState().threads.find((t) => t.id === threadId);
			if (!fresh) {
				setAgentState("idle");
				return;
			}

			const history = fresh.messages.map((m) => ({
				id: m.id,
				role: m.role,
				text: m.text,
				createdAt: m.createdAt,
			}));
			const profile = useProfileStore.getState().profile;
			const profilePrompt = buildProfilePrompt(profile);
			const systemPrompt = profilePrompt
				? `${baseSystemPrompt()}\n\n${profilePrompt}`
				: baseSystemPrompt();

			const assistantId = await chat.addMessage(threadId, "assistant", "");
			const controller = new AbortController();
			abortRef.current = controller;
			setStreaming(true);
			setStreamingThreadId(threadId);
			setAgentState("thinking");
			try {
				setStateProviderLabel(getProvider(fresh.providerId).label);
			} catch {
				setStateProviderLabel(fresh.providerId);
			}
			setStateModelId(fresh.modelId);
			let sawDelta = false;
			const markWorking = () => {
				if (!sawDelta) {
					sawDelta = true;
					setAgentState("working");
				}
			};

			try {
				const provider = getProvider(fresh.providerId);
				const requestMessages = toProviderMessages(history, systemPrompt);

				if (fresh.providerId === "node") {
					await provider.streamChat({
						apiKey: "",
						model: fresh.modelId,
						messages: requestMessages,
						signal: controller.signal,
						onEvent: (event) => {
							if (event.type === "delta") {
								markWorking();
								useChatStore.getState().appendToMessage(threadId, assistantId, event.text);
							}
						},
					});
				} else {
					const apiKey = await getProviderKey(fresh.providerId);
					if (!apiKey) {
						throw new Error("No API key saved for this provider. Add one in Settings.");
					}
					await provider.streamChat(
						{
							apiKey,
							model: fresh.modelId,
							messages: requestMessages,
							signal: controller.signal,
							onEvent: (event) => {
								if (event.type === "delta") {
									markWorking();
									useChatStore.getState().appendToMessage(threadId, assistantId, event.text);
								}
							},
						},
						xhrStreamTransport,
					);
				}

				await chat.finalizeMessage(threadId, assistantId, false);
				// The turn finished; show a brief completed state, then settle.
				setAgentState("completed");
				completedTimer.current = setTimeout(() => {
					setAgentState((s) => (s === "completed" ? "idle" : s));
					completedTimer.current = null;
				}, 4000);
				if (fresh.title === "New chat") {
					void generateTitle(threadId, trimmed);
				}
				refreshSmartReplies(threadId);
			} catch (err) {
				const aborted = err instanceof ProviderError && err.code === "aborted";
				const message =
					err instanceof Error ? err.message : "Something went wrong. Try again.";
				// Remove the empty assistant bubble on failure so retry is clean.
				const state = useChatStore.getState();
				const target = state.threads.find((t) => t.id === threadId);
				const assistantMsg = target?.messages.find((m) => m.id === assistantId);
				if (assistantMsg && assistantMsg.text.length === 0) {
					await state.finalizeMessage(threadId, assistantId, true);
				} else {
					await state.finalizeMessage(threadId, assistantId, false);
				}
				if (aborted) {
					// User pressed stop; stay idle rather than showing an error.
					setAgentState("idle");
				} else {
					const offline = err instanceof ProviderError && err.code === "network";
					setAgentState(offline ? "offline" : "error");
					setError(message);
				}
			} finally {
				abortRef.current = null;
				setStreaming(false);
				setStreamingThreadId(null);
			}
		},
		[generateTitle, refreshSmartReplies],
	);

	const send = useCallback(
		async (threadId: string, text: string) => {
			await runTurn(threadId, text, true);
		},
		[runTurn],
	);

	const retry = useCallback(
		async (threadId: string) => {
			if (abortRef.current) return;
			const t = useChatStore.getState().threads.find((x) => x.id === threadId);
			const lastUser = [...(t?.messages ?? [])]
				.reverse()
				.find((m) => m.role === "user");
			if (!lastUser) return;
			// Re-run the failed turn without appending a duplicate user message.
			await runTurn(threadId, lastUser.text, false);
		},
		[runTurn],
	);

	const stop = useCallback(() => {
		abortRef.current?.abort();
		if (completedTimer.current) {
			clearTimeout(completedTimer.current);
			completedTimer.current = null;
		}
		// The abort surfaces as an "aborted" ProviderError; treat a user
		// stop as plain idle rather than an error state.
		setAgentState("idle");
		setError(null);
	}, []);

	const clearError = useCallback(() => {
		setError(null);
		setAgentState("idle");
	}, []);

	return {
		streaming,
		streamingThreadId,
		error,
		agentState,
		stateProviderLabel,
		stateModelId,
		stateStartedAt,
		smartReplies,
		send,
		retry,
		stop,
		clearError,
		refreshSmartReplies,
	};
}
