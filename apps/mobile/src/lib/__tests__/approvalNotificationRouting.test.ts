/**
 * Unit tests for approval notification routing (pure logic).
 *
 * Run: `npm run test:providers` (add the compiled file to
 * scripts/test-providers.sh) or compile with tsconfig.test.json and run
 * with `node --test`.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
	APPROVAL_ACTION_APPROVE,
	APPROVAL_ACTION_DENY,
	APPROVAL_CATEGORY_ID,
	approvalDeepLink,
	approvalIdFromData,
	decisionForActionIdentifier,
} from "../approvalNotificationRouting";

describe("approval notification routing", () => {
	it("exposes the category and action identifiers the node contract needs", () => {
		assert.equal(APPROVAL_CATEGORY_ID, "shadow.approval");
		assert.equal(APPROVAL_ACTION_APPROVE, "shadow.approval.approve");
		assert.equal(APPROVAL_ACTION_DENY, "shadow.approval.deny");
	});

	it("extracts the approval id from notification data", () => {
		assert.equal(
			approvalIdFromData({ type: "approval.created", approval_id: "abc-123" }),
			"abc-123",
		);
	});

	it("rejects missing or malformed payloads", () => {
		assert.equal(approvalIdFromData(null), null);
		assert.equal(approvalIdFromData(undefined), null);
		assert.equal(approvalIdFromData("abc-123"), null);
		assert.equal(approvalIdFromData({}), null);
		assert.equal(approvalIdFromData({ approval_id: 42 }), null);
		assert.equal(approvalIdFromData({ approval_id: "" }), null);
	});

	it("maps action identifiers to decisions", () => {
		assert.equal(decisionForActionIdentifier(APPROVAL_ACTION_APPROVE), "approve");
		assert.equal(decisionForActionIdentifier(APPROVAL_ACTION_DENY), "deny");
	});

	it("routes body taps and unknown actions to the detail screen", () => {
		assert.equal(decisionForActionIdentifier("expo.modules.notifications.DEFAULT_ACTION_IDENTIFIER"), null);
		assert.equal(decisionForActionIdentifier("something-else"), null);
	});

	it("builds the approval deep link", () => {
		assert.equal(approvalDeepLink("abc-123"), "shadow://approvals/abc-123");
		assert.equal(approvalDeepLink("a/b"), "shadow://approvals/a%2Fb");
	});
});
