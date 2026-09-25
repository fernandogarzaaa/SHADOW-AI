import { useEffect, useRef, useState } from "react";
import {
	FlatList,
	KeyboardAvoidingView,
	Platform,
	Pressable,
	Text,
	TextInput,
	View,
} from "react-native";
import { router } from "expo-router";
import * as Clipboard from "expo-clipboard";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import {
	AlertCircleIcon,
	ChatIcon,
	CopyIcon,
	RefreshIcon,
	SendIcon,
	StopIcon,
} from "@/components/icons";
import { MarkdownRenderer } from "@/components/markdown/MarkdownRenderer";
import { useChatStream, type ChatMessage } from "@/hooks/useChatStream";
import { useConnectionStore } from "@/stores/useConnectionStore";
import { useTheme } from "@/theme";

async function copyText(text: string): Promise<void> {
	await Clipboard.setStringAsync(text);
	await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
}

function MessageBubble({
	message,
	onCopy,
	onRetry,
}: {
	message: ChatMessage;
	onCopy: () => void;
	onRetry: () => void;
}) {
	const { colors } = useTheme();
	const isUser = message.role === "user";

	if (isUser) {
		return (
			<View style={{ alignItems: "flex-end", marginVertical: 4 }}>
				<View
					style={{
						maxWidth: "85%",
						backgroundColor: colors.primary,
						borderRadius: 16,
						borderBottomRightRadius: 4,
						paddingHorizontal: 14,
						paddingVertical: 10,
					}}
				>
					<Text style={{ color: colors.primaryForeground, fontSize: 15 }}>
						{message.text}
					</Text>
				</View>
				<Pressable
					onPress={onCopy}
					hitSlop={8}
					style={{ padding: 6 }}
					accessibilityLabel="Copy message"
				>
					<CopyIcon size={14} color={colors.mutedForeground} />
				</Pressable>
			</View>
		);
	}

	if (message.failed) {
		return (
			<View style={{ alignItems: "flex-start", marginVertical: 4 }}>
				<View
					style={{
						maxWidth: "90%",
						backgroundColor: colors.card,
						borderRadius: 16,
						borderBottomLeftRadius: 4,
						borderWidth: 1,
						borderColor: colors.destructive,
						paddingHorizontal: 14,
						paddingVertical: 10,
						gap: 8,
					}}
				>
					<View
						style={{ flexDirection: "row", alignItems: "center", gap: 6 }}
					>
						<AlertCircleIcon size={16} color={colors.destructive} />
						<Text
							style={{
								color: colors.destructive,
								fontSize: 13,
								fontWeight: "600",
							}}
						>
							Send failed
						</Text>
					</View>
					<Text style={{ color: colors.foreground, fontSize: 14 }}>
						{message.text}
					</Text>
					<Pressable
						onPress={onRetry}
						style={{
							flexDirection: "row",
							alignItems: "center",
							gap: 6,
							alignSelf: "flex-start",
							paddingVertical: 6,
							paddingHorizontal: 12,
							borderRadius: 999,
							backgroundColor: colors.muted,
						}}
						accessibilityLabel="Retry request"
					>
						<RefreshIcon size={14} color={colors.foreground} />
						<Text style={{ color: colors.foreground, fontSize: 13 }}>
							Retry
						</Text>
					</Pressable>
				</View>
			</View>
		);
	}

	return (
		<View style={{ alignItems: "flex-start", marginVertical: 4 }}>
			<View
				style={{
					maxWidth: "90%",
					backgroundColor: colors.card,
					borderRadius: 16,
					borderBottomLeftRadius: 4,
					paddingHorizontal: 14,
					paddingVertical: 10,
				}}
			>
				{message.streaming ? (
					<Text style={{ color: colors.foreground, fontSize: 15 }}>
						{message.text}
						<Text style={{ color: colors.primary }}>{"\u25cd"}</Text>
					</Text>
				) : (
					<MarkdownRenderer content={message.text} />
				)}
			</View>
			{!message.streaming && message.text.length > 0 ? (
				<Pressable
					onPress={onCopy}
					hitSlop={8}
					style={{ padding: 6 }}
					accessibilityLabel="Copy message"
				>
					<CopyIcon size={14} color={colors.mutedForeground} />
				</Pressable>
			) : null}
		</View>
	);
}

