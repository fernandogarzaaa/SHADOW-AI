import BottomSheet from "@gorhom/bottom-sheet";
import * as Haptics from "expo-haptics";
import { router, useFocusEffect, useLocalSearchParams } from "expo-router";
import { useCallback, useRef, useState } from "react";
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
	deleteArtifact,
	getArtifact,
	getArtifactVersion,
	listArtifactVersions,
	updateArtifact,
	ShadowApiError,
	type Artifact,
	type ArtifactVersion,
} from "@/api/shadow";
import { MarkdownRenderer } from "@/components/markdown/MarkdownRenderer";
import { Sheet, SheetScrollView, SheetView } from "@/components/ui/sheet";
import { SemanticSpacing, Spacing, typography, useTheme } from "@/theme";

const MONO_KINDS = new Set(["code", "csv", "json"]);

function formatDate(epochSeconds: number): string {
	const d = new Date(epochSeconds * 1000);
	if (Number.isNaN(d.getTime())) return "";
	return d.toLocaleString(undefined, {
		month: "short",
		day: "numeric",
		year: "numeric",
		hour: "numeric",
		minute: "2-digit",
	});
}

function ArtifactBody({ artifact }: { artifact: Artifact }) {
	const { colors } = useTheme();
	if (artifact.kind === "markdown") {
		return <MarkdownRenderer content={artifact.content} />;
	}
	if (MONO_KINDS.has(artifact.kind)) {
		return (
			<Text
				style={[
					typography.code,
					{ color: colors.foreground, fontSize: 13, lineHeight: 19 },
				]}
				selectable
			>
				{artifact.content}
			</Text>
		);
	}
	// html and text: plain readable rendering.
	return (
		<Text
			style={[typography.body, { color: colors.foreground }]}
			selectable
		>
			{artifact.content}
		</Text>
	);
}

/**
 * Artifact detail: read, edit, version history with restore, delete.
 * Restoring a version PATCHes that version's content, which the node
 * records as a new current version.
 */
