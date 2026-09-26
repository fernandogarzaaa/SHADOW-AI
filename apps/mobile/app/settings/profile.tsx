import * as Haptics from "expo-haptics";
import { useEffect, useState } from "react";
import {
	Alert,
	Pressable,
	ScrollView,
	StyleSheet,
	Text,
	TextInput,
	View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useProfileStore, type AgentTone } from "@/stores/useProfileStore";
import { Spacing, typography, useTheme } from "../../src/theme";

const TONES: Array<{ id: AgentTone; label: string }> = [
	{ id: "warm", label: "warm" },
	{ id: "direct", label: "direct" },
	{ id: "playful", label: "playful" },
];

/**
 * Explicit local profile (memory v1). Everything here was typed by the
 * user; shadow learns nothing in the background. The profile is injected
 * into each chat's system prompt and stored only on this phone.
 */
export default function ProfileScreen() {
	const { colors } = useTheme();
	const insets = useSafeAreaInsets();
	const { profile, saveProfile, clearProfile } = useProfileStore();

	const [name, setName] = useState(profile.name);
	const [facts, setFacts] = useState(profile.facts.join("\n"));
	const [preferences, setPreferences] = useState(profile.preferences.join("\n"));
	const [agentName, setAgentName] = useState(profile.agentName);
	const [tone, setTone] = useState<AgentTone>(profile.tone);
	const [saved, setSaved] = useState(false);

	useEffect(() => {
		setName(profile.name);
		setFacts(profile.facts.join("\n"));
		setPreferences(profile.preferences.join("\n"));
		setAgentName(profile.agentName);
		setTone(profile.tone);
	}, [profile]);

	const dirty =
		name.trim() !== profile.name ||
		facts !== profile.facts.join("\n") ||
		preferences !== profile.preferences.join("\n") ||
		agentName.trim() !== profile.agentName ||
		tone !== profile.tone;

	async function handleSave() {
		await saveProfile({
			name,
			facts: facts.split("\n"),
			preferences: preferences.split("\n"),
			agentName,
			tone,
		});
		setSaved(true);
		Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
		setTimeout(() => setSaved(false), 2000);
	}

	function handleClear() {
		Alert.alert(
			"Clear profile",
			"This deletes your name, facts, preferences, and agent personality from this phone.",
			[
				{ text: "Cancel", style: "cancel" },
				{
					text: "Clear",
					style: "destructive",
					onPress: () => void clearProfile(),
				},
			],
		);
	}

	const inputStyle = [
		styles.input,
		typography.body,
		{
			color: colors.foreground,
			backgroundColor: colors.card,
			borderColor: colors.border,
		},
	];

	return (
		<ScrollView
			style={{ backgroundColor: colors.background }}
			contentContainerStyle={[
				styles.container,
				{
					paddingTop: insets.top + Spacing.md,
					paddingBottom: Math.max(insets.bottom, Spacing.xl),
				},
			]}
			keyboardShouldPersistTaps="handled"
		>
			<Text style={[typography.h1, { color: colors.foreground }]}>
				local profile
			</Text>
			<Text style={[typography.body, { color: colors.mutedForeground, marginTop: 8 }]}>
				only what you write here. i add it to each chat so i
				know the basics about you. nothing is learned in the
				background and nothing leaves this phone.
			</Text>

			<Text style={[styles.label, typography.uiLabel, { color: colors.foreground }]}>
				My name
			</Text>
			<TextInput
				style={inputStyle}
				value={agentName}
				onChangeText={setAgentName}
				placeholder="shadow"
				placeholderTextColor={colors.mutedForeground}
				maxLength={24}
				autoCapitalize="none"
			/>

			<Text style={[styles.label, typography.uiLabel, { color: colors.foreground }]}>
				How I talk
			</Text>
			<View style={styles.toneRow}>
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
								styles.tonePill,
								{
									borderColor: active ? colors.primary : colors.border,
									backgroundColor: active ? colors.userBubble : colors.card,
								},
							]}
							accessibilityRole="radio"
							accessibilityState={{ selected: active }}
							accessibilityLabel={`Tone: ${t.label}`}
						>
							<Text
								style={[
									typography.uiLabel,
									{
										color: colors.foreground,
										fontWeight: active ? "700" : "400",
									},
								]}
							>
								{t.label}
							</Text>
						</Pressable>
					);
				})}
			</View>

			<Text style={[styles.label, typography.uiLabel, { color: colors.foreground }]}>
				Your name
			</Text>
			<TextInput
				style={inputStyle}
				value={name}
				onChangeText={setName}
				placeholder="What should I call you?"
				placeholderTextColor={colors.mutedForeground}
				autoCapitalize="words"
			/>

			<Text style={[styles.label, typography.uiLabel, { color: colors.foreground }]}>
				Facts about you
			</Text>
			<TextInput
				style={[inputStyle, styles.multiline]}
				value={facts}
				onChangeText={setFacts}
				placeholder={"One per line, for example:\nLives in Manila\nWorks night shifts"}
				placeholderTextColor={colors.mutedForeground}
				multiline
			/>

			<Text style={[styles.label, typography.uiLabel, { color: colors.foreground }]}>
				Preferences
			</Text>
			<TextInput
				style={[inputStyle, styles.multiline]}
				value={preferences}
				onChangeText={setPreferences}
				placeholder={"One per line, for example:\nKeep answers short\nUse metric units"}
				placeholderTextColor={colors.mutedForeground}
				multiline
			/>

			<Pressable
				onPress={() => void handleSave()}
				disabled={!dirty}
				style={[
					styles.saveButton,
					{ backgroundColor: dirty ? colors.primary : colors.muted },
				]}
				accessibilityRole="button"
				accessibilityLabel="Save profile"
			>
				<Text
					style={[
						typography.uiLabel,
						{
							color: dirty ? colors.primaryForeground : colors.mutedForeground,
							fontWeight: "700",
						},
					]}
				>
					{saved ? "Saved" : "Save"}
				</Text>
			</Pressable>

			<Pressable
				onPress={handleClear}
				style={styles.clearRow}
				accessibilityRole="button"
				accessibilityLabel="Clear profile"
			>
				<Text style={[typography.body, { color: colors.destructive }]}>
					Clear profile
				</Text>
			</Pressable>
		</ScrollView>
	);
}

const styles = StyleSheet.create({
	container: {
		flexGrow: 1,
		paddingHorizontal: Spacing.xl,
	},
	label: {
		marginTop: Spacing.lg,
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
	toneRow: {
		flexDirection: "row",
		gap: Spacing.sm,
	},
	tonePill: {
		borderWidth: 1.5,
		borderRadius: 18,
		paddingHorizontal: Spacing.md,
		paddingVertical: 10,
	},
	multiline: {
		minHeight: 96,
		textAlignVertical: "top",
	},
	saveButton: {
		marginTop: Spacing.xl,
		borderRadius: 14,
		paddingVertical: 14,
		alignItems: "center",
	},
	clearRow: {
		marginTop: Spacing.md,
		alignItems: "center",
		paddingVertical: 8,
	},
});
