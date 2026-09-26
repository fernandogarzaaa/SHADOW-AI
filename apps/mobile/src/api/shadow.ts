/**
 * Typed SHADOW node client used by all screens.
 * Auth: HMAC-SHA256 per request (see @/lib/shadowSigner).
 */

import { authHeaders } from "@/lib/shadowSigner";
import { useConnectionStore } from "@/stores/useConnectionStore";

export type ApprovalRisk = "low" | "medium" | "high";
export type ApprovalStatus = "pending" | "approved" | "denied" | "expired";

export interface ApprovalAction {
	tool_name: string;
	description: string;
	params: Record<string, unknown>;
	risk: ApprovalRisk;
	destructive: boolean;
	data_used: string[];
	model_used: string;
	destination: string;
}

export interface ApprovalRequest {
	id: string;
	action: ApprovalAction;
	reason: string;
	status: ApprovalStatus;
	action_preview: string;
	risk_label: string;
	requires_double_confirmation: boolean;
	created_at: string;
	expires_at: string;
	decided_at: string | null;
	deny_reason: string | null;
}

export interface HealthResponse {
	status: string;
	version: string;
	local_first: boolean;
	auth_required: boolean;
}

export interface PairStartResponse {
	pairing_id: string;
	expires_in: number;
}

export interface PairedDevice {
	id: string;
	name: string;
	paired_at: string;
	revoked: boolean;
}

export interface PairConfirmResponse {
	device: PairedDevice;
	shared_secret: string;
}

export interface ApprovalsResponse {
	approvals: ApprovalRequest[];
	count: number;
}

export interface AskAgentResponse {
	answer: string;
	sources?: unknown;
	[k: string]: unknown;
}

export class ShadowApiError extends Error {
	constructor(
		message: string,
		public status: number,
		public body?: string,
	) {
		super(message);
		this.name = "ShadowApiError";
	}
}

interface ShadowFetchInit {
	method?: string;
	body?: unknown;
	auth?: boolean;
}

function normalizeBaseUrl(raw: string): string {
	let base = raw.trim().replace(/\/+$/, "");
	if (!/^https?:\/\//i.test(base)) {
		base = `http://${base}`;
	}
	return base;
}

function getBaseUrl(): string {
	const { nodeUrl } = useConnectionStore.getState();
	if (!nodeUrl) {
		throw new ShadowApiError("Not paired with a SHADOW node", 0);
	}
	return normalizeBaseUrl(nodeUrl);
}

function messageFromBody(bodyText: string): string | null {
	try {
		const parsed = JSON.parse(bodyText) as {
			error?: unknown;
			message?: unknown;
			detail?: unknown;
		};
		for (const key of ["message", "error", "detail"] as const) {
			const value = parsed[key];
			if (typeof value === "string" && value.length > 0) {
				return value;
			}
		}
	} catch {
		// not JSON
	}
	return null;
}

function friendlyError(status: number, bodyText: string): string {
	const serverMessage = messageFromBody(bodyText);
	if (serverMessage) return serverMessage;
	switch (status) {
		case 400:
			return "The node rejected the request.";
		case 401:
			return "Authentication failed. The pairing may have been revoked.";
		case 403:
			return "The node refused this request.";
		case 404:
			return "Not found. The pairing code may have expired.";
		case 410:
			return "The pairing code has expired. Generate a new one on the node.";
		case 429:
			return "Too many requests. Wait a moment and try again.";
		default:
			if (status >= 500) {
				return "The node ran into an error. Try again in a moment.";
			}
			return `Request failed with status ${status}.`;
	}
}

/**
 * Authenticated JSON request against the paired node.
 * Defaults to HMAC auth; pass auth: false for /pair/* and /health.
 * Throws ShadowApiError (carries status) on non-2xx.
 */
export async function shadowFetch(
	path: string,
	init: ShadowFetchInit = {},
): Promise<Response> {
	const { method = "GET", body, auth = true } = init;
	const base = getBaseUrl();
	const bodyString = body === undefined ? "" : JSON.stringify(body);
	// The node signs request.url.path only (no query string); sign the same
	// canonical path here or requests like /approvals?status=pending get 401.
	const signPath = path.split("?")[0];

	const headers: Record<string, string> = {
		Accept: "application/json",
	};
	if (body !== undefined) {
		headers["Content-Type"] = "application/json";
	}
	if (auth) {
		const { deviceId, deviceSecret } = useConnectionStore.getState();
		if (!deviceId || !deviceSecret) {
			throw new ShadowApiError("Not paired with a SHADOW node", 0);
		}
		const signed = await authHeaders({
			deviceId,
			secret: deviceSecret,
			method,
			path: signPath,
			body: bodyString,
		});
		Object.assign(headers, signed);
	}

	let response: Response;
	try {
		response = await fetch(`${base}${path}`, {
			method,
			headers,
			body: body === undefined ? undefined : bodyString,
		});
	} catch (error) {
		throw new ShadowApiError(
			"Could not reach the node. Check that the URL is correct and your phone is on the same network.",
			0,
			error instanceof Error ? error.message : undefined,
		);
	}

	if (!response.ok) {
		const text = await response.text().catch(() => "");
		throw new ShadowApiError(friendlyError(response.status, text), response.status, text);
	}
	return response;
}

