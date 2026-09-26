import BottomSheet from "@gorhom/bottom-sheet";
import * as Haptics from "expo-haptics";
import * as Linking from "expo-linking";
import { forwardRef, useEffect, useMemo, useState } from "react";
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
	getCustomBaseUrl,
	getProvider,
	setCustomBaseUrl,
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
	openrouter: {
		steps:
			"Open your OpenRouter account settings, go to API keys, and create a key. It starts with sk-or-.",
		url: "https://openrouter.ai/settings/keys",
		linkLabel: "Open openrouter.ai",
	},
	opencode: {
		steps:
			"Sign in at opencode.ai/auth and copy your Zen API key.",
		url: "https://opencode.ai/auth",
		linkLabel: "Open opencode.ai/auth",
	},
	xai: {
		steps:
			"Open the xAI console, go to API keys, and create a key.",
		url: "https://console.x.ai",
		linkLabel: "Open console.x.ai",
	},
	gemini: {
		steps:
			"Open Google AI Studio, create an API key, and paste it here.",
		url: "https://aistudio.google.com/apikey",
		linkLabel: "Open aistudio.google.com",
	},
	deepseek: {
		steps:
			"Open the DeepSeek platform, go to API keys, and create a key.",
		url: "https://platform.deepseek.com/api_keys",
		linkLabel: "Open platform.deepseek.com",
	},
	mistral: {
		steps:
			"Open the Mistral console, go to API keys, and create a key.",
		url: "https://console.mistral.ai/api-keys",
		linkLabel: "Open console.mistral.ai",
	},
	groq: {
		steps:
			"Open the Groq console, go to API keys, and create a key.",
		url: "https://console.groq.com/keys",
		linkLabel: "Open console.groq.com",
	},
	together: {
		steps:
			"Open Together AI settings, go to API keys, and create a key.",
		url: "https://api.together.xyz/settings/api-keys",
		linkLabel: "Open api.together.xyz",
	},
	cohere: {
		steps:
			"Open the Cohere dashboard, go to API keys, and create a key.",
		url: "https://dashboard.cohere.com/api-keys",
		linkLabel: "Open dashboard.cohere.com",
	},
	custom: {
		steps:
			"Enter the base URL of any OpenAI-compatible server, then its API key. Use the /v1 root for servers like Ollama or LM Studio.",
		url: "",
		linkLabel: "",
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
		const [baseUrl, setBaseUrl] = useState("");
		const [showKey, setShowKey] = useState(false);
		const [saving, setSaving] = useState(false);
		const [error, setError] = useState<string | null>(null);
		const isCustom = providerId === "custom";

		// Pre-fill the stored base URL when editing the custom endpoint.
		useEffect(() => {
			if (isCustom) {
				void getCustomBaseUrl().then((url) => {
					if (url) {
						setBaseUrl(url);
					}
				});
			}
		}, [isCustom]);

		const snapPoints = useMemo(() => ["70%"], []);
		const provider = getProvider(providerId);
		const help = HELP[providerId];

		async function handleSave() {
			const trimmed = key.trim();
			if (!trimmed || saving) return;
			if (isCustom && baseUrl.trim().length === 0) return;
			setSaving(true);
			setError(null);
			try {
				// Custom endpoints need a base URL before the key can be
				// validated. The URL is not secret, so it persists even if
				// key validation fails below.
				if (isCustom) {
					await setCustomBaseUrl(baseUrl);
				}
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

						{isCustom ? (
							<SheetTextInput
								value={baseUrl}
								onChangeText={(v) => {
									setBaseUrl(v);
									if (error) setError(null);
								}}
								placeholder="Base URL, e.g. http://192.168.1.10:11434/v1"
								autoCapitalize="none"
								autoCorrect={false}
								keyboardType="url"
								style={[
									styles.input,
									typography.body,
									{ color: colors.foreground, borderColor: colors.border, marginBottom: 12 },
								]}
							/>
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
							disabled={key.trim().length === 0 || (isCustom && baseUrl.trim().length === 0) || saving}
							style={[
								styles.saveButton,
								{
									backgroundColor:
										key.trim().length === 0 || (isCustom && baseUrl.trim().length === 0) || saving ? colors.muted : colors.primary,
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
												key.trim().length === 0 || (isCustom && baseUrl.trim().length === 0)
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
