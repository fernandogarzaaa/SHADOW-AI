import { Pressable, StyleSheet, Text, View } from "react-native";
import { SettingsScreen } from "@/components/settings";
import { CheckIcon } from "@/components/icons";
import { SemanticSpacing, Spacing, typography, useTheme } from "@/theme";
import { type ThemeMode, useThemeMode } from "@/theme/ThemeProvider";

/** Static swatches for the preview cards, mirroring the vendor themes. */
const PREVIEWS: Record<
	Exclude<ThemeMode, "system">,
	{ background: string; card: string; primary: string; foreground: string }
> = {
	light: {
		background: "#F6F1EA",
		card: "#FFFFFF",
		primary: "#0064E0",
		foreground: "#3d3833",
	},
	dark: {
		background: "#161412",
		card: "#1e1b17",
		primary: "#2f7fe8",
		foreground: "#e9e2d5",
	},
};

const THEME_OPTIONS: Array<{
	value: ThemeMode;
	label: string;
	description: string;
}> = [
	{ value: "system", label: "System", description: "Follow this device" },
	{ value: "light", label: "Light", description: "Warm cream, always" },
	{ value: "dark", label: "Dark", description: "Deep ink, always" },
];

function PreviewSwatch({ mode }: { mode: ThemeMode }) {
	const left = PREVIEWS.light;
	const right = PREVIEWS.dark;
	const a = mode === "dark" ? right : left;
	const b = mode === "system" ? right : a;
	return (
		<View style={styles.swatch} accessibilityElementsHidden>
			<View style={[styles.swatchHalf, { backgroundColor: a.background }]}>
				<View
					style={[
						styles.swatchCard,
						{ backgroundColor: a.card, borderColor: a.foreground + "22" },
					]}
				/>
				<View style={[styles.swatchDot, { backgroundColor: a.primary }]} />
			</View>
			{mode === "system" ? (
				<View style={[styles.swatchHalf, { backgroundColor: b.background }]}>
					<View
						style={[
							styles.swatchCard,
							{ backgroundColor: b.card, borderColor: b.foreground + "22" },
						]}
					/>
					<View style={[styles.swatchDot, { backgroundColor: b.primary }]} />
				</View>
			) : null}
		</View>
	);
}

function ThemeModeSelector() {
	const { colors } = useTheme();
	const { themeMode, setThemeMode } = useThemeMode();

	return (
		<View style={styles.options}>
			{THEME_OPTIONS.map((option) => {
				const isSelected = themeMode === option.value;
				return (
					<Pressable
						key={option.value}
						onPress={() => setThemeMode(option.value)}
						style={({ pressed }) => [
							styles.option,
							{
								backgroundColor: colors.card,
								borderColor: isSelected ? colors.primary : colors.border,
								borderWidth: isSelected ? 2 : StyleSheet.hairlineWidth,
								opacity: pressed ? 0.7 : 1,
							},
						]}
						accessibilityRole="radio"
						accessibilityState={{ checked: isSelected }}
						accessibilityLabel={`${option.label} theme. ${option.description}.`}
					>
						<PreviewSwatch mode={option.value} />
						<View style={styles.optionText}>
							<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "600" }]}>
								{option.label}
							</Text>
							<Text style={[typography.meta, { color: colors.mutedForeground }]}>
								{option.description}
							</Text>
						</View>
						{isSelected ? (
							<CheckIcon size={20} color={colors.primary} />
						) : (
							<View style={styles.checkSpacer} />
						)}
					</Pressable>
				);
			})}
		</View>
	);
}

/**
 * Appearance: a real, persisted Light / Dark / System selector with
 * live theme previews.
 */
export default function AppearanceScreen() {
	const { colors } = useTheme();

	return (
		<SettingsScreen title="Appearance">
			<Text
				style={[
					typography.body,
					{ color: colors.mutedForeground, marginBottom: Spacing.md },
				]}
			>
				Your choice is saved on this phone and applies everywhere,
				including the floating tab bar.
			</Text>
			<ThemeModeSelector />
		</SettingsScreen>
	);
}

const styles = StyleSheet.create({
	options: {
		gap: Spacing.md,
	},
	option: {
		flexDirection: "row",
		alignItems: "center",
		gap: Spacing.md,
		borderRadius: SemanticSpacing.radiusCard,
		padding: Spacing.md,
		minHeight: 88,
	},
	swatch: {
		width: 64,
		height: 64,
		borderRadius: 16,
		overflow: "hidden",
		flexDirection: "row",
	},
	swatchHalf: {
		flex: 1,
		alignItems: "center",
		justifyContent: "center",
		gap: 4,
	},
	swatchCard: {
		width: 30,
		height: 18,
		borderRadius: 5,
		borderWidth: 1,
	},
	swatchDot: {
		width: 10,
		height: 10,
		borderRadius: 5,
	},
	optionText: {
		flex: 1,
		gap: 2,
	},
	checkSpacer: {
		width: 20,
	},
});
