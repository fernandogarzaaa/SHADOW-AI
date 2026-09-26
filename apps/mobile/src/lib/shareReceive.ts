/**
 * Share-sheet receive (Android).
 *
 * When another app shares text, a link, or media into SHADOW, the
 * manifest SEND filters (plugins/withSystemIntegrations.js) bring the
 * app forward and react-native-receive-sharing-intent exposes the
 * payload. This module files it as a new chat message in a fresh thread.
 *
 * The native module is absent in Expo Go: setup degrades to a no-op.
 * React Native imports are lazy so the pure formatter stays testable.
 * Never throws.
 */

import { messageForSharedFiles, type SharedFile } from "./shareFormat";

function getNativeModule(): {
	getReceivedFiles?: (
		handler: (files: SharedFile[]) => void,
		errorHandler: (e: unknown) => void,
	) => void;
	clearReceivedFiles?: () => void;
} | null {
	try {
		// eslint-disable-next-line @typescript-eslint/no-require-imports
		const { NativeModules } = require("react-native") as typeof import("react-native");
		if (!NativeModules.ReceiveSharingIntent) return null;
		// eslint-disable-next-line @typescript-eslint/no-require-imports
		const mod = require("react-native-receive-sharing-intent").default;
		if (!mod || typeof mod.getReceivedFiles !== "function") return null;
		return mod;
	} catch {
		return null;
	}
}

async function handleSharedFiles(files: SharedFile[]): Promise<void> {
	const message = messageForSharedFiles(files);
	if (!message) return;
	try {
		// eslint-disable-next-line @typescript-eslint/no-require-imports
		const { router } = require("expo-router") as typeof import("expo-router");
		// eslint-disable-next-line @typescript-eslint/no-require-imports
		const { useChatStore } = require("../stores/useChatStore") as typeof import("../stores/useChatStore");
		// eslint-disable-next-line @typescript-eslint/no-require-imports
		const { useProviderStore } = require("../stores/useProviderStore") as typeof import("../stores/useProviderStore");
		const { providerId, modelId } = useProviderStore.getState();
		const threadId = await useChatStore.getState().createThread(providerId, modelId);
		router.push({
			pathname: "/chat/[id]",
			params: { id: threadId, autosend: `I shared this with you:\n\n${message}` },
		});
	} catch {
		// Store/router unavailable; drop the share rather than crash.
	}
}

/**
 * Start listening for shared content. Returns a cleanup function.
 * Safe in Expo Go (no native module): returns a no-op cleanup.
 */
export function setupShareReceive(): () => void {
	const noop = () => {};
	const mod = getNativeModule();
	if (!mod || !mod.getReceivedFiles) return noop;
	try {
		mod.getReceivedFiles(
			(files: SharedFile[]) => {
				void handleSharedFiles(files ?? []);
			},
			() => {},
		);
		return () => {
			try {
				mod.clearReceivedFiles?.();
			} catch {
				// Best-effort cleanup.
			}
		};
	} catch {
		return noop;
	}
}
