import BottomSheet from "@gorhom/bottom-sheet";
import * as Haptics from "expo-haptics";
import * as SecureStore from "expo-secure-store";
import { router } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { Alert } from "react-native";
import { SettingsGroup, SettingsRow, SettingsScreen } from "@/components/settings/primitives";
import { KeySheet } from "@/components/companion/KeySheet";
import { ModelSheet } from "@/components/companion/ModelSheet";
import {
	AiAgentIcon,
	BellIcon,
	BrainIcon,
	CloudIcon,
	DocumentIcon,
	HelpIcon,
	InfoIcon,
	KeyIcon,
	LockIcon,
	MoonIcon,
	TrashIcon,
	UsersIcon,
} from "@/components/icons";
import { getAvatar } from "@/avatars";
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
import { useTheme } from "@/theme";

const PUSH_REGISTERED_KEY = "shadow_push_registered";
const ICON_SIZE = 18;

/**
 * Settings, regrouped around what the app actually does: chat (provider,
 * model, keys), personal (avatar, personality), the optional node link,
 * preferences, support, legal, about, and a data reset. Every row leads
 * to real behavior; nothing here is decorative.
 */
export default function SettingsIndexScreen() {
	const { colors } = useTheme();
	const {
		nodeUrl,
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
	const avatarLabel = getAvatar(profile.avatarId).label;

	return (
		<SettingsScreen title="Settings" showClose>
			<SettingsGroup>
				<SettingsRow
					title="Model"
					value={`${activeProvider.label} · ${activeModelLabel}`}
					icon={<BrainIcon size={ICON_SIZE} color={colors.foreground} />}
					onPress={() => modelSheetRef.current?.snapToIndex(0)}
				/>
				{KEY_PROVIDERS.map((id) => (
					<SettingsRow
						key={id}
						title={`${getProvider(id).label} key`}
						value={keyedProviders.includes(id) ? "Added" : "Not added"}
						icon={<KeyIcon size={ICON_SIZE} color={colors.foreground} />}
						onPress={() => handleKeyRowPress(id)}
					/>
				))}
			</SettingsGroup>

			<SettingsGroup>
				<SettingsRow
					title="Avatar"
					value={avatarLabel}
					icon={<AiAgentIcon size={ICON_SIZE} color={colors.foreground} />}
					onPress={() => router.push("/settings/avatar")}
				/>
				<SettingsRow
					title="Personality and profile"
					value={profile.name || (profile.facts.length > 0 ? "Set" : "Not set")}
					icon={<UsersIcon size={ICON_SIZE} color={colors.foreground} />}
					onPress={() => router.push("/settings/profile")}
				/>
			</SettingsGroup>

			<SettingsGroup>
				<SettingsRow
					title="SHADOW node"
					value={isPaired ? (nodeUrl ?? "Linked") : "Not linked"}
					icon={<CloudIcon size={ICON_SIZE} color={colors.foreground} />}
					onPress={() => router.push("/settings/link-node")}
				/>
			</SettingsGroup>

			<SettingsGroup>
				<SettingsRow
					title="Appearance"
					value={undefined}
					icon={<MoonIcon size={ICON_SIZE} color={colors.foreground} />}
					onPress={() => router.push("/settings/appearance")}
				/>
				<SettingsRow
					title="Push notifications"
					value={pushStatus}
					icon={<BellIcon size={ICON_SIZE} color={colors.foreground} />}
				/>
				<SettingsRow
					title="App lock"
					icon={<LockIcon size={ICON_SIZE} color={colors.foreground} />}
					toggle={appLockEnabled}
					onToggleChange={(value) => void handleAppLockToggle(value)}
				/>
			</SettingsGroup>

			<SettingsGroup>
				<SettingsRow
					title="Support"
					icon={<HelpIcon size={ICON_SIZE} color={colors.foreground} />}
					onPress={() => router.push("/settings/support")}
				/>
			</SettingsGroup>

			<SettingsGroup>
				<SettingsRow
					title="Legal"
					icon={<DocumentIcon size={ICON_SIZE} color={colors.foreground} />}
					onPress={() => router.push("/settings/legal")}
				/>
				<SettingsRow
					title="About"
					icon={<InfoIcon size={ICON_SIZE} color={colors.foreground} />}
					onPress={() => router.push("/settings/about")}
				/>
			</SettingsGroup>

			<SettingsGroup>
				<SettingsRow
					title="Reset SHADOW"
					destructive
					icon={<TrashIcon size={ICON_SIZE} color={colors.destructive} />}
					onPress={handleReset}
				/>
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
