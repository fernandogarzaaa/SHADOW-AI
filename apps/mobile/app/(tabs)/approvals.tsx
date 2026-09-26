import { FlashList } from "@shopify/flash-list";
import * as Haptics from "expo-haptics";
import { router } from "expo-router";
import { useCallback, useEffect } from "react";
import {
	ActivityIndicator,
	Pressable,
	RefreshControl,
	StyleSheet,
	Text,
	View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import type { ApprovalRequest } from "@/api/shadow";
import { ApprovalCard } from "@/components/approvals/ApprovalCard";
import type { ShadowEvent } from "@/hooks/useShadowEventStream";
import { useShadowEventStream } from "@/hooks/useShadowEventStream";
import { useApprovalsStore } from "@/stores/useApprovalsStore";
import { useConnectionStore } from "@/stores/useConnectionStore";
import { Spacing, typography, useTheme } from "@/theme";
import { Badge, DepthBackground } from "@/components/ui";
import { withOpacity } from "@/utils/colors";

function PendingCountBadge({ count }: { count: number }) {
	return <Badge variant="destructive">{String(count)} pending</Badge>;
}

function ConnectPrompt() {
	const { colors } = useTheme();
	const handlePress = () => {
		Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
		router.push("/settings/link-node");
	};

	return (
		<View style={styles.centered}>
			<Text style={[typography.h2, { color: colors.foreground, textAlign: "center" }]}>
				Link your node
			</Text>
			<Text style={[typography.body, { color: colors.mutedForeground, textAlign: "center", marginTop: 8 }]}>
				Pair with your shadow node to review actions waiting for approval.
			</Text>
			<Pressable
				onPress={handlePress}
				accessibilityRole="button"
				style={({ pressed }) => [
					styles.actionButton,
					{ backgroundColor: colors.primary, opacity: pressed ? 0.8 : 1 },
				]}
			>
				<Text style={[typography.uiLabel, { color: colors.primaryForeground, fontWeight: "700" }]}>
					Link node
				</Text>
			</Pressable>
		</View>
	);
}

function EmptyState({ onCheckAgain }: { onCheckAgain: () => void }) {
	const { colors } = useTheme();
	const handlePress = () => {
		Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
		onCheckAgain();
	};

	return (
		<View style={styles.centered}>
			<Text style={[typography.h2, { color: colors.foreground, textAlign: "center" }]}>
				All clear. No pending approvals.
			</Text>
			<Text style={[typography.body, { color: colors.mutedForeground, textAlign: "center", marginTop: 8 }]}>
				New requests from your node will appear here in real time.
			</Text>
			<Pressable
				onPress={handlePress}
				accessibilityRole="button"
				style={({ pressed }) => [
					styles.actionButton,
					{ backgroundColor: colors.muted, opacity: pressed ? 0.7 : 1 },
				]}
			>
				<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "700" }]}>
					Check again
				</Text>
			</Pressable>
		</View>
	);
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
	const { colors } = useTheme();
	const handlePress = () => {
		Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
		onRetry();
	};

	return (
		<View style={styles.centered}>
			<Text style={[typography.h2, { color: colors.foreground, textAlign: "center" }]}>
				Could not load approvals
			</Text>
			<Text style={[typography.body, { color: colors.mutedForeground, textAlign: "center", marginTop: 8 }]}>
				{message}
			</Text>
			<Pressable
				onPress={handlePress}
				accessibilityRole="button"
				style={({ pressed }) => [
					styles.actionButton,
					{ backgroundColor: colors.muted, opacity: pressed ? 0.7 : 1 },
				]}
			>
				<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "700" }]}>
					Retry
				</Text>
			</Pressable>
		</View>
	);
}

