import { Tabs } from "expo-router";
import { ChatIcon, CheckIcon, SettingsIcon } from "@/components/icons";
import { useTheme } from "@/theme";

const TAB_ICON_SIZE = 24;

export default function TabsLayout() {
	const { colors } = useTheme();

	return (
		<Tabs
			initialRouteName="approvals"
			screenOptions={{
				headerShown: false,
				tabBarActiveTintColor: colors.primary,
				tabBarInactiveTintColor: colors.mutedForeground,
				tabBarStyle: {
					backgroundColor: colors.card,
					borderTopColor: colors.border,
				},
			}}
		>
			<Tabs.Screen
				name="approvals"
				options={{
					title: "Approvals",
					tabBarIcon: ({ color, size }) => (
						<CheckIcon size={size ?? TAB_ICON_SIZE} color={color} />
					),
				}}
			/>
			<Tabs.Screen
				name="chat"
				options={{
					title: "Chat",
					tabBarIcon: ({ color, size }) => (
						<ChatIcon size={size ?? TAB_ICON_SIZE} color={color} />
					),
				}}
			/>
			<Tabs.Screen
				name="settings"
				options={{
					title: "Settings",
					href: "/settings",
					tabBarIcon: ({ color, size }) => (
						<SettingsIcon size={size ?? TAB_ICON_SIZE} color={color} />
					),
				}}
			/>
			{/* Legacy template tabs: keep the routes reachable but hide them from the bar */}
			<Tabs.Screen name="diff" options={{ href: null }} />
			<Tabs.Screen name="files" options={{ href: null }} />
			<Tabs.Screen name="git" options={{ href: null }} />
			<Tabs.Screen name="terminal" options={{ href: null }} />
		</Tabs>
	);
}
