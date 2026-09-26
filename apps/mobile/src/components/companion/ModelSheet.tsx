import BottomSheet from "@gorhom/bottom-sheet";
import * as Haptics from "expo-haptics";
import { forwardRef, useMemo } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Sheet, SheetView } from "@/components/ui/sheet";
import {
	KEY_PROVIDERS,
	getProvider,
	type ProviderId,
} from "@/providers";
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

		return (
			<Sheet ref={ref} snapPoints={snapPoints}>
				<SheetView>
					<Text style={[typography.h2, { color: colors.foreground, paddingHorizontal: Spacing.lg, paddingBottom: Spacing.md }]}>
						Model
					</Text>
					{providers.map((id) => {
						const provider = getProvider(id);
						const hasKey = id === "node" || keyedProviders.includes(id);
						return (
							<View key={id} style={styles.section}>
								<Text
									style={[
										typography.uiLabel,
										{ color: colors.mutedForeground, paddingHorizontal: Spacing.lg, fontWeight: "700" },
									]}
								>
									{provider.label}
								</Text>
								{hasKey ? (
									provider.models.map((model) => {
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
									})
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
});