/** The approvals inbox: pending requests from the shadow node, live via SSE. */
export default function ApprovalsScreen() {
	const { colors } = useTheme();
	const insets = useSafeAreaInsets();
	const isPaired = useConnectionStore((state) => state.isPaired);

	const approvals = useApprovalsStore((state) => state.approvals);
	const loading = useApprovalsStore((state) => state.loading);
	const refreshing = useApprovalsStore((state) => state.refreshing);
	const error = useApprovalsStore((state) => state.error);
	const fetchApprovals = useApprovalsStore((state) => state.fetchApprovals);
	const applyEvent = useApprovalsStore((state) => state.applyEvent);

	const handleEvent = useCallback(
		(event: ShadowEvent) => {
			applyEvent(event);
		},
		[applyEvent],
	);

	useShadowEventStream({ enabled: isPaired, onEvent: handleEvent });

	useEffect(() => {
		if (isPaired) {
			fetchApprovals().catch(() => {});
		}
	}, [isPaired, fetchApprovals]);

	const handleRefresh = useCallback(() => {
		Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
		fetchApprovals().catch(() => {});
	}, [fetchApprovals]);

	const handleOpenApproval = useCallback((approval: ApprovalRequest) => {
		router.push(`/approvals/${approval.id}`);
	}, []);

	const renderItem = useCallback(
		({ item }: { item: ApprovalRequest }) => (
			<ApprovalCard approval={item} onPress={() => handleOpenApproval(item)} />
		),
		[handleOpenApproval],
	);

	const pendingCount = approvals.filter(
		(approval) => approval.status === "pending",
	).length;

	if (!isPaired) {
		return (
			<View
				style={[
					styles.container,
					{
						paddingTop: insets.top,
						paddingBottom: insets.bottom,
					},
				]}
			>
				<DepthBackground />
				<ConnectPrompt />
			</View>
		);
	}

	const showEmpty = !loading && !error && approvals.length === 0;
	const showError = !loading && error !== null && approvals.length === 0;

	return (
		<View
			style={[
				styles.container,
				{
					paddingTop: insets.top,
					paddingBottom: insets.bottom,
				},
			]}
		>
			<DepthBackground />
			<View style={styles.header}>
				<Text style={[typography.title, { color: colors.foreground }]}>Approvals</Text>
				<PendingCountBadge count={pendingCount} />
			</View>

			{loading ? (
				<View style={styles.centered}>
					<ActivityIndicator size="large" color={colors.primary} />
				</View>
			) : showError ? (
				<ErrorState message={error ?? "Something went wrong"} onRetry={handleRefresh} />
			) : showEmpty ? (
				<EmptyState onCheckAgain={handleRefresh} />
			) : (
				<View style={styles.list}>
					{error !== null ? (
						<Pressable
							onPress={handleRefresh}
							accessibilityRole="button"
							style={[
								styles.retryBanner,
								{
									borderColor: withOpacity(colors.destructive, 0.3),
									backgroundColor: withOpacity(colors.destructive, 0.08),
								},
							]}
						>
							<Text style={[typography.body, { color: colors.destructive, textAlign: "center" }]}>
								{error} Tap to retry.
							</Text>
						</Pressable>
					) : null}
					<FlashList
						data={approvals}
						renderItem={renderItem}
						keyExtractor={(item) => item.id}
						contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 24 }}
						ItemSeparatorComponent={() => <View style={{ height: 12 }} />}
						refreshControl={
							<RefreshControl
								refreshing={refreshing}
								onRefresh={handleRefresh}
								tintColor={colors.primary}
							/>
						}
					/>
				</View>
			)}
		</View>
	);
}

const styles = StyleSheet.create({
	container: {
		flex: 1,
	},
	header: {
		flexDirection: "row",
		alignItems: "center",
		justifyContent: "space-between",
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.md,
	},
	badge: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: 999,
		paddingHorizontal: 10,
		paddingVertical: 2,
	},
	centered: {
		flex: 1,
		alignItems: "center",
		justifyContent: "center",
		gap: 4,
		paddingHorizontal: Spacing.xl,
	},
	actionButton: {
		marginTop: Spacing.md,
		borderRadius: 14,
		paddingHorizontal: Spacing.xl,
		paddingVertical: 12,
		alignItems: "center",
	},
	list: {
		flex: 1,
	},
	retryBanner: {
		marginHorizontal: Spacing.md,
		marginBottom: Spacing.sm,
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: 12,
		paddingHorizontal: Spacing.md,
		paddingVertical: 10,
	},
});
