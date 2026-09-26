import BottomSheet from "@gorhom/bottom-sheet";
import * as Haptics from "expo-haptics";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
	FlatList,
	KeyboardAvoidingView,
	Platform,
	Pressable,
	StyleSheet,
	Text,
	View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Composer } from "@/components/companion/Composer";
import { AgentMark } from "@/components/companion/AgentMark";
import { AgentStateLine } from "@/components/companion/AgentStateLine";
import { KeySheet } from "@/components/companion/KeySheet";
import { MessageView } from "@/components/companion/MessageView";
import { ModelSheet } from "@/components/companion/ModelSheet";
import { SmartReplies } from "@/components/companion/SmartReplies";
import { AvatarStatusPill } from "@/components/AvatarStatusPill";
import { ChevronLeftIcon, PlusIcon } from "@/components/icons";
import { useProviderChat } from "@/hooks/useProviderChat";
import { getProvider, type ProviderId } from "@/providers";
import { useChatStore, type ChatMessage } from "@/stores/useChatStore";
import { useProfileStore } from "@/stores/useProfileStore";
import { useProviderStore } from "@/stores/useProviderStore";
import { Spacing, SemanticSpacing, typography, useTheme } from "@/theme";

const SUGGESTIONS = [
	"plan my day",
	"explain a tricky idea simply",
	"draft a message",
	"brainstorm with me",
];

