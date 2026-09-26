/**
 * Pure routing logic for rich approval notifications. No Expo imports here
 * so this module stays unit-testable in plain node; the Expo wiring lives
 * in `./approvalNotifications`.
 */

/** Notification category the node attaches to approval pushes. */
export const APPROVAL_CATEGORY_ID = "shadow.approval";

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
