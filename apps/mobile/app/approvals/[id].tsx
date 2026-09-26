import * as Haptics from "expo-haptics";
import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import {
	ActivityIndicator,
	Pressable,
	ScrollView,
	StyleSheet,
	Text,
	TextInput,
	View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import type { ApprovalRequest } from "@/api/shadow";
import { ExpiryCountdown } from "@/components/approvals/ExpiryCountdown";
import { RiskBadge } from "@/components/approvals/RiskBadge";
import { ChevronLeft, WarningIcon } from "@/components/icons";
import { useApprovalsStore } from "@/stores/useApprovalsStore";
import { Spacing, typography, useTheme } from "@/theme";
import { withOpacity } from "@/utils/colors";

function formatTimestamp(value: string | null | undefined): string {
	if (!value) return "Unknown";
	const parsed = new Date(value);
	if (Number.isNaN(parsed.getTime())) return value;
	return parsed.toLocaleString();
}

function ReceiptRow({
	label,
	children,
	last,
}: {
	label: string;
	children: React.ReactNode;
	last?: boolean;
}) {
	const { colors } = useTheme();
	return (
		<View
			style={[
				styles.receiptRow,
				!last && { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
			]}
		>
			<Text style={[typography.body, styles.receiptLabel, { color: colors.mutedForeground }]}>
				{label}
			</Text>
			<View style={styles.receiptValue}>{children}</View>
		</View>
	);
}

function ParamRows({ params }: { params: Record<string, unknown> }) {
	const { colors } = useTheme();
	const entries = Object.entries(params ?? {});
	if (entries.length === 0) {
		return (
			<Text style={[typography.body, { color: colors.mutedForeground }]}>
				No itemized details.
			</Text>
		);
	}
	return (
		<View>
			{entries.map(([key, value], index) => {
				const display =
					value !== null && typeof value === "object"
						? JSON.stringify(value, null, 2)
						: String(value);
				return (
					<ReceiptRow key={key} label={key} last={index === entries.length - 1}>
						<Text
							style={[typography.body, { color: colors.foreground }]}
							selectable
						>
							{display}
						</Text>
					</ReceiptRow>
				);
			})}
		</View>
	);
}

function DataChips({ items }: { items: string[] }) {
	const { colors } = useTheme();
	if (items.length === 0) {
		return (
			<Text style={[typography.body, { color: colors.mutedForeground }]}>
				None listed.
			</Text>
		);
	}
	return (
		<View style={styles.chips}>
			{items.map((item) => (
				<View
					key={item}
					style={[
						styles.chip,
						{ borderColor: colors.border, backgroundColor: colors.background },
					]}
				>
					<Text style={[typography.meta, { color: colors.foreground }]}>{item}</Text>
				</View>
			))}
		</View>
	);
}

function DecidedBanner({ approval }: { approval: ApprovalRequest }) {
	const { colors } = useTheme();
	if (approval.status === "pending") return null;
	const isApproved = approval.status === "approved";
	const base = isApproved ? colors.success : colors.destructive;
	return (
		<View
			style={[
				styles.decided,
				{
					borderColor: withOpacity(base, 0.4),
					backgroundColor: withOpacity(base, 0.1),
				},
			]}
		>
			<Text style={[typography.body, { color: base, fontWeight: "700" }]}>
				{isApproved ? "Allowed" : `Denied${approval.status === "expired" ? " (expired)" : ""}`}
			</Text>
			{!isApproved && approval.deny_reason ? (
				<Text style={[typography.body, { color: colors.foreground, marginTop: 4 }]}>
					Reason: {approval.deny_reason}
				</Text>
			) : null}
			<Text style={[typography.meta, { color: colors.mutedForeground, marginTop: 4 }]}>
				Decided {formatTimestamp(approval.decided_at)}
			</Text>
		</View>
	);
}

/**
 * Approval detail as a consent-forward receipt: the consent promise up
 * top, itemized details in the middle, Deny + Allow pills at the bottom.
 */
export default function ApprovalDetailScreen() {
	const { colors } = useTheme();
	const insets = useSafeAreaInsets();
	const { id } = useLocalSearchParams<{ id: string }>();

	const approval = useApprovalsStore((state) =>
		state.approvals.find((item) => item.id === id),
	);
	const decide = useApprovalsStore((state) => state.decide);
	const storeError = useApprovalsStore((state) => state.error);

	const [denyExpanded, setDenyExpanded] = useState(false);
	const [denyReason, setDenyReason] = useState("");
	const [confirmingAllow, setConfirmingAllow] = useState(false);
	const [submitting, setSubmitting] = useState(false);

	if (!approval) {
		return (
			<View
				style={[
					styles.centered,
					{
						backgroundColor: colors.background,
						paddingTop: insets.top,
						paddingBottom: insets.bottom,
					},
				]}
			>
				<Text style={[typography.h2, { color: colors.foreground, textAlign: "center" }]}>
					Approval not found
				</Text>
				<Text style={[typography.body, { color: colors.mutedForeground, textAlign: "center", marginTop: 4 }]}>
					It may have expired or been decided on another device.
				</Text>
				<Pressable
					onPress={() => router.back()}
					accessibilityRole="button"
					style={[styles.pillButton, { backgroundColor: colors.muted, marginTop: Spacing.lg }]}
				>
					<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "700" }]}>
						Go back
					</Text>
				</Pressable>
			</View>
		);
	}

	const { action } = approval;
	const isPending = approval.status === "pending";

	const handleBack = () => {
		Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
		router.back();
	};

	const handleAllow = async () => {
		if (approval.requires_double_confirmation && !confirmingAllow) {
			Haptics.selectionAsync().catch(() => {});
			setConfirmingAllow(true);
			return;
		}
		Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
		setSubmitting(true);
		await decide(approval.id, "approve");
		setSubmitting(false);
		setConfirmingAllow(false);
		const updated = useApprovalsStore
			.getState()
			.approvals.find((item) => item.id === approval.id);
		Haptics.notificationAsync(
			updated?.status === "approved"
				? Haptics.NotificationFeedbackType.Success
				: Haptics.NotificationFeedbackType.Error,
		).catch(() => {});
	};

	const handleDenyPress = () => {
		Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
		setDenyExpanded((prev) => !prev);
	};

	const handleConfirmDeny = async () => {
		Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
		setSubmitting(true);
		await decide(approval.id, "deny", denyReason.trim() || undefined);
		setSubmitting(false);
		setDenyExpanded(false);
		const updated = useApprovalsStore
			.getState()
			.approvals.find((item) => item.id === approval.id);
		Haptics.notificationAsync(
			updated?.status === "denied"
				? Haptics.NotificationFeedbackType.Success
				: Haptics.NotificationFeedbackType.Error,
		).catch(() => {});
	};

	return (
		<View
			style={[
				styles.container,
				{
					backgroundColor: colors.background,
					paddingTop: insets.top,
					paddingBottom: insets.bottom,
				},
			]}
		>
			<View style={styles.header}>
				<Pressable
					onPress={handleBack}
					accessibilityRole="button"
					accessibilityLabel="Back"
					style={styles.backButton}
					hitSlop={8}
				>
					<ChevronLeft size={24} color={colors.foreground} />
				</Pressable>
				<Text style={[typography.h2, { color: colors.foreground }]}>
					Approval request
				</Text>
			</View>

			<ScrollView
				style={styles.scroll}
				contentContainerStyle={styles.scrollContent}
				keyboardShouldPersistTaps="handled"
			>
				<DecidedBanner approval={approval} />

				{isPending ? (
					<View
						style={[
							styles.consent,
							{
								backgroundColor: withOpacity(colors.primary, 0.08),
								borderColor: withOpacity(colors.primary, 0.25),
							},
						]}
					>
						<Text style={[typography.body, { color: colors.foreground, fontWeight: "600" }]}>
							Nothing gets spent, sent, or shared without your approval.
						</Text>
						<Text style={[typography.meta, { color: colors.mutedForeground, marginTop: 4 }]}>
							Review the details below, then allow or deny.
						</Text>
					</View>
				) : null}

				<View
					style={[
						styles.receipt,
						{ backgroundColor: colors.card, borderColor: colors.border },
					]}
				>
					<Text style={[typography.h2, { color: colors.foreground }]}>
						{approval.action_preview?.trim() || action.description}
					</Text>

					<View style={styles.badges}>
						<RiskBadge risk={action.risk} />
						{action.destructive && (
							<View
								style={[
									styles.flag,
									{
										borderColor: withOpacity(colors.destructive, 0.4),
										backgroundColor: withOpacity(colors.destructive, 0.1),
									},
								]}
							>
								<WarningIcon size={12} color={colors.destructive} />
								<Text style={[styles.flagLabel, { color: colors.destructive }]}>
									Destructive
								</Text>
							</View>
						)}
						{approval.requires_double_confirmation && (
							<View
								style={[
									styles.flag,
									{
										borderColor: withOpacity(colors.warning, 0.4),
										backgroundColor: withOpacity(colors.warning, 0.1),
									},
								]}
							>
								<Text style={[styles.flagLabel, { color: colors.warning }]}>
									Needs double confirm
								</Text>
							</View>
						)}
					</View>

					{approval.risk_label ? (
						<Text style={[typography.body, { color: colors.mutedForeground, marginTop: 8 }]}>
							{approval.risk_label}
						</Text>
					) : null}

					{approval.reason ? (
						<View style={styles.reasonBlock}>
							<Text style={[typography.uiLabel, styles.sectionLabel, { color: colors.mutedForeground }]}>
								Why this needs your approval
							</Text>
							<Text style={[typography.body, { color: colors.foreground, marginTop: 4 }]}>
								{approval.reason}
							</Text>
						</View>
					) : null}

					<View style={styles.divider}>
						<Text style={[typography.uiLabel, styles.sectionLabel, { color: colors.mutedForeground }]}>
							Details
						</Text>
					</View>
					<ParamRows params={action.params ?? {}} />

					<View style={styles.divider}>
						<Text style={[typography.uiLabel, styles.sectionLabel, { color: colors.mutedForeground }]}>
							Receipt
						</Text>
					</View>
					<ReceiptRow label="Tool">
						<Text style={[typography.body, { color: colors.foreground }]} selectable>
							{action.tool_name}
						</Text>
					</ReceiptRow>
					<ReceiptRow label="Model">
						<Text style={[typography.body, { color: colors.foreground }]} selectable>
							{action.model_used || "Unknown"}
						</Text>
					</ReceiptRow>
					<ReceiptRow label="Destination">
						<Text style={[typography.body, { color: colors.foreground }]} selectable>
							{action.destination || "Unknown"}
						</Text>
					</ReceiptRow>
					<ReceiptRow label="Data used">
						<DataChips items={action.data_used ?? []} />
					</ReceiptRow>
					<ReceiptRow label="Requested">
						<Text style={[typography.body, { color: colors.foreground }]}>
							{formatTimestamp(approval.created_at)}
						</Text>
					</ReceiptRow>
					<ReceiptRow label="Expires" last>
						{approval.expires_at ? (
							<ExpiryCountdown expiresAt={approval.expires_at} />
						) : (
							<Text style={[typography.body, { color: colors.foreground }]}>No expiry</Text>
						)}
					</ReceiptRow>
				</View>

				{storeError !== null && (
					<View
						style={[
							styles.error,
							{
								borderColor: withOpacity(colors.destructive, 0.4),
								backgroundColor: withOpacity(colors.destructive, 0.08),
							},
						]}
					>
						<Text style={[typography.body, { color: colors.destructive }]}>{storeError}</Text>
					</View>
				)}

				{isPending ? (
					<View style={styles.actions}>
						{submitting ? (
							<View style={styles.submitting}>
								<ActivityIndicator size="large" color={colors.primary} />
							</View>
						) : (
							<>
								<View style={styles.pills}>
									<Pressable
										onPress={handleDenyPress}
										accessibilityRole="button"
										accessibilityLabel="Deny this request"
										style={({ pressed }) => [
											styles.pillButton,
											styles.denyPill,
											{ borderColor: colors.destructive, opacity: pressed ? 0.7 : 1 },
										]}
									>
										<Text style={[typography.uiLabel, { color: colors.destructive, fontWeight: "700" }]}>
											Deny
										</Text>
									</Pressable>
									<Pressable
										onPress={() => void handleAllow()}
										accessibilityRole="button"
										accessibilityLabel={confirmingAllow ? "Tap again to confirm allowing" : "Allow this request"}
										style={({ pressed }) => [
											styles.pillButton,
											{ backgroundColor: colors.primary, opacity: pressed ? 0.8 : 1 },
										]}
									>
										<Text style={[typography.uiLabel, { color: "#FFFFFF", fontWeight: "700" }]}>
											{confirmingAllow ? "Tap again to confirm" : "Allow"}
										</Text>
									</Pressable>
								</View>

								{denyExpanded ? (
									<View style={styles.denyForm}>
										<TextInput
											value={denyReason}
											onChangeText={setDenyReason}
											placeholder="Reason for denying (optional)"
											placeholderTextColor={colors.mutedForeground}
											multiline
											style={[
												styles.denyInput,
												typography.body,
												{
													color: colors.foreground,
													borderColor: colors.border,
													backgroundColor: colors.card,
												},
											]}
										/>
										<Pressable
											onPress={() => void handleConfirmDeny()}
											accessibilityRole="button"
											accessibilityLabel="Confirm deny"
											style={({ pressed }) => [
												styles.pillButton,
												{ backgroundColor: colors.destructive, opacity: pressed ? 0.8 : 1 },
											]}
										>
											<Text style={[typography.uiLabel, { color: "#FFFFFF", fontWeight: "700" }]}>
												Confirm deny
											</Text>
										</Pressable>
									</View>
								) : null}
							</>
						)}
					</View>
				) : (
					<Pressable
						onPress={handleBack}
						accessibilityRole="button"
						style={[styles.pillButton, { backgroundColor: colors.muted, marginTop: Spacing.lg }]}
					>
						<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "700" }]}>
							Back to inbox
						</Text>
					</Pressable>
				)}
			</ScrollView>
		</View>
	);
}

