import * as Haptics from "expo-haptics";
import { useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import {
	ActivityIndicator,
	Alert,
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
	createIdea,
	deleteIdea,
	generateFeed,
	listFeed,
	listIdeas,
	runIdea,
	ShadowApiError,
	updateIdea,
	type FeedUnit,
	type Idea,
} from "@/api/shadow";
import { useConnectionStore } from "@/stores/useConnectionStore";
import { SemanticSpacing, Spacing, typography, useTheme } from "@/theme";

const KIND_LABEL: Record<string, string> = {
	morning_brief: "BRIEF",
	goals_briefing: "GOALS",
	memory_digest: "MEMORY",
};

function formatDate(ts: number): string {
	const d = new Date(ts * 1000);
	const mm = String(d.getMonth() + 1).padStart(2, "0");
	const dd = String(d.getDate()).padStart(2, "0");
	const yy = String(d.getFullYear()).slice(2);
	return `${mm}.${dd}.${yy}`;
}

const STATUS_LABEL: Record<string, string> = {
	new: "NEW",
	running: "RUNNING",
	done: "DONE",
	dismissed: "DISMISSED",
};

function FeedCard({ unit }: { unit: FeedUnit }) {
	const { colors } = useTheme();
	return (
		<View
			style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}
		>
			<View style={styles.cardHeader}>
				<Text style={[typography.meta, { color: colors.primary, fontWeight: "700" }]}>
					{KIND_LABEL[unit.kind] ?? unit.kind}
				</Text>
				<Text style={[typography.meta, { color: colors.mutedForeground }]}>
					{formatDate(unit.created_at)}
				</Text>
			</View>
			<Text style={[typography.body, { color: colors.foreground, fontWeight: "700", marginTop: Spacing.xs }]}>
				{unit.title}
			</Text>
			<Text style={[typography.body, { color: colors.foreground, marginTop: Spacing.xs }]}>
				{unit.body}
			</Text>
		</View>
	);
}

function IdeaCard({
	idea,
	onChanged,
}: {
	idea: Idea;
	onChanged: () => void;
}) {
	const { colors } = useTheme();

	async function setStatus(status: "done" | "dismissed" | "new") {
		try {
			await updateIdea(idea.id, { status });
			onChanged();
		} catch (e) {
			Alert.alert("Could not update", e instanceof ShadowApiError ? e.message : "Try again.");
		}
	}

	async function handleRun() {
		try {
			const res = await runIdea(idea.id);
			const needsApproval = res.plan.actions.filter((a) => a.requires_approval).length;
			void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
			Alert.alert(
				"Idea planned",
				`${res.plan.actions.length} actions planned${needsApproval ? `, ${needsApproval} need your approval` : ""}. Review them under Approvals.`,
			);
			onChanged();
		} catch (e) {
			Alert.alert("Could not run", e instanceof ShadowApiError ? e.message : "Try again.");
		}
	}

	function handleDelete() {
		Alert.alert("Delete this idea?", `"${idea.title}" will be removed.`, [
			{ text: "Cancel", style: "cancel" },
			{
				text: "Delete",
				style: "destructive",
				onPress: () => {
					deleteIdea(idea.id).then(onChanged).catch((e: unknown) =>
						Alert.alert("Could not delete", e instanceof ShadowApiError ? e.message : "Try again."),
					);
				},
			},
		]);
	}

	return (
		<View
			style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}
		>
			<View style={styles.cardHeader}>
				<Text style={[typography.meta, { color: colors.primary, fontWeight: "700" }]}>
					{STATUS_LABEL[idea.status] ?? idea.status}
				</Text>
				<Text style={[typography.meta, { color: colors.mutedForeground }]}>
					{formatDate(idea.updated_at)}
				</Text>
			</View>
			<Text style={[typography.body, { color: colors.foreground, fontWeight: "700", marginTop: Spacing.xs }]}>
				{idea.title}
			</Text>
			{idea.description ? (
				<Text style={[typography.body, { color: colors.foreground, marginTop: Spacing.xs }]}>
					{idea.description}
				</Text>
			) : null}
			{idea.plan.length > 0 ? (
				<Text style={[typography.meta, { color: colors.mutedForeground, marginTop: Spacing.sm }]}>
					Planned: {idea.plan.slice(0, 3).map((a) => a.description).join(" · ")}
					{idea.plan.length > 3 ? ` (+${idea.plan.length - 3} more)` : ""}
				</Text>
			) : null}
			<View style={styles.ideaActions}>
				{idea.status === "new" ? (
					<Pressable
						onPress={() => void handleRun()}
						style={({ pressed }) => [styles.chip, { backgroundColor: colors.primary, opacity: pressed ? 0.8 : 1 }]}
						accessibilityRole="button"
						accessibilityLabel={`Run idea ${idea.title}`}
					>
						<Text style={[typography.uiLabel, { color: colors.primaryForeground, fontWeight: "700" }]}>Run</Text>
					</Pressable>
				) : null}
				{idea.status === "new" || idea.status === "running" ? (
					<Pressable
						onPress={() => void setStatus("done")}
						style={({ pressed }) => [styles.chip, { backgroundColor: colors.muted, opacity: pressed ? 0.7 : 1 }]}
						accessibilityRole="button"
						accessibilityLabel={`Mark idea ${idea.title} done`}
					>
						<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "700" }]}>Done</Text>
					</Pressable>
				) : null}
				{idea.status !== "dismissed" && idea.status !== "done" ? (
					<Pressable
						onPress={() => void setStatus("dismissed")}
						style={({ pressed }) => [styles.chip, { backgroundColor: colors.muted, opacity: pressed ? 0.7 : 1 }]}
						accessibilityRole="button"
						accessibilityLabel={`Dismiss idea ${idea.title}`}
					>
						<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "700" }]}>Dismiss</Text>
					</Pressable>
				) : null}
				{(idea.status === "dismissed" || idea.status === "done") ? (
					<Pressable
						onPress={() => void setStatus("new")}
						style={({ pressed }) => [styles.chip, { backgroundColor: colors.muted, opacity: pressed ? 0.7 : 1 }]}
						accessibilityRole="button"
						accessibilityLabel={`Restore idea ${idea.title}`}
					>
						<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "700" }]}>Restore</Text>
					</Pressable>
				) : null}
				<Pressable
					onPress={handleDelete}
					style={styles.deleteChip}
					accessibilityRole="button"
					accessibilityLabel={`Delete idea ${idea.title}`}
				>
					<Text style={[typography.uiLabel, { color: colors.destructive }]}>Delete</Text>
				</Pressable>
			</View>
		</View>
	);
}

