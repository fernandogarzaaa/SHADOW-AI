import BottomSheet from "@gorhom/bottom-sheet";
import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useRef } from "react";
import { StyleSheet, View } from "react-native";
import { KeySheet } from "@/components/companion/KeySheet";
import { KEY_PROVIDERS, type ProviderId } from "@/providers";
import { useProviderStore } from "@/stores/useProviderStore";
import { useTheme } from "../../src/theme";

function coerceProviderId(raw: unknown): ProviderId {
	if (typeof raw === "string" && (KEY_PROVIDERS as string[]).includes(raw)) {
		return raw as ProviderId;
	}
	return "anthropic";
}

/** Step 3 of onboarding: paste the API key, validate, save, enter chat. */
export default function KeyEntryScreen() {
	const { colors } = useTheme();
	const { providerId: rawId } = useLocalSearchParams<{ providerId?: string }>();
	const providerId = coerceProviderId(rawId);
	const sheetRef = useRef<BottomSheet>(null);

	useEffect(() => {
		const timer = setTimeout(() => {
			sheetRef.current?.snapToIndex(0);
		}, 350);
		return () => clearTimeout(timer);
	}, []);

	async function handleSaved() {
		await useProviderStore.getState().initialize();
		await useProviderStore.getState().setProvider(providerId);
		router.replace("/onboarding/personality");
	}

	return (
		<View style={[styles.container, { backgroundColor: colors.background }]}>
			<KeySheet
				ref={sheetRef}
				providerId={providerId}
				onSaved={handleSaved}
				onClose={() => router.back()}
			/>
		</View>
	);
}

const styles = StyleSheet.create({
	container: {
		flex: 1,
	},
});
