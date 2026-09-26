import BottomSheet from "@gorhom/bottom-sheet";
import * as Haptics from "expo-haptics";
import { forwardRef, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { Sheet, SheetTextInput, SheetView } from "@/components/ui/sheet";
import {
	KEY_PROVIDERS,
	getProvider,
	getProviderKey,
	type ModelInfo,
	type ProviderId,
} from "@/providers";
import { getModels } from "@/providers/modelCatalog";
import { useConnectionStore } from "@/stores/useConnectionStore";
import { useProviderStore } from "@/stores/useProviderStore";
import { Spacing, typography, useTheme } from "@/theme";

interface ModelSheetProps {
	onPick: (providerId: ProviderId, modelId: string) => void;
	onAddKey: (providerId: ProviderId) => void;
}

/**
 * Provider/model switcher. Keyed providers without a saved key offer
 * "Add key" instead of models. The node provider appears only when a
 * node is linked.
 */
export const ModelSheet = forwardRef<BottomSheet, ModelSheetProps>(
	function ModelSheet({ onPick, onAddKey }, ref) {
		const { colors } = useTheme();
		const { providerId: activeProvider, modelId: activeModel, keyedProviders } =
			useProviderStore();
		const isPaired = useConnectionStore((s) => s.isPaired);

		const snapPoints = useMemo(() => ["70%", "92%"], []);
		const providers: ProviderId[] = useMemo(
			() => [...KEY_PROVIDERS, ...(isPaired ? (["node"] as ProviderId[]) : [])],
			[isPaired],
		);

		// Live catalogs for providers that expose listModels (OpenRouter,
		// OpenCode). Falls back to the static list on any failure.
		const [catalogs, setCatalogs] = useState<
			Partial<Record<ProviderId, { models: ModelInfo[]; live: boolean }>>
		>({});
		const [loadingCatalogs, setLoadingCatalogs] = useState<ProviderId[]>([]);
		// Manual model id for the custom endpoint (its model list may be
		// empty when the catalog is unreachable).
		const [customModelId, setCustomModelId] = useState("");

		useEffect(() => {
			let cancelled = false;
			(async () => {
				for (const id of keyedProviders) {
					if (cancelled || catalogs[id] || loadingCatalogs.includes(id)) {
						continue;
					}
					if (!getProvider(id).listModels) {
						continue;
					}
					setLoadingCatalogs((prev) => (prev.includes(id) ? prev : [...prev, id]));
					try {
						const key = await getProviderKey(id);
						if (!key) {
							continue;
						}
						const result = await getModels(getProvider(id), key);
						if (!cancelled) {
							setCatalogs((prev) => ({ ...prev, [id]: result }));
						}
					} finally {
						if (!cancelled) {
							setLoadingCatalogs((prev) => prev.filter((p) => p !== id));
						}
					}
				}
			})();
			return () => {
				cancelled = true;
			};
		}, [keyedProviders]);

		return (
			<Sheet ref={ref} snapPoints={snapPoints}>
				<SheetView>
					<Text style={[typography.h2, { color: colors.foreground, paddingHorizontal: Spacing.lg, paddingBottom: Spacing.md }]}>
						Model
					</Text>
					{providers.map((id) => {
						const provider = getProvider(id);
						const hasKey = id === "node" || keyedProviders.includes(id);
						const catalog = catalogs[id];
						const models = catalog?.models ?? provider.models;
						const isLive = catalog?.live ?? false;
						const isLoading = loadingCatalogs.includes(id);
						return (
							<View key={id} style={styles.section}>
								<View style={styles.sectionHeader}>
									<Text
										style={[
											typography.uiLabel,
											{ color: colors.mutedForeground, paddingHorizontal: Spacing.lg, fontWeight: "700" },
										]}
									>
										{provider.label}
									</Text>
									{isLoading ? (
										<ActivityIndicator size="small" color={colors.mutedForeground} />
									) : isLive ? (
										<Text style={[typography.meta, { color: colors.primary, fontWeight: "600" }]}>
											{models.length} models, updated today
										</Text>
									) : null}
								</View>
								{hasKey ? (
									<>
										{id === "custom" ? (
											<View style={styles.customRow}>
												<SheetTextInput
													value={customModelId}
													onChangeText={setCustomModelId}
													placeholder="Model id, e.g. llama3.1"
													autoCapitalize="none"
													autoCorrect={false}
													style={[
														styles.customInput,
														typography.body,
														{ color: colors.foreground, borderColor: colors.border },
													]}
												/>
												<Pressable
													onPress={() => {
														const trimmed = customModelId.trim();
														if (!trimmed) return;
														Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
														onPick(id, trimmed);
													}}
													style={({ pressed }) => [
														styles.useButton,
														{ backgroundColor: colors.primary, opacity: pressed ? 0.7 : 1 },
													]}
													accessibilityRole="button"
													accessibilityLabel="Use custom model id"
												>
													<Text style={[typography.uiLabel, { color: colors.primaryForeground }]}>
														Use
													</Text>
												</Pressable>
											</View>
										) : null}
										{models.map((model) => {
										const active = id === activeProvider && model.id === activeModel;
										return (
											<Pressable
												key={model.id}
												onPress={() => {
													Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
													onPick(id, model.id);
												}}
												style={({ pressed }) => [
													styles.row,
													{ opacity: pressed ? 0.6 : 1 },
												]}
												accessibilityRole="button"
												accessibilityLabel={`Use ${model.label}`}
											>
												<View style={styles.rowText}>
													<Text style={[typography.body, { color: colors.foreground, fontWeight: active ? "700" : "400" }]}>
														{model.label}
													</Text>
													<Text style={[typography.meta, { color: colors.mutedForeground }]}>
														{model.blurb}
													</Text>
												</View>
												{active ? (
													<Text style={[typography.uiLabel, { color: colors.primary, fontWeight: "700" }]}>
														Active
													</Text>
												) : null}
											</Pressable>
										);
									})}
									</>
								) : (
									<Pressable
										onPress={() => {
											Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
											onAddKey(id);
										}}
										style={({ pressed }) => [
											styles.row,
											{ opacity: pressed ? 0.6 : 1 },
										]}
										accessibilityRole="button"
										accessibilityLabel={`Add ${provider.label} API key`}
									>
										<Text style={[typography.body, { color: colors.primary, fontWeight: "600" }]}>
											Add API key
										</Text>
									</Pressable>
								)}
							</View>
						);
					})}
				</SheetView>
			</Sheet>
		);
	},
);

const styles = StyleSheet.create({
	section: {
		marginBottom: Spacing.md,
	},
	sectionHeader: {
		flexDirection: "row",
		alignItems: "center",
		justifyContent: "space-between",
		paddingRight: Spacing.lg,
		marginBottom: 2,
	},
	row: {
		flexDirection: "row",
		alignItems: "center",
		gap: Spacing.sm,
		paddingHorizontal: Spacing.lg,
		paddingVertical: Spacing.md,
	},
	rowText: {
		flex: 1,
		gap: 2,
	},
	customRow: {
		flexDirection: "row",
		alignItems: "center",
		gap: Spacing.sm,
		paddingHorizontal: Spacing.lg,
		paddingVertical: Spacing.sm,
	},
	customInput: {
		flex: 1,
		borderWidth: 1,
		borderRadius: 10,
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.sm,
	},
	useButton: {
		borderRadius: 10,
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.sm,
	},
});
