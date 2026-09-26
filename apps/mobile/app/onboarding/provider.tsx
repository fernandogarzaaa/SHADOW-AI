import * as Haptics from "expo-haptics";
import { router } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { ChevronLeftIcon } from "@/components/icons";
import { KEY_PROVIDERS, getDefaultModel, getProvider, type ProviderId } from "@/providers";
import { Spacing, typography, useTheme } from "../../src/theme";

/** Step 2 of onboarding: pick which provider the API key belongs to. */
export default function ProviderSelectScreen() {
	const { colors } = useTheme();
	const insets = useSafeAreaInsets();

	function choose(providerId: ProviderId) {
		Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
		router.push({ pathname: "/onboarding/key", params: { providerId } });
	}

	return (
		<View
			style={[
				styles.container,
				{
					backgroundColor: colors.background,
					paddingTop: insets.top + Spacing.md,
					paddingBottom: Math.max(insets.bottom, Spacing.xl),
				},
			]}
		>
			<Pressable
				onPress={() => router.back()}
				style={styles.backBtn}
				hitSlop={8}
				accessibilityRole="button"
				accessibilityLabel="Back"
			>
				<ChevronLeftIcon size={18} color={colors.foreground} />
				<Text style={[typography.uiLabel, { color: colors.foreground }]}>Back</Text>
			</Pressable>

			<Text style={[typography.h1, { color: colors.foreground, marginTop: Spacing.lg }]}>
				Choose a provider
			</Text>
			<Text style={[typography.body, { color: colors.mutedForeground, marginTop: 8 }]}>
				SHADOW talks to the provider directly with your key. You can add
				the other one later in Settings.
			</Text>

			<View style={styles.cards}>
				{KEY_PROVIDERS.map((id) => {
					const provider = getProvider(id);
					const defaultModel =
						provider.models.find((m) => m.id === getDefaultModel(id))?.label ??
						provider.defaultModel;
					return (
						<Pressable
							key={id}
							onPress={() => choose(id)}
							style={({ pressed }) => [
								styles.card,
								{
									borderColor: colors.border,
									backgroundColor: colors.card,
									opacity: pressed ? 0.7 : 1,
								},
							]}
							accessibilityRole="button"
							accessibilityLabel={`Use ${provider.label}`}
						>
							<Text style={[typography.h2, { color: colors.foreground }]}>
								{provider.label}
							</Text>
							<Text style={[typography.body, { color: colors.mutedForeground, marginTop: 4 }]}>
								Default model: {defaultModel}
							</Text>
							<Text style={[typography.meta, { color: colors.primary, marginTop: 8, fontWeight: "600" }]}>
								Add API key
							</Text>
						</Pressable>
					);
				})}
			</View>
		</View>
	);
}

const styles = StyleSheet.create({
	container: {
		flex: 1,
		paddingHorizontal: Spacing.xl,
	},
	backBtn: {
		flexDirection: "row",
		alignItems: "center",
		gap: 6,
		alignSelf: "flex-start",
		paddingVertical: 8,
		paddingRight: 12,
	},
	cards: {
		marginTop: Spacing.xl,
		gap: Spacing.md,
	},
	card: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: 16,
		padding: Spacing.lg,
	},
});
