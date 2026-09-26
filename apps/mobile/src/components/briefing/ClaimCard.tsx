import * as Haptics from "expo-haptics";
import { useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { confirmClaim, refuteClaim, type Claim } from "@/api/shadow";
import { CheckIcon, XIcon } from "@/components/icons";
import { Button, GlassView } from "@/components/ui";
import { Spacing, typography, useTheme } from "@/theme";

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
 * One open claim as a glass decision card. Confirm is the solid
 * primary action; Refute is the quieter outline action. Both hit the
 * real node endpoints; the card removes itself optimistically and
 * rolls back with an inline error if the request fails. Icon plus text
 * label on both actions: the decision is never conveyed by color alone.
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
		<GlassView
			borderRadius={20}
			accessibilityLabel={`Open claim: ${statement}`}
			style={styles.card}
		>
			<View style={styles.inner}>
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
					<Button
						variant="outline"
						size="md"
						isLoading={busy === "refuted"}
						isDisabled={busy !== null}
						onPress={() => void decide("refuted")}
						accessibilityLabel={`Refute claim: ${statement}`}
						style={styles.action}
					>
						<View style={styles.actionContent}>
							<XIcon size={18} color={colors.destructive} />
							<Button.Label>Refute</Button.Label>
						</View>
					</Button>
					<Button
						variant="primary"
						size="md"
						isLoading={busy === "confirmed"}
						isDisabled={busy !== null}
						onPress={() => void decide("confirmed")}
						accessibilityLabel={`Confirm claim: ${statement}`}
						style={styles.action}
					>
						<View style={styles.actionContent}>
							<CheckIcon size={18} color={colors.primaryForeground} />
							<Button.Label>Confirm</Button.Label>
						</View>
					</Button>
				</View>
			</View>
		</GlassView>
	);
}

const styles = StyleSheet.create({
	card: {
		// GlassView carries the surface.
	},
	inner: {
		padding: Spacing.md,
	},
	actions: {
		flexDirection: "row",
		gap: Spacing.sm,
		marginTop: Spacing.md,
	},
	action: {
		flex: 1,
	},
	actionContent: {
		flexDirection: "row",
		alignItems: "center",
		justifyContent: "center",
		gap: 8,
	},
});
