import { Alert } from "react-native";
import {
	SettingsGroup,
	SettingsRow,
	SettingsScreen,
} from "@/components/settings";
import { settingsApi } from "@/api";
import { useConnectionStore } from "@/stores/useConnectionStore";

function getConnectionType(url: string | null): {
	type: string;
	label: string;
} {
	if (!url) return { type: "unknown", label: "Not connected" };

	const isTailscale = url.includes(".ts.net") || /100\.\d+\.\d+\.\d+/.test(url);
	const isCloudflare =
		url.includes(".trycloudflare.com") || url.includes("cloudflare");

	if (isTailscale) return { type: "tailscale", label: "via Tailscale" };
	if (isCloudflare) return { type: "cloudflare", label: "via Cloudflare" };
	return { type: "local", label: "Local Network" };
}

export default function ConnectionScreen() {
	const { serverUrl } = useConnectionStore();

	const serverHost = serverUrl ? new URL(serverUrl).host : "Not connected";
	const connectionInfo = getConnectionType(serverUrl);

	const handleRestartOpenCode = async () => {
		Alert.alert(
			"Restart backend",
			"This will restart the node server. Continue?",
			[
				{ text: "Cancel", style: "cancel" },
				{
					text: "Restart",
					onPress: async () => {
						try {
							await settingsApi.restartOpenCode();
							Alert.alert("Success", "Node is restarting...");
						} catch (err) {
							Alert.alert(
								"Error",
								err instanceof Error ? err.message : "Failed to restart"
							);
						}
					},
				},
			]
		);
	};

	return (
		<SettingsScreen title="Connection">
			<SettingsGroup footer={`Connected ${connectionInfo.label}`}>
				<SettingsRow
					title="Server"
					value={serverHost}
				/>
			</SettingsGroup>

			<SettingsGroup>
				<SettingsRow
					title="Restart backend"
					onPress={handleRestartOpenCode}
				/>
			</SettingsGroup>
		</SettingsScreen>
	);
}
