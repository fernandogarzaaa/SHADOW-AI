/**
 * Pure-TypeScript base64 codec (no dependencies).
 *
 * Used for binary payloads that must travel as text: server TTS audio
 * bytes are base64-encoded before being written to the app cache via
 * expo-file-system.
 */

const ALPHABET =
	"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

const REVERSE: Record<string, number> = {};
for (let i = 0; i < ALPHABET.length; i++) {
	REVERSE[ALPHABET[i]] = i;
}

/** Encode bytes as standard base64 (with padding). */
export function bytesToBase64(bytes: Uint8Array): string {
	let out = "";
	for (let i = 0; i < bytes.length; i += 3) {
		const b0 = bytes[i];
		const b1 = i + 1 < bytes.length ? bytes[i + 1] : 0;
		const b2 = i + 2 < bytes.length ? bytes[i + 2] : 0;
		const n = (b0 << 16) | (b1 << 8) | b2;
		out += ALPHABET[(n >>> 18) & 63];
		out += ALPHABET[(n >>> 12) & 63];
		out += i + 1 < bytes.length ? ALPHABET[(n >>> 6) & 63] : "=";
		out += i + 2 < bytes.length ? ALPHABET[n & 63] : "=";
	}
	return out;
}

/** Decode standard base64 to bytes. Throws on invalid input. */
export function base64ToBytes(input: string): Uint8Array {
	const clean = input.replace(/\s/g, "");
	if (clean.length % 4 !== 0) {
		throw new Error("Invalid base64: length must be a multiple of 4");
	}
	if (!/^[A-Za-z0-9+/]*={0,2}$/.test(clean)) {
		throw new Error("Invalid base64: illegal characters");
	}
	const pad = clean.endsWith("==") ? 2 : clean.endsWith("=") ? 1 : 0;
	const out = new Uint8Array(((clean.length / 4) | 0) * 3 - pad);
	let o = 0;
	for (let i = 0; i < clean.length; i += 4) {
		const n =
			(REVERSE[clean[i]] << 18) |
			(REVERSE[clean[i + 1]] << 12) |
			((REVERSE[clean[i + 2]] ?? 0) << 6) |
			(REVERSE[clean[i + 3]] ?? 0);
		out[o++] = (n >>> 16) & 255;
		if (o < out.length) out[o++] = (n >>> 8) & 255;
		if (o < out.length) out[o++] = n & 255;
	}
	return out;
}
