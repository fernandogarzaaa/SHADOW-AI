import * as Clipboard from "expo-clipboard";
import Constants from "expo-constants";
import * as Haptics from "expo-haptics";
import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import * as SecureStore from "expo-secure-store";
import { SettingsGroup, SettingsRow, SettingsScreen } from "@/components/settings/primitives";
import { getProvider } from "@/providers";
import { useChatStore } from "@/stores/useChatStore";
import { useConnectionStore } from "@/stores/useConnectionStore";
import { useProviderStore } from "@/stores/useProviderStore";
import { Spacing, typography, useTheme } from "@/theme";

const PUSH_REGISTERED_KEY = "shadow_push_registered";

function shortenId(id: string): string {
	if (id.length <= 20) return id;
	return `${id.slice(0, 8)}...${id.slice(-4)}`;
}

/**
 * Support info: the real facts a support conversation needs, copied
 * straight from the app's stores. Nothing leaves the phone unless the
 * user shares it themselves.
 */
export default function SupportScreen() {
	const { colors } = useTheme();
	const { nodeUrl, deviceId, deviceName, isPaired } = useConnectionStore();
	const { providerId, modelId } = useProviderStore();
	const threadCount = useChatStore((s) => s.threads.length);
	const [pushStatus, setPushStatus] = useState("Checking");

	useEffect(() => {
		let active = true;
		SecureStore.getItemAsync(PUSH_REGISTERED_KEY)
			.then((value) => {
				if (active) {
					setPushStatus(value === "true" ? "Registered" : "Not registered");
				}
			})
			.catch(() => {
				if (active) setPushStatus("Not registered");
			});
		return () => {
			active = false;
		};
	}, [isPaired]);

	const provider = getProvider(providerId);
	const modelLabel =
		provider.models.find((m) => m.id === modelId)?.label ?? modelId;

	const copyAll = async () => {
		const summary = [
			`SHADOW ${Constants.expoConfig?.version ?? "1.0.0"}`,
			`Device: ${deviceName ?? "Unknown"} (${deviceId ? shortenId(deviceId) : "unknown id"})`,
			`Node: ${isPaired ? nodeUrl ?? "linked" : "not linked"}`,
			`Model: ${provider.label} ${modelLabel}`,
			`Chats: ${threadCount}`,
			`Push: ${pushStatus}`,
		].join("\n");
		await Clipboard.setStringAsync(summary);
		await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
	};

	return (
		<SettingsScreen title="Support" showClose={false}>
			<Text
				style={[
					typography.body,
					{ color: colors.mutedForeground, marginBottom: Spacing.md },
				]}
			>
				If something goes wrong, share these details with whoever is
				helping you. They never leave this phone unless you copy them.
			</Text>

			<SettingsGroup>
				<SettingsRow
					title="App version"
					value={Constants.expoConfig?.version ?? "1.0.0"}
				/>
				<SettingsRow title="Device" value={deviceName ?? "Unknown"} />
				<SettingsRow
					title="Device ID"
					value={deviceId ? shortenId(deviceId) : "Unknown"}
				/>
				<SettingsRow
					title="Node"
					value={isPaired ? (nodeUrl ?? "Linked") : "Not linked"}
				/>
				<SettingsRow
					title="Model"
					value={`${provider.label} · ${modelLabel}`}
				/>
				<SettingsRow title="Chats" value={`${threadCount}`} />
				<SettingsRow title="Push notifications" value={pushStatus} />
			</SettingsGroup>

			<Pressable
				onPress={() => void copyAll()}
				style={({ pressed }) => [
					styles.copyButton,
					{
						backgroundColor: colors.card,
						borderColor: colors.border,
						opacity: pressed ? 0.6 : 1,
					},
				]}
				accessibilityRole="button"
				accessibilityLabel="Copy support details"
			>
				<Text
					style={[
						typography.uiLabel,
						{ color: colors.foreground, fontWeight: "600" },
					]}
				>
					Copy support details
				</Text>
			</Pressable>
		</SettingsScreen>
	);
}

const styles = StyleSheet.create({
	copyButton: {
		marginTop: Spacing.lg,
		borderRadius: 999,
		borderWidth: StyleSheet.hairlineWidth,
		minHeight: 44,
		alignItems: "center",
		justifyContent: "center",
		paddingHorizontal: Spacing.lg,
	},
});
