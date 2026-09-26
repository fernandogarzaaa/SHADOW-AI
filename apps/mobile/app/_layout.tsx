import "../src/styles/index.css";

import { BottomSheetModalProvider } from "@gorhom/bottom-sheet";
import { useFonts } from "expo-font";
import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { Button } from "../src/components/ui";
import {
	setupApprovalNotificationCategories,
	startApprovalNotificationResponses,
} from "../src/lib/approvalNotifications";
import { setupAppIntents } from "../src/lib/appIntents";
import { setupShareReceive } from "../src/lib/shareReceive";
import { LockIcon } from "../src/components/icons";
import { unlockApp } from "../src/lib/appLock";
import { useConnectionStore } from "../src/stores/useConnectionStore";
import { Spacing, typography, ThemeProvider, useTheme } from "../src/theme";

// Keep the splash screen visible until we explicitly hide it
// This MUST be called at module level (not inside components) to work reliably in preview builds
SplashScreen.preventAutoHideAsync();

function RootLayoutContent() {
	const { colors, isDark } = useTheme();

	return (
		<>
			<Stack
				screenOptions={{
					headerShown: false,
					contentStyle: {
						backgroundColor: colors.background,
					},
					animation: "slide_from_right",
				}}
			>
				<Stack.Screen name="index" />
				<Stack.Screen name="onboarding" />
				<Stack.Screen name="(tabs)" options={{ headerShown: false }} />
				<Stack.Screen
					name="settings"
					options={{
						presentation: "fullScreenModal",
						animation: "slide_from_bottom",
					}}
				/>
			</Stack>
			<StatusBar style={isDark ? "light" : "dark"} />
		</>
	);
}

function UnlockScreen({ onUnlocked }: { onUnlocked: () => void }) {
	const { colors } = useTheme();
	const [failed, setFailed] = useState(false);
	const [unlocking, setUnlocking] = useState(false);

	const attempt = useCallback(async () => {
		if (unlocking) return;
		setUnlocking(true);
		setFailed(false);
		const ok = await unlockApp();
		setUnlocking(false);
		if (ok) {
			onUnlocked();
		} else {
			setFailed(true);
		}
	}, [unlocking, onUnlocked]);

	useEffect(() => {
		attempt();
	}, [attempt]);

	return (
		<View style={[styles.unlockContainer, { backgroundColor: colors.background }]}>
			<LockIcon size={44} color={colors.mutedForeground} />
			<Text style={[typography.h2, { color: colors.foreground, marginTop: Spacing.lg, textAlign: "center" }]}>
				SHADOW is locked
			</Text>
			<Text style={[typography.meta, { color: colors.mutedForeground, marginTop: Spacing.sm, textAlign: "center" }]}>
				Authenticate to continue.
			</Text>
			{failed && (
				<Text style={[typography.meta, { color: colors.error, marginTop: Spacing.md, textAlign: "center" }]}>
					Authentication did not succeed. Try again.
				</Text>
			)}
			<Button
				variant="primary"
				size="lg"
				onPress={attempt}
				isLoading={unlocking}
				style={{ marginTop: Spacing.xl, width: 200 }}
			>
				<Button.Label>{unlocking ? "Unlocking..." : "Unlock"}</Button.Label>
			</Button>
		</View>
	);
}

export default function RootLayout() {
	/* eslint-disable @typescript-eslint/no-require-imports -- Metro bundler requires static require() for assets */
	const [fontsLoaded, fontError] = useFonts({
		// Sans fonts - for UI text (headers, labels, buttons, settings)
		"IBMPlexSans-Regular": require("../assets/fonts/IBMPlexSans-Regular.ttf"),
		"IBMPlexSans-Medium": require("../assets/fonts/IBMPlexSans-Medium.ttf"),
		"IBMPlexSans-SemiBold": require("../assets/fonts/IBMPlexSans-SemiBold.ttf"),
		"IBMPlexSans-Bold": require("../assets/fonts/IBMPlexSans-Bold.ttf"),
		// Mono fonts - for code blocks and technical content
		"IBMPlexMono-Regular": require("../assets/fonts/IBMPlexMono-Regular.ttf"),
		"IBMPlexMono-Medium": require("../assets/fonts/IBMPlexMono-Medium.ttf"),
		"IBMPlexMono-SemiBold": require("../assets/fonts/IBMPlexMono-SemiBold.ttf"),
		"IBMPlexMono-Bold": require("../assets/fonts/IBMPlexMono-Bold.ttf"),
	});
	/* eslint-enable @typescript-eslint/no-require-imports */

	const restore = useConnectionStore((s) => s.restore);
	const restored = useConnectionStore((s) => s.restored);
	const isPaired = useConnectionStore((s) => s.isPaired);
	const appLockEnabled = useConnectionStore((s) => s.appLockEnabled);
	const [unlocked, setUnlocked] = useState(false);

	// Restore the pairing from SecureStore on app launch.
	useEffect(() => {
		restore();
	}, [restore]);

	// Approval notification actions: register the Approve / Deny category and
	// route notification responses (decide in place, or deep-link on tap).
	useEffect(() => {
		setupApprovalNotificationCategories();
		const subscription = startApprovalNotificationResponses();
		return () => subscription.remove();
	}, []);

	// App Intents (Siri / Spotlight / Shortcuts / Assistant): route
	// invocations that opened the app into chat actions.
	useEffect(() => {
		void setupAppIntents();
	}, []);

	// Share sheet (Android): shared text/links from other apps arrive here.
	useEffect(() => {
		return setupShareReceive();
	}, []);

	// Reset the unlock gate whenever pairing is removed.
	useEffect(() => {
		if (!isPaired) {
			setUnlocked(false);
		}
	}, [isPaired]);

	useEffect(() => {
		if (fontError) {
			console.error("Font loading error:", fontError);
		}
		if (fontsLoaded) {
			console.log("Fonts loaded successfully");
		}
		if ((fontsLoaded || fontError) && restored) {
			SplashScreen.hideAsync();
		}
	}, [fontsLoaded, fontError, restored]);

	const ready = (fontsLoaded || fontError) && restored;
	const needsUnlock = ready && isPaired && appLockEnabled && !unlocked;

	// Don't render until fonts are loaded and the connection is restored
	if (!ready) {
		return null;
	}

	return (
		<GestureHandlerRootView style={{ flex: 1 }}>
			<BottomSheetModalProvider>
				<SafeAreaProvider>
					<ThemeProvider>
						{needsUnlock ? (
							<UnlockScreen onUnlocked={() => setUnlocked(true)} />
						) : (
							<RootLayoutContent />
						)}
					</ThemeProvider>
				</SafeAreaProvider>
			</BottomSheetModalProvider>
		</GestureHandlerRootView>
	);
}

const styles = StyleSheet.create({
	unlockContainer: {
		flex: 1,
		alignItems: "center",
		justifyContent: "center",
		paddingHorizontal: Spacing.xl,
	},
});
