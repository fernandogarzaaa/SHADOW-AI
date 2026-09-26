import * as Haptics from "expo-haptics";
import { Pressable, ScrollView, StyleSheet, Text } from "react-native";
import { Spacing, typography, useTheme } from "@/theme";

export function SmartReplies({
	replies,
	onPick,
}: {
	replies: string[];
	onPick: (reply: string) => void;
}) {
	const { colors } = useTheme();

	if (replies.length === 0) {
		return null;
	}

	return (
		<ScrollView
			horizontal
			showsHorizontalScrollIndicator={false}
			style={styles.scroll}
			contentContainerStyle={styles.content}
			keyboardShouldPersistTaps="handled"
		>
			{replies.map((reply) => (
				<Pressable
					key={reply}
					onPress={() => {
						Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
						onPick(reply);
					}}
					// Chips are visually compact; the hit area reaches 44pt.
					hitSlop={{ top: 8, bottom: 8, left: 4, right: 4 }}
					style={({ pressed }) => [
						styles.chip,
						{
							borderColor: colors.border,
							backgroundColor: colors.background,
							opacity: pressed ? 0.6 : 1,
						},
					]}
					accessibilityRole="button"
					accessibilityLabel={`Suggested reply: ${reply}`}
				>
					<Text
						style={[typography.meta, { color: colors.foreground }]}
						numberOfLines={1}
					>
						{reply}
					</Text>
				</Pressable>
			))}
		</ScrollView>
	);
}

const styles = StyleSheet.create({
	scroll: {
		maxHeight: 44,
	},
	content: {
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.xs,
		gap: Spacing.sm,
		alignItems: "center",
	},
	chip: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: 16,
		paddingHorizontal: Spacing.md,
		paddingVertical: 8,
		maxWidth: 240,
	},
});
