import * as Haptics from "expo-haptics";
import { useState } from "react";
import {
	ActivityIndicator,
	Pressable,
	StyleSheet,
	Text,
	View,
} from "react-native";
import { confirmClaim, refuteClaim, type Claim } from "@/api/shadow";
import { CheckIcon, XIcon } from "@/components/icons";
import { SemanticSpacing, Spacing, typography, useTheme } from "@/theme";

type Decision = "confirmed" | "refuted";

interface ClaimCardProps {
	claim: Claim;
	/** Called after the node accepts the decision so the parent can remove the card. */
	onResolved: (claimId: string) => void;
}

function shortStatement(claim: Claim): string {
	return claim.statement?.trim() || claim.claim_id;
}

/**
 * One open claim as a tappable decision card. Confirm and Refute hit the
 * real node endpoints; the card removes itself optimistically and rolls
 * back with an inline error if the request fails. Icon plus text label on
 * both actions: the decision is never conveyed by color alone.
 */
export function ClaimCard({ claim, onResolved }: ClaimCardProps) {
	const { colors } = useTheme();
	const [busy, setBusy] = useState<Decision | null>(null);
	const [error, setError] = useState<string | null>(null);
	const statement = shortStatement(claim);

	async function decide(decision: Decision) {
		if (busy) return;
		setBusy(decision);
		setError(null);
		Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
		try {
			if (decision === "confirmed") {
				await confirmClaim(claim.claim_id);
			} else {
				await refuteClaim(claim.claim_id);
			}
			Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
			onResolved(claim.claim_id);
		} catch (e) {
			Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
			setError(
				e instanceof Error ? e.message : "Could not save your decision.",
			);
			setBusy(null);
		}
	}

	return (
		<View
			style={[
				styles.card,
				{ backgroundColor: colors.card, borderColor: colors.border },
			]}
			accessibilityLabel={`Open claim: ${statement}`}
		>
			<Text
				style={[typography.body, { color: colors.foreground }]}
				numberOfLines={3}
			>
				{statement}
			</Text>
			<Text
				style={[
					typography.meta,
					{ color: colors.mutedForeground, marginTop: 4 },
				]}
			>
				awaiting confirmation
			</Text>

			{error ? (
				<Text
					style={[
						typography.meta,
						{ color: colors.destructive, marginTop: Spacing.sm },
					]}
					accessibilityRole="alert"
				>
					{error} Tap an action to try again.
				</Text>
			) : null}

			<View style={styles.actions}>
				<Pressable
					onPress={() => void decide("refuted")}
					disabled={busy !== null}
					style={({ pressed }) => [
						styles.action,
						{
							borderColor: colors.border,
							backgroundColor: colors.card,
							opacity: pressed || busy === "confirmed" ? 0.6 : 1,
						},
					]}
					accessibilityRole="button"
					accessibilityLabel={`Refute claim: ${statement}`}
					accessibilityState={{ disabled: busy !== null, busy: busy === "refuted" }}
				>
					{busy === "refuted" ? (
						<ActivityIndicator size="small" color={colors.mutedForeground} />
					) : (
						<>
							<XIcon size={18} color={colors.destructive} />
							<Text
								style={[
									typography.uiLabel,
									{ color: colors.foreground, fontWeight: "600" },
								]}
							>
								Refute
							</Text>
						</>
					)}
				</Pressable>
				<Pressable
					onPress={() => void decide("confirmed")}
					disabled={busy !== null}
					style={({ pressed }) => [
						styles.action,
						{
							borderColor: colors.border,
							backgroundColor: colors.card,
							opacity: pressed || busy === "refuted" ? 0.6 : 1,
						},
					]}
					accessibilityRole="button"
					accessibilityLabel={`Confirm claim: ${statement}`}
					accessibilityState={{ disabled: busy !== null, busy: busy === "confirmed" }}
				>
					{busy === "confirmed" ? (
						<ActivityIndicator size="small" color={colors.mutedForeground} />
					) : (
						<>
							<CheckIcon size={18} color={colors.success} />
							<Text
								style={[
									typography.uiLabel,
									{ color: colors.foreground, fontWeight: "600" },
								]}
							>
								Confirm
							</Text>
						</>
					)}
				</Pressable>
			</View>
		</View>
	);
}

const styles = StyleSheet.create({
	card: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: SemanticSpacing.radiusCard,
		padding: Spacing.md,
	},
	actions: {
		flexDirection: "row",
		gap: Spacing.sm,
		marginTop: Spacing.md,
	},
	action: {
		flex: 1,
		flexDirection: "row",
		alignItems: "center",
		justifyContent: "center",
		gap: Spacing.xs,
		minHeight: SemanticSpacing.buttonHeightMd,
		borderRadius: SemanticSpacing.radiusButton,
		borderWidth: StyleSheet.hairlineWidth,
		paddingHorizontal: Spacing.md,
	},
});
