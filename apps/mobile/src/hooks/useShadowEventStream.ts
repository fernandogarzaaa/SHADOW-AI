import { useCallback, useEffect, useRef } from "react";
import { AppState, type AppStateStatus } from "react-native";
import { authHeaders } from "@/lib/shadowSigner";
import { parseSseChunk } from "@/lib/sseParse";
import { useConnectionStore } from "@/stores/useConnectionStore";

/** Event delivered by the SHADOW node SSE stream. */
export interface ShadowEvent {
	type: string;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	properties: any;
}

interface UseShadowEventStreamOptions {
	/** Connect only when true (typically when the node is paired). */
	enabled: boolean;
	/** Called for every parsed event envelope. */
	onEvent: (event: ShadowEvent) => void;
}

interface ShadowConnectionCredentials {
	isPaired: boolean;
	nodeUrl: string | null;
	deviceId?: string | null;
	deviceSecret?: string | null;
}

const INITIAL_RECONNECT_DELAY_MS = 1000;
const MAX_RECONNECT_DELAY_MS = 30000;
const CONNECTION_TIMEOUT_MS = 30000;
const STREAM_PATH = "/agent/stream";
const DEBUG_STREAM = __DEV__;

/**
 * Maintains a persistent SSE connection to the SHADOW node's
 * `GET /agent/stream` endpoint using XMLHttpRequest (React Native does not
 * expose fetch response streaming reliably).
 *
 * Authenticated with the HMAC-SHA256 headers from `@/lib/shadowSigner`.
 * Reconnects with exponential backoff (1s, 2s, 4s ... capped at 30s) and
 * disconnects while the app is in the background.
 */
