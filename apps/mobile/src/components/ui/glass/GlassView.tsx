import { BlurView } from "expo-blur";
import { LinearGradient } from "expo-linear-gradient";
import type { ReactNode } from "react";
import {
	StyleSheet,
	View,
	type StyleProp,
	type ViewStyle,
} from "react-native";
import { useTheme } from "@/theme";
import { withOpacity } from "@/utils/colors";

interface GlassViewProps {
	children?: ReactNode;
	style?: StyleProp<ViewStyle>;
	/** Blur intensity, 0-100. Defaults to 70. */
	intensity?: number;
	/** Corner radius. Defaults to 20. */
	borderRadius?: number;
	/** Extra translucent tint over the blur. Defaults to a theme-aware wash. */
	tintColor?: string;
	/** Specular top-edge highlight, the Liquid Glass light edge. Defaults to true. */
	highlight?: boolean;
	/** Accessibility label for the surface (e.g. when it is a card). */
	accessibilityLabel?: string;
	/** Accessibility role for the surface. */
	accessibilityRole?: "button" | "none";
}

/**
 * Liquid-glass surface: backdrop blur plus a translucent theme-aware
 * tint and a specular top-edge highlight.
 *
 * This is the seam for true Apple Liquid Glass: when the app moves off
 * Expo Go onto development builds, the BlurView here can be swapped for
 * expo-glass-effect's GlassView without touching any screen code.
 * Until then this approximation is Expo Go safe on both platforms.
 */
export function GlassView({
	children,
	style,
	intensity = 70,
	borderRadius = 20,
	tintColor,
	highlight = true,
	accessibilityLabel,
	accessibilityRole,
}: GlassViewProps) {
	const { colors, isDark } = useTheme();
	const tint = tintColor ?? withOpacity(colors.card, isDark ? 0.55 : 0.6);
	const edgeColor = isDark
		? withOpacity("#FFFFFF", 0.16)
		: withOpacity("#FFFFFF", 0.7);

	return (
		<View
			accessibilityLabel={accessibilityLabel}
			accessibilityRole={accessibilityRole}
			style={[
				styles.root,
				{
					borderRadius,
					borderColor: edgeColor,
				},
				style,
			]}
		>
			<BlurView
				intensity={intensity}
				tint={isDark ? "dark" : "light"}
				style={[StyleSheet.absoluteFill, { borderRadius }]}
			/>
			<View
				pointerEvents="none"
				style={[StyleSheet.absoluteFill, { borderRadius, backgroundColor: tint }]}
			/>
			{highlight ? (
				<LinearGradient
					pointerEvents="none"
					colors={[
						isDark ? withOpacity("#FFFFFF", 0.22) : withOpacity("#FFFFFF", 0.85),
						"transparent",
					]}
					style={[
						styles.highlight,
						{ borderTopLeftRadius: borderRadius, borderTopRightRadius: borderRadius },
					]}
				/>
			) : null}
			{children}
		</View>
	);
}

const styles = StyleSheet.create({
	root: {
		overflow: "hidden",
		borderWidth: StyleSheet.hairlineWidth,
	},
	highlight: {
		position: "absolute",
		top: 0,
		left: 0,
		right: 0,
		height: 48,
	},
});
