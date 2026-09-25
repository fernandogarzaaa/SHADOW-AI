import { Platform } from "react-native";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import * as SecureStore from "expo-secure-store";
import Constants from "expo-constants";

import { useConnectionStore } from "@/stores/useConnectionStore";
import { authHeaders } from "@/lib/shadowSigner";

/**
 * Push notification wiring between the SHADOW mobile app and the Shadow Node.
 *
 * The node sends approval alerts as Expo push messages to this device.
 * Registering the token requires:
 *   - a completed pairing (deviceId in the connection store, secret in SecureStore)
 *   - notification permission granted by the user
 *   - a real EAS projectId in app config (extra.eas.projectId)
 *   - a development / preview / production build (Expo Go cannot receive
 *     real push tokens)
 *
 * Every function here is defensive: on any failure the token helpers return
 * null and registerPushTokenForDevice() returns false instead of throwing,
 * because Worker A's pairing flow calls it inside try/catch and pairing
 * must succeed even when push is unavailable.
 */

const PUSH_TOKEN_PREFIX = "ExponentPushToken[";
const EAS_PROJECT_ID_PLACEHOLDER = "TODO-inan-eas-project-id";
const PUSH_REGISTERED_KEY = "shadow_push_registered";
const DEVICE_SECRET_KEY = "shadow_device_secret";
const APPROVALS_CHANNEL_ID = "approvals";

/** The slice of connection state this module needs. Worker A owns the store. */
interface PushConnectionState {
	deviceId: string | null;
	isPaired: boolean;
	nodeUrl: string | null;
	baseUrl: string | null;
	serverUrl: string | null;
}

function readConnectionState(): PushConnectionState {
	return useConnectionStore.getState() as unknown as PushConnectionState;
}

function readEasProjectId(): string | null {
	const projectId = Constants.expoConfig?.extra?.eas?.projectId;
	if (typeof projectId !== "string") return null;
	if (projectId === EAS_PROJECT_ID_PLACEHOLDER) return null;
	return projectId;
}

/**
 * Ask the user for notification permission. Creates the Android "approvals"
 * channel with high importance so approval alerts surface immediately.
 * Returns true only when notifications are granted.
 */
export async function ensurePushPermissions(): Promise<boolean> {
	try {
		if (!Device.isDevice) return false;

		const existing = await Notifications.getPermissionsAsync();
		let status = existing.status;
		if (status !== "granted") {
			const requested = await Notifications.requestPermissionsAsync();
			status = requested.status;
		}
		if (status !== "granted") return false;

		if (Platform.OS === "android") {
			await Notifications.setNotificationChannelAsync(APPROVALS_CHANNEL_ID, {
				name: "Approvals",
				importance: Notifications.AndroidImportance.MAX,
				vibrationPattern: [0, 250, 250, 250],
				lightColor: "#0A0A0A",
				sound: undefined,
			});
		}
		return true;
	} catch {
		return false;
	}
}

/**
 * Fetch this device's Expo push token. Returns null when no EAS projectId is
 * configured (still the placeholder), when running on a simulator, or when
 * the token request fails.
 */
export async function getExpoPushToken(): Promise<string | null> {
	try {
		const projectId = readEasProjectId();
		if (!projectId) return null;
		const { data } = await Notifications.getExpoPushTokenAsync({ projectId });
		return typeof data === "string" && data.length > 0 ? data : null;
	} catch {
		return null;
	}
}

interface PushRegistrationResponse {
	push_registered?: boolean;
}

/**
 * Register this device's Expo push token with the paired Shadow Node via
 * POST /devices/{deviceId}/push-token. Idempotent on the node side.
 * Returns true on success, false (never throws) on any failure.
 */
export async function registerPushTokenForDevice(): Promise<boolean> {
	try {
		const state = readConnectionState();
		if (!state.isPaired || !state.deviceId) return false;

		const granted = await ensurePushPermissions();
		if (!granted) return false;

		const token = await getExpoPushToken();
		if (!token || !token.startsWith(PUSH_TOKEN_PREFIX)) return false;

		const secret = await SecureStore.getItemAsync(DEVICE_SECRET_KEY);
		if (!secret) return false;

		const baseUrl = state.nodeUrl ?? state.baseUrl ?? state.serverUrl ?? null;
		if (!baseUrl) return false;

		const deviceId = state.deviceId;
		const path = `/devices/${encodeURIComponent(deviceId)}/push-token`;
		const body = JSON.stringify({ push_token: token });
		const headers = await authHeaders({
			deviceId,
			secret,
			method: "POST",
			path,
			body,
		});

		const response = await fetch(`${baseUrl}${path}`, {
			method: "POST",
			headers: {
				...headers,
				"Content-Type": "application/json",
			},
			body,
		});
		if (!response.ok) return false;

		const payload = (await response.json().catch(() => null)) as PushRegistrationResponse | null;
		if (!payload || payload.push_registered !== true) return false;

		await SecureStore.setItemAsync(PUSH_REGISTERED_KEY, "true");
		return true;
	} catch {
		return false;
	}
}

/** Snapshot for the settings screen: permission state, current token, registration flag. */
export async function getPushStatus(): Promise<{
	granted: boolean;
	token: string | null;
	registered: boolean;
}> {
	try {
		const permission = await Notifications.getPermissionsAsync();
		const granted = permission.status === "granted";
		const token = granted ? await getExpoPushToken() : null;
		const registered = (await SecureStore.getItemAsync(PUSH_REGISTERED_KEY)) === "true";
		return { granted, token, registered };
	} catch {
		return { granted: false, token: null, registered: false };
	}
}
