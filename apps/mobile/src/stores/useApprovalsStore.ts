import { create } from "zustand";
import {
	approveApproval,
	denyApproval,
	listApprovals,
	type ApprovalRequest,
} from "@/api/shadow";
import type { ShadowEvent } from "@/hooks/useShadowEventStream";

interface ApprovalsState {
	/** All known approvals: pending (sorted by expiry) plus decided items kept for context. */
	approvals: ApprovalRequest[];
	/** True on the first load while nothing is shown yet. */
	loading: boolean;
	/** True on pull-to-refresh / foreground refreshes. */
	refreshing: boolean;
	/** Last human-readable failure, if any. */
	error: string | null;
	/** Epoch ms of the last successful fetch. */
	lastUpdated: number | null;
}

interface ApprovalsActions {
	/** Fetch pending approvals from the node and merge with decided items we already know. */
	fetchApprovals: () => Promise<void>;
	/** Apply a stream event (approval.created / approval.updated). */
	applyEvent: (event: ShadowEvent) => void;
	/**
	 * Decide an approval optimistically: update the row immediately, call the
	 * node API, reconcile with the returned approval, roll back on error.
	 */
	decide: (
		id: string,
		decision: "approve" | "deny",
		reason?: string,
	) => Promise<void>;
	clearError: () => void;
}

type ApprovalsStore = ApprovalsState & ApprovalsActions;

function toTimestamp(value: string | null | undefined): number {
	if (!value) return Number.POSITIVE_INFINITY;
	const parsed = Date.parse(value);
	return Number.isNaN(parsed) ? Number.POSITIVE_INFINITY : parsed;
}

function toDecidedTimestamp(value: string | null | undefined): number {
	if (!value) return 0;
	const parsed = Date.parse(value);
	return Number.isNaN(parsed) ? 0 : parsed;
}

/** Pending approvals first (soonest expiry on top), then decided (newest first). */
function sortApprovals(approvals: ApprovalRequest[]): ApprovalRequest[] {
	return [...approvals].sort((a, b) => {
		const aPending = a.status === "pending";
		const bPending = b.status === "pending";
		if (aPending && bPending) {
			return toTimestamp(a.expires_at) - toTimestamp(b.expires_at);
		}
		if (aPending) return -1;
		if (bPending) return 1;
		return toDecidedTimestamp(b.decided_at) - toDecidedTimestamp(a.decided_at);
	});
}

function messageOf(error: unknown): string {
	if (error instanceof Error && error.message) {
		return error.message;
	}
	return "Something went wrong. Please try again.";
}

export const useApprovalsStore = create<ApprovalsStore>((set, get) => ({
	approvals: [],
	loading: false,
	refreshing: false,
	error: null,
	lastUpdated: null,

	fetchApprovals: async () => {
		const hasContent = get().approvals.length > 0;
		set(
			hasContent
				? { refreshing: true, error: null }
				: { loading: true, error: null },
		);

		try {
			const { approvals: pending } = await listApprovals("pending");
			const pendingIds = new Set(pending.map((approval) => approval.id));
			// Keep decided items the node no longer lists so the inbox keeps
			// context after a refresh. Server data always wins on conflicts.
			const decided = get().approvals.filter(
				(approval) =>
					approval.status !== "pending" && !pendingIds.has(approval.id),
			);
			set({
				approvals: sortApprovals([...pending, ...decided]),
				loading: false,
				refreshing: false,
				error: null,
				lastUpdated: Date.now(),
			});
		} catch (error) {
			set({
				loading: false,
				refreshing: false,
				error: messageOf(error),
			});
		}
	},

	applyEvent: (event: ShadowEvent) => {
		if (event.type !== "approval.created" && event.type !== "approval.updated") {
			return;
		}
		const incoming = event.properties as ApprovalRequest | null;
		if (!incoming || typeof incoming.id !== "string") {
			return;
		}

		set((state) => {
			const exists = state.approvals.some(
				(approval) => approval.id === incoming.id,
			);
			const next = exists
				? state.approvals.map((approval) =>
						approval.id === incoming.id ? incoming : approval,
					)
				: [incoming, ...state.approvals];
			return { approvals: sortApprovals(next) };
		});
	},

	decide: async (id, decision, reason) => {
		const previous = get().approvals.find((approval) => approval.id === id);
		if (!previous || previous.status !== "pending") {
			return;
		}

		const now = new Date().toISOString();
		const optimisticStatus = decision === "approve" ? "approved" : "denied";

		set((state) => ({
			approvals: sortApprovals(
				state.approvals.map((approval) =>
					approval.id === id
						? {
								...approval,
								status: optimisticStatus,
								decided_at: now,
								deny_reason:
									decision === "deny" ? (reason ?? null) : approval.deny_reason,
							}
						: approval,
				),
			),
			error: null,
		}));

		try {
			const reconciled =
				decision === "approve"
					? await approveApproval(id)
					: await denyApproval(id, reason);
			set((state) => ({
				approvals: sortApprovals(
					state.approvals.map((approval) =>
						approval.id === id ? reconciled : approval,
					),
				),
			}));
		} catch (error) {
			set((state) => ({
				approvals: sortApprovals(
					state.approvals.map((approval) =>
						approval.id === id ? previous : approval,
					),
				),
				error: messageOf(error),
			}));
		}
	},

	clearError: () => {
		set({ error: null });
	},
}));
