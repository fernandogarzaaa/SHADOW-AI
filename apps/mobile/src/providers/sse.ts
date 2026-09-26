/**
 * Pure Server-Sent Events framing parser.
 *
 * No React Native dependencies: importable from plain node for unit tests.
 *
 * Splits a growing text buffer into complete SSE events. Each returned
 * event is the concatenation of its `data:` line payloads (per the SSE
 * spec, multiple data lines join with "\n"). Comment lines (`: ...`) and
 * other fields (`event:`, `id:`, `retry:`) are ignored. The trailing
 * incomplete fragment is returned as `rest` so the caller can prepend it
 * to the next chunk.
 */

export interface SseFramingResult {
	/** Complete event payloads (raw data strings, not yet JSON-parsed). */
	events: string[];
	/** Incomplete trailing fragment for the next chunk. */
	rest: string;
}

export function splitSseEvents(buffer: string): SseFramingResult {
	const events: string[] = [];
	// SSE events are separated by a blank line. Handle \r\n too.
	const normalized = buffer.replace(/\r\n/g, "\n");
	const segments = normalized.split("\n\n");
	const rest = segments.pop() ?? "";

	for (const segment of segments) {
		const dataLines: string[] = [];
		for (const rawLine of segment.split("\n")) {
			const line = rawLine.trimEnd();
			if (line.startsWith(":")) {
				continue; // heartbeat / comment
			}
			if (line.startsWith("data:")) {
				dataLines.push(line.slice("data:".length).trimStart());
			}
		}
		if (dataLines.length > 0) {
			events.push(dataLines.join("\n"));
		}
	}

	return { events, rest };
}

/**
 * Stateful incremental parser: feed it the full responseText seen so far
 * (as delivered by XHR onprogress) and it yields only the newly completed
 * events since the last call.
 */
export class IncrementalSseParser {
	private rest = "";
	private seenLength = 0;

	push(fullText: string): string[] {
		const newChunk = fullText.slice(this.seenLength);
		this.seenLength = fullText.length;
		const { events, rest } = splitSseEvents(this.rest + newChunk);
		this.rest = rest;
		return events;
	}

	/** Drain any trailing buffered event at stream end. */
	flush(): string[] {
		if (this.rest.trim().length === 0) {
			return [];
		}
		const { events, rest } = splitSseEvents(`${this.rest}\n\n`);
		this.rest = rest;
		return events;
	}
}
