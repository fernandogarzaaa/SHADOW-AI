/**
 * Typed provider errors with user-facing copy.
 *
 * Copy rules: friendly, no em dashes, never leak key material or raw
 * provider payloads into the message shown to the user.
 */

export type ProviderErrorCode =
	| "invalid_key"
	| "rate_limited"
	| "quota"
	| "bad_request"
	| "server"
	| "network"
	| "aborted"
	| "unknown";

export class ProviderError extends Error {
	readonly code: ProviderErrorCode;
	readonly status?: number;

	constructor(code: ProviderErrorCode, message: string, status?: number) {
		super(message);
		this.name = "ProviderError";
		this.code = code;
		this.status = status;
	}
}

/**
 * Map an HTTP failure to a typed ProviderError. `bodyText` is used only to
 * detect well-known shapes; it is never embedded in the user message.
 */
export function mapHttpError(
	status: number,
	bodyText: string,
	providerLabel: string,
): ProviderError {
	const body = bodyText.toLowerCase();
	if (status === 401 || status === 403) {
		return new ProviderError(
			"invalid_key",
			`Your ${providerLabel} key was rejected. Check the key and try again.`,
			status,
		);
	}
	if (status === 429) {
		return new ProviderError(
			"rate_limited",
			`${providerLabel} rate-limited the request. Wait a moment and try again.`,
			status,
		);
	}
	if (status === 402 || body.includes("insufficient_quota") || body.includes("billing")) {
		return new ProviderError(
			"quota",
			`Your ${providerLabel} account is out of credit or quota. Top up billing on their site, then retry.`,
			status,
		);
	}
	if (status >= 400 && status < 500) {
		return new ProviderError(
			"bad_request",
			`${providerLabel} rejected the request. If this keeps happening, try a different model.`,
			status,
		);
	}
	if (status >= 500) {
		return new ProviderError(
			"server",
			`${providerLabel} had a server error. Try again in a bit.`,
			status,
		);
	}
	return new ProviderError(
		"unknown",
		`Something went wrong talking to ${providerLabel}. Try again.`,
		status,
	);
}

export function toProviderError(error: unknown, providerLabel: string): ProviderError {
	if (error instanceof ProviderError) {
		return error;
	}
	if (error instanceof Error) {
		if (error.name === "AbortError" || /aborted/i.test(error.message)) {
			return new ProviderError("aborted", "Cancelled.");
		}
		if (/network|fetch failed|failed to fetch|econnrefused|timed out|timeout/i.test(error.message)) {
			return new ProviderError(
				"network",
				"Could not reach the network. Check your connection and try again.",
			);
		}
		return new ProviderError(
			"unknown",
			`Something went wrong talking to ${providerLabel}. Try again.`,
		);
	}
	return new ProviderError(
		"unknown",
		`Something went wrong talking to ${providerLabel}. Try again.`,
	);
}
