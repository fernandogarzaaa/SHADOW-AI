import * as Haptics from "expo-haptics";
import { router } from "expo-router";
import { useMemo, useState } from "react";
import {
	FlatList,
	Pressable,
	StyleSheet,
	Text,
	TextInput,
	View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { ShadowAvatar } from "@/components/Avatar";
import {
	FolderIcon,
	ArrowRightIcon,
	PencilIcon,
	SearchIcon,
	SettingsIcon,
} from "@/components/icons";
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
					style={[typography.body, { color: colors.foreground }]}
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
		</Pressable>
	);
}

/**
 * Chats list: the Chat tab home. The active thread is the "Main chat";
 * every other thread is a "Side chat". Bottom row: settings, search,
 * compose. Unread dots come from real last-read tracking in the chat
 * store (markThreadRead), never invented.
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
		Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
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
		<View
			style={[styles.container, { backgroundColor: colors.background }]}
		>
			{/* Header: title + action button */}
			<View style={[styles.header, { paddingTop: insets.top + Spacing.sm }]}>
				<View style={styles.headerSpacer} />
				<Text
					style={[typography.h2, { color: colors.foreground }]}
					accessibilityRole="header"
				>
					{agentName || "shadow"}
				</Text>
				<Pressable
					onPress={() => {
						if (active) openThread(active.id);
					}}
					style={({ pressed }) => [
						styles.headerAction,
						{
							backgroundColor: colors.card,
							borderColor: colors.border,
							opacity: pressed ? 0.6 : 1,
						},
					]}
					accessibilityRole="button"
					accessibilityLabel="Open main chat"
				>
					<ArrowRightIcon size={20} color={colors.foreground} />
				</Pressable>
			</View>

			{/* Main chat pill */}
			<View style={styles.content}>
				{active ? (
					<Pressable
						onPress={() => openThread(active.id)}
						style={({ pressed }) => [
							styles.mainPill,
							{
								backgroundColor: colors.card,
								borderColor: colors.border,
								opacity: pressed ? 0.7 : 1,
							},
						]}
						accessibilityRole="button"
						accessibilityLabel={`Main chat: ${active.title}`}
					>
						<ShadowAvatar avatarId={avatarId} size={28} />
						<Text
							style={[typography.uiLabel, { color: colors.foreground, fontWeight: "600" }]}
							numberOfLines={1}
						>
							Main chat
						</Text>
						<Text
							style={[typography.meta, { color: colors.mutedForeground, flex: 1 }]}
							numberOfLines={1}
						>
							{active.title}
						</Text>
					</Pressable>
				) : null}

				<View style={styles.sectionHeader}>
					<Text
						style={[
							typography.meta,
							{ color: colors.mutedForeground, fontWeight: "600" },
						]}
					>
						Side chats
					</Text>
					<FolderIcon size={18} color={colors.mutedForeground} />
				</View>

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

			{/* Bottom row: settings, search, compose */}
			<View
				style={[
					styles.bottomRow,
					{ paddingBottom: Math.max(insets.bottom, Spacing.md) + 76 },
				]}
			>
				<Pressable
					onPress={() => router.push("/settings")}
					style={({ pressed }) => [
						styles.circleButton,
						{
							backgroundColor: colors.card,
							borderColor: colors.border,
							opacity: pressed ? 0.6 : 1,
						},
					]}
					accessibilityRole="button"
					accessibilityLabel="Open settings"
				>
					<SettingsIcon size={22} color={colors.foreground} />
				</Pressable>
				<View
					style={[
						styles.searchPill,
						{ backgroundColor: colors.card, borderColor: colors.border },
					]}
				>
					<SearchIcon size={18} color={colors.mutedForeground} />
					<TextInput
						value={query}
						onChangeText={setQuery}
						placeholder="Search"
						placeholderTextColor={colors.mutedForeground}
						style={[typography.body, { color: colors.foreground, flex: 1 }]}
						accessibilityLabel="Search side chats"
						returnKeyType="search"
					/>
				</View>
				<Pressable
					onPress={() => void handleCompose()}
					style={({ pressed }) => [
						styles.circleButton,
						{
							backgroundColor: colors.card,
							borderColor: colors.border,
							opacity: pressed ? 0.6 : 1,
						},
					]}
					accessibilityRole="button"
					accessibilityLabel="Start a new chat"
				>
					<PencilIcon size={22} color={colors.foreground} />
				</Pressable>
			</View>
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
		paddingHorizontal: Spacing.lg,
		paddingBottom: Spacing.sm,
	},
	headerSpacer: {
		width: SemanticSpacing.buttonHeightMd,
	},
	headerAction: {
		width: SemanticSpacing.buttonHeightMd,
		height: SemanticSpacing.buttonHeightMd,
		borderRadius: SemanticSpacing.buttonHeightMd / 2,
		borderWidth: StyleSheet.hairlineWidth,
		alignItems: "center",
		justifyContent: "center",
	},
	content: {
		flex: 1,
		paddingHorizontal: Spacing.lg,
	},
	mainPill: {
		flexDirection: "row",
		alignItems: "center",
		gap: Spacing.sm,
		borderRadius: 999,
		borderWidth: StyleSheet.hairlineWidth,
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.sm,
		minHeight: 56,
		marginBottom: Spacing.lg,
	},
	sectionHeader: {
		flexDirection: "row",
		alignItems: "center",
		justifyContent: "space-between",
		marginBottom: Spacing.sm,
	},
	listContent: {
		paddingBottom: Spacing.xl,
		gap: 4,
	},
	row: {
		flexDirection: "row",
		alignItems: "center",
		gap: Spacing.sm,
		paddingVertical: Spacing.md,
		minHeight: SemanticSpacing.buttonHeightMd,
	},
	rowText: {
		flex: 1,
		gap: 2,
	},
	unreadDot: {
		width: 10,
		height: 10,
		borderRadius: 5,
	},
	bottomRow: {
		flexDirection: "row",
		alignItems: "center",
		gap: Spacing.sm,
		paddingHorizontal: Spacing.lg,
	},
	circleButton: {
		width: SemanticSpacing.buttonHeightMd,
		height: SemanticSpacing.buttonHeightMd,
		borderRadius: SemanticSpacing.buttonHeightMd / 2,
		borderWidth: StyleSheet.hairlineWidth,
		alignItems: "center",
		justifyContent: "center",
	},
	searchPill: {
		flex: 1,
		flexDirection: "row",
		alignItems: "center",
		gap: Spacing.sm,
		borderRadius: 999,
		borderWidth: StyleSheet.hairlineWidth,
		paddingHorizontal: Spacing.md,
		height: SemanticSpacing.buttonHeightMd,
	},
});
