import BottomSheet from "@gorhom/bottom-sheet";
import * as Haptics from "expo-haptics";
import { useRouter } from "expo-router";
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
import { ThreadSheet } from "@/components/companion/ThreadSheet";
import { ShadowAvatar } from "@/components/Avatar";
import { MenuIcon, PlusIcon } from "@/components/icons";
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

export default function ChatScreen() {
	const { colors } = useTheme();
	const router = useRouter();
	const insets = useSafeAreaInsets();

	const { threads, activeThreadId, setActiveThread, createThread } = useChatStore();
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

	const threadSheetRef = useRef<BottomSheet>(null);
	const modelSheetRef = useRef<BottomSheet>(null);
	const keySheetRef = useRef<BottomSheet>(null);
	const [keyProvider, setKeyProvider] = useState<ProviderId>("anthropic");
	const listRef = useRef<FlatList<ChatMessage>>(null);

	const thread = threads.find((t) => t.id === activeThreadId) ?? null;
	const messages = useMemo(
		() => (thread ? [...thread.messages].reverse() : []),
		[thread],
	);

	// Ensure there is always an active thread once stores are ready.
	useEffect(() => {
		if (!initialized) return;
		if (!activeThreadId) {
			void createThread(providerId, modelId);
		}
	}, [initialized, activeThreadId, createThread, providerId, modelId]);

	// Refresh smart replies when the active thread changes.
	useEffect(() => {
		if (activeThreadId && !streaming) {
			refreshSmartReplies(activeThreadId);
		}
	}, [activeThreadId, streaming, refreshSmartReplies]);

	const ensureThread = useCallback(async (): Promise<string | null> => {
		if (activeThreadId) return activeThreadId;
		return createThread(providerId, modelId);
	}, [activeThreadId, createThread, providerId, modelId]);

	const handleSend = useCallback(
		async (text: string) => {
			clearError();
			const id = await ensureThread();
			if (id) {
				await send(id, text);
			}
		},
		[ensureThread, send, clearError],
	);

	const handleRetry = useCallback(async () => {
		if (!activeThreadId) return;
		clearError();
		// Retry re-runs the failed turn; it never duplicates the user message.
		await retry(activeThreadId);
	}, [activeThreadId, retry, clearError]);

	const handleNewThread = useCallback(async () => {
		if (streaming) stop();
		threadSheetRef.current?.close();
		await createThread(providerId, modelId);
	}, [createThread, providerId, modelId, streaming, stop]);

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
			await createThread(pickedProvider, pickedModel);
		},
		[providerId, modelId, setProvider, setModel, createThread, streaming, stop],
	);

	const handleAddKey = useCallback((id: ProviderId) => {
		modelSheetRef.current?.close();
		setKeyProvider(id);
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
						threadSheetRef.current?.snapToIndex(0);
					}}
					style={({ pressed }) => [
						styles.headerButton,
						{ opacity: pressed ? 0.6 : 1 },
					]}
					hitSlop={10}
					accessibilityRole="button"
					accessibilityLabel="Open chat list"
				>
					<MenuIcon size={22} color={colors.foreground} />
				</Pressable>

				<View
					style={styles.headerTitle}
					accessibilityRole="header"
					accessibilityLabel={`Chat with ${agentName || "shadow"}. ${thread?.title ?? "New chat"}. ${threadProvider.label}, ${threadModelLabel}.`}
				>
					<ShadowAvatar avatarId={avatarId} size={32} />
					<View style={styles.headerTitleText}>
						<Text
							style={[typography.uiLabel, { color: colors.foreground, fontWeight: "700" }]}
							numberOfLines={1}
						>
							{agentName || "shadow"}
						</Text>
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
								style={[typography.meta, { color: colors.mutedForeground }]}
								numberOfLines={1}
							>
								{thread?.title ?? "New chat"} · {threadProvider.label} · {threadModelLabel}
							</Text>
						</Pressable>
					</View>
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
				streaming={streaming && streamingThreadId === activeThreadId}
				disabled={!initialized}
			/>

			<ThreadSheet
				ref={threadSheetRef}
				onSelect={(id) => {
					if (streaming) stop();
					threadSheetRef.current?.close();
					setActiveThread(id);
				}}
				onNewThread={() => void handleNewThread()}
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
		paddingBottom: Spacing.sm,
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
		flexDirection: "row",
		alignItems: "center",
		justifyContent: "center",
		gap: Spacing.sm,
	},
	headerTitleText: {
		flexShrink: 1,
		gap: 2,
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
