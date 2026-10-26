import * as Haptics from "expo-haptics";
import { router, useFocusEffect, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import {
	ActivityIndicator,
	Alert,
	Image,
	Pressable,
	ScrollView,
	StyleSheet,
	Text,
	TextInput,
	View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import {
	BROWSER_ACTIVE_STATUSES,
	browserFrameSource,
	getBrowserTask,
	replyBrowserTask,
	ShadowApiError,
	stopBrowserTask,
	type BrowserTask,
} from "@/api/shadow";
import { browserStatusLabel, describeBrowserStep } from "@/lib/browserStatus";
import { useApprovalsStore } from "@/stores/useApprovalsStore";
import { useConnectionStore } from "@/stores/useConnectionStore";
import { SemanticSpacing, Spacing, typography, useTheme } from "@/theme";

const POLL_MS = 1500;

/**
 * Live view of a browser task running on the user's Shadow node: the latest
 * screenshot, the step log, and inline approve / deny / answer / stop. Steps
 * that change a site only continue after approval (here, in Approvals, or
 * from the notification, which opens the app first).
 */
export default function BrowserTaskScreen() {
	const { colors } = useTheme();
	const insets = useSafeAreaInsets();
	const { id } = useLocalSearchParams<{ id: string }>();
	const isPaired = useConnectionStore((s) => s.isPaired);
	const decide = useApprovalsStore((s) => s.decide);

	const [task, setTask] = useState<BrowserTask | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [frame, setFrame] = useState<{ uri: string; headers: Record<string, string> } | null>(null);
	const [reply, setReply] = useState("");
	const [busy, setBusy] = useState(false);
	const frameAt = useRef(0);
	const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
	const focused = useRef(false);

	const poll = useCallback(async () => {
		if (!isPaired || !id) return;
		try {
			const t = await getBrowserTask(id);
			setTask(t);
			setError(null);
			if (t.frame_at && t.frame_at !== frameAt.current) {
				frameAt.current = t.frame_at;
				setFrame(await browserFrameSource(id, t.frame_at));
			}
			if (focused.current && BROWSER_ACTIVE_STATUSES.has(t.status)) {
				timer.current = setTimeout(() => void poll(), POLL_MS);
			}
		} catch (e) {
			setError(e instanceof ShadowApiError ? e.message : "Couldn't reach your node.");
			if (focused.current) timer.current = setTimeout(() => void poll(), POLL_MS * 2);
		}
	}, [isPaired, id]);

	useFocusEffect(
		useCallback(() => {
			focused.current = true;
			void poll();
			return () => {
				focused.current = false;
				if (timer.current) clearTimeout(timer.current);
			};
		}, [poll]),
	);

	useEffect(() => () => {
		if (timer.current) clearTimeout(timer.current);
	}, []);

	async function handleDecision(approve: boolean) {
		if (!task?.approval_id) return;
		setBusy(true);
		try {
			// Same store (and Face ID gate, when app lock is on) as the
			// Approvals tab.
			await decide(task.approval_id, approve ? "approve" : "deny");
			void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
		} finally {
			setBusy(false);
			void poll();
		}
	}

	async function handleReply() {
		const text = reply.trim();
		if (!text || !id) return;
		setBusy(true);
		try {
			await replyBrowserTask(id, text);
			setReply("");
		} catch (e) {
			Alert.alert("Couldn't send", e instanceof ShadowApiError ? e.message : "Try again.");
		} finally {
			setBusy(false);
			void poll();
		}
	}

	function handleStop() {
		if (!id) return;
		Alert.alert("Stop this task?", "The browser stops after its current step.", [
			{ text: "Keep going", style: "cancel" },
			{
				text: "Stop",
				style: "destructive",
				onPress: () => {
					stopBrowserTask(id)
						.then(() => void poll())
						.catch((e: unknown) => Alert.alert("Couldn't stop", e instanceof ShadowApiError ? e.message : "Try again."));
				},
			},
		]);
	}

	const active = task ? BROWSER_ACTIVE_STATUSES.has(task.status) : false;

	return (
		<View style={[styles.container, { paddingTop: insets.top, backgroundColor: colors.background }]}>
			<View style={styles.header}>
				<Pressable onPress={() => router.back()} accessibilityRole="button" accessibilityLabel="Back" hitSlop={12}>
					<Text style={[typography.uiLabel, { color: colors.primary, fontWeight: "700" }]}>{"< Browser"}</Text>
				</Pressable>
				{active ? (
					<Pressable onPress={handleStop} accessibilityRole="button" accessibilityLabel="Stop task" hitSlop={12}>
						<Text style={[typography.uiLabel, { color: colors.destructive, fontWeight: "700" }]}>Stop</Text>
					</Pressable>
				) : null}
			</View>
			{!task ? (
				<View style={styles.center}>
					{error ? (
						<Text style={[typography.body, { color: colors.destructive, textAlign: "center" }]}>{error}</Text>
					) : (
						<ActivityIndicator color={colors.primary} accessibilityLabel="Loading task" />
					)}
				</View>
			) : (
				<ScrollView
					contentContainerStyle={[styles.list, { paddingBottom: Math.max(insets.bottom, Spacing.xl) }]}
					keyboardShouldPersistTaps="handled"
				>
					<Text style={[typography.h2, { color: colors.foreground }]}>{task.goal}</Text>
					<Text
						style={[typography.meta, { color: task.status === "failed" ? colors.destructive : colors.mutedForeground }]}
						accessibilityLiveRegion="polite"
					>
						{browserStatusLabel(task.status)}
						{task.url ? ` · ${task.url}` : ""}
					</Text>

					{task.status === "waiting_approval" && task.approval_id ? (
						<View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.warning }]}>
							<Text style={[typography.body, { color: colors.foreground, fontWeight: "700" }]}>Approve this step?</Text>
							<Text style={[typography.meta, { color: colors.mutedForeground, marginTop: Spacing.xs }]}>
								The browser wants to change something on {hostOf(task.url)}. Nothing happens until you decide.
							</Text>
							<View style={styles.actionRow}>
								<Pressable
									onPress={() => void handleDecision(true)}
									disabled={busy}
									accessibilityRole="button"
									style={({ pressed }) => [styles.halfButton, { backgroundColor: colors.primary, opacity: pressed || busy ? 0.7 : 1 }]}
								>
									<Text style={[typography.uiLabel, { color: colors.primaryForeground, fontWeight: "700" }]}>Approve</Text>
								</Pressable>
								<Pressable
									onPress={() => router.push(`/approvals/${task.approval_id}`)}
									accessibilityRole="button"
									style={({ pressed }) => [styles.halfButton, { borderColor: colors.border, borderWidth: StyleSheet.hairlineWidth, opacity: pressed ? 0.7 : 1 }]}
								>
									<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "600" }]}>Details</Text>
								</Pressable>
								<Pressable
									onPress={() => void handleDecision(false)}
									disabled={busy}
									accessibilityRole="button"
									style={({ pressed }) => [styles.halfButton, { borderColor: colors.destructive, borderWidth: StyleSheet.hairlineWidth, opacity: pressed || busy ? 0.7 : 1 }]}
								>
									<Text style={[typography.uiLabel, { color: colors.destructive, fontWeight: "700" }]}>Deny</Text>
								</Pressable>
							</View>
						</View>
					) : null}

					{task.status === "waiting_user" && task.question ? (
						<View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.warning }]}>
							<Text style={[typography.body, { color: colors.foreground, fontWeight: "700" }]}>{task.question}</Text>
							<TextInput
								style={[styles.input, typography.body, { color: colors.foreground, backgroundColor: colors.background, borderColor: colors.border }]}
								value={reply}
								onChangeText={setReply}
								placeholder="Your answer"
								placeholderTextColor={colors.mutedForeground}
								accessibilityLabel="Your answer"
								onSubmitEditing={() => void handleReply()}
								returnKeyType="send"
							/>
							<Pressable
								onPress={() => void handleReply()}
								disabled={busy || !reply.trim()}
								accessibilityRole="button"
								style={({ pressed }) => [styles.button, { backgroundColor: colors.primary, opacity: pressed || busy || !reply.trim() ? 0.6 : 1 }]}
							>
								<Text style={[typography.uiLabel, { color: colors.primaryForeground, fontWeight: "700" }]}>Answer</Text>
							</Pressable>
						</View>
					) : null}

					{frame ? (
						<Image
							source={frame}
							style={[styles.frame, { borderColor: colors.border, backgroundColor: colors.card }]}
							resizeMode="contain"
							accessibilityLabel={`Live view of ${task.title || "the page"}`}
						/>
					) : null}

					{task.answer ? (
						<View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
							<Text style={[typography.body, { color: colors.foreground }]} selectable>
								{task.answer}
							</Text>
							{task.notes.map((n) => (
								<Text key={n} style={[typography.meta, { color: colors.mutedForeground, marginTop: Spacing.xs }]}>
									{"• "}
									{n}
								</Text>
							))}
						</View>
					) : null}
					{task.error ? (
						<Text style={[typography.body, { color: colors.destructive }]}>{task.error}</Text>
					) : null}

					<Text style={[styles.sectionLabel, typography.uiLabel, { color: colors.foreground }]}>Steps</Text>
					{task.steps.length === 0 ? (
						<Text style={[typography.meta, { color: colors.mutedForeground }]}>Starting…</Text>
					) : (
						task.steps.map((s) => (
							<Text key={s.n} style={[typography.meta, { color: colors.foreground }]}>
								{`${s.n}. `}
								<Text style={{ fontWeight: "600" }}>{describeBrowserStep(s.action)}</Text>
								<Text style={{ color: colors.mutedForeground }}>{` · ${s.result}`}</Text>
							</Text>
						))
					)}
				</ScrollView>
			)}
		</View>
	);
}

