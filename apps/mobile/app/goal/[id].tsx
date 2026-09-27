import * as Haptics from "expo-haptics";
import { router, useFocusEffect, useLocalSearchParams } from "expo-router";
import { useCallback, useState } from "react";
import {
	ActivityIndicator,
	Alert,
	Pressable,
	ScrollView,
	StyleSheet,
	Text,
	TextInput,
	View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import {
	deleteGoal,
	getGoal,
	logGoalProgress,
	ShadowApiError,
	updateGoal,
	type GoalDetail,
} from "@/api/shadow";
import { useConnectionStore } from "@/stores/useConnectionStore";
import { SemanticSpacing, Spacing, typography, useTheme } from "@/theme";

function formatDateTime(ts: number): string {
	const d = new Date(ts * 1000);
	const mm = String(d.getMonth() + 1).padStart(2, "0");
	const dd = String(d.getDate()).padStart(2, "0");
	const yy = String(d.getFullYear()).slice(2);
	return `${mm}.${dd}.${yy}`;
}

const STATUS_LABEL: Record<string, string> = {
	active: "ACTIVE",
	completed: "COMPLETED",
	abandoned: "ABANDONED",
};

/**
 * Goal detail: progress timeline, log-progress composer, and lifecycle
 * actions (complete / reopen / abandon / delete).
 */
export default function GoalDetailScreen() {
	const { colors } = useTheme();
	const insets = useSafeAreaInsets();
	const { id } = useLocalSearchParams<{ id: string }>();
	const isPaired = useConnectionStore((s) => s.isPaired);

	const [goal, setGoal] = useState<GoalDetail | null>(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);

	const [note, setNote] = useState("");
	const [percent, setPercent] = useState("");
	const [saving, setSaving] = useState(false);

	const load = useCallback(async () => {
		if (!isPaired || !id) {
			setLoading(false);
			return;
		}
		setError(null);
		try {
			setGoal(await getGoal(id));
		} catch (e) {
			setError(
				e instanceof ShadowApiError ? e.message : "Could not load the goal.",
			);
		} finally {
			setLoading(false);
		}
	}, [isPaired, id]);

	useFocusEffect(
		useCallback(() => {
			setLoading(true);
			void load();
		}, [load]),
	);

	async function handleLogProgress() {
		const n = note.trim();
		if (!n || !id) return;
		const p = percent.trim() === "" ? null : Number(percent.trim());
		if (p !== null && (!Number.isInteger(p) || p < 0 || p > 100)) {
			Alert.alert("Percent must be a whole number from 0 to 100.");
			return;
		}
		setSaving(true);
		try {
			await logGoalProgress(id, n, p);
			setNote("");
			setPercent("");
			void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
			void load();
		} catch (e) {
			Alert.alert(
				"Could not save",
				e instanceof ShadowApiError ? e.message : "Try again.",
			);
		} finally {
			setSaving(false);
		}
	}

	async function handleStatus(status: "completed" | "abandoned" | "active") {
		if (!id) return;
		try {
			await updateGoal(id, { status });
			void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
			void load();
		} catch (e) {
			Alert.alert(
				"Could not update",
				e instanceof ShadowApiError ? e.message : "Try again.",
			);
		}
	}

	function handleDelete() {
		if (!id || !goal) return;
		Alert.alert("Delete this goal?", `"${goal.title}" and its progress history will be removed.`, [
			{ text: "Cancel", style: "cancel" },
			{
				text: "Delete",
				style: "destructive",
				onPress: () => {
					deleteGoal(id)
						.then(() => router.back())
						.catch((e: unknown) =>
							Alert.alert(
								"Could not delete",
								e instanceof ShadowApiError ? e.message : "Try again.",
							),
						);
				},
			},
		]);
	}

	return (
		<View style={[styles.container, { paddingTop: insets.top }]}>
			<View style={styles.header}>
				<Pressable
					onPress={() => router.back()}
					accessibilityRole="button"
					accessibilityLabel="Back to goals"
					hitSlop={12}
				>
					<Text style={[typography.uiLabel, { color: colors.primary, fontWeight: "700" }]}>
						{"< Goals"}
					</Text>
				</Pressable>
			</View>
			{loading ? (
				<ActivityIndicator
					style={styles.center}
					color={colors.primary}
					accessibilityLabel="Loading goal"
				/>
			) : error || !goal ? (
				<View style={styles.center}>
					<Text style={[typography.body, { color: colors.destructive, textAlign: "center" }]}>
						{error ?? "Goal not found."}
					</Text>
				</View>
			) : (
				<ScrollView
					contentContainerStyle={[
						styles.list,
						{ paddingBottom: Math.max(insets.bottom, Spacing.xl) },
					]}
				>
					<View style={styles.titleRow}>
						<Text style={[typography.h1, { color: colors.foreground, flex: 1 }]}>
							{goal.title}
						</Text>
					</View>
					<Text style={[typography.meta, { color: colors.mutedForeground, marginTop: Spacing.xs }]}>
						{STATUS_LABEL[goal.status] ?? goal.status}
						{goal.target_date ? ` · due ${goal.target_date}` : ""}
					</Text>
					{goal.description ? (
						<Text style={[typography.body, { color: colors.foreground, marginTop: Spacing.sm }]}>
							{goal.description}
						</Text>
					) : null}

					<Text style={[styles.sectionLabel, typography.uiLabel, { color: colors.foreground }]}>
						Log progress
					</Text>
					<TextInput
						style={[styles.input, styles.multiline, typography.body, { color: colors.foreground, backgroundColor: colors.card, borderColor: colors.border }]}
						value={note}
						onChangeText={setNote}
						placeholder="What moved forward?"
						placeholderTextColor={colors.mutedForeground}
						multiline
						maxLength={2000}
					/>
					<TextInput
						style={[styles.input, styles.percentInput, typography.body, { color: colors.foreground, backgroundColor: colors.card, borderColor: colors.border }]}
						value={percent}
						onChangeText={setPercent}
						placeholder="Percent complete (0-100, optional)"
						placeholderTextColor={colors.mutedForeground}
						keyboardType="number-pad"
						maxLength={3}
					/>
					<Pressable
						onPress={() => void handleLogProgress()}
						disabled={saving || !note.trim()}
						style={({ pressed }) => [
							styles.button,
							{ backgroundColor: colors.primary, opacity: pressed || saving || !note.trim() ? 0.7 : 1 },
						]}
						accessibilityRole="button"
						accessibilityLabel="Log progress"
					>
						<Text style={[typography.uiLabel, { color: colors.primaryForeground, fontWeight: "700" }]}>
							{saving ? "Saving" : "Log progress"}
						</Text>
					</Pressable>

					<Text style={[styles.sectionLabel, typography.uiLabel, { color: colors.foreground }]}>
						Progress ({goal.entries.length})
					</Text>
					{goal.entries.length === 0 ? (
						<Text style={[typography.body, { color: colors.mutedForeground }]}>
							No updates yet. Log the first one above.
						</Text>
					) : (
						goal.entries.map((e) => (
							<View
								key={e.id}
								style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}
							>
								<View style={styles.entryHeader}>
									<Text style={[typography.meta, { color: colors.mutedForeground }]}>
										{formatDateTime(e.created_at)}
									</Text>
									{e.percent !== null ? (
										<Text style={[typography.uiLabel, { color: colors.primary, fontWeight: "700" }]}>
											{e.percent}%
										</Text>
									) : null}
								</View>
								<Text style={[typography.body, { color: colors.foreground, marginTop: Spacing.xs }]}>
									{e.note}
								</Text>
							</View>
						))
					)}

					<Text style={[styles.sectionLabel, typography.uiLabel, { color: colors.foreground }]}>
						Goal lifecycle
					</Text>
					<View style={styles.actionRow}>
						{goal.status === "active" ? (
							<>
								<Pressable
									onPress={() => void handleStatus("completed")}
									style={({ pressed }) => [styles.halfButton, { backgroundColor: colors.primary, opacity: pressed ? 0.8 : 1 }]}
									accessibilityRole="button"
									accessibilityLabel="Mark goal complete"
								>
									<Text style={[typography.uiLabel, { color: colors.primaryForeground, fontWeight: "700" }]}>
										Complete
									</Text>
								</Pressable>
								<Pressable
									onPress={() => void handleStatus("abandoned")}
									style={({ pressed }) => [styles.halfButton, { backgroundColor: colors.card, borderColor: colors.border, borderWidth: StyleSheet.hairlineWidth, opacity: pressed ? 0.7 : 1 }]}
									accessibilityRole="button"
									accessibilityLabel="Abandon goal"
								>
									<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "700" }]}>
										Abandon
									</Text>
								</Pressable>
							</>
						) : (
							<Pressable
								onPress={() => void handleStatus("active")}
								style={({ pressed }) => [styles.halfButton, { backgroundColor: colors.card, borderColor: colors.border, borderWidth: StyleSheet.hairlineWidth, opacity: pressed ? 0.7 : 1 }]}
								accessibilityRole="button"
								accessibilityLabel="Reopen goal"
							>
								<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "700" }]}>
									Reopen
								</Text>
							</Pressable>
						)}
					</View>
					<Pressable
						onPress={handleDelete}
						style={styles.deleteLink}
						accessibilityRole="button"
						accessibilityLabel="Delete goal"
					>
						<Text style={[typography.uiLabel, { color: colors.destructive }]}>
							Delete goal
						</Text>
					</Pressable>
				</ScrollView>
			)}
		</View>
	);
}