export function useShadowEventStream({
	enabled,
	onEvent,
}: UseShadowEventStreamOptions): void {
	const isPaired = useConnectionStore((state) => state.isPaired);
	const nodeUrl = useConnectionStore((state) => state.nodeUrl);

	const xhrRef = useRef<XMLHttpRequest | null>(null);
	const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
	const connectionTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
	const lastProcessedIndexRef = useRef(0);
	const bufferRef = useRef("");
	const connectIdRef = useRef(0);
	const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY_MS);
	const isActiveRef = useRef(true);
	const isConnectingRef = useRef(false);
	const appStateRef = useRef<AppStateStatus>(AppState.currentState);
	const onEventRef = useRef(onEvent);
	const connectRef = useRef<() => void>(() => {});

	onEventRef.current = onEvent;

	const clearTimers = useCallback(() => {
		if (reconnectTimeoutRef.current) {
			clearTimeout(reconnectTimeoutRef.current);
			reconnectTimeoutRef.current = null;
		}
		if (connectionTimeoutRef.current) {
			clearTimeout(connectionTimeoutRef.current);
			connectionTimeoutRef.current = null;
		}
	}, []);

	const abortConnection = useCallback(() => {
		// Invalidate any in-flight signing attempt so a late XHR never opens.
		connectIdRef.current += 1;
		if (xhrRef.current) {
			xhrRef.current.abort();
			xhrRef.current = null;
		}
		isConnectingRef.current = false;
		bufferRef.current = "";
	}, []);

	const doScheduleReconnect = useCallback(() => {
		const { isPaired: paired } = useConnectionStore.getState() as unknown as Pick<
			ShadowConnectionCredentials,
			"isPaired"
		>;
		if (!isActiveRef.current || !paired) {
			return;
		}

		clearTimers();

		const delay = reconnectDelayRef.current;
		if (DEBUG_STREAM) {
			console.log(`[ShadowEventStream] Scheduling reconnect in ${delay}ms`);
		}

		reconnectTimeoutRef.current = setTimeout(() => {
			if (isActiveRef.current) {
				connectRef.current();
			}
		}, delay);

		reconnectDelayRef.current = Math.min(
			reconnectDelayRef.current * 2,
			MAX_RECONNECT_DELAY_MS,
		);
	}, [clearTimers]);

	const connect = useCallback(() => {
		const conn = useConnectionStore.getState() as unknown as ShadowConnectionCredentials;
		const { isPaired: paired, nodeUrl: url, deviceId, deviceSecret } = conn;

		if (!paired || !url || !deviceId || !deviceSecret) {
			if (DEBUG_STREAM) {
				console.log("[ShadowEventStream] Not paired, skipping connect");
			}
			return;
		}

		if (isConnectingRef.current || xhrRef.current) {
			if (DEBUG_STREAM) {
				console.log("[ShadowEventStream] Already connecting or connected");
			}
			return;
		}

		if (appStateRef.current !== "active") {
			if (DEBUG_STREAM) {
				console.log("[ShadowEventStream] App not active, skipping connect");
			}
			return;
		}

		isConnectingRef.current = true;
		clearTimers();

		let normalizedUrl = url.trim();
		if (
			!normalizedUrl.startsWith("http://") &&
			!normalizedUrl.startsWith("https://")
		) {
			normalizedUrl = `http://${normalizedUrl}`;
		}
		if (normalizedUrl.endsWith("/")) {
			normalizedUrl = normalizedUrl.slice(0, -1);
		}
		const streamUrl = `${normalizedUrl}${STREAM_PATH}`;
		const connectId = ++connectIdRef.current;

		if (DEBUG_STREAM) {
			console.log(`[ShadowEventStream] Connecting to ${streamUrl}`);
		}

		void (async () => {
			let headers: Record<string, string>;
			try {
				headers = await authHeaders({
					deviceId,
					secret: deviceSecret,
					method: "GET",
					path: STREAM_PATH,
					body: "",
				});
			} catch (signError) {
				console.error("[ShadowEventStream] Failed to sign request", signError);
				isConnectingRef.current = false;
				if (isActiveRef.current && connectId === connectIdRef.current) {
					doScheduleReconnect();
				}
				return;
			}

			if (!isActiveRef.current || connectId !== connectIdRef.current) {
				// Aborted or superseded while signing.
				return;
			}

			const xhr = new XMLHttpRequest();
			xhrRef.current = xhr;
			lastProcessedIndexRef.current = 0;
			bufferRef.current = "";

			connectionTimeoutRef.current = setTimeout(() => {
				if (xhrRef.current === xhr && isConnectingRef.current) {
					console.warn("[ShadowEventStream] Connection timeout");
					xhr.abort();
				}
			}, CONNECTION_TIMEOUT_MS);

			xhr.open("GET", streamUrl, true);
			for (const [name, value] of Object.entries(headers)) {
				xhr.setRequestHeader(name, value);
			}
			xhr.setRequestHeader("Accept", "text/event-stream");
			xhr.setRequestHeader("Cache-Control", "no-cache");

		xhr.onreadystatechange = () => {
			if (xhr.readyState === XMLHttpRequest.HEADERS_RECEIVED) {
				if (connectionTimeoutRef.current) {
					clearTimeout(connectionTimeoutRef.current);
					connectionTimeoutRef.current = null;
				}

				if (xhr.status === 200) {
					if (DEBUG_STREAM) {
						console.log("[ShadowEventStream] Connected");
					}
					isConnectingRef.current = false;
					reconnectDelayRef.current = INITIAL_RECONNECT_DELAY_MS;
				} else {
					console.error(
						`[ShadowEventStream] Connection failed: ${xhr.status}`,
					);
					isConnectingRef.current = false;
				}
			}

			if (
				xhr.readyState === XMLHttpRequest.LOADING ||
				xhr.readyState === XMLHttpRequest.DONE
			) {
				const newData = xhr.responseText.slice(lastProcessedIndexRef.current);
				lastProcessedIndexRef.current = xhr.responseText.length;

				if (newData) {
					const { events, rest } = parseSseChunk(
						bufferRef.current + newData,
					);
					bufferRef.current = rest;

					for (const event of events) {
						if (DEBUG_STREAM) {
							console.log("[ShadowEventStream] Event:", event.type);
						}
						onEventRef.current(event);
					}
				}
			}

			if (xhr.readyState === XMLHttpRequest.DONE) {
				if (DEBUG_STREAM) {
					console.log("[ShadowEventStream] Connection closed");
				}
				xhrRef.current = null;
				isConnectingRef.current = false;

				if (isActiveRef.current) {
					doScheduleReconnect();
				}
			}
		};

		const handleFailure = (label: string) => {
			if (DEBUG_STREAM) {
				console.error(`[ShadowEventStream] ${label}`);
			}
			if (connectionTimeoutRef.current) {
				clearTimeout(connectionTimeoutRef.current);
				connectionTimeoutRef.current = null;
			}
			xhrRef.current = null;
			isConnectingRef.current = false;

			if (isActiveRef.current) {
				doScheduleReconnect();
			}
		};

		xhr.onerror = () => handleFailure("XHR error");
		xhr.ontimeout = () => handleFailure("XHR timeout");

		xhr.send();
		})();
	}, [clearTimers, doScheduleReconnect]);

	connectRef.current = connect;

	// Pause the stream while the app is backgrounded; resume on foreground.
	useEffect(() => {
		const handleAppStateChange = (nextAppState: AppStateStatus) => {
			const previousState = appStateRef.current;
			appStateRef.current = nextAppState;

			if (
				previousState.match(/inactive|background/) &&
				nextAppState === "active"
			) {
				if (DEBUG_STREAM) {
					console.log("[ShadowEventStream] App became active, reconnecting");
				}
				abortConnection();
				clearTimers();
				reconnectDelayRef.current = INITIAL_RECONNECT_DELAY_MS;
				setTimeout(() => {
					connectRef.current();
				}, 100);
			} else if (nextAppState.match(/inactive|background/)) {
				if (DEBUG_STREAM) {
					console.log("[ShadowEventStream] App backgrounded, disconnecting");
				}
				abortConnection();
				clearTimers();
			}
		};

		const subscription = AppState.addEventListener(
			"change",
			handleAppStateChange,
		);
		return () => {
			subscription.remove();
		};
	}, [abortConnection, clearTimers]);

	// Connect while enabled and paired; tear down on unmount.
	useEffect(() => {
		isActiveRef.current = true;

		if (enabled && isPaired && appStateRef.current === "active") {
			connectRef.current();
		}

		return () => {
			isActiveRef.current = false;
			abortConnection();
			clearTimers();
		};
	}, [enabled, isPaired, nodeUrl, abortConnection, clearTimers]);
}
