import { LinearGradient } from "expo-linear-gradient";
import { StyleSheet, View } from "react-native";
import { useTheme } from "@/theme";
import { withOpacity } from "@/utils/colors";

/**
 * Ambient depth behind glass surfaces: a warm gradient wash plus two
 * soft color glows. Glass needs something to refract; over a flat
 * solid color the blur has nothing to work with and the effect dies.
 *
 * Render as the first child of a screen's root (which should then use
 * a transparent background).
 */
export function DepthBackground() {
	const { colors, isDark } = useTheme();

	return (
		<View pointerEvents="none" style={StyleSheet.absoluteFill}>
			<LinearGradient
				colors={
					isDark
						? ["#1B1815", "#151313", "#12100E"]
						: [colors.background, "#F3EDE2", "#EFE7D8"]
				}
				style={StyleSheet.absoluteFill}
			/>
			{/* Cobalt glow, top right */}
			<View
				style={[
					styles.blob,
					{
						width: 340,
						height: 340,
						borderRadius: 170,
						top: -110,
						right: -90,
						backgroundColor: withOpacity(colors.primary, isDark ? 0.16 : 0.1),
					},
				]}
			/>
			{/* Warm amber glow, lower left */}
			<View
				style={[
					styles.blob,
					{
						width: 300,
						height: 300,
						borderRadius: 150,
						bottom: "18%",
						left: -110,
						backgroundColor: isDark
							? withOpacity("#8A6B3F", 0.22)
							: withOpacity("#D9BE8C", 0.35),
					},
				]}
			/>
		</View>
	);
}

const styles = StyleSheet.create({
	blob: {
		position: "absolute",
	},
});
