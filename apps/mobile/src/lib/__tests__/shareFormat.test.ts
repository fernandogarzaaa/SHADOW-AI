/**
 * Unit tests for share-sheet payload formatting (shareFormat).
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { messageForSharedFiles } from "../shareFormat";

describe("messageForSharedFiles", () => {
	it("returns null for empty input", () => {
		assert.equal(messageForSharedFiles([]), null);
		assert.equal(messageForSharedFiles([{}]), null);
		assert.equal(messageForSharedFiles([{ text: "   " }]), null);
	});

	it("prefers text content", () => {
		assert.equal(
			messageForSharedFiles([{ text: "hello world", filePath: "/x.jpg" }]),
			"hello world",
		);
	});

	it("uses weblinks when no text", () => {
		assert.equal(
			messageForSharedFiles([{ weblink: "https://example.com/a" }]),
			"https://example.com/a",
		);
	});

	it("labels media files when only a path is shared", () => {
		assert.equal(
			messageForSharedFiles([
				{ filePath: "/sdcard/DCIM/pic.jpg", mimeType: "image/jpeg" },
			]),
			"[shared image: pic.jpg]",
		);
		assert.equal(
			messageForSharedFiles([
				{ filePath: "/sdcard/doc.pdf", mimeType: "application/pdf" },
			]),
			"[shared file: doc.pdf]",
		);
	});

	it("joins multiple shared items", () => {
		assert.equal(
			messageForSharedFiles([
				{ text: "first" },
				{ weblink: "https://example.com" },
			]),
			"first\n\nhttps://example.com",
		);
	});
});
