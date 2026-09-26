/**
 * Codegen config for @avasapp/react-native-app-intents.
 *
 * - `npx app-intents generate` reads this file and emits native surfaces
 *   (Swift App Intents + App Shortcuts, Android shortcuts + App Actions).
 * - The Expo plugin (`@avasapp/react-native-app-intents` in app.config.js)
 *   auto-loads this same file at prebuild time.
 *
 * The bundle/package id tracks the APP_VARIANT build variant, mirroring
 * app.config.js, so preview and dev prebuilds never get production
 * native identifiers.
 */

import { defineAppIntentsConfig } from "@avasapp/react-native-app-intents/codegen";

const variant = process.env.APP_VARIANT ?? "production";

function appId(): string {
	if (variant === "development") return "ai.shadow.app.dev";
	if (variant === "preview") return "ai.shadow.app.preview";
	return "ai.shadow.app";
}

export default defineAppIntentsConfig({
	intents: ["src/intents/**/*.intents.ts"],
	scheme: "shadow",
	ios: {
		// Written under the generated iOS project folder at prebuild.
		output: "ShadowAppIntents.swift",
		bundleIdentifier: appId(),
		siriUsageDescription:
			"Allow Siri to run SHADOW actions like asking a question or saving a memory.",
	},
	android: {
		packageName: appId(),
	},
});