export default function ArtifactDetailScreen() {
	const { colors } = useTheme();
	const insets = useSafeAreaInsets();
	const params = useLocalSearchParams<{ id: string }>();
	const id = params.id;

	const [artifact, setArtifact] = useState<Artifact | null>(null);
	const [versions, setVersions] = useState<ArtifactVersion[]>([]);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [editing, setEditing] = useState(false);
	const [editTitle, setEditTitle] = useState("");
	const [editContent, setEditContent] = useState("");
	const [saving, setSaving] = useState(false);
	const [viewingVersion, setViewingVersion] = useState<{
		version: number;
		content: string;
	} | null>(null);

	const versionsSheetRef = useRef<BottomSheet>(null);

	const load = useCallback(async () => {
		if (!id) {
			setError("Missing artifact id.");
			setLoading(false);
			return;
		}
		setError(null);
		try {
			const [a, v] = await Promise.all([
				getArtifact(id),
				listArtifactVersions(id),
			]);
			setArtifact(a);
			setVersions([...v.versions].sort((x, y) => y.version - x.version));
		} catch (e) {
			setError(
				e instanceof ShadowApiError ? e.message : "Could not load the artifact.",
			);
		} finally {
			setLoading(false);
		}
	}, [id]);

	useFocusEffect(
		useCallback(() => {
			setLoading(true);
			void load();
		}, [load]),
	);

	function startEditing() {
		if (!artifact) return;
		setEditTitle(artifact.title);
		setEditContent(artifact.content);
		setViewingVersion(null);
		setEditing(true);
	}

	async function handleSave() {
		if (!artifact) return;
		if (!editTitle.trim()) {
			Alert.alert("Missing title", "Give the artifact a title first.");
			return;
		}
		setSaving(true);
		try {
			const updated = await updateArtifact(artifact.id, {
				title: editTitle.trim(),
				content: editContent,
			});
			void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
			setArtifact(updated);
			setVersions((v) => [
				{
					version: updated.version,
					created_at: updated.updated_at,
					size_bytes: updated.size_bytes,
				},
				...v,
			]);
			setEditing(false);
		} catch (e) {
			Alert.alert(
				"Could not save",
				e instanceof ShadowApiError ? e.message : "Try again.",
			);
		} finally {
			setSaving(false);
		}
	}

	async function handleViewVersion(version: number) {
		if (!artifact) return;
		try {
			const v = await getArtifactVersion(artifact.id, version);
			setViewingVersion({ version, content: v.content });
			versionsSheetRef.current?.close();
		} catch (e) {
			Alert.alert(
				"Could not load version",
				e instanceof ShadowApiError ? e.message : "Try again.",
			);
		}
	}

	async function handleRestore() {
		if (!artifact || !viewingVersion) return;
		Alert.alert(
			"Restore this version?",
			`Version ${viewingVersion.version} becomes the current content, saved as version ${artifact.version + 1}.`,
			[
				{ text: "Cancel", style: "cancel" },
				{
					text: "Restore",
					onPress: async () => {
						try {
							const updated = await updateArtifact(artifact.id, {
								content: viewingVersion.content,
							});
							void Haptics.notificationAsync(
								Haptics.NotificationFeedbackType.Success,
							);
							setArtifact(updated);
							setVersions((v) => [
								{
									version: updated.version,
									created_at: updated.updated_at,
									size_bytes: updated.size_bytes,
								},
								...v,
							]);
							setViewingVersion(null);
						} catch (e) {
							Alert.alert(
								"Could not restore",
								e instanceof ShadowApiError ? e.message : "Try again.",
							);
						}
					},
				},
			],
		);
	}

	function handleDelete() {
		if (!artifact) return;
		Alert.alert(
			"Delete artifact?",
			`"${artifact.title}" and all its versions will be removed from the node.`,
			[
				{ text: "Cancel", style: "cancel" },
				{
					text: "Delete",
					style: "destructive",
					onPress: async () => {
						try {
							await deleteArtifact(artifact.id);
							void Haptics.notificationAsync(
								Haptics.NotificationFeedbackType.Success,
							);
							router.back();
						} catch (e) {
							Alert.alert(
								"Could not delete",
								e instanceof ShadowApiError ? e.message : "Try again.",
							);
						}
					},
				},
			],
		);
	}

	if (loading) {
		return (
			<View style={[styles.center, { paddingTop: insets.top }]}>
				<ActivityIndicator color={colors.primary} accessibilityLabel="Loading artifact" />
			</View>
		);
	}

	if (error || !artifact) {
		return (
			<View style={[styles.center, { paddingTop: insets.top, paddingHorizontal: Spacing.xl }]}>
				<Text
					style={[typography.body, { color: colors.destructive, textAlign: "center" }]}
				>
					{error ?? "Artifact not found."}
				</Text>
				<Pressable
					onPress={() => router.back()}
					style={({ pressed }) => [
						styles.button,
						{
							backgroundColor: colors.primary,
							opacity: pressed ? 0.8 : 1,
							marginTop: Spacing.lg,
						},
					]}
					accessibilityRole="button"
					accessibilityLabel="Go back"
				>
					<Text
						style={[typography.uiLabel, { color: colors.primaryForeground, fontWeight: "700" }]}
					>
						Go back
					</Text>
				</Pressable>
			</View>
		);
	}

	const shownVersion = viewingVersion?.version ?? artifact.version;
	const shownContent = viewingVersion?.content ?? artifact.content;

	return (
		<View style={[styles.container, { paddingTop: insets.top }]}>
			<View style={styles.header}>
				<Pressable
					onPress={() => router.back()}
					hitSlop={8}
					accessibilityRole="button"
					accessibilityLabel="Back"
				>
					<Text style={[typography.body, { color: colors.primary }]}>Back</Text>
				</Pressable>
				<View style={styles.headerActions}>
					<Pressable
						onPress={() => versionsSheetRef.current?.snapToIndex(0)}
						hitSlop={8}
						accessibilityRole="button"
						accessibilityLabel="Version history"
					>
						<Text style={[typography.body, { color: colors.primary }]}>
							History
						</Text>
					</Pressable>
					{editing ? (
						<Pressable
							onPress={() => void handleSave()}
							disabled={saving}
							hitSlop={8}
							accessibilityRole="button"
							accessibilityLabel="Save changes"
						>
							<Text
								style={[
									typography.body,
									{ color: colors.primary, fontWeight: "700", opacity: saving ? 0.6 : 1 },
								]}
							>
								{saving ? "Saving" : "Save"}
							</Text>
						</Pressable>
					) : (
						<Pressable
							onPress={startEditing}
							hitSlop={8}
							accessibilityRole="button"
							accessibilityLabel="Edit artifact"
						>
							<Text style={[typography.body, { color: colors.primary }]}>Edit</Text>
						</Pressable>
					)}
				</View>
			</View>

			<ScrollView
				contentContainerStyle={[
					styles.scroll,
					{ paddingBottom: Math.max(insets.bottom, Spacing.xl) + 90 },
				]}
			>
				{viewingVersion ? (
					<View
						style={[
							styles.versionBanner,
							{ backgroundColor: colors.muted, borderColor: colors.border },
						]}
					>
						<Text style={[typography.meta, { color: colors.mutedForeground, flex: 1 }]}>
							Viewing version {viewingVersion.version} of {artifact.version}
						</Text>
						<Pressable
							onPress={() => void handleRestore()}
							accessibilityRole="button"
							accessibilityLabel={`Restore version ${viewingVersion.version}`}
						>
							<Text style={[typography.uiLabel, { color: colors.primary, fontWeight: "700" }]}>
								Restore
							</Text>
						</Pressable>
						<Pressable
							onPress={() => setViewingVersion(null)}
							accessibilityRole="button"
							accessibilityLabel="Back to current version"
						>
							<Text style={[typography.uiLabel, { color: colors.primary }]}>
								Current
							</Text>
						</Pressable>
					</View>
				) : null}

				{editing ? (
					<>
						<TextInput
							value={editTitle}
							onChangeText={setEditTitle}
							placeholder="Title"
							placeholderTextColor={colors.mutedForeground}
							maxLength={200}
							style={[styles.input, typography.titleSmall, { color: colors.foreground, borderColor: colors.border }]}
						/>
						<TextInput
							value={editContent}
							onChangeText={setEditContent}
							placeholder="Content"
							placeholderTextColor={colors.mutedForeground}
							multiline
							style={[styles.input, styles.multiline, typography.body, { color: colors.foreground, borderColor: colors.border }]}
						/>
					</>
				) : (
					<>
						<Text style={[typography.h1, { color: colors.foreground }]}>
							{artifact.title}
						</Text>
						<Text
							style={[
								typography.meta,
								{ color: colors.mutedForeground, marginTop: Spacing.xs },
							]}
						>
							{artifact.kind} · v{shownVersion} · updated {formatDate(artifact.updated_at)}
						</Text>
						{artifact.tags.length > 0 ? (
							<Text style={[typography.meta, { color: colors.mutedForeground, marginTop: Spacing.xs }]}>
								{artifact.tags.join(", ")}
							</Text>
						) : null}
						<View style={styles.body}>
							<ArtifactBody artifact={{ ...artifact, content: shownContent }} />
						</View>
					</>
				)}
			</ScrollView>

			<View
				style={[
					styles.footer,
					{ paddingBottom: Math.max(insets.bottom, Spacing.md), borderColor: colors.border },
				]}
			>
				<Pressable
					onPress={handleDelete}
					style={({ pressed }) => [
						styles.deleteButton,
						{ opacity: pressed ? 0.7 : 1 },
					]}
					accessibilityRole="button"
					accessibilityLabel="Delete artifact"
				>
					<Text style={[typography.uiLabel, { color: colors.destructive }]}>
						Delete
					</Text>
				</Pressable>
			</View>

			<Sheet ref={versionsSheetRef} snapPoints={["60%"]}>
				<SheetView>
					<Text
						style={[
							typography.titleSmall,
							{ color: colors.foreground, marginBottom: Spacing.md },
						]}
					>
						Version history
					</Text>
					<SheetScrollView>
						{versions.map((v) => (
							<Pressable
								key={v.version}
								onPress={() => void handleViewVersion(v.version)}
								style={({ pressed }) => [
									styles.versionRow,
									{
										backgroundColor: colors.card,
										borderColor: colors.border,
										opacity: pressed ? 0.7 : 1,
									},
								]}
								accessibilityRole="button"
								accessibilityLabel={`View version ${v.version}`}
							>
								<Text
									style={[
										typography.body,
										{
											color: colors.foreground,
											fontWeight: v.version === artifact.version ? "700" : "400",
										},
									]}
								>
									Version {v.version}
									{v.version === artifact.version ? " (current)" : ""}
								</Text>
								<Text style={[typography.meta, { color: colors.mutedForeground }]}>
									{formatDate(v.created_at)} · {(v.size_bytes / 1024).toFixed(1)} KB
								</Text>
							</Pressable>
						))}
						{versions.length === 0 ? (
							<Text style={[typography.body, { color: colors.mutedForeground }]}>
								No versions found.
							</Text>
						) : null}
					</SheetScrollView>
				</SheetView>
			</Sheet>
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
	},
	header: {
		flexDirection: "row",
		alignItems: "center",
		justifyContent: "space-between",
		paddingHorizontal: Spacing.xl,
		paddingBottom: Spacing.md,
	},
	headerActions: {
		flexDirection: "row",
		gap: Spacing.lg,
	},
	scroll: {
		paddingHorizontal: Spacing.xl,
		paddingTop: Spacing.sm,
		gap: Spacing.md,
	},
	body: {
		marginTop: Spacing.sm,
	},
	versionBanner: {
		flexDirection: "row",
		alignItems: "center",
		gap: Spacing.md,
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: SemanticSpacing.radiusInput,
		padding: Spacing.md,
	},
	input: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: SemanticSpacing.radiusInput,
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.md,
		minHeight: SemanticSpacing.inputHeight,
	},
	multiline: {
		minHeight: 320,
		textAlignVertical: "top",
		marginTop: Spacing.md,
	},
	footer: {
		borderTopWidth: StyleSheet.hairlineWidth,
		paddingHorizontal: Spacing.xl,
		paddingTop: Spacing.md,
		alignItems: "center",
	},
	deleteButton: {
		paddingVertical: Spacing.sm,
		paddingHorizontal: Spacing.lg,
	},
	button: {
		borderRadius: SemanticSpacing.radiusModal,
		minHeight: SemanticSpacing.buttonHeightLg,
		justifyContent: "center",
		alignItems: "center",
		paddingHorizontal: Spacing.xl,
	},
	versionRow: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: SemanticSpacing.radiusInput,
		padding: Spacing.md,
		marginBottom: Spacing.sm,
		gap: Spacing.xs,
	},
});
