/**
 * Unit tests for App Intent routing (intentRouting).
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { routeForIntent } from "../intentRouting";
import { askShadow, openShadow, rememberThis } from "../../intents/shadow.intents";

describe("routeForIntent", () => {
	it("routes askShadow with a prompt to the ask action", () => {
		const route = routeForIntent({
			id: askShadow.id,
			params: { prompt: "what is the weather" },
		});
		assert.deepEqual(route, { kind: "ask", prompt: "what is the weather" });
	});

	it("falls back to open when the ask prompt is empty", () => {
		const route = routeForIntent({ id: askShadow.id, params: { prompt: "   " } });
		assert.deepEqual(route, { kind: "open" });
	});

	it("routes rememberThis with text to the remember action", () => {
		const route = routeForIntent({
			id: rememberThis.id,
			params: { text: "buy milk" },
		});
		assert.deepEqual(route, { kind: "remember", text: "buy milk" });
	});

	it("falls back to open when remember text is missing", () => {
		const route = routeForIntent({ id: rememberThis.id, params: {} });
		assert.deepEqual(route, { kind: "open" });
	});

	it("routes openShadow to open", () => {
		assert.deepEqual(routeForIntent({ id: openShadow.id, params: {} }), {
			kind: "open",
		});
	});

	it("routes unknown intent ids to unknown", () => {
		assert.deepEqual(routeForIntent({ id: "nope", params: {} }), {
			kind: "unknown",
		});
	});

	it("trims whitespace from params", () => {
		const route = routeForIntent({
			id: askShadow.id,
			params: { prompt: "  hello  " },
		});
		assert.deepEqual(route, { kind: "ask", prompt: "hello" });
	});
});
