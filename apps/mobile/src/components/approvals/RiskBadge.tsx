import { StyleSheet, Text, View } from "react-native";
import { useTheme } from "@/theme";
import { withOpacity } from "@/utils/colors";

export type ApprovalRisk = "low" | "medium" | "high";

interface RiskBadgeProps {
	risk: ApprovalRisk;
}

/** Color-coded pill showing an approval's risk level. */
export function RiskBadge({ risk }: RiskBadgeProps) {
	const { colors } = useTheme();
	const base =
		risk === "low" ? colors.success : risk === "medium" ? colors.warning : colors.destructive;

	return (
		<View
			style={[
				styles.pill,
				{
					borderColor: withOpacity(base, 0.4),
					backgroundColor: withOpacity(base, 0.12),
				},
			]}
		>
			<Text style={[styles.label, { color: base }]}>{risk}</Text>
		</View>
	);
}

const styles = StyleSheet.create({
	pill: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: 999,
		paddingHorizontal: 8,
		paddingVertical: 2,
	},
	label: {
		fontSize: 11,
		fontWeight: "700",
		textTransform: "uppercase",
	},
});
