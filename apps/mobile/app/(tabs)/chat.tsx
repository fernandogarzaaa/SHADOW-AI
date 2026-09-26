import * as Haptics from "expo-haptics";
import { router } from "expo-router";
import { useMemo, useState } from "react";
import {
	FlatList,
	Pressable,
	StyleSheet,
	Text,
	View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { ShadowAvatar } from "@/components/Avatar";
import {
	ChevronRightIcon,
	PencilIcon,
} from "@/components/icons";
import {
	DepthBackground,
	GlassView,
	IconButton,
	SearchInput,
} from "@/components/ui";
import { useProfileStore } from "@/stores/useProfileStore";
import { useProviderStore } from "@/stores/useProviderStore";
import {
	isThreadUnread,
	useChatStore,
	type ChatThread,
} from "@/stores/useChatStore";
import { SemanticSpacing, Spacing, typography, useTheme } from "@/theme";

function ThreadRow({
	thread,
	unread,
	onPress,
}: {
	thread: ChatThread;
	unread: boolean;
	onPress: () => void;
}) {
	const { colors } = useTheme();
	const lastMessage = thread.messages[thread.messages.length - 1];
	return (
		<Pressable
			onPress={onPress}
			style={({ pressed }) => [
				styles.row,
				{ opacity: pressed ? 0.6 : 1 },
			]}
			accessibilityRole="button"
			accessibilityLabel={`${thread.title}${unread ? ", unread" : ""}`}
		>
			<View style={styles.rowText}>
				<Text
					style={[typography.body, { color: colors.foreground, fontWeight: "600" }]}
					numberOfLines={1}
				>
					{thread.title}
				</Text>
				{lastMessage ? (
					<Text
						style={[typography.meta, { color: colors.mutedForeground }]}
						numberOfLines={1}
					>
						{lastMessage.text}
					</Text>
				) : null}
			</View>
			{unread ? (
				<View
					style={[styles.unreadDot, { backgroundColor: colors.primary }]}
					accessibilityLabel="Unread"
				/>
			) : null}
			<ChevronRightIcon size={18} color={colors.mutedForeground} />
		</Pressable>
	);
}

/**
 * Chats list: the Chat tab home. The active thread is the "Main chat";
 * every other thread is a "Side chat". Liquid glass surfaces over a
 * warm depth background; shadcn-style hierarchy with one primary
 * action (compose).
 */
export default function ChatsScreen() {
	const { colors } = useTheme();
	const insets = useSafeAreaInsets();
	const { threads, activeThreadId, setActiveThread, createThread, initialized } =
		useChatStore();
	const { providerId, modelId } = useProviderStore();
	const agentName = useProfileStore((s) => s.profile.agentName);
	const avatarId = useProfileStore((s) => s.profile.avatarId);
	const [query, setQuery] = useState("");

	const openThread = (id: string) => {
		Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
		setActiveThread(id);
		router.push(`/chat/${id}`);
	};

	const handleCompose = async () => {
		const id = await createThread(providerId, modelId);
		router.push(`/chat/${id}`);
	};

	const active = threads.find((t) => t.id === activeThreadId) ?? threads[0] ?? null;
	const sideChats = useMemo(() => {
		const rest = threads.filter((t) => t.id !== active?.id);
		const q = query.trim().toLowerCase();
		if (!q) return rest;
		return rest.filter((t) => t.title.toLowerCase().includes(q));
	}, [threads, active, query]);

	return (
		<View style={styles.container}>
			<DepthBackground />
			{/* Header */}
			<View style={[styles.header, { paddingTop: insets.top + Spacing.sm }]}>
				<Text
					style={[typography.title, { color: colors.foreground }]}
					accessibilityRole="header"
				>
					{agentName || "shadow"}
				</Text>
			</View>

			<View style={styles.content}>
				{/* Main chat: glass card */}
				{active ? (
					<Pressable
						onPress={() => openThread(active.id)}
						style={({ pressed }) => [{ opacity: pressed ? 0.75 : 1 }]}
						accessibilityRole="button"
						accessibilityLabel={`Main chat: ${active.title}`}
					>
						<GlassView borderRadius={22} style={styles.mainCard}>
							<View style={styles.mainCardInner}>
								<ShadowAvatar avatarId={avatarId} size={40} />
								<View style={styles.mainCardText}>
									<Text
										style={[typography.titleSmall, { color: colors.foreground }]}
										numberOfLines={1}
									>
										Main chat
									</Text>
									<Text
										style={[typography.meta, { color: colors.mutedForeground }]}
										numberOfLines={1}
									>
										{active.title}
									</Text>
								</View>
								<ChevronRightIcon size={20} color={colors.mutedForeground} />
							</View>
						</GlassView>
					</Pressable>
				) : null}

				<Text
					style={[
						typography.uiLabel,
						styles.sectionLabel,
						{ color: colors.mutedForeground },
					]}
				>
					Side chats
				</Text>

				<FlatList
					data={sideChats}
					keyExtractor={(t) => t.id}
					renderItem={({ item }) => (
						<ThreadRow
							thread={item}
							unread={isThreadUnread(item)}
							onPress={() => openThread(item.id)}
						/>
					)}
					ItemSeparatorComponent={() => (
						<View style={[styles.separator, { backgroundColor: colors.border }]} />
					)}
					ListEmptyComponent={
						<Text style={[typography.body, { color: colors.mutedForeground }]}>
							{initialized
								? "No side chats yet. Compose one with the button below."
								: "Loading chats..."}
						</Text>
					}
					contentContainerStyle={styles.listContent}
					keyboardShouldPersistTaps="handled"
				/>
			</View>

			{/* Bottom: floating glass bar with search + primary compose */}
			<View
				style={[
					styles.bottomBar,
					{ marginBottom: Math.max(insets.bottom, 12) + 76 },
				]}
			>
				<GlassView borderRadius={28} style={styles.bottomGlass}>
					<View style={styles.bottomInner}>
						<View style={styles.searchWrap}>
							<SearchInput
								value={query}
								onChangeText={setQuery}
								placeholder="Search chats"
							/>
						</View>
						<IconButton
							variant="primary"
							size="icon-md"
							accessibilityLabel="Start a new chat"
							onPress={() => void handleCompose()}
							icon={
								<PencilIcon size={20} color={colors.primaryForeground} />
							}
						/>
					</View>
				</GlassView>
			</View>
		</View>
	);
}

const styles = StyleSheet.create({
	container: {
		flex: 1,
	},
	header: {
		paddingHorizontal: Spacing.lg,
		paddingBottom: Spacing.sm,
	},
	content: {
		flex: 1,
		paddingHorizontal: Spacing.lg,
	},
	mainCard: {
		marginBottom: Spacing.lg,
	},
	mainCardInner: {
		flexDirection: "row",
		alignItems: "center",
		gap: Spacing.md,
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.md,
	},
	mainCardText: {
		flex: 1,
		gap: 2,
	},
	sectionLabel: {
		fontWeight: "600",
		marginBottom: Spacing.xs,
	},
	listContent: {
		paddingBottom: Spacing.xl,
	},
	row: {
		flexDirection: "row",
		alignItems: "center",
		gap: Spacing.sm,
		paddingVertical: Spacing.md,
		minHeight: SemanticSpacing.buttonHeightMd + 12,
	},
	rowText: {
		flex: 1,
		gap: 2,
	},
	separator: {
		height: StyleSheet.hairlineWidth,
		marginLeft: 0,
		opacity: 0.7,
	},
	unreadDot: {
		width: 10,
		height: 10,
		borderRadius: 5,
	},
	bottomBar: {
		paddingHorizontal: Spacing.lg,
	},
	bottomGlass: {
		// GlassView carries the surface; this keeps layout clean.
	},
	bottomInner: {
		flexDirection: "row",
		alignItems: "center",
		gap: Spacing.sm,
		paddingHorizontal: Spacing.sm,
		paddingVertical: Spacing.sm,
	},
	searchWrap: {
		flex: 1,
	},
});
