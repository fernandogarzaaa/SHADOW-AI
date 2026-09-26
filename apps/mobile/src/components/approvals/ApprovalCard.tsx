import * as Haptics from "expo-haptics";
import { Pressable, StyleSheet, Text, View } from "react-native";
import type { ApprovalRequest } from "@/api/shadow";
import { WarningIcon } from "@/components/icons";
import { ExpiryCountdown } from "./ExpiryCountdown";
import { RiskBadge } from "./RiskBadge";
import { Spacing, typography, useTheme } from "@/theme";
import { withOpacity } from "@/utils/colors";

interface ApprovalCardProps {
	approval: ApprovalRequest;
	onPress: () => void;
}

function StatusPill({ status }: { status: string }) {
	const { colors } = useTheme();
	const base =
		status === "approved"
			? colors.success
			: status === "denied"
				? colors.destructive
				: colors.mutedForeground;
	return (
		<View
			style={[
				styles.pill,
				{
					borderColor: withOpacity(base, 0.4),
					backgroundColor: withOpacity(base, 0.12),
				},
			]}
		>
			<Text style={[styles.pillLabel, { color: base }]}>{status}</Text>
		</View>
	);
}

/**
 * Inbox row for one approval request, styled as a small receipt:
 * action summary, risk badge, itemized meta, expiry countdown, and a
 * consent reminder while the request is pending.
 */
export function ApprovalCard({ approval, onPress }: ApprovalCardProps) {
	const { colors } = useTheme();
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
			style={({ pressed }) => [
				styles.card,
				{
					backgroundColor: colors.card,
					borderColor: colors.border,
					opacity: pressed ? 0.7 : 1,
				},
			]}
		>
			<View style={styles.headRow}>
				<Text
					style={[typography.body, styles.headline, { color: colors.foreground }]}
					numberOfLines={2}
				>
					{headline}
				</Text>
				{isPending ? (
					<RiskBadge risk={action.risk} />
				) : (
					<StatusPill status={approval.status} />
				)}
			</View>

			<View style={styles.metaRow}>
				<Text style={[typography.meta, { color: colors.mutedForeground }]} numberOfLines={1}>
					{action.tool_name}
				</Text>
				{action.destructive && (
					<View style={styles.destructiveRow}>
						<WarningIcon size={12} color={colors.destructive} />
						<Text style={[typography.meta, styles.destructiveLabel, { color: colors.destructive }]}>
							Destructive
						</Text>
					</View>
				)}
				{requires_double_confirmation && isPending && (
					<Text style={[typography.meta, { color: colors.warning }]}>2-tap confirm</Text>
				)}
			</View>

			{isPending && approval.expires_at ? (
				<View style={styles.expiryRow}>
					<ExpiryCountdown expiresAt={approval.expires_at} />
				</View>
			) : null}

			{approval.status === "denied" && approval.deny_reason ? (
				<Text style={[typography.meta, { color: colors.mutedForeground, marginTop: 8 }]} numberOfLines={2}>
					Reason: {approval.deny_reason}
				</Text>
			) : null}

			{risk_label ? (
				<Text style={[typography.meta, { color: colors.mutedForeground, marginTop: 4 }]} numberOfLines={1}>
					{risk_label}
				</Text>
			) : null}

			{isPending ? (
				<Text style={[typography.meta, styles.consent, { color: colors.mutedForeground }]}>
					Nothing gets spent, sent, or shared without your approval.
				</Text>
			) : null}
		</Pressable>
	);
}

const styles = StyleSheet.create({
	card: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: 16,
		padding: Spacing.md,
	},
	headRow: {
		flexDirection: "row",
		alignItems: "flex-start",
		justifyContent: "space-between",
		gap: Spacing.sm,
	},
	headline: {
		flex: 1,
		fontWeight: "600",
	},
	metaRow: {
		marginTop: 6,
		flexDirection: "row",
		alignItems: "center",
		gap: Spacing.sm,
	},
	destructiveRow: {
		flexDirection: "row",
		alignItems: "center",
		gap: 4,
	},
	destructiveLabel: {
		fontWeight: "700",
	},
	expiryRow: {
		marginTop: 8,
	},
	consent: {
		marginTop: 10,
		fontStyle: "italic",
	},
	pill: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: 999,
		paddingHorizontal: 8,
		paddingVertical: 2,
	},
	pillLabel: {
		fontSize: 11,
		fontWeight: "700",
		textTransform: "uppercase",
	},
});
