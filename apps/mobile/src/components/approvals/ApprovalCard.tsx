import * as Haptics from "expo-haptics";
import { Pressable, Text, View } from "react-native";
import type { ApprovalRequest } from "@/api/shadow";
import { WarningIcon } from "@/components/icons";
import { ExpiryCountdown } from "./ExpiryCountdown";
import { RiskBadge } from "./RiskBadge";

interface ApprovalCardProps {
	approval: ApprovalRequest;
	onPress: () => void;
}

const statusPillClasses: Record<string, { container: string; text: string }> = {
	approved: { container: "bg-emerald-500/15 border-emerald-500/40", text: "text-emerald-400" },
	denied: { container: "bg-red-500/15 border-red-500/40", text: "text-red-400" },
	expired: { container: "bg-white/10 border-white/20", text: "text-white/50" },
};

const defaultStatusPill = {
	container: "bg-white/10 border-white/20",
	text: "text-white/50",
};

function StatusPill({ status }: { status: string }) {
	const classes = statusPillClasses[status] ?? defaultStatusPill;
	return (
		<View className={`rounded-full border px-2 py-0.5 ${classes.container}`}>
			<Text className={`text-[11px] font-semibold uppercase ${classes.text}`}>
				{status}
			</Text>
		</View>
	);
}

/**
 * Inbox row for one approval request: action summary, risk badge,
 * destructive warning, expiry countdown, and decided-state pill.
 */
export function ApprovalCard({ approval, onPress }: ApprovalCardProps) {
	const { action, risk_label, requires_double_confirmation } = approval;
	const headline = approval.action_preview?.trim() || action.description;
	const isPending = approval.status === "pending";

	const handlePress = () => {
		Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
		onPress();
	};

	return (
		<Pressable
			onPress={handlePress}
			accessibilityRole="button"
			accessibilityLabel={`Approval: ${headline}`}
			className="rounded-2xl border border-white/10 bg-white/5 p-4 active:bg-white/10"
		>
			<View className="flex-row items-start justify-between gap-2">
				<Text className="flex-1 text-[15px] font-semibold text-white" numberOfLines={2}>
					{headline}
				</Text>
				{isPending ? (
					<RiskBadge risk={action.risk} />
				) : (
					<StatusPill status={approval.status} />
				)}
			</View>

			<View className="mt-1.5 flex-row items-center gap-2">
				<Text className="text-xs text-white/50" numberOfLines={1}>
					{action.tool_name}
				</Text>
				{action.destructive && (
					<View className="flex-row items-center gap-1">
						<WarningIcon size={12} color="#f87171" />
						<Text className="text-xs font-semibold text-red-400">
							Destructive
						</Text>
					</View>
				)}
				{requires_double_confirmation && isPending && (
					<Text className="text-xs text-amber-400">2-tap confirm</Text>
				)}
			</View>

			{isPending && approval.expires_at ? (
				<View className="mt-2">
					<ExpiryCountdown expiresAt={approval.expires_at} />
				</View>
			) : null}

			{approval.status === "denied" && approval.deny_reason ? (
				<Text className="mt-2 text-xs text-white/50" numberOfLines={2}>
					Reason: {approval.deny_reason}
				</Text>
			) : null}

			{risk_label ? (
				<Text className="mt-2 text-xs text-white/40" numberOfLines={1}>
					{risk_label}
				</Text>
			) : null}
		</Pressable>
	);
}
