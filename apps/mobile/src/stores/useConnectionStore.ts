/**
 * SHADOW node connection store.
 *
 * The device secret lives ONLY in expo-secure-store (key `shadow_device_secret`)
 * and in memory while the app runs. Everything else persisted here is
 * non-sensitive (node URL, device id, device name, app-lock flag).
 */

import { registerPushTokenForDevice } from "@/lib/notifications";
import { randomHexBytes } from "@/lib/shadowSigner";
import * as SecureStore from "expo-secure-store";
import { create } from "zustand";

const STORAGE_KEYS = {
	NODE_URL: "shadow_node_url",
	DEVICE_ID: "shadow_device_id",
	DEVICE_NAME: "shadow_device_name",
	DEVICE_SECRET: "shadow_device_secret",
	APP_LOCK: "shadow_app_lock",
} as const;

interface ConnectionState {
	nodeUrl: string | null;
	deviceId: string | null;
	deviceSecret: string | null;
	deviceName: string | null;
	isPaired: boolean;
	appLockEnabled: boolean;
	pairing: boolean;
	pairError: string | null;
	restored: boolean;
	// Kept for the app entry screen, which reads these.
	isInitialized: boolean;
	isConnected: boolean;
	// --- Legacy OpenCode-era surface (deprecated). Kept so not-yet-migrated
	// template files still compile while other workers rewrite them.
	// Do not use in new SHADOW code.
	serverUrl: string | null;
	authToken: string | null;
	directory: string | null;
	homeDirectory: string | null;
	pinnedDirectories: string[];
}

interface ConnectionActions {
	setNodeUrl: (url: string) => Promise<void>;
	pair: (url: string, pairingId: string, deviceName: string) => Promise<void>;
	restore: () => Promise<void>;
	signOut: () => Promise<void>;
	setAppLockEnabled: (enabled: boolean) => Promise<void>;
	/** Alias of restore, kept for the app entry screen. */
	initialize: () => Promise<void>;
	// --- Legacy OpenCode-era actions (deprecated, no-ops or aliases).
	setConnection: (serverUrl: string, authToken: string) => Promise<void>;
	setDirectory: (directory: string) => Promise<void>;
	syncServerDirectory: () => Promise<void>;
	loadPinnedDirectories: () => Promise<void>;
	togglePinnedDirectory: (path: string) => Promise<void>;
	disconnect: () => Promise<void>;
}

type ConnectionStore = ConnectionState & ConnectionActions;

function normalizeUrl(raw: string): string {
	let url = raw.trim().replace(/\/+$/, "");
	if (!/^https?:\/\//i.test(url)) {
		url = `http://${url}`;
	}
	return url;
}

function friendlyPairError(error: unknown): string {
	if (error instanceof Error) {
		const status = (error as { status?: number }).status;
		if (status === 404 || status === 410) {
			return "That pairing code is invalid or has expired. Generate a new one on the node and try again.";
		}
		if (status === 401 || status === 403) {
			return "The node rejected the pairing. Check that pairing is still open on the node.";
		}
		if (status === 0 || /reach|network/i.test(error.message)) {
			return "Could not reach the node. Check the URL and make sure your phone is on the same network.";
		}
		if (error.message && error.message.length > 0 && error.message.length < 160) {
			return error.message;
		}
	}
	return "Pairing failed. Check the URL and pairing code, then try again.";
}

