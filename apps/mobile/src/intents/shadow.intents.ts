/**
 * SHADOW App Intents: the actions Siri, Spotlight, Shortcuts (iOS) and
 * Assistant / App Actions (Android) can invoke.
 *
 * Direction of travel is assistant -> SHADOW: there is no API for an app
 * to send work *to* Siri or the Gemini app, so SHADOW publishes these
 * intents and the OS assistants call into them.
 *
 * Codegen: `npx app-intents generate` (config: app-intents.config.ts).
 * The Expo plugin runs the same codegen at prebuild time.
 */

import { defineIntent, p } from "@avasapp/react-native-app-intents";

/**
 * "Hey Siri, ask Shadow ..." — opens SHADOW with the spoken prompt and
 * sends it as a new chat message.
 */
export const askShadow = defineIntent({
	id: "askShadow",
	title: "Ask Shadow",
	description: "Ask your Shadow AI companion anything. Opens SHADOW and sends your question as a new chat message.",
	phrases: ["Ask Shadow ${prompt}", "Ask ${.applicationName} ${prompt}"],
	params: {
		prompt: p.string({
			title: "Question",
			prompt: "What do you want to ask Shadow?",
			requestValueDialog: "What should I ask Shadow?",
			androidBiiParam: "feature",
		}),
	},
	behavior: { opensAppToForeground: true },
	ios: { appIntent: {} },
	android: {
		appAction: {
			capability: "actions.intent.OPEN_APP_FEATURE",
			fulfillment: "deeplink",
		},
	},
	surfaces: {
		spotlight: true,
		appShortcut: {
			icon: { systemName: "message", androidResourceName: "@mipmap/ic_launcher_round" },
		},
	},
});

/**
 * "Hey Siri, remember this in Shadow" — captures a thought, link, or
 * snippet into SHADOW as a new chat message the agent can file away.
 */
export const rememberThis = defineIntent({
	id: "rememberThis",
	title: "Remember this in Shadow",
	description: "Save a thought, link, or snippet to Shadow. Opens SHADOW and files it as a new message.",
	phrases: [
		"Remember ${text} in Shadow",
		"Save ${text} to ${.applicationName}",
		"Remember this in ${.applicationName}",
	],
	params: {
		text: p.string({
			title: "Thing to remember",
			prompt: "What should Shadow remember?",
			requestValueDialog: "What should I remember?",
		}),
	},
	behavior: { opensAppToForeground: true },
	ios: { appIntent: {} },
	surfaces: {
		spotlight: true,
		appShortcut: {
			icon: { systemName: "bookmark", androidResourceName: "@mipmap/ic_launcher_round" },
		},
	},
});

/**
 * "Hey Siri, open Shadow" — plain launcher shortcut.
 */
export const openShadow = defineIntent({
	id: "openShadow",
	title: "Open Shadow",
	description: "Open the Shadow AI companion.",
	phrases: ["Open ${.applicationName}"],
	params: {},
	behavior: { opensAppToForeground: true },
	ios: { appIntent: {} },
	android: {
		appAction: {
			capability: "actions.intent.OPEN_APP_FEATURE",
			fulfillment: "deeplink",
		},
	},
	surfaces: {
		appShortcut: {
			icon: { systemName: "app", androidResourceName: "@mipmap/ic_launcher_round" },
		},
	},
});

export const shadowIntents = [askShadow, rememberThis, openShadow] as const;
