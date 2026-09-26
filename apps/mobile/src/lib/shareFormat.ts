/**
 * Pure formatting for share-sheet payloads.
 *
 * Kept free of React Native imports so it is unit-testable in plain
 * node. The native bridge lives in shareReceive.ts.
 */

export interface SharedFile {
	filePath?: string;
	text?: string;
	weblink?: string;
	mimeType?: string;
	fileName?: string;
}

/** Turn a shared payload into chat message text, or null when empty. */
export function messageForSharedFiles(files: SharedFile[]): string | null {
	const parts: string[] = [];
	for (const f of files) {
		if (f.text && f.text.trim()) {
			parts.push(f.text.trim());
		} else if (f.weblink && f.weblink.trim()) {
			parts.push(f.weblink.trim());
		} else if (f.filePath) {
			const name = f.fileName || f.filePath.split("/").pop() || "file";
			const kind = (f.mimeType || "").startsWith("image/") ? "image" : "file";
			parts.push(`[shared ${kind}: ${name}]`);
		}
	}
	const text = parts.join("\n\n").trim();
	return text.length > 0 ? text : null;
}