const styles = StyleSheet.create({
	container: {
		flex: 1,
	},
	header: {
		paddingHorizontal: Spacing.xl,
		paddingVertical: Spacing.sm,
	},
	center: {
		flex: 1,
		justifyContent: "center",
		alignItems: "center",
		paddingHorizontal: Spacing.xl,
	},
	list: {
		gap: Spacing.md,
		paddingHorizontal: Spacing.xl,
	},
	titleRow: {
		flexDirection: "row",
		alignItems: "flex-start",
	},
	sectionLabel: {
		marginTop: Spacing.lg,
		fontWeight: "700",
	},
	input: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: SemanticSpacing.radiusInput,
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.md,
		minHeight: SemanticSpacing.inputHeight,
		marginTop: Spacing.sm,
	},
	multiline: {
		minHeight: 96,
		textAlignVertical: "top",
	},
	percentInput: {
		marginTop: Spacing.sm,
	},
	button: {
		marginTop: Spacing.md,
		borderRadius: SemanticSpacing.radiusModal,
		minHeight: SemanticSpacing.buttonHeightLg,
		justifyContent: "center",
		alignItems: "center",
		paddingHorizontal: Spacing.xl,
	},
	card: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: SemanticSpacing.radiusModal,
		padding: Spacing.md,
	},
	entryHeader: {
		flexDirection: "row",
		justifyContent: "space-between",
		alignItems: "center",
	},
	actionRow: {
		flexDirection: "row",
		gap: Spacing.sm,
		marginTop: Spacing.sm,
	},
	halfButton: {
		flex: 1,
		borderRadius: SemanticSpacing.radiusModal,
		minHeight: SemanticSpacing.buttonHeightLg,
		justifyContent: "center",
		alignItems: "center",
	},
	deleteLink: {
		marginTop: Spacing.xl,
		alignItems: "center",
		paddingVertical: Spacing.md,
	},
});
