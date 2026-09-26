/**
 * Pure intent -> navigation-action mapping for App Intents.
 *
 * Kept free of Expo / React Native imports so it is unit-testable in
 * plain node. The side-effectful runtime lives in appIntents.ts.
 */

import { askShadow, openShadow, rememberThis } from "../intents/shadow.intents";

export type IntentRoute =
	| { kind: "ask"; prompt: string }
	| { kind: "remember"; text: string }
	| { kind: "open" }
	| { kind: "unknown" };

export interface IntentEventLike {
	id: string;
	params: Record<string, unknown>;
}

/**
 * Map an intent invocation to the in-app action. Empty prompts fall
 * back to just opening the app.
 */
export function routeForIntent(event: IntentEventLike): IntentRoute {
	switch (event.id) {
		case askShadow.id: {
			const prompt =
				typeof event.params.prompt === "string" ? event.params.prompt.trim() : "";
			return prompt ? { kind: "ask", prompt } : { kind: "open" };
		}
		case rememberThis.id: {
			const text =
				typeof event.params.text === "string" ? event.params.text.trim() : "";
			return text ? { kind: "remember", text } : { kind: "open" };
		}
		case openShadow.id:
			return { kind: "open" };
		default:
			return { kind: "unknown" };
	}
}
