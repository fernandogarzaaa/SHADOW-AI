import * as Haptics from "expo-haptics";
import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import {
	ActivityIndicator,
	Pressable,
	ScrollView,
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

function SectionTitle({ children }: { children: string }) {
	return (
		<Text className="mb-2 text-xs font-semibold uppercase text-white/40">
			{children}
		</Text>
	);
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
	return (
		<View className="mt-5">
			<SectionTitle>{title}</SectionTitle>
			{children}
		</View>
	);
}

function formatTimestamp(value: string | null | undefined): string {
	if (!value) return "Unknown";
	const parsed = new Date(value);
	if (Number.isNaN(parsed.getTime())) return value;
	return parsed.toLocaleString();
}

function ParamRows({ params }: { params: Record<string, unknown> }) {
	const entries = Object.entries(params ?? {});
	if (entries.length === 0) {
		return <Text className="text-sm text-white/40">No parameters.</Text>;
	}
	return (
		<View className="overflow-hidden rounded-xl border border-white/10">
			{entries.map(([key, value], index) => {
				const display =
					value !== null && typeof value === "object"
						? JSON.stringify(value, null, 2)
						: String(value);
				return (
					<View
						key={key}
						className={`flex-row gap-3 px-3 py-2.5 ${index > 0 ? "border-t border-white/10" : ""} ${index % 2 === 1 ? "bg-white/5" : ""}`}
					>
						<Text className="w-28 shrink-0 text-sm font-medium text-white/60">
							{key}
						</Text>
						<Text
							className="flex-1 text-sm text-white"
							selectable
							style={{ fontFamily: "monospace" }}
						>
							{display}
						</Text>
					</View>
				);
			})}
		</View>
	);
}

function DataChips({ items }: { items: string[] }) {
	if (items.length === 0) {
		return <Text className="text-sm text-white/40">None listed.</Text>;
	}
	return (
		<View className="flex-row flex-wrap gap-2">
			{items.map((item) => (
				<View
					key={item}
					className="rounded-full border border-white/15 bg-white/5 px-3 py-1.5"
				>
					<Text className="text-xs text-white/80">{item}</Text>
				</View>
			))}
		</View>
	);
}

function DecidedBanner({ approval }: { approval: ApprovalRequest }) {
	if (approval.status === "pending") return null;
	const isApproved = approval.status === "approved";
	const colors = isApproved
		? "border-emerald-500/40 bg-emerald-500/10"
		: "border-red-500/40 bg-red-500/10";
	const text = isApproved ? "text-emerald-300" : "text-red-300";
	return (
		<View className={`rounded-xl border px-4 py-3 ${colors}`}>
			<Text className={`text-sm font-semibold ${text}`}>
				{isApproved ? "Approved" : `Denied${approval.status === "expired" ? " (expired)" : ""}`}
			</Text>
			{!isApproved && approval.deny_reason ? (
				<Text className="mt-1 text-sm text-white/60">
					Reason: {approval.deny_reason}
				</Text>
			) : null}
			<Text className="mt-1 text-xs text-white/40">
				Decided {formatTimestamp(approval.decided_at)}
			</Text>
		</View>
	);
}

/** Detail screen for one approval request: full context, then approve or deny. */
export default function ApprovalDetailScreen() {
	const insets = useSafeAreaInsets();
	const { id } = useLocalSearchParams<{ id: string }>();

	const approval = useApprovalsStore((state) =>
		state.approvals.find((item) => item.id === id),
	);
	const decide = useApprovalsStore((state) => state.decide);
	const storeError = useApprovalsStore((state) => state.error);

	const [denyExpanded, setDenyExpanded] = useState(false);
	const [denyReason, setDenyReason] = useState("");
	const [confirmingApprove, setConfirmingApprove] = useState(false);
	const [submitting, setSubmitting] = useState(false);

	if (!approval) {
		return (
			<View
				className="flex-1 items-center justify-center bg-black px-8"
				style={{ paddingTop: insets.top, paddingBottom: insets.bottom }}
			>
				<Text className="text-center text-base font-semibold text-white">
					Approval not found
				</Text>
				<Text className="mt-1 text-center text-sm text-white/50">
					It may have expired or been decided on another device.
				</Text>
				<Pressable
					onPress={() => router.back()}
					accessibilityRole="button"
					className="mt-4 rounded-xl bg-white/10 px-6 py-3 active:bg-white/20"
				>
					<Text className="text-sm font-semibold text-white">Go back</Text>
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

	const handleApprove = async () => {
		if (approval.requires_double_confirmation && !confirmingApprove) {
			Haptics.selectionAsync().catch(() => {});
			setConfirmingApprove(true);
			return;
		}
		Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
		setSubmitting(true);
		await decide(approval.id, "approve");
		setSubmitting(false);
		setConfirmingApprove(false);
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
			className="flex-1 bg-black"
			style={{ paddingTop: insets.top, paddingBottom: insets.bottom }}
		>
			<View className="flex-row items-center px-2 py-2">
				<Pressable
					onPress={handleBack}
					accessibilityRole="button"
					accessibilityLabel="Back"
					className="rounded-full p-2 active:bg-white/10"
				>
					<ChevronLeft size={24} color="#fff" />
				</Pressable>
				<Text className="ml-1 text-lg font-semibold text-white">
					Approval request
				</Text>
			</View>

			<ScrollView
				className="flex-1"
				contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 32 }}
				keyboardShouldPersistTaps="handled"
			>
				<DecidedBanner approval={approval} />

				<View className="mt-3">
					<Text className="text-xl font-bold leading-7 text-white">
						{approval.action_preview?.trim() || action.description}
					</Text>
				</View>

				<View className="mt-3 flex-row flex-wrap items-center gap-2">
					<RiskBadge risk={action.risk} />
					{action.destructive && (
						<View className="flex-row items-center gap-1 rounded-full border border-red-500/40 bg-red-500/15 px-2 py-0.5">
							<WarningIcon size={12} color="#f87171" />
							<Text className="text-[11px] font-semibold uppercase text-red-400">
								Destructive
							</Text>
						</View>
					)}
					{approval.requires_double_confirmation && (
						<View className="rounded-full border border-amber-500/40 bg-amber-500/15 px-2 py-0.5">
							<Text className="text-[11px] font-semibold uppercase text-amber-400">
								Needs double confirm
							</Text>
						</View>
					)}
				</View>

				{approval.risk_label ? (
					<Text className="mt-2 text-sm text-white/60">{approval.risk_label}</Text>
				) : null}

				{approval.reason ? (
					<Section title="Why it needs approval">
						<Text className="text-sm leading-5 text-white/80">{approval.reason}</Text>
					</Section>
				) : null}

				<Section title={`Parameters (${action.tool_name})`}>
					<ParamRows params={action.params ?? {}} />
				</Section>

				<Section title="Data used">
					<DataChips items={action.data_used ?? []} />
				</Section>

				<View className="mt-5 overflow-hidden rounded-xl border border-white/10">
					<View className="flex-row justify-between px-3 py-2.5">
						<Text className="text-sm text-white/50">Model</Text>
						<Text className="text-sm text-white" selectable>
							{action.model_used || "Unknown"}
						</Text>
					</View>
					<View className="flex-row justify-between border-t border-white/10 bg-white/5 px-3 py-2.5">
						<Text className="text-sm text-white/50">Destination</Text>
						<Text className="flex-1 text-right text-sm text-white" selectable>
							{action.destination || "Unknown"}
						</Text>
					</View>
					<View className="flex-row justify-between border-t border-white/10 px-3 py-2.5">
						<Text className="text-sm text-white/50">Created</Text>
						<Text className="text-sm text-white">
							{formatTimestamp(approval.created_at)}
						</Text>
					</View>
					<View className="flex-row items-center justify-between border-t border-white/10 bg-white/5 px-3 py-2.5">
						<Text className="text-sm text-white/50">Expires</Text>
						{approval.expires_at ? (
							<ExpiryCountdown expiresAt={approval.expires_at} />
						) : (
							<Text className="text-sm text-white">No expiry</Text>
						)}
					</View>
				</View>

				{storeError !== null && (
					<View className="mt-4 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3">
						<Text className="text-sm text-red-300">{storeError}</Text>
					</View>
				)}

				{isPending ? (
					<View className="mt-6 gap-3">
						{submitting ? (
							<View className="items-center py-4">
								<ActivityIndicator size="large" color="#f5a623" />
							</View>
						) : (
							<>
								<Pressable
									onPress={handleApprove}
									accessibilityRole="button"
									className={`items-center rounded-xl px-6 py-4 ${
										confirmingApprove ? "bg-amber-500" : "bg-emerald-600"
									} active:opacity-80`}
								>
									<Text className="text-base font-bold text-white">
										{confirmingApprove
											? "Tap again to confirm"
											: "Approve"}
									</Text>
								</Pressable>

								{denyExpanded ? (
									<View className="gap-3">
										<TextInput
											value={denyReason}
											onChangeText={setDenyReason}
											placeholder="Reason for denying (optional)"
											placeholderTextColor="rgba(255,255,255,0.35)"
											multiline
											className="rounded-xl border border-white/15 bg-white/5 px-4 py-3 text-sm text-white"
											style={{ minHeight: 80, textAlignVertical: "top" }}
										/>
										<Pressable
											onPress={handleConfirmDeny}
											accessibilityRole="button"
											className="items-center rounded-xl bg-red-600 px-6 py-4 active:opacity-80"
										>
											<Text className="text-base font-bold text-white">
												Confirm deny
											</Text>
										</Pressable>
									</View>
								) : (
									<Pressable
										onPress={handleDenyPress}
										accessibilityRole="button"
										className="items-center rounded-xl border border-red-500/50 bg-red-500/15 px-6 py-4 active:bg-red-500/25"
									>
										<Text className="text-base font-bold text-red-300">
											Deny
										</Text>
									</Pressable>
								)}
							</>
						)}
					</View>
				) : (
					<Pressable
						onPress={handleBack}
						accessibilityRole="button"
						className="mt-6 items-center rounded-xl bg-white/10 px-6 py-4 active:bg-white/20"
					>
						<Text className="text-base font-semibold text-white">
							Back to inbox
						</Text>
					</Pressable>
				)}
			</ScrollView>
		</View>
	);
}
