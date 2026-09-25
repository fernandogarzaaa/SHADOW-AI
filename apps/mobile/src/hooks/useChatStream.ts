import { useCallback, useEffect, useRef, useState } from "react";
import { askAgentStream } from "@/api/shadow";

export interface ChatMessage {
	id: string;
	role: "user" | "agent";
	text: string;
	streaming?: boolean;
	failed?: boolean;
	sources?: unknown;
}

let messageCounter = 0;

function newId(prefix: string): string {
	messageCounter += 1;
	return `${prefix}-${Date.now()}-${messageCounter}`;
}

interface StreamDoneResult {
	answer: string;
	sources?: unknown;
}

/**
 * Encapsulates one ask round-trip against the SHADOW node.
 * Streams agent deltas into a pending message, finalizes on done,
 * and marks the message failed (with the real error text) on failure.
 * Never invents placeholder answers.
 */
export function useChatStream() {
	const [messages, setMessages] = useState<ChatMessage[]>([]);
	const [sending, setSending] = useState(false);
	const sendingRef = useRef(false);
	const cancelRef = useRef<(() => void) | null>(null);
	const messagesRef = useRef<ChatMessage[]>([]);

	useEffect(() => {
		messagesRef.current = messages;
	}, [messages]);

	const finishStream = useCallback(
		(agentId: string, patch: Partial<ChatMessage>) => {
			setMessages((prev) =>
				prev.map((m) =>
					m.id === agentId ? { ...m, streaming: false, ...patch } : m,
				),
			);
			sendingRef.current = false;
			setSending(false);
			cancelRef.current = null;
		},
		[],
	);

	const beginStream = useCallback(
		async (prompt: string, agentId: string) => {
			sendingRef.current = true;
			setSending(true);
			try {
				const cancel = await askAgentStream(prompt, {
					onDelta: (delta: string) => {
						setMessages((prev) =>
							prev.map((m) =>
								m.id === agentId ? { ...m, text: m.text + delta } : m,
							),
						);
					},
					onDone: (result: StreamDoneResult) => {
						finishStream(agentId, {
							text: result.answer,
							sources: result.sources,
						});
					},
					onError: (error: Error) => {
						finishStream(agentId, {
							failed: true,
							text: `Request failed: ${error.message}`,
						});
					},
				});
				cancelRef.current = cancel;
			} catch (error) {
				const detail =
					error instanceof Error ? error.message : "Unknown error";
				finishStream(agentId, {
					failed: true,
					text: `Request failed: ${detail}`,
				});
			}
		},
		[finishStream],
	);

	const send = useCallback(
		(prompt: string) => {
			const text = prompt.trim();
			if (!text || sendingRef.current) return;
			const userMessage: ChatMessage = {
				id: newId("user"),
				role: "user",
				text,
			};
			const agentMessage: ChatMessage = {
				id: newId("agent"),
				role: "agent",
				text: "",
				streaming: true,
			};
			setMessages((prev) => [...prev, userMessage, agentMessage]);
			void beginStream(text, agentMessage.id);
		},
		[beginStream],
	);

	const retry = useCallback(
		(agentMessageId: string) => {
			if (sendingRef.current) return;
			const current = messagesRef.current;
			const failed = current.find((m) => m.id === agentMessageId);
			if (!failed || !failed.failed) return;
			let prompt: string | null = null;
			for (let i = current.indexOf(failed) - 1; i >= 0; i -= 1) {
				if (current[i].role === "user") {
					prompt = current[i].text;
					break;
				}
			}
			if (prompt === null) return;
			const replacement: ChatMessage = {
				id: newId("agent"),
				role: "agent",
				text: "",
				streaming: true,
			};
			setMessages((prev) =>
				prev.map((m) => (m.id === agentMessageId ? replacement : m)),
			);
			void beginStream(prompt, replacement.id);
		},
		[beginStream],
	);

	const cancel = useCallback(() => {
		cancelRef.current?.();
		cancelRef.current = null;
		if (sendingRef.current) {
			sendingRef.current = false;
			setSending(false);
			setMessages((prev) =>
				prev.map((m) =>
					m.streaming
						? {
								...m,
								streaming: false,
								text: m.text || "Cancelled.",
							}
						: m,
				),
			);
		}
	}, []);

	const clear = useCallback(() => {
		cancelRef.current?.();
		cancelRef.current = null;
		sendingRef.current = false;
		setSending(false);
		setMessages([]);
	}, []);

	return { messages, sending, send, cancel, clear, retry };
}
