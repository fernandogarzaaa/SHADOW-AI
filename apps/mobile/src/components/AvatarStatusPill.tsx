import { StyleSheet, Text, View } from "react-native";
import { ShadowAvatar } from "@/components/Avatar";
import type { AvatarId } from "@/avatars";
import type { AgentState } from "@/hooks/useProviderChat";
import { useReduceMotion } from "@/hooks/useReduceMotion";
import { SemanticSpacing, Spacing, typography, useTheme } from "@/theme";

/**
 * Live agent status text, driven by the real 8 agent states from
 * useProviderChat. Kept in sync with AgentStateLine's headlines.
 */
export function agentStatusLabel(state: AgentState, agentName: string): string {
	const name = agentName || "shadow";
	switch (state) {
		case "thinking":
			return `${name} is thinking`;
		case "working":
			return `${name} is working`;
		case "waiting":
			return `${name} is getting ready`;
		case "needs_approval":
			return `${name} needs approval`;
		case "completed":
			return "done";
		case "error":
			return `${name} hit a problem`;
		case "offline":
			return "offline";
		case "idle":
		default:
			return `${name} is idle`;
	}
}

interface AvatarStatusPillProps {
	avatarId: AvatarId;
	agentName: string;
	state: AgentState;
	/** Avatar diameter. The pill overlaps its bottom edge. */
	size?: number;
}

/**
 * The selected Shadow avatar with a live status pill overlapping its
 * bottom edge. Used on the briefing header and the chat header.
 */
export function AvatarStatusPill({
	avatarId,
	agentName,
	state,
	size = 96,
}: AvatarStatusPillProps) {
	const { colors } = useTheme();
	const reduceMotion = useReduceMotion();
	const active =
		state === "thinking" || state === "working" || state === "waiting";

	return (
		<View
			style={styles.wrap}
			accessibilityRole="image"
			accessibilityLabel={`${agentName || "shadow"} avatar. ${agentStatusLabel(state, agentName)}.`}
		>
			<ShadowAvatar avatarId={avatarId} size={size} />
			<View
				style={[
					styles.pill,
					{
						backgroundColor: colors.card,
						borderColor: colors.border,
						// Reduced motion and idle states get no glow ring.
						shadowColor:
							active && !reduceMotion ? colors.primary : "transparent",
					},
				]}
			>
				<View
					style={[
						styles.dot,
						{
							backgroundColor:
								state === "offline" || state === "needs_approval"
									? colors.warning
									: state === "error"
										? colors.destructive
										: state === "completed"
											? colors.success
											: colors.primary,
						},
					]}
				/>
				<Text
					style={[typography.meta, { color: colors.foreground, fontWeight: "600" }]}
					numberOfLines={1}
				>
					{agentStatusLabel(state, agentName)}
				</Text>
			</View>
		</View>
	);
}

const styles = StyleSheet.create({
	wrap: {
		alignItems: "center",
		// Room for the pill overlapping the avatar's bottom edge.
		paddingBottom: 14,
	},
	pill: {
		flexDirection: "row",
		alignItems: "center",
		gap: Spacing.xs,
		marginTop: -22,
		paddingHorizontal: Spacing.md,
		paddingVertical: 8,
		borderRadius: 999,
		borderWidth: StyleSheet.hairlineWidth,
		minHeight: SemanticSpacing.buttonHeightMd,
		shadowOpacity: 0.25,
		shadowRadius: 8,
		shadowOffset: { width: 0, height: 2 },
		elevation: 4,
	},
	dot: {
		width: 7,
		height: 7,
		borderRadius: 4,
	},
});
