import { useState } from "react";
import { Alert, Pressable, Text, TextInput, View } from "react-native";
import { router } from "expo-router";
import { SettingsScreen } from "@/components/settings/primitives";
import { useConnectionStore } from "@/stores/useConnectionStore";
import { useTheme } from "@/theme";

function isValidNodeUrl(value: string): boolean {
	return value.startsWith("http://") || value.startsWith("https://");
}

export default function NodeUrlScreen() {
	const { colors } = useTheme();
	const { nodeUrl, setNodeUrl } = useConnectionStore();
	const [value, setValue] = useState(nodeUrl ?? "");
	const [error, setError] = useState<string | null>(null);

	const handleSave = async () => {
		const trimmed = value.trim();
		if (!isValidNodeUrl(trimmed)) {
			setError("URL must start with http:// or https://");
			return;
		}
		setError(null);
		try {
			await setNodeUrl(trimmed);
			router.back();
		} catch {
			Alert.alert("Could not save", "Failed to save the node URL. Try again.");
		}
	};

	return (
		<SettingsScreen title="Node URL">
			<View style={{ paddingHorizontal: 16, paddingTop: 16, gap: 12 }}>
				<Text style={{ color: colors.mutedForeground, fontSize: 14 }}>
					The HTTP address of your SHADOW node on the local network.
				</Text>
				<TextInput
					value={value}
					onChangeText={(text) => {
						setValue(text);
						setError(null);
					}}
					placeholder="http://192.168.1.10:8000"
					placeholderTextColor={colors.mutedForeground}
					autoCapitalize="none"
					autoCorrect={false}
					keyboardType="url"
					style={{
						backgroundColor: colors.card,
						borderRadius: 12,
						borderWidth: 1,
						borderColor: error ? colors.destructive : colors.border,
						paddingHorizontal: 14,
						paddingVertical: 12,
						color: colors.foreground,
						fontSize: 15,
					}}
				/>
				{error ? (
					<Text style={{ color: colors.destructive, fontSize: 13 }}>{error}</Text>
				) : null}
				<Pressable
					onPress={() => void handleSave()}
					style={{
						backgroundColor: colors.primary,
						borderRadius: 12,
						paddingVertical: 14,
						alignItems: "center",
					}}
					accessibilityLabel="Save node URL"
				>
					<Text
						style={{
							color: colors.primaryForeground,
							fontSize: 15,
							fontWeight: "600",
						}}
					>
						Save
					</Text>
				</Pressable>
			</View>
		</SettingsScreen>
	);
}
