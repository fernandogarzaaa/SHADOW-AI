import {
	warmSandDarkTheme,
	warmSandLightTheme,
} from "./vendor/themes";

const dark = warmSandDarkTheme.colors;
const light = warmSandLightTheme.colors;

/**
 * Warm Sand Dark Theme Colors
 * Matches the desktop app's default dark theme
 * Primary: #edb449 (golden sand)
 * Background: #151313
 */
export const WarmSandDark = {
	background: dark.surface.background,
	foreground: dark.surface.foreground,
	card: dark.surface.elevated,
	cardForeground: dark.surface.elevatedForeground,
	popover: dark.surface.elevated,
	popoverForeground: dark.surface.elevatedForeground,
	primary: dark.primary.base,
	primaryHover: dark.primary.hover ?? dark.primary.base,
	primaryForeground: dark.primary.foreground ?? dark.surface.background,
	muted: dark.surface.muted,
	mutedForeground: dark.surface.mutedForeground,
	secondary: dark.surface.subtle,
	secondaryForeground: dark.surface.foreground,
	accent: dark.surface.subtle,
	accentForeground: dark.surface.foreground,
	destructive: dark.status.error,
	destructiveForeground: dark.status.errorForeground,
	success: dark.status.success,
	successForeground: dark.status.successForeground,
	info: dark.status.info,
	infoForeground: dark.status.infoForeground,
	warning: dark.status.warning,
	warningForeground: dark.status.warningForeground,
	border: dark.interactive.border,
	input: dark.surface.muted,
	ring: dark.primary.base,
	/** Pale periwinkle bubble for the user's own messages. */
	userBubble: "#2A3350",
	userBubbleForeground: "#EDEFF7",
	/** Soft beige blob behind the agent mark. */
	blob: "#4A4033",
} as const;

/**
 * Warm Sand Light Theme Colors
 * Chat-first companion theme: warm cream background (#F6F1EA) with a
 * single cobalt accent (#0064E0). The accent is reserved for send and
 * primary actions; everything else stays neutral.
 */
export const WarmSandLight = {
	background: "#F6F1EA",
	foreground: light.surface.foreground,
	card: "#FFFFFF",
	cardForeground: light.surface.foreground,
	popover: "#FFFFFF",
	popoverForeground: light.surface.foreground,
	primary: "#0064E0",
	primaryHover: "#0053BC",
	primaryForeground: "#FFFFFF",
	muted: "#ECE7DB",
	mutedForeground: "#6D6860",
	secondary: "#ECE7DB",
	secondaryForeground: light.surface.foreground,
	accent: "#0064E0",
	accentForeground: "#FFFFFF",
	destructive: light.status.error,
	destructiveForeground: light.status.errorForeground,
	success: light.status.success,
	successForeground: light.status.successForeground,
	info: light.status.info,
	infoForeground: light.status.infoForeground,
	warning: light.status.warning,
	warningForeground: light.status.warningForeground,
	border: "#E2DCCF",
	input: "#ECE7DB",
	ring: "#0064E0",
	/** Pale periwinkle bubble for the user's own messages. */
	userBubble: "#E3E9FA",
	userBubbleForeground: "#232838",
	/** Soft beige blob behind the agent mark. */
	blob: "#EDE0C8",
} as const;

export type ThemeColors = typeof WarmSandDark | typeof WarmSandLight;

export function getThemeColors(isDark: boolean): ThemeColors {
	return isDark ? WarmSandDark : WarmSandLight;
}
