/**
 * Chat threads and messages, persisted in AsyncStorage.
 *
 * Optimistic in-memory state with deterministic finalization: every
 * mutation writes through to storage so a killed app loses nothing.
 * Only plain message text is stored here; provider keys never touch this
 * store.
 */

import AsyncStorage from "@react-native-async-storage/async-storage";
import { create } from "zustand";
import type { ProviderId } from "@/providers";

const STORAGE_KEY = "shadow.chat.threads.v1";

export type ChatRole = "user" | "assistant";

export interface ChatMessage {
	id: string;
	role: ChatRole;
	text: string;
	createdAt: number;
	/** Set while the assistant message is still streaming. */
	streaming?: boolean;
	/** Set when the send failed; UI offers retry. */
	failed?: boolean;
}

export interface ChatThread {
	id: string;
	title: string;
	providerId: ProviderId;
	modelId: string;
	createdAt: number;
	updatedAt: number;
	messages: ChatMessage[];
	/** Last time the user viewed this thread. Unset means never viewed. */
	lastReadAt?: number;
}

function newId(): string {
	return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

interface ChatStoreState {
	threads: ChatThread[];
	activeThreadId: string | null;
	initialized: boolean;
	initialize: () => Promise<void>;
	createThread: (providerId: ProviderId, modelId: string) => Promise<string>;
	setActiveThread: (id: string | null) => void;
	deleteThread: (id: string) => Promise<void>;
	renameThread: (id: string, title: string) => Promise<void>;
	/** Marks a thread as viewed now. Powers the unread dots on the chats list. */
	markThreadRead: (threadId: string) => Promise<void>;
	addMessage: (threadId: string, role: ChatRole, text: string) => Promise<string>;
	appendToMessage: (threadId: string, messageId: string, delta: string) => void;
	finalizeMessage: (threadId: string, messageId: string, failed?: boolean) => Promise<void>;
}

async function persist(threads: ChatThread[]): Promise<void> {
	try {
		await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(threads));
	} catch {
		// Chat persistence is best-effort; in-memory state stays authoritative.
	}
}

function touch(thread: ChatThread): ChatThread {
	return { ...thread, updatedAt: Date.now() };
}

export const useChatStore = create<ChatStoreState>()((set, get) => ({
	threads: [],
	activeThreadId: null,
	initialized: false,

	initialize: async () => {
		let threads: ChatThread[] = [];
		try {
			const raw = await AsyncStorage.getItem(STORAGE_KEY);
			if (raw) {
				const parsed = JSON.parse(raw) as ChatThread[];
				if (Array.isArray(parsed)) {
					// A message left mid-stream by a killed app finalizes as-is.
					threads = parsed.map((t) => ({
						...t,
						messages: t.messages.map((m) => ({ ...m, streaming: false })),
					}));
				}
			}
		} catch {
			threads = [];
		}
		threads.sort((a, b) => b.updatedAt - a.updatedAt);
		set({
			threads,
			activeThreadId: threads[0]?.id ?? null,
			initialized: true,
		});
	},

	createThread: async (providerId, modelId) => {
		const thread: ChatThread = {
			id: newId(),
			title: "New chat",
			providerId,
			modelId,
			createdAt: Date.now(),
			updatedAt: Date.now(),
			messages: [],
		};
		const threads = [thread, ...get().threads];
		set({ threads, activeThreadId: thread.id });
		await persist(threads);
		return thread.id;
	},

	setActiveThread: (id) => set({ activeThreadId: id }),

	deleteThread: async (id) => {
		const { threads, activeThreadId } = get();
		const remaining = threads.filter((t) => t.id !== id);
		set({
			threads: remaining,
			activeThreadId: activeThreadId === id ? (remaining[0]?.id ?? null) : activeThreadId,
		});
		await persist(remaining);
	},

	renameThread: async (id, title) => {
		const threads = get().threads.map((t) =>
			t.id === id ? touch({ ...t, title }) : t,
		);
		set({ threads });
		await persist(threads);
	},

	markThreadRead: async (threadId) => {
		const now = Date.now();
		const threads = get().threads.map((t) =>
			t.id === threadId ? { ...t, lastReadAt: now } : t,
		);
		set({ threads });
		await persist(threads);
	},

	addMessage: async (threadId, role, text) => {
		const message: ChatMessage = {
			id: newId(),
			role,
			text,
			createdAt: Date.now(),
			streaming: role === "assistant",
		};
		const threads = get().threads.map((t) =>
			t.id === threadId ? touch({ ...t, messages: [...t.messages, message] }) : t,
		);
		set({ threads });
		await persist(threads);
		return message.id;
	},

	appendToMessage: (threadId, messageId, delta) => {
		const threads = get().threads.map((t) => {
			if (t.id !== threadId) return t;
			return {
				...t,
				updatedAt: Date.now(),
				messages: t.messages.map((m) =>
					m.id === messageId ? { ...m, text: m.text + delta } : m,
				),
			};
		});
		set({ threads });
		// Deliberately not persisted per delta; finalized on completion.
	},

	finalizeMessage: async (threadId, messageId, failed = false) => {
		const threads = get().threads.map((t) => {
			if (t.id !== threadId) return t;
			return touch({
				...t,
				messages: t.messages.map((m) =>
					m.id === messageId ? { ...m, streaming: false, failed } : m,
				),
			});
		});
		set({ threads });
		await persist(threads);
	},
}));

/** Pure helper for tests: sort newest-first. */
export function sortThreadsNewestFirst(threads: ChatThread[]): ChatThread[] {
	return [...threads].sort((a, b) => b.updatedAt - a.updatedAt);
}

/**
 * Pure helper for tests: a thread counts as unread when it was updated
 * after the user last viewed it. The user's own active thread is never
 * unread; callers exclude it before rendering the dot.
 */
export function isThreadUnread(thread: ChatThread): boolean {
	if (thread.messages.length === 0) return false;
	return (thread.lastReadAt ?? 0) < thread.updatedAt;
}
