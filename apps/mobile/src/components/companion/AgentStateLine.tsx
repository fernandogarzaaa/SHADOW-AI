import { useEffect, useRef, useState } from "react";
import { Animated, Pressable, StyleSheet, Text, View } from "react-native";
import type { AgentState } from "@/hooks/useProviderChat";
import { useReduceMotion } from "@/hooks/useReduceMotion";
import { SemanticSpacing, Spacing, typography, useTheme } from "@/theme";
import { withOpacity } from "@/utils/colors";

interface AgentStateLineProps {
	state: AgentState;
	agentName: string;
	providerLabel: string | null;
	modelId: string | null;
	startedAt: number | null;
	errorMessage: string | null;
	onRetry: () => void;
	onDismiss: () => void;
	/** Optional: shown for the needs_approval state. */
	onViewApproval?: () => void;
}

/**
 * First-class agent state UI for chat: a calm one-liner with a subtle
 * pulse, always paired with a text label (state is never conveyed by
 * animation or color alone). Tapping expands a short summary; there are
 * no token counters and no chain-of-thought viewer.
 */
export function AgentStateLine({
	state,
	agentName,
	providerLabel,
	modelId,
	startedAt,
	errorMessage,
	onRetry,
	onDismiss,
	onViewApproval,
}: AgentStateLineProps) {
	const { colors } = useTheme();
	const reduceMotion = useReduceMotion();
	const [expanded, setExpanded] = useState(false);
	const [now, setNow] = useState(Date.now());
	const pulse = useRef(new Animated.Value(0.35)).current;

	const active = state === "thinking" || state === "working" || state === "waiting";

	useEffect(() => {
		setExpanded(false);
	}, [state]);

	useEffect(() => {
		// Reduced motion: the dot renders static. State is always paired
		// with a text label, never conveyed by animation alone.
		if (!active || reduceMotion) return;
		const loop = Animated.loop(
			Animated.sequence([
				Animated.timing(pulse, { toValue: 1, duration: 900, useNativeDriver: true }),
				Animated.timing(pulse, { toValue: 0.35, duration: 900, useNativeDriver: true }),
			]),
		);
		loop.start();
		return () => loop.stop();
	}, [active, pulse, reduceMotion]);

	useEffect(() => {
		if (!active) return;
		const interval = setInterval(() => setNow(Date.now()), 1000);
		return () => clearInterval(interval);
	}, [active]);

	if (state === "idle") return null;

	const name = agentName || "shadow";
	const elapsed =
		startedAt != null ? Math.max(0, Math.round((now - startedAt) / 1000)) : 0;
	const elapsedLabel =
		elapsed < 60 ? `${elapsed}s` : `${Math.floor(elapsed / 60)}m ${elapsed % 60}s`;

	const headline =
		state === "waiting"
			? `${name} is getting ready...`
			: state === "thinking"
				? `${name} is thinking...`
				: state === "working"
					? `${name} is writing...`
					: state === "completed"
						? "Done."
						: state === "needs_approval"
							? `${name} needs your approval.`
							: state === "offline"
								? "You're offline."
								: `${name} ran into a problem.`;

	const subline =
		state === "offline"
			? "Check your connection and try again."
			: state === "error"
				? (errorMessage ?? "Something went wrong.")
				: state === "needs_approval"
					? "Nothing continues until you review it."
					: null;

	const dotColor =
		state === "offline" || state === "needs_approval"
			? colors.warning
			: state === "completed"
				? colors.success
				: colors.destructive;

	return (
		<View
			style={[
				styles.container,
				{ backgroundColor: colors.background, borderTopColor: colors.border },
			]}
		>
			<Pressable
				onPress={() => setExpanded((e) => !e)}
				accessibilityRole="button"
				accessibilityLabel={`${headline}. ${expanded ? "Collapse" : "Expand"} details.`}
				style={styles.row}
			>
				{active ? (
					<Animated.View
						style={[
							styles.dot,
							{ backgroundColor: colors.primary, opacity: reduceMotion ? 1 : pulse },
						]}
					/>
				) : (
					<View
						style={[
							styles.dot,
							{
								backgroundColor: dotColor,
							},
						]}
					/>
				)}
				<Text style={[typography.body, { color: colors.foreground, flex: 1 }]}>
					{headline}
				</Text>
				<Text style={[typography.meta, { color: colors.mutedForeground }]}>
					{expanded ? "less" : "more"}
				</Text>
			</Pressable>

			{expanded ? (
				<View style={styles.details}>
					{providerLabel || modelId ? (
						<Text style={[typography.meta, { color: colors.mutedForeground }]}>
							{[providerLabel, modelId].filter(Boolean).join(" · ")}
						</Text>
					) : null}
					{active ? (
						<Text style={[typography.meta, { color: colors.mutedForeground }]}>
							{elapsedLabel} so far
						</Text>
					) : null}
					{subline ? (
						<Text style={[typography.meta, { color: colors.mutedForeground }]}>
							{subline}
						</Text>
					) : null}
				</View>
			) : null}

			{state === "needs_approval" ? (
				<View style={styles.actions}>
					<Pressable
						onPress={onViewApproval}
						accessibilityRole="button"
						accessibilityLabel="View approval"
						style={({ pressed }) => [
							styles.retry,
							{ backgroundColor: colors.primary, opacity: pressed ? 0.8 : 1 },
						]}
					>
						<Text style={[typography.uiLabel, { color: colors.primaryForeground, fontWeight: "700" }]}>
							View approval
						</Text>
					</Pressable>
					<Pressable
						onPress={onDismiss}
						accessibilityRole="button"
						accessibilityLabel="Dismiss"
						style={({ pressed }) => [
							styles.dismiss,
							{
								borderColor: colors.border,
								backgroundColor: withOpacity(colors.muted, 0.5),
								opacity: pressed ? 0.7 : 1,
							},
						]}
					>
						<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "600" }]}>
							Dismiss
						</Text>
					</Pressable>
				</View>
			) : null}

			{state === "error" || state === "offline" ? (
				<View style={styles.actions}>
					<Pressable
						onPress={onRetry}
						accessibilityRole="button"
						accessibilityLabel="Retry sending"
						style={({ pressed }) => [
							styles.retry,
							{ backgroundColor: colors.primary, opacity: pressed ? 0.8 : 1 },
						]}
					>
						<Text style={[typography.uiLabel, { color: colors.primaryForeground, fontWeight: "700" }]}>
							Retry
						</Text>
					</Pressable>
					<Pressable
						onPress={onDismiss}
						accessibilityRole="button"
						accessibilityLabel="Dismiss"
						style={({ pressed }) => [
							styles.dismiss,
							{
								borderColor: colors.border,
								backgroundColor: withOpacity(colors.muted, 0.5),
								opacity: pressed ? 0.7 : 1,
							},
						]}
					>
						<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "600" }]}>
							Dismiss
						</Text>
					</Pressable>
				</View>
			) : null}
		</View>
	);
}

const styles = StyleSheet.create({
	container: {
		borderTopWidth: StyleSheet.hairlineWidth,
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.sm,
	},
	row: {
		flexDirection: "row",
		alignItems: "center",
		gap: Spacing.sm,
		minHeight: SemanticSpacing.buttonHeightMd,
	},
	dot: {
		width: 8,
		height: 8,
		borderRadius: 4,
	},
	details: {
		marginTop: Spacing.sm,
		gap: 2,
		paddingLeft: 16,
	},
	actions: {
		marginTop: Spacing.sm,
		flexDirection: "row",
		gap: Spacing.sm,
	},
	retry: {
		flex: 1,
		borderRadius: 999,
		minHeight: SemanticSpacing.buttonHeightMd,
		justifyContent: "center",
		alignItems: "center",
	},
	dismiss: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: 999,
		minHeight: SemanticSpacing.buttonHeightMd,
		justifyContent: "center",
		paddingHorizontal: Spacing.lg,
		alignItems: "center",
	},
});
