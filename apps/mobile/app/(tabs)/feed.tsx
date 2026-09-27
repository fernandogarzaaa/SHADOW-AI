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
	checkReminders,
	configureAmbient,
	createIdea,
	createReminder,
	deleteIdea,
	deleteReminder,
	dueReminders,
	generateFeed,
	getAmbientStatus,
	listFeed,
	listIdeas,
	listReminders,
	runIdea,
	ShadowApiError,
	updateIdea,
	updateReminder,
	type FeedUnit,
	type Idea,
	type Reminder,
	type ReminderRecurrence,
} from "@/api/shadow";
import { useConnectionStore } from "@/stores/useConnectionStore";
import { SemanticSpacing, Spacing, typography, useTheme } from "@/theme";

const KIND_LABEL: Record<string, string> = {
	morning_brief: "BRIEF",
	goals_briefing: "GOALS",
	memory_digest: "MEMORY",
	reminder: "REMINDER",
};

function formatDate(ts: number): string {
	const d = new Date(ts * 1000);
	const mm = String(d.getMonth() + 1).padStart(2, "0");
	const dd = String(d.getDate()).padStart(2, "0");
	const yy = String(d.getFullYear()).slice(2);
	return `${mm}.${dd}.${yy}`;
}

function formatDateTime(ts: number): string {
	const d = new Date(ts * 1000);
	const hh = String(d.getHours()).padStart(2, "0");
	const mi = String(d.getMinutes()).padStart(2, "0");
	return `${formatDate(ts)} ${hh}:${mi}`;
}