function hostOf(url: string): string {
	try {
		return new URL(url).hostname || "the site";
	} catch {
		return "the site";
	}
}

const styles = StyleSheet.create({
	container: { flex: 1 },
	header: {
		paddingHorizontal: Spacing.xl,
		paddingVertical: Spacing.sm,
		flexDirection: "row",
		justifyContent: "space-between",
	},
	center: { flex: 1, justifyContent: "center", alignItems: "center", paddingHorizontal: Spacing.xl },
	list: { gap: Spacing.md, paddingHorizontal: Spacing.xl },
	sectionLabel: { marginTop: Spacing.lg, fontWeight: "700" },
	card: { borderWidth: StyleSheet.hairlineWidth, borderRadius: SemanticSpacing.radiusModal, padding: Spacing.md },
	frame: {
		width: "100%",
		aspectRatio: 1280 / 800,
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: SemanticSpacing.radiusModal,
	},
	input: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: SemanticSpacing.radiusInput,
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.md,
		minHeight: SemanticSpacing.inputHeight,
		marginTop: Spacing.sm,
	},
	button: {
		marginTop: Spacing.sm,
		borderRadius: SemanticSpacing.radiusModal,
		minHeight: SemanticSpacing.buttonHeightLg,
		justifyContent: "center",
		alignItems: "center",
	},
	actionRow: { flexDirection: "row", gap: Spacing.sm, marginTop: Spacing.md },
	halfButton: {
		flex: 1,
		borderRadius: SemanticSpacing.radiusModal,
		minHeight: SemanticSpacing.buttonHeightMd,
		justifyContent: "center",
		alignItems: "center",
	},
});