const styles = StyleSheet.create({
	container: {
		flex: 1,
	},
	centered: {
		flex: 1,
		alignItems: "center",
		justifyContent: "center",
		paddingHorizontal: Spacing.xl,
	},
	header: {
		flexDirection: "row",
		alignItems: "center",
		gap: 4,
		paddingHorizontal: Spacing.sm,
		paddingVertical: Spacing.sm,
	},
	backButton: {
		borderRadius: 999,
		padding: Spacing.sm,
	},
	scroll: {
		flex: 1,
	},
	scrollContent: {
		paddingHorizontal: Spacing.md,
		paddingBottom: Spacing.xl,
	},
	decided: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: 16,
		padding: Spacing.md,
		marginBottom: Spacing.md,
	},
	consent: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: 16,
		padding: Spacing.md,
		marginBottom: Spacing.md,
	},
	receipt: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: 16,
		padding: Spacing.lg,
	},
	badges: {
		marginTop: Spacing.sm,
		flexDirection: "row",
		flexWrap: "wrap",
		alignItems: "center",
		gap: Spacing.sm,
	},
	flag: {
		flexDirection: "row",
		alignItems: "center",
		gap: 4,
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: 999,
		paddingHorizontal: 8,
		paddingVertical: 2,
	},
	flagLabel: {
		fontSize: 11,
		fontWeight: "700",
		textTransform: "uppercase",
	},
	reasonBlock: {
		marginTop: Spacing.md,
	},
	sectionLabel: {
		fontWeight: "700",
		textTransform: "uppercase",
		fontSize: 12,
	},
	divider: {
		marginTop: Spacing.lg,
		marginBottom: Spacing.sm,
	},
	receiptRow: {
		flexDirection: "row",
		gap: Spacing.md,
		paddingVertical: 10,
	},
	receiptLabel: {
		width: 104,
		flexShrink: 0,
		fontWeight: "600",
	},
	receiptValue: {
		flex: 1,
	},
	chips: {
		flexDirection: "row",
		flexWrap: "wrap",
		gap: Spacing.sm,
	},
	chip: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: 999,
		paddingHorizontal: 12,
		paddingVertical: 6,
	},
	error: {
		marginTop: Spacing.md,
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: 16,
		padding: Spacing.md,
	},
	actions: {
		marginTop: Spacing.lg,
	},
	submitting: {
		alignItems: "center",
		paddingVertical: Spacing.lg,
	},
	pills: {
		flexDirection: "row",
		gap: Spacing.sm,
	},
	pillButton: {
		flex: 1,
		alignItems: "center",
		borderRadius: 999,
		paddingVertical: 16,
		paddingHorizontal: Spacing.lg,
	},
	denyPill: {
		borderWidth: 1.5,
		backgroundColor: "transparent",
	},
	denyForm: {
		marginTop: Spacing.md,
		gap: Spacing.sm,
	},
	denyInput: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: 14,
		paddingHorizontal: Spacing.md,
		paddingVertical: 12,
		minHeight: 80,
		textAlignVertical: "top",
		fontSize: 16,
	},
});
