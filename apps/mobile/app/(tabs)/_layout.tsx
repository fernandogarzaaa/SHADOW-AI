import type { BottomTabBarProps } from "@react-navigation/bottom-tabs";
import * as Haptics from "expo-haptics";
import { BlurView } from "expo-blur";
import { LinearGradient } from "expo-linear-gradient";
import { router, Tabs, type Href } from "expo-router";
import type { ReactNode } from "react";
import { Platform, Pressable, StyleSheet, View, useWindowDimensions } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import {
	BookOpenIcon,
	BulbIcon,
	ChatIcon,
	CheckIcon,
	DocumentIcon,
	ImageIcon,
	ListCheckIcon,
	SettingsIcon,
} from "@/components/icons";
import { useConnectionStore } from "@/stores/useConnectionStore";
import { SemanticSpacing, Spacing, useTheme } from "@/theme";
import { withOpacity } from "@/utils/colors";

const TAB_ICON_SIZE = 24;
/** Preferred tab width; shrinks when many tabs are visible (see below). */
const TAB_WIDTH_PREFERRED = 64;
const TAB_WIDTH_MIN = 40;
const TAB_GAP = 4;

const TAB_ICONS: Record<
	string,
	(props: { size: number; color: string }) => ReactNode
> = {
	chat: (p) => <ChatIcon {...p} />,
	briefing: (p) => <BulbIcon {...p} />,
	feed: (p) => <BookOpenIcon {...p} />,
	goals: (p) => <ListCheckIcon {...p} />,
	approvals: (p) => <CheckIcon {...p} />,
	artifacts: (p) => <DocumentIcon {...p} />,
	media: (p) => <ImageIcon {...p} />,
	settings: (p) => <SettingsIcon {...p} />,
};

/**
 * Floating pill tab bar: a blurred capsule that hovers over content with
 * the active tab wrapped in a darker pill. Screens scroll underneath it.
 */
function FloatingTabBar({ state, descriptors, navigation }: BottomTabBarProps) {
	const { colors, isDark } = useTheme();
	const insets = useSafeAreaInsets();
	const { width: screenWidth } = useWindowDimensions();

	// Routes with href: null are hidden from the bar (the Approvals tab
	// while no node is linked). expo-router extends the tab options with
	// href at runtime, so read it through a narrow cast.
	const visible = state.routes.filter(
		(route) =>
			(descriptors[route.key].options as { href?: string | null }).href !==
			null,
	);

	// Eight destinations share the bar when paired. Keep the pill inside the
	// screen by shrinking the per-tab width: preferred 64pt, down to a 40pt
	// minimum before the pill itself would overflow a narrow phone.
	const pillHorizontalPadding = Spacing.sm * 2;
	const gaps = Math.max(visible.length - 1, 0) * TAB_GAP;
	const available = screenWidth - 24 - pillHorizontalPadding - gaps;
	const tabWidth = Math.max(
		TAB_WIDTH_MIN,
		Math.min(TAB_WIDTH_PREFERRED, Math.floor(available / Math.max(visible.length, 1))),
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
				{/* Specular top edge: the Liquid Glass light catch. */}
				<LinearGradient
					pointerEvents="none"
					colors={[
						isDark ? withOpacity("#FFFFFF", 0.18) : withOpacity("#FFFFFF", 0.8),
						"transparent",
					]}
					style={styles.specular}
				/>
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
								{ width: tabWidth },
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
 * Chat-first tabs: Chat (chats list), Briefing, Feed, Goals, Approvals,
 * Artifacts, and Media (the last five only while a node is linked),
 * Settings.
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
				name="feed"
				options={{
					title: "Feed",
					// The feed lives on the node; hidden entirely when no node is linked.
					href: (isPaired ? "/(tabs)/feed" : null) as Href | null,
				}}
			/>
			<Tabs.Screen
				name="goals"
				options={{
					title: "Goals",
					// Goals live on the node; hidden entirely when no node is linked.
					href: (isPaired ? "/(tabs)/goals" : null) as Href | null,
				}}
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
				name="artifacts"
				options={{
					title: "Artifacts",
					// Artifacts live on the node; hidden entirely when no node is linked.
					href: (isPaired ? "/(tabs)/artifacts" : null) as Href | null,
				}}
			/>
			<Tabs.Screen
				name="media"
				options={{
					title: "Media",
					// Generated images live on the node; hidden entirely when no node is linked.
					href: (isPaired ? "/(tabs)/media" : null) as Href | null,
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
		height: SemanticSpacing.buttonHeightMd + 12,
		borderRadius: 999,
		alignItems: "center",
		justifyContent: "center",
	},
	specular: {
		position: "absolute",
		top: 0,
		left: 0,
		right: 0,
		height: 28,
		borderTopLeftRadius: 999,
		borderTopRightRadius: 999,
	},
	tabActive: {
		// Darker pill behind the active icon, via backgroundColor above.
	},
});
