import BottomSheet from "@gorhom/bottom-sheet";
import * as Haptics from "expo-haptics";
import * as Linking from "expo-linking";
import { forwardRef, useMemo, useState } from "react";
import {
	ActivityIndicator,
	Pressable,
	StyleSheet,
	Text,
	View,
} from "react-native";
import { Sheet, SheetTextInput, SheetView } from "@/components/ui/sheet";
import {
	KeyStoreError,
	getProvider,
	setProviderKey,
	type ProviderId,
} from "@/providers";
import { Spacing, typography, useTheme } from "@/theme";

interface KeySheetProps {
	providerId: ProviderId;
	onSaved: () => void;
	onClose?: () => void;
}

const HELP: Record<ProviderId, { steps: string; url: string; linkLabel: string }> = {
	anthropic: {
		steps:
			"Open the Anthropic Console, go to API keys, and create a key. It starts with sk-ant-.",
		url: "https://console.anthropic.com/settings/keys",
		linkLabel: "Open console.anthropic.com",
	},
	openai: {
		steps:
			"Open the OpenAI dashboard, go to API keys, and create a key. It starts with sk-.",
		url: "https://platform.openai.com/api-keys",
		linkLabel: "Open platform.openai.com",
	},
	node: {
		steps: "The node provider does not use an API key.",
		url: "",
		linkLabel: "",
	},
};

export const KeySheet = forwardRef<BottomSheet, KeySheetProps>(
	function KeySheet({ providerId, onSaved, onClose }, ref) {
		const { colors } = useTheme();
		const [key, setKey] = useState("");
		const [showKey, setShowKey] = useState(false);
		const [saving, setSaving] = useState(false);
		const [error, setError] = useState<string | null>(null);

		const snapPoints = useMemo(() => ["70%"], []);
		const provider = getProvider(providerId);
		const help = HELP[providerId];

		async function handleSave() {
			const trimmed = key.trim();
			if (!trimmed || saving) return;
			setSaving(true);
			setError(null);
			try {
				// Validate before persisting: the key only lands in SecureStore
				// after the provider accepts it.
				await provider.validateKey(trimmed);
				await setProviderKey(providerId, trimmed);
				Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
				setKey("");
				onSaved();
			} catch (err) {
				const message =
					err instanceof KeyStoreError || err instanceof Error
						? err.message
						: "Could not save the key. Try again.";
				setError(message);
				Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
			} finally {
				setSaving(false);
			}
		}

		return (
			<Sheet ref={ref} snapPoints={snapPoints} onClose={onClose}>
				<SheetView>
					<View style={styles.content}>
						<Text style={[typography.h2, { color: colors.foreground }]}>
							Add your {provider.label} key
						</Text>
						<Text style={[typography.body, { color: colors.mutedForeground, marginTop: 8 }]}>
							{help.steps}
						</Text>
						{help.url ? (
							<Pressable
								onPress={() => {
									void Linking.openURL(help.url).catch(() => undefined);
								}}
								style={styles.linkRow}
								accessibilityRole="link"
							>
								<Text style={[typography.body, { color: colors.primary, fontWeight: "600" }]}>
									{help.linkLabel}
								</Text>
							</Pressable>
						) : null}

						<SheetTextInput
							value={key}
							onChangeText={(v) => {
								setKey(v);
								if (error) setError(null);
							}}
							placeholder="Paste API key"
							secureTextEntry={!showKey}
							autoCapitalize="none"
							autoCorrect={false}
							style={[
								styles.input,
								typography.body,
								{ color: colors.foreground, borderColor: colors.border },
							]}
						/>
						<Pressable
							onPress={() => setShowKey((s) => !s)}
							hitSlop={8}
							style={styles.showRow}
							accessibilityRole="button"
							accessibilityLabel={showKey ? "Hide key" : "Show key"}
						>
							<Text style={[typography.meta, { color: colors.primary }]}>
								{showKey ? "Hide key" : "Show key"}
							</Text>
						</Pressable>

						<Text style={[typography.meta, { color: colors.mutedForeground, marginTop: 4 }]}>
							Your key is stored only in this phone's secure storage and sent
							directly to {provider.label}. It is never logged or shared.
						</Text>

						{error ? (
							<Text style={[typography.body, { color: colors.destructive, marginTop: 12 }]}>
								{error}
							</Text>
						) : null}

						<Pressable
							onPress={handleSave}
							disabled={key.trim().length === 0 || saving}
							style={[
								styles.saveButton,
								{
									backgroundColor:
										key.trim().length === 0 || saving ? colors.muted : colors.primary,
								},
							]}
							accessibilityRole="button"
							accessibilityLabel="Validate and save key"
						>
							{saving ? (
								<ActivityIndicator size="small" color={colors.primaryForeground} />
							) : (
								<Text
									style={[
										typography.uiLabel,
										{
											color:
												key.trim().length === 0
													? colors.mutedForeground
													: colors.primaryForeground,
											fontWeight: "700",
										},
									]}
								>
									Validate and save
								</Text>
							)}
						</Pressable>
					</View>
				</SheetView>
			</Sheet>
		);
	},
);

const styles = StyleSheet.create({
	content: {
		paddingHorizontal: Spacing.lg,
		paddingBottom: Spacing.lg,
	},
	linkRow: {
		marginTop: 8,
		alignSelf: "flex-start",
	},
	input: {
		marginTop: 16,
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: 12,
		paddingHorizontal: Spacing.md,
		paddingVertical: 12,
		fontSize: 16,
	},
	showRow: {
		marginTop: 8,
		alignSelf: "flex-end",
	},
	saveButton: {
		marginTop: 16,
		borderRadius: 14,
		paddingVertical: 14,
		alignItems: "center",
	},
});
