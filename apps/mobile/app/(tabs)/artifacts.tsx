import BottomSheet from "@gorhom/bottom-sheet";
import * as Haptics from "expo-haptics";
import { router, useFocusEffect } from "expo-router";
import { useCallback, useRef, useState } from "react";
import {
	ActivityIndicator,
	Alert,
	Pressable,
	RefreshControl,
	ScrollView,
	StyleSheet,
	Text,
	View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import {
	createArtifact,
	listArtifacts,
	ShadowApiError,
	type ArtifactKind,
	type ArtifactSummary,
} from "@/api/shadow";
import { Sheet, SheetScrollView, SheetTextInput, SheetView } from "@/components/ui/sheet";
import { DocumentIcon } from "@/components/icons";
import { useConnectionStore } from "@/stores/useConnectionStore";
import { SemanticSpacing, Spacing, typography, useTheme } from "@/theme";

const KINDS: ArtifactKind[] = ["markdown", "html", "code", "csv", "json", "text"];

const KIND_LABEL: Record<ArtifactKind, string> = {
	markdown: "Markdown",
	html: "HTML",
	code: "Code",
	csv: "CSV",
	json: "JSON",
	text: "Text",
};

function formatDate(epochSeconds: number): string {
	const d = new Date(epochSeconds * 1000);
	if (Number.isNaN(d.getTime())) return "";
	const mm = String(d.getMonth() + 1).padStart(2, "0");
	const dd = String(d.getDate()).padStart(2, "0");
	const yy = String(d.getFullYear()).slice(2);
	return `${mm}.${dd}.${yy}`;
}

function formatSize(bytes: number): string {
	if (bytes < 1024) return `${bytes} B`;
	if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
	return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function ArtifactRow({ item }: { item: ArtifactSummary }) {
	const { colors } = useTheme();
	return (
		<Pressable
			onPress={() => {
				void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
				router.push(`/artifact/${item.id}`);
			}}
			style={({ pressed }) => [
				styles.card,
				{
					backgroundColor: colors.card,
					borderColor: colors.border,
					opacity: pressed ? 0.7 : 1,
				},
			]}
			accessibilityRole="button"
			accessibilityLabel={`Open artifact ${item.title}`}
		>
			<View style={styles.cardHeader}>
				<DocumentIcon size={16} color={colors.primary} />
				<Text
					style={[typography.meta, { color: colors.primary, fontWeight: "700" }]}
				>
					{KIND_LABEL[item.kind] ?? item.kind} · v{item.version}
				</Text>
				<Text style={[typography.meta, { color: colors.mutedForeground }]}>
					{formatDate(item.updated_at)}
				</Text>
			</View>
			<Text
				style={[
					typography.body,
					{ color: colors.foreground, fontWeight: "700", marginTop: Spacing.xs },
				]}
				numberOfLines={2}
			>
				{item.title}
			</Text>
			<Text style={[typography.meta, { color: colors.mutedForeground, marginTop: Spacing.xs }]}>
				{formatSize(item.size_bytes)}
				{item.tags.length > 0 ? ` · ${item.tags.slice(0, 3).join(", ")}` : ""}
			</Text>
		</Pressable>
	);
}

/**
 * Artifacts tab: documents the agent produces, newest first, with kind
 * filters and a creation sheet. Full viewing, editing, and version
 * history live on the artifact detail screen.
 */
export default function ArtifactsScreen() {
	const { colors } = useTheme();
	const insets = useSafeAreaInsets();
	const isPaired = useConnectionStore((s) => s.isPaired);

	const [kindFilter, setKindFilter] = useState<ArtifactKind | null>(null);
	const [items, setItems] = useState<ArtifactSummary[]>([]);
	const [total, setTotal] = useState(0);
	const [loading, setLoading] = useState(true);
	const [refreshing, setRefreshing] = useState(false);
	const [error, setError] = useState<string | null>(null);

	const sheetRef = useRef<BottomSheet>(null);
	const [title, setTitle] = useState("");
	const [kind, setKind] = useState<ArtifactKind>("markdown");
	const [content, setContent] = useState("");
	const [tags, setTags] = useState("");
	const [saving, setSaving] = useState(false);

	const refresh = useCallback(async () => {
		if (!isPaired) {
			setLoading(false);
			return;
		}
		setError(null);
		try {
			const res = await listArtifacts(50, 0, kindFilter ?? undefined);
			const sorted = [...res.artifacts].sort(
				(a, b) =>
					new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
			);
			setItems(sorted);
			setTotal(res.total);
		} catch (e) {
			setError(
				e instanceof ShadowApiError ? e.message : "Could not load artifacts.",
			);
		} finally {
			setLoading(false);
			setRefreshing(false);
		}
	}, [isPaired, kindFilter]);

	useFocusEffect(
		useCallback(() => {
			setLoading(true);
			void refresh();
		}, [refresh]),
	);

	function openCreateSheet() {
		setTitle("");
		setKind("markdown");
		setContent("");
		setTags("");
		void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
		sheetRef.current?.snapToIndex(0);
	}

	async function handleCreate() {
		const t = title.trim();
		if (!t) {
			Alert.alert("Missing title", "Give the artifact a title first.");
			return;
		}
		setSaving(true);
		try {
			const tagList = tags
				.split(",")
				.map((s) => s.trim())
				.filter(Boolean);
			const created = await createArtifact({
				title: t,
				kind,
				content,
				tags: tagList,
			});
			void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
			sheetRef.current?.close();
			void refresh();
			router.push(`/artifact/${created.id}`);
		} catch (e) {
			Alert.alert(
				"Could not save",
				e instanceof ShadowApiError ? e.message : "Try again.",
			);
		} finally {
			setSaving(false);
		}
	}

	return (
		<View style={[styles.container, { paddingTop: insets.top }]}>
			<View style={styles.header}>
				<Text style={[typography.h1, { color: colors.foreground }]}>
					Artifacts
				</Text>
				<Pressable
					onPress={openCreateSheet}
					style={({ pressed }) => [
						styles.newButton,
						{ backgroundColor: colors.primary, opacity: pressed ? 0.8 : 1 },
					]}
					accessibilityRole="button"
					accessibilityLabel="Create artifact"
				>
					<Text
						style={[
							typography.uiLabel,
							{ color: colors.primaryForeground, fontWeight: "700" },
						]}
					>
						New
					</Text>
				</Pressable>
			</View>

			<ScrollView
				horizontal
				showsHorizontalScrollIndicator={false}
				contentContainerStyle={styles.chipRow}
			>
				<FilterChip
					label="All"
					selected={kindFilter === null}
					onPress={() => setKindFilter(null)}
				/>
				{KINDS.map((k) => (
					<FilterChip
						key={k}
						label={KIND_LABEL[k]}
						selected={kindFilter === k}
						onPress={() => setKindFilter(kindFilter === k ? null : k)}
					/>
				))}
			</ScrollView>

			{loading ? (
				<ActivityIndicator
					style={styles.center}
					color={colors.primary}
					accessibilityLabel="Loading artifacts"
				/>
			) : error && items.length === 0 ? (
				<View style={styles.center}>
					<Text
						style={[
							typography.body,
							{ color: colors.destructive, textAlign: "center" },
						]}
					>
						{error}
					</Text>
				</View>
			) : (
				<ScrollView
					contentContainerStyle={[
						styles.list,
						{ paddingBottom: Math.max(insets.bottom, Spacing.xl) + 90 },
					]}
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
					{items.length === 0 ? (
						<Text style={[typography.body, { color: colors.mutedForeground }]}>
							No artifacts yet. Ask the agent to write something, or create
							one with the New button.
						</Text>
					) : (
						items.map((a) => <ArtifactRow key={a.id} item={a} />)
					)}
					{total > items.length ? (
						<Text
							style={[
								typography.meta,
								{ color: colors.mutedForeground, textAlign: "center" },
							]}
						>
							Showing {items.length} of {total}
						</Text>
					) : null}
				</ScrollView>
			)}

			<Sheet ref={sheetRef} snapPoints={["92%"]}>
				<SheetView>
					<Text
						style={[
							typography.titleSmall,
							{ color: colors.foreground, marginBottom: Spacing.md },
						]}
					>
						New artifact
					</Text>
					<SheetScrollView
						contentContainerStyle={{ paddingBottom: Spacing.xl }}
						keyboardShouldPersistTaps="handled"
					>
						<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "700" }]}>
							Title
						</Text>
						<SheetTextInput
							value={title}
							onChangeText={setTitle}
							placeholder="What is this?"
							placeholderTextColor={colors.mutedForeground}
							maxLength={200}
							style={[
								styles.input,
								typography.body,
								{ color: colors.foreground, borderColor: colors.border },
							]}
						/>
						<Text
							style={[
								typography.uiLabel,
								{ color: colors.foreground, fontWeight: "700", marginTop: Spacing.md },
							]}
						>
							Kind
						</Text>
						<View style={styles.kindRow}>
							{KINDS.map((k) => (
								<Pressable
									key={k}
									onPress={() => setKind(k)}
									style={[
										styles.kindChip,
										{
											backgroundColor:
												kind === k ? colors.foreground : colors.card,
											borderColor: colors.border,
										},
									]}
									accessibilityRole="button"
									accessibilityState={{ selected: kind === k }}
									accessibilityLabel={`Kind ${KIND_LABEL[k]}`}
								>
									<Text
										style={[
											typography.uiLabel,
											{
												color: kind === k ? colors.background : colors.foreground,
												fontWeight: "700",
											},
										]}
									>
										{KIND_LABEL[k]}
									</Text>
								</Pressable>
							))}
						</View>
						<Text
							style={[
								typography.uiLabel,
								{ color: colors.foreground, fontWeight: "700", marginTop: Spacing.md },
							]}
						>
							Content
						</Text>
						<SheetTextInput
							value={content}
							onChangeText={setContent}
							placeholder="Write it here. Markdown renders on the detail screen."
							placeholderTextColor={colors.mutedForeground}
							multiline
							style={[
								styles.input,
								styles.multiline,
								typography.body,
								{ color: colors.foreground, borderColor: colors.border },
							]}
						/>
						<Text
							style={[
								typography.uiLabel,
								{ color: colors.foreground, fontWeight: "700", marginTop: Spacing.md },
							]}
						>
							Tags
						</Text>
						<SheetTextInput
							value={tags}
							onChangeText={setTags}
							placeholder="Comma separated, optional"
							placeholderTextColor={colors.mutedForeground}
							maxLength={200}
							style={[
								styles.input,
								typography.body,
								{ color: colors.foreground, borderColor: colors.border },
							]}
						/>
						<Pressable
							onPress={() => void handleCreate()}
							disabled={saving || !title.trim()}
							style={({ pressed }) => [
								styles.button,
								{
									backgroundColor: colors.primary,
									opacity: pressed || saving || !title.trim() ? 0.7 : 1,
								},
							]}
							accessibilityRole="button"
							accessibilityLabel="Save artifact"
						>
							<Text
								style={[
									typography.uiLabel,
									{ color: colors.primaryForeground, fontWeight: "700" },
								]}
							>
								{saving ? "Saving" : "Save artifact"}
							</Text>
						</Pressable>
					</SheetScrollView>
				</SheetView>
			</Sheet>
		</View>
	);
}

