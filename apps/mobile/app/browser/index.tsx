import * as Haptics from "expo-haptics";
import { router, useFocusEffect } from "expo-router";
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
	listBrowserTasks,
	ShadowApiError,
	startBrowserTask,
	type BrowserTask,
} from "@/api/shadow";
import { useConnectionStore } from "@/stores/useConnectionStore";
import { SemanticSpacing, Spacing, typography, useTheme } from "@/theme";
import { browserStatusLabel } from "@/lib/browserStatus";

/**
 * Browser tasks: start one, see recent ones. The task runs in a private
 * Chrome on the user's own Shadow node; this screen only drives it.
 */
export default function BrowserTasksScreen() {
	const { colors } = useTheme();
	const insets = useSafeAreaInsets();
	const isPaired = useConnectionStore((s) => s.isPaired);

	const [tasks, setTasks] = useState<BrowserTask[]>([]);
	const [loading, setLoading] = useState(true);
	const [refreshing, setRefreshing] = useState(false);
	const [goal, setGoal] = useState("");
	const [startUrl, setStartUrl] = useState("");
	const [starting, setStarting] = useState(false);

	const load = useCallback(async () => {
		if (!isPaired) {
			setLoading(false);
			return;
		}
		try {
			setTasks(await listBrowserTasks());
		} catch {
			// Shown as an empty list; pull to refresh retries.
		} finally {
			setLoading(false);
			setRefreshing(false);
		}
	}, [isPaired]);

	useFocusEffect(
		useCallback(() => {
			void load();
		}, [load]),
	);

	async function handleStart() {
		const g = goal.trim();
		if (!g) return;
		setStarting(true);
		try {
			const task = await startBrowserTask(g, startUrl.trim());
			setGoal("");
			setStartUrl("");
			void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
			router.push(`/browser/${task.id}`);
		} catch (e) {
			Alert.alert("Couldn't start", e instanceof ShadowApiError ? e.message : "Try again.");
		} finally {
			setStarting(false);
		}
	}

	return (
		<View style={[styles.container, { paddingTop: insets.top, backgroundColor: colors.background }]}>
			<View style={styles.header}>
				<Pressable onPress={() => router.back()} accessibilityRole="button" accessibilityLabel="Back" hitSlop={12}>
					<Text style={[typography.uiLabel, { color: colors.primary, fontWeight: "700" }]}>{"< Back"}</Text>
				</Pressable>
			</View>
			<ScrollView
				contentContainerStyle={[styles.list, { paddingBottom: Math.max(insets.bottom, Spacing.xl) }]}
				refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); void load(); }} />}
				keyboardShouldPersistTaps="handled"
			>
				<Text style={[typography.h1, { color: colors.foreground }]}>Browser</Text>
				<Text style={[typography.body, { color: colors.mutedForeground }]}>
					A private browser on your Shadow node does tasks for you. Buying, paying, sending, submitting
					forms and signing in wait for your approval. Passwords come from your saved logins and are never
					shown to the model.
				</Text>

				<TextInput
					style={[styles.input, styles.multiline, typography.body, { color: colors.foreground, backgroundColor: colors.card, borderColor: colors.border }]}
					value={goal}
					onChangeText={setGoal}
					placeholder="What should the browser do?"
					placeholderTextColor={colors.mutedForeground}
					multiline
					maxLength={2000}
					accessibilityLabel="Task"
				/>
				<TextInput
					style={[styles.input, typography.body, { color: colors.foreground, backgroundColor: colors.card, borderColor: colors.border }]}
					value={startUrl}
					onChangeText={setStartUrl}
					placeholder="Start at (optional), e.g. example.com"
					placeholderTextColor={colors.mutedForeground}
					autoCapitalize="none"
					autoCorrect={false}
					keyboardType="url"
					accessibilityLabel="Start address"
				/>
				<Pressable
					onPress={handleStart}
					disabled={starting || !goal.trim()}
					accessibilityRole="button"
					accessibilityState={{ disabled: starting || !goal.trim(), busy: starting }}
					style={({ pressed }) => [styles.button, { backgroundColor: colors.primary, opacity: pressed || starting || !goal.trim() ? 0.6 : 1 }]}
				>
					{starting ? (
						<ActivityIndicator color={colors.primaryForeground} />
					) : (
						<Text style={[typography.uiLabel, { color: colors.primaryForeground, fontWeight: "700" }]}>Start</Text>
					)}
				</Pressable>

				<Text style={[styles.sectionLabel, typography.uiLabel, { color: colors.foreground }]}>Recent tasks</Text>
				{loading ? (
					<ActivityIndicator color={colors.primary} accessibilityLabel="Loading tasks" />
				) : tasks.length === 0 ? (
					<Text style={[typography.meta, { color: colors.mutedForeground }]}>No browser tasks yet.</Text>
				) : (
					tasks.map((t) => (
						<Pressable
							key={t.id}
							onPress={() => router.push(`/browser/${t.id}`)}
							accessibilityRole="button"
							accessibilityLabel={`${t.goal}, ${browserStatusLabel(t.status)}`}
							style={({ pressed }) => [styles.card, { backgroundColor: colors.card, borderColor: colors.border, opacity: pressed ? 0.7 : 1 }]}
						>
							<Text style={[typography.body, { color: colors.foreground, fontWeight: "600" }]} numberOfLines={2}>
								{t.goal}
							</Text>
							<Text style={[typography.meta, { color: colors.mutedForeground, marginTop: Spacing.xs }]} numberOfLines={1}>
								{browserStatusLabel(t.status)}
								{t.answer || t.error ? ` · ${t.answer ?? t.error}` : ""}
							</Text>
						</Pressable>
					))
				)}
			</ScrollView>
		</View>
	);
}

const styles = StyleSheet.create({
	container: { flex: 1 },
	header: { paddingHorizontal: Spacing.xl, paddingVertical: Spacing.sm },
	list: { gap: Spacing.md, paddingHorizontal: Spacing.xl },
	sectionLabel: { marginTop: Spacing.lg, fontWeight: "700" },
	input: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: SemanticSpacing.radiusInput,
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.md,
		minHeight: SemanticSpacing.inputHeight,
	},
	multiline: { minHeight: 96, textAlignVertical: "top" },
	button: {
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
});