/**
 * Feed tab: the node's editorial digest (scheduled via the ambient
 * scheduler, on-demand via "Generate now") plus idea cards.
 */
export default function FeedScreen() {
	const { colors } = useTheme();
	const insets = useSafeAreaInsets();
	const isPaired = useConnectionStore((s) => s.isPaired);

	const [segment, setSegment] = useState<"feed" | "ideas">("feed");
	const [units, setUnits] = useState<FeedUnit[]>([]);
	const [total, setTotal] = useState(0);
	const [ideas, setIdeas] = useState<Idea[]>([]);
	const [loading, setLoading] = useState(true);
	const [refreshing, setRefreshing] = useState(false);
	const [generating, setGenerating] = useState(false);
	const [error, setError] = useState<string | null>(null);

	const [ideaTitle, setIdeaTitle] = useState("");
	const [ideaDesc, setIdeaDesc] = useState("");
	const [creatingIdea, setCreatingIdea] = useState(false);

	const refresh = useCallback(async () => {
		if (!isPaired) {
			setLoading(false);
			return;
		}
		setError(null);
		try {
			const [feed, ideaList] = await Promise.all([listFeed(20, 0), listIdeas()]);
			setUnits(feed.items);
			setTotal(feed.total);
			setIdeas(ideaList);
		} catch (e) {
			setError(e instanceof ShadowApiError ? e.message : "Could not load the feed.");
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

	async function handleGenerate() {
		setGenerating(true);
		try {
			await generateFeed([], true);
			void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
			void refresh();
		} catch (e) {
			setError(e instanceof ShadowApiError ? e.message : "Could not generate the feed.");
		} finally {
			setGenerating(false);
		}
	}

	async function handleCreateIdea() {
		const t = ideaTitle.trim();
		if (!t) return;
		setCreatingIdea(true);
		try {
			await createIdea(t, ideaDesc.trim());
			setIdeaTitle("");
			setIdeaDesc("");
			void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
			void refresh();
		} catch (e) {
			Alert.alert("Could not save", e instanceof ShadowApiError ? e.message : "Try again.");
		} finally {
			setCreatingIdea(false);
		}
	}

	const visibleIdeas = ideas.filter((i) => i.status === "new" || i.status === "running");
	const archivedIdeas = ideas.filter((i) => i.status === "done" || i.status === "dismissed");

	return (
		<View style={[styles.container, { paddingTop: insets.top }]}>
			<Text style={[typography.h1, { color: colors.foreground, paddingHorizontal: Spacing.xl }]}>
				Feed
			</Text>
			<View style={[styles.segmentRow, { paddingHorizontal: Spacing.xl, marginTop: Spacing.sm }]}>
				{(
					[
						["feed", "Digest"],
						["ideas", `Ideas (${visibleIdeas.length})`],
					] as const
				).map(([key, label]) => (
					<Pressable
						key={key}
						onPress={() => setSegment(key)}
						style={[
							styles.segment,
							{
								backgroundColor: segment === key ? colors.foreground : colors.card,
								borderColor: colors.border,
							},
						]}
						accessibilityRole="button"
						accessibilityState={{ selected: segment === key }}
						accessibilityLabel={`${label} segment`}
					>
						<Text
							style={[
								typography.uiLabel,
								{ color: segment === key ? colors.background : colors.foreground, fontWeight: "700" },
							]}
						>
							{label}
						</Text>
					</Pressable>
				))}
			</View>

			{loading ? (
				<ActivityIndicator style={styles.center} color={colors.primary} accessibilityLabel="Loading feed" />
			) : error && segment === "feed" && units.length === 0 ? (
				<View style={styles.center}>
					<Text style={[typography.body, { color: colors.destructive, textAlign: "center" }]}>{error}</Text>
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
					{segment === "feed" ? (
						<>
							<Pressable
								onPress={() => void handleGenerate()}
								disabled={generating}
								style={({ pressed }) => [
									styles.button,
									{ backgroundColor: colors.card, borderColor: colors.border, borderWidth: StyleSheet.hairlineWidth, opacity: pressed || generating ? 0.7 : 1 },
								]}
								accessibilityRole="button"
								accessibilityLabel="Generate feed now"
							>
								<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "700" }]}>
									{generating ? "Generating" : "Generate now"}
								</Text>
							</Pressable>
							{units.length === 0 ? (
								<Text style={[typography.body, { color: colors.mutedForeground }]}>
									No feed units yet. Generate one, or wait for the ambient scheduler.
								</Text>
							) : (
								units.map((u) => <FeedCard key={u.id} unit={u} />)
							)}
							{total > units.length ? (
								<Text style={[typography.meta, { color: colors.mutedForeground, textAlign: "center" }]}>
									Showing {units.length} of {total}
								</Text>
							) : null}
						</>
					) : (
						<>
							<Text style={[styles.sectionLabel, typography.uiLabel, { color: colors.foreground }]}>
								New idea
							</Text>
							<TextInput
								style={[styles.input, typography.body, { color: colors.foreground, backgroundColor: colors.card, borderColor: colors.border }]}
								value={ideaTitle}
								onChangeText={setIdeaTitle}
								placeholder="What is the idea?"
								placeholderTextColor={colors.mutedForeground}
								maxLength={140}
							/>
							<TextInput
								style={[styles.input, styles.multiline, typography.body, { color: colors.foreground, backgroundColor: colors.card, borderColor: colors.border }]}
								value={ideaDesc}
								onChangeText={setIdeaDesc}
								placeholder="Details (optional)"
								placeholderTextColor={colors.mutedForeground}
								multiline
								maxLength={2000}
							/>
							<Pressable
								onPress={() => void handleCreateIdea()}
								disabled={creatingIdea || !ideaTitle.trim()}
								style={({ pressed }) => [
									styles.button,
									{ backgroundColor: colors.primary, opacity: pressed || creatingIdea || !ideaTitle.trim() ? 0.7 : 1 },
								]}
								accessibilityRole="button"
								accessibilityLabel="Save idea"
							>
								<Text style={[typography.uiLabel, { color: colors.primaryForeground, fontWeight: "700" }]}>
									{creatingIdea ? "Saving" : "Save idea"}
								</Text>
							</Pressable>

							<Text style={[styles.sectionLabel, typography.uiLabel, { color: colors.foreground }]}>
								Open ideas ({visibleIdeas.length})
							</Text>
							{visibleIdeas.length === 0 ? (
								<Text style={[typography.body, { color: colors.mutedForeground }]}>
									No open ideas. Capture the next one above.
								</Text>
							) : (
								visibleIdeas.map((i) => <IdeaCard key={i.id} idea={i} onChanged={() => void refresh()} />)
							)}
							{archivedIdeas.length > 0 ? (
								<>
									<Text style={[styles.sectionLabel, typography.uiLabel, { color: colors.foreground }]}>
										Archived ({archivedIdeas.length})
									</Text>
									{archivedIdeas.map((i) => <IdeaCard key={i.id} idea={i} onChanged={() => void refresh()} />)}
								</>
							) : null}
						</>
					)}
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
		paddingHorizontal: Spacing.xl,
	},
	segmentRow: {
		flexDirection: "row",
		gap: Spacing.sm,
	},
	segment: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: 999,
		paddingHorizontal: Spacing.lg,
		paddingVertical: Spacing.sm,
	},
	list: {
		gap: Spacing.md,
		paddingHorizontal: Spacing.xl,
		paddingTop: Spacing.md,
	},
	sectionLabel: {
		marginTop: Spacing.lg,
		fontWeight: "700",
	},
	card: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: SemanticSpacing.radiusModal,
		padding: Spacing.lg,
	},
	cardHeader: {
		flexDirection: "row",
		justifyContent: "space-between",
		alignItems: "center",
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
		minHeight: 72,
		textAlignVertical: "top",
	},
	button: {
		marginTop: Spacing.md,
		borderRadius: SemanticSpacing.radiusModal,
		minHeight: SemanticSpacing.buttonHeightLg,
		justifyContent: "center",
		alignItems: "center",
		paddingHorizontal: Spacing.xl,
	},
	ideaActions: {
		flexDirection: "row",
		flexWrap: "wrap",
		gap: Spacing.sm,
		marginTop: Spacing.md,
	},
	chip: {
		borderRadius: 999,
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.xs,
	},
	deleteChip: {
		borderRadius: 999,
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.xs,
	},
});
