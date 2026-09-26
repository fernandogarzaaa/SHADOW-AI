/**
 * SHADOW node provider adapter.
 *
 * Exposes the paired node's agent as an optional ModelProvider, reusing the
 * existing HMAC-authed askAgentStream. No API key: availability is gated on
 * the node being linked (useConnectionStore.isPaired).
 */

import { askAgentStream } from "@/api/shadow";
import { ProviderError } from "./errors";
import type { ModelProvider, StreamRequest } from "./types";

export const nodeProvider: ModelProvider = {
	id: "node",
	label: "SHADOW Node",
	models: [
		{
			id: "node-agent",
			label: "Node agent",
			blurb: "Your linked SHADOW node: approvals context and local tools.",
		},
	],
	defaultModel: "node-agent",

	validateKey: async () => {
		// The node has no API key; pairing itself is the credential.
	},

	streamChat: async (request: StreamRequest) => {
		const { messages, signal, onEvent } = request;
		const prompt = messages
			.filter((m) => m.role !== "system")
			.map((m) => `${m.role === "assistant" ? "Assistant" : "User"}: ${m.content}`)
			.join("\n\n");
		const system = messages
			.filter((m) => m.role === "system")
			.map((m) => m.content)
			.join("\n\n");
		const fullPrompt = system ? `${system}\n\n${prompt}` : prompt;

		try {
			await new Promise<void>((resolve, reject) => {
				let cancel: (() => void) | null = null;
				let settled = false;
				const finish = (fn: () => void) => {
					if (settled) return;
					settled = true;
					fn();
				};

				const onAbort = () => {
					cancel?.();
					finish(() => reject(new ProviderError("aborted", "Cancelled.")));
				};
				signal?.addEventListener("abort", onAbort);

				askAgentStream(fullPrompt, {
					onDelta: (delta) => onEvent({ type: "delta", text: delta }),
					onDone: () => {
						signal?.removeEventListener("abort", onAbort);
						finish(resolve);
					},
					onError: (error) => {
						signal?.removeEventListener("abort", onAbort);
						finish(() => reject(error));
					},
				}).then(
					(cancelFn) => {
						cancel = cancelFn;
						if (signal?.aborted) {
							onAbort();
						}
					},
					(error) => {
						signal?.removeEventListener("abort", onAbort);
						finish(() => reject(error));
					},
				);
			});
			onEvent({ type: "done" });
		} catch (error) {
			if (error instanceof ProviderError) {
				throw error;
			}
			throw new ProviderError(
				"network",
				error instanceof Error ? error.message : "Node request failed.",
			);
		}
	},
};
