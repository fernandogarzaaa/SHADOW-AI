import type { ReactNode } from "react";
import {
	StyleSheet,
	Text,
	View,
	type StyleProp,
	type TextStyle,
	type ViewStyle,
} from "react-native";
import { useTheme } from "@/theme";
import { withOpacity } from "@/utils/colors";

export type BadgeVariant =
	| "default"
	| "secondary"
	| "outline"
	| "success"
	| "warning"
	| "destructive";

interface BadgeProps {
	children: ReactNode;
	variant?: BadgeVariant;
	style?: StyleProp<ViewStyle>;
	labelStyle?: StyleProp<TextStyle>;
	accessibilityLabel?: string;
}

/**
 * Small status pill, shadcn Badge translated to React Native.
 * Tinted fill with a matching hairline border; the label is never
 * conveyed by color alone when it carries meaning (pair with text).
 */
export function Badge({
	children,
	variant = "default",
	style,
	labelStyle,
	accessibilityLabel,
}: BadgeProps) {
	const { colors } = useTheme();

	const base =
		variant === "default"
			? colors.primary
			: variant === "secondary"
				? colors.mutedForeground
				: variant === "success"
					? colors.success
					: variant === "warning"
						? colors.warning
						: variant === "destructive"
							? colors.destructive
							: colors.mutedForeground;

	const solid = variant === "default";

	return (
		<View
			style={[
				styles.pill,
				solid
					? { backgroundColor: base, borderColor: base }
					: {
							borderColor: withOpacity(base, 0.4),
							backgroundColor: withOpacity(base, 0.12),
						},
				style,
			]}
			accessibilityLabel={accessibilityLabel}
		>
			<Text
				style={[
					styles.label,
					{ color: solid ? colors.primaryForeground : base },
					labelStyle,
				]}
			>
				{children}
			</Text>
		</View>
	);
}

const styles = StyleSheet.create({
	pill: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: 999,
		paddingHorizontal: 8,
		paddingVertical: 3,
		alignSelf: "flex-start",
	},
	label: {
		fontSize: 11,
		fontWeight: "700",
		textTransform: "uppercase",
		letterSpacing: 0.4,
	},
});
