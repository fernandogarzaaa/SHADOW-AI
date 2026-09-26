/**
 * Typed SecureStore module for BYOK provider API keys.
 *
 * Keys live ONLY here. Never in AsyncStorage, never in a database, never
 * in logs, never in model context. The only operations are create, read
 * (into memory for a single request), and delete.
 */

import * as SecureStore from "expo-secure-store";
import type { ProviderId } from "./types";

const KEY_PREFIX = "shadow_byok_key_";

function storeKey(provider: ProviderId): string {
	return `${KEY_PREFIX}${provider}`;
}

export class KeyStoreError extends Error {
	constructor(message: string) {
		super(message);
		this.name = "KeyStoreError";
	}
}

function requireKeyProvider(provider: ProviderId): void {
	if (provider === "node") {
		throw new KeyStoreError("The SHADOW node provider does not use an API key.");
	}
}

/** Read the stored key for a provider, or null when none is saved. */
export async function getProviderKey(provider: ProviderId): Promise<string | null> {
	requireKeyProvider(provider);
	try {
		return await SecureStore.getItemAsync(storeKey(provider));
	} catch {
		throw new KeyStoreError("Could not read the saved key. Try again.");
	}
}

/**
 * Save (or replace) the key for a provider. Trims whitespace; rejects
 * empty input with a typed error so callers can show friendly copy.
 */
export async function setProviderKey(provider: ProviderId, rawKey: string): Promise<void> {
	requireKeyProvider(provider);
	const key = rawKey.trim();
	if (key.length === 0) {
		throw new KeyStoreError("Paste your API key first.");
	}
	try {
		await SecureStore.setItemAsync(storeKey(provider), key);
	} catch {
		throw new KeyStoreError("Could not save the key. Try again.");
	}
}

/** Delete the stored key for a provider. */
export async function deleteProviderKey(provider: ProviderId): Promise<void> {
	requireKeyProvider(provider);
	try {
		await SecureStore.deleteItemAsync(storeKey(provider));
	} catch {
		throw new KeyStoreError("Could not remove the key. Try again.");
	}
}

/** True when a key is stored for the provider. Presence only, never the key. */
export async function hasProviderKey(provider: ProviderId): Promise<boolean> {
	const key = await getProviderKey(provider);
	return key !== null && key.length > 0;
}

/** Remove every stored BYOK key. Used by the settings reset flow. */
export async function clearAllProviderKeys(): Promise<void> {
	await Promise.all(
		(["anthropic", "openai"] as const).map((p) =>
			SecureStore.deleteItemAsync(storeKey(p)).catch(() => undefined),
		),
	);
}
