import * as Haptics from "expo-haptics";
import { router } from "expo-router";
import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { getAvatar, type AvatarId } from "@/avatars";
import { ShadowAvatar } from "@/components/Avatar";
import { AvatarPicker } from "@/components/AvatarPicker";
import { useProfileStore, type AgentTone } from "@/stores/useProfileStore";
import { SemanticSpacing, Spacing, typography, useTheme } from "../../src/theme";

const TONES: Array<{ id: AgentTone; label: string; blurb: string }> = [
	{ id: "warm", label: "warm", blurb: "calm and friendly, like a thoughtful friend" },
	{ id: "direct", label: "direct", blurb: "short answers, no small talk" },
	{ id: "playful", label: "playful", blurb: "light and fun, still helpful" },
];

/**
 * Final onboarding step: name the agent, pick its face, and shape how it
 * talks. Stored in the local profile; editable later in Settings.
 */
export default function PersonalityScreen() {
	const { colors } = useTheme();
	const insets = useSafeAreaInsets();
	const { profile, saveProfile } = useProfileStore();
	const [agentName, setAgentName] = useState(profile.agentName || "shadow");
	const [tone, setTone] = useState<AgentTone>(profile.tone);
	const [avatarId, setAvatarId] = useState<AvatarId>(profile.avatarId);

	async function handleDone() {
		const name = agentName.trim() || "shadow";
		Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
		await saveProfile({ agentName: name, tone, avatarId });
		router.replace("/(tabs)/chat");
	}

	const avatar = getAvatar(avatarId);

	return (
		<View
			style={[
				styles.container,
				{
					backgroundColor: colors.background,
					paddingTop: insets.top + Spacing.xl,
					paddingBottom: Math.max(insets.bottom, Spacing.xl),
				},
			]}
		>
			<ScrollView
				style={styles.body}
				contentContainerStyle={styles.bodyContent}
				showsVerticalScrollIndicator={false}
				keyboardShouldPersistTaps="handled"
			>
				<Text style={[typography.h1, { color: colors.foreground }]}>
					make me yours
				</Text>
				<Text style={[typography.body, { color: colors.mutedForeground, marginTop: Spacing.sm }]}>
					give me a name, pick my face, and tell me how to talk. you can change
					this anytime in settings.
				</Text>

				<Text style={[styles.label, typography.uiLabel, { color: colors.foreground }]}>
					my name
				</Text>
				<TextInput
					style={[
						styles.input,
						typography.body,
						{
							color: colors.foreground,
							backgroundColor: colors.card,
							borderColor: colors.border,
						},
					]}
					value={agentName}
					onChangeText={setAgentName}
					placeholder="shadow"
					placeholderTextColor={colors.mutedForeground}
					maxLength={24}
					autoCapitalize="none"
				/>

				<Text style={[styles.label, typography.uiLabel, { color: colors.foreground }]}>
					my look
				</Text>
				<View
					style={styles.previewRow}
					accessibilityRole="image"
					accessibilityLabel={`Preview: ${avatar.label} avatar`}
				>
					<ShadowAvatar avatarId={avatarId} size={96} />
					<Text style={[typography.body, { color: colors.mutedForeground, flex: 1 }]}>
						this is the face of {agentName.trim() || "shadow"}. it shows up in
						chat, your chats list, and approvals.
					</Text>
				</View>
				<AvatarPicker value={avatarId} onSelect={setAvatarId} />

				<Text style={[styles.label, typography.uiLabel, { color: colors.foreground }]}>
					how i talk
				</Text>
				<View style={styles.tones}>
					{TONES.map((t) => {
						const active = tone === t.id;
						return (
							<Pressable
								key={t.id}
								onPress={() => {
									Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
									setTone(t.id);
								}}
								style={({ pressed }) => [
									styles.tone,
									{
										borderColor: active ? colors.primary : colors.border,
										backgroundColor: colors.card,
										opacity: pressed ? 0.7 : 1,
									},
								]}
								accessibilityRole="radio"
								accessibilityState={{ selected: active }}
								accessibilityLabel={`${t.label}: ${t.blurb}`}
							>
								<Text
									style={[
										typography.body,
										{
											color: colors.foreground,
											fontWeight: active ? "700" : "400",
										},
									]}
								>
									{t.label}
								</Text>
								<Text style={[typography.meta, { color: colors.mutedForeground }]}>
									{t.blurb}
								</Text>
							</Pressable>
						);
					})}
				</View>
			</ScrollView>

			<Pressable
				onPress={() => void handleDone()}
				style={({ pressed }) => [
					styles.cta,
					{ backgroundColor: colors.primary, opacity: pressed ? 0.85 : 1 },
				]}
				accessibilityRole="button"
				accessibilityLabel="Start chatting"
			>
				<Text style={[typography.uiLabel, { color: colors.primaryForeground, fontWeight: "700" }]}>
					start chatting
				</Text>
			</Pressable>
		</View>
	);
}

const styles = StyleSheet.create({
	container: {
		flex: 1,
		paddingHorizontal: Spacing.xl,
	},
	body: {
		flex: 1,
	},
	bodyContent: {
		paddingBottom: Spacing.lg,
	},
	label: {
		marginTop: Spacing.xl,
		marginBottom: Spacing.sm,
		fontWeight: "700",
	},
	input: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: SemanticSpacing.radiusInput,
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.md,
		minHeight: SemanticSpacing.inputHeight,
	},
	previewRow: {
		flexDirection: "row",
		alignItems: "center",
		gap: Spacing.md,
		marginBottom: Spacing.md,
	},
	tones: {
		gap: Spacing.sm,
	},
	tone: {
		borderWidth: 1.5,
		borderRadius: SemanticSpacing.radiusCard,
		padding: Spacing.md,
		gap: 2,
		minHeight: SemanticSpacing.buttonHeightMd,
		justifyContent: "center",
	},
	cta: {
		borderRadius: SemanticSpacing.radiusModal,
		minHeight: SemanticSpacing.buttonHeightLg,
		justifyContent: "center",
		alignItems: "center",
	},
});
