import { Tabs } from "expo-router";
import { ChatIcon, CheckIcon, SettingsIcon } from "@/components/icons";
import { useConnectionStore } from "@/stores/useConnectionStore";
import { useTheme } from "@/theme";

const TAB_ICON_SIZE = 24;

/**
 * Chat-first tabs. The Approvals tab exists only while a node is linked;
 * linking and unlinking from Settings adds or removes it live.
 */
export default function TabsLayout() {
	const { colors } = useTheme();
	const isPaired = useConnectionStore((s) => s.isPaired);

	return (
		<Tabs
			initialRouteName="chat"
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
				name="chat"
				options={{
					title: "Chat",
					tabBarIcon: ({ color, size }) => (
						<ChatIcon size={size ?? TAB_ICON_SIZE} color={color} />
					),
				}}
			/>
			<Tabs.Screen
				name="approvals"
				options={{
					title: "Approvals",
					// Hidden entirely when no node is linked.
					href: isPaired ? "/(tabs)/approvals" : null,
					tabBarIcon: ({ color, size }) => (
						<CheckIcon size={size ?? TAB_ICON_SIZE} color={color} />
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
