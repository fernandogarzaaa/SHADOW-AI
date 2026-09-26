import * as Haptics from "expo-haptics";
import { router } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useProfileStore, type AgentTone } from "@/stores/useProfileStore";
import { Spacing, typography, useTheme } from "../../src/theme";

const TONES: Array<{ id: AgentTone; label: string; blurb: string }> = [
	{ id: "warm", label: "warm", blurb: "calm and friendly, like a thoughtful friend" },
	{ id: "direct", label: "direct", blurb: "short answers, no small talk" },
	{ id: "playful", label: "playful", blurb: "light and fun, still helpful" },
];

/**
 * Final onboarding step: name the agent and shape how it talks.
 * Stored in the local profile; editable later in Settings.
 */
export default function PersonalityScreen() {
	const { colors } = useTheme();
	const insets = useSafeAreaInsets();
	const { profile, saveProfile } = useProfileStore();
	const [agentName, setAgentName] = useState(profile.agentName || "shadow");
	const [tone, setTone] = useState<AgentTone>(profile.tone);

	async function handleDone() {
		const name = agentName.trim() || "shadow";
		Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
		await saveProfile({ agentName: name, tone });
		router.replace("/(tabs)/chat");
	}

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
			<View style={styles.body}>
				<Text style={[typography.h1, { color: colors.foreground }]}>
					make me yours
				</Text>
				<Text style={[typography.body, { color: colors.mutedForeground, marginTop: 8 }]}>
					give me a name and tell me how to talk. you can change
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
								style={[
									styles.tone,
									{
										borderColor: active ? colors.primary : colors.border,
										backgroundColor: colors.card,
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
			</View>

			<Pressable
				onPress={() => void handleDone()}
				style={[styles.cta, { backgroundColor: colors.primary }]}
				accessibilityRole="button"
				accessibilityLabel="Start chatting"
			>
				<Text style={[typography.uiLabel, { color: "#FFFFFF", fontWeight: "700" }]}>
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
	label: {
		marginTop: Spacing.xl,
		marginBottom: Spacing.sm,
		fontWeight: "700",
	},
	input: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: 12,
		paddingHorizontal: Spacing.md,
		paddingVertical: 12,
		fontSize: 16,
	},
	tones: {
		gap: Spacing.sm,
	},
	tone: {
		borderWidth: 1.5,
		borderRadius: 14,
		padding: Spacing.md,
		gap: 2,
	},
	cta: {
		borderRadius: 16,
		paddingVertical: 16,
		alignItems: "center",
	},
});
