/**
 * Pure SSE (Server-Sent Events) chunk parser.
 *
 * No React Native dependencies: importable from plain node for unit tests.
 *
 * The SHADOW node streams events as `data: {json}\n\n` where each JSON
 * payload is an envelope of shape `{ type: string; properties: unknown }`.
 * Lines starting with `:` are heartbeat comments and are ignored.
 */

export interface ParsedSseEvent {
	type: string;
	properties: unknown;
}

export interface SseChunkResult {
	/** Fully received events found in this chunk. */
	events: ParsedSseEvent[];
	/** Incomplete trailing data to prepend to the next chunk. */
	rest: string;
}

/**
 * Parse one chunk of SSE text.
 *
 * Splits the buffer on `\n\n` (event boundaries). All complete events are
 * parsed and returned; the trailing incomplete fragment is returned as
 * `rest` so the caller can prepend it to the next chunk.
 */
export function parseSseChunk(buffer: string): SseChunkResult {
	const events: ParsedSseEvent[] = [];
	const segments = buffer.split("\n\n");
	const rest = segments.pop() ?? "";

	for (const segment of segments) {
		let data: string | null = null;

		for (const rawLine of segment.split("\n")) {
			const line = rawLine.trimEnd();

			// Heartbeat comment (e.g. `:heartbeat`), ignore.
			if (line.startsWith(":")) {
				continue;
			}

			// Other SSE fields (id:, event:, retry:) are not used by the node.
			if (!line.startsWith("data:")) {
				continue;
			}

			const payload = line.slice("data:".length).trimStart();
			data = data === null ? payload : data + "\n" + payload;
		}

		if (data === null || data === "") {
			continue;
		}

		try {
			const parsed = JSON.parse(data) as {
				type?: unknown;
				properties?: unknown;
			};
			if (typeof parsed.type !== "string") {
				continue;
			}
			events.push({
				type: parsed.type,
				properties: parsed.properties ?? null,
			});
		} catch {
			// Malformed envelope: skip rather than poison the stream.
		}
	}

	return { events, rest };
}
