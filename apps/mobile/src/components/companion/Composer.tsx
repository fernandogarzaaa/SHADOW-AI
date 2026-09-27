import * as Haptics from "expo-haptics";
import * as FileSystem from "expo-file-system/legacy";
import { useState } from "react";
import {
	ActivityIndicator,
	Alert,
	Pressable,
	StyleSheet,
	Text,
	TextInput,
	View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { MicIcon, PlusIcon, SendIcon, StopIcon } from "@/components/icons";
import { GlassView } from "@/components/ui";
import { ShadowApiError, transcribeAudio } from "@/api/shadow";
import { useVoiceRecorder } from "@/hooks/useVoiceRecorder";
import { Spacing, typography, useTheme } from "@/theme";

interface ComposerProps {
	onSend: (text: string) => void;
	onStop: () => void;
	onNewChat: () => void;
	onSwitchModel: () => void;
	streaming: boolean;
	disabled?: boolean;
}

/**
 * Rounded pill composer: "+" action menu on the left, "Message"
 * placeholder, mic for voice input, cobalt up-arrow send button.
 *
 * The mic records with expo-av and transcribes through the node
 * (POST /voice/transcribe); the text lands in the composer for review
 * before sending. A 503 means the node has no speech-to-text provider.
 */
export function Composer({
	onSend,
	onStop,
	onNewChat,
	onSwitchModel,
	streaming,
	disabled,
}: ComposerProps) {
	const { colors } = useTheme();
	const insets = useSafeAreaInsets();
	const [text, setText] = useState("");
	const [menuOpen, setMenuOpen] = useState(false);
	const recorder = useVoiceRecorder();

	const canSend = text.trim().length > 0 && !streaming && !disabled;

	function handleSend() {
		const trimmed = text.trim();
		if (!trimmed || streaming || disabled) return;
		Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
		setText("");
		setMenuOpen(false);
		onSend(trimmed);
	}

	function handleMenuAction(action: () => void) {
		Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
		setMenuOpen(false);
		action();
	}

	async function handleMicPress() {
		if (streaming || disabled || recorder.transcribing) return;
		if (recorder.recording) {
			Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
			const uri = await recorder.stop();
			if (!uri) return;
			recorder.setTranscribing(true);
			try {
				const result = await transcribeAudio(uri);
				const heard = result.text.trim();
				if (heard) {
					setText((prev) =>
						prev.trim() ? `${prev.trim()} ${heard}` : heard,
					);
					void Haptics.notificationAsync(
						Haptics.NotificationFeedbackType.Success,
					);
				}
			} catch (e) {
				if (e instanceof ShadowApiError && e.status === 503) {
					Alert.alert(
						"Voice input unavailable",
						"Your node does not have speech-to-text set up yet. Type your message instead.",
					);
				} else {
					Alert.alert(
						"Could not transcribe",
						e instanceof ShadowApiError ? e.message : "Try again.",
					);
				}
			} finally {
				recorder.setTranscribing(false);
				// The recording served its purpose; do not keep audio on disk.
				void FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => {});
			}
			return;
		}
		Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
		await recorder.start();
	}

	return (
		<View
			style={[
				styles.container,
				{
					paddingBottom: Math.max(insets.bottom, Spacing.sm),
				},
			]}
		>
			{menuOpen ? (
				<GlassView borderRadius={16} style={styles.menu}>
					<Pressable
						onPress={() => handleMenuAction(onNewChat)}
						style={styles.menuItem}
						accessibilityRole="button"
						accessibilityLabel="Start a new chat"
					>
						<Text style={[typography.body, { color: colors.foreground }]}>
							new chat
						</Text>
					</Pressable>
					<View style={[styles.menuDivider, { backgroundColor: colors.border }]} />
					<Pressable
						onPress={() => handleMenuAction(onSwitchModel)}
						style={styles.menuItem}
						accessibilityRole="button"
						accessibilityLabel="Switch model"
					>
						<Text style={[typography.body, { color: colors.foreground }]}>
							switch model
						</Text>
					</Pressable>
				</GlassView>
			) : null}

			<GlassView borderRadius={28} intensity={80}>
				<View style={styles.pillInner}>
				<Pressable
					onPress={() => {
						Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
						setMenuOpen((open) => !open);
					}}
					style={({ pressed }) => [
						styles.plusButton,
						{ opacity: pressed ? 0.6 : 1 },
					]}
					// Visual is 36pt; the hit area reaches the 44pt minimum.
					hitSlop={6}
					accessibilityRole="button"
					accessibilityLabel="More actions"
					accessibilityState={{ expanded: menuOpen }}
				>
					<PlusIcon size={22} color={colors.mutedForeground} />
				</Pressable>

				<TextInput
					style={[styles.input, typography.body, { color: colors.foreground }]}
					placeholder={
						recorder.recording
							? `Recording ${recorder.elapsedSeconds}s, tap stop when done`
							: "Message"
					}
					placeholderTextColor={colors.mutedForeground}
					accessibilityLabel="Message input"
					accessibilityHint="Type a message to send to your agent"
					value={text}
					onChangeText={setText}
					multiline
					maxLength={8000}
					editable={!disabled}
					onSubmitEditing={handleSend}
					blurOnSubmit={false}
					returnKeyType="send"
				/>

				{recorder.transcribing ? (
					<View
						style={[styles.micButton, { backgroundColor: colors.muted }]}
						accessibilityLabel="Transcribing voice"
					>
						<ActivityIndicator size="small" color={colors.mutedForeground} />
					</View>
				) : (
					<Pressable
						onPress={() => void handleMicPress()}
						disabled={streaming || disabled}
						style={({ pressed }) => [
							styles.micButton,
							{
								backgroundColor: recorder.recording
									? colors.destructive
									: colors.muted,
								opacity: pressed || streaming || disabled ? 0.6 : 1,
							},
						]}
						hitSlop={6}
						accessibilityRole="button"
						accessibilityLabel={
							recorder.recording ? "Stop recording" : "Record voice message"
						}
					>
						{recorder.recording ? (
							<StopIcon size={18} color="#FFFFFF" />
						) : (
							<MicIcon
								size={18}
								color={colors.mutedForeground}
							/>
						)}
					</Pressable>
				)}

				{streaming ? (
					<Pressable
						onPress={() => {
							Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
							onStop();
						}}
						style={[styles.sendButton, { backgroundColor: colors.foreground }]}
						hitSlop={6}
						accessibilityLabel="Stop generating"
						accessibilityRole="button"
					>
						<View style={[styles.stopSquare, { backgroundColor: colors.background }]} />
					</Pressable>
				) : (
					<Pressable
						onPress={handleSend}
						disabled={!canSend}
						style={[
							styles.sendButton,
							{ backgroundColor: canSend ? colors.primary : colors.muted },
						]}
						hitSlop={6}
						accessibilityLabel="Send message"
						accessibilityRole="button"
						accessibilityState={{ disabled: !canSend }}
					>
						{disabled ? (
							<ActivityIndicator size="small" color={colors.mutedForeground} />
						) : (
							<SendIcon
								size={18}
								color={canSend ? colors.primaryForeground : colors.mutedForeground}
							/>
						)}
					</Pressable>
				)}
				</View>
			</GlassView>
		</View>
	);
}

const styles = StyleSheet.create({
	container: {
		paddingHorizontal: Spacing.md,
		paddingTop: Spacing.sm,
	},
	menu: {
		marginBottom: Spacing.sm,
	},
	menuItem: {
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.md,
	},
	menuDivider: {
		height: StyleSheet.hairlineWidth,
	},
	pillInner: {
		flexDirection: "row",
		alignItems: "center",
		paddingLeft: Spacing.sm,
		paddingRight: 6,
		paddingVertical: 6,
		gap: 4,
	},
	plusButton: {
		width: 36,
		height: 36,
		alignItems: "center",
		justifyContent: "center",
	},
	input: {
		flex: 1,
		maxHeight: 140,
		fontSize: 16,
		paddingVertical: 8,
	},
	micButton: {
		width: 36,
		height: 36,
		borderRadius: 18,
		alignItems: "center",
		justifyContent: "center",
	},
	sendButton: {
		width: 36,
		height: 36,
		borderRadius: 18,
		alignItems: "center",
		justifyContent: "center",
	},
	stopSquare: {
		width: 12,
		height: 12,
		borderRadius: 2,
	},
});
