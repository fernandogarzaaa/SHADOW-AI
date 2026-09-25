import { Text, View } from "react-native";

export type ApprovalRisk = "low" | "medium" | "high";

interface RiskBadgeProps {
	risk: ApprovalRisk;
}

const containerClasses: Record<ApprovalRisk, string> = {
	low: "bg-emerald-500/15 border-emerald-500/40",
	medium: "bg-amber-500/15 border-amber-500/40",
	high: "bg-red-500/15 border-red-500/40",
};

const textClasses: Record<ApprovalRisk, string> = {
	low: "text-emerald-400",
	medium: "text-amber-400",
	high: "text-red-400",
};

/** Color-coded pill showing an approval's risk level. */
export function RiskBadge({ risk }: RiskBadgeProps) {
	return (
		<View
			className={`rounded-full border px-2 py-0.5 ${containerClasses[risk]}`}
		>
			<Text className={`text-[11px] font-semibold uppercase ${textClasses[risk]}`}>
				{risk}
			</Text>
		</View>
	);
}
