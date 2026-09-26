import * as Haptics from "expo-haptics";
import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { getAvatar, type AvatarId } from "@/avatars";
import { ShadowAvatar } from "@/components/Avatar";
import { AvatarPicker } from "@/components/AvatarPicker";
import { SettingsScreen } from "@/components/settings/primitives";
import { useProfileStore } from "@/stores/useProfileStore";
import { SemanticSpacing, Spacing, typography, useTheme } from "@/theme";

/**
 * Avatar: pick the face of this SHADOW. The choice is stored on this
 * phone and used across chat, briefing, and the chats list.
 */
export default function AvatarScreen() {
	const { colors } = useTheme();
	const insets = useSafeAreaInsets();
	const { profile, saveProfile } = useProfileStore();
	const [avatarId, setAvatarId] = useState<AvatarId>(profile.avatarId);
	const [saved, setSaved] = useState(false);

	useEffect(() => {
		setAvatarId(profile.avatarId);
	}, [profile.avatarId]);

	const dirty = avatarId !== profile.avatarId;
	const avatar = getAvatar(avatarId);

	async function handleSave() {
		await saveProfile({ avatarId });
		setSaved(true);
		Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
		setTimeout(() => setSaved(false), 2000);
	}

	return (
		<SettingsScreen title="Avatar" showClose={false}>
			<View style={[styles.hero, { paddingTop: Spacing.lg }]}>
				<ShadowAvatar avatarId={avatarId} size={96} />
				<Text style={[typography.h2, { color: colors.foreground, marginTop: Spacing.sm }]}>
					{avatar.label}
				</Text>
				<Text
					style={[
						typography.body,
						{ color: colors.mutedForeground, textAlign: "center", marginTop: 4 },
					]}
				>
					This is the face of your SHADOW, everywhere in the app.
				</Text>
			</View>

			<AvatarPicker value={avatarId} onSelect={setAvatarId} thumbSize={56} />

			<Pressable
				onPress={() => void handleSave()}
				disabled={!dirty}
				style={({ pressed }) => [
					styles.saveButton,
					{
						backgroundColor: dirty ? colors.primary : colors.muted,
						opacity: pressed && dirty ? 0.8 : 1,
						marginBottom: Math.max(insets.bottom, Spacing.md),
					},
				]}
				accessibilityRole="button"
				accessibilityLabel="Save avatar"
			>
				<Text
					style={[
						typography.uiLabel,
						{ color: dirty ? colors.primaryForeground : colors.mutedForeground, fontWeight: "700" },
					]}
				>
					{saved ? "Saved" : "Save"}
				</Text>
			</Pressable>
		</SettingsScreen>
	);
}

const styles = StyleSheet.create({
	hero: {
		alignItems: "center",
		marginBottom: Spacing.lg,
	},
	saveButton: {
		marginTop: Spacing.xl,
		borderRadius: 999,
		minHeight: SemanticSpacing.buttonHeightMd,
		alignItems: "center",
		justifyContent: "center",
		paddingHorizontal: Spacing.lg,
	},
});
