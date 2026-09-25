import * as Device from "expo-device";
import * as Haptics from "expo-haptics";
import { router } from "expo-router";
import { useState } from "react";
import {
	KeyboardAvoidingView,
	Platform,
	Pressable,
	ScrollView,
	StyleSheet,
	Text,
	View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { ChevronLeftIcon } from "@/components/icons";
import { Button, Input } from "@/components/ui";
import { useConnectionStore } from "@/stores/useConnectionStore";
import { Spacing, typography, useTheme } from "../../src/theme";

function defaultDeviceName(): string {
	const name = Device.deviceName ?? Device.modelName ?? null;
	if (name && name.trim().length > 0) {
		return name.trim();
	}
	return Platform.OS === "ios" ? "SHADOW iOS" : "SHADOW Android";
}

function BackButton() {
	const { colors } = useTheme();

	return (
		<Pressable
			onPress={() => {
				Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
				router.back();
			}}
			style={({ pressed }) => [styles.backBtn, pressed && { opacity: 0.6 }]}
			hitSlop={8}
		>
			<ChevronLeftIcon size={18} color={colors.foreground} />
			<Text style={[typography.uiLabel, { color: colors.foreground }]}>
				Back
			</Text>
		</Pressable>
	);
}

export default function ManualScreen() {
	const insets = useSafeAreaInsets();
	const { colors } = useTheme();
	const [nodeUrl, setNodeUrl] = useState("");
	const [pairingCode, setPairingCode] = useState("");
	const [deviceName, setDeviceName] = useState(defaultDeviceName());
	const [fieldError, setFieldError] = useState<string | null>(null);
	const { pair, pairing, pairError } = useConnectionStore();

	async function handlePair() {
		if (!nodeUrl.trim()) {
			setFieldError("Enter your node's URL, for example http://192.168.1.10:8000");
			return;
		}
		if (!pairingCode.trim()) {
			setFieldError("Enter the pairing code shown by your SHADOW node");
			return;
		}
		setFieldError(null);

		Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);

		try {
			await pair(nodeUrl, pairingCode, deviceName);
			Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
			router.replace("/(tabs)/approvals");
		} catch {
			Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
			// pairError from the store is shown inline below.
		}
	}

	return (
		<KeyboardAvoidingView
			behavior={Platform.OS === "ios" ? "position" : "height"}
			style={[styles.container, { backgroundColor: colors.background }]}
			keyboardVerticalOffset={insets.top + Spacing.sm}
		>
			<ScrollView
				style={styles.scrollView}
				contentContainerStyle={{
					paddingTop: insets.top + Spacing.md,
					paddingBottom: insets.bottom + Spacing.xl,
					paddingHorizontal: Spacing.lg,
					flexGrow: 1,
				}}
				keyboardShouldPersistTaps="handled"
				showsVerticalScrollIndicator={false}
			>
				<BackButton />

				<Text
					style={[
						typography.h2,
						{ color: colors.foreground, marginTop: Spacing.md },
					]}
				>
					Pair with your node
				</Text>
				<Text
					style={[
						typography.meta,
						{ color: colors.mutedForeground, marginTop: 8, lineHeight: 20 },
					]}
				>
					Enter the node URL and the pairing code shown in your SHADOW node.
				</Text>

				<View style={styles.field}>
					<Input
						label="Node URL"
						value={nodeUrl}
						onChangeText={setNodeUrl}
						placeholder="http://192.168.1.10:8000"
						autoCapitalize="none"
						autoCorrect={false}
						keyboardType="url"
						helperText="Your node's local address and port"
					/>
				</View>

				<View style={styles.field}>
					<Input
						label="Pairing code"
						value={pairingCode}
						onChangeText={setPairingCode}
						placeholder="Paste the pairing code"
						autoCapitalize="none"
						autoCorrect={false}
					/>
				</View>

				<View style={styles.field}>
					<Input
						label="Device name"
						value={deviceName}
						onChangeText={setDeviceName}
						placeholder="SHADOW mobile"
						autoCapitalize="none"
						autoCorrect={false}
					/>
				</View>

				{(fieldError || pairError) && (
					<Text
						style={[
							typography.meta,
							{ color: colors.error, marginTop: Spacing.md, lineHeight: 20 },
						]}
					>
						{fieldError ?? pairError}
					</Text>
				)}

				<View style={styles.actionArea}>
					<Button
						variant="primary"
						size="lg"
						onPress={handlePair}
						isDisabled={pairing}
						isLoading={pairing}
						style={{ width: "100%" }}
					>
						<Button.Label>{pairing ? "Pairing..." : "Pair"}</Button.Label>
					</Button>
				</View>
			</ScrollView>
		</KeyboardAvoidingView>
	);
}

const styles = StyleSheet.create({
	container: {
		flex: 1,
	},
	scrollView: {
		flex: 1,
	},
	backBtn: {
		flexDirection: "row",
		alignItems: "center",
		gap: 6,
		alignSelf: "flex-start",
		paddingVertical: 8,
		paddingRight: 12,
	},
	field: {
		marginTop: 24,
	},
	actionArea: {
		marginTop: "auto",
		paddingTop: 32,
	},
});
