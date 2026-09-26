import * as Linking from "expo-linking";
import * as Notifications from "expo-notifications";

import { useApprovalsStore } from "@/stores/useApprovalsStore";
import {
	APPROVAL_ACTION_APPROVE,
	APPROVAL_ACTION_DENY,
	APPROVAL_CATEGORY_ID,
	approvalDeepLink,
	approvalIdFromData,
	decisionForActionIdentifier,
} from "./approvalNotificationRouting";

/**
 * Rich approval notifications: Approve / Deny action buttons on the push,
 * decided without opening the app; a body tap deep-links to the approval
 * detail screen.
 *
 * Node push-payload contract (see `_notify_approval_created` in the Shadow
 * Node): the Expo push message must carry
 *   categoryId: "shadow.approval"
 *   data: { type: "approval.created", approval_id: "<id>" }
 * so the buttons render and the response routes to the right approval.
 *
 * Everything here is defensive: category setup and response handling never
 * throw, because a notification tap must never crash the app.
 */

/**
 * Register the approval category with Approve / Deny actions. Call once at
 * app launch (and after pairing); safe to call repeatedly.
 */
export async function setupApprovalNotificationCategories(): Promise<void> {
	try {
		await Notifications.setNotificationCategoryAsync(APPROVAL_CATEGORY_ID, [
			{
				identifier: APPROVAL_ACTION_APPROVE,
				buttonTitle: "Approve",
				options: { opensAppToForeground: false },
			},
			{
				identifier: APPROVAL_ACTION_DENY,
				buttonTitle: "Deny",
				options: { opensAppToForeground: false, isDestructive: true },
			},
		]);
	} catch {
		// Best-effort: without the category the notification still opens
		// the app on tap, it just has no action buttons.
	}
}

/**
 * Start routing notification responses. Returns the subscription; call
 * `.remove()` on unmount. Safe to start once at app launch.
 *
 * Also drains the cold-start response: when a notification tap launches a
 * terminated app, the response may already be delivered before this listener
 * registers, so `getLastNotificationResponseAsync()` is checked too.
 * Responses are deduplicated by notification request id.
 */
export function startApprovalNotificationResponses(): {
	remove: () => void;
} {
	const handled = new Set<string>();

	const handleResponse = async (response: {
		actionIdentifier: string;
		notification: { request: { identifier: string; content: { data: unknown } } };
	}) => {
		try {
			const requestId = response.notification.request.identifier;
			if (handled.has(requestId)) return;
			handled.add(requestId);

			const approvalId = approvalIdFromData(
				response.notification.request.content.data,
			);
			if (!approvalId) {
				return;
			}
			const decision = decisionForActionIdentifier(response.actionIdentifier);
			if (decision) {
				// Decided from the notification shade; the store applies the
				// optimistic update and reconciles with the node. On a cold
				// start the store may not have loaded approvals yet, so
				// refresh first (best-effort; decide() is a safe no-op when
				// the approval is unknown or already decided).
				try {
					await useApprovalsStore.getState().fetchApprovals();
				} catch {
					// Offline or unpaired: decide() still no-ops safely.
				}
				await useApprovalsStore.getState().decide(approvalId, decision);
				return;
			}
			await Linking.openURL(approvalDeepLink(approvalId));
		} catch {
			// A notification tap must never crash the app.
		}
	};

	const subscription =
		Notifications.addNotificationResponseReceivedListener((response) => {
			void handleResponse(response);
		});

	// Cold start: route the response that launched the app, if any.
	void (async () => {
		try {
			const last = await Notifications.getLastNotificationResponseAsync();
			if (last) {
				await handleResponse(last);
			}
		} catch {
			// No launch response; normal start.
		}
	})();

	return subscription;
}
