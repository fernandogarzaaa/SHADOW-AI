import * as Haptics from "expo-haptics";
import { router } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { AgentMark } from "@/components/companion/AgentMark";
import { Spacing, typography, useTheme } from "../../src/theme";

/**
 * Welcome: shadow is a personal AI first. Chat uses your own provider
 * API key; the node link is an optional power feature in Settings.
 * Copy voice: first-person, lowercase-friendly, calm.
 */
export default function WelcomeScreen() {
	const { colors } = useTheme();
	const insets = useSafeAreaInsets();

	return (
		<View
			style={[
				styles.container,
				{
					backgroundColor: colors.background,
					paddingTop: insets.top,
					paddingBottom: Math.max(insets.bottom, Spacing.xl),
				},
			]}
		>
			<View style={styles.body}>
				<AgentMark size={88} />
				<Text style={[styles.wordmark, { color: colors.foreground }]}>
					shadow
				</Text>
				<Text
					style={[
						typography.body,
						{ color: colors.mutedForeground, marginTop: Spacing.md },
					]}
				>
					hi, i'm shadow. your personal ai, living on your phone.
					bring your own api key and i'll take it from there.
				</Text>

				<View style={styles.points}>
					<Point text="your key stays on this phone, in secure storage. it goes straight to the provider." />
					<Point text="chat is home. your threads stay on this device." />
					<Point text="link your shadow node later, in settings, if you want approvals on the go." />
				</View>
			</View>

			<View style={styles.footer}>
				<Pressable
					onPress={() => {
						Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
						router.push("/onboarding/provider");
					}}
					style={[styles.cta, { backgroundColor: colors.primary }]}
					accessibilityRole="button"
					accessibilityLabel="Choose a provider"
				>
					<Text
						style={[
							typography.uiLabel,
							{ color: colors.primaryForeground, fontWeight: "700" },
						]}
					>
						choose a provider
					</Text>
				</Pressable>
			</View>
		</View>
	);
}

function Point({ text }: { text: string }) {
	const { colors } = useTheme();
	return (
		<View style={styles.point}>
			<View style={[styles.dot, { backgroundColor: colors.primary }]} />
			<Text style={[typography.body, { color: colors.foreground, flex: 1 }]}>
				{text}
			</Text>
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
		justifyContent: "center",
	},
	wordmark: {
		fontSize: 40,
		fontWeight: "700",
		letterSpacing: -0.5,
		marginTop: Spacing.lg,
	},
	points: {
		marginTop: Spacing.xl,
		gap: Spacing.lg,
	},
	point: {
		flexDirection: "row",
		gap: Spacing.md,
		alignItems: "flex-start",
	},
	dot: {
		width: 8,
		height: 8,
		borderRadius: 4,
		marginTop: 7,
	},
	footer: {
		gap: Spacing.sm,
	},
	cta: {
		borderRadius: 16,
		paddingVertical: 16,
		alignItems: "center",
	},
});
