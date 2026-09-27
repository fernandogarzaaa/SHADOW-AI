import * as Haptics from "expo-haptics";
import { router, useFocusEffect } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import {
	ActivityIndicator,
	Alert,
	FlatList,
	Pressable,
	StyleSheet,
	Text,
	TextInput,
	View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import {
	deleteMemoryItem,
	getMemoryRecent,
	ingestMemory,
	searchMemory,
	ShadowApiError,
	type MemoryItem,
	type MemorySearchResult,
} from "@/api/shadow";
import { SettingsScreen } from "@/components/settings/primitives";
import { useConnectionStore } from "@/stores/useConnectionStore";
import { SemanticSpacing, Spacing, typography, useTheme } from "../../src/theme";

const PAGE_SIZE = 20;

function formatCardDate(iso: string): string {
	const d = new Date(iso);
	if (Number.isNaN(d.getTime())) return "";
	const mm = String(d.getMonth() + 1).padStart(2, "0");
	const dd = String(d.getDate()).padStart(2, "0");
	const yy = String(d.getFullYear()).slice(2);
	return `${mm}.${dd}.${yy}`;
}

/**
 * Memory: the node's dated memory cards with semantic search. Everything is
 * stored encrypted on the node; search runs against a blind HMAC index so
 * the plaintext never leaves the encrypted store.
 */
export default function MemoryScreen() {
	const { colors } = useTheme();
	const insets = useSafeAreaInsets();
	const isPaired = useConnectionStore((s) => s.isPaired);

	const [items, setItems] = useState<MemoryItem[]>([]);
	const [total, setTotal] = useState(0);
	const [loading, setLoading] = useState(true);
	const [loadingMore, setLoadingMore] = useState(false);
	const [error, setError] = useState<string | null>(null);

	const [query, setQuery] = useState("");
	const [searching, setSearching] = useState(false);
	const [results, setResults] = useState<MemorySearchResult[] | null>(null);
	const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

	const [note, setNote] = useState("");
	const [saving, setSaving] = useState(false);

	const loadRecent = useCallback(
		async (offset: number, append: boolean) => {
			if (!isPaired) {
				setLoading(false);
				return;
			}
			if (append) setLoadingMore(true);
			else {
				setLoading(true);
				setError(null);
			}
			try {
				const page = await getMemoryRecent(PAGE_SIZE, offset);
				setItems((prev) => (append ? [...prev, ...page.items] : page.items));
				setTotal(page.total);
			} catch (e) {
				if (!append)
					setError(
						e instanceof ShadowApiError
							? e.message
							: "Could not load memory.",
					);
			} finally {
				setLoading(false);
				setLoadingMore(false);
			}
		},
		[isPaired],
	);

	const refresh = useCallback(() => {
		void loadRecent(0, false);
	}, [loadRecent]);

	useFocusEffect(refresh);

	// Debounced semantic search.
	useEffect(() => {
		if (searchTimer.current) clearTimeout(searchTimer.current);
		const q = query.trim();
		if (!q || !isPaired) {
			setResults(null);
			setSearching(false);
			return;
		}
		setSearching(true);
		searchTimer.current = setTimeout(() => {
			searchMemory(q, 10)
				.then((r) => setResults(r))
				.catch(() => setResults([]))
				.finally(() => setSearching(false));
		}, 350);
		return () => {
			if (searchTimer.current) clearTimeout(searchTimer.current);
		};
	}, [query, isPaired]);

	async function handleRemember() {
		const text = note.trim();
		if (!text) return;
		setSaving(true);
		try {
			await ingestMemory(text);
			setNote("");
			void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
			refresh();
		} catch (e) {
			Alert.alert(
				"Could not save",
				e instanceof ShadowApiError ? e.message : "Try again.",
			);
		} finally {
			setSaving(false);
		}
	}

	function handleDelete(item: MemoryItem) {
		Alert.alert(
			"Forget this memory?",
			`"${item.text.slice(0, 80)}${item.text.length > 80 ? "..." : ""}"`,
			[
				{ text: "Cancel", style: "cancel" },
				{
					text: "Forget",
					style: "destructive",
					onPress: () => {
						deleteMemoryItem(item.id)
							.then(() => {
								setItems((prev) => prev.filter((i) => i.id !== item.id));
								setTotal((t) => Math.max(0, t - 1));
								void Haptics.notificationAsync(
									Haptics.NotificationFeedbackType.Success,
								);
							})
							.catch((e: unknown) =>
								Alert.alert(
									"Could not delete",
									e instanceof ShadowApiError ? e.message : "Try again.",
								),
							);
					},
				},
			],
		);
	}

	function renderCard({ item }: { item: MemoryItem }) {
		return (
			<View
				style={[
					styles.card,
					{
						backgroundColor: colors.card,
						borderColor: colors.border,
					},
				]}
			>
				<View style={styles.cardHeader}>
					<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "700" }]}>
						{item.category.replace(/_/g, " ").toUpperCase()}
					</Text>
					<Text style={[typography.meta, { color: colors.mutedForeground }]}>
						{formatCardDate(item.created_at)}
					</Text>
				</View>
				<Text
					style={[typography.body, { color: colors.foreground, marginTop: Spacing.xs }]}
					numberOfLines={6}
				>
					{item.text}
				</Text>
				<View style={styles.cardFooter}>
					<Text
						style={[typography.meta, { color: colors.mutedForeground, flex: 1 }]}
						numberOfLines={1}
					>
						{item.source.title}
						{item.sensitive ? " · sensitive" : ""}
					</Text>
					<Pressable
						onPress={() => handleDelete(item)}
						accessibilityRole="button"
						accessibilityLabel="Forget this memory"
						hitSlop={12}
					>
						<Text style={[typography.uiLabel, { color: colors.destructive }]}>
							Forget
						</Text>
					</Pressable>
				</View>
			</View>
		);
	}

	return (
		<SettingsScreen title="Memory" showClose={false}>
			<View
				style={[
					styles.container,
					{ paddingBottom: Math.max(insets.bottom, Spacing.xl) },
				]}
			>
				{!isPaired ? (
					<View style={styles.center}>
						<Text
							style={[
								typography.body,
								{ color: colors.mutedForeground, textAlign: "center" },
							]}
						>
							Link your SHADOW node to see what your assistant
							remembers. Memories live on the node, encrypted.
						</Text>
						<Pressable
							onPress={() => router.push("/settings/link-node")}
							style={({ pressed }) => [
								styles.button,
								{
									backgroundColor: colors.primary,
									opacity: pressed ? 0.85 : 1,
								},
							]}
							accessibilityRole="button"
							accessibilityLabel="Link node"
						>
							<Text
								style={[
									typography.uiLabel,
									{ color: colors.primaryForeground, fontWeight: "700" },
								]}
							>
								Link node
							</Text>
						</Pressable>
					</View>
				) : (
					<FlatList
						data={items}
						keyExtractor={(i) => i.id}
						renderItem={renderCard}
						contentContainerStyle={styles.list}
						ListHeaderComponent={
							<View>
								<TextInput
									style={[
										styles.input,
										typography.body,
										{
											color: colors.foreground,
											backgroundColor: colors.card,
											borderColor: colors.border,
										},
									]}
									value={query}
									onChangeText={setQuery}
									placeholder="Search what your assistant remembers"
									placeholderTextColor={colors.mutedForeground}
									returnKeyType="search"
								/>
								{searching ? (
									<ActivityIndicator
										style={styles.searchSpinner}
										color={colors.primary}
										accessibilityLabel="Searching memory"
									/>
								) : results !== null ? (
									<View style={styles.resultsBlock}>
										<Text
											style={[
												typography.uiLabel,
												{ color: colors.mutedForeground, fontWeight: "700" },
											]}
										>
											{results.length === 0
												? "No matches"
												: `${results.length} match${results.length === 1 ? "" : "es"}`}
										</Text>
										{results.map((r) => (
											<View
												key={r.item.id}
												style={[
													styles.card,
													{
														backgroundColor: colors.card,
														borderColor: colors.border,
														marginTop: Spacing.sm,
													},
												]}
											>
												<Text
													style={[
														typography.meta,
														{ color: colors.mutedForeground },
													]}
												>
													{r.attribution} ·{" "}
													{formatCardDate(r.item.created_at)}
												</Text>
												<Text
													style={[
														typography.body,
														{ color: colors.foreground, marginTop: Spacing.xs },
													]}
													numberOfLines={4}
												>
													{r.item.text}
												</Text>
											</View>
										))}
									</View>
								) : null}

								<Text
									style={[
										styles.sectionLabel,
										typography.uiLabel,
										{ color: colors.foreground },
									]}
								>
									Remember something
								</Text>
								<TextInput
									style={[
										styles.input,
										styles.multiline,
										typography.body,
										{
											color: colors.foreground,
											backgroundColor: colors.card,
											borderColor: colors.border,
										},
									]}
									value={note}
									onChangeText={setNote}
									placeholder="Tell your assistant something to remember"
									placeholderTextColor={colors.mutedForeground}
									multiline
									maxLength={2000}
								/>
								<Pressable
									onPress={() => void handleRemember()}
									disabled={saving || !note.trim()}
									style={({ pressed }) => [
										styles.button,
										{
											backgroundColor: colors.primary,
											opacity: pressed || saving || !note.trim() ? 0.7 : 1,
										},
									]}
									accessibilityRole="button"
									accessibilityLabel="Save memory"
								>
									<Text
										style={[
											typography.uiLabel,
											{ color: colors.primaryForeground, fontWeight: "700" },
										]}
									>
										{saving ? "Saving" : "Remember"}
									</Text>
								</Pressable>

								<Text
									style={[
										styles.sectionLabel,
										typography.uiLabel,
										{ color: colors.foreground },
									]}
								>
									Recent{total > 0 ? ` (${total})` : ""}
								</Text>
							</View>
						}
						ListEmptyComponent={
							loading ? (
								<ActivityIndicator
									style={styles.center}
									color={colors.primary}
									accessibilityLabel="Loading memories"
								/>
							) : error ? (
								<View style={styles.center}>
									<Text
										style={[
											typography.body,
											{ color: colors.destructive, textAlign: "center" },
										]}
									>
										{error}
									</Text>
									<Pressable
										onPress={refresh}
										style={({ pressed }) => [
											styles.button,
											{
												backgroundColor: colors.card,
												borderColor: colors.border,
												borderWidth: StyleSheet.hairlineWidth,
												opacity: pressed ? 0.7 : 1,
											},
										]}
										accessibilityRole="button"
										accessibilityLabel="Retry"
									>
										<Text
											style={[
												typography.uiLabel,
												{ color: colors.foreground, fontWeight: "700" },
											]}
										>
											Retry
										</Text>
									</Pressable>
								</View>
							) : (
								<Text
									style={[
										typography.body,
										{
											color: colors.mutedForeground,
											textAlign: "center",
											marginTop: Spacing.xl,
										},
									]}
								>
									Nothing remembered yet. Add your first memory above.
								</Text>
							)
						}
						ListFooterComponent={
							items.length < total ? (
								<Pressable
									onPress={() => void loadRecent(items.length, true)}
									disabled={loadingMore}
									style={({ pressed }) => [
										styles.button,
										{
											backgroundColor: colors.card,
											borderColor: colors.border,
											borderWidth: StyleSheet.hairlineWidth,
											opacity: pressed || loadingMore ? 0.7 : 1,
										},
									]}
									accessibilityRole="button"
									accessibilityLabel="Load more memories"
								>
									<Text
										style={[
											typography.uiLabel,
											{ color: colors.foreground, fontWeight: "700" },
										]}
									>
										{loadingMore
											? "Loading"
											: `Load more (${total - items.length} left)`}
									</Text>
								</Pressable>
							) : null
						}
					/>
				)}
			</View>
		</SettingsScreen>
	);
}

const styles = StyleSheet.create({
	container: {
		flex: 1,
		paddingHorizontal: Spacing.xl,
		paddingTop: Spacing.md,
	},
	center: {
		flexGrow: 1,
		justifyContent: "center",
		alignItems: "center",
		gap: Spacing.md,
		paddingHorizontal: Spacing.xl,
	},
	list: {
		gap: Spacing.md,
		paddingBottom: Spacing.xl,
	},
	input: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: SemanticSpacing.radiusInput,
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.md,
		minHeight: SemanticSpacing.inputHeight,
	},
	multiline: {
		minHeight: 96,
		textAlignVertical: "top",
		marginTop: Spacing.sm,
	},
	searchSpinner: {
		marginTop: Spacing.md,
	},
	resultsBlock: {
		marginTop: Spacing.md,
	},
	sectionLabel: {
		marginTop: Spacing.xl,
		marginBottom: Spacing.sm,
		fontWeight: "700",
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
	cardHeader: {
		flexDirection: "row",
		justifyContent: "space-between",
		alignItems: "center",
	},
	cardFooter: {
		flexDirection: "row",
		justifyContent: "space-between",
		alignItems: "center",
		marginTop: Spacing.sm,
		gap: Spacing.md,
	},
});
