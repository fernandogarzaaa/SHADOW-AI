import { StyleSheet, Text, View } from "react-native";
import { SettingsScreen } from "@/components/settings/primitives";
import { SemanticSpacing, Spacing, typography, useTheme } from "@/theme";

const SECTIONS: Array<{ title: string; body: string }> = [
	{
		title: "Your keys stay on this phone",
		body: "API keys are saved in this phone's secure storage. A key is sent only to the provider you chose, when you chat with one of its models.",
	},
	{
		title: "Your chats stay on this phone",
		body: "Conversations are stored locally on this device. SHADOW uploads nothing about your chats anywhere.",
	},
	{
		title: "Your profile is explicit",
		body: "The profile SHADOW uses is only what you typed yourself in Personality and profile. Nothing is learned in the background.",
	},
	{
		title: "The node link is optional",
		body: "Linking your SHADOW node is off by default. When linked, briefings, approvals, and agent turns go to your node over your own network.",
	},
];

/**
 * Legal disclosure: a short, honest summary of how SHADOW handles data,
 * based only on what the app actually does. This is an informational
 * summary, not a published privacy policy. The full privacy policy ships
 * with the store listing.
 */
export default function LegalScreen() {
	const { colors } = useTheme();

	return (
		<SettingsScreen title="Legal" showClose={false}>
			{SECTIONS.map((section) => (
				<View
					key={section.title}
					style={[
						styles.card,
						{ backgroundColor: colors.card, borderColor: colors.border },
					]}
				>
					<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "700" }]}>
						{section.title}
					</Text>
					<Text
						style={[
							typography.body,
							{ color: colors.mutedForeground, marginTop: Spacing.xs },
						]}
					>
						{section.body}
					</Text>
				</View>
			))}
			<Text
				style={[
					typography.meta,
					{ color: colors.mutedForeground, marginTop: Spacing.lg },
				]}
			>
				This is an informational summary of how the app behaves today. The
				full privacy policy is part of the store listing.
			</Text>
		</SettingsScreen>
	);
}

const styles = StyleSheet.create({
	card: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: SemanticSpacing.radiusCard,
		padding: Spacing.md,
		marginBottom: Spacing.md,
	},
});