export default function ChatScreen() {
	const insets = useSafeAreaInsets();
	const { colors } = useTheme();
	const { isPaired } = useConnectionStore();
	const { messages, sending, send, cancel, retry } = useChatStream();
	const [draft, setDraft] = useState("");
	const listRef = useRef<FlatList<ChatMessage>>(null);

	useEffect(() => {
		if (messages.length > 0) {
			listRef.current?.scrollToEnd({ animated: true });
		}
	}, [messages]);

	const canSend = draft.trim().length > 0 && !sending;

	const handleSend = () => {
		const text = draft.trim();
		if (!text || sending) return;
		void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
		setDraft("");
		send(text);
	};

	if (!isPaired) {
		return (
			<View
				style={{
					flex: 1,
					backgroundColor: colors.background,
					alignItems: "center",
					justifyContent: "center",
					paddingHorizontal: 32,
					gap: 12,
				}}
			>
				<ChatIcon size={48} color={colors.mutedForeground} />
				<Text
					style={{
						color: colors.foreground,
						fontSize: 18,
						fontWeight: "600",
						textAlign: "center",
					}}
				>
					Not connected
				</Text>
				<Text
					style={{
						color: colors.mutedForeground,
						fontSize: 14,
						textAlign: "center",
					}}
				>
					Pair with your SHADOW node to start chatting.
				</Text>
				<Pressable
					onPress={() => router.push("/onboarding/scan")}
					style={{
						marginTop: 8,
						backgroundColor: colors.primary,
						borderRadius: 999,
						paddingVertical: 12,
						paddingHorizontal: 28,
					}}
					accessibilityLabel="Pair with node"
				>
					<Text
						style={{
							color: colors.primaryForeground,
							fontSize: 15,
							fontWeight: "600",
						}}
					>
						Pair node
					</Text>
				</Pressable>
			</View>
		);
	}

	return (
		<View style={{ flex: 1, backgroundColor: colors.background }}>
			<KeyboardAvoidingView
				behavior={Platform.OS === "ios" ? "padding" : "height"}
				style={{ flex: 1 }}
				keyboardVerticalOffset={insets.top}
			>
				<FlatList
					ref={listRef}
					data={messages}
					keyExtractor={(item) => item.id}
					renderItem={({ item }) => (
						<MessageBubble
							message={item}
							onCopy={() => void copyText(item.text)}
							onRetry={() => retry(item.id)}
						/>
					)}
					contentContainerStyle={{
						paddingHorizontal: 16,
						paddingTop: 12,
						paddingBottom: 12,
						flexGrow: 1,
					}}
					ListEmptyComponent={
						<View
							style={{
								flex: 1,
								alignItems: "center",
								justifyContent: "center",
								gap: 8,
								paddingVertical: 48,
							}}
						>
							<Text
								style={{
									color: colors.foreground,
									fontSize: 17,
									fontWeight: "600",
								}}
							>
								Ask SHADOW anything
							</Text>
							<Text
								style={{
									color: colors.mutedForeground,
									fontSize: 14,
									textAlign: "center",
								}}
							>
								Your node answers here. Responses stream in live.
							</Text>
						</View>
					}
					keyboardShouldPersistTaps="handled"
				/>
				<View
					style={{
						borderTopWidth: 1,
						borderTopColor: colors.border,
						backgroundColor: colors.background,
						paddingHorizontal: 12,
						paddingTop: 8,
						paddingBottom: Math.max(insets.bottom, 12),
					}}
				>
					<View
						style={{
							flexDirection: "row",
							alignItems: "flex-end",
							gap: 8,
						}}
					>
						<TextInput
							value={draft}
							onChangeText={setDraft}
							placeholder="Message SHADOW"
							placeholderTextColor={colors.mutedForeground}
							multiline
							maxLength={8000}
							editable={!sending}
							style={{
								flex: 1,
								maxHeight: 120,
								minHeight: 40,
								backgroundColor: colors.card,
								borderRadius: 20,
								borderWidth: 1,
								borderColor: colors.border,
								paddingHorizontal: 16,
								paddingVertical: 10,
								color: colors.foreground,
								fontSize: 15,
							}}
							onSubmitEditing={handleSend}
							blurOnSubmit={false}
							returnKeyType="send"
						/>
						{sending ? (
							<Pressable
								onPress={cancel}
								style={{
									width: 40,
									height: 40,
									borderRadius: 20,
									backgroundColor: colors.muted,
									alignItems: "center",
									justifyContent: "center",
								}}
								accessibilityLabel="Stop generating"
							>
								<StopIcon size={18} color={colors.foreground} />
							</Pressable>
						) : (
							<Pressable
								onPress={handleSend}
								disabled={!canSend}
								style={{
									width: 40,
									height: 40,
									borderRadius: 20,
									backgroundColor: canSend ? colors.primary : colors.muted,
									alignItems: "center",
									justifyContent: "center",
									opacity: canSend ? 1 : 0.6,
								}}
								accessibilityLabel="Send message"
							>
								<SendIcon
									size={18}
									color={canSend ? colors.primaryForeground : colors.mutedForeground}
								/>
							</Pressable>
						)}
					</View>
				</View>
			</KeyboardAvoidingView>
		</View>
	);
}