function FilterChip({
	label,
	selected,
	onPress,
}: {
	label: string;
	selected: boolean;
	onPress: () => void;
}) {
	const { colors } = useTheme();
	return (
		<Pressable
			onPress={onPress}
			style={[
				styles.chip,
				{
					backgroundColor: selected ? colors.foreground : colors.card,
					borderColor: colors.border,
				},
			]}
			accessibilityRole="button"
			accessibilityState={{ selected }}
			accessibilityLabel={`Filter ${label}`}
		>
			<Text
				style={[
					typography.uiLabel,
					{
						color: selected ? colors.background : colors.foreground,
						fontWeight: "700",
					},
				]}
			>
				{label}
			</Text>
		</Pressable>
	);
}

const styles = StyleSheet.create({
	container: {
		flex: 1,
	},
	header: {
		flexDirection: "row",
		alignItems: "center",
		justifyContent: "space-between",
		paddingHorizontal: Spacing.xl,
	},
	newButton: {
		borderRadius: 999,
		paddingHorizontal: Spacing.lg,
		paddingVertical: Spacing.sm,
		minHeight: SemanticSpacing.buttonHeightMd,
		justifyContent: "center",
	},
	chipRow: {
		flexDirection: "row",
		gap: Spacing.sm,
		paddingHorizontal: Spacing.xl,
		paddingVertical: Spacing.md,
	},
	chip: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: 999,
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.xs,
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
		paddingTop: Spacing.sm,
	},
	card: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: SemanticSpacing.radiusModal,
		padding: Spacing.lg,
	},
	cardHeader: {
		flexDirection: "row",
		alignItems: "center",
		gap: Spacing.xs,
		justifyContent: "space-between",
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
		minHeight: 160,
		textAlignVertical: "top",
	},
	kindRow: {
		flexDirection: "row",
		flexWrap: "wrap",
		gap: Spacing.sm,
		marginTop: Spacing.sm,
	},
	kindChip: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: 999,
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.xs,
	},
	button: {
		marginTop: Spacing.lg,
		borderRadius: SemanticSpacing.radiusModal,
		minHeight: SemanticSpacing.buttonHeightLg,
		justifyContent: "center",
		alignItems: "center",
		paddingHorizontal: Spacing.xl,
	},
});
