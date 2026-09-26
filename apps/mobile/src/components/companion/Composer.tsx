import * as Haptics from "expo-haptics";
import { useState } from "react";
import {
	ActivityIndicator,
	Pressable,
	StyleSheet,
	Text,
	TextInput,
	View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
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
 * placeholder, cobalt up-arrow send button.
 *
 * Note: voice input (mic) is intentionally not shown yet. It needs a
 * real transcription path before it can ship; see the PR handoff notes.
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

	return (
		<View
			style={[
				styles.container,
				{
					backgroundColor: colors.background,
					paddingBottom: Math.max(insets.bottom, Spacing.sm),
				},
			]}
		>
			{menuOpen ? (
				<View
					style={[
						styles.menu,
						{
							backgroundColor: colors.card,
							borderColor: colors.border,
						},
					]}
				>
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
				</View>
			) : null}

			<View
				style={[
					styles.pill,
					{
						backgroundColor: colors.card,
						borderColor: colors.border,
					},
				]}
			>
				<Pressable
					onPress={() => {
						Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
						setMenuOpen((open) => !open);
					}}
					style={({ pressed }) => [
						styles.plusButton,
						{ opacity: pressed ? 0.6 : 1 },
					]}
					accessibilityRole="button"
					accessibilityLabel="More actions"
				>
					<Text style={[typography.h2, { color: colors.mutedForeground }]}>
						＋
					</Text>
				</Pressable>

				<TextInput
					style={[styles.input, typography.body, { color: colors.foreground }]}
					placeholder="Message"
					placeholderTextColor={colors.mutedForeground}
					value={text}
					onChangeText={setText}
					multiline
					maxLength={8000}
					editable={!disabled}
					onSubmitEditing={handleSend}
					blurOnSubmit={false}
					returnKeyType="send"
				/>

				{streaming ? (
					<Pressable
						onPress={() => {
							Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
							onStop();
						}}
						style={[styles.sendButton, { backgroundColor: colors.foreground }]}
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
						accessibilityLabel="Send message"
						accessibilityRole="button"
					>
						{disabled ? (
							<ActivityIndicator size="small" color={colors.mutedForeground} />
						) : (
							<Text
								style={[
									typography.uiLabel,
									{
										color: canSend ? colors.primaryForeground : colors.mutedForeground,
										fontWeight: "700",
									},
								]}
							>
								↑
							</Text>
						)}
					</Pressable>
				)}
			</View>
		</View>
	);
}

const styles = StyleSheet.create({
	container: {
		paddingHorizontal: Spacing.md,
		paddingTop: Spacing.sm,
	},
	menu: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: 16,
		marginBottom: Spacing.sm,
		overflow: "hidden",
	},
	menuItem: {
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.md,
	},
	menuDivider: {
		height: StyleSheet.hairlineWidth,
	},
	pill: {
		flexDirection: "row",
		alignItems: "center",
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: 28,
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
