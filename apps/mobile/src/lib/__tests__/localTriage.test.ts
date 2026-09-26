/**
 * Unit tests for on-device LLM triage (localTriage).
 *
 * The native module is injected as a fake; these tests cover prompt
 * building, local-first fallback routing, and graceful degradation.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
	getLocalLLMAvailability,
	quickCompleteLocalFirst,
	smartRepliesPrompt,
	summarizePrompt,
	threadTitlePrompt,
} from "../localTriage";

describe("localTriage prompts", () => {
	it("builds a bounded thread-title prompt", () => {
		const prompt = threadTitlePrompt("hello world");
		assert.match(prompt, /max 5 words/);
		assert.match(prompt, /hello world/);
	});

	it("truncates long inputs", () => {
		const long = "x".repeat(5000);
		assert.ok(threadTitlePrompt(long).length < 500);
		assert.ok(smartRepliesPrompt(long).length < 900);
		assert.ok(summarizePrompt(long).length < 2200);
	});

	it("builds the smart-replies prompt", () => {
		const prompt = smartRepliesPrompt("the sky is blue");
		assert.match(prompt, /3 short follow-up/);
		assert.match(prompt, /the sky is blue/);
	});
});

describe("quickCompleteLocalFirst", () => {
	it("prefers the local result when available", async () => {
		let cloudCalls = 0;
		const result = await quickCompleteLocalFirst(
			"prompt",
			24,
			async () => {
				cloudCalls += 1;
				return "cloud";
			},
			async () => "local",
		);
		assert.equal(result, "local");
		assert.equal(cloudCalls, 0);
	});

	it("falls back to cloud when local returns null", async () => {
		const result = await quickCompleteLocalFirst(
			"prompt",
			24,
			async () => "cloud",
			async () => null,
		);
		assert.equal(result, "cloud");
	});

	it("falls back to cloud when local throws", async () => {
		const result = await quickCompleteLocalFirst(
			"prompt",
			24,
			async () => "cloud",
			async () => {
				throw new Error("native missing");
			},
		);
		assert.equal(result, "cloud");
	});

	it("returns null when both fail", async () => {
		const result = await quickCompleteLocalFirst(
			"prompt",
			24,
			async () => null,
			async () => null,
		);
		assert.equal(result, null);
	});

	it("returns null when cloud throws", async () => {
		const result = await quickCompleteLocalFirst(
			"prompt",
			24,
			async () => {
				throw new Error("no key");
			},
			async () => null,
		);
		assert.equal(result, null);
	});
});

describe("getLocalLLMAvailability", () => {
	it("degrades gracefully without a native module", async () => {
		// In plain node there is no native runtime; the function must not
		// throw, whatever the loader does.
		const status = await getLocalLLMAvailability();
		assert.equal(typeof status.available, "boolean");
		if (!status.available) {
			assert.equal(typeof status.reason, "string");
		}
	});
});