export const useConnectionStore = create<ConnectionStore>((set, get) => ({
	nodeUrl: null,
	deviceId: null,
	deviceSecret: null,
	deviceName: null,
	isPaired: false,
	appLockEnabled: false,
	pairing: false,
	pairError: null,
	restored: false,
	isInitialized: false,
	isConnected: false,
	serverUrl: null,
	authToken: null,
	directory: null,
	homeDirectory: null,
	pinnedDirectories: [],

	setNodeUrl: async (url: string) => {
		const nodeUrl = normalizeUrl(url);
		await SecureStore.setItemAsync(STORAGE_KEYS.NODE_URL, nodeUrl);
		set({ nodeUrl, serverUrl: nodeUrl });
	},

	pair: async (url: string, pairingId: string, deviceName: string) => {
		set({ pairing: true, pairError: null });
		const nodeUrl = normalizeUrl(url);
		set({ nodeUrl });

		try {
			// Lazy import to avoid a module cycle: shadow.ts reads this store.
			const { pairConfirm } = await import("@/api/shadow");
			const name = deviceName.trim() || "SHADOW mobile";
			const result = await pairConfirm(
				pairingId.trim(),
				name,
				randomHexBytes(16),
			);

			const deviceId = result.device.id;
			const deviceSecret = result.shared_secret;
			const pairedName = result.device.name;

			await Promise.all([
				SecureStore.setItemAsync(STORAGE_KEYS.NODE_URL, nodeUrl),
				SecureStore.setItemAsync(STORAGE_KEYS.DEVICE_ID, deviceId),
				SecureStore.setItemAsync(STORAGE_KEYS.DEVICE_NAME, pairedName),
				SecureStore.setItemAsync(STORAGE_KEYS.DEVICE_SECRET, deviceSecret),
			]);

			set({
				nodeUrl,
				serverUrl: nodeUrl,
				deviceId,
				deviceSecret,
				deviceName: pairedName,
				isPaired: true,
				isConnected: true,
				pairing: false,
				pairError: null,
			});

			// Best-effort: push registration must never break pairing.
			try {
				await registerPushTokenForDevice();
			} catch (pushError) {
				console.warn("[Connection] Push token registration failed:", pushError);
			}
		} catch (error) {
			set({ pairing: false, pairError: friendlyPairError(error) });
			throw error;
		}
	},

	restore: async () => {
		try {
			const [nodeUrl, deviceId, deviceName, deviceSecret, appLockRaw] =
				await Promise.all([
					SecureStore.getItemAsync(STORAGE_KEYS.NODE_URL),
					SecureStore.getItemAsync(STORAGE_KEYS.DEVICE_ID),
					SecureStore.getItemAsync(STORAGE_KEYS.DEVICE_NAME),
					SecureStore.getItemAsync(STORAGE_KEYS.DEVICE_SECRET),
					SecureStore.getItemAsync(STORAGE_KEYS.APP_LOCK),
				]);

			const isPaired = Boolean(nodeUrl && deviceId && deviceSecret);
			set({
				nodeUrl,
				serverUrl: nodeUrl,
				deviceId,
				deviceName,
				deviceSecret: isPaired ? deviceSecret : null,
				isPaired,
				appLockEnabled: appLockRaw === "1",
				restored: true,
				isInitialized: true,
				isConnected: isPaired,
			});
		} catch {
			set({ restored: true, isInitialized: true, isPaired: false, isConnected: false });
		}
	},

	signOut: async () => {
		const { deviceId, isPaired } = get();

		// Best-effort: tell the node to revoke this device before wiping.
		if (isPaired && deviceId) {
			try {
				const { deleteDevice } = await import("@/api/shadow");
				await deleteDevice(deviceId);
			} catch (error) {
				console.warn("[Connection] Device revoke failed, wiping locally:", error);
			}
		}

		await Promise.all([
			SecureStore.deleteItemAsync(STORAGE_KEYS.NODE_URL),
			SecureStore.deleteItemAsync(STORAGE_KEYS.DEVICE_ID),
			SecureStore.deleteItemAsync(STORAGE_KEYS.DEVICE_NAME),
			SecureStore.deleteItemAsync(STORAGE_KEYS.DEVICE_SECRET),
		]);

		set({
			nodeUrl: null,
			serverUrl: null,
			deviceId: null,
			deviceSecret: null,
			deviceName: null,
			isPaired: false,
			isConnected: false,
			pairing: false,
			pairError: null,
		});
	},

	setAppLockEnabled: async (enabled: boolean) => {
		await SecureStore.setItemAsync(
			STORAGE_KEYS.APP_LOCK,
			enabled ? "1" : "0",
		);
		set({ appLockEnabled: enabled });
	},

	initialize: async () => {
		await get().restore();
	},

	// --- Deprecated legacy aliases (see ConnectionState). ---

	setConnection: async (serverUrl: string) => {
		await get().setNodeUrl(serverUrl);
	},

	setDirectory: async () => {
		// OpenCode working-directory concept has no SHADOW equivalent.
	},

	syncServerDirectory: async () => {
		// OpenCode working-directory concept has no SHADOW equivalent.
	},

	loadPinnedDirectories: async () => {
		// OpenCode working-directory concept has no SHADOW equivalent.
	},

	togglePinnedDirectory: async () => {
		// OpenCode working-directory concept has no SHADOW equivalent.
	},

	disconnect: async () => {
		await get().signOut();
	},
}));

export const getConnectionState = () => useConnectionStore.getState();
