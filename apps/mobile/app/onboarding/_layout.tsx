import { Stack } from "expo-router";

export default function OnboardingLayout() {
	return (
		<Stack
			screenOptions={{
				headerShown: false,
				animation: "slide_from_right",
			}}
		>
			<Stack.Screen name="index" />
			<Stack.Screen name="provider" />
			<Stack.Screen name="key" />
			<Stack.Screen name="personality" />
			<Stack.Screen name="scan" />
			<Stack.Screen name="manual" />
		</Stack>
	);
}