export default function ConversationScreen() {
	const { colors } = useTheme();
	const router = useRouter();
	const insets = useSafeAreaInsets();
	const { id } = useLocalSearchParams<{ id: string }>();

	const { threads, setActiveThread, createThread, markThreadRead } = useChatStore();
	const { providerId, modelId, initialized, setProvider, setModel } = useProviderStore();
	const agentName = useProfileStore((s) => s.profile.agentName);
	const avatarId = useProfileStore((s) => s.profile.avatarId);
	const {
		streaming,
		streamingThreadId,
		error,
		agentState,
		stateProviderLabel,
		stateModelId,
		stateStartedAt,
		smartReplies,
		send,
		retry,
		stop,
		clearError,
		refreshSmartReplies,
	} = useProviderChat();

	const modelSheetRef = useRef<BottomSheet>(null);
	const keySheetRef = useRef<BottomSheet>(null);
	const [keyProvider, setKeyProvider] = useState<ProviderId>("anthropic");
	const listRef = useRef<FlatList<ChatMessage>>(null);

	const thread = threads.find((t) => t.id === id) ?? null;
	const messages = useMemo(
		() => (thread ? [...thread.messages].reverse() : []),
		[thread],
	);

	// Keep the store's active thread in sync with the open conversation.
	useEffect(() => {
		if (id) setActiveThread(id);
	}, [id, setActiveThread]);

	// The user is viewing this thread: real last-read tracking for the
	// unread dots on the chats list.
	useFocusEffect(
		useCallback(() => {
			if (id) void markThreadRead(id);
		}, [id, markThreadRead]),
	);
	useEffect(() => {
		if (id) void markThreadRead(id);
	}, [id, thread?.updatedAt, markThreadRead]);

	// Unknown thread id: back to the chats list.
	useEffect(() => {
		if (initialized && id && !thread) {
			router.replace("/(tabs)/chat");
		}
	}, [initialized, id, thread, router]);

	// Refresh smart replies when the thread changes.
	useEffect(() => {
		if (id && !streaming) {
			refreshSmartReplies(id);
		}
	}, [id, streaming, refreshSmartReplies]);

	const handleSend = useCallback(
		async (text: string) => {
			clearError();
			if (id) {
				await send(id, text);
			}
		},
		[id, send, clearError],
	);

	const handleRetry = useCallback(async () => {
		if (!id) return;
		clearError();
		// Retry re-runs the failed turn; it never duplicates the user message.
		await retry(id);
	}, [id, retry, clearError]);

	const handleNewThread = useCallback(async () => {
		if (streaming) stop();
		const newId = await createThread(providerId, modelId);
		router.replace(`/chat/${newId}`);
	}, [createThread, providerId, modelId, streaming, stop, router]);

	const handlePickModel = useCallback(
		async (pickedProvider: ProviderId, pickedModel: string) => {
			modelSheetRef.current?.close();
			if (streaming) stop();
			if (pickedProvider !== providerId) {
				await setProvider(pickedProvider);
			}
			if (pickedModel !== modelId || pickedProvider !== providerId) {
				await setModel(pickedModel);
			}
			// A thread snapshots its provider/model, so a switch starts fresh.
			const newId = await createThread(pickedProvider, pickedModel);
			router.replace(`/chat/${newId}`);
		},
		[providerId, modelId, setProvider, setModel, createThread, streaming, stop, router],
	);

	const handleAddKey = useCallback((keyId: ProviderId) => {
		modelSheetRef.current?.close();
		setKeyProvider(keyId);
		setTimeout(() => keySheetRef.current?.snapToIndex(0), 300);
	}, []);

	const handleKeySaved = useCallback(async () => {
		keySheetRef.current?.close();
		await useProviderStore.getState().refreshKeyPresence();
		const savedProvider = keyProvider;
		await handlePickModel(savedProvider, getProvider(savedProvider).defaultModel);
	}, [handlePickModel, keyProvider]);

	const threadProvider = thread ? getProvider(thread.providerId) : getProvider(providerId);
	const threadModelLabel =
		threadProvider.models.find((m) => m.id === (thread?.modelId ?? modelId))?.label ??
		(thread?.modelId ?? modelId);

	return (
		<KeyboardAvoidingView
			style={[styles.container, { backgroundColor: colors.background }]}
			behavior={Platform.OS === "ios" ? "padding" : "height"}
			keyboardVerticalOffset={insets.top + 56}
		>
			<View
				style={[
					styles.header,
					{
						paddingTop: insets.top + Spacing.sm,
						borderBottomColor: colors.border,
					},
				]}
			>
				<Pressable
					onPress={() => {
						Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
						if (streaming) stop();
						router.back();
					}}
					style={({ pressed }) => [
						styles.headerButton,
						{ opacity: pressed ? 0.6 : 1 },
					]}
					hitSlop={10}
					accessibilityRole="button"
					accessibilityLabel="Back to chats"
				>
					<ChevronLeftIcon size={24} color={colors.foreground} />
				</Pressable>

				<View
					style={styles.headerTitle}
					accessibilityRole="header"
					accessibilityLabel={`Chat with ${agentName || "shadow"}. ${thread?.title ?? "New chat"}. ${threadProvider.label}, ${threadModelLabel}.`}
				>
					<AvatarStatusPill
						avatarId={avatarId}
						agentName={agentName || "shadow"}
						state={agentState}
						size={56}
					/>
					<Pressable
						onPress={() => {
							Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
							modelSheetRef.current?.snapToIndex(0);
						}}
						hitSlop={8}
						accessibilityRole="button"
						accessibilityLabel="Change model"
					>
						<Text
							style={[typography.meta, { color: colors.mutedForeground, textAlign: "center" }]}
							numberOfLines={1}
						>
							{thread?.title ?? "New chat"} · {threadProvider.label} · {threadModelLabel}
						</Text>
					</Pressable>
				</View>

				<Pressable
					onPress={() => {
						Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
						void handleNewThread();
					}}
					style={({ pressed }) => [
						styles.headerButton,
						{ opacity: pressed ? 0.6 : 1 },
					]}
					hitSlop={10}
					accessibilityRole="button"
					accessibilityLabel="Start a new chat"
				>
					<PlusIcon size={22} color={colors.foreground} />
				</Pressable>
			</View>

			{/* Agent state (thinking/working/error/offline) renders above the composer. */}

			{messages.length === 0 ? (
				<View style={styles.empty}>
					<View style={styles.emptyMark}>
						<AgentMark size={72} />
					</View>
					<Text style={[typography.h1, { color: colors.foreground, textAlign: "center" }]}>
						what's on your mind?
					</Text>
					<Text
						style={[
							typography.body,
							{ color: colors.mutedForeground, textAlign: "center", marginTop: 8 },
						]}
					>
						i'm {agentName || "shadow"}, your personal ai.{"\n"}
						{threadProvider.label} · {threadModelLabel}
					</Text>
					<View style={styles.suggestions}>
						{SUGGESTIONS.map((s) => (
							<Pressable
								key={s}
								onPress={() => void handleSend(s)}
								style={({ pressed }) => [
									styles.suggestion,
									{
										borderColor: colors.border,
										backgroundColor: colors.card,
										opacity: pressed ? 0.6 : 1,
									},
								]}
								accessibilityRole="button"
								accessibilityLabel={`Ask: ${s}`}
							>
								<Text style={[typography.body, { color: colors.foreground }]}>
									{s}
								</Text>
							</Pressable>
						))}
					</View>
				</View>
			) : (
				<FlatList
					ref={listRef}
					data={messages}
					keyExtractor={(m) => m.id}
					renderItem={({ item }) => <MessageView message={item} />}
					inverted
					keyboardDismissMode="interactive"
					keyboardShouldPersistTaps="handled"
					maintainVisibleContentPosition={{ minIndexForVisible: 0 }}
					contentContainerStyle={styles.listContent}
					removeClippedSubviews={false}
				/>
			)}

			{!streaming && smartReplies.length > 0 && messages.length > 0 ? (
				<SmartReplies
					replies={smartReplies}
					onPick={(reply) => void handleSend(reply)}
				/>
			) : null}

			<AgentStateLine
				state={agentState}
				agentName={agentName}
				providerLabel={stateProviderLabel}
				modelId={stateModelId}
				startedAt={stateStartedAt}
				errorMessage={error}
				onRetry={() => void handleRetry()}
				onDismiss={clearError}
				onViewApproval={() => router.replace("/(tabs)/approvals")}
			/>

			<Composer
				onSend={(text) => void handleSend(text)}
				onStop={stop}
				onNewChat={() => void handleNewThread()}
				onSwitchModel={() => {
					Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
					modelSheetRef.current?.snapToIndex(0);
				}}
				streaming={streaming && streamingThreadId === id}
				disabled={!initialized}
			/>

			<ModelSheet
				ref={modelSheetRef}
				onPick={(p, m) => void handlePickModel(p, m)}
				onAddKey={handleAddKey}
			/>
			<KeySheet
				ref={keySheetRef}
				providerId={keyProvider}
				onSaved={() => void handleKeySaved()}
			/>
		</KeyboardAvoidingView>
	);
}

const styles = StyleSheet.create({
	container: {
		flex: 1,
	},
	header: {
		flexDirection: "row",
		alignItems: "center",
		paddingHorizontal: Spacing.md,
		paddingBottom: Spacing.xs,
		borderBottomWidth: StyleSheet.hairlineWidth,
	},
	headerButton: {
		width: SemanticSpacing.buttonHeightMd,
		height: SemanticSpacing.buttonHeightMd,
		alignItems: "center",
		justifyContent: "center",
	},
	headerTitle: {
		flex: 1,
		alignItems: "center",
		justifyContent: "center",
		gap: 0,
	},
	listContent: {
		paddingTop: Spacing.md,
		paddingBottom: Spacing.sm,
	},
	empty: {
		flex: 1,
		justifyContent: "center",
		paddingHorizontal: Spacing.xl,
	},
	emptyMark: {
		alignItems: "center",
		marginBottom: Spacing.lg,
	},
	suggestions: {
		marginTop: Spacing.xl,
		gap: Spacing.sm,
	},
	suggestion: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: SemanticSpacing.radiusCard,
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.md,
		minHeight: SemanticSpacing.buttonHeightMd,
		justifyContent: "center",
	},
});
