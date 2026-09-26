import * as Device from "expo-device";
import { CameraView, useCameraPermissions } from "expo-camera";
import * as Haptics from "expo-haptics";
import { router } from "expo-router";
import { Platform } from "react-native";
import { useEffect, useState } from "react";
import {
	ActivityIndicator,
	Pressable,
	StyleSheet,
	Text,
	View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { CameraIcon, ChevronLeftIcon } from "@/components/icons";
import { Button } from "@/components/ui";
import { useConnectionStore } from "@/stores/useConnectionStore";
import { Spacing, typography, useTheme } from "../../src/theme";

/**
 * SHADOW pairing QR payload contract:
 *   {"v":1,"url":"http://192.168.1.10:8000","pairing_id":"..."}
 */

interface QrPayload {
	v?: unknown;
	url?: unknown;
	pairing_id?: unknown;
}

function parseQrPayload(data: string): { url: string; pairingId: string } | null {
	let parsed: QrPayload;
	try {
		parsed = JSON.parse(data) as QrPayload;
	} catch {
		return null;
	}
	if (
		parsed.v !== 1 ||
		typeof parsed.url !== "string" ||
		parsed.url.length === 0 ||
		typeof parsed.pairing_id !== "string" ||
		parsed.pairing_id.length === 0
	) {
		return null;
	}
	return { url: parsed.url, pairingId: parsed.pairing_id };
}

function defaultDeviceName(): string {
	const name = Device.deviceName ?? Device.modelName ?? null;
	if (name && name.trim().length > 0) {
		return name.trim();
	}
	return Platform.OS === "ios" ? "SHADOW iOS" : "SHADOW Android";
}

function BackButton({ light }: { light?: boolean }) {
	const { colors } = useTheme();
	const color = light ? "#fff" : colors.foreground;

	return (
		<Pressable
			onPress={() => {
				Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
				router.back();
			}}
			style={({ pressed }) => [styles.backBtn, pressed && { opacity: 0.6 }]}
			hitSlop={8}
		>
			<ChevronLeftIcon size={18} color={color} />
			<Text style={[typography.uiLabel, { color }]}>Back</Text>
		</Pressable>
	);
}

function ScannerFrame() {
	const { colors } = useTheme();

	return (
		<View style={styles.frame}>
			<View style={[styles.cornerTL, { borderColor: colors.primary }]} />
			<View style={[styles.cornerTR, { borderColor: colors.primary }]} />
			<View style={[styles.cornerBL, { borderColor: colors.primary }]} />
			<View style={[styles.cornerBR, { borderColor: colors.primary }]} />
		</View>
	);
}

export default function ScanScreen() {
	const insets = useSafeAreaInsets();
	const { colors } = useTheme();
	const [permission, requestPermission] = useCameraPermissions();
	const [scanned, setScanned] = useState(false);
	const [invalidCode, setInvalidCode] = useState(false);
	const { pair, pairing, pairError } = useConnectionStore();

	useEffect(() => {
		if (!permission?.granted) {
			requestPermission();
		}
	}, [permission, requestPermission]);

	async function handleBarCodeScanned({ data }: { data: string }) {
		if (scanned || pairing) return;

		setScanned(true);
		setInvalidCode(false);
		await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);

		const payload = parseQrPayload(data);
		if (!payload) {
			setInvalidCode(true);
			setScanned(false);
			return;
		}

		try {
			await pair(payload.url, payload.pairingId, defaultDeviceName());
			Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
			router.replace("/settings/link-node");
		} catch {
			// pairError from the store is shown inline below.
			setScanned(false);
		}
	}

	if (!permission) {
		return (
			<View style={[styles.centered, { backgroundColor: colors.background }]}>
				<ActivityIndicator size="small" color={colors.primary} />
			</View>
		);
	}

	if (!permission.granted) {
		return (
			<View style={[styles.container, { backgroundColor: colors.background }]}>
				<View
					style={{
						paddingTop: insets.top + Spacing.md,
						paddingHorizontal: Spacing.lg,
					}}
				>
					<BackButton />
				</View>

				<View style={styles.permissionContent}>
					<CameraIcon size={48} color={colors.mutedForeground} />

					<Text
						style={[
							typography.h2,
							{ color: colors.foreground, marginTop: 24, textAlign: "center" },
						]}
					>
						Camera Access Required
					</Text>
					<Text
						style={[
							typography.meta,
							styles.permissionText,
							{ color: colors.mutedForeground },
						]}
					>
						SHADOW needs camera access to scan the pairing QR code shown on your node.
					</Text>

					<Button
						variant="primary"
						size="lg"
						onPress={() => {
							Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
							requestPermission();
						}}
						style={{ marginTop: 24 }}
					>
						<Button.Label>Grant Permission</Button.Label>
					</Button>
				</View>
			</View>
		);
	}

	return (
		<View
			style={[styles.cameraContainer, { backgroundColor: colors.background }]}
		>
			<View style={[styles.cameraHeader, { top: insets.top + Spacing.md }]}>
				<BackButton light />
			</View>

			<CameraView
				style={styles.camera}
				facing="back"
				barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
				onBarcodeScanned={scanned ? undefined : handleBarCodeScanned}
			/>

			<View style={styles.overlay}>
				<ScannerFrame />
			</View>

			<View
				style={[
					styles.bottomPanel,
					{
						backgroundColor: colors.background,
						paddingBottom: insets.bottom + Spacing.lg,
					},
				]}
			>
				<Text
					style={[
						typography.uiLabel,
						{
							color: colors.foreground,
							fontWeight: "600",
							textAlign: "center",
						},
					]}
				>
					Scan Pairing Code
				</Text>
				<Text
					style={[
						typography.meta,
						{
							color: colors.mutedForeground,
							textAlign: "center",
							marginTop: 8,
						},
					]}
				>
					Point the camera at the QR code shown by your SHADOW node
				</Text>

				{pairing && (
					<Text
						style={[
							typography.meta,
							{ color: colors.primary, textAlign: "center", marginTop: 12 },
						]}
					>
						Pairing with your node...
					</Text>
				)}

				{invalidCode && (
					<Text
						style={[
							typography.meta,
							{ color: colors.error, textAlign: "center", marginTop: 12 },
						]}
					>
						That is not a SHADOW pairing code. Please scan the QR code shown by your node.
					</Text>
				)}

				{pairError && (
					<Text
						style={[
							typography.meta,
							{ color: colors.error, textAlign: "center", marginTop: 12 },
						]}
					>
						{pairError}
					</Text>
				)}
			</View>
		</View>
	);
}

