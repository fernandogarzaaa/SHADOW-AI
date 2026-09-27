import * as Haptics from "expo-haptics";
import { router, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import {
	ActivityIndicator,
	Pressable,
	RefreshControl,
	ScrollView,
	StyleSheet,
	Text,
	TextInput,
	View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import {
	createGoal,
	getGoalsBriefing,
	listGoals,
	ShadowApiError,
	type GoalsBriefing,
	type GoalSummary,
} from "@/api/shadow";
import { ChevronRightIcon } from "@/components/icons";
import { useConnectionStore } from "@/stores/useConnectionStore";
import { SemanticSpacing, Spacing, typography, useTheme } from "@/theme";

function formatDate(ts: number | null): string {
	if (!ts) return "";
	const d = new Date(ts * 1000);
	const mm = String(d.getMonth() + 1).padStart(2, "0");
	const dd = String(d.getDate()).padStart(2, "0");
	const yy = String(d.getFullYear()).slice(2);
	return `${mm}.${dd}.${yy}`;
}

function GoalCard({ goal, stale }: { goal: GoalSummary; stale: boolean }) {
	const { colors } = useTheme();
	return (
		<Pressable
			onPress={() => router.push(`/goal/${goal.id}`)}
			style={({ pressed }) => [
				styles.card,
				{
					backgroundColor: colors.card,
					borderColor: colors.border,
					opacity: pressed ? 0.85 : 1,
				},
			]}
			accessibilityRole="button"
			accessibilityLabel={`Open goal ${goal.title}`}
		>
			<View style={styles.cardTop}>
				<Text
					style={[typography.body, { color: colors.foreground, fontWeight: "600", flex: 1 }]}
					numberOfLines={2}
				>
					{goal.title}
				</Text>
				<ChevronRightIcon size={18} color={colors.mutedForeground} />
			</View>
			{goal.latest_percent !== null ? (
				<View style={styles.progressTrack}>
					<View
						style={[
							styles.progressFill,
							{
								width: `${goal.latest_percent}%`,
								backgroundColor: colors.primary,
							},
						]}
					/>
				</View>
			) : null}
			<View style={styles.metaRow}>
				{stale ? (
					<Text style={[typography.meta, { color: colors.warning, fontWeight: "700" }]}>
						STALE ·{" "}
					</Text>
				) : null}
				<Text style={[typography.meta, { color: colors.mutedForeground }]}>
					{goal.latest_percent !== null ? `${goal.latest_percent}% · ` : ""}
					{goal.entry_count} {goal.entry_count === 1 ? "update" : "updates"}
					{goal.target_date ? ` · due ${goal.target_date.slice(5)}` : ""}
					{goal.last_progress_at
						? ` · ${formatDate(goal.last_progress_at)}`
						: ""}
				</Text>
			</View>
		</Pressable>
	);
}

/**
 * Goals tab: the briefing (stale / due soon / recent progress) plus the
 * goal list and a composer. Goals live on the node, encrypted at rest.
 */
export default function GoalsScreen() {
	const { colors } = useTheme();
	const insets = useSafeAreaInsets();
	const isPaired = useConnectionStore((s) => s.isPaired);

	const [briefing, setBriefing] = useState<GoalsBriefing | null>(null);
	const [active, setActive] = useState<GoalSummary[]>([]);
	const [completed, setCompleted] = useState<GoalSummary[]>([]);
	const [loading, setLoading] = useState(true);
	const [refreshing, setRefreshing] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [showCompleted, setShowCompleted] = useState(false);

	const [title, setTitle] = useState("");
	const [targetDate, setTargetDate] = useState("");
	const [creating, setCreating] = useState(false);

	const refresh = useCallback(async () => {
		if (!isPaired) {
			setLoading(false);
			return;
		}
		setError(null);
		try {
			const [b, goals] = await Promise.all([getGoalsBriefing(), listGoals()]);
			setBriefing(b);
			setActive(goals.filter((g) => g.status === "active"));
			setCompleted(goals.filter((g) => g.status !== "active"));
		} catch (e) {
			setError(
				e instanceof ShadowApiError ? e.message : "Could not load goals.",
			);
		} finally {
			setLoading(false);
			setRefreshing(false);
		}
	}, [isPaired]);

	useFocusEffect(
		useCallback(() => {
			setLoading(true);
			void refresh();
		}, [refresh]),
	);

	async function handleCreate() {
		const t = title.trim();
		if (!t) return;
		setCreating(true);
		try {
			await createGoal({
				title: t,
				target_date: targetDate.trim() || null,
			});
			setTitle("");
			setTargetDate("");
			void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
			void refresh();
		} catch (e) {
			setError(
				e instanceof ShadowApiError
					? e.message
					: "Could not create the goal. Check the date format (YYYY-MM-DD).",
			);
		} finally {
			setCreating(false);
		}
	}

	const staleIds = new Set((briefing?.stale ?? []).map((g) => g.id));

	return (
		<View style={[styles.container, { paddingTop: insets.top }]}>
			<Text style={[typography.h1, { color: colors.foreground, paddingHorizontal: Spacing.xl, marginBottom: Spacing.md }]}>
				Goals
			</Text>
			{loading ? (
				<ActivityIndicator
					style={styles.center}
					color={colors.primary}
					accessibilityLabel="Loading goals"
				/>
			) : error && !briefing ? (
				<View style={styles.center}>
					<Text style={[typography.body, { color: colors.destructive, textAlign: "center" }]}>
						{error}
					</Text>
					<Pressable
						onPress={() => {
							setLoading(true);
							void refresh();
						}}
						style={[styles.button, { backgroundColor: colors.card, borderColor: colors.border, borderWidth: StyleSheet.hairlineWidth }]}
						accessibilityRole="button"
						accessibilityLabel="Retry"
					>
						<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "700" }]}>
							Retry
						</Text>
					</Pressable>
				</View>
			) : (
				<ScrollView
					contentContainerStyle={[styles.list, { paddingBottom: Math.max(insets.bottom, Spacing.xl) + 90 }]}
					refreshControl={
						<RefreshControl
							refreshing={refreshing}
							onRefresh={() => {
								setRefreshing(true);
								void refresh();
							}}
						/>
					}
				>
					{briefing && (briefing.stale.length > 0 || briefing.due_soon.length > 0 || briefing.overdue.length > 0) ? (
						<View
							style={[
								styles.card,
								{ backgroundColor: colors.card, borderColor: colors.border },
							]}
						>
							<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "700" }]}>
								BRIEFING
							</Text>
							{briefing.overdue.length > 0 ? (
								<Text style={[typography.body, { color: colors.destructive, marginTop: Spacing.xs }]}>
									{briefing.overdue.length} overdue: {briefing.overdue.slice(0, 2).map((g) => g.title).join(", ")}
									{briefing.overdue.length > 2 ? "..." : ""}
								</Text>
							) : null}
							{briefing.due_soon.length > 0 ? (
								<Text style={[typography.body, { color: colors.foreground, marginTop: Spacing.xs }]}>
									{briefing.due_soon.length} due soon: {briefing.due_soon.slice(0, 2).map((g) => g.title).join(", ")}
									{briefing.due_soon.length > 2 ? "..." : ""}
								</Text>
							) : null}
							{briefing.stale.length > 0 ? (
								<Text style={[typography.body, { color: colors.warning, marginTop: Spacing.xs }]}>
									{briefing.stale.length} stale (no progress in 7+ days)
								</Text>
							) : null}
							{briefing.recent_entries.length > 0 ? (
								<Text style={[typography.meta, { color: colors.mutedForeground, marginTop: Spacing.sm }]}>
									Latest: {briefing.recent_entries[0].goal_title} — {briefing.recent_entries[0].note.slice(0, 80)}
								</Text>
							) : null}
						</View>
					) : null}

					<Text style={[styles.sectionLabel, typography.uiLabel, { color: colors.foreground }]}>
						New goal
					</Text>
					<TextInput
						style={[styles.input, typography.body, { color: colors.foreground, backgroundColor: colors.card, borderColor: colors.border }]}
						value={title}
						onChangeText={setTitle}
						placeholder="What are you working toward?"
						placeholderTextColor={colors.mutedForeground}
						maxLength={120}
						returnKeyType="done"
					/>
					<TextInput
						style={[styles.input, styles.dateInput, typography.body, { color: colors.foreground, backgroundColor: colors.card, borderColor: colors.border }]}
						value={targetDate}
						onChangeText={setTargetDate}
						placeholder="Target date (YYYY-MM-DD, optional)"
						placeholderTextColor={colors.mutedForeground}
						maxLength={10}
					/>
					<Pressable
						onPress={() => void handleCreate()}
						disabled={creating || !title.trim()}
						style={({ pressed }) => [
							styles.button,
							{ backgroundColor: colors.primary, opacity: pressed || creating || !title.trim() ? 0.7 : 1 },
						]}
						accessibilityRole="button"
						accessibilityLabel="Create goal"
					>
						<Text style={[typography.uiLabel, { color: colors.primaryForeground, fontWeight: "700" }]}>
							{creating ? "Creating" : "Create goal"}
						</Text>
					</Pressable>

					<Text style={[styles.sectionLabel, typography.uiLabel, { color: colors.foreground }]}>
						Active ({active.length})
					</Text>
					{active.length === 0 ? (
						<Text style={[typography.body, { color: colors.mutedForeground }]}>
							No active goals. Set your first one above.
						</Text>
					) : (
						active.map((g) => <GoalCard key={g.id} goal={g} stale={staleIds.has(g.id)} />)
					)}

					{completed.length > 0 ? (
						<Pressable
							onPress={() => setShowCompleted((v) => !v)}
							style={styles.completedToggle}
							accessibilityRole="button"
							accessibilityLabel="Toggle completed goals"
						>
							<Text style={[typography.uiLabel, { color: colors.mutedForeground, fontWeight: "700" }]}>
								{showCompleted ? "Hide" : "Show"} completed ({completed.length})
							</Text>
						</Pressable>
					) : null}
					{showCompleted
						? completed.map((g) => <GoalCard key={g.id} goal={g} stale={false} />)
						: null}
				</ScrollView>
			)}
		</View>
	);
}

const styles = StyleSheet.create({
	container: {
		flex: 1,
	},
	center: {
		flex: 1,
		justifyContent: "center",
		alignItems: "center",
		gap: Spacing.md,
		paddingHorizontal: Spacing.xl,
	},
	list: {
		gap: Spacing.md,
		paddingHorizontal: Spacing.xl,
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
	dateInput: {
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
		padding: Spacing.lg,
	},
	cardTop: {
		flexDirection: "row",
		alignItems: "center",
		gap: Spacing.sm,
	},
	progressTrack: {
		height: 6,
		borderRadius: 3,
		backgroundColor: "rgba(128,128,128,0.25)",
		marginTop: Spacing.sm,
		overflow: "hidden",
	},
	progressFill: {
		height: 6,
		borderRadius: 3,
	},
	metaRow: {
		flexDirection: "row",
		flexWrap: "wrap",
		marginTop: Spacing.xs,
	},
	completedToggle: {
		marginTop: Spacing.lg,
		paddingVertical: Spacing.sm,
	},
});
