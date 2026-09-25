import { useEffect, useState } from "react";
import { Alert } from "react-native";
import * as Clipboard from "expo-clipboard";
import Constants from "expo-constants";
import * as Haptics from "expo-haptics";
import * as SecureStore from "expo-secure-store";
import { router } from "expo-router";
import { SettingsGroup, SettingsRow, SettingsScreen } from "@/components/settings/primitives";
import { unlockApp } from "@/lib/appLock";
import { useConnectionStore } from "@/stores/useConnectionStore";

const PUSH_REGISTERED_KEY = "shadow_push_registered";

function shortenId(id: string): string {
	if (id.length <= 20) return id;
	return `${id.slice(0, 8)}...${id.slice(-4)}`;
}

export default function SettingsIndexScreen() {
	const {
		nodeUrl,
		deviceId,
		deviceName,
		isPaired,
		appLockEnabled,
		setAppLockEnabled,
		signOut,
	} = useConnectionStore();
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

	const handleCopyDeviceId = async () => {
		if (!deviceId) return;
		await Clipboard.setStringAsync(deviceId);
		await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
	};

	const handleAppLockToggle = async (value: boolean) => {
		if (!value) {
			await setAppLockEnabled(false);
			return;
		}
		try {
			const ok = await unlockApp();
			if (!ok) {
				Alert.alert(
					"App lock unavailable",
					"Biometric authentication or a device passcode is not set up on this device. Enable one in your device settings, then try again.",
				);
				return;
			}
			await setAppLockEnabled(true);
		} catch {
			Alert.alert(
				"App lock unavailable",
				"Could not verify device authentication. Try again.",
			);
		}
	};

	const handleSignOut = () => {
		Alert.alert(
			"Sign out",
			"This removes the pairing between this device and your SHADOW node. You will need to pair again to reconnect.",
			[
				{ text: "Cancel", style: "cancel" },
				{
					text: "Sign out",
					style: "destructive",
					onPress: async () => {
						await signOut();
						router.replace("/onboarding/scan");
					},
				},
			],
		);
	};

	return (
		<SettingsScreen title="Settings" showClose>
			<SettingsGroup>
				<SettingsRow
					title="Node URL"
					value={nodeUrl ?? "Not set"}
					onPress={() => router.push("/settings/node-url")}
				/>
			</SettingsGroup>

			<SettingsGroup>
				<SettingsRow
					title="Device"
					value={deviceName ?? "Unknown"}
				/>
				<SettingsRow
					title="Device ID"
					value={deviceId ? shortenId(deviceId) : "Unknown"}
					onPress={() => void handleCopyDeviceId()}
				/>
				<SettingsRow title="Push notifications" value={pushStatus} />
				<SettingsRow
					title="App lock"
					toggle={appLockEnabled}
					onToggleChange={(value) => void handleAppLockToggle(value)}
				/>
			</SettingsGroup>

			<SettingsGroup>
				<SettingsRow title="App" value="SHADOW" />
				<SettingsRow
					title="Version"
					value={Constants.expoConfig?.version ?? "1.0.0"}
				/>
			</SettingsGroup>

			<SettingsGroup>
				<SettingsRow title="Sign out" destructive onPress={handleSignOut} />
			</SettingsGroup>
		</SettingsScreen>
	);
}
