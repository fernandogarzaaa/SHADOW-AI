import type { BottomTabBarProps } from "@react-navigation/bottom-tabs";
import * as Haptics from "expo-haptics";
import { BlurView } from "expo-blur";
import { router, Tabs, type Href } from "expo-router";
import type { ReactNode } from "react";
import { Platform, Pressable, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import {
	BulbIcon,
	ChatIcon,
	CheckIcon,
	SettingsIcon,
} from "@/components/icons";
import { useConnectionStore } from "@/stores/useConnectionStore";
import { SemanticSpacing, Spacing, useTheme } from "@/theme";
import { withOpacity } from "@/utils/colors";

const TAB_ICON_SIZE = 24;

const TAB_ICONS: Record<
	string,
	(props: { size: number; color: string }) => ReactNode
> = {
	chat: (p) => <ChatIcon {...p} />,
	briefing: (p) => <BulbIcon {...p} />,
	approvals: (p) => <CheckIcon {...p} />,
	settings: (p) => <SettingsIcon {...p} />,
};

/**
 * Floating pill tab bar: a blurred capsule that hovers over content with
 * the active tab wrapped in a darker pill. Screens scroll underneath it.
 */
function FloatingTabBar({ state, descriptors, navigation }: BottomTabBarProps) {
	const { colors, isDark } = useTheme();
	const insets = useSafeAreaInsets();

	// Routes with href: null are hidden from the bar (the Approvals tab
	// while no node is linked). expo-router extends the tab options with
	// href at runtime, so read it through a narrow cast.
	const visible = state.routes.filter(
		(route) =>
			(descriptors[route.key].options as { href?: string | null }).href !==
			null,
	);

	return (
		<View
			pointerEvents="box-none"
			style={[styles.float, { bottom: Math.max(insets.bottom, 12) }]}
		>
			<BlurView
				intensity={isDark ? 60 : 80}
				tint={isDark ? "dark" : "light"}
				style={[
					styles.pill,
					{
						borderColor: colors.border,
						// Translucent fill under the blur, derived from the theme
						// card color so the bar tracks theme changes.
						backgroundColor: withOpacity(colors.card, 0.72),
						// Shadow tinted to the foreground hue; never pure black.
						...Platform.select({
							ios: { shadowColor: withOpacity(colors.foreground, 0.25) },
							android: {},
							default: {},
						}),
					},
				]}
			>
				{visible.map((route) => {
					const { options } = descriptors[route.key];
					const tabHref = (
						options as { href?: Href | null }
					).href;
					const isFocused = state.routes[state.index].key === route.key;
					const Icon = TAB_ICONS[route.name];
					const label =
						typeof options.title === "string" ? options.title : route.name;

					const onPress = () => {
						const event = navigation.emit({
							type: "tabPress",
							target: route.key,
							canPreventDefault: true,
						});
						if (event.defaultPrevented) {
							return;
						}
						Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
						if (
							typeof tabHref === "string" &&
							tabHref !== `/(tabs)/${route.name}`
						) {
							// Cross-navigator destination (the Settings modal):
							// expo-router's default tab bar wraps these in a Link,
							// but this custom bar must follow the href itself.
							router.push(tabHref as Href);
						} else if (!isFocused) {
							navigation.navigate(route.name as never);
						}
					};

					const onLongPress = () => {
						navigation.emit({ type: "tabLongPress", target: route.key });
					};

					return (
						<Pressable
							key={route.key}
							onPress={onPress}
							onLongPress={onLongPress}
							accessibilityRole="button"
							accessibilityState={{ selected: isFocused }}
							accessibilityLabel={label}
							style={({ pressed }) => [
								styles.tab,
								isFocused && [
									styles.tabActive,
									{ backgroundColor: colors.muted },
								],
								{ opacity: pressed ? 0.7 : 1 },
							]}
						>
							{Icon ? (
								<Icon
									size={TAB_ICON_SIZE}
									color={isFocused ? colors.foreground : colors.mutedForeground}
								/>
							) : null}
						</Pressable>
					);
				})}
			</BlurView>
		</View>
	);
}

/**
 * Chat-first tabs: Chat (chats list), Briefing, Approvals (only while a
 * node is linked), Settings.
 */
export default function TabsLayout() {
	const isPaired = useConnectionStore((s) => s.isPaired);

	return (
		<Tabs
			initialRouteName="chat"
			tabBar={(props) => <FloatingTabBar {...props} />}
			screenOptions={{ headerShown: false }}
		>
			<Tabs.Screen
				name="chat"
				options={{ title: "Chat", href: "/(tabs)/chat" as Href }}
			/>
			<Tabs.Screen
				name="briefing"
				options={{ title: "Briefing", href: "/(tabs)/briefing" as Href }}
			/>
			<Tabs.Screen
				name="approvals"
				options={{
					title: "Approvals",
					// Hidden entirely when no node is linked.
					href: (isPaired ? "/(tabs)/approvals" : null) as Href | null,
				}}
			/>
			<Tabs.Screen
				name="settings"
				options={{ title: "Settings", href: "/settings" as Href }}
			/>
		</Tabs>
	);
}

const styles = StyleSheet.create({
	float: {
		position: "absolute",
		left: 0,
		right: 0,
		alignItems: "center",
	},
	pill: {
		flexDirection: "row",
		alignItems: "center",
		borderRadius: 999,
		borderWidth: StyleSheet.hairlineWidth,
		paddingHorizontal: Spacing.sm,
		paddingVertical: 6,
		gap: 4,
		...Platform.select({
			ios: {
				shadowOpacity: 0.15,
				shadowRadius: 16,
				shadowOffset: { width: 0, height: 4 },
			},
			android: { elevation: 8 },
			default: {},
		}),
	},
	tab: {
		width: 64,
		height: SemanticSpacing.buttonHeightMd + 12,
		borderRadius: 999,
		alignItems: "center",
		justifyContent: "center",
	},
	tabActive: {
		// Darker pill behind the active icon, via backgroundColor above.
	},
});
