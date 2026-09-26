/**
 * XMLHttpRequest-based streaming transport for provider SSE calls.
 *
 * React Native's fetch exposes no streaming body access, so provider
 * streaming goes through XHR onprogress and reads the growing
 * responseText, the same pattern the node client already uses in
 * src/api/shadow.ts. The adapter layer diffs the full text itself via
 * IncrementalSseParser.
 *
 * No secrets are logged. Non-2xx responses reject with the status and the
 * raw body so the provider can map a typed error.
 */

import type { StreamTransport } from "./types";

interface XhrResult {
	status: number;
	finalText: string;
}

function postStreamXhr(
	url: string,
	init: {
		headers: Record<string, string>;
		body: string;
		signal?: AbortSignal;
		onChunk: (fullText: string) => void;
	},
): Promise<XhrResult> {
	return new Promise<XhrResult>((resolve, reject) => {
		const xhr = new XMLHttpRequest();
		let settled = false;
		const finish = (fn: () => void) => {
			if (settled) return;
			settled = true;
			fn();
		};

		const onAbort = () => {
			finish(() => {
				try {
					xhr.abort();
				} catch {
					// ignore
				}
				const error = new Error("Aborted");
				error.name = "AbortError";
				reject(error);
			});
		};
		init.signal?.addEventListener("abort", onAbort);

		xhr.open("POST", url);
		for (const [name, value] of Object.entries(init.headers)) {
			xhr.setRequestHeader(name, value);
		}

		xhr.onprogress = () => {
			try {
				init.onChunk(xhr.responseText ?? "");
			} catch {
				// Never let a chunk handler kill the stream.
			}
		};

		xhr.onload = () => {
			init.signal?.removeEventListener("abort", onAbort);
			finish(() =>
				resolve({ status: xhr.status, finalText: xhr.responseText ?? "" }),
			);
		};

		xhr.onerror = () => {
			init.signal?.removeEventListener("abort", onAbort);
			finish(() => reject(new Error("Network request failed")));
		};

		xhr.ontimeout = () => {
			init.signal?.removeEventListener("abort", onAbort);
			finish(() => reject(new Error("Network request timed out")));
		};

		try {
			xhr.send(init.body);
		} catch (error) {
			init.signal?.removeEventListener("abort", onAbort);
			finish(() =>
				reject(error instanceof Error ? error : new Error("Network request failed")),
			);
		}
	});
}

export const xhrStreamTransport: StreamTransport = {
	postStream: postStreamXhr,
};
