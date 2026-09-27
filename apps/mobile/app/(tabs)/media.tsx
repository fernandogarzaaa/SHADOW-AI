import * as Haptics from "expo-haptics";
import { useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import {
	ActivityIndicator,
	Alert,
	Dimensions,
	Modal,
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
	deleteMedia,
	generateMedia,
	getMediaCapabilities,
	listMedia,
	ShadowApiError,
	type GeneratedMedia,
	type MediaSize,
} from "@/api/shadow";
import { MediaFileImage } from "@/components/media/MediaFileImage";
import { useConnectionStore } from "@/stores/useConnectionStore";
import { SemanticSpacing, Spacing, typography, useTheme } from "@/theme";

const SIZES: MediaSize[] = ["1024x1024", "1792x1024", "1024x1792"];

function formatDate(epochSeconds: number): string {
	const d = new Date(epochSeconds * 1000);
	if (Number.isNaN(d.getTime())) return "";
	return d.toLocaleString(undefined, {
		month: "short",
		day: "numeric",
		hour: "numeric",
		minute: "2-digit",
	});
}

/**
 * Media tab: node-generated image gallery. Prompt form with size picker,
 * tap an image for full screen, long-press or the viewer to delete.
 * When the node has no image provider, the tab explains that plainly.
 */
export default function MediaScreen() {
	const { colors } = useTheme();
	const insets = useSafeAreaInsets();
	const isPaired = useConnectionStore((s) => s.isPaired);

	const [items, setItems] = useState<GeneratedMedia[]>([]);
	const [total, setTotal] = useState(0);
	const [loading, setLoading] = useState(true);
	const [refreshing, setRefreshing] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [generateAvailable, setGenerateAvailable] = useState<boolean | null>(null);

	const [prompt, setPrompt] = useState("");
	const [size, setSize] = useState<MediaSize>("1024x1024");
	const [generating, setGenerating] = useState(false);
	const [viewer, setViewer] = useState<GeneratedMedia | null>(null);

	const refresh = useCallback(async () => {
		if (!isPaired) {
			setLoading(false);
			return;
		}
		setError(null);
		try {
			const [caps, res] = await Promise.all([
				getMediaCapabilities().catch(() => null),
				listMedia(60, 0),
			]);
			setGenerateAvailable(caps ? caps.generate.available : null);
			const sorted = [...res.items].sort(
				(a, b) =>
					new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
			);
			setItems(sorted);
			setTotal(res.total);
		} catch (e) {
			setError(
				e instanceof ShadowApiError ? e.message : "Could not load images.",
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

	async function handleGenerate() {
		const p = prompt.trim();
		if (!p) {
			Alert.alert("Missing prompt", "Describe the image you want first.");
			return;
		}
		setGenerating(true);
		try {
			await generateMedia(p, size);
			void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
			setPrompt("");
			setRefreshing(true);
			await refresh();
		} catch (e) {
			if (e instanceof ShadowApiError && e.status === 503) {
				Alert.alert(
					"Image generation unavailable",
					"Your node does not have an image provider configured yet. Add one in the node settings to enable this.",
				);
				setGenerateAvailable(false);
			} else {
				Alert.alert(
					"Could not generate",
					e instanceof ShadowApiError ? e.message : "Try again.",
				);
			}
		} finally {
			setGenerating(false);
		}
	}

	function handleDelete(item: GeneratedMedia) {
		Alert.alert(
			"Delete image?",
			`"${item.prompt.slice(0, 60)}${item.prompt.length > 60 ? "..." : ""}" will be removed from the node.`,
			[
				{ text: "Cancel", style: "cancel" },
				{
					text: "Delete",
					style: "destructive",
					onPress: async () => {
						try {
							await deleteMedia(item.id);
							void Haptics.notificationAsync(
								Haptics.NotificationFeedbackType.Success,
							);
							setViewer(null);
							setRefreshing(true);
							await refresh();
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

	const tile = (Dimensions.get("window").width - Spacing.xl * 2 - Spacing.sm * 2) / 3;

	return (
		<View style={[styles.container, { paddingTop: insets.top }]}>
			<Text style={[typography.h1, { color: colors.foreground, paddingHorizontal: Spacing.xl }]}>
				Media
			</Text>

			{generateAvailable === false ? (
				<View
					style={[
						styles.notice,
						{ backgroundColor: colors.muted, borderColor: colors.border, marginHorizontal: Spacing.xl },
					]}
				>
					<Text style={[typography.body, { color: colors.mutedForeground }]}>
						Image generation needs a provider. Configure one on your SHADOW
						node to start creating images here.
					</Text>
				</View>
			) : (
				<View style={[styles.form, { paddingHorizontal: Spacing.xl }]}>
					<TextInput
						style={[
							styles.input,
							typography.body,
							{
								color: colors.foreground,
								borderColor: colors.border,
								backgroundColor: colors.card,
							},
						]}
						placeholder="Describe an image..."
						placeholderTextColor={colors.mutedForeground}
						value={prompt}
						onChangeText={setPrompt}
						multiline
						maxLength={1000}
						editable={!generating}
						accessibilityLabel="Image prompt"
					/>
					<View style={styles.sizeRow}>
						{SIZES.map((s) => (
							<Pressable
								key={s}
								onPress={() => setSize(s)}
								style={[
									styles.sizeChip,
									{
										backgroundColor: size === s ? colors.foreground : colors.card,
										borderColor: colors.border,
									},
								]}
								accessibilityRole="button"
								accessibilityState={{ selected: size === s }}
								accessibilityLabel={`Size ${s}`}
							>
								<Text
									style={[
										typography.uiLabel,
										{
											color: size === s ? colors.background : colors.foreground,
											fontWeight: "700",
										},
									]}
								>
									{s}
								</Text>
							</Pressable>
						))}
					</View>
					<Pressable
						onPress={() => void handleGenerate()}
						disabled={generating || !prompt.trim()}
						style={({ pressed }) => [
							styles.button,
							{
								backgroundColor: colors.primary,
								opacity: pressed || generating || !prompt.trim() ? 0.7 : 1,
							},
						]}
						accessibilityRole="button"
						accessibilityLabel="Generate image"
					>
						{generating ? (
							<ActivityIndicator color={colors.primaryForeground} />
						) : (
							<Text
								style={[
									typography.uiLabel,
									{ color: colors.primaryForeground, fontWeight: "700" },
								]}
							>
								Generate
							</Text>
						)}
					</Pressable>
				</View>
			)}

			{loading ? (
				<ActivityIndicator
					style={styles.center}
					color={colors.primary}
					accessibilityLabel="Loading images"
				/>
			) : error && items.length === 0 ? (
				<View style={styles.center}>
					<Text
						style={[typography.body, { color: colors.destructive, textAlign: "center" }]}
					>
						{error}
					</Text>
				</View>
			) : (
				<ScrollView
					contentContainerStyle={[
						styles.grid,
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
							No images yet. Describe one above to generate your first.
						</Text>
					) : (
						items.map((item) => (
							<Pressable
								key={item.id}
								onPress={() => {
									void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
									setViewer(item);
								}}
								onLongPress={() => handleDelete(item)}
								style={{ width: tile, height: tile }}
								accessibilityRole="button"
								accessibilityLabel={`View image: ${item.prompt}`}
								accessibilityHint="Long press to delete"
							>
								<MediaFileImage
									mediaId={item.id}
									style={[styles.thumb, { width: tile, height: tile }]}
									accessibilityLabel={item.prompt}
								/>
							</Pressable>
						))
					)}
					{total > items.length ? (
						<Text
							style={[
								typography.meta,
								{ color: colors.mutedForeground, textAlign: "center", width: "100%" },
							]}
						>
							Showing {items.length} of {total}
						</Text>
					) : null}
				</ScrollView>
			)}

			<Modal
				visible={viewer !== null}
				animationType="fade"
				presentationStyle="fullScreen"
				onRequestClose={() => setViewer(null)}
			>
				<View style={[styles.viewer, { backgroundColor: "#000000", paddingTop: insets.top }]}>
					{viewer ? (
						<MediaFileImage
							mediaId={viewer.id}
							style={styles.viewerImage}
							accessibilityLabel={viewer.prompt}
						/>
					) : null}
					<Text
						style={[typography.body, { color: "#FFFFFF", padding: Spacing.lg }]}
						numberOfLines={3}
					>
						{viewer?.prompt}
					</Text>
					<Text style={[typography.meta, { color: "#999999", paddingHorizontal: Spacing.lg }]}>
						{viewer ? `${viewer.size} · ${formatDate(viewer.created_at)}` : ""}
					</Text>
					<View style={[styles.viewerActions, { paddingBottom: Math.max(insets.bottom, Spacing.xl) }]}>
						<Pressable
							onPress={() => setViewer(null)}
							style={styles.viewerButton}
							accessibilityRole="button"
							accessibilityLabel="Close viewer"
						>
							<Text style={[typography.uiLabel, { color: "#FFFFFF", fontWeight: "700" }]}>
								Close
							</Text>
						</Pressable>
						<Pressable
							onPress={() => viewer && handleDelete(viewer)}
							style={styles.viewerButton}
							accessibilityRole="button"
							accessibilityLabel="Delete image"
						>
							<Text style={[typography.uiLabel, { color: "#FF6B6B", fontWeight: "700" }]}>
								Delete
							</Text>
						</Pressable>
					</View>
				</View>
			</Modal>
		</View>
	);
}

const styles = StyleSheet.create({
	container: {
		flex: 1,
	},
	notice: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: SemanticSpacing.radiusModal,
		padding: Spacing.lg,
		marginTop: Spacing.md,
	},
	form: {
		gap: Spacing.sm,
		marginTop: Spacing.md,
	},
	input: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: SemanticSpacing.radiusInput,
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.md,
		minHeight: 64,
		maxHeight: 120,
		textAlignVertical: "top",
	},
	sizeRow: {
		flexDirection: "row",
		gap: Spacing.sm,
	},
	sizeChip: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: 999,
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.xs,
	},
	button: {
		borderRadius: SemanticSpacing.radiusModal,
		minHeight: SemanticSpacing.buttonHeightLg,
		justifyContent: "center",
		alignItems: "center",
		paddingHorizontal: Spacing.xl,
	},
	center: {
		flex: 1,
		justifyContent: "center",
		alignItems: "center",
		paddingHorizontal: Spacing.xl,
	},
	grid: {
		flexDirection: "row",
		flexWrap: "wrap",
		gap: Spacing.sm,
		paddingHorizontal: Spacing.xl,
		paddingTop: Spacing.md,
	},
	thumb: {
		borderRadius: 10,
	},
	viewer: {
		flex: 1,
	},
	viewerImage: {
		flex: 1,
		width: "100%",
	},
	viewerActions: {
		flexDirection: "row",
		justifyContent: "space-around",
		paddingTop: Spacing.md,
	},
	viewerButton: {
		paddingVertical: Spacing.md,
		paddingHorizontal: Spacing.xl,
	},
});
