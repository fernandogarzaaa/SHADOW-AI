import { useEffect, useRef, useState } from "react";
import { Animated, Pressable, StyleSheet, Text, View } from "react-native";
import { ShadowAvatar } from "@/components/Avatar";
import {
	CheckIcon,
	CloseCircleIcon,
	InfoIcon,
} from "@/components/icons";
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
	/**
	 * Optional one-line detail (provider, model, elapsed) revealed when the
	 * user taps the avatar. When omitted the avatar is not tappable.
	 */
	detail?: string | null;
}

/**
 * The selected Shadow avatar as a live status instrument: it breathes
 * while the agent is active, pairs every state with an icon and a text
 * label (never color alone), and taps through to a detail line.
 * Used on the briefing header and the chat header.
 */
export function AvatarStatusPill({
	avatarId,
	agentName,
	state,
	size = 96,
	detail,
}: AvatarStatusPillProps) {
	const { colors } = useTheme();
	const reduceMotion = useReduceMotion();
	const [showDetail, setShowDetail] = useState(false);
	const breath = useRef(new Animated.Value(0)).current;

	const active =
		state === "thinking" || state === "working" || state === "waiting";

	useEffect(() => {
		setShowDetail(false);
	}, [state]);

	useEffect(() => {
		// Breathing ring while the agent is active. Transform and opacity
		// only, native driver; a static ring when reduced motion is on.
		if (!active || reduceMotion) {
			breath.setValue(0);
			return;
		}
		const loop = Animated.loop(
			Animated.sequence([
				Animated.timing(breath, {
					toValue: 1,
					duration: 1400,
					useNativeDriver: true,
				}),
				Animated.timing(breath, {
					toValue: 0,
					duration: 1400,
					useNativeDriver: true,
				}),
			]),
		);
		loop.start();
		return () => loop.stop();
	}, [active, breath, reduceMotion]);

	const ringScale = breath.interpolate({
		inputRange: [0, 1],
		outputRange: [1, 1.1],
	});
	const ringOpacity = breath.interpolate({
		inputRange: [0, 1],
		outputRange: [0.55, 0.05],
	});

	const indicator =
		state === "completed" ? (
			<CheckIcon size={14} color={colors.success} />
		) : state === "error" ? (
			<CloseCircleIcon size={14} color={colors.destructive} />
		) : state === "needs_approval" ? (
			<InfoIcon size={14} color={colors.warning} />
		) : (
			<View
				style={[
					styles.dot,
					{
						backgroundColor:
							state === "offline"
								? colors.mutedForeground
								: active
									? colors.primary
									: colors.mutedForeground,
					},
				]}
			/>
		);

	const tappable = detail != null && detail.length > 0;
	const statusText = agentStatusLabel(state, agentName);

	const avatar = (
		<View style={styles.avatarWrap}>
			{active && !reduceMotion ? (
				<Animated.View
					style={[
						styles.ring,
						{
							width: size + 18,
							height: size + 18,
							borderRadius: (size + 18) / 2,
							borderColor: colors.primary,
							transform: [{ scale: ringScale }],
							opacity: ringOpacity,
						},
					]}
					pointerEvents="none"
				/>
			) : null}
			<ShadowAvatar avatarId={avatarId} size={size} />
		</View>
	);

	return (
		<View
			style={styles.wrap}
			accessibilityRole="image"
			accessibilityLabel={`${agentName || "shadow"} avatar. ${statusText}.`}
		>
			{tappable ? (
				<Pressable
					onPress={() => setShowDetail((v) => !v)}
					accessibilityRole="button"
					accessibilityLabel={
						showDetail ? "Hide status details" : "Show status details"
					}
					accessibilityState={{ expanded: showDetail }}
					accessibilityHint={`${statusText}. Activate to ${showDetail ? "hide" : "show"} details.`}
					style={({ pressed }) => [{ opacity: pressed ? 0.85 : 1 }]}
				>
					{avatar}
				</Pressable>
			) : (
				avatar
			)}
			<View
				style={[
					styles.pill,
					{
						backgroundColor: colors.card,
						borderColor: colors.border,
						// Active states get a soft glow ring; idle and
						// reduced-motion states stay flat.
						shadowColor:
							active && !reduceMotion ? colors.primary : "transparent",
					},
				]}
			>
				{indicator}
				<Text
					style={[typography.meta, { color: colors.foreground, fontWeight: "600" }]}
					numberOfLines={1}
				>
					{statusText}
				</Text>
			</View>
			{showDetail && tappable ? (
				<Text
					style={[
						typography.meta,
						{
							color: colors.mutedForeground,
							marginTop: Spacing.xs,
							textAlign: "center",
						},
					]}
					numberOfLines={2}
				>
					{detail}
				</Text>
			) : null}
		</View>
	);
}

const styles = StyleSheet.create({
	wrap: {
		alignItems: "center",
		// Room for the pill overlapping the avatar's bottom edge.
		paddingBottom: 14,
	},
	avatarWrap: {
		alignItems: "center",
		justifyContent: "center",
	},
	ring: {
		position: "absolute",
		borderWidth: 2,
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