async function readJson<T>(response: Response): Promise<T> {
	return (await response.json()) as T;
}

export async function getHealth(): Promise<HealthResponse> {
	return readJson<HealthResponse>(
		await shadowFetch("/health", { auth: false }),
	);
}

export async function pairStart(): Promise<PairStartResponse> {
	return readJson<PairStartResponse>(
		await shadowFetch("/pair/start", { method: "POST", body: {}, auth: false }),
	);
}

export async function pairConfirm(
	pairingId: string,
	deviceName: string,
	publicKey: string,
): Promise<PairConfirmResponse> {
	return readJson<PairConfirmResponse>(
		await shadowFetch("/pair/confirm", {
			method: "POST",
			auth: false,
			body: {
				pairing_id: pairingId,
				device_name: deviceName,
				public_key: publicKey,
			},
		}),
	);
}

export async function listDevices(): Promise<{ devices: PairedDevice[] }> {
	return readJson(await shadowFetch("/devices"));
}

export async function deleteDevice(deviceId: string): Promise<void> {
	await shadowFetch(`/devices/${encodeURIComponent(deviceId)}`, {
		method: "DELETE",
	});
}

export async function listApprovals(
	status?: string,
): Promise<ApprovalsResponse> {
	const query = status ? `?status=${encodeURIComponent(status)}` : "";
	return readJson<ApprovalsResponse>(
		await shadowFetch(`/approvals${query}`),
	);
}

export async function approveApproval(id: string): Promise<ApprovalRequest> {
	return readJson<ApprovalRequest>(
		await shadowFetch(`/approvals/${encodeURIComponent(id)}/approve`, {
			method: "POST",
			body: {},
		}),
	);
}

export async function denyApproval(
	id: string,
	reason?: string,
): Promise<ApprovalRequest> {
	return readJson<ApprovalRequest>(
		await shadowFetch(`/approvals/${encodeURIComponent(id)}/deny`, {
			method: "POST",
			body: reason ? { reason } : {},
		}),
	);
}

export async function sweepApprovals(): Promise<ApprovalsResponse> {
	return readJson<ApprovalsResponse>(
		await shadowFetch("/approvals/sweep", { method: "POST", body: {} }),
	);
}

export async function askAgent(prompt: string): Promise<AskAgentResponse> {
	return readJson<AskAgentResponse>(
		await shadowFetch("/agent/ask", { method: "POST", body: { prompt } }),
	);
}

export interface AskAgentStreamCallbacks {
	onDelta: (delta: string) => void;
	onDone: (result: { answer: string }) => void;
	onError: (error: Error) => void;
}

interface StreamEnvelope {
	type?: string;
	properties?: Record<string, unknown>;
}

/**
 * Streaming agent request over XMLHttpRequest (fetch has no streaming body
 * access in React Native). Parses `data:` SSE lines into envelopes and calls
 * back on agent.message.delta / agent.message.done. Resolves with a cancel
 * function that aborts the stream.
 */