function isOverdue(r: Reminder): boolean {
	return r.status === "pending" && r.due_at * 1000 < Date.now();
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

function ReminderCard({
	reminder,
	onChanged,
}: {
	reminder: Reminder;
	onChanged: () => void;
}) {
	const { colors } = useTheme();
	const overdue = isOverdue(reminder);

	async function dismiss() {
		try {
			await updateReminder(reminder.id, { status: "dismissed" });
			onChanged();
		} catch (e) {
			Alert.alert("Could not update", e instanceof ShadowApiError ? e.message : "Try again.");
		}
	}

	function handleDelete() {
		Alert.alert("Delete this reminder?", `"${reminder.title}" will be removed.`, [
			{ text: "Cancel", style: "cancel" },
			{
				text: "Delete",
				style: "destructive",
				onPress: () => {
					deleteReminder(reminder.id).then(onChanged).catch((e: unknown) =>
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
				<Text
					style={[
						typography.meta,
						{ color: overdue ? colors.destructive : colors.primary, fontWeight: "700" },
					]}
				>
					{overdue ? "OVERDUE" : reminder.recurrence !== "none" ? reminder.recurrence.toUpperCase() : reminder.status.toUpperCase()}
				</Text>
				<Text style={[typography.meta, { color: colors.mutedForeground }]}>
					{formatDateTime(reminder.due_at)}
				</Text>
			</View>
			<Text style={[typography.body, { color: colors.foreground, fontWeight: "700", marginTop: Spacing.xs }]}>
				{reminder.title}
			</Text>
			{reminder.note ? (
				<Text style={[typography.body, { color: colors.foreground, marginTop: Spacing.xs }]}>
					{reminder.note}
				</Text>
			) : null}
			{reminder.status === "pending" ? (
				<View style={styles.ideaActions}>
					<Pressable
						onPress={() => void dismiss()}
						style={({ pressed }) => [styles.chip, { backgroundColor: colors.muted, opacity: pressed ? 0.7 : 1 }]}
						accessibilityRole="button"
						accessibilityLabel={`Dismiss reminder ${reminder.title}`}
					>
						<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "700" }]}>Dismiss</Text>
					</Pressable>
					<Pressable
						onPress={handleDelete}
						style={styles.deleteChip}
						accessibilityRole="button"
						accessibilityLabel={`Delete reminder ${reminder.title}`}
					>
						<Text style={[typography.uiLabel, { color: colors.destructive }]}>Delete</Text>
					</Pressable>
				</View>
			) : null}
		</View>
	);
}

/**
 * Feed tab: the node's editorial digest (scheduled via the ambient
 * scheduler, on-demand via "Generate now"), idea cards, and reminders.
 */
export default function FeedScreen() {
	const { colors } = useTheme();
	const insets = useSafeAreaInsets();
	const isPaired = useConnectionStore((s) => s.isPaired);

	const [segment, setSegment] = useState<"feed" | "ideas" | "reminders">("feed");
	const [units, setUnits] = useState<FeedUnit[]>([]);
	const [total, setTotal] = useState(0);
	const [ideas, setIdeas] = useState<Idea[]>([]);
	const [reminders, setReminders] = useState<Reminder[]>([]);
	const [quietStart, setQuietStart] = useState<string | null>(null);
	const [quietEnd, setQuietEnd] = useState<string | null>(null);
	const [loading, setLoading] = useState(true);
	const [refreshing, setRefreshing] = useState(false);
	const [generating, setGenerating] = useState(false);
	const [checking, setChecking] = useState(false);
	const [error, setError] = useState<string | null>(null);

	const [ideaTitle, setIdeaTitle] = useState("");
	const [ideaDesc, setIdeaDesc] = useState("");
	const [creatingIdea, setCreatingIdea] = useState(false);

	const [remTitle, setRemTitle] = useState("");
	const [remNote, setRemNote] = useState("");
	const [remDate, setRemDate] = useState("");
	const [remTime, setRemTime] = useState("");
	const [remRecurrence, setRemRecurrence] = useState<ReminderRecurrence>("none");
	const [creatingReminder, setCreatingReminder] = useState(false);
	const [quietFormStart, setQuietFormStart] = useState("");
	const [quietFormEnd, setQuietFormEnd] = useState("");
	const [savingQuiet, setSavingQuiet] = useState(false);

	const refresh = useCallback(async () => {
		if (!isPaired) {
			setLoading(false);
			return;
		}
		setError(null);
		try {
			const [feed, ideaList, reminderList, ambient] = await Promise.all([
				listFeed(20, 0),
				listIdeas(),
				listReminders(),
				getAmbientStatus(),
			]);
			setUnits(feed.items);
			setTotal(feed.total);
			setIdeas(ideaList);
			setReminders(reminderList);
			setQuietStart((ambient.config?.quiet_start as string | undefined) ?? null);
			setQuietEnd((ambient.config?.quiet_end as string | undefined) ?? null);
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
	const pendingReminders = reminders.filter((r) => r.status === "pending");
	const pastReminders = reminders.filter((r) => r.status !== "pending");

	function dueTimestamp(): number | null {
		const now = Date.now();
		if (remDate.trim() && remTime.trim()) {
			const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(remDate.trim());
			const t = /^(\d{2}):(\d{2})$/.exec(remTime.trim());
			if (!m || !t) return null;
			const d = new Date(
				Number(m[1]),
				Number(m[2]) - 1,
				Number(m[3]),
				Number(t[1]),
				Number(t[2]),
				0,
			);
			if (Number.isNaN(d.getTime())) return null;
			return Math.floor(d.getTime() / 1000);
		}
		return null;
	}

	function applyQuickChip(hoursFromNow: number | null, tomorrow9 = false) {
		const d = new Date();
		if (tomorrow9) {
			d.setDate(d.getDate() + 1);
			d.setHours(9, 0, 0, 0);
		} else if (hoursFromNow !== null) {
			d.setTime(d.getTime() + hoursFromNow * 3600 * 1000);
		}
		const pad = (n: number) => String(n).padStart(2, "0");
		setRemDate(`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`);
		setRemTime(`${pad(d.getHours())}:${pad(d.getMinutes())}`);
	}

	async function handleCreateReminder() {
		const t = remTitle.trim();
		const dueAt = dueTimestamp();
		if (!t || dueAt === null) {
			Alert.alert("Missing details", "Give the reminder a title and a valid date (YYYY-MM-DD) and time (HH:MM).");
			return;
		}
		setCreatingReminder(true);
		try {
			await createReminder(t, dueAt, remNote.trim(), remRecurrence);
			setRemTitle("");
			setRemNote("");
			setRemDate("");
			setRemTime("");
			setRemRecurrence("none");
			void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
			void refresh();
		} catch (e) {
			Alert.alert("Could not save", e instanceof ShadowApiError ? e.message : "Try again.");
		} finally {
			setCreatingReminder(false);
		}
	}

	async function handleCheckNow() {
		setChecking(true);
		try {
			const res = await checkReminders();
			if (res.quiet) {
				Alert.alert("Quiet hours", `${res.held.length} reminder${res.held.length === 1 ? "" : "s"} held until quiet hours end.`);
			} else if (res.fired.length > 0) {
				void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
			}
			void refresh();
			// Also surface anything newly due even without firing.
			void dueReminders().catch(() => []);
		} catch (e) {
			Alert.alert("Could not check", e instanceof ShadowApiError ? e.message : "Try again.");
		} finally {
			setChecking(false);
		}
	}

	async function handleSaveQuietHours() {
		const s = quietFormStart.trim();
		const e = quietFormEnd.trim();
		if ((s && !/^\d{2}:\d{2}$/.test(s)) || (e && !/^\d{2}:\d{2}$/.test(e))) {
			Alert.alert("Invalid time", "Use HH:MM, 24-hour, e.g. 22:00.");
			return;
		}
		setSavingQuiet(true);
		try {
			const cfg = await configureAmbient({ quiet_start: s, quiet_end: e });
			setQuietStart((cfg?.quiet_start as string | undefined) ?? null);
			setQuietEnd((cfg?.quiet_end as string | undefined) ?? null);
			setQuietFormStart("");
			setQuietFormEnd("");
			void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
		} catch (err) {
			Alert.alert("Could not save", err instanceof ShadowApiError ? err.message : "Try again.");
		} finally {
			setSavingQuiet(false);
		}
	}

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
						["reminders", `Reminders (${pendingReminders.length})`],
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
					) : segment === "ideas" ? (
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
					) : (
						<>
							<Text style={[styles.sectionLabel, typography.uiLabel, { color: colors.foreground }]}>
								New reminder
							</Text>
							<TextInput
								style={[styles.input, typography.body, { color: colors.foreground, backgroundColor: colors.card, borderColor: colors.border }]}
								value={remTitle}
								onChangeText={setRemTitle}
								placeholder="Remind me to..."
								placeholderTextColor={colors.mutedForeground}
								maxLength={140}
							/>
							<TextInput
								style={[styles.input, typography.body, { color: colors.foreground, backgroundColor: colors.card, borderColor: colors.border }]}
								value={remNote}
								onChangeText={setRemNote}
								placeholder="Note (optional)"
								placeholderTextColor={colors.mutedForeground}
								maxLength={500}
							/>
							<View style={styles.chipRow}>
								{(
									[
										["In 1h", () => applyQuickChip(1)],
										["In 3h", () => applyQuickChip(3)],
										["Tomorrow 9am", () => applyQuickChip(null, true)],
										["Next week", () => applyQuickChip(168)],
									] as const
								).map(([label, fn]) => (
									<Pressable
										key={label}
										onPress={fn}
										style={({ pressed }) => [styles.chip, { backgroundColor: colors.muted, opacity: pressed ? 0.7 : 1 }]}
										accessibilityRole="button"
										accessibilityLabel={`Set due ${label}`}
									>
										<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "700" }]}>{label}</Text>
									</Pressable>
								))}
							</View>
							<View style={styles.dateRow}>
								<TextInput
									style={[styles.input, styles.dateInput, typography.body, { color: colors.foreground, backgroundColor: colors.card, borderColor: colors.border }]}
									value={remDate}
									onChangeText={setRemDate}
									placeholder="YYYY-MM-DD"
									placeholderTextColor={colors.mutedForeground}
									maxLength={10}
								/>
								<TextInput
									style={[styles.input, styles.dateInput, typography.body, { color: colors.foreground, backgroundColor: colors.card, borderColor: colors.border }]}
									value={remTime}
									onChangeText={setRemTime}
									placeholder="HH:MM"
									placeholderTextColor={colors.mutedForeground}
									maxLength={5}
								/>
							</View>
							<View style={styles.chipRow}>
								{(["none", "daily", "weekly"] as const).map((r) => (
									<Pressable
										key={r}
										onPress={() => setRemRecurrence(r)}
										style={[
											styles.chip,
											{
												backgroundColor: remRecurrence === r ? colors.foreground : colors.card,
												borderColor: colors.border,
												borderWidth: StyleSheet.hairlineWidth,
											},
										]}
										accessibilityRole="button"
										accessibilityState={{ selected: remRecurrence === r }}
										accessibilityLabel={`Repeat ${r}`}
									>
										<Text style={[typography.uiLabel, { color: remRecurrence === r ? colors.background : colors.foreground, fontWeight: "700" }]}>
											{r === "none" ? "Once" : r === "daily" ? "Daily" : "Weekly"}
										</Text>
									</Pressable>
								))}
							</View>
							<Pressable
								onPress={() => void handleCreateReminder()}
								disabled={creatingReminder || !remTitle.trim() || !remDate.trim() || !remTime.trim()}
								style={({ pressed }) => [
									styles.button,
									{ backgroundColor: colors.primary, opacity: pressed || creatingReminder || !remTitle.trim() ? 0.7 : 1 },
								]}
								accessibilityRole="button"
								accessibilityLabel="Save reminder"
							>
								<Text style={[typography.uiLabel, { color: colors.primaryForeground, fontWeight: "700" }]}>
									{creatingReminder ? "Saving" : "Save reminder"}
								</Text>
							</Pressable>

							<Pressable
								onPress={() => void handleCheckNow()}
								disabled={checking}
								style={({ pressed }) => [
									styles.button,
									{ backgroundColor: colors.card, borderColor: colors.border, borderWidth: StyleSheet.hairlineWidth, opacity: pressed || checking ? 0.7 : 1 },
								]}
								accessibilityRole="button"
								accessibilityLabel="Fire due reminders now"
							>
								<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "700" }]}>
									{checking ? "Checking" : "Check due now"}
								</Text>
							</Pressable>

							<Text style={[styles.sectionLabel, typography.uiLabel, { color: colors.foreground }]}>
								Upcoming ({pendingReminders.length})
							</Text>
							{pendingReminders.length === 0 ? (
								<Text style={[typography.body, { color: colors.mutedForeground }]}>
									No upcoming reminders. Set one above.
								</Text>
							) : (
								pendingReminders.map((r) => <ReminderCard key={r.id} reminder={r} onChanged={() => void refresh()} />)
							)}
							{pastReminders.length > 0 ? (
								<>
									<Text style={[styles.sectionLabel, typography.uiLabel, { color: colors.foreground }]}>
										Fired & dismissed ({pastReminders.length})
									</Text>
									{pastReminders.map((r) => <ReminderCard key={r.id} reminder={r} onChanged={() => void refresh()} />)}
								</>
							) : null}

							<Text style={[styles.sectionLabel, typography.uiLabel, { color: colors.foreground }]}>
								Quiet hours
							</Text>
							<Text style={[typography.body, { color: colors.mutedForeground, marginBottom: Spacing.sm }]}>
								{quietStart && quietEnd
									? `Notifications held ${quietStart} to ${quietEnd} (node time). Due reminders fire after quiet hours end.`
									: "Off. During quiet hours due reminders wait instead of pushing."}
							</Text>
							<View style={styles.dateRow}>
								<TextInput
									style={[styles.input, styles.dateInput, typography.body, { color: colors.foreground, backgroundColor: colors.card, borderColor: colors.border }]}
									value={quietFormStart}
									onChangeText={setQuietFormStart}
									placeholder={quietStart ?? "22:00"}
									placeholderTextColor={colors.mutedForeground}
									maxLength={5}
								/>
								<TextInput
									style={[styles.input, styles.dateInput, typography.body, { color: colors.foreground, backgroundColor: colors.card, borderColor: colors.border }]}
									value={quietFormEnd}
									onChangeText={setQuietFormEnd}
									placeholder={quietEnd ?? "07:00"}
									placeholderTextColor={colors.mutedForeground}
									maxLength={5}
								/>
							</View>
							<Pressable
								onPress={() => void handleSaveQuietHours()}
								disabled={savingQuiet}
								style={({ pressed }) => [
									styles.button,
									{ backgroundColor: colors.card, borderColor: colors.border, borderWidth: StyleSheet.hairlineWidth, opacity: pressed || savingQuiet ? 0.7 : 1 },
								]}
								accessibilityRole="button"
								accessibilityLabel="Save quiet hours"
							>
								<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "700" }]}>
									{savingQuiet ? "Saving" : quietStart || quietEnd ? "Update quiet hours" : "Set quiet hours"}
								</Text>
							</Pressable>
							{quietStart || quietEnd ? (
								<Pressable
									onPress={() => { setQuietFormStart(""); setQuietFormEnd(""); void handleSaveQuietHours(); }}
									disabled={savingQuiet}
									style={styles.deleteChip}
									accessibilityRole="button"
									accessibilityLabel="Clear quiet hours"
								>
									<Text style={[typography.uiLabel, { color: colors.destructive }]}>Clear quiet hours</Text>
								</Pressable>
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
	chipRow: {
		flexDirection: "row",
		flexWrap: "wrap",
		gap: Spacing.sm,
		marginTop: Spacing.sm,
	},
	dateRow: {
		flexDirection: "row",
		gap: Spacing.sm,
	},
	dateInput: {
		flex: 1,
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
