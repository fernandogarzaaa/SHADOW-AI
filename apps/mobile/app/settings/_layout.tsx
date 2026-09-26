import { Stack } from "expo-router";
import { useTheme } from "@/theme";

export default function SettingsLayout() {
	const { colors } = useTheme();

	return (
		<Stack
			screenOptions={{
				headerShown: false,
				animation: "slide_from_right",
				contentStyle: {
					backgroundColor: colors.background,
				},
			}}
		>
			<Stack.Screen name="index" />
			<Stack.Screen name="link-node" />
			<Stack.Screen name="profile" />
			<Stack.Screen name="avatar" />
			<Stack.Screen name="appearance" />
			<Stack.Screen name="support" />
			<Stack.Screen name="legal" />
			<Stack.Screen name="about" />
		</Stack>
	);
}
