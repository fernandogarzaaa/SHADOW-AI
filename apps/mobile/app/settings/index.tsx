import BottomSheet from "@gorhom/bottom-sheet";
import * as Clipboard from "expo-clipboard";
import Constants from "expo-constants";
import * as Haptics from "expo-haptics";
import * as SecureStore from "expo-secure-store";
import { router } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { Alert } from "react-native";
import { SettingsGroup, SettingsRow, SettingsScreen } from "@/components/settings/primitives";
import { KeySheet } from "@/components/companion/KeySheet";
import { ModelSheet } from "@/components/companion/ModelSheet";
import { unlockApp } from "@/lib/appLock";
import {
	KEY_PROVIDERS,
	clearAllProviderKeys,
	deleteProviderKey,
	getProvider,
	type ProviderId,
} from "@/providers";
import { useChatStore } from "@/stores/useChatStore";
import { useConnectionStore } from "@/stores/useConnectionStore";
import { useProfileStore } from "@/stores/useProfileStore";
import { useProviderStore } from "@/stores/useProviderStore";

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
	} = useConnectionStore();
	const { providerId, modelId, keyedProviders, setProvider, setModel, refreshKeyPresence } =
		useProviderStore();
	const profile = useProfileStore((s) => s.profile);
	const [pushStatus, setPushStatus] = useState("Checking");
	const [keySheetProvider, setKeySheetProvider] = useState<ProviderId>("anthropic");

	const keySheetRef = useRef<BottomSheet>(null);
	const modelSheetRef = useRef<BottomSheet>(null);

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

	const openKeySheet = useCallback((id: ProviderId) => {
		setKeySheetProvider(id);
		setTimeout(() => keySheetRef.current?.snapToIndex(0), 250);
	}, []);

	const handleKeyRowPress = useCallback(
		(id: ProviderId) => {
			const added = keyedProviders.includes(id);
			const label = getProvider(id).label;
			if (!added) {
				openKeySheet(id);
				return;
			}
			Alert.alert(
				`${label} key`,
				"A key is saved in this phone's secure storage. Replace it or remove it.",
				[
					{ text: "Cancel", style: "cancel" },
					{
						text: "Replace",
						onPress: () => openKeySheet(id),
					},
					{
						text: "Remove",
						style: "destructive",
						onPress: async () => {
							await deleteProviderKey(id);
							await refreshKeyPresence();
						},
					},
				],
			);
		},
		[keyedProviders, openKeySheet, refreshKeyPresence],
	);

	const handleKeySaved = useCallback(async () => {
		keySheetRef.current?.close();
		await refreshKeyPresence();
		await setProvider(keySheetProvider);
	}, [refreshKeyPresence, setProvider, keySheetProvider]);

	const handlePickModel = useCallback(
		async (pickedProvider: ProviderId, pickedModel: string) => {
			modelSheetRef.current?.close();
			if (pickedProvider !== providerId) {
				await setProvider(pickedProvider);
			}
			if (pickedModel !== modelId) {
				await setModel(pickedModel);
			}
			Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
		},
		[providerId, modelId, setProvider, setModel],
	);

	const handleAddKeyFromSheet = useCallback(
		(id: ProviderId) => {
			modelSheetRef.current?.close();
			openKeySheet(id);
		},
		[openKeySheet],
	);

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

	const handleReset = () => {
		Alert.alert(
			"Reset SHADOW",
			"This removes all API keys, chats, and your local profile from this phone. The node link is kept.",
			[
				{ text: "Cancel", style: "cancel" },
				{
					text: "Reset",
					style: "destructive",
					onPress: async () => {
						await clearAllProviderKeys();
						await useProfileStore.getState().clearProfile();
						const chat = useChatStore.getState();
						for (const t of [...chat.threads]) {
							await chat.deleteThread(t.id);
						}
						await refreshKeyPresence();
						router.replace("/onboarding");
					},
				},
			],
		);
	};

	const activeProvider = getProvider(providerId);
	const activeModelLabel =
		activeProvider.models.find((m) => m.id === modelId)?.label ?? modelId;

	return (
		<SettingsScreen title="Settings" showClose>
			<SettingsGroup>
				{KEY_PROVIDERS.map((id) => (
					<SettingsRow
						key={id}
						title={`${getProvider(id).label} key`}
						value={keyedProviders.includes(id) ? "Added" : "Not added"}
						onPress={() => handleKeyRowPress(id)}
					/>
				))}
				<SettingsRow
					title="Model"
					value={`${activeProvider.label} · ${activeModelLabel}`}
					onPress={() => modelSheetRef.current?.snapToIndex(0)}
				/>
			</SettingsGroup>

			<SettingsGroup>
				<SettingsRow
					title="Local profile"
					value={profile.name || (profile.facts.length > 0 ? "Set" : "Not set")}
					onPress={() => router.push("/settings/profile")}
				/>
				<SettingsRow
					title="Appearance"
					onPress={() => router.push("/settings/appearance")}
				/>
			</SettingsGroup>

			<SettingsGroup>
				<SettingsRow
					title="SHADOW node"
					value={isPaired ? (nodeUrl ?? "Linked") : "Not linked"}
					onPress={() => router.push("/settings/link-node")}
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
				<SettingsRow title="Reset SHADOW" destructive onPress={handleReset} />
			</SettingsGroup>

			<KeySheet
				ref={keySheetRef}
				providerId={keySheetProvider}
				onSaved={() => void handleKeySaved()}
			/>
			<ModelSheet
				ref={modelSheetRef}
				onPick={(p, m) => void handlePickModel(p, m)}
				onAddKey={handleAddKeyFromSheet}
			/>
		</SettingsScreen>
	);
}