export async function askAgentStream(
	prompt: string,
	callbacks: AskAgentStreamCallbacks,
): Promise<() => void> {
	const path = "/agent/ask_stream";
	const base = getBaseUrl();
	const { deviceId, deviceSecret } = useConnectionStore.getState();
	if (!deviceId || !deviceSecret) {
		throw new ShadowApiError("Not paired with a SHADOW node", 0);
	}
	const bodyString = JSON.stringify({ prompt });
	const signed = await authHeaders({
		deviceId,
		secret: deviceSecret,
		method: "POST",
		path,
		body: bodyString,
	});

	return new Promise<() => void>((resolve, reject) => {
		const xhr = new XMLHttpRequest();
		let seenLength = 0;
		let finished = false;

		const finishWithError = (error: Error) => {
			if (finished) return;
			finished = true;
			callbacks.onError(error);
		};

		const handleLine = (line: string) => {
			const trimmed = line.trim();
			if (!trimmed.startsWith("data:")) return;
			const payload = trimmed.slice("data:".length).trim();
			if (payload.length === 0 || payload === "[DONE]") return;
			let envelope: StreamEnvelope;
			try {
				envelope = JSON.parse(payload) as StreamEnvelope;
			} catch {
				return;
			}
			if (envelope.type === "agent.message.delta") {
				const delta = envelope.properties?.["delta"];
				if (typeof delta === "string") {
					callbacks.onDelta(delta);
				}
			} else if (envelope.type === "agent.message.done") {
				if (finished) return;
				finished = true;
				const answer = envelope.properties?.["answer"];
				callbacks.onDone({
					answer: typeof answer === "string" ? answer : "",
				});
			}
		};

		xhr.open("POST", `${base}${path}`);
		for (const [key, value] of Object.entries(signed)) {
			xhr.setRequestHeader(key, value);
		}
		xhr.setRequestHeader("Content-Type", "application/json");
		xhr.setRequestHeader("Accept", "text/event-stream");

		xhr.onprogress = () => {
			try {
				const text = xhr.responseText ?? "";
				const chunk = text.slice(seenLength);
				seenLength = text.length;
				for (const line of chunk.split("\n")) {
					handleLine(line);
				}
			} catch {
				// Never let a parse hiccup kill the stream.
			}
		};

		xhr.onerror = () => {
			finishWithError(
				new ShadowApiError(
					"The stream connection failed.",
					xhr.status || 0,
				),
			);
		};

		xhr.onload = () => {
			if (finished) return;
			if (xhr.status >= 200 && xhr.status < 300) {
				finishWithError(
					new ShadowApiError("The stream ended without a result.", xhr.status),
				);
			} else {
				const text = xhr.responseText ?? "";
				finishWithError(
					new ShadowApiError(friendlyError(xhr.status, text), xhr.status, text),
				);
			}
		};

		try {
			xhr.send(bodyString);
		} catch (error) {
			reject(
				error instanceof Error ? error : new Error("Failed to start the stream."),
			);
			return;
		}

		resolve(() => {
			finished = true;
			xhr.abort();
		});
	});
}

/* ------------------------------------------------------------------ */
/* Ambient surfaces (PR #21 node verification, PR #23 GHOST ambient).  */
/* Used by the Briefing tab. All requests go through the HMAC-signed   */
/* shadowFetch like every other node endpoint.                         */
/* ------------------------------------------------------------------ */

export interface ExecutionSummary {
	execution_id: string;
	intent?: string;
	tool_name?: string;
	verification?: "VERIFIED" | "FAILED" | "UNCERTAIN" | "CONFLICTING" | string;
	started_at?: string;
	[key: string]: unknown;
}

export interface AmbientRun {
	run_id: string;
	objective?: string;
	status?: string;
	started_at?: string;
	steps_total?: number;
	steps_done?: number;
	[key: string]: unknown;
}

export interface AmbientStatus {
	config?: {
		enabled?: boolean;
		interval_seconds?: number;
		stealth_mode?: boolean;
		[key: string]: unknown;
	};
	tasks_available?: string[];
	background_running?: boolean;
	[key: string]: unknown;
}

export interface Claim {
	claim_id: string;
	statement?: string;
	status?: "unconfirmed" | "confirmed" | "refuted" | string;
	run_id?: string | null;
	[key: string]: unknown;
}

export async function listExecutions(limit = 20): Promise<ExecutionSummary[]> {
	return readJson<ExecutionSummary[]>(
		await shadowFetch(`/executions?limit=${encodeURIComponent(limit)}`),
	);
}

export async function getAmbientStatus(): Promise<AmbientStatus> {
	return readJson<AmbientStatus>(await shadowFetch("/ambient/status"));
}

export async function listAmbientRuns(limit = 20): Promise<AmbientRun[]> {
	return readJson<AmbientRun[]>(
		await shadowFetch(`/ambient/runs?limit=${encodeURIComponent(limit)}`),
	);
}

export async function listClaims(
	status?: "unconfirmed" | "confirmed" | "refuted",
): Promise<Claim[]> {
	const query = status ? `?status=${encodeURIComponent(status)}` : "";
	return readJson<Claim[]>(await shadowFetch(`/claims${query}`));
}

const CLAIM_DECISION_EVIDENCE = "Decided by the user in the SHADOW app.";

/** Confirm a world-state claim. The node moves it out of "unconfirmed". */
export async function confirmClaim(claimId: string): Promise<Claim> {
	return readJson<Claim>(
		await shadowFetch(`/claims/${encodeURIComponent(claimId)}/confirm`, {
			method: "POST",
			body: { evidence: CLAIM_DECISION_EVIDENCE },
		}),
	);
}

/** Refute a world-state claim. The node moves it out of "unconfirmed". */
export async function refuteClaim(claimId: string): Promise<Claim> {
	return readJson<Claim>(
		await shadowFetch(`/claims/${encodeURIComponent(claimId)}/refute`, {
			method: "POST",
			body: { evidence: CLAIM_DECISION_EVIDENCE },
		}),
	);
}
