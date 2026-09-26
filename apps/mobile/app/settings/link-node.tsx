import * as Haptics from "expo-haptics";
import { router } from "expo-router";
import { Alert, Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { SettingsGroup, SettingsRow, SettingsScreen } from "@/components/settings/primitives";
import { useConnectionStore } from "@/stores/useConnectionStore";
import { Spacing, typography, useTheme } from "../../src/theme";

/**
 * Optional node linking. Linking unlocks the Approvals tab and the
 * SHADOW node chat provider; everything else works without it.
 */
export default function LinkNodeScreen() {
	const { colors } = useTheme();
	const insets = useSafeAreaInsets();
	const { isPaired, nodeUrl, deviceName, signOut } = useConnectionStore();

	const handleUnlink = () => {
		Alert.alert(
			"Unlink node",
			"This removes the pairing between this device and your SHADOW node. The Approvals tab will disappear until you link again.",
			[
				{ text: "Cancel", style: "cancel" },
				{
					text: "Unlink",
					style: "destructive",
					onPress: async () => {
						await signOut();
						router.back();
					},
				},
			],
		);
	};

	if (isPaired) {
		return (
			<SettingsScreen title="SHADOW node">
				<SettingsGroup>
					<SettingsRow title="Status" value="Linked" />
					<SettingsRow title="Node URL" value={nodeUrl ?? "Unknown"} />
					<SettingsRow title="Device name" value={deviceName ?? "Unknown"} />
				</SettingsGroup>
				<SettingsGroup>
					<SettingsRow title="Unlink node" destructive onPress={handleUnlink} />
				</SettingsGroup>
			</SettingsScreen>
		);
	}

	return (
		<View
			style={[
				styles.container,
				{
					backgroundColor: colors.background,
					paddingTop: insets.top,
					paddingBottom: Math.max(insets.bottom, Spacing.xl),
				},
			]}
		>
			<View style={styles.body}>
				<Text style={[typography.h1, { color: colors.foreground }]}>
					Link your node
				</Text>
				<Text style={[typography.body, { color: colors.mutedForeground, marginTop: Spacing.md }]}>
					Linking is optional. It unlocks the Approvals tab and lets you
					chat with your node's agent, which knows about your approvals
					and automations.
				</Text>
				<Text style={[typography.body, { color: colors.mutedForeground, marginTop: Spacing.md }]}>
					Show the pairing QR code on your SHADOW node, then scan it here.
				</Text>
			</View>

			<View style={styles.footer}>
				<Pressable
					onPress={() => {
						Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
						router.push("/onboarding/scan");
					}}
					style={[styles.cta, { backgroundColor: colors.primary }]}
					accessibilityRole="button"
					accessibilityLabel="Scan pairing QR code"
				>
					<Text
						style={[
							typography.uiLabel,
							{ color: colors.primaryForeground, fontWeight: "700" },
						]}
					>
						Scan QR code
					</Text>
				</Pressable>
				<Pressable
					onPress={() => {
						Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
						router.push("/onboarding/manual");
					}}
					style={styles.secondary}
					accessibilityRole="button"
					accessibilityLabel="Enter pairing details manually"
				>
					<Text style={[typography.uiLabel, { color: colors.primary, fontWeight: "600" }]}>
						Enter details manually
					</Text>
				</Pressable>
			</View>
		</View>
	);
}

const styles = StyleSheet.create({
	container: {
		flex: 1,
		paddingHorizontal: Spacing.xl,
	},
	body: {
		flex: 1,
		justifyContent: "center",
	},
	footer: {
		gap: Spacing.sm,
	},
	cta: {
		borderRadius: 16,
		paddingVertical: 16,
		alignItems: "center",
	},
	secondary: {
		paddingVertical: 12,
		alignItems: "center",
	},
});
