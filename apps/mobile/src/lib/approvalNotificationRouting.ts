/**
 * Pure routing logic for rich approval notifications. No Expo imports here
 * so this module stays unit-testable in plain node; the Expo wiring lives
 * in `./approvalNotifications`.
 */

/** Notification category the node attaches to routine approval pushes
 * (Approve / Deny buttons on the notification). */
export const APPROVAL_CATEGORY_ID = "shadow.approval";

/** Category for approvals with real consequences (browser steps, sends,
 * irreversible or high-risk actions): a single Review button that opens
 * the app, so the full card is seen before deciding. */
export const APPROVAL_REVIEW_CATEGORY_ID = "shadow.approval.review";
export const APPROVAL_ACTION_REVIEW = "shadow.approval.review.open";

/** Action identifiers for the Approve / Deny buttons. */
export const APPROVAL_ACTION_APPROVE = "shadow.approval.approve";
export const APPROVAL_ACTION_DENY = "shadow.approval.deny";

/** Deep-link scheme and route for the approval detail screen. */
export const APPROVAL_DEEP_LINK_SCHEME = "shadow";
export const APPROVAL_DEEP_LINK_PATH = "approvals";

/**
 * Extract the approval id from a notification's data payload. Pure.
 * Returns null when the payload is missing or malformed.
 */
export function approvalIdFromData(data: unknown): string | null {
	if (!data || typeof data !== "object") {
		return null;
	}
	const id = (data as Record<string, unknown>)["approval_id"];
	return typeof id === "string" && id.length > 0 ? id : null;
}

/**
 * Map a tapped notification action identifier to an approval decision.
 * Pure. Returns null for the default body tap and unknown actions, which
 * route to the approval detail screen instead.
 */
export function decisionForActionIdentifier(
	actionIdentifier: string,
): "approve" | "deny" | null {
	if (actionIdentifier === APPROVAL_ACTION_APPROVE) {
		return "approve";
	}
	if (actionIdentifier === APPROVAL_ACTION_DENY) {
		return "deny";
	}
	return null;
}

/** Deep-link URL that opens the approval detail screen. Pure. */
export function approvalDeepLink(approvalId: string): string {
	return `${APPROVAL_DEEP_LINK_SCHEME}://${APPROVAL_DEEP_LINK_PATH}/${encodeURIComponent(approvalId)}`;
}

/**
 * Reminder notifications: the node sends pushes with
 *   data: { type: "reminder.fired", reminder_id: "<id>" }
 * (see `_notify_proactive` / `fire_due` in the Shadow Node). Tapping one
 * deep-links to the Feed tab's Reminders segment.
 */

/** Deep-link URL that opens the Feed tab (Reminders live there). */
export const REMINDER_DEEP_LINK = `${APPROVAL_DEEP_LINK_SCHEME}://feed`;

/** Browser task pushes: data { type: "browser.task", task_id, event }. */
export function browserTaskIdFromData(data: unknown): string | null {
	if (!data || typeof data !== "object") {
		return null;
	}
	const d = data as Record<string, unknown>;
	if (d["type"] !== "browser.task") return null;
	const id = d["task_id"];
	return typeof id === "string" && id.length > 0 ? id : null;
}

/** Deep link to a browser task's live view. Pure. */
export function browserTaskDeepLink(taskId: string): string {
	return `${APPROVAL_DEEP_LINK_SCHEME}://browser/${encodeURIComponent(taskId)}`;
}

/** True when a notification's data payload is a fired-reminder push. Pure. */
export function isReminderNotification(data: unknown): boolean {
	if (!data || typeof data !== "object") {
		return false;
	}
	return (data as Record<string, unknown>)["type"] === "reminder.fired";
}
