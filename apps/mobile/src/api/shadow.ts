/**
 * Typed SHADOW node client used by all screens.
 * Auth: HMAC-SHA256 per request (see @/lib/shadowSigner).
 */

import { authHeaders, randomHexBytes } from "@/lib/shadowSigner";
import { useConnectionStore } from "@/stores/useConnectionStore";
import * as FileSystem from "expo-file-system/legacy";

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

export interface Page<T> {
	items: T[];
	count: number;
	next_cursor: string | null;
}

export interface ApprovalsResponse extends Page<ApprovalRequest> {}

export interface DevicesResponse extends Page<PairedDevice> {}

export interface SweepResponse {
	expired: string[];
	remaining_pending: number;
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

export async function listDevices(): Promise<DevicesResponse> {
	return readJson(await shadowFetch("/devices"));
}

export async function revokeDevice(deviceId: string): Promise<{ revoked: string }> {
	return readJson(
		await shadowFetch(`/devices/${encodeURIComponent(deviceId)}/revoke`, {
			method: "POST",
			body: {},
		}),
	);
}

/** @deprecated Use revokeDevice. Kept as an alias during the contract migration. */
export async function deleteDevice(deviceId: string): Promise<void> {
	await revokeDevice(deviceId);
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

export async function sweepApprovals(): Promise<SweepResponse> {
	return readJson<SweepResponse>(
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

export interface PersonaProfile {
	name: string;
	avatar_emoji: string;
	vibe: string;
	status: string;
	updated_at: number;
}

export interface PersonaUpdate {
	name?: string;
	avatar_emoji?: string;
	vibe?: string;
	status?: string;
}

/** The assistant's Cookie-style identity, stored on the node. */
export async function getPersona(): Promise<PersonaProfile> {
	return readJson<PersonaProfile>(await shadowFetch("/persona"));
}

/** Update the assistant's identity. The vibe takes effect immediately. */
export async function updatePersona(patch: PersonaUpdate): Promise<PersonaProfile> {
	return readJson<PersonaProfile>(
		await shadowFetch("/persona", { method: "PUT", body: patch }),
	);
}

export interface MemorySourceRef {
	id: string;
	kind: string;
	title: string;
}

export interface MemoryItem {
	id: string;
	type: string;
	category: string;
	text: string;
	source: MemorySourceRef;
	tags: string[];
	confidence: number;
	sensitive: boolean;
	created_at: string;
	updated_at: string;
}

export interface MemoryRecentResponse {
	items: MemoryItem[];
	count: number;
	total: number;
	limit: number;
	offset: number;
}

export interface MemorySearchResult {
	item: MemoryItem;
	score: number;
	freshness: number;
	attribution: string;
	explanation: string;
}

/** Newest-first memory cards for the Memory screen. */
export async function getMemoryRecent(
	limit = 20,
	offset = 0,
): Promise<MemoryRecentResponse> {
	return readJson<MemoryRecentResponse>(
		await shadowFetch(
			`/memory/recent?limit=${encodeURIComponent(limit)}&offset=${encodeURIComponent(offset)}`,
		),
	);
}

/** Semantic (blind-index FTS) search over memory. Sensitive items excluded. */
export async function searchMemory(
	q: string,
	limit = 10,
): Promise<MemorySearchResult[]> {
	return readJson<MemorySearchResult[]>(
		await shadowFetch(
			`/memory/search?q=${encodeURIComponent(q)}&limit=${encodeURIComponent(limit)}`,
		),
	);
}

/** Store a new memory from free text. Returns the created item(s). */
export async function ingestMemory(text: string): Promise<MemoryItem[]> {
	const body = await readJson<{ items: MemoryItem[] }>(
		await shadowFetch("/memory/ingest", {
			method: "POST",
			body: { text, source_kind: "manual", source_title: "Note" },
		}),
	);
	return body.items;
}

/** Revoke one memory item. */
export async function deleteMemoryItem(id: string): Promise<void> {
	await shadowFetch(`/memory/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export type GoalStatus = "active" | "completed" | "abandoned";

export interface Goal {
	id: string;
	title: string;
	description: string;
	status: GoalStatus;
	target_date: string | null;
	created_at: number;
	updated_at: number;
}

export interface GoalSummary extends Goal {
	entry_count: number;
	latest_percent: number | null;
	last_progress_at: number | null;
}

export interface ProgressEntry {
	id: string;
	goal_id: string;
	note: string;
	percent: number | null;
	created_at: number;
}

export interface GoalDetail extends Goal {
	entries: ProgressEntry[];
}

export interface BriefingEntry extends ProgressEntry {
	goal_title: string;
}

export interface GoalsBriefing {
	generated_at: number;
	active_count: number;
	completed_count: number;
	stale: GoalSummary[];
	due_soon: GoalSummary[];
	overdue: GoalSummary[];
	completed_this_week: GoalSummary[];
	recent_entries: BriefingEntry[];
}

export interface GoalCreate {
	title: string;
	description?: string;
	target_date?: string | null;
}

export interface GoalUpdate {
	title?: string;
	description?: string;
	status?: GoalStatus;
	target_date?: string | null;
}

/** List goals newest-updated first, each with a progress roll-up. */
export async function listGoals(status?: GoalStatus): Promise<GoalSummary[]> {
	const q = status ? `?status=${encodeURIComponent(status)}` : "";
	return readJson<GoalSummary[]>(await shadowFetch(`/goals${q}`));
}

/** Create a goal. */
export async function createGoal(data: GoalCreate): Promise<Goal> {
	return readJson<Goal>(
		await shadowFetch("/goals", { method: "POST", body: data }),
	);
}

/** Goal detail with progress entries, newest first. */
export async function getGoal(id: string): Promise<GoalDetail> {
	return readJson<GoalDetail>(
		await shadowFetch(`/goals/${encodeURIComponent(id)}`),
	);
}

/** Update title/description/status/target_date. */
export async function updateGoal(id: string, patch: GoalUpdate): Promise<Goal> {
	return readJson<Goal>(
		await shadowFetch(`/goals/${encodeURIComponent(id)}`, {
			method: "PATCH",
			body: patch,
		}),
	);
}

/** Delete a goal and its progress entries. */
export async function deleteGoal(id: string): Promise<void> {
	await shadowFetch(`/goals/${encodeURIComponent(id)}`, { method: "DELETE" });
}

/** Log a progress entry on a goal. */
export async function logGoalProgress(
	id: string,
	note: string,
	percent?: number | null,
): Promise<ProgressEntry> {
	return readJson<ProgressEntry>(
		await shadowFetch(`/goals/${encodeURIComponent(id)}/progress`, {
			method: "POST",
			body: { note, percent: percent ?? null },
		}),
	);
}

/** Goal briefing: stale, due soon, overdue, completed this week, recent progress. */
export async function getGoalsBriefing(): Promise<GoalsBriefing> {
	return readJson<GoalsBriefing>(await shadowFetch("/goals/briefing"));
}

export type FeedKind = "morning_brief" | "goals_briefing" | "memory_digest";

export interface FeedUnit {
	id: string;
	kind: FeedKind;
	title: string;
	body: string;
	created_at: number;
}

export interface FeedPage {
	items: FeedUnit[];
	count: number;
	total: number;
	limit: number;
	offset: number;
}

export type IdeaStatus = "new" | "running" | "done" | "dismissed";

export interface PlannedAction {
	description: string;
	requires_approval: boolean;
}

export interface Idea {
	id: string;
	title: string;
	description: string;
	status: IdeaStatus;
	plan: PlannedAction[];
	created_at: number;
	updated_at: number;
}

/** Feed units newest-first, paginated. */
export async function listFeed(limit = 20, offset = 0): Promise<FeedPage> {
	return readJson<FeedPage>(
		await shadowFetch(`/feed?limit=${limit}&offset=${offset}`),
	);
}

/** Generate editorial units now. Empty kinds = all; force bypasses the per-kind dedupe. */
export async function generateFeed(
	kinds: FeedKind[] = [],
	force = false,
): Promise<{ units: FeedUnit[]; count: number }> {
	return readJson<{ units: FeedUnit[]; count: number }>(
		await shadowFetch("/feed/generate", { method: "POST", body: { kinds, force } }),
	);
}

/** List idea cards newest-updated first. */
export async function listIdeas(status?: IdeaStatus): Promise<Idea[]> {
	const q = status ? `?status=${encodeURIComponent(status)}` : "";
	return readJson<Idea[]>(await shadowFetch(`/ideas${q}`));
}

/** Create an idea card. */
export async function createIdea(title: string, description?: string): Promise<Idea> {
	return readJson<Idea>(
		await shadowFetch("/ideas", { method: "POST", body: { title, description: description ?? "" } }),
	);
}

/** Update an idea card. */
export async function updateIdea(
	id: string,
	patch: { title?: string; description?: string; status?: IdeaStatus },
): Promise<Idea> {
	return readJson<Idea>(
		await shadowFetch(`/ideas/${encodeURIComponent(id)}`, { method: "PATCH", body: patch }),
	);
}

/** Delete an idea card. */
export async function deleteIdea(id: string): Promise<void> {
	await shadowFetch(`/ideas/${encodeURIComponent(id)}`, { method: "DELETE" });
}

/** Turn an idea into an agent plan. Risky actions raise approvals; nothing executes here. */
export async function runIdea(
	id: string,
): Promise<{ idea: Idea; plan: { actions: PlannedAction[] } }> {
	return readJson<{ idea: Idea; plan: { actions: PlannedAction[] } }>(
		await shadowFetch(`/ideas/${encodeURIComponent(id)}/run`, { method: "POST" }),
	);
}

/* Reminders + quiet hours (Phase 5). All requests go through the      */
/* HMAC-signed shadowFetch like every other node endpoint.             */
/* ------------------------------------------------------------------- */

export type ReminderRecurrence = "none" | "daily" | "weekly";
export type ReminderStatus = "pending" | "fired" | "dismissed";

export interface Reminder {
	id: string;
	title: string;
	note: string;
	due_at: number;
	recurrence: ReminderRecurrence;
	status: ReminderStatus;
	last_fired_at: number | null;
	created_at: number;
	updated_at: number;
}

/** Create a reminder. dueAt is a unix timestamp (seconds). */
export async function createReminder(
	title: string,
	dueAt: number,
	note?: string,
	recurrence: ReminderRecurrence = "none",
): Promise<Reminder> {
	return readJson<Reminder>(
		await shadowFetch("/reminders", {
			method: "POST",
			body: { title, due_at: dueAt, note: note ?? "", recurrence },
		}),
	);
}

/** List reminders, soonest-due first. */
export async function listReminders(status?: ReminderStatus): Promise<Reminder[]> {
	const q = status ? `?status=${encodeURIComponent(status)}` : "";
	return readJson<Reminder[]>(await shadowFetch(`/reminders${q}`));
}

/** Pending reminders whose due time has passed. */
export async function dueReminders(): Promise<Reminder[]> {
	return readJson<Reminder[]>(await shadowFetch("/reminders/due"));
}

/** Update a reminder. */
export async function updateReminder(
	id: string,
	patch: {
		title?: string;
		note?: string;
		due_at?: number;
		recurrence?: ReminderRecurrence;
		status?: ReminderStatus;
	},
): Promise<Reminder> {
	return readJson<Reminder>(
		await shadowFetch(`/reminders/${encodeURIComponent(id)}`, {
			method: "PATCH",
			body: patch,
		}),
	);
}

/** Delete a reminder. */
export async function deleteReminder(id: string): Promise<void> {
	await shadowFetch(`/reminders/${encodeURIComponent(id)}`, { method: "DELETE" });
}

/** Fire due reminders now. During quiet hours nothing fires; held ids are reported. */
export async function checkReminders(): Promise<{
	fired: Reminder[];
	held: string[];
	quiet: boolean;
}> {
	return readJson<{ fired: Reminder[]; held: string[]; quiet: boolean }>(
		await shadowFetch("/reminders/check", { method: "POST" }),
	);
}

export interface AmbientConfigPatch {
	enabled?: boolean;
	interval_seconds?: number;
	stealth_mode?: boolean;
	tasks?: string[];
	quiet_start?: string;
	quiet_end?: string;
}

/** Update the ambient scheduler config (incl. quiet hours as HH:MM; "" clears). */
export async function configureAmbient(
	patch: AmbientConfigPatch,
): Promise<AmbientStatus["config"]> {
	return readJson<AmbientStatus["config"]>(
		await shadowFetch("/ambient/config", { method: "POST", body: patch }),
	);
}

/* ------------------------------------------------------------------ */
/* Artifacts, voice, media (Phase 6). All requests go through the      */
/* HMAC-signed shadowFetch like every other node endpoint.             */
/* ------------------------------------------------------------------ */

export type ArtifactKind =
	| "markdown"
	| "html"
	| "code"
	| "csv"
	| "json"
	| "text";

export interface ArtifactSummary {
	id: string;
	title: string;
	kind: ArtifactKind;
	version: number;
	tags: string[];
	created_at: number;
	updated_at: number;
	size_bytes: number;
}

export interface Artifact extends ArtifactSummary {
	content: string;
}

export interface ArtifactListResponse {
	artifacts: ArtifactSummary[];
	total: number;
}

export interface ArtifactVersion {
	version: number;
	created_at: number;
	size_bytes: number;
}

export interface ArtifactCreate {
	title: string;
	kind: ArtifactKind;
	content: string;
	tags?: string[];
}

export interface ArtifactPatch {
	title?: string;
	kind?: ArtifactKind;
	content?: string;
}

/** List artifacts newest-first, optionally filtered by kind. */
export async function listArtifacts(
	limit = 20,
	offset = 0,
	kind?: ArtifactKind,
): Promise<ArtifactListResponse> {
	const q = new URLSearchParams({ limit: String(limit), offset: String(offset) });
	if (kind) q.set("kind", kind);
	return readJson<ArtifactListResponse>(await shadowFetch(`/artifacts?${q}`));
}

/** Create an artifact. */
export async function createArtifact(data: ArtifactCreate): Promise<Artifact> {
	return readJson<Artifact>(
		await shadowFetch("/artifacts", { method: "POST", body: data }),
	);
}

/** Fetch one artifact with its full content. */
export async function getArtifact(id: string): Promise<Artifact> {
	return readJson<Artifact>(
		await shadowFetch(`/artifacts/${encodeURIComponent(id)}`),
	);
}

/** Update title/kind/content; bumps the version. */
export async function updateArtifact(
	id: string,
	patch: ArtifactPatch,
): Promise<Artifact> {
	return readJson<Artifact>(
		await shadowFetch(`/artifacts/${encodeURIComponent(id)}`, {
			method: "PATCH",
			body: patch,
		}),
	);
}

/** Version history for an artifact. */
export async function listArtifactVersions(
	id: string,
): Promise<{ versions: ArtifactVersion[] }> {
	return readJson<{ versions: ArtifactVersion[] }>(
		await shadowFetch(`/artifacts/${encodeURIComponent(id)}/versions`),
	);
}

/** Fetch the artifact as it was at a specific version. */
export async function getArtifactVersion(
	id: string,
	version: number,
): Promise<Artifact> {
	return readJson<Artifact>(
		await shadowFetch(
			`/artifacts/${encodeURIComponent(id)}/versions/${encodeURIComponent(version)}`,
		),
	);
}

/** Delete an artifact. */
export async function deleteArtifact(id: string): Promise<void> {
	await shadowFetch(`/artifacts/${encodeURIComponent(id)}`, {
		method: "DELETE",
	});
}

export interface VoiceCapability {
	available: boolean;
	provider: string | null;
	note: string;
}

export interface VoiceCapabilities {
	tts: VoiceCapability;
	stt: VoiceCapability;
}

export interface MediaCapabilities {
	generate: VoiceCapability;
}

export type VoiceAudioFormat = "mp3" | "wav";

/** What the node can do with voice right now. */
export async function getVoiceCapabilities(): Promise<VoiceCapabilities> {
	return readJson<VoiceCapabilities>(await shadowFetch("/voice/capabilities"));
}

/** What the node can do with media generation right now. */
export async function getMediaCapabilities(): Promise<MediaCapabilities> {
	return readJson<MediaCapabilities>(await shadowFetch("/media/capabilities"));
}

export interface TranscribeResult {
	text: string;
	language?: string;
}

/**
 * Send a recorded audio file for transcription. The audio travels as
 * base64 inside a JSON body: binary-safe for both the HMAC signature and
 * the wire, unlike multipart (see the node's _canonical_body). Throws
 * ShadowApiError with status 503 when the node has no STT provider
 * configured.
 */
export async function transcribeAudio(
	fileUri: string,
	mimeType = "audio/m4a",
): Promise<TranscribeResult> {
	const info = await FileSystem.getInfoAsync(fileUri);
	if (!info.exists) {
		throw new ShadowApiError("Recording not found. Try recording again.", 0);
	}
	const audioBase64 = await FileSystem.readAsStringAsync(fileUri, {
		encoding: FileSystem.EncodingType.Base64,
	});
	const filename = fileUri.split("/").pop() || "recording.m4a";
	return readJson<TranscribeResult>(
		await shadowFetch("/voice/transcribe", {
			method: "POST",
			body: { audio_base64: audioBase64, filename, mime_type: mimeType },
		}),
	);
}

export type MediaSize = "1024x1024" | "1792x1024" | "1024x1792";

export interface GeneratedMedia {
	id: string;
	prompt: string;
	size: MediaSize;
	mime: string;
	created_at: number;
	bytes: number;
}

export interface MediaListResponse {
	items: GeneratedMedia[];
	total: number;
}

/** Generate an image on the node. 503 when no image provider is configured. */
export async function generateMedia(
	prompt: string,
	size: MediaSize = "1024x1024",
): Promise<GeneratedMedia> {
	return readJson<GeneratedMedia>(
		await shadowFetch("/media/generate", {
			method: "POST",
			body: { prompt, size },
		}),
	);
}

/** List generated images newest-first. */
export async function listMedia(
	limit = 30,
	offset = 0,
): Promise<MediaListResponse> {
	return readJson<MediaListResponse>(
		await shadowFetch(`/media?limit=${limit}&offset=${offset}`),
	);
}

/** Delete a generated image. */
export async function deleteMedia(id: string): Promise<void> {
	await shadowFetch(`/media/${encodeURIComponent(id)}`, { method: "DELETE" });
}

/**
 * Authenticated binary download helper: computes the HMAC headers for a
 * GET and hands the caller the base URL plus headers, so expo-file-system
 * can download straight to disk. Used for /voice/speak and
 * /media/{id}/content responses.
 */
export async function authedDownloadParams(
	path: string,
): Promise<{ url: string; headers: Record<string, string> }> {
	const base = getBaseUrl();
	const signPath = path.split("?")[0];
	const { deviceId, deviceSecret } = useConnectionStore.getState();
	if (!deviceId || !deviceSecret) {
		throw new ShadowApiError("Not paired with a SHADOW node", 0);
	}
	const headers = await authHeaders({
		deviceId,
		secret: deviceSecret,
		method: "GET",
		path: signPath,
		body: "",
	});
	return { url: `${base}${path}`, headers };
}

/** Binary endpoint result: raw bytes plus the response content type. */
export interface BinaryResponse {
	data: ArrayBuffer;
	contentType: string;
}

async function readBinary(response: Response): Promise<BinaryResponse> {
	const data = await response.arrayBuffer();
	const contentType =
		response.headers.get("content-type") ?? "application/octet-stream";
	return { data, contentType };
}

/**
 * POST /voice/speak: synthesize speech on the node.
 * 503 when no TTS provider is configured.
 */
export async function synthesizeSpeech(
	text: string,
	voice?: string,
	format: VoiceAudioFormat = "mp3",
): Promise<BinaryResponse> {
	return readBinary(await shadowFetch("/voice/speak", {
		method: "POST",
		body: { text, voice, format },
	}));
}

/**
 * GET /media/{id}/content: raw bytes of a generated image.
 */
export async function getMediaContent(id: string): Promise<BinaryResponse> {
	return readBinary(
		await shadowFetch(`/media/${encodeURIComponent(id)}/content`),
	);
}
