import { FlashList } from "@shopify/flash-list";
import * as Haptics from "expo-haptics";
import { router } from "expo-router";
import { useCallback, useEffect } from "react";
import {
	ActivityIndicator,
	Pressable,
	RefreshControl,
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

function PendingCountBadge({ count }: { count: number }) {
	return (
		<View className="rounded-full bg-amber-500/20 border border-amber-500/40 px-2.5 py-0.5">
			<Text className="text-sm font-semibold text-amber-400">{count}</Text>
		</View>
	);
}

function ConnectPrompt() {
	const handlePress = () => {
		Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
		router.push("/onboarding/scan");
	};

	return (
		<View className="flex-1 items-center justify-center gap-4 px-8">
			<Text className="text-center text-lg font-semibold text-white">
				Connect your node
			</Text>
			<Text className="text-center text-sm text-white/50">
				Pair with your SHADOW node to review actions waiting for approval.
			</Text>
			<Pressable
				onPress={handlePress}
				accessibilityRole="button"
				className="rounded-xl bg-white/10 px-6 py-3 active:bg-white/20"
			>
				<Text className="text-sm font-semibold text-white">Pair now</Text>
			</Pressable>
		</View>
	);
}

function EmptyState({ onCheckAgain }: { onCheckAgain: () => void }) {
	const handlePress = () => {
		Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
		onCheckAgain();
	};

	return (
		<View className="flex-1 items-center justify-center gap-3 px-8">
			<Text className="text-center text-base font-semibold text-white">
				All clear. No pending approvals.
			</Text>
			<Text className="text-center text-sm text-white/50">
				New requests from your node will appear here in real time.
			</Text>
			<Pressable
				onPress={handlePress}
				accessibilityRole="button"
				className="mt-1 rounded-xl bg-white/10 px-6 py-3 active:bg-white/20"
			>
				<Text className="text-sm font-semibold text-white">Check again</Text>
			</Pressable>
		</View>
	);
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
	const handlePress = () => {
		Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
		onRetry();
	};

	return (
		<View className="flex-1 items-center justify-center gap-3 px-8">
			<Text className="text-center text-base font-semibold text-white">
				Could not load approvals
			</Text>
			<Text className="text-center text-sm text-white/50">{message}</Text>
			<Pressable
				onPress={handlePress}
				accessibilityRole="button"
				className="mt-1 rounded-xl bg-white/10 px-6 py-3 active:bg-white/20"
			>
				<Text className="text-sm font-semibold text-white">Retry</Text>
			</Pressable>
		</View>
	);
}

/** The approvals inbox: pending requests from the SHADOW node, live via SSE. */
export default function ApprovalsScreen() {
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
				className="flex-1 bg-black"
				style={{ paddingTop: insets.top, paddingBottom: insets.bottom }}
			>
				<ConnectPrompt />
			</View>
		);
	}

	const showEmpty = !loading && !error && approvals.length === 0;
	const showError = !loading && error !== null && approvals.length === 0;

	return (
		<View
			className="flex-1 bg-black"
			style={{ paddingTop: insets.top, paddingBottom: insets.bottom }}
		>
			<View className="flex-row items-center justify-between px-4 py-3">
				<Text className="text-2xl font-bold text-white">Approvals</Text>
				<PendingCountBadge count={pendingCount} />
			</View>

			{loading ? (
				<View className="flex-1 items-center justify-center">
					<ActivityIndicator size="large" color="#f5a623" />
				</View>
			) : showError ? (
				<ErrorState message={error ?? "Something went wrong"} onRetry={handleRefresh} />
			) : showEmpty ? (
				<EmptyState onCheckAgain={handleRefresh} />
			) : (
				<View className="flex-1">
					{error !== null ? (
						<Pressable
							onPress={handleRefresh}
							accessibilityRole="button"
							className="mx-4 mb-2 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2.5"
						>
							<Text className="text-center text-sm text-red-300">
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
								tintColor="#f5a623"
							/>
						}
					/>
				</View>
			)}
		</View>
	);
}
