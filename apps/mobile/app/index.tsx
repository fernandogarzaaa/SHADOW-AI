import { Redirect } from "expo-router";
import { useEffect, useState } from "react";
import { View } from "react-native";
import { SplashScreen } from "../src/components/ui/SplashScreen";
import { hasProviderKey, KEY_PROVIDERS } from "../src/providers";
import { useConnectionStore } from "../src/stores/useConnectionStore";
import { useProviderStore } from "../src/stores/useProviderStore";
import { useProfileStore } from "../src/stores/useProfileStore";
import { useChatStore } from "../src/stores/useChatStore";
import { useDeepLinkAuth } from "../src/hooks/useDeepLinkAuth";
import { useTheme } from "../src/theme";

export default function Index() {
	const { initialize, isInitialized, isPaired } = useConnectionStore();
	const initializeProviders = useProviderStore((s) => s.initialize);
	const initializeProfile = useProfileStore((s) => s.initialize);
	const initializeChat = useChatStore((s) => s.initialize);
	const { colors } = useTheme();
	const [isLoading, setIsLoading] = useState(true);
	const [hasKey, setHasKey] = useState(false);
	const [showSplash, setShowSplash] = useState(true);

	// Handle deep link authentication (URL with token parameter)
	const { isProcessing: isProcessingDeepLink } = useDeepLinkAuth({
		onAuthSuccess: (serverUrl) => {
			console.log(`[Index] Deep link auth successful for: ${serverUrl}`);
		},
		onAuthError: (error) => {
			console.error(`[Index] Deep link auth failed:`, error.message);
		},
	});

	useEffect(() => {
		async function init() {
			await Promise.all([
				initialize(),
				initializeProviders(),
				initializeProfile(),
				initializeChat(),
			]);
			const keyed = await Promise.all(
				KEY_PROVIDERS.map((p) => hasProviderKey(p).catch(() => false)),
			);
			const hasAnyKey = keyed.some(Boolean);
			setHasKey(hasAnyKey);
			// Node-only users land in chat with the node as their provider,
			// not a keyless default that would fail on send.
			if (!hasAnyKey && useConnectionStore.getState().isPaired) {
				await useProviderStore.getState().setProvider("node");
			}
			setIsLoading(false);
		}
		init();
	}, [initialize, initializeProviders, initializeProfile, initializeChat]);

	// Wait for initialization and deep link processing before showing content
	const isReady = !isLoading && isInitialized && !isProcessingDeepLink;

	// Show splash screen while loading
	if (showSplash) {
		return (
			<View style={{ flex: 1, backgroundColor: colors.background }}>
				<SplashScreen
					isReady={isReady}
					onComplete={() => setShowSplash(false)}
				/>
			</View>
		);
	}

	// Chat is home. Onboarding (provider key entry) runs only when the user
	// has neither a provider key nor a linked node.
	if (hasKey || isPaired) {
		return <Redirect href="/(tabs)/chat" />;
	}

	return <Redirect href="/onboarding" />;
}