const styles = StyleSheet.create({
	container: {
		flex: 1,
	},
	centered: {
		flex: 1,
		alignItems: "center",
		justifyContent: "center",
	},
	backBtn: {
		flexDirection: "row",
		alignItems: "center",
		gap: 6,
		alignSelf: "flex-start",
		paddingVertical: 8,
		paddingRight: 12,
	},
	permissionContent: {
		flex: 1,
		alignItems: "center",
		justifyContent: "center",
		paddingHorizontal: Spacing.lg,
	},
	permissionText: {
		textAlign: "center",
		marginTop: 12,
		maxWidth: 280,
		lineHeight: 20,
	},
	cameraContainer: {
		flex: 1,
	},

	cameraHeader: {
		position: "absolute",
		left: 0,
		right: 0,
		zIndex: 10,
		paddingHorizontal: Spacing.lg,
	},
	camera: {
		flex: 1,
	},
	overlay: {
		...StyleSheet.absoluteFillObject,
		alignItems: "center",
		justifyContent: "center",
	},
	frame: {
		width: 256,
		height: 256,
	},
	cornerTL: {
		position: "absolute",
		left: 0,
		top: 0,
		width: 40,
		height: 40,
		borderLeftWidth: 3,
		borderTopWidth: 3,
		borderTopLeftRadius: 12,
	},
	cornerTR: {
		position: "absolute",
		right: 0,
		top: 0,
		width: 40,
		height: 40,
		borderRightWidth: 3,
		borderTopWidth: 3,
		borderTopRightRadius: 12,
	},
	cornerBL: {
		position: "absolute",
		left: 0,
		bottom: 0,
		width: 40,
		height: 40,
		borderLeftWidth: 3,
		borderBottomWidth: 3,
		borderBottomLeftRadius: 12,
	},
	cornerBR: {
		position: "absolute",
		right: 0,
		bottom: 0,
		width: 40,
		height: 40,
		borderRightWidth: 3,
		borderBottomWidth: 3,
		borderBottomRightRadius: 12,
	},
	bottomPanel: {
		position: "absolute",
		bottom: 0,
		left: 0,
		right: 0,
		borderTopLeftRadius: 20,
		borderTopRightRadius: 20,
		paddingHorizontal: Spacing.lg,
		paddingTop: Spacing.lg,
	},
});
