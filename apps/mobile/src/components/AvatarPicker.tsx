import * as Haptics from "expo-haptics";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { AVATARS, type AvatarId } from "@/avatars";
import { ShadowAvatar } from "@/components/Avatar";
import { Radius, SemanticSpacing, Spacing, typography, useTheme } from "@/theme";

interface AvatarPickerProps {
	value: AvatarId;
	onSelect: (id: AvatarId) => void;
	/** Diameter of each option thumbnail in points. */
	thumbSize?: number;
}

const OPTION_SIZE = 64; // >= 44pt touch target with room for the thumb + ring

/**
 * Grid of the five shadow avatars. The selected one gets a cobalt ring;
 * every option is a 44pt+ radio target with haptic feedback on change.
 */
export function AvatarPicker({
	value,
	onSelect,
	thumbSize = 52,
}: AvatarPickerProps) {
	const { colors } = useTheme();

	return (
		<View
			style={styles.grid}
			accessibilityRole="radiogroup"
			accessibilityLabel="Choose your agent's look"
		>
			{AVATARS.map((avatar) => {
				const selected = avatar.id === value;
				return (
					<Pressable
						key={avatar.id}
						onPress={() => {
							if (avatar.id !== value) {
								Haptics.impactAsync(
									Haptics.ImpactFeedbackStyle.Light,
								).catch(() => {});
							}
							onSelect(avatar.id);
						}}
						style={({ pressed }) => [
							styles.option,
							{ opacity: pressed ? 0.7 : 1 },
						]}
						accessibilityRole="radio"
						accessibilityState={{ selected }}
						accessibilityLabel={`${avatar.label} avatar${selected ? ", selected" : ""}`}
					>
						<View
							style={[
								styles.ring,
								{
									borderColor: selected ? colors.primary : colors.border,
									borderWidth: selected ? 2.5 : StyleSheet.hairlineWidth,
									padding: selected ? 2 : 3,
								},
							]}
						>
							<ShadowAvatar avatarId={avatar.id} size={thumbSize} />
						</View>
						<Text
							style={[
								typography.meta,
								styles.optionLabel,
								{
									color: selected
										? colors.foreground
										: colors.mutedForeground,
									fontWeight: selected ? "700" : "400",
								},
							]}
						>
							{avatar.label}
						</Text>
					</Pressable>
				);
			})}
		</View>
	);
}

const styles = StyleSheet.create({
	grid: {
		flexDirection: "row",
		flexWrap: "wrap",
		gap: Spacing.sm,
	},
	option: {
		width: OPTION_SIZE,
		minHeight: SemanticSpacing.buttonHeightMd,
		alignItems: "center",
		justifyContent: "center",
	},
	ring: {
		borderRadius: Radius.full,
		alignItems: "center",
		justifyContent: "center",
	},
	optionLabel: {
		marginTop: 2,
	},
});
